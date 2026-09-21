# Reordenamiento e integridad del flujo del chatbot — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reordenar y blindar el flujo conversacional del chatbot: T&C como primera pantalla, input bloqueado en pasos de botones, CESFAM antes de RUT/Nombre, paso de foto oculto tras flag y scroll anclado al inicio del mensaje del bot.

**Architecture:** Todo el flujo vive en un unico archivo cliente `static/js/saludbot.js` (un arreglo `steps` recorrido por indice, con presentacion en `askCurrentStep` y `showTyping`). Los cambios son de orden de pasos, de gate del input y de scroll dentro de ese archivo. No hay cambios de backend ni de modelo. Las pruebas siguen la tecnica ya usada en el repo: leer `saludbot.js` como texto y afirmar sobre el orden y la presencia de las construcciones (`SaludBotScriptTests`), mas la regresion de backend ya existente.

**Tech Stack:** JavaScript vanilla (sin build, sin arnes de test JS), Django test runner contra MySQL 8.4, plantillas Django.

## Global Constraints

- Codigo, comentarios y mensajes de commit en espanol, **sin tildes en identificadores**. Textos de UI (strings) si llevan tildes/emoji: no tocar esa convencion existente.
- Sin emojis en los mensajes de commit.
- Tests con el runner de Django contra MySQL 8.4, **no** SQLite ni pytest. Comando: `.venv/bin/python manage.py test solicitudes`.
- **No** se modifica el modelo `Solicitud`, `solicitudes/views.py` ni el modulo de gestion. El rechazo server-side de T&C ya existe (`Solicitud.clean()` lanza `ValidationError` si `acepta_terminos` es falso) y se conserva como regresion (`test_endpoint_rechaza_sin_terminos`).
- **No** se toca el archivo en desuso `solicitudes/templates/solicitudes/chatbot.html` ni `solicitudes/static/solicitudes/chatbot.js`.
- Cada commit termina con las lineas de atribucion:
  ```
  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_0125u967AuBBEDP1JHij8tg5
  ```
- El comportamiento puramente visual (gate del input, scroll) no tiene arnes JS: se prueba por asercion sobre el codigo fuente y se verifica manualmente. Cada tarea con verificacion manual la deja anotada.

## File Structure

- Modify: `static/js/saludbot.js` — todo el flujo (orden de `steps`, `start`, `askCurrentStep`, `showTyping`, `scrollToLatest`, flag de foto).
- Modify: `solicitudes/tests.py` — clase `SaludBotScriptTests` (actualizar 1 test, agregar 4).
- Sin cambios: `solicitudes/views.py`, `solicitudes/models.py`.

Orden objetivo del arreglo `steps`:
```
acepta_terminos -> motivo -> detalle_sintomas -> centro_salud -> rut -> nombre
   -> edad -> telefono -> credencial(si/no) -> foto(oculto) -> neuro(si/no) -> tipo -> otro
```

---

### Task 1: T&C como primera pantalla

Mueve `acepta_terminos` al inicio del arreglo `steps` (antes de `motivo`) y reestructura la apertura para que la conversacion abra con la tarjeta de terminos; el saludo con botones rapidos se muestra al llegar al paso `motivo`.

**Files:**
- Modify: `static/js/saludbot.js` (arreglo `steps`, `start()`, `askCurrentStep()`)
- Test: `solicitudes/tests.py` (clase `SaludBotScriptTests`)

**Interfaces:**
- Consumes: nada de tareas previas.
- Produces: el paso `motivo` pasa a llevar la marca `quick: true` y su render incluye el saludo + `quickActions()`. Las tareas siguientes asumen el orden `acepta_terminos` antes de `motivo` antes de `detalle_sintomas`.

- [ ] **Step 1: Actualizar el test de orden (falla primero)**

En `solicitudes/tests.py`, reemplazar por completo `test_terminos_se_piden_despues_del_aviso_de_urgencia` (dentro de `SaludBotScriptTests`) por:

