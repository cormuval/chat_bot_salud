# Arquitectura: módulo de gestión y validación de solicitudes

## Contexto

El chatbot (`morbilidad.cmvalparaiso.cl`) es solo una parte del sistema. Las
solicitudes que crea deben ser **validadas y gestionadas por los equipos de
cada centro de salud**. Se necesita un módulo para revisarlas y gestionarlas,
más control de horario de disponibilidad del chatbot.

Estado actual del proyecto:

- Un solo proyecto Django (`cesfam_chatbot`) con una sola app (`solicitudes`).
- MySQL en producción detrás de nginx + HTTPS, deploy con runner self-hosted
  + pm2.
- `django.contrib.auth` y `django.contrib.admin` ya activos.
- Se llega al chatbot por `morbilidad.cmvalparaiso.cl`.

## Decisión: un único proyecto, no dos

**Se implementa el módulo de gestión como una app nueva (`gestion`) dentro del
mismo proyecto**, no como un proyecto separado que comparta la base de datos.

### Por qué no dos proyectos con BD compartida

El patrón "dos codebases apuntando a las mismas tablas" (shared-database
integration) es un anti-patrón que solo se justifica con **equipos
independientes, cadencias de release distintas o stacks diferentes**. Ninguno
aplica: mismo autor, mismo Django, proyecto chico.

| Criterio | Un proyecto (app nueva) | Dos proyectos, misma BD |
| --- | --- | --- |
| Dueño del esquema / migraciones | Uno solo, sin ambigüedad | Dos historiales sobre las mismas tablas → conflictos, o `managed=False` + modelos duplicados que se desincronizan |
| Relación `Solicitud` ↔ gestión | FK real, integridad garantizada | Referencias frágiles entre codebases |
| Fuente de verdad del modelo | Única | Duplicada, con drift asegurado |
| Deploy | Uno (runner + pm2 + nginx ya existentes) | Dos deploys, dos configs |

### Separación público/interno

La preocupación válida ("el chatbot es público, la gestión es interna") se
resuelve por **app + auth + routing**, no por proyecto + BD separada:

- App `solicitudes` (existente): dueña de `Solicitud`, solo la crea el chatbot.
- App `gestion` (nueva): dueña del ciclo de vida de validación; lee
  `Solicitud` y escribe su propio modelo.
- Endpoints de gestión detrás de `@login_required` + filtrado por rol y centro.

## Decisiones tomadas

- **Acceso:** subdominio propio `seleccion.cmvalparaiso.cl`, mismo deploy /
  mismo WSGI; nginx enruta ambos hosts y se agrega a `ALLOWED_HOSTS` +
  `CSRF_TRUSTED_ORIGINS`.
- **Login:** únicamente OAuth con Google Workspace. No hay contraseñas
  propias ni formulario de login local.
- **Usuarios:** un rol por usuario y un centro (más un centro satélite
  opcional). El alcance multi-centro se resuelve por rol, no por lista de
  centros.
- **Alcance:** MVP funcional primero (Etapa 1, Etapa 2 y ventana horaria),
  iterar después.

## Diseño de las piezas

### Autenticación: OAuth con Google Workspace

Los funcionarios ya usan Google Workspace, así que **el único mecanismo de
login es OAuth con Google**. Consecuencias de diseño:

- La **identidad** (correo, nombre) la provee Google y vive en el `User` de
  `django.contrib.auth`. No se guardan contraseñas: el modelo de usuario no
  se reemplaza, solo se deja de usar el login por formulario.
- Se restringe el `hd` (hosted domain) al dominio institucional; un correo
  Gmail personal no puede entrar aunque el flujo OAuth sea válido.
- La **autorización** (rol y centro) no viene de Google: vive en una tabla
  propia del sistema, descrita abajo.
- Un correo del dominio que autentica correctamente pero **no tiene fila en
  la tabla de perfiles queda rechazado**. La tabla de perfiles es la lista de
  autorización: solo entra quien fue dado de alta antes. No se crean cuentas
  automáticamente al primer login.

### Perfil de usuario: rol y centro

Tabla complementaria (`PerfilUsuario` en la app `gestion`) con
`OneToOne → User`. Aporta lo que Google no sabe:

- `rol` — exactamente **uno** por usuario (campo con choices, no M2M). Los
  roles compuestos ya cubren las combinaciones necesarias.
- `centro` — FK a `Centro`, y `centro_satelite` FK opcional, para el caso
  real de un CESFAM con su CECOSF asociado.
- `activo` — permite revocar el acceso sin borrar el historial de acciones.

`correo` y `nombre` **no se duplican acá**: son de `User`, poblados por Google.

#### Roles

| Rol | Alcance | Qué puede hacer |
| --- | --- | --- |
| `ADMIN` | Todos los centros | Todo |
| `SUPERVISOR_DAS` | Todos los centros | Vista administrativa |
| `SUPERVISOR_CENTRO` | Su centro (+ satélite) | Vista administrativa |
| `SOME` | Su centro (+ satélite) | Gestión de perfiles + Etapa 1 + Etapa 2 |
| `FULL` | Su centro (+ satélite) | Etapa 1 + Etapa 2 |
| `SELECTOR` | Su centro (+ satélite) | Etapa 1 (selección de demanda) |
| `COMUNICADOR` | Su centro (+ satélite) | Etapa 2 (contacto y agendamiento) |

Solo `SELECTOR` y `COMUNICADOR` —y quienes los engloban, `FULL` y `SOME`—
participan de la **operación**. Los tres roles supervisores tienen vista
administrativa: `SUPERVISOR_CENTRO` acotada a su centro, `ADMIN` y
`SUPERVISOR_DAS` sobre todos los centros.

