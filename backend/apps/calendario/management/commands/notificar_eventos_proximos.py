"""Comando pensado para ejecutarse periódicamente vía cron (ver sección 33 del
sistema: Namecheap/cPanel ofrece cron jobs). Notifica al administrador sobre
eventos de calendario (producciones programadas, entregas) que ocurren dentro
de las próximas 24 horas y para los que todavía no se avisó.

Uso: python manage.py notificar_eventos_proximos
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.calendario.models import EventoCalendario
from apps.notificaciones.models import Notificacion
from apps.notificaciones.services import notificar_admins


class Command(BaseCommand):
    help = "Notifica al administrador los eventos de calendario próximos a ocurrir (siguientes 24 horas)."

    def handle(self, *args, **options):
        ahora = timezone.now()
        limite = ahora + timezone.timedelta(hours=24)
        proximos = EventoCalendario.objects.filter(fecha_inicio__gte=ahora, fecha_inicio__lte=limite)

        ya_notificados = set(
            Notificacion.objects.filter(
                tipo=Notificacion.Tipo.PRODUCCION_PROGRAMADA, referencia_id__in=proximos.values_list("id", flat=True)
            ).values_list("referencia_id", flat=True)
        )

        creadas = 0
        for evento in proximos.exclude(id__in=ya_notificados):
            notificar_admins(
                tipo=Notificacion.Tipo.PRODUCCION_PROGRAMADA,
                titulo=f"Próximo: {evento.titulo}",
                mensaje=f"{evento.titulo} está programado para {evento.fecha_inicio:%d/%m/%Y %H:%M}.",
                referencia_id=evento.id,
            )
            creadas += 1

        self.stdout.write(self.style.SUCCESS(f"{creadas} evento(s) próximos notificados."))
