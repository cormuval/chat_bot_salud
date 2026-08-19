# Puesta en marcha del entorno local

Pauta para dejar SaludBot corriendo desde cero tras clonar el repositorio en
una máquina nueva. Recorre los mismos pasos que se ejecutaron la primera vez
que se montó el entorno, incluidos los tropiezos que costaron tiempo, para no
volver a descubrirlos.

Los comandos están en formato Unix (macOS/Linux). Los `.ps1` de la raíz son el
equivalente para el entorno Windows del autor.

## Requisitos previos

| Herramienta | Versión usada | Notas |
| --- | --- | --- |
| Python | 3.13 | El README dice 3.12; 3.13 instala y corre sin problemas |
| Docker + Compose | 29.x / v5.x | Provee MySQL 8.4, el mismo motor que producción |
| git | cualquiera | — |

No hace falta instalar MySQL en el sistema: lo entrega el contenedor.

## 1. Entorno virtual y dependencias

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

## 2. Archivo `.env`

```bash
cp .env.example .env
```

Generar una `SECRET_KEY` propia y pegarla en el archivo:

```bash
.venv/bin/python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
```

Los valores relevantes para local quedan así:

```env
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost
GESTION_HOST=127.0.0.1

DB_ENGINE=mysql
DB_NAME=chat_bot_salud
DB_USER=saludbot
DB_PASSWORD=saludbot_dev
DB_HOST=127.0.0.1
DB_PORT=3306
MYSQL_ROOT_PASSWORD=saludbot_root_dev
```

Dos cosas que no son evidentes:

- **`docker-compose.yml` lee el mismo `.env`.** `DB_USER` y `DB_PASSWORD` no
  solo configuran a Django: son los que el contenedor usa como `MYSQL_USER` y
  `MYSQL_PASSWORD` al crear la base. Por eso **no sirve dejar `DB_USER=root`**
  como viene en `.env.example`: la imagen oficial de MySQL rechaza
  `MYSQL_USER=root` y el contenedor no arranca.
- Ese usuario **se crea una única vez**, cuando el volumen está vacío. Si
  después cambias `DB_USER`/`DB_PASSWORD` en `.env`, hay que rehacer el volumen
  (`docker compose down -v`) o crear el usuario a mano con root.

La elección de `GESTION_HOST=127.0.0.1` no es arbitraria; se explica en el
paso 6.

## 3. Levantar MySQL

```bash
docker compose up -d
```

Esperar a que el healthcheck pase a `healthy` antes de seguir:

```bash
docker inspect -f '{{.State.Health.Status}}' saludbot-mysql
```

En el primer arranque, con el volumen vacío, el contenedor ejecuta
`sql/crear_mysql_saludbot.sql`. Ese script crea la tabla `centros` con los 15
CESFAM y la tabla `solicitudes_solicitud` ya en su forma final.

Si el puerto 3306 está ocupado por otro MySQL de la máquina, detenerlo o
cambiar `DB_PORT` en `.env`:

```bash
lsof -nP -iTCP:3306 -sTCP:LISTEN
```

## 4. Privilegios para la base de tests

El runner de Django crea y destruye una base `test_chat_bot_salud` en cada
corrida, y el usuario de la aplicación no tiene permiso para eso por defecto.
Sin este paso los tests fallan con `Access denied ... to database
'test_chat_bot_salud'`:

```bash
docker exec -i saludbot-mysql mysql -uroot -psaludbot_root_dev \
  -e "GRANT ALL PRIVILEGES ON \`test\_%\`.* TO 'saludbot'@'%'; FLUSH PRIVILEGES;"
```

## 5. Migraciones

Las tablas de `solicitudes` **ya existen**: las creó el script SQL del paso 3.
Aplicar sus migraciones de verdad fallaría, así que se marcan como aplicadas y
solo después se corre el resto. Es lo mismo que hace `prepare_mysql.ps1`.

```bash
.venv/bin/python manage.py migrate solicitudes --fake
.venv/bin/python manage.py migrate
```

El segundo comando sí crea de verdad las tablas de `admin`, `auth`,
`contenttypes`, `sessions` y `gestion`.

Verificar que todo quedó consistente:

```bash
.venv/bin/python manage.py test
```

