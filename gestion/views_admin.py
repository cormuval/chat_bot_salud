from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import redirect, render

from .forms_admin import PerfilAdminForm
from .models import PerfilUsuario
from .permisos import (
    centros_administrables,
    es_ultimo_admin_activo,
    obtener_perfil_activo,
    puede_administrar_perfiles,
    roles_asignables,
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


def _puede_operar_sobre(perfil_editor, rol_objetivo, centro_objetivo_id):
    asignables = {r.value for r in roles_asignables(perfil_editor)}
    if rol_objetivo not in asignables:
        return False
    if perfil_editor.rol in {PerfilUsuario.Rol.ADMIN, PerfilUsuario.Rol.SUPERVISOR_DAS}:
        return True
    return centro_objetivo_id == perfil_editor.centro_id


@login_required
def perfil_crear(request):
    editor = obtener_perfil_activo(request.user)
    if editor is None or not puede_administrar_perfiles(editor):
        return redirect("gestion:sin_acceso")
    form = PerfilAdminForm(request.POST or None, perfil_editor=editor, es_creacion=True)
    if request.method == "POST" and form.is_valid():
        rol = form.cleaned_data["rol"]
        centro = form.cleaned_data["centro"]
        if not _puede_operar_sobre(editor, rol, centro.pk):
            form.add_error(None, "No tiene permiso para asignar ese rol o centro.")
        else:
            email = form.cleaned_data["email"].strip()
            user = User.objects.filter(email__iexact=email).first()
            if user is None:
                user = User.objects.create_user(username=email, email=email)
            if PerfilUsuario.objects.filter(usuario=user).exists():
                form.add_error("email", "Ese usuario ya tiene un perfil. Editelo desde la lista.")
            else:
                perfil = form.save(commit=False)
                perfil.usuario = user
                perfil.save()
                messages.success(request, "Perfil creado.")
                return redirect("gestion:perfiles_lista")
    return render(request, "gestion/perfil_form.html", {"perfil": editor, "form": form, "es_creacion": True})


@login_required
def perfil_editar(request, pk):
    editor = obtener_perfil_activo(request.user)
    if editor is None or not puede_administrar_perfiles(editor):
        return redirect("gestion:sin_acceso")
    objetivo = _perfiles_del_alcance(editor).filter(pk=pk).first()
    if objetivo is None:
        return redirect("gestion:perfiles_lista")
    # Se calcula antes de instanciar el form: ModelForm.is_valid() muta
    # `objetivo` in-place (es la misma instancia que form.instance) con los
    # datos posteados, asi que despues de is_valid() ya no refleja el estado
    # guardado en la base de datos.
    era_ultimo_admin_activo = es_ultimo_admin_activo(objetivo)
    form = PerfilAdminForm(request.POST or None, instance=objetivo, perfil_editor=editor, es_creacion=False)
    if request.method == "POST" and form.is_valid():
        rol = form.cleaned_data["rol"]
        centro = form.cleaned_data["centro"]
        activo = form.cleaned_data["activo"]
        if not _puede_operar_sobre(editor, rol, centro.pk):
            form.add_error(None, "No tiene permiso para asignar ese rol o centro.")
        elif era_ultimo_admin_activo and (not activo or rol != PerfilUsuario.Rol.ADMIN):
            form.add_error(None, "No puede dejar el sistema sin administradores activos.")
        else:
            form.save()
            messages.success(request, "Perfil actualizado.")
            return redirect("gestion:perfiles_lista")
    return render(request, "gestion/perfil_form.html", {"perfil": editor, "form": form, "es_creacion": False})
