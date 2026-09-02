from datetime import date
from unittest.mock import MagicMock, patch

from decimal import Decimal

from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.materia_prima import services as materia_prima_services
from apps.materia_prima.models import MateriaPrima, UnidadMedida
from apps.usuarios.models import Usuario
from apps.ventas import services as ventas_services
from apps.produccion.models import Producto
from apps.produccion import services as produccion_services

from . import odoo_client, services
from .models import SincronizacionOdoo


def crear_usuario(username, rol):
    return Usuario.objects.create_user(username=username, password="ClaveSegura123!", rol=rol)


class OdooClientTests(TestCase):
    def test_sin_credenciales_lanza_no_configurado(self):
        with self.assertRaises(odoo_client.OdooNoConfigurado):
            odoo_client.execute_kw("res.partner", "search", [[]])

    @override_settings(ODOO_URL="http://odoo.local", ODOO_DB="db", ODOO_USERNAME="admin", ODOO_API_KEY="k")
    @patch("apps.odoo_integration.odoo_client.xmlrpc.client.ServerProxy")
    def test_autenticacion_rechazada_lanza_error(self, mock_server_proxy):
        mock_common = MagicMock()
        mock_common.authenticate.return_value = False
        mock_server_proxy.return_value = mock_common
        with self.assertRaises(odoo_client.OdooError):
            odoo_client.execute_kw("res.partner", "search", [[]])

    @override_settings(ODOO_URL="http://odoo.local", ODOO_DB="db", ODOO_USERNAME="admin", ODOO_API_KEY="k")
    @patch("apps.odoo_integration.odoo_client.xmlrpc.client.ServerProxy")
    def test_execute_kw_llama_con_uid_autenticado(self, mock_server_proxy):
        mock_common = MagicMock()
        mock_common.authenticate.return_value = 7
        mock_models = MagicMock()
        mock_models.execute_kw.return_value = [1, 2, 3]
        # Primera instancia de ServerProxy -> common; segunda -> models.
        mock_server_proxy.side_effect = [mock_common, mock_models]

        resultado = odoo_client.execute_kw("res.partner", "search", [[]])

        self.assertEqual(resultado, [1, 2, 3])
        mock_models.execute_kw.assert_called_once_with("db", 7, "k", "res.partner", "search", [[]], {})