Deben pasar los 48 tests contra MySQL. Aparece un `UserWarning: No directory
at: staticfiles/` de Whitenoise: es inofensivo en local y desaparece con
`collectstatic`.

## 6. Hosts: por qué `localhost` y `127.0.0.1`

El enrutamiento es por subdominio. `HostBasedUrlconfMiddleware` compara el
hostname de la request (sin puerto) contra `GESTION_HOST`: si calza, sirve el
módulo de gestión; si no, el chatbot. Es decir, se necesitan **dos hostnames
distintos apuntando al mismo servidor**.

En producción son `morbilidad.cmvalparaiso.cl` y `seleccion.cmvalparaiso.cl`.
En local la elección la impone Google, no Django.

### Lo que no funciona: `gestion.localhost`

`.env.example`, el README y los docs mencionan `gestion.localhost` como host
local de gestión. **Resuelve bien** (macOS mapea `localhost` y todo lo que
cuelgue de él a loopback, por RFC 6761) y **Django lo enruta bien**, pero
**Google rechaza el login**:

```
Acceso bloqueado: error de autorización
Error 400: invalid_request
```

Google valida el `redirect_uri` contra sus reglas de política, y una de ellas
es que *el TLD del host debe pertenecer a la Public Suffix List*. `localhost`
no está en esa lista. Google hace una excepción explícita para los hosts
`localhost` y `127.0.0.1` — por eso ahí se permite HTTP sin TLS — pero esa
excepción cubre el host exacto, no subdominios inventados debajo de él.

Alternativas que también se descartan: dominios como `gestion.localtest.me` o
`*.nip.io` sí están en la Public Suffix List y resuelven a 127.0.0.1, pero
Google no los considera localhost y entonces exige HTTPS. Un `.test` en
`/etc/hosts` tampoco sirve: no está en la Public Suffix List.

### Lo que sí funciona

Repartir los dos hostnames que Google sí exceptúa:

| Módulo | URL local |
| --- | --- |
| Gestión | `http://127.0.0.1:8000/` |
| Chatbot | `http://localhost:8000/` |

Ambos apuntan a loopback pero mandan un `Host` distinto, que es justo lo que
el middleware necesita. De ahí `GESTION_HOST=127.0.0.1` en el paso 2.

El reparto inverso (gestión en `localhost`, chatbot en `127.0.0.1`) funciona
igual de bien. Lo único que importa es que el host de gestión coincida con el
redirect URI registrado en Google; ver paso 7.

## 7. Credenciales de Google OAuth

El módulo de gestión se entra solo con cuenta de Google Workspace. Hace falta
un **OAuth 2.0 Client ID** tipo *Web application* en Google Cloud Console, con:

- **URI de redirección autorizado:** `http://127.0.0.1:8000/oidc/callback/`
  (debe coincidir con `GESTION_HOST`)
- (Producción, ya registrado: `https://seleccion.cmvalparaiso.cl/oidc/callback/`)

El `client_id` y el `client_secret` van a `.env`:

```env
GOOGLE_OAUTH_CLIENT_ID=...apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=...
GOOGLE_WORKSPACE_DOMAIN=cmvalparaiso.cl
```

**El redirect URI se compara como string exacto.** `localhost` y `127.0.0.1`
son entradas distintas para Google aunque apunten al mismo sitio; registrar una
y enviar la otra da `Error 400: redirect_uri_mismatch`. El detalle del error en
esa pantalla muestra el `redirect_uri` que llegó, que es la forma rápida de
diagnosticarlo.

Para ver qué está enviando la aplicación sin pasar por el navegador:

```bash
curl -s -o /dev/null -D - 'http://127.0.0.1:8000/oidc/authenticate/' \
  | grep -i '^location:' | tr '&' '\n'
```

Un detalle más: hay que navegar desde el mismo host de principio a fin. Si el
login se inicia en un host y el callback llega a otro, la cookie de sesión no
viaja y `mozilla-django-oidc` falla por `state` no coincidente.

El campo *Orígenes autorizados de JavaScript* no se usa: el flujo es
server-side.

## 8. Alta de usuarios del módulo de gestión

