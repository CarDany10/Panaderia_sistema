from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.produccion.models import Producto, Produccion
from apps.usuarios.models import Usuario

from . import gcal_client, services
from .models import EventoCalendario


def crear_usuario(username, rol):
    return Usuario.objects.create_user(username=username, password="ClaveSegura123!", rol=rol)


class GoogleCalendarClientTests(TestCase):
    """Pruebas del adaptador contra la API de Google, simulada por completo:
    nunca se hace una llamada de red real en este entorno."""

    def _fechas(self):
        inicio = timezone.now()
        return inicio, inicio + timedelta(hours=1)

    def test_sin_credenciales_lanza_no_configurado(self):
        inicio, fin = self._fechas()
        with self.assertRaises(gcal_client.GoogleCalendarNoConfigurado):
            gcal_client.crear_evento(titulo="x", descripcion="", fecha_inicio=inicio, fecha_fin=fin)

    @override_settings(GOOGLE_CALENDAR_CREDENTIALS_JSON="esto-no-es-json")
    def test_credenciales_invalidas_lanza_no_configurado(self):
        inicio, fin = self._fechas()
        with self.assertRaises(gcal_client.GoogleCalendarNoConfigurado):
            gcal_client.crear_evento(titulo="x", descripcion="", fecha_inicio=inicio, fecha_fin=fin)

    @override_settings(GOOGLE_CALENDAR_CREDENTIALS_JSON='{"type": "service_account"}')
    def test_credenciales_validas_sin_calendar_id_lanza_no_configurado(self):
        inicio, fin = self._fechas()
        with patch("apps.calendario.gcal_client.service_account.Credentials.from_service_account_info"):
            with self.assertRaises(gcal_client.GoogleCalendarNoConfigurado):
                gcal_client.crear_evento(titulo="x", descripcion="", fecha_inicio=inicio, fecha_fin=fin)

    @override_settings(
        GOOGLE_CALENDAR_CREDENTIALS_JSON='{"type": "service_account"}',
        GOOGLE_CALENDAR_ID="calendario-panaderia",
    )
    @patch("apps.calendario.gcal_client.build")
    @patch("apps.calendario.gcal_client.service_account.Credentials.from_service_account_info")
    def test_crear_evento_llama_a_la_api_con_el_calendario_correcto(self, mock_creds, mock_build):
        mock_service = MagicMock()
        mock_service.events.return_value.insert.return_value.execute.return_value = {"id": "evt-999"}
        mock_build.return_value = mock_service

        inicio, fin = self._fechas()
        resultado = gcal_client.crear_evento(
            titulo="Producción de pan", descripcion="500 unidades", fecha_inicio=inicio, fecha_fin=fin
        )

        self.assertEqual(resultado, "evt-999")
        _, kwargs = mock_service.events.return_value.insert.call_args
        self.assertEqual(kwargs["calendarId"], "calendario-panaderia")
        self.assertEqual(kwargs["body"]["summary"], "Producción de pan")

    @override_settings(
        GOOGLE_CALENDAR_CREDENTIALS_JSON='{"type": "service_account"}',
        GOOGLE_CALENDAR_ID="calendario-panaderia",
    )
    @patch("apps.calendario.gcal_client.build")
    @patch("apps.calendario.gcal_client.service_account.Credentials.from_service_account_info")
    def test_eliminar_evento_ignora_404_de_google(self, mock_creds, mock_build):
        from googleapiclient.errors import HttpError

        respuesta_404 = MagicMock(status=404)
        mock_service = MagicMock()
        mock_service.events.return_value.delete.return_value.execute.side_effect = HttpError(
            respuesta_404, b"not found"
        )
        mock_build.return_value = mock_service

        # No debe lanzar excepción: un evento ya borrado en Google no es un error.
        gcal_client.eliminar_evento(google_event_id="evt-999")


