# Acceso y navegación del módulo de gestión — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dar al módulo de gestión una página de login propia, redirigir el cierre de sesión hacia ella, un 404 controlado y una página de sin-acceso que se lea como tema de permisos y ofrezca salida.

**Architecture:** Vistas y templates nuevos en la app `gestion`, más tres settings (`LOGIN_URL`, `LOGOUT_REDIRECT_URL`, `handler404`). No se toca el backend OIDC ni las reglas de acceso. Todo cuelga del urlconf de gestión (`cesfam_chatbot/urls_gestion.py`), que sirve el subdominio de gestión.

**Tech Stack:** Django 5.2, `mozilla_django_oidc`, templates Django, `static/css/gestion.css`. Sin dependencias nuevas.

**Spec:** `docs/superpowers/specs/2026-09-01-acceso-navegacion-gestion-design.md`

## Global Constraints

- Código, comentarios y mensajes de commit en **español, sin tildes en identificadores**. Sin emojis en commits.
- Tests con el **Django test runner** (`.venv/bin/python manage.py test`), NO pytest. Correrlos contra **MySQL** (Docker up), no SQLite.
- Los tests del módulo de gestión usan `HTTP_HOST="gestion.localhost"` y la clase se decora con `@override_settings(ALLOWED_HOSTS=["gestion.localhost", "testserver"], GESTION_HOST="gestion.localhost")`.
- Seguir los patrones de la app `gestion`: vistas en `gestion/views.py`, templates en `gestion/templates/gestion/`, estilos en `static/css/gestion.css`.
- No tocar `gestion/auth.py` ni las reglas de quién tiene acceso.

---

### Task 1: Página de login y navegación oculta sin sesión

**Files:**
- Modify: `gestion/views.py` (agregar vista `login`)
- Modify: `gestion/urls.py` (agregar ruta `login/`)
- Create: `gestion/templates/gestion/login.html`
- Modify: `gestion/templates/gestion/base.html:52` (envolver `<nav>` en `{% if perfil %}`)
- Modify: `cesfam_chatbot/settings.py:175` (`LOGIN_URL`)
- Modify: `static/css/gestion.css` (estilo `.auth-card`)
- Test: `gestion/tests.py` (clase nueva `AccesoLoginTests`)

**Interfaces:**
- Produces: vista `gestion.views.login` (nombre de url `gestion:login`, path `/login/`), template `gestion/login.html`, setting `LOGIN_URL = "gestion:login"`.

- [ ] **Step 1: Escribir el test que falla**

En `gestion/tests.py`, agregar al final:

```python
@override_settings(ALLOWED_HOSTS=["gestion.localhost", "testserver"], GESTION_HOST="gestion.localhost")
class AccesoLoginTests(TestCase):
    def setUp(self):
        self.centro = Centro.objects.get(pk=620)

    def test_sin_sesion_una_ruta_protegida_redirige_al_login(self):
        response = self.client.get("/selector/", HTTP_HOST="gestion.localhost")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/login/?next=/selector/")

    def test_login_muestra_boton_de_google_con_next(self):
        response = self.client.get("/login/?next=/selector/", HTTP_HOST="gestion.localhost")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/oidc/authenticate/", html=False)
        self.assertContains(response, "next=%2Fselector%2F", html=False)

    def test_login_descarta_next_con_host_externo(self):
        response = self.client.get(
            "/login/?next=https://malicioso.example/x", HTTP_HOST="gestion.localhost"
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "malicioso.example", html=False)

    def test_login_no_muestra_navegacion(self):
        response = self.client.get("/login/", HTTP_HOST="gestion.localhost")
        self.assertNotContains(response, 'aria-label="Navegacion principal"', html=False)
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/python manage.py test gestion.tests.AccesoLoginTests -v 2`
Expected: FAIL — `/login/` da 404 (ruta no existe) y la ruta protegida redirige a `oidc_authentication_init`, no a `/login/`.

- [ ] **Step 3: Agregar la ruta de login**

En `gestion/urls.py`, dentro de `urlpatterns`, después de `path("sin-acceso/", ...)`:

```python
    path("login/", views.login, name="login"),
```

- [ ] **Step 4: Escribir la vista de login**

En `gestion/views.py`, agregar los imports que falten al inicio:

```python
from django.utils.http import url_has_allowed_host_and_scheme
```

Y la vista (junto a `sin_acceso`):

