"""
Dados de TESTE para começar a usar o sistema rapidamente.

    python manage.py seed_teste            # cria/atualiza tudo (idempotente)
    python manage.py seed_teste --reset    # apaga as paradas da rota de teste antes de recriar

O que cria:
  - Usuários: superusuário, motorista e aluno (senha de teste abaixo)
  - Cidade "Itaú" + ônibus de teste + rota "itau-manha" (Itaú - Manhã)
  - 3 paradas COM coordenadas reais (CONFIRMED), na ordem operacional
  - Rota favoritada pelos 3 usuários (para já receberem avisos/sino)

ATENÇÃO: é só para desenvolvimento. Não rode em produção (as senhas são públicas).
"""
from datetime import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from buses.models import Bus, BusRoute, City, Stop
from users.models import User

# ---------------------------------------------------------------------------
# Dados de teste (edite à vontade)
# ---------------------------------------------------------------------------
TEST_PASSWORD = "fluxo12345"

USERS = [
    # (username, role, first_name, is_superuser)
    ("admin", User.Role.SYSTEM_ADMIN, "Super", True),
    ("motorista", User.Role.DRIVER, "Motorista", False),
    ("aluno", User.Role.STUDENT, "Aluno", False),
]

CITY_NAME = "Itaú"
ROUTE_CODE = "itau-manha"
BUS = {"name": "IFRN Itaú 01", "plate": "TST0001", "capacity": 40}

STOPS = [
    # (ordem, nome, latitude, longitude)
    (1, "Praça de Esportes", -5.841376977529005, -37.992065094370204),
    (2, "Posto da Entrada", -5.8381174439715195, -37.98758296492921),
    (3, "Loja de Animais", -5.841317933370803, -37.98905971176274),
]


class Command(BaseCommand):
    help = "Cria usuários de teste, a cidade Itaú, uma rota e 3 paradas com coordenadas (somente dev)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Apaga as paradas existentes da rota de teste antes de recriá-las.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Permite rodar com DEBUG=False (NÃO use em produção).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "DEBUG=False: este seed cria usuários com senha pública. Use --force se tiver certeza."
            )

        users = self._create_users()
        route = self._create_route(users["motorista"])
        self._create_stops(route, reset=options["reset"])
        self._favorite(route, users.values())

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Seed de teste concluído."))
        self.stdout.write(f"  Cidade: {CITY_NAME} | Rota: {route.display_name} (code={route.code}, id={route.pk})")
        for order, name, lat, lng in STOPS:
            self.stdout.write(f"  Parada {order}: {name} ({lat:.6f}, {lng:.6f})")
        self.stdout.write("")
        self.stdout.write("  Logins (senha de todos: %s):" % TEST_PASSWORD)
        for username, role, _, is_super in USERS:
            self.stdout.write(f"    {username:<10} {role}{' (superuser)' if is_super else ''}")

    # ------------------------------------------------------------------
    def _create_users(self):
        created = {}
        for username, role, first_name, is_super in USERS:
            user, new = User.objects.get_or_create(
                username=username,
                defaults={"role": role, "first_name": first_name, "email": f"{username}@teste.local"},
            )
            # Garante papel/permissões e senha conhecida mesmo se o usuário já existia.
            user.role = role
            user.is_superuser = is_super
            user.is_staff = is_super
            user.is_active = True
            user.set_password(TEST_PASSWORD)
            user.save()
            created[username] = user
            self.stdout.write(f"{'+' if new else '~'} usuário {username} ({role})")
        return created

    def _create_route(self, driver):
        city, _ = City.objects.get_or_create(name=CITY_NAME)
        bus, _ = Bus.objects.get_or_create(plate=BUS["plate"], defaults={**BUS, "driver": driver})
        if bus.driver_id != driver.pk:
            bus.driver = driver
            bus.save(update_fields=["driver"])

        route, new = BusRoute.objects.get_or_create(
            code=ROUTE_CODE,
            defaults={
                "city": city,
                "shift": BusRoute.Shift.MORNING,
                "bus": bus,
                "departure_time_city": time(5, 40),
                "departure_time_ifrn": time(12, 0),
            },
        )
        if not new and route.bus_id != bus.pk:
            route.bus = bus
            route.save(update_fields=["bus"])
        self.stdout.write(f"{'+' if new else '~'} rota {route.display_name}")
        return route

    def _create_stops(self, route, reset=False):
        wanted_orders = [order for order, *_ in STOPS]
        # O seed_fluxo cria paradas PENDING (ex.: "Palmeira") nessa mesma rota; removemos o que
        # sobra para a rota ficar exatamente com as 3 paradas de teste.
        qs = Stop.objects.filter(route=route)
        if not reset:
            qs = qs.exclude(order__in=wanted_orders)
        removed = qs.delete()[0]
        if removed:
            self.stdout.write(f"- {removed} parada(s) antiga(s) removida(s)")

        for order, name, lat, lng in STOPS:
            Stop.objects.update_or_create(
                route=route,
                order=order,
                defaults={
                    "name": name,
                    "latitude": lat,
                    "longitude": lng,
                    "coord_status": Stop.CoordStatus.CONFIRMED,
                },
            )
            self.stdout.write(f"+ parada {order}: {name}")

    def _favorite(self, route, users):
        from buses.models import RouteFavorite

        for user in users:
            RouteFavorite.objects.get_or_create(user=user, route=route)
