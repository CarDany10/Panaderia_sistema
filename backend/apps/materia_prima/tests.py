from datetime import date
from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from apps.usuarios.models import Usuario

from . import services
from .models import Compra, MateriaPrima, MovimientoInventarioMateriaPrima, UnidadMedida


def crear_usuario(username, rol):
    return Usuario.objects.create_user(username=username, password="ClaveSegura123!", rol=rol)


class ConversionUnidadesTests(APITestCase):
    def test_libra_a_onza(self):
        self.assertEqual(services.convertir_cantidad(Decimal("1"), "LB", "OZ"), Decimal("16"))

    def test_onza_a_libra(self):
        self.assertEqual(services.convertir_cantidad(Decimal("16"), "OZ", "LB"), Decimal("1"))

    def test_misma_unidad_no_cambia(self):
        self.assertEqual(services.convertir_cantidad(Decimal("5"), "LB", "LB"), Decimal("5"))

    def test_costo_unitario_se_convierte_de_forma_inversa_a_la_cantidad(self):
        # Si 1 lb cuesta Q16, 1 oz debe costar Q1 (16 veces menos).
        costo_por_oz = services.convertir_costo_unitario(Decimal("16"), "LB", "OZ")
        self.assertEqual(costo_por_oz, Decimal("1"))


