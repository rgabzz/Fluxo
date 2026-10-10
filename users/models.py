from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        STUDENT = "STUDENT", "Aluno"
        DRIVER = "DRIVER", "Motorista"
        CITY_ADMIN = "CITY_ADMIN", "Prefeitura"
        SYSTEM_ADMIN = "SYSTEM_ADMIN", "Sistema"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT)

    @property
    def is_fluxo_admin(self) -> bool:
        return self.is_superuser or self.role in (self.Role.CITY_ADMIN, self.Role.SYSTEM_ADMIN)

    @property
    def is_driver(self) -> bool:
        return self.role == self.Role.DRIVER
