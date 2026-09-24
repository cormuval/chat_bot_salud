import re

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .cupos import cupos_del_alcance
from .forms import AccionComunicadorForm, DecisionSelectorForm, WhatsappComunicadorForm
from .mensajes import armar_mensaje_whatsapp, url_whatsapp_para_gestion
from .models import CupoDiario, Gestion
from .permisos import (
    gestion_alcanzable_o_404,
    obtener_perfil_activo,
    puede_administrar_perfiles,
    puede_cargar_cupos,
    puede_escribir_comunicador,
    puede_escribir_selector,
    puede_usar_comunicador,
    puede_usar_selector,
    puede_ver_no_aplica,
    puede_ver_reportes,
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


def _texto_correccion_selector(gestion):
    if gestion.decision == Gestion.Decision.RECHAZADA:
        from .templatetags.gestion_ui import horas_restantes_rechazo

        return horas_restantes_rechazo(gestion)
    return "Sin intentos registrados"


def _registros_contacto(gestion):
    return list(
        gestion.registros_contacto.select_related("usuario").order_by(
            "-creado_en", "-pk"
        )
    )


def _contexto_detalle_comunicador(
    perfil,
    gestion,
    form,
    form_whatsapp,
    puede_escribir,
    es_fragmento,
    whatsapp_url="",
):
    return {
        "perfil": perfil,
        "gestion": gestion,
        "form": form,
        "form_whatsapp": form_whatsapp,
        "puede_escribir": puede_escribir,
        "es_fragmento": es_fragmento,
        "whatsapp_url": whatsapp_url,
        "registros_contacto": _registros_contacto(gestion),
    }


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


@login_required
def admin_panel(request):
    perfil = obtener_perfil_activo(request.user)
    if perfil is None or not (
        puede_administrar_perfiles(perfil) or puede_ver_reportes(perfil)
    ):
        return redirect("gestion:sin_acceso")
    return render(
        request,
        "gestion/admin_panel.html",
        {
            "perfil": perfil,
            "puede_perfiles": puede_administrar_perfiles(perfil),
            "puede_reportes": puede_ver_reportes(perfil),
        },
    )


def sin_acceso(request):
    return render(request, "gestion/sin_acceso.html")


def pagina_no_encontrada(request, exception):
    """Handler 404 del modulo de gestion. Solo se renderiza con DEBUG=False;
    con DEBUG=True Django muestra su pagina tecnica antes de llegar aca."""
    return render(request, "gestion/404.html", status=404)


def login(request):
    """Pagina de entrada del modulo: un boton para iniciar sesion con Google.
    Si el usuario ya tiene sesion y perfil, salta directo al panel. Preserva
    'next' validado contra el host actual para volver a la ruta pedida."""
    perfil = obtener_perfil_activo(request.user)
    if perfil is not None:
        return redirect("gestion:panel")
    next_url = request.GET.get("next", "")
    if not url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        next_url = ""
    return render(request, "gestion/login.html", {"next": next_url})


@login_required
def selector_lista(request):
    perfil = obtener_perfil_activo(request.user)
    if perfil is None or not puede_usar_selector(perfil):
        return redirect("gestion:sin_acceso")
    mostrar_no_aplica = puede_ver_no_aplica(perfil)
    conteos_selector = {
        "pendientes": Gestion.objects.cola_selector(perfil).count(),
        "decididas": Gestion.objects.decididas_corregibles_selector(perfil).count(),
        "no_aplica": Gestion.objects.no_aplica_selector(perfil).count()
        if mostrar_no_aplica
        else 0,
    }
    mostrar_columna_centro = perfil.centros_permitidos().count() > 1
    seccion = request.GET.get("seccion", "pendientes")
    if seccion == "decididas":
        gestiones = Gestion.objects.decididas_corregibles_selector(perfil)
    elif seccion == "no_aplica" and mostrar_no_aplica:
        gestiones = Gestion.objects.no_aplica_selector(perfil)
    else:
        seccion = "pendientes"
        gestiones = Gestion.objects.cola_selector(perfil)
    puede_cargar = puede_cargar_cupos(perfil)
    cupos = cupos_del_alcance(perfil, timezone.localdate()) if puede_cargar else []
    context = {
        "perfil": perfil,
        "gestiones": gestiones,
        "puede_escribir": puede_escribir_selector(perfil),
        "seccion": seccion,
        "mostrar_no_aplica": mostrar_no_aplica,
        "conteos_selector": conteos_selector,
        "mostrar_columna_centro": mostrar_columna_centro,
        "cupos": cupos,
        "puede_cargar_cupos": puede_cargar,
    }
    if request.GET.get("fragmento") == "1":
        return render(request, "gestion/_tabla_selector.html", context)
    return render(request, "gestion/selector_lista.html", context)


@login_required
def selector_detalle(request, pk):
    perfil = obtener_perfil_activo(request.user)
    if perfil is None or not puede_usar_selector(perfil):
        return redirect("gestion:sin_acceso")
    es_fragmento = request.GET.get("fragmento") == "1"
    template = "gestion/_detalle_selector.html" if es_fragmento else "gestion/selector_detalle.html"
    seccion_origen = request.GET.get("seccion", "pendientes")
    if seccion_origen not in {"pendientes", "decididas", "no_aplica"}:
        seccion_origen = "pendientes"
    if seccion_origen == "no_aplica" and not puede_ver_no_aplica(perfil):
        seccion_origen = "pendientes"
    gestion = gestion_alcanzable_o_404(perfil, pk)
    puede_escribir = puede_escribir_selector(perfil)
    form = DecisionSelectorForm(request.POST or None)
    if request.method == "POST":
        if not puede_escribir:
            return redirect("gestion:sin_acceso")
        if form.is_valid():
            try:
                form.guardar(gestion, request.user)
                mensaje_resultado = {
                    Gestion.Decision.ACEPTADA: f"Aceptada como {gestion.get_prioridad_clinica_display()}",
                    Gestion.Decision.RECHAZADA: "Rechazada",
                    Gestion.Decision.NO_APLICA: "Marcada como no aplica",
                }.get(gestion.decision, "Decision registrada")
                if es_fragmento:
                    seccion_destino = {
                        Gestion.Decision.PENDIENTE: "pendientes",
                        Gestion.Decision.ACEPTADA: "decididas",
                        Gestion.Decision.RECHAZADA: "decididas",
                        Gestion.Decision.NO_APLICA: "no_aplica",
                    }[gestion.decision]
                    accion_fila = "keep" if seccion_origen == seccion_destino else "remove"
                    if accion_fila == "keep":
                        siguiente = gestion
                    elif seccion_origen == "decididas":
                        siguiente = Gestion.objects.decididas_corregibles_selector(perfil).first()
                    elif seccion_origen == "no_aplica":
                        siguiente = Gestion.objects.no_aplica_selector(perfil).first()
                    else:
                        siguiente = Gestion.objects.cola_selector(perfil).first()
                    if siguiente is None:
                        return render(
                            request,
                            "gestion/_cola_selector_vacia.html",
                            {
                                "seccion_origen": seccion_origen,
                                "seccion_destino": seccion_destino,
                                "accion_fila": accion_fila,
                            },
                        )
                    gestion = gestion_alcanzable_o_404(perfil, siguiente.pk)
                    form = DecisionSelectorForm()
                    foto_credencial_data_url = _foto_credencial_data_url(gestion)
                    return render(
                        request,
                        "gestion/_detalle_selector.html",
                        {
                            "perfil": perfil,
                            "gestion": gestion,
                            "form": form,
                            "puede_escribir": puede_escribir,
                            "foto_credencial_data_url": foto_credencial_data_url,
                            "mensaje_resultado": mensaje_resultado,
                            "es_fragmento": es_fragmento,
                            "seccion_origen": seccion_origen,
                            "seccion_destino": seccion_destino,
                            "accion_fila": accion_fila,
                            "texto_correccion_fila": _texto_correccion_selector(gestion),
                        },
                    )
                messages.success(request, "Decision registrada.")
                if seccion_origen == "pendientes":
                    return redirect("gestion:selector_lista")
                return HttpResponseRedirect(
                    f"{reverse('gestion:selector_lista')}?seccion={seccion_origen}"
                )
            except ValidationError as exc:
                form.add_error(None, exc)
    return render(
        request,
        template,
        {
            "perfil": perfil,
            "gestion": gestion,
            "form": form,
            "puede_escribir": puede_escribir,
            "foto_credencial_data_url": _foto_credencial_data_url(gestion),
            "mensaje_resultado": "",
            "es_fragmento": es_fragmento,
            "seccion_origen": seccion_origen,
            "seccion_destino": seccion_origen,
            "accion_fila": "keep",
            "texto_correccion_fila": _texto_correccion_selector(gestion),
        },
    )


@require_POST
def guardar_cupo(request):
    perfil = obtener_perfil_activo(request.user)
    if perfil is None or not puede_cargar_cupos(perfil):
        return redirect("gestion:sin_acceso")
    try:
        centro_id = int(request.POST.get("centro_id", ""))
        cupos = int(request.POST.get("cupos_iniciales", ""))
    except (TypeError, ValueError):
        messages.error(request, "Indica un numero de cupos valido.")
        return redirect("gestion:selector_lista")
    if cupos < 0:
        messages.error(request, "Los cupos no pueden ser negativos.")
        return redirect("gestion:selector_lista")
    if not perfil.centros_permitidos().filter(pk=centro_id).exists():
        return redirect("gestion:sin_acceso")
    CupoDiario.objects.update_or_create(
        centro_id=centro_id,
        fecha=timezone.localdate(),
        defaults={"cupos_iniciales": cupos, "registrado_por": request.user},
    )
    messages.success(request, "Cupos actualizados.")
    return redirect("gestion:selector_lista")


@login_required
def comunicador_lista(request):
    perfil = obtener_perfil_activo(request.user)
    if perfil is None or not puede_usar_comunicador(perfil):
        return redirect("gestion:sin_acceso")
    gestiones = list(Gestion.objects.tabla_comunicador(perfil))
    gestiones_aceptadas = [
        gestion for gestion in gestiones if gestion.decision == Gestion.Decision.ACEPTADA
    ]
    gestiones_rechazadas = [
        gestion for gestion in gestiones if gestion.decision == Gestion.Decision.RECHAZADA
    ]
    return render(
        request,
        "gestion/comunicador_lista.html",
        {
            "perfil": perfil,
            "gestiones": gestiones,
            "gestiones_aceptadas": gestiones_aceptadas,
            "gestiones_rechazadas": gestiones_rechazadas,
            "puede_escribir": puede_escribir_comunicador(perfil),
        },
    )


@login_required
def comunicador_detalle(request, pk):
    perfil = obtener_perfil_activo(request.user)
    if perfil is None or not puede_usar_comunicador(perfil):
        return redirect("gestion:sin_acceso")
    es_fragmento = request.GET.get("fragmento") == "1"
    template = "gestion/_detalle_comunicador.html" if es_fragmento else "gestion/comunicador_detalle.html"
    if request.method == "POST":
        gestion = _gestion_para_post_comunicador_o_404(perfil, pk)
    else:
        gestion = get_object_or_404(Gestion.objects.tabla_comunicador(perfil), pk=pk)
    puede_escribir = puede_escribir_comunicador(perfil)
    form = AccionComunicadorForm(request.POST or None)
    form_whatsapp = WhatsappComunicadorForm(gestion=gestion)
    if request.method == "POST":
        if not puede_escribir:
            return redirect("gestion:sin_acceso")
        if form.is_valid():
            try:
                form.guardar(gestion, request.user)
                _advertir_cierre_automatico(request, gestion)
                if es_fragmento:
                    return render(
                        request,
                        "gestion/_confirmacion_comunicador.html",
                        {
                            "perfil": perfil,
                            "gestion": gestion,
                            "mensaje_resultado": "Contacto registrado.",
                        },
                    )
                messages.success(request, "Contacto registrado.")
                return redirect("gestion:comunicador_lista")
            except ValidationError as exc:
                form.add_error(None, exc)
    return render(
        request,
        template,
        _contexto_detalle_comunicador(
            perfil,
            gestion,
            form,
            form_whatsapp,
            puede_escribir,
            es_fragmento,
        ),
    )


@login_required
@require_POST
def registrar_whatsapp(request, pk):
    perfil = obtener_perfil_activo(request.user)
    if perfil is None or not puede_escribir_comunicador(perfil):
        return redirect("gestion:sin_acceso")
    gestion = _gestion_para_post_comunicador_o_404(perfil, pk)
    es_fragmento = request.GET.get("fragmento") == "1"
    form = WhatsappComunicadorForm(request.POST, gestion=gestion)
    if not form.is_valid():
        if es_fragmento:
            return render(
                request,
                "gestion/_detalle_comunicador.html",
                _contexto_detalle_comunicador(
                    perfil,
                    gestion,
                    AccionComunicadorForm(),
                    form,
                    True,
                    True,
                ),
            )
        messages.error(request, "El formulario de WhatsApp no es valido.")
        return redirect("gestion:comunicador_detalle", pk=gestion.pk)
    url = url_whatsapp_para_gestion(gestion, cuerpo=form.cleaned_data["cuerpo"])
    if not url:
        messages.error(request, "La solicitud no tiene un telefono valido para WhatsApp.")
        return redirect("gestion:comunicador_detalle", pk=gestion.pk)
    mensaje = armar_mensaje_whatsapp(gestion, form.cleaned_data["cuerpo"])
    try:
        gestion.registrar_click_whatsapp(
            request.user,
            token_contacto=form.cleaned_data.get("token_contacto", ""),
            mensaje=mensaje,
        )
    except ValidationError:
        messages.error(
            request,
            "La solicitud ya no esta disponible para registrar contacto.",
        )
        return redirect("gestion:comunicador_lista")
    _advertir_cierre_automatico(request, gestion)
    if es_fragmento:
        return render(
            request,
            "gestion/_detalle_comunicador.html",
            _contexto_detalle_comunicador(
                perfil,
                gestion,
                AccionComunicadorForm(),
                WhatsappComunicadorForm(
                    initial={"cuerpo": form.cleaned_data["cuerpo"]},
                    gestion=gestion,
                ),
                True,
                True,
                whatsapp_url=url,
            ),
        )
    return HttpResponseRedirect(url)
