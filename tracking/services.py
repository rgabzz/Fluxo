"""Regras de negócio da jornada (iniciar, receber GPS, avançar paradas, atraso, cancelar, finalizar)."""
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from notifications.models import Event
from notifications.services import emit_event

from .models import BusLocation, Journey, JourneyStopProgress
from .progress import Sample, TrackState, evaluate


class Conflict(ValidationError):
    status_code = 409


# ------------------------------------------------------------------ helpers
def can_operate(user, journey: Journey) -> bool:
    return user.is_fluxo_admin or (journey.driver_id is not None and journey.driver_id == user.id)


def ensure_operable(user, journey: Journey):
    if not can_operate(user, journey):
        raise PermissionDenied("Você não é o motorista desta jornada.")
    if not journey.is_active:
        raise Conflict("A jornada não está em andamento.")


def next_stop(journey: Journey):
    reached = journey.progress.values_list("stop_id", flat=True)
    return journey.route.stops.exclude(id__in=reached).order_by("order").first()


def _pending_departure(journey: Journey):
    return journey.progress.filter(departed_at__isnull=True).select_related("stop").order_by("-stop__order").first()


# ------------------------------------------------------------------ ciclo da jornada
@transaction.atomic
def start_journey(user, route) -> Journey:
    if not route.is_operating:
        raise Conflict("Esta rota está suspensa.")

    driver = route.bus.driver if route.bus_id and route.bus.driver_id else None
    if user.is_driver:
        if driver is None or driver.id != user.id:
            raise PermissionDenied("Você não é o motorista desta rota.")
        driver = user
    else:  # admin iniciando (testes/suporte)
        driver = driver or user

    try:
        with transaction.atomic():
            journey = Journey.objects.create(route=route, driver=driver)
    except IntegrityError:
        raise Conflict("Já existe uma jornada em andamento para esta rota ou para este motorista.")

    emit_event(
        Event.Type.JOURNEY_STARTED,
        title=f"Jornada iniciada: {route.display_name}",
        message="O ônibus saiu e a viagem está em andamento.",
        route=route,
        actor=user,
        journey_id=journey.pk,
    )
    return journey


@transaction.atomic
def report_delay(user, journey: Journey, minutes: int, note: str = ""):
    ensure_operable(user, journey)
    journey.delay_minutes, journey.delay_note = minutes, note
    journey.save(update_fields=["delay_minutes", "delay_note"])
    emit_event(
        Event.Type.DELAY_REPORTED,
        title=f"Atraso de {minutes} min: {journey.route.display_name}",
        message=note,
        route=journey.route,
        actor=user,
        level=Event.Level.IMPORTANT,
        journey_id=journey.pk,
        payload={"minutes": minutes},
    )


@transaction.atomic
def cancel_journey(user, journey: Journey, reason: str = ""):
    ensure_operable(user, journey)
    journey.status, journey.finished_at, journey.cancel_reason = (
        Journey.Status.CANCELED,
        timezone.now(),
        reason,
    )
    journey.save(update_fields=["status", "finished_at", "cancel_reason"])
    emit_event(
        Event.Type.STATUS_CHANGED,
        title=f"Jornada cancelada: {journey.route.display_name}",
        message=reason,
        route=journey.route,
        actor=user,
        level=Event.Level.URGENT,
        journey_id=journey.pk,
    )


@transaction.atomic
def finish_journey(user, journey: Journey):
    ensure_operable(user, journey)
    journey.status, journey.finished_at = Journey.Status.FINISHED, timezone.now()
    journey.save(update_fields=["status", "finished_at"])
    emit_event(
        Event.Type.JOURNEY_FINISHED,
        title=f"Jornada finalizada: {journey.route.display_name}",
        route=journey.route,
        actor=user,
        journey_id=journey.pk,
    )


