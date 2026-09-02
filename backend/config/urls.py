from django.contrib import admin
from django.http import JsonResponse
from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView


def health(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    # Panel técnico de soporte del desarrollador, no forma parte del producto (Webflow).
    path("admin/", admin.site.urls),
    path("api/v1/health/", health, name="health"),
    path("api/v1/auth/login/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/v1/auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    # Los endpoints propios de cada módulo (usuarios, materia prima, producción, etc.)
    # se agregan a partir de Fase 5 en adelante, con sus permisos y serializers por rol.
]
