"""Lógica de dominio del inventario de materia prima.

Todo cambio de existencia pasa por aquí (nunca se escribe stock_actual desde una
vista directamente), para garantizar que cada movimiento quede registrado con su
motivo y trazabilidad (regla de negocio: ninguna cantidad desaparece sin explicación).
"""

from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import ValidationError

from .models import Compra, MateriaPrima, MovimientoInventarioMateriaPrima

FACTOR_LB_A_OZ = Decimal("16")


def convertir_cantidad(cantidad, de_unidad, a_unidad):
    """1 libra = 16 onzas. Nunca se usa float para no perder precisión."""
    cantidad = Decimal(cantidad)
    if de_unidad == a_unidad:
        return cantidad
    if de_unidad == "LB" and a_unidad == "OZ":
        return cantidad * FACTOR_LB_A_OZ
    if de_unidad == "OZ" and a_unidad == "LB":
        return cantidad / FACTOR_LB_A_OZ
    raise ValidationError(f"Conversión no soportada de {de_unidad} a {a_unidad}.")


def convertir_costo_unitario(costo_unitario, de_unidad, a_unidad):
    """Convierte un costo-por-unidad de de_unidad a a_unidad, de forma consistente
    con convertir_cantidad (si 1 lb = 16 oz, el costo por oz es 1/16 del costo por lb)."""
    equivalencia = convertir_cantidad(Decimal("1"), a_unidad, de_unidad)
    return Decimal(costo_unitario) * equivalencia


@transaction.atomic
def registrar_compra(
    *,
    materia_prima_id,
    lote,
    cantidad,
    unidad_medida,
    costo_total,
    fecha_compra,
    creado_por,
    costo_unitario=None,
):
    materia_prima = MateriaPrima.objects.select_for_update().get(pk=materia_prima_id)
    cantidad = Decimal(cantidad)
    costo_total = Decimal(costo_total)
    if cantidad <= 0:
        raise ValidationError("La cantidad comprada debe ser mayor a cero.")

    # Costo unitario auto-calculado de ESTA compra si no se indica; nunca un
    # promedio de compras anteriores (regla de negocio).
    costo_unitario = Decimal(costo_unitario) if costo_unitario is not None else (
        costo_total / cantidad
    )

    cantidad_nativa = convertir_cantidad(cantidad, unidad_medida, materia_prima.unidad_medida)

    compra = Compra.objects.create(
        materia_prima=materia_prima,
        lote=lote,
        cantidad=cantidad,
        unidad_medida=unidad_medida,
        cantidad_nativa=cantidad_nativa,
        cantidad_restante=cantidad_nativa,
        costo_total=costo_total,
        costo_unitario=costo_unitario,
        fecha_compra=fecha_compra,
        creado_por=creado_por,
    )
    materia_prima.stock_actual += cantidad_nativa
    materia_prima.save(update_fields=["stock_actual"])
    MovimientoInventarioMateriaPrima.objects.create(
        materia_prima=materia_prima,
        tipo=MovimientoInventarioMateriaPrima.Tipo.COMPRA,
        cantidad=cantidad_nativa,
        compra=compra,
        motivo=f"Compra lote {lote}",
        saldo_resultante=materia_prima.stock_actual,
        creado_por=creado_por,
    )
    return compra


@transaction.atomic
def consumir_fifo(*, materia_prima_id, cantidad_nativa, tipo, motivo, creado_por):
    """Descuenta cantidad_nativa de los lotes de Compra disponibles, en orden FIFO
    por fecha de compra, generando un movimiento por cada lote afectado (para
    conservar el costo exacto consumido de cada uno). Usado por Merma directa de
    materia prima (esta fase) y por Consumo en producción (Fase 7).

    Nunca deja el stock en negativo: si la cantidad solicitada supera la
    existencia, se rechaza con un mensaje genérico (sin exponer cifras a quien no
    debe verlas; el detalle numérico solo lo recibe quien tiene permiso, vía la
    vista que llama a este servicio).
    """
    materia_prima = MateriaPrima.objects.select_for_update().get(pk=materia_prima_id)
    cantidad_nativa = Decimal(cantidad_nativa)
    if cantidad_nativa <= 0:
        raise ValidationError("La cantidad debe ser mayor a cero.")
    if cantidad_nativa > materia_prima.stock_actual:
        raise ValidationError(
            "Materia prima insuficiente para esta operación: "
            f"disponible {materia_prima.stock_actual}, solicitado {cantidad_nativa}."
        )

    restante = cantidad_nativa
    movimientos = []
    lotes = Compra.objects.select_for_update().filter(
        materia_prima=materia_prima, cantidad_restante__gt=0
    ).order_by("fecha_compra", "creado_en")
    for lote in lotes:
        if restante <= 0:
            break
        tomado = min(lote.cantidad_restante, restante)
        lote.cantidad_restante -= tomado
        lote.save(update_fields=["cantidad_restante"])
        materia_prima.stock_actual -= tomado
        materia_prima.save(update_fields=["stock_actual"])
        movimientos.append(
            MovimientoInventarioMateriaPrima.objects.create(
                materia_prima=materia_prima,
                tipo=tipo,
                cantidad=-tomado,
                compra=lote,
                motivo=motivo,
                saldo_resultante=materia_prima.stock_actual,
                creado_por=creado_por,
            )
        )
        restante -= tomado

    if restante > 0:
        raise ValidationError(
            "Los lotes de compra registrados no cubren el stock disponible; "
            "revisar el inventario antes de continuar."
        )
    return movimientos


@transaction.atomic
def registrar_ajuste(*, materia_prima_id, cantidad_delta, motivo, creado_por):
    """Corrección manual de un Administrador (p. ej. tras un conteo físico). A
    diferencia de consumir_fifo, no se atribuye a un lote específico: es una
    corrección de conteo, no un consumo real contra una compra."""
    materia_prima = MateriaPrima.objects.select_for_update().get(pk=materia_prima_id)
    cantidad_delta = Decimal(cantidad_delta)
    if cantidad_delta == 0:
        raise ValidationError("El ajuste no puede ser de cantidad cero.")
    nuevo_stock = materia_prima.stock_actual + cantidad_delta
    if nuevo_stock < 0:
        raise ValidationError("El ajuste dejaría el inventario en negativo.")
    materia_prima.stock_actual = nuevo_stock
    materia_prima.save(update_fields=["stock_actual"])
    return MovimientoInventarioMateriaPrima.objects.create(
        materia_prima=materia_prima,
        tipo=MovimientoInventarioMateriaPrima.Tipo.AJUSTE,
        cantidad=cantidad_delta,
        motivo=motivo,
        saldo_resultante=materia_prima.stock_actual,
        creado_por=creado_por,
    )
