from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from gestion.models import Gestion


class Command(BaseCommand):
    help = "Cierra automaticamente solicitudes rechazadas hace 24 horas."

    def handle(self, *args, **options):
        ahora = timezone.now()
        cerradas = 0
        with transaction.atomic():
            for gestion in Gestion.objects.rechazados_vencidos(ahora).select_for_update():
                gestion.cerrar_rechazado_automatico(ahora)
                cerradas += 1
        self.stdout.write(self.style.SUCCESS(f"{cerradas} rechazado(s) cerrados."))
