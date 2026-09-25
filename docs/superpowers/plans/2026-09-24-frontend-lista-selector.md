# Revision de frontend de la lista del selector — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que la tabla del selector se vea como tabla a 100% de zoom en todas las pestañas (columnas fijas, Motivo truncado a 1 linea), con pestaña activa marcada, tarjeta de cupos compacta y Motivo en 2 lineas en movil.

**Architecture:** Solo templates + CSS del modulo `gestion`. La tabla del selector recibe una clase modificadora `data-table--selector` y un `<colgroup>`; todo el CSS nuevo se acota a esa clase para no tocar las otras `.data-table` (comunicador, perfiles, palabras). Se arregla `.truncate` (hoy sobre un `<span>` inline, nunca trunco). Sin cambios de vistas ni logica.

**Tech Stack:** Plantillas Django, CSS plano (`static/css/gestion.css`), runner de Django contra MySQL 8.4.

## Global Constraints

- Codigo, comentarios y commits en espanol, **sin tildes en identificadores**; strings de UI con tildes se mantienen. Sin emojis en commits.
- Tests con el runner de Django contra **MySQL 8.4** (Docker arriba), no SQLite ni pytest. Comando: `.venv/bin/python manage.py test gestion`.
- **No** tocar las otras tablas `.data-table` (comunicador, perfiles, palabras): todas las reglas nuevas de tabla se acotan a `.data-table--selector`.
- **No** cambiar vistas, URLs ni logica; los `href` de las pestañas (`/selector/`, `?seccion=decididas`, `?seccion=no_aplica`) y el form POST de cupos no cambian.
- Anchos de columna: Paciente 18%, Centro 16%, Prioridad 11rem, Motivo sin ancho (absorbe el resto), Fecha 9rem, Correccion 12rem, Abrir 5rem.
- Se mantiene la columna "Abrir" y el `overflow-wrap: anywhere` de las celdas (con anchos fijos solo corta palabras que no caben).
- Usar los tokens existentes (`--space-*`, `--primary`, `--line`, `--surface`).
- Vistas de gestion se prueban con `@override_settings(ALLOWED_HOSTS=["gestion.localhost", "testserver"], GESTION_HOST="gestion.localhost")`, `force_login` y rutas literales con `HTTP_HOST="gestion.localhost"`.
- Cada commit termina con:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_0125u967AuBBEDP1JHij8tg5
  ```

## File Structure

- Modify: `gestion/templates/gestion/_tabla_selector.html` — clase modificadora, `<colgroup>`, `title` del Motivo, pestañas.
- Modify: `gestion/templates/gestion/selector_lista.html` — markup de la tarjeta de cupos.
- Modify: `static/css/gestion.css` — layout fijo acotado, `.truncate`, `.tab-nav`/activo, cupos, movil.
- Modify: `gestion/tests.py` — clase nueva `ListaSelectorFrontendTests`.

---

### Task 1: Tabla del selector con columnas fijas y Motivo truncado

**Files:**
- Modify: `gestion/templates/gestion/_tabla_selector.html`
- Modify: `static/css/gestion.css`
- Test: `gestion/tests.py` (clase nueva `ListaSelectorFrontendTests`)

**Interfaces:**
- Produces: clase `data-table--selector` en la tabla; `<col class="col-paciente|col-centro|col-prioridad|col-motivo|col-fecha|col-correccion|col-abrir">`; clase `ListaSelectorFrontendTests` (con `setUp` de selector logueado) que las Tasks 2 y 3 extienden.

- [ ] **Step 1: Escribir los tests (fallan primero)**

Agregar al final de `gestion/tests.py`:

```python
@override_settings(ALLOWED_HOSTS=["gestion.localhost", "testserver"], GESTION_HOST="gestion.localhost")
class ListaSelectorFrontendTests(TestCase):
    CSS = Path(__file__).resolve().parent.parent / "static" / "css" / "gestion.css"

    def setUp(self):
        self.centro = Centro.objects.get(pk=620)
        self.user = User.objects.create_user("sel@x.cl", "sel@x.cl")
        PerfilUsuario.objects.create(
            usuario=self.user, rol=PerfilUsuario.Rol.SELECTOR, centro=self.centro
        )
        self.client.force_login(self.user)

    def _get(self, url):
        return self.client.get(url, HTTP_HOST="gestion.localhost")

    def test_tabla_tiene_clase_selector_y_colgroup(self):
        r = self._get("/selector/")
        self.assertContains(r, 'class="data-table data-table--selector"')
        self.assertContains(r, "<colgroup>")
        self.assertContains(r, 'class="col-motivo"')
        self.assertNotContains(r, 'class="col-correccion"')

    def test_decididas_agrega_col_correccion(self):
        r = self._get("/selector/?seccion=decididas")
        self.assertContains(r, 'class="col-correccion"')

    def test_motivo_trunca_con_texto_completo_en_title(self):
        crear_solicitud_base(
            centro_salud=self.centro,
            detalle_motivo="Dolor de cabeza intenso hace tres dias",
        )
        r = self._get("/selector/")
        self.assertContains(
            r, 'class="truncate" title="Dolor de cabeza intenso hace tres dias"'
        )

    def test_css_layout_fijo_acotado_y_truncate(self):
        css = self.CSS.read_text(encoding="utf-8")
        self.assertIn(".data-table--selector { table-layout: fixed; }", css)
        self.assertIn(".data-table--selector .col-paciente { width: 18%; }", css)
        self.assertIn(
            ".truncate { display: block; max-width: 100%; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }",
            css,
        )
        self.assertIn("-webkit-line-clamp: 2", css)
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `.venv/bin/python manage.py test gestion.tests.ListaSelectorFrontendTests -v 2`
Expected: FAIL (no existe la clase modificadora, el colgroup, el title ni las reglas CSS).