```python
    def test_terminos_es_la_primera_pantalla(self):
        script = Path(settings.BASE_DIR, "static", "js", "saludbot.js").read_text(encoding="utf-8")

        terminos_index = script.index('field: "acepta_terminos"')
        motivo_index = script.index('field: "motivo"')
        sintomas_index = script.index('field: "detalle_sintomas"')

        self.assertLess(terminos_index, motivo_index)
        self.assertLess(motivo_index, sintomas_index)

    def test_apertura_presenta_terminos_antes_del_saludo(self):
        script = Path(settings.BASE_DIR, "static", "js", "saludbot.js").read_text(encoding="utf-8")

        # start() ya no publica el saludo directamente: presenta el paso actual
        # (terminos). El saludo vive en el render del paso motivo.
        start_body = script[script.index("function start()"):script.index("function showSummary()")]
        self.assertIn("askCurrentStep();", start_body)
        self.assertNotIn("Soy SaludBot", start_body)
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/python manage.py test solicitudes.tests.SaludBotScriptTests -v 2`
Expected: FAIL (`test_terminos_es_la_primera_pantalla` y `test_apertura_presenta_terminos_antes_del_saludo` fallan: hoy `motivo` va antes que `acepta_terminos` y `start()` publica el saludo).

- [ ] **Step 3: Reordenar los pasos y marcar `motivo`**

En `static/js/saludbot.js`, mover el objeto de paso `acepta_terminos` para que sea el **primer** elemento del arreglo `steps` (antes del paso `motivo`). El objeto que hoy es:

```js
    {
      field: "acepta_terminos",
      prompt: "Antes de continuar, debes aceptar los Terminos y Condiciones de uso de la plataforma.",
      type: "terms",
    },
```

queda como primer elemento del arreglo. El paso `motivo` (que hoy es el primero) queda en segundo lugar y se le agrega la marca `quick: true`:

```js
    {
      field: "motivo",
      prompt: "¿Por qué problema de salud necesitas consultar hoy?",
      quick: true,
      validate: minLength("Describe el motivo de consulta con al menos 3 caracteres.", 3),
    },
```

- [ ] **Step 4: Reestructurar `start()` y el render del paso `motivo`**

En `static/js/saludbot.js`, reemplazar la funcion `start()` completa por:

```js
  function start() {
    askCurrentStep();
    resetInactivityTimer();
  }
```

En `askCurrentStep()`, agregar el render especial del saludo para el paso `motivo`, junto a los otros casos especiales (`photo`, `terms`). Insertar este bloque **antes** del bloque `if (step.options)` / `let prompt = step.prompt;`:

```js
    if (step.quick) {
      const greetingName = userName ? `, ${escapeHtml(userName)}` : "";
      const saludo = `Hola 👋 Soy SaludBot${greetingName}, asistente virtual de salud familiar. Te ayudaré a solicitar una atención de salud médica y a recopilar información necesaria para que el equipo revise tu caso. ¿Qué problema de salud necesitas consultar hoy?`;
      showTyping(() => addMessage(`${saludo}${quickActions()}`, "bot", { html: true }));
      return;
    }
```

- [ ] **Step 5: Correr el test para verificar que pasa**

Run: `.venv/bin/python manage.py test solicitudes.tests.SaludBotScriptTests -v 2`
Expected: PASS.

- [ ] **Step 6: Verificacion manual anotada**

Levantar `runserver`, abrir el chatbot: la primera tarjeta debe ser Terminos y Condiciones; al aceptar, aparece el saludo con los botones rapidos y luego el flujo del motivo. Anotar el resultado en el PR.

- [ ] **Step 7: Commit**

