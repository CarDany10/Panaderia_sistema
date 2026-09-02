"""Agregaciones de solo lectura para el dashboard de cada rol (secciones 26-29).

No introduce datos nuevos: combina lo que ya existe en cada módulo (igual que
Historial), pre-calculado para que la pantalla de inicio de cada rol se arme
con una sola llamada en vez de varias.
"""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from apps.calendario.models import EventoCalendario
from apps.materia_prima.models import MateriaPrima
from apps.pedidos.models import DetallePedido, Pedido
from apps.pedidos.serializers import PedidoSerializer, PedidoTrabajadorSerializer
from apps.produccion.models import Producto, Produccion
from apps.produccion.serializers import ProduccionAdminSerializer
from apps.ventas.models import DetalleVenta, Venta


def _productos_mas_vendidos(top=5):
    combinados = {}

    for fila in DetalleVenta.objects.exclude(venta__estado=Venta.Estado.ANULADA).values(
        "producto_id", "producto__nombre"
    ).annotate(cantidad=Sum("cantidad_en_unidades")):
        acumulado = combinados.setdefault(
            fila["producto_id"], {"producto": fila["producto__nombre"], "cantidad": Decimal("0")}
        )
        acumulado["cantidad"] += fila["cantidad"]

    for fila in DetallePedido.objects.exclude(pedido__estado=Pedido.Estado.CANCELADO).values(
        "producto_id", "producto__nombre"
    ).annotate(cantidad=Sum("cantidad_en_unidades")):
        acumulado = combinados.setdefault(
            fila["producto_id"], {"producto": fila["producto__nombre"], "cantidad": Decimal("0")}
        )
        acumulado["cantidad"] += fila["cantidad"]

    ordenados = sorted(combinados.values(), key=lambda x: x["cantidad"], reverse=True)[:top]
    return [{"producto": r["producto"], "cantidad_vendida": str(r["cantidad"])} for r in ordenados]


def _ingresos_desde(fecha_desde):
    total_ventas = Venta.objects.filter(
        creado_en__date__gte=fecha_desde, estado=Venta.Estado.COMPLETADA
    ).aggregate(t=Sum("total"))["t"] or Decimal("0")
    total_pedidos = Pedido.objects.filter(creado_en__date__gte=fecha_desde).exclude(
        estado=Pedido.Estado.CANCELADO
    ).aggregate(t=Sum("total"))["t"] or Decimal("0")
    return total_ventas + total_pedidos


def dashboard_admin():
    hoy = timezone.localdate()
    inicio_semana = hoy - timedelta(days=hoy.weekday())
    inicio_mes = hoy.replace(day=1)

    valor_materia_prima = sum((m.valor_inventario for m in MateriaPrima.objects.all()), Decimal("0"))
    valor_producto_terminado = sum((p.valor_inventario for p in Producto.objects.all()), Decimal("0"))

    materias_stock_bajo = [
        {
            "id": m.id,
            "nombre": m.nombre,
            "existencia_actual": str(m.stock_actual),
            "stock_minimo": str(m.stock_minimo),
        }
        for m in MateriaPrima.objects.all()
        if m.stock_bajo
    ]
    productos_stock_bajo = [
        {
            "id": p.id,
            "nombre": p.nombre,
            "existencia_actual": str(p.stock_actual),
            "stock_minimo": str(p.stock_minimo),
        }
        for p in Producto.objects.all()
        if p.stock_bajo
    ]

    return {
        "valor_inventario_materia_prima": str(valor_materia_prima),
        "valor_inventario_producto_terminado": str(valor_producto_terminado),
        "ventas_dia": str(_ingresos_desde(hoy)),
        "ventas_semana": str(_ingresos_desde(inicio_semana)),
        "ventas_mes": str(_ingresos_desde(inicio_mes)),
        "producciones_recientes": ProduccionAdminSerializer(
            Produccion.objects.select_related("producto").order_by("-fecha", "-id")[:5], many=True
        ).data,
        "pedidos_pendientes": Pedido.objects.filter(estado=Pedido.Estado.PENDIENTE).count(),
        "materias_primas_stock_bajo": materias_stock_bajo,
        "productos_stock_bajo": productos_stock_bajo,
        "productos_mas_vendidos": _productos_mas_vendidos(),
    }


def dashboard_trabajador():
    ahora = timezone.now()
    limite = ahora + timedelta(days=7)
    producciones_programadas = list(
        EventoCalendario.objects.filter(
            tipo=EventoCalendario.Tipo.PRODUCCION, fecha_inicio__gte=ahora, fecha_inicio__lte=limite
        )
        .order_by("fecha_inicio")
        .values("id", "titulo", "fecha_inicio", "fecha_fin")
    )

    pedidos_activos = Pedido.objects.filter(
        estado__in=[Pedido.Estado.PENDIENTE, Pedido.Estado.EN_PREPARACION]
    )
    cantidades_requeridas = (
        DetallePedido.objects.filter(pedido__in=pedidos_activos)
        .values("producto__nombre")
        .annotate(cantidad=Sum("cantidad_en_unidades"))
        .order_by("-cantidad")
    )

    return {
        "producciones_programadas": producciones_programadas,
        "productos_a_producir": [
            {"producto": r["producto__nombre"], "cantidad_requerida": str(r["cantidad"])}
            for r in cantidades_requeridas
        ],
        "pedidos_relacionados_con_produccion": PedidoTrabajadorSerializer(
            pedidos_activos.order_by("-creado_en")[:10], many=True
        ).data,
    }


def dashboard_repartidor(repartidor):
    pedidos_asignados = Pedido.objects.filter(entrega__repartidor=repartidor)
    en_preparacion_o_camino = pedidos_asignados.filter(
        estado__in=[Pedido.Estado.EN_PREPARACION, Pedido.Estado.EN_CAMINO]
    ).order_by("entrega__fecha_asignacion")

    perfil = getattr(repartidor, "perfil_repartidor", None)

    return {
        "pedidos_pendientes": pedidos_asignados.filter(estado=Pedido.Estado.EN_PREPARACION).count(),
        "pedidos_en_camino": PedidoSerializer(
            pedidos_asignados.filter(estado=Pedido.Estado.EN_CAMINO), many=True
        ).data,
        "proximas_entregas": PedidoSerializer(en_preparacion_o_camino, many=True).data,
        "entregas_recientes": PedidoSerializer(
            pedidos_asignados.filter(estado=Pedido.Estado.ENTREGADO).order_by("-creado_en")[:10], many=True
        ).data,
        "calificacion_promedio": perfil.calificacion_promedio if perfil else None,
    }


def dashboard_cliente(cliente):
    pedidos_actuales = Pedido.objects.filter(cliente=cliente).exclude(
        estado__in=[Pedido.Estado.ENTREGADO, Pedido.Estado.CANCELADO]
    )
    historial = Pedido.objects.filter(
        cliente=cliente, estado__in=[Pedido.Estado.ENTREGADO, Pedido.Estado.CANCELADO]
    ).order_by("-creado_en")[:10]
    pendientes_calificar = [
        p
        for p in Pedido.objects.filter(cliente=cliente, estado=Pedido.Estado.ENTREGADO).select_related(
            "entrega", "entrega__calificacion"
        )
        if hasattr(p, "entrega") and not hasattr(p.entrega, "calificacion")
    ]

    return {
        "pedidos_actuales": PedidoSerializer(pedidos_actuales.order_by("-creado_en"), many=True).data,
        "historial": PedidoSerializer(historial, many=True).data,
        "pedidos_pendientes_de_calificar": PedidoSerializer(pendientes_calificar, many=True).data,
    }
