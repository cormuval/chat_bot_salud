# Panel de administración del módulo de gestión — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dar a los roles de mando un panel dentro del módulo para gestionar perfiles de acceso (con guardas por rol y alcance) y descargar tres reportes operativos en CSV.

**Architecture:** Vistas y templates nuevos en `gestion`, reglas de acceso en `gestion/permisos.py`, filtros de plantilla en `gestion/templatetags/gestion_ui.py`. El alta de perfil crea el `User` de Django por email. Los reportes se generan como CSV con `StreamingHttpResponse` y stdlib `csv`, reutilizando el alcance por centro existente (`centros_permitidos`).

**Tech Stack:** Django 5.2, templates Django, stdlib `csv`. Sin dependencias nuevas.

**Spec:** `docs/superpowers/specs/2026-09-01-panel-administracion-gestion-design.md`

## Global Constraints

- Código, comentarios y mensajes de commit en **español, sin tildes en identificadores**. Sin emojis en commits.
- Tests con el **Django test runner** contra **MySQL** (Docker up), no pytest ni SQLite.
- Tests de gestión: `HTTP_HOST="gestion.localhost"` y clase decorada con `@override_settings(ALLOWED_HOSTS=["gestion.localhost", "testserver"], GESTION_HOST="gestion.localhost")`.
- Guardas de rol validadas **en el servidor**, no solo ocultando opciones en el form.
- Seguir patrones de `gestion`: vistas en `gestion/views.py` (o módulos nuevos importados), templates en `gestion/templates/gestion/`, permisos en `gestion/permisos.py`.

**Depende de:** el plan de acceso y navegación (login, nav oculta sin perfil). Puede implementarse después de ese, sobre el mismo `base.html`.

---

### Task 1: Reglas de acceso y shell del panel

**Files:**
- Modify: `gestion/permisos.py` (funciones de admin)
- Modify: `gestion/templatetags/gestion_ui.py` (filtros para el template)
- Modify: `gestion/views.py` (vista `admin_panel`)
- Modify: `gestion/urls.py` (ruta `admin/`)
- Create: `gestion/templates/gestion/admin_panel.html`
- Modify: `gestion/templates/gestion/base.html` (link "Administracion" en la nav)
- Test: `gestion/tests.py` (clase `AdminPanelAccesoTests`)

**Interfaces:**
- Produces:
  - `permisos.puede_administrar_perfiles(perfil) -> bool`
  - `permisos.puede_ver_reportes(perfil) -> bool`
  - `permisos.roles_asignables(perfil) -> list[PerfilUsuario.Rol]`
  - `permisos.centros_administrables(perfil) -> QuerySet[Centro]`
  - `permisos.es_ultimo_admin_activo(perfil) -> bool`
  - vista `gestion:admin_panel` en `/admin-panel/`
  - filtros de template `puede_administrar` y `puede_ver_reportes`

- [ ] **Step 1: Escribir el test que falla**

En `gestion/tests.py`:

```python
@override_settings(ALLOWED_HOSTS=["gestion.localhost", "testserver"], GESTION_HOST="gestion.localhost")
class AdminPanelAccesoTests(TestCase):
    def setUp(self):
        self.centro = Centro.objects.get(pk=620)

    def _login(self, rol):
        usuario = User.objects.create_user(f"{rol}@cmvalparaiso.cl", email=f"{rol}@cmvalparaiso.cl")
        PerfilUsuario.objects.create(usuario=usuario, rol=rol, centro=self.centro)
        self.client.force_login(usuario)
        return usuario

    def test_rol_operativo_no_ve_panel(self):
        self._login(PerfilUsuario.Rol.SELECTOR)
        response = self.client.get("/admin-panel/", HTTP_HOST="gestion.localhost")
        self.assertEqual(response.status_code, 302)

    def test_admin_ve_panel_con_accesos(self):
        self._login(PerfilUsuario.Rol.ADMIN)
        response = self.client.get("/admin-panel/", HTTP_HOST="gestion.localhost")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Perfiles")
        self.assertContains(response, "Reportes")

    def test_supervisor_centro_ve_panel(self):
        self._login(PerfilUsuario.Rol.SUPERVISOR_CENTRO)
        response = self.client.get("/admin-panel/", HTTP_HOST="gestion.localhost")
        self.assertEqual(response.status_code, 200)
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/python manage.py test gestion.tests.AdminPanelAccesoTests -v 2`
Expected: FAIL — `/admin-panel/` no existe (404/error de url).

- [ ] **Step 3: Agregar las reglas de acceso**

En `gestion/permisos.py`, agregar el import y las funciones:

