from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import PaqueteViewSet, ProduccionViewSet, ProductoViewSet

router = DefaultRouter()
router.register("producciones", ProduccionViewSet, basename="produccion")
router.register("paquetes", PaqueteViewSet, basename="paquete")
router.register("", ProductoViewSet, basename="producto")

urlpatterns = [
    path("", include(router.urls)),
]
