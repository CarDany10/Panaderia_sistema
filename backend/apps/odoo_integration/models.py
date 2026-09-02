from django.db import models


class SincronizacionOdoo(models.Model):
    class Tipo(models.TextChoices):
        VENTA = "VENTA", "Venta"
        COMPRA = "COMPRA", "Compra"

    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    referencia_id = models.PositiveIntegerField()
    # Nulo mientras no se haya sincronizado con éxito (p. ej. Odoo no configurado
    # todavía, o el último intento falló — ver `error`).
    odoo_id = models.PositiveIntegerField(null=True, blank=True)
    sincronizado_en = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado_en"]
        unique_together = ("tipo", "referencia_id")

    def __str__(self):
        estado = "sincronizado" if self.odoo_id else "pendiente"
        return f"{self.tipo} #{self.referencia_id} ({estado})"
