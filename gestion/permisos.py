from django.shortcuts import get_object_or_404

from .models import Gestion, PerfilUsuario


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


def gestion_alcanzable_o_404(perfil, pk):
    queryset = Gestion.objects.select_related(
        "solicitud",
        "solicitud__centro_salud",
        "motivo_rechazo",
        "decidido_por",
        "contactado_por",
    ).del_alcance(perfil)
    return get_object_or_404(queryset, pk=pk)
