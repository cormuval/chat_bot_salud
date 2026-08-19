from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management.color import no_style
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from gestion.auth import OIDCAuthenticationBackendGestion
from gestion.models import Gestion, MotivoRechazo, PerfilUsuario
from solicitudes.models import Centro, Solicitud


def crear_solicitud_base(**overrides):
    data = {
        "nombre": "Ana Maria Perez",
        "rut": "25747311-2",
        "edad": 34,
        "sexo": "N",
        "telefono": "+56949106239",
        "centro_salud": Centro.objects.get(pk=620),
        "acepta_terminos": True,
        "motivo": "consulta medica",
        "detalle_motivo": "dolor de garganta",
        "priorizacion_solicitud": Solicitud.Prioridad.BAJA,
        "puntaje_prioridad": 0,
    }
    data.update(overrides)
    return Solicitud.objects.create(**data)


class PerfilUsuarioTests(TestCase):
    def setUp(self):
        self.centro = Centro.objects.get(pk=620)
        self.satelite = Centro.objects.get(pk=626)

    def _perfil(self, rol, correo, satelite=None):
        usuario = User.objects.create_user(correo, email=correo)
        return PerfilUsuario.objects.create(
            usuario=usuario,
            rol=rol,
            centro=self.centro,
            centro_satelite=satelite,
        )

    def test_perfil_arranca_activo(self):
        perfil = self._perfil(PerfilUsuario.Rol.SELECTOR, "selector@example.com")
        self.assertTrue(perfil.activo)
        self.assertEqual(perfil.usuario.perfil_gestion, perfil)

    def test_rol_de_centro_solo_ve_su_centro(self):
        perfil = self._perfil(PerfilUsuario.Rol.SELECTOR, "selector@example.com")
        self.assertFalse(perfil.ve_todos_los_centros)
        self.assertEqual([c.pk for c in perfil.centros_permitidos()], [620])

    def test_rol_de_centro_con_satelite_ve_ambos(self):
        perfil = self._perfil(
            PerfilUsuario.Rol.COMUNICADOR, "comunicador@example.com", satelite=self.satelite
        )
        self.assertEqual(sorted(c.pk for c in perfil.centros_permitidos()), [620, 626])

    def test_admin_y_supervisor_das_ven_todos_los_centros(self):
        admin = self._perfil(PerfilUsuario.Rol.ADMIN, "admin@example.com")
        das = self._perfil(PerfilUsuario.Rol.SUPERVISOR_DAS, "das@example.com")

        total = Centro.objects.count()
        for perfil in (admin, das):
            self.assertTrue(perfil.ve_todos_los_centros)
            self.assertEqual(perfil.centros_permitidos().count(), total)

    def test_supervisor_centro_no_ve_todos(self):
        perfil = self._perfil(PerfilUsuario.Rol.SUPERVISOR_CENTRO, "supervisor@example.com")
        self.assertFalse(perfil.ve_todos_los_centros)

    def test_un_usuario_no_puede_tener_dos_perfiles(self):
        perfil = self._perfil(PerfilUsuario.Rol.SELECTOR, "selector@example.com")
        # transaction.atomic es necesario: sin el, la IntegrityError deja la
        # transaccion del TestCase rota y falla el teardown.
        with self.assertRaises(IntegrityError), transaction.atomic():
            PerfilUsuario.objects.create(
                usuario=perfil.usuario,
                rol=PerfilUsuario.Rol.COMUNICADOR,
                centro=self.centro,
            )

    def test_los_siete_roles_estan_definidos(self):
        self.assertEqual(
            [rol.value for rol in PerfilUsuario.Rol],
            [
                "ADMIN",
                "SUPERVISOR_DAS",
                "SUPERVISOR_CENTRO",
                "SOME",
                "FULL",
                "SELECTOR",
                "COMUNICADOR",
            ],
        )


