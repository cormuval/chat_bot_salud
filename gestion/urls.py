from django.urls import path

from . import views

app_name = "gestion"

urlpatterns = [
    path("", views.panel, name="panel"),
    path("sin-acceso/", views.sin_acceso, name="sin_acceso"),
    path("admin-panel/", views.admin_panel, name="admin_panel"),
    path("login/", views.login, name="login"),
    path("selector/", views.selector_lista, name="selector_lista"),
    path("selector/<int:pk>/", views.selector_detalle, name="selector_detalle"),
    path("comunicador/", views.comunicador_lista, name="comunicador_lista"),
    path("comunicador/<int:pk>/", views.comunicador_detalle, name="comunicador_detalle"),
    path("comunicador/<int:pk>/whatsapp/", views.registrar_whatsapp, name="whatsapp"),
]
