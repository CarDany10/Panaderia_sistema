from rest_framework import status
from rest_framework.test import APITestCase

from apps.usuarios.models import Usuario

from . import services
from .models import Notificacion


def crear_usuario(username, rol):
    return Usuario.objects.create_user(username=username, password="ClaveSegura123!", rol=rol)


class NotificarAdminsTests(APITestCase):
    def test_notificar_admins_crea_una_por_cada_admin_activo(self):
        admin1 = crear_usuario("admin_n1", Usuario.Rol.ADMIN)
        admin2 = crear_usuario("admin_n2", Usuario.Rol.ADMIN)
        admin_inactivo = crear_usuario("admin_n3", Usuario.Rol.ADMIN)
        admin_inactivo.is_active = False
        admin_inactivo.save()
        crear_usuario("trab_n", Usuario.Rol.TRABAJADOR)

        services.notificar_admins(tipo=Notificacion.Tipo.STOCK_BAJO, titulo="x", mensaje="y")

        self.assertEqual(Notificacion.objects.filter(destinatario=admin1).count(), 1)
        self.assertEqual(Notificacion.objects.filter(destinatario=admin2).count(), 1)
        self.assertEqual(Notificacion.objects.filter(destinatario=admin_inactivo).count(), 0)


class NotificacionAPITests(APITestCase):
    def setUp(self):
        self.usuario1 = crear_usuario("u1_notif", Usuario.Rol.CLIENTE)
        self.usuario2 = crear_usuario("u2_notif", Usuario.Rol.CLIENTE)
        self.notif1 = services.crear_notificacion(
            destinatario=self.usuario1, tipo=Notificacion.Tipo.ESTADO_PEDIDO, titulo="A", mensaje="a"
        )
        self.notif2 = services.crear_notificacion(
            destinatario=self.usuario2, tipo=Notificacion.Tipo.ESTADO_PEDIDO, titulo="B", mensaje="b"
        )

    def test_usuario_solo_ve_sus_propias_notificaciones(self):
        self.client.force_authenticate(user=self.usuario1)
        resp = self.client.get("/api/v1/notificaciones/")
        data = resp.data["results"] if "results" in resp.data else resp.data
        ids = [n["id"] for n in data]
        self.assertIn(self.notif1.id, ids)
        self.assertNotIn(self.notif2.id, ids)

    def test_no_puede_marcar_leida_una_notificacion_ajena(self):
        self.client.force_authenticate(user=self.usuario1)
        resp = self.client.post(f"/api/v1/notificaciones/{self.notif2.id}/marcar-leida/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_marcar_leida_propia(self):
        self.client.force_authenticate(user=self.usuario1)
        resp = self.client.post(f"/api/v1/notificaciones/{self.notif1.id}/marcar-leida/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.notif1.refresh_from_db()
        self.assertTrue(self.notif1.leida)

    def test_marcar_todas_leidas(self):
        services.crear_notificacion(
            destinatario=self.usuario1, tipo=Notificacion.Tipo.ESTADO_PEDIDO, titulo="C", mensaje="c"
        )
        self.client.force_authenticate(user=self.usuario1)
        resp = self.client.post("/api/v1/notificaciones/marcar-todas-leidas/")
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Notificacion.objects.filter(destinatario=self.usuario1, leida=False).exists())

    def test_filtrar_por_leida(self):
        self.client.force_authenticate(user=self.usuario1)
        resp = self.client.get("/api/v1/notificaciones/?leida=false")
        data = resp.data["results"] if "results" in resp.data else resp.data
        self.assertEqual(len(data), 1)
