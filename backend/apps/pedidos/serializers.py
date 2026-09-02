from decimal import Decimal

from rest_framework import serializers

from apps.produccion.models import Paquete, Producto
from apps.usuarios.models import Usuario

from . import services
from .models import Calificacion, DetallePedido, Entrega, Pedido


class ItemPedidoSerializer(serializers.Serializer):
    producto = serializers.PrimaryKeyRelatedField(queryset=Producto.objects.filter(activo=True))
    cantidad = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    paquete = serializers.PrimaryKeyRelatedField(
        queryset=Paquete.objects.filter(activo=True), required=False, allow_null=True
    )


class PedidoCrearSerializer(serializers.Serializer):
    direccion_entrega = serializers.CharField()
    telefono_contacto = serializers.CharField(max_length=30)
    items = ItemPedidoSerializer(many=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("Debe incluir al menos un producto en el pedido.")
        return value

    def create(self, validated_data):
        cliente = self.context["request"].user
        items = [
            {
                "producto_id": item["producto"].id,
                "cantidad": item["cantidad"],
                "paquete_id": item["paquete"].id if item.get("paquete") else None,
            }
            for item in validated_data["items"]
        ]
        return services.registrar_pedido(
            cliente=cliente,
            items=items,
            direccion_entrega=validated_data["direccion_entrega"],
            telefono_contacto=validated_data["telefono_contacto"],
        )


class DetallePedidoSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source="producto.nombre", read_only=True)
    paquete_nombre = serializers.CharField(source="paquete.nombre", read_only=True, default=None)

    class Meta:
        model = DetallePedido
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


class DetallePedidoTrabajadorSerializer(serializers.ModelSerializer):
    """Sin precios: al Trabajador solo le interesa qué y cuánto preparar."""

    producto_nombre = serializers.CharField(source="producto.nombre", read_only=True)

    class Meta:
        model = DetallePedido
        fields = ["id", "producto", "producto_nombre", "cantidad", "cantidad_en_unidades"]
        read_only_fields = fields


class CalificacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Calificacion
        fields = ["id", "estrellas", "comentario", "creado_en"]
        read_only_fields = fields


class EntregaSerializer(serializers.ModelSerializer):
    repartidor_nombre = serializers.CharField(source="repartidor.username", read_only=True)
    calificacion = CalificacionSerializer(read_only=True)

    class Meta:
        model = Entrega
        fields = [
            "id",
            "repartidor",
            "repartidor_nombre",
            "fecha_asignacion",
            "fecha_entrega",
            "calificacion",
        ]
        read_only_fields = fields


class PedidoSerializer(serializers.ModelSerializer):
    """Vista completa: Administrador, Cliente (dueño) y Repartidor (asignado)."""

    numero = serializers.CharField(read_only=True)
    cliente_nombre = serializers.CharField(source="cliente.username", read_only=True)
    detalles = DetallePedidoSerializer(many=True, read_only=True)
    entrega = EntregaSerializer(read_only=True)

    class Meta:
        model = Pedido
        fields = [
            "id",
            "numero",
            "cliente",
            "cliente_nombre",
            "estado",
            "direccion_entrega",
            "telefono_contacto",
            "total",
            "detalles",
            "entrega",
            "creado_en",
        ]
        read_only_fields = fields


class PedidoTrabajadorSerializer(serializers.ModelSerializer):
    """Solo lo necesario para producir: sin cliente, dirección, teléfono, precios
    ni datos de entrega/calificación."""

    numero = serializers.CharField(read_only=True)
    detalles = DetallePedidoTrabajadorSerializer(many=True, read_only=True)

    class Meta:
        model = Pedido
        fields = ["id", "numero", "estado", "detalles", "creado_en"]
        read_only_fields = fields


class AsignarRepartidorSerializer(serializers.Serializer):
    repartidor = serializers.PrimaryKeyRelatedField(
        queryset=Usuario.objects.filter(rol=Usuario.Rol.REPARTIDOR, is_active=True)
    )


class CancelarPedidoSerializer(serializers.Serializer):
    motivo = serializers.CharField(max_length=255)


class CalificarPedidoSerializer(serializers.Serializer):
    estrellas = serializers.IntegerField(min_value=1, max_value=5)
    comentario = serializers.CharField(required=False, allow_blank=True, default="")
