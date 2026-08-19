# Modulo de Seleccion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convertir las solicitudes creadas por el chatbot en un flujo operativo de seleccion y comunicacion, con decisiones clinicas, avisos al paciente, cierre automatico de rechazos y filtrado por rol/centro.

**Architecture:** La app `solicitudes` sigue siendo la unica que crea `Solicitud`; la app `gestion` agrega una tabla `Gestion` one-to-one y una senal `post_save` para crear el registro administrativo. La logica de negocio vive en modelos/querysets y formularios pequenos; las vistas de gestion solo filtran por `PerfilUsuario`, renderizan colas y ejecutan acciones POST. El cierre automatico tiene dos capas: filtro en vivo en la tabla del comunicador y comando `manage.py cerrar_rechazados` para materializar `cerrada_en` y `motivo_cierre`.

**Tech Stack:** Django 5.2.8, Python 3.13 compatible con el entorno local actual, MySQL 8.4, `mozilla-django-oidc==5.0.2`, test runner nativo de Django (`manage.py test`).

## Global Constraints

- Spec de referencia: `docs/superpowers/specs/2026-07-28-modulo-seleccion-design.md`.
- App publica `solicitudes` no cambia su responsabilidad: es la unica que crea `Solicitud`.
- App interna sigue llamandose `gestion`; no renombrar app ni tablas ya creadas.
- Codigo, comentarios, mensajes de commit y docs en espanol, sin tildes en identificadores. Sin emojis en commits.
- Comando de tests del proyecto: `.venv/bin/python manage.py test` en Unix/macOS/Linux; en Windows usar `.\.venv\Scripts\python.exe manage.py test`.
- Tests contra MySQL local, no SQLite, antes de dar por terminada una tarea.
- No agregar dependencias externas.
- Las dos prioridades comparten escala exacta: `URGENTE`, `ALTA`, `MEDIA`, `BAJA`; la prioridad administrativa de `Solicitud.priorizacion_solicitud` no se sobrescribe con `Gestion.prioridad_clinica`.
- Roles exactos ya existentes en `PerfilUsuario.Rol`: `ADMIN`, `SUPERVISOR_DAS`, `SUPERVISOR_CENTRO`, `SOME`, `FULL`, `SELECTOR`, `COMUNICADOR`.
- Toda consulta operativa filtra por `PerfilUsuario.centros_permitidos()`. `ADMIN` y `SUPERVISOR_DAS` ven todos los centros.
- Abrir un caso fuera del alcance del perfil devuelve 404, no 403.
- WhatsApp se implementa solo como enlace `wa.me`; no integrar API de WhatsApp.
- Zona horaria del reloj: `America/Santiago`, usando `django.utils.timezone`.

---

## Estrategia De Ejecucion Por Etapas

Este plan es largo y debe ejecutarse por etapas. Cada tarea deja software funcional y testeable:

1. **Base de datos y ciclo de vida:** modelos, migracion, senal, querysets y admin.
2. **Autorizacion operativa:** helpers de rol/centro y carga segura de casos.
3. **Selector:** cola, detalle y decisiones/correcciones.
4. **Comunicador:** tabla, acciones de contacto y enlace WhatsApp.
5. **Cierre automatico:** comando `cerrar_rechazados`.
6. **UI/documentacion/regresion:** plantillas, navegacion, textos y verificacion manual.

Si se usa `subagent-driven-development`, despachar un subagente por tarea. Si se ejecuta inline, hacer checkpoints despues de cada tarea y correr la suite completa antes de pasar a la siguiente.

## File Structure

- Modify: `gestion/models.py` — agrega `MotivoRechazo`, `Gestion`, `GestionQuerySet`, metodos de transicion y orden de prioridades.
- Modify: `gestion/admin.py` — registra `MotivoRechazo` y `Gestion`, mantiene `PerfilUsuarioAdmin`.
- Modify: `gestion/apps.py` — carga senales con `ready()`.
- Create: `gestion/signals.py` — crea una fila `Gestion` cuando se crea una `Solicitud`.
- Create: `gestion/forms.py` — formularios de decisiones del selector y acciones del comunicador.
- Create: `gestion/permisos.py` — helpers de rol, escritura y querysets por perfil.
- Modify: `gestion/views.py` — reemplaza la pantalla inicial "en construccion" por vistas operativas.
- Modify: `gestion/urls.py` — rutas `selector/`, `selector/<id>/`, `comunicador/`, `comunicador/<id>/`.
- Create: `gestion/management/__init__.py`.
- Create: `gestion/management/commands/__init__.py`.
- Create: `gestion/management/commands/cerrar_rechazados.py` — comando horario para materializar cierres vencidos.
- Create: `gestion/templates/gestion/base.html` — layout interno.
- Create: `gestion/templates/gestion/selector_lista.html` — cola del selector.
- Create: `gestion/templates/gestion/selector_detalle.html` — detalle y formulario de decision.
- Create: `gestion/templates/gestion/comunicador_lista.html` — tabla del comunicador.
- Create: `gestion/templates/gestion/comunicador_detalle.html` — acciones de contacto.
- Create: `gestion/templates/gestion/sin_acceso.html` — pagina de acceso denegado.
- Modify: `gestion/tests.py` — tests de modelo, senal, permisos, vistas y comando.
- Create: `gestion/migrations/0002_motivo_rechazo_gestion.py` — generada por `makemigrations`.
- Modify: `docs/arquitectura-modulo-gestion.md` — actualizar estado del modulo.
- Modify: `README.md` — agregar comandos operativos del cierre automatico.

---

### Task 1: Modelos, Querysets, Senal Y Admin

**Files:**
- Modify: `gestion/models.py`
- Modify: `gestion/apps.py`
- Create: `gestion/signals.py`
- Modify: `gestion/admin.py`
- Create: `gestion/migrations/0002_motivo_rechazo_gestion.py` via `makemigrations`
- Test: `gestion/tests.py`

**Interfaces:**
- Consumes: `solicitudes.models.Solicitud`, `solicitudes.models.Centro`, `django.contrib.auth.models.User`.
- Produces:
  - `MotivoRechazo(nombre: str, mensaje_paciente: str, activo: bool, orden: int)`.
  - `Gestion(solicitud: Solicitud)` con decisiones `PENDIENTE`, `ACEPTADA`, `RECHAZADA`, `NO_APLICA`.
  - `Gestion.MotivoCierre`: `AGENDADA`, `NO_ACEPTA`, `NO_CONTACTADO`, `AVISADO_WHATSAPP`, `SIN_AVISO`.
  - `Gestion.objects.cola_selector(perfil) -> QuerySet[Gestion]`.
  - `Gestion.objects.tabla_comunicador(perfil) -> QuerySet[Gestion]`.
  - `Gestion.objects.rechazados_vencidos(ahora=None) -> QuerySet[Gestion]`.
  - `Gestion.aceptar(usuario, prioridad_clinica)`, `rechazar(usuario, motivo)`, `marcar_no_aplica(usuario)`.
  - `Gestion.registrar_no_contesta(usuario)`, `registrar_click_whatsapp(usuario)`, `registrar_agendada(usuario, fecha_hora)`, `registrar_no_acepta(usuario)`, `registrar_no_contactado(usuario)`.
  - `Gestion.url_whatsapp() -> str | None`.

