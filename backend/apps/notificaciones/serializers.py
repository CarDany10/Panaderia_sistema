from rest_framework import serializers

from .models import Notificacion


class NotificacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notificacion
        fields = ["id", "tipo", "titulo", "mensaje", "leida", "referencia_id", "creado_en"]
        read_only_fields = fields
