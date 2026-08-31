import re

from django.db import migrations


PATRON_SALUDO = re.compile(r"^\s*Hola[ ,]*\{nombre\}\s*[,.\-]?\s*", re.IGNORECASE)
CUERPO_ACEPTADA = (
    "Estamos intentando comunicarnos con usted para gestionar la asignacion de "
    "una hora de atencion de morbilidad. Por favor, responda este mensaje para "
    "continuar con la gestion."
)


def forwards(apps, schema_editor):
    PlantillaWhatsapp = apps.get_model("gestion", "PlantillaWhatsapp")
    MotivoRechazo = apps.get_model("gestion", "MotivoRechazo")
    PlantillaWhatsapp.objects.update_or_create(
        clave="aceptada",
        defaults={
            "descripcion": "Solicitud aceptada",
            "cuerpo": CUERPO_ACEPTADA,
            "activo": True,
        },
    )
    for motivo in MotivoRechazo.objects.all():
        limpio = PATRON_SALUDO.sub("", motivo.mensaje_paciente, count=1)
        if limpio != motivo.mensaje_paciente:
            motivo.mensaje_paciente = limpio.strip()
            motivo.save(update_fields=["mensaje_paciente"])


def backwards(apps, schema_editor):
    # No hay un respaldo exacto de los textos originales ni una marca que distinga
    # plantillas creadas por la migracion de ediciones posteriores hechas en admin.
    # Revertir datos aqui podria borrar configuracion valida o reescribir motivos.
    return None


class Migration(migrations.Migration):

    dependencies = [
        ('gestion', '0006_plantilla_whatsapp_y_help_text'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