- [ ] **Step 1: Escribir tests de modelos y senal**

Agregar al final de `gestion/tests.py`:

```python
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.utils import timezone

from gestion.models import Gestion, MotivoRechazo
from solicitudes.models import Solicitud


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


class GestionModeloTests(TestCase):
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
```

- [ ] **Step 2: Correr tests y confirmar falla inicial**

Run: `.venv/bin/python manage.py test gestion.tests.GestionModeloTests -v 2`
Expected: FAIL con `ImportError` o `AttributeError` porque `Gestion` y `MotivoRechazo` aun no existen.

- [ ] **Step 3: Implementar modelos y queryset**

En `gestion/models.py`, conservar `PerfilUsuario` y agregar debajo:

```python
from datetime import timedelta
from urllib.parse import quote_plus

from django.core.exceptions import ValidationError
from django.db.models import Case, IntegerField, Q, QuerySet, Value, When
from django.utils import timezone

from solicitudes.models import Solicitud


class MotivoRechazo(models.Model):
    nombre = models.CharField(max_length=120)
    mensaje_paciente = models.TextField()
    activo = models.BooleanField(default=True)
    orden = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "gestion_motivo_rechazo"
        ordering = ["orden", "nombre"]
        verbose_name = "motivo de rechazo"
        verbose_name_plural = "motivos de rechazo"

    def __str__(self):
        return self.nombre


class GestionQuerySet(QuerySet):
    def con_orden_prioridad_administrativa(self):
        return self.alias(
            orden_prioridad_admin=Case(
                When(solicitud__priorizacion_solicitud=Solicitud.Prioridad.URGENTE, then=Value(1)),
                When(solicitud__priorizacion_solicitud=Solicitud.Prioridad.ALTA, then=Value(2)),
                When(solicitud__priorizacion_solicitud=Solicitud.Prioridad.MEDIA, then=Value(3)),
                When(solicitud__priorizacion_solicitud=Solicitud.Prioridad.BAJA, then=Value(4)),
                default=Value(5),
                output_field=IntegerField(),
            )
        ).order_by("orden_prioridad_admin", "solicitud__date_solicitud")

    def con_orden_comunicador(self):
        return self.alias(
            orden_decision=Case(
                When(decision=Gestion.Decision.ACEPTADA, then=Value(1)),
                When(decision=Gestion.Decision.RECHAZADA, then=Value(2)),
                default=Value(9),
                output_field=IntegerField(),
            ),
            orden_prioridad_clinica=Case(
                When(prioridad_clinica=Solicitud.Prioridad.URGENTE, then=Value(1)),
                When(prioridad_clinica=Solicitud.Prioridad.ALTA, then=Value(2)),
                When(prioridad_clinica=Solicitud.Prioridad.MEDIA, then=Value(3)),
                When(prioridad_clinica=Solicitud.Prioridad.BAJA, then=Value(4)),
                default=Value(9),
                output_field=IntegerField(),
            ),
        ).order_by("orden_decision", "orden_prioridad_clinica", "solicitud__date_solicitud")

    def del_alcance(self, perfil):
        if perfil.ve_todos_los_centros:
            return self
        return self.filter(solicitud__centro_salud__in=perfil.centros_permitidos())

    def cola_selector(self, perfil):
        return (
            self.select_related("solicitud", "solicitud__centro_salud")
            .del_alcance(perfil)
            .filter(decision=Gestion.Decision.PENDIENTE, cerrada_en__isnull=True)
            .con_orden_prioridad_administrativa()
        )

    def tabla_comunicador(self, perfil, ahora=None):
        ahora = ahora or timezone.now()
        vencimiento = ahora - timedelta(hours=24)
        return (
            self.select_related("solicitud", "solicitud__centro_salud", "motivo_rechazo")
            .del_alcance(perfil)
            .filter(cerrada_en__isnull=True)
            .filter(Q(decision=Gestion.Decision.ACEPTADA) | Q(decision=Gestion.Decision.RECHAZADA))
            .exclude(decision=Gestion.Decision.RECHAZADA, fecha_decision__lte=vencimiento)
            .con_orden_comunicador()
        )

    def rechazados_vencidos(self, ahora=None):
        ahora = ahora or timezone.now()
        vencimiento = ahora - timedelta(hours=24)
        return self.filter(
            decision=Gestion.Decision.RECHAZADA,
            cerrada_en__isnull=True,
            fecha_decision__lte=vencimiento,
        )


class Gestion(models.Model):
    class Decision(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        ACEPTADA = "ACEPTADA", "Aceptada"
        RECHAZADA = "RECHAZADA", "Rechazada"
        NO_APLICA = "NO_APLICA", "No aplica"

    class MotivoCierre(models.TextChoices):
        AGENDADA = "AGENDADA", "Agendada"
        NO_ACEPTA = "NO_ACEPTA", "El paciente no acepta"
        NO_CONTACTADO = "NO_CONTACTADO", "No se logro contactar"
        AVISADO_WHATSAPP = "AVISADO_WHATSAPP", "Avisado por WhatsApp"
        SIN_AVISO = "SIN_AVISO", "Sin aviso"

    solicitud = models.OneToOneField(
        Solicitud,
        on_delete=models.CASCADE,
        related_name="gestion",
    )
    decision = models.CharField(
        max_length=10,
        choices=Decision.choices,
        default=Decision.PENDIENTE,
    )
    prioridad_clinica = models.CharField(
        max_length=8,
        choices=Solicitud.Prioridad.choices,
        blank=True,
    )
    motivo_rechazo = models.ForeignKey(
        MotivoRechazo,
        on_delete=models.RESTRICT,
        blank=True,
        null=True,
        related_name="gestiones",
    )
    decidido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="decisiones_gestion",
    )
    fecha_decision = models.DateTimeField(blank=True, null=True)
    fecha_hora_citacion = models.DateTimeField(blank=True, null=True)
    intentos_contacto = models.PositiveSmallIntegerField(default=0)
    fecha_ultimo_intento = models.DateTimeField(blank=True, null=True)
    aviso_whatsapp_en = models.DateTimeField(blank=True, null=True)
    contactado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="contactos_gestion",
    )
    cerrada_en = models.DateTimeField(blank=True, null=True)
    motivo_cierre = models.CharField(
        max_length=20,
        choices=MotivoCierre.choices,
        blank=True,
    )

    objects = GestionQuerySet.as_manager()

    class Meta:
        db_table = "gestion_solicitud"
        ordering = ["solicitud__date_solicitud"]
        indexes = [
            models.Index(fields=["decision", "cerrada_en"], name="gestion_dec_cierre_idx"),
            models.Index(fields=["fecha_decision"], name="gestion_fecha_dec_idx"),
        ]
        verbose_name = "gestion de solicitud"
        verbose_name_plural = "gestiones de solicitudes"

    def __str__(self):
        return f"Gestion #{self.pk} - solicitud #{self.solicitud_id}"

    @property
    def puede_corregir_decision(self):
        return self.intentos_contacto == 0 and self.cerrada_en is None

    def clean(self):
        super().clean()
        if self.decision == self.Decision.ACEPTADA and not self.prioridad_clinica:
            raise ValidationError({"prioridad_clinica": "Debe indicar prioridad clinica."})
        if self.decision == self.Decision.RECHAZADA and not self.motivo_rechazo_id:
            raise ValidationError({"motivo_rechazo": "Debe indicar motivo de rechazo."})
        if self.fecha_hora_citacion and self.motivo_cierre != self.MotivoCierre.AGENDADA:
            raise ValidationError({"fecha_hora_citacion": "Solo una cita agendada puede tener fecha y hora."})

    def _registrar_decision(self, usuario):
        if not self.puede_corregir_decision:
            raise ValidationError("La decision no se puede corregir porque ya hay intentos registrados.")
        self.decidido_por = usuario
        self.fecha_decision = timezone.now()
        self.cerrada_en = None
        self.motivo_cierre = ""

    def aceptar(self, usuario, prioridad_clinica):
        if not prioridad_clinica:
            raise ValidationError({"prioridad_clinica": "Debe indicar prioridad clinica."})
        self._registrar_decision(usuario)
        self.decision = self.Decision.ACEPTADA
        self.prioridad_clinica = prioridad_clinica
        self.motivo_rechazo = None
        self.full_clean()
        self.save()

    def rechazar(self, usuario, motivo):
        if motivo is None:
            raise ValidationError({"motivo_rechazo": "Debe indicar motivo de rechazo."})
        self._registrar_decision(usuario)
        self.decision = self.Decision.RECHAZADA
        self.prioridad_clinica = ""
        self.motivo_rechazo = motivo
        self.full_clean()
        self.save()

    def marcar_no_aplica(self, usuario):
        self._registrar_decision(usuario)
        self.decision = self.Decision.NO_APLICA
        self.prioridad_clinica = ""
        self.motivo_rechazo = None
        self.full_clean()
        self.save()

    def _registrar_intento(self, usuario, cerrar=False, motivo_cierre=""):
        self.intentos_contacto += 1
        self.fecha_ultimo_intento = timezone.now()
        self.contactado_por = usuario
        if cerrar:
            self.cerrada_en = timezone.now()
            self.motivo_cierre = motivo_cierre
        self.full_clean()
        self.save()

    def registrar_no_contesta(self, usuario):
        self._registrar_intento(usuario)

    def registrar_click_whatsapp(self, usuario):
        if self.aviso_whatsapp_en is None:
            self.aviso_whatsapp_en = timezone.now()
        self._registrar_intento(usuario)

    def registrar_agendada(self, usuario, fecha_hora):
        self.fecha_hora_citacion = fecha_hora
        self._registrar_intento(usuario, cerrar=True, motivo_cierre=self.MotivoCierre.AGENDADA)

    def registrar_no_acepta(self, usuario):
        self._registrar_intento(usuario, cerrar=True, motivo_cierre=self.MotivoCierre.NO_ACEPTA)

    def registrar_no_contactado(self, usuario):
        self._registrar_intento(usuario, cerrar=True, motivo_cierre=self.MotivoCierre.NO_CONTACTADO)

    def cerrar_rechazado_automatico(self, ahora=None):
        ahora = ahora or timezone.now()
        self.cerrada_en = ahora
        self.motivo_cierre = (
            self.MotivoCierre.AVISADO_WHATSAPP
            if self.aviso_whatsapp_en
            else self.MotivoCierre.SIN_AVISO
        )
        self.full_clean()
        self.save()

    def url_whatsapp(self):
        telefono = "".join(ch for ch in self.solicitud.telefono if ch.isdigit())
        if not telefono:
            return None
        if self.motivo_rechazo_id:
            mensaje_base = self.motivo_rechazo.mensaje_paciente
        else:
            mensaje_base = "Hola {nombre}, le contactamos desde su centro de salud por su solicitud de morbilidad."
        mensaje = mensaje_base.format(nombre=self.solicitud.nombre)
        return f"https://wa.me/{telefono}?text={quote_plus(mensaje)}"
```