@override_settings(ALLOWED_HOSTS=["gestion.localhost", "testserver"], GESTION_HOST="gestion.localhost")
class HostRoutingTests(TestCase):
    def test_subdominio_gestion_resuelve_su_urlconf(self):
        # "/" ahora exige sesion, asi que probamos con "/sin-acceso/": vive en
        # urls_gestion, no requiere login, y su sola resolucion en 200 confirma
        # que el host de gestion esta usando ese urlconf y no el del chatbot.
        response = self.client.get("/sin-acceso/", HTTP_HOST="gestion.localhost")
        self.assertEqual(response.status_code, 200)
        self.assertIn("no tiene acceso", response.content.decode("utf-8").lower())

    def test_host_default_resuelve_chatbot(self):
        response = self.client.get("/", HTTP_HOST="testserver")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("construcción", response.content.decode("utf-8"))

    def test_url_del_chatbot_no_existe_en_subdominio_gestion(self):
        response = self.client.get("/terminos/", HTTP_HOST="gestion.localhost")
        self.assertEqual(response.status_code, 404)


OIDC_TEST_SETTINGS = {
    "GOOGLE_WORKSPACE_DOMAIN": "cmvalparaiso.cl",
    "OIDC_RP_CLIENT_ID": "test-client-id",
    "OIDC_RP_CLIENT_SECRET": "test-client-secret",
}


@override_settings(**OIDC_TEST_SETTINGS)
class BackendVerifyClaimsTests(TestCase):
    def setUp(self):
        self.backend = OIDCAuthenticationBackendGestion()

    def _claims(self, **overrides):
        base = {
            "email": "funcionario@cmvalparaiso.cl",
            "email_verified": True,
            "hd": "cmvalparaiso.cl",
        }
        base.update(overrides)
        return base

    def test_acepta_cuenta_del_dominio_institucional(self):
        self.assertTrue(self.backend.verify_claims(self._claims()))

    def test_rechaza_dominio_distinto(self):
        self.assertFalse(self.backend.verify_claims(self._claims(hd="otrodominio.cl")))

    def test_rechaza_cuenta_sin_claim_hd(self):
        claims = self._claims()
        del claims["hd"]
        self.assertFalse(self.backend.verify_claims(claims))

    def test_rechaza_correo_no_verificado(self):
        self.assertFalse(self.backend.verify_claims(self._claims(email_verified=False)))

    def test_rechaza_claims_sin_correo(self):
        claims = self._claims()
        del claims["email"]
        self.assertFalse(self.backend.verify_claims(claims))

    def test_rechaza_email_verified_como_string_false(self):
        # Google siempre manda booleano, pero el claim no deberia confiar en
        # la verdad de python de un string: "false" es truthy.
        self.assertFalse(
            self.backend.verify_claims(self._claims(email_verified="false"))
        )

    def test_acepta_dominio_con_distinta_capitalizacion(self):
        # GOOGLE_WORKSPACE_DOMAIN podria escribirse con mayusculas en el .env;
        # la comparacion no deberia depender de eso.
        self.assertTrue(self.backend.verify_claims(self._claims(hd="CMValparaiso.cl")))

    def test_get_userinfo_prioriza_el_hd_del_id_token(self):
        # Si alguien rompe el override de get_userinfo, la regla del dominio
        # se cae en silencio: este test cablea que get_userinfo() realmente
        # combina el payload (id token) con la respuesta de userinfo.
        payload = {"hd": "cmvalparaiso.cl", "email": "funcionario@cmvalparaiso.cl"}
        with patch(
            "mozilla_django_oidc.auth.OIDCAuthenticationBackend.get_userinfo",
            return_value={"email": "funcionario@cmvalparaiso.cl"},
        ):
            combinados = self.backend.get_userinfo("token-de-acceso", "id-token", payload)
        self.assertEqual(combinados["hd"], "cmvalparaiso.cl")

    def test_combinar_claims_prioriza_los_del_id_token(self):
        # El endpoint de userinfo no siempre trae "hd"; el ID token si, y viene
        # firmado por Google, asi que manda por sobre la respuesta de userinfo.
        combinados = self.backend._combinar_claims(
            {"email": "funcionario@cmvalparaiso.cl"},
            {"hd": "cmvalparaiso.cl", "email": "suplantado@otro.cl"},
        )
        self.assertEqual(combinados["hd"], "cmvalparaiso.cl")
        self.assertEqual(combinados["email"], "suplantado@otro.cl")


