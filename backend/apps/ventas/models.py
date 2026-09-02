from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.produccion.models import Paquete, Producto


class Venta(models.Model):
    class Estado(models.TextChoices):
        COMPLETADA = "COMPLETADA", "Completada"
        ANULADA = "ANULADA", "Anulada"

    # Nula en una venta de mostrador sin cuenta de cliente asociada.
    cliente = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="ventas"
    )
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.COMPLETADA)
    metodo_pago = models.CharField(max_length=50, blank=True)
    direccion_entrega = models.TextField(blank=True)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="ventas_registradas"
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado_en", "-id"]

    def __str__(self):
        return f"Venta #{self.id:05d}"

    @property
    def numero(self):
        return f"{self.id:05d}"


class DetalleVenta(models.Model):
    venta = models.ForeignKey(Venta, on_delete=models.PROTECT, related_name="detalles")
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name="+")
    paquete = models.ForeignKey(Paquete, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    # Cantidad tal como la declaró quien vendió: unidades, o paquetes si se indicó paquete.
    cantidad = models.DecimalField(max_digits=12, decimal_places=2)
    cantidad_en_unidades = models.DecimalField(max_digits=12, decimal_places=2)
    # Precio vigente al momento de la venta (no cambia si luego se edita el catálogo).
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.cantidad} x {self.producto.nombre}"
