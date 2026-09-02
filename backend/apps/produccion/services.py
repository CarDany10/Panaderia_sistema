"""Lógica de dominio de Producción y Producto Terminado.

Como en apps.materia_prima, ninguna existencia de Producto cambia salvo a través
de un movimiento con motivo — y toda producción consume materia prima real vía el
mismo mecanismo FIFO de lotes que ya usa Merma de materia prima (Fase 6).
"""

from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.materia_prima import services as materia_prima_services
from apps.materia_prima.models import MateriaPrima, MovimientoInventarioMateriaPrima

from .models import ConsumoMateriaPrima, MovimientoInventarioProductoTerminado, Producto, Produccion


@transaction.atomic
def registrar_produccion(
    *,
    producto_id,
    fecha,
    cantidad_planificada,
    cantidad_producida,
    cantidad_merma,
    consumos,  # lista de {materia_prima_id, cantidad, unidad_medida}
    creado_por,
):
    cantidad_producida = Decimal(cantidad_producida)
    cantidad_merma = Decimal(cantidad_merma or 0)
    if cantidad_producida <= 0:
        raise ValidationError("La cantidad producida debe ser mayor a cero.")
    if cantidad_merma < 0:
        raise ValidationError("La merma no puede ser negativa.")
    if cantidad_merma > cantidad_producida:
        raise ValidationError("La merma no puede superar la cantidad producida.")
    if not consumos:
        raise ValidationError("Debe registrarse al menos un consumo de materia prima.")

    producto = Producto.objects.select_for_update().get(pk=producto_id)

    produccion = Produccion.objects.create(
        producto=producto,
        fecha=fecha,
        cantidad_planificada=Decimal(cantidad_planificada),
        cantidad_producida=cantidad_producida,
        cantidad_merma=cantidad_merma,
        creado_por=creado_por,
    )

    costo_total = Decimal("0")
    for item in consumos:
        materia_prima = MateriaPrima.objects.get(pk=item["materia_prima_id"])
        cantidad_nativa = materia_prima_services.convertir_cantidad(
            item["cantidad"], item["unidad_medida"], materia_prima.unidad_medida
        )
        movimientos = materia_prima_services.consumir_fifo(
            materia_prima_id=materia_prima.id,
            cantidad_nativa=cantidad_nativa,
            tipo=MovimientoInventarioMateriaPrima.Tipo.PRODUCCION,
            motivo=f"Producción #{produccion.numero} - {producto.nombre}",
            creado_por=creado_por,
        )
        costo_consumo = sum(
            (abs(m.cantidad) * m.compra.costo_unitario_nativo for m in movimientos),
            Decimal("0"),
        )
        consumo = ConsumoMateriaPrima.objects.create(
            produccion=produccion,
            materia_prima=materia_prima,
            cantidad=item["cantidad"],
            unidad_medida=item["unidad_medida"],
            costo_correspondiente=costo_consumo,
        )
        consumo.movimientos.set(movimientos)
        costo_total += costo_consumo

    produccion.costo_total = costo_total
    produccion.costo_unitario = costo_total / cantidad_producida
    produccion.save(update_fields=["costo_total", "costo_unitario"])

    producto.stock_actual += cantidad_producida
    producto.save(update_fields=["stock_actual"])
    MovimientoInventarioProductoTerminado.objects.create(
        producto=producto,
        tipo=MovimientoInventarioProductoTerminado.Tipo.PRODUCCION,
        cantidad=cantidad_producida,
        motivo=f"Producción #{produccion.numero}",
        saldo_resultante=producto.stock_actual,
        creado_por=creado_por,
    )
    if cantidad_merma > 0:
        producto.stock_actual -= cantidad_merma
        producto.save(update_fields=["stock_actual"])
        MovimientoInventarioProductoTerminado.objects.create(
            producto=producto,
            tipo=MovimientoInventarioProductoTerminado.Tipo.MERMA,
            cantidad=-cantidad_merma,
            motivo=f"Merma de producción #{produccion.numero}",
            saldo_resultante=producto.stock_actual,
            creado_por=creado_por,
        )

    return produccion


@transaction.atomic
def registrar_merma_producto_terminado(*, producto_id, cantidad, motivo, creado_por):
    """Merma de producto terminado independiente de una producción (p. ej. se dañó
    en anaquel). A diferencia de la materia prima, el producto terminado no tiene
    lotes con costo propio: la salida es simplemente de cantidad, sin atribución
    de costo adicional."""
    producto = Producto.objects.select_for_update().get(pk=producto_id)
    cantidad = Decimal(cantidad)
    if cantidad <= 0:
        raise ValidationError("La cantidad debe ser mayor a cero.")
    if cantidad > producto.stock_actual:
        raise ValidationError("No hay suficiente producto terminado disponible para esta merma.")
    producto.stock_actual -= cantidad
    producto.save(update_fields=["stock_actual"])
    return MovimientoInventarioProductoTerminado.objects.create(
        producto=producto,
        tipo=MovimientoInventarioProductoTerminado.Tipo.MERMA,
        cantidad=-cantidad,
        motivo=motivo,
        saldo_resultante=producto.stock_actual,
        creado_por=creado_por,
    )


@transaction.atomic
def registrar_ajuste_producto_terminado(*, producto_id, cantidad_delta, motivo, creado_por):
    producto = Producto.objects.select_for_update().get(pk=producto_id)
    cantidad_delta = Decimal(cantidad_delta)
    if cantidad_delta == 0:
        raise ValidationError("El ajuste no puede ser de cantidad cero.")
    nuevo_stock = producto.stock_actual + cantidad_delta
    if nuevo_stock < 0:
        raise ValidationError("El ajuste dejaría el inventario en negativo.")
    producto.stock_actual = nuevo_stock
    producto.save(update_fields=["stock_actual"])
    return MovimientoInventarioProductoTerminado.objects.create(
        producto=producto,
        tipo=MovimientoInventarioProductoTerminado.Tipo.AJUSTE,
        cantidad=cantidad_delta,
        motivo=motivo,
        saldo_resultante=producto.stock_actual,
        creado_por=creado_por,
    )
