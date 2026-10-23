"""Configuración: lee las llaves desde variables de entorno o desde el archivo .env.

Nunca escribas una llave dentro del código. En tu computadora van en .env;
en GitHub van en Settings → Secrets and variables → Actions; en Colab, en el panel 🔑.
"""
import os

try:                                    # python-dotenv es opcional: si existe, carga .env
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _texto(nombre, defecto=""):
    return (os.environ.get(nombre) or defecto).strip()


def _bandera(nombre, defecto="0"):
    return _texto(nombre, defecto).lower() in ("1", "true", "si", "sí", "yes")


def _entero_acotado(nombre, defecto, minimo, maximo):
    """Lee un entero sin permitir que una variable mal formada rompa o desborde la ejecución."""
    try:
        valor = int(_texto(nombre, str(defecto)))
    except ValueError:
        valor = defecto
    return max(minimo, min(maximo, valor))


TELEGRAM_BOT_TOKEN   = _texto("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID     = _texto("TELEGRAM_CHAT_ID")        # tu chat; el bot solo atiende a este chat
OPENAI_API_KEY       = _texto("OPENAI_API_KEY")
ALPHAVANTAGE_API_KEY = _texto("ALPHAVANTAGE_API_KEY")

MODELO     = _texto("MODELO", "gpt-5.5")                 # Python controla el formato; razonamiento desactivado
MODO_CLASE = _bandera("MODO_CLASE", "1")                  # 1 = muestra cada entrega entre agentes

# Interruptor explícito: permite desactivar el modo real aunque existan llaves.
HABILITAR_MODO_REAL = _bandera("HABILITAR_MODO_REAL", "1")

# Modo simulación: se activa por petición, por interruptor apagado o por llaves incompletas.
MODO_SIMULACION = (_bandera("MODO_SIMULACION") or not HABILITAR_MODO_REAL
                   or not (OPENAI_API_KEY and ALPHAVANTAGE_API_KEY))

MAX_ANALISIS_POR_RUN = _entero_acotado("MAX_ANALISIS_POR_RUN", 3, 1, 3)
COOLDOWN_SEGUNDOS = _entero_acotado("COOLDOWN_SEGUNDOS", 60, 0, 3600)
CARPETA_SALIDAS = _texto("CARPETA_SALIDAS", "salidas")


def resumen():
    """Estado de la configuración sin revelar ningún valor secreto."""
    def estado(valor):
        return "✅ configurada" if valor else "⬜ vacía"
    return {
        "TELEGRAM_BOT_TOKEN": estado(TELEGRAM_BOT_TOKEN),
        "TELEGRAM_CHAT_ID": estado(TELEGRAM_CHAT_ID),
        "OPENAI_API_KEY": estado(OPENAI_API_KEY),
        "ALPHAVANTAGE_API_KEY": estado(ALPHAVANTAGE_API_KEY),
        "MODELO": MODELO,
        "MODO_REAL_HABILITADO": "sí" if HABILITAR_MODO_REAL else "no",
        "MODO_SIMULACION": "sí" if MODO_SIMULACION else "no (datos y agentes reales)",
        "MAX_ANALISIS_POR_RUN": MAX_ANALISIS_POR_RUN,
        "COOLDOWN_SEGUNDOS": COOLDOWN_SEGUNDOS,
    }
