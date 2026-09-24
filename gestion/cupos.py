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
