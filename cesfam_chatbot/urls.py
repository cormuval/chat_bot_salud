from django.urls import path

from solicitudes import views


urlpatterns = [
    path("", views.saludbot, name="home"),
    path("chatbot/", views.chatbot, name="chatbot"),
    path("saludbot/", views.saludbot, name="saludbot"),
    path("terminos/", views.terminos, name="terminos"),
    path("api/solicitudes/", views.crear_solicitud, name="crear_solicitud"),
]

handler404 = views.pagina_no_encontrada
