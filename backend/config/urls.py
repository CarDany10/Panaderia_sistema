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
    path("api/v1/ventas/", include("apps.ventas.urls")),
    path("api/v1/pedidos/", include("apps.pedidos.urls")),
    path("api/v1/calendario/", include("apps.calendario.urls")),
    path("api/v1/notificaciones/", include("apps.notificaciones.urls")),
    path("api/v1/historial/", include("apps.historial.urls")),
    path("api/v1/dashboard/", include("apps.dashboard.urls")),
    path("api/v1/odoo/", include("apps.odoo_integration.urls")),
]
