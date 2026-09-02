from django.core.validators import MaxValueValidator, MinValueValidator
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from .texto import normalizar
from .validators import (
    formatear_rut_sin_puntos,
    formatear_telefono_con_codigo_pais,
    validar_rut_chileno,
    validar_telefono_chileno,
)


class Centro(models.Model):
    id_centro = models.IntegerField(primary_key=True)
    centro = models.CharField(max_length=150, unique=True)

    class Meta:
        db_table = "centros"
        ordering = ["id_centro"]
        verbose_name = "centro"
        verbose_name_plural = "centros"

    def __str__(self):
        return self.centro


class Solicitud(models.Model):
    class Sexo(models.TextChoices):
        FEMENINO = "F", "Femenino"
        MASCULINO = "M", "Masculino"
        OTRO = "O", "Otro"
        PREFIERE_NO_DECIR = "N", "Prefiere no decir"

    class Prioridad(models.TextChoices):
        URGENTE = "URGENTE", "Urgente"
        ALTA = "ALTA", "Alta"
        MEDIA = "MEDIA", "Media"
        BAJA = "BAJA", "Baja"

    class TipoCondicion(models.TextChoices):
        NEURODIVERGENTE = "NEURODIVERGENTE", "Neurodivergente"
        CUIDADOR_NEURODIVERGENTE = "CUIDADOR_NEURODIVERGENTE", "Cuidador neurodivergente"
        PRAIS = "PRAIS", "PRAIS"
        GESTANTE = "GESTANTE", "Gestante"
        OTRO = "OTRO", "Otro"

    id_solicitud = models.BigAutoField(primary_key=True)
    # default="" solo para poder agregar la columna sobre las filas historicas
    # (creadas cuando el chatbot no persistia el nombre). En filas nuevas el
    # campo es obligatorio: blank=False hace que full_clean lo exija.
    nombre = models.CharField(max_length=150, default="")
    rut = models.CharField(max_length=12, validators=[validar_rut_chileno])
    edad = models.PositiveSmallIntegerField(validators=[MinValueValidator(0), MaxValueValidator(120)])
    sexo = models.CharField(max_length=1, choices=Sexo.choices)
    telefono = models.CharField(max_length=12, validators=[validar_telefono_chileno])
    centro_salud = models.ForeignKey(
        Centro,
        db_column="id_centro",
        on_delete=models.RESTRICT,
        related_name="solicitudes",
    )
    credendencial_cuidador_discapacidad = models.BooleanField(default=False)
    credencial_cuidador_discapacidad_foto = models.TextField(blank=True)
    Neurodivergente_prais_gestante = models.BooleanField(default=False)
    Neurodivergente_prais_gestante_tipo = models.CharField(
        max_length=32,
        choices=TipoCondicion.choices,
        blank=True,
    )
    Neurodivergente_prais_gestante_otro = models.CharField(max_length=50, blank=True)
    acepta_terminos = models.BooleanField(default=False)
    motivo = models.CharField(max_length=160)
    detalle_motivo = models.TextField()
    fecha_solicitud = models.DateField(default=timezone.localdate)
    date_solicitud = models.DateTimeField(auto_now_add=True)
    priorizacion_solicitud = models.CharField(max_length=8, choices=Prioridad.choices, default=Prioridad.BAJA)
    puntaje_prioridad = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["-date_solicitud"]
        verbose_name = "solicitud"
        verbose_name_plural = "solicitudes"

    def __str__(self):
        return f"Solicitud #{self.id_solicitud} - {self.rut} - {self.priorizacion_solicitud}"

    def clean(self):
        super().clean()
        if self.nombre:
            self.nombre = " ".join(self.nombre.split())
            if not self.nombre:
                raise ValidationError({"nombre": "Debes indicar el nombre del paciente."})

        if self.rut:
            self.rut = formatear_rut_sin_puntos(self.rut)

        if self.telefono:
            self.telefono = formatear_telefono_con_codigo_pais(self.telefono)

        if not self.acepta_terminos:
            raise ValidationError({"acepta_terminos": "Debes aceptar los terminos y condiciones."})

        if not self.credendencial_cuidador_discapacidad:
            self.credencial_cuidador_discapacidad_foto = ""

        if not self.Neurodivergente_prais_gestante:
            self.Neurodivergente_prais_gestante_tipo = ""
            self.Neurodivergente_prais_gestante_otro = ""
            return

        if self.Neurodivergente_prais_gestante and not self.Neurodivergente_prais_gestante_tipo:
            raise ValidationError(
                {"Neurodivergente_prais_gestante_tipo": "Debes especificar la condicion declarada."}
            )

        if self.Neurodivergente_prais_gestante_tipo == self.TipoCondicion.OTRO and not self.Neurodivergente_prais_gestante_otro.strip():
            raise ValidationError(
                {"Neurodivergente_prais_gestante_otro": "Debes especificar la opcion otro."}
            )

        if self.Neurodivergente_prais_gestante_tipo != self.TipoCondicion.OTRO:
            self.Neurodivergente_prais_gestante_otro = ""


class PalabraClavePrioridad(models.Model):
    class Nivel(models.TextChoices):
        URGENTE = "URGENTE", "Urgente"
        MODERADA = "MODERADA", "Moderada"

    texto = models.CharField(max_length=120)
    texto_normalizado = models.CharField(max_length=120, unique=True, editable=False)
    nivel = models.CharField(max_length=10, choices=Nivel.choices)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "solicitudes_palabra_clave_prioridad"
        ordering = ["nivel", "texto_normalizado"]
        verbose_name = "palabra clave de prioridad"
        verbose_name_plural = "palabras clave de prioridad"

    def __str__(self):
        return f"{self.texto} ({self.get_nivel_display()})"

    def save(self, *args, **kwargs):
        self.texto_normalizado = normalizar(self.texto)
        super().save(*args, **kwargs)
