"""Adaptador delgado sobre la API externa estándar de Odoo (XML-RPC), aislado
igual que apps.calendario.gcal_client para poder simularlo por completo en
pruebas sin red ni una instancia real de Odoo.

Odoo no es el núcleo del sistema (ver docs/01-ANALISIS_Y_ARQUITECTURA.md,
sección 3.4): es un conector contable opcional. Django sigue siendo la fuente
de verdad operativa; esto solo empuja ventas/compras hacia Odoo como facturas,
para quien necesite contabilidad/facturación fiscal formal.

Aviso importante para quien despliegue esto contra una instancia real de Odoo:
los IDs de diario contable (ODOO_JOURNAL_ID_VENTAS/COMPRAS) y la configuración
de cuentas/impuestos son específicos de cada instalación de Odoo y no se
pueden adivinar desde aquí — debe configurarlos quien administre esa Odoo.
"""

import xmlrpc.client

from django.conf import settings

TIMEOUT_SEGUNDOS = 15


class OdooNoConfigurado(Exception):
    """No hay credenciales de Odoo configuradas todavía."""


class OdooError(Exception):
    """Odoo respondió con un error (autenticación rechazada, falla de la API, etc.)."""


def _config():
    url = getattr(settings, "ODOO_URL", "") or ""
    db = getattr(settings, "ODOO_DB", "") or ""
    username = getattr(settings, "ODOO_USERNAME", "") or ""
    api_key = getattr(settings, "ODOO_API_KEY", "") or ""
    if not all([url, db, username, api_key]):
        raise OdooNoConfigurado(
            "Faltan credenciales de Odoo (ODOO_URL/ODOO_DB/ODOO_USERNAME/ODOO_API_KEY)."
        )
    return url, db, username, api_key


def _autenticar():
    url, db, username, api_key = _config()
    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
    try:
        uid = common.authenticate(db, username, api_key, {})
    except (xmlrpc.client.Fault, OSError) as exc:
        raise OdooError(f"No se pudo conectar con Odoo: {exc}") from exc
    if not uid:
        raise OdooError("Autenticación con Odoo rechazada; revisar usuario/API key/base de datos.")
    return url, db, uid, api_key


def execute_kw(modelo, metodo, args, kwargs=None):
    url, db, uid, api_key = _autenticar()
    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
    try:
        return models.execute_kw(db, uid, api_key, modelo, metodo, args, kwargs or {})
    except xmlrpc.client.Fault as exc:
        raise OdooError(str(exc)) from exc


def buscar_o_crear_partner(*, nombre, email=""):
    existentes = execute_kw("res.partner", "search", [[["name", "=", nombre]]])
    if existentes:
        return existentes[0]
    return execute_kw("res.partner", "create", [{"name": nombre, "email": email}])


def _lineas_factura(lineas):
    return [
        (
            0,
            0,
            {
                "name": linea["nombre"],
                "quantity": float(linea["cantidad"]),
                "price_unit": float(linea["precio_unitario"]),
            },
        )
        for linea in lineas
    ]


def crear_factura_cliente(*, partner_id, fecha, lineas, referencia=""):
    """Crea una factura de cliente (account.move, move_type=out_invoice) a
    partir de una Venta o Pedido. `lineas`: [{"nombre","cantidad","precio_unitario"}]."""
    valores = {
        "move_type": "out_invoice",
        "partner_id": partner_id,
        "invoice_date": fecha.isoformat(),
        "ref": referencia,
        "invoice_line_ids": _lineas_factura(lineas),
    }
    journal_id = getattr(settings, "ODOO_JOURNAL_ID_VENTAS", "") or ""
    if journal_id:
        valores["journal_id"] = int(journal_id)
    return execute_kw("account.move", "create", [valores])


def crear_factura_proveedor(*, partner_id, fecha, lineas, referencia=""):
    """Crea una factura de proveedor (account.move, move_type=in_invoice) a
    partir de una Compra de materia prima."""
    valores = {
        "move_type": "in_invoice",
        "partner_id": partner_id,
        "invoice_date": fecha.isoformat(),
        "ref": referencia,
        "invoice_line_ids": _lineas_factura(lineas),
    }
    journal_id = getattr(settings, "ODOO_JOURNAL_ID_COMPRAS", "") or ""
    if journal_id:
        valores["journal_id"] = int(journal_id)
    return execute_kw("account.move", "create", [valores])
