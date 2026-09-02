from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.usuarios.models import Usuario
from apps.usuarios.permissions import EsAdministrador, EsCliente, EsRepartidor, EsTrabajador

from . import services
from .models import Pedido
from .serializers import (
    AsignarRepartidorSerializer,
    CalificarPedidoSerializer,
    CancelarPedidoSerializer,
    PedidoCrearSerializer,
    PedidoSerializer,
    PedidoTrabajadorSerializer,
)


class PedidoViewSet(viewsets.ModelViewSet):
    """Pedidos del cliente. Cada rol ve solo lo que le corresponde: Cliente sus
    propios pedidos, Repartidor los que tiene asignados, Trabajador todos (para
    saber qué producir, sin datos financieros ni del cliente) y Administrador
    todos con control total.
    """

    http_method_names = ["get", "post", "head", "options"]

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [(EsAdministrador | EsTrabajador | EsRepartidor | EsCliente)()]
        if self.action == "create":
            return [EsCliente()]
        if self.action == "asignar_repartidor":
            return [EsAdministrador()]
        if self.action in ("marcar_en_camino", "marcar_entregado"):
            return [EsRepartidor()]
        if self.action == "cancelar":
            return [(EsAdministrador | EsCliente)()]
        if self.action == "calificar":
            return [EsCliente()]
        return [EsAdministrador()]

    def get_queryset(self):
        qs = Pedido.objects.select_related("cliente").prefetch_related(
            "detalles__producto", "detalles__paquete", "entrega__repartidor", "entrega__calificacion"
        )
        user = self.request.user
        if not user.is_authenticated:
            return qs.none()
        if user.rol == Usuario.Rol.ADMIN or user.rol == Usuario.Rol.TRABAJADOR:
            return qs
        if user.rol == Usuario.Rol.REPARTIDOR:
            return qs.filter(entrega__repartidor=user)
        if user.rol == Usuario.Rol.CLIENTE:
            return qs.filter(cliente=user)
        return qs.none()

    def get_serializer_class(self):
        if self.action == "create":
            return PedidoCrearSerializer
        if self.request.user.is_authenticated and self.request.user.rol == Usuario.Rol.TRABAJADOR:
            return PedidoTrabajadorSerializer
        return PedidoSerializer

    def create(self, request, *args, **kwargs):
        entrada = PedidoCrearSerializer(data=request.data, context={"request": request})
        entrada.is_valid(raise_exception=True)
        pedido = entrada.save()
        return Response(PedidoSerializer(pedido).data, status=201)

    @action(detail=True, methods=["post"], url_path="asignar-repartidor")
    def asignar_repartidor(self, request, pk=None):
        pedido = self.get_object()
        serializer = AsignarRepartidorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pedido = services.asignar_repartidor(
            pedido_id=pedido.id,
            repartidor=serializer.validated_data["repartidor"],
            creado_por=request.user,
        )
        return Response(PedidoSerializer(pedido).data)

    @action(detail=True, methods=["post"], url_path="marcar-en-camino")
    def marcar_en_camino(self, request, pk=None):
        pedido = self.get_object()
        pedido = services.marcar_en_camino(pedido_id=pedido.id, repartidor=request.user)
        return Response(PedidoSerializer(pedido).data)

    @action(detail=True, methods=["post"], url_path="marcar-entregado")
    def marcar_entregado(self, request, pk=None):
        pedido = self.get_object()
        pedido = services.marcar_entregado(pedido_id=pedido.id, repartidor=request.user)
        return Response(PedidoSerializer(pedido).data)

    @action(detail=True, methods=["post"], url_path="cancelar")
    def cancelar(self, request, pk=None):
        pedido = self.get_object()
        serializer = CancelarPedidoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pedido = services.cancelar_pedido(
            pedido_id=pedido.id,
            motivo=serializer.validated_data["motivo"],
            creado_por=request.user,
            solo_si_pendiente=(request.user.rol == Usuario.Rol.CLIENTE),
        )
        return Response(PedidoSerializer(pedido).data)

    @action(detail=True, methods=["post"], url_path="calificar")
    def calificar(self, request, pk=None):
        pedido = self.get_object()
        serializer = CalificarPedidoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.calificar_repartidor(
            pedido_id=pedido.id,
            cliente=request.user,
            estrellas=serializer.validated_data["estrellas"],
            comentario=serializer.validated_data.get("comentario", ""),
        )
        # Se vuelve a consultar (en vez de reusar `pedido`) para que la relación
        # entrega.calificacion recién creada no quede con una caché desactualizada.
        pedido_actualizado = self.get_queryset().get(pk=pedido.id)
        return Response(PedidoSerializer(pedido_actualizado).data, status=201)
