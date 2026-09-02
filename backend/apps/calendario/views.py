from rest_framework import viewsets
from rest_framework.response import Response

from apps.usuarios.permissions import EsAdministrador

from . import services
from .models import EventoCalendario
from .serializers import (
    EventoCalendarioActualizarSerializer,
    EventoCalendarioCrearSerializer,
    EventoCalendarioSerializer,
)


class EventoCalendarioViewSet(viewsets.ModelViewSet):
    """Gestión de la integración con Google Calendar — exclusiva de Administrador
    (sección 6 del sistema). Un evento se guarda localmente aunque Google Calendar
    todavía no esté conectado; se sincroniza en cuanto haya credenciales."""

    permission_classes = [EsAdministrador]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        qs = EventoCalendario.objects.select_related("creado_por").all()
        tipo = self.request.query_params.get("tipo")
        referencia_id = self.request.query_params.get("referencia_id")
        if tipo:
            qs = qs.filter(tipo=tipo)
        if referencia_id:
            qs = qs.filter(referencia_id=referencia_id)
        return qs

    def get_serializer_class(self):
        if self.action == "create":
            return EventoCalendarioCrearSerializer
        if self.action == "partial_update":
            return EventoCalendarioActualizarSerializer
        return EventoCalendarioSerializer

    def create(self, request, *args, **kwargs):
        entrada = EventoCalendarioCrearSerializer(data=request.data, context={"request": request})
        entrada.is_valid(raise_exception=True)
        evento = entrada.save()
        return Response(EventoCalendarioSerializer(evento).data, status=201)

    def partial_update(self, request, *args, **kwargs):
        evento = self.get_object()
        entrada = EventoCalendarioActualizarSerializer(data=request.data, partial=True)
        entrada.is_valid(raise_exception=True)
        evento = services.actualizar_evento(evento_id=evento.id, **entrada.validated_data)
        return Response(EventoCalendarioSerializer(evento).data)

    def destroy(self, request, *args, **kwargs):
        evento = self.get_object()
        services.eliminar_evento(evento_id=evento.id)
        return Response(status=204)
