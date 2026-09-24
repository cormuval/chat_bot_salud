# Motivos, categoria Receta y alertas de seguridad — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Renombrar/ampliar los botones de motivo con la categoria "Receta", darle a Receta una rama acortada (sin alerta de urgencia, con pregunta de medicamento en vez de sintomas), y sumar a la tarjeta de urgencia el signo de ACV y la linea de salud mental *4141.

**Architecture:** Todo el flujo vive en `static/js/saludbot.js` (arreglo `steps` recorrido por indice; presentacion en `askCurrentStep`; ramificacion en `submitValue`). Los cambios son de contenido (`quickActions`, `renderUrgencyWarning`) y de una rama condicional para Receta (deteccion + flag `state.esReceta` + prompt/validacion condicionales del paso de detalle + salto de la tarjeta de urgencia). No hay cambios de backend ni de modelo. Las pruebas siguen la tecnica del repo: leer `saludbot.js` como texto y afirmar sobre contenido y construcciones (`SaludBotScriptTests`).

**Tech Stack:** JavaScript vanilla (sin build, sin arnes de test JS), Django test runner contra MySQL 8.4, plantillas Django.

## Global Constraints

- Codigo, comentarios y mensajes de commit en espanol, **sin tildes en identificadores**. Textos de UI (strings) si llevan tildes/emoji: no tocar esa convencion.
- Sin emojis en los mensajes de commit.
- Tests con el runner de Django, **no** SQLite ni pytest. Los tests de este plan son `SimpleTestCase` (leen `saludbot.js` como texto, sin BD) y corren aunque Docker/MySQL este caido. Comando por clase: `.venv/bin/python manage.py test solicitudes.tests.SaludBotScriptTests -v 2`.
- **No** se modifica el modelo `Solicitud` ni `solicitudes/views.py`. El backend ya acepta cualquier `motivo`/`detalle_motivo` de texto (no hay enum de motivos).
- **No** se toca el archivo en desuso `solicitudes/templates/solicitudes/chatbot.html` ni `solicitudes/static/solicitudes/chatbot.js`.
- Cada commit termina con las lineas de atribucion:
  ```
  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_0125u967AuBBEDP1JHij8tg5
  ```
- El comportamiento de ruteo (rama Receta) y el visual no tienen arnes JS: se prueban por asercion sobre el fuente y se verifican manualmente. Cada tarea con verificacion manual la deja anotada.

## File Structure

- Modify: `static/js/saludbot.js` — botones de motivo, tarjeta de urgencia y rama de Receta.
- Modify: `solicitudes/tests.py` — clase `SaludBotScriptTests` (agregar 3 tests).
- Sin cambios: `solicitudes/views.py`, `solicitudes/models.py`.

---

### Task 1: Botones de motivo (renombrar Fiebre, agregar Receta)

**Files:**
- Modify: `static/js/saludbot.js` (funcion `quickActions()`)
- Test: `solicitudes/tests.py` (clase `SaludBotScriptTests`)

**Interfaces:**
- Consumes: nada de tareas previas.
- Produces: el arreglo de `quickActions()` incluye `"Receta"` como ultima etiqueta y `"Fiebre"` en vez de `"Tengo Fiebre"`.

- [ ] **Step 1: Escribir el test (falla primero)**

Agregar a `SaludBotScriptTests` en `solicitudes/tests.py`:

```python
    def test_botones_de_motivo_renombran_fiebre_y_agregan_receta(self):
        script = Path(settings.BASE_DIR, "static", "js", "saludbot.js").read_text(encoding="utf-8")
        quick = script[script.index("function quickActions()"):script.index("function renderOptionButtons(")]

        self.assertIn('"Fiebre"', quick)
        self.assertNotIn('"Tengo Fiebre"', quick)
        self.assertIn('"Receta"', quick)
        # Receta va al final, despues de "Otros motivos".
        self.assertLess(quick.index('"Otros motivos"'), quick.index('"Receta"'))
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/python manage.py test solicitudes.tests.SaludBotScriptTests.test_botones_de_motivo_renombran_fiebre_y_agregan_receta -v 2`
Expected: FAIL (hoy la lista tiene `"Tengo Fiebre"` y no tiene `"Receta"`).

- [ ] **Step 3: Actualizar la lista de `quickActions()`**

En `static/js/saludbot.js`, reemplazar el arreglo `actions` dentro de `quickActions()` por:

