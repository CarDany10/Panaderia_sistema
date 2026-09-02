from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.produccion.models import Paquete, Producto


class Pedido(models.Model):
    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        EN_PREPARACION = "EN_PREPARACION", "En preparación"
        EN_CAMINO = "EN_CAMINO", "En camino"
        ENTREGADO = "ENTREGADO", "Entregado"
        CANCELADO = "CANCELADO", "Cancelado"

    cliente = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="pedidos"
    )
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.PENDIENTE)
    # Snapshot al momento del pedido: no depende de que el cliente no cambie después
    # su dirección/teléfono predeterminados en su perfil.
    direccion_entrega = models.TextField()
    telefono_contacto = models.CharField(max_length=30)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado_en", "-id"]

    def __str__(self):
        return f"Pedido #{self.id:05d} ({self.estado})"

    @property
    def numero(self):
        return f"{self.id:05d}"


class DetallePedido(models.Model):
    pedido = models.ForeignKey(Pedido, on_delete=models.PROTECT, related_name="detalles")
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name="+")
    paquete = models.ForeignKey(
        Paquete, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    cantidad = models.DecimalField(max_digits=12, decimal_places=2)
    cantidad_en_unidades = models.DecimalField(max_digits=12, decimal_places=2)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.cantidad} x {self.producto.nombre}"


class Entrega(models.Model):
    pedido = models.OneToOneField(Pedido, on_delete=models.PROTECT, related_name="entrega")
    repartidor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="entregas"
    )
    fecha_asignacion = models.DateTimeField(auto_now_add=True)
    fecha_entrega = models.DateTimeField(null=True, blank=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="entregas_asignadas"
    )

    class Meta:
        ordering = ["-fecha_asignacion"]

    def __str__(self):
        return f"Entrega de pedido #{self.pedido_id:05d} a {self.repartidor.username}"


class Calificacion(models.Model):
    entrega = models.OneToOneField(Entrega, on_delete=models.PROTECT, related_name="calificacion")
    # Denormalizado (además de entrega.pedido.cliente y entrega.repartidor) para
    # poder calcular el promedio de un repartidor con una consulta directa y simple.
    cliente = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="calificaciones_hechas"
    )
    repartidor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="calificaciones_recibidas"
    )
    estrellas = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comentario = models.TextField(blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado_en"]

    def __str__(self):
        return f"{self.estrellas} estrellas a {self.repartidor.username}"
