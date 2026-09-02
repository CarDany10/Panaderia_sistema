from django.urls import path

from .views import HistorialView

urlpatterns = [
    path("", HistorialView.as_view(), name="historial"),
]
