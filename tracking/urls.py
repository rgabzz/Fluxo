from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import JourneyViewSet, RouteLiveView

router = DefaultRouter()
router.register(r"journeys", JourneyViewSet, basename="journeys")

urlpatterns = [path("routes/<int:pk>/live/", RouteLiveView.as_view()), *router.urls]
