"""Bitácora unificada del sistema (sección 25): un único apartado de consulta que
combina los movimientos reales de cada módulo, en vez de mantener una tabla de
auditoría paralela que podría desincronizarse de los datos reales si algún flujo
olvidara escribir en ella. Los movimientos/registros originales (Compra,
MovimientoInventarioMateriaPrima, Produccion, MovimientoInventarioProductoTerminado,
Venta, Pedido) siguen siendo la única fuente de verdad; esto solo los junta,
filtra y ordena para presentarlos en un solo lugar.
"""

from datetime import datetime

from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.materia_prima.models import MovimientoInventarioMateriaPrima
from apps.pedidos.models import Pedido
from apps.produccion.models import MovimientoInventarioProductoTerminado, Produccion
from apps.ventas.models import Venta

TIPOS_VALIDOS = {"COMPRA", "PRODUCCION", "VENTA", "PEDIDO", "MERMA", "AJUSTE"}
LIMITE_POR_FUENTE = 1000


def _entrada(*, categoria, tipo, fecha, descripcion, referencia_id, detalle):
    return {
        "categoria": categoria,
        "tipo": tipo,
        "fecha": fecha,
        "descripcion": descripcion,
        "referencia_id": referencia_id,
        "detalle": detalle,
    }


def _rango_fecha(qs, campo, fecha_desde, fecha_hasta, es_date=False):
    if fecha_desde:
        qs = qs.filter(**{f"{campo}__gte" if es_date else f"{campo}__date__gte": fecha_desde})
    if fecha_hasta:
        qs = qs.filter(**{f"{campo}__lte" if es_date else f"{campo}__date__lte": fecha_hasta})
    return qs


def listar_historial(
    *, fecha_desde=None, fecha_hasta=None, tipo=None, materia_prima_id=None, producto_id=None, limit=50, offset=0
):
    if tipo and tipo not in TIPOS_VALIDOS:
        raise ValidationError(f"Tipo de operación desconocido: {tipo}. Válidos: {sorted(TIPOS_VALIDOS)}.")

    entradas = []

    # Movimientos de materia prima: compra, consumo en producción, merma, ajuste.
    if tipo in (None, "COMPRA", "PRODUCCION", "MERMA", "AJUSTE"):
        qs = MovimientoInventarioMateriaPrima.objects.select_related("materia_prima", "creado_por")
        if tipo:
            qs = qs.filter(tipo=tipo)
        if materia_prima_id:
            qs = qs.filter(materia_prima_id=materia_prima_id)
        qs = _rango_fecha(qs, "creado_en", fecha_desde, fecha_hasta)
        for m in qs.order_by("-creado_en")[:LIMITE_POR_FUENTE]:
            entradas.append(
                _entrada(
                    categoria="MOVIMIENTO_MATERIA_PRIMA",
                    tipo=m.tipo,
                    fecha=m.creado_en,
                    descripcion=f"{m.materia_prima.nombre}: {m.cantidad} {m.materia_prima.unidad_medida} ({m.motivo})",
                    referencia_id=m.id,
                    detalle={
                        "materia_prima": m.materia_prima.nombre,
                        "cantidad": str(m.cantidad),
                        "saldo_resultante": str(m.saldo_resultante),
                        "motivo": m.motivo,
                        "creado_por": m.creado_por.username,
                    },
                )
            )

    # Movimientos de producto terminado: entrada por producción, venta, merma, ajuste.
    if tipo in (None, "PRODUCCION", "VENTA", "MERMA", "AJUSTE"):
        qs = MovimientoInventarioProductoTerminado.objects.select_related("producto", "creado_por")
        if tipo:
            qs = qs.filter(tipo=tipo)
        if producto_id:
            qs = qs.filter(producto_id=producto_id)
        qs = _rango_fecha(qs, "creado_en", fecha_desde, fecha_hasta)
        for m in qs.order_by("-creado_en")[:LIMITE_POR_FUENTE]:
            entradas.append(
                _entrada(
                    categoria="MOVIMIENTO_PRODUCTO_TERMINADO",
                    tipo=m.tipo,
                    fecha=m.creado_en,
                    descripcion=f"{m.producto.nombre}: {m.cantidad} unidades ({m.motivo})",
                    referencia_id=m.id,
                    detalle={
                        "producto": m.producto.nombre,
                        "cantidad": str(m.cantidad),
                        "saldo_resultante": str(m.saldo_resultante),
                        "motivo": m.motivo,
                        "creado_por": m.creado_por.username,
                    },
                )
            )

    # Registro de producción (con costo, distinto del movimiento de entrada de arriba).
    if tipo in (None, "PRODUCCION"):
        qs = Produccion.objects.select_related("producto")
        if producto_id:
            qs = qs.filter(producto_id=producto_id)
        if materia_prima_id:
            qs = qs.filter(consumos__materia_prima_id=materia_prima_id).distinct()
        qs = _rango_fecha(qs, "fecha", fecha_desde, fecha_hasta, es_date=True)
        for p in qs.order_by("-fecha")[:LIMITE_POR_FUENTE]:
            fecha_dt = timezone.make_aware(datetime.combine(p.fecha, datetime.min.time()))
            entradas.append(
                _entrada(
                    categoria="PRODUCCION",
                    tipo="PRODUCCION",
                    fecha=fecha_dt,
                    descripcion=(
                        f"Producción #{p.numero} de {p.producto.nombre}: "
                        f"{p.cantidad_producida} producidas, {p.cantidad_merma} de merma"
                    ),
                    referencia_id=p.id,
                    detalle={
                        "producto": p.producto.nombre,
                        "cantidad_producida": str(p.cantidad_producida),
                        "cantidad_merma": str(p.cantidad_merma),
                        "costo_total": str(p.costo_total),
                        "costo_unitario": str(p.costo_unitario),
                    },
                )
            )

    # Ventas de mostrador.
    if tipo in (None, "VENTA"):
        qs = Venta.objects.select_related("cliente")
        if producto_id:
            qs = qs.filter(detalles__producto_id=producto_id).distinct()
        qs = _rango_fecha(qs, "creado_en", fecha_desde, fecha_hasta)
        for v in qs.order_by("-creado_en")[:LIMITE_POR_FUENTE]:
            entradas.append(
                _entrada(
                    categoria="VENTA",
                    tipo=v.estado,
                    fecha=v.creado_en,
                    descripcion=f"Venta #{v.numero}: Q{v.total} ({v.estado})",
                    referencia_id=v.id,
                    detalle={
                        "cliente": v.cliente.username if v.cliente else None,
                        "total": str(v.total),
                        "estado": v.estado,
                    },
                )
            )

    # Pedidos de clientes.
    if tipo in (None, "PEDIDO"):
        qs = Pedido.objects.select_related("cliente")
        if producto_id:
            qs = qs.filter(detalles__producto_id=producto_id).distinct()
        qs = _rango_fecha(qs, "creado_en", fecha_desde, fecha_hasta)
        for p in qs.order_by("-creado_en")[:LIMITE_POR_FUENTE]:
            entradas.append(
                _entrada(
                    categoria="PEDIDO",
                    tipo=p.estado,
                    fecha=p.creado_en,
                    descripcion=f"Pedido #{p.numero} de {p.cliente.username}: Q{p.total} ({p.estado})",
                    referencia_id=p.id,
                    detalle={"cliente": p.cliente.username, "total": str(p.total), "estado": p.estado},
                )
            )

    entradas.sort(key=lambda e: e["fecha"], reverse=True)
    total = len(entradas)
    return {"total": total, "resultados": entradas[offset : offset + limit]}
