from datetime import date
from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from apps.materia_prima import services as materia_prima_services
from apps.materia_prima.models import MateriaPrima, UnidadMedida
from apps.usuarios.models import Usuario

from . import services
from .models import MovimientoInventarioProductoTerminado, Producto, Produccion


def crear_usuario(username, rol):
    return Usuario.objects.create_user(username=username, password="ClaveSegura123!", rol=rol)


class RegistrarProduccionTests(APITestCase):
    def setUp(self):
        self.admin = crear_usuario("admin_prod", Usuario.Rol.ADMIN)
        self.trabajador = crear_usuario("trab_prod", Usuario.Rol.TRABAJADOR)
        self.harina = MateriaPrima.objects.create(nombre="Harina P", unidad_medida=UnidadMedida.LB)
        self.levadura = MateriaPrima.objects.create(nombre="Levadura P", unidad_medida=UnidadMedida.OZ)
        materia_prima_services.registrar_compra(
            materia_prima_id=self.harina.id,
            lote="H-1",
            cantidad=Decimal("100"),
            unidad_medida="LB",
            costo_total=Decimal("400"),  # Q4/lb
            fecha_compra=date.today(),
            creado_por=self.admin,
        )
        materia_prima_services.registrar_compra(
            materia_prima_id=self.levadura.id,
            lote="Y-1",
            cantidad=Decimal("32"),
            unidad_medida="OZ",
            costo_total=Decimal("64"),  # Q2/oz
            fecha_compra=date.today(),
            creado_por=self.admin,
        )
        self.producto = Producto.objects.create(nombre="Pan Francés", precio_unitario=Decimal("1.50"))

    def test_registrar_produccion_consume_materia_prima_y_calcula_costo(self):
        produccion = services.registrar_produccion(
            producto_id=self.producto.id,
            fecha=date.today(),
            cantidad_planificada=Decimal("500"),
            cantidad_producida=Decimal("450"),
            cantidad_merma=Decimal("10"),
            consumos=[
                {"materia_prima_id": self.harina.id, "cantidad": Decimal("20"), "unidad_medida": "LB"},
                {"materia_prima_id": self.levadura.id, "cantidad": Decimal("8"), "unidad_medida": "OZ"},
            ],
            creado_por=self.trabajador,
        )
        # 20 lb x Q4 + 8 oz x Q2 = Q80 + Q16 = Q96
        self.assertEqual(produccion.costo_total, Decimal("96"))
        self.assertEqual(produccion.costo_unitario, Decimal("96") / Decimal("450"))

        self.harina.refresh_from_db()
        self.levadura.refresh_from_db()
        self.assertEqual(self.harina.stock_actual, Decimal("80"))
        self.assertEqual(self.levadura.stock_actual, Decimal("24"))

    def test_produccion_ingresa_al_inventario_de_producto_terminado_neto_de_merma(self):
        services.registrar_produccion(
            producto_id=self.producto.id,
            fecha=date.today(),
            cantidad_planificada=Decimal("500"),
            cantidad_producida=Decimal("450"),
            cantidad_merma=Decimal("10"),
            consumos=[
                {"materia_prima_id": self.harina.id, "cantidad": Decimal("20"), "unidad_medida": "LB"},
            ],
            creado_por=self.admin,
        )
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_actual, Decimal("440"))
        movimientos = MovimientoInventarioProductoTerminado.objects.filter(producto=self.producto)
        self.assertEqual(movimientos.count(), 2)
        tipos = set(movimientos.values_list("tipo", flat=True))
        self.assertEqual(
            tipos, {MovimientoInventarioProductoTerminado.Tipo.PRODUCCION, MovimientoInventarioProductoTerminado.Tipo.MERMA}
        )

    def test_no_permite_consumir_mas_materia_prima_de_la_disponible(self):
        with self.assertRaises(Exception):
            services.registrar_produccion(
                producto_id=self.producto.id,
                fecha=date.today(),
                cantidad_planificada=Decimal("10000"),
                cantidad_producida=Decimal("10000"),
                cantidad_merma=Decimal("0"),
                consumos=[
                    {"materia_prima_id": self.harina.id, "cantidad": Decimal("999999"), "unidad_medida": "LB"},
                ],
                creado_por=self.trabajador,
            )
        # Nada debe quedar registrado: ni la producción, ni el consumo de materia prima.
        self.assertEqual(Produccion.objects.count(), 0)
        self.harina.refresh_from_db()
        self.assertEqual(self.harina.stock_actual, Decimal("100"))

    def test_merma_no_puede_superar_cantidad_producida(self):
        with self.assertRaises(Exception):
            services.registrar_produccion(
                producto_id=self.producto.id,
                fecha=date.today(),
                cantidad_planificada=Decimal("10"),
                cantidad_producida=Decimal("10"),
                cantidad_merma=Decimal("11"),
                consumos=[
                    {"materia_prima_id": self.harina.id, "cantidad": Decimal("1"), "unidad_medida": "LB"},
                ],
                creado_por=self.admin,
            )

    def test_api_admin_puede_registrar_produccion(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post(
            "/api/v1/produccion/producciones/",
            {
                "producto": self.producto.id,
                "fecha": str(date.today()),
                "cantidad_planificada": "100",
                "cantidad_producida": "100",
                "cantidad_merma": "0",
                "consumos": [
                    {"materia_prima_id": self.harina.id, "cantidad": "5", "unidad_medida": "LB"}
                ],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertIn("costo_total", resp.data)
        self.assertNotIn("creado_por", resp.data)

    def test_api_trabajador_puede_registrar_produccion_pero_respuesta_sin_costos(self):
        self.client.force_authenticate(user=self.trabajador)
        resp = self.client.post(
            "/api/v1/produccion/producciones/",
            {
                "producto": self.producto.id,
                "fecha": str(date.today()),
                "cantidad_planificada": "100",
                "cantidad_producida": "100",
                "cantidad_merma": "0",
                "consumos": [
                    {"materia_prima_id": self.harina.id, "cantidad": "5", "unidad_medida": "LB"}
                ],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertNotIn("costo_total", resp.data)
        self.assertNotIn("costo_unitario", resp.data)
        self.assertNotIn("creado_por", resp.data)
        for consumo in resp.data["consumos"]:
            self.assertNotIn("costo_correspondiente", consumo)

    def test_api_cliente_no_tiene_acceso(self):
        cliente = crear_usuario("cli_prod", Usuario.Rol.CLIENTE)
        self.client.force_authenticate(user=cliente)
        resp = self.client.get("/api/v1/produccion/producciones/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_produccion_no_admite_edicion_ni_borrado(self):
        produccion = services.registrar_produccion(
            producto_id=self.producto.id,
            fecha=date.today(),
            cantidad_planificada=Decimal("10"),
            cantidad_producida=Decimal("10"),
            cantidad_merma=Decimal("0"),
            consumos=[{"materia_prima_id": self.harina.id, "cantidad": Decimal("1"), "unidad_medida": "LB"}],
            creado_por=self.admin,
        )
        self.client.force_authenticate(user=self.admin)
        resp = self.client.delete(f"/api/v1/produccion/producciones/{produccion.id}/")
        self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        resp = self.client.patch(
            f"/api/v1/produccion/producciones/{produccion.id}/", {"cantidad_producida": "999"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class ProductoVisibilidadTests(APITestCase):
    def setUp(self):
        self.admin = crear_usuario("admin_pt", Usuario.Rol.ADMIN)
        self.trabajador = crear_usuario("trab_pt", Usuario.Rol.TRABAJADOR)
        self.repartidor = crear_usuario("rep_pt", Usuario.Rol.REPARTIDOR)
        self.producto = Producto.objects.create(nombre="Champurrada", precio_unitario=Decimal("0.75"))

    def test_admin_ve_precio_y_stock(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get(f"/api/v1/produccion/{self.producto.id}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("precio_unitario", resp.data)
        self.assertIn("stock_actual", resp.data)

    def test_trabajador_no_ve_precio_ni_stock(self):
        self.client.force_authenticate(user=self.trabajador)
        resp = self.client.get(f"/api/v1/produccion/{self.producto.id}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertNotIn("precio_unitario", resp.data)
        self.assertNotIn("stock_actual", resp.data)

    def test_repartidor_no_tiene_acceso_a_producto(self):
        self.client.force_authenticate(user=self.repartidor)
        resp = self.client.get("/api/v1/produccion/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_trabajador_no_puede_crear_producto(self):
        self.client.force_authenticate(user=self.trabajador)
        resp = self.client.post(
            "/api/v1/produccion/", {"nombre": "Otro", "precio_unitario": "1"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class MermaYAjusteProductoTerminadoTests(APITestCase):
    def setUp(self):
        self.admin = crear_usuario("admin_mp2", Usuario.Rol.ADMIN)
        self.trabajador = crear_usuario("trab_mp2", Usuario.Rol.TRABAJADOR)
        self.producto = Producto.objects.create(nombre="Rosca", precio_unitario=Decimal("2.00"))
        services.registrar_ajuste_producto_terminado(
            producto_id=self.producto.id,
            cantidad_delta=Decimal("50"),
            motivo="Carga inicial",
            creado_por=self.admin,
        )

    def test_merma_directa_reduce_stock(self):
        services.registrar_merma_producto_terminado(
            producto_id=self.producto.id, cantidad=Decimal("5"), motivo="Se dañaron", creado_por=self.admin
        )
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_actual, Decimal("45"))

    def test_merma_no_puede_superar_stock_disponible(self):
        with self.assertRaises(Exception):
            services.registrar_merma_producto_terminado(
                producto_id=self.producto.id, cantidad=Decimal("9999"), motivo="Exceso", creado_por=self.admin
            )

    def test_ajuste_no_deja_stock_negativo(self):
        with self.assertRaises(Exception):
            services.registrar_ajuste_producto_terminado(
                producto_id=self.producto.id, cantidad_delta=Decimal("-9999"), motivo="Exceso", creado_por=self.admin
            )

    def test_trabajador_no_puede_registrar_merma_ni_ajuste_via_api(self):
        self.client.force_authenticate(user=self.trabajador)
        resp = self.client.post(
            f"/api/v1/produccion/{self.producto.id}/registrar-merma/",
            {"cantidad": "1", "motivo": "intento"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        resp = self.client.post(
            f"/api/v1/produccion/{self.producto.id}/ajustar/",
            {"cantidad_delta": "1", "motivo": "intento"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
