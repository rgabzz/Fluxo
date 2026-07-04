from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .viewset import BusViewSet, CityViewSet,BusRouteViewSet

router = DefaultRouter()
router.register(r'buses', BusViewSet)
router.register(r'cities', CityViewSet)
router.register(r'routes', BusRouteViewSet)

urlpatterns = [
    path('', include(router.urls)),
]