El login con Google **no crea cuentas al vuelo** (`OIDC_CREATE_USER = False`).
Un correo del dominio institucional sin perfil dado de alta no entra. En un
entorno recién montado no hay ningún usuario, así que el primero hay que
crearlo por consola.

Este snippet da de alta a un administrador de forma idempotente:

```bash
.venv/bin/python manage.py shell <<'PY'
import secrets
from django.contrib.auth.models import User
from gestion.models import PerfilUsuario
from solicitudes.models import Centro

CORREOS = ["alguien@cmvalparaiso.cl"]

# Centro base: para el rol ADMIN es informativo (ve todos los centros), pero
# la FK es obligatoria.
centro = Centro.objects.order_by("id_centro").first()

for correo in CORREOS:
    usuario = User.objects.filter(email__iexact=correo).first()
    creado = usuario is None
    if creado:
        usuario = User(username=correo.split("@")[0], email=correo)
        usuario.set_password(secrets.token_urlsafe(16))
    usuario.is_active = usuario.is_staff = usuario.is_superuser = True
    usuario.save()

    PerfilUsuario.objects.update_or_create(
        usuario=usuario,
        defaults={"rol": PerfilUsuario.Rol.ADMIN, "centro": centro, "activo": True},
    )
    print(f"{correo} listo (creado={creado})")
PY
```

Sobre las decisiones que hay ahí:

- **`is_superuser`/`is_staff`** son necesarios para operar `/admin/`, que es
  desde donde se da de alta al resto del equipo (ver README, sección *Módulo
  de gestión: alta de usuarios*).
- **La contraseña** solo sirve para el formulario de `/admin/`, que no pasa por
  Google. Se genera aleatoria; si se necesita entrar por ahí, fijarla con
  `manage.py changepassword <username>`.
- **El `centro`** es obligatorio por la FK pero informativo para el rol `ADMIN`,
  que ve todos los centros de todas formas.
- Para revocar un acceso se desmarca `activo` en el perfil. **No borrar el
  usuario**: se pierde el historial de acciones.

Verificar que un usuario pasa el filtro real del backend OIDC:

```bash
.venv/bin/python manage.py shell -c "
from django.contrib.auth.models import User
print(User.objects.filter(email__iexact='alguien@cmvalparaiso.cl',
                          is_active=True, perfil_gestion__activo=True).exists())
"
```

## 9. Correr el proyecto

```bash
.venv/bin/python manage.py runserver
```

| Qué | URL |
| --- | --- |
| Chatbot | http://localhost:8000/ |
| Términos | http://localhost:8000/terminos/ |
| Gestión | http://127.0.0.1:8000/ |
| Admin de Django | http://127.0.0.1:8000/admin/ |

`/admin/` y `/oidc/` viven **solo** en el urlconf de gestión: pedirlos en el
host del chatbot devuelve 404, y es el comportamiento correcto — el host
público no expone rutas de autenticación ni de administración.

En el día a día, después de la primera vez, basta con:

```bash
docker compose up -d
.venv/bin/python manage.py runserver
```

## Diagnóstico rápido

| Síntoma | Causa |
| --- | --- |
| `Access denied ... 'test_chat_bot_salud'` | Falta el `GRANT` del paso 4 |
| El contenedor no arranca | `DB_USER=root` en `.env`; usar otro nombre |
| Credenciales inválidas contra MySQL | `DB_USER`/`DB_PASSWORD` cambiaron después de crear el volumen |
| `Error 400: invalid_request` en Google | El `redirect_uri` usa un host fuera de la Public Suffix List (`gestion.localhost`) |
| `Error 400: redirect_uri_mismatch` | El host enviado no es idéntico al registrado (`localhost` ≠ `127.0.0.1`) |
| Login de Google OK pero rebota a `/sin-acceso/` | El usuario no tiene `PerfilUsuario` activo (paso 8) |
| `DisallowedHost` | Falta el hostname en `ALLOWED_HOSTS` |
| 404 en `/admin/` | Se está pidiendo en el host del chatbot en vez del de gestión |

## Pendiente

`.env.example`, `README.md` y `docs/arquitectura-modulo-gestion.md` siguen
documentando `gestion.localhost` como host local de gestión y como redirect
URI. Según el paso 6, esa configuración nunca pudo funcionar con el login de
Google. Conviene alinearlos con este documento.
