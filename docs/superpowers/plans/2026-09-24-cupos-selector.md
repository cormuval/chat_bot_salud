# Cupos reales disponibles en el selector — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el selector cargue los cupos medicos del dia por centro dentro de la plataforma y vea cuantos quedan disponibles (derivado: iniciales menos aceptadas de hoy), reemplazando el Informe Diario manual.

**Architecture:** Un modelo nuevo `CupoDiario` en `gestion` (cupos_iniciales por centro y dia) y un helper `cupos_del_alcance(perfil, fecha)` que calcula disponibles en vivo (sin persistir el contador), usando limites datetime tz-aware para contar las aceptadas del dia (evita el bug de `CONVERT_TZ`). La vista `selector_lista` inyecta los cupos del alcance y una vista `guardar_cupo` (POST) los crea/edita. El template del selector muestra una tarjeta por centro. Sin tope duro.

**Tech Stack:** Django 5.2 (models, cache no aplica), MySQL 8.4 via runner de Django, plantillas Django.

## Global Constraints

- Codigo, comentarios y mensajes de commit en espanol, **sin tildes en identificadores**. Textos de UI (strings) si llevan tildes: no tocar esa convencion.
- Sin emojis en los mensajes de commit.
- Tests con el runner de Django contra **MySQL 8.4** (Docker arriba), **no** SQLite ni pytest. Comando: `.venv/bin/python manage.py test gestion`.
- `CupoDiario` guarda **solo** `cupos_iniciales`; los disponibles son **derivados** (no se persiste un contador).
- El conteo de "aceptadas de hoy" usa **limites datetime tz-aware** (`gestion/reportes.py: limites_datetime`), **nunca** `fecha_decision__date` (en MySQL genera `DATE(CONVERT_TZ(...))` que devuelve NULL sin tablas de tz).
- **Sin tope duro:** aceptar con 0 disponibles se permite; `disponibles` puede ser 0 o negativo (informativo).
- Solo roles de selector (SELECTOR / FULL / SOME) cargan cupos, y solo de centros de su alcance (`perfil.centros_permitidos()`).
- Modelos de gestion usan `settings.AUTH_USER_MODEL` para FKs a usuario y `Centro` importado de `solicitudes.models` (patron existente de `gestion/models.py`).
- Vistas de gestion se prueban con `@override_settings(ALLOWED_HOSTS=["gestion.localhost", "testserver"], GESTION_HOST="gestion.localhost")`, `self.client.force_login(user)` y rutas literales con `HTTP_HOST="gestion.localhost"` (patron existente en `gestion/tests.py`).
- No se toca el chatbot (`solicitudes`) salvo usar el modelo `Centro` (FK/lectura).
- Cada commit termina con:
  ```
  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_0125u967AuBBEDP1JHij8tg5
  ```

## File Structure

- Modify: `gestion/models.py` — modelo `CupoDiario`.
- Create: `gestion/cupos.py` — helper `cupos_del_alcance(perfil, fecha)`.
- Create: `gestion/migrations/00XX_cupodiario.py` — generada por `makemigrations`.
- Modify: `gestion/permisos.py` — `puede_cargar_cupos(perfil)`.
- Modify: `gestion/views.py` — `guardar_cupo` (nueva) + cupos en el contexto de `selector_lista`.
- Modify: `gestion/urls.py` — ruta `guardar_cupo`.
- Modify: `gestion/templates/gestion/selector_lista.html` — tarjetas de cupos.
- Modify: `static/css/gestion.css` — estilo minimo de las tarjetas.
- Modify: `gestion/tests.py` — tests de modelo/helper y de vistas.

Contexto reutilizable de `gestion/tests.py`: factory `crear_solicitud_base(**overrides)` (crea `Solicitud`; una senal `post_save` crea su `Gestion` en PENDIENTE, accesible como `.gestion`). `Centro.objects.get(pk=620)` (Rodelillo) y `pk=615` (Baron) existen por seed.

---

### Task 1: Modelo CupoDiario, migracion y helper de calculo

**Files:**
- Modify: `gestion/models.py`
- Create: `gestion/cupos.py`
- Create: migracion (via `makemigrations gestion`)
- Test: `gestion/tests.py` (clase nueva `CupoDiarioTests(TestCase)`)

