from django.db import migrations

from solicitudes.texto import normalizar

URGENTES = [
    "dolor pecho", "dificultad respiratoria", "falta de aire", "convulsion",
    "desmayo", "sangrado", "embarazo", "gestante", "suicida",
]
MODERADAS = [
    "fiebre", "dolor intenso", "vomitos", "diarrea", "infeccion", "herida",
]


def sembrar(apps, schema_editor):
    Palabra = apps.get_model("solicitudes", "PalabraClavePrioridad")
    for texto in URGENTES:
        Palabra.objects.get_or_create(
            texto_normalizado=normalizar(texto),
            defaults={"texto": texto, "nivel": "URGENTE", "activo": True},
        )
    for texto in MODERADAS:
        Palabra.objects.get_or_create(
            texto_normalizado=normalizar(texto),
            defaults={"texto": texto, "nivel": "MODERADA", "activo": True},
        )


def revertir(apps, schema_editor):
    Palabra = apps.get_model("solicitudes", "PalabraClavePrioridad")
    normalizados = [normalizar(t) for t in URGENTES + MODERADAS]
    Palabra.objects.filter(texto_normalizado__in=normalizados).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("solicitudes", "0007_palabraclaveprioridad"),
    ]

    operations = [migrations.RunPython(sembrar, revertir)]