```python
from solicitudes.models import Centro  # agregar junto a los imports existentes


ROLES_ADMIN_GLOBAL = {PerfilUsuario.Rol.ADMIN, PerfilUsuario.Rol.SUPERVISOR_DAS}
ROLES_ADMIN_PERFILES = ROLES_ADMIN_GLOBAL | {PerfilUsuario.Rol.SUPERVISOR_CENTRO}
ROLES_OPERATIVOS = {
    PerfilUsuario.Rol.SELECTOR,
    PerfilUsuario.Rol.COMUNICADOR,
    PerfilUsuario.Rol.FULL,
    PerfilUsuario.Rol.SOME,
}


def puede_administrar_perfiles(perfil):
    return perfil.rol in ROLES_ADMIN_PERFILES


def puede_ver_reportes(perfil):
    return perfil.rol in ROLES_ADMIN_PERFILES


def roles_asignables(perfil):
    if perfil.rol in ROLES_ADMIN_GLOBAL:
        return list(PerfilUsuario.Rol)
    return [rol for rol in PerfilUsuario.Rol if rol in ROLES_OPERATIVOS]


def centros_administrables(perfil):
    if perfil.rol in ROLES_ADMIN_GLOBAL:
        return Centro.objects.all()
    return Centro.objects.filter(pk=perfil.centro_id)


def es_ultimo_admin_activo(perfil):
    if perfil.rol != PerfilUsuario.Rol.ADMIN or not perfil.activo:
        return False
    otros = PerfilUsuario.objects.filter(
        rol=PerfilUsuario.Rol.ADMIN, activo=True
    ).exclude(pk=perfil.pk)
    return not otros.exists()
```

- [ ] **Step 4: Agregar los filtros de template**

En `gestion/templatetags/gestion_ui.py`, agregar:

```python
from gestion import permisos


@register.filter
def puede_administrar(perfil):
    return bool(perfil) and permisos.puede_administrar_perfiles(perfil)


@register.filter
def puede_ver_reportes(perfil):
    return bool(perfil) and permisos.puede_ver_reportes(perfil)
```

- [ ] **Step 5: Agregar la vista del panel**

En `gestion/views.py`, agregar el import y la vista:

```python
from .permisos import puede_administrar_perfiles, puede_ver_reportes  # junto a los imports de permisos


@login_required
def admin_panel(request):
    perfil = obtener_perfil_activo(request.user)
    if perfil is None or not (
        puede_administrar_perfiles(perfil) or puede_ver_reportes(perfil)
    ):
        return redirect("gestion:sin_acceso")
    return render(
        request,
        "gestion/admin_panel.html",
        {
            "perfil": perfil,
            "puede_perfiles": puede_administrar_perfiles(perfil),
            "puede_reportes": puede_ver_reportes(perfil),
        },
    )
```

- [ ] **Step 6: Agregar la ruta**

En `gestion/urls.py`, dentro de `urlpatterns`:

```python
    path("admin-panel/", views.admin_panel, name="admin_panel"),
```

- [ ] **Step 7: Crear el template del panel**

Crear `gestion/templates/gestion/admin_panel.html`:

```html
{% extends "gestion/base.html" %}
{% block title %}Administracion{% endblock %}
{% block content %}
<section class="page-title"><div><h2>Administracion</h2></div></section>
<div class="admin-tiles">
  {% if puede_perfiles %}<a class="button" href="{% url 'gestion:perfiles_lista' %}">Perfiles</a>{% endif %}
  {% if puede_reportes %}<a class="button" href="{% url 'gestion:reportes' %}">Reportes</a>{% endif %}
</div>
{% endblock %}
```

Nota: las rutas `gestion:perfiles_lista` y `gestion:reportes` se crean en las tareas 2 y 4. Para que este template no rompa en esta tarea, agregar ambas rutas como stubs ahora en `gestion/urls.py` apuntando a vistas placeholder, o implementar las tareas en orden y correr el test de esta tarea al final. **Recomendado:** implementar en orden; el test de la Task 1 se corre después de la Task 4. Por ahora, reemplazar los `href` por `#` y ajustarlos en las tareas siguientes.

Versión de esta tarea (sin rutas aún):

```html
{% extends "gestion/base.html" %}
{% block title %}Administracion{% endblock %}
{% block content %}
<section class="page-title"><div><h2>Administracion</h2></div></section>
<div class="admin-tiles">
  {% if puede_perfiles %}<a class="button" href="#" data-admin-perfiles>Perfiles</a>{% endif %}
  {% if puede_reportes %}<a class="button" href="#" data-admin-reportes>Reportes</a>{% endif %}
</div>
{% endblock %}
```

- [ ] **Step 8: Agregar el link en la navegación**

En `gestion/templates/gestion/base.html`, agregar `{% load gestion_ui %}` al inicio (después de `{% load static %}`), y dentro del `{% if perfil %}` de la nav, tras el enlace Comunicador:

```html
      {% if perfil|puede_administrar or perfil|puede_ver_reportes %}
        <a href="{% url 'gestion:admin_panel' %}">Administracion</a>
      {% endif %}
```

- [ ] **Step 9: Agregar estilo de las tiles**

En `static/css/gestion.css`, al final:

```css
.admin-tiles { display: flex; gap: var(--space-3); flex-wrap: wrap; }
```

- [ ] **Step 10: Correr el test y verificar que pasa**

Run: `.venv/bin/python manage.py test gestion.tests.AdminPanelAccesoTests -v 2`
Expected: PASS (3 tests).

- [ ] **Step 11: Commit**

```bash
git add gestion/permisos.py gestion/templatetags/gestion_ui.py gestion/views.py gestion/urls.py gestion/templates/gestion/admin_panel.html gestion/templates/gestion/base.html static/css/gestion.css gestion/tests.py
git commit -m "Agrega el shell del panel de administracion y sus reglas de acceso"
```

