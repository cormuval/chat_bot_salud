# Mejoras UI Selector y Comunicador Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar las nueve mejoras levantadas para el Selector y el Comunicador sin tocar el chatbot publico.

**Architecture:** La entrega se divide en tres fases mergeables: presentacion y correccion del modal, mensaje editable de WhatsApp, e historial de comunicaciones. Se mantiene el stack actual de Django con templates, CSS y JavaScript plano; los cambios de datos viven en modelos y migraciones de `gestion`.

**Tech Stack:** Django 5.2, Django test runner, templates Django, CSS plano, JavaScript sin build, MySQL 8.4 local via `docker compose`.

## Global Constraints

- Codigo, comentarios, mensajes de commit y docs en espanol, sin tildes en identificadores.
- No tocar el chatbot publico ni archivos de `solicitudes` salvo que un test existente lo exija indirectamente.
- No agregar npm, framework CSS, framework JS ni paso de build.
- Routing de gestion por `cesfam_chatbot/urls_gestion.py` y `gestion/urls.py`; no tocar el urlconf principal para nuevas rutas de gestion.
- Base local y verificacion final en MySQL 8.4; no dar por buena la tarea con SQLite.
- Tests con `.venv/bin/python manage.py test`; usar exclusivamente el Django test runner.
- La ejecucion recomendada es por etapas: completar y verificar cada fase antes de pasar a la siguiente.

---

## File Structure

- Modify: `gestion/templates/gestion/base.html` - agrega sprite SVG inline reutilizable.
- Modify: `gestion/templates/gestion/_detalle_selector.html` - botones con clases semanticas, iconos e identidad vertical.
- Modify: `gestion/templates/gestion/_detalle_comunicador.html` - identidad vertical, formulario editable de WhatsApp e historial.
- Modify: `gestion/templates/gestion/_confirmacion_comunicador.html` - conserva foco y datos para cierre del modal.
- Modify: `gestion/templates/gestion/selector_lista.html` - extrae la tabla a parcial e incluye contenedor refrescable.
- Create: `gestion/templates/gestion/_tabla_selector.html` - tabla del selector reutilizable por pagina completa y fetch.
- Modify: `static/css/gestion.css` - token `--wsp`, variantes de boton, iconos, identidad modal, editor WhatsApp e historial.
- Modify: `static/js/gestion.js` - guardia de fragmento, refresco de tabla al cerrar, apertura de WhatsApp en pestana nueva.
- Modify: `gestion/views.py` - `selector_lista?fragmento=1`, contexto de comunicador con mensajes e historial, POST WhatsApp fragmentado.
- Modify: `gestion/forms.py` - `WhatsappComunicadorForm.cuerpo` con validacion no vacia y maximo 800 caracteres.
- Modify: `gestion/models.py` - modelos `PlantillaWhatsapp` y `RegistroContacto`, armador de mensajes y escritura de historial.
- Create: `gestion/mensajes.py` - funciones puras para cuerpo editable, mensaje completo y URL de WhatsApp.
- Modify: `gestion/admin.py` - admin de `PlantillaWhatsapp` y `RegistroContacto`.
- Create: `gestion/migrations/0006_plantilla_whatsapp_y_help_text.py` - modelo de plantilla y `help_text` de motivo.
- Create: `gestion/migrations/0007_seed_plantilla_whatsapp_y_limpia_motivos.py` - datos de plantilla y limpieza reversible de saludos.
- Create: `gestion/migrations/0008_registro_contacto.py` - modelo de historial.
- Create: `gestion/migrations/0009_backfill_registro_contacto.py` - backfill desde `TokenContactoGestion`.
- Modify: `gestion/tests.py` - tests de UI, fragmentos, mensajes, migraciones, historial e idempotencia.
- Create: `docs/despliegue-mejoras-ui-seleccion.md` - nota operativa con revision manual de motivos no transformados y alcance del backfill.

---

### Task 1: Fase 1 - Botones Semanticos e Identidad Vertical

**Files:**
- Modify: `gestion/templates/gestion/base.html`
- Modify: `gestion/templates/gestion/_detalle_selector.html`
- Modify: `gestion/templates/gestion/_detalle_comunicador.html`
- Modify: `static/css/gestion.css`
- Modify: `gestion/tests.py`

**Interfaces:**
- Consumes: templates actuales de detalle selector y comunicador.
- Produces: clases CSS `.btn--confirmar`, `.btn--agendar`, `.btn--whatsapp`, `.btn--rechazar`, `.btn--neutro`, `.icon`, `.modal-identity`; simbolos SVG `#ic-check`, `#ic-x`, `#ic-minus`, `#ic-calendar`, `#ic-phone`, `#ic-whatsapp`.

- [ ] **Step 1: Write failing markup tests**

Add these tests to `GestionAccesibilidadMarkupTests` in `gestion/tests.py`:

```python
    def test_base_expone_sprite_svg_de_iconos_de_gestion(self):
        response = self.client.get("/selector/", HTTP_HOST="gestion.localhost")
        self.assertContains(response, '<svg hidden aria-hidden="true"', html=False)
        for symbol_id in (
            "ic-check",
            "ic-x",
            "ic-minus",
            "ic-calendar",
            "ic-phone",
            "ic-whatsapp",
        ):
            self.assertContains(response, f'id="{symbol_id}"', html=False)

    def test_botones_de_selector_tienen_icono_texto_y_clase_de_accion(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        response = self.client.get(
            f"/selector/{gestion.pk}/?fragmento=1",
            HTTP_HOST="gestion.localhost",
        )
        self.assertContains(response, 'class="btn--confirmar"', html=False)
        self.assertContains(response, '<use href="#ic-check"></use>', html=False)
        self.assertContains(response, 'class="btn--rechazar"', html=False)
        self.assertContains(response, '<use href="#ic-x"></use>', html=False)
        self.assertContains(response, 'class="btn--neutro"', html=False)
        self.assertContains(response, '<use href="#ic-minus"></use>', html=False)
        self.assertContains(response, "Aceptar Urgente")
        self.assertContains(response, "Confirmar rechazo")
        self.assertContains(response, "No aplica")

    def test_encabezado_de_modal_selector_muestra_identidad_vertical(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        response = self.client.get(
            f"/selector/{gestion.pk}/?fragmento=1",
            HTTP_HOST="gestion.localhost",
        )
        self.assertContains(response, '<dl class="modal-identity">', html=False)
        self.assertContains(response, "<dt>RUT</dt>", html=False)
        self.assertContains(response, "<dt>Telefono</dt>", html=False)
        self.assertContains(response, "<dt>Centro</dt>", html=False)

    def test_encabezado_de_modal_comunicador_omite_rut_y_destaca_telefono(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)
        response = self.client.get(
            f"/comunicador/{gestion.pk}/?fragmento=1",
            HTTP_HOST="gestion.localhost",
        )
        self.assertContains(response, '<dl class="modal-identity modal-identity--contacto">', html=False)
        self.assertNotContains(response, "<dt>RUT</dt>", html=False)
        self.assertContains(response, f'href="tel:{gestion.solicitud.telefono}"', html=False)
```

- [ ] **Step 2: Run focused tests to verify failure**

Run:

```bash
.venv/bin/python manage.py test gestion.tests.GestionAccesibilidadMarkupTests
```

Expected: FAIL because the sprite, semantic button classes and `.modal-identity` markup do not exist.

- [ ] **Step 3: Add inline SVG sprite**

In `gestion/templates/gestion/base.html`, place the sprite immediately after `<body ...>`:

