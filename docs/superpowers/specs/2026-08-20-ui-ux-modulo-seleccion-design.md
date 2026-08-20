# Módulo de selección: interfaz y experiencia de uso — Diseño

Fecha: 2026-08-20
Versión: 1
Relacionado: `docs/superpowers/specs/2026-07-28-modulo-seleccion-design.md`,
`docs/arquitectura-modulo-gestion.md`,
`docs/deuda-almacenamiento-imagenes-credencial.md`

> Documento para validar antes de escribir código. La spec del 2026-07-28 definió
> el flujo de trabajo del módulo y quedó implementada en el PR #13. Esta spec cubre
> la capa que ese PR dejó deliberadamente fuera: cómo se ve y cómo se opera.

## Objetivo

El módulo de selección funciona pero se entrega en HTML sin estilos. Las dos
pantallas operativas son legibles solo para quien ya sabe qué está mirando, y las
acciones —aceptar, rechazar, avisar por WhatsApp— no se leen como acciones aunque
existan. Esta spec define la interfaz y el flujo de operación de ambos roles.

Un hallazgo que conviene dejar registrado, porque motivó parte de este trabajo y
es fácil de malinterpretar: **los botones de acción ya existen en las plantillas**.
No se ven cuando el usuario tiene un rol de solo lectura, porque los formularios
están envueltos en `{% if puede_escribir %}` y en su lugar aparece la frase "Vista
de solo lectura". Verificado renderizando las mismas dos páginas con la misma
cuenta y distinto rol: con `FULL` aparecen los cuatro controles, con `ADMIN` no
aparece ninguno. No hay funcionalidad faltante que construir; hay una interfaz que
diseñar.

## Contexto de operación

Los dos roles trabajan con ritmos distintos, y el diseño se separa por eso.

| | Selector | Comunicador |
| --- | --- | --- |
| Cuándo | Ráfaga: el chatbot abre L-V 08:00–08:20 | Continuo, durante toda la jornada |
| Volumen | 40+ casos por centro, de golpe | Los mismos casos, uno por llamada |
| Qué necesita | Despachar rápido sin volver a la lista | Ver de un vistazo a quién ya intentó |
| Costo por caso | Segundos | Minutos (la llamada) |

De ahí la diferencia central del diseño: **el selector salta automáticamente al
siguiente caso al decidir; el comunicador no**. Quien llama elige a quién marcar
según quién le contestó y a qué hora conviene insistir, no según el orden de la
fila. Auto-avanzar ahí copiaría un patrón útil en la ráfaga y molesto en las
llamadas.

Pantalla base de diseño: **1366×768**, el equipamiento típico de box y mostrador.
Debe además comportarse razonablemente en móvil, sin que eso lo convierta en un
proyecto aparte.

## Alcance

**Dentro de alcance:**

- Fundación visual del módulo: `gestion.css`, encabezado, navegación, identidad.
- Rediseño de las dos listas y de los dos detalles.
- Detalle en modal, con las acciones explícitas y siempre visibles.
- Flujo de despacho en ráfaga para el selector.
- Desglose por caso de la prioridad administrativa.
- Qué ve un rol de solo lectura.
- Aviso de teléfono inválido y cuenta regresiva de las rechazadas.

**Fuera de alcance:**

- Atajos de teclado. Con el modal de un clic el costo por caso ya baja bastante;
  agregar teclas a una pantalla de decisión clínica antes de ver cómo opera el
  equipo es optimizar a ciegas. Se reevalúa con uso real.
- Reportes, estadísticas y tableros. Siguen fuera, igual que en la spec anterior.
- Cambios al chatbot, salvo la función aditiva de desglose descrita más abajo.
- Framework de CSS o de JS, y cualquier paso de build. El proyecto no usa npm.
- Los pendientes de la spec anterior listados al final de este documento.

## Enfoque técnico: mejora progresiva

**El modal no reemplaza nada, se monta encima.** Las cuatro vistas actuales siguen
respondiendo igual. Sin JavaScript —o abriendo un enlace en pestaña nueva— el
usuario cae en la página completa de hoy. Esto importa por una razón concreta: los
110 tests existentes ejercitan ese flujo de páginas, y así ninguno se rompe ni hay
que reescribirlo.

### El fragmento no es una ruta nueva