---

### Task 2: Listar perfiles con alcance

**Files:**
- Create: `gestion/views_admin.py` (vistas de perfiles)
- Modify: `gestion/urls.py` (ruta `perfiles/`)
- Create: `gestion/templates/gestion/perfiles_lista.html`
- Modify: `gestion/templates/gestion/admin_panel.html` (href real a perfiles)
- Test: `gestion/tests.py` (clase `PerfilesListaTests`)

**Interfaces:**
- Consumes: `permisos.puede_administrar_perfiles`, `permisos.centros_administrables` (Task 1).
- Produces: vista `gestion:perfiles_lista` en `/perfiles/`.

- [ ] **Step 1: Escribir el test que falla**

```python
@override_settings(ALLOWED_HOSTS=["gestion.localhost", "testserver"], GESTION_HOST="gestion.localhost")
class PerfilesListaTests(TestCase):
    def setUp(self):
        self.centro_a = Centro.objects.get(pk=620)
        self.centro_b = Centro.objects.exclude(pk=620).first()

    def _login(self, rol, centro):
        u = User.objects.create_user(f"admin-{rol}@cmvalparaiso.cl", email=f"admin-{rol}@cmvalparaiso.cl")
        PerfilUsuario.objects.create(usuario=u, rol=rol, centro=centro)
        self.client.force_login(u)

    def test_admin_ve_perfiles_de_todos_los_centros(self):
        otro = User.objects.create_user("otro@cmvalparaiso.cl", email="otro@cmvalparaiso.cl")
        PerfilUsuario.objects.create(usuario=otro, rol=PerfilUsuario.Rol.SELECTOR, centro=self.centro_b)
        self._login(PerfilUsuario.Rol.ADMIN, self.centro_a)
        response = self.client.get("/perfiles/", HTTP_HOST="gestion.localhost")
        self.assertContains(response, "otro@cmvalparaiso.cl")

    def test_supervisor_centro_solo_ve_su_centro(self):
        otro = User.objects.create_user("otro-b@cmvalparaiso.cl", email="otro-b@cmvalparaiso.cl")
        PerfilUsuario.objects.create(usuario=otro, rol=PerfilUsuario.Rol.SELECTOR, centro=self.centro_b)
        self._login(PerfilUsuario.Rol.SUPERVISOR_CENTRO, self.centro_a)
        response = self.client.get("/perfiles/", HTTP_HOST="gestion.localhost")
        self.assertNotContains(response, "otro-b@cmvalparaiso.cl")
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/python manage.py test gestion.tests.PerfilesListaTests -v 2`
Expected: FAIL — `/perfiles/` no existe.

- [ ] **Step 3: Crear el módulo de vistas de admin con la lista**

Crear `gestion/views_admin.py`:

```python
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .models import PerfilUsuario
from .permisos import (
    centros_administrables,
    obtener_perfil_activo,
    puede_administrar_perfiles,
)


def _perfiles_del_alcance(perfil):
    qs = PerfilUsuario.objects.select_related("usuario", "centro").order_by(
        "usuario__email"
    )
    if perfil.rol in {PerfilUsuario.Rol.ADMIN, PerfilUsuario.Rol.SUPERVISOR_DAS}:
        return qs
    return qs.filter(centro_id=perfil.centro_id)


@login_required
def perfiles_lista(request):
    perfil = obtener_perfil_activo(request.user)
    if perfil is None or not puede_administrar_perfiles(perfil):
        return redirect("gestion:sin_acceso")
    return render(
        request,
        "gestion/perfiles_lista.html",
        {"perfil": perfil, "perfiles": _perfiles_del_alcance(perfil)},
    )
```

Nota: `obtener_perfil_activo` vive en `gestion/permisos.py` — verificar que esté exportado allí (ya lo está: lo usan las vistas actuales vía import desde `permisos`).

- [ ] **Step 4: Agregar la ruta**

En `gestion/urls.py`, agregar el import y la ruta:

```python
from . import views_admin
```
```python
    path("perfiles/", views_admin.perfiles_lista, name="perfiles_lista"),
```

- [ ] **Step 5: Crear el template de la lista**

Crear `gestion/templates/gestion/perfiles_lista.html`:

```html
{% extends "gestion/base.html" %}
{% block title %}Perfiles{% endblock %}
{% block content %}
<section class="page-title">
  <div><h2>Perfiles de acceso</h2></div>
  <a class="button btn--confirmar" href="{% url 'gestion:perfil_crear' %}">Nuevo perfil</a>
</section>
<table class="data-table">
  <thead><tr><th>Correo</th><th>Rol</th><th>Centro</th><th>Activo</th><th></th></tr></thead>
  <tbody>
    {% for p in perfiles %}
      <tr>
        <td data-label="Correo">{{ p.usuario.email }}</td>
        <td data-label="Rol">{{ p.get_rol_display }}</td>
        <td data-label="Centro">{{ p.centro }}</td>
        <td data-label="Activo">{{ p.activo|yesno:"Si,No" }}</td>
        <td data-label="Editar"><a href="{% url 'gestion:perfil_editar' p.pk %}">Editar</a></td>
      </tr>
    {% empty %}
      <tr><td colspan="5"><div class="empty-state">No hay perfiles en su alcance.</div></td></tr>
    {% endfor %}
  </tbody>
</table>
{% endblock %}
```

