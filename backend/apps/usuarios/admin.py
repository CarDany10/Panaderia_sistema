from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import PerfilCliente, PerfilRepartidor, Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Rol", {"fields": ("rol",)}),)
    list_display = ("username", "email", "rol", "is_staff", "is_active")
    list_filter = UserAdmin.list_filter + ("rol",)


@admin.register(PerfilCliente)
class PerfilClienteAdmin(admin.ModelAdmin):
    list_display = ("usuario", "telefono")
    search_fields = ("usuario__username",)


@admin.register(PerfilRepartidor)
class PerfilRepartidorAdmin(admin.ModelAdmin):
    list_display = ("usuario", "telefono", "calificacion_promedio")
    search_fields = ("usuario__username",)
