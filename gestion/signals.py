from django.db.models.signals import post_save
from django.dispatch import receiver

from solicitudes.models import Solicitud

from .models import Gestion


@receiver(post_save, sender=Solicitud)
def crear_gestion_para_solicitud(sender, instance, created, **kwargs):
    if created:
        Gestion.objects.get_or_create(solicitud=instance)