- [ ] **Step 4: Crear senal en `gestion/signals.py`**

```python
from django.db.models.signals import post_save
from django.dispatch import receiver

from solicitudes.models import Solicitud

from .models import Gestion


@receiver(post_save, sender=Solicitud)
def crear_gestion_para_solicitud(sender, instance, created, **kwargs):
    if created:
        Gestion.objects.get_or_create(solicitud=instance)
```

- [ ] **Step 5: Cargar senales en `gestion/apps.py`**

Reemplazar el archivo por:

```python
from django.apps import AppConfig


class GestionConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "gestion"

    def ready(self):
        from . import signals  # noqa: F401
```

- [ ] **Step 6: Registrar admin**

En `gestion/admin.py`, mantener `PerfilUsuarioAdmin` y agregar:

```python
from .models import Gestion, MotivoRechazo, PerfilUsuario


@admin.register(MotivoRechazo)
class MotivoRechazoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "activo", "orden")
    list_filter = ("activo",)
    search_fields = ("nombre", "mensaje_paciente")
    ordering = ("orden", "nombre")


@admin.register(Gestion)
class GestionAdmin(admin.ModelAdmin):
    list_display = (
        "solicitud",
        "decision",
        "prioridad_clinica",
        "motivo_rechazo",
        "intentos_contacto",
        "cerrada_en",
        "motivo_cierre",
    )
    list_filter = ("decision", "prioridad_clinica", "motivo_cierre", "solicitud__centro_salud")
    search_fields = ("solicitud__nombre", "solicitud__rut", "solicitud__telefono")
    readonly_fields = ("solicitud",)
    list_select_related = ("solicitud", "motivo_rechazo", "decidido_por", "contactado_por")
```

- [ ] **Step 7: Generar migracion**

Run: `.venv/bin/python manage.py makemigrations gestion`
Expected: crea `gestion/migrations/0002_motivo_rechazo_gestion.py`.

