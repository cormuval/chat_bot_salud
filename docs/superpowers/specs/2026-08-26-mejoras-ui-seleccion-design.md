# Mejoras pendientes del Selector y del Comunicador — Diseño

Fecha: 2026-08-26
Versión: 1
Relacionado: `docs/superpowers/specs/2026-08-20-ui-ux-modulo-seleccion-design.md`,
`docs/superpowers/specs/2026-07-28-modulo-seleccion-design.md`,
`docs/arquitectura-modulo-gestion.md`

> Documento para validar antes de escribir código. Recoge las nueve mejoras que el
> equipo levantó tras usar el módulo entregado en el PR #15: tres del Selector y
> seis del Comunicador.

## Objetivo

El módulo de gestión ya se opera. De ese uso salieron nueve observaciones, y al
revisarlas contra el código aparecen dos hechos que cambian cómo hay que abordarlas.

El primero: **ocho de las nueve son de presentación**, pero una —el historial de
comunicaciones— no se puede resolver con CSS porque el dato no existe. Hoy `Gestion`
guarda solo el *último* contacto (`intentos_contacto`, `fecha_ultimo_intento`,
`ultima_accion_contacto`); no hay bitácora por evento que consultar.

El segundo: la observación "restablecer la vista al cerrar el modal" **describe un
bug, no una preferencia**. El módulo dibuja a veces la página completa del selector
—encabezado, navegación y tabla— dentro del `<dialog>`. La causa está identificada
y se documenta más abajo.

## Alcance

**Dentro de alcance:**

- Paleta e iconografía de los botones de acción de ambos módulos.
- Reordenación vertical de los encabezados de ambos modales.
- Corrección del modal que dibuja la página completa, y refresco de la tabla.
- Plantilla base de WhatsApp editable desde el admin.
- Edición del cuerpo del mensaje antes de enviarlo, con las partes fijas protegidas.
- Apertura de WhatsApp Web en pestaña nueva.
- Bitácora de comunicaciones por solicitud, con su vista en el modal.

**Fuera de alcance:**

- Atajos de teclado. Siguen fuera, igual que en la spec anterior.
- Reportes, estadísticas y tableros.
- Cambios al chatbot. Nada de este trabajo lo toca.
- Framework de CSS o de JS, y cualquier paso de build. El proyecto no usa npm.
- Los pendientes que la spec del 2026-08-20 dejó abiertos y siguen abiertos: el
  catálogo de motivos de rechazo, el cron de `cerrar_rechazados`, el historial de
  *decisiones* (distinto del de comunicaciones que sí entra acá) y los índices
  combinados con el centro.

## Bloque 1 — Paleta e iconografía de acciones

*Cubre Selector #1 y Comunicador #5.*

Los colores **ya existen** en el `:root` de `static/css/gestion.css` —`--ok`,
`--danger`, `--muted`, `--primary`—; nunca se conectaron a los botones. Hoy todos
comparten la misma regla `background: var(--surface)` y se ven idénticos. Falta un
solo token nuevo, el verde de WhatsApp.

### El principio: el color codifica la acción, nunca la prioridad

Los cuatro botones "Aceptar" del selector llevan prioridad clínica, y esas
prioridades ya tienen color propio (`--prio-urgente` rojo, `--prio-alta` naranja,
`--prio-media` azul, `--prio-baja` verde). Pintar cada botón con el color de su
prioridad dejaría **rojo "Aceptar Urgente" al lado de rojo "Rechazar"** y verde
"Aceptar Baja" al lado del verde de confirmar: exactamente el riesgo de selección
incorrecta que la observación quiere bajar.

Por eso el color codifica **qué hace el botón**. Los cuatro "Aceptar" comparten
verde y se distinguen por su etiqueta. La prioridad se lee en el texto y en el
distintivo de la tabla, que ya la muestra.

| Clase | Botones | Tratamiento | Contraste sobre blanco |
| --- | --- | --- | --- |
| `.btn--confirmar` | Aceptar (×4 prioridades) | sólido `--ok` `#166534` | 7.0:1 |
| `.btn--agendar` | Agendada | sólido `--primary` `#1976d2` | 4.6:1 |
| `.btn--whatsapp` | Abrir WhatsApp | sólido `--wsp` `#0d7d6f` | 5.0:1 |
| `.btn--rechazar` | Rechazar, El paciente no acepta, No se logró contactar | contorno `--danger` `#b91c1c` | 6.5:1 |
| `.btn--neutro` | No aplica, No contesta | contorno `--muted` `#64748b` | 4.8:1 |

