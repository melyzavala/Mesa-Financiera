"""Batuta, el orquestador: decide el orden y pasa el output de cada agente como input del siguiente.

Como un director de orquesta, no toca ningún instrumento: dirige a Iris, Euler y Vera."""
import json
import os
import re
from datetime import datetime, timezone

from . import config
from .agentes import agente_analista, agente_comunicador, agente_recolector

PATRON_TICKER = re.compile(r"[A-Z0-9.\-]{1,12}")


def normalizar_ticker(texto):
    """'aapl ' → 'AAPL'. Lanza ValueError si no parece un ticker."""
    ticker = (texto or "").strip().upper()
    if not PATRON_TICKER.fullmatch(ticker):
        raise ValueError(f"Ticker no válido: '{texto}'. Ejemplo correcto: AAPL")
    return ticker


def resumir_ficha_para_aviso(ficha):
    """Muestra trazabilidad en Telegram sin publicar las series completas."""
    resumen = {campo: ficha.get(campo) for campo in
               ("ticker", "precio", "cambio_pct", "fecha_dato", "fuente")}
    for campo in ("serie_semanal_accion", "serie_semanal_spy"):
        serie = ficha.get(campo) or []
        resumen[campo] = {
            "observaciones": len(serie),
            "primera": serie[0] if serie else None,
            "ultima": serie[-1] if serie else None,
        }
    return resumen


def pipeline(ticker, avisar=print, guardar=True):
    """Batuta ejecuta la cadena Iris → Euler → Vera.

    avisar: función que recibe textos de avance (print en terminal, enviar a Telegram en el bot).
    Devuelve un diccionario con las tres entregas, útil como evidencia.
    """
    ticker = normalizar_ticker(ticker)
    modo = "SIMULACIÓN" if config.MODO_SIMULACION else "REAL"

    avisar(f"🎼 Batuta · Orquestador\nRecibí tu orden. Inicio la cadena para {ticker} (modo {modo}).")
    avisar(f"🛰️ Iris · Recolectora buscando datos de {ticker}…")
    ficha, consultas = agente_recolector(ticker)
    if config.MODO_CLASE:
        ficha_visible = resumir_ficha_para_aviso(ficha)
        avisar("📦 Entrega 1→2 · Iris → Euler (resumen de ficha):\n"
               + json.dumps(ficha_visible, ensure_ascii=False, indent=1)
               + f"\n🔧 Consultas Alpha Vantage: {', '.join(consultas) or 'ninguna (simulación)'}")

    avisar("🧮 Euler · Analista Financiero calculando e interpretando…")
    analisis = agente_analista(ficha)
    if config.MODO_CLASE:
        avisar("📦 Entrega 2→3 · Euler → Vera (indicadores):\n"
               + json.dumps(analisis["indicadores"], ensure_ascii=False, indent=1))

    avisar("✍️ Vera · Editora Financiera jerarquizando y redactando…")
    nota = agente_comunicador(analisis)

    resultado = {
        "ticker": ticker,
        "modo": modo,
        "fecha_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "entrega_1_ficha": ficha,
        "consultas_alpha_vantage": consultas,
        "entrega_2_analisis": analisis,
        "entrega_3_nota": nota,
    }
    if guardar:
        resultado["archivo"] = guardar_evidencia(resultado)
    return resultado


def guardar_evidencia(resultado):
    """Guarda la corrida completa en salidas/TICKER_fecha.json (evidencia para la rúbrica)."""
    os.makedirs(config.CARPETA_SALIDAS, exist_ok=True)
    sello = resultado["fecha_utc"].replace(":", "").replace("-", "")[:15]
    ruta = os.path.join(config.CARPETA_SALIDAS, f"{resultado['ticker']}_{sello}.json")
    with open(ruta, "w", encoding="utf-8") as archivo:
        json.dump(resultado, archivo, ensure_ascii=False, indent=2)
    return ruta
