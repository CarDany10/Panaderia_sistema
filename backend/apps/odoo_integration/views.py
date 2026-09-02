from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.usuarios.permissions import EsAdministrador

from . import odoo_client, services
from .models import SincronizacionOdoo
from .serializers import SincronizacionOdooSerializer


class SincronizarVentaView(APIView):
    """Gestión de la integración con Odoo (sección 6) — exclusiva de Admin.
    Empuja una Venta ya registrada como factura de cliente en Odoo."""

    permission_classes = [EsAdministrador]

    def post(self, request, venta_id):
        try:
            registro = services.sincronizar_venta(venta_id)
        except odoo_client.OdooError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(SincronizacionOdooSerializer(registro).data)


class SincronizarCompraView(APIView):
    """Empuja una Compra de materia prima ya registrada como factura de
    proveedor en Odoo."""

    permission_classes = [EsAdministrador]

    def post(self, request, compra_id):
        try:
            registro = services.sincronizar_compra(compra_id)
        except odoo_client.OdooError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(SincronizacionOdooSerializer(registro).data)


class EstadoSincronizacionViewSet(viewsets.ReadOnlyModelViewSet):
    """Consulta del estado de sincronización (qué se envió a Odoo y qué sigue
    pendiente), para que el Administrador pueda ver de un vistazo qué falta."""

    queryset = SincronizacionOdoo.objects.all()
    serializer_class = SincronizacionOdooSerializer
    permission_classes = [EsAdministrador]