```django
  <svg hidden aria-hidden="true" focusable="false">
    <symbol id="ic-check" viewBox="0 0 24 24">
      <path d="M20 6 9 17l-5-5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    </symbol>
    <symbol id="ic-x" viewBox="0 0 24 24">
      <path d="M18 6 6 18M6 6l12 12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
    </symbol>
    <symbol id="ic-minus" viewBox="0 0 24 24">
      <path d="M5 12h14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
    </symbol>
    <symbol id="ic-calendar" viewBox="0 0 24 24">
      <path d="M8 2v4M16 2v4M3 10h18M5 5h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    </symbol>
    <symbol id="ic-phone" viewBox="0 0 24 24">
      <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.8 19.8 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.12 4.18 2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.35 1.9.66 2.81a2 2 0 0 1-.45 2.11L8.09 9.87a16 16 0 0 0 6 6l1.23-1.23a2 2 0 0 1 2.11-.45c.91.31 1.85.53 2.81.66A2 2 0 0 1 22 16.92Z" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    </symbol>
    <symbol id="ic-whatsapp" viewBox="0 0 24 24">
      <path d="M20.5 11.8a8.4 8.4 0 0 1-12.4 7.4L3 20.5l1.4-5a8.4 8.4 0 1 1 16.1-3.7Z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
      <path d="M8.7 8.5c.2-.5.4-.5.8-.5h.6c.2 0 .4.1.5.4l.7 1.7c.1.3.1.5-.1.7l-.4.5c-.1.2-.2.3 0 .6.5.9 1.2 1.6 2.2 2.1.3.2.5.1.6-.1l.6-.7c.2-.2.4-.3.7-.2l1.6.8c.3.1.4.3.4.6 0 .7-.5 1.4-1.1 1.7-.7.3-2.8.1-5-1.7-2.2-1.8-3.1-4.1-3-4.9.1-.4.2-.7.4-1Z" fill="currentColor"/>
    </symbol>
  </svg>
```

- [ ] **Step 4: Update modal headers and buttons**

In `_detalle_selector.html`, replace the header paragraph with:

```django
      <dl class="modal-identity">
        <div><dt>RUT</dt><dd>{{ gestion.solicitud.rut }}</dd></div>
        <div><dt>Telefono</dt><dd>{{ gestion.solicitud.telefono }}</dd></div>
        <div><dt>Centro</dt><dd>{{ gestion.solicitud.centro_salud }}</dd></div>
      </dl>
```

Change the accept button to:

```django
            <button class="btn--confirmar" type="submit" name="decision" value="ACEPTADA">
              <svg class="icon" aria-hidden="true"><use href="#ic-check"></use></svg>
              Aceptar {{ etiqueta }}
            </button>
```

Change the reject summary and reject submit button to:

```django
        <summary>
          <svg class="icon" aria-hidden="true"><use href="#ic-x"></use></svg>
          Rechazar
        </summary>
```

```django
          <button class="btn--rechazar" type="submit">
            <svg class="icon" aria-hidden="true"><use href="#ic-x"></use></svg>
            Confirmar rechazo
          </button>
```

Change the no-aplica button to:

```django
        <button class="btn--neutro" type="submit" name="decision" value="NO_APLICA">
          <svg class="icon" aria-hidden="true"><use href="#ic-minus"></use></svg>
          No aplica
        </button>
```

In `_detalle_comunicador.html`, replace the header paragraph with:

```django
      <dl class="modal-identity modal-identity--contacto">
        <div>
          <dt>Telefono</dt>
          <dd><a href="tel:{{ gestion.solicitud.telefono }}">{{ gestion.solicitud.telefono }}</a></dd>
        </div>
        <div><dt>Centro</dt><dd>{{ gestion.solicitud.centro_salud }}</dd></div>
      </dl>
```

Update communicator buttons:

```django
          <button class="btn--agendar" type="submit" name="accion" value="AGENDADA">
            <svg class="icon" aria-hidden="true"><use href="#ic-calendar"></use></svg>
            Agendada
          </button>
```

```django
        <button class="btn--rechazar" type="submit" name="accion" value="NO_ACEPTA">
          <svg class="icon" aria-hidden="true"><use href="#ic-x"></use></svg>
          El paciente no acepta
        </button>
        <button class="btn--neutro" type="submit" name="accion" value="NO_CONTESTA">
          <svg class="icon" aria-hidden="true"><use href="#ic-phone"></use></svg>
          No contesta
        </button>
        <button class="btn--rechazar" type="submit" name="accion" value="NO_CONTACTADO">
          <svg class="icon" aria-hidden="true"><use href="#ic-x"></use></svg>
          No se logro contactar
        </button>
```

Update the WhatsApp submit button:

```django
        <button class="btn--whatsapp" type="submit" {% if not gestion|telefono_whatsapp_valido %}disabled{% endif %}>
          <svg class="icon" aria-hidden="true"><use href="#ic-whatsapp"></use></svg>
          Abrir WhatsApp y registrar intento
        </button>
```

- [ ] **Step 5: Add CSS for variants and identity**

Append to `static/css/gestion.css` near the button rules:

```css
:root {
  --wsp: #0d7d6f;
}

button,
.button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.icon {
  width: 1rem;
  height: 1rem;
  flex: 0 0 auto;
}

.btn--confirmar {
  border-color: var(--ok);
  background: var(--ok);
  color: #fff;
}

.btn--agendar {
  border-color: var(--primary);
  background: var(--primary);
  color: #fff;
}

.btn--whatsapp {
  border-color: var(--wsp);
  background: var(--wsp);
  color: #fff;
}

.btn--rechazar {
  border-color: var(--danger);
  background: var(--surface);
  color: var(--danger);
}

.btn--neutro {
  border-color: var(--muted);
  background: var(--surface);
  color: var(--muted);
}

.modal-header {
  align-items: start;
}

.modal-header h2 {
  margin: 0 0 var(--space-2);
}

.modal-identity {
  margin: 0;
  display: grid;
  gap: 4px;
}

.modal-identity div {
  display: grid;
  grid-template-columns: 5.5rem minmax(0, 1fr);
  gap: var(--space-2);
}

.modal-identity dt {
  color: var(--muted);
  font-weight: 800;
}

.modal-identity dd {
  margin: 0;
}

.modal-identity--contacto dd {
  font-size: 1.05rem;
  font-weight: 800;
}
```

- [ ] **Step 6: Run focused tests**

Run:

```bash
.venv/bin/python manage.py test gestion.tests.GestionAccesibilidadMarkupTests
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add gestion/templates/gestion/base.html gestion/templates/gestion/_detalle_selector.html gestion/templates/gestion/_detalle_comunicador.html static/css/gestion.css gestion/tests.py
git commit -m "feat: mejora acciones e identidad de modales"
```

---

### Task 2: Fase 1 - Fragment Guard y Refresco de Tabla del Selector

**Files:**
- Create: `gestion/templates/gestion/_tabla_selector.html`
- Modify: `gestion/templates/gestion/selector_lista.html`
- Modify: `gestion/templates/gestion/_detalle_selector.html`
- Modify: `gestion/templates/gestion/_cola_selector_vacia.html`
- Modify: `gestion/views.py`
- Modify: `static/js/gestion.js`
- Modify: `gestion/tests.py`

**Interfaces:**
- Consumes: `selector_lista(request)` y links `data-detail-url`.
- Produces: `selector_lista?fragmento=1&seccion=<seccion>` que devuelve `data-fragment-kind="selector-table"`; JS `refreshSelectorTable()` que reemplaza `[data-selector-table-region]`; guardia `extractFragmentOrNavigate(response, html)`.

- [ ] **Step 1: Write failing tests for table fragment and removed incremental attributes**

Replace the three selector counter transition tests in `gestion/tests.py` with:

