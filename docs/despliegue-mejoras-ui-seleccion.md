# Despliegue mejoras UI Selector y Comunicador

Fecha prevista: 2026-08-28

## Motivos de rechazo no transformados

La migracion `0007_seed_plantilla_whatsapp_y_limpia_motivos` solo limpia motivos
que comienzan con el patron `Hola {nombre}`. Los motivos que no calzan se dejan
intactos para evitar reescrituras inventadas.

Despues de migrar, revisar en el admin de Django los motivos de rechazo activos y
confirmar que `mensaje_paciente` contiene solo el cuerpo del mensaje, sin saludo ni
cierre.

## Historial no reconstruible

La migracion `0009_backfill_registro_contacto` crea registros historicos desde
`TokenContactoGestion`. Las gestiones con `intentos_contacto > 0` sin token asociado
no son reconstruibles porque el sistema anterior no guardaba cada evento.

El historial nuevo es confiable desde el despliegue de esta version. El backfill
solo cubre eventos con token. La reversa de la migracion de backfill no borra
registros porque no existe una marca persistida que distinga sin ambiguedad un
registro reconstruido de una llamada real posterior con usuario eliminado.

## Bloqueador de popups

El flujo abre una pestana vacia antes del `fetch` para conservar el gesto del
usuario. Si el navegador bloquea igualmente la apertura, el modal muestra un enlace
manual `Abrir WhatsApp`.

Validar el flujo en los navegadores usados por el equipo antes de dar por cerrada
la fase 2.

## Verificacion tecnica

Ejecutar:

```bash
docker compose up -d
.venv/bin/python manage.py migrate
.venv/bin/python manage.py test
```
