"""Los tres agentes de la Mesa Financiera.

  Iris  · La Recolectora  (Agente 1) → consulta la API de Alpha Vantage y entrega una FICHA (JSON)
  Euler · Analista Financiero (Agente 2) → recibe la ficha, Python calcula y OpenAI interpreta → ANÁLISIS (JSON)
  Vera  · Editora Financiera  (Agente 3) → edita el hallazgo; Python compone la NOTA para Telegram
  (Batuta, el orquestador que los dirige, vive en mesa/pipeline.py)

Regla de oro: los números los calcula el código; la IA solo interpreta.
"""
import json
import math
import re
import statistics
from datetime import date, timedelta

import requests

from . import config

DESCARGO = "Nota educativa, no es recomendación de inversión."
FIRMA_VERA = "✍️ Vera | Mesa Financiera"
CAMPOS_FICHA = ("ticker", "precio", "cambio_pct", "fecha_dato",
                "serie_semanal_accion", "serie_semanal_spy")
PATRONES_INYECCION = re.compile(
    r"(ignora (las|todas|cualquier) instrucciones|ignore (all|previous) instructions|"
    r"system prompt|mensaje del sistema|revela.*(clave|token|api key)|"
    r"ejecuta (un |el )?(comando|código|script))", re.IGNORECASE)

# ----------------------------------------------------------------------
# Conexión con OpenAI (solo se usa fuera del modo simulación)
# ----------------------------------------------------------------------
_cliente = None


def _cliente_openai():
    global _cliente
    if _cliente is None:
        from openai import OpenAI
        _cliente = OpenAI(api_key=config.OPENAI_API_KEY)
    return _cliente


def llamar_openai(system, mensaje, max_tokens=900):
    """Envía un mensaje compacto con la Responses API."""
    base = dict(model=config.MODELO, max_output_tokens=max_tokens, instructions=system,
                input=mensaje, store=False, reasoning={"effort": "none"})
    cliente = _cliente_openai()
    respuesta = cliente.responses.create(**base)
    texto = respuesta.output_text.strip()
    return texto


def extraer_json(texto):
    """Recupera el objeto JSON de un texto (a veces el modelo agrega palabras alrededor)."""
    inicio, fin = texto.find("{"), texto.rfind("}")
    if inicio == -1 or fin <= inicio:
        raise ValueError("El agente no devolvió JSON")
    return json.loads(texto[inicio:fin + 1])


