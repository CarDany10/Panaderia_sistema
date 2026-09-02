from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from apps.produccion import services as produccion_services
from apps.produccion.models import Paquete, Producto
from apps.usuarios.models import Usuario

from . import services
from .models import Venta


def crear_usuario(username, rol):
    return Usuario.objects.create_user(username=username, password="ClaveSegura123!", rol=rol)


class RegistrarVentaTests(APITestCase):
    def setUp(self):
        self.admin = crear_usuario("admin_venta", Usuario.Rol.ADMIN)
        self.producto = Producto.objects.create(nombre="Pan Francés V", precio_unitario=Decimal("1.50"))
        produccion_services.registrar_ajuste_producto_terminado(
            producto_id=self.producto.id,
            cantidad_delta=Decimal("500"),
            motivo="Carga inicial",
            creado_por=self.admin,
        )
        self.paquete = Paquete.objects.create(
            producto=self.producto, nombre="Paquete x20", unidades_por_paquete=20, precio_paquete=Decimal("25")
        )

    def test_venta_por_unidad_descuenta_stock_y_calcula_total(self):
        venta = services.registrar_venta(
            cliente_id=None,
            items=[{"producto_id": self.producto.id, "cantidad": Decimal("50"), "paquete_id": None}],
            creado_por=self.admin,
        )
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_actual, Decimal("450"))
        self.assertEqual(venta.total, Decimal("75.00"))  # 50 x 1.50

    def test_venta_por_paquete_descuenta_unidades_correctas(self):
        venta = services.registrar_venta(
            cliente_id=None,
            items=[{"producto_id": self.producto.id, "cantidad": Decimal("3"), "paquete_id": self.paquete.id}],
            creado_por=self.admin,
        )
        self.producto.refresh_from_db()
        # 3 paquetes x 20 unidades = 60 unidades descontadas
        self.assertEqual(self.producto.stock_actual, Decimal("440"))
        self.assertEqual(venta.total, Decimal("75.00"))  # 3 x Q25

    def test_no_permite_vender_mas_de_lo_disponible(self):
        with self.assertRaises(Exception):
            services.registrar_venta(
                cliente_id=None,
                items=[{"producto_id": self.producto.id, "cantidad": Decimal("999999"), "paquete_id": None}],
                creado_por=self.admin,
            )
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_actual, Decimal("500"))
        self.assertEqual(Venta.objects.count(), 0)

    def test_anular_venta_revierte_inventario_sin_borrar_registro(self):
        venta = services.registrar_venta(
            cliente_id=None,
            items=[{"producto_id": self.producto.id, "cantidad": Decimal("50"), "paquete_id": None}],
            creado_por=self.admin,
        )
        services.anular_venta(venta_id=venta.id, motivo="Cliente se arrepintió", creado_por=self.admin)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_actual, Decimal("500"))
        venta.refresh_from_db()
        self.assertEqual(venta.estado, Venta.Estado.ANULADA)
        self.assertTrue(Venta.objects.filter(id=venta.id).exists())

    def test_no_se_puede_anular_dos_veces(self):
        venta = services.registrar_venta(
            cliente_id=None,
            items=[{"producto_id": self.producto.id, "cantidad": Decimal("10"), "paquete_id": None}],
            creado_por=self.admin,
        )
        services.anular_venta(venta_id=venta.id, motivo="motivo", creado_por=self.admin)
        with self.assertRaises(Exception):
            services.anular_venta(venta_id=venta.id, motivo="otra vez", creado_por=self.admin)

    def test_api_admin_puede_registrar_venta(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post(
            "/api/v1/ventas/",
            {"items": [{"producto": self.producto.id, "cantidad": "5"}]},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data["total"], "7.50")

    def test_api_trabajador_no_puede_vender(self):
        trabajador = crear_usuario("trab_venta", Usuario.Rol.TRABAJADOR)
        self.client.force_authenticate(user=trabajador)
        resp = self.client.post(
            "/api/v1/ventas/",
            {"items": [{"producto": self.producto.id, "cantidad": "5"}]},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_api_cliente_no_puede_vender(self):
        cliente = crear_usuario("cli_venta", Usuario.Rol.CLIENTE)
        self.client.force_authenticate(user=cliente)
        resp = self.client.get("/api/v1/ventas/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_venta_no_admite_edicion_ni_borrado(self):
        venta = services.registrar_venta(
            cliente_id=None,
            items=[{"producto_id": self.producto.id, "cantidad": Decimal("1"), "paquete_id": None}],
            creado_por=self.admin,
        )
        self.client.force_authenticate(user=self.admin)
        resp = self.client.delete(f"/api/v1/ventas/{venta.id}/")
        self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        resp = self.client.patch(f"/api/v1/ventas/{venta.id}/", {"total": "0"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_api_anular_venta(self):
        self.client.force_authenticate(user=self.admin)
        crear = self.client.post(
            "/api/v1/ventas/",
            {"items": [{"producto": self.producto.id, "cantidad": "2"}]},
            format="json",
        )
        venta_id = crear.data["id"]
        resp = self.client.post(f"/api/v1/ventas/{venta_id}/anular/", {"motivo": "Error de cobro"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["estado"], "ANULADA")


class PaqueteTests(APITestCase):
    def setUp(self):
        self.admin = crear_usuario("admin_paq", Usuario.Rol.ADMIN)
        self.trabajador = crear_usuario("trab_paq", Usuario.Rol.TRABAJADOR)
        self.producto = Producto.objects.create(nombre="Champurrada", precio_unitario=Decimal("0.75"))

    def test_admin_puede_crear_paquete(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post(
            "/api/v1/produccion/paquetes/",
            {
                "producto": self.producto.id,
                "nombre": "Paquete x20",
                "unidades_por_paquete": 20,
                "precio_paquete": "12.00",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

    def test_trabajador_no_puede_crear_paquete(self):
        self.client.force_authenticate(user=self.trabajador)
        resp = self.client.post(
            "/api/v1/produccion/paquetes/",
            {
                "producto": self.producto.id,
                "nombre": "Paquete x20",
                "unidades_por_paquete": 20,
                "precio_paquete": "12.00",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
