from django.contrib import admin
from django.urls import path, include

from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView
)

urlpatterns = [
    path('admin/', admin.site.urls),

    # AUTH
    path('api/auth/', include('users.auth_urls')),

    # JWT LOGIN
    path('api/token/', TokenObtainPairView.as_view()),
    path('api/token/refresh/', TokenRefreshView.as_view()),

    # USERS (ADMIN)
    path('api/', include('users.urls')),
]