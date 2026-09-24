# Spec 3 — Defensa contra bots en el chatbot publico

Fecha: 2026-09-24
Modulo: `solicitudes` (chatbot publico, host `morbilidad.cmvalparaiso.cl`)
Archivos principales: `solicitudes/antibot.py` (nuevo), `solicitudes/views.py`,
`templates/chat/saludbot.html`, `static/js/saludbot.js`, `static/css/saludbot.css`,
`solicitudes/tests.py`.

## Contexto

El endpoint publico `crear_solicitud` (`solicitudes/views.py`, ruta
`/api/solicitudes/`) recibe el JSON del chatbot y crea la `Solicitud`. Hoy tiene
`@require_POST`, CSRF y `full_clean()`, pero **ninguna defensa contra envios
automatizados**: ni honeypot, ni verificacion de tiempo, ni rate limiting. Es
endurecimiento preventivo (sin incidente concreto) pedido en la revision del
equipo y por el referente de ciberseguridad, para frenar spam (solicitudes
basura que ensucian la cola del selector) y floods.

Decision de alcance (usuario): **solo defensas invisibles**, sin CAPTCHA ni
terceros en el flujo (datos de salud sensibles, usuarios mayores/vulnerables,
cero friccion). Un CAPTCHA queda como capa futura si el referente lo exige.

El chatbot postea JSON desde `static/js/saludbot.js` (funcion `finish()`), asi
que las defensas viven en el backend + un par de campos que el frontend agrega al
payload. El proyecto no define `CACHES` en settings, por lo que usa el cache por
defecto de Django (LocMemCache, por worker). `SECRET_KEY` existe (para firmar).
Detras de nginx hay proxy (`USE_PROXY_SSL_HEADER` configurable).

## Arquitectura

Modulo nuevo `solicitudes/antibot.py` con helpers puros y testeables, enchufados
al inicio de `crear_solicitud` **antes** de construir la `Solicitud`:

- `firmar_token_tiempo() -> str` y `validar_token_tiempo(token) -> str | None`
- `honeypot_activado(payload) -> bool`
- `ip_cliente(request) -> str`
- `rate_limit_excedido(request) -> bool`

`crear_solicitud` los invoca en orden y corta segun el resultado. El template
`saludbot.html` embebe el token de tiempo firmado y el campo honeypot oculto;
`saludbot.js` los incluye en el payload.

## Capa 1 — Honeypot

- Campo senuelo `sitio_web` en `saludbot.html`, oculto por CSS (fuera de
  pantalla, `tabindex="-1"`, `autocomplete="off"`). Clase `.hp`:
  `position:absolute; left:-9999px;` (invisible, sin ocupar espacio). El nombre es
  deliberadamente **no-personal** (no `apellido`/`nombre`/etc.) para que un
  autocompletado/gestor de contrasenas no lo llene y cause una perdida silenciosa.
- `saludbot.js` lee ese input y envia `sitio_web` en el payload; el usuario real
  nunca lo toca, asi que llega vacio.
- `honeypot_activado(payload)` devuelve `True` si `sitio_web` tiene contenido
  (tras `strip`). En ese caso `crear_solicitud` responde **201 fingido**
  (`{"ok": True, ...}` sin `Solicitud` creada) para no revelar la deteccion.

Nota: contra un bot dirigido directamente a la API el honeypot es marginal (podria
no enviar el campo); es la capa barata que atrapa bots genericos de formularios.
El peso real lo llevan las capas 2 y 3.

## Capa 2 — Verificacion de tiempo (token firmado)

- Al servir la pagina del chatbot (`saludbot` view en `solicitudes/views.py`), el
  servidor genera `firmar_token_tiempo()`: un token firmado con
  `django.core.signing` (`TimestampSigner` o `dumps` con `SECRET_KEY`) que lleva
  el instante de emision. Se pasa al template en el contexto y se embebe (p. ej.
  como `data-token-tiempo` en `.saludbot` o un input oculto).
- `saludbot.js` lo reenvia en el payload como `token_tiempo`.
- `validar_token_tiempo(token)` en `crear_solicitud`:
  - Firma invalida o token ausente -> invalido.
  - Antiguedad **< 8 segundos** (envio casi instantaneo, tipico de bot) ->
    invalido. 8 s es holgado: el flujo conversacional con indicadores de
    "escribiendo" ya toma bastante mas, sin falsos positivos.
  - Antiguedad **> 30 minutos** (expiracion; el flujo real dura mucho menos) ->
    invalido, se trata como token vencido.
  - Devuelve `None` si es valido, o un codigo/motivo si no.
