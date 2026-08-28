from datetime import timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.color import no_style
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.http import Http404
from django.test import TestCase, TransactionTestCase, override_settings
from django.template import Context, Template
from django.utils import timezone

from gestion.auth import OIDCAuthenticationBackendGestion
from gestion.models import (
    Gestion,
    MotivoRechazo,
    PerfilUsuario,
    PlantillaWhatsapp,
    RegistroContacto,
)
from gestion.permisos import (
    gestion_alcanzable_o_404,
    puede_escribir_comunicador,
    puede_escribir_selector,
    puede_usar_comunicador,
    puede_usar_selector,
    puede_ver_no_aplica,
)
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


class PermisosGestionTests(TestCase):
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
        self.otro_centro = Centro.objects.get(pk=621)

    def _perfil(self, rol, centro=None):
        usuario = User.objects.create_user(
            f"{rol.lower()}-{User.objects.count()}@cmvalparaiso.cl"
        )
        return PerfilUsuario.objects.create(
            usuario=usuario,
            rol=rol,
            centro=centro or self.centro,
        )

    def test_roles_de_escritura_selector(self):
        roles_si = [PerfilUsuario.Rol.SELECTOR, PerfilUsuario.Rol.FULL, PerfilUsuario.Rol.SOME]
        roles_no = [
            PerfilUsuario.Rol.COMUNICADOR,
            PerfilUsuario.Rol.SUPERVISOR_CENTRO,
            PerfilUsuario.Rol.SUPERVISOR_DAS,
            PerfilUsuario.Rol.ADMIN,
        ]
        for rol in roles_si:
            self.assertTrue(puede_escribir_selector(self._perfil(rol)))
        for rol in roles_no:
            self.assertFalse(puede_escribir_selector(self._perfil(rol)))

    def test_roles_de_escritura_comunicador(self):
        roles_si = [PerfilUsuario.Rol.COMUNICADOR, PerfilUsuario.Rol.FULL, PerfilUsuario.Rol.SOME]
        roles_no = [
            PerfilUsuario.Rol.SELECTOR,
            PerfilUsuario.Rol.SUPERVISOR_CENTRO,
            PerfilUsuario.Rol.SUPERVISOR_DAS,
            PerfilUsuario.Rol.ADMIN,
        ]
        for rol in roles_si:
            self.assertTrue(puede_escribir_comunicador(self._perfil(rol)))
        for rol in roles_no:
            self.assertFalse(puede_escribir_comunicador(self._perfil(rol)))

    def test_supervisores_y_admin_pueden_usar_pantallas_en_solo_lectura(self):
        for rol in [PerfilUsuario.Rol.SUPERVISOR_CENTRO, PerfilUsuario.Rol.SUPERVISOR_DAS, PerfilUsuario.Rol.ADMIN]:
            perfil = self._perfil(rol)
            self.assertTrue(puede_usar_selector(perfil))
            self.assertTrue(puede_usar_comunicador(perfil))
            self.assertFalse(puede_escribir_selector(perfil))
            self.assertFalse(puede_escribir_comunicador(perfil))

    def test_selector_no_usa_comunicador_y_comunicador_no_usa_selector(self):
        self.assertTrue(puede_usar_selector(self._perfil(PerfilUsuario.Rol.SELECTOR)))
        self.assertFalse(puede_usar_comunicador(self._perfil(PerfilUsuario.Rol.SELECTOR)))
        self.assertFalse(puede_usar_selector(self._perfil(PerfilUsuario.Rol.COMUNICADOR)))
        self.assertTrue(puede_usar_comunicador(self._perfil(PerfilUsuario.Rol.COMUNICADOR)))

    def test_roles_que_ven_no_aplica(self):
        for rol in [PerfilUsuario.Rol.SELECTOR, PerfilUsuario.Rol.FULL, PerfilUsuario.Rol.SOME, PerfilUsuario.Rol.SUPERVISOR_CENTRO, PerfilUsuario.Rol.SUPERVISOR_DAS, PerfilUsuario.Rol.ADMIN]:
            self.assertTrue(puede_ver_no_aplica(self._perfil(rol)))
        self.assertFalse(puede_ver_no_aplica(self._perfil(PerfilUsuario.Rol.COMUNICADOR)))

    def test_gestion_fuera_de_alcance_devuelve_404(self):
        gestion = crear_solicitud_base(centro_salud=self.otro_centro).gestion
        perfil = self._perfil(PerfilUsuario.Rol.SELECTOR, centro=self.centro)
        with self.assertRaises(Http404):
            gestion_alcanzable_o_404(perfil, gestion.pk)


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

    def test_logout_por_get_no_esta_permitido(self):
        # mozilla-django-oidc solo cierra sesion por POST; por GET responde 405.
        # Si algun dia se enlaza el logout con un <a href>, este test lo delata.
        response = self.client.get("/oidc/logout/", HTTP_HOST="gestion.localhost")
        self.assertEqual(response.status_code, 405)

    def test_logout_por_post_cierra_la_sesion(self):
        usuario = User.objects.create_user(
            username="selector", email="selector@cmvalparaiso.cl", password="x"
        )
        PerfilUsuario.objects.create(
            usuario=usuario,
            rol=PerfilUsuario.Rol.SELECTOR,
            centro=Centro.objects.get(pk=620),
        )
        self.client.force_login(usuario)

        # La cabecera debe ofrecer el logout como formulario POST, no como enlace.
        pagina = self.client.get("/selector/", HTTP_HOST="gestion.localhost")
        html = pagina.content.decode("utf-8")
        self.assertIn('action="/oidc/logout/"', html)
        self.assertNotIn('href="/oidc/logout/"', html)

        response = self.client.post("/oidc/logout/", HTTP_HOST="gestion.localhost")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/sin-acceso/")
        self.assertNotIn("_auth_user_id", self.client.session)


@override_settings(ALLOWED_HOSTS=["gestion.localhost", "testserver"], GESTION_HOST="gestion.localhost")
class PanelRequiereLoginTests(TestCase):
    def setUp(self):
        self.centro = Centro.objects.get(pk=620)

    def test_anonimo_es_redirigido_al_login(self):
        response = self.client.get("/", HTTP_HOST="gestion.localhost")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/oidc/authenticate/", response["Location"])

    def test_usuario_con_perfil_va_a_cola_selector(self):
        usuario = User.objects.create_user(
            "funcionario@cmvalparaiso.cl", email="funcionario@cmvalparaiso.cl"
        )
        PerfilUsuario.objects.create(
            usuario=usuario, rol=PerfilUsuario.Rol.SELECTOR, centro=self.centro
        )
        self.client.force_login(usuario)

        response = self.client.get("/", HTTP_HOST="gestion.localhost")
        self.assertRedirects(response, "/selector/", fetch_redirect_response=False)

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


