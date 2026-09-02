from django.conf import settings
from django.db import models


class EventoCalendario(models.Model):
    class Tipo(models.TextChoices):
        PRODUCCION = "PRODUCCION", "Producción"
        PEDIDO = "PEDIDO", "Pedido"

    tipo = models.CharField(max_length=12, choices=Tipo.choices)
    # Id de la Produccion o el Pedido relacionado (según `tipo`). Sin FK/GenericForeignKey
    # a propósito: es solo una referencia de lectura para el calendario, no una
    # relación que deba imponer integridad referencial sobre esos módulos.
    referencia_id = models.PositiveIntegerField()
    # Vacío mientras no se haya sincronizado con Google (p. ej. si aún no se
    # configuran las credenciales) — el evento local no se pierde por eso.
    google_event_id = models.CharField(max_length=255, blank=True)
    titulo = models.CharField(max_length=255)
    descripcion = models.TextField(blank=True)
    fecha_inicio = models.DateTimeField()
    fecha_fin = models.DateTimeField()
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="eventos_calendario"
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["fecha_inicio"]
        unique_together = ("tipo", "referencia_id")

    def __str__(self):
        return f"{self.titulo} ({self.fecha_inicio:%Y-%m-%d %H:%M})"