- Token invalido por firma o por "muy rapido" -> **201 fingido** (silencioso, no
  se le da pista al bot). Token vencido (> 30 min) -> respuesta que invita a
  recargar la pagina (mensaje claro, es un caso que un humano lento podria topar).

Se usa `django.core.signing` (stdlib de Django, sin dependencias nuevas). La firma
con `SECRET_KEY` impide que un bot forje un timestamp viejo para saltarse el
minimo de 8 s.

## Capa 3 — Rate limiting por IP

- `ip_cliente(request)`: toma la IP real del **ultimo** valor de `X-Forwarded-For`
  (el que agrega nuestro nginx = la IP que conecto al proxy); los valores de la
  izquierda los puede falsear el cliente, por eso no se usan. Si no existe XFF, cae
  a `REMOTE_ADDR`. **Supuesto:** un unico proxy de confianza (nginx) delante; si se
  agrega otro proxy/CDN, ajustar el indice del valor tomado.
- `rate_limit_excedido(request)`: cuenta **cada intento** (POST) por IP en el cache
  de Django dentro de una ventana (no solo los exitosos, para frenar floods de
  payloads invalidos). Limite: **10 solicitudes por IP cada 10 minutos** (holgado:
  alguien puede registrar a varios familiares). Implementacion con clave de cache
  por IP y ventana de 600 s (`cache.add` fija el TTL una vez + `cache.incr` atomico:
  ventana fija, no deslizante).
- Excedido -> **429 Too Many Requests** con `{"ok": False, "errors": [...]}` y
  mensaje claro ("Demasiadas solicitudes desde tu conexion, intenta mas tarde").
  Es el unico caso visible, porque un usuario legitimo que lo tope necesita
  saberlo. `saludbot.js` ya renderiza `result.errors` cuando la respuesta no es
  `ok`.

Limitacion aceptada: LocMemCache es por worker, asi que el conteo no se comparte
entre procesos; para el volumen y despliegue de este servicio (pocos workers) es
suficiente como freno de floods. Si se necesitara exactitud multi-worker, se
migraria el cache a uno compartido (fuera de alcance de esta spec).

## Orden de evaluacion en `crear_solicitud`

1. Rate limit por IP -> si excede, **429** y corta.
2. Honeypot con contenido -> **201 fingido**, no guarda.
3. Token de tiempo invalido/muy rapido -> **201 fingido**, no guarda; vencido ->
   respuesta de "recarga la pagina".
4. Si pasa las tres, sigue el flujo actual (normalizar payload, `full_clean`,
   guardar) sin cambios.

## Frontend

- `saludbot.html`: agrega el input honeypot `sitio_web` (oculto) y el token de
  tiempo (`data-token-tiempo` o input oculto con el valor del contexto).
- `static/css/saludbot.css`: clase `.hp` que oculta el honeypot sin ocupar
  espacio.
- `static/js/saludbot.js`: lee el token de tiempo y el honeypot del DOM y los
  agrega al `payload` de `finish()` (`token_tiempo`, `sitio_web`). Maneja el
  nuevo caso 429 mostrando el mensaje (ya cubierto por el flujo de error
  existente).

## Testing

Django `TestCase` contra MySQL 8.4 (Docker arriba; runner de Django, no SQLite,
no pytest):

- Token valido + tiempo suficiente + honeypot vacio -> **201**, `Solicitud`
  creada.
- Honeypot con contenido -> **201** fingido, `Solicitud.objects.count() == 0`.
- Token ausente o con firma invalida -> no crea `Solicitud`.
- Token con antiguedad < 8 s (envio instantaneo) -> no crea `Solicitud`.
- Token vencido (> 30 min) -> respuesta de recarga, no crea `Solicitud`.
- Rate limit: al 11.º envio desde la misma IP en la ventana -> **429**; los
  primeros 10 pasan.
- Test unitario de `firmar_token_tiempo`/`validar_token_tiempo` (round-trip y
  rechazo de firma alterada), sin BD.

Para los tests que necesitan controlar el tiempo, se firma el token con un
timestamp explicito (o se congela el reloj) para simular "muy rapido" y "vencido"
de forma determinista. El cache se limpia (`cache.clear()`) en el `setUp`/`tearDown`
de los tests de rate limit para no arrastrar conteos entre casos.

Correr `.venv/bin/python manage.py test` antes de dar la tarea por terminada.

## Fuera de alcance

- CAPTCHA / verificacion con terceros (Cloudflare Turnstile, reCAPTCHA): capa
  futura si el referente lo exige.
- Captura de cupos reales en el selector (Spec 4).
- No se cambia el modelo `Solicitud`; las defensas son de transporte/entrada.
- El archivo en desuso `solicitudes/templates/solicitudes/chatbot.html` /
  `solicitudes/static/solicitudes/chatbot.js` no se toca.
