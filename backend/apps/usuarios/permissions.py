from rest_framework.permissions import BasePermission

from .models import Usuario


class EsAdministrador(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.rol == Usuario.Rol.ADMIN
        )


class EsTrabajador(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.rol == Usuario.Rol.TRABAJADOR
        )


class EsRepartidor(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.rol == Usuario.Rol.REPARTIDOR
        )


class EsCliente(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.rol == Usuario.Rol.CLIENTE
        )
