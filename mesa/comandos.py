"""Interpreta los mensajes que el alumno escribe en Telegram (lo comparten el bot continuo y GitHub Actions)."""
import time

from . import config
from .pipeline import normalizar_ticker, pipeline
from .telegram_io import chat_autorizado, enviar

_ULTIMA_SOLICITUD = {}

AYUDA = ("🤖 Mesa Financiera de 3 agentes\n"
         "/analiza TICKER → ejemplo: /analiza AAPL\n"
         "Batuta dirige: Iris (Alpha Vantage) → Euler (análisis) → Vera (nota)\n"
         "Límite gratuito de Alpha Vantage: 25 consultas al día.")


def es_analisis(texto):
    partes = (texto or "").strip().lower().split()
    return bool(partes) and partes[0] == "/analiza"


def atender(mensaje):
    """Procesa un mensaje de Telegram. Devuelve el resultado del pipeline o None."""
    chat_id = mensaje["chat"]["id"]
    texto = (mensaje.get("text") or "").strip()

    if not chat_autorizado(chat_id):
        enviar(chat_id, "Este bot es privado.")
        return None
    if not es_analisis(texto):
        enviar(chat_id, AYUDA)
        return None

    partes = texto.split()
    if len(partes) != 2:
        enviar(chat_id, "Usa el formato exacto: /analiza TICKER (ejemplo: /analiza MSFT)")
        return None
    try:
        ticker = normalizar_ticker(partes[1])
    except ValueError:
        enviar(chat_id, "Escribe un ticker válido. Ejemplo: /analiza MSFT")
        return None

    clave = (str(chat_id), ticker)
    ahora = time.monotonic()
    restante = config.COOLDOWN_SEGUNDOS - (ahora - _ULTIMA_SOLICITUD.get(clave, -float("inf")))
    if restante > 0:
        enviar(chat_id, f"⏳ {ticker} ya fue solicitado recientemente. Espera {int(restante) + 1} segundos.")
        return None
    _ULTIMA_SOLICITUD[clave] = ahora

    try:
        resultado = pipeline(ticker, avisar=lambda t: enviar(chat_id, t))
        enviar(chat_id, resultado["entrega_3_nota"])
        return resultado
    except Exception as error:
        _ULTIMA_SOLICITUD.pop(clave, None)  # un fallo no bloquea un reintento legítimo
        enviar(chat_id, f"⚠️ No pude completar el análisis real: {error}. "
                        "No se generaron datos ficticios. Puedes intentar de nuevo en unos minutos.")
        raise
