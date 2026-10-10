from django.db import transaction
from django.db.models import ProtectedError
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from notifications.models import Event
from notifications.services import emit_event
from users.permissions import IsAdmin, IsDriverOrAdmin

from .models import Bus, BusList, BusListEntry, BusRoute, City, RouteFavorite, Stop
from .serializers import (
    BusListEntrySerializer,
    BusListSerializer,
    BusRouteSerializer,
    BusSerializer,
    CitySerializer,
    StopSerializer,
)


class AdminWriteViewSet(ModelViewSet):
    """Leitura para qualquer usuário logado; escrita só para admin."""

    def get_permissions(self):
        if self.request.method in ("POST", "PUT", "PATCH", "DELETE"):
            return [IsAdmin()]
        return [IsAuthenticated()]


class ConflictError(APIException):
    status_code = 409
    default_detail = "Operação não permitida no estado atual."
    default_code = "conflict"


class CityViewSet(AdminWriteViewSet):
    queryset = City.objects.all()
    serializer_class = CitySerializer

    def perform_destroy(self, instance):
        try:
            instance.delete()
        except ProtectedError:
            raise ConflictError("Não é possível excluir: existem rotas cadastradas nesta cidade.")


class BusViewSet(AdminWriteViewSet):
    queryset = Bus.objects.all()
    serializer_class = BusSerializer


