# Panel de administración del módulo de gestión — Diseño

Fecha: 2026-09-01
Versión: 1
Relacionado: `docs/superpowers/specs/2026-09-01-acceso-navegacion-gestion-design.md`,
`docs/arquitectura-modulo-gestion.md`

> Documento para validar antes de escribir código. Segunda de tres specs del
> módulo de gestión. La primera cubre acceso y navegación; la tercera, los
> parámetros de priorización editables.

## Objetivo

Dar a los roles de mando un lugar dentro del módulo para dos tareas que hoy solo
se hacen tocando la base de datos o el admin de Django:

1. **Gestionar perfiles de acceso** (crear, modificar, dar de baja), es decir dar y
   revocar el acceso de los funcionarios al módulo.
2. **Descargar reportes** operativos: qué solicitudes ingresaron, qué contactó el
   comunicador y qué decidió el selector.

Hoy los perfiles se administran por el admin de Django, que exige ser superusuario
—un eje de permiso distinto del rol de `PerfilUsuario`— y vive en una UI y un login
aparte. Y no hay ninguna forma de exportar datos operativos. Esta spec resuelve
ambas cosas dentro del módulo, con su mismo login con Google y su modelo de roles.

## Alcance

**Dentro de alcance:**

- Sección "Administración" en la navegación, visible solo para roles de mando.
- CRUD de perfiles con alcance y guardas de seguridad por rol.
- Tres reportes descargables en CSV, con filtro de fecha y alcance por centro.

**Fuera de alcance:**

- Edición de las palabras clave de prioridad administrativa. Va en la spec 3.
- Página de login, 404 y sin-acceso. Van en la spec 1.
- Cambios al chatbot público.
- Reportes con gráficos, tableros o estadísticas en pantalla. Estos tres reportes
  son descargas de datos, no visualizaciones.
- Edición masiva de perfiles o importación desde archivo.

## Contexto de partida

- **`PerfilUsuario`** complementa al `User` de Django con `rol`, `centro`,
  `centro_satelite`, `anexo_telefono` y `activo`. Ya funciona como lista de
  autorización: sin perfil activo no se entra.
- **Roles** (`PerfilUsuario.Rol`): ADMIN, SUPERVISOR_DAS, SUPERVISOR_CENTRO, SOME,
  FULL, SELECTOR, COMUNICADOR. `ROLES_TODOS_LOS_CENTROS = {ADMIN, SUPERVISOR_DAS}`.
- **`centros_permitidos()` / `del_alcance()`** ya implementan el filtrado por centro
  que las colas del selector y del comunicador respetan. La reportería reutiliza ese
  mismo alcance.
- **`OIDC_CREATE_USER = False`**: el login con Google no crea cuentas. El `User` de
  Django debe existir —con `is_active=True`— antes del primer login para que
  `filter_users_by_claims` haga el match por email. Esto condiciona el alta de
  perfiles (ver más abajo).
- **`RegistroContacto`** (bitácora del comunicador) y las decisiones en `Gestion`
  ya guardan lo que los reportes necesitan.

## Diseño

### Shell del panel

Sección **"Administración"** en la nav del `base.html`, visible solo para roles con
acceso (ADMIN, SUPERVISOR_DAS, SUPERVISOR_CENTRO). Una vista de aterrizaje
(`gestion:admin_panel`) con dos accesos: **Perfiles** y **Reportes**. Cada uno se
muestra según lo que el rol puede hacer.

El acceso se decide en `gestion/permisos.py`, siguiendo el patrón de las funciones
`puede_*` que ya existen:

- `puede_administrar_perfiles(perfil)` → ADMIN, SUPERVISOR_DAS, SUPERVISOR_CENTRO.
- `puede_ver_reportes(perfil)` → ADMIN, SUPERVISOR_DAS, SUPERVISOR_CENTRO.

### Parte A — Gestión de perfiles

**El alta crea `User` + `PerfilUsuario`.** Como el login no crea cuentas, dar de alta
a una persona significa asegurar que exista su `User` de Django. El formulario de
alta pide **email, rol y centro(s)**; la vista:

1. Busca el `User` por email (case-insensitive). Si no existe, lo crea con
   `is_active=True` y sin contraseña utilizable (`set_unusable_password`): el acceso
   es solo por Google.
2. Crea el `PerfilUsuario` asociado. Si el usuario ya tenía perfil, se edita en vez
   de duplicar (la relación es OneToOne).

**Operaciones:**

- **Listar** perfiles dentro del alcance: ADMIN y SUPERVISOR_DAS ven todos;
  SUPERVISOR_CENTRO ve solo los de su centro.
- **Crear / modificar:** email (solo en alta), rol, centro base, centro satélite,
  anexo, activo.
- **Dar de baja:** `activo = False`. Baja lógica, no borrado: el modelo existe para
  "revocar el acceso sin borrar el historial". Reactivable poniendo `activo = True`.

**Guardas de seguridad (validadas en el servidor, no solo ocultas en el form):**

| Rol que administra | Sobre qué perfiles | Roles que puede asignar |
| --- | --- | --- |
| ADMIN, SUPERVISOR_DAS | Todos los centros | Cualquiera |
| SUPERVISOR_CENTRO | Solo su centro | Solo operativos: SELECTOR, COMUNICADOR, FULL, SOME |

Un SUPERVISOR_CENTRO no puede crear ni editar perfiles ADMIN, SUPERVISOR_DAS ni
SUPERVISOR_CENTRO, ni operar sobre perfiles de otro centro. Estas reglas se
comprueban al recibir el POST —no basta con no mostrar las opciones—, porque es la
superficie más sensible del módulo: un hueco aquí es escalada de privilegios.

