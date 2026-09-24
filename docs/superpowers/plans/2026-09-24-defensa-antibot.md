# Defensa contra bots del chatbot — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Endurecer el endpoint publico `crear_solicitud` con tres defensas invisibles (honeypot, token de tiempo firmado, rate limiting por IP), sin dependencias externas ni friccion para el usuario.

**Architecture:** Un modulo nuevo `solicitudes/antibot.py` con helpers puros (firmar/validar token con `django.core.signing`, honeypot, IP de cliente, rate limit sobre el cache de Django) se enchufa al inicio de `crear_solicitud`. La vista `saludbot` emite el token firmado al template; `saludbot.html` agrega el honeypot y el token; `saludbot.js` los manda en el payload. Sin cambios de modelo.

**Tech Stack:** Django 5.2 (signing + cache), JavaScript vanilla, plantillas Django, runner de Django contra MySQL 8.4.

## Global Constraints

- Codigo, comentarios y mensajes de commit en espanol, **sin tildes en identificadores**. Textos de UI (strings) si llevan tildes/emoji: no tocar esa convencion.
- Sin emojis en los mensajes de commit.
- Tests con el runner de Django, **no** SQLite ni pytest. Los tests de endpoint son `TestCase` (BD): correr contra MySQL 8.4 (Docker arriba). Los de helpers/frontend son `SimpleTestCase` (sin BD).
- **No** se modifica el modelo `Solicitud`. Las defensas son de entrada.
- **No** se toca el archivo en desuso `solicitudes/templates/solicitudes/chatbot.html` ni `solicitudes/static/solicitudes/chatbot.js`.
- Parametros (en `solicitudes/antibot.py`): `SEGUNDOS_MINIMOS = 8`, `SEGUNDOS_MAXIMOS = 30 * 60`, `RATE_LIMITE = 10`, `RATE_VENTANA_SEG = 10 * 60`.
- El rate limit cuenta **cada intento** de POST por IP (no solo los exitosos), para frenar floods de payloads invalidos.
- Ante honeypot / token invalido / token muy rapido: **201 fingido** (sin crear `Solicitud`), para no revelar la deteccion. Ante token vencido: **400** con mensaje de recarga. Ante rate limit: **429** con mensaje.
- Cada commit termina con las lineas de atribucion:
  ```
  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_0125u967AuBBEDP1JHij8tg5
  ```

## File Structure

- Create: `solicitudes/antibot.py` — helpers de defensa (firma de token, honeypot, IP, rate limit).
- Modify: `solicitudes/views.py` — `crear_solicitud` (chequeos + pop de campos antibot), `saludbot` (token al contexto), helper `_respuesta_fingida`.
- Modify: `templates/chat/saludbot.html` — input honeypot + token de tiempo.
- Modify: `static/css/saludbot.css` — clase `.hp` (oculta el honeypot).
- Modify: `static/js/saludbot.js` — agrega `token_tiempo` y `apellido_2` al payload.
- Modify: `solicitudes/tests.py` — tests de helpers, de endpoint y de frontend; actualizar los tests de endpoint existentes por el token obligatorio.

---

### Task 1: Modulo antibot (helpers puros)

**Files:**
- Create: `solicitudes/antibot.py`
- Test: `solicitudes/tests.py` (clase nueva `AntibotHelpersTests(SimpleTestCase)`)

**Interfaces:**
- Produces:
  - `firmar_token_tiempo(ts=None) -> str`
  - `validar_token_tiempo(token) -> str | None` (None = valido; si no: `"invalido"`, `"muy_rapido"`, `"vencido"`)
  - `honeypot_activado(body) -> bool`
  - `ip_cliente(request) -> str`
  - `rate_limit_excedido(request) -> bool` (incrementa el contador de la IP y devuelve True si supera `RATE_LIMITE`)
  - Constantes: `SEGUNDOS_MINIMOS`, `SEGUNDOS_MAXIMOS`, `RATE_LIMITE`, `RATE_VENTANA_SEG`

- [ ] **Step 1: Escribir los tests (fallan primero)**

Agregar al final de `solicitudes/tests.py`:

```python
class AntibotHelpersTests(SimpleTestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()

    def tearDown(self):
        from django.core.cache import cache
        cache.clear()

    def test_token_valido_round_trip(self):
        import time
        from solicitudes.antibot import firmar_token_tiempo, validar_token_tiempo, SEGUNDOS_MINIMOS
        token = firmar_token_tiempo(ts=time.time() - (SEGUNDOS_MINIMOS + 5))
        self.assertIsNone(validar_token_tiempo(token))

    def test_token_ausente_o_firma_invalida(self):
        from solicitudes.antibot import validar_token_tiempo
        self.assertEqual(validar_token_tiempo(""), "invalido")
        self.assertEqual(validar_token_tiempo(None), "invalido")
        self.assertEqual(validar_token_tiempo("esto-no-es-un-token"), "invalido")

    def test_token_muy_rapido(self):
        import time
        from solicitudes.antibot import firmar_token_tiempo, validar_token_tiempo
        token = firmar_token_tiempo(ts=time.time())  # recien emitido
        self.assertEqual(validar_token_tiempo(token), "muy_rapido")

    def test_token_vencido(self):
        import time
        from solicitudes.antibot import firmar_token_tiempo, validar_token_tiempo
        token = firmar_token_tiempo(ts=time.time() - (31 * 60))
        self.assertEqual(validar_token_tiempo(token), "vencido")

    def test_honeypot(self):
        from solicitudes.antibot import honeypot_activado
        self.assertFalse(honeypot_activado({}))
        self.assertFalse(honeypot_activado({"apellido_2": ""}))
        self.assertFalse(honeypot_activado({"apellido_2": "   "}))
        self.assertTrue(honeypot_activado({"apellido_2": "http://spam"}))

    def test_ip_cliente_prefiere_x_forwarded_for(self):
        from django.test import RequestFactory
        from solicitudes.antibot import ip_cliente
        req = RequestFactory().post(
            "/api/solicitudes/", HTTP_X_FORWARDED_FOR="1.2.3.4, 5.6.7.8", REMOTE_ADDR="9.9.9.9"
        )
        self.assertEqual(ip_cliente(req), "1.2.3.4")
        req2 = RequestFactory().post("/api/solicitudes/", REMOTE_ADDR="9.9.9.9")
        self.assertEqual(ip_cliente(req2), "9.9.9.9")

    def test_rate_limit_bloquea_tras_el_limite(self):
        from django.test import RequestFactory
        from solicitudes.antibot import rate_limit_excedido, RATE_LIMITE
        req = RequestFactory().post("/api/solicitudes/", REMOTE_ADDR="7.7.7.7")
        for _ in range(RATE_LIMITE):
            self.assertFalse(rate_limit_excedido(req))
        self.assertTrue(rate_limit_excedido(req))
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `.venv/bin/python manage.py test solicitudes.tests.AntibotHelpersTests -v 2`
Expected: FAIL (no existe `solicitudes/antibot.py`).

- [ ] **Step 3: Crear `solicitudes/antibot.py`**

```python
import time

from django.core import signing
from django.core.cache import cache

SEGUNDOS_MINIMOS = 8
SEGUNDOS_MAXIMOS = 30 * 60
RATE_LIMITE = 10
RATE_VENTANA_SEG = 10 * 60
_SALT = "solicitudes.antibot.token_tiempo"


def firmar_token_tiempo(ts=None):
    """Token firmado con el instante de emision. `ts` explicito facilita los tests."""
    momento = time.time() if ts is None else ts
    return signing.dumps({"ts": momento}, salt=_SALT)


def validar_token_tiempo(token):
    """None si el token es valido; si no, el motivo:
    'invalido' (ausente/firma mala), 'muy_rapido' (< SEGUNDOS_MINIMOS),
    'vencido' (> SEGUNDOS_MAXIMOS)."""
    if not token:
        return "invalido"
    try:
        datos = signing.loads(token, salt=_SALT)
    except signing.BadSignature:
        return "invalido"
    ts = datos.get("ts")
    if not isinstance(ts, (int, float)):
        return "invalido"
    transcurrido = time.time() - ts
    if transcurrido < SEGUNDOS_MINIMOS:
        return "muy_rapido"
    if transcurrido > SEGUNDOS_MAXIMOS:
        return "vencido"
    return None


def honeypot_activado(body):
    """True si el campo senuelo llego con contenido (lo llena un bot, no el humano)."""
    return bool(str(body.get("apellido_2") or "").strip())


