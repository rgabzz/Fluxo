from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import User


class RegisterSerializer(serializers.ModelSerializer):
    """Cadastro PÚBLICO: sempre cria ALUNO. O papel não pode ser escolhido aqui."""

    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    class Meta:
        model = User
        fields = ["username", "email", "first_name", "last_name", "password"]

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        return User.objects.create_user(role=User.Role.STUDENT, **validated_data)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "role", "is_active"]
        read_only_fields = ["id"]


class AdminCreateUserSerializer(serializers.ModelSerializer):
    """Usado só por admins para criar motoristas e outros admins."""

    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "role", "password"]
        read_only_fields = ["id"]

    def validate_password(self, value):
        validate_password(value)
        return value

    def validate_role(self, value):
        # Só superuser cria SYSTEM_ADMIN.
        request = self.context.get("request")
        if value == User.Role.SYSTEM_ADMIN and not (request and request.user.is_superuser):
            raise serializers.ValidationError("Apenas superusuários criam administradores do sistema.")
        return value

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)