El token nuevo es `--wsp: #0d7d6f`. Es el verde de WhatsApp oscurecido: el
`#128c7e` de la marca da 4.1:1 con texto blanco y no alcanza el mínimo de 4.5:1.

### Sólido y contorno no son decoración

Las acciones que cierran el caso en contra del paciente —rechazar, no acepta, no se
logró contactar— van en **contorno**, para pesar visualmente menos que la acción
esperada. "Rechazar" además ya vive dentro de un `<details>` que exige un segundo
clic; el contorno acompaña esa jerarquía en vez de contradecirla.

### Iconografía sin dependencias

Un sprite `<svg hidden>` con `<symbol>` en `gestion/templates/gestion/base.html`
—check, x, guion, calendario, teléfono, WhatsApp— y uso vía
`<svg class="icon" aria-hidden="true"><use href="#ic-check"></use></svg>`. Cero
build, cero petición de red, coherente con la regla del proyecto de no usar npm.

**El icono acompaña al texto, nunca lo reemplaza.** Se mantiene la regla firme de la
spec anterior: el color no es el único portador de significado. Cada botón se
distingue por su etiqueta aunque quien mire no separe rojo de verde.

## Bloque 2 — Encabezados de los modales

*Cubre Selector #3 y Comunicador #4.*

Hoy ambos modales aplastan la identidad del paciente en una línea con guiones:

```
12.345.678-9 - +56912345678 - CESFAM Placeres
```

Pasa a una `<dl class="modal-identity">` con etiqueta y valor, un dato bajo el otro:

```
Maria Perez                                         [x]
  RUT       12.345.678-9
  Telefono  +56 9 1234 5678
  Centro    CESFAM Placeres
```

El Selector muestra RUT, Teléfono y Centro. El Comunicador muestra Teléfono —con su
enlace `tel:`, que ya tiene— y Centro, sin RUT, tal como pide la observación: quien
llama no necesita el RUT y sí necesita el teléfono grande.

El encabezado crece de dos líneas a unas cuatro. `.modal-body` ya tiene
`overflow: auto` y `.modal-actions` ya es `position: sticky`, así que el pie con las
acciones sigue visible sin scroll. No hay riesgo de empujarlo fuera de pantalla.

## Bloque 3 — El modal deja de dibujar la página completa

*Cubre Selector #2.*

### La causa

`static/js/gestion.js` inyecta en el `<dialog>` **cualquier** cuerpo que devuelva el
`fetch`, sin verificar que sea un fragmento. Ocurre en los dos caminos:

```js
dialog.innerHTML = await response.text();   // loadFragment y submitFragmentForm
```

`fetch` sigue los redirects de forma transparente. Cuando la vista responde un 302
—sesión expirada hacia el login, pérdida de permiso hacia `sin_acceso`, o un POST
sin `fragmento=1` hacia `selector_lista`— el `fetch` lo sigue y devuelve la **página
completa** con su `base.html`: encabezado, navegación y tabla. Eso es lo que termina
dibujado dentro del modal, y es la redundancia que el equipo reportó.

`response.redirected` y `response.url` existen en la respuesta y hoy no se consultan.

### La corrección, en dos partes

**Guardia de fragmento.** Antes de inyectar nada se verifica que `response.redirected`
sea falso y que el HTML recibido contenga `[data-fragment-kind]`. Si cualquiera de
las dos falla, no se inyecta: se cierra el modal y se navega a `response.url`. Así la
sesión expirada lleva al login y la pérdida de permiso a `sin_acceso`, que es donde
el usuario tiene que estar, en vez de quedar dibujados dentro de un diálogo.

**Refresco de la tabla al cerrar.** El modal cuenta las acciones de su sesión. Al
cerrarse con al menos una, pide la sección actual y reemplaza el `<tbody>` y los
contadores, con scroll al tope de la tabla.

