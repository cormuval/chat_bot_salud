# Palabras clave de priorización editables — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mover las palabras clave de prioridad administrativa de constantes en el código a un modelo editable por el rol SUPERVISOR_DAS, con match normalizado sin acentos, sembrando las palabras actuales para no cambiar el comportamiento.

**Architecture:** Un modelo `PalabraClavePrioridad` en la app `solicitudes` (donde se consume la priorización), leído por `solicitudes/priorizacion.py` con cache invalidado por señales. La UI de edición vive en `gestion`. Una migración de datos siembra las palabras actuales. La normalización (minúsculas + sin acentos) se define una vez y se usa en el match y en la unicidad del modelo.

**Tech Stack:** Django 5.2, stdlib `unicodedata`, cache de Django. Sin dependencias nuevas.

**Spec:** `docs/superpowers/specs/2026-09-01-priorizacion-editable-design.md`

## Global Constraints

- Código, comentarios y mensajes de commit en **español, sin tildes en identificadores**. Sin emojis en commits.
- Tests con el **Django test runner** contra **MySQL** (Docker up), no pytest ni SQLite. `TextField` mapea a `LONGTEXT` en MySQL.
- Tests de gestión: `HTTP_HOST="gestion.localhost"` y clase decorada con `@override_settings(ALLOWED_HOSTS=["gestion.localhost", "testserver"], GESTION_HOST="gestion.localhost")`.
- **Esta es la única serie que toca el chatbot** (`solicitudes`): se hace en la dirección de dependencia permitida (gestión depende de solicitudes, no al revés).
- Puntajes (+4 / +1), umbrales (6 / 4 / 2) y criterios estáticos (edad, credencial, condición) siguen fijos en código.

**Depende de:** el plan del panel de administración (sección "Administracion" en la nav y `permisos.py`). La UI de esta feature cuelga de ese panel.

---

### Task 1: Modelo de palabra clave y normalización

**Files:**
- Create: `solicitudes/texto.py` (función `normalizar`)
- Modify: `solicitudes/models.py` (modelo `PalabraClavePrioridad`)
- Create: `solicitudes/migrations/00NN_palabra_clave_prioridad.py` (vía makemigrations)
- Test: `solicitudes/tests.py` (clase `PalabraClavePrioridadModeloTests`)

**Interfaces:**
- Produces:
  - `solicitudes.texto.normalizar(texto: str) -> str`
  - modelo `solicitudes.models.PalabraClavePrioridad` con campos `texto`, `texto_normalizado`, `nivel` (choices URGENTE/MODERADA), `activo`.

- [ ] **Step 1: Escribir el test que falla**

En `solicitudes/tests.py` (agregar imports de ser necesario: `from solicitudes.models import PalabraClavePrioridad` y `from solicitudes.texto import normalizar`):

```python
from django.db import IntegrityError
from django.test import TestCase

from solicitudes.models import PalabraClavePrioridad
from solicitudes.texto import normalizar


class PalabraClavePrioridadModeloTests(TestCase):
    def test_normalizar_quita_acentos_y_mayusculas(self):
        self.assertEqual(normalizar("Convulsión"), "convulsion")
        self.assertEqual(normalizar("  FIEBRE "), "fiebre")

    def test_guardar_calcula_texto_normalizado(self):
        p = PalabraClavePrioridad.objects.create(texto="Convulsión", nivel="URGENTE")
        self.assertEqual(p.texto_normalizado, "convulsion")

    def test_unicidad_por_forma_normalizada(self):
        PalabraClavePrioridad.objects.create(texto="Fiebre", nivel="MODERADA")
        with self.assertRaises(IntegrityError):
            PalabraClavePrioridad.objects.create(texto="fiebre", nivel="MODERADA")
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/python manage.py test solicitudes.tests.PalabraClavePrioridadModeloTests -v 2`
Expected: FAIL — no existe el modelo ni el módulo `texto`.

- [ ] **Step 3: Crear la función de normalización**

Crear `solicitudes/texto.py`:

```python
import unicodedata


def normalizar(texto):
    """Minusculas y sin acentos, para comparar palabras clave sin que las
    tildes o mayusculas cambien el resultado."""
    base = (texto or "").strip().lower()
    descompuesto = unicodedata.normalize("NFKD", base)
    return "".join(c for c in descompuesto if not unicodedata.combining(c))
```

- [ ] **Step 4: Agregar el modelo**

En `solicitudes/models.py`, agregar el import y el modelo (al final):

```python
from .texto import normalizar


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
```

