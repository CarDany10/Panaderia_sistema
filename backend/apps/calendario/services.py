"""Lógica de dominio de EventoCalendario.

El evento local (EventoCalendario) es siempre la fuente de verdad dentro del
sistema; la sincronización con Google es un efecto adicional que nunca debe
impedir que el administrador programe un evento — si las credenciales de Google
todavía no están configuradas, el evento se guarda igual y queda sin
google_event_id hasta que la integración se conecte.
"""

from django.db import transaction
from rest_framework.exceptions import ValidationError

from . import gcal_client
from .models import EventoCalendario


@transaction.atomic
def registrar_evento(*, tipo, referencia_id, titulo, descripcion, fecha_inicio, fecha_fin, creado_por):
    if fecha_fin <= fecha_inicio:
        raise ValidationError("La fecha de fin debe ser posterior a la fecha de inicio.")
    if EventoCalendario.objects.filter(tipo=tipo, referencia_id=referencia_id).exists():
        raise ValidationError(
            "Ya existe un evento de calendario registrado para esta producción/pedido."
        )

    evento = EventoCalendario.objects.create(
        tipo=tipo,
        referencia_id=referencia_id,
        titulo=titulo,
        descripcion=descripcion,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        creado_por=creado_por,
    )
    try:
        google_event_id = gcal_client.crear_evento(
            titulo=titulo, descripcion=descripcion, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin
        )
    except gcal_client.GoogleCalendarNoConfigurado:
        return evento
    evento.google_event_id = google_event_id
    evento.save(update_fields=["google_event_id"])
    return evento


@transaction.atomic
def actualizar_evento(*, evento_id, titulo=None, descripcion=None, fecha_inicio=None, fecha_fin=None):
    evento = EventoCalendario.objects.select_for_update().get(pk=evento_id)
    if titulo is not None:
        evento.titulo = titulo
    if descripcion is not None:
        evento.descripcion = descripcion
    if fecha_inicio is not None:
        evento.fecha_inicio = fecha_inicio
    if fecha_fin is not None:
        evento.fecha_fin = fecha_fin
    if evento.fecha_fin <= evento.fecha_inicio:
        raise ValidationError("La fecha de fin debe ser posterior a la fecha de inicio.")
    evento.save()

    if evento.google_event_id:
        try:
            gcal_client.actualizar_evento(
                google_event_id=evento.google_event_id,
                titulo=evento.titulo,
                descripcion=evento.descripcion,
                fecha_inicio=evento.fecha_inicio,
                fecha_fin=evento.fecha_fin,
            )
        except gcal_client.GoogleCalendarNoConfigurado:
            pass
    return evento


@transaction.atomic
def eliminar_evento(*, evento_id):
    evento = EventoCalendario.objects.select_for_update().get(pk=evento_id)
    if evento.google_event_id:
        try:
            gcal_client.eliminar_evento(google_event_id=evento.google_event_id)
        except gcal_client.GoogleCalendarNoConfigurado:
            pass
    evento.delete()
