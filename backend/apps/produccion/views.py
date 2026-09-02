from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.usuarios.models import Usuario
from apps.usuarios.permissions import EsAdministrador, EsTrabajador

from . import services
from .models import Paquete, Producto, Produccion
from .serializers import (
    AjusteProductoTerminadoSerializer,
    MermaProductoTerminadoSerializer,
    MovimientoInventarioProductoTerminadoSerializer,
    PaqueteSerializer,
    ProduccionAdminSerializer,
    ProduccionCrearSerializer,
    ProduccionTrabajadorSerializer,
    ProductoAdminSerializer,
    ProductoTrabajadorSerializer,
)


class PaqueteViewSet(viewsets.ModelViewSet):
    """Configuración de venta por paquete de un producto. Exclusivo de Administrador
    en esta fase; se expone lectura pública/de cliente al construir Pedidos (Fase 10)."""

    queryset = Paquete.objects.select_related("producto").all()
    serializer_class = PaqueteSerializer
    permission_classes = [EsAdministrador]
    http_method_names = ["get", "post", "patch", "head", "options"]


class ProductoViewSet(viewsets.ModelViewSet):
    """Catálogo de producto terminado. Alta/edición, ajustes y mermas directas son
    exclusivas de Administrador; la lectura (con campos filtrados) es compartida
    con Trabajador, que la necesita para registrar producciones."""

    queryset = Producto.objects.all()
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [(EsAdministrador | EsTrabajador)()]
        return [EsAdministrador()]

    def get_serializer_class(self):
        if self.request.user.is_authenticated and self.request.user.rol == Usuario.Rol.ADMIN:
            return ProductoAdminSerializer
        return ProductoTrabajadorSerializer

    @action(detail=True, methods=["get"])
    def movimientos(self, request, pk=None):
        producto = self.get_object()
        qs = producto.movimientos.all()
        return Response(MovimientoInventarioProductoTerminadoSerializer(qs, many=True).data)

    @action(detail=True, methods=["post"], url_path="ajustar")
    def ajustar(self, request, pk=None):
        producto = self.get_object()
        serializer = AjusteProductoTerminadoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        movimiento = services.registrar_ajuste_producto_terminado(
            producto_id=producto.id,
            cantidad_delta=serializer.validated_data["cantidad_delta"],
            motivo=serializer.validated_data["motivo"],
            creado_por=request.user,
        )
        return Response(
            MovimientoInventarioProductoTerminadoSerializer(movimiento).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="registrar-merma")
    def registrar_merma(self, request, pk=None):
        producto = self.get_object()
        serializer = MermaProductoTerminadoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        movimiento = services.registrar_merma_producto_terminado(
            producto_id=producto.id,
            cantidad=serializer.validated_data["cantidad"],
            motivo=serializer.validated_data["motivo"],
            creado_por=request.user,
        )
        return Response(
            MovimientoInventarioProductoTerminadoSerializer(movimiento).data,
            status=status.HTTP_201_CREATED,
        )


class ProduccionViewSet(viewsets.ModelViewSet):
    """Registro de producciones. Tanto Admin como Trabajador pueden registrar y
    consultar (con campos financieros ocultos para Trabajador); no se permite
    editar ni borrar una producción ya registrada (afectó inventario real)."""

    queryset = Produccion.objects.select_related("producto").prefetch_related(
        "consumos__materia_prima"
    )
    http_method_names = ["get", "post", "head", "options"]

    def get_permissions(self):
        return [(EsAdministrador | EsTrabajador)()]

    def get_output_serializer_class(self):
        if self.request.user.rol == Usuario.Rol.ADMIN:
            return ProduccionAdminSerializer
        return ProduccionTrabajadorSerializer

    def get_serializer_class(self):
        if self.action == "create":
            return ProduccionCrearSerializer
        return self.get_output_serializer_class()

    def create(self, request, *args, **kwargs):
        entrada = ProduccionCrearSerializer(data=request.data, context={"request": request})
        entrada.is_valid(raise_exception=True)
        produccion = entrada.save()
        salida = self.get_output_serializer_class()(produccion)
        return Response(salida.data, status=status.HTTP_201_CREATED)