- [ ] **Step 5: Generar la migración de esquema**

Run: `.venv/bin/python manage.py makemigrations solicitudes`
Expected: crea `solicitudes/migrations/00NN_palabra_clave_prioridad.py`. Revisar que solo cree el modelo `PalabraClavePrioridad`.

- [ ] **Step 6: Aplicar la migración y correr el test**

Run: `.venv/bin/python manage.py migrate solicitudes && .venv/bin/python manage.py test solicitudes.tests.PalabraClavePrioridadModeloTests -v 2`
Expected: PASS (3 tests).

- [ ] **Step 7: Commit**

```bash
git add solicitudes/texto.py solicitudes/models.py solicitudes/migrations/ solicitudes/tests.py
git commit -m "Agrega el modelo de palabra clave de prioridad y la normalizacion"
```

---

### Task 2: Migración de datos que siembra las palabras actuales

**Files:**
- Create: `solicitudes/migrations/00NN_seed_palabras_prioridad.py`
- Test: `solicitudes/tests.py` (clase `SeedPalabrasPrioridadTests`)

**Interfaces:**
- Consumes: modelo `PalabraClavePrioridad` (Task 1), `solicitudes.texto.normalizar`.
- Produces: 9 palabras URGENTE y 6 MODERADA en la BD, idénticas a las constantes actuales.

- [ ] **Step 1: Escribir el test que falla**

```python
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
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/python manage.py test solicitudes.tests.SeedPalabrasPrioridadTests -v 2`
Expected: FAIL — no hay filas sembradas.

- [ ] **Step 3: Crear la migración de datos**

Crear `solicitudes/migrations/00NN_seed_palabras_prioridad.py` (ajustar `dependencies` a la migración de la Task 1):

```python
from django.db import migrations

from solicitudes.texto import normalizar

URGENTES = [
    "dolor pecho", "dificultad respiratoria", "falta de aire", "convulsion",
    "desmayo", "sangrado", "embarazo", "gestante", "suicida",
]
MODERADAS = [
    "fiebre", "dolor intenso", "vomitos", "diarrea", "infeccion", "herida",
]


def sembrar(apps, schema_editor):
    Palabra = apps.get_model("solicitudes", "PalabraClavePrioridad")
    for texto in URGENTES:
        Palabra.objects.get_or_create(
            texto_normalizado=normalizar(texto),
            defaults={"texto": texto, "nivel": "URGENTE", "activo": True},
        )
    for texto in MODERADAS:
        Palabra.objects.get_or_create(
            texto_normalizado=normalizar(texto),
            defaults={"texto": texto, "nivel": "MODERADA", "activo": True},
        )


def revertir(apps, schema_editor):
    Palabra = apps.get_model("solicitudes", "PalabraClavePrioridad")
    normalizados = [normalizar(t) for t in URGENTES + MODERADAS]
    Palabra.objects.filter(texto_normalizado__in=normalizados).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("solicitudes", "00NN_palabra_clave_prioridad"),
    ]

    operations = [migrations.RunPython(sembrar, revertir)]
```

Nota: en la migración se setea `texto_normalizado` explícitamente porque las migraciones usan el modelo histórico (`apps.get_model`), que no ejecuta el `save()` personalizado.

- [ ] **Step 4: Aplicar y correr el test**

Run: `.venv/bin/python manage.py migrate solicitudes && .venv/bin/python manage.py test solicitudes.tests.SeedPalabrasPrioridadTests -v 2`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add solicitudes/migrations/ solicitudes/tests.py
git commit -m "Siembra las palabras clave de prioridad actuales"
```

---

### Task 3: Leer las palabras desde la BD con cache y match normalizado

**Files:**
- Modify: `solicitudes/priorizacion.py` (leer de BD + match normalizado)
- Create: `solicitudes/signals.py` (invalidar cache)
- Modify: `solicitudes/apps.py` (conectar señales en `ready`)
- Test: `solicitudes/tests.py` (clase `PriorizacionDesdeBDTests`)

**Interfaces:**
- Consumes: `PalabraClavePrioridad` (Task 1), `solicitudes.texto.normalizar`.
- Produces: `priorizacion.calcular_prioridad` y `priorizacion.desglosar_prioridad` leen las palabras activas desde la BD (cacheadas). Mismos puntajes y umbrales.

- [ ] **Step 1: Escribir el test que falla**

```python
from django.core.cache import cache

from solicitudes.priorizacion import calcular_prioridad


