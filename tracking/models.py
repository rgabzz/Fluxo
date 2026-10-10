from django.conf import settings
from django.db import models
from django.db.models import Q


class Journey(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = "IN_PROGRESS", "Em andamento"
        FINISHED = "FINISHED", "Finalizada"
        CANCELED = "CANCELED", "Cancelada"

    route = models.ForeignKey("buses.BusRoute", on_delete=models.CASCADE, related_name="journeys")
    driver = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="journeys"
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.IN_PROGRESS, db_index=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    delay_minutes = models.PositiveSmallIntegerField(default=0)
    delay_note = models.CharField(max_length=300, blank=True)
    cancel_reason = models.CharField(max_length=300, blank=True)

    # Estado interno da detecção automática (ver tracking/progress.py)
    last_sample_at = models.DateTimeField(null=True, blank=True)
    arrival_streak = models.PositiveSmallIntegerField(default=0)
    arrival_last_at = models.DateTimeField(null=True, blank=True)
    departure_streak = models.PositiveSmallIntegerField(default=0)
    departure_last_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]
        constraints = [
            # no máximo uma jornada em andamento por rota e por motorista
            models.UniqueConstraint(
                fields=["route"], condition=Q(status="IN_PROGRESS"), name="one_active_journey_per_route"
            ),
            models.UniqueConstraint(
                fields=["driver"], condition=Q(status="IN_PROGRESS"), name="one_active_journey_per_driver"
            ),
        ]

    @property
    def is_active(self) -> bool:
        return self.status == self.Status.IN_PROGRESS

    def __str__(self):
        return f"Jornada #{self.pk} - {self.route} ({self.status})"


class JourneyStopProgress(models.Model):
    class Source(models.TextChoices):
        AUTO = "AUTO", "GPS"
        MANUAL = "MANUAL", "Motorista"

    journey = models.ForeignKey(Journey, on_delete=models.CASCADE, related_name="progress")
    stop = models.ForeignKey("buses.Stop", on_delete=models.CASCADE, related_name="+")
    reached_at = models.DateTimeField()
    departed_at = models.DateTimeField(null=True, blank=True)
    source = models.CharField(max_length=6, choices=Source.choices, default=Source.AUTO)

    class Meta:
        ordering = ["stop__order"]
        constraints = [
            models.UniqueConstraint(fields=["journey", "stop"], name="unique_progress_per_stop_in_journey")
        ]


class BusLocation(models.Model):
    """Última posição conhecida do ônibus (uma linha por jornada, sobrescrita a cada amostra)."""

    journey = models.OneToOneField(Journey, on_delete=models.CASCADE, related_name="location")
    latitude = models.FloatField()
    longitude = models.FloatField()
    accuracy = models.FloatField(null=True, blank=True)
    speed = models.FloatField(null=True, blank=True)
    heading = models.FloatField(null=True, blank=True)
    recorded_at = models.DateTimeField()
    updated_at = models.DateTimeField(auto_now=True)
