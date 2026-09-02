"""Lógica de dominio de Pedidos, Entregas y Calificaciones.

Un pedido del cliente descuenta inventario de producto terminado igual que una
Venta de mostrador (misma tabla de movimientos, mismo bloqueo de sobreventa);
cancelarlo revierte ese inventario con un ajuste explícito, igual que anular una
venta. El resto (asignación de repartidor, cambios de estado, calificación) sigue
el flujo descrito en el sistema: PENDIENTE -> EN_PREPARACION -> EN_CAMINO ->
ENTREGADO, con CANCELADO como salida excepcional antes de EN_CAMINO.
"""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.notificaciones import services as notificaciones_services
from apps.notificaciones.models import Notificacion
from apps.produccion.models import MovimientoInventarioProductoTerminado, Paquete, Producto
from apps.usuarios.models import PerfilRepartidor

from .models import Calificacion, DetallePedido, Entrega, Pedido


def _notificar_cliente(*, pedido, mensaje):
    notificaciones_services.crear_notificacion(
        destinatario=pedido.cliente,
        tipo=Notificacion.Tipo.ESTADO_PEDIDO,
        titulo=f"Pedido #{pedido.numero}",
        mensaje=mensaje,
        referencia_id=pedido.id,
    )


@transaction.atomic
def registrar_pedido(*, cliente, items, direccion_entrega, telefono_contacto):
    if not items:
        raise ValidationError("Debe incluir al menos un producto en el pedido.")

    pedido = Pedido.objects.create(
        cliente=cliente,
        direccion_entrega=direccion_entrega,
        telefono_contacto=telefono_contacto,
    )

    total = Decimal("0")
    for item in items:
        producto = Producto.objects.select_for_update().get(pk=item["producto_id"])
        paquete = None
        cantidad = Decimal(item["cantidad"])
        if item.get("paquete_id"):
            try:
                paquete = Paquete.objects.get(pk=item["paquete_id"], producto=producto, activo=True)
            except Paquete.DoesNotExist:
                raise ValidationError(
                    f"El paquete indicado no existe o no corresponde al producto '{producto.nombre}'."
                )
            precio_unitario = paquete.precio_paquete
            cantidad_en_unidades = cantidad * paquete.unidades_por_paquete
        else:
            precio_unitario = producto.precio_unitario
            cantidad_en_unidades = cantidad

        if cantidad_en_unidades > producto.stock_actual:
            raise ValidationError(
                f"No hay suficiente '{producto.nombre}' disponible para este pedido."
            )

        subtotal = precio_unitario * cantidad
        DetallePedido.objects.create(
            pedido=pedido,
            producto=producto,
            paquete=paquete,
            cantidad=cantidad,
            cantidad_en_unidades=cantidad_en_unidades,
            precio_unitario=precio_unitario,
            subtotal=subtotal,
        )
        producto.stock_actual -= cantidad_en_unidades
        producto.save(update_fields=["stock_actual"])
        MovimientoInventarioProductoTerminado.objects.create(
            producto=producto,
            tipo=MovimientoInventarioProductoTerminado.Tipo.VENTA,
            cantidad=-cantidad_en_unidades,
            motivo=f"Pedido #{pedido.numero}",
            saldo_resultante=producto.stock_actual,
            creado_por=cliente,
        )
        total += subtotal

    pedido.total = total
    pedido.save(update_fields=["total"])

    _notificar_cliente(pedido=pedido, mensaje="Recibimos tu pedido y está pendiente de preparación.")
    notificaciones_services.notificar_admins(
        tipo=Notificacion.Tipo.NUEVO_PEDIDO,
        titulo=f"Nuevo pedido #{pedido.numero}",
        mensaje=f"{cliente.username} realizó un pedido por un total de Q{total}.",
        referencia_id=pedido.id,
    )
    return pedido


@transaction.atomic
def asignar_repartidor(*, pedido_id, repartidor, creado_por):
    pedido = Pedido.objects.select_for_update().get(pk=pedido_id)
    if pedido.estado not in (Pedido.Estado.PENDIENTE, Pedido.Estado.EN_PREPARACION):
        raise ValidationError(
            "Solo se puede asignar repartidor a un pedido pendiente o en preparación."
        )
    if hasattr(pedido, "entrega"):
        raise ValidationError("Este pedido ya tiene un repartidor asignado.")
    Entrega.objects.create(pedido=pedido, repartidor=repartidor, creado_por=creado_por)
    if pedido.estado == Pedido.Estado.PENDIENTE:
        pedido.estado = Pedido.Estado.EN_PREPARACION
        pedido.save(update_fields=["estado"])

    notificaciones_services.crear_notificacion(
        destinatario=repartidor,
        tipo=Notificacion.Tipo.PEDIDO_ASIGNADO,
        titulo=f"Nuevo pedido asignado #{pedido.numero}",
        mensaje=f"Se te asignó el pedido #{pedido.numero} para entrega en: {pedido.direccion_entrega}.",
        referencia_id=pedido.id,
    )
    _notificar_cliente(pedido=pedido, mensaje="Tu pedido está en preparación.")
    return pedido