**Nota:** un administrador no debería poder darse de baja ni degradarse a sí mismo y
quedar sin ningún ADMIN activo. La validación de "no dejar el sistema sin
administradores" se resuelve en el plan; la spec la deja señalada como requisito.

### Parte B — Reportería

Tres reportes. Cada uno es una vista con un formulario **fecha desde / fecha hasta**
y un botón de descarga. El centro se filtra automáticamente por el alcance del perfil
(`del_alcance`); no hay selector de centro manual. Salida **CSV UTF-8 con BOM**
—abre en Excel y Sheets con tildes y eñes correctas, sin agregar dependencias— y se
genera con `StreamingHttpResponse` por si el volumen crece.

| Reporte | Fuente | Campo de fecha | Columnas |
| --- | --- | --- | --- |
| Solicitudes creadas | `Solicitud` | `date_solicitud` | fecha, RUT, nombre, teléfono, edad, sexo, centro, motivo, detalle, prioridad administrativa, puntaje |
| Contactabilidad del comunicador | `RegistroContacto` | `creado_en` | fecha, paciente, RUT, centro, canal, resultado, usuario, mensaje |
| Gestiones del selector | `Gestion` | `fecha_decision` | fecha de decisión, paciente, RUT, centro, decisión, prioridad clínica, motivo de rechazo, decidido por |

El rango de fechas es obligatorio para acotar la descarga. Sin `desde/hasta` válidos
la vista no exporta y pide completarlos.

**Protección de datos.** El reporte de solicitudes contiene datos personales
sensibles (RUT, teléfono, síntomas). El acceso queda restringido por rol y alcance de
centro. Es un punto a declarar en la revisión de ciberseguridad y de protección de
datos: quién puede descargar qué, y que la descarga respeta el aislamiento por centro
que el resto del módulo ya aplica.

## Enfoque técnico

- **Sin dependencias nuevas.** CRUD con `ModelForm` y vistas de `gestion`; CSV con el
  módulo `csv` de la stdlib y `StreamingHttpResponse`.
- **Se reutiliza el alcance existente** (`centros_permitidos`, `del_alcance`) en vez
  de reinventar el filtrado por centro.
- **Las guardas de rol viven en `permisos.py`** junto a las demás reglas del módulo,
  para no dispersar la lógica de autorización.
- **Un archivo por responsabilidad:** vistas de perfiles y vistas de reportes
  separadas; los reportes, al compartir estructura (filtro de fecha + streaming CSV),
  se apoyan en un ayudante común de exportación.

## Pruebas

Django test runner, contra MySQL:

- **Acceso:** un rol operativo (SELECTOR) no ve la sección Administración ni puede
  entrar a sus rutas (302/403); ADMIN, SUPERVISOR_DAS y SUPERVISOR_CENTRO sí.
- **Alta:** crear un perfil con un email nuevo crea el `User` (`is_active=True`, sin
  contraseña utilizable) y el `PerfilUsuario`. Con un email existente, reutiliza el
  `User`.
- **Baja:** dar de baja pone `activo = False` y no borra la fila.
- **Guardas:** un SUPERVISOR_CENTRO no puede crear un ADMIN ni tocar un perfil de otro
  centro (el POST se rechaza aunque se fuerce el dato).
- **No dejar sin ADMIN:** no se puede dar de baja al último ADMIN activo.
- **Reportes — alcance:** un SUPERVISOR_CENTRO solo obtiene filas de su centro; un
  ADMIN, de todos.
- **Reportes — fecha:** el rango filtra por el campo de fecha correcto de cada
  reporte; sin rango válido no exporta.
- **Reportes — formato:** la respuesta es CSV con BOM UTF-8 y las columnas descritas.

## Decisiones tomadas

- Panel propio dentro del módulo, con el login y los roles del módulo; no se usa el
  admin de Django ni se exige ser superusuario.
- Perfiles: ADMIN y SUPERVISOR_DAS gestionan a nivel global; SUPERVISOR_CENTRO solo
  su centro y solo roles operativos.
- El alta de perfil crea también el `User` de Django por email.
- La baja es lógica (`activo = False`), no borrado.
- Reportes en CSV UTF-8, con rango de fecha obligatorio y alcance por centro.
- Los tres reportes son descargas, no tableros.

## Consecuencias asumidas

- **Se crean `User` sin contraseña utilizable.** Es correcto: el acceso es solo por
  Google. Quedan cuentas "pre-autorizadas" que recién se completan al primer login,
  igual que hoy pero ahora desde el panel en vez del shell.
- **Los reportes exponen datos personales a quien tiene el rol.** Es el propósito del
  reporte; el control es el rol y el alcance de centro, más la mención explícita en la
  revisión de protección de datos.
- **El panel amplía lo que ADMIN ve.** Hoy ADMIN es solo lectura sobre las colas; con
  esta spec suma administración. No cambia su acceso a las colas.

## Referencias

- `gestion/models.py` — `PerfilUsuario`, `Gestion`, `RegistroContacto`, alcance por centro.
- `gestion/permisos.py` — funciones `puede_*`; aquí van las nuevas reglas.
- `gestion/auth.py` — `OIDC_CREATE_USER = False` y el match por email en el login.
- `solicitudes/models.py` — `Solicitud`, fuente del reporte de solicitudes.
- `gestion/templates/gestion/base.html` — navegación donde entra la sección Administración.

## Historial de versiones

| Versión | Fecha | Cambios |
| --- | --- | --- |
| 1 | 2026-09-01 | Versión inicial, validada en sesión de brainstorming. |
