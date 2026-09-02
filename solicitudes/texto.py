import unicodedata


def normalizar(texto):
    """Minusculas y sin acentos, para comparar palabras clave sin que las
    tildes o mayusculas cambien el resultado."""
    base = (texto or "").strip().lower()
    descompuesto = unicodedata.normalize("NFKD", base)
    return "".join(c for c in descompuesto if not unicodedata.combining(c))
