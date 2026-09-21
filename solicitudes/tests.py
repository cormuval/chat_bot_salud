import json
from pathlib import Path

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.conf import settings
from django.db import IntegrityError
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from .models import Centro, PalabraClavePrioridad, Solicitud
from .priorizacion import calcular_prioridad, desglosar_prioridad
from .texto import normalizar
from .validators import formatear_telefono_con_codigo_pais, validar_rut_chileno, validar_telefono_chileno


class SolicitudTests(TestCase):
    def valid_payload(self):
        return {
            "nombre": "Ana Maria Perez",
            "rut": "25747311-2",
            "edad": 34,
            "sexo": "F",
            "telefono": "949106239",
            "centro_salud": "620",
            "credendencial_cuidador_discapacidad": False,
            "Neurodivergente_prais_gestante": False,
            "acepta_terminos": True,
            "motivo": "consulta medica",
            "detalle_motivo": "dolor de garganta hace tres dias",
        }

    def test_creacion_solicitud_valida(self):
        payload = self.valid_payload()
        payload["centro_salud_id"] = payload.pop("centro_salud")
        prioridad = calcular_prioridad(payload)
        payload["priorizacion_solicitud"] = prioridad["clasificacion"]
        payload["puntaje_prioridad"] = prioridad["puntaje"]
        solicitud = Solicitud(**payload)
        solicitud.full_clean()
        solicitud.save()

        self.assertEqual(solicitud.id_solicitud, 1)
        self.assertEqual(solicitud.priorizacion_solicitud, "BAJA")
        self.assertEqual(solicitud.puntaje_prioridad, 0)
        self.assertEqual(solicitud.nombre, "Ana Maria Perez")
        self.assertEqual(solicitud.rut, "25747311-2")
        self.assertEqual(solicitud.telefono, "+56949106239")
        self.assertEqual(solicitud.centro_salud_id, 620)
        self.assertEqual(solicitud.centro_salud.centro, "Centro De Salud Familiar Rodelillo")
        self.assertTrue(solicitud.acepta_terminos)

    def test_catalogo_centros_incluye_cesfam_y_cecosf(self):
        self.assertEqual(Centro.objects.get(pk=626).centro, "Centro Comunitario De Salud Familiar Porvenir Bajo")
        self.assertEqual(Centro.objects.get(pk=627).centro, "Centro Comunitario De Salud Familiar Juan Pablo II")

    def test_rechaza_rut_invalido(self):
        with self.assertRaises(ValidationError):
            validar_rut_chileno("20.112.654-8")

    def test_rechaza_telefono_invalido(self):
        with self.assertRaises(ValidationError):
            validar_telefono_chileno("85881767")

    def test_normaliza_telefono_sin_codigo_pais(self):
        validar_telefono_chileno("949106239")
        self.assertEqual(formatear_telefono_con_codigo_pais("949106239"), "+56949106239")

    def test_prioridad_por_reglas(self):
        self.assertEqual(calcular_prioridad({"detalle_motivo": "control", "edad": 5})["clasificacion"], "MEDIA")
        self.assertEqual(calcular_prioridad({"detalle_motivo": "control", "edad": 65})["clasificacion"], "MEDIA")
        self.assertEqual(
            calcular_prioridad(
                {
                    "detalle_motivo": "control",
                    "edad": 40,
                    "credendencial_cuidador_discapacidad": True,
                }
            )["clasificacion"],
            "MEDIA",
        )
        self.assertEqual(
            calcular_prioridad(
                {
                    "detalle_motivo": "control",
                    "edad": 40,
                    "Neurodivergente_prais_gestante": True,
                }
            )["clasificacion"],
            "MEDIA",
        )
        self.assertEqual(
            calcular_prioridad(
                {
                    "detalle_motivo": "control",
                    "edad": 65,
                    "credendencial_cuidador_discapacidad": True,
                }
            )["clasificacion"],
            "ALTA",
        )
        self.assertEqual(
            calcular_prioridad({"detalle_motivo": "dolor pecho intenso", "edad": 65})["clasificacion"],
            "URGENTE",
        )
        self.assertEqual(calcular_prioridad({"detalle_motivo": "control", "edad": 40})["clasificacion"], "BAJA")

    def test_endpoint_crea_solicitud(self):
        response = self.client.post(
            reverse("crear_solicitud"),
            data=json.dumps(self.valid_payload()),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertTrue(body["ok"])
        # Se compara contra la fila realmente creada, no contra un 1 fijo: el
        # contador AUTO_INCREMENT de InnoDB no vuelve atras con el rollback de
        # la transaccion del TestCase, asi que el id depende de cuantas filas
        # crearon los tests anteriores.
        self.assertEqual(body["id_solicitud"], Solicitud.objects.get().id_solicitud)
        self.assertEqual(body["priorizacion_solicitud"], "BAJA")
        self.assertEqual(body["puntaje_prioridad"], 0)
        self.assertEqual(Solicitud.objects.get().nombre, "Ana Maria Perez")
        self.assertEqual(body["resumen"]["nombre"], "Ana Maria Perez")
        self.assertEqual(body["resumen"]["rut"], "25747311-2")
        self.assertEqual(body["resumen"]["telefono"], "+56949106239")
        self.assertEqual(body["resumen"]["centro_salud"], 620)
        self.assertEqual(body["resumen"]["centro_salud_nombre"], "Centro De Salud Familiar Rodelillo")

    def test_endpoint_rechaza_sin_terminos(self):
        payload = self.valid_payload()
        payload["acepta_terminos"] = False
        response = self.client.post(
            reverse("crear_solicitud"),
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Solicitud.objects.count(), 0)

    def test_endpoint_acepta_payload_saludbot(self):
        response = self.client.post(
            reverse("crear_solicitud"),
            data=json.dumps(
                {
                    "nombre": "Ana Maria Perez",
                    "rut": "25747311-2",
                    "edad": 34,
                    "telefono": "949106239",
                    "centro_salud": "620",
                    "motivo": "Tengo fiebre",
                    "detalle_motivo": "Fiebre desde ayer con dolor de cuerpo",
                    "acepta_terminos": True,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        solicitud = Solicitud.objects.get()
        self.assertEqual(solicitud.nombre, "Ana Maria Perez")
        self.assertEqual(solicitud.rut, "25747311-2")
        self.assertEqual(solicitud.telefono, "+56949106239")
        self.assertEqual(solicitud.centro_salud_id, 620)
        self.assertEqual(solicitud.sexo, "N")
        self.assertEqual(solicitud.puntaje_prioridad, 1)
        self.assertEqual(solicitud.priorizacion_solicitud, "BAJA")

    def test_endpoint_rechaza_sin_nombre(self):
        payload = self.valid_payload()
        payload.pop("nombre")
        response = self.client.post(
            reverse("crear_solicitud"),
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("nombre", response.json()["errors"])
        self.assertEqual(Solicitud.objects.count(), 0)

    def test_endpoint_rechaza_nombre_en_blanco(self):
        payload = self.valid_payload()
        payload["nombre"] = "   "
        response = self.client.post(
            reverse("crear_solicitud"),
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("nombre", response.json()["errors"])
        self.assertEqual(Solicitud.objects.count(), 0)

    def test_endpoint_normaliza_espacios_del_nombre(self):
        payload = self.valid_payload()
        payload["nombre"] = "  Ana   Maria  Perez  "
        response = self.client.post(
            reverse("crear_solicitud"),
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Solicitud.objects.get().nombre, "Ana Maria Perez")

    def test_endpoint_guarda_condicion_otro_y_foto(self):
        payload = self.valid_payload()
        payload.update(
            {
                "credendencial_cuidador_discapacidad": True,
                "credencial_cuidador_discapacidad_foto": "data:image/png;base64,AAA",
                "Neurodivergente_prais_gestante": True,
                "Neurodivergente_prais_gestante_tipo": "OTRO",
                "Neurodivergente_prais_gestante_otro": "otra condicion",
            }
        )
        response = self.client.post(
            reverse("crear_solicitud"),
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        solicitud = Solicitud.objects.get()
        self.assertEqual(solicitud.credencial_cuidador_discapacidad_foto, "data:image/png;base64,AAA")
        self.assertEqual(solicitud.Neurodivergente_prais_gestante_tipo, "OTRO")
        self.assertEqual(solicitud.Neurodivergente_prais_gestante_otro, "otra condicion")


class DesglosePrioridadTests(TestCase):
    def test_desglose_suma_el_mismo_puntaje_que_calcular_prioridad(self):
        casos = [
            {"detalle_motivo": "control", "edad": 40},
            {"detalle_motivo": "dolor pecho", "edad": 68},
            {
                "detalle_motivo": "vomitos con diarrea",
                "edad": 4,
                "credendencial_cuidador_discapacidad": True,
                "Neurodivergente_prais_gestante": True,
            },
        ]
        for datos in casos:
            with self.subTest(datos=datos):
                desglose = desglosar_prioridad(datos)
                self.assertEqual(
                    sum(factor["puntaje"] for factor in desglose),
                    calcular_prioridad(datos)["puntaje"],
                )

    def test_desglose_identifica_factores_concretos(self):
        desglose = desglosar_prioridad(
            {
                "motivo": "dolor pecho",
                "detalle_motivo": "adulto mayor con fiebre",
                "edad": 68,
                "credendencial_cuidador_discapacidad": True,
            }
        )
        self.assertEqual(
            desglose,
            [
                {
                    "codigo": "palabra_urgente",
                    "descripcion": 'palabra clave "dolor pecho"',
                    "puntaje": 4,
                },
                {
                    "codigo": "palabra_moderada",
                    "descripcion": 'palabra clave "fiebre"',
                    "puntaje": 1,
                },
                {"codigo": "edad", "descripcion": "edad 68 anos", "puntaje": 2},
                {
                    "codigo": "credencial",
                    "descripcion": "credencial de cuidador",
                    "puntaje": 2,
                },
            ],
        )


class SaludBotScriptTests(SimpleTestCase):
    def test_terminos_es_la_primera_pantalla(self):
        script = Path(settings.BASE_DIR, "static", "js", "saludbot.js").read_text(encoding="utf-8")

        terminos_index = script.index('field: "acepta_terminos"')
        motivo_index = script.index('field: "motivo"')
        sintomas_index = script.index('field: "detalle_sintomas"')

        self.assertLess(terminos_index, motivo_index)
        self.assertLess(motivo_index, sintomas_index)

    def test_apertura_presenta_terminos_antes_del_saludo(self):
        script = Path(settings.BASE_DIR, "static", "js", "saludbot.js").read_text(encoding="utf-8")

        # start() ya no publica el saludo directamente: presenta el paso actual
        # (terminos). El saludo vive en el render del paso motivo.
        start_body = script[script.index("function start()"):script.index("function showSummary()")]
        self.assertIn("askCurrentStep();", start_body)
        self.assertNotIn("Soy SaludBot", start_body)

    def test_mensaje_final_informa_revision_profesional_destacada(self):
        script = Path(settings.BASE_DIR, "static", "js", "saludbot.js").read_text(encoding="utf-8")

        self.assertIn(
            "Su solicitud será revisada por un profesional clínico durante el día. Una vez evaluada, le informaremos si se le asignará una hora de atención médica o si deberá realizar una nueva solicitud al día siguiente.",
            script,
        )
        self.assertIn("success-notice", script)
        self.assertIn("success-notice__title", script)
        self.assertIn("Importante", script)

    def test_scroll_ancla_el_inicio_del_mensaje_del_bot(self):
        script = Path(settings.BASE_DIR, "static", "js", "saludbot.js").read_text(encoding="utf-8")

        self.assertIn("function scrollToLatest(target, sender)", script)
        self.assertIn('block: sender === "bot" ? "start" : "nearest"', script)
        # addMessage pasa el emisor al scroll para decidir el anclaje.
        self.assertIn("scrollToLatest(row, sender);", script)

    def test_cesfam_se_pregunta_antes_del_rut_y_nombre(self):
        script = Path(settings.BASE_DIR, "static", "js", "saludbot.js").read_text(encoding="utf-8")

        centro_index = script.index('field: "centro_salud"')
        rut_index = script.index('field: "rut"')
        nombre_index = script.index('field: "nombre"')
        sintomas_index = script.index('field: "detalle_sintomas"')

        self.assertLess(sintomas_index, centro_index)
        self.assertLess(centro_index, rut_index)
        self.assertLess(centro_index, nombre_index)

    def test_input_se_bloquea_en_pasos_de_botones(self):
        script = Path(settings.BASE_DIR, "static", "js", "saludbot.js").read_text(encoding="utf-8")

        self.assertIn("function esPasoDeBotones(step)", script)
        # El gate se deriva del tipo de paso y se aplica al input y al boton.
        self.assertIn("const gate = esPasoDeBotones(steps[state.index]);", script)
        self.assertIn("input.disabled = gate;", script)

    def test_paso_de_foto_oculto_por_flag(self):
        script = Path(settings.BASE_DIR, "static", "js", "saludbot.js").read_text(encoding="utf-8")

        self.assertIn("const ADJUNTO_FOTO_HABILITADO = false;", script)
        # El skip del paso de foto respeta el flag.
        self.assertIn("!ADJUNTO_FOTO_HABILITADO", script)

    def test_no_hay_scroll_sin_emisor_que_pise_el_anclaje(self):
        script = Path(settings.BASE_DIR, "static", "js", "saludbot.js").read_text(encoding="utf-8")
        # Ninguna llamada bare a scrollToLatest: todas pasan el emisor, para que
        # ninguna caiga en "nearest" y pise el anclaje "start" del mensaje del bot.
        self.assertNotIn("scrollToLatest();", script)


@override_settings(DEBUG=False)
class ErrorPagesTests(SimpleTestCase):
    def test_pagina_no_encontrada_muestra_imagen_404(self):
        response = self.client.get("/ruta-inexistente/")

        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "img/404.webp", status_code=404)


class PalabraClavePrioridadModeloTests(TestCase):
    def test_normalizar_quita_acentos_y_mayusculas(self):
        self.assertEqual(normalizar("Convulsión"), "convulsion")
        self.assertEqual(normalizar("  FIEBRE "), "fiebre")

    def test_guardar_calcula_texto_normalizado(self):
        p = PalabraClavePrioridad.objects.create(texto="Mareó", nivel="URGENTE")
        self.assertEqual(p.texto_normalizado, "mareo")

    def test_unicidad_por_forma_normalizada(self):
        PalabraClavePrioridad.objects.create(texto="Tos", nivel="MODERADA")
        with self.assertRaises(IntegrityError):
            PalabraClavePrioridad.objects.create(texto="tos", nivel="MODERADA")


class SeedPalabrasPrioridadTests(TestCase):
    def test_semilla_reproduce_las_palabras_actuales(self):
        urgentes = set(
            PalabraClavePrioridad.objects.filter(nivel="URGENTE", activo=True)
            .values_list("texto_normalizado", flat=True)
        )
        self.assertIn("convulsion", urgentes)
        self.assertIn("dolor pecho", urgentes)
        self.assertEqual(
            PalabraClavePrioridad.objects.filter(nivel="URGENTE").count(), 9
        )
        self.assertEqual(
            PalabraClavePrioridad.objects.filter(nivel="MODERADA").count(), 6
        )


class PriorizacionDesdeBDTests(TestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def _datos(self, texto):
        return {"motivo": texto, "detalle_motivo": "", "edad": 30,
                "credendencial_cuidador_discapacidad": False,
                "Neurodivergente_prais_gestante": False}

    def test_palabra_activa_sube_la_prioridad(self):
        # 'convulsion' viene sembrada como URGENTE (+4) => ALTA
        self.assertEqual(calcular_prioridad(self._datos("convulsion"))["clasificacion"], "ALTA")

    def test_match_ignora_acentos(self):
        self.assertEqual(calcular_prioridad(self._datos("Convulsión"))["clasificacion"], "ALTA")

    def test_desactivar_palabra_baja_la_prioridad(self):
        PalabraClavePrioridad.objects.filter(texto_normalizado="convulsion").update(activo=False)
        cache.clear()
        self.assertEqual(calcular_prioridad(self._datos("convulsion"))["clasificacion"], "BAJA")

    def test_palabra_nueva_aplica_sin_tocar_codigo(self):
        PalabraClavePrioridad.objects.create(texto="mareo", nivel="URGENTE")
        self.assertEqual(calcular_prioridad(self._datos("tengo mareo"))["clasificacion"], "ALTA")
