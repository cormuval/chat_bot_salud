from django.core.cache import cache

from .texto import normalizar

CACHE_PALABRAS = "solicitudes_palabras_prioridad_v1"

# Red de seguridad: aunque las senales invalidan el cache al editar una palabra,
# LocMemCache es por worker; un TTL corto asegura que cualquier worker que se
# pierda la senal se auto-sane. Editar palabras es raro, 5 min de desfase es
# despreciable para el triaje.
CACHE_PALABRAS_TTL = 300


def palabras_por_nivel():
    """Palabras activas agrupadas por nivel, en forma normalizada. Cacheadas;
    la cache se invalida al guardar o borrar una palabra (ver signals.py)."""
    data = cache.get(CACHE_PALABRAS)
    if data is None:
        from .models import PalabraClavePrioridad

        data = {"URGENTE": [], "MODERADA": []}
        for texto_norm, nivel in PalabraClavePrioridad.objects.filter(
            activo=True
        ).values_list("texto_normalizado", "nivel"):
            data.setdefault(nivel, []).append(texto_norm)
        cache.set(CACHE_PALABRAS, data, CACHE_PALABRAS_TTL)
    return data


def _primera_coincidencia(texto, palabras_normalizadas):
    normal = normalizar(texto)
    for palabra in palabras_normalizadas:
        if palabra in normal:
            return palabra
    return ""


def desglosar_prioridad(datos):
    edad = int(datos.get("edad") or 0)
    clinical_text = f"{datos.get('motivo', '')} {datos.get('detalle_motivo', '')}"
    factores = []

    palabras = palabras_por_nivel()

    palabra_urgente = _primera_coincidencia(clinical_text, palabras["URGENTE"])
    if palabra_urgente:
        factores.append(
            {
                "codigo": "palabra_urgente",
                "descripcion": f'palabra clave "{palabra_urgente}"',
                "puntaje": 4,
            }
        )

    palabra_moderada = _primera_coincidencia(clinical_text, palabras["MODERADA"])
    if palabra_moderada:
        factores.append(
            {
                "codigo": "palabra_moderada",
                "descripcion": f'palabra clave "{palabra_moderada}"',
                "puntaje": 1,
            }
        )

    if edad <= 5 or edad >= 65:
        factores.append(
            {"codigo": "edad", "descripcion": f"edad {edad} anos", "puntaje": 2}
        )

    if bool(datos.get("credendencial_cuidador_discapacidad")):
        factores.append(
            {
                "codigo": "credencial",
                "descripcion": "credencial de cuidador",
                "puntaje": 2,
            }
        )

    if bool(datos.get("Neurodivergente_prais_gestante")):
        factores.append(
            {
                "codigo": "condicion",
                "descripcion": "condicion declarada",
                "puntaje": 2,
            }
        )

    return factores


def calcular_prioridad(datos):
    puntaje = sum(factor["puntaje"] for factor in desglosar_prioridad(datos))

    if puntaje >= 6:
        clasificacion = "URGENTE"
        etiqueta = "Urgente"
    elif puntaje >= 4:
        clasificacion = "ALTA"
        etiqueta = "Alta"
    elif puntaje >= 2:
        clasificacion = "MEDIA"
        etiqueta = "Media"
    else:
        clasificacion = "BAJA"
        etiqueta = "Baja"

    return {
        "puntaje": puntaje,
        "clasificacion": clasificacion,
        "etiqueta": etiqueta,
    }
