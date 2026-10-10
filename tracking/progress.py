"""
Detecção de chegada/saída de paradas por GPS. Funções PURAS (sem banco), fáceis de testar.

Regras (relatório V2, seção 9):
  chegada  = 3 amostras seguidas a <= 75 m da próxima parada
  saída    = 2 amostras seguidas a > 125 m da parada em que estava
  ignora   = amostras com precisão pior que 40 m
  sequência= amostras consecutivas com no máximo 20 s entre si
"""
from dataclasses import dataclass, replace
from datetime import datetime
from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_M = 6_371_000


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = radians(lat1), radians(lat2)
    dphi, dlmb = p2 - p1, radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_M * asin(sqrt(a))


@dataclass(frozen=True)
class Sample:
    latitude: float
    longitude: float
    recorded_at: datetime
    accuracy: float | None = None


@dataclass(frozen=True)
class TrackState:
    arrival_streak: int = 0
    arrival_last_at: datetime | None = None
    departure_streak: int = 0
    departure_last_at: datetime | None = None


@dataclass(frozen=True)
class Result:
    state: TrackState
    arrived: bool = False
    departed: bool = False
    ignored: bool = False


def _advance_streak(streak: int, last_at, now, max_gap_s: float) -> int:
    """Soma 1 se a amostra continua a sequência; senão recomeça em 1."""
    if streak > 0 and last_at is not None and 0 <= (now - last_at).total_seconds() <= max_gap_s:
        return streak + 1
    return 1


def evaluate(
    sample: Sample,
    state: TrackState,
    next_stop: tuple[float, float] | None,
    departing_stop: tuple[float, float] | None,
    cfg: dict,
) -> Result:
    """
    next_stop      = (lat, lng) da próxima parada ainda não alcançada (None se sem coordenada/sem próxima)
    departing_stop = (lat, lng) da última parada alcançada que ainda não foi marcada como "saiu"
    """
    if sample.accuracy is not None and sample.accuracy > cfg["MAX_ACCURACY_M"]:
        return Result(state=state, ignored=True)

    gap = cfg["MAX_SEQUENCE_GAP_S"]
    now = sample.recorded_at
    new = state
    arrived = departed = False

    # ---- chegada
    if next_stop is not None:
        d = haversine_m(sample.latitude, sample.longitude, *next_stop)
        if d <= cfg["ARRIVAL_RADIUS_M"]:
            streak = _advance_streak(new.arrival_streak, new.arrival_last_at, now, gap)
            if streak >= cfg["ARRIVAL_SAMPLES"]:
                arrived = True
                new = replace(new, arrival_streak=0, arrival_last_at=None)
            else:
                new = replace(new, arrival_streak=streak, arrival_last_at=now)
        else:
            new = replace(new, arrival_streak=0, arrival_last_at=None)
    else:
        new = replace(new, arrival_streak=0, arrival_last_at=None)

    # ---- saída
    if departing_stop is not None:
        d = haversine_m(sample.latitude, sample.longitude, *departing_stop)
        if d > cfg["DEPARTURE_RADIUS_M"]:
            streak = _advance_streak(new.departure_streak, new.departure_last_at, now, gap)
            if streak >= cfg["DEPARTURE_SAMPLES"]:
                departed = True
                new = replace(new, departure_streak=0, departure_last_at=None)
            else:
                new = replace(new, departure_streak=streak, departure_last_at=now)
        else:
            new = replace(new, departure_streak=0, departure_last_at=None)
    else:
        new = replace(new, departure_streak=0, departure_last_at=None)

    return Result(state=new, arrived=arrived, departed=departed)
