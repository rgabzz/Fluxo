from django.utils import timezone
from rest_framework import serializers

from buses.models import BusRoute

from .models import BusLocation, Journey, JourneyStopProgress
from .services import next_stop


class LocationSampleSerializer(serializers.Serializer):
    latitude = serializers.FloatField(min_value=-90, max_value=90)
    longitude = serializers.FloatField(min_value=-180, max_value=180)
    accuracy = serializers.FloatField(required=False, allow_null=True, min_value=0)
    speed = serializers.FloatField(required=False, allow_null=True)
    heading = serializers.FloatField(required=False, allow_null=True)
    recorded_at = serializers.DateTimeField(default=timezone.now)


class LocationBatchSerializer(serializers.Serializer):
    """
    Aceita UMA amostra (campos soltos) ou várias em `samples` (fila offline, com replay=true).
    """

    samples = LocationSampleSerializer(many=True, required=False)
    replay = serializers.BooleanField(required=False, default=False)

    def to_internal_value(self, data):
        from django.conf import settings

        data = data.copy() if hasattr(data, "copy") else dict(data)
        if "samples" not in data:  # modo amostra única
            single = LocationSampleSerializer(data=data)
            single.is_valid(raise_exception=True)
            return {"samples": [single.validated_data], "replay": False}
        out = super().to_internal_value(data)
        limit = settings.FLUXO_TRACKING["MAX_BATCH_SIZE"]
        if not out["samples"] or len(out["samples"]) > limit:
            raise serializers.ValidationError({"samples": f"Envie de 1 a {limit} amostras."})
        return out


class DelaySerializer(serializers.Serializer):
    minutes = serializers.IntegerField(min_value=1, max_value=600)
    note = serializers.CharField(required=False, allow_blank=True, max_length=300, default="")


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=300, default="")


class StartJourneySerializer(serializers.Serializer):
    route = serializers.PrimaryKeyRelatedField(queryset=BusRoute.objects.all())


class LocationOutSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusLocation
        fields = ["latitude", "longitude", "accuracy", "speed", "heading", "recorded_at", "updated_at"]


class ProgressOutSerializer(serializers.ModelSerializer):
    stop_name = serializers.CharField(source="stop.name", read_only=True)
    order = serializers.IntegerField(source="stop.order", read_only=True)

    class Meta:
        model = JourneyStopProgress
        fields = ["stop", "stop_name", "order", "reached_at", "departed_at", "source"]


class JourneySerializer(serializers.ModelSerializer):
    route_name = serializers.CharField(source="route.display_name", read_only=True)
    location = serializers.SerializerMethodField()
    progress = ProgressOutSerializer(many=True, read_only=True)
    next_stop_id = serializers.SerializerMethodField()
    stops_total = serializers.SerializerMethodField()

    class Meta:
        model = Journey
        fields = [
            "id", "route", "route_name", "driver", "status", "started_at", "finished_at",
            "delay_minutes", "delay_note", "cancel_reason",
            "location", "progress", "next_stop_id", "stops_total",
        ]  # fmt: skip

    def get_location(self, obj):
        loc = getattr(obj, "location", None)
        return LocationOutSerializer(loc).data if loc else None

    def get_next_stop_id(self, obj):
        nxt = next_stop(obj) if obj.is_active else None
        return nxt.pk if nxt else None

    def get_stops_total(self, obj):
        return obj.route.stops.count()