`SOME` es el único rol operativo que además administra perfiles (dar de alta
usuarios de su centro y asignarles rol); `ADMIN` lo hace sobre todo el sistema.

El alcance se deriva del rol, no de una lista de centros por usuario: por eso
se descarta la M2M usuario ↔ centros que contemplaba la versión anterior de
este documento.

### Modelo de gestión

`Gestion` en la app nueva, con `OneToOne → Solicitud` (mantiene el modelo del
chatbot limpio del flujo administrativo, pero con FK real por compartir BD en
un mismo proyecto). Guarda la decisión del selector, la gestión de contacto del
comunicador y el cierre, en campos separados.

Las dos etapas corresponden una a una con los roles operativos: Etapa 1 la
opera el `SELECTOR` y Etapa 2 el `COMUNICADOR`.

El detalle del modelo, con todos sus campos, está en
`docs/superpowers/specs/2026-07-28-modulo-seleccion-design.md`. Ese documento
es la fuente de verdad del flujo; acá solo queda el encuadre arquitectónico.

Filtrado del queryset: `ADMIN` y `SUPERVISOR_DAS` ven todos los centros; el
resto ve solo su `centro` y su `centro_satelite`. El filtro se deriva del rol
del perfil, no de una lista de centros por usuario.

### Etapa 1 — cola del selector

Vista custom tipo *worklist* (no el admin de Django, que no calza con el flujo).
Lista de pendientes del centro, ordenada por la prioridad que calcula el
chatbot. Sobre cada solicitud el selector toma una de tres decisiones:
**aceptar** (registrando una prioridad clínica propia), **rechazar** (con
motivo de un catálogo editable) o **no aplica** (pruebas o simulaciones, que
salen del flujo).

> Reemplaza a la versión anterior de este documento, que definía la Etapa 1
> como "asignar / denegar hora" con estados `PENDIENTE` / `CON_HORA` /
> `SIN_HORA`, y un contador de cupos informativo. La administración de cupos
> queda fuera de alcance.

Conviven **dos prioridades con la misma escala** y sin sobrescribirse: la
administrativa, que calcula el chatbot y ordena esta cola, y la clínica, que
asigna el selector y ordena la cola del comunicador.

### Etapa 2 — comunicador y WhatsApp por deep-link

Una sola tabla: aceptadas primero, ordenadas por prioridad clínica, y las
rechazadas al final. El comunicador llama a las aceptadas para ofrecer la
citación y registra el desenlace; los "no contesta" suman un intento y el caso
sigue abierto.

Sin integración con la API de WhatsApp. El backend arma el enlace
`https://wa.me/<telefono>?text=<mensaje urlencoded>`. El teléfono ya se guarda
con código de país (`formatear_telefono_con_codigo_pais`), y el texto sale del
motivo de rechazo, editable desde el admin. Usar el enlace **registra un
intento, no un contacto**: abrir una ventana no prueba que el mensaje se haya
enviado.

Los rechazados **se cierran solos a las 24 horas**, distinguiendo si se les
avisó por WhatsApp o si nadie los contactó. Los aceptados no se cierran solos.

### Ventana horaria del chatbot (L-V 08:00–08:20)

Config en BD, no hardcodeada: modelo singleton `ConfiguracionChatbot`
(`activo`, días, `hora_inicio`, `hora_fin`, `mensaje_fuera_horario`).

**Se valida en el backend, no solo en el JS.** Hoy `crear_solicitud`
(`solicitudes/views.py:77`) aceptaría un POST a cualquier hora; hay que
rechazar fuera de ventana ahí, usando `America/Santiago` (ya configurado en
`TIME_ZONE`). El frontend muestra el mensaje amable; el backend hace cumplir
la regla.

## Impacto en configuración

- `ALLOWED_HOSTS` y `CSRF_TRUSTED_ORIGINS`: agregar `seleccion.cmvalparaiso.cl`.
- nginx: nuevo server_name apuntando al mismo WSGI.
- `INSTALLED_APPS`: agregar `gestion`.
- OAuth de Google: `client_id` y `client_secret` por `.env` (nunca en el
  repo), y agregarlos al secret `ENV_PROD` del deploy. El redirect URI
  autorizado en Google Cloud Console apunta al subdominio de gestión.
- Login local: `LOGIN_URL` apuntando al flujo OAuth. El admin de Django queda
  solo para superusuarios.

## Estado

Decision de arquitectura **aprobada**. Autenticacion y perfiles
**implementados** (ver `docs/superpowers/plans/2026-07-27-login-google-perfiles.md`).
Modelo `Gestion`, cola del selector, tabla del comunicador, enlace de WhatsApp
y cierre automatico de rechazados **implementados** (ver
`docs/superpowers/plans/2026-08-19-modulo-seleccion.md`).

Pendientes fuera de este alcance: reportes, estadisticas, tableros, agenda
propia, administracion de cupos, UI de gestion de perfiles para el rol `SOME`,
API de WhatsApp y mejoras futuras del chatbot.

## Referencias

- `docs/superpowers/specs/2026-07-28-modulo-seleccion-design.md` — flujo
  completo de las Etapas 1 y 2, y modelo `Gestion` en detalle.
- `solicitudes/models.py` — modelo `Solicitud`.
- `solicitudes/views.py:77` — `crear_solicitud` (punto donde validar horario).
- `cesfam_chatbot/settings.py:18-30` — `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS`.