```python
    def test_selector_lista_fragmento_devuelve_solo_region_refrescable(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        response = self.client.get(
            "/selector/?fragmento=1&seccion=pendientes",
            HTTP_HOST="gestion.localhost",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-fragment-kind="selector-table"', html=False)
        self.assertContains(response, f'data-row-id="{gestion.pk}"', html=False)
        self.assertNotContains(response, "<html", html=False)

    def test_post_fragmento_selector_no_expone_transicion_incremental(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        response = self.client.post(
            f"/selector/{gestion.pk}/?fragmento=1&seccion=pendientes",
            {
                "decision": Gestion.Decision.ACEPTADA,
                "prioridad_clinica": Solicitud.Prioridad.ALTA,
            },
            HTTP_HOST="gestion.localhost",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-fragment-kind="selector-empty"', html=False)
        self.assertNotContains(response, "data-selector-row-action", html=False)
        self.assertNotContains(response, "data-selector-correction-text", html=False)

    def test_post_fragmento_selector_desde_decididas_sigue_mostrando_caso_corregible(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)
        response = self.client.post(
            f"/selector/{gestion.pk}/?fragmento=1&seccion=decididas",
            {
                "decision": Gestion.Decision.RECHAZADA,
                "motivo_rechazo": self.motivo.pk,
            },
            HTTP_HOST="gestion.localhost",
        )
        self.assertContains(response, f'data-current-row-id="{gestion.pk}"', html=False)
        self.assertNotContains(response, "data-selector-row-action", html=False)
        self.assertContains(response, "quedan", html=False)
```

Update `test_js_de_fragmentos_no_reenvia_formularios_y_actualiza_contadores`:

```python
    def test_js_de_fragmentos_no_reenvia_formularios_y_refresca_tabla_al_cerrar(self):
        javascript = (
            Path(__file__).resolve().parent.parent / "static" / "js" / "gestion.js"
        ).read_text()
        self.assertNotIn("form.submit()", javascript)
        self.assertNotIn("data-selector-counter", javascript)
        self.assertNotIn("data-selector-correction", javascript)
        self.assertIn("dialogActionsCount", javascript)
        self.assertIn("refreshSelectorTable", javascript)
        self.assertIn("data-selector-table-region", javascript)
        self.assertIn("response.redirected", javascript)
        self.assertIn("data-fragment-kind", javascript)
        self.assertIn("dialogRequestInFlight", javascript)
        self.assertIn("setDialogButtonsDisabled", javascript)
```

- [ ] **Step 2: Run focused tests to verify failure**

Run:

```bash
.venv/bin/python manage.py test gestion.tests.SelectorViewsTests gestion.tests.GestionAccesibilidadMarkupTests
```

Expected: FAIL because `selector_lista?fragmento=1` still returns the full page and JS still contains incremental selector code.

- [ ] **Step 3: Extract selector table partial**

Create `gestion/templates/gestion/_tabla_selector.html` with the current table markup from `selector_lista.html`, wrapped in a refreshable region:

```django
{% load gestion_ui %}
<div data-fragment-kind="selector-table" data-selector-table-region data-selector-section="{{ seccion }}">
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
        <tr class="row-link" data-row-id="{{ gestion.pk }}" data-detail-url="{% url 'gestion:selector_detalle' gestion.pk %}?fragmento=1&amp;seccion={{ seccion }}">
          <td data-label="Paciente">{{ gestion.solicitud.nombre }}</td>
          {% if mostrar_columna_centro %}<td data-label="Centro">{{ gestion.solicitud.centro_salud }}</td>{% endif %}
          <td data-label="Prioridad administrativa">
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
          <td data-label="Abrir"><a href="{% url 'gestion:selector_detalle' gestion.pk %}?seccion={{ seccion }}">Abrir</a></td>
        </tr>
      {% empty %}
        <tr><td colspan="{% if mostrar_columna_centro %}{% if seccion == "decididas" %}7{% else %}6{% endif %}{% else %}{% if seccion == "decididas" %}6{% else %}5{% endif %}{% endif %}"><div class="empty-state">No hay solicitudes en esta seccion.</div></td></tr>
      {% endfor %}
    </tbody>
  </table>
</div>
```

Replace the nav and table in `selector_lista.html` with:

```django
{% include "gestion/_tabla_selector.html" %}
```

- [ ] **Step 4: Add fragment branch in selector_lista**

In `gestion/views.py`, compute the existing context in a local `context` dict and render `_tabla_selector.html` when `request.GET.get("fragmento") == "1"`:

```python
    context = {
        "perfil": perfil,
        "gestiones": gestiones,
        "puede_escribir": puede_escribir_selector(perfil),
        "seccion": seccion,
        "mostrar_no_aplica": mostrar_no_aplica,
        "conteos_selector": conteos_selector,
        "mostrar_columna_centro": mostrar_columna_centro,
    }
    if request.GET.get("fragmento") == "1":
        return render(request, "gestion/_tabla_selector.html", context)
    return render(request, "gestion/selector_lista.html", context)
```

- [ ] **Step 5: Remove selector incremental data attributes**

In `_detalle_selector.html`, replace the root `<article>` with:

```django
<article class="modal-panel" data-fragment-kind="selector-detail" data-current-row-id="{{ gestion.pk }}">
```

In `_cola_selector_vacia.html`, keep only fragment kind and focus target:

```django
<section class="modal-panel" data-fragment-kind="selector-empty">
  <header class="modal-header">
    <h2 data-dialog-focus tabindex="-1">No quedan casos en esta seccion</h2>
    <button type="button" class="icon-button" data-dialog-close aria-label="Cerrar">x</button>
  </header>
  <div class="modal-body">
    <p>La tabla se actualizara al cerrar este modal.</p>
  </div>
  <footer class="modal-actions">
    <button type="button" data-dialog-close>Cerrar</button>
  </footer>
</section>
```

- [ ] **Step 6: Replace JS fragment injection and selector refresh**

In `static/js/gestion.js`, remove `removeResolvedRow`, `ajustarContadorSelector`, `actualizarContadoresSelector` and `actualizarFilaConservada`. Add these helpers after state variables:

```js
  let dialogActionsCount = 0;

  function currentSelectorSection() {
    return document.querySelector("[data-selector-table-region]")?.dataset.selectorSection || "pendientes";
  }

  function selectorFragmentUrl() {
    const url = new URL(window.location.href);
    url.searchParams.set("fragmento", "1");
    url.searchParams.set("seccion", currentSelectorSection());
    return url.toString();
  }

  async function refreshSelectorTable() {
    const region = document.querySelector("[data-selector-table-region]");
    if (!region) return;
    const response = await fetch(selectorFragmentUrl(), {
      headers: { "X-Requested-With": "fetch" },
    });
    const html = await response.text();
    const fragment = extractFragmentOrNavigate(response, html);
    if (!fragment) return;
    if (fragment.dataset.fragmentKind !== "selector-table") return;
    region.replaceWith(fragment);
    document.querySelector("[data-gestion-list]")?.scrollIntoView({ block: "start" });
  }

  function extractFragmentOrNavigate(response, html) {
    if (response.redirected) {
      window.location.href = response.url;
      return null;
    }
    const template = document.createElement("template");
    template.innerHTML = html.trim();
    const fragment = template.content.querySelector("[data-fragment-kind]");
    if (!fragment) {
      window.location.href = response.url || window.location.href;
      return null;
    }
    return fragment;
  }

  function replaceDialogWithFragment(response, html) {
    const fragment = extractFragmentOrNavigate(response, html);
    if (!fragment) return false;
    dialog.replaceChildren(fragment);
    bindDialog();
    if (!dialog.open) dialog.showModal();
    focusDialogContent();
    return true;
  }
```

Update `loadFragment` to use `replaceDialogWithFragment(response, await response.text())`.

Update `submitFragmentForm` after successful `fetch`:

```js
      const html = await response.text();
      if (replaceDialogWithFragment(response, html)) {
        dialogActionsCount += 1;
      }
```

Update `closeDialog`:

```js
  function closeDialog() {
    const shouldRefreshSelector = dialogActionsCount > 0 && document.querySelector("[data-selector-table-region]");
    dialog.close();
    dialog.innerHTML = "";
    dialogActionsCount = 0;
    if (lastTrigger) lastTrigger.focus();
    if (shouldRefreshSelector) {
      refreshSelectorTable().catch(() => window.location.reload());
    }
  }
```

- [ ] **Step 7: Run focused tests**

