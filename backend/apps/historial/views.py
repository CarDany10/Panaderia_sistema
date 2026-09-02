from django.utils.dateparse import parse_date
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.usuarios.permissions import EsAdministrador

from . import services


class HistorialView(APIView):
    """Bitácora única del sistema (sección 25): un solo apartado filtrable, en vez
    de reportes separados por módulo. Exclusivo de Administrador.

    Parámetros de consulta admitidos: fecha_desde, fecha_hasta (YYYY-MM-DD),
    tipo (COMPRA|PRODUCCION|VENTA|PEDIDO|MERMA|AJUSTE), materia_prima_id,
    producto_id, limit, offset.
    """

    permission_classes = [EsAdministrador]

    def get(self, request):
        params = request.query_params
        resultado = services.listar_historial(
            fecha_desde=parse_date(params["fecha_desde"]) if params.get("fecha_desde") else None,
            fecha_hasta=parse_date(params["fecha_hasta"]) if params.get("fecha_hasta") else None,
            tipo=params.get("tipo") or None,
            materia_prima_id=params.get("materia_prima_id") or None,
            producto_id=params.get("producto_id") or None,
            limit=int(params.get("limit", 50)),
            offset=int(params.get("offset", 0)),
        )
        return Response(resultado)
