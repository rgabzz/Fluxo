from rest_framework import serializers

from .models import Bus, BusList, BusListEntry, BusRoute, City, Stop


class CitySerializer(serializers.ModelSerializer):
    class Meta:
        model = City
        fields = "__all__"


class BusSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bus
        fields = "__all__"


class StopSerializer(serializers.ModelSerializer):
    class Meta:
        model = Stop
        fields = ["id", "route", "order", "name", "latitude", "longitude", "coord_status"]

    def validate(self, attrs):
        # Em PATCH, completa com os valores atuais para validar o conjunto.
        get = lambda k: attrs.get(k, getattr(self.instance, k, None))  # noqa: E731
        status, lat, lng = get("coord_status") or Stop.CoordStatus.PENDING, get("latitude"), get("longitude")
        if status == Stop.CoordStatus.PENDING:
            if lat is not None or lng is not None:
                raise serializers.ValidationError(
                    "Parada com coordenada PENDENTE não pode ter latitude/longitude. "
                    "Marque como CONFIRMED (ou DEMO) ao informar as coordenadas."
                )
        elif lat is None or lng is None:
            raise serializers.ValidationError("Status CONFIRMED/DEMO exige latitude e longitude.")
        return attrs


class BusRouteSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="display_name", read_only=True)
    city_name = serializers.CharField(source="city.name", read_only=True)
    bus_name = serializers.CharField(source="bus.name", read_only=True, default=None)
    driver = serializers.IntegerField(source="bus.driver_id", read_only=True, default=None)
    stops = StopSerializer(many=True, read_only=True)
    is_favorite = serializers.SerializerMethodField()

    class Meta:
        model = BusRoute
        fields = [
            "id", "code", "name", "city", "city_name", "shift", "operating_status",
            "bus", "bus_name", "driver", "departure_time_city", "departure_time_ifrn",
            "stops", "is_favorite", "created_at",
        ]  # fmt: skip
        # suspender/retomar tem endpoint próprio (gera evento); não se altera por PATCH
        read_only_fields = ["operating_status", "created_at"]

    def get_is_favorite(self, obj):
        fav_ids = self.context.get("favorite_route_ids")
        return obj.pk in fav_ids if fav_ids is not None else False


class BusListSerializer(serializers.ModelSerializer):
    route_name = serializers.CharField(source="bus_route.display_name", read_only=True)
    capacity = serializers.IntegerField(source="bus_route.bus.capacity", read_only=True, default=None)
    entries_count = serializers.SerializerMethodField()
    is_full = serializers.SerializerMethodField()
    joined = serializers.SerializerMethodField()

    class Meta:
        model = BusList
        fields = ["id", "bus_route", "route_name", "date", "capacity", "entries_count", "is_full", "joined", "created_at"]
        read_only_fields = ["created_at"]

    def get_entries_count(self, obj):
        return obj.entries.count()

    def get_is_full(self, obj):
        cap = obj.bus_route.bus.capacity if obj.bus_route.bus_id else None
        return bool(cap) and obj.entries.count() >= cap

    def get_joined(self, obj):
        user = self.context["request"].user
        return obj.entries.filter(user=user).exists()

    def validate(self, attrs):
        route = attrs.get("bus_route") or getattr(self.instance, "bus_route", None)
        date = attrs.get("date") or getattr(self.instance, "date", None)
        user = self.context["request"].user
        if route and user.is_driver and not (route.bus_id and route.bus.driver_id == user.id):
            raise serializers.ValidationError({"bus_route": "Você não é o motorista desta rota."})
        if route and date:
            dup = BusList.objects.filter(bus_route=route, date=date)
            if self.instance:
                dup = dup.exclude(pk=self.instance.pk)
            if dup.exists():
                raise serializers.ValidationError("Já existe uma lista para esta rota nesta data.")
        return attrs


class BusListEntrySerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = BusListEntry
        fields = ["id", "user", "username", "full_name", "stay", "created_at"]

    def get_full_name(self, obj):
        return obj.user.get_full_name() or obj.user.username