Las mismas vistas `selector_detalle` y `comunicador_detalle` responden con el
parcial, sin el layout, cuando reciben `?fragmento=1`. Con eso el filtrado por
centro, el 404 fuera de alcance y el chequeo de `puede_escribir` son literalmente
el mismo código. No se duplica lógica de permisos, que es donde estos rediseños
suelen abrir agujeros.

### El POST siempre devuelve HTML

Al guardar con `fragmento=1`:

- Si el formulario falla, vuelve el mismo parcial con sus errores.
- Si guarda bien y es el selector, vuelve el parcial del **siguiente** caso de la
  cola. Si no queda ninguno, vuelve un parcial de cola vacía.
- Si guarda bien y es el comunicador, vuelve una confirmación y el modal se cierra.

El JavaScript solo intercambia el contenido del `<dialog>`, saca la fila resuelta
de la lista y actualiza el contador. Un endpoint, un tipo de respuesta, sin mezclar
JSON con HTML.

### Por qué el detalle se carga y no se pre-renderiza

La alternativa —incrustar los 40 detalles ocultos en la lista— evitaría el fetch,
pero la foto de credencial se guarda en base64 dentro de la fila
(`docs/deuda-almacenamiento-imagenes-credencial.md`). Pre-renderizar arrastraría
hasta 40 imágenes en base64 en cada carga de la cola. Con fetch, esa foto se paga
solo al abrir el caso que la tiene.

## Fundación visual

`static/css/gestion.css`, CSS vanilla, siguiendo el patrón del proyecto.

Su bloque `:root` copia los tokens de `saludbot.css` —`--primary: #1976D2`,
`--text`, `--muted`, `--line`, sombras— y agrega los propios de una herramienta
densa: escala de espaciado compacta y colores de estado para las cuatro
prioridades.

Se descartó extraer los tokens a un archivo común compartido con el chatbot: eso
obligaría a editar la plantilla del chatbot para enlazarlo, y no se justifica
cruzar ese límite por algo cosmético. Son doce líneas duplicadas, comentadas como
copiadas de `saludbot.css`, a cambio de cero riesgo sobre la app pública. Si más
adelante se quiere fuente única, se extrae entonces.

**Regla firme: el color nunca es el único portador de significado.** El distintivo
de prioridad siempre lleva su texto. "Urgente" no puede depender de que quien mira
distinga rojo de naranjo.

`base.html` gana lo que hoy no tiene: encabezado con la marca, quién está
conectado, su rol, su centro y la salida de sesión. Hoy se entra al módulo y nada
en pantalla dice quién eres ni qué alcance tienes.

## Etapa 1 — El selector

### La cola

Con 40+ casos cada columna tiene que ganarse el espacio. Se retiran dos:

- `Decision`, que en la pestaña de pendientes siempre dice "Pendiente".
- `Centro`, que solo tiene sentido para `ADMIN` y `SUPERVISOR_DAS`. Un `SELECTOR`
  ve un único centro. La columna se muestra solo cuando el perfil alcanza más de
  uno, dato que `centros_permitidos()` ya entrega.

Con ese espacio entra el **motivo de consulta truncado**, que es lo que permite
triar de un vistazo cuál abrir primero.

La prioridad pasa a distintivo con color y texto. La fecha se muestra relativa
("hace 2 h") con la absoluta en el `title`. La fila completa es clickeable, no solo
el enlace "Abrir": objetivo más grande, menos puntería.

Las tres pestañas se mantienen —Pendientes, Decididas corregibles, No aplica— con
el conteo al lado, que con este volumen es información operativa.

### El modal

Cuerpo con scroll y **pie fijo con las acciones siempre visibles**, sin necesidad
de bajar. Ese pie es la corrección directa al problema reportado: hoy el formulario
queda al final de una lista de definiciones larga.

El contenido prioriza lo que se lee para decidir:

1. Motivo y detalle libre, destacados arriba.
2. Datos del paciente en grilla compacta.
3. Condiciones declaradas y credencial de cuidador, con su foto si existe.
4. Prioridad administrativa con su desglose **visible**, no solo en hover: en el
   modal hay espacio y es el contexto de la decisión.

Las acciones, contadas en clics:

| Acción | Interacción | Clics |
| --- | --- | --- |
| Aceptar | Cuatro botones, uno por prioridad clínica | 1 |
| Rechazar | Un clic despliega el catálogo de motivos, el segundo confirma | 2 |
| No aplica | Un clic, presentado como acción secundaria | 1 |

Hoy aceptar son tres interacciones: elegir decisión, elegir prioridad, enviar.

Al guardar, el modal salta al siguiente caso con una confirmación breve de lo que
ocurrió ("Aceptada como Urgente"), y la fila decidida desaparece de la lista
detrás.

### Corrección de decisiones

Decidir a un clic en ráfaga tiene riesgo de error, y la red de seguridad ya existe
en el diseño del módulo: mientras el comunicador no registre ningún intento,
cualquier selector del centro puede corregir desde "Decididas corregibles".

Esa pestaña debe mostrar además **cuánto tiempo queda para corregir** en las
rechazadas. La implementación bloquea la corrección de una rechazada con más de 24
horas (`gestion/models.py`, `_registrar_decision`), y hoy eso no se comunica en
ninguna parte: el usuario se entera cuando ya no puede.

## Etapa 2 — El comunicador

### La tabla de trabajo

Hoy es una sola lista donde la columna "Prioridad" dice "Rechazada" para los
rechazos, mezclando dos cosas distintas. Se separa en dos grupos con encabezado,
respetando el mismo orden que ya calcula `tabla_comunicador()`:

- **Aceptadas — llamar por teléfono**, de `URGENTE` a `BAJA` por prioridad clínica.
- **Rechazadas — avisar por WhatsApp**, al final.

Son dos tareas diferentes y conviene que se lean así.

El estado de cada caso es lo más legible de la fila: intentos, cuándo fue el último
y quién lo hizo. Los casos nunca intentados se destacan: son el trabajo real
pendiente. El teléfono se convierte en enlace `tel:`, que en el celular marca
directo.

Dos cosas que hoy faltan y que esta spec resuelve:

- **Aviso de teléfono inválido.** `url_whatsapp()` ya devuelve nulo cuando el
  teléfono no calza con `+569XXXXXXXX`, pero la fila no lo indica y el botón se
  muestra igual, así que el error aparece recién al hacer clic. Pasa a marcarse en
  la fila, con el botón deshabilitado y la razón visible. La spec anterior pedía
  exactamente esto ("no se arma el enlace y la fila lo indica") y quedó a medias.
- **Cuenta regresiva de las rechazadas.** Se cierran solas a las 24 horas de la
  decisión y desaparecen de la tabla, hoy sin ningún aviso. Mostrar "quedan 6 h
  para avisar" convierte una regla invisible en información accionable.

### El modal

Mismo patrón, con el pie de acciones fijo: Agendada —que despliega fecha y hora—,
El paciente no acepta, No contesta, y No se logró contactar. El botón de WhatsApp
queda separado y explícito, diciendo lo que hace: abre WhatsApp **y registra un
intento**.

El modal muestra también el historial de contacto del caso: cuántos intentos, el
último, quién contactó y cuál fue la última acción registrada.

### Vista previa del mensaje de WhatsApp

La spec anterior dice que el comunicador "solo revisa y envía", pero hoy no puede
revisar nada: el mensaje aparece cuando WhatsApp ya se abrió. El modal muestra el
texto compuesto —el `mensaje_paciente` del motivo con `{nombre}` reemplazado—
antes de abrir la ventana.

### El token de idempotencia

El formulario lleva un token oculto que evita que un doble envío cuente dos
intentos. Como el modal reemplaza el fragmento completo después de cada acción,
cada render trae token nuevo y la protección se mantiene.

**El JavaScript no debe reutilizar un fragmento ya enviado.** Si lo hiciera, la
segunda acción se descartaría en silencio, sin error visible. Queda anotado acá
porque es el tipo de defecto que no se descubre probando a mano.

## Prioridad administrativa: el desglose por caso

Al pasar el cursor —o el foco de teclado— sobre el distintivo de prioridad, se
muestra **qué factores sumaron en esa solicitud concreta**, no una definición
genérica del nivel:

```
Urgente (8 pts)
  palabra clave "dolor pecho"     +4
  edad 68 años                    +2
  credencial de cuidador          +2
```

Se eligió el desglose por caso sobre la definición genérica por dos razones: es más
útil para decidir, y evita redactar una definición clínica de "Urgente" que el
algoritmo no cumple.