Run:

```bash
.venv/bin/python manage.py test gestion.tests.SelectorViewsTests gestion.tests.GestionAccesibilidadMarkupTests gestion.tests.GestionListasUiTests
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add gestion/templates/gestion/_tabla_selector.html gestion/templates/gestion/selector_lista.html gestion/templates/gestion/_detalle_selector.html gestion/templates/gestion/_cola_selector_vacia.html gestion/views.py static/js/gestion.js gestion/tests.py
git commit -m "fix: refresca tabla del selector al cerrar modal"
```

---

### Task 3: Fase 2 - Plantilla de WhatsApp y Armador de Mensajes

**Files:**
- Create: `gestion/mensajes.py`
- Modify: `gestion/models.py`
- Modify: `gestion/admin.py`
- Create: `gestion/migrations/0006_plantilla_whatsapp_y_help_text.py`
- Create: `gestion/migrations/0007_seed_plantilla_whatsapp_y_limpia_motivos.py`
- Modify: `gestion/templatetags/gestion_ui.py`
- Modify: `gestion/tests.py`

**Interfaces:**
- Produces: `PlantillaWhatsapp.obtener_cuerpo_activo(clave: str) -> str`; `gestion.mensajes.armar_mensaje_whatsapp(gestion, cuerpo: str) -> str`; `gestion.mensajes.url_whatsapp_para_gestion(gestion, cuerpo: str | None = None) -> str | None`; `Gestion.url_whatsapp(cuerpo=None)`.

- [ ] **Step 1: Write failing model and message tests**

Add to `GestionModelTests`:

```python
    def test_url_whatsapp_aceptada_usa_plantilla_activa_y_partes_fijas(self):
        PlantillaWhatsapp.objects.create(
            clave="aceptada",
            descripcion="Aceptada",
            cuerpo="Estamos intentando comunicarnos con usted.",
        )
        gestion = crear_solicitud_base(nombre="Ana Perez").gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)
        url = gestion.url_whatsapp()
        self.assertTrue(url.startswith("https://wa.me/56949106239?text="))
        self.assertIn("Hola%2C+Ana+Perez.", url)
        self.assertIn("Estamos+intentando+comunicarnos+con+usted.", url)
        self.assertIn("Muchas+gracias.", url)

    def test_url_whatsapp_rechazada_usa_motivo_como_cuerpo_sin_duplicar_saludo(self):
        self.motivo.mensaje_paciente = "Faltan datos para continuar."
        self.motivo.save(update_fields=["mensaje_paciente"])
        gestion = crear_solicitud_base(nombre="Ana Perez").gestion
        gestion.rechazar(self.usuario, self.motivo)
        url = gestion.url_whatsapp()
        self.assertIn("Hola%2C+Ana+Perez.", url)
        self.assertIn("Faltan+datos+para+continuar.", url)
        self.assertEqual(url.count("Hola"), 1)
```

Update imports:

```python
from gestion.models import Gestion, MotivoRechazo, PerfilUsuario, PlantillaWhatsapp
```

- [ ] **Step 2: Run focused tests to verify failure**

Run:

```bash
.venv/bin/python manage.py test gestion.tests.GestionModelTests
```

Expected: FAIL because `PlantillaWhatsapp` and the new message builder do not exist.

- [ ] **Step 3: Add model**

In `gestion/models.py`, after `MotivoRechazo` add:

```python
class PlantillaWhatsapp(models.Model):
    clave = models.CharField(max_length=32, unique=True)
    descripcion = models.CharField(max_length=120)
    cuerpo = models.TextField(
        help_text=(
            "Solo el cuerpo. El saludo con el nombre, el centro y el cierre "
            "los agrega el sistema."
        )
    )
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "gestion_plantilla_whatsapp"
        ordering = ["clave"]
        verbose_name = "plantilla de WhatsApp"
        verbose_name_plural = "plantillas de WhatsApp"

    def __str__(self):
        return self.descripcion

    @classmethod
    def obtener_cuerpo_activo(cls, clave):
        plantilla = cls.objects.filter(clave=clave, activo=True).first()
        if plantilla:
            return plantilla.cuerpo
        return (
            "Estamos intentando comunicarnos con usted para gestionar la "
            "asignacion de una hora de atencion de morbilidad. Por favor, "
            "responda este mensaje para continuar con la gestion."
        )
```

- [ ] **Step 4: Add message builder**

Create `gestion/mensajes.py`:

```python
import re
from urllib.parse import quote_plus

from .models import Gestion, PlantillaWhatsapp


def cuerpo_whatsapp_para_gestion(gestion):
    if gestion.motivo_rechazo_id:
        return gestion.motivo_rechazo.mensaje_paciente
    return PlantillaWhatsapp.obtener_cuerpo_activo("aceptada")


def armar_mensaje_whatsapp(gestion, cuerpo):
    cuerpo_limpio = " ".join((cuerpo or "").split())
    return (
        f"Hola, {gestion.solicitud.nombre}. Somos del "
        f"{gestion.solicitud.centro_salud}.\n"
        f"{cuerpo_limpio}\n"
        "Muchas gracias."
    )


def url_whatsapp_para_gestion(gestion, cuerpo=None):
    telefono = gestion.solicitud.telefono
    if not re.fullmatch(r"\+569\d{8}", telefono):
        return None
    cuerpo_final = cuerpo if cuerpo is not None else cuerpo_whatsapp_para_gestion(gestion)
    mensaje = armar_mensaje_whatsapp(gestion, cuerpo_final)
    return f"https://wa.me/{telefono.removeprefix('+')}?text={quote_plus(mensaje)}"
```

In `Gestion.url_whatsapp`, replace the current body with:

```python
        from .mensajes import url_whatsapp_para_gestion

        return url_whatsapp_para_gestion(self, cuerpo=cuerpo)
```

Change the signature to:

```python
    def url_whatsapp(self, cuerpo=None):
```

- [ ] **Step 5: Add admin**

In `gestion/admin.py`, import and register:

```python
from .models import Gestion, MotivoRechazo, PerfilUsuario, PlantillaWhatsapp
```

```python
@admin.register(PlantillaWhatsapp)
class PlantillaWhatsappAdmin(admin.ModelAdmin):
    list_display = ("clave", "descripcion", "activo")
    list_filter = ("activo",)
    search_fields = ("clave", "descripcion", "cuerpo")
```

- [ ] **Step 6: Create schema migration**

Run:

```bash
.venv/bin/python manage.py makemigrations gestion --name plantilla_whatsapp_y_help_text
```

Expected: creates `gestion/migrations/0006_plantilla_whatsapp_y_help_text.py`.

Open the migration and verify it includes `CreateModel(name="PlantillaWhatsapp", ...)` and `AlterField(model_name="motivorechazo", name="mensaje_paciente", ...)`.

- [ ] **Step 7: Create data migration**

Create empty migration:

```bash
.venv/bin/python manage.py makemigrations gestion --empty --name seed_plantilla_whatsapp_y_limpia_motivos
```

Edit `gestion/migrations/0007_seed_plantilla_whatsapp_y_limpia_motivos.py`:

```python
import re

from django.db import migrations


PATRON_SALUDO = re.compile(r"^\s*Hola[ ,]*\{nombre\}\s*[,.\-]?\s*", re.IGNORECASE)
CUERPO_ACEPTADA = (
    "Estamos intentando comunicarnos con usted para gestionar la asignacion de "
    "una hora de atencion de morbilidad. Por favor, responda este mensaje para "
    "continuar con la gestion."
)


def forwards(apps, schema_editor):
    PlantillaWhatsapp = apps.get_model("gestion", "PlantillaWhatsapp")
    MotivoRechazo = apps.get_model("gestion", "MotivoRechazo")
    PlantillaWhatsapp.objects.update_or_create(
        clave="aceptada",
        defaults={
            "descripcion": "Solicitud aceptada",
            "cuerpo": CUERPO_ACEPTADA,
            "activo": True,
        },
    )
    for motivo in MotivoRechazo.objects.all():
        limpio = PATRON_SALUDO.sub("", motivo.mensaje_paciente, count=1)
        if limpio != motivo.mensaje_paciente:
            motivo.mensaje_paciente = limpio.strip()
            motivo.save(update_fields=["mensaje_paciente"])


def backwards(apps, schema_editor):
    PlantillaWhatsapp = apps.get_model("gestion", "PlantillaWhatsapp")
    MotivoRechazo = apps.get_model("gestion", "MotivoRechazo")
    PlantillaWhatsapp.objects.filter(clave="aceptada").delete()
    for motivo in MotivoRechazo.objects.all():
        if not PATRON_SALUDO.match(motivo.mensaje_paciente):
            motivo.mensaje_paciente = f"Hola {{nombre}}, {motivo.mensaje_paciente}"
            motivo.save(update_fields=["mensaje_paciente"])


class Migration(migrations.Migration):

    dependencies = [
        ("gestion", "0006_plantilla_whatsapp_y_help_text"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
```

- [ ] **Step 8: Update template filters**

In `gestion/templatetags/gestion_ui.py`, update `mensaje_whatsapp_previo`:

```python
@register.filter
def mensaje_whatsapp_previo(gestion):
    from gestion.mensajes import armar_mensaje_whatsapp, cuerpo_whatsapp_para_gestion

    return armar_mensaje_whatsapp(gestion, cuerpo_whatsapp_para_gestion(gestion))
```

- [ ] **Step 9: Run focused tests**

Run:

```bash
.venv/bin/python manage.py test gestion.tests.GestionModelTests gestion.tests.GestionTemplateTagsTests
```

Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add gestion/models.py gestion/mensajes.py gestion/admin.py gestion/migrations/0006_plantilla_whatsapp_y_help_text.py gestion/migrations/0007_seed_plantilla_whatsapp_y_limpia_motivos.py gestion/templatetags/gestion_ui.py gestion/tests.py
git commit -m "feat: agrega plantilla editable de WhatsApp"
```

---

### Task 4: Fase 2 - Edicion del Cuerpo y Apertura de WhatsApp en Nueva Pestana

**Files:**
- Modify: `gestion/forms.py`
- Modify: `gestion/views.py`
- Modify: `gestion/templates/gestion/_detalle_comunicador.html`
- Modify: `static/js/gestion.js`
- Modify: `static/css/gestion.css`
- Modify: `gestion/tests.py`

**Interfaces:**
- Consumes: `Gestion.url_whatsapp(cuerpo=None)` from Task 3.
- Produces: POST `gestion:whatsapp` accepts `cuerpo`, returns `_detalle_comunicador.html` for `?fragmento=1` with `data-whatsapp-url`; fixed greeting and closing are outside `<textarea>`.

- [ ] **Step 1: Write failing tests for editable body**

Add to `ComunicadorViewsTests`:

```python
    def test_fragmento_comunicador_whatsapp_tiene_partes_fijas_fuera_del_textarea(self):
        PlantillaWhatsapp.objects.create(
            clave="aceptada",
            descripcion="Aceptada",
            cuerpo="Cuerpo editable.",
        )
        gestion = crear_solicitud_base(centro_salud=self.centro, nombre="Ana Perez").gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)
        response = self.client.get(
            f"/comunicador/{gestion.pk}/?fragmento=1",
            HTTP_HOST="gestion.localhost",
        )
        self.assertContains(response, "Hola, Ana Perez. Somos del")
        self.assertContains(response, "Muchas gracias.")
        self.assertContains(response, 'name="cuerpo"', html=False)
        textarea_start = response.content.decode("utf-8").index('name="cuerpo"')
        textarea_chunk = response.content.decode("utf-8")[textarea_start:textarea_start + 300]
        self.assertNotIn("Ana Perez", textarea_chunk)
        self.assertIn("Cuerpo editable.", textarea_chunk)

    def test_whatsapp_fragmentado_devuelve_modal_con_url_y_registra_cuerpo_editado(self):
        gestion = crear_solicitud_base(centro_salud=self.centro, nombre="Ana Perez").gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)
        response = self.client.get(
            f"/comunicador/{gestion.pk}/?fragmento=1",
            HTTP_HOST="gestion.localhost",
        )
        token = response.context["form_whatsapp"]["token_contacto"].value()
        response = self.client.post(
            f"/comunicador/{gestion.pk}/whatsapp/?fragmento=1",
            {"token_contacto": token, "cuerpo": "Mensaje editado por comunicador."},
            HTTP_HOST="gestion.localhost",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-fragment-kind="comunicador-detail"', html=False)
        self.assertContains(response, "data-whatsapp-url=", html=False)
        self.assertContains(response, "Mensaje editado por comunicador.")
        gestion.refresh_from_db()
        self.assertEqual(gestion.intentos_contacto, 1)

    def test_whatsapp_fragmentado_rechaza_cuerpo_vacio_sin_registrar_intento(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)
        response = self.client.post(
            f"/comunicador/{gestion.pk}/whatsapp/?fragmento=1",
            {"token_contacto": "token-vacio", "cuerpo": "   "},
            HTTP_HOST="gestion.localhost",
        )
        self.assertContains(response, "Debe escribir el cuerpo del mensaje.")
        gestion.refresh_from_db()
        self.assertEqual(gestion.intentos_contacto, 0)
```

- [ ] **Step 2: Run focused tests to verify failure**

Run:

```bash
.venv/bin/python manage.py test gestion.tests.ComunicadorViewsTests
```

Expected: FAIL because `cuerpo` is not in `WhatsappComunicadorForm` and the WhatsApp POST redirects to `wa.me`.

- [ ] **Step 3: Extend WhatsappComunicadorForm**

In `gestion/forms.py`, import the body helper:

```python
from .mensajes import cuerpo_whatsapp_para_gestion
```

Replace `WhatsappComunicadorForm` with:

```python
class WhatsappComunicadorForm(forms.Form):
    cuerpo = forms.CharField(
        max_length=800,
        required=True,
        widget=forms.Textarea(attrs={"rows": 5}),
        error_messages={
            "required": "Debe escribir el cuerpo del mensaje.",
            "max_length": "El cuerpo no puede superar 800 caracteres.",
        },
    )
    token_contacto = forms.CharField(
        max_length=128,
        required=False,
        widget=forms.HiddenInput,
    )

    def __init__(self, *args, gestion=None, **kwargs):
        super().__init__(*args, **kwargs)
        if gestion is not None and not self.is_bound:
            self.initial["cuerpo"] = cuerpo_whatsapp_para_gestion(gestion)
        if not self.is_bound and not self.initial.get("token_contacto"):
            self.initial["token_contacto"] = secrets.token_urlsafe(16)

    def clean_cuerpo(self):
        cuerpo = " ".join(self.cleaned_data["cuerpo"].split())
        if not cuerpo:
            raise forms.ValidationError("Debe escribir el cuerpo del mensaje.")
        return cuerpo
```

- [ ] **Step 4: Pass gestion to form**

In `comunicador_detalle`, replace:

```python
    form_whatsapp = WhatsappComunicadorForm()
```

with:

```python
    form_whatsapp = WhatsappComunicadorForm(gestion=gestion)
```

- [ ] **Step 5: Render fixed parts and textarea**

In `_detalle_comunicador.html`, replace the WhatsApp preview section with:

```django
    <section>
      <h3>Mensaje de WhatsApp</h3>
      {% if gestion|telefono_whatsapp_valido %}
        <div class="message-preview">
          <p>Hola, {{ gestion.solicitud.nombre }}. Somos del {{ gestion.solicitud.centro_salud }}.</p>
          {% if puede_escribir %}
            <p class="muted">El cuerpo se puede editar antes de abrir WhatsApp.</p>
          {% else %}
            <p>{{ gestion|mensaje_whatsapp_previo }}</p>
          {% endif %}
          <p>Muchas gracias.</p>
        </div>
      {% else %}
        <p class="danger-text">Telefono invalido para WhatsApp</p>
      {% endif %}
    </section>
```

Inside the WhatsApp form, before `{{ form_whatsapp.token_contacto }}`, add:

```django
        <label class="whatsapp-editor">
          <span>Cuerpo del mensaje</span>
          {{ form_whatsapp.cuerpo }}
        </label>
        {% if form_whatsapp.cuerpo.errors %}<div data-dialog-error-focus tabindex="-1">{{ form_whatsapp.cuerpo.errors }}</div>{% endif %}
```

Change the form action to preserve fragment mode:

```django
      <form method="post" action="{% url 'gestion:whatsapp' gestion.pk %}{% if es_fragmento %}?fragmento=1{% endif %}" data-whatsapp-form>
```

- [ ] **Step 6: Update registrar_whatsapp**

In `gestion/views.py`, import:

```python
from .mensajes import url_whatsapp_para_gestion
```

In `registrar_whatsapp`, set:

```python
    es_fragmento = request.GET.get("fragmento") == "1"
    form = WhatsappComunicadorForm(request.POST, gestion=gestion)
```

Replace invalid-form redirect with fragment render when `es_fragmento`:

```python
    if not form.is_valid():
        if es_fragmento:
            return render(
                request,
                "gestion/_detalle_comunicador.html",
                {
                    "perfil": perfil,
                    "gestion": gestion,
                    "form": AccionComunicadorForm(),
                    "form_whatsapp": form,
                    "puede_escribir": True,
                    "es_fragmento": True,
                    "whatsapp_url": "",
                },
            )
        messages.error(request, "El formulario de WhatsApp no es valido.")
        return redirect("gestion:comunicador_detalle", pk=gestion.pk)
```

Build the URL from cleaned body before registering:

```python
    url = url_whatsapp_para_gestion(gestion, cuerpo=form.cleaned_data["cuerpo"])
```

After successful registration, return a fragment for `es_fragmento`:

```python
    if es_fragmento:
        return render(
            request,
            "gestion/_detalle_comunicador.html",
            {
                "perfil": perfil,
                "gestion": gestion,
                "form": AccionComunicadorForm(),
                "form_whatsapp": WhatsappComunicadorForm(
                    initial={"cuerpo": form.cleaned_data["cuerpo"]},
                    gestion=gestion,
                ),
                "puede_escribir": True,
                "es_fragmento": True,
                "whatsapp_url": url,
            },
        )
    return HttpResponseRedirect(url)
```

In `_detalle_comunicador.html`, add `data-whatsapp-url` to the root article:

```django
<article class="modal-panel" data-fragment-kind="comunicador-detail" data-current-row-id="{{ gestion.pk }}"{% if whatsapp_url %} data-whatsapp-url="{{ whatsapp_url }}"{% endif %}>
```

- [ ] **Step 7: Add JS for new-tab WhatsApp**

In `static/js/gestion.js`, add:

```js
  async function submitWhatsappForm(form, submitter) {
    if (dialogRequestInFlight) return;
    const popup = window.open("", "_blank", "noopener");
    dialogRequestInFlight = true;
    setDialogButtonsDisabled(true);
    const data = new FormData(form);
    if (submitter && submitter.name) data.set(submitter.name, submitter.value);
    try {
      const response = await fetch(form.action, {
        method: "POST",
        body: data,
        headers: { "X-Requested-With": "fetch" },
      });
      if (!response.ok) throw new Error("No se pudo guardar.");
      const html = await response.text();
      const replaced = replaceDialogWithFragment(response, html);
      const url = dialog.querySelector("[data-whatsapp-url]")?.dataset.whatsappUrl;
      if (url && popup) {
        popup.location.href = url;
      } else if (url) {
        mostrarEnlaceWhatsapp(url);
      } else if (popup) {
        popup.close();
      }
      if (replaced) dialogActionsCount += 1;
    } finally {
      dialogRequestInFlight = false;
    }
  }

  function mostrarEnlaceWhatsapp(url) {
    let status = dialog.querySelector("[data-dialog-status]");
    if (!status) {
      status = document.createElement("p");
      status.className = "warning-text";
      status.setAttribute("role", "alert");
      status.setAttribute("data-dialog-status", "");
      dialog.querySelector(".modal-header")?.after(status);
    }
    status.innerHTML = `<a href="${url}" target="_blank" rel="noopener">Abrir WhatsApp</a>`;
  }
```

In `bindDialog`, add:

```js
    dialog.querySelectorAll("[data-whatsapp-form]").forEach((form) => {
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        submitWhatsappForm(form, event.submitter).catch(() => {
          setDialogButtonsDisabled(false);
          mostrarErrorDeEnvio();
        });
      });
    });
