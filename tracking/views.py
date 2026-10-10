from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from buses.models import BusRoute
from users.permissions import IsDriverOrAdmin

from . import services
from .models import Journey
from .serializers import (
    DelaySerializer,
    JourneySerializer,
    LocationBatchSerializer,
    ReasonSerializer,
    StartJourneySerializer,
)

STALE_AFTER_S = 60  # sem posição nova há 1 min => o app pode mostrar "sinal perdido"


class JourneyViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """
    GET  /api/journeys/?route=&status=&active=1      (qualquer usuário logado)
    POST /api/journeys/                {route}       (motorista da rota ou admin) => inicia
    POST /api/journeys/<id>/location/  amostra única ou {samples:[...], replay:true}
    POST /api/journeys/<id>/stops/<stop_id>/reach/   confirma parada manualmente (próxima da ordem)
    POST /api/journeys/<id>/delay/     {minutes, note}
    POST /api/journeys/<id>/cancel/    {reason}
    POST /api/journeys/<id>/finish/
    """

    serializer_class = JourneySerializer
    pagination_class = None

    def get_queryset(self):
        qs = Journey.objects.select_related("route__city", "route__bus", "location").prefetch_related("progress__stop")
        p = self.request.query_params
        if p.get("route"):
            qs = qs.filter(route_id=p["route"])
        if p.get("status"):
            qs = qs.filter(status=p["status"])
        if p.get("active") in ("1", "true"):
            qs = qs.filter(status=Journey.Status.IN_PROGRESS)
        return qs

    def list(self, request, *args, **kwargs):
        return Response(self.get_serializer(self.get_queryset()[:100], many=True).data)

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return super().get_permissions()
        return [IsDriverOrAdmin()]

    def _fresh(self, pk):
        return self.get_serializer(self.get_queryset().get(pk=pk)).data

    def create(self, request):
        ser = StartJourneySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        journey = services.start_journey(request.user, ser.validated_data["route"])
        return Response(self._fresh(journey.pk), status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def location(self, request, pk=None):
        journey = self.get_object()
        ser = LocationBatchSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        summary = services.ingest_samples(
            request.user, journey, ser.validated_data["samples"], replay=ser.validated_data["replay"]
        )
        return Response(summary)

    @action(detail=True, methods=["post"], url_path=r"stops/(?P<stop_id>\d+)/reach")
    def reach(self, request, pk=None, stop_id=None):
        journey = self.get_object()
        services.reach_stop_manually(request.user, journey, int(stop_id))
        return Response(self._fresh(journey.pk))

    @action(detail=True, methods=["post"])
    def delay(self, request, pk=None):
        journey = self.get_object()
        ser = DelaySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        services.report_delay(request.user, journey, ser.validated_data["minutes"], ser.validated_data["note"])
        return Response(self._fresh(journey.pk))

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        journey = self.get_object()
        ser = ReasonSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        services.cancel_journey(request.user, journey, ser.validated_data["reason"])
        return Response(self._fresh(journey.pk))

    @action(detail=True, methods=["post"])
    def finish(self, request, pk=None):
        journey = self.get_object()
        services.finish_journey(request.user, journey)
        return Response(self._fresh(journey.pk))


class RouteLiveView(APIView):
    """
    GET /api/routes/<id>/live/  -> tudo que a tela de mapa/timeline do aluno precisa em UMA chamada.
    Fazer polling aqui a cada ~5 s.
    """

    def get(self, request, pk):
        route = get_object_or_404(BusRoute.objects.select_related("city", "bus"), pk=pk)
        journey = (
            Journey.objects.filter(route=route, status=Journey.Status.IN_PROGRESS)
            .select_related("location")
            .prefetch_related("progress")
            .first()
        )
        done = {p.stop_id: p for p in journey.progress.all()} if journey else {}
        current_set = False
        stops = []
        for s in route.stops.all():
            if s.pk in done:
                state = "done"
            elif journey and not current_set:
                state, current_set = "current", True
            else:
                state = "upcoming"
            p = done.get(s.pk)
            stops.append(
                {
                    "id": s.pk, "order": s.order, "name": s.name,
                    "latitude": s.latitude, "longitude": s.longitude, "coord_status": s.coord_status,
                    "state": state,
                    "reached_at": p.reached_at if p else None,
                    "departed_at": p.departed_at if p else None,
                }
            )  # fmt: skip

        loc = getattr(journey, "location", None) if journey else None
        stale = bool(loc and (timezone.now() - loc.updated_at).total_seconds() > STALE_AFTER_S)
        return Response(
            {
                "route": {
                    "id": route.pk,
                    "code": route.code,
                    "name": route.display_name,
                    "operating_status": route.operating_status,
                },
                "journey": (
                    {
                        "id": journey.pk,
                        "status": journey.status,
                        "started_at": journey.started_at,
                        "delay_minutes": journey.delay_minutes,
                        "delay_note": journey.delay_note,
                    }
                    if journey
                    else None
                ),
                "location": (
                    {
                        "latitude": loc.latitude, "longitude": loc.longitude, "heading": loc.heading,
                        "speed": loc.speed, "recorded_at": loc.recorded_at, "stale": stale,
                    }
                    if loc
                    else None
                ),  # fmt: skip
                "stops": stops,
                "server_time": timezone.now(),
            }
        )
