from django.utils.dateparse import parse_datetime
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from users.permissions import IsAdmin

from .models import Event, EventRead, PushToken
from .serializers import NoticeSerializer, NotificationSerializer, PushTokenSerializer
from .services import annotate_read, emit_event, visible_events_for


class NotificationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """
    Sino + tela de avisos do usuário logado.

    GET  /api/notifications/?route=<id>&unread=1&after_id=<id>&since=<iso>&limit=50
    GET  /api/notifications/unread-count/
    POST /api/notifications/<id>/read/
    POST /api/notifications/read-all/
    """

    serializer_class = NotificationSerializer
    pagination_class = None

    def get_queryset(self):
        qs = annotate_read(visible_events_for(self.request.user), self.request.user).select_related("route__city")
        p = self.request.query_params
        if p.get("route"):
            qs = qs.filter(route_id=p["route"])
        if p.get("unread") in ("1", "true"):
            qs = qs.filter(is_read=False)
        if p.get("after_id"):
            qs = qs.filter(id__gt=p["after_id"])
        if p.get("since"):
            since = parse_datetime(p["since"])
            if since:
                qs = qs.filter(created_at__gt=since)
        return qs.order_by("-id")

    def list(self, request, *args, **kwargs):
        try:
            limit = max(1, min(int(request.query_params.get("limit", 50)), 200))
        except ValueError:
            limit = 50
        unread = annotate_read(visible_events_for(request.user), request.user).filter(is_read=False).count()
        data = self.get_serializer(self.get_queryset()[:limit], many=True).data
        return Response({"unread_count": unread, "results": data})

    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        n = annotate_read(visible_events_for(request.user), request.user).filter(is_read=False).count()
        return Response({"unread_count": n})

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        event = self.get_object()  # já respeita a visibilidade do usuário
        EventRead.objects.get_or_create(user=request.user, event=event)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        unread_ids = (
            annotate_read(visible_events_for(request.user), request.user)
            .filter(is_read=False)
            .values_list("id", flat=True)
        )
        EventRead.objects.bulk_create(
            [EventRead(user=request.user, event_id=i) for i in unread_ids], ignore_conflicts=True
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class NoticeViewSet(viewsets.ModelViewSet):
    """Avisos administrativos (somente admin). Criar um aviso gera o evento e o push."""

    permission_classes = [IsAdmin]
    serializer_class = NoticeSerializer
    queryset = Event.objects.filter(type=Event.Type.NOTICE)

    def perform_create(self, serializer):
        d = serializer.validated_data
        serializer.instance = emit_event(
            Event.Type.NOTICE,
            title=d["title"],
            message=d.get("message", ""),
            level=d.get("level", Event.Level.INFO),
            route=d.get("route"),
            actor=self.request.user,
        )


class PushTokenView(APIView):
    """POST registra/atualiza o token do aparelho; DELETE remove (logout)."""

    def post(self, request):
        ser = PushTokenSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        PushToken.objects.update_or_create(
            token=ser.validated_data["token"],
            defaults={"user": request.user, "platform": ser.validated_data.get("platform", "android")},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    def delete(self, request):
        PushToken.objects.filter(user=request.user, token=request.data.get("token", "")).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
