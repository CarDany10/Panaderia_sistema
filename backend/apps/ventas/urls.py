from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import VentaViewSet

router = DefaultRouter()
router.register("", VentaViewSet, basename="venta")

urlpatterns = [
    path("", include(router.urls)),
]
