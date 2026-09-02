"""Adaptador delgado sobre la API oficial de Google Calendar.

Aislado en este módulo (en vez de llamar a googleapiclient directamente desde
services.py) para poder simularlo por completo en pruebas sin red ni credenciales
reales, y para que el resto del sistema nunca dependa de detalles de la librería
de Google.

Las credenciales (cuenta de servicio) se leen exclusivamente de variables de
entorno — nunca se commitea un archivo de credenciales al repositorio (regla de
seguridad #5/#30 del sistema).
"""

import json

from django.conf import settings
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/calendar"]


class GoogleCalendarNoConfigurado(Exception):
    """No hay credenciales o calendario configurados todavía."""


class GoogleCalendarError(Exception):
    """La API de Google respondió con un error."""


def _calendar_id():
    calendar_id = getattr(settings, "GOOGLE_CALENDAR_ID", "") or ""
    if not calendar_id:
        raise GoogleCalendarNoConfigurado("No hay un GOOGLE_CALENDAR_ID configurado.")
    return calendar_id


def _construir_servicio():
    credenciales_json = getattr(settings, "GOOGLE_CALENDAR_CREDENTIALS_JSON", "") or ""
    if not credenciales_json:
        raise GoogleCalendarNoConfigurado(
            "No hay credenciales de Google Calendar configuradas "
            "(GOOGLE_CALENDAR_CREDENTIALS_JSON)."
        )
    try:
        info = json.loads(credenciales_json)
    except json.JSONDecodeError as exc:
        raise GoogleCalendarNoConfigurado(
            "GOOGLE_CALENDAR_CREDENTIALS_JSON no contiene un JSON válido."
        ) from exc
    credenciales = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("calendar", "v3", credentials=credenciales, cache_discovery=False)


def _cuerpo_evento(*, titulo, descripcion, fecha_inicio, fecha_fin):
    return {
        "summary": titulo,
        "description": descripcion,
        "start": {"dateTime": fecha_inicio.isoformat()},
        "end": {"dateTime": fecha_fin.isoformat()},
    }


def crear_evento(*, titulo, descripcion, fecha_inicio, fecha_fin):
    servicio = _construir_servicio()
    cuerpo = _cuerpo_evento(
        titulo=titulo, descripcion=descripcion, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin
    )
    try:
        evento = servicio.events().insert(calendarId=_calendar_id(), body=cuerpo).execute()
    except HttpError as exc:
        raise GoogleCalendarError(str(exc)) from exc
    return evento["id"]


def actualizar_evento(*, google_event_id, titulo, descripcion, fecha_inicio, fecha_fin):
    servicio = _construir_servicio()
    cuerpo = _cuerpo_evento(
        titulo=titulo, descripcion=descripcion, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin
    )
    try:
        servicio.events().update(
            calendarId=_calendar_id(), eventId=google_event_id, body=cuerpo
        ).execute()
    except HttpError as exc:
        raise GoogleCalendarError(str(exc)) from exc


def eliminar_evento(*, google_event_id):
    servicio = _construir_servicio()
    try:
        servicio.events().delete(calendarId=_calendar_id(), eventId=google_event_id).execute()
    except HttpError as exc:
        # 404/410: ya no existe en Google (pudo borrarse manualmente) — no es un
        # error real para nuestro propósito de "asegurarse de que no quede".
        if exc.resp is not None and exc.resp.status in (404, 410):
            return
        raise GoogleCalendarError(str(exc)) from exc


def obtener_evento(*, google_event_id):
    servicio = _construir_servicio()
    try:
        return servicio.events().get(calendarId=_calendar_id(), eventId=google_event_id).execute()
    except HttpError as exc:
        raise GoogleCalendarError(str(exc)) from exc