@override_settings(**OIDC_TEST_SETTINGS)
class BackendFiltroDePerfilTests(TestCase):
    def setUp(self):
        self.backend = OIDCAuthenticationBackendGestion()
        self.centro = Centro.objects.get(pk=620)
        self.claims = {
            "email": "funcionario@cmvalparaiso.cl",
            "email_verified": True,
            "hd": "cmvalparaiso.cl",
        }

    def _usuario(self, correo="funcionario@cmvalparaiso.cl"):
        return User.objects.create_user(correo, email=correo)

    def test_usuario_con_perfil_activo_entra(self):
        usuario = self._usuario()
        PerfilUsuario.objects.create(
            usuario=usuario, rol=PerfilUsuario.Rol.SELECTOR, centro=self.centro
        )
        self.assertEqual(list(self.backend.filter_users_by_claims(self.claims)), [usuario])

    def test_usuario_sin_perfil_no_entra(self):
        self._usuario()
        self.assertEqual(list(self.backend.filter_users_by_claims(self.claims)), [])

    def test_usuario_con_perfil_inactivo_no_entra(self):
        usuario = self._usuario()
        PerfilUsuario.objects.create(
            usuario=usuario,
            rol=PerfilUsuario.Rol.SELECTOR,
            centro=self.centro,
            activo=False,
        )
        self.assertEqual(list(self.backend.filter_users_by_claims(self.claims)), [])

    def test_correo_desconocido_no_entra(self):
        usuario = self._usuario("otro@cmvalparaiso.cl")
        PerfilUsuario.objects.create(
            usuario=usuario, rol=PerfilUsuario.Rol.SELECTOR, centro=self.centro
        )
        self.assertEqual(list(self.backend.filter_users_by_claims(self.claims)), [])

    def test_claims_sin_correo_no_entra(self):
        self.assertEqual(list(self.backend.filter_users_by_claims({})), [])

    def test_usuario_inactivo_no_entra(self):
        # User.is_active=False y PerfilUsuario.activo=True se ven identicos
        # ("activo") en el admin en espanol: es facil desmarcar el que no es.
        usuario = self._usuario()
        usuario.is_active = False
        usuario.save()
        PerfilUsuario.objects.create(
            usuario=usuario, rol=PerfilUsuario.Rol.SELECTOR, centro=self.centro
        )
        self.assertEqual(list(self.backend.filter_users_by_claims(self.claims)), [])


@override_settings(**OIDC_TEST_SETTINGS)
class BackendUpdateUserTests(TestCase):
    def setUp(self):
        self.backend = OIDCAuthenticationBackendGestion()

    def test_update_user_sincroniza_nombre_y_apellido_desde_los_claims(self):
        usuario = User.objects.create_user(
            "funcionario@cmvalparaiso.cl", email="funcionario@cmvalparaiso.cl"
        )
        self.backend.update_user(usuario, {"given_name": "Ana", "family_name": "Perez"})

        usuario.refresh_from_db()
        self.assertEqual(usuario.first_name, "Ana")
        self.assertEqual(usuario.last_name, "Perez")


