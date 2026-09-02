from decimal import Decimal

from rest_framework import serializers

from . import services
from .models import ConsumoMateriaPrima, MovimientoInventarioProductoTerminado, Producto, Produccion


class ProductoAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = Producto
        fields = ["id", "nombre", "descripcion", "precio_unitario", "stock_actual", "activo"]
        read_only_fields = ["id", "stock_actual"]


class ProductoTrabajadorSerializer(serializers.ModelSerializer):
    """Sin precio_unitario ni stock_actual: igual que con materia prima, un
    Trabajador no debe ver cifras financieras ni cantidades de inventario."""

    class Meta:
        model = Producto
        fields = ["id", "nombre", "descripcion", "activo"]
        read_only_fields = fields


class ConsumoMateriaPrimaEntradaSerializer(serializers.Serializer):
    """Un ítem del payload de entrada al registrar una producción (no es un
    ModelSerializer: el consumo real se calcula en services.registrar_produccion)."""

    materia_prima_id = serializers.IntegerField()
    cantidad = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal("0.001"))
    unidad_medida = serializers.ChoiceField(choices=["LB", "OZ"])


class ConsumoMateriaPrimaAdminSerializer(serializers.ModelSerializer):
    materia_prima_nombre = serializers.CharField(source="materia_prima.nombre", read_only=True)

    class Meta:
        model = ConsumoMateriaPrima
        fields = [
            "id",
            "materia_prima",
            "materia_prima_nombre",
            "cantidad",
            "unidad_medida",
            "costo_correspondiente",
        ]
        read_only_fields = fields


class ConsumoMateriaPrimaTrabajadorSerializer(serializers.ModelSerializer):
    """Sin costo_correspondiente: es información financiera."""

    materia_prima_nombre = serializers.CharField(source="materia_prima.nombre", read_only=True)

    class Meta:
        model = ConsumoMateriaPrima
        fields = ["id", "materia_prima", "materia_prima_nombre", "cantidad", "unidad_medida"]
        read_only_fields = fields


class ProduccionCrearSerializer(serializers.Serializer):
    """Serializer de entrada para crear una producción (delega en services)."""

    producto = serializers.PrimaryKeyRelatedField(queryset=Producto.objects.all())
    fecha = serializers.DateField()
    cantidad_planificada = serializers.DecimalField(max_digits=12, decimal_places=2)
    cantidad_producida = serializers.DecimalField(max_digits=12, decimal_places=2)
    cantidad_merma = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, default=Decimal("0")
    )
    consumos = ConsumoMateriaPrimaEntradaSerializer(many=True)

    def create(self, validated_data):
        creado_por = self.context["request"].user
        return services.registrar_produccion(
            producto_id=validated_data["producto"].id,
            fecha=validated_data["fecha"],
            cantidad_planificada=validated_data["cantidad_planificada"],
            cantidad_producida=validated_data["cantidad_producida"],
            cantidad_merma=validated_data.get("cantidad_merma", Decimal("0")),
            consumos=validated_data["consumos"],
            creado_por=creado_por,
        )


class ProduccionAdminSerializer(serializers.ModelSerializer):
    numero = serializers.CharField(read_only=True)
    cantidad_disponible = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    consumos = ConsumoMateriaPrimaAdminSerializer(many=True, read_only=True)
    producto_nombre = serializers.CharField(source="producto.nombre", read_only=True)

    class Meta:
        model = Produccion
        fields = [
            "id",
            "numero",
            "producto",
            "producto_nombre",
            "fecha",
            "cantidad_planificada",
            "cantidad_producida",
            "cantidad_merma",
            "cantidad_disponible",
            "costo_total",
            "costo_unitario",
            "consumos",
            "creado_en",
        ]
        read_only_fields = fields


class ProduccionTrabajadorSerializer(serializers.ModelSerializer):
    """Sin costo_total ni costo_unitario: información financiera exclusiva de
    Administrador. Tampoco expone quién la registró (regla de negocio: el
    registro de producción no incluye responsable)."""

    numero = serializers.CharField(read_only=True)
    cantidad_disponible = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    consumos = ConsumoMateriaPrimaTrabajadorSerializer(many=True, read_only=True)
    producto_nombre = serializers.CharField(source="producto.nombre", read_only=True)

    class Meta:
        model = Produccion
        fields = [
            "id",
            "numero",
            "producto",
            "producto_nombre",
            "fecha",
            "cantidad_planificada",
            "cantidad_producida",
            "cantidad_merma",
            "cantidad_disponible",
            "consumos",
            "creado_en",
        ]
        read_only_fields = fields


class MovimientoInventarioProductoTerminadoSerializer(serializers.ModelSerializer):
    class Meta:
        model = MovimientoInventarioProductoTerminado
        fields = ["id", "producto", "tipo", "cantidad", "motivo", "saldo_resultante", "creado_por", "creado_en"]
        read_only_fields = fields


class AjusteProductoTerminadoSerializer(serializers.Serializer):
    cantidad_delta = serializers.DecimalField(max_digits=12, decimal_places=2)
    motivo = serializers.CharField(max_length=255)

    def validate_cantidad_delta(self, value):
        if value == 0:
            raise serializers.ValidationError("El ajuste no puede ser de cantidad cero.")
        return value


class MermaProductoTerminadoSerializer(serializers.Serializer):
    cantidad = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    motivo = serializers.CharField(max_length=255)