class PriorizacionDesdeBDTests(TestCase):
    def setUp(self):
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
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/python manage.py test solicitudes.tests.PriorizacionDesdeBDTests -v 2`
Expected: FAIL — `priorizacion.py` aún usa las constantes; agregar/desactivar palabras no tiene efecto.

- [ ] **Step 3: Reescribir la lectura de palabras en priorizacion.py**

En `solicitudes/priorizacion.py`, reemplazar las constantes `URGENT_KEYWORDS` / `MODERATE_KEYWORDS` y las funciones de match por lo siguiente. Mantener intactos `desglosar_prioridad` (el resto), `calcular_prioridad` y los criterios estáticos.

Agregar arriba:

```python
from django.core.cache import cache

from .texto import normalizar

CACHE_PALABRAS = "solicitudes_palabras_prioridad_v1"


def palabras_por_nivel():
    """Palabras activas agrupadas por nivel, en forma normalizada. Cacheadas;
    la cache se invalida al guardar o borrar una palabra (ver signals.py)."""
    data = cache.get(CACHE_PALABRAS)
    if data is None:
        from .models import PalabraClavePrioridad

        data = {"URGENTE": [], "MODERADA": []}
        for texto_norm, nivel in PalabraClavePrioridad.objects.filter(
            activo=True
        ).values_list("texto_normalizado", "nivel"):
            data.setdefault(nivel, []).append(texto_norm)
        cache.set(CACHE_PALABRAS, data, None)
    return data


def _primera_coincidencia(texto, palabras_normalizadas):
    normal = normalizar(texto)
    for palabra in palabras_normalizadas:
        if palabra in normal:
            return palabra
    return ""
```

Y en `desglosar_prioridad`, reemplazar el uso de `_first_keyword(clinical_text, URGENT_KEYWORDS)` / `MODERATE_KEYWORDS` por:

```python
    palabras = palabras_por_nivel()

    palabra_urgente = _primera_coincidencia(clinical_text, palabras["URGENTE"])
    if palabra_urgente:
        factores.append(
            {
                "codigo": "palabra_urgente",
                "descripcion": f'palabra clave "{palabra_urgente}"',
                "puntaje": 4,
            }
        )

    palabra_moderada = _primera_coincidencia(clinical_text, palabras["MODERADA"])
    if palabra_moderada:
        factores.append(
            {
                "codigo": "palabra_moderada",
                "descripcion": f'palabra clave "{palabra_moderada}"',
                "puntaje": 1,
            }
        )
```

Borrar las constantes `URGENT_KEYWORDS`, `MODERATE_KEYWORDS` y las funciones `_contains_any` / `_first_keyword` si ya no se usan en el archivo (verificar con grep antes de borrar).

- [ ] **Step 4: Crear las señales de invalidación de cache**

Crear `solicitudes/signals.py`:

```python
from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import PalabraClavePrioridad
from .priorizacion import CACHE_PALABRAS


@receiver([post_save, post_delete], sender=PalabraClavePrioridad)
def invalidar_cache_palabras(sender, **kwargs):
    cache.delete(CACHE_PALABRAS)
```

- [ ] **Step 5: Conectar las señales en apps.py**

En `solicitudes/apps.py`, dentro de la clase de config, agregar el método `ready`:

```python
    def ready(self):
        from . import signals  # noqa: F401
```

Si `apps.py` no tiene la clase de config referenciada en `INSTALLED_APPS`, verificar el `default_auto_field`/nombre y ajustar; el objetivo es que `ready()` importe `signals`.

- [ ] **Step 6: Correr el test y verificar que pasa**

Run: `.venv/bin/python manage.py test solicitudes.tests.PriorizacionDesdeBDTests -v 2`
Expected: PASS (4 tests).

- [ ] **Step 7: Correr toda la suite de solicitudes (regresión de priorización)**

Run: `.venv/bin/python manage.py test solicitudes -v 1`
Expected: OK. Las pruebas de priorización existentes siguen pasando porque las palabras sembradas reproducen las constantes.

- [ ] **Step 8: Commit**

```bash
git add solicitudes/priorizacion.py solicitudes/signals.py solicitudes/apps.py solicitudes/tests.py
git commit -m "Lee las palabras de prioridad desde la BD con match normalizado y cache"
```

---

### Task 4: UI de edición de palabras clave (SUPERVISOR_DAS)

**Files:**
- Modify: `gestion/permisos.py` (`puede_editar_palabras_prioridad`)
- Modify: `gestion/templatetags/gestion_ui.py` (filtro `puede_editar_palabras`)
- Create: `gestion/forms_admin.py` o modificar el existente (`PalabraPrioridadForm`)
- Modify: `gestion/views_admin.py` (vistas de palabras)
- Modify: `gestion/urls.py` (rutas)
- Create: `gestion/templates/gestion/palabras_lista.html`, `gestion/templates/gestion/palabra_form.html`
- Modify: `gestion/templates/gestion/admin_panel.html` (tile "Palabras clave")
- Test: `gestion/tests.py` (clase `PalabrasPrioridadUiTests`)

**Interfaces:**
- Consumes: `PalabraClavePrioridad` (Task 1).
- Produces: `permisos.puede_editar_palabras_prioridad(perfil) -> bool`; vistas `gestion:palabras_lista`, `gestion:palabra_crear`, `gestion:palabra_editar`.

- [ ] **Step 1: Escribir el test que falla**

En `gestion/tests.py`:

```python
from solicitudes.models import PalabraClavePrioridad


