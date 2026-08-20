URGENT_KEYWORDS = [
    "dolor pecho",
    "dificultad respiratoria",
    "falta de aire",
    "convulsion",
    "desmayo",
    "sangrado",
    "embarazo",
    "gestante",
    "suicida",
]

MODERATE_KEYWORDS = [
    "fiebre",
    "dolor intenso",
    "vomitos",
    "diarrea",
    "infeccion",
    "herida",
]


def _contains_any(text, keywords):
    normalized = (text or "").lower()
    return any(keyword in normalized for keyword in keywords)


def _first_keyword(text, keywords):
    normalized = (text or "").lower()
    for keyword in keywords:
        if keyword in normalized:
            return keyword
    return ""


def desglosar_prioridad(datos):
    edad = int(datos.get("edad") or 0)
    clinical_text = f"{datos.get('motivo', '')} {datos.get('detalle_motivo', '')}"
    factores = []

    palabra_urgente = _first_keyword(clinical_text, URGENT_KEYWORDS)
    if palabra_urgente:
        factores.append(
            {
                "codigo": "palabra_urgente",
                "descripcion": f'palabra clave "{palabra_urgente}"',
                "puntaje": 4,
            }
        )

    palabra_moderada = _first_keyword(clinical_text, MODERATE_KEYWORDS)
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
