from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Usuario
from .permissions import EsAdministrador
from .serializers import (
    RegistroClienteSerializer,
    UsuarioAdminSerializer,
    UsuarioMeSerializer,
)


class RegistroClienteView(generics.CreateAPIView):
    """Alta pública de una cuenta de Cliente. No requiere autenticación."""

    serializer_class = RegistroClienteSerializer
    permission_classes = [permissions.AllowAny]


class LogoutView(APIView):
    """Invalida el refresh token del usuario (lista negra) al cerrar sesión."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        refresh = request.data.get("refresh")
        if not refresh:
            return Response(
                {"detail": "El campo 'refresh' es obligatorio."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            RefreshToken(refresh).blacklist()
        except TokenError:
            return Response(
                {"detail": "Token inválido o ya invalidado."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_205_RESET_CONTENT)


class MeView(generics.RetrieveUpdateAPIView):
    """Perfil propio del usuario autenticado, sea cual sea su rol."""

    serializer_class = UsuarioMeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class UsuarioAdminViewSet(viewsets.ModelViewSet):
    """Gestión de cuentas de Administrador, Trabajador y Repartidor (solo Admin).

    Los usuarios nunca se borran (se desactivan) para conservar la trazabilidad de
    quién realizó cada operación en el historial del sistema.
    """

    queryset = Usuario.objects.exclude(rol=Usuario.Rol.CLIENTE).order_by("username")
    serializer_class = UsuarioAdminSerializer
    permission_classes = [EsAdministrador]
    http_method_names = ["get", "post", "patch", "head", "options"]

    @action(detail=True, methods=["post"], url_path="hacer-admin")
    def hacer_admin(self, request, pk=None):
        usuario = self.get_object()
        usuario.rol = Usuario.Rol.ADMIN
        usuario.save(update_fields=["rol"])
        return Response(UsuarioAdminSerializer(usuario).data)

    @action(detail=True, methods=["post"], url_path="desactivar")
    def desactivar(self, request, pk=None):
        usuario = self.get_object()
        usuario.is_active = False
        usuario.save(update_fields=["is_active"])
        return Response(UsuarioAdminSerializer(usuario).data)

    @action(detail=True, methods=["post"], url_path="activar")
    def activar(self, request, pk=None):
        usuario = self.get_object()
        usuario.is_active = True
        usuario.save(update_fields=["is_active"])
        return Response(UsuarioAdminSerializer(usuario).data)