```bash
git add static/js/saludbot.js solicitudes/tests.py
git commit -F - <<'EOF'
Pone los terminos y condiciones como primera pantalla del chatbot

El paso acepta_terminos pasa a ser el primero del flujo; start() presenta
la tarjeta de terminos y el saludo con botones rapidos se muestra recien en
el paso motivo, tras aceptar.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0125u967AuBBEDP1JHij8tg5
EOF
```

---

### Task 2: CESFAM antes de RUT y Nombre

Mueve el paso `centro_salud` para que se pregunte despues de `detalle_sintomas` y antes de `rut`.

**Files:**
- Modify: `static/js/saludbot.js` (arreglo `steps`)
- Test: `solicitudes/tests.py` (clase `SaludBotScriptTests`)

**Interfaces:**
- Consumes: orden de Task 1 (`acepta_terminos`, `motivo`, `detalle_sintomas` al inicio).
- Produces: `centro_salud` queda antes de `rut` y `nombre`.

- [ ] **Step 1: Escribir el test (falla primero)**

Agregar a `SaludBotScriptTests`:

```python
    def test_cesfam_se_pregunta_antes_del_rut_y_nombre(self):
        script = Path(settings.BASE_DIR, "static", "js", "saludbot.js").read_text(encoding="utf-8")

        centro_index = script.index('field: "centro_salud"')
        rut_index = script.index('field: "rut"')
        nombre_index = script.index('field: "nombre"')
        sintomas_index = script.index('field: "detalle_sintomas"')

        self.assertLess(sintomas_index, centro_index)
        self.assertLess(centro_index, rut_index)
        self.assertLess(centro_index, nombre_index)
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/python manage.py test solicitudes.tests.SaludBotScriptTests.test_cesfam_se_pregunta_antes_del_rut_y_nombre -v 2`
Expected: FAIL (hoy `centro_salud` esta despues de `rut` y `nombre`).

- [ ] **Step 3: Mover el paso `centro_salud`**

En `static/js/saludbot.js`, cortar el objeto de paso completo:

```js
    {
      field: "centro_salud",
      prompt: "Selecciona el CESFAM donde quieres orientar esta solicitud.",
      options: centrosSalud,
      validate(value) {
        return centrosSalud.some((centro) => centro.id === value)
          ? null
          : "Selecciona una opcion de CESFAM de la lista.";
      },
      display(value) {
        return centrosSalud.find((centro) => centro.id === value)?.nombre || value;
      },
    },
```

y pegarlo entre el paso `detalle_sintomas` y el paso `rut` (queda justo antes de `rut`). No cambia el contenido del objeto, solo su posicion.

- [ ] **Step 4: Correr el test para verificar que pasa**

Run: `.venv/bin/python manage.py test solicitudes.tests.SaludBotScriptTests.test_cesfam_se_pregunta_antes_del_rut_y_nombre -v 2`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add static/js/saludbot.js solicitudes/tests.py
git commit -F - <<'EOF'
Pregunta el CESFAM antes del RUT y el nombre

Mueve el paso centro_salud para que se responda tras el detalle de sintomas
y antes de los datos de identificacion.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0125u967AuBBEDP1JHij8tg5
EOF
```

---

### Task 3: Bloquear el input de texto en pasos de botones

En los pasos que se responden con botones (terminos, opciones), el campo de texto queda deshabilitado (visible pero gris); se reactiva en los pasos de texto libre.

**Files:**
- Modify: `static/js/saludbot.js` (nuevo helper `esPasoDeBotones`, `showTyping()`)
- Test: `solicitudes/tests.py` (clase `SaludBotScriptTests`)

**Interfaces:**
- Consumes: arreglo `steps` con `type`/`options` ya definidos.
- Produces: helper `esPasoDeBotones(step)` que devuelve `true` cuando el paso tiene `type` u `options`.

- [ ] **Step 1: Escribir el test (falla primero)**

Agregar a `SaludBotScriptTests`:

```python
    def test_input_se_bloquea_en_pasos_de_botones(self):
        script = Path(settings.BASE_DIR, "static", "js", "saludbot.js").read_text(encoding="utf-8")

        self.assertIn("function esPasoDeBotones(step)", script)
        # El gate se deriva del tipo de paso y se aplica al input y al boton.
        self.assertIn("const gate = esPasoDeBotones(steps[state.index]);", script)
        self.assertIn("input.disabled = gate;", script)
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/python manage.py test solicitudes.tests.SaludBotScriptTests.test_input_se_bloquea_en_pasos_de_botones -v 2`
Expected: FAIL (no existe `esPasoDeBotones`).

- [ ] **Step 3: Agregar el helper**

En `static/js/saludbot.js`, agregar la funcion cerca de los otros helpers de pasos (por ejemplo, justo despues de `function displayCondicion(value)`):

```js
  function esPasoDeBotones(step) {
    return Boolean(step && (step.type || step.options));
  }
