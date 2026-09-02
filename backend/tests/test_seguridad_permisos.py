"""Matriz de permisos por rol (regla de negocio #40 / sección 40 del sistema):
'comprobar que ningún usuario pueda acceder mediante una URL o API directamente
a información para la cual no tiene permisos'.

Este archivo no repite las pruebas detalladas de cada app (ya cubren casos de
negocio específicos); es una red de seguridad consolidada y data-driven: una
tabla de endpoints × rol permitido, para detectar de un vistazo si un cambio
futuro abre por error un endpoint sensible a un rol que no debería tocarlo.

Un usuario anónimo siempre debe recibir 401 en endpoints protegidos. Un rol no
autorizado debe recibir 403 (o 404 cuando el propio queryset ya lo oculta,
como en pedidos/entregas — ver las pruebas de cada app para ese detalle fino).
"""

from rest_framework import status
from rest_framework.test import APITestCase

from apps.usuarios.models import Usuario

ROLES = ["ADMIN", "TRABAJADOR", "REPARTIDOR", "CLIENTE"]

# (método, url, {roles que deben poder acceder sin 403})
ENDPOINTS_PROTEGIDOS = [
    ("get", "/api/v1/usuarios/", {"ADMIN"}),
    ("get", "/api/v1/usuarios/me/", {"ADMIN", "TRABAJADOR", "REPARTIDOR", "CLIENTE"}),
    ("get", "/api/v1/materia-prima/", {"ADMIN", "TRABAJADOR"}),
    ("get", "/api/v1/materia-prima/compras/", {"ADMIN"}),
    ("get", "/api/v1/materia-prima/alertas-stock-bajo/", {"ADMIN"}),
    ("get", "/api/v1/produccion/", {"ADMIN", "TRABAJADOR", "CLIENTE"}),
    ("get", "/api/v1/produccion/producciones/", {"ADMIN", "TRABAJADOR"}),
    ("get", "/api/v1/produccion/paquetes/", {"ADMIN", "TRABAJADOR", "CLIENTE"}),
    ("get", "/api/v1/ventas/", {"ADMIN"}),
    ("get", "/api/v1/pedidos/", {"ADMIN", "TRABAJADOR", "REPARTIDOR", "CLIENTE"}),
    ("get", "/api/v1/calendario/eventos/", {"ADMIN"}),
    ("get", "/api/v1/notificaciones/", {"ADMIN", "TRABAJADOR", "REPARTIDOR", "CLIENTE"}),
    ("get", "/api/v1/historial/", {"ADMIN"}),
    ("get", "/api/v1/dashboard/", {"ADMIN", "TRABAJADOR", "REPARTIDOR", "CLIENTE"}),
    ("get", "/api/v1/odoo/estado/", {"ADMIN"}),
]


class MatrizDePermisosTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuarios = {
            rol: Usuario.objects.create_user(
                username=f"matriz_{rol.lower()}", password="ClaveSegura123!", rol=getattr(Usuario.Rol, rol)
            )
            for rol in ROLES
        }

    def test_anonimo_nunca_accede_a_endpoints_protegidos(self):
        for metodo, url, _ in ENDPOINTS_PROTEGIDOS:
            with self.subTest(url=url):
                resp = getattr(self.client, metodo)(url)
                self.assertEqual(
                    resp.status_code, status.HTTP_401_UNAUTHORIZED, f"{metodo.upper()} {url} sin auth"
                )

    def test_matriz_de_roles_por_endpoint(self):
        for metodo, url, roles_permitidos in ENDPOINTS_PROTEGIDOS:
            for rol in ROLES:
                usuario = self.usuarios[rol]
                self.client.force_authenticate(user=usuario)
                with self.subTest(url=url, rol=rol):
                    resp = getattr(self.client, metodo)(url)
                    if rol in roles_permitidos:
                        self.assertNotEqual(
                            resp.status_code,
                            status.HTTP_403_FORBIDDEN,
                            f"{rol} debería poder acceder a {metodo.upper()} {url}",
                        )
                    else:
                        self.assertEqual(
                            resp.status_code,
                            status.HTTP_403_FORBIDDEN,
                            f"{rol} NO debería poder acceder a {metodo.upper()} {url} (recibió {resp.status_code})",
                        )
                self.client.force_authenticate(user=None)
