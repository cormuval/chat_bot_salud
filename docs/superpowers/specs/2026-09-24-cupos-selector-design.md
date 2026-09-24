# Spec 4 — Cupos reales disponibles en el selector

Fecha: 2026-09-24
Modulo: `gestion` (modulo interno, host `seleccion.cmvalparaiso.cl`)
Archivos principales: `gestion/models.py`, `gestion/views.py`, `gestion/urls.py`,
`gestion/permisos.py`, `gestion/templates/gestion/selector_lista.html`,
`gestion/tests.py`, migracion nueva.

## Contexto

Hoy la disponibilidad de cupos medicos por CESFAM llega al selector por fuera de la
plataforma (un "Informe Diario" manual). El acta pide **capturar ese dato dentro del
selector** para reemplazar ese informe: que el selector cargue los cupos del dia y
vea cuantos le quedan disponibles a medida que acepta solicitudes.

Decisiones tomadas en el brainstorming:
- **Granularidad:** un numero de cupos por **centro y por dia** (sin distinguir
  prioridad ni profesional).
- **Quien carga:** el **propio selector** (roles SELECTOR / FULL / SOME), al empezar
  su jornada, para los centros de su alcance.
- **Efecto:** **contador informativo**. Descuenta con cada solicitud aceptada pero
  **no impide** aceptar de mas (sin tope duro); la decision clinica manda.
- **Disponibles = dato derivado** (no un contador que se decrementa y guarda), para
  no desincronizarse.

Estado actual relevante:
- El selector lista solicitudes en `selector_lista` (`gestion/views.py`), template
  `gestion/templates/gestion/selector_lista.html` (+ parcial `_tabla_selector.html`).
- Aceptar una solicitud fija `Gestion.decision = "ACEPTADA"` y `fecha_decision`
  (DateTimeField). Rechazar/No aplica no cuentan como aceptada.
- El alcance de un selector es su `centro` (+ `centro_satelite` opcional):
  `PerfilUsuario.centros_permitidos()`. Los roles globales (ADMIN, SUPERVISOR_DAS)
  son de solo lectura, no cargan cupos.
- `Centro` vive en `solicitudes.models`.
- **Gotcha de MySQL:** filtrar `fecha_decision__date == hoy` genera
  `DATE(CONVERT_TZ(...))`, que devuelve NULL si MySQL no tiene tablas de zona horaria
  (ver `docs/deuda...` y la Spec del CSV). Se debe contar "aceptadas de hoy" con
  limites datetime tz-aware `[inicio, fin)` (el mismo patron de
  `gestion/reportes.py: limites_datetime`), no con `__date`.

## Modelo

Nuevo `CupoDiario` en `gestion/models.py`:

- `centro` — FK a `solicitudes.Centro` (PROTECT o CASCADE segun patron del repo).
- `fecha` — `DateField` (fecha local America/Santiago del dia de carga).
- `cupos_iniciales` — `PositiveSmallIntegerField` (>= 0).
- `registrado_por` — FK a `User` (quien cargo/edito por ultima vez), nullable.
- `creado_en` / `actualizado_en` — timestamps.
- `Meta`: `unique_together = ("centro", "fecha")` (un registro por centro y dia);
  ordering razonable.

Guarda **solo** el numero cargado. Los "disponibles" no se persisten.

## Calculo de disponibles (derivado)

Helper (en `gestion/models.py` como metodo/queryset, o en un modulo de servicio de
`gestion`), p. ej. `cupos_del_alcance(perfil, fecha)` que devuelve, por cada centro
del alcance del selector, un dict con:

```
{ "centro": <Centro>, "iniciales": <int|None>, "aceptadas": <int>, "disponibles": <int|None> }
```

- `iniciales` = `cupos_iniciales` del `CupoDiario` de (centro, fecha) o `None` si aun
  no se cargo hoy.
- `aceptadas` = cantidad de `Gestion` con `decision = ACEPTADA` cuyo
  `solicitud.centro_salud == centro` y `fecha_decision` dentro de `[inicio, fin)` del
  dia (bordes tz-aware, **sin** `__date`).