- [ ] **Step 3: Template de la tabla**

En `gestion/templates/gestion/_tabla_selector.html`:

(a) Cambiar la apertura de la tabla y agregar el `<colgroup>` justo despues:

```html
  <table class="data-table data-table--selector" data-gestion-list>
    <colgroup>
      <col class="col-paciente">
      {% if mostrar_columna_centro %}<col class="col-centro">{% endif %}
      <col class="col-prioridad">
      <col class="col-motivo">
      <col class="col-fecha">
      {% if seccion == "decididas" %}<col class="col-correccion">{% endif %}
      <col class="col-abrir">
    </colgroup>
```

(b) Reemplazar la celda del Motivo por:

```html
          <td data-label="Motivo"><span class="truncate" title="{{ gestion.solicitud.detalle_motivo|default:gestion.solicitud.motivo }}">{{ gestion.solicitud.detalle_motivo|default:gestion.solicitud.motivo }}</span></td>
```

- [ ] **Step 4: CSS de tabla y truncate**

En `static/css/gestion.css`:

(a) Reemplazar la linea de `.truncate` (hoy `.truncate { max-width: 34rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }`) por:

```css
.truncate { display: block; max-width: 100%; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
```

(b) Justo despues de la linea `.data-table th, .data-table td { ... }`, agregar:

```css
/* Tabla del selector: columnas de ancho fijo; el Motivo (sin ancho) absorbe el
   resto y trunca, asi un texto largo no aplasta ni desborda. */
.data-table--selector { table-layout: fixed; }
.data-table--selector .col-paciente { width: 18%; }
.data-table--selector .col-centro { width: 16%; }
.data-table--selector .col-prioridad { width: 11rem; }
.data-table--selector .col-fecha { width: 9rem; }
.data-table--selector .col-correccion { width: 12rem; }
.data-table--selector .col-abrir { width: 5rem; }
```

(c) Dentro del `@media (max-width: 900px)`, reemplazar la linea `.truncate { white-space: normal; }` por:

```css
  .data-table--selector colgroup { display: none; }
  .truncate { white-space: normal; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
```

- [ ] **Step 5: Correr los tests para verificar que pasan**

Run: `.venv/bin/python manage.py test gestion.tests.ListaSelectorFrontendTests -v 2`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add gestion/templates/gestion/_tabla_selector.html static/css/gestion.css gestion/tests.py
git commit -F - <<'EOF'
Da columnas fijas a la tabla del selector y trunca el Motivo