def ip_cliente(request):
    """IP real: primer valor de X-Forwarded-For (detras de nginx), o REMOTE_ADDR."""
    reenviada = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if reenviada:
        return reenviada.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def rate_limit_excedido(request):
    """Cuenta cada intento por IP en el cache; True si supera RATE_LIMITE en la ventana."""
    ip = ip_cliente(request) or "desconocida"
    clave = f"antibot:rate:{ip}"
    intentos = cache.get(clave, 0) + 1
    cache.set(clave, intentos, RATE_VENTANA_SEG)
    return intentos > RATE_LIMITE
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `.venv/bin/python manage.py test solicitudes.tests.AntibotHelpersTests -v 2`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add solicitudes/antibot.py solicitudes/tests.py
git commit -F - <<'EOF'
Agrega el modulo antibot con helpers de defensa

Firma/validacion de token de tiempo (django.core.signing), deteccion de
honeypot, IP de cliente detras de proxy y rate limit por IP sobre el cache.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0125u967AuBBEDP1JHij8tg5
EOF
```

---

### Task 2: Enchufar las defensas en `crear_solicitud` y `saludbot`

Integra los helpers al endpoint y emite el token en la pagina. **Ojo:** el token pasa a ser obligatorio, asi que los tests de endpoint existentes (que postean sin token) deben actualizarse en esta misma tarea.

**Files:**
- Modify: `solicitudes/views.py` (`crear_solicitud`, `saludbot`, nuevo `_respuesta_fingida`)
- Test: `solicitudes/tests.py` (clase `SolicitudTests`: `setUp`, `valid_payload`, `test_creacion_solicitud_valida`, `test_endpoint_acepta_payload_saludbot`; y tests nuevos de antibot en el endpoint)

**Interfaces:**
- Consumes: `firmar_token_tiempo`, `validar_token_tiempo`, `honeypot_activado`, `rate_limit_excedido` de `solicitudes/antibot.py` (Task 1).
- Produces: `crear_solicitud` corta con 429/201-fingido/400 segun defensa; `saludbot` pasa `token_tiempo` al contexto; `_respuesta_fingida() -> JsonResponse` (201 con cuerpo plausible, sin fila).

- [ ] **Step 1: Actualizar los tests de endpoint existentes + escribir los nuevos**

En `solicitudes/tests.py`, dentro de `class SolicitudTests(TestCase)`:

(a) Agregar `setUp` que limpia el cache (evita que el rate limit arrastre conteos entre tests, ya que el cache LocMem persiste en el proceso):

```python
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
```

(b) En `valid_payload`, agregar el token valido y el honeypot vacio (import arriba del metodo o dentro):

```python
    def valid_payload(self):
        import time
        from solicitudes.antibot import firmar_token_tiempo
        return {
            "nombre": "Ana Maria Perez",
            "rut": "25747311-2",
            "edad": 34,
            "sexo": "F",
            "telefono": "949106239",
            "centro_salud": "620",
            "credendencial_cuidador_discapacidad": False,
            "Neurodivergente_prais_gestante": False,
            "acepta_terminos": True,
            "motivo": "consulta medica",
            "detalle_motivo": "dolor de garganta hace tres dias",
            "token_tiempo": firmar_token_tiempo(ts=time.time() - 30),
            "apellido_2": "",
        }
```

(c) En `test_creacion_solicitud_valida` (construye `Solicitud` directo desde `valid_payload`), sacar los campos antibot antes de construir el modelo. Justo despues de `payload = self.valid_payload()` y del `pop("centro_salud")`, agregar:

```python
        payload.pop("token_tiempo", None)
        payload.pop("apellido_2", None)
```

(d) En `test_endpoint_acepta_payload_saludbot` (postea un dict inline), agregar el token al JSON. En el diccionario que se serializa, agregar estas dos claves (el import va al inicio del metodo):

```python
                    "token_tiempo": __import__("solicitudes.antibot", fromlist=["firmar_token_tiempo"]).firmar_token_tiempo(ts=__import__("time").time() - 30),
                    "apellido_2": "",
