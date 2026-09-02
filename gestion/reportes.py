import csv
from datetime import date

from django.http import StreamingHttpResponse


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
