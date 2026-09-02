from decimal import Decimal

from django.conf import settings
from django.db import models


class UnidadMedida(models.TextChoices):
    LB = "LB", "Libras"
    OZ = "OZ", "Onzas"


class MateriaPrima(models.Model):
    nombre = models.CharField(max_length=150, unique=True)
    descripcion = models.TextField(blank=True)
    unidad_medida = models.CharField(max_length=2, choices=UnidadMedida.choices)
    # Solo se modifica a través de movimientos (Compra/consumo/merma/ajuste), nunca
    # directamente, para que ninguna cantidad pueda "desaparecer" sin quedar registrada.
    stock_actual = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0"))
    stock_minimo = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0"))
    activa = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return f"{self.nombre} ({self.get_unidad_medida_display()})"

    @property
    def stock_bajo(self):
        return self.stock_actual < self.stock_minimo

    @property
    def valor_inventario(self):
        """Suma del valor de cada lote de compra aún no consumido, a su costo real
        (nunca un promedio inventado) — ver apps.materia_prima.services."""
        total = Decimal("0")
        for compra in self.compras.filter(cantidad_restante__gt=0):
            total += compra.cantidad_restante * compra.costo_unitario_nativo
        return total


class Compra(models.Model):
    materia_prima = models.ForeignKey(
        MateriaPrima, on_delete=models.PROTECT, related_name="compras"
    )
    lote = models.CharField(max_length=100)
    cantidad = models.DecimalField(max_digits=12, decimal_places=3)
    unidad_medida = models.CharField(max_length=2, choices=UnidadMedida.choices)
    # Cantidad convertida a la unidad nativa de la materia prima al momento de la
    # compra (inmutable) y cuánto de ese lote queda sin consumir (mutable, FIFO).
    cantidad_nativa = models.DecimalField(max_digits=12, decimal_places=3)
    cantidad_restante = models.DecimalField(max_digits=12, decimal_places=3)
    costo_total = models.DecimalField(max_digits=12, decimal_places=2)
    costo_unitario = models.DecimalField(max_digits=12, decimal_places=4)
    fecha_compra = models.DateField()
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="compras_registradas",
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["fecha_compra", "creado_en"]

    def __str__(self):
        return f"Compra {self.lote} de {self.materia_prima.nombre}"

    @property
    def costo_unitario_nativo(self):
        from .services import convertir_costo_unitario

        return convertir_costo_unitario(
            self.costo_unitario, self.unidad_medida, self.materia_prima.unidad_medida
        )


class MovimientoInventarioMateriaPrima(models.Model):
    class Tipo(models.TextChoices):
        COMPRA = "COMPRA", "Compra"
        PRODUCCION = "PRODUCCION", "Consumo en producción"
        MERMA = "MERMA", "Merma"
        AJUSTE = "AJUSTE", "Ajuste autorizado"

    materia_prima = models.ForeignKey(
        MateriaPrima, on_delete=models.PROTECT, related_name="movimientos"
    )
    tipo = models.CharField(max_length=12, choices=Tipo.choices)
    # En unidad nativa de la materia prima. Positivo = entrada, negativo = salida.
    cantidad = models.DecimalField(max_digits=12, decimal_places=3)
    compra = models.ForeignKey(
        Compra,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="movimientos",
        help_text="Lote específico afectado (compra, consumo o merma). Nulo en ajustes.",
    )
    motivo = models.CharField(max_length=255)
    saldo_resultante = models.DecimalField(max_digits=12, decimal_places=3)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="movimientos_materia_prima",
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creado_en", "-id"]

    def __str__(self):
        return f"{self.tipo} {self.cantidad} {self.materia_prima.unidad_medida} - {self.materia_prima.nombre}"
