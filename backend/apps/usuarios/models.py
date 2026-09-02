from django.contrib.auth.models import AbstractUser
from django.db import models


class Usuario(AbstractUser):
    class Rol(models.TextChoices):
        ADMIN = "ADMIN", "Administrador"
        TRABAJADOR = "TRABAJADOR", "Trabajador de producción"
        REPARTIDOR = "REPARTIDOR", "Repartidor"
        CLIENTE = "CLIENTE", "Cliente"

    rol = models.CharField(max_length=20, choices=Rol.choices)

    def __str__(self):
        return f"{self.username} ({self.get_rol_display()})"
