"""
Carrega o catálogo de rotas/paradas da V2 (relatório, seção 7).

    python manage.py seed_fluxo

É idempotente: pode rodar várias vezes. NÃO inventa coordenadas: todas as paradas entram como
PENDING (sem lat/lng). Preencha as coordenadas reais pelo Django Admin (Rotas > Paradas) ou por
PATCH /api/stops/<id>/ com coord_status=CONFIRMED.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from buses.models import BusRoute, City, Stop

S = BusRoute.Shift
CATALOG = [
    # (code, cidade, turno, [paradas em ordem operacional])
    ("itau-manha", "Itaú", S.MORNING, ["Praça de Esportes", "Posto da Entrada", "Palmeira", "Loja de Animais"]),
    ("severiano-manha", "Severiano Melo", S.MORNING, ["Rádio", "Contorno", "Malhada", "São Dimas", "Boa Vista", "Melancias"]),
    ("severiano-tarde", "Severiano Melo", S.AFTERNOON, ["Rádio", "Contorno", "Malhada", "São Dimas", "Boa Vista", "Melancias", "Bico Torto"]),
    ("rodolfo-fernandes-manha", "Rodolfo Fernandes", S.MORNING, ["Prefeitura", "Entrada"]),
    ("rodolfo-fernandes-noite", "Rodolfo Fernandes", S.NIGHT, ["Prefeitura", "Entrada"]),
    ("caraubas-manha", "Caraúbas", S.MORNING, ["Farmácia", "Rede 10", "Honda", "Rodoviária", "IFRN Campus Apodi"]),
    ("felipe-guerra-manha", "Felipe Guerra", S.MORNING, []),  # ainda sem paradas cadastradas
]  # fmt: skip


class Command(BaseCommand):
    help = "Cria cidades, rotas e paradas do catálogo da V2 (sem coordenadas inventadas)."

    @transaction.atomic
    def handle(self, *args, **options):
        created_routes = created_stops = 0
        for code, city_name, shift, stops in CATALOG:
            city, _ = City.objects.get_or_create(name=city_name)
            route, created = BusRoute.objects.get_or_create(code=code, defaults={"city": city, "shift": shift})
            created_routes += created
            for order, name in enumerate(stops, start=1):
                _, c = Stop.objects.get_or_create(
                    route=route, order=order, defaults={"name": name, "coord_status": Stop.CoordStatus.PENDING}
                )
                created_stops += c
        self.stdout.write(self.style.SUCCESS(f"Rotas novas: {created_routes} | paradas novas: {created_stops}"))
        pending = Stop.objects.filter(coord_status=Stop.CoordStatus.PENDING).count()
        self.stdout.write(f"Paradas com coordenada pendente: {pending} (preencher antes do teste em campo)")
