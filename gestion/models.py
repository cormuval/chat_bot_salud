from datetime import timedelta
from urllib.parse import quote_plus

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
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
        if (
            self.fecha_hora_citacion
            and self.motivo_cierre != self.MotivoCierre.AGENDADA
        ):
            raise ValidationError(
                {
                    "fecha_hora_citacion": (
                        "Solo una cita agendada puede tener fecha y hora."
                    )
                }
            )

    def _registrar_decision(self, usuario):
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
        self._registrar_intento(
            usuario, cerrar=True, motivo_cierre=self.MotivoCierre.AGENDADA
        )

    def registrar_no_acepta(self, usuario):
        self._registrar_intento(
            usuario, cerrar=True, motivo_cierre=self.MotivoCierre.NO_ACEPTA
        )

    def registrar_no_contactado(self, usuario):
        self._registrar_intento(
            usuario, cerrar=True, motivo_cierre=self.MotivoCierre.NO_CONTACTADO
        )

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
            mensaje_base = (
                "Hola {nombre}, le contactamos desde su centro de salud por su "
                "solicitud de morbilidad."
            )
        mensaje = mensaje_base.format(nombre=self.solicitud.nombre)
        return f"https://wa.me/{telefono}?text={quote_plus(mensaje)}"