**Cambio en `solicitudes/priorizacion.py`.** Hoy `calcular_prioridad()` devuelve
solo el total y la clasificación. Se agrega una función que devuelve los factores
que sumaron, y `calcular_prioridad` pasa a apoyarse en ella. El puntaje y la
clasificación **no cambian**; los tests existentes del chatbot lo garantizan.

Es tocar la app `solicitudes`, que tanto la spec anterior ("el chatbot no se toca")
como la regla de alcances del proyecto dejan fuera del trabajo de gestión. Se
autorizó explícitamente por ser puramente aditivo y por dejar una sola fuente de
verdad. Las alternativas se descartaron: replicar las reglas dentro de `gestion`
las duplica en dos lugares y el día que se calibre el algoritmo el tooltip queda
mintiendo; persistir el desglose en la `Solicitud` exige migración y modificar el
flujo de creación del chatbot.

La accesibilidad manda que esté disponible en hover **y** en foco de teclado, así
que no puede implementarse solo con el atributo `title`.

## Roles de solo lectura

`ADMIN`, `SUPERVISOR_DAS` y `SUPERVISOR_CENTRO` ven las mismas pantallas, con el
distintivo de rol en el encabezado dejando claro el estado. En el modal, el pie de
acciones se reemplaza por el **rastro de la decisión**: quién decidió y cuándo,
cuántos intentos lleva, quién contactó, cuál fue la última acción y, si está
cerrado, con qué motivo.

Todo ese dato ya está guardado en el modelo y ninguna pantalla lo muestra hoy. Es
exactamente lo que un supervisor entra a mirar.

No se cambia el permiso: `ADMIN` de solo lectura en las pantallas operativas es un
acuerdo de la reunión del 2026-07-30 y sigue vigente.

## Responsive y accesibilidad

1366×768 es el caso base. Bajo los ~900px las tablas se reordenan como tarjetas
apiladas y el modal pasa a pantalla completa.

El elemento `<dialog>` nativo aporta atrapado de foco y cierre con Esc sin
librerías. Al cerrar, el foco vuelve a la fila que lo abrió. Ninguna información se
transmite solo por color.

## Archivos afectados

| Archivo | Cambio |
| --- | --- |
| `static/css/gestion.css` | nuevo — tokens y componentes densos |
| `static/js/gestion.js` | nuevo — `<dialog>`, fetch, guardar-y-siguiente, foco |
| `gestion/templates/gestion/_detalle_selector.html` | nuevo — parcial |
| `gestion/templates/gestion/_detalle_comunicador.html` | nuevo — parcial |
| `gestion/templates/gestion/base.html` | encabezado, navegación, `{% static %}` |
| `gestion/templates/gestion/selector_lista.html` | rediseño |
| `gestion/templates/gestion/selector_detalle.html` | pasa a usar el parcial |
| `gestion/templates/gestion/comunicador_lista.html` | rediseño |
| `gestion/templates/gestion/comunicador_detalle.html` | pasa a usar el parcial |
| `gestion/views.py` | soporte de `fragmento=1` |
| `solicitudes/priorizacion.py` | aditivo — desglose de factores |
| `gestion/tests.py` | tests nuevos |

Que el parcial lo use también la página completa es lo que evita mantener dos
versiones del detalle en paralelo.

## Verificación

Con el test runner de Django contra MySQL, como el resto del proyecto.

Los 110 tests actuales **deben seguir pasando sin modificarse**: cubren el flujo de
páginas completas, que es el respaldo sin JavaScript. Si alguno se cae al
reestructurar las plantillas, eso señala un cambio de comportamiento que hay que
justificar, no una aserción que haya que actualizar para que pase. Se agregan:

- El fragmento responde sin el layout de `base.html`.
- El fragmento respeta el 404 por alcance de centro y el permiso de escritura, con
  los mismos casos que ya cubren las páginas completas.
- El POST con `fragmento=1` devuelve el siguiente caso en el orden real de la cola
  (prioridad administrativa, luego el más antiguo).
- El POST con `fragmento=1` sobre el último caso devuelve el parcial de cola vacía.
- El desglose de prioridad suma exactamente el puntaje total de
  `calcular_prioridad()`, para cada combinación de factores.
