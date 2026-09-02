from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.usuarios.models import Usuario

from . import services


class DashboardView(APIView):
    """Un solo endpoint que responde con el resumen correspondiente al rol del
    usuario autenticado (secciones 26-29): Administrador, Trabajador, Repartidor
    o Cliente reciben formas de respuesta distintas, cada una sin datos que no
    les corresponde ver."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        rol = request.user.rol
        if rol == Usuario.Rol.ADMIN:
            return Response(services.dashboard_admin())
        if rol == Usuario.Rol.TRABAJADOR:
            return Response(services.dashboard_trabajador())
        if rol == Usuario.Rol.REPARTIDOR:
            return Response(services.dashboard_repartidor(request.user))
        if rol == Usuario.Rol.CLIENTE:
            return Response(services.dashboard_cliente(request.user))
        return Response(status=403)
