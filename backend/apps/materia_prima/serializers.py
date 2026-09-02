from decimal import Decimal

from rest_framework import serializers

from .models import Compra, MateriaPrima, MovimientoInventarioMateriaPrima
from . import services


class MateriaPrimaAdminSerializer(serializers.ModelSerializer):
    stock_bajo = serializers.BooleanField(read_only=True)
    valor_inventario = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )

    class Meta:
        model = MateriaPrima
        fields = [
            "id",
            "nombre",
            "descripcion",
            "unidad_medida",
            "stock_actual",
            "stock_minimo",
            "activa",
            "stock_bajo",
            "valor_inventario",
        ]
        # stock_actual solo cambia a través de movimientos (Compra/Merma/Ajuste),
        # nunca por edición directa del catálogo.
        read_only_fields = ["id", "stock_actual"]


class MateriaPrimaTrabajadorSerializer(serializers.ModelSerializer):
    """Sin stock_actual, stock_minimo ni valor_inventario: un Trabajador no debe ver
    la cantidad total disponible ni información financiera (regla de negocio)."""

    class Meta:
        model = MateriaPrima
        fields = ["id", "nombre", "descripcion", "unidad_medida", "activa"]
        read_only_fields = fields


class CompraSerializer(serializers.ModelSerializer):
    costo_unitario = serializers.DecimalField(
        max_digits=12, decimal_places=4, required=False, allow_null=True
    )

    class Meta:
        model = Compra
        fields = [
            "id",
            "materia_prima",
            "lote",
            "cantidad",
            "unidad_medida",
            "cantidad_nativa",
            "cantidad_restante",
            "costo_total",
            "costo_unitario",
            "fecha_compra",
            "creado_por",
            "creado_en",
        ]
        read_only_fields = [
            "id",
            "cantidad_nativa",
            "cantidad_restante",
            "creado_por",
            "creado_en",
        ]

    def create(self, validated_data):
        creado_por = self.context["request"].user
        return services.registrar_compra(
            materia_prima_id=validated_data["materia_prima"].id,
            lote=validated_data["lote"],
            cantidad=validated_data["cantidad"],
            unidad_medida=validated_data["unidad_medida"],
            costo_total=validated_data["costo_total"],
            costo_unitario=validated_data.get("costo_unitario"),
            fecha_compra=validated_data["fecha_compra"],
            creado_por=creado_por,
        )


class MovimientoInventarioMateriaPrimaSerializer(serializers.ModelSerializer):
    class Meta:
        model = MovimientoInventarioMateriaPrima
        fields = [
            "id",
            "materia_prima",
            "tipo",
            "cantidad",
            "compra",
            "motivo",
            "saldo_resultante",
            "creado_por",
            "creado_en",
        ]
        read_only_fields = fields


class AjusteInventarioSerializer(serializers.Serializer):
    cantidad_delta = serializers.DecimalField(max_digits=12, decimal_places=3)
    motivo = serializers.CharField(max_length=255)

    def validate_cantidad_delta(self, value):
        if value == 0:
            raise serializers.ValidationError("El ajuste no puede ser de cantidad cero.")
        return value


class MermaInventarioSerializer(serializers.Serializer):
    cantidad = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal("0.001"))
    motivo = serializers.CharField(max_length=255)
