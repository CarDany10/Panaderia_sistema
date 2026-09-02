from decimal import Decimal

from rest_framework import serializers

from apps.produccion.models import Paquete, Producto
from apps.usuarios.models import Usuario

from . import services
from .models import DetalleVenta, Venta


class ItemVentaSerializer(serializers.Serializer):
    producto = serializers.PrimaryKeyRelatedField(queryset=Producto.objects.all())
    cantidad = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    paquete = serializers.PrimaryKeyRelatedField(
        queryset=Paquete.objects.all(), required=False, allow_null=True
    )


class VentaCrearSerializer(serializers.Serializer):
    cliente = serializers.PrimaryKeyRelatedField(
        queryset=Usuario.objects.filter(rol=Usuario.Rol.CLIENTE), required=False, allow_null=True
    )
    metodo_pago = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")
    direccion_entrega = serializers.CharField(required=False, allow_blank=True, default="")
    items = ItemVentaSerializer(many=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("Debe incluir al menos un producto en la venta.")
        return value

    def create(self, validated_data):
        creado_por = self.context["request"].user
        cliente = validated_data.get("cliente")
        items = [
            {
                "producto_id": item["producto"].id,
                "cantidad": item["cantidad"],
                "paquete_id": item["paquete"].id if item.get("paquete") else None,
            }
            for item in validated_data["items"]
        ]
        return services.registrar_venta(
            cliente_id=cliente.id if cliente else None,
            items=items,
            metodo_pago=validated_data.get("metodo_pago", ""),
            direccion_entrega=validated_data.get("direccion_entrega", ""),
            creado_por=creado_por,
        )


class DetalleVentaSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source="producto.nombre", read_only=True)
    paquete_nombre = serializers.CharField(source="paquete.nombre", read_only=True, default=None)

    class Meta:
        model = DetalleVenta
        fields = [
            "id",
            "producto",
            "producto_nombre",
            "paquete",
            "paquete_nombre",
            "cantidad",
            "cantidad_en_unidades",
            "precio_unitario",
            "subtotal",
        ]
        read_only_fields = fields


class VentaSerializer(serializers.ModelSerializer):
    numero = serializers.CharField(read_only=True)
    cliente_nombre = serializers.SerializerMethodField()
    detalles = DetalleVentaSerializer(many=True, read_only=True)

    class Meta:
        model = Venta
        fields = [
            "id",
            "numero",
            "cliente",
            "cliente_nombre",
            "estado",
            "metodo_pago",
            "direccion_entrega",
            "total",
            "detalles",
            "creado_en",
        ]
        read_only_fields = fields

    def get_cliente_nombre(self, obj):
        return obj.cliente.username if obj.cliente else None


class AnularVentaSerializer(serializers.Serializer):
    motivo = serializers.CharField(max_length=255)