```

- [ ] **Step 8: Add CSS for editor**

Append:

```css
.whatsapp-editor {
  display: grid;
  gap: var(--space-2);
  width: min(100%, 42rem);
}

.whatsapp-editor span {
  font-weight: 800;
}

.whatsapp-editor textarea {
  width: 100%;
  min-height: 8rem;
  resize: vertical;
}
```

- [ ] **Step 9: Run focused tests**

Run:

```bash
.venv/bin/python manage.py test gestion.tests.ComunicadorViewsTests gestion.tests.GestionAccesibilidadMarkupTests
```

Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add gestion/forms.py gestion/views.py gestion/templates/gestion/_detalle_comunicador.html static/js/gestion.js static/css/gestion.css gestion/tests.py
git commit -m "feat: permite editar cuerpo de WhatsApp"
```

---

### Task 5: Fase 3 - Modelo de Historial e Idempotencia

**Files:**
- Modify: `gestion/models.py`
- Modify: `gestion/admin.py`
- Create: `gestion/migrations/0008_registro_contacto.py`
- Create: `gestion/migrations/0009_backfill_registro_contacto.py`
- Modify: `gestion/tests.py`

**Interfaces:**
- Produces: `RegistroContacto` with `related_name="registros_contacto"`; `_registrar_intento(..., mensaje="")`; `Gestion.registrar_click_whatsapp(usuario, token_contacto="", mensaje="")`.

- [ ] **Step 1: Write failing model tests**

Add to `GestionModelTests`:

```python
    def test_registrar_no_contesta_crea_registro_contacto_de_llamada(self):
        gestion = crear_solicitud_base().gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)
        gestion.registrar_no_contesta(self.usuario, token_contacto="token-llamada")
        registro = gestion.registros_contacto.get()
        self.assertEqual(registro.canal, RegistroContacto.Canal.LLAMADA)
        self.assertEqual(registro.resultado, Gestion.AccionContacto.NO_CONTESTA)
        self.assertEqual(registro.usuario, self.usuario)
        self.assertEqual(registro.mensaje, "")

    def test_registrar_whatsapp_crea_registro_con_mensaje(self):
        gestion = crear_solicitud_base().gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)
        gestion.registrar_click_whatsapp(
            self.usuario,
            token_contacto="token-whatsapp",
            mensaje="Mensaje enviado.",
        )
        registro = gestion.registros_contacto.get()
        self.assertEqual(registro.canal, RegistroContacto.Canal.WHATSAPP)
        self.assertEqual(registro.resultado, Gestion.AccionContacto.WHATSAPP)
        self.assertEqual(registro.mensaje, "Mensaje enviado.")

    def test_token_duplicado_no_duplica_historial(self):
        gestion = crear_solicitud_base().gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)
        gestion.registrar_no_contesta(self.usuario, token_contacto="token-repetido")
        gestion.registrar_no_contesta(self.usuario, token_contacto="token-repetido")
        self.assertEqual(gestion.registros_contacto.count(), 1)
```

Update imports:

```python
from gestion.models import Gestion, MotivoRechazo, PerfilUsuario, PlantillaWhatsapp, RegistroContacto
```

- [ ] **Step 2: Run focused tests to verify failure**

