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
