# Palabras clave de priorización editables — Diseño

Fecha: 2026-09-01
Versión: 1
Relacionado: `docs/superpowers/specs/2026-09-01-panel-administracion-gestion-design.md`,
`docs/arquitectura-modulo-gestion.md`, memoria de deuda de triaje.

> Documento para validar antes de escribir código. Tercera de tres specs del
> módulo de gestión. Es la única que toca deliberadamente el chatbot público,
> porque la priorización administrativa se calcula ahí.

## Objetivo

Hoy, las palabras clave que suben la prioridad administrativa de una solicitud
—`URGENT_KEYWORDS` y `MODERATE_KEYWORDS`— están escritas en
`solicitudes/priorizacion.py`. Cambiar una palabra exige editar código y hacer un
despliegue. La idea es que el **supervisor global (SUPERVISOR_DAS)** pueda mantener
esa lista desde el módulo, sin tocar código.

Solo las palabras son móviles. Los criterios estáticos —edad, credencial de
cuidador, condición declarada—, los puntajes de cada nivel y los umbrales de
clasificación siguen fijos en código.

## Alcance

**Dentro de alcance:**

- Un modelo para las palabras clave de prioridad, con su nivel.
- Migración que siembra las palabras actuales, sin cambiar el comportamiento.
- Lectura de esas palabras desde la lógica de priorización, en vez de constantes.
- Normalización del match: minúsculas y sin acentos.
- Una vista en gestión para que SUPERVISOR_DAS mantenga la lista.

**Fuera de alcance:**

- Editar puntajes (+4 / +1) o umbrales (6 / 4 / 2). Siguen en código.
- Editar los criterios estáticos (edad, credencial, condición).
- Recalcular la prioridad de solicitudes ya ingresadas.
- Resolver la calibración de triaje pendiente. Esto la habilita, no la resuelve.
- El panel de administración en sí (perfiles, reportería). Va en la spec 2; esta
  vista se cuelga de esa sección "Administración".

## Contexto de partida

- **`solicitudes/priorizacion.py`** define `URGENT_KEYWORDS` (9 palabras, +4) y
  `MODERATE_KEYWORDS` (6 palabras, +1). `calcular_prioridad` suma factores y
  clasifica: ≥6 URGENTE, ≥4 ALTA, ≥2 MEDIA, si no BAJA.
- **El match actual** es substring en minúsculas, sin normalizar acentos:
  "convulsión" con tilde no matchea la palabra "convulsion".
- **Se consume en dos lugares:** al crear la solicitud (`solicitudes/views.py`,
  guarda `priorizacion_solicitud` y `puntaje_prioridad`) y en gestión para mostrar el
  desglose por caso (`gestion/templatetags/gestion_ui.py::desglose_prioridad`, que
  llama a `desglosar_prioridad` por fila del selector).
- **Dirección de dependencia:** `gestion` depende de `solicitudes` (Gestion →
  Solicitud), nunca al revés. Esto decide dónde vive el modelo nuevo.

## Diseño

### Modelo (en la app `solicitudes`)

```python
class PalabraClavePrioridad(models.Model):
    class Nivel(models.TextChoices):
        URGENTE = "URGENTE", "Urgente"
        MODERADA = "MODERADA", "Moderada"

    texto = models.CharField(max_length=120)
    nivel = models.CharField(max_length=10, choices=Nivel.choices)
    activo = models.BooleanField(default=True)
```

El modelo vive en `solicitudes` porque es ahí donde se consume, y porque
`solicitudes` no puede depender de `gestion`. La UI de edición vive en `gestion`, que
sí puede importar el modelo de `solicitudes`. Así no se invierte la dependencia entre
el chatbot y el módulo interno.

Para evitar duplicados que difieren solo en mayúsculas o acentos, se guarda además
una forma normalizada (`texto_normalizado`, minúsculas y sin acentos) con
restricción de unicidad. Es la misma normalización que usa el match.

### Cambio en `priorizacion.py`

Las constantes `URGENT_KEYWORDS` / `MODERATE_KEYWORDS` se reemplazan por una lectura
de las palabras activas, agrupadas por nivel. El resto de `desglosar_prioridad` y
`calcular_prioridad` no cambia: mismos puntajes, mismos umbrales, mismos criterios
estáticos.

**Normalización del match.** Al comparar, se normalizan ambos lados —el texto clínico
de la solicitud y cada palabra— a minúsculas y sin acentos (`unicodedata`, quitando
los diacríticos). Con eso "convulsión" y "convulsion" matchean igual, y el supervisor
no tiene que preocuparse de las tildes al escribir. La misma normalización se usa
para la unicidad del modelo.

**Rendimiento.** `desglosar_prioridad` se llama una vez por fila en la tabla del
selector (40+ filas). Para no disparar una consulta por fila, las palabras activas se
cargan una sola vez y se cachean (Django cache) bajo una clave propia; el `save` y el
`delete` del modelo invalidan esa clave (vía señales). El chatbot las consulta una vez
por solicitud creada. Así, editar palabras rara vez y leerlas seguido no cuesta.

