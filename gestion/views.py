from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect, render

from .forms import AccionComunicadorForm, DecisionSelectorForm
from .models import Gestion
from .permisos import (
    gestion_alcanzable_o_404,
    obtener_perfil_activo,
    puede_escribir_comunicador,
    puede_escribir_selector,
    puede_usar_comunicador,
    puede_usar_selector,
)


def _tiene_perfil_activo(usuario):
    # mozilla_django_oidc sobreescribe get_user() sin llamar a
    # user_can_authenticate() (a diferencia de ModelBackend), asi que
    # desmarcar User.is_active en el admin no revoca por si solo una sesion
    # ya iniciada. Lo chequeamos aca ademas de en el perfil.
    if not usuario.is_active:
        return False
    perfil = getattr(usuario, "perfil_gestion", None)
    return perfil is not None and perfil.activo


@login_required
def panel(request):
    if not _tiene_perfil_activo(request.user):
        return redirect("gestion:sin_acceso")
    return HttpResponse("Módulo de gestión — en construcción")


def sin_acceso(request):
    return HttpResponse(
        "Su cuenta no tiene acceso al módulo de gestión. "
        "Solicite a la administración que le asigne un perfil."
    )


@login_required
def selector_lista(request):
    perfil = obtener_perfil_activo(request.user)
    if perfil is None or not puede_usar_selector(perfil):
        return redirect("gestion:sin_acceso")
    gestiones = Gestion.objects.cola_selector(perfil)
    return render(
        request,
        "gestion/selector_lista.html",
        {
            "perfil": perfil,
            "gestiones": gestiones,
            "puede_escribir": puede_escribir_selector(perfil),
        },
    )


@login_required
def selector_detalle(request, pk):
    perfil = obtener_perfil_activo(request.user)
    if perfil is None or not puede_usar_selector(perfil):
        return redirect("gestion:sin_acceso")
    gestion = gestion_alcanzable_o_404(perfil, pk)
    puede_escribir = puede_escribir_selector(perfil)
    form = DecisionSelectorForm(request.POST or None)
    if request.method == "POST":
        if not puede_escribir:
            return redirect("gestion:sin_acceso")
        if form.is_valid():
            try:
                form.guardar(gestion, request.user)
                messages.success(request, "Decision registrada.")
                return redirect("gestion:selector_lista")
            except ValidationError as exc:
                form.add_error(None, exc)
    return render(
        request,
        "gestion/selector_detalle.html",
        {
            "perfil": perfil,
            "gestion": gestion,
            "form": form,
            "puede_escribir": puede_escribir,
        },
    )


@login_required
def comunicador_lista(request):
    perfil = obtener_perfil_activo(request.user)
    if perfil is None or not puede_usar_comunicador(perfil):
        return redirect("gestion:sin_acceso")
    gestiones = Gestion.objects.tabla_comunicador(perfil)
    return render(
        request,
        "gestion/comunicador_lista.html",
        {
            "perfil": perfil,
            "gestiones": gestiones,
            "puede_escribir": puede_escribir_comunicador(perfil),
        },
    )


@login_required
def comunicador_detalle(request, pk):
    perfil = obtener_perfil_activo(request.user)
    if perfil is None or not puede_usar_comunicador(perfil):
        return redirect("gestion:sin_acceso")
    gestion = gestion_alcanzable_o_404(perfil, pk)
    puede_escribir = puede_escribir_comunicador(perfil)
    form = AccionComunicadorForm(request.POST or None)
    if request.method == "POST":
        if not puede_escribir:
            return redirect("gestion:sin_acceso")
        if form.is_valid():
            form.guardar(gestion, request.user)
            messages.success(request, "Contacto registrado.")
            return redirect("gestion:comunicador_lista")
    return render(
        request,
        "gestion/comunicador_detalle.html",
        {
            "perfil": perfil,
            "gestion": gestion,
            "form": form,
            "puede_escribir": puede_escribir,
        },
    )


@login_required
def registrar_whatsapp(request, pk):
    perfil = obtener_perfil_activo(request.user)
    if perfil is None or not puede_escribir_comunicador(perfil):
        return redirect("gestion:sin_acceso")
    gestion = gestion_alcanzable_o_404(perfil, pk)
    url = gestion.url_whatsapp()
    if not url:
        messages.error(request, "La solicitud no tiene un telefono valido para WhatsApp.")
        return redirect("gestion:comunicador_detalle", pk=gestion.pk)
    gestion.registrar_click_whatsapp(request.user)
    return HttpResponseRedirect(url)
