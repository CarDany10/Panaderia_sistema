from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from apps.produccion import services as produccion_services
from apps.produccion.models import Paquete, Producto
from apps.usuarios.models import PerfilCliente, PerfilRepartidor, Usuario

from . import services
from .models import Pedido


def crear_usuario(username, rol):
    u = Usuario.objects.create_user(username=username, password="ClaveSegura123!", rol=rol)
    if rol == Usuario.Rol.CLIENTE:
        PerfilCliente.objects.create(usuario=u)
    elif rol == Usuario.Rol.REPARTIDOR:
        PerfilRepartidor.objects.create(usuario=u)
    return u


class RegistrarPedidoTests(APITestCase):
    def setUp(self):
        self.admin = crear_usuario("admin_ped", Usuario.Rol.ADMIN)
        self.cliente = crear_usuario("cliente_ped", Usuario.Rol.CLIENTE)
        self.producto = Producto.objects.create(nombre="Pan Francés PD", precio_unitario=Decimal("1.50"))
        produccion_services.registrar_ajuste_producto_terminado(
            producto_id=self.producto.id, cantidad_delta=Decimal("100"), motivo="Carga inicial", creado_por=self.admin
        )

    def test_registrar_pedido_descuenta_stock_y_calcula_total(self):
        pedido = services.registrar_pedido(
            cliente=self.cliente,
            items=[{"producto_id": self.producto.id, "cantidad": Decimal("10"), "paquete_id": None}],
            direccion_entrega="Zona 1",
            telefono_contacto="5555-5555",
        )
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_actual, Decimal("90"))
        self.assertEqual(pedido.total, Decimal("15.00"))
        self.assertEqual(pedido.estado, Pedido.Estado.PENDIENTE)

    def test_no_permite_pedir_mas_de_lo_disponible(self):
        with self.assertRaises(Exception):
            services.registrar_pedido(
                cliente=self.cliente,
                items=[{"producto_id": self.producto.id, "cantidad": Decimal("9999"), "paquete_id": None}],
                direccion_entrega="Zona 1",
                telefono_contacto="5555-5555",
            )
        self.assertEqual(Pedido.objects.count(), 0)

    def test_api_cliente_crea_pedido(self):
        self.client.force_authenticate(user=self.cliente)
        resp = self.client.post(
            "/api/v1/pedidos/",
            {
                "direccion_entrega": "Zona 1",
                "telefono_contacto": "5555-5555",
                "items": [{"producto": self.producto.id, "cantidad": "5"}],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data["estado"], "PENDIENTE")

    def test_api_trabajador_no_puede_crear_pedido(self):
        trabajador = crear_usuario("trab_ped", Usuario.Rol.TRABAJADOR)
        self.client.force_authenticate(user=trabajador)
        resp = self.client.post(
            "/api/v1/pedidos/",
            {"direccion_entrega": "Z", "telefono_contacto": "1", "items": [{"producto": self.producto.id, "cantidad": "1"}]},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class VisibilidadPedidoTests(APITestCase):
    def setUp(self):
        self.admin = crear_usuario("admin_vp", Usuario.Rol.ADMIN)
        self.cliente1 = crear_usuario("cliente_vp1", Usuario.Rol.CLIENTE)
        self.cliente2 = crear_usuario("cliente_vp2", Usuario.Rol.CLIENTE)
        self.trabajador = crear_usuario("trab_vp", Usuario.Rol.TRABAJADOR)
        self.repartidor1 = crear_usuario("rep_vp1", Usuario.Rol.REPARTIDOR)
        self.repartidor2 = crear_usuario("rep_vp2", Usuario.Rol.REPARTIDOR)
        self.producto = Producto.objects.create(nombre="Rosca VP", precio_unitario=Decimal("2.00"))
        produccion_services.registrar_ajuste_producto_terminado(
            producto_id=self.producto.id, cantidad_delta=Decimal("100"), motivo="Carga", creado_por=self.admin
        )
        self.pedido = services.registrar_pedido(
            cliente=self.cliente1,
            items=[{"producto_id": self.producto.id, "cantidad": Decimal("5"), "paquete_id": None}],
            direccion_entrega="Zona 1",
            telefono_contacto="5555-5555",
        )

    def test_cliente_dueno_ve_su_pedido(self):
        self.client.force_authenticate(user=self.cliente1)
        resp = self.client.get(f"/api/v1/pedidos/{self.pedido.id}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_otro_cliente_no_ve_el_pedido(self):
        self.client.force_authenticate(user=self.cliente2)
        resp = self.client.get(f"/api/v1/pedidos/{self.pedido.id}/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_trabajador_ve_pedido_sin_precios_ni_cliente(self):
        self.client.force_authenticate(user=self.trabajador)
        resp = self.client.get(f"/api/v1/pedidos/{self.pedido.id}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertNotIn("total", resp.data)
        self.assertNotIn("cliente", resp.data)
        self.assertNotIn("direccion_entrega", resp.data)

    def test_repartidor_no_asignado_no_ve_el_pedido(self):
        self.client.force_authenticate(user=self.repartidor1)
        resp = self.client.get(f"/api/v1/pedidos/{self.pedido.id}/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_ve_todo(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get(f"/api/v1/pedidos/{self.pedido.id}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("total", resp.data)


class FlujoEntregaYCalificacionTests(APITestCase):
    def setUp(self):
        self.admin = crear_usuario("admin_flujo", Usuario.Rol.ADMIN)
        self.cliente = crear_usuario("cliente_flujo", Usuario.Rol.CLIENTE)
        self.repartidor = crear_usuario("rep_flujo", Usuario.Rol.REPARTIDOR)
        self.otro_repartidor = crear_usuario("rep_flujo_otro", Usuario.Rol.REPARTIDOR)
        self.producto = Producto.objects.create(nombre="Concha", precio_unitario=Decimal("1.00"))
        produccion_services.registrar_ajuste_producto_terminado(
            producto_id=self.producto.id, cantidad_delta=Decimal("50"), motivo="Carga", creado_por=self.admin
        )
        self.pedido = services.registrar_pedido(
            cliente=self.cliente,
            items=[{"producto_id": self.producto.id, "cantidad": Decimal("5"), "paquete_id": None}],
            direccion_entrega="Zona 2",
            telefono_contacto="4444-4444",
        )

    def test_flujo_completo_asignacion_entrega_calificacion(self):
        # Admin asigna repartidor.
        pedido = services.asignar_repartidor(pedido_id=self.pedido.id, repartidor=self.repartidor, creado_por=self.admin)
        self.assertEqual(pedido.estado, Pedido.Estado.EN_PREPARACION)

        # El repartidor marca en camino y luego entregado.
        pedido = services.marcar_en_camino(pedido_id=pedido.id, repartidor=self.repartidor)
        self.assertEqual(pedido.estado, Pedido.Estado.EN_CAMINO)
        pedido = services.marcar_entregado(pedido_id=pedido.id, repartidor=self.repartidor)
        self.assertEqual(pedido.estado, Pedido.Estado.ENTREGADO)
        self.assertIsNotNone(pedido.entrega.fecha_entrega)

        # El cliente califica.
        calificacion = services.calificar_repartidor(
            pedido_id=pedido.id, cliente=self.cliente, estrellas=5, comentario="Excelente"
        )
        self.assertEqual(calificacion.estrellas, 5)
        perfil = PerfilRepartidor.objects.get(usuario=self.repartidor)
        self.assertEqual(perfil.calificacion_promedio, Decimal("5.00"))

    def test_no_se_puede_asignar_repartidor_dos_veces(self):
        services.asignar_repartidor(pedido_id=self.pedido.id, repartidor=self.repartidor, creado_por=self.admin)
        with self.assertRaises(Exception):
            services.asignar_repartidor(pedido_id=self.pedido.id, repartidor=self.otro_repartidor, creado_por=self.admin)

    def test_otro_repartidor_no_puede_marcar_en_camino(self):
        services.asignar_repartidor(pedido_id=self.pedido.id, repartidor=self.repartidor, creado_por=self.admin)
        with self.assertRaises(Exception):
            services.marcar_en_camino(pedido_id=self.pedido.id, repartidor=self.otro_repartidor)

    def test_no_se_puede_marcar_entregado_sin_pasar_por_en_camino(self):
        services.asignar_repartidor(pedido_id=self.pedido.id, repartidor=self.repartidor, creado_por=self.admin)
        with self.assertRaises(Exception):
            services.marcar_entregado(pedido_id=self.pedido.id, repartidor=self.repartidor)

    def test_no_se_puede_calificar_antes_de_entregado(self):
        services.asignar_repartidor(pedido_id=self.pedido.id, repartidor=self.repartidor, creado_por=self.admin)
        with self.assertRaises(Exception):
            services.calificar_repartidor(pedido_id=self.pedido.id, cliente=self.cliente, estrellas=5)

    def test_no_se_puede_calificar_dos_veces(self):
        services.asignar_repartidor(pedido_id=self.pedido.id, repartidor=self.repartidor, creado_por=self.admin)
        services.marcar_en_camino(pedido_id=self.pedido.id, repartidor=self.repartidor)
        services.marcar_entregado(pedido_id=self.pedido.id, repartidor=self.repartidor)
        services.calificar_repartidor(pedido_id=self.pedido.id, cliente=self.cliente, estrellas=4)
        with self.assertRaises(Exception):
            services.calificar_repartidor(pedido_id=self.pedido.id, cliente=self.cliente, estrellas=3)

    def test_api_flujo_completo(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post(
            f"/api/v1/pedidos/{self.pedido.id}/asignar-repartidor/",
            {"repartidor": self.repartidor.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)

        self.client.force_authenticate(user=self.repartidor)
        resp = self.client.post(f"/api/v1/pedidos/{self.pedido.id}/marcar-en-camino/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp = self.client.post(f"/api/v1/pedidos/{self.pedido.id}/marcar-entregado/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.client.force_authenticate(user=self.cliente)
        resp = self.client.post(
            f"/api/v1/pedidos/{self.pedido.id}/calificar/", {"estrellas": 5}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)

        # El promedio del repartidor queda visible en su propio perfil. Se vuelve a
        # consultar el usuario (en vez de reusar self.repartidor) porque ese objeto
        # de Python ya tiene cacheada la relación perfil_repartidor desde el setUp,
        # de antes de que el promedio se actualizara.
        repartidor_actualizado = Usuario.objects.get(pk=self.repartidor.id)
        self.client.force_authenticate(user=repartidor_actualizado)
        resp = self.client.get("/api/v1/usuarios/me/")
        self.assertEqual(resp.data["calificacion_promedio"], Decimal("5.00"))

    def test_api_repartidor_no_puede_calificar(self):
        self.client.force_authenticate(user=self.repartidor)
        resp = self.client.post(f"/api/v1/pedidos/{self.pedido.id}/calificar/", {"estrellas": 5}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_api_cliente_no_puede_asignar_repartidor(self):
        self.client.force_authenticate(user=self.cliente)
        resp = self.client.post(
            f"/api/v1/pedidos/{self.pedido.id}/asignar-repartidor/", {"repartidor": self.repartidor.id}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class CancelarPedidoTests(APITestCase):
    def setUp(self):
        self.admin = crear_usuario("admin_cancel", Usuario.Rol.ADMIN)
        self.cliente = crear_usuario("cliente_cancel", Usuario.Rol.CLIENTE)
        self.repartidor = crear_usuario("rep_cancel", Usuario.Rol.REPARTIDOR)
        self.producto = Producto.objects.create(nombre="Torta Cancel", precio_unitario=Decimal("5.00"))
        produccion_services.registrar_ajuste_producto_terminado(
            producto_id=self.producto.id, cantidad_delta=Decimal("20"), motivo="Carga", creado_por=self.admin
        )
        self.pedido = services.registrar_pedido(
            cliente=self.cliente,
            items=[{"producto_id": self.producto.id, "cantidad": Decimal("4"), "paquete_id": None}],
            direccion_entrega="Zona 3",
            telefono_contacto="3333-3333",
        )

    def test_cliente_cancela_pedido_pendiente_revierte_stock(self):
        services.cancelar_pedido(
            pedido_id=self.pedido.id, motivo="Cambié de opinión", creado_por=self.cliente, solo_si_pendiente=True
        )
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_actual, Decimal("20"))
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado, Pedido.Estado.CANCELADO)

    def test_cliente_no_puede_cancelar_pedido_en_preparacion(self):
        services.asignar_repartidor(pedido_id=self.pedido.id, repartidor=self.repartidor, creado_por=self.admin)
        with self.assertRaises(Exception):
            services.cancelar_pedido(
                pedido_id=self.pedido.id, motivo="intento", creado_por=self.cliente, solo_si_pendiente=True
            )

    def test_admin_puede_cancelar_pedido_en_preparacion(self):
        services.asignar_repartidor(pedido_id=self.pedido.id, repartidor=self.repartidor, creado_por=self.admin)
        services.cancelar_pedido(pedido_id=self.pedido.id, motivo="Producto dañado", creado_por=self.admin)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock_actual, Decimal("20"))

    def test_no_se_puede_cancelar_pedido_en_camino(self):
        services.asignar_repartidor(pedido_id=self.pedido.id, repartidor=self.repartidor, creado_por=self.admin)
        services.marcar_en_camino(pedido_id=self.pedido.id, repartidor=self.repartidor)
        with self.assertRaises(Exception):
            services.cancelar_pedido(pedido_id=self.pedido.id, motivo="tarde", creado_por=self.admin)

    def test_api_cliente_cancela_su_propio_pedido(self):
        self.client.force_authenticate(user=self.cliente)
        resp = self.client.post(f"/api/v1/pedidos/{self.pedido.id}/cancelar/", {"motivo": "Ya no lo quiero"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data["estado"], "CANCELADO")


class NotificacionesDePedidoTests(APITestCase):
    def setUp(self):
        from apps.notificaciones.models import Notificacion

        self.Notificacion = Notificacion
        self.admin = crear_usuario("admin_notif_ped", Usuario.Rol.ADMIN)
        self.cliente = crear_usuario("cliente_notif_ped", Usuario.Rol.CLIENTE)
        self.repartidor = crear_usuario("rep_notif_ped", Usuario.Rol.REPARTIDOR)
        self.producto = Producto.objects.create(nombre="Pan Notif", precio_unitario=Decimal("1.00"))
        produccion_services.registrar_ajuste_producto_terminado(
            producto_id=self.producto.id, cantidad_delta=Decimal("50"), motivo="Carga", creado_por=self.admin
        )

    def test_crear_pedido_notifica_cliente_y_admin(self):
        pedido = services.registrar_pedido(
            cliente=self.cliente,
            items=[{"producto_id": self.producto.id, "cantidad": Decimal("3"), "paquete_id": None}],
            direccion_entrega="Zona 4",
            telefono_contacto="1111-2222",
        )
        self.assertTrue(
            self.Notificacion.objects.filter(
                destinatario=self.cliente, tipo=self.Notificacion.Tipo.ESTADO_PEDIDO, referencia_id=pedido.id
            ).exists()
        )
        self.assertTrue(
            self.Notificacion.objects.filter(
                destinatario=self.admin, tipo=self.Notificacion.Tipo.NUEVO_PEDIDO, referencia_id=pedido.id
            ).exists()
        )

    def test_flujo_completo_genera_notificacion_en_cada_paso(self):
        pedido = services.registrar_pedido(
            cliente=self.cliente,
            items=[{"producto_id": self.producto.id, "cantidad": Decimal("2"), "paquete_id": None}],
            direccion_entrega="Zona 4",
            telefono_contacto="1111-2222",
        )
        services.asignar_repartidor(pedido_id=pedido.id, repartidor=self.repartidor, creado_por=self.admin)
        self.assertTrue(
            self.Notificacion.objects.filter(
                destinatario=self.repartidor, tipo=self.Notificacion.Tipo.PEDIDO_ASIGNADO
            ).exists()
        )
        services.marcar_en_camino(pedido_id=pedido.id, repartidor=self.repartidor)
        services.marcar_entregado(pedido_id=pedido.id, repartidor=self.repartidor)

        mensajes_cliente = list(
            self.Notificacion.objects.filter(
                destinatario=self.cliente, tipo=self.Notificacion.Tipo.ESTADO_PEDIDO
            ).values_list("mensaje", flat=True)
        )
        # Recibido, en preparación, en camino, entregado.
        self.assertEqual(len(mensajes_cliente), 4)

    def test_cancelar_pedido_notifica_a_cliente_y_repartidor_asignado(self):
        pedido = services.registrar_pedido(
            cliente=self.cliente,
            items=[{"producto_id": self.producto.id, "cantidad": Decimal("2"), "paquete_id": None}],
            direccion_entrega="Zona 4",
            telefono_contacto="1111-2222",
        )
        services.asignar_repartidor(pedido_id=pedido.id, repartidor=self.repartidor, creado_por=self.admin)
        services.cancelar_pedido(pedido_id=pedido.id, motivo="Sin insumos", creado_por=self.admin)

        self.assertTrue(
            self.Notificacion.objects.filter(destinatario=self.repartidor, titulo__icontains="cancelado").exists()
        )
