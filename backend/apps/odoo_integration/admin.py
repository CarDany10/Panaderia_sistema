from django.contrib import admin

from .models import SincronizacionOdoo


@admin.register(SincronizacionOdoo)
class SincronizacionOdooAdmin(admin.ModelAdmin):
    list_display = ("tipo", "referencia_id", "odoo_id", "sincronizado_en", "error")
    list_filter = ("tipo",)