Nota: los enlaces `perfil_crear` y `perfil_editar` se crean en la Task 3. Correr el test de esta tarea después de la Task 3, o usar `href="#"` temporal. Para esta tarea, cambiar esos dos `href` por `#` y ajustarlos en la Task 3.

- [ ] **Step 6: Actualizar el href de Perfiles en el panel**

En `gestion/templates/gestion/admin_panel.html`, cambiar `href="#" data-admin-perfiles` por `href="{% url 'gestion:perfiles_lista' %}"`.

- [ ] **Step 7: Correr el test y verificar que pasa**

Run: `.venv/bin/python manage.py test gestion.tests.PerfilesListaTests -v 2`
Expected: PASS (2 tests).

- [ ] **Step 8: Commit**

```bash
git add gestion/views_admin.py gestion/urls.py gestion/templates/gestion/perfiles_lista.html gestion/templates/gestion/admin_panel.html gestion/tests.py
git commit -m "Lista perfiles de acceso con alcance por rol"
```

---

### Task 3: Crear, editar y dar de baja perfiles con guardas

**Files:**
- Create: `gestion/forms_admin.py` (`PerfilAdminForm`)
- Modify: `gestion/views_admin.py` (vistas `perfil_crear`, `perfil_editar`)
- Modify: `gestion/urls.py` (rutas)
- Create: `gestion/templates/gestion/perfil_form.html`
- Modify: `gestion/templates/gestion/perfiles_lista.html` (href reales)
- Test: `gestion/tests.py` (clase `PerfilesCrudTests`)

**Interfaces:**
- Consumes: `permisos.roles_asignables`, `permisos.centros_administrables`, `permisos.es_ultimo_admin_activo` (Task 1).
- Produces: vistas `gestion:perfil_crear` (`/perfiles/nuevo/`) y `gestion:perfil_editar` (`/perfiles/<pk>/`).

- [ ] **Step 1: Escribir el test que falla**

```python
@override_settings(ALLOWED_HOSTS=["gestion.localhost", "testserver"], GESTION_HOST="gestion.localhost")
class PerfilesCrudTests(TestCase):
    def setUp(self):
        self.centro_a = Centro.objects.get(pk=620)
        self.centro_b = Centro.objects.exclude(pk=620).first()

    def _login(self, rol, centro):
        u = User.objects.create_user(f"jefe-{rol}@cmvalparaiso.cl", email=f"jefe-{rol}@cmvalparaiso.cl")
        PerfilUsuario.objects.create(usuario=u, rol=rol, centro=centro)
        self.client.force_login(u)

    def test_admin_crea_perfil_y_user_por_email(self):
        self._login(PerfilUsuario.Rol.ADMIN, self.centro_a)
        response = self.client.post(
            "/perfiles/nuevo/",
            {"email": "nuevo@cmvalparaiso.cl", "rol": "SELECTOR", "centro": self.centro_a.pk, "activo": "on"},
            HTTP_HOST="gestion.localhost",
        )
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(email="nuevo@cmvalparaiso.cl")
        self.assertTrue(user.is_active)
        self.assertFalse(user.has_usable_password())
        self.assertTrue(PerfilUsuario.objects.filter(usuario=user, rol="SELECTOR").exists())

    def test_supervisor_centro_no_puede_crear_admin(self):
        self._login(PerfilUsuario.Rol.SUPERVISOR_CENTRO, self.centro_a)
        response = self.client.post(
            "/perfiles/nuevo/",
            {"email": "x@cmvalparaiso.cl", "rol": "ADMIN", "centro": self.centro_a.pk, "activo": "on"},
            HTTP_HOST="gestion.localhost",
        )
        self.assertFalse(User.objects.filter(email="x@cmvalparaiso.cl").exists())

    def test_supervisor_centro_no_puede_crear_en_otro_centro(self):
        self._login(PerfilUsuario.Rol.SUPERVISOR_CENTRO, self.centro_a)
        self.client.post(
            "/perfiles/nuevo/",
            {"email": "y@cmvalparaiso.cl", "rol": "SELECTOR", "centro": self.centro_b.pk, "activo": "on"},
            HTTP_HOST="gestion.localhost",
        )
        self.assertFalse(User.objects.filter(email="y@cmvalparaiso.cl").exists())

    def test_dar_de_baja_es_logico(self):
        self._login(PerfilUsuario.Rol.ADMIN, self.centro_a)
        u = User.objects.create_user("baja@cmvalparaiso.cl", email="baja@cmvalparaiso.cl")
        p = PerfilUsuario.objects.create(usuario=u, rol="SELECTOR", centro=self.centro_a)
        self.client.post(
            f"/perfiles/{p.pk}/",
            {"rol": "SELECTOR", "centro": self.centro_a.pk},  # sin 'activo' => False
            HTTP_HOST="gestion.localhost",
        )
        p.refresh_from_db()
        self.assertFalse(p.activo)
        self.assertTrue(PerfilUsuario.objects.filter(pk=p.pk).exists())

    def test_no_se_puede_dar_de_baja_al_ultimo_admin(self):
        u = User.objects.create_user("unico-admin@cmvalparaiso.cl", email="unico-admin@cmvalparaiso.cl")
        p = PerfilUsuario.objects.create(usuario=u, rol="ADMIN", centro=self.centro_a)
        self.client.force_login(u)
        self.client.post(
            f"/perfiles/{p.pk}/",
            {"rol": "ADMIN", "centro": self.centro_a.pk},  # intenta desactivar
            HTTP_HOST="gestion.localhost",
        )
        p.refresh_from_db()
        self.assertTrue(p.activo)
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/python manage.py test gestion.tests.PerfilesCrudTests -v 2`
Expected: FAIL — `/perfiles/nuevo/` y `/perfiles/<pk>/` no existen.