- [ ] **Step 8: Ajustar migracion para filas existentes**

Editar la migracion generada y agregar una operacion `RunPython` despues de crear `Gestion`:

```python
def crear_gestiones_existentes(apps, schema_editor):
    Solicitud = apps.get_model("solicitudes", "Solicitud")
    Gestion = apps.get_model("gestion", "Gestion")
    existentes = set(Gestion.objects.values_list("solicitud_id", flat=True))
    nuevas = [
        Gestion(solicitud_id=solicitud_id)
        for solicitud_id in Solicitud.objects.values_list("id_solicitud", flat=True)
        if solicitud_id not in existentes
    ]
    Gestion.objects.bulk_create(nuevas, ignore_conflicts=True)
```

Agregar a `operations`:

```python
migrations.RunPython(crear_gestiones_existentes, migrations.RunPython.noop),
```

- [ ] **Step 9: Correr tests del modelo**

Run: `.venv/bin/python manage.py test gestion.tests.GestionModeloTests -v 2`
Expected: PASS.

- [ ] **Step 10: Correr regresion completa**

Run: `.venv/bin/python manage.py test`
Expected: PASS.

- [ ] **Step 11: Commit**

```bash
git add gestion/models.py gestion/apps.py gestion/signals.py gestion/admin.py gestion/migrations/0002_motivo_rechazo_gestion.py gestion/tests.py
git commit -m "Agrega ciclo de vida base para solicitudes en gestion"
```

---

### Task 2: Permisos Operativos Y Carga Segura De Casos

**Files:**
- Create: `gestion/permisos.py`
- Modify: `gestion/tests.py`

**Interfaces:**
- Consumes: `PerfilUsuario.Rol`, `Gestion.objects.del_alcance(perfil)`.
- Produces:
  - `obtener_perfil_activo(usuario) -> PerfilUsuario | None`.
  - `puede_usar_selector(perfil) -> bool`.
  - `puede_usar_comunicador(perfil) -> bool`.
  - `puede_escribir_selector(perfil) -> bool`.
  - `puede_escribir_comunicador(perfil) -> bool`.
  - `puede_ver_no_aplica(perfil) -> bool`.
  - `gestion_alcanzable_o_404(perfil, pk) -> Gestion`.

- [ ] **Step 1: Escribir tests de permisos**

Agregar a `gestion/tests.py`:

```python
from django.http import Http404

from gestion.permisos import (
    gestion_alcanzable_o_404,
    puede_escribir_comunicador,
    puede_escribir_selector,
    puede_usar_comunicador,
    puede_usar_selector,
    puede_ver_no_aplica,
)


class PermisosGestionTests(TestCase):
    def setUp(self):
        self.centro = Centro.objects.get(pk=620)
        self.otro_centro = Centro.objects.get(pk=621)

    def _perfil(self, rol, centro=None):
        usuario = User.objects.create_user(f"{rol.lower()}@cmvalparaiso.cl")
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
```

- [ ] **Step 2: Correr tests y confirmar falla inicial**

Run: `.venv/bin/python manage.py test gestion.tests.PermisosGestionTests -v 2`
Expected: FAIL con `ModuleNotFoundError: No module named 'gestion.permisos'`.

- [ ] **Step 3: Crear `gestion/permisos.py`**

```python
from django.shortcuts import get_object_or_404

from .models import Gestion, PerfilUsuario


ROLES_SELECTOR = {
    PerfilUsuario.Rol.SELECTOR,
    PerfilUsuario.Rol.FULL,
    PerfilUsuario.Rol.SOME,
}
ROLES_COMUNICADOR = {
    PerfilUsuario.Rol.COMUNICADOR,
    PerfilUsuario.Rol.FULL,
    PerfilUsuario.Rol.SOME,
}
ROLES_SOLO_LECTURA = {
    PerfilUsuario.Rol.SUPERVISOR_CENTRO,
    PerfilUsuario.Rol.SUPERVISOR_DAS,
    PerfilUsuario.Rol.ADMIN,
}


def obtener_perfil_activo(usuario):
    if not usuario.is_authenticated or not usuario.is_active:
        return None
    perfil = getattr(usuario, "perfil_gestion", None)
    if perfil is None or not perfil.activo:
        return None
    return perfil


def puede_usar_selector(perfil):
    return perfil.rol in ROLES_SELECTOR | ROLES_SOLO_LECTURA


def puede_usar_comunicador(perfil):
    return perfil.rol in ROLES_COMUNICADOR | ROLES_SOLO_LECTURA


def puede_escribir_selector(perfil):
    return perfil.rol in ROLES_SELECTOR


def puede_escribir_comunicador(perfil):
    return perfil.rol in ROLES_COMUNICADOR


def puede_ver_no_aplica(perfil):
    return perfil.rol != PerfilUsuario.Rol.COMUNICADOR


def gestion_alcanzable_o_404(perfil, pk):
    queryset = Gestion.objects.select_related(
        "solicitud",
        "solicitud__centro_salud",
        "motivo_rechazo",
        "decidido_por",
        "contactado_por",
    ).del_alcance(perfil)
    return get_object_or_404(queryset, pk=pk)
```

- [ ] **Step 4: Correr tests de permisos**

Run: `.venv/bin/python manage.py test gestion.tests.PermisosGestionTests -v 2`
Expected: PASS.

- [ ] **Step 5: Correr regresion completa**