class RegistrarEventoServiceTests(TestCase):
    def setUp(self):
        self.admin = crear_usuario("admin_cal", Usuario.Rol.ADMIN)
        self.producto = Producto.objects.create(nombre="Pan Cal", precio_unitario="1.00")
        self.produccion = Produccion.objects.create(
            producto=self.producto,
            fecha=timezone.now().date(),
            cantidad_planificada=100,
            cantidad_producida=100,
            creado_por=self.admin,
        )

    def _fechas(self):
        inicio = timezone.now()
        return inicio, inicio + timedelta(hours=2)

    def test_registrar_evento_sin_google_configurado_se_guarda_localmente(self):
        inicio, fin = self._fechas()
        evento = services.registrar_evento(
            tipo=EventoCalendario.Tipo.PRODUCCION,
            referencia_id=self.produccion.id,
            titulo="Producción de pan francés",
            descripcion="",
            fecha_inicio=inicio,
            fecha_fin=fin,
            creado_por=self.admin,
        )
        self.assertEqual(evento.google_event_id, "")
        self.assertTrue(EventoCalendario.objects.filter(pk=evento.id).exists())

    @patch("apps.calendario.services.gcal_client.crear_evento", return_value="evt-abc")
    def test_registrar_evento_con_google_disponible_guarda_id(self, mock_crear):
        inicio, fin = self._fechas()
        evento = services.registrar_evento(
            tipo=EventoCalendario.Tipo.PRODUCCION,
            referencia_id=self.produccion.id,
            titulo="Producción de pan francés",
            descripcion="",
            fecha_inicio=inicio,
            fecha_fin=fin,
            creado_por=self.admin,
        )
        self.assertEqual(evento.google_event_id, "evt-abc")
        mock_crear.assert_called_once()

    def test_no_permite_fecha_fin_antes_de_inicio(self):
        inicio, fin = self._fechas()
        with self.assertRaises(Exception):
            services.registrar_evento(
                tipo=EventoCalendario.Tipo.PRODUCCION,
                referencia_id=self.produccion.id,
                titulo="x",
                descripcion="",
                fecha_inicio=fin,
                fecha_fin=inicio,
                creado_por=self.admin,
            )

    def test_no_permite_dos_eventos_para_la_misma_referencia(self):
        inicio, fin = self._fechas()
        services.registrar_evento(
            tipo=EventoCalendario.Tipo.PRODUCCION,
            referencia_id=self.produccion.id,
            titulo="x",
            descripcion="",
            fecha_inicio=inicio,
            fecha_fin=fin,
            creado_por=self.admin,
        )
        with self.assertRaises(Exception):
            services.registrar_evento(
                tipo=EventoCalendario.Tipo.PRODUCCION,
                referencia_id=self.produccion.id,
                titulo="y",
                descripcion="",
                fecha_inicio=inicio,
                fecha_fin=fin,
                creado_por=self.admin,
            )

    @patch("apps.calendario.services.gcal_client.actualizar_evento")
    @patch("apps.calendario.services.gcal_client.crear_evento", return_value="evt-xyz")
    def test_actualizar_evento_sincroniza_con_google_si_tiene_id(self, mock_crear, mock_actualizar):
        inicio, fin = self._fechas()
        evento = services.registrar_evento(
            tipo=EventoCalendario.Tipo.PRODUCCION,
            referencia_id=self.produccion.id,
            titulo="Original",
            descripcion="",
            fecha_inicio=inicio,
            fecha_fin=fin,
            creado_por=self.admin,
        )
        services.actualizar_evento(evento_id=evento.id, titulo="Actualizado")
        mock_actualizar.assert_called_once()
        evento.refresh_from_db()
        self.assertEqual(evento.titulo, "Actualizado")

    @patch("apps.calendario.services.gcal_client.eliminar_evento")
    @patch("apps.calendario.services.gcal_client.crear_evento", return_value="evt-del")
    def test_eliminar_evento_llama_a_google_y_borra_localmente(self, mock_crear, mock_eliminar):
        inicio, fin = self._fechas()
        evento = services.registrar_evento(
            tipo=EventoCalendario.Tipo.PRODUCCION,
            referencia_id=self.produccion.id,
            titulo="A borrar",
            descripcion="",
            fecha_inicio=inicio,
            fecha_fin=fin,
            creado_por=self.admin,
        )
        services.eliminar_evento(evento_id=evento.id)
        mock_eliminar.assert_called_once_with(google_event_id="evt-del")
        self.assertFalse(EventoCalendario.objects.filter(pk=evento.id).exists())


class EventoCalendarioAPITests(APITestCase):
    def setUp(self):
        self.admin = crear_usuario("admin_cal_api", Usuario.Rol.ADMIN)
        self.trabajador = crear_usuario("trab_cal_api", Usuario.Rol.TRABAJADOR)
        self.producto = Producto.objects.create(nombre="Pan Cal API", precio_unitario="1.00")
        self.produccion = Produccion.objects.create(
            producto=self.producto,
            fecha=timezone.now().date(),
            cantidad_planificada=50,
            cantidad_producida=50,
            creado_por=self.admin,
        )
        self.inicio = timezone.now()
        self.fin = self.inicio + timedelta(hours=1)

    def test_admin_crea_evento_para_produccion_existente(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post(
            "/api/v1/calendario/eventos/",
            {
                "tipo": "PRODUCCION",
                "referencia_id": self.produccion.id,
                "titulo": "Producción #1",
                "fecha_inicio": self.inicio.isoformat(),
                "fecha_fin": self.fin.isoformat(),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertFalse(resp.data["sincronizado_con_google"])

    def test_referencia_inexistente_es_rechazada(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post(
            "/api/v1/calendario/eventos/",
            {
                "tipo": "PRODUCCION",
                "referencia_id": 99999,
                "titulo": "x",
                "fecha_inicio": self.inicio.isoformat(),
                "fecha_fin": self.fin.isoformat(),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_trabajador_no_tiene_acceso(self):
        self.client.force_authenticate(user=self.trabajador)
        resp = self.client.get("/api/v1/calendario/eventos/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_filtrar_por_tipo_y_referencia(self):
        self.client.force_authenticate(user=self.admin)
        self.client.post(
            "/api/v1/calendario/eventos/",
            {
                "tipo": "PRODUCCION",
                "referencia_id": self.produccion.id,
                "titulo": "Producción #1",
                "fecha_inicio": self.inicio.isoformat(),
                "fecha_fin": self.fin.isoformat(),
            },
            format="json",
        )
        resp = self.client.get(f"/api/v1/calendario/eventos/?tipo=PRODUCCION&referencia_id={self.produccion.id}")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.data["results"] if "results" in resp.data else resp.data
        self.assertEqual(len(data), 1)

    def test_actualizar_y_eliminar_evento(self):
        self.client.force_authenticate(user=self.admin)
        creado = self.client.post(
            "/api/v1/calendario/eventos/",
            {
                "tipo": "PRODUCCION",
                "referencia_id": self.produccion.id,
                "titulo": "Original",
                "fecha_inicio": self.inicio.isoformat(),
                "fecha_fin": self.fin.isoformat(),
            },
            format="json",
        )
        evento_id = creado.data["id"]

        resp = self.client.patch(
            f"/api/v1/calendario/eventos/{evento_id}/", {"titulo": "Actualizado"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["titulo"], "Actualizado")

        resp = self.client.delete(f"/api/v1/calendario/eventos/{evento_id}/")
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(EventoCalendario.objects.filter(pk=evento_id).exists())
