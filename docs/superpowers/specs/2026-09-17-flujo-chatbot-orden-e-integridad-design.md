# Spec 1 — Reordenamiento e integridad del flujo del chatbot

Fecha: 2026-09-17
Modulo: `solicitudes` (chatbot publico, host `morbilidad.cmvalparaiso.cl`)
Archivos principales: `static/js/saludbot.js`, `templates/chat/saludbot.html`,
`solicitudes/views.py`, `solicitudes/tests.py`.

## Contexto

El flujo del chatbot vive en `static/js/saludbot.js` (renderizado por
`templates/chat/saludbot.html`; el archivo `solicitudes/templates/solicitudes/chatbot.html`
esta en desuso y no se toca). Es un formulario conversacional por pasos: cada paso
declara `field`, `prompt`, `validate` y, segun el caso, `type` (`terms`/`photo`),
`options`, `skip`, `transform` y `display`.

De la revision del equipo y la reunion salieron observaciones sobre el orden y la
integridad de ese flujo. Varias no son features nuevas sino reordenar y blindar
pasos que ya existen. Esta spec cubre solo eso; el contenido clinico (motivos,
Receta, ACV, *4141), la defensa contra bots y la captura de cupos en el selector
son specs separadas.

### Orden actual del flujo

```
motivo -> (alerta de urgencia) -> T&C -> detalle -> RUT -> Nombre -> edad
      -> telefono -> CESFAM -> credencial(si/no) -> foto -> neuro(si/no) -> tipo -> otro
```

Problemas detectados:

- Los T&C aparecen en el paso 2, no primero.
- El input de texto libre queda habilitado durante los pasos de botones (T&C,
  CESFAM, credencial, neuro), de modo que el usuario puede escribir y evadir el
  gate. Esta es la raiz de "al no aceptar los terminos, el sistema pasa igual" y
  de "deberia desaparecer el campo de escribir texto antes de los T&C".
- El CESFAM se pregunta despues del RUT y el Nombre.
- El paso de foto de credencial guarda base64 en la fila, funcionalidad que el
  acta pide excluir del flujo (ver `docs/deuda-almacenamiento-imagenes-credencial.md`).
- Cuando el bot publica un mensaje largo, el scroll baja al final y el inicio del
  mensaje queda por encima de la vista; hay que subir para leerlo.

## Flujo objetivo

```
T&C (primera pantalla) -> saludo + motivo -> alerta de urgencia -> detalle
   -> CESFAM -> RUT -> Nombre -> edad -> telefono -> credencial(si/no)
   -> neuro(si/no) -> tipo -> otro
```

Sin paso de foto de credencial (oculto tras flag, ver mas abajo).

## Cambios

### 1. T&C como primera pantalla

La conversacion abre con la tarjeta de Terminos y Condiciones. El saludo de
bienvenida y la pregunta de motivo (con los botones rapidos) se muestran recien
despues de aceptar.

- Reestructurar `start()` en `saludbot.js`: en vez de abrir con el saludo + motivo,
  abre presentando el paso de T&C.
- El paso `acepta_terminos` (hoy en el indice 1) pasa a ser el primer paso del
  arreglo `steps`, antes de `motivo`.
- Tras aceptar, se muestra el saludo de bienvenida y luego el paso de motivo.

### 2. Gate del input en pasos de botones

En los pasos que se responden con botones (T&C, CESFAM, credencial, neuro y su
sub-paso `tipo`), el campo de texto libre queda **deshabilitado**: visible pero
gris y no editable. Se reactiva automaticamente en los pasos de texto libre
(motivo, detalle, RUT, nombre, edad, telefono).

- El estado del input se deriva del tipo de paso, no se maneja caso a caso: un
  paso es "de botones" si tiene `type` (`terms`/`photo`) o `options`; en esos
  casos `input.disabled = true` al presentarlo, y `false` en el resto.
- Al reactivarlo en un paso de texto, se conserva el foco automatico existente.

### 3. Aceptacion de T&C tambien en el servidor (defensa en profundidad)

`crear_solicitud` (`solicitudes/views.py`) rechaza la creacion con HTTP 400 si
`acepta_terminos` no es verdadero, en lugar de guardar la solicitud igual. Cierra
el "pasa igual" aunque el front sea manipulado, y es la unica parte de esta spec
verificable con el runner de Django.

- Tras normalizar el payload y convertir `acepta_terminos` a booleano, si es
  falso se devuelve `{"ok": False, "errors": {...}}` con status 400 y un mensaje
  claro, sin construir ni guardar la `Solicitud`.
- No cambia el modelo: el campo `acepta_terminos` ya existe.

### 4. CESFAM antes de RUT y Nombre

Mover el step `centro_salud` en el arreglo `steps` para que quede despues de
`detalle_sintomas` y antes de `rut`. La logica del paso (opciones, validacion,
`display`, actualizacion de `state.selectedCentroName`) no cambia, solo su
posicion.

### 5. Ocultar el paso de foto tras un flag

- Definir una constante `ADJUNTO_FOTO_HABILITADO = false` en `saludbot.js`.
- El step de foto (`credencial_cuidador_discapacidad_foto`, `type: "photo"`) se
  mantiene definido en el codigo, pero su `skip()` devuelve `true` cuando el flag
  esta apagado (ademas de la condicion actual de no tener credencial). Asi el paso
  queda excluido del flujo sin borrar codigo.
- Con el flag apagado, el front envia `credencial_cuidador_discapacidad_foto: ""`
  (el backend ya tolera vacio; sin cambios de modelo).
- Revertir la decision a futuro = poner el flag en `true`.

### 6. Scroll anclado al inicio del mensaje del bot

Cuando el bot publica un mensaje nuevo, el chat se posiciona con el **inicio** de
ese mensaje pegado al tope de la ventana de conversacion, para leerlo de corrido.

- Reemplazar el criterio de `scrollToLatest` (que hoy baja al final con
  `scrollHeight - clientHeight`) por un `scrollIntoView({ block: "start" })`
  sobre la fila del ultimo mensaje del bot.
- Solo reancla el ultimo mensaje del **bot**; el eco de la respuesta del usuario
  no reancla.
- Si el mensaje ya entra completo en la vista, no se fuerza scroll (evitar saltos
  innecesarios en mensajes cortos).

## Testing

- **Runner de Django contra MySQL 8.4** (no SQLite, no pytest):
  - `crear_solicitud` con `acepta_terminos=true` (u equivalentes veraces) crea la
    solicitud y responde 201.
  - `crear_solicitud` con `acepta_terminos` falso o ausente responde 400 y **no**
    crea ninguna fila.
- **Verificacion visual/manual** (no hay arnes de JS en el repo): orden de pasos,
  T&C como primera pantalla, input deshabilitado en pasos de botones, ausencia del
  paso de foto y anclaje del scroll al inicio del mensaje del bot.

Correr `.venv/bin/python manage.py test` antes de dar la tarea por terminada.

## Fuera de alcance

- Contenido de motivos, categoria "Receta", signo ACV y alerta *4141 (spec 2).
- Defensa contra bots (spec 3).
- Captura de cupos reales en el selector (spec 4).
- No se modifica el modelo `Solicitud` ni el modulo de gestion.
- El archivo en desuso `solicitudes/templates/solicitudes/chatbot.html` y su
  `chatbot.js` no se tocan.