@override_settings(ALLOWED_HOSTS=["gestion.localhost", "testserver"], GESTION_HOST="gestion.localhost")
class RutasDeLoginTests(TestCase):
    def test_ruta_de_login_existe_en_el_subdominio(self):
        response = self.client.get("/oidc/authenticate/", HTTP_HOST="gestion.localhost")
        # Redirige al consentimiento de Google.
        self.assertEqual(response.status_code, 302)
        self.assertIn("accounts.google.com", response["Location"])

    def test_ruta_de_login_no_existe_en_el_host_publico(self):
        response = self.client.get("/oidc/authenticate/", HTTP_HOST="testserver")
        self.assertEqual(response.status_code, 404)

    def test_admin_no_existe_en_el_host_publico(self):
        response = self.client.get("/admin/", HTTP_HOST="testserver")
        self.assertEqual(response.status_code, 404)

    def test_admin_existe_en_el_subdominio_de_gestion(self):
        response = self.client.get("/admin/", HTTP_HOST="gestion.localhost")
        # Sin sesion, el admin redirige a su propio login.
        self.assertEqual(response.status_code, 302)

    def test_sin_acceso_responde_200(self):
        response = self.client.get("/sin-acceso/", HTTP_HOST="gestion.localhost")
        self.assertEqual(response.status_code, 200)
        self.assertIn("no tiene acceso", response.content.decode("utf-8").lower())


@override_settings(ALLOWED_HOSTS=["gestion.localhost", "testserver"], GESTION_HOST="gestion.localhost")
class PanelRequiereLoginTests(TestCase):
    def setUp(self):
        self.centro = Centro.objects.get(pk=620)

    def test_anonimo_es_redirigido_al_login(self):
        response = self.client.get("/", HTTP_HOST="gestion.localhost")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/oidc/authenticate/", response["Location"])

    def test_usuario_con_perfil_ve_el_panel(self):
        usuario = User.objects.create_user(
            "funcionario@cmvalparaiso.cl", email="funcionario@cmvalparaiso.cl"
        )
        PerfilUsuario.objects.create(
            usuario=usuario, rol=PerfilUsuario.Rol.SELECTOR, centro=self.centro
        )
        self.client.force_login(usuario)

        response = self.client.get("/", HTTP_HOST="gestion.localhost")
        self.assertEqual(response.status_code, 200)
        self.assertIn("construcción", response.content.decode("utf-8"))

    def test_usuario_sin_perfil_no_ve_el_panel(self):
        usuario = User.objects.create_user(
            "colado@cmvalparaiso.cl", email="colado@cmvalparaiso.cl"
        )
        self.client.force_login(usuario)

        response = self.client.get("/", HTTP_HOST="gestion.localhost")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/sin-acceso/", response["Location"])

    def test_usuario_con_is_active_false_no_ve_el_panel(self):
        # mozilla_django_oidc sobreescribe get_user() sin llamar a
        # user_can_authenticate(): desmarcar User.is_active en el admin no
        # alcanza para cortar una sesion ya iniciada si no lo chequeamos aca.
        usuario = User.objects.create_user(
            "revocado@cmvalparaiso.cl", email="revocado@cmvalparaiso.cl"
        )
        PerfilUsuario.objects.create(
            usuario=usuario, rol=PerfilUsuario.Rol.SELECTOR, centro=self.centro
        )
        self.client.force_login(usuario)

        usuario.is_active = False
        usuario.save()

        response = self.client.get("/", HTTP_HOST="gestion.localhost")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/sin-acceso/", response["Location"])