**Interfaces:**
- Produces:
  - `CupoDiario` (campos `centro`, `fecha`, `cupos_iniciales`, `registrado_por`, `creado_en`, `actualizado_en`; `unique_together = ("centro", "fecha")`).
  - `cupos_del_alcance(perfil, fecha) -> list[dict]`, cada dict con `centro` (Centro), `iniciales` (int|None), `aceptadas` (int), `disponibles` (int|None).

- [ ] **Step 1: Escribir los tests (fallan primero)**

Agregar al final de `gestion/tests.py`:

```python
class CupoDiarioTests(TestCase):
    def _perfil_selector(self, centro):
        usuario = User.objects.create_user("sel@x.cl", "sel@x.cl")
        return PerfilUsuario.objects.create(
            usuario=usuario, rol=PerfilUsuario.Rol.SELECTOR, centro=centro
        )

    def _aceptar(self, centro, cuando):
        gestion = crear_solicitud_base(centro_salud=centro).gestion
        gestion.decision = Gestion.Decision.ACEPTADA
        gestion.fecha_decision = cuando
        gestion.save()
        return gestion

    def test_cupo_unico_por_centro_y_fecha(self):
        from gestion.models import CupoDiario
        centro = Centro.objects.get(pk=620)
        hoy = timezone.localdate()
        CupoDiario.objects.create(centro=centro, fecha=hoy, cupos_iniciales=10)
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                CupoDiario.objects.create(centro=centro, fecha=hoy, cupos_iniciales=5)

    def test_cupos_del_alcance_calcula_disponibles(self):
        from gestion.models import CupoDiario
        from gestion.cupos import cupos_del_alcance
        centro = Centro.objects.get(pk=620)
        otro = Centro.objects.get(pk=615)
        hoy = timezone.localdate()
        ahora = timezone.now()
        CupoDiario.objects.create(centro=centro, fecha=hoy, cupos_iniciales=10)
        self._aceptar(centro, ahora)
        self._aceptar(centro, ahora)
        # ruido que NO debe contar:
        crear_solicitud_base(centro_salud=centro)  # pendiente
        rechazada = crear_solicitud_base(centro_salud=centro).gestion
        rechazada.decision = Gestion.Decision.RECHAZADA
        rechazada.fecha_decision = ahora
        rechazada.save()
        self._aceptar(centro, ahora - timedelta(days=1))  # aceptada ayer
        self._aceptar(otro, ahora)  # aceptada hoy en otro centro

        perfil = self._perfil_selector(centro)
        filas = cupos_del_alcance(perfil, hoy)
        fila = next(f for f in filas if f["centro"].pk == centro.pk)
        self.assertEqual(fila["iniciales"], 10)
        self.assertEqual(fila["aceptadas"], 2)
        self.assertEqual(fila["disponibles"], 8)

    def test_disponibles_none_cuando_no_hay_registro(self):
        from gestion.cupos import cupos_del_alcance
        centro = Centro.objects.get(pk=620)
        perfil = self._perfil_selector(centro)
        filas = cupos_del_alcance(perfil, timezone.localdate())
        fila = next(f for f in filas if f["centro"].pk == centro.pk)
        self.assertIsNone(fila["iniciales"])
        self.assertIsNone(fila["disponibles"])

    def test_conteo_aceptadas_no_usa_convert_tz(self):
        from gestion.reportes import limites_datetime
        centro = Centro.objects.get(pk=620)
        hoy = timezone.localdate()
        inicio, fin = limites_datetime(hoy, hoy)
        qs = Gestion.objects.filter(
            solicitud__centro_salud=centro,
            decision=Gestion.Decision.ACEPTADA,
            fecha_decision__gte=inicio,
            fecha_decision__lt=fin,
        )
        self.assertNotIn("CONVERT_TZ", str(qs.query))
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `.venv/bin/python manage.py test gestion.tests.CupoDiarioTests -v 2`
Expected: FAIL (no existe `CupoDiario` ni `gestion/cupos.py`).

- [ ] **Step 3: Agregar el modelo `CupoDiario`**

En `gestion/models.py`, agregar al final del archivo:

```python
class CupoDiario(models.Model):
    """Cupos medicos iniciales disponibles que el selector carga por centro y dia.
    Guarda solo el numero cargado; los disponibles se calculan en vivo (ver
    gestion/cupos.py)."""

    centro = models.ForeignKey(
        Centro, on_delete=models.PROTECT, related_name="cupos_diarios"
    )
    fecha = models.DateField()
    cupos_iniciales = models.PositiveSmallIntegerField()
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("centro", "fecha")
        ordering = ["-fecha", "centro__centro"]

    def __str__(self):
        return f"{self.centro} {self.fecha}: {self.cupos_iniciales}"