Run: `.venv/bin/python manage.py test`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add gestion/permisos.py gestion/tests.py
git commit -m "Define permisos operativos por rol y centro"
```

---

### Task 3: Pantalla Del Selector Y Decisiones

**Files:**
- Create: `gestion/forms.py`
- Modify: `gestion/views.py`
- Modify: `gestion/urls.py`
- Create: `gestion/templates/gestion/base.html`
- Create: `gestion/templates/gestion/selector_lista.html`
- Create: `gestion/templates/gestion/selector_detalle.html`
- Modify: `gestion/tests.py`

**Interfaces:**
- Consumes: `Gestion.aceptar`, `Gestion.rechazar`, `Gestion.marcar_no_aplica`, permisos de Task 2.
- Produces: rutas `gestion:selector_lista`, `gestion:selector_detalle`; formulario `DecisionSelectorForm`.

- [ ] **Step 1: Escribir tests de selector**

Agregar a `gestion/tests.py`:

```python
class SelectorViewsTests(TestCase):
    def setUp(self):
        self.centro = Centro.objects.get(pk=620)
        self.otro_centro = Centro.objects.get(pk=621)
        self.usuario = User.objects.create_user("selector@cmvalparaiso.cl", email="selector@cmvalparaiso.cl")
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
        baja = crear_solicitud_base(centro_salud=self.centro, priorizacion_solicitud=Solicitud.Prioridad.BAJA).gestion
        urgente = crear_solicitud_base(centro_salud=self.centro, priorizacion_solicitud=Solicitud.Prioridad.URGENTE).gestion
        crear_solicitud_base(centro_salud=self.otro_centro, priorizacion_solicitud=Solicitud.Prioridad.URGENTE)

        response = self.client.get("/selector/", HTTP_HOST="gestion.localhost")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["gestiones"]), [urgente, baja])

    def test_aceptar_registra_prioridad_clinica(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        response = self.client.post(
            f"/selector/{gestion.pk}/",
            {"decision": Gestion.Decision.ACEPTADA, "prioridad_clinica": Solicitud.Prioridad.ALTA},
            HTTP_HOST="gestion.localhost",
        )
        self.assertEqual(response.status_code, 302)
        gestion.refresh_from_db()
        self.assertEqual(gestion.decision, Gestion.Decision.ACEPTADA)
        self.assertEqual(gestion.prioridad_clinica, Solicitud.Prioridad.ALTA)

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
        self.assertFalse(Gestion.objects.tabla_comunicador(self.perfil).filter(pk=gestion.pk).exists())

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

    def test_comunicador_no_puede_entrar_a_selector(self):
        self.perfil.rol = PerfilUsuario.Rol.COMUNICADOR
        self.perfil.save()
        response = self.client.get("/selector/", HTTP_HOST="gestion.localhost")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/sin-acceso/", response["Location"])
```

- [ ] **Step 2: Correr tests y confirmar falla inicial**

Run: `.venv/bin/python manage.py test gestion.tests.SelectorViewsTests -v 2`
Expected: FAIL con 404 para `/selector/`.

- [ ] **Step 3: Crear `DecisionSelectorForm` en `gestion/forms.py`**

```python
from django import forms

from solicitudes.models import Solicitud

from .models import Gestion, MotivoRechazo


class DecisionSelectorForm(forms.Form):
    decision = forms.ChoiceField(choices=Gestion.Decision.choices)
    prioridad_clinica = forms.ChoiceField(
        choices=[("", "Seleccione prioridad clinica")] + list(Solicitud.Prioridad.choices),
        required=False,
    )
    motivo_rechazo = forms.ModelChoiceField(
        queryset=MotivoRechazo.objects.none(),
        required=False,
        empty_label="Seleccione motivo de rechazo",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["motivo_rechazo"].queryset = MotivoRechazo.objects.filter(activo=True)

    def clean(self):
        cleaned = super().clean()
        decision = cleaned.get("decision")
        if decision == Gestion.Decision.ACEPTADA and not cleaned.get("prioridad_clinica"):
            self.add_error("prioridad_clinica", "Debe indicar prioridad clinica.")
        if decision == Gestion.Decision.RECHAZADA and not cleaned.get("motivo_rechazo"):
            self.add_error("motivo_rechazo", "Debe indicar motivo de rechazo.")
        return cleaned

    def guardar(self, gestion, usuario):
        decision = self.cleaned_data["decision"]
        if decision == Gestion.Decision.ACEPTADA:
            gestion.aceptar(usuario, self.cleaned_data["prioridad_clinica"])
        elif decision == Gestion.Decision.RECHAZADA:
            gestion.rechazar(usuario, self.cleaned_data["motivo_rechazo"])
        elif decision == Gestion.Decision.NO_APLICA:
            gestion.marcar_no_aplica(usuario)
        return gestion
```

- [ ] **Step 4: Implementar vistas del selector**

En `gestion/views.py`, importar `render`, `get_object_or_404`, `messages`, formularios y permisos; reemplazar `panel` para redirigir a selector/comunicador segun rol, y agregar:

```python
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import render

from .forms import DecisionSelectorForm
from .models import Gestion
from .permisos import (
    gestion_alcanzable_o_404,
    obtener_perfil_activo,
    puede_escribir_selector,
    puede_usar_selector,
)


@login_required
def selector_lista(request):
    perfil = obtener_perfil_activo(request.user)
    if perfil is None or not puede_usar_selector(perfil):
        return redirect("gestion:sin_acceso")
    gestiones = Gestion.objects.cola_selector(perfil)
    return render(
        request,
        "gestion/selector_lista.html",
        {"perfil": perfil, "gestiones": gestiones, "puede_escribir": puede_escribir_selector(perfil)},
    )


@login_required
def selector_detalle(request, pk):
    perfil = obtener_perfil_activo(request.user)
    if perfil is None or not puede_usar_selector(perfil):
        return redirect("gestion:sin_acceso")
    gestion = gestion_alcanzable_o_404(perfil, pk)
    puede_escribir = puede_escribir_selector(perfil)
    form = DecisionSelectorForm(request.POST or None)
    if request.method == "POST":
        if not puede_escribir:
            return redirect("gestion:sin_acceso")
        if form.is_valid():
            try:
                form.guardar(gestion, request.user)
                messages.success(request, "Decision registrada.")
                return redirect("gestion:selector_lista")
            except ValidationError as exc:
                form.add_error(None, exc)
    return render(
        request,
        "gestion/selector_detalle.html",
        {"perfil": perfil, "gestion": gestion, "form": form, "puede_escribir": puede_escribir},
    )
```

- [ ] **Step 5: Agregar rutas**

En `gestion/urls.py`, agregar:

```python
path("selector/", views.selector_lista, name="selector_lista"),
path("selector/<int:pk>/", views.selector_detalle, name="selector_detalle"),
```

- [ ] **Step 6: Crear plantillas minimas**

`gestion/templates/gestion/base.html`:

```html
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}Modulo de seleccion{% endblock %}</title>
</head>
<body>
  <nav>
    <a href="{% url 'gestion:selector_lista' %}">Selector</a>
  </nav>
  {% for message in messages %}<p>{{ message }}</p>{% endfor %}
  {% block content %}{% endblock %}
</body>
</html>
```

`gestion/templates/gestion/selector_lista.html`:

```html
{% extends "gestion/base.html" %}
{% block title %}Cola del selector{% endblock %}
{% block content %}
<h1>Cola del selector</h1>
<table>
  <thead><tr><th>Paciente</th><th>Centro</th><th>Prioridad administrativa</th><th>Fecha</th><th></th></tr></thead>
  <tbody>
    {% for gestion in gestiones %}
      <tr>
        <td>{{ gestion.solicitud.nombre }}</td>
        <td>{{ gestion.solicitud.centro_salud }}</td>
        <td>{{ gestion.solicitud.get_priorizacion_solicitud_display }}</td>
        <td>{{ gestion.solicitud.date_solicitud }}</td>
        <td><a href="{% url 'gestion:selector_detalle' gestion.pk %}">Abrir</a></td>
      </tr>
    {% empty %}
      <tr><td colspan="5">No hay solicitudes pendientes.</td></tr>
    {% endfor %}
  </tbody>
</table>
{% endblock %}
```

`gestion/templates/gestion/selector_detalle.html`:

```html
{% extends "gestion/base.html" %}
{% block title %}Solicitud {{ gestion.solicitud_id }}{% endblock %}
{% block content %}
<h1>{{ gestion.solicitud.nombre }}</h1>
<p>{{ gestion.solicitud.rut }} - {{ gestion.solicitud.telefono }}</p>
<p>{{ gestion.solicitud.motivo }}</p>
<p>{{ gestion.solicitud.detalle_motivo }}</p>
{% if form.non_field_errors %}{{ form.non_field_errors }}{% endif %}
{% if puede_escribir %}
  <form method="post">
    {% csrf_token %}
    {{ form.as_p }}
    <button type="submit">Guardar decision</button>
  </form>
{% else %}
  <p>Vista de solo lectura.</p>
{% endif %}
{% endblock %}
```

- [ ] **Step 7: Correr tests del selector**

Run: `.venv/bin/python manage.py test gestion.tests.SelectorViewsTests -v 2`
Expected: PASS.

- [ ] **Step 8: Correr regresion completa**

Run: `.venv/bin/python manage.py test`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add gestion/forms.py gestion/views.py gestion/urls.py gestion/templates/gestion/base.html gestion/templates/gestion/selector_lista.html gestion/templates/gestion/selector_detalle.html gestion/tests.py
git commit -m "Implementa cola y decisiones del selector"
```

---

### Task 4: Tabla Del Comunicador, Contactos Y WhatsApp

**Files:**
- Modify: `gestion/forms.py`
- Modify: `gestion/views.py`
- Modify: `gestion/urls.py`
- Create: `gestion/templates/gestion/comunicador_lista.html`
- Create: `gestion/templates/gestion/comunicador_detalle.html`
- Modify: `gestion/tests.py`

**Interfaces:**
- Consumes: `Gestion.objects.tabla_comunicador(perfil)`, metodos de contacto de Task 1, permisos de Task 2.
- Produces: rutas `gestion:comunicador_lista`, `gestion:comunicador_detalle`, `gestion:whatsapp`.
- Produces: `AccionComunicadorForm`.

- [ ] **Step 1: Escribir tests del comunicador**

Agregar a `gestion/tests.py`:

```python
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
        response = self.client.post(f"/comunicador/{gestion.pk}/whatsapp/", HTTP_HOST="gestion.localhost")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("https://wa.me/"))
        gestion.refresh_from_db()
        self.assertEqual(gestion.intentos_contacto, 1)
        self.assertIsNotNone(gestion.aviso_whatsapp_en)
        self.assertIsNone(gestion.cerrada_en)

    def test_selector_no_puede_entrar_a_comunicador(self):
        self.perfil.rol = PerfilUsuario.Rol.SELECTOR
        self.perfil.save()
        response = self.client.get("/comunicador/", HTTP_HOST="gestion.localhost")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/sin-acceso/", response["Location"])
```

- [ ] **Step 2: Correr tests y confirmar falla inicial**

Run: `.venv/bin/python manage.py test gestion.tests.ComunicadorViewsTests -v 2`
Expected: FAIL con 404 para `/comunicador/`.

- [ ] **Step 3: Agregar `AccionComunicadorForm`**

En `gestion/forms.py`, agregar:

```python
class AccionComunicadorForm(forms.Form):
    AGENDADA = "AGENDADA"
    NO_ACEPTA = "NO_ACEPTA"
    NO_CONTESTA = "NO_CONTESTA"
    NO_CONTACTADO = "NO_CONTACTADO"

    accion = forms.ChoiceField(
        choices=[
            (AGENDADA, "Agendada"),
            (NO_ACEPTA, "El paciente no acepta la citacion"),
            (NO_CONTESTA, "No contesta"),
            (NO_CONTACTADO, "No se logro contactar"),
        ]
    )
    fecha_hora_citacion = forms.DateTimeField(
        required=False,
        input_formats=["%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("accion") == self.AGENDADA and not cleaned.get("fecha_hora_citacion"):
            self.add_error("fecha_hora_citacion", "Debe indicar fecha y hora acordadas.")
        return cleaned

    def guardar(self, gestion, usuario):
        accion = self.cleaned_data["accion"]
        if accion == self.AGENDADA:
            gestion.registrar_agendada(usuario, self.cleaned_data["fecha_hora_citacion"])
        elif accion == self.NO_ACEPTA:
            gestion.registrar_no_acepta(usuario)
        elif accion == self.NO_CONTESTA:
            gestion.registrar_no_contesta(usuario)
        elif accion == self.NO_CONTACTADO:
            gestion.registrar_no_contactado(usuario)
        return gestion
```

- [ ] **Step 4: Implementar vistas del comunicador**

En `gestion/views.py`, agregar:

```python
from django.http import HttpResponseRedirect

from .forms import AccionComunicadorForm
from .permisos import puede_escribir_comunicador, puede_usar_comunicador


@login_required
def comunicador_lista(request):
    perfil = obtener_perfil_activo(request.user)
    if perfil is None or not puede_usar_comunicador(perfil):
        return redirect("gestion:sin_acceso")
    gestiones = Gestion.objects.tabla_comunicador(perfil)
    return render(
        request,
        "gestion/comunicador_lista.html",
        {"perfil": perfil, "gestiones": gestiones, "puede_escribir": puede_escribir_comunicador(perfil)},
    )


@login_required
def comunicador_detalle(request, pk):
    perfil = obtener_perfil_activo(request.user)
    if perfil is None or not puede_usar_comunicador(perfil):
        return redirect("gestion:sin_acceso")
    gestion = gestion_alcanzable_o_404(perfil, pk)
    puede_escribir = puede_escribir_comunicador(perfil)
    form = AccionComunicadorForm(request.POST or None)
    if request.method == "POST":
        if not puede_escribir:
            return redirect("gestion:sin_acceso")
        if form.is_valid():
            form.guardar(gestion, request.user)
            messages.success(request, "Contacto registrado.")
            return redirect("gestion:comunicador_lista")
    return render(
        request,
        "gestion/comunicador_detalle.html",
        {"perfil": perfil, "gestion": gestion, "form": form, "puede_escribir": puede_escribir},
    )


@login_required
def registrar_whatsapp(request, pk):
    perfil = obtener_perfil_activo(request.user)
    if perfil is None or not puede_escribir_comunicador(perfil):
        return redirect("gestion:sin_acceso")
    gestion = gestion_alcanzable_o_404(perfil, pk)
    url = gestion.url_whatsapp()
    if not url:
        messages.error(request, "La solicitud no tiene un telefono valido para WhatsApp.")
        return redirect("gestion:comunicador_detalle", pk=gestion.pk)
    gestion.registrar_click_whatsapp(request.user)
    return HttpResponseRedirect(url)
```

- [ ] **Step 5: Agregar rutas**

En `gestion/urls.py`, agregar:

```python
path("comunicador/", views.comunicador_lista, name="comunicador_lista"),
path("comunicador/<int:pk>/", views.comunicador_detalle, name="comunicador_detalle"),
path("comunicador/<int:pk>/whatsapp/", views.registrar_whatsapp, name="whatsapp"),
```

- [ ] **Step 6: Crear plantillas**

En `gestion/templates/gestion/base.html`, agregar el enlace al comunicador dentro de `<nav>`:

```html
<a href="{% url 'gestion:comunicador_lista' %}">Comunicador</a>
```

`gestion/templates/gestion/comunicador_lista.html`:

```html
{% extends "gestion/base.html" %}
{% block title %}Tabla del comunicador{% endblock %}
{% block content %}
<h1>Tabla del comunicador</h1>
<table>
  <thead><tr><th>Paciente</th><th>Telefono</th><th>Prioridad</th><th>Intentos</th><th>Ultimo intento</th><th>Motivo</th><th></th></tr></thead>
  <tbody>
    {% for gestion in gestiones %}
      <tr>
        <td>{{ gestion.solicitud.nombre }}</td>
        <td>{{ gestion.solicitud.telefono }}</td>
        <td>{% if gestion.decision == "ACEPTADA" %}{{ gestion.get_prioridad_clinica_display }}{% else %}Rechazada{% endif %}</td>
        <td>{{ gestion.intentos_contacto }}</td>
        <td>{{ gestion.fecha_ultimo_intento|default:"-" }}</td>
        <td>{{ gestion.motivo_rechazo|default:"-" }}</td>
        <td><a href="{% url 'gestion:comunicador_detalle' gestion.pk %}">Abrir</a></td>
      </tr>
    {% empty %}
      <tr><td colspan="7">No hay casos pendientes de comunicacion.</td></tr>
    {% endfor %}
  </tbody>
</table>
{% endblock %}
```

`gestion/templates/gestion/comunicador_detalle.html`:

```html
{% extends "gestion/base.html" %}
{% block title %}Contacto {{ gestion.solicitud_id }}{% endblock %}
{% block content %}
<h1>{{ gestion.solicitud.nombre }}</h1>
<p>{{ gestion.solicitud.telefono }} - {{ gestion.solicitud.centro_salud }}</p>
<p>Decision: {{ gestion.get_decision_display }}</p>
{% if gestion.motivo_rechazo %}<p>Motivo: {{ gestion.motivo_rechazo }}</p>{% endif %}
{% if puede_escribir %}
  <form method="post">
    {% csrf_token %}
    {{ form.as_p }}
    <button type="submit">Registrar contacto</button>
  </form>
  <form method="post" action="{% url 'gestion:whatsapp' gestion.pk %}">
    {% csrf_token %}
    <button type="submit">Abrir WhatsApp</button>
  </form>
{% else %}
  <p>Vista de solo lectura.</p>
{% endif %}
{% endblock %}
```

- [ ] **Step 7: Correr tests del comunicador**

Run: `.venv/bin/python manage.py test gestion.tests.ComunicadorViewsTests -v 2`
Expected: PASS.

- [ ] **Step 8: Correr regresion completa**

Run: `.venv/bin/python manage.py test`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add gestion/forms.py gestion/views.py gestion/urls.py gestion/templates/gestion/comunicador_lista.html gestion/templates/gestion/comunicador_detalle.html gestion/tests.py
git commit -m "Implementa tabla y acciones del comunicador"
```

---

### Task 5: Comando De Cierre Automatico De Rechazados

**Files:**
- Create: `gestion/management/__init__.py`
- Create: `gestion/management/commands/__init__.py`
- Create: `gestion/management/commands/cerrar_rechazados.py`
- Modify: `gestion/tests.py`

**Interfaces:**
- Consumes: `Gestion.objects.rechazados_vencidos()`, `Gestion.cerrar_rechazado_automatico()`.
- Produces: `manage.py cerrar_rechazados`.

- [ ] **Step 1: Escribir tests del comando**

Agregar a `gestion/tests.py`:

```python
from io import StringIO

from django.core.management import call_command


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
        self.assertEqual(gestion.motivo_cierre, Gestion.MotivoCierre.AVISADO_WHATSAPP)

    def test_no_cierra_rechazado_menor_a_24_horas(self):
        gestion = crear_solicitud_base().gestion
        gestion.rechazar(self.usuario, self.motivo)
        call_command("cerrar_rechazados")
        gestion.refresh_from_db()
        self.assertIsNone(gestion.cerrada_en)
```

- [ ] **Step 2: Correr tests y confirmar falla inicial**

Run: `.venv/bin/python manage.py test gestion.tests.CerrarRechazadosCommandTests -v 2`
Expected: FAIL con `Unknown command: 'cerrar_rechazados'`.

- [ ] **Step 3: Crear comando**

`gestion/management/commands/cerrar_rechazados.py`:

```python
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
```

- [ ] **Step 4: Correr tests del comando**

Run: `.venv/bin/python manage.py test gestion.tests.CerrarRechazadosCommandTests -v 2`
Expected: PASS.

- [ ] **Step 5: Correr regresion completa**

Run: `.venv/bin/python manage.py test`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add gestion/management gestion/tests.py
git commit -m "Agrega cierre automatico de rechazados"
```

---

### Task 6: Navegacion, Documentacion Y Verificacion Final

**Files:**
- Modify: `gestion/views.py`
- Modify: `gestion/templates/gestion/base.html`
- Modify: `gestion/templates/gestion/sin_acceso.html`
- Modify: `docs/arquitectura-modulo-gestion.md`
- Modify: `README.md`
- Modify: `gestion/tests.py`

**Interfaces:**
- Consumes: tareas 1-5.
- Produces: `panel()` redirige a pantalla principal segun rol y docs operativas.

- [ ] **Step 1: Escribir tests del panel principal**

Agregar a `gestion/tests.py`:

```python
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
```

- [ ] **Step 2: Implementar redireccion del panel**

En `gestion/views.py`, reemplazar `panel` por:

```python
@login_required
def panel(request):
    perfil = obtener_perfil_activo(request.user)
    if perfil is None:
        return redirect("gestion:sin_acceso")
    if puede_usar_selector(perfil):
        return redirect("gestion:selector_lista")
    if puede_usar_comunicador(perfil):
        return redirect("gestion:comunicador_lista")
    return redirect("gestion:sin_acceso")
```

- [ ] **Step 3: Crear `sin_acceso.html` y usar plantilla**

`gestion/templates/gestion/sin_acceso.html`:

```html
{% extends "gestion/base.html" %}
{% block title %}Sin acceso{% endblock %}
{% block content %}
<h1>Sin acceso</h1>
<p>Su cuenta no tiene acceso al modulo de seleccion.</p>
{% endblock %}
```

En `gestion/views.py`, reemplazar `sin_acceso` por:

```python
def sin_acceso(request):
    return render(request, "gestion/sin_acceso.html")
```

- [ ] **Step 4: Actualizar docs**

En `README.md`, agregar una seccion:

```markdown
## Modulo de seleccion: operacion local

El flujo operativo vive en el host de gestion:

- Selector: `http://127.0.0.1:8000/selector/`
- Comunicador: `http://127.0.0.1:8000/comunicador/`

El cierre automatico de rechazados se ejecuta con:

```bash
.venv/bin/python manage.py cerrar_rechazados
```

En produccion debe programarse cada hora por cron o por el scheduler disponible.
La vista del comunicador filtra en vivo los rechazados vencidos, asi que una
caida del cron no muestra trabajo vencido; solo retrasa el dato historico de
`cerrada_en` y `motivo_cierre`.
```

En `docs/arquitectura-modulo-gestion.md`, en la seccion `## Estado`, reemplazar el parrafo de estado actual por:

```markdown
Decision de arquitectura **aprobada**. Autenticacion y perfiles
**implementados** (ver `docs/superpowers/plans/2026-07-27-login-google-perfiles.md`).
Modelo `Gestion`, cola del selector, tabla del comunicador, enlace de WhatsApp
y cierre automatico de rechazados **implementados** (ver
`docs/superpowers/plans/2026-08-19-modulo-seleccion.md`).

Pendientes fuera de este alcance: reportes, estadisticas, tableros, agenda
propia, administracion de cupos, UI de gestion de perfiles para el rol `SOME`,
API de WhatsApp y mejoras futuras del chatbot.
```

- [ ] **Step 5: Correr tests del panel**

Run: `.venv/bin/python manage.py test gestion.tests.PanelRedireccionTests -v 2`
Expected: PASS.

- [ ] **Step 6: Correr verificaciones finales**

Run: `.venv/bin/python manage.py makemigrations --check --dry-run`
Expected: `No changes detected`.

Run: `.venv/bin/python manage.py check`
Expected: `System check identified no issues`.

Run: `.venv/bin/python manage.py test`
Expected: PASS.

- [ ] **Step 7: Verificacion manual local**

Con MySQL arriba (`docker compose up -d`) y un usuario con `PerfilUsuario` activo:

```bash
.venv/bin/python manage.py runserver
```

Abrir:

- `http://localhost:8000/` debe seguir mostrando el chatbot.
- `http://127.0.0.1:8000/selector/` debe mostrar la cola del selector si el rol puede usarla.
- `http://127.0.0.1:8000/comunicador/` debe mostrar la tabla del comunicador si el rol puede usarla.
- Un `SELECTOR` que abra `/comunicador/` debe caer en `/sin-acceso/`.
- Un `COMUNICADOR` que abra `/selector/` debe caer en `/sin-acceso/`.
- Al aceptar una solicitud, debe aparecer en la tabla del comunicador.
- Al rechazar una solicitud, debe aparecer con boton de WhatsApp y salir de la tabla 24 horas despues de `fecha_decision`.

- [ ] **Step 8: Commit**

```bash
git add gestion/views.py gestion/templates/gestion/base.html gestion/templates/gestion/sin_acceso.html gestion/tests.py README.md docs/arquitectura-modulo-gestion.md
git commit -m "Documenta y conecta el modulo de seleccion"
```

---

## Self-Review

**1. Spec coverage**

- Modelo `Gestion` con ciclo de vida completo: Task 1.
- Catalogo editable de motivos de rechazo y mensaje al paciente: Task 1 admin + Task 3 form.
- Cola del selector con tres decisiones: Task 3.
- Correccion bloqueada despues de intentos del comunicador: Task 1 `puede_corregir_decision` + Task 3 test.
- Tabla del comunicador, intentos, contacto y WhatsApp: Task 4.
- Rechazados al final y aceptados ordenados por prioridad clinica: Task 1 queryset + Task 4 test.
- Cierre automatico a 24 horas con `AVISADO_WHATSAPP` y `SIN_AVISO`: Task 5.
- Filtrado por centro y por rol: Task 2 + tests de vistas Tasks 3 y 4.
- 404 para casos fuera de alcance: Task 2.
- No tocar chatbot como creador de `Solicitud`: Task 1 integra con senal en `gestion`, no modifica `solicitudes.views`.
- Solicitudes anteriores al despliegue reciben fila `Gestion`: Task 1 migracion `RunPython`.
- Telefono invalido no arma WhatsApp: Task 1 test `url_whatsapp_none_con_telefono_invalido`.
- No se implementa API WhatsApp ni reportes: fuera del file structure y de las tareas.

**2. Escaneo de relleno**

No quedan instrucciones abiertas ni pasos que deleguen decisiones esenciales al implementador. Los cambios documentales incluyen el texto exacto que debe agregarse o reemplazarse.

**3. Type consistency**

- `Gestion.Decision` se define en Task 1 y se consume con los mismos nombres en formularios, vistas y tests.
- `Gestion.MotivoCierre` se define en Task 1 y se consume en Task 5.
- `Gestion.objects.tabla_comunicador(perfil)` y `Gestion.objects.cola_selector(perfil)` se definen en Task 1 y se consumen en Tasks 3 y 4.
- `gestion_alcanzable_o_404(perfil, pk)` se define en Task 2 y se consume en Tasks 3 y 4.
- `AccionComunicadorForm` produce accion `NO_CONTESTA`, que no se guarda como estado persistente; solo llama `registrar_no_contesta`.

**4. Riesgos de ejecucion**

- La migracion agrega indices por `decision/cerrada_en` y `fecha_decision`; el indice combinado por centro no puede declararse directamente sobre `solicitud__centro_salud` en Django. El filtrado por centro se apoya en el FK `Solicitud.centro_salud` ya indexado por Django y en el join contra `Solicitud`.
- Los tests del plan usan `HTTP_HOST="gestion.localhost"` para seguir patrones actuales, aunque el setup local recomendado para Google usa `GESTION_HOST=127.0.0.1`.
- Las plantillas son funcionales y minimas. La mejora visual puede hacerse despues sin cambiar la logica de negocio.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-19-modulo-seleccion.md`. Two execution options:

**1. Subagent-Driven (recommended)** - dispatch a fresh subagent per task, review between tasks, fast iteration. Recommended here because the plan touches six separable surfaces: modelo, permisos, selector, comunicador, comando y docs.

**2. Inline Execution** - execute tasks in this session using `executing-plans`, batch execution with checkpoints after each task.

Which approach?
