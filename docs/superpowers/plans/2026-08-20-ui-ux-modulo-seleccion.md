# UI UX Modulo De Seleccion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convertir las pantallas operativas del modulo de seleccion desde HTML sin estilos a una interfaz densa, clara y operable con listas redisenadas, detalle en modal, acciones explicitas y desglose de prioridad administrativa.

**Architecture:** La mejora es progresiva: las paginas completas actuales siguen existiendo y los mismos endpoints devuelven parciales cuando reciben `?fragmento=1`. La logica de negocio ya implementada en `Gestion`, formularios y permisos se mantiene como fuente unica; esta capa agrega helpers de presentacion, parciales compartidos, CSS vanilla y un JS delgado que solo carga fragmentos, envia formularios y actualiza la lista.

**Tech Stack:** Django 5.2.8, templates Django, CSS vanilla en `static/css/gestion.css`, JavaScript vanilla en `static/js/gestion.js`, MySQL 8.4, test runner nativo de Django (`manage.py test`). Sin npm, sin framework CSS, sin framework de tests JavaScript.

## Global Constraints

- Spec de referencia: `docs/superpowers/specs/2026-08-20-ui-ux-modulo-seleccion-design.md`.
- Pantalla base de diseno: **1366x768**.
- Bajo los ~900px las tablas se reordenan como tarjetas apiladas y el modal pasa a pantalla completa.
- El modal no reemplaza nada, se monta encima; sin JavaScript el usuario cae en la pagina completa.
- Las mismas vistas `selector_detalle` y `comunicador_detalle` responden con el parcial, sin layout, cuando reciben `?fragmento=1`.
- El POST siempre devuelve HTML: error de formulario, siguiente caso, cola vacia o confirmacion.
- El selector salta automaticamente al siguiente caso al decidir; el comunicador no.
- No agregar atajos de teclado.
- No agregar reportes, estadisticas ni tableros.
- No agregar framework de CSS o JS ni paso de build; el proyecto no usa npm.
- No pre-renderizar los detalles en la lista: la foto de credencial se carga solo al abrir el caso.
- El color nunca es el unico portador de significado.
- `ADMIN`, `SUPERVISOR_DAS` y `SUPERVISOR_CENTRO` siguen siendo solo lectura en pantallas operativas.
- Codigo, comentarios, mensajes de commit y docs en espanol, sin tildes en identificadores. Sin emojis en commits.
- Tests con Django test runner contra MySQL local: `.venv/bin/python manage.py test`.

---

## Estrategia De Ejecucion Por Etapas

El plan debe ejecutarse en dos PRs, en el orden de la spec:

1. **Fase 1 - Fundacion visual y listas:** CSS, base, helpers de UI, listas del selector y comunicador, telefono invalido y cuenta regresiva visible. No toca el flujo POST ni introduce modal.
2. **Fase 2 - Interaccion:** desglose de prioridad, parciales, `fragmento=1`, `<dialog>`, acciones explicitas, guardar-y-siguiente del selector y confirmacion/cierre del comunicador.

Si se usa `subagent-driven-development`, despachar un subagente por tarea. Si se ejecuta inline, hacer checkpoint y correr los tests indicados al final de cada tarea.

## File Structure

- Create: `static/css/gestion.css` - tokens visuales copiados de `saludbot.css`, layout denso, tablas, tarjetas responsive, modal, botones, distintivos y estados.
- Create: `static/js/gestion.js` - `<dialog>`, fetch de fragmentos, envio de formularios con HTML, remocion de filas, actualizacion de contadores y retorno de foco.
- Create: `gestion/templatetags/__init__.py` - paquete de template tags.
- Create: `gestion/templatetags/gestion_ui.py` - helpers de presentacion: prioridad, tiempo relativo, cuenta regresiva, telefono WhatsApp, mensaje previo.
- Modify: `gestion/templates/gestion/base.html` - `{% static %}`, encabezado, navegacion, identidad, usuario conectado, rol, centro y salida.
- Modify: `gestion/templates/gestion/selector_lista.html` - cola redisenada, tabs con conteos, fila clickeable, motivo truncado, prioridad con desglose y correccion visible.
- Create: `gestion/templates/gestion/_detalle_selector.html` - parcial compartido del detalle selector con pie fijo y acciones.
- Modify: `gestion/templates/gestion/selector_detalle.html` - wrapper de pagina completa que incluye `_detalle_selector.html`.
- Modify: `gestion/templates/gestion/comunicador_lista.html` - dos grupos de trabajo, telefono `tel:`, telefono invalido, estado de intentos y cuenta regresiva.
- Create: `gestion/templates/gestion/_detalle_comunicador.html` - parcial compartido del detalle comunicador con historial, WhatsApp y acciones.
- Modify: `gestion/templates/gestion/comunicador_detalle.html` - wrapper de pagina completa que incluye `_detalle_comunicador.html`.
- Modify: `gestion/views.py` - soporte `fragmento=1`, siguiente caso del selector, parcial de cola vacia y confirmacion del comunicador.
- Modify: `gestion/tests.py` - tests de UI servidor, fragmentos, permisos, POST HTML, telefono invalido y solo lectura.
- Modify: `solicitudes/priorizacion.py` - funcion aditiva de desglose de factores sin cambiar puntaje ni clasificacion.
- Modify: `solicitudes/tests.py` - tests del desglose.

---

### Task 1: Fundacion Visual, Layout Base Y Helpers De UI

**Files:**
- Create: `static/css/gestion.css`
- Create: `gestion/templatetags/__init__.py`
- Create: `gestion/templatetags/gestion_ui.py`
- Modify: `gestion/templates/gestion/base.html`
- Modify: `gestion/tests.py`

**Interfaces:**
- Consumes: `PerfilUsuario`, `Gestion`, `Solicitud`, `Gestion.url_whatsapp()`.
- Produces:
  - Template filter `prioridad_css(valor: str) -> str`.
  - Template filter `tiempo_relativo(fecha: datetime) -> str`.
  - Template filter `horas_restantes_rechazo(gestion: Gestion) -> str`.
  - Template filter `telefono_whatsapp_valido(gestion: Gestion) -> bool`.
  - Template filter `mensaje_whatsapp_previo(gestion: Gestion) -> str`.
  - Bloques de template: `extra_head`, `body_attrs`, `content`.

- [ ] **Step 1: Escribir tests de helpers y layout base**

Agregar al final de `gestion/tests.py`:

```python
from django.template import Context, Template


class GestionUiHelpersTests(TestCase):
    def setUp(self):
        self.centro = Centro.objects.get(pk=620)
        self.usuario = User.objects.create_user(
            "selector-ui@cmvalparaiso.cl", email="selector-ui@cmvalparaiso.cl"
        )
        self.perfil = PerfilUsuario.objects.create(
            usuario=self.usuario,
            rol=PerfilUsuario.Rol.SELECTOR,
            centro=self.centro,
        )
        self.motivo = MotivoRechazo.objects.create(
            nombre="Datos insuficientes",
            mensaje_paciente="Hola {nombre}, faltan datos para resolver su solicitud.",
        )

    def _render(self, source, context):
        template = Template("{% load gestion_ui %}" + source)
        return template.render(Context(context)).strip()

    def test_prioridad_css_entrega_clase_estable(self):
        html = self._render("{{ valor|prioridad_css }}", {"valor": Solicitud.Prioridad.URGENTE})
        self.assertEqual(html, "prioridad--urgente")

    def test_tiempo_relativo_entrega_horas_y_minutos(self):
        hace_dos_horas = timezone.now() - timedelta(hours=2, minutes=10)
        html = self._render("{{ fecha|tiempo_relativo }}", {"fecha": hace_dos_horas})
        self.assertEqual(html, "hace 2 h")

    def test_horas_restantes_rechazo_muestra_plazo(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        gestion.rechazar(self.usuario, self.motivo)
        Gestion.objects.filter(pk=gestion.pk).update(
            fecha_decision=timezone.now() - timedelta(hours=18, minutes=10)
        )
        gestion.refresh_from_db()
        html = self._render("{{ gestion|horas_restantes_rechazo }}", {"gestion": gestion})
        self.assertEqual(html, "quedan 5 h para avisar")

    def test_telefono_whatsapp_valido_usa_url_whatsapp(self):
        gestion = crear_solicitud_base(centro_salud=self.centro, telefono="123").gestion
        gestion.rechazar(self.usuario, self.motivo)
        html = self._render(
            "{% if gestion|telefono_whatsapp_valido %}si{% else %}no{% endif %}",
            {"gestion": gestion},
        )
        self.assertEqual(html, "no")

    def test_mensaje_whatsapp_previo_reemplaza_nombre(self):
        gestion = crear_solicitud_base(
            centro_salud=self.centro,
            nombre="Ana Perez",
        ).gestion
        gestion.rechazar(self.usuario, self.motivo)
        html = self._render("{{ gestion|mensaje_whatsapp_previo }}", {"gestion": gestion})
        self.assertIn("Ana Perez", html)
        self.assertNotIn("{nombre}", html)


@override_settings(ALLOWED_HOSTS=["gestion.localhost", "testserver"], GESTION_HOST="gestion.localhost")
class GestionBaseLayoutTests(TestCase):
    def setUp(self):
        self.centro = Centro.objects.get(pk=620)
        self.usuario = User.objects.create_user(
            "selector-base@cmvalparaiso.cl", email="selector-base@cmvalparaiso.cl"
        )
        PerfilUsuario.objects.create(
            usuario=self.usuario,
            rol=PerfilUsuario.Rol.SELECTOR,
            centro=self.centro,
        )
        self.client.force_login(self.usuario)

    def test_base_carga_css_js_y_datos_de_sesion(self):
        response = self.client.get("/selector/", HTTP_HOST="gestion.localhost")
        self.assertContains(response, 'href="/static/css/gestion.css"', html=False)
        self.assertContains(response, 'src="/static/js/gestion.js"', html=False)
        self.assertContains(response, "selector-base@cmvalparaiso.cl")
        self.assertContains(response, "Selector")
        self.assertContains(response, str(self.centro))
        self.assertContains(response, "Cerrar sesion")
```