- [ ] **Step 3: Crear el form**

Crear `gestion/forms_admin.py`:

```python
from django import forms

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
```

- [ ] **Step 4: Agregar las vistas de crear y editar**

En `gestion/views_admin.py`, agregar imports y vistas:

```python
from django.contrib import messages
from django.contrib.auth.models import User

from .forms_admin import PerfilAdminForm
from .permisos import es_ultimo_admin_activo, roles_asignables


def _puede_operar_sobre(perfil_editor, rol_objetivo, centro_objetivo_id):
    asignables = {r.value for r in roles_asignables(perfil_editor)}
    if rol_objetivo not in asignables:
        return False
    if perfil_editor.rol in {PerfilUsuario.Rol.ADMIN, PerfilUsuario.Rol.SUPERVISOR_DAS}:
        return True
    return centro_objetivo_id == perfil_editor.centro_id


@login_required
def perfil_crear(request):
    editor = obtener_perfil_activo(request.user)
    if editor is None or not puede_administrar_perfiles(editor):
        return redirect("gestion:sin_acceso")
    form = PerfilAdminForm(request.POST or None, perfil_editor=editor, es_creacion=True)
    if request.method == "POST" and form.is_valid():
        rol = form.cleaned_data["rol"]
        centro = form.cleaned_data["centro"]
        if not _puede_operar_sobre(editor, rol, centro.pk):
            form.add_error(None, "No tiene permiso para asignar ese rol o centro.")
        else:
            email = form.cleaned_data["email"].strip()
            user = User.objects.filter(email__iexact=email).first()
            if user is None:
                user = User.objects.create_user(username=email, email=email)
            if PerfilUsuario.objects.filter(usuario=user).exists():
                form.add_error("email", "Ese usuario ya tiene un perfil. Editelo desde la lista.")
            else:
                perfil = form.save(commit=False)
                perfil.usuario = user
                perfil.save()
                messages.success(request, "Perfil creado.")
                return redirect("gestion:perfiles_lista")
    return render(request, "gestion/perfil_form.html", {"perfil": editor, "form": form, "es_creacion": True})


@login_required
def perfil_editar(request, pk):
    editor = obtener_perfil_activo(request.user)
    if editor is None or not puede_administrar_perfiles(editor):
        return redirect("gestion:sin_acceso")
    objetivo = _perfiles_del_alcance(editor).filter(pk=pk).first()
    if objetivo is None:
        return redirect("gestion:perfiles_lista")
    form = PerfilAdminForm(request.POST or None, instance=objetivo, perfil_editor=editor, es_creacion=False)
    if request.method == "POST" and form.is_valid():
        rol = form.cleaned_data["rol"]
        centro = form.cleaned_data["centro"]
        activo = form.cleaned_data["activo"]
        if not _puede_operar_sobre(editor, rol, centro.pk):
            form.add_error(None, "No tiene permiso para asignar ese rol o centro.")
        elif es_ultimo_admin_activo(objetivo) and (not activo or rol != PerfilUsuario.Rol.ADMIN):
            form.add_error(None, "No puede dejar el sistema sin administradores activos.")
        else:
            form.save()
            messages.success(request, "Perfil actualizado.")
            return redirect("gestion:perfiles_lista")
    return render(request, "gestion/perfil_form.html", {"perfil": editor, "form": form, "es_creacion": False})
```

- [ ] **Step 5: Agregar las rutas**

En `gestion/urls.py`:

```python
    path("perfiles/nuevo/", views_admin.perfil_crear, name="perfil_crear"),
    path("perfiles/<int:pk>/", views_admin.perfil_editar, name="perfil_editar"),
```

- [ ] **Step 6: Crear el template del form**

Crear `gestion/templates/gestion/perfil_form.html`:

```html
{% extends "gestion/base.html" %}
{% block title %}{% if es_creacion %}Nuevo perfil{% else %}Editar perfil{% endif %}{% endblock %}
{% block content %}
<section class="page-title"><div><h2>{% if es_creacion %}Nuevo perfil{% else %}Editar perfil{% endif %}</h2></div></section>
<form method="post" class="admin-form">
  {% csrf_token %}
  {{ form.as_p }}
  <button class="btn--confirmar" type="submit">Guardar</button>
  <a class="button" href="{% url 'gestion:perfiles_lista' %}">Cancelar</a>
</form>
{% endblock %}
```

- [ ] **Step 7: Poner los href reales en la lista de perfiles**

