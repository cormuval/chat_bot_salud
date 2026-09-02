from django import forms

from solicitudes.models import PalabraClavePrioridad
from solicitudes.texto import normalizar

from .models import PerfilUsuario
from .permisos import centros_administrables, roles_asignables


class PerfilAdminForm(forms.ModelForm):
    """Form de perfil que restringe roles y centros a lo que el administrador
    que edita tiene permitido. `perfil_editor` es quien esta administrando."""

    email = forms.EmailField(required=True)

    class Meta:
        model = PerfilUsuario
        fields = ["rol", "centro", "centro_satelite", "anexo_telefono", "activo"]

    def __init__(self, *args, perfil_editor=None, es_creacion=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.perfil_editor = perfil_editor
        if not es_creacion:
            del self.fields["email"]
        if perfil_editor is not None:
            asignables = {r.value for r in roles_asignables(perfil_editor)}
            self.fields["rol"].choices = [
                (v, l) for v, l in self.fields["rol"].choices if v in asignables
            ]
            self.fields["centro"].queryset = centros_administrables(perfil_editor)
            self.fields["centro_satelite"].queryset = centros_administrables(perfil_editor)


class PalabraPrioridadForm(forms.ModelForm):
    class Meta:
        model = PalabraClavePrioridad
        fields = ["texto", "nivel", "activo"]

    def clean_texto(self):
        texto = self.cleaned_data["texto"]
        normalizado = normalizar(texto)
        existentes = PalabraClavePrioridad.objects.filter(texto_normalizado=normalizado)
        if self.instance.pk:
            existentes = existentes.exclude(pk=self.instance.pk)
        if existentes.exists():
            raise forms.ValidationError(
                "Ya existe una palabra equivalente (ignorando acentos y mayusculas)."
            )
        return texto
