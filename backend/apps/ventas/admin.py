from django.contrib import admin

from .models import DetalleVenta, Venta


class DetalleVentaInline(admin.TabularInline):
    model = DetalleVenta
    extra = 0
    readonly_fields = ("producto", "paquete", "cantidad", "cantidad_en_unidades", "precio_unitario", "subtotal")
    can_delete = False


@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    list_display = ("id", "cliente", "estado", "total", "metodo_pago", "creado_en")
    list_filter = ("estado",)
    search_fields = ("cliente__username",)
    inlines = [DetalleVentaInline]