Run:

```bash
.venv/bin/python manage.py test gestion.tests.GestionModelTests
```

Expected: FAIL because `RegistroContacto` does not exist.

- [ ] **Step 3: Add model and write path**

In `gestion/models.py`, after `TokenContactoGestion`, add:

```python
class RegistroContacto(models.Model):
    class Canal(models.TextChoices):
        LLAMADA = "LLAMADA", "Llamada telefonica"
        WHATSAPP = "WHATSAPP", "WhatsApp"

    gestion = models.ForeignKey(
        Gestion,
        on_delete=models.CASCADE,
        related_name="registros_contacto",
    )
    canal = models.CharField(max_length=10, choices=Canal.choices)
    resultado = models.CharField(max_length=20, choices=Gestion.AccionContacto.choices)
    mensaje = models.TextField(blank=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="registros_contacto_gestion",
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "gestion_registro_contacto"
        ordering = ["-creado_en", "-pk"]
        indexes = [
            models.Index(fields=["gestion", "-creado_en"], name="gestion_reg_contacto_idx"),
        ]
        verbose_name = "registro de contacto"
        verbose_name_plural = "registros de contacto"

    def __str__(self):
        return f"{self.gestion_id} {self.get_canal_display()} {self.get_resultado_display()}"

    @classmethod
    def canal_para_accion(cls, accion):
        if accion == Gestion.AccionContacto.WHATSAPP:
            return cls.Canal.WHATSAPP
        return cls.Canal.LLAMADA
```

Update `_registrar_intento` signature:

```python
        mensaje="",
```

Inside `mutar`, after token creation and before incrementing counters:

```python
            RegistroContacto.objects.create(
                gestion=gestion,
                canal=RegistroContacto.canal_para_accion(accion),
                resultado=accion,
                mensaje=mensaje if accion == self.AccionContacto.WHATSAPP else "",
                usuario=usuario,
            )
```

Update `registrar_click_whatsapp`:

```python
    def registrar_click_whatsapp(self, usuario, token_contacto="", mensaje=""):
        return self._registrar_intento(
            usuario,
            self.AccionContacto.WHATSAPP,
            registrar_whatsapp=True,
            token_contacto=token_contacto,
            mensaje=mensaje,
        )
```

- [ ] **Step 4: Register admin**

In `gestion/admin.py`, import `RegistroContacto` and add:

```python
@admin.register(RegistroContacto)
class RegistroContactoAdmin(admin.ModelAdmin):
    list_display = ("gestion", "canal", "resultado", "usuario", "creado_en")
    list_filter = ("canal", "resultado", "creado_en")
    search_fields = ("gestion__solicitud__nombre", "gestion__solicitud__rut", "usuario__email", "mensaje")
    readonly_fields = ("gestion", "canal", "resultado", "mensaje", "usuario", "creado_en")
    list_select_related = ("gestion", "gestion__solicitud", "usuario")
```

- [ ] **Step 5: Create schema migration**

Run:

```bash
.venv/bin/python manage.py makemigrations gestion --name registro_contacto
```

Expected: creates `gestion/migrations/0008_registro_contacto.py`.

- [ ] **Step 6: Create backfill migration**

Run:

```bash
.venv/bin/python manage.py makemigrations gestion --empty --name backfill_registro_contacto
```

Edit `gestion/migrations/0009_backfill_registro_contacto.py`:

```python
from django.db import migrations


def canal_para_accion(accion):
    if accion == "WHATSAPP":
        return "WHATSAPP"
    return "LLAMADA"


def forwards(apps, schema_editor):
    TokenContactoGestion = apps.get_model("gestion", "TokenContactoGestion")
    RegistroContacto = apps.get_model("gestion", "RegistroContacto")
    registros = []
    for token in TokenContactoGestion.objects.all().order_by("creado_en", "pk"):
        registros.append(
            RegistroContacto(
                gestion_id=token.gestion_id,
                canal=canal_para_accion(token.accion),
                resultado=token.accion,
                mensaje="",
                usuario_id=None,
                creado_en=token.creado_en,
            )
        )
    RegistroContacto.objects.bulk_create(registros, batch_size=500)


def backwards(apps, schema_editor):
    RegistroContacto = apps.get_model("gestion", "RegistroContacto")
    RegistroContacto.objects.filter(usuario__isnull=True, mensaje="").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("gestion", "0008_registro_contacto"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
```

- [ ] **Step 7: Pass WhatsApp message into history**

In `registrar_whatsapp`, after building `url`, compute:

```python
    mensaje = armar_mensaje_whatsapp(gestion, form.cleaned_data["cuerpo"])
```

Import:

```python
from .mensajes import armar_mensaje_whatsapp, url_whatsapp_para_gestion
```

Pass to registrar:

```python
        gestion.registrar_click_whatsapp(
            request.user,
            token_contacto=form.cleaned_data.get("token_contacto", ""),
            mensaje=mensaje,
        )
```

- [ ] **Step 8: Run focused tests**

Run:

```bash
.venv/bin/python manage.py test gestion.tests.GestionModelTests gestion.tests.ComunicadorViewsTests
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add gestion/models.py gestion/admin.py gestion/views.py gestion/migrations/0008_registro_contacto.py gestion/migrations/0009_backfill_registro_contacto.py gestion/tests.py
git commit -m "feat: registra historial de comunicaciones"
```

---

### Task 6: Fase 3 - Vista del Historial en Modal

**Files:**
- Modify: `gestion/views.py`
- Modify: `gestion/templates/gestion/_detalle_comunicador.html`
- Modify: `static/css/gestion.css`
- Modify: `gestion/tests.py`

**Interfaces:**
- Consumes: `gestion.registros_contacto` from Task 5.
- Produces: context variable `registros_contacto`; `<details class="contact-history">` visible for roles de solo lectura.

- [ ] **Step 1: Write failing modal tests**

Add to `ComunicadorViewsTests`:

```python
    def test_fragmento_comunicador_muestra_bitacora_de_comunicaciones(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)
        gestion.registrar_no_contesta(self.usuario, token_contacto="llamada-1")
        gestion.registrar_click_whatsapp(
            self.usuario,
            token_contacto="wsp-1",
            mensaje="Hola, paciente. Mensaje enviado.",
        )
        response = self.client.get(
            f"/comunicador/{gestion.pk}/?fragmento=1",
            HTTP_HOST="gestion.localhost",
        )
        self.assertContains(response, "Historial de comunicaciones (2)")
        self.assertContains(response, "Llamada telefonica")
        self.assertContains(response, "WhatsApp")
        self.assertContains(response, "Mensaje enviado.")
        self.assertContains(response, self.usuario.email or self.usuario.username)

    def test_historial_visible_para_solo_lectura(self):
        gestion = crear_solicitud_base(centro_salud=self.centro).gestion
        gestion.aceptar(self.usuario, Solicitud.Prioridad.MEDIA)
        gestion.registrar_no_contesta(self.usuario, token_contacto="solo-lectura")
        self.perfil.rol = PerfilUsuario.Rol.ADMIN
        self.perfil.save(update_fields=["rol"])
        response = self.client.get(
            f"/comunicador/{gestion.pk}/?fragmento=1",
            HTTP_HOST="gestion.localhost",
        )
        self.assertContains(response, "Historial de comunicaciones (1)")
        self.assertContains(response, "Vista de solo lectura")
```

- [ ] **Step 2: Run focused tests to verify failure**

Run:

```bash
.venv/bin/python manage.py test gestion.tests.ComunicadorViewsTests
```

Expected: FAIL because the modal still shows only aggregate contact fields.

- [ ] **Step 3: Query history in views**

In `comunicador_detalle`, update the GET and POST querysets to prefetch:

```python
from django.db.models import Prefetch
```

```python
from .models import Gestion, RegistroContacto
```

Use this queryset in context:

```python
    registros_contacto = list(
        gestion.registros_contacto.select_related("usuario").order_by("-creado_en", "-pk")
    )
```

