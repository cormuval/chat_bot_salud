import json

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import Centro, Solicitud
from .priorizacion import calcular_prioridad, desglosar_prioridad
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