La tabla del selector usa table-layout fixed con colgroup (acotado a
.data-table--selector) para que un Motivo largo no aplaste ni desborde, y
.truncate pasa a display block para truncar de verdad (sobre un span inline
nunca truncaba). Texto completo en el title; 2 lineas en movil.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0125u967AuBBEDP1JHij8tg5
EOF
```

---

### Task 2: Pestañas con estado activo

**Files:**
- Modify: `gestion/templates/gestion/_tabla_selector.html` (nav de secciones)
- Modify: `static/css/gestion.css`
- Test: `gestion/tests.py` (agregar a `ListaSelectorFrontendTests`)

**Interfaces:**
- Consumes: `ListaSelectorFrontendTests` (Task 1). Variable de contexto `seccion` (existente: `"pendientes"`, `"decididas"` o `"no_aplica"`).

- [ ] **Step 1: Escribir los tests (fallan primero)**

Agregar a `ListaSelectorFrontendTests`:

```python
    def test_pestana_activa_pendientes(self):
        r = self._get("/selector/")
        self.assertContains(r, 'class="tab-nav"')
        self.assertContains(
            r, 'class="tab-link is-active" href="/selector/" aria-current="page"'
        )
        self.assertContains(r, 'class="tab-link" href="/selector/?seccion=decididas"')

    def test_pestana_activa_decididas(self):
        r = self._get("/selector/?seccion=decididas")
        self.assertContains(
            r,
            'class="tab-link is-active" href="/selector/?seccion=decididas" aria-current="page"',
        )
        self.assertContains(r, 'class="tab-link" href="/selector/"')

    def test_css_pestana_activa(self):
        css = self.CSS.read_text(encoding="utf-8")
        self.assertIn(".tab-nav {", css)
        self.assertIn(".tab-link.is-active {", css)
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `.venv/bin/python manage.py test gestion.tests.ListaSelectorFrontendTests -v 2`
Expected: FAIL en los 3 tests nuevos.

- [ ] **Step 3: Template de las pestañas**

En `gestion/templates/gestion/_tabla_selector.html`, reemplazar el bloque `<nav class="gestion-nav" aria-label="Secciones del selector"> ... </nav>` completo por (mantener cada `<a>` en una linea, con los atributos en este orden):

```html
  <nav class="tab-nav" aria-label="Secciones del selector">
    <a class="tab-link{% if seccion == "pendientes" %} is-active{% endif %}" href="{% url 'gestion:selector_lista' %}"{% if seccion == "pendientes" %} aria-current="page"{% endif %}>Pendientes <strong>{{ conteos_selector.pendientes }}</strong></a>
    <a class="tab-link{% if seccion == "decididas" %} is-active{% endif %}" href="{% url 'gestion:selector_lista' %}?seccion=decididas"{% if seccion == "decididas" %} aria-current="page"{% endif %}>Decididas corregibles <strong>{{ conteos_selector.decididas }}</strong></a>
    {% if mostrar_no_aplica %}
      <a class="tab-link{% if seccion == "no_aplica" %} is-active{% endif %}" href="{% url 'gestion:selector_lista' %}?seccion=no_aplica"{% if seccion == "no_aplica" %} aria-current="page"{% endif %}>No aplica <strong>{{ conteos_selector.no_aplica }}</strong></a>
    {% endif %}
  </nav>
```

- [ ] **Step 4: CSS de pestañas**

En `static/css/gestion.css`, justo despues del bloque `.gestion-nav a, .tab-link { ... }`, agregar:

```css
/* Pestañas de seccion del selector (distintas del nav principal). */
.tab-nav {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
  background: var(--surface);
  border-bottom: 1px solid var(--line);
}
.tab-link.is-active {
  background: var(--primary);
  border-color: var(--primary);
  color: #FFFFFF;
}
```

- [ ] **Step 5: Correr los tests para verificar que pasan**

Run: `.venv/bin/python manage.py test gestion.tests.ListaSelectorFrontendTests -v 2`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add gestion/templates/gestion/_tabla_selector.html static/css/gestion.css gestion/tests.py
git commit -F - <<'EOF'
Marca la pestaña activa del selector

Las pestañas de seccion pasan a su propia clase tab-nav (antes reusaban el
estilo del nav principal) y la seccion actual lleva is-active y
aria-current="page".

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0125u967AuBBEDP1JHij8tg5
EOF
```

---

### Task 3: Tarjeta de cupos compacta y espaciado

**Files:**
- Modify: `gestion/templates/gestion/selector_lista.html` (bloque de cupos)
- Modify: `static/css/gestion.css` (bloque `.cupos-selector` / `.cupo-card`)
- Test: `gestion/tests.py` (agregar a `ListaSelectorFrontendTests`)

**Interfaces:**
- Consumes: `ListaSelectorFrontendTests` (Task 1); contexto `cupos`/`puede_cargar_cupos` (existente); `CupoDiario` (existente).

- [ ] **Step 1: Escribir los tests (fallan primero)**

Agregar a `ListaSelectorFrontendTests`:

```python
    def test_cupo_muestra_numero_grande(self):
        from gestion.models import CupoDiario
        CupoDiario.objects.create(
            centro=self.centro, fecha=timezone.localdate(), cupos_iniciales=18
        )
        r = self._get("/selector/")
        self.assertContains(r, '<span class="cupo-card__numero">18</span>')
        self.assertContains(r, "Cupos del dia")
        self.assertContains(r, 'name="cupos_iniciales"')

    def test_css_cupos_no_se_estira(self):
        css = self.CSS.read_text(encoding="utf-8")
        self.assertIn("repeat(auto-fill, minmax(260px, 360px))", css)
        self.assertIn(".cupo-card__numero {", css)
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `.venv/bin/python manage.py test gestion.tests.ListaSelectorFrontendTests -v 2`
Expected: FAIL en los 2 tests nuevos.