@override_settings(ALLOWED_HOSTS=["gestion.localhost", "testserver"], GESTION_HOST="gestion.localhost")
class PanelRedireccionTests(TestCase):
    def setUp(self):
        self.centro = Centro.objects.get(pk=620)

    def _login(self, rol):
        usuario = User.objects.create_user(f"{rol.lower()}@cmvalparaiso.cl")
        PerfilUsuario.objects.create(usuario=usuario, rol=rol, centro=self.centro)
        self.client.force_login(usuario)

    def test_selector_va_a_cola_selector(self):
        self._login(PerfilUsuario.Rol.SELECTOR)
        response = self.client.get("/", HTTP_HOST="gestion.localhost")
        self.assertRedirects(response, "/selector/", fetch_redirect_response=False)

    def test_comunicador_va_a_tabla_comunicador(self):
        self._login(PerfilUsuario.Rol.COMUNICADOR)
        response = self.client.get("/", HTTP_HOST="gestion.localhost")
        self.assertRedirects(response, "/comunicador/", fetch_redirect_response=False)

    def test_full_va_a_cola_selector(self):
        self._login(PerfilUsuario.Rol.FULL)
        response = self.client.get("/", HTTP_HOST="gestion.localhost")
        self.assertRedirects(response, "/selector/", fetch_redirect_response=False)


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

    def test_registrar_no_contesta_crea_registro_contacto_de_llamada(self):
        gestion = crear_solicitud_base().gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)
        gestion.registrar_no_contesta(self.usuario, token_contacto="token-llamada")
        registro = gestion.registros_contacto.get()
        self.assertEqual(registro.canal, RegistroContacto.Canal.LLAMADA)
        self.assertEqual(registro.resultado, Gestion.AccionContacto.NO_CONTESTA)
        self.assertEqual(registro.usuario, self.usuario)
        self.assertEqual(registro.mensaje, "")

    def test_registrar_whatsapp_crea_registro_con_mensaje(self):
        gestion = crear_solicitud_base().gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)
        gestion.registrar_click_whatsapp(
            self.usuario,
            token_contacto="token-whatsapp",
            mensaje="Mensaje enviado.",
        )
        registro = gestion.registros_contacto.get()
        self.assertEqual(registro.canal, RegistroContacto.Canal.WHATSAPP)
        self.assertEqual(registro.resultado, Gestion.AccionContacto.WHATSAPP)
        self.assertEqual(registro.mensaje, "Mensaje enviado.")

    def test_token_duplicado_no_duplica_historial(self):
        gestion = crear_solicitud_base().gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)
        gestion.registrar_no_contesta(self.usuario, token_contacto="token-repetido")
        gestion.registrar_no_contesta(self.usuario, token_contacto="token-repetido")
        self.assertEqual(gestion.registros_contacto.count(), 1)

    def test_no_contesta_duplicado_no_suma_otro_intento(self):
        gestion = crear_solicitud_base().gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)

        gestion.registrar_no_contesta(self.usuario, token_contacto="token-repetido")
        gestion.registrar_no_contesta(self.usuario, token_contacto="token-repetido")

        gestion.refresh_from_db()
        self.assertEqual(gestion.intentos_contacto, 1)
        self.assertEqual(gestion.tokens_contacto.count(), 1)
        self.assertEqual(
            gestion.ultima_accion_contacto,
            Gestion.AccionContacto.NO_CONTESTA,
        )

    def test_reintento_tardio_no_reaplica_token_anterior(self):
        gestion = crear_solicitud_base().gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)

        gestion.registrar_no_contesta(self.usuario, token_contacto="token-uno")
        gestion.registrar_no_contesta(self.usuario, token_contacto="token-dos")
        gestion.registrar_no_contesta(self.usuario, token_contacto="token-uno")

        gestion.refresh_from_db()
        self.assertEqual(gestion.intentos_contacto, 2)
        self.assertEqual(gestion.tokens_contacto.count(), 2)

    def test_mismo_token_con_distinta_accion_aplica_ambas(self):
        gestion = crear_solicitud_base().gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)

        gestion.registrar_no_contesta(self.usuario, token_contacto="token-compartido")
        gestion.registrar_click_whatsapp(
            self.usuario, token_contacto="token-compartido"
        )

        gestion.refresh_from_db()
        self.assertEqual(gestion.intentos_contacto, 2)
        self.assertEqual(gestion.tokens_contacto.count(), 2)
        self.assertIsNotNone(gestion.aviso_whatsapp_en)

    def test_click_whatsapp_duplicado_no_suma_otro_intento(self):
        gestion = crear_solicitud_base().gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)
        gestion.registrar_click_whatsapp(
            self.usuario, token_contacto="token-whatsapp"
        )
        gestion.registrar_click_whatsapp(
            self.usuario, token_contacto="token-whatsapp"
        )
        gestion.refresh_from_db()
        self.assertEqual(gestion.intentos_contacto, 1)
        self.assertIsNotNone(gestion.aviso_whatsapp_en)

    def test_cierre_duplicado_no_suma_otro_intento(self):
        gestion = crear_solicitud_base().gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)
        gestion.registrar_no_acepta(
            self.usuario, token_contacto="token-cierre"
        )
        gestion.registrar_no_acepta(
            self.usuario, token_contacto="token-cierre"
        )
        gestion.refresh_from_db()
        self.assertEqual(gestion.intentos_contacto, 1)
        self.assertEqual(gestion.motivo_cierre, Gestion.MotivoCierre.NO_ACEPTA)

    def test_agendada_exige_fecha_hora(self):
        gestion = crear_solicitud_base().gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)
        with self.assertRaises(ValidationError):
            gestion.registrar_agendada(self.usuario, None)
        gestion.refresh_from_db()
        self.assertIsNone(gestion.cerrada_en)
        self.assertIsNone(gestion.fecha_hora_citacion)

    def test_url_whatsapp_reemplaza_nombre_y_codifica_mensaje(self):
        gestion = crear_solicitud_base(nombre="Ana Perez").gestion
        gestion.rechazar(self.usuario, self.motivo)
        url = gestion.url_whatsapp()
        self.assertTrue(url.startswith("https://wa.me/56949106239?text="))
        self.assertIn("Ana+Perez", url)

    def test_url_whatsapp_aceptada_usa_plantilla_activa_y_partes_fijas(self):
        PlantillaWhatsapp.objects.update_or_create(
            clave="aceptada",
            defaults={
                "descripcion": "Aceptada",
                "cuerpo": "Estamos intentando comunicarnos con usted.",
            },
        )
        gestion = crear_solicitud_base(nombre="Ana Perez").gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)
        url = gestion.url_whatsapp()
        self.assertTrue(url.startswith("https://wa.me/56949106239?text="))
        self.assertIn("Hola%2C+Ana+Perez.", url)
        self.assertIn("Estamos+intentando+comunicarnos+con+usted.", url)
        self.assertIn("Muchas+gracias.", url)

    def test_url_whatsapp_rechazada_usa_motivo_como_cuerpo_sin_duplicar_saludo(self):
        self.motivo.mensaje_paciente = "Faltan datos para continuar."
        self.motivo.save(update_fields=["mensaje_paciente"])
        gestion = crear_solicitud_base(nombre="Ana Perez").gestion
        gestion.rechazar(self.usuario, self.motivo)
        url = gestion.url_whatsapp()
        self.assertIn("Hola%2C+Ana+Perez.", url)
        self.assertIn("Faltan+datos+para+continuar.", url)
        self.assertEqual(url.count("Hola"), 1)

    def test_url_whatsapp_no_falla_con_marcador_desconocido(self):
        self.motivo.mensaje_paciente = "Hola {nombre}, centro {centro}."
        self.motivo.save(update_fields=["mensaje_paciente"])
        gestion = crear_solicitud_base(nombre="Ana Perez").gestion
        gestion.rechazar(self.usuario, self.motivo)

        url = gestion.url_whatsapp()

        self.assertIn("Ana+Perez", url)
        self.assertIn("%7Bcentro%7D", url)

    def test_url_whatsapp_none_con_telefono_invalido(self):
        gestion = crear_solicitud_base(telefono="").gestion
        gestion.rechazar(self.usuario, self.motivo)
        self.assertIsNone(gestion.url_whatsapp())

    def test_url_whatsapp_none_con_telefono_chileno_invalido(self):
        gestion = crear_solicitud_base(telefono="123").gestion
        gestion.rechazar(self.usuario, self.motivo)
        self.assertIsNone(gestion.url_whatsapp())

    def test_rechazados_vencidos_usa_fecha_decision_mas_24_horas(self):
        gestion = crear_solicitud_base().gestion
        gestion.rechazar(self.usuario, self.motivo)
        Gestion.objects.filter(pk=gestion.pk).update(
            fecha_decision=timezone.now() - timedelta(hours=25)
        )
        self.assertEqual(list(Gestion.objects.rechazados_vencidos()), [gestion])


class GestionConcurrenciaTests(TransactionTestCase):
    serialized_rollback = True

    def setUp(self):
        self.selector = User.objects.create_user("selector-concurrencia")
        self.comunicador = User.objects.create_user("comunicador-concurrencia")
        self.motivo = MotivoRechazo.objects.create(
            nombre="Datos insuficientes",
            mensaje_paciente="Hola {nombre}, faltan datos.",
        )

    def test_selector_obsoleto_no_sobrescribe_intento_del_comunicador(self):
        gestion = crear_solicitud_base().gestion
        gestion.aceptar(self.selector, Solicitud.Prioridad.MEDIA)
        selector_obsoleto = Gestion.objects.get(pk=gestion.pk)

        Gestion.objects.get(pk=gestion.pk).registrar_no_contesta(self.comunicador)

        with self.assertRaises(ValidationError):
            selector_obsoleto.rechazar(self.selector, self.motivo)

        gestion.refresh_from_db()
        self.assertEqual(gestion.decision, Gestion.Decision.ACEPTADA)
        self.assertEqual(gestion.intentos_contacto, 1)

    def test_dos_selectores_sin_contacto_conservan_ultimo_guardado(self):
        gestion = crear_solicitud_base().gestion
        primer_selector = Gestion.objects.get(pk=gestion.pk)
        segundo_selector = Gestion.objects.get(pk=gestion.pk)

        primer_selector.aceptar(self.selector, Solicitud.Prioridad.MEDIA)
        segundo_selector.rechazar(self.selector, self.motivo)

        gestion.refresh_from_db()
        self.assertEqual(gestion.decision, Gestion.Decision.RECHAZADA)
        self.assertEqual(gestion.motivo_rechazo, self.motivo)
        self.assertEqual(gestion.intentos_contacto, 0)

    def test_comunicador_obsoleto_conserva_cierre_automatico(self):
        gestion = crear_solicitud_base().gestion
        gestion.rechazar(self.selector, self.motivo)
        comunicador_obsoleto = Gestion.objects.get(pk=gestion.pk)
        momento_cierre = timezone.now()

        Gestion.objects.get(pk=gestion.pk).cerrar_rechazado_automatico(
            ahora=momento_cierre
        )
        comunicador_obsoleto.registrar_no_contesta(self.comunicador)

        gestion.refresh_from_db()
        self.assertEqual(gestion.cerrada_en, momento_cierre)
        self.assertEqual(gestion.motivo_cierre, Gestion.MotivoCierre.SIN_AVISO)
        self.assertEqual(gestion.intentos_contacto, 1)
        self.assertEqual(
            gestion.ultima_accion_contacto,
            Gestion.AccionContacto.NO_CONTESTA,
        )

    def test_comunicador_obsoleto_no_registra_intento_en_no_aplica(self):
        gestion = crear_solicitud_base().gestion
        gestion.aceptar(self.selector, Solicitud.Prioridad.MEDIA)
        comunicador_obsoleto = Gestion.objects.get(pk=gestion.pk)

        Gestion.objects.get(pk=gestion.pk).marcar_no_aplica(self.selector)

        with self.assertRaises(ValidationError):
            comunicador_obsoleto.registrar_no_contesta(
                self.comunicador, token_contacto="token-obsoleto"
            )

        gestion.refresh_from_db()
        self.assertEqual(gestion.decision, Gestion.Decision.NO_APLICA)
        self.assertEqual(gestion.intentos_contacto, 0)


