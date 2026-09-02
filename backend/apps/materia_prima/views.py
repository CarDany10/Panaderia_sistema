from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status

from apps.usuarios.models import Usuario
from apps.usuarios.permissions import EsAdministrador, EsTrabajador

from . import services
from .models import Compra, MateriaPrima, MovimientoInventarioMateriaPrima
from .serializers import (
    AjusteInventarioSerializer,
    CompraSerializer,
    MateriaPrimaAdminSerializer,
    MateriaPrimaTrabajadorSerializer,
    MermaInventarioSerializer,
    MovimientoInventarioMateriaPrimaSerializer,
)


class MateriaPrimaViewSet(viewsets.ModelViewSet):
    """Catálogo de materia prima. Lectura compartida entre Admin y Trabajador (con
    campos distintos por rol); todo lo demás (alta, compras, ajustes, mermas,
    movimientos) es exclusivo del Administrador.
    """

    queryset = MateriaPrima.objects.all()
    # Sin destroy: una materia prima con movimientos no se borra, se desactiva.
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [(EsAdministrador | EsTrabajador)()]
        return [EsAdministrador()]

    def get_serializer_class(self):
        if self.request.user.is_authenticated and self.request.user.rol == Usuario.Rol.ADMIN:
            return MateriaPrimaAdminSerializer
        return MateriaPrimaTrabajadorSerializer

    @action(detail=True, methods=["get"])
    def movimientos(self, request, pk=None):
        materia_prima = self.get_object()
        qs = materia_prima.movimientos.all()
        return Response(MovimientoInventarioMateriaPrimaSerializer(qs, many=True).data)

    @action(detail=True, methods=["post"], url_path="ajustar")
    def ajustar(self, request, pk=None):
        materia_prima = self.get_object()
        serializer = AjusteInventarioSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        movimiento = services.registrar_ajuste(
            materia_prima_id=materia_prima.id,
            cantidad_delta=serializer.validated_data["cantidad_delta"],
            motivo=serializer.validated_data["motivo"],
            creado_por=request.user,
        )
        return Response(
            MovimientoInventarioMateriaPrimaSerializer(movimiento).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="registrar-merma")
    def registrar_merma(self, request, pk=None):
        materia_prima = self.get_object()
        serializer = MermaInventarioSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        movimientos = services.consumir_fifo(
            materia_prima_id=materia_prima.id,
            cantidad_nativa=serializer.validated_data["cantidad"],
            tipo=MovimientoInventarioMateriaPrima.Tipo.MERMA,
            motivo=serializer.validated_data["motivo"],
            creado_por=request.user,
        )
        return Response(
            MovimientoInventarioMateriaPrimaSerializer(movimientos, many=True).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["get"], url_path="alertas-stock-bajo")
    def alertas_stock_bajo(self, request):
        ahora = timezone.now()
        data = [
            {
                "materia_prima_id": m.id,
                "materia_prima": m.nombre,
                "existencia_actual": m.stock_actual,
                "stock_minimo": m.stock_minimo,
                "diferencia": m.stock_minimo - m.stock_actual,
                "fecha_alerta": ahora,
            }
            for m in self.get_queryset()
            if m.stock_bajo
        ]
        return Response(data)


class CompraViewSet(viewsets.ModelViewSet):
    """Cada compra es un movimiento independiente e inmutable una vez registrada."""

    queryset = Compra.objects.select_related("materia_prima").all()
    serializer_class = CompraSerializer
    permission_classes = [EsAdministrador]
    http_method_names = ["get", "post", "head", "options"]
