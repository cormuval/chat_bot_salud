# Acceso y navegación del módulo de gestión — Diseño

Fecha: 2026-09-01
Versión: 1
Relacionado: `docs/arquitectura-modulo-gestion.md`,
`docs/superpowers/specs/2026-08-20-ui-ux-modulo-seleccion-design.md`

> Documento para validar antes de escribir código. Primera de tres specs que
> ordenan un conjunto de cambios del módulo de gestión. Las otras dos —panel de
> administración (perfiles y reportería) y parámetros de priorización editables—
> se abordan por separado.

## Objetivo

El módulo de gestión funciona pero su capa de acceso tiene dos huecos que
confunden al usuario:

1. **No hay página de login.** `LOGIN_URL` apunta directo a `oidc_authentication_init`,
   así que un usuario sin sesión salta a la pantalla de Google sin pasar por una
   puerta propia del sistema. Y `LOGOUT_REDIRECT_URL` es `/sin-acceso/`: al cerrar
   sesión el usuario queda en la misma vista, que solo dice "Sin acceso". No queda
   claro que cerró sesión ni cómo volver a entrar.

2. **No hay 404 propio.** `urls_gestion.py` no define `handler404`, así que una ruta
   inexistente cae en la página técnica de Django, ajena a la identidad del módulo.

Esta spec cierra ambos huecos y, de paso, separa dos situaciones que hoy se
confunden: "esto no existe" (404) y "no tienes permiso" (sin acceso).

## Alcance

**Dentro de alcance:**

- Página de login del módulo, con un único botón de ingreso con Google.
- Redirección del cierre de sesión a esa página de login.
- 404 controlado del módulo, con su identidad visual.
- Mejora de `/sin-acceso/` para que se lea como un tema de permisos y ofrezca salida.
- Ocultar la navegación cuando no hay sesión.

**Fuera de alcance:**

- Panel de administración: gestión de perfiles y reportería. Va en la spec 2.
- Parámetros de priorización editables. Va en la spec 3.
- Cambios al chatbot público. Nada de este trabajo lo toca.
- `handler500` u otras páginas de error. Solo el 404, como se pidió.
- Cambios al backend OIDC (`gestion/auth.py`) y a las reglas de quién tiene acceso.

## Contexto de partida

Lo relevante ya existe y no se reescribe:

- **Login con Google** vía `mozilla_django_oidc`, con el backend
  `gestion.auth.OIDCAuthenticationBackendGestion`. `OIDC_CREATE_USER = False`: no se
  crean cuentas al vuelo; solo entra quien tiene un `PerfilUsuario` activo.
- **`/sin-acceso/`** (`gestion:sin_acceso`) ya existe como vista pública; hoy solo
  muestra un `<h1>Sin acceso</h1>` dentro de `base.html`.
- **El botón "Cerrar sesión"** del `base.html` ya hace POST a `oidc_logout` (el
  logout de mozilla-django-oidc solo acepta POST).
- **`panel`** (`/`) enruta por rol a selector, comunicador o sin-acceso, y está
  protegido con `@login_required`.

## Diseño

### 1. Página de login

Ruta nueva `login/` (`gestion:login`), en `gestion/urls.py`, con una vista pública
—sin `@login_required`, porque es la puerta para quien no tiene sesión—. Renderiza
`gestion/login.html`: un layout mínimo con la identidad del módulo y un único botón
**"Iniciar sesión con Google"**.

El botón es un enlace a `oidc_authentication_init` que preserva el parámetro `next`:

```
{% url 'oidc_authentication_init' %}?next={{ next|urlencode }}
```

`LOGIN_URL` pasa de `oidc_authentication_init` a `gestion:login`. Con eso, el flujo
de `@login_required` cambia de forma coherente en todo el módulo: un usuario sin
sesión que entra a `/selector/` es redirigido a `/login/?next=/selector/`, ve la
página con el botón, y el salto a Google ocurre **solo al presionar el botón**. Tras
autenticar, vuelve a la ruta que había pedido.

La vista lee `next` de `request.GET`, lo valida con `url_has_allowed_host_and_scheme`
contra el host actual —para no reenviar a un destino externo— y cae a `/` si no es
seguro o no viene.

### 2. Cierre de sesión hacia el login

`LOGOUT_REDIRECT_URL` pasa de `/sin-acceso/` a la página de login (`/login/`). El
botón "Cerrar sesión" del header no cambia: sigue siendo un POST a `oidc_logout`;
solo cambia el destino final. Así, al cerrar sesión el usuario aterriza en una
pantalla que explícitamente dice "inicie sesión", no en un "Sin acceso" ambiguo.

### 3. 404 controlado del módulo

Se agrega `handler404 = "gestion.views.pagina_no_encontrada"` en `cesfam_chatbot/urls_gestion.py`
(el urlconf que sirve el subdominio de gestión). La vista renderiza
`gestion/404.html` con estado 404: mismo header y estilos del módulo, un mensaje de
"la página que buscas no existe" y un enlace de vuelta al inicio (`/`).