Para eso `selector_lista` gana una rama `?fragmento=1` que renderiza un
`_tabla_selector.html` nuevo —extraído del `selector_lista.html` actual— sin
`base.html`. **Es el mismo patrón que ya usa el detalle**: misma vista, mismo
filtrado por centro, mismos permisos, sin ruta nueva y sin duplicar lógica de
autorización, que es donde estos rediseños suelen abrir agujeros.

### Consecuencia asumida: se retira el ajuste incremental

El refresco al cerrar vuelve obsoleto el ajuste incremental que hace hoy el JS:
`ajustarContadorSelector`, `actualizarContadoresSelector`, `actualizarFilaConservada`
y `removeResolvedRow`, junto con los atributos `data-selector-row-action`,
`data-selector-correction-text` y `data-selector-counter` que los alimentan.

Retirarlo quita unas 40 líneas de JavaScript y **elimina una clase entera de bug**:
el contador que se desincroniza de la base. Durante la ráfaga el usuario no ve la
tabla —el modal está encima—, así que actualizarla caso a caso no aporta nada que el
refresco al cerrar no entregue mejor.

El costo hay que decirlo con precisión: **obliga a reescribir seis tests** en
`gestion/tests.py`, en las líneas 1115, 1128, 1146, 1147, 1912 y 1913. Se reescriben
para afirmar el comportamiento nuevo; no se borran ni se dejan romper en silencio.

## Bloque 4 — El mensaje de WhatsApp

*Cubre Comunicador #2, #3 y #6.*

### Dónde vive la plantilla

Modelo nuevo, editable desde el admin de Django:

```python
class PlantillaWhatsapp(models.Model):
    clave = models.CharField(max_length=32, unique=True)
    descripcion = models.CharField(max_length=120)
    cuerpo = models.TextField(
        help_text="Solo el cuerpo. El saludo con el nombre, el centro y el "
                  "cierre los agrega el sistema."
    )
    activo = models.BooleanField(default=True)
```

Queda simétrico con `MotivoRechazo`, que el equipo ya administra: ajustar una coma en
la redacción no exige un despliegue. Una migración de datos siembra la fila `aceptada`
con el texto validado por el equipo:

> Estamos intentando comunicarnos con usted para gestionar la asignación de una hora
> de atención de morbilidad. Por favor, responda este mensaje para continuar con la
> gestión.

**La redacción sigue el enfoque de equidad de género que pide la observación:** el
saludo es "Hola, {nombre}" sin tratamiento, y el cuerpo usa "usted" y verbos que no
asumen el género de quien recibe.

### La estructura del mensaje

Las partes fijas viven en código (`gestion/mensajes.py`) porque son estructura, no
redacción:

```
Hola, {nombre}. Somos del {centro}.      <- fijo, armado en el servidor
{cuerpo}                                  <- editable por el comunicador
Muchas gracias.                           <- fijo
```

### Cómo se protegen el nombre y el centro

El requisito pide que el usuario edite pero que ciertos datos de la solicitud
sobrevivan a la edición. Se resuelve por construcción, no por validación:

- Las partes fijas se **renderizan fuera del `<textarea>`**, como texto. No hay
  control de formulario que las contenga, así que la UI no ofrece forma de tocarlas.
- El POST envía **únicamente el cuerpo**. Nombre y centro nunca viajan desde el
  cliente: el servidor los lee de la base al rearmar el mensaje.
- El cuerpo se valida no vacío y con un máximo de 800 caracteres.

Una validación de "el texto todavía contiene el nombre" habría dejado la puerta
abierta a que el cliente mande el nombre; esto la cierra.

### Unificar las rechazadas, con migración de datos

Hoy hay dos fuentes de mensaje: las rechazadas usan `MotivoRechazo.mensaje_paciente`
y las aceptadas un texto fijo en `models.py`. Con este cambio ambas usan el mismo
esquema y `mensaje_paciente` pasa a ser **solo el cuerpo**.

Eso obliga a mirar los datos existentes. `MotivoRechazo` no tiene seed —las filas las
crea el equipo desde el admin— y la convención observada es un mensaje **completo con
saludo**: `"Hola {nombre}, faltan datos."`. Anteponerle el encabezado fijo le
mandaría al paciente el saludo dos veces.

