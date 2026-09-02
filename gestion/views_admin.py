from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import redirect, render

from solicitudes.models import Solicitud

from .forms_admin import PerfilAdminForm
from .models import Gestion, PerfilUsuario, RegistroContacto
from .permisos import (
    centros_administrables,
    es_ultimo_admin_activo,
    obtener_perfil_activo,
    puede_administrar_perfiles,
    puede_ver_reportes,
    roles_asignables,
)
from .reportes import exportar_csv, rango_fechas


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
    # Guarda de frontera: el editor tampoco puede operar sobre un perfil cuyo
    # rol o centro ACTUAL este fuera de su alcance. Sin esto, un supervisor de
    # centro podria degradar o desactivar a un admin de su mismo centro.
    if not _puede_operar_sobre(editor, objetivo.rol, objetivo.centro_id):
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


@login_required
def reportes(request):
    perfil = obtener_perfil_activo(request.user)
    if perfil is None or not puede_ver_reportes(perfil):
        return redirect("gestion:sin_acceso")
    return render(request, "gestion/reportes.html", {"perfil": perfil})


def _solicitudes_del_alcance(perfil):
    qs = Solicitud.objects.select_related("centro_salud").order_by("date_solicitud")
    if perfil.ve_todos_los_centros:
        return qs
    return qs.filter(centro_salud__in=perfil.centros_permitidos())


@login_required
def reporte_solicitudes(request):
    perfil = obtener_perfil_activo(request.user)
    if perfil is None or not puede_ver_reportes(perfil):
        return redirect("gestion:sin_acceso")
    desde, hasta = rango_fechas(request)
    if desde is None or hasta is None:
        messages.error(request, "Indique el rango de fechas (desde y hasta).")
        return redirect("gestion:reportes")
    qs = _solicitudes_del_alcance(perfil).filter(date_solicitud__date__range=(desde, hasta))
    encabezados = ["Fecha", "RUT", "Nombre", "Telefono", "Edad", "Sexo", "Centro",
                   "Motivo", "Detalle", "Prioridad administrativa", "Puntaje"]
    filas = (
        [
            s.date_solicitud.strftime("%Y-%m-%d %H:%M"), s.rut, s.nombre, s.telefono,
            s.edad, s.get_sexo_display(), str(s.centro_salud), s.motivo, s.detalle_motivo,
            s.get_priorizacion_solicitud_display(), s.puntaje_prioridad,
        ]
        for s in qs.iterator()
    )
    return exportar_csv("solicitudes.csv", encabezados, filas)


def _registros_del_alcance(perfil):
    qs = RegistroContacto.objects.select_related(
        "gestion__solicitud__centro_salud", "usuario"
    ).order_by("creado_en")
    if perfil.ve_todos_los_centros:
        return qs
    return qs.filter(gestion__solicitud__centro_salud__in=perfil.centros_permitidos())


@login_required
def reporte_contactabilidad(request):
    perfil = obtener_perfil_activo(request.user)
    if perfil is None or not puede_ver_reportes(perfil):
        return redirect("gestion:sin_acceso")
    desde, hasta = rango_fechas(request)
    if desde is None or hasta is None:
        messages.error(request, "Indique el rango de fechas (desde y hasta).")
        return redirect("gestion:reportes")
    qs = _registros_del_alcance(perfil).filter(creado_en__date__range=(desde, hasta))
    encabezados = ["Fecha", "Paciente", "RUT", "Centro", "Canal", "Resultado", "Usuario", "Mensaje"]
    filas = (
        [
            r.creado_en.strftime("%Y-%m-%d %H:%M"), r.gestion.solicitud.nombre,
            r.gestion.solicitud.rut, str(r.gestion.solicitud.centro_salud),
            r.get_canal_display(), r.get_resultado_display(),
            r.usuario.email if r.usuario else "", r.mensaje,
        ]
        for r in qs.iterator()
    )
    return exportar_csv("contactabilidad.csv", encabezados, filas)


@login_required
def reporte_gestiones(request):
    perfil = obtener_perfil_activo(request.user)
    if perfil is None or not puede_ver_reportes(perfil):
        return redirect("gestion:sin_acceso")
    desde, hasta = rango_fechas(request)
    if desde is None or hasta is None:
        messages.error(request, "Indique el rango de fechas (desde y hasta).")
        return redirect("gestion:reportes")
    qs = (
        Gestion.objects.select_related("solicitud__centro_salud", "decidido_por", "motivo_rechazo")
        .del_alcance(perfil)
        .filter(fecha_decision__date__range=(desde, hasta))
        .order_by("fecha_decision")
    )
    encabezados = ["Fecha decision", "Paciente", "RUT", "Centro", "Decision",
                   "Prioridad clinica", "Motivo rechazo", "Decidido por"]
    filas = (
        [
            g.fecha_decision.strftime("%Y-%m-%d %H:%M") if g.fecha_decision else "",
            g.solicitud.nombre, g.solicitud.rut, str(g.solicitud.centro_salud),
            g.get_decision_display(), g.get_prioridad_clinica_display() or "",
            str(g.motivo_rechazo) if g.motivo_rechazo_id else "",
            g.decidido_por.email if g.decidido_por else "",
        ]
        for g in qs.iterator()
    )
    return exportar_csv("gestiones-selector.csv", encabezados, filas)
