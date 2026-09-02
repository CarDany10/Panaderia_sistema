from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.usuarios.permissions import EsAdministrador

from . import services
from .models import Venta
from .serializers import AnularVentaSerializer, VentaCrearSerializer, VentaSerializer


class VentaViewSet(viewsets.ModelViewSet):
    """Registro de ventas de mostrador (producto terminado ya disponible). Exclusivo
    de Administrador: el Trabajador no vende y el Cliente compra vía Pedido (Fase 10).

    No se edita ni se borra una venta; para revertir inventario se usa la acción
    `anular`, que conserva el registro original y dejar rastro del porqué.
    """

    queryset = Venta.objects.select_related("cliente").prefetch_related("detalles__producto", "detalles__paquete")
    permission_classes = [EsAdministrador]
    http_method_names = ["get", "post", "head", "options"]

    def get_serializer_class(self):
        if self.action == "create":
            return VentaCrearSerializer
        return VentaSerializer

    def create(self, request, *args, **kwargs):
        entrada = VentaCrearSerializer(data=request.data, context={"request": request})
        entrada.is_valid(raise_exception=True)
        venta = entrada.save()
        return Response(VentaSerializer(venta).data, status=201)

    @action(detail=True, methods=["post"], url_path="anular")
    def anular(self, request, pk=None):
        venta = self.get_object()
        serializer = AnularVentaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        venta = services.anular_venta(
            venta_id=venta.id,
            motivo=serializer.validated_data["motivo"],
            creado_por=request.user,
        )
        return Response(VentaSerializer(venta).data)