- Una solicitud con teléfono inválido no ofrece el botón de WhatsApp.
- Un rol de solo lectura recibe el rastro de la decisión y ningún control de acción.

No se introduce framework de tests de JavaScript: el proyecto no tiene ninguno, y
el JS queda lo bastante delgado como para que la cobertura del servidor sea
suficiente.

No automatizable: la legibilidad real de la cola en un monitor de 1366×768 y que el
modal se sienta rápido en la ráfaga de las 08:20.

## Entrega en dos fases

**Fase 1 — Fundación visual y listas.** `gestion.css`, `base.html` con encabezado y
rol, y el rediseño de las cuatro plantillas de lista, incluidos el aviso de
teléfono inválido y la cuenta regresiva de las rechazadas. No toca `views.py` ni
requiere migraciones; sí puede agregar propiedades de solo lectura al modelo para
que las plantillas no calculen reglas de negocio. Sale rápido y ya es una mejora
visible y usable.

**Fase 2 — Interacción.** Parciales, soporte de `fragmento=1`, el modal, las
acciones explícitas, el desglose de prioridad y la vista de solo lectura.

Dos PRs, en ese orden.

## Decisiones tomadas

- Pantalla base 1366×768, con comportamiento razonable en móvil.
- El selector salta al siguiente caso al decidir; el comunicador no.
- Modal cargado por fetch, sobre las páginas actuales, no en reemplazo de ellas.
- Se descartó el layout de dos paneles: en 1366×768 quedan unos 480px para el
  detalle y el contenido clínico no entra cómodo.
- Tokens compartidos con el chatbot, hoja propia y densa para gestión.
- Tooltip de prioridad con desglose por caso, no definición genérica del nivel.
- Los roles de solo lectura ven el rastro de la decisión, no una vista aparte con
  conteos: reportes y tableros siguen fuera de alcance.
- Sin atajos de teclado en esta iteración.

## Consecuencias asumidas

**El desglose le va a mostrar al equipo clínico los casos mal calibrados.** El
algoritmo suma por palabras clave, edad y condiciones declaradas, y produce
resultados discutibles: "herida infectada" y "vómitos con diarrea" quedan en `BAJA`
con 1 punto. Exponerlo es una consecuencia buscada —empuja a calibrarlo con datos
reales, que es justamente lo que la spec anterior propone medir comparando la
prioridad administrativa con la clínica—, pero hay que anticipar que va a generar
preguntas del equipo. Va junto al trabajo pendiente de calibración del triaje.

## Pendientes que esta spec no aborda

Del contraste entre la spec del 2026-07-28 y lo implementado en el PR #13 quedaron
estos puntos abiertos. Solo el del teléfono inválido se resuelve acá; los demás
siguen pendientes y necesitan su propio trabajo:

- **El catálogo de motivos de rechazo.** La migración crea la tabla vacía. Sin
  filas, el selector no puede rechazar. Requiere la validación clínica que la spec
  anterior dejó explícitamente abierta.
- **El cron horario de `cerrar_rechazados`.** El comando existe y está probado,
  pero no está programado en ninguna parte.
- **El historial de decisiones.** La spec pide que cada cambio guarde quién y
  cuándo, y que ante dos selectores "quede registro de ambos". Hoy `decidido_por` y
  `fecha_decision` se sobrescriben: solo sobrevive la última.
- **Los índices combinados con el centro.** Pedidos por la spec, pero el centro
  vive en otra tabla y un índice compuesto no es posible tal como está descrito.

## Referencias

- `docs/superpowers/specs/2026-07-28-modulo-seleccion-design.md` — flujo del módulo.
- `docs/superpowers/plans/2026-08-19-modulo-seleccion.md` — plan implementado en el PR #13.
- `gestion/permisos.py` — roles de escritura y de solo lectura.
- `gestion/models.py` — `GestionQuerySet`, orden de las dos colas.
- `solicitudes/priorizacion.py` — cálculo de la prioridad administrativa.
- `static/css/saludbot.css` — tokens visuales del chatbot.
- `docs/deuda-almacenamiento-imagenes-credencial.md` — foto en base64 en la fila.

## Historial de versiones

| Versión | Fecha | Cambios |
| --- | --- | --- |
| 1 | 2026-08-20 | Versión inicial, validada en sesión de brainstorming. |