- [ ] **Step 2: Correr tests y confirmar falla inicial**

Run: `.venv/bin/python manage.py test gestion.tests.GestionUiHelpersTests gestion.tests.GestionBaseLayoutTests -v 2`

Expected: FAIL con `TemplateSyntaxError: 'gestion_ui' is not a registered tag library` y/o ausencia de `gestion.css`.

- [ ] **Step 3: Crear template tags**

Crear `gestion/templatetags/__init__.py` vacio.

Crear `gestion/templatetags/gestion_ui.py`:

```python
from datetime import timedelta

from django import template
from django.utils import timezone

from gestion.models import Gestion


register = template.Library()


@register.filter
def prioridad_css(valor):
    return f"prioridad--{str(valor or '').lower()}"


@register.filter
def tiempo_relativo(fecha):
    if not fecha:
        return "-"
    delta = timezone.now() - fecha
    if delta < timedelta(minutes=1):
        return "recien"
    if delta < timedelta(hours=1):
        return f"hace {max(1, int(delta.total_seconds() // 60))} min"
    if delta < timedelta(days=1):
        return f"hace {int(delta.total_seconds() // 3600)} h"
    return f"hace {delta.days} d"


@register.filter
def horas_restantes_rechazo(gestion):
    if (
        gestion.decision != Gestion.Decision.RECHAZADA
        or gestion.fecha_decision is None
        or gestion.cerrada_en is not None
    ):
        return ""
    vence = gestion.fecha_decision + timedelta(hours=24)
    restante = vence - timezone.now()
    if restante.total_seconds() <= 0:
        return "plazo vencido"
    horas = int(restante.total_seconds() // 3600)
    if horas >= 1:
        return f"quedan {horas} h para avisar"
    minutos = max(1, int(restante.total_seconds() // 60))
    return f"quedan {minutos} min para avisar"


@register.filter
def telefono_whatsapp_valido(gestion):
    return bool(gestion.url_whatsapp())


@register.filter
def mensaje_whatsapp_previo(gestion):
    if gestion.motivo_rechazo_id:
        mensaje = gestion.motivo_rechazo.mensaje_paciente
    else:
        mensaje = (
            "Hola {nombre}, le contactamos desde su centro de salud por su "
            "solicitud de morbilidad."
        )
    return mensaje.replace("{nombre}", gestion.solicitud.nombre)
```

- [ ] **Step 4: Crear CSS base**

Crear `static/css/gestion.css`:

```css
/* Tokens copiados de static/css/saludbot.css para no tocar la app publica. */
:root {
  --app-bg: #f4f7fb;
  --primary: #1976d2;
  --primary-700: #145ea8;
  --text: #1f2937;
  --muted: #64748b;
  --surface: #ffffff;
  --line: #d8e2ef;
  --shadow: 0 12px 30px rgba(31, 41, 55, 0.10);
  --soft-shadow: 0 4px 14px rgba(31, 41, 55, 0.10);
  --ok: #166534;
  --warn: #b45309;
  --danger: #b91c1c;
  --info: #0369a1;
  --prio-urgente: #b91c1c;
  --prio-alta: #c2410c;
  --prio-media: #0369a1;
  --prio-baja: #166534;
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 24px;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  min-height: 100vh;
  background: var(--app-bg);
  color: var(--text);
  font-family: Arial, Helvetica, sans-serif;
  font-size: 14px;
  letter-spacing: 0;
}

a { color: var(--primary-700); font-weight: 700; text-decoration: none; }
a:hover, a:focus { text-decoration: underline; }
button, input, select, textarea { font: inherit; }
button { cursor: pointer; }

.gestion-shell {
  min-height: 100vh;
  display: grid;
  grid-template-rows: auto 1fr;
}

.gestion-header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: var(--space-4);
  padding: var(--space-3) var(--space-5);
  background: var(--surface);
  border-bottom: 1px solid var(--line);
}

.gestion-brand h1 { margin: 0; font-size: 1.2rem; line-height: 1.2; }
.gestion-brand p, .session-box p { margin: 2px 0 0; color: var(--muted); }
.session-box { display: flex; align-items: center; gap: var(--space-3); flex-wrap: wrap; justify-content: flex-end; }
.session-pill { padding: 4px 8px; border: 1px solid var(--line); border-radius: 999px; background: #eef6ff; color: var(--primary-700); font-weight: 700; }

.gestion-nav {
  display: flex;
  gap: var(--space-2);
  padding: 0 var(--space-5) var(--space-3);
  background: var(--surface);
  border-bottom: 1px solid var(--line);
}

.gestion-nav a, .tab-link {
  min-height: 34px;
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: 0 var(--space-3);
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface);
}

.gestion-main { width: min(100% - 32px, 1280px); margin: 0 auto; padding: var(--space-5) 0; }
.page-title { display: flex; align-items: end; justify-content: space-between; gap: var(--space-4); margin-bottom: var(--space-4); }
.page-title h2 { margin: 0; font-size: 1.35rem; }
.page-title p { margin: 4px 0 0; color: var(--muted); }

.data-table { width: 100%; border-collapse: collapse; background: var(--surface); box-shadow: var(--soft-shadow); }
.data-table th, .data-table td { padding: 10px 12px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
.data-table th { color: var(--muted); font-size: 0.78rem; text-transform: uppercase; }
.row-link { cursor: pointer; }
.row-link:hover { background: #f8fbff; }
.truncate { max-width: 34rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.priority-badge, .status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 8px;
  border-radius: 999px;
  border: 1px solid currentColor;
  font-weight: 800;
  white-space: nowrap;
}
.prioridad--urgente { color: var(--prio-urgente); background: #fef2f2; }
.prioridad--alta { color: var(--prio-alta); background: #fff7ed; }
.prioridad--media { color: var(--prio-media); background: #f0f9ff; }
.prioridad--baja { color: var(--prio-baja); background: #f0fdf4; }

.muted { color: var(--muted); }
.warning-text { color: var(--warn); font-weight: 700; }
.danger-text { color: var(--danger); font-weight: 700; }
.empty-state { padding: var(--space-5); border: 1px dashed var(--line); background: var(--surface); text-align: center; color: var(--muted); }

@media (max-width: 900px) {
  .gestion-header { grid-template-columns: 1fr; padding: var(--space-3); }
  .session-box { justify-content: flex-start; }
  .gestion-nav { padding: 0 var(--space-3) var(--space-3); overflow-x: auto; }
  .gestion-main { width: min(100% - 20px, 1280px); padding: var(--space-3) 0; }
  .data-table, .data-table thead, .data-table tbody, .data-table tr, .data-table th, .data-table td { display: block; }
  .data-table thead { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
  .data-table tr { margin-bottom: var(--space-3); border: 1px solid var(--line); background: var(--surface); box-shadow: var(--soft-shadow); }
  .data-table td { display: grid; grid-template-columns: 9rem minmax(0, 1fr); gap: var(--space-2); border-bottom: 1px solid var(--line); }
  .data-table td::before { content: attr(data-label); color: var(--muted); font-weight: 700; }
  .truncate { white-space: normal; }
}
```

- [ ] **Step 5: Actualizar `base.html`**

Reemplazar `gestion/templates/gestion/base.html` por:

```html
{% load static %}
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}Modulo de seleccion{% endblock %}</title>
  <link rel="stylesheet" href="{% static 'css/gestion.css' %}">
  {% block extra_head %}{% endblock %}
</head>
<body {% block body_attrs %}{% endblock %}>
  <div class="gestion-shell">
    <header class="gestion-header">
      <div class="gestion-brand">
        <h1>Modulo de seleccion</h1>
        <p>Solicitudes de morbilidad CESFAM</p>
      </div>
      {% if perfil %}
        <div class="session-box" aria-label="Sesion actual">
          <span>{{ request.user.email|default:request.user.username }}</span>
          <span class="session-pill">{{ perfil.get_rol_display }}</span>
          <span class="muted">{{ perfil.centro }}</span>
          <a href="{% url 'oidc_logout' %}">Cerrar sesion</a>
        </div>
      {% endif %}
    </header>
    <nav class="gestion-nav" aria-label="Navegacion principal">
      <a href="{% url 'gestion:selector_lista' %}">Selector</a>
      <a href="{% url 'gestion:comunicador_lista' %}">Comunicador</a>
    </nav>
    <main class="gestion-main">
      {% for message in messages %}
        <p class="status-badge">{{ message }}</p>
      {% endfor %}
      {% block content %}{% endblock %}
    </main>
  </div>
  <script src="{% static 'js/gestion.js' %}" defer></script>
</body>
</html>
```

- [ ] **Step 6: Crear JS inicial no operativo**

Crear `static/js/gestion.js`:

```javascript
(function () {
  "use strict";

  document.documentElement.classList.add("js");
})();
```

- [ ] **Step 7: Correr tests de la tarea**

Run: `.venv/bin/python manage.py test gestion.tests.GestionUiHelpersTests gestion.tests.GestionBaseLayoutTests -v 2`

Expected: PASS.

- [ ] **Step 8: Correr regresion completa**