```

- [ ] **Step 4: Aplicar el gate en `showTyping`**

En `static/js/saludbot.js`, dentro de `showTyping`, reemplazar el cuerpo del `window.setTimeout(...)` final por:

```js
    window.setTimeout(() => {
      row.remove();
      state.waiting = false;
      const gate = esPasoDeBotones(steps[state.index]);
      input.disabled = gate;
      submitButton.disabled = gate;
      callback();
      scrollToLatest();
      if (!gate) input.focus();
    }, 520);
```

(El paso que se esta presentando es `steps[state.index]`, porque `askCurrentStep` llama a `showTyping` antes de avanzar el indice. Para el paso de urgencia, `showUrgencyWarning` ya deja el input deshabilitado y no lo reactiva, asi que la tarjeta de urgencia tambien queda bloqueada.)

- [ ] **Step 5: Correr el test para verificar que pasa**

Run: `.venv/bin/python manage.py test solicitudes.tests.SaludBotScriptTests.test_input_se_bloquea_en_pasos_de_botones -v 2`
Expected: PASS.

- [ ] **Step 6: Verificacion manual anotada**

En `runserver`: durante la tarjeta de T&C, la seleccion de CESFAM y las preguntas si/no, el campo de texto debe verse gris y no aceptar escritura; en motivo, detalle, RUT, nombre, edad y telefono debe estar activo y con foco. Anotar en el PR.

- [ ] **Step 7: Commit**

```bash
git add static/js/saludbot.js solicitudes/tests.py
git commit -F - <<'EOF'
Bloquea el input de texto en los pasos de botones

Deriva el estado del campo de texto del tipo de paso: deshabilitado en
terminos y pasos de opciones, activo en los pasos de texto libre. Cierra la
via para evadir el gate de terminos escribiendo texto.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0125u967AuBBEDP1JHij8tg5
EOF
```

---

### Task 4: Ocultar el paso de foto tras un flag

Excluye el paso de foto de credencial del flujo mediante un flag, sin borrar el codigo. El backend ya tolera foto vacia (sin cambios).

**Files:**
- Modify: `static/js/saludbot.js` (nueva constante y `skip()` del paso de foto)
- Test: `solicitudes/tests.py` (clase `SaludBotScriptTests`)

**Interfaces:**
- Consumes: paso de foto existente (`field: "credencial_cuidador_discapacidad_foto"`, `type: "photo"`).
- Produces: constante `ADJUNTO_FOTO_HABILITADO` (booleano) que gobierna si el paso se muestra.

- [ ] **Step 1: Escribir el test (falla primero)**

Agregar a `SaludBotScriptTests`:

```python
    def test_paso_de_foto_oculto_por_flag(self):
        script = Path(settings.BASE_DIR, "static", "js", "saludbot.js").read_text(encoding="utf-8")

        self.assertIn("const ADJUNTO_FOTO_HABILITADO = false;", script)
        # El skip del paso de foto respeta el flag.
        self.assertIn("!ADJUNTO_FOTO_HABILITADO", script)
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/python manage.py test solicitudes.tests.SaludBotScriptTests.test_paso_de_foto_oculto_por_flag -v 2`
Expected: FAIL (no existe la constante).

- [ ] **Step 3: Agregar la constante**

En `static/js/saludbot.js`, agregar la constante junto a la configuracion del inicio del IIFE (por ejemplo, justo despues de `const INACTIVITY_LIMIT_MS = 20 * 60 * 1000;`):

```js
  const ADJUNTO_FOTO_HABILITADO = false;
