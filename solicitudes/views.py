import json

from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from .models import Solicitud
from .priorizacion import calcular_prioridad
from .validators import formatear_rut_sin_puntos, formatear_telefono_con_codigo_pais


def chatbot(request):
    return saludbot(request)


def saludbot(request):
    return render(
        request,
        "chat/saludbot.html",
        {
            "nombre_cesfam": request.GET.get("cesfam", "Corporacion Municipal de Valparaiso"),
            "user_name": request.GET.get("user_name", ""),
        },
    )


def terminos(request):
    return render(request, "chat/terminos.html")


def pagina_no_encontrada(request, exception):
    return render(request, "404.html", status=404)


def _json_body(request):
    try:
        return json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        raise ValidationError("El cuerpo de la solicitud debe ser JSON valido.")


def _bool_from_payload(value):
    if isinstance(value, bool):
        return value

    normalized = str(value or "").strip().lower()
    return normalized in {"si", "sí", "s", "true", "1", "yes"}


def _normalizar_payload(payload):
    data = payload.copy()

    if "detalle_sintomas" in data and "detalle_motivo" not in data:
        data["detalle_motivo"] = data.pop("detalle_sintomas")

    if "cesfam" in data and "centro_salud" not in data:
        data["centro_salud"] = data.pop("cesfam")

    # SaludBot no pregunta sexo ni flags clinico-sociales en este flujo inicial.
    data.setdefault("sexo", "N")
    data.setdefault("credendencial_cuidador_discapacidad", False)
    data.setdefault("Neurodivergente_prais_gestante", False)
    data.setdefault("credencial_cuidador_discapacidad_foto", "")
    data.setdefault("Neurodivergente_prais_gestante_tipo", "")
    data.setdefault("Neurodivergente_prais_gestante_otro", "")
    data.setdefault("acepta_terminos", False)

    if data.get("nombre"):
        data["nombre"] = " ".join(str(data["nombre"]).split())

    if data.get("rut"):
        data["rut"] = formatear_rut_sin_puntos(data["rut"])

    if data.get("telefono"):
        data["telefono"] = formatear_telefono_con_codigo_pais(data["telefono"])

    if "centro_salud" in data:
        data["centro_salud_id"] = data.pop("centro_salud")

    return data


@require_POST
def crear_solicitud(request):
    try:
        payload = _normalizar_payload(_json_body(request))
        payload["credendencial_cuidador_discapacidad"] = _bool_from_payload(
            payload.get("credendencial_cuidador_discapacidad")
        )
        payload["Neurodivergente_prais_gestante"] = _bool_from_payload(
            payload.get("Neurodivergente_prais_gestante")
        )
        payload["acepta_terminos"] = _bool_from_payload(payload.get("acepta_terminos"))

        if not payload["credendencial_cuidador_discapacidad"]:
            payload["credencial_cuidador_discapacidad_foto"] = ""

        if not payload["Neurodivergente_prais_gestante"]:
            payload["Neurodivergente_prais_gestante_tipo"] = ""
            payload["Neurodivergente_prais_gestante_otro"] = ""

        prioridad = calcular_prioridad(payload)
        payload["priorizacion_solicitud"] = prioridad["clasificacion"]
        payload["puntaje_prioridad"] = prioridad["puntaje"]

        solicitud = Solicitud(**payload)
        solicitud.full_clean()
        solicitud.save()
    except ValidationError as exc:
        return JsonResponse({"ok": False, "errors": exc.message_dict if hasattr(exc, "message_dict") else exc.messages}, status=400)
    except TypeError as exc:
        return JsonResponse({"ok": False, "errors": [str(exc)]}, status=400)

    return JsonResponse(
        {
            "ok": True,
            "id_solicitud": solicitud.id_solicitud,
            "priorizacion_solicitud": solicitud.priorizacion_solicitud,
            "puntaje_prioridad": solicitud.puntaje_prioridad,
            "resumen": {
                "nombre": solicitud.nombre,
                "rut": solicitud.rut,
                "edad": solicitud.edad,
                "telefono": solicitud.telefono,
                "centro_salud": solicitud.centro_salud_id,
                "centro_salud_nombre": solicitud.centro_salud.centro,
                "motivo": solicitud.motivo,
                "detalle_motivo": solicitud.detalle_motivo,
            },
        },
        status=201,
    )