### Semilla (migración de datos)

Una migración de datos en `solicitudes` inserta las 9 palabras urgentes y las 6
moderadas actuales, con su nivel y `activo=True`. El día del despliegue, la lista en
BD es idéntica a las constantes de hoy: **el comportamiento no cambia** hasta que el
supervisor edite algo. La migración es reversible (borra las filas sembradas).

### Retroactividad: solo solicitudes nuevas

Las solicitudes ya ingresadas conservan su `priorizacion_solicitud` y
`puntaje_prioridad`, calculados al crearse. Cambiar las palabras **no recalcula**
histórico ni cola. Esto mantiene trazable con qué criterio se priorizó cada caso y no
reordena colas que el equipo ya está mirando.

### UI de edición (en gestión)

Bajo la sección "Administración" (spec 2), una vista **"Palabras clave de prioridad"**:

- Listar las palabras, agrupadas o marcadas por nivel (Urgente / Moderada) y estado.
- Agregar una palabra: texto + nivel.
- Editar: texto, nivel, activo.
- Dar de baja: `activo = False` (no se borra; deja de contar sin perder el registro).

**Acceso restringido a SUPERVISOR_DAS**, el supervisor global —no el de centro—, tal
como se pidió. Se agrega `puede_editar_palabras_prioridad(perfil)` en
`gestion/permisos.py`. (Si más adelante se quiere incluir a ADMIN, es una línea en esa
función; por ahora queda solo SUPERVISOR_DAS.)

## Enfoque técnico

- **El modelo y su migración viven en `solicitudes`; la UI en `gestion`.** Es el único
  cruce de esta serie de specs hacia el chatbot, y se hace en la dirección permitida.
- **Sin dependencias nuevas.** `unicodedata` es stdlib; el cache es el de Django.
- **La normalización se define una vez** (una función `normalizar(texto)`) y se usa en
  el match y en la unicidad del modelo, para que nunca diverjan.

## Pruebas

Django test runner, contra MySQL:

- **Semilla:** tras migrar, las palabras en BD reproducen exactamente el puntaje que
  daban las constantes para un conjunto de textos de prueba (comportamiento intacto).
- **Lectura desde BD:** agregar una palabra urgente hace que una solicitud nueva con
  ese término suba de prioridad; desactivarla lo revierte, todo sin tocar código.
- **Normalización:** una palabra "convulsion" matchea un texto con "convulsión" y
  viceversa; el match ignora mayúsculas y acentos.
- **Unicidad:** no se puede crear "Fiebre" si ya existe "fiebre" (misma forma
  normalizada).
- **Retroactividad:** cambiar palabras no altera `priorizacion_solicitud` de
  solicitudes existentes.
- **Acceso:** solo SUPERVISOR_DAS entra a la vista de palabras; los demás roles
  reciben 302/403.
- **Cache:** guardar o borrar una palabra invalida el cache y el siguiente cálculo ve
  el cambio.

## Decisiones tomadas

- Solo la lista de palabras y su nivel es editable; puntajes, umbrales y criterios
  estáticos siguen en código.
- El cambio aplica solo a solicitudes nuevas; no se recalcula histórico.
- El modelo vive en `solicitudes`; la UI en `gestion`.
- El match se normaliza sin acentos y sin mayúsculas.
- Acceso restringido a SUPERVISOR_DAS.
- Una migración siembra las palabras actuales para no cambiar el comportamiento.

## Consecuencias asumidas

- **Se toca el chatbot.** La priorización pasa de leer constantes a leer la BD. Es
  inherente a la feature y se hace en la dirección de dependencia correcta; la semilla
  garantiza que el día uno nada cambia.
- **Badge vs desglose en históricos.** El badge de prioridad usa el valor guardado
  (fuente de verdad); el desglose del selector se recalcula en vivo. Para una solicitud
  creada antes de un cambio de palabras, el desglose podría no sumar exactamente el
  badge. Como los cambios serán infrecuentes y la cola de pendientes rota a diario, el
  impacto es mínimo. Guardar el desglose histórico queda como mejora futura.
- **Lista vacía es válida.** Si el supervisor borra todas las palabras, la prioridad
  depende solo de los criterios estáticos. Es su decisión; no se fuerza un mínimo.
- **Esto no calibra el triaje.** Solo pone las palabras en manos del supervisor. La
  calibración clínica de fondo sigue pendiente y necesita su propio trabajo con el
  equipo de salud.

## Referencias

- `solicitudes/priorizacion.py` — lógica de priorización; aquí se reemplazan las constantes.
- `solicitudes/views.py` — cálculo al crear la solicitud.
- `solicitudes/models.py` — donde vive el modelo nuevo.
- `gestion/templatetags/gestion_ui.py` — `desglose_prioridad`, consumo por fila.
- `gestion/permisos.py` — regla de acceso de SUPERVISOR_DAS.

## Historial de versiones

| Versión | Fecha | Cambios |
| --- | --- | --- |
| 1 | 2026-09-01 | Versión inicial, validada en sesión de brainstorming. |