```

- [ ] **Step 4: Respetar el flag en el `skip()` del paso de foto**

En `static/js/saludbot.js`, en el paso `credencial_cuidador_discapacidad_foto`, reemplazar su `skip()` por:

```js
      skip() {
        return !ADJUNTO_FOTO_HABILITADO || !state.data.credendencial_cuidador_discapacidad;
      },
```

- [ ] **Step 5: Correr el test para verificar que pasa**

Run: `.venv/bin/python manage.py test solicitudes.tests.SaludBotScriptTests.test_paso_de_foto_oculto_por_flag -v 2`
Expected: PASS.

- [ ] **Step 6: Verificar que el backend sigue tolerando foto**

Run: `.venv/bin/python manage.py test solicitudes.tests.SolicitudTests.test_endpoint_guarda_condicion_otro_y_foto -v 2`
Expected: PASS (sin cambios de backend; el endpoint sigue aceptando el campo si llega).

- [ ] **Step 7: Verificacion manual anotada**

En `runserver`: al responder "Si" a credencial de discapacidad/cuidador, el flujo debe pasar directo a la pregunta de neurodivergente/PRAIS/gestante, sin pedir foto. Anotar en el PR.

- [ ] **Step 8: Commit**

```bash
git add static/js/saludbot.js solicitudes/tests.py
git commit -F - <<'EOF'
Oculta el paso de foto de credencial tras un flag

Agrega ADJUNTO_FOTO_HABILITADO (apagado) que excluye el paso de foto del
flujo sin borrar el codigo, para poder revertir la decision cambiando el
flag. El backend ya tolera foto vacia.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0125u967AuBBEDP1JHij8tg5
EOF
```

---

### Task 5: Anclar el scroll al inicio del mensaje del bot

Cuando el bot publica un mensaje, el chat posiciona el inicio de ese mensaje al tope de la ventana (para leer de arriba hacia abajo). Los mensajes que ya entran completos no fuerzan salto; el eco del usuario no reancla.

**Files:**
- Modify: `static/js/saludbot.js` (`scrollToLatest()`, llamada en `addMessage()`)
- Test: `solicitudes/tests.py` (clase `SaludBotScriptTests`)

**Interfaces:**
- Consumes: `addMessage(content, sender, options)` ya pasa la fila creada a `scrollToLatest`.
- Produces: `scrollToLatest(target, sender)` con anclaje `block: "start"` para el bot.

- [ ] **Step 1: Escribir el test (falla primero)**

Agregar a `SaludBotScriptTests`:

```python
    def test_scroll_ancla_el_inicio_del_mensaje_del_bot(self):
        script = Path(settings.BASE_DIR, "static", "js", "saludbot.js").read_text(encoding="utf-8")

        self.assertIn("function scrollToLatest(target, sender)", script)
        self.assertIn('block: sender === "bot" ? "start" : "nearest"', script)
        # addMessage pasa el emisor al scroll para decidir el anclaje.
        self.assertIn("scrollToLatest(row, sender);", script)
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/python manage.py test solicitudes.tests.SaludBotScriptTests.test_scroll_ancla_el_inicio_del_mensaje_del_bot -v 2`
Expected: FAIL (la firma actual es `scrollToLatest(target)` y usa `block: "end"`).

- [ ] **Step 3: Reescribir `scrollToLatest`**

En `static/js/saludbot.js`, reemplazar la funcion `scrollToLatest` completa por:

```js
  function scrollToLatest(target, sender) {
    const element = target || messages.lastElementChild;
    if (!element) return;
    window.requestAnimationFrame(() => {
      const contenedor = messages.getBoundingClientRect();
      const fila = element.getBoundingClientRect();
      const entraCompleto = fila.top >= contenedor.top && fila.bottom <= contenedor.bottom;
      if (entraCompleto) return; // ya visible: no forzar salto
      element.scrollIntoView({
        behavior: "smooth",
        block: sender === "bot" ? "start" : "nearest",
        inline: "nearest",
      });
    });
  }