```

(e) Agregar los tests nuevos de antibot en el endpoint:

```python
    def test_endpoint_honeypot_finge_exito_sin_guardar(self):
        payload = self.valid_payload()
        payload["apellido_2"] = "http://spam.example"
        response = self.client.post(
            reverse("crear_solicitud"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(Solicitud.objects.count(), 0)

    def test_endpoint_token_ausente_no_guarda(self):
        payload = self.valid_payload()
        payload.pop("token_tiempo")
        response = self.client.post(
            reverse("crear_solicitud"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Solicitud.objects.count(), 0)

    def test_endpoint_token_muy_rapido_no_guarda(self):
        import time
        from solicitudes.antibot import firmar_token_tiempo
        payload = self.valid_payload()
        payload["token_tiempo"] = firmar_token_tiempo(ts=time.time())  # instantaneo
        response = self.client.post(
            reverse("crear_solicitud"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Solicitud.objects.count(), 0)

    def test_endpoint_token_vencido_pide_recargar(self):
        import time
        from solicitudes.antibot import firmar_token_tiempo
        payload = self.valid_payload()
        payload["token_tiempo"] = firmar_token_tiempo(ts=time.time() - (31 * 60))
        response = self.client.post(
            reverse("crear_solicitud"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Solicitud.objects.count(), 0)

    def test_endpoint_rate_limit_devuelve_429(self):
        from solicitudes.antibot import RATE_LIMITE
        ultimo = None
        for _ in range(RATE_LIMITE + 1):
            ultimo = self.client.post(
                reverse("crear_solicitud"),
                data=json.dumps(self.valid_payload()),
                content_type="application/json",
            )
        self.assertEqual(ultimo.status_code, 429)
```

- [ ] **Step 2: Correr los tests para verificar el estado esperado**

Run: `.venv/bin/python manage.py test solicitudes.tests.SolicitudTests -v 2`
Expected: FAIL. Los tests nuevos de antibot fallan (aun no hay defensa: honeypot/token no cortan, no hay 429), y `test_creacion_solicitud_valida` puede fallar si `valid_payload` ya trae los campos antibot sin que la vista los sepa manejar. Esto se resuelve con la implementacion del Step 3.

- [ ] **Step 3: Implementar las defensas en `solicitudes/views.py`**

Agregar el import al inicio del archivo (junto a los otros imports de `.`):

```python
from .antibot import (
    honeypot_activado,
    rate_limit_excedido,
    validar_token_tiempo,
)
```

Agregar el helper de respuesta fingida, justo antes de `crear_solicitud`:

```python
def _respuesta_fingida():
    """201 con cuerpo plausible pero sin crear Solicitud: no revela la deteccion."""
    return JsonResponse(
        {
            "ok": True,
            "id_solicitud": 0,
            "priorizacion_solicitud": "",
            "puntaje_prioridad": 0,
            "resumen": {
                "nombre": "", "rut": "", "edad": "", "telefono": "",
                "centro_salud": "", "centro_salud_nombre": "",
                "motivo": "", "detalle_motivo": "",
            },
        },
        status=201,
    )
```

Reemplazar el inicio de `crear_solicitud` (desde `@require_POST` hasta la linea `payload = _normalizar_payload(_json_body(request))` inclusive) por:

```python
@require_POST
def crear_solicitud(request):
    if rate_limit_excedido(request):
        return JsonResponse(
            {"ok": False, "errors": ["Demasiadas solicitudes desde tu conexion, intenta mas tarde."]},
            status=429,
        )
    try:
        body = _json_body(request)
    except ValidationError as exc:
        return JsonResponse({"ok": False, "errors": exc.messages}, status=400)

    if honeypot_activado(body):
        return _respuesta_fingida()

    motivo_token = validar_token_tiempo(body.get("token_tiempo"))
    if motivo_token == "vencido":
        return JsonResponse(
            {"ok": False, "errors": ["Tu sesion expiro. Recarga la pagina e intenta nuevamente."]},
            status=400,
        )
    if motivo_token is not None:
        return _respuesta_fingida()

    body.pop("token_tiempo", None)
    body.pop("apellido_2", None)
    try:
        payload = _normalizar_payload(body)
```

(El resto del cuerpo del `try` — desde `payload["credendencial_cuidador_discapacidad"] = ...` hasta el `return JsonResponse(...)` final — queda **igual**.)

Modificar `saludbot` para emitir el token al contexto. Agregar el import (junto al de las defensas o en su propia linea):

```python
from .antibot import firmar_token_tiempo
```

y cambiar el `render` de `saludbot`:

```python
def saludbot(request):
    return render(
        request,
        "chat/saludbot.html",
        {
            "nombre_cesfam": request.GET.get("cesfam", "Corporacion Municipal de Valparaiso"),
            "user_name": request.GET.get("user_name", ""),
            "token_tiempo": firmar_token_tiempo(),
        },
    )
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `.venv/bin/python manage.py test solicitudes.tests.SolicitudTests -v 2`
Expected: PASS (los tests actualizados con token y los nuevos de antibot).

(El test de que la pagina emite el token vive en Task 3, junto al cambio de template que lo hace pasar, para que Task 2 cierre en verde.)

- [ ] **Step 5: Commit**

```bash
git add solicitudes/views.py solicitudes/tests.py
git commit -F - <<'EOF'
Enchufa las defensas antibot en crear_solicitud y saludbot

Rate limit por IP (429), honeypot y token de tiempo (201 fingido si es
invalido/muy rapido, 400 si vencido) antes de construir la Solicitud; saludbot
emite el token firmado. Actualiza los tests de endpoint por el token obligatorio.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0125u967AuBBEDP1JHij8tg5
EOF
```

---

### Task 3: Frontend (honeypot + token en la pagina y el payload)

**Files:**
- Modify: `templates/chat/saludbot.html` (input honeypot + `data-token-tiempo`)
- Modify: `static/css/saludbot.css` (clase `.hp`)
- Modify: `static/js/saludbot.js` (payload con `token_tiempo` y `apellido_2`)
- Test: `solicitudes/tests.py` (clase nueva `AntibotFrontendTests(SimpleTestCase)`)

**Interfaces:**
- Consumes: la vista `saludbot` pasa `token_tiempo` al contexto (Task 2).
- Produces: el payload de `finish()` incluye `token_tiempo` y `apellido_2`; el DOM tiene el honeypot oculto y el token.

- [ ] **Step 1: Escribir los tests (fallan primero)**

Agregar al final de `solicitudes/tests.py`:

```python
class AntibotFrontendTests(SimpleTestCase):
    def test_template_tiene_honeypot_y_token(self):
        html = Path(settings.BASE_DIR, "templates", "chat", "saludbot.html").read_text(encoding="utf-8")
        self.assertIn('name="apellido_2"', html)
        self.assertIn("data-token-tiempo=", html)
        self.assertIn("token_tiempo", html)  # el atributo referencia la variable de contexto

    def test_css_oculta_el_honeypot(self):
        css = Path(settings.BASE_DIR, "static", "css", "saludbot.css").read_text(encoding="utf-8")
        self.assertIn(".hp", css)

    def test_js_envia_token_y_honeypot_en_el_payload(self):
        js = Path(settings.BASE_DIR, "static", "js", "saludbot.js").read_text(encoding="utf-8")
        self.assertIn("token_tiempo:", js)
        self.assertIn("apellido_2:", js)


class AntibotPaginaTests(TestCase):
    def test_pagina_saludbot_emite_token_de_tiempo(self):
        response = self.client.get(reverse("saludbot"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-token-tiempo=")
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `.venv/bin/python manage.py test solicitudes.tests.AntibotFrontendTests -v 2`
Expected: FAIL (aun no existen el honeypot, el token en el template ni las claves en el payload).

- [ ] **Step 3: Agregar honeypot y token al template**

En `templates/chat/saludbot.html`, en la etiqueta `<main class="saludbot" ...>`, agregar el atributo del token (junto a `data-centro`/`data-user-name`):

```html
    data-token-tiempo="{{ token_tiempo }}"
```

Y dentro del `<form id="chatForm" ...>`, agregar el input honeypot (por ejemplo justo despues de `{% csrf_token %}`):

```html
      <input class="hp" type="text" name="apellido_2" tabindex="-1" autocomplete="off" aria-hidden="true">
```

- [ ] **Step 4: Ocultar el honeypot en el CSS**

En `static/css/saludbot.css`, agregar la clase (cerca de `.sr-only`, que ya existe con un patron similar):

```css
.hp {
  position: absolute;
  left: -9999px;
  width: 1px;
  height: 1px;
  overflow: hidden;
}
```

- [ ] **Step 5: Enviar token y honeypot en el payload**

En `static/js/saludbot.js`:

(a) Cerca del inicio del IIFE, donde se leen `root.dataset.*` (por ejemplo junto a `const userName = root.dataset.userName || "";`), agregar:

```js
  const tokenTiempo = root.dataset.tokenTiempo || "";
```

(b) En `finish()`, agregar dos claves al objeto `payload` (al final, antes del `};`):

```js
      token_tiempo: tokenTiempo,
      apellido_2: (document.querySelector('input[name="apellido_2"]') || {}).value || "",
```

- [ ] **Step 6: Correr los tests de frontend + el de emision del token**

Run: `.venv/bin/python manage.py test solicitudes.tests.AntibotFrontendTests solicitudes.tests.AntibotPaginaTests -v 2`
Expected: PASS (frontend verde y la pagina emite `data-token-tiempo`).

- [ ] **Step 7: Verificacion manual anotada**

En `runserver`: el campo honeypot no debe verse; completar el flujo normal debe crear la solicitud (token valido); inspeccionar el payload en las devtools para confirmar que van `token_tiempo` (no vacio) y `apellido_2` (vacio). Anotar en el PR.

- [ ] **Step 8: Commit**

```bash
git add templates/chat/saludbot.html static/css/saludbot.css static/js/saludbot.js solicitudes/tests.py
git commit -F - <<'EOF'
Agrega honeypot y token de tiempo al frontend del chatbot

El template emite el token firmado en data-token-tiempo y un input honeypot
oculto (.hp); saludbot.js los manda en el payload (token_tiempo, apellido_2).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0125u967AuBBEDP1JHij8tg5
EOF
```

---

### Task 4: Suite completa y verificacion final

**Files:**
- Sin cambios de codigo; corrida completa y notas de cierre.

- [ ] **Step 1: Correr toda la suite de solicitudes contra MySQL**

Run: `.venv/bin/python manage.py test solicitudes -v 2`
Expected: PASS (helpers, endpoint con y sin defensa, frontend, y los tests preexistentes de solicitud que ahora incluyen token).

- [ ] **Step 2: Correr la suite completa del proyecto**

Run: `.venv/bin/python manage.py test`
Expected: PASS.

- [ ] **Step 3: Checklist de verificacion manual del PR**

Confirmar en `runserver` y dejar anotado en el PR: (1) el flujo normal crea la solicitud (token valido, honeypot vacio); (2) el honeypot no es visible; (3) el payload lleva `token_tiempo` y `apellido_2`. Opcional/observacional: un POST directo sin token a `/api/solicitudes/` responde 201 sin crear fila (defensa activa).

---

## Self-Review

**Spec coverage:**
- Capa 1 honeypot (`honeypot_activado`, 201 fingido) → Task 1 (helper) + Task 2 (wiring) + Task 3 (campo). ✔
- Capa 2 token de tiempo firmado (min 8 s, expira 30 min, anti-forja con signing) → Task 1 (firmar/validar) + Task 2 (wiring + emision) + Task 3 (envio). ✔
- Capa 3 rate limit por IP (10 cada 10 min, XFF con fallback, 429) → Task 1 (`ip_cliente`/`rate_limit_excedido`) + Task 2 (wiring 429). ✔
- Orden de evaluacion (rate limit → honeypot → token) → Task 2 Step 3. ✔
- Respuestas: 201 fingido / 400 vencido / 429 → Task 2 (implementacion y tests). ✔
- Sin cambios de modelo; sin dependencias externas (usa `django.core.signing` y el cache) → respetado. ✔
- Testing determinista del tiempo (token firmado con `ts` explicito) y `cache.clear()` en rate limit → Task 1 y Task 2 (setUp). ✔

**Placeholder scan:** sin TBD/TODO; cada paso trae codigo o comando concreto. ✔

**Type consistency:** `firmar_token_tiempo(ts=None)`, `validar_token_tiempo(token) -> None|"invalido"|"muy_rapido"|"vencido"`, `honeypot_activado(body)`, `ip_cliente(request)`, `rate_limit_excedido(request)` usados con las mismas firmas en views y tests; `_respuesta_fingida()` sin args; el atributo `data-token-tiempo` del template se lee como `root.dataset.tokenTiempo` en JS (camelCase correcto del dataset). Constantes `RATE_LIMITE`/`SEGUNDOS_MINIMOS` referenciadas en los tests coinciden con `antibot.py`. ✔

**Independencia de tareas:** el test de emision del token (`AntibotPaginaTests`) vive en Task 3, junto al cambio de template que lo hace pasar, asi que cada tarea cierra su suite en verde sin cruces rojos. Task 2 no deja tests en rojo.
