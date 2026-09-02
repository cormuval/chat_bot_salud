from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import PalabraClavePrioridad
from .priorizacion import CACHE_PALABRAS


@receiver([post_save, post_delete], sender=PalabraClavePrioridad)
def invalidar_cache_palabras(sender, **kwargs):
    cache.delete(CACHE_PALABRAS)