La migración de datos quita el prefijo de los motivos que siguen esa convención
(`^\s*Hola[ ,]*\{nombre\}\s*[,.\-]?\s*`) y **deja intacto lo que no calce**, en vez de
adivinar. Los motivos no transformados se listan en la nota de despliegue para que el
equipo los revise en el admin. Es reversible: la migración inversa vuelve a anteponer
el saludo.

### Pestaña nueva sin caer en el bloqueador de popups

El orden de las operaciones es lo que hace que esto funcione. Un `window.open` después
de un `await fetch` ya perdió el gesto del usuario y el navegador lo bloquea. Por eso:

1. El handler abre `window.open("", "_blank", "noopener")` **mientras todavía tiene el
   gesto del usuario**.
2. Hace el POST por fetch, que valida el cuerpo, registra el intento y devuelve el
   fragmento del modal refrescado con `data-whatsapp-url` en su raíz.
3. Asigna esa URL a la pestaña ya abierta.

Se mantiene la regla de la spec anterior —un endpoint, un tipo de respuesta, HTML— sin
mezclar JSON. Si el POST falla, la pestaña se cierra.

**Si el navegador bloquea igual** (`window.open` devuelve `null`), el modal muestra un
enlace `target="_blank"` para que el usuario lo abra a mano. El intento ya quedó
registrado, así que el historial no depende de si la pestaña se abrió.

## Bloque 5 — Historial de comunicaciones

*Cubre Comunicador #1.*

### El modelo

```python
class RegistroContacto(models.Model):
    class Canal(models.TextChoices):
        LLAMADA = "LLAMADA", "Llamada telefonica"
        WHATSAPP = "WHATSAPP", "WhatsApp"

    gestion = models.ForeignKey(Gestion, related_name="registros_contacto", ...)
    canal = models.CharField(max_length=10, choices=Canal.choices)
    resultado = models.CharField(max_length=20, choices=Gestion.AccionContacto.choices)
    mensaje = models.TextField(blank=True)          # solo en WhatsApp
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=SET_NULL, null=True, ...)
    creado_en = models.DateTimeField(auto_now_add=True)
```

El canal se deriva de la acción: `WHATSAPP` cuando la acción es
`AccionContacto.WHATSAPP`, `LLAMADA` en los otros cuatro casos.

Se descartó ampliar `TokenContactoGestion` para que hiciera de historial: mezclaría
idempotencia con auditoría en una tabla donde el token es opcional, y quedarían
huecos. Esa tabla se queda con su rol actual y no se toca.

### Dónde se escribe

Dentro de `_registrar_intento`, que es el **único punto por donde ya pasan las cinco
acciones**, y dentro del `transaction.atomic()` de `_mutar_bloqueado`: la fila del
historial y el contador `intentos_contacto` se mueven juntos o no se mueven ninguno.

Solo se escribe cuando `mutar` devuelve `True`. Así el camino idempotente del token
—el que evita el doble registro por doble clic— tampoco duplica filas del historial.

### Qué se registra y qué no

Se registra el **resultado** de la gestión, que es lo que el comunicador ya declara
con los botones que presiona. No se registra el intento de llamada en sí: el enlace
`tel:` no deja rastro hoy, y convertirlo en un POST ensuciaría el historial con
llamadas iniciadas y nunca resueltas, además de agregar un paso a un flujo que se
ejecuta decenas de veces al día.

### Backfill de lo ya ocurrido

Una migración de datos crea un `RegistroContacto` por cada `TokenContactoGestion`
existente, que ya tiene gestión, acción y `creado_en`. Quedan sin `usuario` ni
`mensaje`, porque ese dato nunca se guardó.

Las gestiones con `intentos_contacto > 0` y sin tokens asociados **no son
reconstruibles** y quedan fuera del backfill. Se documenta acá en vez de inventar
filas: un historial con datos fabricados es peor que un historial que empieza en una
fecha conocida.

### La vista

Sección colapsable en el modal del comunicador, junto al resto del caso, con el
conteo en el encabezado:

```
Historial de comunicaciones (3)
  26/08 10:14  WhatsApp  Avisado      renzo@...  "Hola, Maria Perez. Somos..."
  26/08 09:52  Llamada   No contesta  renzo@...
  25/08 16:30  Llamada   No contesta  ana@...
```

