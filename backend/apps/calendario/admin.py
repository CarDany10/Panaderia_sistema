from django.contrib import admin

from .models import EventoCalendario


@admin.register(EventoCalendario)
class EventoCalendarioAdmin(admin.ModelAdmin):
    list_display = ("titulo", "tipo", "referencia_id", "fecha_inicio", "fecha_fin", "google_event_id")
    list_filter = ("tipo",)
    search_fields = ("titulo",)
