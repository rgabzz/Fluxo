from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):

    class Role(models.TextChoices):
        STUDENT = "STUDENT", "Aluno"
        DRIVER = "DRIVER", "Motorista"
        CITY_ADMIN = "CITY_ADMIN", "Prefeitura"
        SYSTEM_ADMIN = "SYSTEM_ADMIN", "Sistema"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.STUDENT
    )