@transaction.atomic
def marcar_en_camino(*, pedido_id, repartidor):
    pedido = Pedido.objects.select_for_update().get(pk=pedido_id)
    if not hasattr(pedido, "entrega") or pedido.entrega.repartidor_id != repartidor.id:
        raise ValidationError("Este pedido no está asignado a este repartidor.")
    if pedido.estado != Pedido.Estado.EN_PREPARACION:
        raise ValidationError("Solo un pedido en preparación puede pasar a 'en camino'.")
    pedido.estado = Pedido.Estado.EN_CAMINO
    pedido.save(update_fields=["estado"])
    _notificar_cliente(pedido=pedido, mensaje="Tu pedido va en camino.")
    return pedido


@transaction.atomic
def marcar_entregado(*, pedido_id, repartidor):
    pedido = Pedido.objects.select_for_update().get(pk=pedido_id)
    if not hasattr(pedido, "entrega") or pedido.entrega.repartidor_id != repartidor.id:
        raise ValidationError("Este pedido no está asignado a este repartidor.")
    if pedido.estado != Pedido.Estado.EN_CAMINO:
        raise ValidationError("Solo un pedido en camino puede marcarse como entregado.")
    pedido.estado = Pedido.Estado.ENTREGADO
    pedido.save(update_fields=["estado"])
    entrega = pedido.entrega
    entrega.fecha_entrega = timezone.now()
    entrega.save(update_fields=["fecha_entrega"])
    _notificar_cliente(pedido=pedido, mensaje="Tu pedido fue entregado. ¡Gracias por tu compra!")
    return pedido


@transaction.atomic
def cancelar_pedido(*, pedido_id, motivo, creado_por, solo_si_pendiente=False):
    pedido = Pedido.objects.select_for_update().get(pk=pedido_id)
    if solo_si_pendiente and pedido.estado != Pedido.Estado.PENDIENTE:
        raise ValidationError("Solo se puede cancelar un pedido mientras está pendiente.")
    if pedido.estado in (Pedido.Estado.EN_CAMINO, Pedido.Estado.ENTREGADO, Pedido.Estado.CANCELADO):
        raise ValidationError("Este pedido ya no se puede cancelar.")

    for detalle in pedido.detalles.select_related("producto"):
        producto = Producto.objects.select_for_update().get(pk=detalle.producto_id)
        producto.stock_actual += detalle.cantidad_en_unidades
        producto.save(update_fields=["stock_actual"])
        MovimientoInventarioProductoTerminado.objects.create(
            producto=producto,
            tipo=MovimientoInventarioProductoTerminado.Tipo.AJUSTE,
            cantidad=detalle.cantidad_en_unidades,
            motivo=f"Cancelación de pedido #{pedido.numero}: {motivo}",
            saldo_resultante=producto.stock_actual,
            creado_por=creado_por,
        )

    pedido.estado = Pedido.Estado.CANCELADO
    pedido.save(update_fields=["estado"])

    _notificar_cliente(pedido=pedido, mensaje=f"Tu pedido fue cancelado: {motivo}")
    if hasattr(pedido, "entrega"):
        notificaciones_services.crear_notificacion(
            destinatario=pedido.entrega.repartidor,
            tipo=Notificacion.Tipo.ESTADO_PEDIDO,
            titulo=f"Pedido #{pedido.numero} cancelado",
            mensaje=f"El pedido #{pedido.numero} que tenías asignado fue cancelado: {motivo}",
            referencia_id=pedido.id,
        )
    return pedido


@transaction.atomic
def calificar_repartidor(*, pedido_id, cliente, estrellas, comentario=""):
    pedido = Pedido.objects.select_related("entrega").get(pk=pedido_id)
    if pedido.estado != Pedido.Estado.ENTREGADO:
        raise ValidationError("Solo se puede calificar un pedido ya entregado.")
    if not hasattr(pedido, "entrega"):
        raise ValidationError("Este pedido no tiene repartidor asignado.")
    entrega = pedido.entrega
    if hasattr(entrega, "calificacion"):
        raise ValidationError("Este pedido ya fue calificado.")

    calificacion = Calificacion.objects.create(
        entrega=entrega,
        cliente=cliente,
        repartidor=entrega.repartidor,
        estrellas=estrellas,
        comentario=comentario,
    )
    _recalcular_promedio_repartidor(entrega.repartidor)
    return calificacion


def _recalcular_promedio_repartidor(repartidor):
    from django.db.models import Avg

    promedio = Calificacion.objects.filter(repartidor=repartidor).aggregate(p=Avg("estrellas"))["p"]
    perfil, _ = PerfilRepartidor.objects.get_or_create(usuario=repartidor)
    perfil.calificacion_promedio = round(Decimal(promedio), 2) if promedio is not None else None
    perfil.save(update_fields=["calificacion_promedio"])
