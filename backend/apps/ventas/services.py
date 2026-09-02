"""Lógica de dominio de Ventas de producto terminado.

Cada venta descuenta inventario real (nunca cantidades superiores a las
disponibles) y queda registrada de forma permanente; anular una venta no borra
el registro, revierte el inventario con un ajuste explícito y trazable.
"""

from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.produccion.models import MovimientoInventarioProductoTerminado, Paquete, Producto

from .models import DetalleVenta, Venta


@transaction.atomic
def registrar_venta(*, cliente_id, items, creado_por, metodo_pago="", direccion_entrega=""):
    if not items:
        raise ValidationError("Debe incluir al menos un producto en la venta.")

    venta = Venta.objects.create(
        cliente_id=cliente_id,
        metodo_pago=metodo_pago,
        direccion_entrega=direccion_entrega,
        creado_por=creado_por,
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
                f"No hay suficiente producto terminado disponible de '{producto.nombre}' para esta venta."
            )

        subtotal = precio_unitario * cantidad
        DetalleVenta.objects.create(
            venta=venta,
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
            motivo=f"Venta #{venta.numero}",
            saldo_resultante=producto.stock_actual,
            creado_por=creado_por,
        )
        total += subtotal

    venta.total = total
    venta.save(update_fields=["total"])
    return venta


@transaction.atomic
def anular_venta(*, venta_id, motivo, creado_por):
    venta = Venta.objects.select_for_update().get(pk=venta_id)
    if venta.estado == Venta.Estado.ANULADA:
        raise ValidationError("La venta ya está anulada.")

    for detalle in venta.detalles.select_related("producto"):
        producto = Producto.objects.select_for_update().get(pk=detalle.producto_id)
        producto.stock_actual += detalle.cantidad_en_unidades
        producto.save(update_fields=["stock_actual"])
        MovimientoInventarioProductoTerminado.objects.create(
            producto=producto,
            tipo=MovimientoInventarioProductoTerminado.Tipo.AJUSTE,
            cantidad=detalle.cantidad_en_unidades,
            motivo=f"Anulación de venta #{venta.numero}: {motivo}",
            saldo_resultante=producto.stock_actual,
            creado_por=creado_por,
        )

    venta.estado = Venta.Estado.ANULADA
    venta.save(update_fields=["estado"])
    return venta
