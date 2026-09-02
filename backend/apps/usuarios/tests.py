from rest_framework import status
from rest_framework.test import APITestCase

from .models import PerfilCliente, PerfilRepartidor, Usuario


def crear_usuario(username, rol, password="ClaveSegura123!"):
    return Usuario.objects.create_user(username=username, password=password, rol=rol)


class RegistroClienteTests(APITestCase):
    def test_registro_cliente_crea_usuario_con_rol_cliente_y_perfil(self):
        resp = self.client.post(
            "/api/v1/usuarios/registro-cliente/",
            {
                "username": "cliente1",
                "email": "cliente1@example.com",
                "password": "ClaveSegura123!",
                "telefono": "5555-5555",
                "direccion_entrega_predeterminada": "Zona 1, Ciudad",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        usuario = Usuario.objects.get(username="cliente1")
        self.assertEqual(usuario.rol, Usuario.Rol.CLIENTE)
        self.assertTrue(PerfilCliente.objects.filter(usuario=usuario).exists())

    def test_registro_cliente_ignora_intento_de_asignar_rol_admin(self):
        resp = self.client.post(
            "/api/v1/usuarios/registro-cliente/",
            {
                "username": "cliente2",
                "password": "ClaveSegura123!",
                "rol": "ADMIN",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        usuario = Usuario.objects.get(username="cliente2")
        self.assertEqual(usuario.rol, Usuario.Rol.CLIENTE)

    def test_registro_cliente_rechaza_password_debil(self):
        resp = self.client.post(
            "/api/v1/usuarios/registro-cliente/",
            {"username": "cliente3", "password": "12345"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Usuario.objects.filter(username="cliente3").exists())


class GestionUsuariosAdminTests(APITestCase):
    def setUp(self):
        self.admin = crear_usuario("admin1", Usuario.Rol.ADMIN)
        self.trabajador = crear_usuario("trabajador1", Usuario.Rol.TRABAJADOR)
        self.repartidor = crear_usuario("repartidor1", Usuario.Rol.REPARTIDOR)
        self.cliente = crear_usuario("cliente_x", Usuario.Rol.CLIENTE)
        PerfilCliente.objects.create(usuario=self.cliente)

    def autenticar(self, usuario):
        self.client.force_authenticate(user=usuario)

    def test_admin_puede_crear_trabajador(self):
        self.autenticar(self.admin)
        resp = self.client.post(
            "/api/v1/usuarios/",
            {
                "username": "nuevo_trabajador",
                "password": "ClaveSegura123!",
                "rol": "TRABAJADOR",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

    def test_admin_puede_crear_repartidor_y_se_genera_perfil(self):
        self.autenticar(self.admin)
        resp = self.client.post(
            "/api/v1/usuarios/",
            {
                "username": "nuevo_repartidor",
                "password": "ClaveSegura123!",
                "rol": "REPARTIDOR",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        usuario = Usuario.objects.get(username="nuevo_repartidor")
        self.assertTrue(PerfilRepartidor.objects.filter(usuario=usuario).exists())

    def test_admin_no_puede_crear_usuario_con_rol_cliente(self):
        self.autenticar(self.admin)
        resp = self.client.post(
            "/api/v1/usuarios/",
            {
                "username": "intento_cliente",
                "password": "ClaveSegura123!",
                "rol": "CLIENTE",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_trabajador_no_puede_listar_usuarios(self):
        self.autenticar(self.trabajador)
        resp = self.client.get("/api/v1/usuarios/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_repartidor_no_puede_crear_usuarios(self):
        self.autenticar(self.repartidor)
        resp = self.client.post(
            "/api/v1/usuarios/",
            {"username": "x", "password": "ClaveSegura123!", "rol": "TRABAJADOR"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_cliente_no_puede_listar_usuarios(self):
        self.autenticar(self.cliente)
        resp = self.client.get("/api/v1/usuarios/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonimo_no_puede_listar_usuarios(self):
        resp = self.client.get("/api/v1/usuarios/")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_admin_puede_promover_trabajador_a_admin(self):
        self.autenticar(self.admin)
        resp = self.client.post(f"/api/v1/usuarios/{self.trabajador.id}/hacer-admin/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.trabajador.refresh_from_db()
        self.assertEqual(self.trabajador.rol, Usuario.Rol.ADMIN)

    def test_trabajador_no_puede_autopromoverse_a_admin(self):
        self.autenticar(self.trabajador)
        resp = self.client.post(f"/api/v1/usuarios/{self.trabajador.id}/hacer-admin/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.trabajador.refresh_from_db()
        self.assertEqual(self.trabajador.rol, Usuario.Rol.TRABAJADOR)

    def test_admin_puede_desactivar_y_reactivar_usuario(self):
        self.autenticar(self.admin)
        resp = self.client.post(f"/api/v1/usuarios/{self.trabajador.id}/desactivar/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.trabajador.refresh_from_db()
        self.assertFalse(self.trabajador.is_active)

        resp = self.client.post(f"/api/v1/usuarios/{self.trabajador.id}/activar/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.trabajador.refresh_from_db()
        self.assertTrue(self.trabajador.is_active)

    def test_usuarios_no_soporta_borrado_definitivo(self):
        self.autenticar(self.admin)
        resp = self.client.delete(f"/api/v1/usuarios/{self.trabajador.id}/")
        self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class PerfilPropioTests(APITestCase):
    def setUp(self):
        self.cliente = crear_usuario("cliente_me", Usuario.Rol.CLIENTE)
        PerfilCliente.objects.create(
            usuario=self.cliente, telefono="1111-1111", direccion_entrega_predeterminada="Zona 5"
        )
        self.trabajador = crear_usuario("trabajador_me", Usuario.Rol.TRABAJADOR)
        self.repartidor = crear_usuario("repartidor_me", Usuario.Rol.REPARTIDOR)
        PerfilRepartidor.objects.create(usuario=self.repartidor, telefono="2222-2222")

    def test_cliente_ve_su_telefono_y_direccion_no_calificacion(self):
        self.client.force_authenticate(user=self.cliente)
        resp = self.client.get("/api/v1/usuarios/me/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["telefono"], "1111-1111")
        self.assertEqual(resp.data["direccion_entrega_predeterminada"], "Zona 5")
        self.assertNotIn("calificacion_promedio", resp.data)

    def test_repartidor_ve_su_calificacion_no_direccion(self):
        self.client.force_authenticate(user=self.repartidor)
        resp = self.client.get("/api/v1/usuarios/me/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsNone(resp.data["calificacion_promedio"])
        self.assertNotIn("direccion_entrega_predeterminada", resp.data)

    def test_trabajador_no_ve_telefono_ni_direccion_ni_calificacion(self):
        self.client.force_authenticate(user=self.trabajador)
        resp = self.client.get("/api/v1/usuarios/me/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertNotIn("telefono", resp.data)
        self.assertNotIn("direccion_entrega_predeterminada", resp.data)
        self.assertNotIn("calificacion_promedio", resp.data)

    def test_usuario_no_puede_cambiar_su_propio_rol_via_me(self):
        self.client.force_authenticate(user=self.trabajador)
        resp = self.client.patch(
            "/api/v1/usuarios/me/", {"rol": "ADMIN"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.trabajador.refresh_from_db()
        self.assertEqual(self.trabajador.rol, Usuario.Rol.TRABAJADOR)

    def test_cliente_puede_actualizar_su_telefono(self):
        self.client.force_authenticate(user=self.cliente)
        resp = self.client.patch(
            "/api/v1/usuarios/me/", {"telefono": "9999-9999"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["telefono"], "9999-9999")


class AutenticacionJWTTests(APITestCase):
    def setUp(self):
        self.admin = crear_usuario("admin_auth", Usuario.Rol.ADMIN, password="ClaveSegura123!")

    def test_login_devuelve_access_y_refresh(self):
        resp = self.client.post(
            "/api/v1/auth/login/",
            {"username": "admin_auth", "password": "ClaveSegura123!"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("access", resp.data)
        self.assertIn("refresh", resp.data)

    def test_login_con_password_incorrecta_es_rechazado(self):
        resp = self.client.post(
            "/api/v1/auth/login/",
            {"username": "admin_auth", "password": "incorrecta"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_invalida_el_refresh_token(self):
        login = self.client.post(
            "/api/v1/auth/login/",
            {"username": "admin_auth", "password": "ClaveSegura123!"},
            format="json",
        )
        refresh = login.data["refresh"]
        access = login.data["access"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        logout_resp = self.client.post(
            "/api/v1/auth/logout/", {"refresh": refresh}, format="json"
        )
        self.assertEqual(logout_resp.status_code, status.HTTP_205_RESET_CONTENT)

        refresh_resp = self.client.post(
            "/api/v1/auth/refresh/", {"refresh": refresh}, format="json"
        )
        self.assertEqual(refresh_resp.status_code, status.HTTP_401_UNAUTHORIZED)
