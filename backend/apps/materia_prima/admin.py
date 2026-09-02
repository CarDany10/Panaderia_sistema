from django.contrib import admin

from .models import Compra, MateriaPrima, MovimientoInventarioMateriaPrima


@admin.register(MateriaPrima)
class MateriaPrimaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "unidad_medida", "stock_actual", "stock_minimo", "activa")
    search_fields = ("nombre",)
    list_filter = ("unidad_medida", "activa")


@admin.register(Compra)
class CompraAdmin(admin.ModelAdmin):
    list_display = (
        "lote",
        "materia_prima",
        "cantidad",
        "unidad_medida",
        "costo_total",
        "costo_unitario",
        "fecha_compra",
        "cantidad_restante",
    )
    search_fields = ("lote", "materia_prima__nombre")
    list_filter = ("unidad_medida",)


@admin.register(MovimientoInventarioMateriaPrima)
class MovimientoInventarioMateriaPrimaAdmin(admin.ModelAdmin):
    list_display = ("materia_prima", "tipo", "cantidad", "saldo_resultante", "creado_por", "creado_en")
    list_filter = ("tipo",)
    search_fields = ("materia_prima__nombre", "motivo")
