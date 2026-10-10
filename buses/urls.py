from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .viewset import BusListViewSet, BusRouteViewSet, BusViewSet, CityViewSet, StopViewSet

router = DefaultRouter()
router.register(r"buses", BusViewSet)
router.register(r"cities", CityViewSet)
router.register(r"routes", BusRouteViewSet, basename="routes")
router.register(r"stops", StopViewSet, basename="stops")
router.register(r"bus-lists", BusListViewSet, basename="bus-lists")

urlpatterns = [path("", include(router.urls))]
