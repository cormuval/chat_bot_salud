from django.contrib import admin

from .models import Gestion, MotivoRechazo, PerfilUsuario, PlantillaWhatsapp


@admin.register(PerfilUsuario)
class PerfilUsuarioAdmin(admin.ModelAdmin):
    list_display = ("usuario", "rol", "centro", "centro_satelite", "activo")
    list_filter = ("rol", "activo", "centro")
    search_fields = ("usuario__email", "usuario__first_name", "usuario__last_name")
    autocomplete_fields = ("usuario",)
    list_select_related = ("usuario", "centro", "centro_satelite")


@admin.register(MotivoRechazo)
class MotivoRechazoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "activo", "orden")
    list_filter = ("activo",)
    search_fields = ("nombre", "mensaje_paciente")
    ordering = ("orden", "nombre")


@admin.register(PlantillaWhatsapp)
class PlantillaWhatsappAdmin(admin.ModelAdmin):
    list_display = ("clave", "descripcion", "activo")
    list_filter = ("activo",)
    search_fields = ("clave", "descripcion", "cuerpo")


@admin.register(Gestion)
class GestionAdmin(admin.ModelAdmin):
    list_display = (
        "solicitud",
        "decision",
        "prioridad_clinica",
        "motivo_rechazo",
        "intentos_contacto",
        "cerrada_en",
        "motivo_cierre",
    )
    list_filter = ("decision", "prioridad_clinica", "motivo_cierre", "solicitud__centro_salud")
    search_fields = ("solicitud__nombre", "solicitud__rut", "solicitud__telefono")
    readonly_fields = ("solicitud",)
    list_select_related = ("solicitud", "motivo_rechazo", "decidido_por", "contactado_por")