```js
    const actions = [
      "Fiebre",
      "Dolor o malestar",
      "Problemas respiratorios",
      "Vómitos o diarrea",
      "Problemas al orinar",
      "Otros motivos",
      "Receta",
    ];
```

- [ ] **Step 4: Correr el test para verificar que pasa**

Run: `.venv/bin/python manage.py test solicitudes.tests.SaludBotScriptTests.test_botones_de_motivo_renombran_fiebre_y_agregan_receta -v 2`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add static/js/saludbot.js solicitudes/tests.py
git commit -F - <<'EOF'
Renombra Fiebre y agrega el boton Receta en los motivos

Cambia "Tengo Fiebre" por "Fiebre" y suma "Receta" como ultimo boton de motivo.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0125u967AuBBEDP1JHij8tg5
EOF
```

---

### Task 2: Alerta de urgencia — signo de ACV y linea de salud mental

**Files:**
- Modify: `static/js/saludbot.js` (funcion `renderUrgencyWarning()`)
- Test: `solicitudes/tests.py` (clase `SaludBotScriptTests`)

**Interfaces:**
- Consumes: nada de tareas previas.
- Produces: la tarjeta de urgencia incluye el item de ACV y la linea *4141.

- [ ] **Step 1: Escribir el test (falla primero)**

Agregar a `SaludBotScriptTests`:

```python
    def test_alerta_urgencia_incluye_acv_y_salud_mental(self):
        script = Path(settings.BASE_DIR, "static", "js", "saludbot.js").read_text(encoding="utf-8")
        card = script[script.index("function renderUrgencyWarning()"):script.index("function showUrgencyWarning()")]

        self.assertIn("Problemas o dificultad para hablar (posible ACV)", card)
        self.assertIn("*4141", card)
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/python manage.py test solicitudes.tests.SaludBotScriptTests.test_alerta_urgencia_incluye_acv_y_salud_mental -v 2`
Expected: FAIL (hoy no hay item de ACV ni linea *4141).

- [ ] **Step 3: Agregar el item de ACV y la linea de salud mental**

En `static/js/saludbot.js`, en `renderUrgencyWarning()`:

Agregar el item de ACV al final de la lista `<ul>`, despues de `<li>Debilidad repentina de un brazo o una pierna</li>`:

```js
          <li>Problemas o dificultad para hablar (posible ACV)</li>
```

Y agregar la linea de salud mental como un `<p>` nuevo, justo despues del `<p>` que termina en "...solicita una ambulancia al número 131." y antes del `<div class="summary-actions urgency-actions">`:

```js
        <p>Si tienes pensamientos de hacerte daño o quitarte la vida, llama al Fono de prevención del suicidio *4141 (gratuito) o acude al servicio de urgencia más cercano.</p>
```

- [ ] **Step 4: Correr el test para verificar que pasa**

Run: `.venv/bin/python manage.py test solicitudes.tests.SaludBotScriptTests.test_alerta_urgencia_incluye_acv_y_salud_mental -v 2`
Expected: PASS.

- [ ] **Step 5: Verificacion manual anotada**

En `runserver`, elegir un motivo clinico (p. ej. "Fiebre"): la tarjeta de urgencia debe listar "Problemas o dificultad para hablar (posible ACV)" y mostrar la linea de salud mental con *4141. Anotar en el PR.

- [ ] **Step 6: Commit**

```bash
git add static/js/saludbot.js solicitudes/tests.py
git commit -F - <<'EOF'
Agrega signo de ACV y linea de salud mental a la alerta de urgencia

