from rest_framework import serializers

from .models import SincronizacionOdoo


class SincronizacionOdooSerializer(serializers.ModelSerializer):
    sincronizado = serializers.SerializerMethodField()

    class Meta:
        model = SincronizacionOdoo
        fields = [
            "id",
            "tipo",
            "referencia_id",
            "odoo_id",
            "sincronizado",
            "sincronizado_en",
            "error",
            "creado_en",
        ]
        read_only_fields = fields

    def get_sincronizado(self, obj):
        return bool(obj.odoo_id)
