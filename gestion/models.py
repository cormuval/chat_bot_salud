import re
from datetime import timedelta
from urllib.parse import quote_plus

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Case, IntegerField, Q, QuerySet, Value, When
from django.utils import timezone

from solicitudes.models import Centro, Solicitud


class PerfilUsuario(models.Model):
    """Complementa al User de Django con la informacion que Google no entrega:
    el rol dentro del sistema y el centro al que pertenece el funcionario.

    Ademas funciona como lista de autorizacion: sin perfil activo no se entra
    al modulo de gestion, aunque el login con Google sea correcto.
    """

    class Rol(models.TextChoices):
        ADMIN = "ADMIN", "Administrador/a"
        SUPERVISOR_DAS = "SUPERVISOR_DAS", "Supervisor/a DAS"
        SUPERVISOR_CENTRO = "SUPERVISOR_CENTRO", "Supervisor/a de centro"
        SOME = "SOME", "SOME"
        FULL = "FULL", "Full"
        SELECTOR = "SELECTOR", "Selector"
        COMUNICADOR = "COMUNICADOR", "Comunicador"

    # Roles cuyo alcance es toda la corporacion y no un centro puntual.
    ROLES_TODOS_LOS_CENTROS = frozenset({Rol.ADMIN, Rol.SUPERVISOR_DAS})

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="perfil_gestion",
    )
    rol = models.CharField(max_length=20, choices=Rol.choices)
    centro = models.ForeignKey(
        Centro,
        on_delete=models.RESTRICT,
        related_name="perfiles",
        help_text="Centro base. Para ADMIN y SUPERVISOR_DAS es informativo: ven todos.",
    )
    centro_satelite = models.ForeignKey(
        Centro,
        on_delete=models.SET_NULL,
        related_name="perfiles_satelite",
        blank=True,
        null=True,
        help_text="CECOSF u otro centro asociado que este funcionario tambien gestiona.",
    )
    anexo_telefono = models.CharField(max_length=20, blank=True)
    activo = models.BooleanField(
        default=True,
        help_text="Desmarcar para revocar el acceso sin borrar el historial.",
    )

    class Meta:
        db_table = "gestion_perfil_usuario"
        ordering = ["usuario__email"]
        verbose_name = "perfil de usuario"
        verbose_name_plural = "perfiles de usuario"

    def __str__(self):
        return f"{self.usuario.email} ({self.get_rol_display()})"

    @property
    def ve_todos_los_centros(self):
        return self.rol in self.ROLES_TODOS_LOS_CENTROS

    def centros_permitidos(self):
        """Centros cuyas solicitudes puede ver este perfil."""
        if self.ve_todos_los_centros:
            return Centro.objects.all()

        ids = [self.centro_id]
        if self.centro_satelite_id:
            ids.append(self.centro_satelite_id)
        return Centro.objects.filter(pk__in=ids)


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
                When(
                    solicitud__priorizacion_solicitud=Solicitud.Prioridad.URGENTE,
                    then=Value(1),
                ),
                When(
                    solicitud__priorizacion_solicitud=Solicitud.Prioridad.ALTA,
                    then=Value(2),
                ),
                When(
                    solicitud__priorizacion_solicitud=Solicitud.Prioridad.MEDIA,
                    then=Value(3),
                ),
                When(
                    solicitud__priorizacion_solicitud=Solicitud.Prioridad.BAJA,
                    then=Value(4),
                ),
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
                When(
                    prioridad_clinica=Solicitud.Prioridad.URGENTE,
                    then=Value(1),
                ),
                When(
                    prioridad_clinica=Solicitud.Prioridad.ALTA,
                    then=Value(2),
                ),
                When(
                    prioridad_clinica=Solicitud.Prioridad.MEDIA,
                    then=Value(3),
                ),
                When(
                    prioridad_clinica=Solicitud.Prioridad.BAJA,
                    then=Value(4),
                ),
                default=Value(9),
                output_field=IntegerField(),
            ),
        ).order_by(
            "orden_decision", "orden_prioridad_clinica", "solicitud__date_solicitud"
        )

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

    def decididas_corregibles_selector(self, perfil, ahora=None):
        ahora = ahora or timezone.now()
        vencimiento = ahora - timedelta(hours=24)
        return (
            self.select_related(
                "solicitud",
                "solicitud__centro_salud",
                "motivo_rechazo",
                "decidido_por",
            )
            .del_alcance(perfil)
            .filter(
                decision__in=(
                    Gestion.Decision.ACEPTADA,
                    Gestion.Decision.RECHAZADA,
                ),
                intentos_contacto=0,
                cerrada_en__isnull=True,
            )
            .exclude(
                decision=Gestion.Decision.RECHAZADA,
                fecha_decision__lte=vencimiento,
            )
            .con_orden_prioridad_administrativa()
        )

    def no_aplica_selector(self, perfil):
        return (
            self.select_related(
                "solicitud",
                "solicitud__centro_salud",
                "decidido_por",
            )
            .del_alcance(perfil)
            .filter(decision=Gestion.Decision.NO_APLICA)
            .order_by("-fecha_decision")
        )

    def tabla_comunicador(self, perfil, ahora=None):
        ahora = ahora or timezone.now()
        vencimiento = ahora - timedelta(hours=24)
        return (
            self.select_related(
                "solicitud", "solicitud__centro_salud", "motivo_rechazo"
            )
            .del_alcance(perfil)
            .filter(cerrada_en__isnull=True)
            .filter(
                Q(decision=Gestion.Decision.ACEPTADA)
                | Q(decision=Gestion.Decision.RECHAZADA)
            )
            .exclude(
                decision=Gestion.Decision.RECHAZADA,
                fecha_decision__lte=vencimiento,
            )
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

    class AccionContacto(models.TextChoices):
        NO_CONTESTA = "NO_CONTESTA", "No contesta"
        WHATSAPP = "WHATSAPP", "WhatsApp"
        AGENDADA = "AGENDADA", "Agendada"
        NO_ACEPTA = "NO_ACEPTA", "El paciente no acepta"
        NO_CONTACTADO = "NO_CONTACTADO", "No se logro contactar"

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
    ultima_accion_contacto = models.CharField(
        max_length=20,
        choices=AccionContacto.choices,
        blank=True,
    )
    ultimo_token_contacto = models.CharField(max_length=64, blank=True)

    objects = GestionQuerySet.as_manager()

    class Meta:
        db_table = "gestion_solicitud"
        ordering = ["solicitud__date_solicitud"]
        indexes = [
            models.Index(
                fields=["decision", "cerrada_en"], name="gestion_dec_cierre_idx"
            ),
            models.Index(fields=["fecha_decision"], name="gestion_fecha_dec_idx"),
        ]
        verbose_name = "gestion de solicitud"
        verbose_name_plural = "gestiones de solicitudes"

    def __str__(self):
        return f"Gestion #{self.pk} - solicitud #{self.solicitud_id}"

    @property
    def puede_corregir_decision(self):
        return self.intentos_contacto == 0 and self.cerrada_en is None

    @classmethod
    def motivos_cierre_automatico(cls):
        return (
            cls.MotivoCierre.AVISADO_WHATSAPP,
            cls.MotivoCierre.SIN_AVISO,
        )

    @property
    def tiene_cierre_automatico(self):
        return (
            self.cerrada_en is not None
            and self.motivo_cierre in self.motivos_cierre_automatico()
        )

    def rechazado_vencido(self, ahora=None):
        ahora = ahora or timezone.now()
        return (
            self.decision == self.Decision.RECHAZADA
            and self.fecha_decision is not None
            and self.fecha_decision <= ahora - timedelta(hours=24)
        )

    def clean(self):
        super().clean()
        if self.decision == self.Decision.ACEPTADA and not self.prioridad_clinica:
            raise ValidationError(
                {"prioridad_clinica": "Debe indicar prioridad clinica."}
            )
        if self.decision == self.Decision.RECHAZADA and not self.motivo_rechazo_id:
            raise ValidationError(
                {"motivo_rechazo": "Debe indicar motivo de rechazo."}
            )
        cita_con_cierre_automatico = (
            self.decision == self.Decision.RECHAZADA
            and self.motivo_cierre in self.motivos_cierre_automatico()
        )
        if (
            self.fecha_hora_citacion
            and self.motivo_cierre != self.MotivoCierre.AGENDADA
            and not cita_con_cierre_automatico
        ):
            raise ValidationError(
                {
                    "fecha_hora_citacion": (
                        "Solo una cita agendada puede tener fecha y hora."
                    )
                }
            )
        if (
            self.motivo_cierre == self.MotivoCierre.AGENDADA
            and not self.fecha_hora_citacion
        ):
            raise ValidationError(
                {"fecha_hora_citacion": "Debe indicar fecha y hora de citacion."}
            )

    def _mutar_bloqueado(self, mutacion, campos):
        with transaction.atomic():
            bloqueada = (
                type(self)
                .objects.select_for_update()
                .get(pk=self.pk)
            )
            guardar = mutacion(bloqueada)
            if guardar:
                bloqueada.full_clean()
                bloqueada.save(update_fields=campos)

        for nombre in campos:
            campo = self._meta.get_field(nombre)
            setattr(self, campo.attname, getattr(bloqueada, campo.attname))
            if campo.is_relation:
                self._state.fields_cache.pop(nombre, None)
        return guardar

    def _registrar_decision(self, usuario):
        if self.rechazado_vencido():
            raise ValidationError(
                "La decision no se puede corregir porque vencio el plazo de "
                "correccion de 24 horas."
            )
        if not self.puede_corregir_decision:
            raise ValidationError(
                "La decision no se puede corregir porque ya hay intentos registrados."
            )
        self.decidido_por = usuario
        self.fecha_decision = timezone.now()
        self.cerrada_en = None
        self.motivo_cierre = ""

    def aceptar(self, usuario, prioridad_clinica):
        if not prioridad_clinica:
            raise ValidationError(
                {"prioridad_clinica": "Debe indicar prioridad clinica."}
            )
        def mutar(gestion):
            gestion._registrar_decision(usuario)
            gestion.decision = self.Decision.ACEPTADA
            gestion.prioridad_clinica = prioridad_clinica
            gestion.motivo_rechazo = None
            return True

        return self._mutar_bloqueado(
            mutar,
            [
                "decision",
                "prioridad_clinica",
                "motivo_rechazo",
                "decidido_por",
                "fecha_decision",
                "cerrada_en",
                "motivo_cierre",
            ],
        )

    def rechazar(self, usuario, motivo):
        if motivo is None:
            raise ValidationError({"motivo_rechazo": "Debe indicar motivo de rechazo."})
        def mutar(gestion):
            gestion._registrar_decision(usuario)
            gestion.decision = self.Decision.RECHAZADA
            gestion.prioridad_clinica = ""
            gestion.motivo_rechazo = motivo
            return True

        return self._mutar_bloqueado(
            mutar,
            [
                "decision",
                "prioridad_clinica",
                "motivo_rechazo",
                "decidido_por",
                "fecha_decision",
                "cerrada_en",
                "motivo_cierre",
            ],
        )

    def marcar_no_aplica(self, usuario):
        def mutar(gestion):
            gestion._registrar_decision(usuario)
            gestion.decision = self.Decision.NO_APLICA
            gestion.prioridad_clinica = ""
            gestion.motivo_rechazo = None
            return True

        return self._mutar_bloqueado(
            mutar,
            [
                "decision",
                "prioridad_clinica",
                "motivo_rechazo",
                "decidido_por",
                "fecha_decision",
                "cerrada_en",
                "motivo_cierre",
            ],
        )

    def _registrar_intento(
        self,
        usuario,
        accion,
        cerrar=False,
        motivo_cierre="",
        fecha_hora_citacion=None,
        registrar_whatsapp=False,
        token_contacto="",
    ):
        def mutar(gestion):
            ahora = timezone.now()
            if gestion.decision not in (
                self.Decision.ACEPTADA,
                self.Decision.RECHAZADA,
            ):
                raise ValidationError(
                    "La solicitud ya no esta disponible para registrar contacto."
                )
            if gestion.cerrada_en is not None and not gestion.tiene_cierre_automatico:
                return False
            if token_contacto and gestion.ultimo_token_contacto == token_contacto:
                return False

            if gestion.cerrada_en is None and gestion.rechazado_vencido(ahora):
                gestion._aplicar_cierre_automatico(ahora)

            gestion.intentos_contacto += 1
            gestion.fecha_ultimo_intento = ahora
            gestion.contactado_por = usuario
            gestion.ultima_accion_contacto = accion
            if token_contacto:
                gestion.ultimo_token_contacto = token_contacto
            if registrar_whatsapp and gestion.aviso_whatsapp_en is None:
                gestion.aviso_whatsapp_en = ahora
            if fecha_hora_citacion is not None:
                gestion.fecha_hora_citacion = fecha_hora_citacion
            if cerrar and gestion.cerrada_en is None:
                gestion.cerrada_en = ahora
                gestion.motivo_cierre = motivo_cierre
            return True

        return self._mutar_bloqueado(
            mutar,
            [
                "intentos_contacto",
                "fecha_ultimo_intento",
                "contactado_por",
                "ultima_accion_contacto",
                "ultimo_token_contacto",
                "aviso_whatsapp_en",
                "fecha_hora_citacion",
                "cerrada_en",
                "motivo_cierre",
            ],
        )

    def registrar_no_contesta(self, usuario, token_contacto=""):
        return self._registrar_intento(
            usuario,
            self.AccionContacto.NO_CONTESTA,
            token_contacto=token_contacto,
        )

    def registrar_click_whatsapp(self, usuario, token_contacto=""):
        return self._registrar_intento(
            usuario,
            self.AccionContacto.WHATSAPP,
            registrar_whatsapp=True,
            token_contacto=token_contacto,
        )

    def registrar_agendada(self, usuario, fecha_hora, token_contacto=""):
        if fecha_hora is None:
            raise ValidationError(
                {"fecha_hora_citacion": "Debe indicar fecha y hora de citacion."}
            )
        return self._registrar_intento(
            usuario,
            self.AccionContacto.AGENDADA,
            cerrar=True,
            motivo_cierre=self.MotivoCierre.AGENDADA,
            fecha_hora_citacion=fecha_hora,
            token_contacto=token_contacto,
        )

    def registrar_no_acepta(self, usuario, token_contacto=""):
        return self._registrar_intento(
            usuario,
            self.AccionContacto.NO_ACEPTA,
            cerrar=True,
            motivo_cierre=self.MotivoCierre.NO_ACEPTA,
            token_contacto=token_contacto,
        )

    def registrar_no_contactado(self, usuario, token_contacto=""):
        return self._registrar_intento(
            usuario,
            self.AccionContacto.NO_CONTACTADO,
            cerrar=True,
            motivo_cierre=self.MotivoCierre.NO_CONTACTADO,
            token_contacto=token_contacto,
        )

    def _aplicar_cierre_automatico(self, ahora):
        self.cerrada_en = ahora
        self.motivo_cierre = (
            self.MotivoCierre.AVISADO_WHATSAPP
            if self.aviso_whatsapp_en
            else self.MotivoCierre.SIN_AVISO
        )

    def cerrar_rechazado_automatico(self, ahora=None):
        ahora = ahora or timezone.now()

        def mutar(gestion):
            if (
                gestion.decision != self.Decision.RECHAZADA
                or gestion.cerrada_en is not None
            ):
                return False
            gestion._aplicar_cierre_automatico(ahora)
            return True

        return self._mutar_bloqueado(
            mutar,
            ["cerrada_en", "motivo_cierre"],
        )

    def url_whatsapp(self):
        telefono = self.solicitud.telefono
        if not re.fullmatch(r"\+569\d{8}", telefono):
            return None
        if self.motivo_rechazo_id:
            mensaje_base = self.motivo_rechazo.mensaje_paciente
        else:
            mensaje_base = (
                "Hola {nombre}, le contactamos desde su centro de salud por su "
                "solicitud de morbilidad."
            )
        mensaje = mensaje_base.replace("{nombre}", self.solicitud.nombre)
        return f"https://wa.me/{telefono.removeprefix('+')}?text={quote_plus(mensaje)}"