```

- [ ] **Step 4: Generar la migracion**

Run: `.venv/bin/python manage.py makemigrations gestion`
Expected: crea un archivo `gestion/migrations/00XX_cupodiario.py` (el numero depende de las migraciones existentes). No editar a mano.

- [ ] **Step 5: Crear el helper `gestion/cupos.py`**

```python
from .models import CupoDiario, Gestion
from .reportes import limites_datetime


def cupos_del_alcance(perfil, fecha):
    """Cupos del dia `fecha` para cada centro del alcance del `perfil`.

    Devuelve una lista de dicts: {centro, iniciales, aceptadas, disponibles}.
    - iniciales: cupos_iniciales cargados hoy, o None si no se cargo.
    - aceptadas: Gestion ACEPTADA de ese centro con fecha_decision dentro del dia
      (limites tz-aware, sin __date para no gatillar CONVERT_TZ en MySQL).
    - disponibles: iniciales - aceptadas, o None si no hay iniciales.
    """
    inicio, fin = limites_datetime(fecha, fecha)
    centros = perfil.centros_permitidos()
    registros = {
        c.centro_id: c.cupos_iniciales
        for c in CupoDiario.objects.filter(centro__in=centros, fecha=fecha)
    }
    filas = []
    for centro in centros:
        iniciales = registros.get(centro.pk)
        aceptadas = Gestion.objects.filter(
            solicitud__centro_salud=centro,
            decision=Gestion.Decision.ACEPTADA,
            fecha_decision__gte=inicio,
            fecha_decision__lt=fin,
        ).count()
        disponibles = None if iniciales is None else iniciales - aceptadas
        filas.append(
            {
                "centro": centro,
                "iniciales": iniciales,
                "aceptadas": aceptadas,
                "disponibles": disponibles,
            }
        )
    return filas
```

- [ ] **Step 6: Correr los tests para verificar que pasan**

Run: `.venv/bin/python manage.py test gestion.tests.CupoDiarioTests -v 2`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add gestion/models.py gestion/cupos.py gestion/migrations/ gestion/tests.py
git commit -F - <<'EOF'
Agrega el modelo CupoDiario y el calculo de disponibles

CupoDiario guarda los cupos iniciales por centro y dia (unico por ambos). El
helper cupos_del_alcance calcula disponibles en vivo (iniciales menos aceptadas
de hoy) usando limites tz-aware para no gatillar CONVERT_TZ en MySQL.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0125u967AuBBEDP1JHij8tg5
EOF
```

---

### Task 2: Permiso, vista guardar_cupo, ruta y contexto del selector

**Files:**
- Modify: `gestion/permisos.py` (`puede_cargar_cupos`)
- Modify: `gestion/views.py` (`guardar_cupo` + contexto de `selector_lista`)
- Modify: `gestion/urls.py` (ruta)
- Test: `gestion/tests.py` (clase nueva `GuardarCupoTests`)

**Interfaces:**
- Consumes: `CupoDiario` y `cupos_del_alcance` (Task 1); `obtener_perfil_activo`, `ROLES_SELECTOR`, `perfil.centros_permitidos()` (existentes).
- Produces: `puede_cargar_cupos(perfil) -> bool`; ruta `gestion:guardar_cupo`; `selector_lista` agrega `cupos` y `puede_cargar_cupos` al contexto.

- [ ] **Step 1: Escribir los tests (fallan primero)**

Agregar a `gestion/tests.py`:

```python
@override_settings(ALLOWED_HOSTS=["gestion.localhost", "testserver"], GESTION_HOST="gestion.localhost")
class GuardarCupoTests(TestCase):
    def setUp(self):
        self.centro = Centro.objects.get(pk=620)
        self.otro = Centro.objects.get(pk=615)
        self.user = User.objects.create_user("sel@x.cl", "sel@x.cl")
        self.perfil = PerfilUsuario.objects.create(
            usuario=self.user, rol=PerfilUsuario.Rol.SELECTOR, centro=self.centro
        )
        self.client.force_login(self.user)

    def test_selector_carga_y_edita_cupo(self):
        from gestion.models import CupoDiario
        hoy = timezone.localdate()
        r = self.client.post(
            "/selector/cupos/",
            {"centro_id": self.centro.pk, "cupos_iniciales": 12},
            HTTP_HOST="gestion.localhost",
        )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(
            CupoDiario.objects.get(centro=self.centro, fecha=hoy).cupos_iniciales, 12
        )
        self.client.post(
            "/selector/cupos/",
            {"centro_id": self.centro.pk, "cupos_iniciales": 7},
            HTTP_HOST="gestion.localhost",
        )
        self.assertEqual(
            CupoDiario.objects.filter(centro=self.centro, fecha=hoy).count(), 1
        )
        self.assertEqual(
            CupoDiario.objects.get(centro=self.centro, fecha=hoy).cupos_iniciales, 7
        )

    def test_no_carga_centro_fuera_de_alcance(self):
        from gestion.models import CupoDiario
        r = self.client.post(
            "/selector/cupos/",
            {"centro_id": self.otro.pk, "cupos_iniciales": 5},
            HTTP_HOST="gestion.localhost",
        )
        self.assertEqual(r.status_code, 302)
        self.assertIn("sin-acceso", r["Location"])
        self.assertFalse(CupoDiario.objects.filter(centro=self.otro).exists())

    def test_rol_sin_permiso_no_carga(self):
        from gestion.models import CupoDiario
        u2 = User.objects.create_user("sup@x.cl", "sup@x.cl")
        PerfilUsuario.objects.create(
            usuario=u2, rol=PerfilUsuario.Rol.SUPERVISOR_CENTRO, centro=self.centro
        )
        self.client.force_login(u2)
        r = self.client.post(
            "/selector/cupos/",
            {"centro_id": self.centro.pk, "cupos_iniciales": 5},
            HTTP_HOST="gestion.localhost",
        )
        self.assertIn("sin-acceso", r["Location"])
        self.assertFalse(CupoDiario.objects.filter(centro=self.centro).exists())

    def test_selector_lista_incluye_cupos_en_contexto(self):
        from gestion.models import CupoDiario
        CupoDiario.objects.create(
            centro=self.centro, fecha=timezone.localdate(), cupos_iniciales=9
        )
        r = self.client.get("/selector/", HTTP_HOST="gestion.localhost")
        self.assertEqual(r.status_code, 200)
        self.assertIn("cupos", r.context)
        self.assertTrue(
            any(
                f["centro"].pk == self.centro.pk and f["iniciales"] == 9
                for f in r.context["cupos"]
            )
        )
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `.venv/bin/python manage.py test gestion.tests.GuardarCupoTests -v 2`
Expected: FAIL (no existe la ruta `guardar_cupo` ni el contexto `cupos`).

- [ ] **Step 3: Agregar el permiso**

En `gestion/permisos.py`, agregar (cerca de `puede_escribir_selector`):

```python
def puede_cargar_cupos(perfil):
    return perfil.rol in ROLES_SELECTOR
```

- [ ] **Step 4: Agregar la vista `guardar_cupo` y cupos al contexto de `selector_lista`**

En `gestion/views.py`:

(a) En el import de `.permisos`, agregar `puede_cargar_cupos` a la lista importada.

(b) Agregar el import del helper y de `timezone` (si no esta): al inicio, junto a los otros imports de `django.utils`:

```python
from django.utils import timezone

from .cupos import cupos_del_alcance
from .models import CupoDiario
```

(c) En `selector_lista`, antes de armar `context`, calcular los cupos solo para roles que cargan (evita computar sobre todos los centros para roles globales de solo lectura):

```python
    puede_cargar = puede_cargar_cupos(perfil)
    cupos = cupos_del_alcance(perfil, timezone.localdate()) if puede_cargar else []
```

y agregar al dict `context`:

```python
        "cupos": cupos,
        "puede_cargar_cupos": puede_cargar,