```python
def login(request):
    """Pagina de entrada del modulo: un boton para iniciar sesion con Google.
    Si el usuario ya tiene sesion y perfil, salta directo al panel. Preserva
    'next' validado contra el host actual para volver a la ruta pedida."""
    perfil = obtener_perfil_activo(request.user)
    if perfil is not None:
        return redirect("gestion:panel")
    next_url = request.GET.get("next", "")
    if not url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        next_url = ""
    return render(request, "gestion/login.html", {"next": next_url})
```

- [ ] **Step 5: Crear el template de login**

Crear `gestion/templates/gestion/login.html`:

```html
{% extends "gestion/base.html" %}
{% block title %}Iniciar sesion{% endblock %}
{% block content %}
<section class="auth-card">
  <h2>Iniciar sesion</h2>
  <p>Acceda con su cuenta institucional de Google para usar el modulo.</p>
  <a class="button btn--confirmar" href="{% url 'oidc_authentication_init' %}{% if next %}?next={{ next|urlencode }}{% endif %}">
    Iniciar sesion con Google
  </a>
</section>
{% endblock %}
```

- [ ] **Step 6: Ocultar la navegación sin perfil**

En `gestion/templates/gestion/base.html`, envolver el bloque `<nav class="gestion-nav" ...> ... </nav>` (línea 52 y sus cierres) en `{% if perfil %} ... {% endif %}`:

```html
    {% if perfil %}
    <nav class="gestion-nav" aria-label="Navegacion principal">
      <a href="{% url 'gestion:selector_lista' %}">Selector</a>
      <a href="{% url 'gestion:comunicador_lista' %}">Comunicador</a>
    </nav>
    {% endif %}
```

- [ ] **Step 7: Cambiar LOGIN_URL**

En `cesfam_chatbot/settings.py`, línea 175:

```python
LOGIN_URL = "gestion:login"
```

- [ ] **Step 8: Agregar estilo de la tarjeta de acceso**

En `static/css/gestion.css`, al final:

```css
.auth-card {
  max-width: 32rem;
  margin: var(--space-5) auto;
  padding: var(--space-5);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 8px;
  box-shadow: var(--soft-shadow);
  display: grid;
  gap: var(--space-3);
  justify-items: start;
}
.auth-card h2 { margin: 0; }
.auth-card p { margin: 0; color: var(--muted); }
```

- [ ] **Step 9: Correr los tests y verificar que pasan**

Run: `.venv/bin/python manage.py test gestion.tests.AccesoLoginTests -v 2`
Expected: PASS (4 tests).

- [ ] **Step 10: Commit**

```bash
git add gestion/views.py gestion/urls.py gestion/templates/gestion/login.html gestion/templates/gestion/base.html cesfam_chatbot/settings.py static/css/gestion.css gestion/tests.py
git commit -m "Agrega la pagina de login del modulo de gestion"
```

---

### Task 2: Cierre de sesión hacia el login y sin-acceso con salida

**Files:**
- Modify: `cesfam_chatbot/settings.py:178` (`LOGOUT_REDIRECT_URL`)
- Modify: `gestion/templates/gestion/sin_acceso.html`
- Test: `gestion/tests.py` (agregar a `AccesoLoginTests`)

**Interfaces:**
- Consumes: la ruta `gestion:login` (Task 1).
- Produces: `LOGOUT_REDIRECT_URL = "/login/"`; `sin_acceso.html` con formulario POST a `oidc_logout`.

- [ ] **Step 1: Escribir el test que falla**

En `gestion/tests.py`, agregar métodos a `AccesoLoginTests`:

```python
    def test_logout_redirige_al_login(self):
        from django.conf import settings
        self.assertEqual(settings.LOGOUT_REDIRECT_URL, "/login/")

    def test_sin_acceso_ofrece_cerrar_sesion(self):
        response = self.client.get("/sin-acceso/", HTTP_HOST="gestion.localhost")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/oidc/logout/", html=False)
        self.assertContains(response, "permisos", html=False)
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/python manage.py test gestion.tests.AccesoLoginTests.test_logout_redirige_al_login gestion.tests.AccesoLoginTests.test_sin_acceso_ofrece_cerrar_sesion -v 2`
Expected: FAIL — `LOGOUT_REDIRECT_URL` es `/sin-acceso/` y el template no tiene el formulario de logout.

- [ ] **Step 3: Cambiar LOGOUT_REDIRECT_URL**

En `cesfam_chatbot/settings.py`, línea 178:

```python
LOGOUT_REDIRECT_URL = "/login/"
```

- [ ] **Step 4: Reescribir el template sin-acceso**

Reemplazar `gestion/templates/gestion/sin_acceso.html` por:

```html
{% extends "gestion/base.html" %}
{% block title %}Sin acceso{% endblock %}
{% block content %}
<section class="auth-card">
  <h2>Sin acceso</h2>
  <p>Su cuenta inicio sesion correctamente, pero no tiene permisos habilitados
     para el modulo de gestion. Si cree que es un error, contacte al administrador.</p>
  <form method="post" action="{% url 'oidc_logout' %}">
    {% csrf_token %}
    <button type="submit">Cerrar sesion y usar otra cuenta</button>
  </form>
</section>
{% endblock %}
```

- [ ] **Step 5: Correr los tests y verificar que pasan**

Run: `.venv/bin/python manage.py test gestion.tests.AccesoLoginTests -v 2`
Expected: PASS (6 tests).

- [ ] **Step 6: Commit**

```bash
git add cesfam_chatbot/settings.py gestion/templates/gestion/sin_acceso.html gestion/tests.py
git commit -m "Redirige el cierre de sesion al login y da salida en sin-acceso"
```

---

### Task 3: 404 controlado del módulo

**Files:**
- Modify: `gestion/views.py` (agregar vista `pagina_no_encontrada`)
- Modify: `cesfam_chatbot/urls_gestion.py` (agregar `handler404`)
- Create: `gestion/templates/gestion/404.html`
- Test: `gestion/tests.py` (clase nueva `Error404GestionTests`)

**Interfaces:**
- Consumes: `base.html` (Task 1, nav ya oculta sin perfil).
- Produces: `handler404 = "gestion.views.pagina_no_encontrada"` en el urlconf de gestión; template `gestion/404.html`.

- [ ] **Step 1: Escribir el test que falla**

En `gestion/tests.py`, agregar:

```python
@override_settings(
    DEBUG=False,
    ALLOWED_HOSTS=["gestion.localhost", "testserver"],
    GESTION_HOST="gestion.localhost",
)
class Error404GestionTests(TestCase):
    def test_ruta_inexistente_renderiza_404_del_modulo(self):
        response = self.client.get("/ruta-que-no-existe-xyz/", HTTP_HOST="gestion.localhost")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "no existe", status_code=404, html=False)
        self.assertTemplateUsed(response, "gestion/404.html")
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/python manage.py test gestion.tests.Error404GestionTests -v 2`
Expected: FAIL — sin `handler404` propio, la respuesta no usa `gestion/404.html`.

- [ ] **Step 3: Escribir la vista de 404**

En `gestion/views.py`, agregar (no requiere `login_required`; recibe `exception` como todo handler404):

```python
def pagina_no_encontrada(request, exception):
    """Handler 404 del modulo de gestion. Solo se renderiza con DEBUG=False;
    con DEBUG=True Django muestra su pagina tecnica antes de llegar aca."""
    return render(request, "gestion/404.html", status=404)
```

- [ ] **Step 4: Registrar el handler404**

En `cesfam_chatbot/urls_gestion.py`, después de `urlpatterns`:

```python
handler404 = "gestion.views.pagina_no_encontrada"
```

- [ ] **Step 5: Crear el template 404**

Crear `gestion/templates/gestion/404.html`:

```html
{% extends "gestion/base.html" %}
{% block title %}Pagina no encontrada{% endblock %}
{% block content %}
<section class="auth-card">
  <h2>Pagina no encontrada</h2>
  <p>La pagina que buscas no existe o la direccion es incorrecta.</p>
  <a class="button" href="/">Volver al inicio</a>
</section>
{% endblock %}
```

- [ ] **Step 6: Correr el test y verificar que pasa**

Run: `.venv/bin/python manage.py test gestion.tests.Error404GestionTests -v 2`
Expected: PASS.

- [ ] **Step 7: Correr toda la suite de gestión**

Run: `.venv/bin/python manage.py test gestion -v 1`
Expected: OK, sin fallos.

- [ ] **Step 8: Commit**

```bash
git add gestion/views.py cesfam_chatbot/urls_gestion.py gestion/templates/gestion/404.html gestion/tests.py
git commit -m "Agrega el 404 controlado del modulo de gestion"
```

---

## Notas de verificación final

- El 404 propio solo se ve con `DEBUG=False` (en local, con `DEBUG=True`, Django muestra su página técnica). El test lo fuerza con `@override_settings(DEBUG=False)`, igual que el test del 404 del chatbot en `solicitudes/tests.py`.
- Correr la suite completa antes de dar por terminado: `.venv/bin/python manage.py test`.