@override_settings(ALLOWED_HOSTS=["gestion.localhost", "testserver"], GESTION_HOST="gestion.localhost")
class PalabrasPrioridadUiTests(TestCase):
    def setUp(self):
        self.centro = Centro.objects.get(pk=620)

    def _login(self, rol):
        u = User.objects.create_user(f"p-{rol}@cmvalparaiso.cl", email=f"p-{rol}@cmvalparaiso.cl")
        PerfilUsuario.objects.create(usuario=u, rol=rol, centro=self.centro)
        self.client.force_login(u)

    def test_solo_supervisor_das_accede(self):
        self._login(PerfilUsuario.Rol.ADMIN)
        self.assertEqual(self.client.get("/palabras-prioridad/", HTTP_HOST="gestion.localhost").status_code, 302)

    def test_supervisor_das_ve_lista(self):
        self._login(PerfilUsuario.Rol.SUPERVISOR_DAS)
        self.assertEqual(self.client.get("/palabras-prioridad/", HTTP_HOST="gestion.localhost").status_code, 200)

    def test_supervisor_das_crea_palabra(self):
        self._login(PerfilUsuario.Rol.SUPERVISOR_DAS)
        response = self.client.post(
            "/palabras-prioridad/nueva/",
            {"texto": "mareo intenso", "nivel": "URGENTE", "activo": "on"},
            HTTP_HOST="gestion.localhost",
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            PalabraClavePrioridad.objects.filter(texto_normalizado="mareo intenso").exists()
        )
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/python manage.py test gestion.tests.PalabrasPrioridadUiTests -v 2`
Expected: FAIL — la ruta `/palabras-prioridad/` no existe.

- [ ] **Step 3: Agregar el permiso**

En `gestion/permisos.py`:

```python
def puede_editar_palabras_prioridad(perfil):
    return perfil.rol == PerfilUsuario.Rol.SUPERVISOR_DAS
```

- [ ] **Step 4: Agregar el filtro de template**

En `gestion/templatetags/gestion_ui.py`:

```python
@register.filter
def puede_editar_palabras(perfil):
    return bool(perfil) and permisos.puede_editar_palabras_prioridad(perfil)
```

- [ ] **Step 5: Agregar el form**

En `gestion/forms_admin.py` (creado en el plan del panel), agregar:

```python
from solicitudes.models import PalabraClavePrioridad


class PalabraPrioridadForm(forms.ModelForm):
    class Meta:
        model = PalabraClavePrioridad
        fields = ["texto", "nivel", "activo"]
```

- [ ] **Step 6: Agregar las vistas**

En `gestion/views_admin.py`:

```python
from solicitudes.models import PalabraClavePrioridad

from .forms_admin import PalabraPrioridadForm
from .permisos import puede_editar_palabras_prioridad


@login_required
def palabras_lista(request):
    perfil = obtener_perfil_activo(request.user)
    if perfil is None or not puede_editar_palabras_prioridad(perfil):
        return redirect("gestion:sin_acceso")
    return render(
        request,
        "gestion/palabras_lista.html",
        {"perfil": perfil, "palabras": PalabraClavePrioridad.objects.all()},
    )


@login_required
def palabra_crear(request):
    perfil = obtener_perfil_activo(request.user)
    if perfil is None or not puede_editar_palabras_prioridad(perfil):
        return redirect("gestion:sin_acceso")
    form = PalabraPrioridadForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("gestion:palabras_lista")
    return render(request, "gestion/palabra_form.html", {"perfil": perfil, "form": form})


