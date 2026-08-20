import secrets

from django import forms

from solicitudes.models import Solicitud

from .models import Gestion, MotivoRechazo


class DecisionSelectorForm(forms.Form):
    decision = forms.ChoiceField(
        choices=[
            (Gestion.Decision.ACEPTADA, Gestion.Decision.ACEPTADA.label),
            (Gestion.Decision.RECHAZADA, Gestion.Decision.RECHAZADA.label),
            (Gestion.Decision.NO_APLICA, Gestion.Decision.NO_APLICA.label),
        ]
    )
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
    token_contacto = forms.CharField(
        max_length=128,
        required=False,
        widget=forms.HiddenInput,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound and not self.initial.get("token_contacto"):
            self.initial["token_contacto"] = secrets.token_urlsafe(16)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("accion") == self.AGENDADA and not cleaned.get("fecha_hora_citacion"):
            self.add_error("fecha_hora_citacion", "Debe indicar fecha y hora acordadas.")
        return cleaned

    def guardar(self, gestion, usuario):
        accion = self.cleaned_data["accion"]
        token_contacto = self.cleaned_data.get("token_contacto", "")
        if accion == self.AGENDADA:
            gestion.registrar_agendada(
                usuario,
                self.cleaned_data["fecha_hora_citacion"],
                token_contacto=token_contacto,
            )
        elif accion == self.NO_ACEPTA:
            gestion.registrar_no_acepta(usuario, token_contacto=token_contacto)
        elif accion == self.NO_CONTESTA:
            gestion.registrar_no_contesta(usuario, token_contacto=token_contacto)
        elif accion == self.NO_CONTACTADO:
            gestion.registrar_no_contactado(usuario, token_contacto=token_contacto)
        return gestion


class WhatsappComunicadorForm(forms.Form):
    token_contacto = forms.CharField(
        max_length=128,
        required=False,
        widget=forms.HiddenInput,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound and not self.initial.get("token_contacto"):
            self.initial["token_contacto"] = secrets.token_urlsafe(16)
