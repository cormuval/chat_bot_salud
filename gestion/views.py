from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

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

@login_required
def panel(request):
    perfil = obtener_perfil_activo(request.user)
    if perfil is None:
        return redirect("gestion:sin_acceso")
    if puede_usar_selector(perfil):
        return redirect("gestion:selector_lista")
    if puede_usar_comunicador(perfil):
        return redirect("gestion:comunicador_lista")
    return redirect("gestion:sin_acceso")


def sin_acceso(request):
    return render(request, "gestion/sin_acceso.html")


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
    gestion = get_object_or_404(Gestion.objects.tabla_comunicador(perfil), pk=pk)
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
@require_POST
def registrar_whatsapp(request, pk):
    perfil = obtener_perfil_activo(request.user)
    if perfil is None or not puede_escribir_comunicador(perfil):
        return redirect("gestion:sin_acceso")
    gestion = get_object_or_404(Gestion.objects.tabla_comunicador(perfil), pk=pk)
    url = gestion.url_whatsapp()
    if not url:
        messages.error(request, "La solicitud no tiene un telefono valido para WhatsApp.")
        return redirect("gestion:comunicador_detalle", pk=gestion.pk)
    gestion.registrar_click_whatsapp(request.user)
    return HttpResponseRedirect(url)