En `gestion/templates/gestion/perfiles_lista.html`, si en la Task 2 se dejaron como `#`, cambiar el botón "Nuevo perfil" a `{% url 'gestion:perfil_crear' %}` y el enlace "Editar" a `{% url 'gestion:perfil_editar' p.pk %}`.

- [ ] **Step 8: Correr el test y verificar que pasa**

Run: `.venv/bin/python manage.py test gestion.tests.PerfilesCrudTests -v 2`
Expected: PASS (5 tests).

- [ ] **Step 9: Commit**

```bash
git add gestion/forms_admin.py gestion/views_admin.py gestion/urls.py gestion/templates/gestion/perfil_form.html gestion/templates/gestion/perfiles_lista.html gestion/tests.py
git commit -m "Agrega alta, edicion y baja de perfiles con guardas de rol y centro"
```

---

### Task 4: Utilidad de exportación CSV y reporte de solicitudes

**Files:**
- Create: `gestion/reportes.py` (helper CSV + consultas)
- Modify: `gestion/views_admin.py` (vistas `reportes`, `reporte_solicitudes`)
- Modify: `gestion/urls.py` (rutas)
- Create: `gestion/templates/gestion/reportes.html`
- Modify: `gestion/templates/gestion/admin_panel.html` (href real a reportes)
- Test: `gestion/tests.py` (clase `ReporteSolicitudesTests`)

**Interfaces:**
- Consumes: `permisos.puede_ver_reportes`, `PerfilUsuario.centros_permitidos()`.
- Produces:
  - `reportes.exportar_csv(nombre_archivo, encabezados, filas) -> StreamingHttpResponse`
  - `reportes.rango_fechas(request) -> tuple[date|None, date|None]`
  - vistas `gestion:reportes` (`/reportes/`) y `gestion:reporte_solicitudes` (`/reportes/solicitudes/`)

- [ ] **Step 1: Escribir el test que falla**

```python
@override_settings(ALLOWED_HOSTS=["gestion.localhost", "testserver"], GESTION_HOST="gestion.localhost")
class ReporteSolicitudesTests(TestCase):
    def setUp(self):
        self.centro = Centro.objects.get(pk=620)
        u = User.objects.create_user("rep@cmvalparaiso.cl", email="rep@cmvalparaiso.cl")
        PerfilUsuario.objects.create(usuario=u, rol=PerfilUsuario.Rol.ADMIN, centro=self.centro)
        self.client.force_login(u)
        crear_solicitud_base(centro_salud=self.centro, nombre="Pedro Test", rut="25747311-2")

    def test_descarga_csv_de_solicitudes(self):
        response = self.client.get(
            "/reportes/solicitudes/?desde=2000-01-01&hasta=2100-01-01",
            HTTP_HOST="gestion.localhost",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        contenido = b"".join(response.streaming_content).decode("utf-8")
        self.assertTrue(contenido.startswith("\ufeff"))
        self.assertIn("Pedro Test", contenido)
        self.assertIn("RUT", contenido)

    def test_sin_rango_no_exporta(self):
        response = self.client.get("/reportes/solicitudes/", HTTP_HOST="gestion.localhost")
        self.assertNotEqual(response.get("Content-Type", ""), "text/csv; charset=utf-8")
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/python manage.py test gestion.tests.ReporteSolicitudesTests -v 2`
Expected: FAIL — rutas de reportes no existen.

- [ ] **Step 3: Crear el helper de reportes**

Crear `gestion/reportes.py`:

```python
import csv
from datetime import date

from django.http import StreamingHttpResponse


class _Buffer:
    def write(self, value):
        return value


def exportar_csv(nombre_archivo, encabezados, filas):
    """Devuelve un CSV en streaming, UTF-8 con BOM para que Excel respete
    tildes y enies."""
    writer = csv.writer(_Buffer())

    def generar():
        yield "\ufeff"  # BOM UTF-8
        yield writer.writerow(encabezados)
        for fila in filas:
            yield writer.writerow(fila)

    response = StreamingHttpResponse(generar(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{nombre_archivo}"'
    return response


def _parse_fecha(valor):
    try:
        return date.fromisoformat(valor)
    except (ValueError, TypeError):
        return None


def rango_fechas(request):
    return _parse_fecha(request.GET.get("desde")), _parse_fecha(request.GET.get("hasta"))
```

- [ ] **Step 4: Agregar las vistas de reportes**

En `gestion/views_admin.py`, agregar imports y vistas:

```python
from solicitudes.models import Solicitud

from .reportes import exportar_csv, rango_fechas
from .permisos import puede_ver_reportes


@login_required
def reportes(request):
    perfil = obtener_perfil_activo(request.user)
    if perfil is None or not puede_ver_reportes(perfil):
        return redirect("gestion:sin_acceso")
    return render(request, "gestion/reportes.html", {"perfil": perfil})


def _solicitudes_del_alcance(perfil):
    qs = Solicitud.objects.select_related("centro_salud").order_by("date_solicitud")
    if perfil.ve_todos_los_centros:
        return qs
    return qs.filter(centro_salud__in=perfil.centros_permitidos())


@login_required
def reporte_solicitudes(request):
    perfil = obtener_perfil_activo(request.user)
    if perfil is None or not puede_ver_reportes(perfil):
        return redirect("gestion:sin_acceso")
    desde, hasta = rango_fechas(request)
    if desde is None or hasta is None:
        messages.error(request, "Indique el rango de fechas (desde y hasta).")
        return redirect("gestion:reportes")
    qs = _solicitudes_del_alcance(perfil).filter(date_solicitud__date__range=(desde, hasta))
    encabezados = ["Fecha", "RUT", "Nombre", "Telefono", "Edad", "Sexo", "Centro",
                   "Motivo", "Detalle", "Prioridad administrativa", "Puntaje"]
    filas = (
        [
            s.date_solicitud.strftime("%Y-%m-%d %H:%M"), s.rut, s.nombre, s.telefono,
            s.edad, s.get_sexo_display(), str(s.centro_salud), s.motivo, s.detalle_motivo,
            s.get_priorizacion_solicitud_display(), s.puntaje_prioridad,
        ]
        for s in qs.iterator()
    )
    return exportar_csv("solicitudes.csv", encabezados, filas)
```

- [ ] **Step 5: Agregar las rutas**

En `gestion/urls.py`:

```python
    path("reportes/", views_admin.reportes, name="reportes"),
    path("reportes/solicitudes/", views_admin.reporte_solicitudes, name="reporte_solicitudes"),
```

- [ ] **Step 6: Crear el template de reportes**

Crear `gestion/templates/gestion/reportes.html`:

```html
{% extends "gestion/base.html" %}
{% block title %}Reportes{% endblock %}
{% block content %}
<section class="page-title"><div><h2>Reportes</h2><p>Descargas en CSV. Indique el rango de fechas.</p></div></section>
{% for m in messages %}<p class="danger-text">{{ m }}</p>{% endfor %}
<form method="get" action="{% url 'gestion:reporte_solicitudes' %}" class="admin-form">
  <label>Desde <input type="date" name="desde" required></label>
  <label>Hasta <input type="date" name="hasta" required></label>
  <button class="btn--confirmar" type="submit">Descargar solicitudes</button>
</form>
{% endblock %}
```

- [ ] **Step 7: Poner el href real de Reportes en el panel**

En `gestion/templates/gestion/admin_panel.html`, cambiar `href="#" data-admin-reportes` por `href="{% url 'gestion:reportes' %}"`.

- [ ] **Step 8: Correr el test y verificar que pasa**

Run: `.venv/bin/python manage.py test gestion.tests.ReporteSolicitudesTests -v 2`
Expected: PASS (2 tests).

- [ ] **Step 9: Commit**

```bash
git add gestion/reportes.py gestion/views_admin.py gestion/urls.py gestion/templates/gestion/reportes.html gestion/templates/gestion/admin_panel.html gestion/tests.py
git commit -m "Agrega el reporte de solicitudes en CSV"
```

---

### Task 5: Reportes de contactabilidad y de gestiones del selector

**Files:**
- Modify: `gestion/views_admin.py` (vistas `reporte_contactabilidad`, `reporte_gestiones`)
- Modify: `gestion/urls.py` (rutas)
- Modify: `gestion/templates/gestion/reportes.html` (dos formularios más)
- Test: `gestion/tests.py` (clase `ReportesOperativosTests`)

**Interfaces:**
- Consumes: `reportes.exportar_csv`, `reportes.rango_fechas` (Task 4), `Gestion`, `RegistroContacto`, `PerfilUsuario.centros_permitidos()`.
- Produces: vistas `gestion:reporte_contactabilidad` y `gestion:reporte_gestiones`.

- [ ] **Step 1: Escribir el test que falla**

```python
@override_settings(ALLOWED_HOSTS=["gestion.localhost", "testserver"], GESTION_HOST="gestion.localhost")
class ReportesOperativosTests(TestCase):
    def setUp(self):
        self.centro = Centro.objects.get(pk=620)
        self.usuario = User.objects.create_user("rep2@cmvalparaiso.cl", email="rep2@cmvalparaiso.cl")
        PerfilUsuario.objects.create(usuario=self.usuario, rol=PerfilUsuario.Rol.ADMIN, centro=self.centro)
        self.client.force_login(self.usuario)
        sol = crear_solicitud_base(centro_salud=self.centro, nombre="Luz Vega")
        self.gestion = sol.gestion
        self.gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)
        self.gestion.registrar_no_contesta(self.usuario, token_contacto="t1")

    def test_reporte_contactabilidad(self):
        response = self.client.get(
            "/reportes/contactabilidad/?desde=2000-01-01&hasta=2100-01-01",
            HTTP_HOST="gestion.localhost",
        )
        contenido = b"".join(response.streaming_content).decode("utf-8")
        self.assertIn("Luz Vega", contenido)
        self.assertIn("No contesta", contenido)

    def test_reporte_gestiones_selector(self):
        response = self.client.get(
            "/reportes/gestiones/?desde=2000-01-01&hasta=2100-01-01",
            HTTP_HOST="gestion.localhost",
        )
        contenido = b"".join(response.streaming_content).decode("utf-8")
        self.assertIn("Luz Vega", contenido)
        self.assertIn("Aceptada", contenido)
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/python manage.py test gestion.tests.ReportesOperativosTests -v 2`
Expected: FAIL — rutas no existen.

