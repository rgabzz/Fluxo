from rest_framework import serializers

from .models import Event, PushToken


class NotificationSerializer(serializers.ModelSerializer):
    read = serializers.BooleanField(source="is_read", read_only=True)
    route_name = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = ["id", "type", "title", "message", "level", "route", "route_name", "journey_id", "payload", "created_at", "read"]

    def get_route_name(self, obj):
        return obj.route.display_name if obj.route_id else None


class NoticeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = ["id", "title", "message", "level", "route", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_title(self, value):
        if not value.strip():
            raise serializers.ValidationError("Informe um título.")
        return value.strip()


class PushTokenSerializer(serializers.ModelSerializer):
    # Declarado à mão para NÃO herdar o validador "unique": o app reenvia o mesmo token a cada abertura.
    token = serializers.CharField(max_length=255)

    class Meta:
        model = PushToken
        fields = ["token", "platform"]

    def validate_token(self, value):
        if not value.startswith(("ExponentPushToken[", "ExpoPushToken[")):
            raise serializers.ValidationError("Token Expo inválido.")
        return value
