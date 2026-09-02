from django.apps import AppConfig


class SolicitudesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "solicitudes"

    def ready(self):
        from . import signals  # noqa: F401
