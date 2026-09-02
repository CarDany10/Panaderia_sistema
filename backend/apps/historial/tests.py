from datetime import date, timedelta
from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from apps.materia_prima import services as materia_prima_services
from apps.materia_prima.models import MateriaPrima, UnidadMedida
from apps.pedidos import services as pedidos_services
from apps.produccion import services as produccion_services
from apps.produccion.models import Producto
from apps.usuarios.models import Usuario
from apps.ventas import services as ventas_services


def crear_usuario(username, rol):
    return Usuario.objects.create_user(username=username, password="ClaveSegura123!", rol=rol)


class HistorialTests(APITestCase):
    def setUp(self):
        self.admin = crear_usuario("admin_hist", Usuario.Rol.ADMIN)
        self.trabajador = crear_usuario("trab_hist", Usuario.Rol.TRABAJADOR)
        self.cliente = crear_usuario("cliente_hist", Usuario.Rol.CLIENTE)

        self.harina = MateriaPrima.objects.create(nombre="Harina Hist", unidad_medida=UnidadMedida.LB)
        self.compra = materia_prima_services.registrar_compra(
            materia_prima_id=self.harina.id, lote="H-1", cantidad=Decimal("50"), unidad_medida="LB",
            costo_total=Decimal("200"), fecha_compra=date.today(), creado_por=self.admin,
        )
        self.producto = Producto.objects.create(nombre="Pan Hist", precio_unitario=Decimal("1.00"))
        self.produccion = produccion_services.registrar_produccion(
            producto_id=self.producto.id, fecha=date.today(), cantidad_planificada=Decimal("20"),
            cantidad_producida=Decimal("20"), cantidad_merma=Decimal("0"),
            consumos=[{"materia_prima_id": self.harina.id, "cantidad": Decimal("10"), "unidad_medida": "LB"}],
            creado_por=self.admin,
        )
        self.venta = ventas_services.registrar_venta(
            cliente_id=None, items=[{"producto_id": self.producto.id, "cantidad": Decimal("5"), "paquete_id": None}],
            creado_por=self.admin,
        )
        self.pedido = pedidos_services.registrar_pedido(
            cliente=self.cliente, items=[{"producto_id": self.producto.id, "cantidad": Decimal("3"), "paquete_id": None}],
            direccion_entrega="Zona 1", telefono_contacto="1111-1111",
        )

    def test_solo_admin_accede(self):
        self.client.force_authenticate(user=self.trabajador)
        resp = self.client.get("/api/v1/historial/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_incluye_todas_las_categorias(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get("/api/v1/historial/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        categorias = {item["categoria"] for item in resp.data["resultados"]}
        self.assertEqual(
            categorias,
            {"MOVIMIENTO_MATERIA_PRIMA", "MOVIMIENTO_PRODUCTO_TERMINADO", "PRODUCCION", "VENTA", "PEDIDO"},
        )

    def test_filtro_por_tipo_compra_solo_materia_prima(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get("/api/v1/historial/?tipo=COMPRA")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(all(r["categoria"] == "MOVIMIENTO_MATERIA_PRIMA" for r in resp.data["resultados"]))
        self.assertTrue(all(r["tipo"] == "COMPRA" for r in resp.data["resultados"]))

    def test_filtro_por_tipo_pedido(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get("/api/v1/historial/?tipo=PEDIDO")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(all(r["categoria"] == "PEDIDO" for r in resp.data["resultados"]))

    def test_filtro_por_materia_prima(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get(f"/api/v1/historial/?materia_prima_id={self.harina.id}")
        self.assertGreater(len(resp.data["resultados"]), 0)
        # También debe aparecer la producción que consumió esta materia prima.
        categorias = {r["categoria"] for r in resp.data["resultados"]}
        self.assertIn("PRODUCCION", categorias)

    def test_filtro_por_producto(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get(f"/api/v1/historial/?producto_id={self.producto.id}")
        categorias = {r["categoria"] for r in resp.data["resultados"]}
        self.assertIn("VENTA", categorias)
        self.assertIn("PEDIDO", categorias)
        self.assertIn("PRODUCCION", categorias)

    def test_filtro_por_fecha_fuera_de_rango_no_devuelve_nada(self):
        self.client.force_authenticate(user=self.admin)
        ayer_lejano = (date.today() - timedelta(days=30)).isoformat()
        anteayer_lejano = (date.today() - timedelta(days=31)).isoformat()
        resp = self.client.get(f"/api/v1/historial/?fecha_desde={anteayer_lejano}&fecha_hasta={ayer_lejano}")
        self.assertEqual(resp.data["resultados"], [])

    def test_tipo_invalido_devuelve_400(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get("/api/v1/historial/?tipo=NO_EXISTE")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_paginacion_con_limit_y_offset(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get("/api/v1/historial/?limit=1&offset=0")
        self.assertEqual(len(resp.data["resultados"]), 1)
        self.assertGreater(resp.data["total"], 1)
