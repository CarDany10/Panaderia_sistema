from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import Usuario
from .permissions import EsAdministrador
from .serializers import (
    RegistroClienteSerializer,
    UsuarioAdminSerializer,
    UsuarioMeSerializer,
)


class LoginRateLimitedView(TokenObtainPairView):
    """Login con límite de intentos por IP (protección contra fuerza bruta de
    contraseñas, regla de seguridad #30 del sistema).

    Nota de despliegue: django-ratelimit usa el backend de caché de Django; con
    la caché en memoria local (la que queda si no se configura otra), el límite
    es por proceso — en un despliegue con varios workers, el límite real
    efectivo se multiplica por esa cantidad. Para un límite exacto entre
    workers, configurar un backend de caché compartido (p. ej. Redis o el de
    base de datos) en producción.
    """

    @method_decorator(ratelimit(key="ip", rate="10/m", method="POST", block=False))
    def post(self, request, *args, **kwargs):
        if getattr(request, "limited", False):
            return Response(
                {"detail": "Demasiados intentos de inicio de sesión. Espera un momento e intenta de nuevo."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        return super().post(request, *args, **kwargs)


class RegistroClienteView(generics.CreateAPIView):
    """Alta pública de una cuenta de Cliente. No requiere autenticación.

    Límite de intentos por IP para evitar registro masivo/spam automatizado.
    """

    serializer_class = RegistroClienteSerializer
    permission_classes = [permissions.AllowAny]

    @method_decorator(ratelimit(key="ip", rate="5/h", method="POST", block=False))
    def post(self, request, *args, **kwargs):
        if getattr(request, "limited", False):
            return Response(
                {"detail": "Demasiados registros desde esta conexión. Intenta de nuevo más tarde."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        return super().post(request, *args, **kwargs)


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