Suma "Problemas o dificultad para hablar (posible ACV)" a la lista de sintomas
de alarma y una linea de advertencia de salud mental con el Fono de prevencion
del suicidio *4141, dentro de la misma tarjeta de urgencia.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0125u967AuBBEDP1JHij8tg5
EOF
```

---

### Task 3: Rama de Receta (sin urgencia, pregunta de medicamento)

**Files:**
- Modify: `static/js/saludbot.js` (`state`, helper `esMotivoReceta`, paso `detalle_sintomas`, resolucion de prompt en `askCurrentStep`, rama en `submitValue`, reset en `restart`/`resetByInactivity`)
- Test: `solicitudes/tests.py` (clase `SaludBotScriptTests`)

**Interfaces:**
- Consumes: el boton `Receta` de Task 1 (el usuario lo dispara), pero la logica funciona sobre el valor del motivo, no depende de Task 1 tecnicamente.
- Produces: helper `esMotivoReceta(valor)` -> booleano; flag `state.esReceta`; el paso `detalle_sintomas` con `prompt` como funcion (condicional) y `validate` condicional; `askCurrentStep` resuelve `step.prompt` cuando es funcion.

- [ ] **Step 1: Escribir el test (falla primero)**

Agregar a `SaludBotScriptTests`:

```python
    def test_rama_receta_omite_urgencia_y_pregunta_medicamento(self):
        script = Path(settings.BASE_DIR, "static", "js", "saludbot.js").read_text(encoding="utf-8")

        self.assertIn("function esMotivoReceta(", script)
        self.assertIn("state.esReceta", script)
        self.assertIn("medicamento(s) necesitas repetir", script)
        # askCurrentStep resuelve prompt cuando es funcion (para el detalle condicional).
        self.assertIn('typeof step.prompt === "function"', script)
        # En submitValue, tras el motivo, Receta salta la tarjeta de urgencia.
        submit = script[script.index("function submitValue("):script.index("function handlePhotoFile(")]
        self.assertIn("state.esReceta", submit)
        self.assertIn("showUrgencyWarning()", submit)
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/python manage.py test solicitudes.tests.SaludBotScriptTests.test_rama_receta_omite_urgencia_y_pregunta_medicamento -v 2`
Expected: FAIL (no existe `esMotivoReceta` ni `state.esReceta`).

- [ ] **Step 3: Agregar el flag al `state` y el helper `esMotivoReceta`**

En `static/js/saludbot.js`, agregar `esReceta: false,` al objeto `state`:

```js
  const state = {
    index: 0,
    data: {},
    selectedCentroName: centroInicial,
    waiting: false,
    complete: false,
    submitting: false,
    esReceta: false,
  };
```

Y agregar el helper junto a los otros helpers de pasos (por ejemplo, despues de `function minLength(message, length) { ... }`):

```js
  function esMotivoReceta(valor) {
    return String(valor).trim().toLowerCase() === "receta";
  }
```

- [ ] **Step 4: Hacer condicional el paso `detalle_sintomas`**

En `static/js/saludbot.js`, reemplazar el objeto de paso `detalle_sintomas` completo por:

```js
    {
      field: "detalle_sintomas",
      prompt() {
        if (state.esReceta) {
          return "¿Qué medicamento(s) necesitas repetir? Indica el nombre y la dosis si la conoces.";
        }
        return `Gracias. Para ayudarte mejor, cuéntanos un poco más:
* ¿Qué síntomas tienes?
* ¿Cuándo comenzaron?
* ¿Han empeorado, mejorado o siguen igual?
* ¿Has recibido atención médica por este problema?`;
      },
      validate(value) {
        if (state.esReceta) {
          return value.trim().length >= 3
            ? null
            : "Indica el medicamento que necesitas repetir (al menos 3 caracteres).";
        }
        return value.trim().length >= 20
          ? null
          : "Describe tus sintomas con al menos 20 caracteres para orientar mejor la atencion.";
      },
    },
```

- [ ] **Step 5: Resolver `step.prompt` cuando es funcion, en `askCurrentStep`**

En `static/js/saludbot.js`, en `askCurrentStep`, en el tramo generico que arma el prompt (el que empieza con `let prompt = step.prompt;`), cambiar la primera linea para soportar prompt-funcion:

```js
    let prompt = typeof step.prompt === "function" ? step.prompt() : step.prompt;
    if (step.options) {
      prompt = `${formatPromptText(prompt)}${renderOptionButtons(step.options)}`;
    } else {
      prompt = formatPromptText(prompt);
    }

    showTyping(() => addMessage(prompt, "bot", { html: true }));
```

- [ ] **Step 6: Ramificar en `submitValue` tras el motivo**

En `static/js/saludbot.js`, en `submitValue`, reemplazar el bloque que va desde `state.data[step.field] = ...` hasta el `if (step.field === "motivo") { showUrgencyWarning(); return; }` por:

```js
    state.data[step.field] = step.transform ? step.transform(value) : value.trim();
    if (step.field === "centro_salud") {
      state.selectedCentroName = displayValue;
    }
    if (step.field === "motivo") {
      state.esReceta = esMotivoReceta(value);
    }
    state.index += 1;

    if (step.field === "motivo") {
      if (state.esReceta) {
        askCurrentStep();
      } else {
        showUrgencyWarning();
      }
      return;
    }

    askCurrentStep();
