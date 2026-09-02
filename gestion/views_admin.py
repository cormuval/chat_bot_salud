from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .models import PerfilUsuario
from .permisos import (
    centros_administrables,
    obtener_perfil_activo,
    puede_administrar_perfiles,
)


def _perfiles_del_alcance(perfil):
    qs = PerfilUsuario.objects.select_related("usuario", "centro").order_by(
        "usuario__email"
    )
    if perfil.rol in {PerfilUsuario.Rol.ADMIN, PerfilUsuario.Rol.SUPERVISOR_DAS}:
        return qs
    return qs.filter(centro_id=perfil.centro_id)


@login_required
def perfiles_lista(request):
    perfil = obtener_perfil_activo(request.user)
    if perfil is None or not puede_administrar_perfiles(perfil):
        return redirect("gestion:sin_acceso")
    return render(
        request,
        "gestion/perfiles_lista.html",
        {"perfil": perfil, "perfiles": _perfiles_del_alcance(perfil)},
    )
