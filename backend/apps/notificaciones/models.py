from django.conf import settings
from django.db import models


class Notificacion(models.Model):
    class Tipo(models.TextChoices):
        STOCK_BAJO = "STOCK_BAJO", "Stock bajo de materia prima"
        NUEVO_PEDIDO = "NUEVO_PEDIDO", "Nuevo pedido"
        PEDIDO_ASIGNADO = "PEDIDO_ASIGNADO", "Pedido asignado"
        ESTADO_PEDIDO = "ESTADO_PEDIDO", "Cambio de estado de pedido"
        PRODUCCION_PROGRAMADA = "PRODUCCION_PROGRAMADA", "Producción programada próxima"

    destinatario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notificaciones"
    )
    tipo = models.CharField(max_length=30, choices=Tipo.choices)
    titulo = models.CharField(max_length=150)
    mensaje = models.TextField()
    leida = models.BooleanField(default=False)
    # Id del registro relacionado (materia prima, pedido, evento de calendario...)
    # según el tipo — sin FK fija a propósito, ya que el tipo de referencia varía.
    referencia_id = models.PositiveIntegerField(null=True, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado_en"]

    def __str__(self):
        return f"{self.tipo} -> {self.destinatario.username}: {self.titulo}"