- [ ] **Step 3: Markup de la tarjeta**

En `gestion/templates/gestion/selector_lista.html`, reemplazar el bloque `<div class="cupo-card__info"> ... </div>` por:

```html
      <div class="cupo-card__info">
        <strong class="cupo-card__centro">{{ fila.centro }}</strong>
        {% if fila.disponibles is None %}
          <span class="cupo-card__disponibles">Sin cargar</span>
        {% else %}
          <span class="cupo-card__disponibles"><span class="cupo-card__numero">{{ fila.disponibles }}</span> / {{ fila.iniciales }} disponibles</span>
        {% endif %}
      </div>
```

- [ ] **Step 4: CSS de cupos**

En `static/css/gestion.css`, reemplazar las reglas `.cupos-selector`, `.cupos-selector__titulo` y `.cupos-selector__grid` por:

```css
.cupos-selector {
  margin: 0 0 var(--space-4);
}
.cupos-selector__titulo {
  margin: 0 0 var(--space-2);
  font-size: 1rem;
}
.cupos-selector__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 360px));
  gap: var(--space-3);
}
```

y agregar despues de `.cupo-card__disponibles { ... }`:

```css
.cupo-card__info {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}
.cupo-card__numero {
  font-size: 1.8rem;
  line-height: 1;
}
```

- [ ] **Step 5: Correr los tests para verificar que pasan**

Run: `.venv/bin/python manage.py test gestion.tests.ListaSelectorFrontendTests -v 2`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add gestion/templates/gestion/selector_lista.html static/css/gestion.css gestion/tests.py
git commit -F - <<'EOF'
Compacta la tarjeta de cupos del selector

La grilla de cupos usa auto-fill con ancho acotado (una sola tarjeta ya no se
estira a todo el ancho), los disponibles se muestran como numero grande y el
espaciado usa los tokens del modulo.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0125u967AuBBEDP1JHij8tg5
EOF
```

---

### Task 4: Suite completa y verificacion final

- [ ] **Step 1:** Run `.venv/bin/python manage.py test gestion -v 2` — Expected: PASS (incluye los tests existentes del selector: hrefs `?seccion=decididas`, "Cupos del dia", render de tarjetas).
- [ ] **Step 2:** Run `.venv/bin/python manage.py test` — Expected: PASS.
- [ ] **Step 3: Checklist manual del PR** (cambio visual): a 100% de zoom, Pendientes y Decididas corregibles se ven como tabla sin desbordar; nombres legibles (sin cortes letra por letra); Motivo en 1 linea con "…" y texto completo al pasar el mouse; la pestaña activa se distingue; la tarjeta de cupos no ocupa todo el ancho; a zoom alto / movil, modo tarjeta con Motivo en 2 lineas.

---

## Self-Review

**Spec coverage:** columnas fijas acotadas + colgroup condicional → Task 1; `.truncate` arreglado + title → Task 1; movil 2 lineas (+ ocultar colgroup) → Task 1; pestañas `tab-nav` + `is-active` + `aria-current` → Task 2; cupos `auto-fill` + numero grande → Task 3; espaciado con tokens → Task 3; otras `.data-table` intactas → todas las reglas acotadas a `.data-table--selector` o clases propias. ✔

**Placeholder scan:** sin TBD; cada paso trae codigo o comando concreto. ✔

**Type consistency:** clases `data-table--selector`, `col-*`, `tab-nav`, `is-active`, `cupo-card__numero` usadas igual en templates, CSS y tests; `ListaSelectorFrontendTests` definida en Task 1 y extendida en 2 y 3; el orden de atributos de las pestañas en el template (class, href, aria-current) coincide con las aserciones. ✔
