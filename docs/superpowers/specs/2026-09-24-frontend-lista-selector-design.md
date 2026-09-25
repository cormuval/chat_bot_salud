# Revision de frontend — vista de lista del selector

Fecha: 2026-09-24
Modulo: `gestion` (host `seleccion.cmvalparaiso.cl`)
Archivos principales: `gestion/templates/gestion/_tabla_selector.html`,
`gestion/templates/gestion/selector_lista.html`, `static/css/gestion.css`,
`gestion/tests.py`.

## Contexto

Tras cerrar la serie de 4 specs, el fix #36 resolvio que `/selector/` se viera en
blanco a 100% de zoom (texto largo sin espacios inflaba la tabla y reventaba el grid
`.gestion-shell`). Pero la tabla quedo a medias:

- La celda Motivo usa `<span class="truncate">`, y `.truncate` (`max-width`,
  `text-overflow: ellipsis`) esta sobre un `<span>` **inline**, donde esas reglas no
  aplican: **nunca trunco**. Es la causa original del desborde (#28).
- `.data-table` usa `table-layout` automatico: las columnas se dimensionan al
  contenido y un Motivo muy largo aplasta a las demas. Con el `overflow-wrap:
  anywhere` de #36, los nombres se cortan letra por letra.
- La pestaña "Decididas corregibles" agrega una columna (Correccion) y sigue
  desbordando.

Ademas, en la vista de lista: las pestañas (Pendientes / Decididas / No aplica) no
marcan cual esta activa (reusan la clase `.gestion-nav` del nav principal), y la
tarjeta de cupos se estira a todo el ancho cuando hay un solo centro.

Alcance acordado: **toda la vista de lista del selector** (tabla + pestañas +
tarjetas de cupos + espaciado). Otras tablas que usan `.data-table` (comunicador,
perfiles, palabras) **no se tocan**.

## Diseño

### 1. Tabla del selector con columnas fijas

- Clase modificadora `data-table--selector` en la tabla de `_tabla_selector.html`;
  todas las reglas nuevas se acotan a ella (las otras `.data-table` no cambian).
- `table-layout: fixed` + un `<colgroup>` con una `<col>` por columna (las
  condicionales Centro y Correccion llevan su `<col>` bajo la misma condicion que su
  `<th>`). Anchos:

| Columna | Ancho | Comportamiento |
|---|---|---|
| Paciente | 18% | envuelve por palabras |
| Centro (si `mostrar_columna_centro`) | 16% | envuelve por palabras |
| Prioridad administrativa | 11rem | badge, sin cortes |
| Motivo | resto (sin ancho) | **1 linea con "…"** |
| Fecha | 9rem | relativa |
| Correccion (solo `seccion == "decididas"`) | 12rem | envuelve |
| Abrir | 5rem | enlace (se mantiene) |

- Como el Motivo no tiene ancho propio, absorbe el espacio restante: la columna
  extra de "Decididas corregibles" solo le resta ancho al Motivo y deja de desbordar.
- El `overflow-wrap: anywhere` de #36 se mantiene en las celdas: con anchos fijos ya
  no aplasta columnas; solo corta una palabra que no cabe en su columna (red de
  seguridad para nombres/centros sin espacios).

### 2. Motivo truncado (arreglar `.truncate`)

- `.truncate` pasa a `display: block` y `max-width: 100%` (en vez de 34rem), con
  `white-space: nowrap; overflow: hidden; text-overflow: ellipsis`, de modo que
  trunca al ancho de su celda.
- El `<span class="truncate">` del Motivo lleva `title="{{ texto completo }}"` para
  ver el texto completo al pasar el mouse. El texto completo sigue en el detalle del
  caso.

### 3. Pestañas con estado activo

- La nav de secciones deja de usar `.gestion-nav` (que es el estilo del nav principal)
  y pasa a una clase propia `tab-nav`.
- La pestaña de la `seccion` actual lleva `aria-current="page"` y la clase
  `is-active`, con estilo resaltado (fondo/borde de color primario). Los `href`
  (`?seccion=decididas`, etc.) no cambian.

### 4. Tarjeta de cupos compacta

- `.cupos-selector__grid` pasa de `auto-fit` a `auto-fill` (con una sola tarjeta no se
  estira a todo el ancho; cada tarjeta ~260–360px).
- Los disponibles se muestran como **numero grande** ("16" grande + "/ 18
  disponibles" chico, o "Sin cargar"), con el input + "Guardar" en una linea.
- Sin cambios de comportamiento: mismo formulario POST a `gestion:guardar_cupo`.

### 5. Vista movil (< 900px)

- Se mantiene el modo tarjetas existente (filas como tarjetas, `data-label`). El
  layout fijo no aplica ahi (las tablas pasan a `display: block`; el `<colgroup>` se
  ignora).
- El Motivo en modo tarjeta muestra **hasta 2 lineas** (`-webkit-line-clamp: 2`)
  en vez de 1, reemplazando el actual `.truncate { white-space: normal }` que lo
  mostraba entero.

### 6. Espaciado

Separacion consistente (tokens `--space-*` existentes) entre titulo, bloque de cupos,
pestañas y tabla.

## Testing

`gestion/tests.py` (TestCase contra MySQL 8.4; runner de Django). Asercion sobre el
HTML renderizado de `/selector/` y sobre el CSS como texto (convencion del repo):

- La tabla renderizada tiene la clase `data-table--selector` y un `<colgroup>`;
  en `?seccion=decididas` aparece la `<col>` de Correccion y en pendientes no.
- La pestaña activa lleva `aria-current="page"`: en `/selector/` es Pendientes; en
  `?seccion=decididas` es Decididas corregibles (y Pendientes no).
- El Motivo lleva `class="truncate"` con `title=` que contiene el texto completo.
- `gestion.css` define `table-layout: fixed` acotado a `.data-table--selector`,
  `.truncate` con `display: block`, `.tab-nav` y el estado `is-active`, y
  `.cupos-selector__grid` con `auto-fill`.
- Los tests existentes del selector (hrefs `?seccion=decididas`, "Cupos del dia",
  render de tarjetas) siguen pasando.

**Verificacion manual (obligatoria, es cambio visual):** a 100% de zoom, Pendientes y
Decididas corregibles se ven como tabla sin desbordar, nombres legibles (sin cortes
letra por letra), Motivo en una linea con "…"; la pestaña activa se distingue; la
tarjeta de cupos no ocupa todo el ancho; a zoom alto / movil, modo tarjeta con Motivo
en 2 lineas.

Correr `.venv/bin/python manage.py test` antes de dar la tarea por terminada.

## Fuera de alcance

- Tablas del **comunicador**, perfiles y palabras (siguen con `.data-table` sin
  cambios; la del comunicador podria tener el mismo aplastamiento — revisarla aparte).
- Vista de detalle del caso (`selector_detalle`).
- Cambios de logica/vistas: es un cambio de templates + CSS.
