from rest_framework import generics, mixins, permissions, viewsets
from rest_framework.response import Response

from .models import User
from .permissions import IsAdmin
from .serializers import AdminCreateUserSerializer, RegisterSerializer, UserSerializer


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]


class MeView(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        u = request.user
        return Response(
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "first_name": u.first_name,
                "last_name": u.last_name,
                "role": u.role,
            }
        )


class UserViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Gestão de usuários (somente admin). `?role=DRIVER` filtra por papel."""

    permission_classes = [IsAdmin]

    def get_queryset(self):
        qs = User.objects.all().order_by("id")
        role = self.request.query_params.get("role")
        return qs.filter(role=role) if role else qs

    def get_serializer_class(self):
        return AdminCreateUserSerializer if self.action == "create" else UserSerializer

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "request": self.request}