```

- [ ] **Step 4: Pasar el emisor desde `addMessage`**

En `static/js/saludbot.js`, en `addMessage`, cambiar la llamada final `scrollToLatest(row);` por:

```js
    scrollToLatest(row, sender);
```

- [ ] **Step 5: Correr el test para verificar que pasa**

Run: `.venv/bin/python manage.py test solicitudes.tests.SaludBotScriptTests.test_scroll_ancla_el_inicio_del_mensaje_del_bot -v 2`
Expected: PASS.

- [ ] **Step 6: Verificacion manual anotada**

En `runserver`, con un mensaje largo del bot (por ejemplo la tarjeta de urgencia o el detalle de sintomas): al aparecer, su primera linea debe quedar arriba, sin necesidad de subir. Mensajes cortos no deben provocar saltos bruscos. Anotar en el PR.

- [ ] **Step 7: Commit**

```bash
git add static/js/saludbot.js solicitudes/tests.py
git commit -F - <<'EOF'
Ancla el scroll al inicio del ultimo mensaje del bot

Al publicar un mensaje del bot, posiciona su primera linea al tope de la
ventana en vez de bajar al final; los mensajes que ya entran completos no
fuerzan salto y el eco del usuario no reancla.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0125u967AuBBEDP1JHij8tg5
EOF
```

---

### Task 6: Suite completa y verificacion final

**Files:**
- Sin cambios de codigo; corrida completa y notas de cierre.

- [ ] **Step 1: Correr toda la suite de solicitudes**

Run: `.venv/bin/python manage.py test solicitudes -v 2`
Expected: PASS (incluye la regresion `test_endpoint_rechaza_sin_terminos`, que confirma que el rechazo server-side de T&C sigue vigente).

- [ ] **Step 2: Correr la suite completa del proyecto**

Run: `.venv/bin/python manage.py test`
Expected: PASS.

- [ ] **Step 3: Checklist de verificacion manual del PR**

Confirmar en `runserver` y dejar anotado en el PR: (1) T&C es la primera pantalla; (2) input bloqueado en pasos de botones; (3) CESFAM antes de RUT/Nombre; (4) sin paso de foto; (5) scroll anclado arriba en mensajes largos.

---

## Self-Review

**Spec coverage:**
- T&C primera pantalla → Task 1. ✔
- Gate del input en pasos de botones → Task 3. ✔
- T&C server-side → ya existente (`Solicitud.clean()` + `test_endpoint_rechaza_sin_terminos`); conservado como regresion en Task 6. ✔
- CESFAM antes de RUT/Nombre → Task 2. ✔
- Ocultar foto tras flag → Task 4. ✔
- Scroll anclado arriba → Task 5. ✔

**Placeholder scan:** sin TBD/TODO; cada paso muestra codigo o comando concreto. ✔

**Type consistency:** `esPasoDeBotones(step)` (Task 3) usado con el mismo nombre en `showTyping`; `scrollToLatest(target, sender)` (Task 5) usado con esa firma en `addMessage`; `ADJUNTO_FOTO_HABILITADO` (Task 4) usado en el `skip()` del paso de foto; `quick: true` (Task 1) leido en `askCurrentStep`. ✔