Add `"registros_contacto": registros_contacto` to every render of `_detalle_comunicador.html`, including `registrar_whatsapp`.

- [ ] **Step 4: Render history section**

In `_detalle_comunicador.html`, after the current audit `<section>`, add:

```django
    <details class="contact-history" open>
      <summary>Historial de comunicaciones ({{ registros_contacto|length }})</summary>
      {% if registros_contacto %}
        <table class="history-table">
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Canal</th>
              <th>Resultado</th>
              <th>Usuario</th>
              <th>Mensaje</th>
            </tr>
          </thead>
          <tbody>
            {% for registro in registros_contacto %}
              <tr>
                <td><time title="{{ registro.creado_en }}">{{ registro.creado_en|date:"d/m H:i" }}</time></td>
                <td>{{ registro.get_canal_display }}</td>
                <td>{{ registro.get_resultado_display }}</td>
                <td>{% if registro.usuario %}{{ registro.usuario.email|default:registro.usuario.username }}{% else %}Sin usuario{% endif %}</td>
                <td>{% if registro.mensaje %}<span class="history-message">{{ registro.mensaje }}</span>{% else %}-{% endif %}</td>
              </tr>
            {% endfor %}
          </tbody>
        </table>
      {% else %}
        <p class="muted">Sin comunicaciones registradas.</p>
      {% endif %}
    </details>
```

- [ ] **Step 5: Add CSS**

Append:

```css
.contact-history {
  border-top: 1px solid var(--line);
  padding-top: var(--space-3);
}

.contact-history summary {
  cursor: pointer;
  font-weight: 800;
}

.history-table {
  width: 100%;
  margin-top: var(--space-3);
  border-collapse: collapse;
}

.history-table th,
.history-table td {
  padding: 8px;
  border-bottom: 1px solid var(--line);
  text-align: left;
  vertical-align: top;
}

.history-message {
  display: inline-block;
  max-width: 28rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
```

- [ ] **Step 6: Run focused tests**

Run:

```bash
.venv/bin/python manage.py test gestion.tests.ComunicadorViewsTests gestion.tests.GestionAccesibilidadMarkupTests
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add gestion/views.py gestion/templates/gestion/_detalle_comunicador.html static/css/gestion.css gestion/tests.py
git commit -m "feat: muestra historial de comunicaciones"
```

---

### Task 7: Nota de Despliegue y Riesgos Operativos

**Files:**
- Create: `docs/despliegue-mejoras-ui-seleccion.md`
- Modify: `gestion/tests.py`

**Interfaces:**
- Produces: documento de despliegue con notas para revisar motivos de rechazo no transformados, backfill parcial y prueba de popup.

- [ ] **Step 1: Write docs existence test**

Add to `GestionBaseLayoutTests` or a new `GestionDocsTests`:

```python
class GestionDocsTests(TestCase):
    def test_nota_despliegue_mejoras_ui_documenta_riesgos_operativos(self):
        path = Path(__file__).resolve().parent.parent / "docs" / "despliegue-mejoras-ui-seleccion.md"
        contenido = path.read_text(encoding="utf-8")
        self.assertIn("Motivos de rechazo no transformados", contenido)
        self.assertIn("Historial no reconstruible", contenido)
        self.assertIn("Bloqueador de popups", contenido)
```

- [ ] **Step 2: Run docs test to verify failure**

Run:

```bash
.venv/bin/python manage.py test gestion.tests.GestionDocsTests
```

Expected: FAIL because the deployment note does not exist.

- [ ] **Step 3: Create deployment note**

Create `docs/despliegue-mejoras-ui-seleccion.md`:

```markdown
# Despliegue mejoras UI Selector y Comunicador

Fecha prevista: 2026-08-26

## Motivos de rechazo no transformados

La migracion `0007_seed_plantilla_whatsapp_y_limpia_motivos` solo limpia motivos
que comienzan con el patron `Hola {nombre}`. Los motivos que no calzan se dejan
intactos para evitar reescrituras inventadas.

Despues de migrar, revisar en el admin de Django los motivos de rechazo activos y
confirmar que `mensaje_paciente` contiene solo el cuerpo del mensaje, sin saludo ni
cierre.

## Historial no reconstruible

La migracion `0009_backfill_registro_contacto` crea registros historicos desde
`TokenContactoGestion`. Las gestiones con `intentos_contacto > 0` sin token asociado
no son reconstruibles porque el sistema anterior no guardaba cada evento.

El historial nuevo es confiable desde el despliegue de esta version. El backfill
solo cubre eventos con token.

## Bloqueador de popups

El flujo abre una pestana vacia antes del `fetch` para conservar el gesto del
usuario. Si el navegador bloquea igualmente la apertura, el modal muestra un enlace
manual `Abrir WhatsApp`.

Validar el flujo en los navegadores usados por el equipo antes de dar por cerrada
la fase 2.

## Verificacion tecnica

Ejecutar:

```bash
docker compose up -d
.venv/bin/python manage.py migrate
.venv/bin/python manage.py test
```
```

- [ ] **Step 4: Run docs test**

Run:

```bash
.venv/bin/python manage.py test gestion.tests.GestionDocsTests
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add docs/despliegue-mejoras-ui-seleccion.md gestion/tests.py
git commit -m "docs: agrega nota de despliegue de mejoras ui"
```

---

### Task 8: Verificacion Final por Fases

**Files:**
- No source edits expected.

**Interfaces:**
- Consumes: all previous tasks.
- Produces: working tree verified on MySQL with all tests passing.

- [ ] **Step 1: Start MySQL**

Run:

```bash
docker compose up -d
```

Expected: container `saludbot-mysql` running.

- [ ] **Step 2: Apply migrations**

Run:

```bash
.venv/bin/python manage.py migrate
```

Expected: applies migrations through `gestion.0009_backfill_registro_contacto`.

- [ ] **Step 3: Run full test suite**

Run:

```bash
.venv/bin/python manage.py test
```

Expected: all tests pass.

- [ ] **Step 4: Manual browser smoke test**

Run:

```bash
.venv/bin/python manage.py runserver
```

Expected: server starts. In the browser, use host `gestion.localhost` and verify:

- Selector detail modal opens as a fragment, shows vertical identity, semantic buttons and icons.
- After making one selector decision and closing the modal, selector table counts and rows refresh.
- If a fragment request redirects to login or `sin-acceso`, the full page is not injected into the dialog.
- Comunicador modal shows editable WhatsApp body with greeting and closing outside the textarea.
- WhatsApp opens in a new tab or exposes a manual link when blocked.
- Historial de comunicaciones increments once per non-idempotent action and remains visible for read-only roles.

- [ ] **Step 5: Final commit if verification changes docs or tests**

If manual verification caused a small correction, commit it:

```bash
git add gestion static docs
git commit -m "fix: ajusta verificacion de mejoras ui"
```

If there were no changes, do not create an empty commit.

---

## Self-Review

**Spec coverage:**  
Bloque 1 is covered by Task 1. Bloque 2 is covered by Task 1. Bloque 3 is covered by Task 2. Bloque 4 is covered by Tasks 3 and 4. Bloque 5 is covered by Tasks 5 and 6. Consequences and deployment notes are covered by Task 7. Full verification is covered by Task 8.

**Placeholder scan:**  
The plan contains exact paths, commands, expected results and concrete code snippets. It does not use open-ended placeholder instructions.

**Type consistency:**  
`PlantillaWhatsapp.obtener_cuerpo_activo`, `armar_mensaje_whatsapp`, `url_whatsapp_para_gestion`, `Gestion.url_whatsapp(cuerpo=None)`, `RegistroContacto.Canal`, `registrar_click_whatsapp(..., mensaje="")`, `registros_contacto` and `whatsapp_url` are introduced before later tasks consume them.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-26-mejoras-ui-seleccion.md`. Two execution options:

**1. Subagent-Driven (recommended)** - dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** - execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
