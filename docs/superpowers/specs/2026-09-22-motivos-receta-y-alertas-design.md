# Spec 2 — Motivos, categoria Receta y alertas de seguridad del chatbot

Fecha: 2026-09-22
Modulo: `solicitudes` (chatbot publico, host `morbilidad.cmvalparaiso.cl`)
Archivo principal: `static/js/saludbot.js`. Tests en `solicitudes/tests.py`
(`SaludBotScriptTests`).

## Contexto

El flujo del chatbot vive en `static/js/saludbot.js` (arreglo `steps` recorrido
por indice; ver Spec 1). El motivo se elige con botones rapidos (`quickActions()`)
o escribiendo texto; tras elegir motivo se muestra la tarjeta de urgencia
(`renderUrgencyWarning()` via `showUrgencyWarning()`), luego el paso de sintomas
(`detalle_sintomas`), y el resto del flujo. El texto de sintomas se guarda como
`detalle_motivo` en el backend.

De la reunion y el acta salieron tres ajustes de contenido y reglas de negocio,
que esta spec agrupa. No cambian el modelo `Solicitud` ni el backend.

Estado actual relevante:
- Botones de motivo: `Tengo Fiebre`, `Dolor o malestar`, `Problemas respiratorios`,
  `Vomitos o diarrea`, `Problemas al orinar`, `Otros motivos`.
- Tarjeta de urgencia: lista de sintomas de alarma (dolor de pecho, dificultad
  para respirar, perdida de conciencia, convulsiones, sangrado, debilidad
  repentina de un brazo o una pierna) + recomendacion de SAPU/urgencia y
  ambulancia 131. No menciona ACV ni salud mental.
- En `submitValue`, tras contestar el motivo:
  `if (step.field === "motivo") { showUrgencyWarning(); return; }`.

## Cambios

### 1. Botones de motivo

Nueva lista de `quickActions()`, en este orden:

```
Fiebre · Dolor o malestar · Problemas respiratorios · Vomitos o diarrea ·
Problemas al orinar · Otros motivos · Receta
```

- Se renombra `Tengo Fiebre` a `Fiebre`.
- Se agrega `Receta` como ultimo boton.
- Las demas etiquetas quedan igual.

El valor enviado del boton es su etiqueta (`data-value`), asi que el motivo
guardado sera `Receta`, `Fiebre`, etc.

### 2. Rama de Receta (flujo acortado)

`Receta` (repeticion de receta) no es morbilidad aguda, asi que toma un camino
distinto. Se considera "motivo Receta" cuando el motivo, normalizado (minusculas,
sin espacios sobrantes), es exactamente `receta` — cubre el boton `Receta` y el
texto escrito `receta`/`Receta`. Variantes libres ("repeticion de receta") siguen
el flujo normal (aceptable: el boton es el camino esperado).

Diferencias respecto al flujo normal (todo lo demas queda igual):

- **No se muestra la tarjeta de urgencia.** En `submitValue`, tras el motivo: si
  es Receta, se continua directo al siguiente paso (`askCurrentStep()`) en vez de
  `showUrgencyWarning()`.
- **El paso `detalle_sintomas` se vuelve la pregunta de medicamento.** Su prompt
  pasa a: *"¿Que medicamento(s) necesitas repetir? Indica el nombre y la dosis si
  la conoces."* y su validacion se relaja (un nombre de medicamento es corto; se
  pide un minimo razonable, p. ej. 3 caracteres, no los 20 del detalle de
  sintomas). La respuesta se guarda en el mismo campo (`detalle_sintomas` ->
  `detalle_motivo`), sin cambios de backend.

Se mantienen, en el mismo orden que el flujo normal: CESFAM, RUT, Nombre, edad,
telefono, credencial, neurodivergencia y el resumen final.

El prompt y la validacion condicionales del paso `detalle_sintomas` se derivan de
si el motivo es Receta (por ejemplo, un flag `state.esReceta` fijado al contestar
el motivo, leido por el paso). El resumen final sigue mostrando la respuesta bajo
la fila de detalle existente; no se agrega una etiqueta nueva.

### 3. Alerta de urgencia: ACV y salud mental

En `renderUrgencyWarning()` (tarjeta que se muestra en el flujo normal tras el
motivo):

- **Signo de ACV.** Se agrega a la lista de sintomas de alarma el item:
  *"Problemas o dificultad para hablar (posible ACV)"*. Es un item mas de la
  lista, con la mencion de posible ACV incluida en el texto.
- **Linea de salud mental.** Se agrega dentro de la misma tarjeta una linea de
  advertencia: *"Si tienes pensamientos de hacerte dano o quitarte la vida, llama
  al Fono de prevencion del suicidio *4141 (gratuito) o acude al servicio de
  urgencia mas cercano."* Es una advertencia clara e inmediata, no un canal de
  contencion; se muestra siempre (no depende de detectar palabras clave).

**Consecuencia aceptada:** como esta linea vive en la tarjeta de urgencia y la
rama de Receta omite esa tarjeta, la advertencia de salud mental no aparece en el
flujo de Receta. Se considera aceptable porque Receta es un tramite, no morbilidad
aguda. (Decision del usuario.)

## Testing

Aserciones sobre el fuente de `saludbot.js` (`SaludBotScriptTests`,
`SimpleTestCase`, la convencion del repo para el flujo JS; no hay arnes de
navegador):

- `quickActions()` contiene `"Receta"` y `"Fiebre"`, ya no contiene `"Tengo Fiebre"`.
- La tarjeta de urgencia contiene el item `"Problemas o dificultad para hablar (posible ACV)"`.
- La tarjeta de urgencia contiene la linea de salud mental con `"*4141"`.
- La logica de motivo distingue Receta: existe la deteccion de motivo Receta y la
  rama que omite `showUrgencyWarning()` para ese caso (aserciones sobre las
  construcciones correspondientes).
- El paso `detalle_sintomas` tiene el prompt de medicamento condicionado a Receta.

Verificacion manual (comportamiento en navegador): elegir `Receta` no muestra la
tarjeta de urgencia y pregunta por el medicamento; elegir un motivo clinico si
muestra la tarjeta con el item de ACV y la linea *4141; el resto del flujo de
Receta (CESFAM, datos, resumen, envio) completa y guarda `motivo="Receta"` con la
respuesta del medicamento en `detalle_motivo`.

Correr `.venv/bin/python manage.py test` (runner de Django, MySQL 8.4) antes de
dar la tarea por terminada.

## Fuera de alcance

- Defensa contra bots (Spec 3).
- Captura de cupos reales en el selector (Spec 4).
- No se modifica el modelo `Solicitud` ni el backend; el catalogo de motivos no se
  persiste como enum (el motivo sigue siendo texto libre con botones de ayuda).
- El archivo en desuso `solicitudes/templates/solicitudes/chatbot.html` /
  `solicitudes/static/solicitudes/chatbot.js` no se toca.
