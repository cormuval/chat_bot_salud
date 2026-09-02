from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    # Login institucional con Google. Vive solo en este urlconf: el host
    # publico del chatbot no expone rutas de autenticacion.
    path("oidc/", include("mozilla_django_oidc.urls")),
    path("admin/", admin.site.urls),
    path("", include("gestion.urls")),
]

handler404 = "gestion.views.pagina_no_encontrada"