class RegistrarCompraTests(APITestCase):
    def setUp(self):
        self.admin = crear_usuario("admin_mp", Usuario.Rol.ADMIN)
        self.harina = MateriaPrima.objects.create(
            nombre="Harina", unidad_medida=UnidadMedida.LB, stock_minimo=Decimal("20")
        )

    def test_registrar_compra_incrementa_stock_y_crea_movimiento(self):
        compra = services.registrar_compra(
            materia_prima_id=self.harina.id,
            lote="L-001",
            cantidad=Decimal("100"),
            unidad_medida="LB",
            costo_total=Decimal("500"),
            fecha_compra=date.today(),
            creado_por=self.admin,
        )
        self.harina.refresh_from_db()
        self.assertEqual(self.harina.stock_actual, Decimal("100"))
        self.assertEqual(compra.costo_unitario, Decimal("5"))
        mov = MovimientoInventarioMateriaPrima.objects.get(compra=compra)
        self.assertEqual(mov.tipo, MovimientoInventarioMateriaPrima.Tipo.COMPRA)
        self.assertEqual(mov.cantidad, Decimal("100"))
        self.assertEqual(mov.saldo_resultante, Decimal("100"))

    def test_costo_unitario_manual_no_se_recalcula(self):
        compra = services.registrar_compra(
            materia_prima_id=self.harina.id,
            lote="L-002",
            cantidad=Decimal("100"),
            unidad_medida="LB",
            costo_total=Decimal("500"),
            costo_unitario=Decimal("6.50"),
            fecha_compra=date.today(),
            creado_por=self.admin,
        )
        self.assertEqual(compra.costo_unitario, Decimal("6.50"))

    def test_compra_en_onzas_convierte_a_libras_nativas(self):
        compra = services.registrar_compra(
            materia_prima_id=self.harina.id,
            lote="L-003",
            cantidad=Decimal("32"),
            unidad_medida="OZ",
            costo_total=Decimal("32"),
            fecha_compra=date.today(),
            creado_por=self.admin,
        )
        self.assertEqual(compra.cantidad_nativa, Decimal("2"))
        self.harina.refresh_from_db()
        self.assertEqual(self.harina.stock_actual, Decimal("2"))

    def test_api_no_admin_no_puede_registrar_compra(self):
        trabajador = crear_usuario("trab_compra", Usuario.Rol.TRABAJADOR)
        self.client.force_authenticate(user=trabajador)
        resp = self.client.post(
            "/api/v1/materia-prima/compras/",
            {
                "materia_prima": self.harina.id,
                "lote": "L-004",
                "cantidad": "10",
                "unidad_medida": "LB",
                "costo_total": "50",
                "fecha_compra": str(date.today()),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_compra_no_admite_actualizacion_ni_borrado(self):
        compra = services.registrar_compra(
            materia_prima_id=self.harina.id,
            lote="L-005",
            cantidad=Decimal("10"),
            unidad_medida="LB",
            costo_total=Decimal("50"),
            fecha_compra=date.today(),
            creado_por=self.admin,
        )
        self.client.force_authenticate(user=self.admin)
        resp = self.client.delete(f"/api/v1/materia-prima/compras/{compra.id}/")
        self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        resp = self.client.put(f"/api/v1/materia-prima/compras/{compra.id}/", {}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class ConsumoFifoTests(APITestCase):
    def setUp(self):
        self.admin = crear_usuario("admin_fifo", Usuario.Rol.ADMIN)
        self.azucar = MateriaPrima.objects.create(nombre="Azúcar", unidad_medida=UnidadMedida.LB)
        # Lote más antiguo, más barato.
        self.lote_1 = services.registrar_compra(
            materia_prima_id=self.azucar.id,
            lote="A-1",
            cantidad=Decimal("50"),
            unidad_medida="LB",
            costo_total=Decimal("200"),  # Q4.00/lb
            fecha_compra=date(2026, 1, 1),
            creado_por=self.admin,
        )
        # Lote más reciente, más caro.
        self.lote_2 = services.registrar_compra(
            materia_prima_id=self.azucar.id,
            lote="A-2",
            cantidad=Decimal("50"),
            unidad_medida="LB",
            costo_total=Decimal("300"),  # Q6.00/lb
            fecha_compra=date(2026, 2, 1),
            creado_por=self.admin,
        )

    def test_consumo_dentro_de_un_solo_lote_usa_el_mas_antiguo(self):
        movimientos = services.consumir_fifo(
            materia_prima_id=self.azucar.id,
            cantidad_nativa=Decimal("30"),
            tipo=MovimientoInventarioMateriaPrima.Tipo.PRODUCCION,
            motivo="Producción #1",
            creado_por=self.admin,
        )
        self.assertEqual(len(movimientos), 1)
        self.assertEqual(movimientos[0].compra, self.lote_1)
        self.lote_1.refresh_from_db()
        self.assertEqual(self.lote_1.cantidad_restante, Decimal("20"))

    def test_consumo_que_cruza_dos_lotes_genera_dos_movimientos(self):
        movimientos = services.consumir_fifo(
            materia_prima_id=self.azucar.id,
            cantidad_nativa=Decimal("70"),
            tipo=MovimientoInventarioMateriaPrima.Tipo.MERMA,
            motivo="Lote dañado",
            creado_por=self.admin,
        )
        self.assertEqual(len(movimientos), 2)
        self.assertEqual(movimientos[0].compra, self.lote_1)
        self.assertEqual(movimientos[0].cantidad, Decimal("-50"))
        self.assertEqual(movimientos[1].compra, self.lote_2)
        self.assertEqual(movimientos[1].cantidad, Decimal("-20"))
        self.lote_1.refresh_from_db()
        self.lote_2.refresh_from_db()
        self.assertEqual(self.lote_1.cantidad_restante, Decimal("0"))
        self.assertEqual(self.lote_2.cantidad_restante, Decimal("30"))

    def test_no_permite_consumir_mas_de_lo_disponible(self):
        with self.assertRaises(Exception):
            services.consumir_fifo(
                materia_prima_id=self.azucar.id,
                cantidad_nativa=Decimal("999"),
                tipo=MovimientoInventarioMateriaPrima.Tipo.MERMA,
                motivo="Intento excesivo",
                creado_por=self.admin,
            )
        self.azucar.refresh_from_db()
        self.assertEqual(self.azucar.stock_actual, Decimal("100"))

    def test_valor_inventario_refleja_costo_real_de_cada_lote_restante(self):
        # 50 lb a Q4.00 + 50 lb a Q6.00 = Q200 + Q300 = Q500
        self.assertEqual(self.azucar.valor_inventario, Decimal("500.00"))
        services.consumir_fifo(
            materia_prima_id=self.azucar.id,
            cantidad_nativa=Decimal("50"),
            tipo=MovimientoInventarioMateriaPrima.Tipo.PRODUCCION,
            motivo="Producción #2",
            creado_por=self.admin,
        )
        self.azucar.refresh_from_db()
        # Se consumió todo el lote barato (Q4.00); queda solo el de Q6.00 x 50 = Q300
        self.assertEqual(self.azucar.valor_inventario, Decimal("300.00"))


class AjusteInventarioTests(APITestCase):
    def setUp(self):
        self.admin = crear_usuario("admin_ajuste", Usuario.Rol.ADMIN)
        self.sal = MateriaPrima.objects.create(
            nombre="Sal", unidad_medida=UnidadMedida.LB, stock_minimo=Decimal("5")
        )
        services.registrar_compra(
            materia_prima_id=self.sal.id,
            lote="S-1",
            cantidad=Decimal("10"),
            unidad_medida="LB",
            costo_total=Decimal("20"),
            fecha_compra=date.today(),
            creado_por=self.admin,
        )

    def test_ajuste_positivo_incrementa_stock(self):
        services.registrar_ajuste(
            materia_prima_id=self.sal.id,
            cantidad_delta=Decimal("5"),
            motivo="Conteo físico encontró más sal",
            creado_por=self.admin,
        )
        self.sal.refresh_from_db()
        self.assertEqual(self.sal.stock_actual, Decimal("15"))

    def test_ajuste_no_puede_dejar_stock_negativo(self):
        with self.assertRaises(Exception):
            services.registrar_ajuste(
                materia_prima_id=self.sal.id,
                cantidad_delta=Decimal("-999"),
                motivo="Corrección exagerada",
                creado_por=self.admin,
            )
        self.sal.refresh_from_db()
        self.assertEqual(self.sal.stock_actual, Decimal("10"))

    def test_api_trabajador_no_puede_ajustar_ni_registrar_merma(self):
        trabajador = crear_usuario("trab_ajuste", Usuario.Rol.TRABAJADOR)
        self.client.force_authenticate(user=trabajador)
        resp = self.client.post(
            f"/api/v1/materia-prima/{self.sal.id}/ajustar/",
            {"cantidad_delta": "1", "motivo": "intento"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        resp = self.client.post(
            f"/api/v1/materia-prima/{self.sal.id}/registrar-merma/",
            {"cantidad": "1", "motivo": "intento"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class VisibilidadPorRolTests(APITestCase):
    def setUp(self):
        self.admin = crear_usuario("admin_vis", Usuario.Rol.ADMIN)
        self.trabajador = crear_usuario("trab_vis", Usuario.Rol.TRABAJADOR)
        self.repartidor = crear_usuario("rep_vis", Usuario.Rol.REPARTIDOR)
        self.cliente = crear_usuario("cli_vis", Usuario.Rol.CLIENTE)
        self.harina = MateriaPrima.objects.create(
            nombre="Harina Visibilidad",
            unidad_medida=UnidadMedida.LB,
            stock_minimo=Decimal("20"),
        )
        services.registrar_compra(
            materia_prima_id=self.harina.id,
            lote="V-1",
            cantidad=Decimal("100"),
            unidad_medida="LB",
            costo_total=Decimal("500"),
            fecha_compra=date.today(),
            creado_por=self.admin,
        )

    def test_admin_ve_stock_y_valor(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get(f"/api/v1/materia-prima/{self.harina.id}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("stock_actual", resp.data)
        self.assertIn("valor_inventario", resp.data)

    def test_trabajador_no_ve_stock_ni_valor(self):
        self.client.force_authenticate(user=self.trabajador)
        resp = self.client.get(f"/api/v1/materia-prima/{self.harina.id}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertNotIn("stock_actual", resp.data)
        self.assertNotIn("stock_minimo", resp.data)
        self.assertNotIn("valor_inventario", resp.data)
        self.assertEqual(resp.data["nombre"], "Harina Visibilidad")

    def test_repartidor_no_tiene_acceso(self):
        self.client.force_authenticate(user=self.repartidor)
        resp = self.client.get("/api/v1/materia-prima/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_cliente_no_tiene_acceso(self):
        self.client.force_authenticate(user=self.cliente)
        resp = self.client.get("/api/v1/materia-prima/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_solo_admin_ve_movimientos(self):
        self.client.force_authenticate(user=self.trabajador)
        resp = self.client.get(f"/api/v1/materia-prima/{self.harina.id}/movimientos/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.admin)
        resp = self.client.get(f"/api/v1/materia-prima/{self.harina.id}/movimientos/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)


class AlertaStockBajoTests(APITestCase):
    def setUp(self):
        self.admin = crear_usuario("admin_alerta", Usuario.Rol.ADMIN)
        self.harina_baja = MateriaPrima.objects.create(
            nombre="Harina Baja",
            unidad_medida=UnidadMedida.LB,
            stock_minimo=Decimal("50"),
        )
        services.registrar_compra(
            materia_prima_id=self.harina_baja.id,
            lote="B-1",
            cantidad=Decimal("10"),
            unidad_medida="LB",
            costo_total=Decimal("50"),
            fecha_compra=date.today(),
            creado_por=self.admin,
        )
        self.harina_ok = MateriaPrima.objects.create(
            nombre="Harina Ok", unidad_medida=UnidadMedida.LB, stock_minimo=Decimal("5")
        )
        services.registrar_compra(
            materia_prima_id=self.harina_ok.id,
            lote="B-2",
            cantidad=Decimal("100"),
            unidad_medida="LB",
            costo_total=Decimal("500"),
            fecha_compra=date.today(),
            creado_por=self.admin,
        )

    def test_alerta_solo_incluye_materias_bajo_minimo(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get("/api/v1/materia-prima/alertas-stock-bajo/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        nombres = [item["materia_prima"] for item in resp.data]
        self.assertIn("Harina Baja", nombres)
        self.assertNotIn("Harina Ok", nombres)

    def test_trabajador_no_puede_consultar_alertas(self):
        trabajador = crear_usuario("trab_alerta", Usuario.Rol.TRABAJADOR)
        self.client.force_authenticate(user=trabajador)
        resp = self.client.get("/api/v1/materia-prima/alertas-stock-bajo/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
