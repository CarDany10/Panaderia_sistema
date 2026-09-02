from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.usuarios.views import LogoutView


def health(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    # Panel técnico de soporte del desarrollador, no forma parte del producto (Webflow).
    path("admin/", admin.site.urls),
    path("api/v1/health/", health, name="health"),
    path("api/v1/auth/login/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/v1/auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/v1/auth/logout/", LogoutView.as_view(), name="token_logout"),
    path("api/v1/usuarios/", include("apps.usuarios.urls")),
    path("api/v1/materia-prima/", include("apps.materia_prima.urls")),
    path("api/v1/produccion/", include("apps.produccion.urls")),
    # Los endpoints de los demás módulos (ventas, pedidos, etc.) se agregan
    # a partir de Fase 9 en adelante, con sus permisos y serializers por rol.
]
