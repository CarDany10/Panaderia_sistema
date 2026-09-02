from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CompraViewSet, MateriaPrimaViewSet

router = DefaultRouter()
router.register("compras", CompraViewSet, basename="compra")
router.register("", MateriaPrimaViewSet, basename="materia-prima")

urlpatterns = [
    path("", include(router.urls)),
]