class GestionModeloTests(TestCase):

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        # InnoDB no revierte AUTO_INCREMENT al deshacer la transaccion de TestCase.
        sql = connection.ops.sequence_reset_by_name_sql(
            no_style(),
            [{"table": Solicitud._meta.db_table, "column": Solicitud._meta.pk.column}],
        )
        with connection.cursor() as cursor:
            for sentencia in sql:
                cursor.execute(sentencia)

    def setUp(self):
        self.centro = Centro.objects.get(pk=620)
        self.usuario = User.objects.create_user(
            "selector@cmvalparaiso.cl", email="selector@cmvalparaiso.cl"
        )
        self.motivo = MotivoRechazo.objects.create(
            nombre="Datos insuficientes",
            mensaje_paciente="Hola {nombre}, su solicitud no incluye informacion suficiente.",
            orden=10,
        )

    def test_senal_crea_gestion_pendiente_para_solicitud_nueva(self):
        solicitud = crear_solicitud_base()
        self.assertEqual(solicitud.gestion.decision, Gestion.Decision.PENDIENTE)

    def test_senal_no_duplica_gestion_al_actualizar_solicitud(self):
        solicitud = crear_solicitud_base()
        primera_id = solicitud.gestion.pk
        solicitud.detalle_motivo = "detalle actualizado"
        solicitud.save()
        self.assertEqual(Gestion.objects.filter(solicitud=solicitud).count(), 1)
        self.assertEqual(solicitud.gestion.pk, primera_id)

    def test_aceptar_exige_prioridad_clinica_y_limpia_rechazo(self):
        gestion = crear_solicitud_base().gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.ALTA)
        gestion.refresh_from_db()
        self.assertEqual(gestion.decision, Gestion.Decision.ACEPTADA)
        self.assertEqual(gestion.prioridad_clinica, Solicitud.Prioridad.ALTA)
        self.assertIsNone(gestion.motivo_rechazo)
        self.assertEqual(gestion.decidido_por, self.usuario)
        self.assertIsNotNone(gestion.fecha_decision)

    def test_rechazar_exige_motivo_y_limpia_prioridad_clinica(self):
        gestion = crear_solicitud_base().gestion
        gestion.rechazar(self.usuario, self.motivo)
        gestion.refresh_from_db()
        self.assertEqual(gestion.decision, Gestion.Decision.RECHAZADA)
        self.assertEqual(gestion.motivo_rechazo, self.motivo)
        self.assertEqual(gestion.prioridad_clinica, "")

    def test_no_aplica_sale_del_flujo_sin_datos_de_comunicador(self):
        gestion = crear_solicitud_base().gestion
        gestion.marcar_no_aplica(self.usuario)
        gestion.refresh_from_db()
        self.assertEqual(gestion.decision, Gestion.Decision.NO_APLICA)
        self.assertEqual(gestion.prioridad_clinica, "")
        self.assertIsNone(gestion.motivo_rechazo)

    def test_no_permite_aceptar_sin_prioridad(self):
        gestion = crear_solicitud_base().gestion
        with self.assertRaises(ValidationError):
            gestion.aceptar(self.usuario, "")

    def test_no_permite_rechazar_sin_motivo(self):
        gestion = crear_solicitud_base().gestion
        with self.assertRaises(ValidationError):
            gestion.rechazar(self.usuario, None)

    def test_registrar_no_contesta_suma_intento_sin_cerrar(self):
        gestion = crear_solicitud_base().gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)
        gestion.registrar_no_contesta(self.usuario)
        gestion.refresh_from_db()
        self.assertEqual(gestion.intentos_contacto, 1)
        self.assertIsNotNone(gestion.fecha_ultimo_intento)
        self.assertIsNone(gestion.cerrada_en)

    def test_url_whatsapp_reemplaza_nombre_y_codifica_mensaje(self):
        gestion = crear_solicitud_base(nombre="Ana Perez").gestion
        gestion.rechazar(self.usuario, self.motivo)
        url = gestion.url_whatsapp()
        self.assertTrue(url.startswith("https://wa.me/56949106239?text="))
        self.assertIn("Ana+Perez", url)

    def test_url_whatsapp_none_con_telefono_invalido(self):
        gestion = crear_solicitud_base(telefono="").gestion
        gestion.rechazar(self.usuario, self.motivo)
        self.assertIsNone(gestion.url_whatsapp())

    def test_rechazados_vencidos_usa_fecha_decision_mas_24_horas(self):
        gestion = crear_solicitud_base().gestion
        gestion.rechazar(self.usuario, self.motivo)
        Gestion.objects.filter(pk=gestion.pk).update(
            fecha_decision=timezone.now() - timedelta(hours=25)
        )
        self.assertEqual(list(Gestion.objects.rechazados_vencidos()), [gestion])