Visible **también para los roles de solo lectura**, coherente con la decisión de la
spec anterior de que esos roles ven el rastro y no una vista aparte.

Se descartó una columna con botón en la tabla del comunicador: el modal ya es la
superficie de trabajo por solicitud, y en 1366×768 esa tabla va justa de ancho.

## Plan de entrega

Tres fases, en este orden, mergeables por separado:

**Fase 1 — Presentación y corrección del modal.** Bloques 1, 2 y 3. Sin migraciones.
Entrega valor visible de inmediato y arregla el bug reportado.

**Fase 2 — El mensaje de WhatsApp.** Bloque 4. Tres migraciones: el modelo
`PlantillaWhatsapp`, el `AlterField` del `help_text` de `MotivoRechazo.mensaje_paciente`
y la de datos que siembra la plantilla y limpia los saludos de los motivos.

**Fase 3 — El historial.** Bloque 5. Dos migraciones: el modelo `RegistroContacto` y
la de datos del backfill.

Cinco migraciones en total: tres de esquema y dos de datos. Ninguna destructiva; la de
limpieza de motivos es reversible.

## Decisiones tomadas

- El color de los botones codifica el tipo de acción, no la prioridad clínica.
- Iconografía por sprite SVG inline; el icono acompaña al texto, no lo reemplaza.
- El encabezado de ambos modales pasa a lista vertical con etiquetas.
- El JS valida que la respuesta sea un fragmento antes de inyectarla; ante redirect,
  navega en vez de dibujar.
- La tabla del selector se refresca por fetch al cerrar el modal, y se retira el
  ajuste incremental de filas y contadores.
- `selector_lista` responde el fragmento de tabla con `?fragmento=1`, sin ruta nueva.
- La plantilla de WhatsApp vive en un modelo editable desde el admin, no en código.
  Se descartó una plantilla por centro: nadie la pidió todavía.
- Las partes fijas del mensaje se protegen por construcción —fuera del formulario,
  rearmadas en el servidor—, no por validar el texto que manda el cliente.
- Aceptadas y rechazadas comparten un solo armador de mensajes, con migración que
  limpia el saludo duplicado de los motivos existentes.
- La pestaña de WhatsApp se abre antes del fetch para conservar el gesto del usuario.
- El historial va en tabla propia y se escribe en `_registrar_intento`, dentro de la
  transacción existente.
- Se registra el resultado de la gestión, no el intento de llamada.

## Consecuencias asumidas

**Seis tests se reescriben.** Retirar el ajuste incremental invalida las afirmaciones
sobre `data-selector-row-action`, `data-selector-correction-text` y
`data-selector-counter`. Es trabajo previsto, no daño colateral.

**El historial arranca vacío para los casos sin token.** El backfill reconstruye lo
que `TokenContactoGestion` alcanza a cubrir; el resto no existe y no se va a inventar.
El equipo debe saber que el historial no es retroactivo hasta el origen.

**Los motivos de rechazo que no calcen con el patrón quedan para revisión manual.** La
migración es deliberadamente conservadora. La nota de despliegue tiene que listarlos.

**El bloqueador de popups es un riesgo real, no teórico.** El diseño lo mitiga con el
orden de operaciones y tiene una salida por enlace si aun así ocurre. Conviene
verificarlo en los navegadores del equipo durante la fase 2.

## Referencias

- `docs/superpowers/specs/2026-08-20-ui-ux-modulo-seleccion-design.md` — interfaz base.
- `docs/superpowers/specs/2026-07-28-modulo-seleccion-design.md` — flujo del módulo.
- `static/js/gestion.js` — `loadFragment` y `submitFragmentForm`, origen del bug.
- `static/css/gestion.css` — tokens de color ya presentes en `:root`.
- `gestion/models.py` — `_registrar_intento`, `_mutar_bloqueado`, `url_whatsapp`.
- `gestion/views.py` — `selector_lista`, `selector_detalle`, `registrar_whatsapp`.
- `gestion/templatetags/gestion_ui.py` — `mensaje_whatsapp_previo`.

## Historial de versiones

| Versión | Fecha | Cambios |
| --- | --- | --- |
| 1 | 2026-08-26 | Versión inicial, validada en sesión de brainstorming. |
