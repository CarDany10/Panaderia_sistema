from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ProduccionViewSet, ProductoViewSet

router = DefaultRouter()
router.register("producciones", ProduccionViewSet, basename="produccion")
router.register("", ProductoViewSet, basename="producto")

urlpatterns = [
    path("", include(router.urls)),
]
