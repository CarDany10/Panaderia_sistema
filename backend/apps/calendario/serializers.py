from rest_framework import serializers

from apps.pedidos.models import Pedido
from apps.produccion.models import Produccion

from . import services
from .models import EventoCalendario


class EventoCalendarioSerializer(serializers.ModelSerializer):
    sincronizado_con_google = serializers.SerializerMethodField()

    class Meta:
        model = EventoCalendario
        fields = [
            "id",
            "tipo",
            "referencia_id",
            "titulo",
            "descripcion",
            "fecha_inicio",
            "fecha_fin",
            "sincronizado_con_google",
            "creado_por",
            "creado_en",
            "actualizado_en",
        ]
        read_only_fields = fields

    def get_sincronizado_con_google(self, obj):
        return bool(obj.google_event_id)


class EventoCalendarioCrearSerializer(serializers.Serializer):
    tipo = serializers.ChoiceField(choices=EventoCalendario.Tipo.choices)
    referencia_id = serializers.IntegerField()
    titulo = serializers.CharField(max_length=255)
    descripcion = serializers.CharField(required=False, allow_blank=True, default="")
    fecha_inicio = serializers.DateTimeField()
    fecha_fin = serializers.DateTimeField()

    def validate(self, attrs):
        modelo = Produccion if attrs["tipo"] == EventoCalendario.Tipo.PRODUCCION else Pedido
        if not modelo.objects.filter(pk=attrs["referencia_id"]).exists():
            raise serializers.ValidationError(
                f"No existe {'una producción' if modelo is Produccion else 'un pedido'} con id "
                f"{attrs['referencia_id']}."
            )
        return attrs

    def create(self, validated_data):
        return services.registrar_evento(creado_por=self.context["request"].user, **validated_data)


class EventoCalendarioActualizarSerializer(serializers.Serializer):
    titulo = serializers.CharField(max_length=255, required=False)
    descripcion = serializers.CharField(required=False, allow_blank=True)
    fecha_inicio = serializers.DateTimeField(required=False)
    fecha_fin = serializers.DateTimeField(required=False)