# ------------------------------------------------------------------ progresso
def _mark_reached(journey: Journey, stop, when, source, actor):
    # ao chegar numa parada, a anterior (se ainda "aberta") é dada como concluída
    journey.progress.filter(departed_at__isnull=True).update(departed_at=when)
    JourneyStopProgress.objects.create(journey=journey, stop=stop, reached_at=when, source=source)
    emit_event(
        Event.Type.STOP_REACHED,  # atualiza progresso, NÃO vai ao sino
        title=f"Parada alcançada: {stop.name}",
        route=journey.route,
        actor=actor,
        journey_id=journey.pk,
        payload={"stop_id": stop.pk, "order": stop.order},
    )


@transaction.atomic
def reach_stop_manually(user, journey: Journey, stop_id: int):
    """Motorista confirma a PRÓXIMA parada (único caminho p/ paradas sem coordenada)."""
    journey = Journey.objects.select_for_update().select_related("route").get(pk=journey.pk)
    ensure_operable(user, journey)
    nxt = next_stop(journey)
    if nxt is None:
        raise Conflict("Todas as paradas já foram concluídas.")
    if nxt.pk != stop_id:
        raise Conflict(f"A próxima parada da ordem é '{nxt.name}' (id {nxt.pk}). Não é possível pular nem voltar.")
    _mark_reached(journey, nxt, timezone.now(), JourneyStopProgress.Source.MANUAL, user)
    return nxt


@transaction.atomic
def ingest_samples(user, journey: Journey, samples: list[dict], replay: bool = False) -> dict:
    """
    Recebe 1..N amostras de GPS do motorista.
    replay=True => envio de fila offline: não aplica o limite de idade (30 s) da amostra.
    """
    cfg = settings.FLUXO_TRACKING
    journey = Journey.objects.select_for_update().select_related("route").get(pk=journey.pk)
    ensure_operable(user, journey)

    now = timezone.now()
    state = TrackState(
        journey.arrival_streak, journey.arrival_last_at, journey.departure_streak, journey.departure_last_at
    )
    summary = {"accepted": 0, "ignored": 0, "reached_stops": [], "departed_stops": []}
    last_accepted = None

    for raw in sorted(samples, key=lambda s: s["recorded_at"]):
        t = raw["recorded_at"]
        too_future = t > now + timedelta(seconds=60)
        out_of_order = journey.last_sample_at is not None and t <= journey.last_sample_at
        if too_future or out_of_order:
            summary["ignored"] += 1
            continue

        summary["accepted"] += 1
        journey.last_sample_at = t
        last_accepted = raw

        too_old = (not replay) and (now - t).total_seconds() > cfg["MAX_SAMPLE_AGE_S"]
        if too_old:  # atualiza a posição, mas não conta para chegada/saída
            continue

        nxt = next_stop(journey)
        nxt_xy = (nxt.latitude, nxt.longitude) if nxt and nxt.has_coordinates else None
        dep = _pending_departure(journey)
        dep_xy = (dep.stop.latitude, dep.stop.longitude) if dep and dep.stop.has_coordinates else None

        result = evaluate(
            Sample(raw["latitude"], raw["longitude"], t, raw.get("accuracy")), state, nxt_xy, dep_xy, cfg
        )
        state = result.state
        if result.ignored:
            continue
        if result.departed and dep:
            dep.departed_at = t
            dep.save(update_fields=["departed_at"])
            summary["departed_stops"].append(dep.stop_id)
        if result.arrived and nxt:
            _mark_reached(journey, nxt, t, JourneyStopProgress.Source.AUTO, user)
            summary["reached_stops"].append(nxt.pk)

    if last_accepted:
        BusLocation.objects.update_or_create(
            journey=journey,
            defaults={
                "latitude": last_accepted["latitude"],
                "longitude": last_accepted["longitude"],
                "accuracy": last_accepted.get("accuracy"),
                "speed": last_accepted.get("speed"),
                "heading": last_accepted.get("heading"),
                "recorded_at": last_accepted["recorded_at"],
            },
        )

    journey.arrival_streak, journey.arrival_last_at = state.arrival_streak, state.arrival_last_at
    journey.departure_streak, journey.departure_last_at = state.departure_streak, state.departure_last_at
    journey.save(
        update_fields=["last_sample_at", "arrival_streak", "arrival_last_at", "departure_streak", "departure_last_at"]
    )
    return summary