Run: `.venv/bin/python manage.py test`

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add static/css/gestion.css static/js/gestion.js gestion/templatetags gestion/templates/gestion/base.html gestion/tests.py
git commit -m "Agrega fundacion visual de gestion"
```

---

### Task 2: Listas Redisenadas Sin Modal

**Files:**
- Modify: `gestion/views.py`
- Modify: `gestion/templates/gestion/selector_lista.html`
- Modify: `gestion/templates/gestion/comunicador_lista.html`
- Modify: `gestion/tests.py`

**Interfaces:**
- Consumes: filters de `gestion_ui`, `Gestion.objects.cola_selector()`, `decididas_corregibles_selector()`, `no_aplica_selector()`, `tabla_comunicador()`.
- Produces:
  - Contexto de selector: `conteos_selector: dict[str, int]`, `mostrar_columna_centro: bool`.
  - Contexto de comunicador: `gestiones_aceptadas`, `gestiones_rechazadas`.

- [ ] **Step 1: Escribir tests de listas**

Agregar a `gestion/tests.py`:

```python
@override_settings(ALLOWED_HOSTS=["gestion.localhost", "testserver"], GESTION_HOST="gestion.localhost")
class GestionListasUiTests(TestCase):
    def setUp(self):
        self.centro = Centro.objects.get(pk=620)
        self.usuario = User.objects.create_user("selector-lista@cmvalparaiso.cl")
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

    def test_selector_lista_oculta_decision_y_centro_para_selector_de_un_centro(self):
        gestion = crear_solicitud_base(
            centro_salud=self.centro,
            motivo="Dolor pecho",
            detalle_motivo="Dolor pecho desde la noche anterior",
            priorizacion_solicitud=Solicitud.Prioridad.URGENTE,
        ).gestion
        response = self.client.get("/selector/", HTTP_HOST="gestion.localhost")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dolor pecho desde la noche anterior")
        self.assertContains(response, "Urgente")
        self.assertContains(response, f'data-detail-url="/selector/{gestion.pk}/?fragmento=1"', html=False)
        self.assertNotContains(response, "<th>Decision</th>", html=False)
        self.assertNotContains(response, "<th>Centro</th>", html=False)

    def test_selector_lista_muestra_centro_para_admin(self):
        self.perfil.rol = PerfilUsuario.Rol.ADMIN
        self.perfil.save(update_fields=["rol"])
        crear_solicitud_base(centro_salud=self.centro).gestion
        response = self.client.get("/selector/", HTTP_HOST="gestion.localhost")
        self.assertContains(response, "<th>Centro</th>", html=False)

    def test_selector_tabs_muestran_conteos(self):
        pendiente = crear_solicitud_base(centro_salud=self.centro).gestion
        decidida = crear_solicitud_base(centro_salud=self.centro).gestion
        decidida.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)
        no_aplica = crear_solicitud_base(centro_salud=self.centro).gestion
        no_aplica.marcar_no_aplica(self.usuario)
        response = self.client.get("/selector/", HTTP_HOST="gestion.localhost")
        self.assertContains(response, "Pendientes")
        self.assertContains(response, ">1<", html=False)
        self.assertEqual(pendiente.decision, Gestion.Decision.PENDIENTE)


@override_settings(ALLOWED_HOSTS=["gestion.localhost", "testserver"], GESTION_HOST="gestion.localhost")
class ComunicadorListaUiTests(TestCase):
    def setUp(self):
        self.centro = Centro.objects.get(pk=620)
        self.usuario = User.objects.create_user("comunicador-lista@cmvalparaiso.cl")
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

    def test_comunicador_separa_aceptadas_y_rechazadas(self):
        aceptada = crear_solicitud_base(centro_salud=self.centro).gestion
        aceptada.aceptar(self.usuario, Solicitud.Prioridad.URGENTE)
        rechazada = crear_solicitud_base(centro_salud=self.centro).gestion
        rechazada.rechazar(self.usuario, self.motivo)
        response = self.client.get("/comunicador/", HTTP_HOST="gestion.localhost")
        self.assertContains(response, "Aceptadas - llamar por telefono")
        self.assertContains(response, "Rechazadas - avisar por WhatsApp")
        self.assertLess(
            response.content.decode("utf-8").index("Aceptadas - llamar por telefono"),
            response.content.decode("utf-8").index("Rechazadas - avisar por WhatsApp"),
        )

    def test_comunicador_marca_telefono_invalido_y_deshabilita_whatsapp(self):
        gestion = crear_solicitud_base(centro_salud=self.centro, telefono="123").gestion
        gestion.rechazar(self.usuario, self.motivo)
        response = self.client.get("/comunicador/", HTTP_HOST="gestion.localhost")
        self.assertContains(response, "Telefono invalido para WhatsApp")
        self.assertContains(response, "WhatsApp no disponible")
        self.assertContains(response, "disabled")

    def test_comunicador_muestra_tel_y_cuenta_regresiva_de_rechazo(self):
        gestion = crear_solicitud_base(centro_salud=self.centro, telefono="+56949106239").gestion
        gestion.rechazar(self.usuario, self.motivo)
        Gestion.objects.filter(pk=gestion.pk).update(
            fecha_decision=timezone.now() - timedelta(hours=18)
        )
        response = self.client.get("/comunicador/", HTTP_HOST="gestion.localhost")
        self.assertContains(response, 'href="tel:+56949106239"', html=False)
        self.assertContains(response, "quedan 5 h para avisar")
```

- [ ] **Step 2: Correr tests y confirmar falla inicial**

Run: `.venv/bin/python manage.py test gestion.tests.GestionListasUiTests gestion.tests.ComunicadorListaUiTests -v 2`

Expected: FAIL por contexto faltante y textos ausentes.

- [ ] **Step 3: Agregar contexto de listas en vistas**

En `gestion/views.py`, dentro de `selector_lista`, calcular conteos antes de elegir seccion:

```python
    conteos_selector = {
        "pendientes": Gestion.objects.cola_selector(perfil).count(),
        "decididas": Gestion.objects.decididas_corregibles_selector(perfil).count(),
        "no_aplica": Gestion.objects.no_aplica_selector(perfil).count()
        if mostrar_no_aplica
        else 0,
    }
    mostrar_columna_centro = perfil.centros_permitidos().count() > 1
```

Agregar al contexto de `selector_lista`:

```python
            "conteos_selector": conteos_selector,
            "mostrar_columna_centro": mostrar_columna_centro,
```

En `comunicador_lista`, cambiar el contexto a:

```python
    gestiones = list(Gestion.objects.tabla_comunicador(perfil))
    gestiones_aceptadas = [
        gestion for gestion in gestiones if gestion.decision == Gestion.Decision.ACEPTADA
    ]
    gestiones_rechazadas = [
        gestion for gestion in gestiones if gestion.decision == Gestion.Decision.RECHAZADA
    ]
    return render(
        request,
        "gestion/comunicador_lista.html",
        {
            "perfil": perfil,
            "gestiones": gestiones,
            "gestiones_aceptadas": gestiones_aceptadas,
            "gestiones_rechazadas": gestiones_rechazadas,
            "puede_escribir": puede_escribir_comunicador(perfil),
        },
    )
```

- [ ] **Step 4: Redisenar selector_lista**

Reemplazar `gestion/templates/gestion/selector_lista.html` por:

```html
{% extends "gestion/base.html" %}
{% load gestion_ui %}
{% block title %}Cola del selector{% endblock %}
{% block body_attrs %}data-gestion-page="selector"{% endblock %}
{% block content %}
<section class="page-title">
  <div>
    <h2>Solicitudes del selector</h2>
    <p>Abra un caso para revisar motivo, condiciones y decision.</p>
  </div>
</section>

<nav class="gestion-nav" aria-label="Secciones del selector">
  <a class="tab-link" href="{% url 'gestion:selector_lista' %}">Pendientes <strong>{{ conteos_selector.pendientes }}</strong></a>
  <a class="tab-link" href="{% url 'gestion:selector_lista' %}?seccion=decididas">Decididas corregibles <strong>{{ conteos_selector.decididas }}</strong></a>
  {% if mostrar_no_aplica %}
    <a class="tab-link" href="{% url 'gestion:selector_lista' %}?seccion=no_aplica">No aplica <strong>{{ conteos_selector.no_aplica }}</strong></a>
  {% endif %}
</nav>

<table class="data-table" data-gestion-list>
  <thead>
    <tr>
      <th>Paciente</th>
      {% if mostrar_columna_centro %}<th>Centro</th>{% endif %}
      <th>Prioridad administrativa</th>
      <th>Motivo</th>
      <th>Fecha</th>
      {% if seccion == "decididas" %}<th>Correccion</th>{% endif %}
      <th></th>
    </tr>
  </thead>
  <tbody>
    {% for gestion in gestiones %}
      <tr class="row-link" data-row-id="{{ gestion.pk }}" data-detail-url="{% url 'gestion:selector_detalle' gestion.pk %}?fragmento=1">
        <td data-label="Paciente">{{ gestion.solicitud.nombre }}</td>
        {% if mostrar_columna_centro %}<td data-label="Centro">{{ gestion.solicitud.centro_salud }}</td>{% endif %}
        <td data-label="Prioridad administrativa">
          <span class="priority-badge {{ gestion.solicitud.priorizacion_solicitud|prioridad_css }}">
            {{ gestion.solicitud.get_priorizacion_solicitud_display }}
          </span>
        </td>
        <td data-label="Motivo"><span class="truncate">{{ gestion.solicitud.detalle_motivo|default:gestion.solicitud.motivo }}</span></td>
        <td data-label="Fecha"><time title="{{ gestion.solicitud.date_solicitud }}">{{ gestion.solicitud.date_solicitud|tiempo_relativo }}</time></td>
        {% if seccion == "decididas" %}
          <td data-label="Correccion">
            {% if gestion.decision == "RECHAZADA" %}
              <span class="warning-text">{{ gestion|horas_restantes_rechazo }}</span>
            {% else %}
              Sin intentos registrados
            {% endif %}
          </td>
        {% endif %}
        <td data-label="Abrir"><a href="{% url 'gestion:selector_detalle' gestion.pk %}">Abrir</a></td>
      </tr>
    {% empty %}
      <tr><td colspan="7"><div class="empty-state">No hay solicitudes en esta seccion.</div></td></tr>
    {% endfor %}
  </tbody>
</table>
{% endblock %}
```

- [ ] **Step 5: Redisenar comunicador_lista**

Reemplazar `gestion/templates/gestion/comunicador_lista.html` por:

```html
{% extends "gestion/base.html" %}
{% load gestion_ui %}
{% block title %}Tabla del comunicador{% endblock %}
{% block body_attrs %}data-gestion-page="comunicador"{% endblock %}
{% block content %}
<section class="page-title">
  <div>
    <h2>Tabla del comunicador</h2>
    <p>Priorice llamados pendientes y avisos de rechazo.</p>
  </div>
