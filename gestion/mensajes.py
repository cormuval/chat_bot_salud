import re
from urllib.parse import quote_plus

from .models import PlantillaWhatsapp


def cuerpo_whatsapp_para_gestion(gestion):
    if gestion.motivo_rechazo_id:
        return gestion.motivo_rechazo.mensaje_paciente
    return PlantillaWhatsapp.obtener_cuerpo_activo("aceptada")


def armar_mensaje_whatsapp(gestion, cuerpo):
    # El cuerpo es editable y puede arrastrar el marcador {nombre} desde una
    # plantilla o un motivo de rechazo. Se sustituye aca para que nunca salga
    # crudo al paciente, igual que hacia el codigo previo a la unificacion.
    cuerpo_limpio = " ".join((cuerpo or "").split())
    cuerpo_limpio = cuerpo_limpio.replace("{nombre}", gestion.solicitud.nombre)
    return (
        f"Hola, {gestion.solicitud.nombre}. Somos del "
        f"{gestion.solicitud.centro_salud}.\n"
        f"{cuerpo_limpio}\n"
        "Muchas gracias."
    )


def url_whatsapp_para_gestion(gestion, cuerpo=None):
    telefono = gestion.solicitud.telefono
    if not re.fullmatch(r"\+569\d{8}", telefono):
        return None
    cuerpo_final = cuerpo if cuerpo is not None else cuerpo_whatsapp_para_gestion(gestion)
    mensaje = armar_mensaje_whatsapp(gestion, cuerpo_final)
    return f"https://wa.me/{telefono.removeprefix('+')}?text={quote_plus(mensaje)}"
