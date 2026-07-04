from rest_framework import serializers
from .models import Bus,City,BusRoute,BusList

class BusSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bus
        fields = '__all__'

class CitySerializer(serializers.ModelSerializer):
    class Meta:
        model = City
        fields = '__all__'

class BusRouteSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusRoute
        fields = '__all__'    

class BusListSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusList
        fields = "__all__"    