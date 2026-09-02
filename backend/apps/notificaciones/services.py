"""Creación de notificaciones. Pensado para que otros módulos (materia prima,
pedidos, calendario, etc.) llamen a estas funciones tras completar su propia
operación — la notificación nunca es la causa de un fallo de negocio: si algo
sale mal aquí, es un problema aparte de la operación principal que la originó.

La arquitectura queda abierta a otros canales (correo, push) más adelante: hoy
solo se persiste en Notificacion (canal "in-app"), pero nada impide añadir un
envío adicional dentro de crear_notificacion sin tocar a quienes la llaman.
"""

from .models import Notificacion


def crear_notificacion(*, destinatario, tipo, titulo, mensaje, referencia_id=None):
    return Notificacion.objects.create(
        destinatario=destinatario,
        tipo=tipo,
        titulo=titulo,
        mensaje=mensaje,
        referencia_id=referencia_id,
    )


def notificar_admins(*, tipo, titulo, mensaje, referencia_id=None):
    from apps.usuarios.models import Usuario

    admins = Usuario.objects.filter(rol=Usuario.Rol.ADMIN, is_active=True)
    return [
        crear_notificacion(
            destinatario=admin, tipo=tipo, titulo=titulo, mensaje=mensaje, referencia_id=referencia_id
        )
        for admin in admins
    ]


def marcar_leida(*, notificacion_id, usuario):
    notificacion = Notificacion.objects.get(pk=notificacion_id, destinatario=usuario)
    notificacion.leida = True
    notificacion.save(update_fields=["leida"])
    return notificacion


def marcar_todas_leidas(*, usuario):
    Notificacion.objects.filter(destinatario=usuario, leida=False).update(leida=True)