</section>

<h3>Aceptadas - llamar por telefono</h3>
{% include "gestion/_tabla_comunicador_grupo.html" with gestiones=gestiones_aceptadas grupo="aceptadas" %}

<h3>Rechazadas - avisar por WhatsApp</h3>
{% include "gestion/_tabla_comunicador_grupo.html" with gestiones=gestiones_rechazadas grupo="rechazadas" %}
{% endblock %}
```

Crear `gestion/templates/gestion/_tabla_comunicador_grupo.html`:

```html
{% load gestion_ui %}
<table class="data-table" data-gestion-list>
  <thead>
    <tr>
      <th>Paciente</th>
      <th>Telefono</th>
      <th>Prioridad / motivo</th>
      <th>Estado</th>
      <th>Ultimo intento</th>
      <th>Plazo</th>
      <th></th>
    </tr>
  </thead>
  <tbody>
    {% for gestion in gestiones %}
      <tr class="row-link {% if gestion.intentos_contacto == 0 %}row-pending{% endif %}" data-row-id="{{ gestion.pk }}" data-detail-url="{% url 'gestion:comunicador_detalle' gestion.pk %}?fragmento=1">
        <td data-label="Paciente">{{ gestion.solicitud.nombre }}</td>
        <td data-label="Telefono">
          <a href="tel:{{ gestion.solicitud.telefono }}">{{ gestion.solicitud.telefono }}</a>
          {% if gestion.decision == "RECHAZADA" and not gestion|telefono_whatsapp_valido %}
            <div class="danger-text">Telefono invalido para WhatsApp</div>
          {% endif %}
        </td>
        <td data-label="Prioridad / motivo">
          {% if gestion.decision == "ACEPTADA" %}
            <span class="priority-badge {{ gestion.prioridad_clinica|prioridad_css }}">{{ gestion.get_prioridad_clinica_display }}</span>
          {% else %}
            {{ gestion.motivo_rechazo }}
          {% endif %}
        </td>
        <td data-label="Estado">
          {% if gestion.intentos_contacto == 0 %}
            <strong>Sin intentos</strong>
          {% else %}
            {{ gestion.intentos_contacto }} intento{{ gestion.intentos_contacto|pluralize }} - {{ gestion.get_ultima_accion_contacto_display }}
          {% endif %}
        </td>
        <td data-label="Ultimo intento">{{ gestion.fecha_ultimo_intento|tiempo_relativo }}</td>
        <td data-label="Plazo">{% if gestion.decision == "RECHAZADA" %}{{ gestion|horas_restantes_rechazo }}{% else %}-{% endif %}</td>
        <td data-label="Abrir">
          <a href="{% url 'gestion:comunicador_detalle' gestion.pk %}">Abrir</a>
          {% if gestion.decision == "RECHAZADA" and not gestion|telefono_whatsapp_valido %}
            <button type="button" disabled>WhatsApp no disponible</button>
          {% endif %}
        </td>
      </tr>
    {% empty %}
      <tr><td colspan="7"><div class="empty-state">No hay casos en este grupo.</div></td></tr>
    {% endfor %}
  </tbody>
</table>
```

- [ ] **Step 6: Correr tests de listas**

Run: `.venv/bin/python manage.py test gestion.tests.GestionListasUiTests gestion.tests.ComunicadorListaUiTests -v 2`

Expected: PASS.

- [ ] **Step 7: Correr regresion completa**

Run: `.venv/bin/python manage.py test`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add gestion/views.py gestion/templates/gestion/selector_lista.html gestion/templates/gestion/comunicador_lista.html gestion/templates/gestion/_tabla_comunicador_grupo.html gestion/tests.py
git commit -m "Redisena listas del modulo de seleccion"
```

---

### Task 3: Desglose De Prioridad Administrativa

**Files:**
- Modify: `solicitudes/priorizacion.py`
- Modify: `solicitudes/tests.py`
- Modify: `gestion/templatetags/gestion_ui.py`
- Modify: `gestion/templates/gestion/selector_lista.html`
- Modify: `gestion/templates/gestion/_detalle_selector.html` after Task 4 creates it
- Modify: `gestion/tests.py`

**Interfaces:**
- Produces:
  - `desglosar_prioridad(datos: dict) -> list[dict[str, object]]`.
  - Cada factor: `{"codigo": str, "descripcion": str, "puntaje": int}`.
  - `calcular_prioridad(datos)` sigue retornando `{"puntaje", "clasificacion", "etiqueta"}` sin cambios.
  - Template filter `desglose_prioridad(solicitud: Solicitud) -> list[dict[str, object]]`.

- [ ] **Step 1: Escribir tests de desglose en solicitudes**

Agregar a `solicitudes/tests.py`:

```python
from .priorizacion import calcular_prioridad, desglosar_prioridad


class DesglosePrioridadTests(TestCase):
    def test_desglose_suma_el_mismo_puntaje_que_calcular_prioridad(self):
        casos = [
            {"detalle_motivo": "control", "edad": 40},
            {"detalle_motivo": "dolor pecho", "edad": 68},
            {
                "detalle_motivo": "vomitos con diarrea",
                "edad": 4,
                "credendencial_cuidador_discapacidad": True,
                "Neurodivergente_prais_gestante": True,
            },
        ]
        for datos in casos:
            with self.subTest(datos=datos):
                desglose = desglosar_prioridad(datos)
                self.assertEqual(
                    sum(factor["puntaje"] for factor in desglose),
                    calcular_prioridad(datos)["puntaje"],
                )

    def test_desglose_identifica_factores_concretos(self):
        desglose = desglosar_prioridad(
            {
                "motivo": "dolor pecho",
                "detalle_motivo": "adulto mayor con fiebre",
                "edad": 68,
                "credendencial_cuidador_discapacidad": True,
            }
        )
        self.assertEqual(
            desglose,
            [
                {"codigo": "palabra_urgente", "descripcion": 'palabra clave "dolor pecho"', "puntaje": 4},
                {"codigo": "palabra_moderada", "descripcion": 'palabra clave "fiebre"', "puntaje": 1},
                {"codigo": "edad", "descripcion": "edad 68 anos", "puntaje": 2},
                {"codigo": "credencial", "descripcion": "credencial de cuidador", "puntaje": 2},
            ],
        )
```

- [ ] **Step 2: Correr tests y confirmar falla inicial**

Run: `.venv/bin/python manage.py test solicitudes.tests.DesglosePrioridadTests -v 2`

Expected: FAIL con `ImportError` para `desglosar_prioridad`.

- [ ] **Step 3: Implementar desglose sin cambiar clasificacion**

Reemplazar `solicitudes/priorizacion.py` por:

```python
URGENT_KEYWORDS = [
    "dolor pecho",
    "dificultad respiratoria",
    "falta de aire",
    "convulsion",
    "desmayo",
    "sangrado",
    "embarazo",
    "gestante",
    "suicida",
]

MODERATE_KEYWORDS = [
    "fiebre",
    "dolor intenso",
    "vomitos",
    "diarrea",
    "infeccion",
    "herida",
]


def _contains_any(text, keywords):
    normalized = (text or "").lower()
    return any(keyword in normalized for keyword in keywords)


def _first_keyword(text, keywords):
    normalized = (text or "").lower()
    for keyword in keywords:
        if keyword in normalized:
            return keyword
    return ""


def desglosar_prioridad(datos):
    edad = int(datos.get("edad") or 0)
    clinical_text = f"{datos.get('motivo', '')} {datos.get('detalle_motivo', '')}"
    factores = []

    palabra_urgente = _first_keyword(clinical_text, URGENT_KEYWORDS)
    if palabra_urgente:
        factores.append(
            {
                "codigo": "palabra_urgente",
                "descripcion": f'palabra clave "{palabra_urgente}"',
                "puntaje": 4,
            }
        )

    palabra_moderada = _first_keyword(clinical_text, MODERATE_KEYWORDS)
    if palabra_moderada:
        factores.append(
            {
                "codigo": "palabra_moderada",
                "descripcion": f'palabra clave "{palabra_moderada}"',
                "puntaje": 1,
            }
        )

    if edad <= 5 or edad >= 65:
        factores.append(
            {"codigo": "edad", "descripcion": f"edad {edad} anos", "puntaje": 2}
        )

    if bool(datos.get("credendencial_cuidador_discapacidad")):
        factores.append(
            {
                "codigo": "credencial",
                "descripcion": "credencial de cuidador",
                "puntaje": 2,
            }
        )

    if bool(datos.get("Neurodivergente_prais_gestante")):
        factores.append(
            {
                "codigo": "condicion",
                "descripcion": "condicion declarada",
                "puntaje": 2,
            }
        )

    return factores


def calcular_prioridad(datos):
    puntaje = sum(factor["puntaje"] for factor in desglosar_prioridad(datos))

    if puntaje >= 6:
        clasificacion = "URGENTE"
        etiqueta = "Urgente"
    elif puntaje >= 4:
        clasificacion = "ALTA"
        etiqueta = "Alta"
    elif puntaje >= 2:
        clasificacion = "MEDIA"
        etiqueta = "Media"
    else:
        clasificacion = "BAJA"
        etiqueta = "Baja"

    return {
        "puntaje": puntaje,
        "clasificacion": clasificacion,
        "etiqueta": etiqueta,
    }
```

- [ ] **Step 4: Agregar filtro de template para Solicitud persistida**

En `gestion/templatetags/gestion_ui.py`, agregar imports:

```python
from solicitudes.priorizacion import desglosar_prioridad
```

Agregar al final:

```python
@register.filter
def desglose_prioridad(solicitud):
    return desglosar_prioridad(
        {
            "motivo": solicitud.motivo,
            "detalle_motivo": solicitud.detalle_motivo,
            "edad": solicitud.edad,
            "credendencial_cuidador_discapacidad": solicitud.credendencial_cuidador_discapacidad,
            "Neurodivergente_prais_gestante": solicitud.Neurodivergente_prais_gestante,
        }
    )
```

- [ ] **Step 5: Escribir test de presencia accesible en lista**

Agregar a `GestionListasUiTests`:

```python
    def test_prioridad_en_lista_expone_desglose_en_hover_y_foco(self):
        crear_solicitud_base(
            centro_salud=self.centro,
            motivo="dolor pecho",
            detalle_motivo="adulto mayor",
            edad=68,
            priorizacion_solicitud=Solicitud.Prioridad.URGENTE,
            puntaje_prioridad=6,
        ).gestion
        response = self.client.get("/selector/", HTTP_HOST="gestion.localhost")
        self.assertContains(response, "prioridad-detalle")
        self.assertContains(response, 'tabindex="0"', html=False)
        self.assertContains(response, 'palabra clave "dolor pecho"')
        self.assertContains(response, "edad 68 anos")
```

- [ ] **Step 6: Renderizar tooltip accesible en `selector_lista.html`**

Reemplazar el contenido del `<td data-label="Prioridad administrativa">` por:

```html
<span class="priority-badge {{ gestion.solicitud.priorizacion_solicitud|prioridad_css }}" tabindex="0" aria-describedby="prioridad-{{ gestion.pk }}">
  {{ gestion.solicitud.get_priorizacion_solicitud_display }} ({{ gestion.solicitud.puntaje_prioridad }} pts)
</span>
<span id="prioridad-{{ gestion.pk }}" class="prioridad-detalle" role="tooltip">
  {% for factor in gestion.solicitud|desglose_prioridad %}
    <span>{{ factor.descripcion }} +{{ factor.puntaje }}</span>
  {% empty %}
    <span>sin factores de prioridad +0</span>
  {% endfor %}
</span>
```

Agregar a `static/css/gestion.css`:

```css
.prioridad-detalle {
  position: absolute;
  z-index: 20;
  min-width: 220px;
  max-width: 320px;
  padding: var(--space-2);
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface);
  box-shadow: var(--shadow);
  color: var(--text);
  display: none;
}
.prioridad-detalle span { display: block; margin: 2px 0; }
.priority-badge:hover + .prioridad-detalle,
.priority-badge:focus + .prioridad-detalle { display: block; }
```

- [ ] **Step 7: Correr tests de desglose y UI**

Run: `.venv/bin/python manage.py test solicitudes.tests.DesglosePrioridadTests gestion.tests.GestionListasUiTests -v 2`

Expected: PASS.

- [ ] **Step 8: Correr regresion completa**