class BusRouteViewSet(AdminWriteViewSet):
    """
    /api/routes/?city=<id>&shift=MORNING&operating_status=ACTIVE
    POST /api/routes/<id>/suspend/  {"note": "..."}   (admin)
    POST /api/routes/<id>/resume/   {"note": "..."}   (admin)
    POST /api/routes/<id>/favorite/ | DELETE ...      (qualquer usuário)
    POST /api/routes/<id>/stops/reorder/ {"order": [stop_id, ...]}  (admin)
    """

    serializer_class = BusRouteSerializer
    pagination_class = None
    TRACKED_FIELDS = ("shift", "city_id", "bus_id", "departure_time_city", "departure_time_ifrn")

    def get_queryset(self):
        qs = BusRoute.objects.select_related("city", "bus").prefetch_related("stops")
        p = self.request.query_params
        for key in ("city", "shift", "operating_status"):
            if p.get(key):
                qs = qs.filter(**{key: p[key]})
        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        if self.request.user.is_authenticated:
            ctx["favorite_route_ids"] = set(
                RouteFavorite.objects.filter(user=self.request.user).values_list("route_id", flat=True)
            )
        return ctx

    def get_permissions(self):
        if self.action in ("favorite",):
            return [IsAuthenticated()]
        if self.action in ("suspend", "resume", "reorder_stops"):
            return [IsAdmin()]
        return super().get_permissions()

    @transaction.atomic
    def perform_update(self, serializer):
        before = {f: getattr(serializer.instance, f) for f in self.TRACKED_FIELDS}
        route = serializer.save()
        changed = [f for f in self.TRACKED_FIELDS if getattr(route, f) != before[f]]
        if changed:  # RouteUpdated: alteração de rota/horário
            emit_event(
                Event.Type.ROUTE_UPDATED,
                title=f"Rota atualizada: {route.display_name}",
                message="Houve alteração de horário ou de dados da rota. Confira os detalhes.",
                route=route,
                actor=self.request.user,
                level=Event.Level.IMPORTANT,
                payload={"changed": changed},
            )

    def _set_operating(self, request, pk, new_status, title, level):
        route = self.get_object()
        if route.operating_status == new_status:
            return Response({"detail": "A rota já está nesse estado."}, status=status.HTTP_409_CONFLICT)
        route.operating_status = new_status
        route.save(update_fields=["operating_status"])
        emit_event(
            Event.Type.OPERATING_CHANGED,
            title=f"{title}: {route.display_name}",
            message=request.data.get("note", ""),
            route=route,
            actor=request.user,
            level=level,
        )
        return Response(self.get_serializer(route).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def suspend(self, request, pk=None):
        return self._set_operating(request, pk, BusRoute.OperatingStatus.SUSPENDED, "Rota suspensa", Event.Level.URGENT)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def resume(self, request, pk=None):
        return self._set_operating(request, pk, BusRoute.OperatingStatus.ACTIVE, "Rota retomada", Event.Level.IMPORTANT)

    @action(detail=True, methods=["post", "delete"])
    def favorite(self, request, pk=None):
        route = self.get_object()
        if request.method == "POST":
            RouteFavorite.objects.get_or_create(user=request.user, route=route)
        else:
            RouteFavorite.objects.filter(user=request.user, route=route).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="stops/reorder")
    @transaction.atomic
    def reorder_stops(self, request, pk=None):
        route = self.get_object()
        ids = request.data.get("order")
        current = set(route.stops.values_list("id", flat=True))
        if not isinstance(ids, list) or set(ids) != current or len(ids) != len(current):
            return Response(
                {"order": "Envie a lista COMPLETA de IDs de paradas da rota, sem repetir."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # duas fases por causa da constraint unique(route, order)
        for i, sid in enumerate(ids):
            Stop.objects.filter(pk=sid).update(order=1000 + i)
        for i, sid in enumerate(ids, start=1):
            Stop.objects.filter(pk=sid).update(order=i)
        return Response(StopSerializer(Stop.objects.filter(route=route).order_by("order"), many=True).data)


class StopViewSet(AdminWriteViewSet):
    """/api/stops/?route=<id>  (leitura: logado; escrita: admin)"""

    serializer_class = StopSerializer
    pagination_class = None

    def get_queryset(self):
        qs = Stop.objects.select_related("route")
        if self.request.query_params.get("route"):
            qs = qs.filter(route_id=self.request.query_params["route"])
        return qs


class BusListViewSet(ModelViewSet):
    """
    Listas de embarque por rota/dia.
    POST   /api/bus-lists/<id>/join/    {"stay": false}   (aluno entra / atualiza)
    DELETE /api/bus-lists/<id>/leave/                      (aluno sai)
    GET    /api/bus-lists/<id>/entries/                    (motorista da rota ou admin)
    GET    /api/bus-lists/mine/                            (listas em que o aluno está)
    """

    serializer_class = BusListSerializer
    pagination_class = None

    def get_queryset(self):
        qs = BusList.objects.select_related("bus_route__city", "bus_route__bus")
        user = self.request.user
        if user.is_driver:  # motorista só enxerga as listas das próprias rotas
            qs = qs.filter(bus_route__bus__driver=user)
        p = self.request.query_params
        if p.get("route"):
            qs = qs.filter(bus_route_id=p["route"])
        if p.get("date"):
            qs = qs.filter(date=p["date"])
        return qs

    def get_permissions(self):
        if self.action in ("join", "leave", "mine"):
            return [IsAuthenticated()]
        if self.request.method in ("POST", "PUT", "PATCH"):
            return [IsDriverOrAdmin()]
        if self.request.method == "DELETE":
            return [IsAdmin()]
        return [IsAuthenticated()]

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def join(self, request, pk=None):
        bus_list = self.get_object()
        if not bus_list.bus_route.is_operating:
            return Response({"detail": "Esta rota está suspensa."}, status=status.HTTP_409_CONFLICT)
        stay = bool(request.data.get("stay", False))
        entry, created = BusListEntry.objects.update_or_create(
            bus_list=bus_list, user=request.user, defaults={"stay": stay}
        )
        return Response(
            BusListEntrySerializer(entry).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )

    @action(detail=True, methods=["delete"])
    def leave(self, request, pk=None):
        bus_list = self.get_object()
        BusListEntry.objects.filter(bus_list=bus_list, user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"])
    def entries(self, request, pk=None):
        bus_list = self.get_object()
        if not request.user.is_fluxo_admin and not (
            request.user.is_driver and bus_list.bus_route.bus_id and bus_list.bus_route.bus.driver_id == request.user.id
        ):
            raise PermissionDenied("Apenas o motorista da rota ou admins veem os passageiros.")
        qs = bus_list.entries.select_related("user").order_by("created_at")
        return Response(BusListEntrySerializer(qs, many=True).data)

    @action(detail=False, methods=["get"])
    def mine(self, request):
        qs = self.get_queryset().filter(entries__user=request.user)
        return Response(self.get_serializer(qs, many=True).data)
