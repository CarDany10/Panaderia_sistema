from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.materia_prima.models import MateriaPrima, MovimientoInventarioMateriaPrima


class Producto(models.Model):
    nombre = models.CharField(max_length=150, unique=True)
    descripcion = models.TextField(blank=True)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    # Solo cambia a través de movimientos (producción/venta/merma/ajuste), igual que
    # MateriaPrima.stock_actual: nunca se edita directamente.
    stock_actual = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class MovimientoInventarioProductoTerminado(models.Model):
    class Tipo(models.TextChoices):
        PRODUCCION = "PRODUCCION", "Entrada por producción"
        VENTA = "VENTA", "Salida por venta"
        MERMA = "MERMA", "Merma"
        AJUSTE = "AJUSTE", "Ajuste autorizado"

    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name="movimientos")
    tipo = models.CharField(max_length=12, choices=Tipo.choices)
    # Positivo = entrada, negativo = salida.
    cantidad = models.DecimalField(max_digits=12, decimal_places=2)
    motivo = models.CharField(max_length=255)
    saldo_resultante = models.DecimalField(max_digits=12, decimal_places=2)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="movimientos_producto_terminado",
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado_en", "-id"]

    def __str__(self):
        return f"{self.tipo} {self.cantidad} - {self.producto.nombre}"


class Produccion(models.Model):
    # Sin campo de "responsable de producción": no forma parte del registro
    # (regla de negocio explícita). creado_por se conserva solo como auditoría
    # técnica interna y nunca se expone en los serializers de producción.
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name="producciones")
    fecha = models.DateField()
    cantidad_planificada = models.DecimalField(max_digits=12, decimal_places=2)
    cantidad_producida = models.DecimalField(max_digits=12, decimal_places=2)
    cantidad_merma = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    # Derivados exclusivamente de ConsumoMateriaPrima: costo_total = suma de sus
    # costo_correspondiente; costo_unitario = costo_total / cantidad_producida.
    costo_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    costo_unitario = models.DecimalField(max_digits=12, decimal_places=4, default=Decimal("0"))
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="producciones_registradas"
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return f"Producción #{self.id:05d} - {self.producto.nombre}"

    @property
    def numero(self):
        return f"{self.id:05d}"

    @property
    def cantidad_disponible(self):
        return self.cantidad_producida - self.cantidad_merma


class ConsumoMateriaPrima(models.Model):
    produccion = models.ForeignKey(Produccion, on_delete=models.PROTECT, related_name="consumos")
    materia_prima = models.ForeignKey(MateriaPrima, on_delete=models.PROTECT, related_name="+")
    # Tal como lo declaró quien registró la producción (puede diferir de la unidad
    # nativa de la materia prima; el consumo real se convierte internamente).
    cantidad = models.DecimalField(max_digits=12, decimal_places=3)
    unidad_medida = models.CharField(max_length=2, choices=[("LB", "Libras"), ("OZ", "Onzas")])
    # Suma exacta de lo que costaron los lotes realmente consumidos (FIFO), nunca
    # un costo estimado o promedio.
    costo_correspondiente = models.DecimalField(max_digits=12, decimal_places=2)
    # Movimientos de inventario de materia prima que efectivamente generó este
    # consumo (uno por cada lote FIFO afectado) — trazabilidad exacta del costo.
    movimientos = models.ManyToManyField(
        MovimientoInventarioMateriaPrima, related_name="consumos_produccion", blank=True
    )

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.cantidad} {self.unidad_medida} de {self.materia_prima.nombre}"