```

- [ ] **Step 7: Resetear `esReceta` al reiniciar la conversacion**

En `static/js/saludbot.js`, agregar `state.esReceta = false;` en `restart()` y en `resetByInactivity()`, junto a los otros reseteos de estado (donde se hace `state.submitting = false;`), para que una nueva conversacion no herede la rama de Receta.

- [ ] **Step 8: Correr el test para verificar que pasa**

Run: `.venv/bin/python manage.py test solicitudes.tests.SaludBotScriptTests.test_rama_receta_omite_urgencia_y_pregunta_medicamento -v 2`
Expected: PASS.

- [ ] **Step 9: Verificacion manual anotada**

En `runserver`: elegir "Receta" NO debe mostrar la tarjeta de urgencia y debe preguntar por el medicamento; completar el flujo (CESFAM, RUT, nombre, edad, telefono, credencial, neuro, resumen) y enviar; confirmar que la solicitud guarda `motivo="Receta"` y el medicamento en el detalle. Elegir un motivo clinico (p. ej. "Fiebre") SI debe mostrar la tarjeta de urgencia y pedir sintomas (min 20). Anotar en el PR.

- [ ] **Step 10: Commit**

```bash
git add static/js/saludbot.js solicitudes/tests.py
git commit -F - <<'EOF'
Agrega la rama de Receta al flujo del chatbot

Receta (motivo normalizado "receta") toma un camino acortado: no muestra la
tarjeta de urgencia y el paso de detalle pregunta por el medicamento en vez de
sintomas (validacion relajada). El resto del flujo queda igual. Se agrega el
flag state.esReceta, el helper esMotivoReceta, prompt-funcion en askCurrentStep
y el reseteo del flag al reiniciar.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0125u967AuBBEDP1JHij8tg5
EOF
```

---

### Task 4: Suite completa y verificacion final

**Files:**
- Sin cambios de codigo; corrida completa y notas de cierre.

- [ ] **Step 1: Correr toda la suite de solicitudes**

Run: `.venv/bin/python manage.py test solicitudes -v 2`
Expected: PASS (incluye `test_endpoint_acepta_payload_saludbot`, que confirma que el endpoint sigue aceptando el payload del saludbot sin cambios de backend).

Si Docker/MySQL esta caido, correr al menos la clase sin BD:
`.venv/bin/python manage.py test solicitudes.tests.SaludBotScriptTests -v 2` (debe quedar verde) y dejar anotado que la suite con BD queda pendiente por infraestructura.

- [ ] **Step 2: Correr la suite completa del proyecto (si hay MySQL)**

Run: `.venv/bin/python manage.py test`
Expected: PASS.

- [ ] **Step 3: Checklist de verificacion manual del PR**

Confirmar en `runserver` y dejar anotado en el PR: (1) boton "Receta" al final y "Fiebre" renombrado; (2) Receta no muestra urgencia y pregunta por medicamento; (3) motivo clinico si muestra urgencia con ACV y linea *4141; (4) el flujo de Receta completa y guarda `motivo="Receta"`.

---

## Self-Review

**Spec coverage:**
- Renombrar Fiebre + agregar Receta al final → Task 1. ✔
- Rama de Receta (sin urgencia, pregunta de medicamento, resto igual) → Task 3. ✔
- Signo de ACV en la alerta → Task 2. ✔
- Linea de salud mental *4141 en la tarjeta de urgencia → Task 2. ✔
- Sin cambios de modelo/backend; motivo sigue siendo texto → respetado (ninguna tarea toca backend). ✔
- Consecuencia aceptada (la linea *4141 no aparece en Receta porque Receta omite la tarjeta) → coherente con Task 2 + Task 3 (la linea vive en `renderUrgencyWarning`, que Receta no invoca). ✔

**Placeholder scan:** sin TBD/TODO; cada paso muestra codigo o comando concreto. ✔

**Type consistency:** `esMotivoReceta(valor)` (Task 3) usado con ese nombre en `submitValue`; `state.esReceta` (Task 3) fijado en `submitValue`, leido en el paso `detalle_sintomas` y en `askCurrentStep` (indirecto via prompt-funcion); `typeof step.prompt === "function"` (Task 3) coincide con el paso `detalle_sintomas` que define `prompt()` como metodo. Boundaries de los tests (`renderOptionButtons`, `showUrgencyWarning`, `handlePhotoFile`) existen en el archivo actual. ✔