- [ ] **Step 3: Agregar las vistas**

En `gestion/views_admin.py`, agregar imports y vistas:

```python
from .models import Gestion, RegistroContacto


def _registros_del_alcance(perfil):
    qs = RegistroContacto.objects.select_related(
        "gestion__solicitud__centro_salud", "usuario"
    ).order_by("creado_en")
    if perfil.ve_todos_los_centros:
        return qs
    return qs.filter(gestion__solicitud__centro_salud__in=perfil.centros_permitidos())


@login_required
def reporte_contactabilidad(request):
    perfil = obtener_perfil_activo(request.user)
    if perfil is None or not puede_ver_reportes(perfil):
        return redirect("gestion:sin_acceso")
    desde, hasta = rango_fechas(request)
    if desde is None or hasta is None:
        messages.error(request, "Indique el rango de fechas (desde y hasta).")
        return redirect("gestion:reportes")
    qs = _registros_del_alcance(perfil).filter(creado_en__date__range=(desde, hasta))
    encabezados = ["Fecha", "Paciente", "RUT", "Centro", "Canal", "Resultado", "Usuario", "Mensaje"]
    filas = (
        [
            r.creado_en.strftime("%Y-%m-%d %H:%M"), r.gestion.solicitud.nombre,
            r.gestion.solicitud.rut, str(r.gestion.solicitud.centro_salud),
            r.get_canal_display(), r.get_resultado_display(),
            r.usuario.email if r.usuario else "", r.mensaje,
        ]
        for r in qs.iterator()
    )
    return exportar_csv("contactabilidad.csv", encabezados, filas)


@login_required
def reporte_gestiones(request):
    perfil = obtener_perfil_activo(request.user)
    if perfil is None or not puede_ver_reportes(perfil):
        return redirect("gestion:sin_acceso")
    desde, hasta = rango_fechas(request)
    if desde is None or hasta is None:
        messages.error(request, "Indique el rango de fechas (desde y hasta).")
        return redirect("gestion:reportes")
    qs = (
        Gestion.objects.select_related("solicitud__centro_salud", "decidido_por", "motivo_rechazo")
        .del_alcance(perfil)
        .filter(fecha_decision__date__range=(desde, hasta))
        .order_by("fecha_decision")
    )
    encabezados = ["Fecha decision", "Paciente", "RUT", "Centro", "Decision",
                   "Prioridad clinica", "Motivo rechazo", "Decidido por"]
    filas = (
        [
            g.fecha_decision.strftime("%Y-%m-%d %H:%M") if g.fecha_decision else "",
            g.solicitud.nombre, g.solicitud.rut, str(g.solicitud.centro_salud),
            g.get_decision_display(), g.get_prioridad_clinica_display() or "",
            str(g.motivo_rechazo) if g.motivo_rechazo_id else "",
            g.decidido_por.email if g.decidido_por else "",
        ]
        for g in qs.iterator()
    )
    return exportar_csv("gestiones-selector.csv", encabezados, filas)
```

Nota: `Gestion.objects.del_alcance(perfil)` ya existe en `GestionQuerySet`.

- [ ] **Step 4: Agregar las rutas**

En `gestion/urls.py`:

```python
    path("reportes/contactabilidad/", views_admin.reporte_contactabilidad, name="reporte_contactabilidad"),
    path("reportes/gestiones/", views_admin.reporte_gestiones, name="reporte_gestiones"),
```

- [ ] **Step 5: Agregar los dos formularios al template de reportes**

En `gestion/templates/gestion/reportes.html`, después del formulario de solicitudes, agregar:

```html
<form method="get" action="{% url 'gestion:reporte_contactabilidad' %}" class="admin-form">
  <label>Desde <input type="date" name="desde" required></label>
  <label>Hasta <input type="date" name="hasta" required></label>
  <button class="btn--confirmar" type="submit">Descargar contactabilidad</button>
</form>
<form method="get" action="{% url 'gestion:reporte_gestiones' %}" class="admin-form">
  <label>Desde <input type="date" name="desde" required></label>
  <label>Hasta <input type="date" name="hasta" required></label>
  <button class="btn--confirmar" type="submit">Descargar gestiones del selector</button>
</form>
```

- [ ] **Step 6: Correr el test y verificar que pasa**

Run: `.venv/bin/python manage.py test gestion.tests.ReportesOperativosTests -v 2`
Expected: PASS (2 tests).

- [ ] **Step 7: Correr toda la suite**

Run: `.venv/bin/python manage.py test`
Expected: OK, sin fallos.

- [ ] **Step 8: Commit**

```bash
git add gestion/views_admin.py gestion/urls.py gestion/templates/gestion/reportes.html gestion/tests.py
git commit -m "Agrega los reportes de contactabilidad y de gestiones del selector"
```

---

## Notas de verificación final

- Confirmar visualmente (server con `DEBUG=False`, sesión de un ADMIN) que la sección "Administracion" aparece en la nav y que los tres CSV descargan y abren en Excel con tildes correctas.
- El reporte de solicitudes contiene datos personales sensibles: dejar constancia en el contexto de la revisión de ciberseguridad (ver spec).
