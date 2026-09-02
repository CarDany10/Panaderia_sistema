from django.contrib import admin

from .models import Calificacion, DetallePedido, Entrega, Pedido


class DetallePedidoInline(admin.TabularInline):
    model = DetallePedido
    extra = 0
    readonly_fields = ("producto", "paquete", "cantidad", "cantidad_en_unidades", "precio_unitario", "subtotal")
    can_delete = False


@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    list_display = ("id", "cliente", "estado", "total", "creado_en")
    list_filter = ("estado",)
    search_fields = ("cliente__username",)
    inlines = [DetallePedidoInline]


@admin.register(Entrega)
class EntregaAdmin(admin.ModelAdmin):
    list_display = ("pedido", "repartidor", "fecha_asignacion", "fecha_entrega")
    search_fields = ("pedido__id", "repartidor__username")


@admin.register(Calificacion)
class CalificacionAdmin(admin.ModelAdmin):
    list_display = ("repartidor", "cliente", "estrellas", "creado_en")
    list_filter = ("estrellas",)
