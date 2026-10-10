from django.conf import settings
from django.db import models


class Event(models.Model):
    """
    Fonte única de eventos do sistema (mesma lista do relatório da V2, seção 10).
    Sino e tela de avisos leem daqui, com IDs estáveis.
    """

    class Type(models.TextChoices):
        NOTICE = "NOTICE", "Aviso administrativo"
        JOURNEY_STARTED = "JOURNEY_STARTED", "Jornada iniciada"
        DELAY_REPORTED = "DELAY_REPORTED", "Atraso informado"
        STATUS_CHANGED = "STATUS_CHANGED", "Jornada cancelada"
        JOURNEY_FINISHED = "JOURNEY_FINISHED", "Jornada finalizada"
        ROUTE_UPDATED = "ROUTE_UPDATED", "Rota/horário alterado"
        OPERATING_CHANGED = "OPERATING_CHANGED", "Suspensão/retomada"
        STOP_REACHED = "STOP_REACHED", "Parada alcançada"

    class Level(models.TextChoices):
        INFO = "INFO", "Informativo"
        IMPORTANT = "IMPORTANT", "Importante"
        URGENT = "URGENT", "Urgente"

    type = models.CharField(max_length=20, choices=Type.choices)
    # route vazio => aviso geral (vai para todos).
    route = models.ForeignKey(
        "buses.BusRoute", on_delete=models.SET_NULL, null=True, blank=True, related_name="events"
    )
    journey_id = models.PositiveBigIntegerField(null=True, blank=True)  # sem FK: evita dependência circular
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    title = models.CharField(max_length=140)
    message = models.TextField(blank=True)
    level = models.CharField(max_length=10, choices=Level.choices, default=Level.INFO)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-id"]
        indexes = [models.Index(fields=["route", "-id"])]

    def __str__(self):
        return f"[{self.type}] {self.title}"


class EventRead(models.Model):
    """Leitura separada por usuário: badge conta só os não lidos, lidos ficam no histórico."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="event_reads")
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="reads")
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "event"], name="unique_read_per_user_event")]


class PushToken(models.Model):
    class Platform(models.TextChoices):
        ANDROID = "android", "Android"
        IOS = "ios", "iOS"
        WEB = "web", "Web"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="push_tokens")
    token = models.CharField(max_length=255, unique=True)
    platform = models.CharField(max_length=10, choices=Platform.choices, default=Platform.ANDROID)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
