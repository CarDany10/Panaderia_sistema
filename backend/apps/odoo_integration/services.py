"""Sincronización de Ventas y Compras hacia Odoo como facturas contables.

Igual que con Google Calendar: si Odoo no está configurado, la operación no
falla — queda registrada como pendiente (SincronizacionOdoo.error explica por
qué) para reintentarla cuando se conecten las credenciales. Si Odoo SÍ está
configurado pero la llamada falla de verdad (auth rechazada, API rota), el
error se re-lanza: quien pidió explícitamente sincronizar debe enterarse.
"""

from django.utils import timezone

from apps.materia_prima.models import Compra
from apps.ventas.models import Venta

from . import odoo_client
from .models import SincronizacionOdoo


def sincronizar_venta(venta_id):
    venta = Venta.objects.select_related("cliente").prefetch_related("detalles__producto").get(pk=venta_id)
    registro, _ = SincronizacionOdoo.objects.get_or_create(
        tipo=SincronizacionOdoo.Tipo.VENTA, referencia_id=venta.id
    )
    nombre_cliente = venta.cliente.username if venta.cliente else "Cliente de mostrador"
    email_cliente = venta.cliente.email if venta.cliente else ""
    lineas = [
        {"nombre": d.producto.nombre, "cantidad": d.cantidad, "precio_unitario": d.precio_unitario}
        for d in venta.detalles.all()
    ]

    try:
        partner_id = odoo_client.buscar_o_crear_partner(nombre=nombre_cliente, email=email_cliente)
        odoo_id = odoo_client.crear_factura_cliente(
            partner_id=partner_id,
            fecha=venta.creado_en.date(),
            lineas=lineas,
            referencia=f"Venta #{venta.numero}",
        )
    except odoo_client.OdooNoConfigurado as exc:
        registro.error = str(exc)
        registro.save(update_fields=["error"])
        return registro
    except odoo_client.OdooError as exc:
        registro.error = str(exc)
        registro.save(update_fields=["error"])
        raise

    registro.odoo_id = odoo_id
    registro.sincronizado_en = timezone.now()
    registro.error = ""
    registro.save(update_fields=["odoo_id", "sincronizado_en", "error"])
    return registro


def sincronizar_compra(compra_id):
    compra = Compra.objects.select_related("materia_prima").get(pk=compra_id)
    registro, _ = SincronizacionOdoo.objects.get_or_create(
        tipo=SincronizacionOdoo.Tipo.COMPRA, referencia_id=compra.id
    )
    lineas = [
        {
            "nombre": f"{compra.materia_prima.nombre} (lote {compra.lote})",
            "cantidad": compra.cantidad,
            "precio_unitario": compra.costo_unitario,
        }
    ]

    try:
        # Sin un proveedor identificado en el modelo de Compra (no se pidió en
        # el sistema), se registra contra un proveedor genérico por lote.
        partner_id = odoo_client.buscar_o_crear_partner(nombre=f"Proveedor lote {compra.lote}")
        odoo_id = odoo_client.crear_factura_proveedor(
            partner_id=partner_id,
            fecha=compra.fecha_compra,
            lineas=lineas,
            referencia=f"Compra {compra.lote} - {compra.materia_prima.nombre}",
        )
    except odoo_client.OdooNoConfigurado as exc:
        registro.error = str(exc)
        registro.save(update_fields=["error"])
        return registro
    except odoo_client.OdooError as exc:
        registro.error = str(exc)
        registro.save(update_fields=["error"])
        raise

    registro.odoo_id = odoo_id
    registro.sincronizado_en = timezone.now()
    registro.error = ""
    registro.save(update_fields=["odoo_id", "sincronizado_en", "error"])
    return registro
