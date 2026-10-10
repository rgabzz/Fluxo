from django.contrib import admin
from django.urls import include, path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    path("admin/", admin.site.urls),
    # Auth
    path("api/auth/", include("users.auth_urls")),
    path("api/token/", TokenObtainPairView.as_view()),
    path("api/token/refresh/", TokenRefreshView.as_view()),
    # Recursos
    path("api/", include("users.urls")),
    path("api/", include("buses.urls")),
    path("api/", include("tracking.urls")),
    path("api/", include("notifications.urls")),
]
