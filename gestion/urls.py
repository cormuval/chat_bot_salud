from django.urls import path

from . import views

app_name = "gestion"

urlpatterns = [
    path("", views.panel, name="panel"),
    path("sin-acceso/", views.sin_acceso, name="sin_acceso"),
    path("selector/", views.selector_lista, name="selector_lista"),
    path("selector/<int:pk>/", views.selector_detalle, name="selector_detalle"),
]
