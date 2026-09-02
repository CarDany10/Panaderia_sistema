from datetime import date
from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from apps.materia_prima import services as materia_prima_services
from apps.materia_prima.models import MateriaPrima, UnidadMedida
from apps.pedidos import services as pedidos_services
from apps.produccion import services as produccion_services
from apps.produccion.models import Producto
from apps.usuarios.models import PerfilRepartidor, Usuario
from apps.ventas import services as ventas_services


def crear_usuario(username, rol):
    u = Usuario.objects.create_user(username=username, password="ClaveSegura123!", rol=rol)
    if rol == Usuario.Rol.REPARTIDOR:
        PerfilRepartidor.objects.create(usuario=u)
    return u


class DashboardAdminTests(APITestCase):
    def setUp(self):
        self.admin = crear_usuario("admin_dash", Usuario.Rol.ADMIN)
        self.cliente = crear_usuario("cliente_dash", Usuario.Rol.CLIENTE)

        self.harina = MateriaPrima.objects.create(
            nombre="Harina Dash", unidad_medida=UnidadMedida.LB, stock_minimo=Decimal("200")
        )
        materia_prima_services.registrar_compra(
            materia_prima_id=self.harina.id, lote="D-1", cantidad=Decimal("50"), unidad_medida="LB",
            costo_total=Decimal("200"), fecha_compra=date.today(), creado_por=self.admin,
        )
        self.producto = Producto.objects.create(
            nombre="Pan Dash", precio_unitario=Decimal("1.00"), stock_minimo=Decimal("100")
        )
        produccion_services.registrar_produccion(
            producto_id=self.producto.id, fecha=date.today(), cantidad_planificada=Decimal("30"),
            cantidad_producida=Decimal("30"), cantidad_merma=Decimal("0"),
            consumos=[{"materia_prima_id": self.harina.id, "cantidad": Decimal("10"), "unidad_medida": "LB"}],
            creado_por=self.admin,
        )
        ventas_services.registrar_venta(
            cliente_id=None, items=[{"producto_id": self.producto.id, "cantidad": Decimal("5"), "paquete_id": None}],
            creado_por=self.admin,
        )
        pedidos_services.registrar_pedido(
            cliente=self.cliente, items=[{"producto_id": self.producto.id, "cantidad": Decimal("2"), "paquete_id": None}],
            direccion_entrega="Zona 1", telefono_contacto="1111-1111",
        )

    def test_admin_ve_dashboard_completo(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get("/api/v1/dashboard/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        for campo in (
            "valor_inventario_materia_prima", "valor_inventario_producto_terminado",
            "ventas_dia", "ventas_semana", "ventas_mes", "producciones_recientes",
            "pedidos_pendientes", "materias_primas_stock_bajo", "productos_stock_bajo",
            "productos_mas_vendidos",
        ):
            self.assertIn(campo, resp.data)

    def test_stock_bajo_de_materia_prima_y_producto_aparecen(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get("/api/v1/dashboard/")
        nombres_mp = [m["nombre"] for m in resp.data["materias_primas_stock_bajo"]]
        nombres_pt = [p["nombre"] for p in resp.data["productos_stock_bajo"]]
        self.assertIn("Harina Dash", nombres_mp)
        self.assertIn("Pan Dash", nombres_pt)

    def test_ventas_dia_incluye_venta_de_mostrador_y_pedido(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get("/api/v1/dashboard/")
        # Venta: 5 x 1.00 = 5.00 ; Pedido: 2 x 1.00 = 2.00 -> total 7.00
        self.assertEqual(Decimal(resp.data["ventas_dia"]), Decimal("7.00"))

    def test_pedidos_pendientes_cuenta_correctamente(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get("/api/v1/dashboard/")
        self.assertEqual(resp.data["pedidos_pendientes"], 1)

    def test_producto_valor_inventario_usa_costo_promedio_ponderado(self):
        self.producto.refresh_from_db()
        # Costo de la producción: 10 lb x Q4.00/lb (200/50) = Q40 / 30 producidas = Q1.333.../unidad
        # Stock actual tras venta(5)+pedido(2) = 30-7 = 23 unidades
        self.assertEqual(self.producto.stock_actual, Decimal("23"))
        costo_esperado = Decimal("40") / Decimal("30")
        self.assertAlmostEqual(self.producto.costo_promedio_ponderado, costo_esperado, places=6)


class DashboardOtrosRolesTests(APITestCase):
    def setUp(self):
        self.admin = crear_usuario("admin_dash2", Usuario.Rol.ADMIN)
        self.trabajador = crear_usuario("trab_dash2", Usuario.Rol.TRABAJADOR)
        self.repartidor = crear_usuario("rep_dash2", Usuario.Rol.REPARTIDOR)
        self.cliente = crear_usuario("cliente_dash2", Usuario.Rol.CLIENTE)
        self.producto = Producto.objects.create(nombre="Concha Dash", precio_unitario=Decimal("1.00"))
        produccion_services.registrar_ajuste_producto_terminado(
            producto_id=self.producto.id, cantidad_delta=Decimal("50"), motivo="Carga", creado_por=self.admin
        )
        self.pedido = pedidos_services.registrar_pedido(
            cliente=self.cliente, items=[{"producto_id": self.producto.id, "cantidad": Decimal("4"), "paquete_id": None}],
            direccion_entrega="Zona 2", telefono_contacto="2222-2222",
        )

    def test_dashboard_trabajador_no_incluye_precios_ni_cliente(self):
        self.client.force_authenticate(user=self.trabajador)
        resp = self.client.get("/api/v1/dashboard/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("productos_a_producir", resp.data)
        for pedido in resp.data["pedidos_relacionados_con_produccion"]:
            self.assertNotIn("total", pedido)
            self.assertNotIn("cliente", pedido)

    def test_dashboard_trabajador_agrega_cantidades_requeridas(self):
        self.client.force_authenticate(user=self.trabajador)
        resp = self.client.get("/api/v1/dashboard/")
        productos = {p["producto"]: p["cantidad_requerida"] for p in resp.data["productos_a_producir"]}
        self.assertEqual(productos.get("Concha Dash"), "4.00")

    def test_dashboard_repartidor_solo_ve_lo_asignado(self):
        pedidos_services.asignar_repartidor(pedido_id=self.pedido.id, repartidor=self.repartidor, creado_por=self.admin)
        self.client.force_authenticate(user=self.repartidor)
        resp = self.client.get("/api/v1/dashboard/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["pedidos_pendientes"], 1)
        self.assertIsNone(resp.data["calificacion_promedio"])

    def test_dashboard_repartidor_sin_asignaciones_no_ve_nada(self):
        otro_repartidor = crear_usuario("rep_dash3", Usuario.Rol.REPARTIDOR)
        pedidos_services.asignar_repartidor(pedido_id=self.pedido.id, repartidor=self.repartidor, creado_por=self.admin)
        self.client.force_authenticate(user=otro_repartidor)
        resp = self.client.get("/api/v1/dashboard/")
        self.assertEqual(resp.data["pedidos_pendientes"], 0)
        self.assertEqual(resp.data["proximas_entregas"], [])

    def test_dashboard_cliente_ve_su_pedido_actual(self):
        self.client.force_authenticate(user=self.cliente)
        resp = self.client.get("/api/v1/dashboard/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["pedidos_actuales"]), 1)
        self.assertEqual(resp.data["historial"], [])

    def test_dashboard_cliente_no_ve_pedidos_de_otro_cliente(self):
        otro_cliente = crear_usuario("cliente_dash3", Usuario.Rol.CLIENTE)
        self.client.force_authenticate(user=otro_cliente)
        resp = self.client.get("/api/v1/dashboard/")
        self.assertEqual(resp.data["pedidos_actuales"], [])

    def test_dashboard_cliente_pendiente_de_calificar_tras_entrega(self):
        pedidos_services.asignar_repartidor(pedido_id=self.pedido.id, repartidor=self.repartidor, creado_por=self.admin)
        pedidos_services.marcar_en_camino(pedido_id=self.pedido.id, repartidor=self.repartidor)
        pedidos_services.marcar_entregado(pedido_id=self.pedido.id, repartidor=self.repartidor)

        self.client.force_authenticate(user=self.cliente)
        resp = self.client.get("/api/v1/dashboard/")
        self.assertEqual(len(resp.data["pedidos_pendientes_de_calificar"]), 1)

        pedidos_services.calificar_repartidor(pedido_id=self.pedido.id, cliente=self.cliente, estrellas=5)
        resp = self.client.get("/api/v1/dashboard/")
        self.assertEqual(resp.data["pedidos_pendientes_de_calificar"], [])