```

(d) Agregar la vista nueva (por ejemplo despues de `selector_detalle`):

```python
@require_POST
def guardar_cupo(request):
    perfil = obtener_perfil_activo(request.user)
    if perfil is None or not puede_cargar_cupos(perfil):
        return redirect("gestion:sin_acceso")
    try:
        centro_id = int(request.POST.get("centro_id", ""))
        cupos = int(request.POST.get("cupos_iniciales", ""))
    except (TypeError, ValueError):
        messages.error(request, "Indica un numero de cupos valido.")
        return redirect("gestion:selector_lista")
    if cupos < 0:
        messages.error(request, "Los cupos no pueden ser negativos.")
        return redirect("gestion:selector_lista")
    if not perfil.centros_permitidos().filter(pk=centro_id).exists():
        return redirect("gestion:sin_acceso")
    CupoDiario.objects.update_or_create(
        centro_id=centro_id,
        fecha=timezone.localdate(),
        defaults={"cupos_iniciales": cupos, "registrado_por": request.user},
    )
    messages.success(request, "Cupos actualizados.")
    return redirect("gestion:selector_lista")
```

- [ ] **Step 5: Agregar la ruta**

En `gestion/urls.py`, agregar (junto a las rutas del selector):

```python
    path("selector/cupos/", views.guardar_cupo, name="guardar_cupo"),
```

- [ ] **Step 6: Correr los tests para verificar que pasan**

Run: `.venv/bin/python manage.py test gestion.tests.GuardarCupoTests -v 2`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add gestion/permisos.py gestion/views.py gestion/urls.py gestion/tests.py
git commit -F - <<'EOF'
Agrega la carga de cupos y su contexto en el selector

Nuevo permiso puede_cargar_cupos (roles de selector), vista guardar_cupo (POST,
update_or_create del CupoDiario del dia validando el alcance) y ruta; selector_lista
inyecta los cupos del alcance y la bandera de carga en el contexto.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0125u967AuBBEDP1JHij8tg5
EOF
```

---

### Task 3: Tarjetas de cupos en el template del selector

**Files:**
- Modify: `gestion/templates/gestion/selector_lista.html`
- Modify: `static/css/gestion.css`
- Test: `gestion/tests.py` (agregar a `GuardarCupoTests`)

**Interfaces:**
- Consumes: contexto `cupos` y `puede_cargar_cupos` de `selector_lista` (Task 2); ruta `gestion:guardar_cupo`.

- [ ] **Step 1: Escribir el test (falla primero)**

Agregar a `GuardarCupoTests` en `gestion/tests.py`:

```python
    def test_selector_lista_muestra_tarjeta_de_cupos(self):
        from gestion.models import CupoDiario
        CupoDiario.objects.create(
            centro=self.centro, fecha=timezone.localdate(), cupos_iniciales=9
        )
        r = self.client.get("/selector/", HTTP_HOST="gestion.localhost")
        self.assertContains(r, "Cupos del dia")
        self.assertContains(r, 'name="cupos_iniciales"')
        self.assertContains(r, "/selector/cupos/")
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/python manage.py test gestion.tests.GuardarCupoTests.test_selector_lista_muestra_tarjeta_de_cupos -v 2`
Expected: FAIL (el template aun no muestra las tarjetas).

- [ ] **Step 3: Agregar las tarjetas al template**

En `gestion/templates/gestion/selector_lista.html`, insertar entre la seccion `page-title` y el `{% include "gestion/_tabla_selector.html" %}`:

```html
{% if puede_cargar_cupos and cupos %}
<section class="cupos-selector" aria-label="Cupos disponibles del dia">
  <h3 class="cupos-selector__titulo">Cupos del dia</h3>
  <div class="cupos-selector__grid">
    {% for fila in cupos %}
    <form class="cupo-card" method="post" action="{% url 'gestion:guardar_cupo' %}">
      {% csrf_token %}
      <input type="hidden" name="centro_id" value="{{ fila.centro.pk }}">
      <div class="cupo-card__info">
        <strong>{{ fila.centro }}</strong>
        <span class="cupo-card__disponibles">
          {% if fila.disponibles is None %}
            Sin cargar
          {% else %}
            {{ fila.disponibles }} / {{ fila.iniciales }} disponibles
          {% endif %}
        </span>
      </div>
      <div class="cupo-card__form">
        <label class="sr-only" for="cupo-{{ fila.centro.pk }}">Cupos iniciales de {{ fila.centro }}</label>
        <input id="cupo-{{ fila.centro.pk }}" type="number" min="0" name="cupos_iniciales"
               value="{{ fila.iniciales|default_if_none:'' }}">
        <button type="submit">Guardar</button>
      </div>
    </form>
    {% endfor %}
  </div>
</section>
{% endif %}
```