@override_settings(ALLOWED_HOSTS=["gestion.localhost", "testserver"], GESTION_HOST="gestion.localhost")
class SelectorViewsTests(TestCase):
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
        self.otro_centro = Centro.objects.get(pk=621)
        self.usuario = User.objects.create_user(
            "selector@cmvalparaiso.cl", email="selector@cmvalparaiso.cl"
        )
        self.perfil = PerfilUsuario.objects.create(
            usuario=self.usuario,
            rol=PerfilUsuario.Rol.SELECTOR,
            centro=self.centro,
        )
        self.motivo = MotivoRechazo.objects.create(
            nombre="Datos insuficientes",
            mensaje_paciente="Hola {nombre}, faltan datos.",
        )
        self.client.force_login(self.usuario)

    def test_lista_muestra_solo_pendientes_del_centro_en_orden_admin(self):
        baja = crear_solicitud_base(
            centro_salud=self.centro,
            priorizacion_solicitud=Solicitud.Prioridad.BAJA,
        ).gestion
        urgente = crear_solicitud_base(
            centro_salud=self.centro,
            priorizacion_solicitud=Solicitud.Prioridad.URGENTE,
        ).gestion
        crear_solicitud_base(
            centro_salud=self.otro_centro,
            priorizacion_solicitud=Solicitud.Prioridad.URGENTE,
        )

        response = self.client.get("/selector/", HTTP_HOST="gestion.localhost")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["gestiones"]), [urgente, baja])

    def test_lista_permite_navegar_decididas_corregibles_y_no_aplica(self):
        pendiente = crear_solicitud_base(centro_salud=self.centro).gestion
        corregible = crear_solicitud_base(
            centro_salud=self.centro, nombre="Caso corregible"
        ).gestion
        corregible.aceptar(self.usuario, Solicitud.Prioridad.ALTA)
        contactada = crear_solicitud_base(
            centro_salud=self.centro, nombre="Caso contactado"
        ).gestion
        contactada.rechazar(self.usuario, self.motivo)
        contactada.registrar_no_contesta(self.usuario)
        no_aplica = crear_solicitud_base(centro_salud=self.centro).gestion
        no_aplica.marcar_no_aplica(self.usuario)

        response = self.client.get("/selector/", HTTP_HOST="gestion.localhost")
        self.assertEqual(list(response.context["gestiones"]), [pendiente])
        self.assertContains(response, "?seccion=decididas")
        self.assertContains(response, "?seccion=no_aplica")

        response = self.client.get(
            "/selector/?seccion=decididas", HTTP_HOST="gestion.localhost"
        )
        self.assertEqual(list(response.context["gestiones"]), [corregible])
        self.assertNotContains(response, contactada.solicitud.nombre)

        response = self.client.get(
            "/selector/?seccion=no_aplica", HTTP_HOST="gestion.localhost"
        )
        self.assertEqual(list(response.context["gestiones"]), [no_aplica])

    @patch("gestion.views.puede_ver_no_aplica", return_value=False)
    def test_lista_oculta_no_aplica_si_el_perfil_no_puede_verlo(self, _permiso):
        no_aplica = crear_solicitud_base(centro_salud=self.centro).gestion
        no_aplica.marcar_no_aplica(self.usuario)

        response = self.client.get("/selector/", HTTP_HOST="gestion.localhost")

        self.assertNotContains(response, "?seccion=no_aplica")
        response = self.client.get(
            "/selector/?seccion=no_aplica", HTTP_HOST="gestion.localhost"
        )
        self.assertEqual(response.context["seccion"], "pendientes")
        self.assertNotIn(no_aplica, response.context["gestiones"])

    def test_detalle_muestra_datos_clinicos_y_decision_en_solo_lectura(self):
        gestion = crear_solicitud_base(
            centro_salud=self.centro,
            edad=67,
            sexo=Solicitud.Sexo.FEMENINO,
            priorizacion_solicitud=Solicitud.Prioridad.URGENTE,
            credendencial_cuidador_discapacidad=True,
            credencial_cuidador_discapacidad_foto="data:image/png;base64,AAAA",
            Neurodivergente_prais_gestante=True,
            Neurodivergente_prais_gestante_tipo=Solicitud.TipoCondicion.OTRO,
            Neurodivergente_prais_gestante_otro="Condicion especial",
        ).gestion
        gestion.rechazar(self.usuario, self.motivo)
        self.perfil.rol = PerfilUsuario.Rol.SUPERVISOR_CENTRO
        self.perfil.save(update_fields=["rol"])

        response = self.client.get(
            f"/selector/{gestion.pk}/", HTTP_HOST="gestion.localhost"
        )

        self.assertEqual(response.status_code, 200)
        for contenido in (
            "67",
            "Femenino",
            str(self.centro),
            "Urgente",
            "Condicion especial",
            "Credencial declarada",
            "Foto adjunta",
            "Rechazada",
            self.motivo.nombre,
            self.usuario.email,
        ):
            self.assertContains(response, contenido)
        self.assertContains(response, "Fecha de decision")
        self.assertContains(response, "Vista de solo lectura")
        self.assertContains(response, "<img", html=False)
        self.assertContains(response, "data:image/png;base64,AAAA")

    def test_detalle_no_renderiza_foto_si_no_es_data_url_de_imagen(self):
        gestion = crear_solicitud_base(
            centro_salud=self.centro,
            credendencial_cuidador_discapacidad=True,
            credencial_cuidador_discapacidad_foto="javascript:alert(1)",
        ).gestion

        response = self.client.get(
            f"/selector/{gestion.pk}/", HTTP_HOST="gestion.localhost"
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<img", html=False)

    def test_aceptar_registra_prioridad_clinica(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        response = self.client.post(
            f"/selector/{gestion.pk}/",
            {
                "decision": Gestion.Decision.ACEPTADA,
                "prioridad_clinica": Solicitud.Prioridad.ALTA,
            },
            HTTP_HOST="gestion.localhost",
        )
        self.assertEqual(response.status_code, 302)
        gestion.refresh_from_db()
        self.assertEqual(gestion.decision, Gestion.Decision.ACEPTADA)
        self.assertEqual(gestion.prioridad_clinica, Solicitud.Prioridad.ALTA)

    def test_post_sin_fragmento_redirige_a_lista_y_no_devuelve_parcial(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion

        response = self.client.post(
            f"/selector/{gestion.pk}/",
            {"decision": Gestion.Decision.NO_APLICA},
            HTTP_HOST="gestion.localhost",
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, "/selector/")
        self.assertNotContains(
            response, 'data-fragment-kind="selector-detail"', status_code=302
        )

    def test_detalle_completo_usa_acciones_sin_fragmento(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion

        response = self.client.get(
            f"/selector/{gestion.pk}/", HTTP_HOST="gestion.localhost"
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "?fragmento=1")
        self.assertContains(
            response,
            f'action="/selector/{gestion.pk}/?seccion=pendientes"',
            html=False,
        )

    def test_detalle_completo_conserva_seccion_en_acciones_sin_javascript(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)

        response = self.client.get(
            f"/selector/{gestion.pk}/?seccion=decididas",
            HTTP_HOST="gestion.localhost",
        )

        self.assertContains(
            response,
            f'action="/selector/{gestion.pk}/?seccion=decididas"',
            html=False,
        )

    def test_rechazar_registra_motivo(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        response = self.client.post(
            f"/selector/{gestion.pk}/",
            {"decision": Gestion.Decision.RECHAZADA, "motivo_rechazo": self.motivo.pk},
            HTTP_HOST="gestion.localhost",
        )
        self.assertEqual(response.status_code, 302)
        gestion.refresh_from_db()
        self.assertEqual(gestion.decision, Gestion.Decision.RECHAZADA)
        self.assertEqual(gestion.motivo_rechazo, self.motivo)

    def test_no_aplica_no_llega_al_comunicador(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        response = self.client.post(
            f"/selector/{gestion.pk}/",
            {"decision": Gestion.Decision.NO_APLICA},
            HTTP_HOST="gestion.localhost",
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            Gestion.objects.tabla_comunicador(self.perfil).filter(pk=gestion.pk).exists()
        )

    def test_pendiente_es_una_decision_invalida(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        response = self.client.post(
            f"/selector/{gestion.pk}/",
            {"decision": Gestion.Decision.PENDIENTE},
            HTTP_HOST="gestion.localhost",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("decision", response.context["form"].errors)
        gestion.refresh_from_db()
        self.assertEqual(gestion.decision, Gestion.Decision.PENDIENTE)

    def test_no_permite_corregir_si_ya_hay_intento(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)
        gestion.registrar_no_contesta(self.usuario)
        response = self.client.post(
            f"/selector/{gestion.pk}/",
            {"decision": Gestion.Decision.NO_APLICA},
            HTTP_HOST="gestion.localhost",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ya hay intentos registrados")

    def test_no_permite_corregir_rechazo_vencido_por_url_directa(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        gestion.rechazar(self.usuario, self.motivo)
        Gestion.objects.filter(pk=gestion.pk).update(
            fecha_decision=timezone.now() - timedelta(hours=25)
        )

        response = self.client.post(
            f"/selector/{gestion.pk}/",
            {
                "decision": Gestion.Decision.ACEPTADA,
                "prioridad_clinica": Solicitud.Prioridad.ALTA,
            },
            HTTP_HOST="gestion.localhost",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "plazo de correccion")
        gestion.refresh_from_db()
        self.assertEqual(gestion.decision, Gestion.Decision.RECHAZADA)
        self.assertEqual(gestion.motivo_rechazo, self.motivo)

    def test_comunicador_no_puede_entrar_a_selector(self):
        self.perfil.rol = PerfilUsuario.Rol.COMUNICADOR
        self.perfil.save()
        response = self.client.get("/selector/", HTTP_HOST="gestion.localhost")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/sin-acceso/", response["Location"])

    def test_fragmento_selector_no_incluye_layout_y_respeta_permiso(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        response = self.client.get(
            f"/selector/{gestion.pk}/?fragmento=1",
            HTTP_HOST="gestion.localhost",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-fragment-kind="selector-detail"', html=False)
        self.assertNotContains(response, "<html", html=False)
        self.assertContains(response, "Guardar decision")

    def test_fragmento_selector_solo_lectura_no_muestra_controles(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        self.perfil.rol = PerfilUsuario.Rol.ADMIN
        self.perfil.save(update_fields=["rol"])
        response = self.client.get(
            f"/selector/{gestion.pk}/?fragmento=1",
            HTTP_HOST="gestion.localhost",
        )
        self.assertContains(response, "Vista de solo lectura")
        self.assertNotContains(response, "Aceptar urgente")

    def test_post_fragmento_selector_devuelve_siguiente_caso(self):
        primero = crear_solicitud_base(
            centro_salud=self.centro,
            priorizacion_solicitud=Solicitud.Prioridad.URGENTE,
            detalle_motivo="primer caso",
        ).gestion
        segundo = crear_solicitud_base(
            centro_salud=self.centro,
            priorizacion_solicitud=Solicitud.Prioridad.BAJA,
            detalle_motivo="segundo caso",
        ).gestion
        response = self.client.post(
            f"/selector/{primero.pk}/?fragmento=1",
            {"decision": Gestion.Decision.ACEPTADA, "prioridad_clinica": Solicitud.Prioridad.ALTA},
            HTTP_HOST="gestion.localhost",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-fragment-kind="selector-detail"', html=False)
        self.assertContains(response, f'data-current-row-id="{segundo.pk}"', html=False)
        self.assertContains(response, "Aceptada como Alta")

    def test_selector_lista_fragmento_devuelve_solo_region_refrescable(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        response = self.client.get(
            "/selector/?fragmento=1&seccion=pendientes",
            HTTP_HOST="gestion.localhost",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-fragment-kind="selector-table"', html=False)
        self.assertContains(response, f'data-row-id="{gestion.pk}"', html=False)
        self.assertNotContains(response, "<html", html=False)

    def test_post_fragmento_selector_no_expone_transicion_incremental(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        response = self.client.post(
            f"/selector/{gestion.pk}/?fragmento=1&seccion=pendientes",
            {
                "decision": Gestion.Decision.ACEPTADA,
                "prioridad_clinica": Solicitud.Prioridad.ALTA,
            },
            HTTP_HOST="gestion.localhost",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-fragment-kind="selector-empty"', html=False)
        self.assertNotContains(response, "data-selector-row-action", html=False)
        self.assertNotContains(response, "data-selector-correction-text", html=False)

    def test_post_fragmento_selector_desde_decididas_sigue_mostrando_caso_corregible(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)
        response = self.client.post(
            f"/selector/{gestion.pk}/?fragmento=1&seccion=decididas",
            {
                "decision": Gestion.Decision.RECHAZADA,
                "motivo_rechazo": self.motivo.pk,
            },
            HTTP_HOST="gestion.localhost",
        )

        self.assertContains(response, f'data-current-row-id="{gestion.pk}"', html=False)
        self.assertNotContains(response, "data-selector-row-action", html=False)
        self.assertContains(response, "quedan", html=False)

    def test_post_sin_fragmento_selector_redirige_a_seccion_de_origen(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)

        response = self.client.post(
            f"/selector/{gestion.pk}/?seccion=decididas",
            {
                "decision": Gestion.Decision.RECHAZADA,
                "motivo_rechazo": self.motivo.pk,
            },
            HTTP_HOST="gestion.localhost",
        )

        self.assertRedirects(
            response,
            "/selector/?seccion=decididas",
            fetch_redirect_response=False,
        )

    def test_post_fragmento_selector_ultimo_devuelve_cola_vacia(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        response = self.client.post(
            f"/selector/{gestion.pk}/?fragmento=1",
            {"decision": Gestion.Decision.NO_APLICA},
            HTTP_HOST="gestion.localhost",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-fragment-kind="selector-empty"', html=False)
        self.assertContains(response, "No quedan casos en esta seccion")

    def test_post_fragmento_selector_con_error_devuelve_mismo_parcial(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        response = self.client.post(
            f"/selector/{gestion.pk}/?fragmento=1",
            {"decision": Gestion.Decision.ACEPTADA},
            HTTP_HOST="gestion.localhost",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-current-row-id="%s"' % gestion.pk, html=False)
        self.assertContains(response, "Debe indicar prioridad clinica")

    def test_post_fragmento_selector_rechazo_invalido_muestra_error_y_reabre_detalle(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion

        response = self.client.post(
            f"/selector/{gestion.pk}/?fragmento=1",
            {"decision": Gestion.Decision.RECHAZADA},
            HTTP_HOST="gestion.localhost",
        )

        self.assertContains(response, "Debe indicar motivo de rechazo")
        self.assertContains(response, '<details class="reject-box" open>', html=False)
        self.assertContains(response, 'data-dialog-error-focus', html=False)

    def test_detalle_selector_completo_acepta_prioridad_sin_javascript(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion

        response = self.client.get(
            f"/selector/{gestion.pk}/",
            HTTP_HOST="gestion.localhost",
        )

        self.assertContains(
            response,
            'name="prioridad_clinica" value="ALTA"',
            html=False,
        )
        response = self.client.post(
            f"/selector/{gestion.pk}/",
            {
                "decision": Gestion.Decision.ACEPTADA,
                "prioridad_clinica": Solicitud.Prioridad.ALTA,
            },
            HTTP_HOST="gestion.localhost",
        )

        self.assertRedirects(response, "/selector/", fetch_redirect_response=False)
        gestion.refresh_from_db()
        self.assertEqual(gestion.decision, Gestion.Decision.ACEPTADA)
        self.assertEqual(gestion.prioridad_clinica, Solicitud.Prioridad.ALTA)


@override_settings(ALLOWED_HOSTS=["gestion.localhost", "testserver"], GESTION_HOST="gestion.localhost")
class ComunicadorViewsTests(TestCase):
    def setUp(self):
        self.centro = Centro.objects.get(pk=620)
        self.usuario = User.objects.create_user("comunicador@cmvalparaiso.cl", email="comunicador@cmvalparaiso.cl")
        self.perfil = PerfilUsuario.objects.create(
            usuario=self.usuario,
            rol=PerfilUsuario.Rol.COMUNICADOR,
            centro=self.centro,
        )
        self.motivo = MotivoRechazo.objects.create(
            nombre="Datos insuficientes",
            mensaje_paciente="Hola {nombre}, faltan datos.",
        )
        self.client.force_login(self.usuario)

    def test_tabla_ordena_aceptadas_por_prioridad_clinica_y_rechazadas_al_final(self):
        rechazada = crear_solicitud_base(centro_salud=self.centro).gestion
        rechazada.rechazar(self.usuario, self.motivo)
        baja = crear_solicitud_base(centro_salud=self.centro).gestion
        baja.aceptar(self.usuario, Solicitud.Prioridad.BAJA)
        urgente = crear_solicitud_base(centro_salud=self.centro).gestion
        urgente.aceptar(self.usuario, Solicitud.Prioridad.URGENTE)

        response = self.client.get("/comunicador/", HTTP_HOST="gestion.localhost")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["gestiones"]), [urgente, baja, rechazada])

    def test_no_contesta_suma_intento_y_deja_abierto(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)
        response = self.client.post(
            f"/comunicador/{gestion.pk}/",
            {"accion": "NO_CONTESTA"},
            HTTP_HOST="gestion.localhost",
        )
        self.assertEqual(response.status_code, 302)
        gestion.refresh_from_db()
        self.assertEqual(gestion.intentos_contacto, 1)
        self.assertIsNone(gestion.cerrada_en)

    def test_formularios_generan_tokens_distintos(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)

        response = self.client.get(
            f"/comunicador/{gestion.pk}/", HTTP_HOST="gestion.localhost"
        )

        token_contacto = response.context["form"]["token_contacto"].value()
        token_whatsapp = response.context["form_whatsapp"]["token_contacto"].value()
        self.assertTrue(token_contacto)
        self.assertTrue(token_whatsapp)
        self.assertNotEqual(token_contacto, token_whatsapp)
        self.assertContains(response, f'value="{token_contacto}"', count=1)
        self.assertContains(response, f'value="{token_whatsapp}"', count=1)

    def test_whatsapp_y_cierre_desde_misma_pagina_aplican_ambos(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)
        detalle = f"/comunicador/{gestion.pk}/"
        response = self.client.get(detalle, HTTP_HOST="gestion.localhost")
        token_contacto = response.context["form"]["token_contacto"].value()
        token_whatsapp = response.context["form_whatsapp"]["token_contacto"].value()

        self.client.post(
            f"{detalle}whatsapp/",
            {"token_contacto": token_whatsapp, "cuerpo": "Mensaje de prueba."},
            HTTP_HOST="gestion.localhost",
        )
        self.client.post(
            detalle,
            {"accion": "NO_ACEPTA", "token_contacto": token_contacto},
            HTTP_HOST="gestion.localhost",
        )

        gestion.refresh_from_db()
        self.assertEqual(gestion.intentos_contacto, 2)
        self.assertIsNotNone(gestion.aviso_whatsapp_en)
        self.assertEqual(gestion.motivo_cierre, Gestion.MotivoCierre.NO_ACEPTA)

    def test_no_contesta_y_whatsapp_desde_misma_pagina_aplican_ambos(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)
        detalle = f"/comunicador/{gestion.pk}/"
        response = self.client.get(detalle, HTTP_HOST="gestion.localhost")
        token_contacto = response.context["form"]["token_contacto"].value()
        token_whatsapp = response.context["form_whatsapp"]["token_contacto"].value()

        self.client.post(
            detalle,
            {"accion": "NO_CONTESTA", "token_contacto": token_contacto},
            HTTP_HOST="gestion.localhost",
        )
        self.client.post(
            f"{detalle}whatsapp/",
            {"token_contacto": token_whatsapp, "cuerpo": "Mensaje de prueba."},
            HTTP_HOST="gestion.localhost",
        )

        gestion.refresh_from_db()
        self.assertEqual(gestion.intentos_contacto, 2)
        self.assertIsNotNone(gestion.aviso_whatsapp_en)

    def test_no_contesta_repetido_con_mismo_token_y_nuevo_formulario(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)
        detalle = f"/comunicador/{gestion.pk}/"
        primer_get = self.client.get(detalle, HTTP_HOST="gestion.localhost")
        primer_token = primer_get.context["form"]["token_contacto"].value()

        for _ in range(2):
            self.client.post(
                detalle,
                {"accion": "NO_CONTESTA", "token_contacto": primer_token},
                HTTP_HOST="gestion.localhost",
            )

        segundo_get = self.client.get(detalle, HTTP_HOST="gestion.localhost")
        segundo_token = segundo_get.context["form"]["token_contacto"].value()
        self.assertNotEqual(primer_token, segundo_token)
        self.client.post(
            detalle,
            {"accion": "NO_CONTESTA", "token_contacto": segundo_token},
            HTTP_HOST="gestion.localhost",
        )

        gestion.refresh_from_db()
        self.assertEqual(gestion.intentos_contacto, 2)

    def test_rechazado_vencido_acepta_post_y_muestra_advertencia(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        gestion.rechazar(self.usuario, self.motivo)
        Gestion.objects.filter(pk=gestion.pk).update(
            fecha_decision=timezone.now() - timedelta(hours=25)
        )

        response = self.client.post(
            f"/comunicador/{gestion.pk}/",
            {"accion": "NO_CONTESTA"},
            HTTP_HOST="gestion.localhost",
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ya se habia cerrado")
        gestion.refresh_from_db()
        self.assertEqual(gestion.intentos_contacto, 1)
        self.assertEqual(gestion.motivo_cierre, Gestion.MotivoCierre.SIN_AVISO)
        self.assertIsNotNone(gestion.cerrada_en)

    def test_rechazado_autocerrado_acepta_post_sin_perder_cierre(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        gestion.rechazar(self.usuario, self.motivo)
        momento_cierre = timezone.now()
        gestion.cerrar_rechazado_automatico(ahora=momento_cierre)

        response = self.client.post(
            f"/comunicador/{gestion.pk}/",
            {"accion": "NO_ACEPTA"},
            HTTP_HOST="gestion.localhost",
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ya se habia cerrado")
        gestion.refresh_from_db()
        self.assertEqual(gestion.intentos_contacto, 1)
        self.assertEqual(gestion.cerrada_en, momento_cierre)
        self.assertEqual(gestion.motivo_cierre, Gestion.MotivoCierre.SIN_AVISO)
        self.assertEqual(
            gestion.ultima_accion_contacto,
            Gestion.AccionContacto.NO_ACEPTA,
        )

    def test_agendada_cierra_con_fecha_hora(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)
        response = self.client.post(
            f"/comunicador/{gestion.pk}/",
            {"accion": "AGENDADA", "fecha_hora_citacion": "2026-08-20 09:30"},
            HTTP_HOST="gestion.localhost",
        )
        self.assertEqual(response.status_code, 302)
        gestion.refresh_from_db()
        self.assertEqual(gestion.motivo_cierre, Gestion.MotivoCierre.AGENDADA)
        self.assertIsNotNone(gestion.fecha_hora_citacion)

    def test_whatsapp_registra_intento_y_redirige_a_wa_me(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        gestion.rechazar(self.usuario, self.motivo)
        response = self.client.post(
            f"/comunicador/{gestion.pk}/whatsapp/",
            {"cuerpo": "Mensaje de prueba."},
            HTTP_HOST="gestion.localhost",
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("https://wa.me/"))
        gestion.refresh_from_db()
        self.assertEqual(gestion.intentos_contacto, 1)
        self.assertIsNotNone(gestion.aviso_whatsapp_en)
        self.assertIsNone(gestion.cerrada_en)

    def test_whatsapp_obsoleto_no_redirige_ni_contacta_no_aplica(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)
        comunicador_obsoleto = Gestion.objects.select_related("solicitud").get(
            pk=gestion.pk
        )
        Gestion.objects.get(pk=gestion.pk).marcar_no_aplica(self.usuario)

        with patch(
            "gestion.views._gestion_para_post_comunicador_o_404",
            return_value=comunicador_obsoleto,
        ):
            response = self.client.post(
                f"/comunicador/{gestion.pk}/whatsapp/",
                {
                    "token_contacto": "token-whatsapp-obsoleto",
                    "cuerpo": "Mensaje de prueba.",
                },
                HTTP_HOST="gestion.localhost",
            )

        self.assertRedirects(
            response, "/comunicador/", fetch_redirect_response=False
        )
        gestion.refresh_from_db()
        self.assertEqual(gestion.decision, Gestion.Decision.NO_APLICA)
        self.assertEqual(gestion.intentos_contacto, 0)

    def test_selector_no_puede_entrar_a_comunicador(self):
        self.perfil.rol = PerfilUsuario.Rol.SELECTOR
        self.perfil.save()
        response = self.client.get("/comunicador/", HTTP_HOST="gestion.localhost")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/sin-acceso/", response["Location"])

    def test_detalle_no_permite_accion_en_casos_fuera_de_la_tabla(self):
        pendiente = crear_solicitud_base(centro_salud=self.centro).gestion
        no_aplica = crear_solicitud_base(centro_salud=self.centro).gestion
        no_aplica.marcar_no_aplica(self.usuario)

        for gestion in (pendiente, no_aplica):
            response = self.client.post(
                f"/comunicador/{gestion.pk}/",
                {"accion": "NO_CONTESTA"},
                HTTP_HOST="gestion.localhost",
            )

            self.assertEqual(response.status_code, 404)
            gestion.refresh_from_db()
            self.assertEqual(gestion.intentos_contacto, 0)

    def test_whatsapp_no_permite_casos_fuera_de_la_tabla(self):
        pendiente = crear_solicitud_base(centro_salud=self.centro).gestion
        no_aplica = crear_solicitud_base(centro_salud=self.centro).gestion
        no_aplica.marcar_no_aplica(self.usuario)

        for gestion in (pendiente, no_aplica):
            response = self.client.post(
                f"/comunicador/{gestion.pk}/whatsapp/",
                HTTP_HOST="gestion.localhost",
            )

            self.assertEqual(response.status_code, 404)
            gestion.refresh_from_db()
            self.assertEqual(gestion.intentos_contacto, 0)

    def test_whatsapp_get_no_registra_intento(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        gestion.rechazar(self.usuario, self.motivo)

        response = self.client.get(
            f"/comunicador/{gestion.pk}/whatsapp/",
            HTTP_HOST="gestion.localhost",
        )

        self.assertEqual(response.status_code, 405)
        gestion.refresh_from_db()
        self.assertEqual(gestion.intentos_contacto, 0)

    def test_detalle_comunicador_completo_envia_contacto_sin_fragmento(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)

        response = self.client.get(
            f"/comunicador/{gestion.pk}/",
            HTTP_HOST="gestion.localhost",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f'action="/comunicador/{gestion.pk}/"',
            html=False,
        )
        self.assertNotContains(response, "?fragmento=1", html=False)

    def test_fragmento_comunicador_no_incluye_layout_y_muestra_historial(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)
        gestion.registrar_no_contesta(self.usuario, token_contacto="primer-token")
        response = self.client.get(
            f"/comunicador/{gestion.pk}/?fragmento=1",
            HTTP_HOST="gestion.localhost",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-fragment-kind="comunicador-detail"', html=False)
        self.assertNotContains(response, "<html", html=False)
        self.assertContains(response, "Historial de contacto")
        self.assertContains(response, "1 intento")

    def test_fragmento_comunicador_muestra_vista_previa_whatsapp(self):
        gestion = crear_solicitud_base(
            centro_salud=self.centro,
            nombre="Ana Perez",
        ).gestion
        gestion.rechazar(self.usuario, self.motivo)
        response = self.client.get(
            f"/comunicador/{gestion.pk}/?fragmento=1",
            HTTP_HOST="gestion.localhost",
        )
        self.assertContains(response, "Mensaje de WhatsApp")
        self.assertContains(response, "Ana Perez")

    def test_fragmento_comunicador_invalido_deshabilita_whatsapp(self):
        gestion = crear_solicitud_base(centro_salud=self.centro, telefono="123").gestion
        gestion.rechazar(self.usuario, self.motivo)
        response = self.client.get(
            f"/comunicador/{gestion.pk}/?fragmento=1",
            HTTP_HOST="gestion.localhost",
        )
        self.assertContains(response, "Telefono invalido para WhatsApp")
        self.assertContains(response, "disabled")

    def test_post_fragmento_comunicador_devuelve_confirmacion(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)
        response = self.client.get(
            f"/comunicador/{gestion.pk}/?fragmento=1",
            HTTP_HOST="gestion.localhost",
        )
        token = response.context["form"]["token_contacto"].value()
        response = self.client.post(
            f"/comunicador/{gestion.pk}/?fragmento=1",
            {"accion": "NO_CONTESTA", "token_contacto": token},
            HTTP_HOST="gestion.localhost",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-fragment-kind="comunicador-confirmation"', html=False)
        self.assertContains(response, "Contacto registrado")
        self.assertContains(response, 'data-case-resolved="false"', html=False)
        self.assertContains(response, "El caso permanece en la cola")

    def test_post_fragmento_comunicador_agendada_invalida_muestra_error_y_reabre_agenda(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)

        response = self.client.post(
            f"/comunicador/{gestion.pk}/?fragmento=1",
            {"accion": "AGENDADA"},
            HTTP_HOST="gestion.localhost",
        )

        self.assertContains(response, "Debe indicar fecha y hora acordadas")
        self.assertContains(response, '<details class="agenda-box" open>', html=False)
        self.assertContains(response, 'data-dialog-error-focus', html=False)

    def test_fragmento_comunicador_whatsapp_tiene_partes_fijas_fuera_del_textarea(self):
        PlantillaWhatsapp.objects.update_or_create(
            clave="aceptada",
            defaults={
                "descripcion": "Aceptada",
                "cuerpo": "Cuerpo editable.",
            },
        )
        gestion = crear_solicitud_base(centro_salud=self.centro, nombre="Ana Perez").gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)
        response = self.client.get(
            f"/comunicador/{gestion.pk}/?fragmento=1",
            HTTP_HOST="gestion.localhost",
        )
        self.assertContains(response, "Hola, Ana Perez. Somos del")
        self.assertContains(response, "Muchas gracias.")
        self.assertContains(response, 'name="cuerpo"', html=False)
        textarea_start = response.content.decode("utf-8").index('name="cuerpo"')
        textarea_chunk = response.content.decode("utf-8")[textarea_start:textarea_start + 300]
        self.assertNotIn("Ana Perez", textarea_chunk)
        self.assertIn("Cuerpo editable.", textarea_chunk)

    def test_whatsapp_fragmentado_devuelve_modal_con_url_y_registra_cuerpo_editado(self):
        gestion = crear_solicitud_base(centro_salud=self.centro, nombre="Ana Perez").gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)
        response = self.client.get(
            f"/comunicador/{gestion.pk}/?fragmento=1",
            HTTP_HOST="gestion.localhost",
        )
        token = response.context["form_whatsapp"]["token_contacto"].value()
        response = self.client.post(
            f"/comunicador/{gestion.pk}/whatsapp/?fragmento=1",
            {"token_contacto": token, "cuerpo": "Mensaje editado por comunicador."},
            HTTP_HOST="gestion.localhost",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-fragment-kind="comunicador-detail"', html=False)
        self.assertContains(response, "data-whatsapp-url=", html=False)
        self.assertContains(response, "Mensaje editado por comunicador.")
        gestion.refresh_from_db()
        self.assertEqual(gestion.intentos_contacto, 1)
        registro = gestion.registros_contacto.get()
        self.assertEqual(
            registro.mensaje,
            "Hola, Ana Perez. Somos del Centro De Salud Familiar Rodelillo.\n"
            "Mensaje editado por comunicador.\nMuchas gracias.",
        )

    def test_whatsapp_fragmentado_rechaza_cuerpo_vacio_sin_registrar_intento(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)
        response = self.client.post(
            f"/comunicador/{gestion.pk}/whatsapp/?fragmento=1",
            {"token_contacto": "token-vacio", "cuerpo": "   "},
            HTTP_HOST="gestion.localhost",
        )
        self.assertContains(response, "Debe escribir el cuerpo del mensaje.")
        gestion.refresh_from_db()
        self.assertEqual(gestion.intentos_contacto, 0)

    def test_fragmento_comunicador_muestra_bitacora_de_comunicaciones(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)
        gestion.registrar_no_contesta(self.usuario, token_contacto="llamada-1")
        gestion.registrar_click_whatsapp(
            self.usuario,
            token_contacto="wsp-1",
            mensaje="Hola, paciente. Mensaje enviado.",
        )

        response = self.client.get(
            f"/comunicador/{gestion.pk}/?fragmento=1",
            HTTP_HOST="gestion.localhost",
        )

        self.assertContains(response, "Historial de comunicaciones (2)")
        self.assertContains(response, "Llamada telefonica")
        self.assertContains(response, "WhatsApp")
        self.assertContains(response, "Mensaje enviado.")
        self.assertContains(response, self.usuario.email or self.usuario.username)

    def test_historial_visible_para_solo_lectura(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)
        gestion.registrar_no_contesta(self.usuario, token_contacto="solo-lectura")
        self.perfil.rol = PerfilUsuario.Rol.ADMIN
        self.perfil.save(update_fields=["rol"])

        response = self.client.get(
            f"/comunicador/{gestion.pk}/?fragmento=1",
            HTTP_HOST="gestion.localhost",
        )

        self.assertContains(response, "Historial de comunicaciones (1)")
        self.assertContains(response, "Vista de solo lectura")


class RegistroContactoBackfillMigrationTests(TransactionTestCase):
    serialized_rollback = True

    migrate_from = [("gestion", "0008_registro_contacto")]
    migrate_to = [("gestion", "0009_backfill_registro_contacto")]

    def setUp(self):
        super().setUp()
        self.executor = MigrationExecutor(connection)
        self.executor.migrate(self.migrate_from)
        self.apps = self.executor.loader.project_state(self.migrate_from).apps

    def tearDown(self):
        self.executor.loader.build_graph()
        self.executor.migrate(self.migrate_to)
        super().tearDown()

    def _crear_gestion_con_token(self, token="token-backfill"):
        User = self.apps.get_model("auth", "User")
        Centro = self.apps.get_model("solicitudes", "Centro")
        Solicitud = self.apps.get_model("solicitudes", "Solicitud")
        GestionHistorica = self.apps.get_model("gestion", "Gestion")
        TokenContactoGestion = self.apps.get_model("gestion", "TokenContactoGestion")

        usuario = User.objects.create_user("migracion-backfill")
        solicitud = Solicitud.objects.create(
            nombre="Ana Maria Perez",
            rut="25747311-2",
            edad=34,
            sexo="N",
            telefono="+56949106239",
            centro_salud=Centro.objects.get(pk=620),
            acepta_terminos=True,
            motivo="consulta medica",
            detalle_motivo="dolor de garganta",
            priorizacion_solicitud="BAJA",
            puntaje_prioridad=0,
        )
        gestion = GestionHistorica.objects.create(
            solicitud=solicitud,
            decision="ACEPTADA",
            prioridad_clinica="MEDIA",
            decidido_por=usuario,
            fecha_decision=timezone.now(),
        )
        contacto = TokenContactoGestion.objects.create(
            gestion=gestion,
            token=token,
            accion="NO_CONTESTA",
        )
        return gestion, contacto

    def test_backfill_conserva_fecha_original_del_token(self):
        gestion, contacto = self._crear_gestion_con_token()
        fecha_original = timezone.now() - timedelta(days=3, hours=2)
        type(contacto).objects.filter(pk=contacto.pk).update(creado_en=fecha_original)

        self.executor.loader.build_graph()
        self.executor.migrate(self.migrate_to)
        apps = self.executor.loader.project_state(self.migrate_to).apps
        RegistroContactoHistorico = apps.get_model("gestion", "RegistroContacto")

        registro = RegistroContactoHistorico.objects.get(gestion_id=gestion.pk)
        self.assertEqual(registro.creado_en, fecha_original)

    def test_reverse_backfill_no_borra_registros_ambiguos(self):
        gestion, contacto = self._crear_gestion_con_token()
        fecha_original = timezone.now() - timedelta(days=3)
        type(contacto).objects.filter(pk=contacto.pk).update(creado_en=fecha_original)

        self.executor.loader.build_graph()
        self.executor.migrate(self.migrate_to)
        apps = self.executor.loader.project_state(self.migrate_to).apps
        RegistroContactoHistorico = apps.get_model("gestion", "RegistroContacto")
        registro_backfill = RegistroContactoHistorico.objects.get(gestion_id=gestion.pk)
        registro_legitimo = RegistroContactoHistorico.objects.create(
            gestion_id=gestion.pk,
            canal="LLAMADA",
            resultado="NO_CONTESTA",
            mensaje="",
            usuario_id=None,
        )
        RegistroContactoHistorico.objects.filter(pk=registro_legitimo.pk).update(
            creado_en=fecha_original
        )

        self.executor.loader.build_graph()
        self.executor.migrate(self.migrate_from)

        ids_restantes = set(
            RegistroContactoHistorico.objects.filter(gestion_id=gestion.pk).values_list(
                "pk", flat=True
            )
        )
        self.assertIn(registro_backfill.pk, ids_restantes)
        self.assertIn(registro_legitimo.pk, ids_restantes)


class CerrarRechazadosCommandTests(TestCase):
    def setUp(self):
        self.usuario = User.objects.create_user("selector@cmvalparaiso.cl")
        self.motivo = MotivoRechazo.objects.create(
            nombre="Datos insuficientes",
            mensaje_paciente="Hola {nombre}, faltan datos.",
        )

    def _rechazado_vencido(self, aviso=False):
        gestion = crear_solicitud_base().gestion
        gestion.rechazar(self.usuario, self.motivo)
        Gestion.objects.filter(pk=gestion.pk).update(
            fecha_decision=timezone.now() - timedelta(hours=25),
            aviso_whatsapp_en=timezone.now() - timedelta(hours=2) if aviso else None,
        )
        gestion.refresh_from_db()
        return gestion

    def test_cierra_rechazado_vencido_sin_aviso(self):
        gestion = self._rechazado_vencido(aviso=False)
        out = StringIO()
        call_command("cerrar_rechazados", stdout=out)
        gestion.refresh_from_db()
        self.assertEqual(gestion.motivo_cierre, Gestion.MotivoCierre.SIN_AVISO)
        self.assertIsNotNone(gestion.cerrada_en)
        self.assertIn("1 rechazado", out.getvalue())

    def test_cierra_rechazado_vencido_con_aviso_whatsapp(self):
        gestion = self._rechazado_vencido(aviso=True)
        call_command("cerrar_rechazados")
        gestion.refresh_from_db()
        self.assertEqual(
            gestion.motivo_cierre, Gestion.MotivoCierre.AVISADO_WHATSAPP
        )

    def test_no_cierra_rechazado_menor_a_24_horas(self):
        gestion = crear_solicitud_base().gestion
        gestion.rechazar(self.usuario, self.motivo)
        call_command("cerrar_rechazados")
        gestion.refresh_from_db()
        self.assertIsNone(gestion.cerrada_en)


class GestionUiHelpersTests(TestCase):
    def setUp(self):
        self.centro = Centro.objects.get(pk=620)
        self.usuario = User.objects.create_user(
            "selector-ui@cmvalparaiso.cl", email="selector-ui@cmvalparaiso.cl"
        )
        self.perfil = PerfilUsuario.objects.create(
            usuario=self.usuario,
            rol=PerfilUsuario.Rol.SELECTOR,
            centro=self.centro,
        )
        self.motivo = MotivoRechazo.objects.create(
            nombre="Datos insuficientes",
            mensaje_paciente="Faltan datos para resolver su solicitud.",
        )

    def _render(self, source, context):
        template = Template("{% load gestion_ui %}" + source)
        return template.render(Context(context)).strip()

    def test_prioridad_css_entrega_clase_estable(self):
        html = self._render("{{ valor|prioridad_css }}", {"valor": Solicitud.Prioridad.URGENTE})
        self.assertEqual(html, "prioridad--urgente")

    def test_tiempo_relativo_entrega_horas_y_minutos(self):
        hace_dos_horas = timezone.now() - timedelta(hours=2, minutes=10)
        html = self._render("{{ fecha|tiempo_relativo }}", {"fecha": hace_dos_horas})
        self.assertEqual(html, "hace 2 h")

    def test_horas_restantes_rechazo_muestra_plazo(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        gestion.rechazar(self.usuario, self.motivo)
        Gestion.objects.filter(pk=gestion.pk).update(
            fecha_decision=timezone.now() - timedelta(hours=18, minutes=10)
        )
        gestion.refresh_from_db()
        html = self._render("{{ gestion|horas_restantes_rechazo }}", {"gestion": gestion})
        self.assertEqual(html, "quedan 5 h para avisar")

    def test_telefono_whatsapp_valido_usa_url_whatsapp(self):
        gestion = crear_solicitud_base(centro_salud=self.centro, telefono="123").gestion
        gestion.rechazar(self.usuario, self.motivo)
        html = self._render(
            "{% if gestion|telefono_whatsapp_valido %}si{% else %}no{% endif %}",
            {"gestion": gestion},
        )
        self.assertEqual(html, "no")

    def test_mensaje_whatsapp_previo_reemplaza_nombre(self):
        gestion = crear_solicitud_base(
            centro_salud=self.centro,
            nombre="Ana Perez",
        ).gestion
        gestion.rechazar(self.usuario, self.motivo)
        html = self._render("{{ gestion|mensaje_whatsapp_previo }}", {"gestion": gestion})
        self.assertIn("Ana Perez", html)
        self.assertNotIn("{nombre}", html)


@override_settings(ALLOWED_HOSTS=["gestion.localhost", "testserver"], GESTION_HOST="gestion.localhost")
class GestionBaseLayoutTests(TestCase):
    def setUp(self):
        self.centro = Centro.objects.get(pk=620)
        self.usuario = User.objects.create_user(
            "selector-base@cmvalparaiso.cl", email="selector-base@cmvalparaiso.cl"
        )
        PerfilUsuario.objects.create(
            usuario=self.usuario,
            rol=PerfilUsuario.Rol.SELECTOR,
            centro=self.centro,
        )
        self.client.force_login(self.usuario)

    def test_base_carga_css_js_y_datos_de_sesion(self):
        response = self.client.get("/selector/", HTTP_HOST="gestion.localhost")
        self.assertContains(response, 'href="/static/css/gestion.css"', html=False)
        self.assertContains(response, 'src="/static/js/gestion.js"', html=False)
        self.assertContains(response, "selector-base@cmvalparaiso.cl")
        self.assertContains(response, "Selector")
        self.assertContains(response, str(self.centro))
        self.assertContains(response, "Cerrar sesion")


@override_settings(ALLOWED_HOSTS=["gestion.localhost", "testserver"], GESTION_HOST="gestion.localhost")
class GestionListasUiTests(TestCase):
    def setUp(self):
        self.centro = Centro.objects.get(pk=620)
        self.usuario = User.objects.create_user("selector-lista@cmvalparaiso.cl")
        self.perfil = PerfilUsuario.objects.create(
            usuario=self.usuario,
            rol=PerfilUsuario.Rol.SELECTOR,
            centro=self.centro,
        )
        self.motivo = MotivoRechazo.objects.create(
            nombre="Datos insuficientes",
            mensaje_paciente="Hola {nombre}, faltan datos.",
        )
        self.client.force_login(self.usuario)

    def test_selector_lista_oculta_decision_y_centro_para_selector_de_un_centro(self):
        gestion = crear_solicitud_base(
            centro_salud=self.centro,
            motivo="Dolor pecho",
            detalle_motivo="Dolor pecho desde la noche anterior",
            priorizacion_solicitud=Solicitud.Prioridad.URGENTE,
        ).gestion
        response = self.client.get("/selector/", HTTP_HOST="gestion.localhost")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dolor pecho desde la noche anterior")
        self.assertContains(response, "Urgente")
        self.assertContains(
            response,
            f'data-detail-url="/selector/{gestion.pk}/?fragmento=1&amp;seccion=pendientes"',
            html=False,
        )
        self.assertNotContains(response, "<th>Decision</th>", html=False)
        self.assertNotContains(response, "<th>Centro</th>", html=False)

    def test_selector_lista_muestra_centro_para_admin(self):
        self.perfil.rol = PerfilUsuario.Rol.ADMIN
        self.perfil.save(update_fields=["rol"])
        crear_solicitud_base(centro_salud=self.centro).gestion
        response = self.client.get("/selector/", HTTP_HOST="gestion.localhost")
        self.assertContains(response, "<th>Centro</th>", html=False)

    def test_prioridad_en_lista_expone_desglose_en_hover_y_foco(self):
        gestion = crear_solicitud_base(
            centro_salud=self.centro,
            motivo="dolor pecho",
            detalle_motivo="adulto mayor",
            edad=68,
            priorizacion_solicitud=Solicitud.Prioridad.URGENTE,
            puntaje_prioridad=6,
        ).gestion
        response = self.client.get("/selector/", HTTP_HOST="gestion.localhost")
        self.assertContains(response, "prioridad-detalle")
        self.assertContains(response, 'tabindex="0"', html=False)
        self.assertContains(
            response,
            f'aria-describedby="prioridad-{gestion.pk}"',
            html=False,
        )
        self.assertContains(response, f'id="prioridad-{gestion.pk}"', html=False)
        self.assertContains(response, 'role="tooltip"', html=False)
        self.assertContains(response, "palabra clave &quot;dolor pecho&quot;", html=False)
        self.assertContains(response, "edad 68 anos")
        css = Path(__file__).resolve().parent.parent / "static" / "css" / "gestion.css"
        self.assertIn(".priority-badge:focus + .prioridad-detalle", css.read_text())

    def test_selector_vacio_usa_colspan_de_sus_columnas_visibles(self):
        response = self.client.get("/selector/", HTTP_HOST="gestion.localhost")
        self.assertContains(response, '<td colspan="5">', html=False)

    def test_selector_tabs_muestran_conteos(self):
        pendiente = crear_solicitud_base(centro_salud=self.centro).gestion
        decidida = crear_solicitud_base(centro_salud=self.centro).gestion
        decidida.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)
        no_aplica = crear_solicitud_base(centro_salud=self.centro).gestion
        no_aplica.marcar_no_aplica(self.usuario)
        response = self.client.get("/selector/", HTTP_HOST="gestion.localhost")
        self.assertContains(response, "Pendientes")
        self.assertContains(response, ">1<", html=False)
        self.assertEqual(pendiente.decision, Gestion.Decision.PENDIENTE)


@override_settings(ALLOWED_HOSTS=["gestion.localhost", "testserver"], GESTION_HOST="gestion.localhost")
class ComunicadorListaUiTests(TestCase):
    def setUp(self):
        self.centro = Centro.objects.get(pk=620)
        self.usuario = User.objects.create_user("comunicador-lista@cmvalparaiso.cl")
        self.perfil = PerfilUsuario.objects.create(
            usuario=self.usuario,
            rol=PerfilUsuario.Rol.COMUNICADOR,
            centro=self.centro,
        )
        self.motivo = MotivoRechazo.objects.create(
            nombre="Datos insuficientes",
            mensaje_paciente="Hola {nombre}, faltan datos.",
        )
        self.client.force_login(self.usuario)

    def test_comunicador_separa_aceptadas_y_rechazadas(self):
        aceptada = crear_solicitud_base(centro_salud=self.centro).gestion
        aceptada.aceptar(self.usuario, Solicitud.Prioridad.URGENTE)
        rechazada = crear_solicitud_base(centro_salud=self.centro).gestion
        rechazada.rechazar(self.usuario, self.motivo)
        response = self.client.get("/comunicador/", HTTP_HOST="gestion.localhost")
        self.assertContains(response, "Aceptadas - llamar por telefono")
        self.assertContains(response, "Rechazadas - avisar por WhatsApp")
        self.assertLess(
            response.content.decode("utf-8").index("Aceptadas - llamar por telefono"),
            response.content.decode("utf-8").index("Rechazadas - avisar por WhatsApp"),
        )

    def test_comunicador_marca_telefono_invalido_y_deshabilita_whatsapp(self):
        gestion = crear_solicitud_base(centro_salud=self.centro, telefono="123").gestion
        gestion.rechazar(self.usuario, self.motivo)
        response = self.client.get("/comunicador/", HTTP_HOST="gestion.localhost")
        self.assertContains(response, "Telefono invalido para WhatsApp")
        self.assertContains(response, "WhatsApp no disponible")
        self.assertContains(response, "disabled")

    def test_comunicador_muestra_tel_y_cuenta_regresiva_de_rechazo(self):
        gestion = crear_solicitud_base(centro_salud=self.centro, telefono="+56949106239").gestion
        gestion.rechazar(self.usuario, self.motivo)
        Gestion.objects.filter(pk=gestion.pk).update(
            fecha_decision=timezone.now() - timedelta(hours=18)
        )
        response = self.client.get("/comunicador/", HTTP_HOST="gestion.localhost")
        self.assertContains(response, 'href="tel:+56949106239"', html=False)
        self.assertContains(response, "quedan 5 h para avisar")


@override_settings(ALLOWED_HOSTS=["gestion.localhost", "testserver"], GESTION_HOST="gestion.localhost")
class GestionAccesibilidadMarkupTests(TestCase):
    def setUp(self):
        self.centro = Centro.objects.get(pk=620)
        self.usuario = User.objects.create_user("ui-a11y@cmvalparaiso.cl")
        self.perfil = PerfilUsuario.objects.create(
            usuario=self.usuario,
            rol=PerfilUsuario.Rol.FULL,
            centro=self.centro,
        )
        self.client.force_login(self.usuario)

    def test_filas_clickeables_conservan_enlace_real(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        response = self.client.get("/selector/", HTTP_HOST="gestion.localhost")
        self.assertContains(
            response,
            f'href="/selector/{gestion.pk}/?seccion=pendientes"',
            html=False,
        )
        self.assertContains(
            response,
            f'data-detail-url="/selector/{gestion.pk}/?fragmento=1&amp;seccion=pendientes"',
            html=False,
        )

    def test_botones_de_modal_tienen_texto_de_accion(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        response = self.client.get(
            f"/selector/{gestion.pk}/?fragmento=1",
            HTTP_HOST="gestion.localhost",
        )
        self.assertContains(response, "Aceptar Urgente")
        self.assertContains(response, "Aceptar Alta")
        self.assertContains(response, "Aceptar Media")
        self.assertContains(response, "Aceptar Baja")
        self.assertContains(response, "Confirmar rechazo")
        self.assertContains(response, "No aplica")

    def test_detalle_completo_no_muestra_cierre_de_modal_sin_efecto(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        response = self.client.get(
            f"/selector/{gestion.pk}/",
            HTTP_HOST="gestion.localhost",
        )
        self.assertNotContains(response, "data-dialog-close", html=False)

    def test_modal_oculta_fecha_de_agenda_hasta_que_se_expande_la_accion(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)
        response = self.client.get(
            f"/comunicador/{gestion.pk}/?fragmento=1",
            HTTP_HOST="gestion.localhost",
        )
        self.assertContains(response, '<details class="agenda-box">', html=False)

    def test_js_de_fragmentos_no_reenvia_formularios_y_refresca_tabla_al_cerrar(self):
        javascript = (
            Path(__file__).resolve().parent.parent / "static" / "js" / "gestion.js"
        ).read_text()
        self.assertNotIn("form.submit()", javascript)
        self.assertNotIn("data-selector-counter", javascript)
        self.assertNotIn("data-selector-correction", javascript)
        self.assertNotIn("data-selector-row-action", javascript)
        self.assertIn("dialogActionsCount", javascript)
        self.assertIn("refreshSelectorTable", javascript)
        self.assertIn("data-selector-table-region", javascript)
        self.assertIn("removeResolvedCommunicatorRow", javascript)
        self.assertIn('data-fragment-kind="comunicador-confirmation"', javascript)
        self.assertIn('dataset.caseResolved !== "true"', javascript)
        self.assertIn("response.redirected", javascript)
        self.assertIn("data-fragment-kind", javascript)
        self.assertIn("dialogRequestInFlight", javascript)
        self.assertIn("setDialogButtonsDisabled", javascript)
        self.assertNotIn('window.open("", "_blank", "noopener")', javascript)
        self.assertIn('window.open("", "_blank")', javascript)
        self.assertIn("popup.opener = null", javascript)
        self.assertIn("popup.location.href = url", javascript)
        cierre_dialogo = javascript[javascript.index('dialog.addEventListener("close"') :]
        self.assertIn("dialogActionsCount > 0", cierre_dialogo)
        self.assertIn("refreshSelectorTable", cierre_dialogo)

    def test_fragmentos_terminales_tienen_objetivo_de_foco_neutro(self):
        vacia = Path(__file__).resolve().parent / "templates" / "gestion" / "_cola_selector_vacia.html"
        confirmacion = (
            Path(__file__).resolve().parent
            / "templates"
            / "gestion"
            / "_confirmacion_comunicador.html"
        )

        self.assertIn("data-dialog-focus", vacia.read_text())
        self.assertIn("data-dialog-focus", confirmacion.read_text())

    def test_vista_solo_lectura_muestra_traza_de_auditoria_completa(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)
        gestion.registrar_no_contesta(self.usuario, token_contacto="auditoria")
        self.perfil.rol = PerfilUsuario.Rol.ADMIN
        self.perfil.save(update_fields=["rol"])

        selector = self.client.get(
            f"/selector/{gestion.pk}/?fragmento=1",
            HTTP_HOST="gestion.localhost",
        )
        comunicador = self.client.get(
            f"/comunicador/{gestion.pk}/?fragmento=1",
            HTTP_HOST="gestion.localhost",
        )

        for response in (selector, comunicador):
            self.assertContains(response, "Decidido por")
            self.assertContains(response, "Fecha de decision")
            self.assertContains(response, "Intentos de contacto")
            self.assertContains(response, "Ultima accion de contacto")
            self.assertContains(response, "Motivo de cierre")

    def test_formulario_de_contacto_fragmentado_conserva_accion_de_fragmento(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)
        response = self.client.get(
            f"/comunicador/{gestion.pk}/?fragmento=1",
            HTTP_HOST="gestion.localhost",
        )
        self.assertContains(
            response,
            f'action="/comunicador/{gestion.pk}/?fragmento=1"',
            html=False,
        )

    def test_base_expone_sprite_svg_de_iconos_de_gestion(self):
        response = self.client.get("/selector/", HTTP_HOST="gestion.localhost")
        self.assertContains(response, '<svg hidden aria-hidden="true"', html=False)
        for symbol_id in (
            "ic-check",
            "ic-x",
            "ic-minus",
            "ic-calendar",
            "ic-phone",
            "ic-whatsapp",
        ):
            self.assertContains(response, f'id="{symbol_id}"', html=False)

    def test_botones_de_selector_tienen_icono_texto_y_clase_de_accion(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        response = self.client.get(
            f"/selector/{gestion.pk}/?fragmento=1",
            HTTP_HOST="gestion.localhost",
        )
        self.assertContains(response, 'class="btn--confirmar"', html=False)
        self.assertContains(response, '<use href="#ic-check"></use>', html=False)
        self.assertContains(response, 'class="btn--rechazar"', html=False)
        self.assertContains(response, '<use href="#ic-x"></use>', html=False)
        self.assertContains(response, 'class="btn--neutro"', html=False)
        self.assertContains(response, '<use href="#ic-minus"></use>', html=False)
        self.assertContains(response, "Aceptar Urgente")
        self.assertContains(response, "Confirmar rechazo")
        self.assertContains(response, "No aplica")

    def test_encabezado_de_modal_selector_muestra_identidad_vertical(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        response = self.client.get(
            f"/selector/{gestion.pk}/?fragmento=1",
            HTTP_HOST="gestion.localhost",
        )
        self.assertContains(response, '<dl class="modal-identity">', html=False)
        self.assertContains(response, "<dt>RUT</dt>", html=False)
        self.assertContains(response, "<dt>Telefono</dt>", html=False)
        self.assertContains(response, "<dt>Centro</dt>", html=False)

    def test_encabezado_de_modal_comunicador_omite_rut_y_destaca_telefono(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)
        response = self.client.get(
            f"/comunicador/{gestion.pk}/?fragmento=1",
            HTTP_HOST="gestion.localhost",
        )
        self.assertContains(
            response,
            '<dl class="modal-identity modal-identity--contacto">',
            html=False,
        )
        self.assertNotContains(response, "<dt>RUT</dt>", html=False)
        self.assertContains(
            response,
            f'href="tel:{gestion.solicitud.telefono}"',
            html=False,
        )
