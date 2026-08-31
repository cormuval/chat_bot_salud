from datetime import timedelta

from django import template
from django.utils import timezone

from gestion.models import Gestion
from solicitudes.priorizacion import desglosar_prioridad


register = template.Library()


@register.filter
def prioridad_css(valor):
    return f"prioridad--{str(valor or '').lower()}"


@register.filter
def tiempo_relativo(fecha):
    if not fecha:
        return "-"
    delta = timezone.now() - fecha
    if delta < timedelta(minutes=1):
        return "recien"
    if delta < timedelta(hours=1):
        return f"hace {max(1, int(delta.total_seconds() // 60))} min"
    if delta < timedelta(days=1):
        return f"hace {int(delta.total_seconds() // 3600)} h"
    return f"hace {delta.days} d"


@register.filter
def horas_restantes_rechazo(gestion):
    if (
        gestion.decision != Gestion.Decision.RECHAZADA
        or gestion.fecha_decision is None
        or gestion.cerrada_en is not None
    ):
        return ""
    vence = gestion.fecha_decision + timedelta(hours=24)
    restante = vence - timezone.now()
    if restante.total_seconds() <= 0:
        return "plazo vencido"
    horas = int(restante.total_seconds() // 3600)
    if horas >= 1:
        return f"quedan {horas} h para avisar"
    minutos = max(1, int(restante.total_seconds() // 60))
    return f"quedan {minutos} min para avisar"


@register.filter
def telefono_whatsapp_valido(gestion):
    return bool(gestion.url_whatsapp())


@register.filter
def mensaje_whatsapp_previo(gestion):
    from gestion.mensajes import armar_mensaje_whatsapp, cuerpo_whatsapp_para_gestion

    return armar_mensaje_whatsapp(gestion, cuerpo_whatsapp_para_gestion(gestion))


@register.filter
def cuerpo_whatsapp_previo(gestion):
    from gestion.mensajes import cuerpo_whatsapp_para_gestion

    return cuerpo_whatsapp_para_gestion(gestion)


@register.filter
def desglose_prioridad(solicitud):
    return desglosar_prioridad(
        {
            "motivo": solicitud.motivo,
            "detalle_motivo": solicitud.detalle_motivo,
            "edad": solicitud.edad,
            "credendencial_cuidador_discapacidad": solicitud.credendencial_cuidador_discapacidad,
            "Neurodivergente_prais_gestante": solicitud.Neurodivergente_prais_gestante,
        }
    )
