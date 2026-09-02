from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import MeView, RegistroClienteView, UsuarioAdminViewSet

router = DefaultRouter()
router.register("", UsuarioAdminViewSet, basename="usuario")

urlpatterns = [
    path("registro-cliente/", RegistroClienteView.as_view(), name="registro-cliente"),
    path("me/", MeView.as_view(), name="usuario-me"),
    path("", include(router.urls)),
]