Es análogo al `handler404` que el chatbot ya tiene en su propio urlconf, pero con la
identidad y las rutas del módulo de gestión. Como el 404 del chatbot, **solo se
renderiza con `DEBUG=False`**; con `DEBUG=True` Django intercepta antes y muestra su
página técnica. Es el comportamiento esperado en desarrollo y no requiere trabajo
extra.

Este 404 cubre **rutas inexistentes**. No cubre "sin permiso": eso es el punto 4.

### 4. `/sin-acceso/` como página de permisos, con salida

`/sin-acceso/` es para un caso distinto del 404: un usuario **autenticado** cuya
cuenta no tiene un perfil de gestión activo. El template se reescribe para que:

- Diga claramente que es un tema de **permisos** —la cuenta no está habilitada para
  el módulo—, no un error ni un "no existe".
- Ofrezca un botón **"Cerrar sesión y usar otra cuenta"** (POST a `oidc_logout`),
  por si la persona entró con la cuenta equivocada. Sin esto queda atrapada: no
  tiene navegación disponible y no hay forma obvia de salir.

Queda así una separación de tres mensajes, cada uno para su situación:

| Situación | Página | Mensaje |
| --- | --- | --- |
| Sin sesión | `/login/` | "Inicie sesión con Google" |
| Ruta inexistente | 404 | "La página no existe" |
| Con sesión, sin perfil activo | `/sin-acceso/` | "Su cuenta no tiene permisos" + salir |

### 5. Navegación oculta sin sesión

El `base.html` muestra la barra de navegación (Selector / Comunicador) siempre. En
las páginas de login y sin-acceso eso ofrece enlaces a rutas protegidas que
rebotarían de vuelta al login. Se envuelve la `<nav>` en `{% if perfil %}`, igual que
ya se hace con el bloque de sesión del header. Sin perfil en contexto —login,
sin-acceso—, no se pinta navegación.

## Enfoque técnico

- **Sin dependencias nuevas.** Todo se resuelve con vistas, templates y tres
  settings (`LOGIN_URL`, `LOGOUT_REDIRECT_URL`, `handler404`).
- **Se siguen los patrones del módulo:** vistas en `gestion/views.py`, templates en
  `gestion/templates/gestion/`, estilos en `static/css/gestion.css`.
- **No se toca `gestion/auth.py`** ni las reglas de acceso: quién puede entrar sigue
  decidiéndose igual. Esta spec cambia la *experiencia* de entrar y salir, no las
  reglas.

## Pruebas

Django test runner, contra MySQL:

- Un usuario sin sesión que pide `/selector/` recibe 302 a `/login/?next=/selector/`.
- `/login/` responde 200 y contiene el botón con el enlace a `oidc_authentication_init`
  y el `next` preservado.
- La vista de login descarta un `next` con host externo y cae a `/`.
- `LOGOUT_REDIRECT_URL` apunta a `/login/` (asegura el destino del cierre de sesión).
- `/sin-acceso/` responde 200, se lee como tema de permisos y contiene el formulario
  de cierre de sesión (POST a `oidc_logout`).
- Con `DEBUG=False`, una ruta inexistente del módulo renderiza `gestion/404.html` con
  estado 404.
- Login y sin-acceso no contienen los enlaces de navegación Selector/Comunicador.

## Decisiones tomadas

- Sin sesión se muestra `/login/`, no un salto directo a Google: una sola puerta de
  entrada visible.
- El 404 (ruta inexistente) y el sin-acceso (permisos) son páginas y mensajes
  distintos.
- `/sin-acceso/` ofrece cerrar sesión para no dejar atrapado a quien entró con la
  cuenta equivocada.
- La navegación no se muestra sin sesión.
- No se toca el backend OIDC ni las reglas de acceso.

## Consecuencias asumidas

- **El 404 propio solo se ve en producción (`DEBUG=False`).** En local se sigue
  viendo la página técnica de Django. Es consistente con el 404 del chatbot y no se
  considera un problema.
- **Cambiar `LOGIN_URL` afecta a todo el urlconf de gestión.** Es justamente lo
  buscado: todas las rutas protegidas pasan a mandar al login propio. El chatbot no
  tiene rutas protegidas, así que no se ve afectado.

## Referencias

- `cesfam_chatbot/urls_gestion.py` — urlconf del subdominio de gestión; aquí va el `handler404`.
- `cesfam_chatbot/settings.py` — `LOGIN_URL`, `LOGOUT_REDIRECT_URL`, config OIDC.
- `gestion/auth.py` — backend OIDC y reglas de acceso (no se toca).
- `gestion/views.py` — `panel`, `sin_acceso`; aquí van las vistas nuevas.
- `gestion/templates/gestion/base.html` — header, navegación, botón de cierre de sesión.

## Historial de versiones

| Versión | Fecha | Cambios |
| --- | --- | --- |
| 1 | 2026-09-01 | Versión inicial, validada en sesión de brainstorming. |
