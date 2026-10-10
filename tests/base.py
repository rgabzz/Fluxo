from datetime import timedelta

from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from buses.models import Bus, BusRoute, City, Stop
from users.models import User

# 0.001 grau de latitude ~ 111 m
BASE_LAT, BASE_LNG = -5.6000, -37.8000


def stop_lat(i):
    """Paradas separadas por ~1,1 km ao longo da latitude."""
    return BASE_LAT + 0.01 * i


@override_settings(PUSH_ENABLED=False)
class FluxoTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        mk = User.objects.create_user
        cls.admin = mk("admin", password="x" * 12, role="CITY_ADMIN")
        cls.driver = mk("driver", password="x" * 12, role="DRIVER")
        cls.driver2 = mk("driver2", password="x" * 12, role="DRIVER")
        cls.student = mk("aluno", password="x" * 12, role="STUDENT")
        cls.student2 = mk("aluno2", password="x" * 12, role="STUDENT")

        cls.city = City.objects.create(name="Itaú")
        cls.bus = Bus.objects.create(name="Bus 1", plate="AAA0001", capacity=2, driver=cls.driver)
        cls.route = BusRoute.objects.create(city=cls.city, bus=cls.bus, shift="MORNING", code="itau-manha")
        cls.stops = [
            Stop.objects.create(
                route=cls.route, order=i + 1, name=f"P{i + 1}",
                latitude=stop_lat(i), longitude=BASE_LNG, coord_status="CONFIRMED",
            )
            for i in range(3)
        ]  # fmt: skip

    def login(self, user):
        self.client.force_authenticate(user)

    def sample(self, lat, lng=BASE_LNG, seconds=0, accuracy=10, base=None):
        base = base or timezone.now()
        return {
            "latitude": lat, "longitude": lng, "accuracy": accuracy,
            "recorded_at": (base + timedelta(seconds=seconds)).isoformat(),
        }  # fmt: skip
