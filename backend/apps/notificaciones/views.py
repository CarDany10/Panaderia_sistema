from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from . import services
from .models import Notificacion
from .serializers import NotificacionSerializer


class NotificacionViewSet(viewsets.ReadOnlyModelViewSet):
    """Cada usuario solo ve (y marca como leídas) sus propias notificaciones,
    sin importar su rol — la restricción es siempre 'son mías', no por rol."""

    serializer_class = NotificacionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Notificacion.objects.filter(destinatario=self.request.user)
        leida = self.request.query_params.get("leida")
        if leida is not None:
            qs = qs.filter(leida=leida.lower() == "true")
        return qs

    @action(detail=True, methods=["post"], url_path="marcar-leida")
    def marcar_leida(self, request, pk=None):
        # get_object() ya resuelve contra get_queryset() (solo notificaciones
        # propias), así que una notificación ajena responde 404, no 403.
        notificacion = self.get_object()
        notificacion.leida = True
        notificacion.save(update_fields=["leida"])
        return Response(NotificacionSerializer(notificacion).data)

    @action(detail=False, methods=["post"], url_path="marcar-todas-leidas")
    def marcar_todas_leidas(self, request):
        services.marcar_todas_leidas(usuario=request.user)
        return Response(status=204)
