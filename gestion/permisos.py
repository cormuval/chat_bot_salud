from django.shortcuts import get_object_or_404

from .models import Gestion, PerfilUsuario
from solicitudes.models import Centro


ROLES_SELECTOR = {
    PerfilUsuario.Rol.SELECTOR,
    PerfilUsuario.Rol.FULL,
    PerfilUsuario.Rol.SOME,
}
ROLES_COMUNICADOR = {
    PerfilUsuario.Rol.COMUNICADOR,
    PerfilUsuario.Rol.FULL,
    PerfilUsuario.Rol.SOME,
}
ROLES_SOLO_LECTURA = {
    PerfilUsuario.Rol.SUPERVISOR_CENTRO,
    PerfilUsuario.Rol.SUPERVISOR_DAS,
    PerfilUsuario.Rol.ADMIN,
}


def obtener_perfil_activo(usuario):
    if not usuario.is_authenticated or not usuario.is_active:
        return None
    perfil = getattr(usuario, "perfil_gestion", None)
    if perfil is None or not perfil.activo:
        return None
    return perfil


def puede_usar_selector(perfil):
    return perfil.rol in ROLES_SELECTOR | ROLES_SOLO_LECTURA


def puede_usar_comunicador(perfil):
    return perfil.rol in ROLES_COMUNICADOR | ROLES_SOLO_LECTURA


def puede_escribir_selector(perfil):
    return perfil.rol in ROLES_SELECTOR


def puede_escribir_comunicador(perfil):
    return perfil.rol in ROLES_COMUNICADOR


def puede_ver_no_aplica(perfil):
    return perfil.rol != PerfilUsuario.Rol.COMUNICADOR


ROLES_ADMIN_GLOBAL = {PerfilUsuario.Rol.ADMIN, PerfilUsuario.Rol.SUPERVISOR_DAS}
ROLES_ADMIN_PERFILES = ROLES_ADMIN_GLOBAL | {PerfilUsuario.Rol.SUPERVISOR_CENTRO}
ROLES_OPERATIVOS = {
    PerfilUsuario.Rol.SELECTOR,
    PerfilUsuario.Rol.COMUNICADOR,
    PerfilUsuario.Rol.FULL,
    PerfilUsuario.Rol.SOME,
}


def puede_administrar_perfiles(perfil):
    return perfil.rol in ROLES_ADMIN_PERFILES


def puede_ver_reportes(perfil):
    return perfil.rol in ROLES_ADMIN_PERFILES


def roles_asignables(perfil):
    if perfil.rol in ROLES_ADMIN_GLOBAL:
        return list(PerfilUsuario.Rol)
    return [rol for rol in PerfilUsuario.Rol if rol in ROLES_OPERATIVOS]


def centros_administrables(perfil):
    if perfil.rol in ROLES_ADMIN_GLOBAL:
        return Centro.objects.all()
    return Centro.objects.filter(pk=perfil.centro_id)


def es_ultimo_admin_activo(perfil):
    if perfil.rol != PerfilUsuario.Rol.ADMIN or not perfil.activo:
        return False
    otros = PerfilUsuario.objects.filter(
        rol=PerfilUsuario.Rol.ADMIN, activo=True
    ).exclude(pk=perfil.pk)
    return not otros.exists()


def gestion_alcanzable_o_404(perfil, pk):
    queryset = Gestion.objects.select_related(
        "solicitud",
        "solicitud__centro_salud",
        "motivo_rechazo",
        "decidido_por",
        "contactado_por",
    ).del_alcance(perfil)
    return get_object_or_404(queryset, pk=pk)