- [ ] **Step 4: Agregar estilo minimo**

En `static/css/gestion.css`, agregar al final:

```css
.cupos-selector {
  margin: 0 0 18px;
}
.cupos-selector__titulo {
  margin: 0 0 8px;
  font-size: 1rem;
}
.cupos-selector__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 12px;
}
.cupo-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px;
  border: 1px solid var(--line, #D8E2EF);
  border-radius: 8px;
  background: #FFFFFF;
}
.cupo-card__disponibles {
  color: #145EA8;
  font-weight: 700;
}
.cupo-card__form {
  display: flex;
  gap: 8px;
}
.cupo-card__form input[type="number"] {
  width: 90px;
}
```

- [ ] **Step 5: Correr el test para verificar que pasa**

Run: `.venv/bin/python manage.py test gestion.tests.GuardarCupoTests.test_selector_lista_muestra_tarjeta_de_cupos -v 2`
Expected: PASS.

- [ ] **Step 6: Verificacion manual anotada**

En `runserver` (host de gestion): como selector, cargar un numero de cupos; el contador debe mostrar "N / M disponibles" y bajar al aceptar una solicitud del centro; recargar al dia siguiente debe pedir cargar de nuevo. Anotar en el PR.

- [ ] **Step 7: Commit**

```bash
git add gestion/templates/gestion/selector_lista.html static/css/gestion.css gestion/tests.py
git commit -F - <<'EOF'
Muestra las tarjetas de cupos del dia en el selector

Arriba de la cola, una tarjeta por centro del alcance con los disponibles y un
formulario para cargar o editar los cupos iniciales del dia.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_0125u967AuBBEDP1JHij8tg5
EOF
```

---

### Task 4: Suite completa y verificacion final

**Files:**
- Sin cambios de codigo; corrida completa y notas de cierre.

- [ ] **Step 1: Correr toda la suite de gestion**

Run: `.venv/bin/python manage.py test gestion -v 2`
Expected: PASS (incluye CupoDiarioTests y GuardarCupoTests, y sin regresiones en el selector).

- [ ] **Step 2: Correr la suite completa del proyecto**

Run: `.venv/bin/python manage.py test`
Expected: PASS.

- [ ] **Step 3: Checklist de verificacion manual del PR**

Confirmar en `runserver` y dejar anotado en el PR: (1) el selector carga cupos por centro de su alcance; (2) el contador de disponibles baja al aceptar; (3) un centro fuera del alcance o un rol sin permiso no puede cargar; (4) el dia siguiente pide cargar de nuevo.

---

## Self-Review

**Spec coverage:**
- Modelo `CupoDiario` (centro, fecha, cupos_iniciales, registrado_por; unico por centro/dia) → Task 1. ✔
- Disponibles derivado (iniciales - aceptadas de hoy, tz-aware sin CONVERT_TZ) → Task 1 (`cupos_del_alcance`) + test anti-CONVERT_TZ. ✔
- Carga por el selector, solo su alcance; permiso `puede_cargar_cupos` → Task 2. ✔
- Contador informativo, sin tope duro (disponibles puede ser 0/negativo) → Task 1 (calculo sin clamp) + Task 3 (solo muestra). ✔
- Por dia (no arrastra) → `fecha=timezone.localdate()` y unicidad; Task 1/2. ✔
- Tarjetas en el selector → Task 3. ✔
- Reporte historico fuera de alcance (issue #34) → no hay tarea (correcto). ✔

**Placeholder scan:** sin TBD/TODO; cada paso trae codigo o comando concreto (la migracion se genera con `makemigrations`, no se escribe a mano). ✔

**Type consistency:** `cupos_del_alcance(perfil, fecha)` devuelve dicts con `centro`/`iniciales`/`aceptadas`/`disponibles`, usados igual en la vista, el template y los tests; `puede_cargar_cupos(perfil)` usado en `selector_lista`, `guardar_cupo` y tests; `CupoDiario` con `unique_together (centro, fecha)` coherente con `update_or_create(centro_id, fecha, ...)`; conteo de aceptadas usa `Gestion.Decision.ACEPTADA` (valor real del modelo) y `limites_datetime` (firma real de `gestion/reportes.py`). ✔
