import re

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import AccionComunicadorForm, DecisionSelectorForm, WhatsappComunicadorForm
from .models import Gestion
from .permisos import (
    gestion_alcanzable_o_404,
    obtener_perfil_activo,
    puede_escribir_comunicador,
    puede_escribir_selector,
    puede_usar_comunicador,
    puede_usar_selector,
    puede_ver_no_aplica,
)


PATRON_FOTO_CREDENCIAL = re.compile(
    r"data:image/(?:png|jpeg|jpg|gif|webp);base64,[A-Za-z0-9+/=]+"
)


def _foto_credencial_data_url(gestion):
    foto = gestion.solicitud.credencial_cuidador_discapacidad_foto
    if foto and PATRON_FOTO_CREDENCIAL.fullmatch(foto):
        return foto
    return ""


def _gestion_para_post_comunicador_o_404(perfil, pk):
    queryset = (
        Gestion.objects.select_related("solicitud", "motivo_rechazo")
        .del_alcance(perfil)
        .filter(
            Q(decision=Gestion.Decision.ACEPTADA, cerrada_en__isnull=True)
            | Q(decision=Gestion.Decision.RECHAZADA, cerrada_en__isnull=True)
            | Q(
                decision=Gestion.Decision.RECHAZADA,
                motivo_cierre__in=Gestion.motivos_cierre_automatico(),
            )
        )
    )
    return get_object_or_404(queryset, pk=pk)


def _advertir_cierre_automatico(request, gestion):
    if gestion.tiene_cierre_automatico or gestion.rechazado_vencido():
        messages.warning(
            request,
            "La solicitud ya se habia cerrado automaticamente; "
            "el registro se aplico igualmente.",
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
    mostrar_no_aplica = puede_ver_no_aplica(perfil)
    seccion = request.GET.get("seccion", "pendientes")
    if seccion == "decididas":
        gestiones = Gestion.objects.decididas_corregibles_selector(perfil)
    elif seccion == "no_aplica" and mostrar_no_aplica:
        gestiones = Gestion.objects.no_aplica_selector(perfil)
    else:
        seccion = "pendientes"
        gestiones = Gestion.objects.cola_selector(perfil)
    return render(
        request,
        "gestion/selector_lista.html",
        {
            "perfil": perfil,
            "gestiones": gestiones,
            "puede_escribir": puede_escribir_selector(perfil),
            "seccion": seccion,
            "mostrar_no_aplica": mostrar_no_aplica,
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
            "foto_credencial_data_url": _foto_credencial_data_url(gestion),
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
    if request.method == "POST":
        gestion = _gestion_para_post_comunicador_o_404(perfil, pk)
    else:
        gestion = get_object_or_404(Gestion.objects.tabla_comunicador(perfil), pk=pk)
    puede_escribir = puede_escribir_comunicador(perfil)
    form = AccionComunicadorForm(request.POST or None)
    form_whatsapp = WhatsappComunicadorForm()
    if request.method == "POST":
        if not puede_escribir:
            return redirect("gestion:sin_acceso")
        if form.is_valid():
            try:
                form.guardar(gestion, request.user)
                _advertir_cierre_automatico(request, gestion)
                messages.success(request, "Contacto registrado.")
                return redirect("gestion:comunicador_lista")
            except ValidationError as exc:
                form.add_error(None, exc)
    return render(
        request,
        "gestion/comunicador_detalle.html",
        {
            "perfil": perfil,
            "gestion": gestion,
            "form": form,
            "form_whatsapp": form_whatsapp,
            "puede_escribir": puede_escribir,
        },
    )


@login_required
@require_POST
def registrar_whatsapp(request, pk):
    perfil = obtener_perfil_activo(request.user)
    if perfil is None or not puede_escribir_comunicador(perfil):
        return redirect("gestion:sin_acceso")
    gestion = _gestion_para_post_comunicador_o_404(perfil, pk)
    url = gestion.url_whatsapp()
    if not url:
        messages.error(request, "La solicitud no tiene un telefono valido para WhatsApp.")
        return redirect("gestion:comunicador_detalle", pk=gestion.pk)
    form = WhatsappComunicadorForm(request.POST)
    if not form.is_valid():
        messages.error(request, "El formulario de WhatsApp no es valido.")
        return redirect("gestion:comunicador_detalle", pk=gestion.pk)
    try:
        gestion.registrar_click_whatsapp(
            request.user,
            token_contacto=form.cleaned_data.get("token_contacto", ""),
        )
    except ValidationError:
        messages.error(
            request,
            "La solicitud ya no esta disponible para registrar contacto.",
        )
        return redirect("gestion:comunicador_lista")
    _advertir_cierre_automatico(request, gestion)
    return HttpResponseRedirect(url)
