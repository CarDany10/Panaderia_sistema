from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import PerfilCliente, PerfilRepartidor, Usuario


class UsuarioAdminSerializer(serializers.ModelSerializer):
    """CRUD de cuentas de Administrador/Trabajador/Repartidor, usado solo por un Admin.

    Los clientes no se crean aquí: se autoregistran vía RegistroClienteSerializer.
    """

    password = serializers.CharField(write_only=True, required=False, min_length=8)

    class Meta:
        model = Usuario
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "rol",
            "is_active",
            "date_joined",
            "password",
        ]
        read_only_fields = ["id", "date_joined"]

    def validate_rol(self, value):
        if value == Usuario.Rol.CLIENTE:
            raise serializers.ValidationError(
                "Los clientes se registran mediante el endpoint público de registro, no aquí."
            )
        return value

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        if not password:
            raise serializers.ValidationError(
                {"password": "La contraseña es obligatoria al crear un usuario."}
            )
        usuario = Usuario(**validated_data)
        usuario.set_password(password)
        usuario.save()
        if usuario.rol == Usuario.Rol.REPARTIDOR:
            PerfilRepartidor.objects.create(usuario=usuario)
        return usuario

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        if instance.rol == Usuario.Rol.REPARTIDOR:
            PerfilRepartidor.objects.get_or_create(usuario=instance)
        return instance


class RegistroClienteSerializer(serializers.ModelSerializer):
    """Autoregistro público de una cuenta de Cliente (sección 9 del sistema)."""

    password = serializers.CharField(write_only=True, min_length=8)
    telefono = serializers.CharField(write_only=True, required=False, allow_blank=True)
    direccion_entrega_predeterminada = serializers.CharField(
        write_only=True, required=False, allow_blank=True
    )

    class Meta:
        model = Usuario
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "password",
            "telefono",
            "direccion_entrega_predeterminada",
        ]
        read_only_fields = ["id"]

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        telefono = validated_data.pop("telefono", "")
        direccion = validated_data.pop("direccion_entrega_predeterminada", "")
        password = validated_data.pop("password")
        usuario = Usuario(rol=Usuario.Rol.CLIENTE, **validated_data)
        usuario.set_password(password)
        usuario.save()
        PerfilCliente.objects.create(
            usuario=usuario,
            telefono=telefono,
            direccion_entrega_predeterminada=direccion,
        )
        return usuario


class UsuarioMeSerializer(serializers.ModelSerializer):
    """Perfil propio del usuario autenticado, con los campos según su rol."""

    telefono = serializers.CharField(required=False, allow_blank=True)
    direccion_entrega_predeterminada = serializers.CharField(
        required=False, allow_blank=True
    )
    calificacion_promedio = serializers.SerializerMethodField()

    class Meta:
        model = Usuario
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "rol",
            "telefono",
            "direccion_entrega_predeterminada",
            "calificacion_promedio",
        ]
        read_only_fields = ["id", "username", "rol", "calificacion_promedio"]

    def get_calificacion_promedio(self, obj):
        perfil = getattr(obj, "perfil_repartidor", None)
        return perfil.calificacion_promedio if perfil else None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.rol == Usuario.Rol.CLIENTE:
            perfil = getattr(instance, "perfil_cliente", None)
            data["telefono"] = perfil.telefono if perfil else ""
            data["direccion_entrega_predeterminada"] = (
                perfil.direccion_entrega_predeterminada if perfil else ""
            )
            data.pop("calificacion_promedio", None)
        elif instance.rol == Usuario.Rol.REPARTIDOR:
            perfil = getattr(instance, "perfil_repartidor", None)
            data["telefono"] = perfil.telefono if perfil else ""
            data.pop("direccion_entrega_predeterminada", None)
        else:
            data.pop("telefono", None)
            data.pop("direccion_entrega_predeterminada", None)
            data.pop("calificacion_promedio", None)
        return data

    def update(self, instance, validated_data):
        telefono = validated_data.pop("telefono", None)
        direccion = validated_data.pop("direccion_entrega_predeterminada", None)
        for attr in ("email", "first_name", "last_name"):
            if attr in validated_data:
                setattr(instance, attr, validated_data[attr])
        instance.save()
        if instance.rol == Usuario.Rol.CLIENTE and (
            telefono is not None or direccion is not None
        ):
            # Se reutiliza el descriptor de la relación (en vez de una consulta aparte)
            # para que la caché de `instance` quede consistente con lo guardado.
            perfil = getattr(instance, "perfil_cliente", None) or PerfilCliente(
                usuario=instance
            )
            if telefono is not None:
                perfil.telefono = telefono
            if direccion is not None:
                perfil.direccion_entrega_predeterminada = direccion
            perfil.save()
        elif instance.rol == Usuario.Rol.REPARTIDOR and telefono is not None:
            perfil = getattr(instance, "perfil_repartidor", None) or PerfilRepartidor(
                usuario=instance
            )
            perfil.telefono = telefono
            perfil.save()
        return instance
