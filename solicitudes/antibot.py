import time

from django.core import signing
from django.core.cache import cache

SEGUNDOS_MINIMOS = 8
SEGUNDOS_MAXIMOS = 30 * 60
RATE_LIMITE = 10
RATE_VENTANA_SEG = 10 * 60
_SALT = "solicitudes.antibot.token_tiempo"


def firmar_token_tiempo(ts=None):
    """Token firmado con el instante de emision. `ts` explicito facilita los tests."""
    momento = time.time() if ts is None else ts
    return signing.dumps({"ts": momento}, salt=_SALT)


def validar_token_tiempo(token):
    """None si el token es valido; si no, el motivo:
    'invalido' (ausente/firma mala), 'muy_rapido' (< SEGUNDOS_MINIMOS),
    'vencido' (> SEGUNDOS_MAXIMOS)."""
    if not token:
        return "invalido"
    try:
        datos = signing.loads(token, salt=_SALT)
    except signing.BadSignature:
        return "invalido"
    ts = datos.get("ts")
    if not isinstance(ts, (int, float)):
        return "invalido"
    transcurrido = time.time() - ts
    if transcurrido < SEGUNDOS_MINIMOS:
        return "muy_rapido"
    if transcurrido > SEGUNDOS_MAXIMOS:
        return "vencido"
    return None


def honeypot_activado(body):
    """True si el campo senuelo llego con contenido (lo llena un bot, no el humano)."""
    return bool(str(body.get("sitio_web") or "").strip())


def ip_cliente(request):
    """IP real detras de un unico proxy de confianza (nginx). El ultimo valor de
    X-Forwarded-For lo agrega nuestro nginx (la IP que conecto al proxy); los de la
    izquierda los puede falsear el cliente, por eso NO se usan. Sin XFF, REMOTE_ADDR."""
    reenviada = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if reenviada:
        return reenviada.split(",")[-1].strip()
    return request.META.get("REMOTE_ADDR", "")


def rate_limit_excedido(request):
    """Cuenta cada intento por IP en el cache; True si supera RATE_LIMITE en la ventana.
    Usa add+incr: el TTL se fija al crear la clave (ventana fija, no se renueva en cada
    intento) y el incremento es atomico."""
    ip = ip_cliente(request) or "desconocida"
    clave = f"antibot:rate:{ip}"
    cache.add(clave, 0, RATE_VENTANA_SEG)
    try:
        intentos = cache.incr(clave)
    except ValueError:
        # La clave expiro entre el add y el incr: reseembrar y reintentar.
        cache.add(clave, 0, RATE_VENTANA_SEG)
        intentos = cache.incr(clave)
    return intentos > RATE_LIMITE
