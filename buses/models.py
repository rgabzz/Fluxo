from datetime import date, timedelta

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q


def tomorrow():
    return date.today() + timedelta(days=1)


class City(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name_plural = "cities"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Bus(models.Model):
    name = models.CharField(max_length=100)  # ex: "IFRN Apodi 01"
    plate = models.CharField(max_length=10, unique=True)
    capacity = models.IntegerField()
    driver = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={"role": "DRIVER"},
    )
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class BusRoute(models.Model):
    """Rota do Fluxo: cidade + turno. Ex.: 'Itaú - Manhã'."""

    class Shift(models.TextChoices):
        MORNING = "MORNING", "Manhã"
        AFTERNOON = "AFTERNOON", "Tarde"
        NIGHT = "NIGHT", "Noite"

    class OperatingStatus(models.TextChoices):
        ACTIVE = "ACTIVE", "Em operação"
        SUSPENDED = "SUSPENDED", "Suspensa"

    # `code` guarda o ID antigo do app (ex.: "itau-manha") para não quebrar dados existentes.
    code = models.SlugField(max_length=60, unique=True, null=True, blank=True)

    # Ônibus pode ficar em aberto enquanto a rota é apenas cadastrada no catálogo.
    bus = models.ForeignKey(Bus, on_delete=models.SET_NULL, null=True, blank=True, related_name="routes")
    city = models.ForeignKey(City, on_delete=models.PROTECT, related_name="routes")
    shift = models.CharField(max_length=10, choices=Shift.choices, default=Shift.MORNING)
    operating_status = models.CharField(
        max_length=10, choices=OperatingStatus.choices, default=OperatingStatus.ACTIVE
    )

    departure_time_city = models.TimeField(null=True, blank=True)  # 05:40
    departure_time_ifrn = models.TimeField(null=True, blank=True)  # 12:00

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["city__name", "shift"]

    @property
    def display_name(self) -> str:
        return f"{self.city.name} - {self.get_shift_display()}"

    @property
    def is_operating(self) -> bool:
        return self.operating_status == self.OperatingStatus.ACTIVE

    def __str__(self):
        return self.display_name


class Stop(models.Model):
    """
    Parada de uma rota, em ordem operacional.

    Regra do relatório da V2: ponto sem coordenada confiável NÃO tem lat/lng inventada.
    PENDING => sem coordenadas (não gera pin/linha/avanço automático).
    CONFIRMED / DEMO => coordenadas obrigatórias.
    """

    class CoordStatus(models.TextChoices):
        CONFIRMED = "CONFIRMED", "Confirmada"
        DEMO = "DEMO", "Demonstrativa"
        PENDING = "PENDING", "Pendente"

    route = models.ForeignKey(BusRoute, on_delete=models.CASCADE, related_name="stops")
    order = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=120)
    latitude = models.FloatField(
        null=True, blank=True, validators=[MinValueValidator(-90), MaxValueValidator(90)]
    )
    longitude = models.FloatField(
        null=True, blank=True, validators=[MinValueValidator(-180), MaxValueValidator(180)]
    )
    coord_status = models.CharField(max_length=10, choices=CoordStatus.choices, default=CoordStatus.PENDING)

    class Meta:
        ordering = ["route_id", "order"]
        constraints = [
            models.UniqueConstraint(fields=["route", "order"], name="unique_stop_order_per_route"),
            models.CheckConstraint(
                name="stop_coords_match_status",
                condition=(
                    Q(coord_status="PENDING", latitude__isnull=True, longitude__isnull=True)
                    | (
                        ~Q(coord_status="PENDING")
                        & Q(latitude__isnull=False, longitude__isnull=False)
                    )
                ),
            ),
        ]

    @property
    def has_coordinates(self) -> bool:
        return self.latitude is not None and self.longitude is not None

    def __str__(self):
        return f"{self.route.display_name} #{self.order} {self.name}"


class RouteFavorite(models.Model):
    user = models.ForeignKey("users.User", on_delete=models.CASCADE, related_name="favorite_routes")
    route = models.ForeignKey(BusRoute, on_delete=models.CASCADE, related_name="favorited_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "route"], name="unique_favorite_per_user_route")
        ]


class BusList(models.Model):
    bus_route = models.ForeignKey(BusRoute, on_delete=models.CASCADE)
    date = models.DateField(default=tomorrow)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]


class BusListEntry(models.Model):
    bus_list = models.ForeignKey(BusList, on_delete=models.CASCADE, related_name="entries")
    user = models.ForeignKey("users.User", on_delete=models.CASCADE)
    stay = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:  # impede duplicatas
        constraints = [
            models.UniqueConstraint(fields=["bus_list", "user"], name="unique_user_per_bus_list")
        ]