@login_required
def palabra_editar(request, pk):
    perfil = obtener_perfil_activo(request.user)
    if perfil is None or not puede_editar_palabras_prioridad(perfil):
        return redirect("gestion:sin_acceso")
    palabra = PalabraClavePrioridad.objects.filter(pk=pk).first()
    if palabra is None:
        return redirect("gestion:palabras_lista")
    form = PalabraPrioridadForm(request.POST or None, instance=palabra)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("gestion:palabras_lista")
    return render(request, "gestion/palabra_form.html", {"perfil": perfil, "form": form})
```

- [ ] **Step 7: Agregar las rutas**

En `gestion/urls.py`:

```python
    path("palabras-prioridad/", views_admin.palabras_lista, name="palabras_lista"),
    path("palabras-prioridad/nueva/", views_admin.palabra_crear, name="palabra_crear"),
    path("palabras-prioridad/<int:pk>/", views_admin.palabra_editar, name="palabra_editar"),
```

- [ ] **Step 8: Crear los templates**

Crear `gestion/templates/gestion/palabras_lista.html`:

```html
{% extends "gestion/base.html" %}
{% block title %}Palabras clave de prioridad{% endblock %}
{% block content %}
<section class="page-title">
  <div><h2>Palabras clave de prioridad</h2></div>
  <a class="button btn--confirmar" href="{% url 'gestion:palabra_crear' %}">Nueva palabra</a>
</section>
<table class="data-table">
  <thead><tr><th>Palabra</th><th>Nivel</th><th>Activa</th><th></th></tr></thead>
  <tbody>
    {% for p in palabras %}
      <tr>
        <td data-label="Palabra">{{ p.texto }}</td>
        <td data-label="Nivel">{{ p.get_nivel_display }}</td>
        <td data-label="Activa">{{ p.activo|yesno:"Si,No" }}</td>
        <td data-label="Editar"><a href="{% url 'gestion:palabra_editar' p.pk %}">Editar</a></td>
      </tr>
    {% empty %}
      <tr><td colspan="4"><div class="empty-state">No hay palabras cargadas.</div></td></tr>
    {% endfor %}
  </tbody>
</table>
{% endblock %}
```

Crear `gestion/templates/gestion/palabra_form.html`:

```html
{% extends "gestion/base.html" %}
{% block title %}Palabra de prioridad{% endblock %}
{% block content %}
<section class="page-title"><div><h2>Palabra de prioridad</h2></div></section>
<form method="post" class="admin-form">
  {% csrf_token %}
  {{ form.as_p }}
  <button class="btn--confirmar" type="submit">Guardar</button>
  <a class="button" href="{% url 'gestion:palabras_lista' %}">Cancelar</a>
</form>
{% endblock %}
```

- [ ] **Step 9: Agregar la tile en el panel de administración**

En `gestion/templates/gestion/admin_panel.html`, agregar dentro de `.admin-tiles`:

```html
  {% if perfil|puede_editar_palabras %}<a class="button" href="{% url 'gestion:palabras_lista' %}">Palabras de prioridad</a>{% endif %}
```

(Asegurar `{% load gestion_ui %}` al inicio del template.)

- [ ] **Step 10: Correr el test y verificar que pasa**

Run: `.venv/bin/python manage.py test gestion.tests.PalabrasPrioridadUiTests -v 2`
Expected: PASS (3 tests).

- [ ] **Step 11: Correr toda la suite**

Run: `.venv/bin/python manage.py test`
Expected: OK, sin fallos.

- [ ] **Step 12: Commit**

```bash
git add gestion/permisos.py gestion/templatetags/gestion_ui.py gestion/forms_admin.py gestion/views_admin.py gestion/urls.py gestion/templates/gestion/palabras_lista.html gestion/templates/gestion/palabra_form.html gestion/templates/gestion/admin_panel.html gestion/tests.py
git commit -m "Agrega la edicion de palabras clave de prioridad para SUPERVISOR_DAS"
```

---

## Notas de verificación final

- El día del despliegue, con las palabras sembradas, la priorización da exactamente lo mismo que antes: no hay cambio de comportamiento hasta que el supervisor edite.
- La consecuencia "badge vs desglose" (una solicitud creada antes de un cambio de palabras puede mostrar un desglose en vivo que no suma el badge guardado) queda documentada en la spec y no se aborda aquí.
- Correr la suite completa (`.venv/bin/python manage.py test`) antes de dar por terminado; incluye la regresión de priorización del chatbot.
