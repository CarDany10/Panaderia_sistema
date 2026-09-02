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


class PerfilCliente(models.Model):
    usuario = models.OneToOneField(
        Usuario, on_delete=models.CASCADE, related_name="perfil_cliente"
    )
    telefono = models.CharField(max_length=30, blank=True)
    direccion_entrega_predeterminada = models.TextField(blank=True)

    def __str__(self):
        return f"Perfil cliente de {self.usuario.username}"


class PerfilRepartidor(models.Model):
    usuario = models.OneToOneField(
        Usuario, on_delete=models.CASCADE, related_name="perfil_repartidor"
    )
    telefono = models.CharField(max_length=30, blank=True)
    # Se recalcula a partir de las Calificaciones registradas (Fase 10). Nulo hasta la
    # primera calificación: no se inventa una calificación inicial.
    calificacion_promedio = models.DecimalField(
        max_digits=3, decimal_places=2, null=True, blank=True
    )

    def __str__(self):
        return f"Perfil repartidor de {self.usuario.username}"