def a_numero(valor):
    """Convierte '123.4', '-0.8%' o '1,234' en número; si no se puede, None."""
    try:
        return float(str(valor).replace("%", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def _texto_externo(valor, campo, limite=120):
    if valor is None:
        return None
    texto = str(valor).strip()
    if len(texto) > limite or any(ord(c) < 32 for c in texto) or PATRONES_INYECCION.search(texto):
        raise ValueError(f"Contenido externo no válido en {campo}")
    return texto or None


def validar_ficha(ficha, ticker_esperado):
    """Aplica un contrato estricto a datos MCP antes de pasarlos a otros agentes."""
    if not isinstance(ficha, dict):
        raise ValueError("La ficha no es un objeto JSON")
    extras = set(ficha) - set(CAMPOS_FICHA)
    if extras:
        raise ValueError("La ficha contiene campos no permitidos")

    ticker_recibido = _texto_externo(ficha.get("ticker"), "ticker", 12)
    if ticker_recibido and ticker_recibido.upper() != ticker_esperado:
        raise ValueError("El ticker de la fuente no coincide con la solicitud")

    salida = {campo: None for campo in CAMPOS_FICHA}
    salida["ticker"] = ticker_esperado
    salida["fecha_dato"] = _texto_externo(ficha.get("fecha_dato"), "fecha_dato", 40)
    for campo in ("precio", "cambio_pct"):
        valor_original = ficha.get(campo)
        valor = a_numero(valor_original)
        if valor_original is not None and valor is None:
            raise ValueError(f"Valor numérico no válido en {campo}")
        salida[campo] = valor

    if salida["precio"] is not None and salida["precio"] <= 0:
        raise ValueError("precio debe ser positivo")
    if salida["cambio_pct"] is not None and not -100 <= salida["cambio_pct"] <= 1000:
        raise ValueError("Cambio porcentual fuera de rango")
    salida["serie_semanal_accion"] = validar_serie(
        ficha.get("serie_semanal_accion"), ("fecha", "cierre_ajustado", "maximo", "minimo"))
    salida["serie_semanal_spy"] = validar_serie(
        ficha.get("serie_semanal_spy"), ("fecha", "cierre_ajustado"))
    return salida


def validar_serie(serie, campos):
    """Valida series compactas, ordenadas de la observación más antigua a la más reciente."""
    if not isinstance(serie, list) or not 53 <= len(serie) <= 110:
        raise ValueError("La serie semanal debe contener entre 53 y 110 observaciones")
    salida, fechas = [], []
    for fila in serie:
        if not isinstance(fila, dict) or set(fila) != set(campos):
            raise ValueError("Fila semanal con contrato no válido")
        fecha = _texto_externo(fila.get("fecha"), "fecha", 10)
        valores = {campo: a_numero(fila.get(campo)) for campo in campos if campo != "fecha"}
        if not fecha or any(valor is None or valor <= 0 for valor in valores.values()):
            raise ValueError("Fila semanal con fecha o valor no válido")
        if "maximo" in valores and valores["maximo"] < valores["minimo"]:
            raise ValueError("Máximo semanal menor que el mínimo")
        fechas.append(fecha)
        salida.append({"fecha": fecha, **valores})
    if fechas != sorted(fechas) or len(fechas) != len(set(fechas)):
        raise ValueError("Las fechas semanales deben ser únicas y ascendentes")
    return salida


class DatosExternosError(RuntimeError):
    """Falla segura al consultar o validar una fuente externa."""


# ----------------------------------------------------------------------
# IRIS · La Recolectora (Agente 1)
# ----------------------------------------------------------------------
CONSULTAS_ALPHA = ("GLOBAL_QUOTE", "TIME_SERIES_WEEKLY_ADJUSTED", "TIME_SERIES_WEEKLY_ADJUSTED")


def _clasificar_rechazo_alpha(datos, funcion):
    """Traduce avisos conocidos sin reenviar texto externo ni exponer la llave."""
    aviso = str(datos.get("Note") or datos.get("Information") or "").lower()
    prefijo = f"Alpha Vantage rechazó {funcion}"
    if "demo" in aviso and "api key" in aviso:
        return f"{prefijo}: la llave configurada es DEMO, no una llave personal"
    if "25" in aviso and ("request" in aviso or "solicitud" in aviso):
        return f"{prefijo}: cuota diaria de 25 solicitudes agotada"
    if "rate limit" in aviso or "frequency" in aviso or "frecuencia" in aviso:
        return f"{prefijo}: límite temporal de frecuencia alcanzado"
    if "premium" in aviso or "subscribe" in aviso or "suscri" in aviso:
        return f"{prefijo}: la respuesta solicita una suscripción o permiso adicional"
    if "api key" in aviso or "apikey" in aviso:
        return f"{prefijo}: llave inválida, inactiva o no reconocida"
    return f"{prefijo}: motivo no identificado por la respuesta segura"


def _consultar_alpha(funcion, ticker):
    """Consulta una función permitida sin exponer la llave en mensajes o evidencias."""
    if funcion not in {"GLOBAL_QUOTE", "TIME_SERIES_WEEKLY_ADJUSTED"}:
        raise DatosExternosError("función de Alpha Vantage no permitida")
    try:
        respuesta = requests.get(
            "https://www.alphavantage.co/query",
            params={"function": funcion, "symbol": ticker, "apikey": config.ALPHAVANTAGE_API_KEY},
            timeout=30,
        )
        respuesta.raise_for_status()
        datos = respuesta.json()
    except (requests.RequestException, ValueError) as error:
        raise DatosExternosError("Alpha Vantage no respondió con datos válidos") from error
    if not isinstance(datos, dict):
        raise DatosExternosError("respuesta inesperada de Alpha Vantage")
    if datos.get("Note") or datos.get("Information"):
        raise DatosExternosError(_clasificar_rechazo_alpha(datos, funcion))
    if datos.get("Error Message"):
        raise DatosExternosError(f"Alpha Vantage no reconoce el ticker {ticker}")
    return datos


def _serie_desde_alpha(datos, incluir_rango):
    bruto = datos.get("Weekly Adjusted Time Series")
    if not isinstance(bruto, dict):
        raise DatosExternosError("Alpha Vantage no entregó la serie semanal ajustada")
    filas = []
    for fecha, valores in sorted(bruto.items())[-105:]:
        if not isinstance(valores, dict):
            raise DatosExternosError("fila semanal no válida en Alpha Vantage")
        cierre_ajustado = a_numero(valores.get("5. adjusted close"))
        fila = {"fecha": fecha, "cierre_ajustado": cierre_ajustado}
        if incluir_rango:
            cierre = a_numero(valores.get("4. close"))
            maximo = a_numero(valores.get("2. high"))
            minimo = a_numero(valores.get("3. low"))
            if None in (cierre_ajustado, cierre, maximo, minimo) or cierre <= 0:
                raise DatosExternosError("fila semanal incompleta en Alpha Vantage")
            factor_ajuste = cierre_ajustado / cierre
            fila.update({"maximo": maximo * factor_ajuste, "minimo": minimo * factor_ajuste})
        filas.append(fila)
    return filas


def obtener_ficha_alpha(ticker):
    """Iris obtiene tres respuestas gratuitas y Python las convierte al contrato interno."""
    cotizacion = _consultar_alpha("GLOBAL_QUOTE", ticker)
    serie_accion = _consultar_alpha("TIME_SERIES_WEEKLY_ADJUSTED", ticker)
    serie_spy = _consultar_alpha("TIME_SERIES_WEEKLY_ADJUSTED", "SPY")
    quote = cotizacion.get("Global Quote")
    if not isinstance(quote, dict) or not quote:
        raise DatosExternosError("Alpha Vantage no entregó la cotización solicitada")
    ficha = {
        "ticker": quote.get("01. symbol") or ticker,
        "precio": quote.get("05. price"),
        "cambio_pct": quote.get("10. change percent"),
        "fecha_dato": quote.get("07. latest trading day"),
        "serie_semanal_accion": _serie_desde_alpha(serie_accion, incluir_rango=True),
        "serie_semanal_spy": _serie_desde_alpha(serie_spy, incluir_rango=False),
    }
    ficha = validar_ficha(ficha, ticker)
    ficha["fuente"] = "Alpha Vantage API"
    return ficha

def ficha_demo(ticker, motivo):
    inicio = date(2024, 10, 18)
    accion, spy = [], []
    precio_accion, precio_spy = 130.0, 500.0
    for i in range(105):
        retorno_spy = 0.0018 + 0.010 * math.sin(i * 0.63)
        retorno_accion = 0.0014 + 1.08 * retorno_spy + 0.018 * math.sin(i * 1.71)
        precio_spy *= 1 + retorno_spy
        precio_accion *= 1 + retorno_accion
        fecha = (inicio + timedelta(days=7 * i)).isoformat()
        spy.append({"fecha": fecha, "cierre_ajustado": round(precio_spy, 4)})
        accion.append({"fecha": fecha, "cierre_ajustado": round(precio_accion, 4),
                       "maximo": round(precio_accion * 1.025, 4),
                       "minimo": round(precio_accion * 0.975, 4)})
    escala = 150.0 / accion[-1]["cierre_ajustado"]
    for fila in accion:
        for campo in ("cierre_ajustado", "maximo", "minimo"):
            fila[campo] = round(fila[campo] * escala, 4)
    ficha = {"ticker": ticker, "precio": 150.0, "cambio_pct": 1.2,
             "fecha_dato": "dato ficticio", "serie_semanal_accion": accion,
             "serie_semanal_spy": spy}
    ficha["fuente"] = f"DATOS DEMO, no son reales ({motivo})"
    return ficha


def agente_recolector(ticker):
    """Devuelve (ficha, consultas_usadas). Nunca sustituye una falla real por datos ficticios."""
    if config.MODO_SIMULACION:
        return ficha_demo(ticker, "modo simulación"), []
    return obtener_ficha_alpha(ticker), list(CONSULTAS_ALPHA)


def resumen_ficha(ficha):
    """Evita enviar cientos de filas a OpenAI cuando los indicadores ya están calculados."""
    return {campo: ficha.get(campo) for campo in ("ticker", "precio", "cambio_pct", "fecha_dato", "fuente")}


# ----------------------------------------------------------------------
# EULER · Analista Financiero (Agente 2)
# ----------------------------------------------------------------------
def calcular_indicadores(ficha):
    """Cálculos deterministas (la IA no hace aritmética)."""
    precio = a_numero(ficha.get("precio"))
    accion = ficha.get("serie_semanal_accion") or []
    spy = ficha.get("serie_semanal_spy") or []
    ultimas_52 = accion[-52:]
    maximo = max((a_numero(f.get("maximo")) for f in ultimas_52), default=None)
    minimo = min((a_numero(f.get("minimo")) for f in ultimas_52), default=None)

    def rendimiento(semanas):
        if len(accion) <= semanas:
            return None
        cierre_actual = a_numero(accion[-1].get("cierre_ajustado"))
        base = a_numero(accion[-(semanas + 1)].get("cierre_ajustado"))
        return None if cierre_actual is None or base in (None, 0) else round((cierre_actual / base - 1) * 100, 1)

    por_fecha_accion = {f["fecha"]: a_numero(f.get("cierre_ajustado")) for f in accion}
    por_fecha_spy = {f["fecha"]: a_numero(f.get("cierre_ajustado")) for f in spy}
    comunes = sorted(set(por_fecha_accion) & set(por_fecha_spy))[-105:]
    retornos_accion, retornos_spy = [], []
    for anterior, actual in zip(comunes, comunes[1:]):
        a0, a1 = por_fecha_accion[anterior], por_fecha_accion[actual]
        s0, s1 = por_fecha_spy[anterior], por_fecha_spy[actual]
        if None not in (a0, a1, s0, s1) and a0 > 0 and s0 > 0:
            retornos_accion.append(a1 / a0 - 1)
            retornos_spy.append(s1 / s0 - 1)

    beta = volatilidad = None
    if len(retornos_accion) >= 52:
        var_spy = statistics.variance(retornos_spy)
        if var_spy > 0:
            beta = round(statistics.covariance(retornos_accion, retornos_spy) / var_spy, 2)
        volatilidad = round(statistics.stdev(retornos_accion) * math.sqrt(52) * 100, 1)

    # Posición en el rango de 52 semanas: (P - min) / (max - min) × 100
    posicion = None
    if None not in (precio, maximo, minimo) and maximo > minimo:
        posicion = round((precio - minimo) / (maximo - minimo) * 100, 1)

    distancia_maximo = None
    if precio is not None and maximo not in (None, 0):
        distancia_maximo = round((precio / maximo - 1) * 100, 1)

    avance_minimo = None
    if precio is not None and minimo not in (None, 0):
        avance_minimo = round((precio / minimo - 1) * 100, 1)

    recuperacion_maximo = None
    if precio not in (None, 0) and maximo is not None:
        recuperacion_maximo = round((maximo / precio - 1) * 100, 1)

    if posicion is None:
        zona = "sin posición disponible"
    elif posicion < 0 or posicion > 100:
        zona = "fuera del rango informado; verificar fechas"
    elif posicion <= 20:
        zona = "cerca del mínimo"
    elif posicion <= 40:
        zona = "zona baja"
    elif posicion <= 60:
        zona = "zona media"
    elif posicion <= 80:
        zona = "zona alta"
    else:
        zona = "cerca del máximo"

    # Semáforo de beta (umbrales didácticos, no normativos)
    if beta is None:
        semaforo = "⚪ sin dato de beta"
    elif beta < 0.8:
        semaforo = "🟢 sensibilidad menor que SPY"
    elif beta <= 1.2:
        semaforo = "🟡 sensibilidad similar a SPY"
    else:
        semaforo = "🔴 sensibilidad mayor que SPY"

    return {"min_52s": minimo, "max_52s": maximo,
            "posicion_rango_52s_pct": posicion, "zona_rango_52s": zona,
            "distancia_max_52s_pct": distancia_maximo,
            "avance_desde_min_52s_pct": avance_minimo,
            "recuperacion_hasta_max_52s_pct": recuperacion_maximo,
            "semaforo_beta": semaforo,
            "beta": beta, "volatilidad_anualizada_pct": volatilidad,
            "rendimiento_1m_pct": rendimiento(4), "rendimiento_3m_pct": rendimiento(13),
            "rendimiento_12m_pct": rendimiento(52),
            "semanas_beta": len(retornos_accion),
            "cambio_pct": a_numero(ficha.get("cambio_pct"))}


PROMPT_ANALISTA = """Eres Euler, el Analista Financiero (Agente 2).
Recibes una ficha de Iris y los indicadores calculados por Python.
Tu personalidad es prudente, analítica y metodológicamente estricta.
Reglas:
- No recalcules, corrijas ni cambies cifras.
- Distingue dato, interpretación y limitación.
- Relaciona el cambio de la última sesión con la posición en el rango de 52 semanas.
- Una observación diaria no confirma una tendencia.
- La beta representa sensibilidad histórica frente al mercado; no mide el riesgo total ni predice pérdidas.
- La beta fue estimada por Python frente a SPY; no la presentes como un dato provisto por Alpha Vantage.
- La volatilidad histórica no predice pérdidas ni rendimientos futuros.
- No infieras causalidad ni uses lenguaje de compra, venta u oportunidad.
- Si faltan datos, declara la limitación y usa exclusivamente la información recibida.
- Describe la posición actual con “se ubica”; evita “se mantiene”, porque una posición no demuestra permanencia.
- Para la pregunta de seguimiento usa “rendimiento de los últimos 12 meses”, no “avance anual”.
El hallazgo principal debe explicar la posición dentro del rango de 52 semanas en una frase,
ser verificable y no repetir el cambio de la sesión, la beta ni una advertencia genérica sobre tendencias.
Responde SOLO con JSON con las claves:
  hallazgo_principal, lectura_riesgo, dato_pendiente, pregunta_para_investigar"""


def lectura_simulada(ind, ficha=None):
    pos = ind["posicion_rango_52s_pct"]
    r3, r12 = ind["rendimiento_3m_pct"], ind["rendimiento_12m_pct"]
    if pos is None or r3 is None or r12 is None:
        hallazgo = "No hay datos suficientes para ubicar la acción y evaluar su trayectoria histórica."
    else:
        sujeto = (ficha or {}).get("ticker") or "La acción"
        ubicacion = {"zona baja": "en la zona baja", "zona media": "en la zona media",
                     "zona alta": "en la zona alta"}.get(ind["zona_rango_52s"], ind["zona_rango_52s"])
        if pos == 50:
            ubicacion = "a mitad"
        direccion = ("rendimientos positivos" if r3 > 0 and r12 > 0 else
                     "rendimientos negativos" if r3 < 0 and r12 < 0 else "una trayectoria mixta")
        hallazgo = f"{sujeto} se ubica {ubicacion} de su rango anual y registra {direccion} a 3 y 12 meses."
    beta = ind["beta"]
    if beta is None:
        lectura_riesgo = "Sensibilidad frente a SPY: no evaluable."
    elif beta < 0.8:
        lectura_riesgo = "Sensibilidad menor que SPY (estimación propia)."
    elif beta <= 1.2:
        lectura_riesgo = "Sensibilidad similar a SPY (estimación propia)."
    else:
        lectura_riesgo = "Sensibilidad mayor que SPY (estimación propia)."
    return {
        "hallazgo_principal": hallazgo,
        "lectura_riesgo": lectura_riesgo,
        "dato_pendiente": "Los datos gratuitos no incluyen utilidades ni flujo de efectivo.",
        "pregunta_para_investigar": ("¿El rendimiento de los últimos 12 meses coincide con una mejora "
                                      "en utilidades y flujo de efectivo?"),
    }


def agente_analista(ficha):
    indicadores = calcular_indicadores(ficha)
    if config.MODO_SIMULACION or str(ficha.get("fuente", "")).startswith("DATOS DEMO"):
        lectura = lectura_simulada(indicadores, ficha)
    else:
        entrada = json.dumps({"ficha": resumen_ficha(ficha), "indicadores": indicadores}, ensure_ascii=False)
        texto = llamar_openai(PROMPT_ANALISTA, entrada)
        try:
            lectura = extraer_json(texto)
        except ValueError:
            lectura = {
                "hallazgo_principal": texto[:300],
                "lectura_riesgo": "No disponible por respuesta no estructurada.",
                "dato_pendiente": "Revisar la respuesta de Euler.",
                "pregunta_para_investigar": "¿Qué datos faltan para completar el análisis?",
            }
    return {"ficha": ficha, "indicadores": indicadores, "lectura": lectura}


# ----------------------------------------------------------------------
# VERA · Editora Financiera (Agente 3)
# ----------------------------------------------------------------------
PROMPT_COMUNICADOR = f"""Eres Vera, la Editora Financiera (Agente 3).
Recibes la ficha, los indicadores calculados por Python y la interpretación de Euler.
Tu personalidad es clara, selectiva, serena y orientada a comunicación financiera.
Tu tarea es editar únicamente el hallazgo principal y la pregunta para profundizar.
Reglas:
- Conserva exactamente las cifras y el significado recibidos. No calcules ni agregues información externa.
- No inventes datos faltantes ni cambies el significado del hallazgo de Euler.
- No repitas la beta dentro del hallazgo principal.
- No agregues al hallazgo una advertencia genérica sobre tendencias.
- No uses lenguaje alarmista ni “comprar”, “vender”, “oportunidad” o “inversión segura”.
- Una oración por campo; máximo 220 caracteres para el hallazgo y 180 para la pregunta.
- No redactes encabezados, modalidad, cifras de precio, riesgo, fuente ni descargo: Python los añadirá.
Responde SOLO con JSON con las claves: hallazgo_principal, pregunta_para_investigar."""


def formatear_capitalizacion(valor):
    numero = a_numero(valor)
    if numero is None:
        return "no disponible"
    return f"{numero / 1_000_000_000:,.0f} mil millones USD"


def formatear_numero(valor, decimales=1):
    numero = a_numero(valor)
    return "no disponible" if numero is None else f"{numero:.{decimales}f}"


def formatear_porcentaje(valor, decimales=2):
    numero = a_numero(valor)
    return "no disponible" if numero is None else f"{numero:+.{decimales}f} %"


def _texto_editorial(valor, respaldo, limite):
    """Acepta sólo una frase breve; ante una salida dudosa conserva el texto validado de Euler."""
    if not isinstance(valor, str):
        return respaldo
    texto = " ".join(valor.split()).strip()
    if not texto or len(texto) > limite or PATRONES_INYECCION.search(texto):
        return respaldo
    if "modalidad no disponible" in texto.lower():
        return respaldo
    numeros_nuevos = set(re.findall(r"\d+(?:[.,]\d+)?", texto))
    numeros_validos = set(re.findall(r"\d+(?:[.,]\d+)?", respaldo))
    if not numeros_nuevos.issubset(numeros_validos):
        return respaldo
    return texto


def nota_estructurada(analisis, edicion=None):
    f, ind, lec = analisis["ficha"], analisis["indicadores"], analisis["lectura"]
    simulada = str(f.get("fuente", "")).startswith("DATOS DEMO")
    modalidad = "⚠️ SIMULACIÓN · Datos ficticios" if simulada else "✅ DATOS REALES"
    fecha_fuente = ("🕒 Dato ficticio | Fuente: simulación local" if simulada else
                    f"🕒 {f.get('fecha_dato') or 'Fecha no disponible'} | Fuente: {f.get('fuente') or 'no disponible'}")
    edicion = edicion or {}
    hallazgo = _texto_editorial(edicion.get("hallazgo_principal"), lec["hallazgo_principal"], 220)
    pregunta = _texto_editorial(edicion.get("pregunta_para_investigar"), lec["pregunta_para_investigar"], 180)
    return (f"{FIRMA_VERA}\n"
            f"{modalidad}\n\n"
            f"📊 {f['ticker']} | Precio, trayectoria y riesgo\n"
            f"💵 Cierre: {formatear_numero(f.get('precio'), 2)} USD | "
            f"Día: {formatear_porcentaje(ind.get('cambio_pct'))}\n\n"
            f"💡 Hallazgo principal\n{hallazgo}\n\n"
            "📍 Rango de 52 semanas (mínimo–máximo)\n"
            f"{formatear_numero(ind.get('min_52s'), 2)}–{formatear_numero(ind.get('max_52s'), 2)} USD | "
            f"Posición: {formatear_numero(ind.get('posicion_rango_52s_pct'))} %\n\n"
            "📈 Rendimiento ajustado\n"
            f"1 mes: {formatear_porcentaje(ind.get('rendimiento_1m_pct'), 1)} | "
            f"3 meses: {formatear_porcentaje(ind.get('rendimiento_3m_pct'), 1)} | "
            f"12 meses: {formatear_porcentaje(ind.get('rendimiento_12m_pct'), 1)}\n\n"
            "⚖️ Riesgo histórico\n"
            f"{ind['semaforo_beta'].split()[0]} Beta: {formatear_numero(ind.get('beta'), 2)} | {lec['lectura_riesgo']}\n"
            f"Volatilidad anualizada: {formatear_numero(ind.get('volatilidad_anualizada_pct'))} %\n\n"
            f"🔎 Para profundizar\n{pregunta}\n\n"
            f"{fecha_fuente}\n\n{DESCARGO}")


def nota_simulada(analisis):
    return nota_estructurada(analisis)


def agente_comunicador(analisis):
    if config.MODO_SIMULACION or str(analisis["ficha"].get("fuente", "")).startswith("DATOS DEMO"):
        return nota_simulada(analisis)
    entrada = {"ticker": analisis["ficha"].get("ticker"), "lectura": analisis["lectura"]}
    texto = llamar_openai(PROMPT_COMUNICADOR, json.dumps(entrada, ensure_ascii=False), max_tokens=220)
    try:
        edicion = extraer_json(texto)
    except (ValueError, json.JSONDecodeError):
        edicion = {}
    return nota_estructurada(analisis, edicion)
