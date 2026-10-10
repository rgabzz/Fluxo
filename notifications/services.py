"""Criação de eventos, regras de destinatário e envio de push (Expo)."""
import logging
import threading

import requests
from django.conf import settings
from django.db import transaction
from django.db.models import Exists, OuterRef, Q

from .models import Event, EventRead, PushToken

log = logging.getLogger(__name__)

# StopReached atualiza o progresso mas NÃO notifica: evita spam (relatório V2, seção 10).
NOTIFIABLE_TYPES = [t for t in Event.Type.values if t != Event.Type.STOP_REACHED]


# ------------------------------------------------------------------ destinatários
def _student_route_ids(user):
    """Rotas que o usuário favoritou ou onde tem reserva em alguma lista."""
    from buses.models import BusListEntry, RouteFavorite

    fav = RouteFavorite.objects.filter(user=user).values("route_id")
    reserved = BusListEntry.objects.filter(user=user).values("bus_list__bus_route_id")
    return fav, reserved


def visible_events_for(user):
    """Eventos notificáveis que ESTE usuário deve ver (sino + tela de avisos)."""
    qs = Event.objects.filter(type__in=NOTIFIABLE_TYPES)
    if user.is_fluxo_admin:
        return qs
    if user.is_driver:
        return qs.filter(Q(route__isnull=True) | Q(route__bus__driver=user))
    fav, reserved = _student_route_ids(user)
    return qs.filter(Q(route__isnull=True) | Q(route_id__in=fav) | Q(route_id__in=reserved))


def annotate_read(qs, user):
    return qs.annotate(is_read=Exists(EventRead.objects.filter(user=user, event=OuterRef("pk"))))


def push_recipient_ids(event: Event) -> set[int]:
    from buses.models import BusListEntry, RouteFavorite
    from users.models import User

    if event.route_id is None:  # aviso geral
        ids = set(User.objects.filter(is_active=True).values_list("id", flat=True))
    else:
        ids = set(RouteFavorite.objects.filter(route_id=event.route_id).values_list("user_id", flat=True))
        ids |= set(
            BusListEntry.objects.filter(bus_list__bus_route_id=event.route_id).values_list("user_id", flat=True)
        )
        driver_id = event.route.bus.driver_id if event.route.bus_id else None
        if driver_id:
            ids.add(driver_id)
    if event.actor_id:
        ids.discard(event.actor_id)
    return ids


# ------------------------------------------------------------------ criação
def emit_event(
    type,
    *,
    title,
    message="",
    route=None,
    actor=None,
    level=Event.Level.INFO,
    journey_id=None,
    payload=None,
) -> Event:
    event = Event.objects.create(
        type=type,
        route=route,
        actor=actor if getattr(actor, "pk", None) else None,
        title=title[:140],
        message=message,
        level=level,
        journey_id=journey_id,
        payload=payload or {},
    )
    if type in NOTIFIABLE_TYPES and settings.PUSH_ENABLED:
        # só dispara depois que a transação confirmar (evita push de algo que deu rollback)
        transaction.on_commit(lambda: _dispatch_push_async(event.pk))
    return event


# ------------------------------------------------------------------ push
def _dispatch_push_async(event_id: int):
    threading.Thread(target=send_push_for_event, args=(event_id,), daemon=True).start()


def send_push_for_event(event_id: int):
    try:
        event = Event.objects.select_related("route__bus").get(pk=event_id)
        tokens = list(
            PushToken.objects.filter(user_id__in=push_recipient_ids(event)).values_list("token", flat=True)
        )
        if tokens:
            _send_expo(tokens, event)
    except Exception:  # push nunca pode derrubar a API
        log.exception("Falha ao enviar push do evento %s", event_id)


def _send_expo(tokens: list[str], event: Event):
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if settings.EXPO_ACCESS_TOKEN:
        headers["Authorization"] = f"Bearer {settings.EXPO_ACCESS_TOKEN}"

    for i in range(0, len(tokens), 100):  # limite da API do Expo: 100 por requisição
        chunk = tokens[i : i + 100]
        messages = [
            {
                "to": t,
                "title": event.title,
                "body": event.message[:200],
                "sound": "default",
                "data": {"event_id": event.pk, "type": event.type, "route_id": event.route_id},
            }
            for t in chunk
        ]
        resp = requests.post(settings.EXPO_PUSH_URL, json=messages, headers=headers, timeout=10)
        resp.raise_for_status()
        dead = [
            chunk[idx]
            for idx, ticket in enumerate(resp.json().get("data", []))
            if ticket.get("status") == "error" and ticket.get("details", {}).get("error") == "DeviceNotRegistered"
        ]
        if dead:
            PushToken.objects.filter(token__in=dead).delete()