Run: `.venv/bin/python manage.py test`

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add solicitudes/priorizacion.py solicitudes/tests.py gestion/templatetags/gestion_ui.py gestion/templates/gestion/selector_lista.html static/css/gestion.css gestion/tests.py
git commit -m "Agrega desglose de prioridad administrativa"
```

---

### Task 4: Parcial Y Flujo Modal Del Selector

**Files:**
- Create: `gestion/templates/gestion/_detalle_selector.html`
- Modify: `gestion/templates/gestion/selector_detalle.html`
- Modify: `gestion/templates/gestion/selector_lista.html`
- Modify: `gestion/views.py`
- Modify: `static/css/gestion.css`
- Modify: `static/js/gestion.js`
- Modify: `gestion/tests.py`

**Interfaces:**
- Consumes: `DecisionSelectorForm`, `Gestion.objects.cola_selector(perfil)`, `gestion_alcanzable_o_404(perfil, pk)`.
- Produces:
  - `selector_detalle(...?fragmento=1)` responde solo `_detalle_selector.html`.
  - POST selector con `fragmento=1` y exito responde el siguiente parcial.
  - Si no queda siguiente caso responde `gestion/_cola_selector_vacia.html`.
  - El parcial incluye `data-fragment-kind="selector-detail"` o `data-fragment-kind="selector-empty"`.

- [ ] **Step 1: Escribir tests de fragmentos del selector**

Agregar a `SelectorViewsTests`:

```python
    def test_fragmento_selector_no_incluye_layout_y_respeta_permiso(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        response = self.client.get(
            f"/selector/{gestion.pk}/?fragmento=1",
            HTTP_HOST="gestion.localhost",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-fragment-kind="selector-detail"', html=False)
        self.assertNotContains(response, "<html", html=False)
        self.assertContains(response, "Guardar decision")

    def test_fragmento_selector_solo_lectura_no_muestra_controles(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        self.perfil.rol = PerfilUsuario.Rol.ADMIN
        self.perfil.save(update_fields=["rol"])
        response = self.client.get(
            f"/selector/{gestion.pk}/?fragmento=1",
            HTTP_HOST="gestion.localhost",
        )
        self.assertContains(response, "Vista de solo lectura")
        self.assertNotContains(response, "Aceptar urgente")

    def test_post_fragmento_selector_devuelve_siguiente_caso(self):
        primero = crear_solicitud_base(
            centro_salud=self.centro,
            priorizacion_solicitud=Solicitud.Prioridad.URGENTE,
            detalle_motivo="primer caso",
        ).gestion
        segundo = crear_solicitud_base(
            centro_salud=self.centro,
            priorizacion_solicitud=Solicitud.Prioridad.BAJA,
            detalle_motivo="segundo caso",
        ).gestion
        response = self.client.post(
            f"/selector/{primero.pk}/?fragmento=1",
            {"decision": Gestion.Decision.ACEPTADA, "prioridad_clinica": Solicitud.Prioridad.ALTA},
            HTTP_HOST="gestion.localhost",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-fragment-kind="selector-detail"', html=False)
        self.assertContains(response, f'data-current-row-id="{segundo.pk}"', html=False)
        self.assertContains(response, "Aceptada como Alta")

    def test_post_fragmento_selector_ultimo_devuelve_cola_vacia(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        response = self.client.post(
            f"/selector/{gestion.pk}/?fragmento=1",
            {"decision": Gestion.Decision.NO_APLICA},
            HTTP_HOST="gestion.localhost",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-fragment-kind="selector-empty"', html=False)
        self.assertContains(response, "No quedan casos pendientes")

    def test_post_fragmento_selector_con_error_devuelve_mismo_parcial(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        response = self.client.post(
            f"/selector/{gestion.pk}/?fragmento=1",
            {"decision": Gestion.Decision.ACEPTADA},
            HTTP_HOST="gestion.localhost",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-current-row-id="%s"' % gestion.pk, html=False)
        self.assertContains(response, "Debe indicar prioridad clinica")
```

- [ ] **Step 2: Correr tests y confirmar falla inicial**

Run: `.venv/bin/python manage.py test gestion.tests.SelectorViewsTests -v 2`

Expected: FAIL porque `fragmento=1` aun renderiza layout completo y POST redirige.

- [ ] **Step 3: Crear parciales del selector**

Crear `gestion/templates/gestion/_cola_selector_vacia.html`:

```html
<section class="modal-panel" data-fragment-kind="selector-empty">
  <header class="modal-header">
    <h2>No quedan casos pendientes</h2>
    <p>La cola del selector esta vacia para su alcance actual.</p>
  </header>
  <footer class="modal-actions">
    <button type="button" data-dialog-close>Cerrar</button>
  </footer>
</section>
```

Crear `gestion/templates/gestion/_detalle_selector.html`:

```html
{% load gestion_ui %}
<article class="modal-panel" data-fragment-kind="selector-detail" data-current-row-id="{{ gestion.pk }}">
  {% if mensaje_resultado %}<p class="status-badge">{{ mensaje_resultado }}</p>{% endif %}
  <header class="modal-header">
    <div>
      <h2>{{ gestion.solicitud.nombre }}</h2>
      <p>{{ gestion.solicitud.rut }} - {{ gestion.solicitud.telefono }} - {{ gestion.solicitud.centro_salud }}</p>
    </div>
    <button type="button" class="icon-button" data-dialog-close aria-label="Cerrar">x</button>
  </header>
  <div class="modal-body">
    <section class="case-summary">
      <h3>Motivo de consulta</h3>
      <p><strong>{{ gestion.solicitud.motivo }}</strong></p>
      <p>{{ gestion.solicitud.detalle_motivo }}</p>
    </section>
    <dl class="detail-grid">
      <dt>Edad</dt><dd>{{ gestion.solicitud.edad }}</dd>
      <dt>Sexo</dt><dd>{{ gestion.solicitud.get_sexo_display }}</dd>
      <dt>Prioridad administrativa</dt>
      <dd>
        <span class="priority-badge {{ gestion.solicitud.priorizacion_solicitud|prioridad_css }}">
          {{ gestion.solicitud.get_priorizacion_solicitud_display }} ({{ gestion.solicitud.puntaje_prioridad }} pts)
        </span>
      </dd>
      <dt>Decision actual</dt><dd>{{ gestion.get_decision_display }}</dd>
      <dt>Decidido por</dt><dd>{% if gestion.decidido_por %}{{ gestion.decidido_por.email|default:gestion.decidido_por.username }}{% else %}Sin decision{% endif %}</dd>
      <dt>Fecha de decision</dt><dd>{{ gestion.fecha_decision|default:"Sin decision" }}</dd>
    </dl>
    <section>
      <h3>Condiciones declaradas</h3>
      {% if gestion.solicitud.Neurodivergente_prais_gestante %}
        <p>{{ gestion.solicitud.get_Neurodivergente_prais_gestante_tipo_display }}{% if gestion.solicitud.Neurodivergente_prais_gestante_otro %} - {{ gestion.solicitud.Neurodivergente_prais_gestante_otro }}{% endif %}</p>
      {% else %}
        <p>Sin condiciones declaradas</p>
      {% endif %}
      {% if gestion.solicitud.credendencial_cuidador_discapacidad %}
        <p>Credencial declarada. {% if gestion.solicitud.credencial_cuidador_discapacidad_foto %}Foto adjunta.{% else %}Sin foto adjunta.{% endif %}</p>
        {% if foto_credencial_data_url %}
          <img class="credential-photo" src="{{ foto_credencial_data_url }}" alt="Foto de credencial de cuidador">
        {% endif %}
      {% endif %}
    </section>
    <section>
      <h3>Desglose de prioridad administrativa</h3>
      <ul class="priority-breakdown">
        {% for factor in gestion.solicitud|desglose_prioridad %}
          <li><span>{{ factor.descripcion }}</span><strong>+{{ factor.puntaje }}</strong></li>
        {% empty %}
          <li><span>sin factores de prioridad</span><strong>+0</strong></li>
        {% endfor %}
      </ul>
    </section>
  </div>
  <footer class="modal-actions">
    {% if form.non_field_errors %}{{ form.non_field_errors }}{% endif %}
    {% if puede_escribir %}
      <form method="post" action="{% url 'gestion:selector_detalle' gestion.pk %}?fragmento=1" data-fragment-form>
        {% csrf_token %}
        {% for prioridad, etiqueta in form.fields.prioridad_clinica.choices %}
          {% if prioridad %}
            <button type="submit" name="decision" value="ACEPTADA" data-extra-name="prioridad_clinica" data-extra-value="{{ prioridad }}">Aceptar {{ etiqueta }}</button>
          {% endif %}
        {% endfor %}
      </form>
      <details class="reject-box">
        <summary>Rechazar</summary>
        <form method="post" action="{% url 'gestion:selector_detalle' gestion.pk %}?fragmento=1" data-fragment-form>
          {% csrf_token %}
          <input type="hidden" name="decision" value="RECHAZADA">
          {{ form.motivo_rechazo }}
          <button type="submit">Confirmar rechazo</button>
          {{ form.motivo_rechazo.errors }}
        </form>
      </details>
      <form method="post" action="{% url 'gestion:selector_detalle' gestion.pk %}?fragmento=1" data-fragment-form>
        {% csrf_token %}
        <button type="submit" name="decision" value="NO_APLICA">No aplica</button>
      </form>
      {{ form.prioridad_clinica.errors }}
    {% else %}
      <div class="read-only-trace">
        <strong>Vista de solo lectura</strong>
        <p>Decision: {{ gestion.get_decision_display }}. Intentos: {{ gestion.intentos_contacto }}. Ultima accion: {{ gestion.get_ultima_accion_contacto_display|default:"Sin contacto" }}.</p>
      </div>
    {% endif %}
  </footer>
</article>
```

- [ ] **Step 4: Usar parcial en pagina completa**

Reemplazar `gestion/templates/gestion/selector_detalle.html` por:

```html
{% extends "gestion/base.html" %}
{% block title %}Solicitud {{ gestion.solicitud_id }}{% endblock %}
{% block content %}
  {% include "gestion/_detalle_selector.html" %}
{% endblock %}
```

- [ ] **Step 5: Implementar `fragmento=1` en `selector_detalle`**

En `gestion/views.py`, dentro de `selector_detalle`, introducir:

```python
    es_fragmento = request.GET.get("fragmento") == "1"
    template = "gestion/_detalle_selector.html" if es_fragmento else "gestion/selector_detalle.html"
```

Reemplazar el bloque de exito POST por:

```python
                form.guardar(gestion, request.user)
                mensaje_resultado = {
                    Gestion.Decision.ACEPTADA: f"Aceptada como {gestion.get_prioridad_clinica_display()}",
                    Gestion.Decision.RECHAZADA: "Rechazada",
                    Gestion.Decision.NO_APLICA: "Marcada como no aplica",
                }.get(gestion.decision, "Decision registrada")
                if es_fragmento:
                    siguiente = Gestion.objects.cola_selector(perfil).first()
                    if siguiente is None:
                        return render(request, "gestion/_cola_selector_vacia.html")
                    gestion = gestion_alcanzable_o_404(perfil, siguiente.pk)
                    form = DecisionSelectorForm()
                    foto_credencial_data_url = _foto_credencial_data_url(gestion)
                    return render(
                        request,
                        "gestion/_detalle_selector.html",
                        {
                            "perfil": perfil,
                            "gestion": gestion,
                            "form": form,
                            "puede_escribir": puede_escribir,
                            "foto_credencial_data_url": foto_credencial_data_url,
                            "mensaje_resultado": mensaje_resultado,
                        },
                    )
                messages.success(request, "Decision registrada.")
                return redirect("gestion:selector_lista")
```

En el `return render` final, usar `template` y agregar `mensaje_resultado: ""`.

- [ ] **Step 6: Extender CSS modal**

Agregar a `static/css/gestion.css`:

```css
.gestion-dialog {
  width: min(960px, calc(100vw - 32px));
  max-height: calc(100vh - 32px);
  padding: 0;
  border: 0;
  border-radius: 8px;
  box-shadow: var(--shadow);
}
.gestion-dialog::backdrop { background: rgba(15, 23, 42, 0.42); }
.modal-panel { max-height: calc(100vh - 32px); display: grid; grid-template-rows: auto minmax(0, 1fr) auto; background: var(--surface); }
.modal-header, .modal-actions { padding: var(--space-4); border-bottom: 1px solid var(--line); display: flex; gap: var(--space-3); align-items: center; justify-content: space-between; }
.modal-actions { border-top: 1px solid var(--line); border-bottom: 0; position: sticky; bottom: 0; background: var(--surface); flex-wrap: wrap; }
.modal-body { padding: var(--space-4); overflow: auto; display: grid; gap: var(--space-4); }
.detail-grid { display: grid; grid-template-columns: 12rem minmax(0, 1fr); gap: var(--space-2) var(--space-4); }
.detail-grid dt { color: var(--muted); font-weight: 700; }
.detail-grid dd { margin: 0; }
.credential-photo { display: block; max-width: 100%; max-height: 24rem; object-fit: contain; border: 1px solid var(--line); }
.priority-breakdown { max-width: 34rem; margin: 0; padding: 0; list-style: none; }
.priority-breakdown li { display: flex; justify-content: space-between; gap: var(--space-3); padding: 6px 0; border-bottom: 1px solid var(--line); }
.icon-button { width: 36px; height: 36px; border: 1px solid var(--line); border-radius: 8px; background: var(--surface); }
@media (max-width: 900px) {
  .gestion-dialog { width: 100vw; height: 100vh; max-height: 100vh; border-radius: 0; }
  .modal-panel { max-height: 100vh; }
  .detail-grid { grid-template-columns: 1fr; }
}
```

- [ ] **Step 7: Implementar JS de modal**

Reemplazar `static/js/gestion.js` por:

```javascript
(function () {
  "use strict";

  document.documentElement.classList.add("js");

  const dialog = document.createElement("dialog");
  dialog.className = "gestion-dialog";
  dialog.setAttribute("aria-label", "Detalle de solicitud");
  document.body.appendChild(dialog);

  let lastTrigger = null;

  function closeDialog() {
    dialog.close();
    dialog.innerHTML = "";
    if (lastTrigger) lastTrigger.focus();
  }

  function removeResolvedRow(fragmentRoot) {
    const currentId = fragmentRoot.getAttribute("data-current-row-id");
    if (!currentId) return;
    const row = document.querySelector(`[data-row-id="${currentId}"]`);
    if (row && fragmentRoot.querySelector(".status-badge")) row.remove();
  }

  async function loadFragment(url) {
    const response = await fetch(url, { headers: { "X-Requested-With": "fetch" } });
    if (!response.ok) throw new Error("No se pudo cargar el detalle.");
    dialog.innerHTML = await response.text();
    bindDialog();
    if (!dialog.open) dialog.showModal();
    const focusTarget = dialog.querySelector("button, a, input, select, textarea");
    if (focusTarget) focusTarget.focus();
  }

  async function submitFragmentForm(form, submitter) {
    const data = new FormData(form);
    if (submitter && submitter.name) data.set(submitter.name, submitter.value);
    if (submitter && submitter.dataset.extraName) {
      data.set(submitter.dataset.extraName, submitter.dataset.extraValue);
    }
    const action = submitter && submitter.formAction ? submitter.formAction : form.action;
    const response = await fetch(action, {
      method: "POST",
      body: data,
      headers: { "X-Requested-With": "fetch" },
    });
    if (!response.ok) throw new Error("No se pudo guardar.");
    const previous = dialog.querySelector("[data-current-row-id]");
    dialog.innerHTML = await response.text();
    if (previous) removeResolvedRow(previous);
    bindDialog();
  }

  function bindDialog() {
    dialog.querySelectorAll("[data-dialog-close]").forEach((button) => {
      button.addEventListener("click", closeDialog);
    });
    dialog.querySelectorAll("[data-fragment-form]").forEach((form) => {
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        submitFragmentForm(form, event.submitter).catch(() => form.submit());
      });
    });
  }

  document.addEventListener("click", (event) => {
    const close = event.target.closest("[data-dialog-close]");
    if (close) {
      closeDialog();
      return;
    }
    const row = event.target.closest("[data-detail-url]");
    if (!row || event.target.closest("a, button, input, select, textarea")) return;
    event.preventDefault();
    lastTrigger = row;
    loadFragment(row.dataset.detailUrl).catch(() => {
      window.location.href = row.querySelector("a[href]").href;
    });
  });

  dialog.addEventListener("close", () => {
    if (lastTrigger) lastTrigger.focus();
  });
})();
```

- [ ] **Step 8: Correr tests del selector**

Run: `.venv/bin/python manage.py test gestion.tests.SelectorViewsTests -v 2`

Expected: PASS.

- [ ] **Step 9: Correr regresion completa**

Run: `.venv/bin/python manage.py test`

Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add gestion/views.py gestion/templates/gestion/_detalle_selector.html gestion/templates/gestion/_cola_selector_vacia.html gestion/templates/gestion/selector_detalle.html static/css/gestion.css static/js/gestion.js gestion/tests.py
git commit -m "Agrega modal progresivo del selector"
```

---

### Task 5: Parcial Y Modal Del Comunicador

**Files:**
- Create: `gestion/templates/gestion/_detalle_comunicador.html`
- Create: `gestion/templates/gestion/_confirmacion_comunicador.html`
- Modify: `gestion/templates/gestion/comunicador_detalle.html`
- Modify: `gestion/views.py`
- Modify: `static/css/gestion.css`
- Modify: `static/js/gestion.js`
- Modify: `gestion/tests.py`

**Interfaces:**
- Consumes: `AccionComunicadorForm`, `WhatsappComunicadorForm`, `_gestion_para_post_comunicador_o_404`, `Gestion.url_whatsapp()`.
- Produces:
  - `comunicador_detalle(...?fragmento=1)` responde solo `_detalle_comunicador.html`.
  - POST comunicador con `fragmento=1` responde `gestion/_confirmacion_comunicador.html`.
  - WhatsApp sigue siendo POST y redireccion externa en pagina completa; en fragmento sigue devolviendo redirect porque debe abrir WhatsApp.

- [ ] **Step 1: Escribir tests de fragmentos del comunicador**

Agregar a `ComunicadorViewsTests`:

```python
    def test_fragmento_comunicador_no_incluye_layout_y_muestra_historial(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)
        gestion.registrar_no_contesta(self.usuario, token_contacto="primer-token")
        response = self.client.get(
            f"/comunicador/{gestion.pk}/?fragmento=1",
            HTTP_HOST="gestion.localhost",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-fragment-kind="comunicador-detail"', html=False)
        self.assertNotContains(response, "<html", html=False)
        self.assertContains(response, "Historial de contacto")
        self.assertContains(response, "1 intento")

    def test_fragmento_comunicador_muestra_vista_previa_whatsapp(self):
        gestion = crear_solicitud_base(
            centro_salud=self.centro,
            nombre="Ana Perez",
        ).gestion
        gestion.rechazar(self.usuario, self.motivo)
        response = self.client.get(
            f"/comunicador/{gestion.pk}/?fragmento=1",
            HTTP_HOST="gestion.localhost",
        )
        self.assertContains(response, "Vista previa de WhatsApp")
        self.assertContains(response, "Ana Perez")

    def test_fragmento_comunicador_invalido_deshabilita_whatsapp(self):
        gestion = crear_solicitud_base(centro_salud=self.centro, telefono="123").gestion
        gestion.rechazar(self.usuario, self.motivo)
        response = self.client.get(
            f"/comunicador/{gestion.pk}/?fragmento=1",
            HTTP_HOST="gestion.localhost",
        )
        self.assertContains(response, "Telefono invalido para WhatsApp")
        self.assertContains(response, "disabled")

    def test_post_fragmento_comunicador_devuelve_confirmacion(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)
        response = self.client.get(
            f"/comunicador/{gestion.pk}/?fragmento=1",
            HTTP_HOST="gestion.localhost",
        )
        token = response.context["form"]["token_contacto"].value()
        response = self.client.post(
            f"/comunicador/{gestion.pk}/?fragmento=1",
            {"accion": "NO_CONTESTA", "token_contacto": token},
            HTTP_HOST="gestion.localhost",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-fragment-kind="comunicador-confirmation"', html=False)
        self.assertContains(response, "Contacto registrado")
```

- [ ] **Step 2: Correr tests y confirmar falla inicial**

Run: `.venv/bin/python manage.py test gestion.tests.ComunicadorViewsTests -v 2`

Expected: FAIL porque el detalle aun renderiza pagina completa y POST redirige.

- [ ] **Step 3: Crear parciales del comunicador**

Crear `gestion/templates/gestion/_confirmacion_comunicador.html`:

```html
<section class="modal-panel" data-fragment-kind="comunicador-confirmation">
  <header class="modal-header">
    <h2>Contacto registrado</h2>
    <button type="button" class="icon-button" data-dialog-close aria-label="Cerrar">x</button>
  </header>
  <div class="modal-body">
    <p>{{ mensaje_resultado }}</p>
  </div>
  <footer class="modal-actions">
    <button type="button" data-dialog-close>Cerrar</button>
  </footer>
</section>
```

Crear `gestion/templates/gestion/_detalle_comunicador.html`:

```html
{% load gestion_ui %}
<article class="modal-panel" data-fragment-kind="comunicador-detail" data-current-row-id="{{ gestion.pk }}">
  <header class="modal-header">
    <div>
      <h2>{{ gestion.solicitud.nombre }}</h2>
      <p><a href="tel:{{ gestion.solicitud.telefono }}">{{ gestion.solicitud.telefono }}</a> - {{ gestion.solicitud.centro_salud }}</p>
    </div>
    <button type="button" class="icon-button" data-dialog-close aria-label="Cerrar">x</button>
  </header>
  <div class="modal-body">
    <section>
      <h3>Solicitud</h3>
      <p>{{ gestion.solicitud.motivo }} - {{ gestion.solicitud.detalle_motivo }}</p>
      <p>Decision: {{ gestion.get_decision_display }}</p>
      {% if gestion.decision == "ACEPTADA" %}
        <p>Prioridad clinica: {{ gestion.get_prioridad_clinica_display }}</p>
      {% else %}
        <p>Motivo de rechazo: {{ gestion.motivo_rechazo }}</p>
        <p class="warning-text">{{ gestion|horas_restantes_rechazo }}</p>
      {% endif %}
    </section>
    <section>
      <h3>Historial de contacto</h3>
      <dl class="detail-grid">
        <dt>Intentos</dt><dd>{{ gestion.intentos_contacto }} intento{{ gestion.intentos_contacto|pluralize }}</dd>
        <dt>Ultimo intento</dt><dd>{{ gestion.fecha_ultimo_intento|default:"Sin intentos" }}</dd>
        <dt>Contactado por</dt><dd>{% if gestion.contactado_por %}{{ gestion.contactado_por.email|default:gestion.contactado_por.username }}{% else %}Sin contacto{% endif %}</dd>
        <dt>Ultima accion</dt><dd>{{ gestion.get_ultima_accion_contacto_display|default:"Sin contacto" }}</dd>
        <dt>Cierre</dt><dd>{{ gestion.get_motivo_cierre_display|default:"Abierto" }}</dd>
      </dl>
    </section>
    <section>
      <h3>Vista previa de WhatsApp</h3>
      {% if gestion|telefono_whatsapp_valido %}
        <p class="message-preview">{{ gestion|mensaje_whatsapp_previo }}</p>
      {% else %}
        <p class="danger-text">Telefono invalido para WhatsApp</p>
      {% endif %}
    </section>
  </div>
  <footer class="modal-actions">
    {% if form.non_field_errors %}{{ form.non_field_errors }}{% endif %}
    {% if puede_escribir %}
      <form method="post" action="{% url 'gestion:comunicador_detalle' gestion.pk %}?fragmento=1" data-fragment-form>
        {% csrf_token %}
        {{ form.token_contacto }}
        <button type="submit" name="accion" value="AGENDADA">Agendada</button>
        {{ form.fecha_hora_citacion }}
        <button type="submit" name="accion" value="NO_ACEPTA">El paciente no acepta</button>
        <button type="submit" name="accion" value="NO_CONTESTA">No contesta</button>
        <button type="submit" name="accion" value="NO_CONTACTADO">No se logro contactar</button>
      </form>
      <form method="post" action="{% url 'gestion:whatsapp' gestion.pk %}" data-whatsapp-form>
        {% csrf_token %}
        {{ form_whatsapp.token_contacto }}
        <button type="submit" {% if not gestion|telefono_whatsapp_valido %}disabled{% endif %}>Abrir WhatsApp y registrar intento</button>
      </form>
    {% else %}
      <div class="read-only-trace">
        <strong>Vista de solo lectura</strong>
        <p>Decision: {{ gestion.get_decision_display }}. Intentos: {{ gestion.intentos_contacto }}. Ultima accion: {{ gestion.get_ultima_accion_contacto_display|default:"Sin contacto" }}.</p>
      </div>
    {% endif %}
  </footer>
</article>
```

- [ ] **Step 4: Usar parcial en pagina completa**

Reemplazar `gestion/templates/gestion/comunicador_detalle.html` por:

```html
{% extends "gestion/base.html" %}
{% block title %}Contacto {{ gestion.solicitud_id }}{% endblock %}
{% block content %}
  {% include "gestion/_detalle_comunicador.html" %}
{% endblock %}
```

- [ ] **Step 5: Implementar `fragmento=1` en comunicador_detalle**

En `gestion/views.py`, dentro de `comunicador_detalle`, agregar:

```python
    es_fragmento = request.GET.get("fragmento") == "1"
    template = "gestion/_detalle_comunicador.html" if es_fragmento else "gestion/comunicador_detalle.html"
```

Reemplazar el bloque de exito POST por:

```python
                form.guardar(gestion, request.user)
                _advertir_cierre_automatico(request, gestion)
                if es_fragmento:
                    return render(
                        request,
                        "gestion/_confirmacion_comunicador.html",
                        {
                            "perfil": perfil,
                            "gestion": gestion,
                            "mensaje_resultado": "Contacto registrado.",
                        },
                    )
                messages.success(request, "Contacto registrado.")
                return redirect("gestion:comunicador_lista")
```

En el `return render` final, usar `template`.

- [ ] **Step 6: Ajustar JS para confirmacion del comunicador**

En `static/js/gestion.js`, dentro de `submitFragmentForm`, despues de `dialog.innerHTML = await response.text();`, agregar:

```javascript
    const confirmation = dialog.querySelector('[data-fragment-kind="comunicador-confirmation"]');
    if (confirmation && previous) removeResolvedRow(previous);
```

Mantener `bindDialog();` al final.

- [ ] **Step 7: Correr tests del comunicador**

Run: `.venv/bin/python manage.py test gestion.tests.ComunicadorViewsTests -v 2`

Expected: PASS.

- [ ] **Step 8: Correr regresion completa**

Run: `.venv/bin/python manage.py test`

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add gestion/views.py gestion/templates/gestion/_detalle_comunicador.html gestion/templates/gestion/_confirmacion_comunicador.html gestion/templates/gestion/comunicador_detalle.html static/js/gestion.js gestion/tests.py
git commit -m "Agrega modal progresivo del comunicador"
```

---

### Task 6: Pulido Visual, Responsive Y Verificacion Manual

**Files:**
- Modify: `static/css/gestion.css`
- Modify: `static/js/gestion.js`
- Modify: `gestion/tests.py`

**Interfaces:**
- Consumes: tareas 1-5.
- Produces: comportamiento responsive estable, botones con estados, foco que vuelve a la fila, y checklist manual documentado en el commit.

- [ ] **Step 1: Agregar tests de accesibilidad basica de markup**

Agregar a `gestion/tests.py`:

```python
@override_settings(ALLOWED_HOSTS=["gestion.localhost", "testserver"], GESTION_HOST="gestion.localhost")
class GestionAccesibilidadMarkupTests(TestCase):
    def setUp(self):
        self.centro = Centro.objects.get(pk=620)
        self.usuario = User.objects.create_user("ui-a11y@cmvalparaiso.cl")
        self.perfil = PerfilUsuario.objects.create(
            usuario=self.usuario,
            rol=PerfilUsuario.Rol.FULL,
            centro=self.centro,
        )
        self.client.force_login(self.usuario)

    def test_filas_clickeables_conservan_enlace_real(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        response = self.client.get("/selector/", HTTP_HOST="gestion.localhost")
        self.assertContains(response, f'href="/selector/{gestion.pk}/"', html=False)
        self.assertContains(response, f'data-detail-url="/selector/{gestion.pk}/?fragmento=1"', html=False)

    def test_botones_de_modal_tienen_texto_de_accion(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        response = self.client.get(
            f"/selector/{gestion.pk}/?fragmento=1",
            HTTP_HOST="gestion.localhost",
        )
        self.assertContains(response, "Aceptar Urgente")
        self.assertContains(response, "Aceptar Alta")
        self.assertContains(response, "Aceptar Media")
        self.assertContains(response, "Aceptar Baja")
        self.assertContains(response, "Confirmar rechazo")
        self.assertContains(response, "No aplica")
```

- [ ] **Step 2: Correr tests y confirmar estado**

Run: `.venv/bin/python manage.py test gestion.tests.GestionAccesibilidadMarkupTests -v 2`

Expected: PASS si las tareas anteriores quedaron consistentes; si falla, corregir los textos exactos de botones, no relajar el test.

- [ ] **Step 3: Completar CSS responsive y estados**

Agregar a `static/css/gestion.css`:

```css
button,
.button {
  min-height: 36px;
  padding: 0 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface);
  color: var(--text);
  font-weight: 700;
}
button:hover,
button:focus,
.button:hover,
.button:focus {
  border-color: var(--primary);
  outline: 3px solid rgba(25, 118, 210, 0.16);
}
button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}
.row-pending td:first-child { border-left: 4px solid var(--primary); }
.message-preview {
  padding: var(--space-3);
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #f8fafc;
  line-height: 1.5;
}
.reject-box {
  padding: 0 var(--space-2);
}
.reject-box summary {
  min-height: 36px;
  display: inline-flex;
  align-items: center;
  font-weight: 800;
  cursor: pointer;
}
.read-only-trace {
  width: 100%;
  padding: var(--space-3);
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #f8fafc;
}
@media (max-width: 900px) {
  .modal-actions {
    align-items: stretch;
  }
  .modal-actions form {
    width: 100%;
    display: grid;
    gap: var(--space-2);
  }
  .modal-actions button,
  .modal-actions select,
  .modal-actions input {
    width: 100%;
  }
}
```

- [ ] **Step 4: Revisar JS contra doble envio de fragmentos**

En `static/js/gestion.js`, modificar `submitFragmentForm` para deshabilitar botones durante el envio:

```javascript
  async function submitFragmentForm(form, submitter) {
    const buttons = Array.from(form.querySelectorAll("button"));
    buttons.forEach((button) => { button.disabled = true; });
    const data = new FormData(form);
    if (submitter && submitter.name) data.set(submitter.name, submitter.value);
    if (submitter && submitter.dataset.extraName) {
      data.set(submitter.dataset.extraName, submitter.dataset.extraValue);
    }
    const action = submitter && submitter.formAction ? submitter.formAction : form.action;
    const response = await fetch(action, {
      method: "POST",
      body: data,
      headers: { "X-Requested-With": "fetch" },
    });
    if (!response.ok) {
      buttons.forEach((button) => { button.disabled = false; });
      throw new Error("No se pudo guardar.");
    }
    const previous = dialog.querySelector("[data-current-row-id]");
    dialog.innerHTML = await response.text();
    if (previous) removeResolvedRow(previous);
    bindDialog();
  }
```

- [ ] **Step 5: Correr verificaciones automatizadas finales**

Run: `.venv/bin/python manage.py makemigrations --check --dry-run`

Expected: `No changes detected`.

Run: `.venv/bin/python manage.py check`

Expected: `System check identified no issues`.

Run: `.venv/bin/python manage.py test`

Expected: PASS.

- [ ] **Step 6: Verificacion manual local 1366x768**

Con MySQL arriba:

```bash
docker compose up -d
.venv/bin/python manage.py runserver
```

Abrir con `GESTION_HOST` configurado segun `.env`:

- Selector `/selector/`: la tabla debe mostrar motivo truncado, prioridad con texto, tabs con conteo, sin columnas `Decision` ni `Centro` para rol de un centro.
- Selector modal: abrir una fila debe mostrar detalle sin navegacion, pie fijo, foto solo si existe, desglose de prioridad visible y acciones de aceptar/rechazar/no aplica.
- Selector POST: aceptar un caso debe quitar la fila de la lista y cargar el siguiente; en el ultimo debe mostrar cola vacia.
- Selector solo lectura (`ADMIN` o supervisor): debe mostrar rastro de decision y ningun control de accion.
- Comunicador `/comunicador/`: aceptadas arriba, rechazadas abajo, telefono con `tel:`, intentos visibles y telefono invalido marcado antes de abrir detalle.
- Comunicador modal: debe mostrar historial, vista previa WhatsApp, acciones fijas y no auto-avanzar tras registrar contacto.
- Responsive bajo 900px: tablas se ven como tarjetas y dialog ocupa pantalla completa.
- Teclado: abrir modal, tabular, cerrar con Esc; el foco debe volver a la fila que abrio el modal.

- [ ] **Step 7: Commit**

```bash
git add static/css/gestion.css static/js/gestion.js gestion/tests.py
git commit -m "Pulir experiencia responsive de gestion"
```

---

## Self-Review

**1. Spec coverage**

- Fundacion visual, `gestion.css`, encabezado, navegacion, identidad: Task 1.
- Redisenio de listas selector y comunicador: Task 2.
- Columnas del selector, motivo truncado, prioridad con texto y fecha relativa: Task 2.
- Tabs con conteo: Task 2.
- Telefono invalido y WhatsApp deshabilitado: Task 2 y Task 5.
- Cuenta regresiva de rechazadas: Task 1 helper + Task 2 render.
- Desglose de prioridad por caso con hover/foco y visible en modal: Task 3 + Task 4.
- Funcion aditiva en `solicitudes/priorizacion.py` sin cambiar `calcular_prioridad`: Task 3.
- Fragmentos sobre las mismas vistas, sin rutas nuevas: Task 4 y Task 5.
- POST con `fragmento=1` devuelve HTML: Task 4 y Task 5.
- Selector guarda y salta al siguiente caso: Task 4.
- Comunicador registra contacto y cierra modal sin auto-avanzar: Task 5.
- Vista previa de mensaje WhatsApp: Task 5.
- Token de idempotencia no se reutiliza porque cada render trae formulario nuevo: Task 5 usa formularios existentes; Task 6 revisa doble envio.
- Roles solo lectura ven rastro y no controles: Task 4 y Task 5.
- Responsive y accesibilidad basica: Task 6.
- Sin framework CSS/JS ni build: todas las tareas usan archivos estaticos vanilla.

**2. Placeholder scan**

No quedan marcadores de relleno ni pasos que deleguen decisiones esenciales. Los snippets incluyen rutas, nombres de funciones, templates y comandos exactos.

**3. Type consistency**

- `desglosar_prioridad(datos)` produce `codigo`, `descripcion`, `puntaje`; `desglose_prioridad` consume esa forma en templates.
- `prioridad_css`, `tiempo_relativo`, `horas_restantes_rechazo`, `telefono_whatsapp_valido` y `mensaje_whatsapp_previo` se definen en Task 1 y se consumen con esos nombres en Tasks 2, 4 y 5.
- `fragmento=1` se implementa en las mismas vistas existentes, sin cambiar urls.
- Los parciales usan `data-fragment-kind` y `data-current-row-id`, que el JS consume con los mismos nombres.

**4. Riesgos de ejecucion**

- El plan agrega varios tests HTML sensibles a texto. Si se cambia microcopy, actualizar el test solo si el texto nuevo mantiene la misma intencion operativa.
- El helper `desglosar_prioridad` convierte las colecciones de palabras clave a listas para que el desglose tenga orden estable en tests y en pantalla.
- La verificacion visual real de 1366x768 y del foco del `<dialog>` no queda completamente automatizada porque el proyecto no tiene Playwright ni framework JS.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-20-ui-ux-modulo-seleccion.md`. Two execution options:

**1. Subagent-Driven (recommended)** - dispatch a fresh subagent per task, review between tasks, fast iteration. Recommended here because the work separates cleanly into helpers/layout, listas, prioridad, selector modal, comunicador modal and QA.

**2. Inline Execution** - execute tasks in this session using `executing-plans`, batch execution with checkpoints after each task.

Which approach?
