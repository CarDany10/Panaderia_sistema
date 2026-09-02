from django.contrib import admin

from .models import (
    ConsumoMateriaPrima,
    MovimientoInventarioProductoTerminado,
    Paquete,
    Producto,
    Produccion,
)


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "precio_unitario", "stock_actual", "activo")
    search_fields = ("nombre",)
    list_filter = ("activo",)


@admin.register(Paquete)
class PaqueteAdmin(admin.ModelAdmin):
    list_display = ("nombre", "producto", "unidades_por_paquete", "precio_paquete", "activo")
    search_fields = ("nombre", "producto__nombre")


class ConsumoMateriaPrimaInline(admin.TabularInline):
    model = ConsumoMateriaPrima
    extra = 0
    readonly_fields = ("materia_prima", "cantidad", "unidad_medida", "costo_correspondiente")
    can_delete = False


@admin.register(Produccion)
class ProduccionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "producto",
        "fecha",
        "cantidad_producida",
        "cantidad_merma",
        "costo_total",
        "costo_unitario",
    )
    list_filter = ("producto",)
    inlines = [ConsumoMateriaPrimaInline]


@admin.register(MovimientoInventarioProductoTerminado)
class MovimientoInventarioProductoTerminadoAdmin(admin.ModelAdmin):
    list_display = ("producto", "tipo", "cantidad", "saldo_resultante", "creado_por", "creado_en")
    list_filter = ("tipo",)
    search_fields = ("producto__nombre", "motivo")