- `disponibles` = `iniciales - aceptadas` cuando `iniciales` no es `None`; si no,
  `None` (se muestra "sin cargar").

`disponibles` puede ser 0 o negativo (informativo, sin bloqueo).

## Vistas y rutas

- **`selector_lista`** (`gestion/views.py`): agrega al contexto los cupos del alcance
  del perfil para la fecha de hoy (via el helper). El template los muestra arriba de
  la cola.
- **`guardar_cupo`** (nueva vista, POST): recibe `centro_id` y `cupos_iniciales`,
  valida que el centro este en el alcance del selector y que el rol pueda cargar
  cupos, y hace `update_or_create` del `CupoDiario` de (centro, hoy) fijando
  `cupos_iniciales` y `registrado_por`. Redirige de vuelta a `selector_lista`.
- **`gestion/urls.py`**: nueva ruta para `guardar_cupo` (name `gestion:guardar_cupo`).

## Permisos

- Nuevo helper en `gestion/permisos.py`: `puede_cargar_cupos(perfil)` = rol en
  `ROLES_SELECTOR` (SELECTOR, FULL, SOME).
- `guardar_cupo` exige `puede_cargar_cupos(perfil)` y que `centro_id` este en
  `perfil.centros_permitidos()`; si no, redirige a `gestion:sin_acceso` (patron
  existente).
- La tarjeta de carga en el template solo se muestra a roles que pueden cargar
  (los roles de solo lectura ven el contador si aplica, pero sin input — o
  simplemente no se les muestra, segun se defina en el plan; MVP: se muestra a los
  roles de selector).

## Frontend (selector)

En `selector_lista.html`, arriba de la cola, una tarjeta por cada centro del alcance:

- Muestra **"Cupos [Centro]: disponibles / iniciales"** (o "sin cargar" si `iniciales`
  es `None`).
- Un pequeño formulario (POST a `guardar_cupo`) con un input numerico para fijar o
  editar `cupos_iniciales` del dia. Editable durante el dia.
- El numero de disponibles se recalcula en cada carga de pagina (y por lo tanto tras
  cada aceptacion, ya que el selector recarga/navega), sin decremento manual.

Sin JS nuevo obligatorio (formulario POST normal). Estilo consistente con las
tarjetas existentes del selector.

## Por dia

Los cupos son por dia calendario (America/Santiago). Un dia nuevo no arrastra el
`CupoDiario` del anterior: si hoy no hay registro, se pide cargar. El historico de
dias previos queda en la tabla pero no se muestra en el selector (ver Fuera de
alcance).

## Testing

`gestion/tests.py` (TestCase contra MySQL 8.4; runner de Django, no SQLite):

- **Modelo:** `unique_together (centro, fecha)` impide dos registros del mismo centro
  y dia; `cupos_iniciales` no acepta negativos.
- **Calculo de disponibles:** con N `cupos_iniciales` y M solicitudes aceptadas hoy en
  ese centro, `disponibles == N - M`. Verificar que **no** cuenta: rechazadas,
  aceptadas de otro dia, aceptadas de otro centro, ni pendientes.
- **Gotcha tz:** el conteo de aceptadas de hoy usa limites datetime y su queryset
  **no** contiene `CONVERT_TZ` (assert sobre `str(qs.query)`), para no repetir el bug
  del CSV.
- **guardar_cupo:** un rol de selector carga/edita el cupo de un centro de su alcance
  (update_or_create, no duplica); un rol de selector NO puede cargar para un centro
  fuera de su alcance (redirect a sin_acceso, sin crear registro); un rol sin permiso
  (p. ej. SUPERVISOR_CENTRO) no puede cargar.
- **Vista selector:** el contexto trae los cupos del alcance para hoy.

Correr `.venv/bin/python manage.py test` antes de dar la tarea por terminada.

## Fuera de alcance

- **Reporte historico de cupos** (cargados vs usados por rango de fechas): documentado
  como issue #34; no se implementa en esta spec.
- Tope duro / bloqueo de aceptacion por falta de cupos (se decidio contador
  informativo).
- Granularidad por prioridad o por profesional.
- No se toca el chatbot (`solicitudes`) salvo el uso del modelo `Centro` (solo
  lectura / FK).
