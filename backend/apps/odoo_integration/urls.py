from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import EstadoSincronizacionViewSet, SincronizarCompraView, SincronizarVentaView

router = DefaultRouter()
router.register("estado", EstadoSincronizacionViewSet, basename="odoo-estado")

urlpatterns = [
    path("ventas/<int:venta_id>/sincronizar/", SincronizarVentaView.as_view(), name="odoo-sincronizar-venta"),
    path("compras/<int:compra_id>/sincronizar/", SincronizarCompraView.as_view(), name="odoo-sincronizar-compra"),
    path("", include(router.urls)),
]
