from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import EventoCalendarioViewSet

router = DefaultRouter()
router.register("eventos", EventoCalendarioViewSet, basename="evento-calendario")

urlpatterns = [
    path("", include(router.urls)),
]
