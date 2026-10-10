from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import NoticeViewSet, NotificationViewSet, PushTokenView

router = DefaultRouter()
router.register(r"notifications", NotificationViewSet, basename="notifications")
router.register(r"notices", NoticeViewSet, basename="notices")

urlpatterns = [path("push-tokens/", PushTokenView.as_view()), *router.urls]