class SincronizarVentaCompraTests(TestCase):
    def setUp(self):
        self.admin = crear_usuario("admin_odoo", Usuario.Rol.ADMIN)
        self.producto = Producto.objects.create(nombre="Pan Odoo", precio_unitario=Decimal("1.00"))
        produccion_services.registrar_ajuste_producto_terminado(
            producto_id=self.producto.id, cantidad_delta=Decimal("50"), motivo="Carga", creado_por=self.admin
        )
        self.venta = ventas_services.registrar_venta(
            cliente_id=None,
            items=[{"producto_id": self.producto.id, "cantidad": Decimal("5"), "paquete_id": None}],
            creado_por=self.admin,
        )
        self.harina = MateriaPrima.objects.create(nombre="Harina Odoo", unidad_medida=UnidadMedida.LB)
        self.compra = materia_prima_services.registrar_compra(
            materia_prima_id=self.harina.id, lote="O-1", cantidad=Decimal("20"), unidad_medida="LB",
            costo_total=Decimal("80"), fecha_compra=date.today(), creado_por=self.admin,
        )

    def test_sincronizar_venta_sin_odoo_configurado_no_falla_y_marca_pendiente(self):
        registro = services.sincronizar_venta(self.venta.id)
        self.assertIsNone(registro.odoo_id)
        self.assertIn("Faltan credenciales", registro.error)

    def test_sincronizar_compra_sin_odoo_configurado_no_falla_y_marca_pendiente(self):
        registro = services.sincronizar_compra(self.compra.id)
        self.assertIsNone(registro.odoo_id)
        self.assertIn("Faltan credenciales", registro.error)

    @patch("apps.odoo_integration.services.odoo_client.crear_factura_cliente", return_value=555)
    @patch("apps.odoo_integration.services.odoo_client.buscar_o_crear_partner", return_value=42)
    def test_sincronizar_venta_con_odoo_disponible_guarda_odoo_id(self, mock_partner, mock_factura):
        registro = services.sincronizar_venta(self.venta.id)
        self.assertEqual(registro.odoo_id, 555)
        self.assertEqual(registro.error, "")
        self.assertIsNotNone(registro.sincronizado_en)
        mock_partner.assert_called_once()
        mock_factura.assert_called_once()

    @patch("apps.odoo_integration.services.odoo_client.crear_factura_proveedor", return_value=777)
    @patch("apps.odoo_integration.services.odoo_client.buscar_o_crear_partner", return_value=42)
    def test_sincronizar_compra_con_odoo_disponible_guarda_odoo_id(self, mock_partner, mock_factura):
        registro = services.sincronizar_compra(self.compra.id)
        self.assertEqual(registro.odoo_id, 777)
        self.assertEqual(registro.error, "")

    @patch(
        "apps.odoo_integration.services.odoo_client.buscar_o_crear_partner",
        side_effect=odoo_client.OdooError("Odoo caído"),
    )
    def test_error_real_de_odoo_se_relanza_y_queda_registrado(self, mock_partner):
        with self.assertRaises(odoo_client.OdooError):
            services.sincronizar_venta(self.venta.id)
        registro = SincronizacionOdoo.objects.get(
            tipo=SincronizacionOdoo.Tipo.VENTA, referencia_id=self.venta.id
        )
        self.assertEqual(registro.error, "Odoo caído")
        self.assertIsNone(registro.odoo_id)

    def test_resincronizar_reutiliza_el_mismo_registro(self):
        services.sincronizar_venta(self.venta.id)
        services.sincronizar_venta(self.venta.id)
        self.assertEqual(
            SincronizacionOdoo.objects.filter(
                tipo=SincronizacionOdoo.Tipo.VENTA, referencia_id=self.venta.id
            ).count(),
            1,
        )


class OdooAPITests(APITestCase):
    def setUp(self):
        self.admin = crear_usuario("admin_odoo_api", Usuario.Rol.ADMIN)
        self.trabajador = crear_usuario("trab_odoo_api", Usuario.Rol.TRABAJADOR)
        self.producto = Producto.objects.create(nombre="Pan Odoo API", precio_unitario=Decimal("1.00"))
        produccion_services.registrar_ajuste_producto_terminado(
            producto_id=self.producto.id, cantidad_delta=Decimal("50"), motivo="Carga", creado_por=self.admin
        )
        self.venta = ventas_services.registrar_venta(
            cliente_id=None,
            items=[{"producto_id": self.producto.id, "cantidad": Decimal("2"), "paquete_id": None}],
            creado_por=self.admin,
        )

    def test_admin_puede_sincronizar_venta_sin_odoo_configurado(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post(f"/api/v1/odoo/ventas/{self.venta.id}/sincronizar/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(resp.data["sincronizado"])

    def test_trabajador_no_puede_sincronizar(self):
        self.client.force_authenticate(user=self.trabajador)
        resp = self.client.post(f"/api/v1/odoo/ventas/{self.venta.id}/sincronizar/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_trabajador_no_puede_ver_estado(self):
        self.client.force_authenticate(user=self.trabajador)
        resp = self.client.get("/api/v1/odoo/estado/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    @patch(
        "apps.odoo_integration.services.odoo_client.buscar_o_crear_partner",
        side_effect=odoo_client.OdooError("Odoo caído"),
    )
    def test_error_real_devuelve_502(self, mock_partner):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post(f"/api/v1/odoo/ventas/{self.venta.id}/sincronizar/")
        self.assertEqual(resp.status_code, status.HTTP_502_BAD_GATEWAY)
