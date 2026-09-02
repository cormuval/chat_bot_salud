import csv
from datetime import date, datetime, time, timedelta

from django.http import StreamingHttpResponse
from django.utils import timezone


class _Buffer:
    def write(self, value):
        return value


def exportar_csv(nombre_archivo, encabezados, filas):
    """Devuelve un CSV en streaming, UTF-8 con BOM para que Excel respete
    tildes y enies."""
    writer = csv.writer(_Buffer())

    def generar():
        yield "﻿"  # BOM UTF-8
        yield writer.writerow(encabezados)
        for fila in filas:
            yield writer.writerow(fila)

    response = StreamingHttpResponse(generar(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{nombre_archivo}"'
    return response


def _parse_fecha(valor):
    try:
        return date.fromisoformat(valor)
    except (ValueError, TypeError):
        return None


def rango_fechas(request):
    return _parse_fecha(request.GET.get("desde")), _parse_fecha(request.GET.get("hasta"))


def limites_datetime(desde, hasta):
    """Convierte el rango de fechas (locales) en un par de datetime tz-aware
    [inicio, fin) para filtrar una columna DateTimeField con __gte/__lt.

    Se evita a proposito el lookup __date, que en MySQL genera
    DATE(CONVERT_TZ(col, 'UTC', TIME_ZONE)); si el MySQL no tiene cargadas las
    tablas de zonas horarias, CONVERT_TZ con zona nombrada devuelve NULL y el
    filtro no matchea ninguna fila (el CSV sale solo con encabezados). Filtrar
    por limites tz-aware compara contra el UTC guardado sin CONVERT_TZ sobre la
    columna, asi funciona con o sin tablas de tz en la BD."""
    tz = timezone.get_current_timezone()
    inicio = timezone.make_aware(datetime.combine(desde, time.min), tz)
    fin = timezone.make_aware(datetime.combine(hasta + timedelta(days=1), time.min), tz)
    return inicio, fin
