"""Los tres agentes de la Mesa Financiera.

  Iris  · La Recolectora  (Agente 1) → consulta Alpha Vantage por MCP y entrega una FICHA (JSON)
  Euler · Analista Financiero (Agente 2) → recibe la ficha, Python calcula y OpenAI interpreta → ANÁLISIS (JSON)
  Vera  · Editora Financiera  (Agente 3) → recibe el análisis y OpenAI redacta la NOTA final para Telegram
  (Batuta, el orquestador que los dirige, vive en mesa/pipeline.py)

Regla de oro: los números los calcula el código; la IA solo interpreta.
"""
import json

from . import config

DESCARGO = "No constituye una recomendación de inversión."
FIRMA_VERA = "✍️ Vera | Mesa Financiera"

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


def llamar_openai(system, mensaje, usar_mcp=False, max_tokens=900):
    """Envía un mensaje con la Responses API. Devuelve texto y herramientas MCP usadas."""
    base = dict(model=config.MODELO, max_output_tokens=max_tokens, instructions=system,
                input=mensaje, store=False)
    cliente = _cliente_openai()
    if usar_mcp:
        respuesta = cliente.responses.create(
            **base,
            tools=[{
                "type": "mcp",
                "server_label": "alphavantage",
                "server_url": f"https://mcp.alphavantage.co/mcp?apikey={config.ALPHAVANTAGE_API_KEY}",
                "require_approval": "never",
            }],
        )
    else:
        respuesta = cliente.responses.create(**base)
    texto = respuesta.output_text.strip()
    herramientas = [getattr(item, "name", "alphavantage") for item in respuesta.output
                     if getattr(item, "type", "") == "mcp_call"]
    return texto, herramientas


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


# ----------------------------------------------------------------------
# IRIS · La Recolectora (Agente 1)
# ----------------------------------------------------------------------
PROMPT_RECOLECTOR = """Eres Iris, la Recolectora (Agente 1) de una mesa financiera educativa.
Tu personalidad: curiosa y meticulosa; jamás inventas un dato.
Tarea: obtener datos REALES de la acción indicada con las herramientas de Alpha Vantage.
Reglas:
- Haz como máximo 2 consultas: cotización actual y datos generales de la empresa.
- NUNCA inventes cifras. Si un dato no está disponible, escribe null.
- Conserva la fecha informada por la fuente.
- No combines datos reales con datos simulados.
- No calcules, interpretes ni emitas recomendaciones.
- Responde SOLO con un JSON con estas claves exactas:
  ticker, nombre, sector, precio, cambio_pct, fecha_dato, pe_ratio, beta,
  max_52s, min_52s, cap_mercado_usd"""

DATOS_DEMO = {
    "nombre": "Empresa ficticia (simulación)", "sector": "Tecnología",
    "precio": 150.0, "cambio_pct": 1.2, "fecha_dato": "dato ficticio",
    "pe_ratio": 28.0, "beta": 1.25, "max_52s": 180.0, "min_52s": 120.0,
    "cap_mercado_usd": 2400000000000,
}


def ficha_demo(ticker, motivo):
    ficha = {"ticker": ticker, **DATOS_DEMO}
    ficha["fuente"] = f"DATOS DEMO, no son reales ({motivo})"
    return ficha


def agente_recolector(ticker):
    """Devuelve (ficha, herramientas_usadas)."""
    if config.MODO_SIMULACION:
        return ficha_demo(ticker, "modo simulación"), []
    try:
        texto, herramientas = llamar_openai(PROMPT_RECOLECTOR, f"Acción: {ticker}", usar_mcp=True)
        ficha = extraer_json(texto)
        ficha["ticker"] = ticker
        ficha["fuente"] = "Alpha Vantage vía MCP"
        return ficha, herramientas
    except Exception as error:                     # MCP caído, cuota agotada o JSON inválido
        return ficha_demo(ticker, f"MCP no disponible: {type(error).__name__}"), []


# ----------------------------------------------------------------------
# EULER · Analista Financiero (Agente 2)
# ----------------------------------------------------------------------
def calcular_indicadores(ficha):
    """Cálculos deterministas (la IA no hace aritmética)."""
    precio, maximo, minimo = (a_numero(ficha.get(k)) for k in ("precio", "max_52s", "min_52s"))
    beta, pe = a_numero(ficha.get("beta")), a_numero(ficha.get("pe_ratio"))

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
        semaforo = "🟢 volatilidad baja"
    elif beta <= 1.2:
        semaforo = "🟡 volatilidad similar al mercado"
    else:
        semaforo = "🔴 volatilidad alta"

    return {"posicion_rango_52s_pct": posicion, "zona_rango_52s": zona,
            "distancia_max_52s_pct": distancia_maximo,
            "avance_desde_min_52s_pct": avance_minimo,
            "recuperacion_hasta_max_52s_pct": recuperacion_maximo,
            "semaforo_beta": semaforo,
            "beta": beta, "pe_ratio": pe, "cambio_pct": a_numero(ficha.get("cambio_pct"))}


PROMPT_ANALISTA = """Eres Euler, el Analista Financiero (Agente 2).
Recibes una ficha de Iris y los indicadores calculados por Python.
Tu personalidad es prudente, analítica y metodológicamente estricta.
Reglas:
- No recalcules, corrijas ni cambies cifras.
- Distingue dato, interpretación y limitación.
- Relaciona el cambio de la última sesión con la posición en el rango de 52 semanas.
- Una observación diaria no confirma una tendencia.
- La beta representa sensibilidad histórica frente al mercado; no mide el riesgo total ni predice pérdidas.
- El P/E no permite afirmar que una acción está cara o barata sin comparables adecuados.
- La capitalización describe tamaño; no demuestra seguridad, calidad ni rentabilidad.
- No infieras causalidad ni uses lenguaje de compra, venta u oportunidad.
- Si faltan datos, declara la limitación y usa exclusivamente la información recibida.
El hallazgo principal debe explicar la situación en una o dos frases, combinar el movimiento de la última
sesión con el contexto de 52 semanas, ser verificable y no repetir la beta ni el P/E.
Responde SOLO con JSON con las claves:
  hallazgo_principal, lectura_riesgo, lectura_valuacion,
  dato_pendiente, pregunta_para_investigar"""


def lectura_simulada(ind, ficha=None):
    pos = ind["posicion_rango_52s_pct"]
    cambio = ind["cambio_pct"]
    distancia = ind["distancia_max_52s_pct"]
    if pos is None or cambio is None:
        hallazgo = "No hay datos suficientes para relacionar el movimiento reciente con el rango de 52 semanas."
    else:
        verbo = "avanzó" if cambio > 0 else "cayó" if cambio < 0 else "no cambió"
        magnitud = abs(cambio)
        distancia_texto = (f" y {abs(distancia):.1f} % por debajo del máximo" if distancia is not None and distancia <= 0
                           else "")
        sujeto = (ficha or {}).get("ticker") or "La acción"
        ubicacion = "a mitad" if pos == 50 else f"en la {ind['zona_rango_52s']}"
        hallazgo = (f"{sujeto} {verbo} {magnitud:.2f} % en la última sesión, pero se mantiene "
                     f"{ubicacion} de su rango de 52 semanas{distancia_texto}. "
                     "Este movimiento aislado no permite confirmar una tendencia.")
    beta = ind["beta"]
    if beta is None:
        lectura_riesgo = "No hay beta disponible para describir su sensibilidad histórica frente al mercado."
    elif beta < 0.8:
        lectura_riesgo = "Menor sensibilidad histórica frente al mercado; no representa por sí sola el riesgo total."
    elif beta <= 1.2:
        lectura_riesgo = "Sensibilidad histórica similar al mercado; no representa por sí sola el riesgo total."
    else:
        lectura_riesgo = "Mayor sensibilidad histórica frente al mercado; no representa por sí sola el riesgo total."
    pe = ind["pe_ratio"]
    lectura_valuacion = ("No hay P/E disponible para esta lectura." if pe is None else
                         f"El precio representa {pe:.1f} veces las utilidades por acción consideradas por la fuente. "
                         "Requiere comparación con empresas similares.")
    return {
        "hallazgo_principal": hallazgo,
        "lectura_riesgo": lectura_riesgo,
        "lectura_valuacion": lectura_valuacion,
        "dato_pendiente": "Comparar la valuación con empresas de tamaño y actividad similares.",
        "pregunta_para_investigar": "¿Cómo se compara su P/E con empresas del mismo sector, tamaño y actividad?",
    }


def agente_analista(ficha):
    indicadores = calcular_indicadores(ficha)
    if config.MODO_SIMULACION or str(ficha.get("fuente", "")).startswith("DATOS DEMO"):
        lectura = lectura_simulada(indicadores, ficha)
    else:
        entrada = json.dumps({"ficha": ficha, "indicadores": indicadores}, ensure_ascii=False)
        texto, _ = llamar_openai(PROMPT_ANALISTA, entrada)
        try:
            lectura = extraer_json(texto)
        except ValueError:
            lectura = {
                "hallazgo_principal": texto[:300],
                "lectura_riesgo": "No disponible por respuesta no estructurada.",
                "lectura_valuacion": "No disponible por respuesta no estructurada.",
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
Redacta una nota para Telegram con: identificación y modalidad; precio y cambio de la última sesión;
hallazgo principal; contexto de 52 semanas; riesgo; perfil y valuación; pregunta; fecha, fuente y descargo.
Reglas:
- Conserva exactamente las cifras recibidas. No calcules ni agregues información externa.
- No inventes datos faltantes ni cambies el significado del hallazgo de Euler.
- No repitas la beta ni el P/E dentro del hallazgo principal.
- No presentes un movimiento diario como tendencia ni la beta como riesgo total o probabilidad de pérdida.
- No califiques el P/E como alto, bajo, caro o barato sin comparables.
- No interpretes la capitalización como seguridad o calidad.
- No uses lenguaje alarmista ni “comprar”, “vender”, “oportunidad” o “inversión segura”.
- Si la fuente es simulada, indícalo claramente. Usa “Alpha Vantage vía MCP” sólo si la consulta real tuvo éxito.
- Omite campos no disponibles o identifícalos como no disponibles.
- Entrega texto plano, sin Markdown, con un máximo de 1,300 caracteres.
- Cierra SIEMPRE con esta frase exacta: {DESCARGO}"""


def formatear_capitalizacion(valor):
    numero = a_numero(valor)
    if numero is None:
        return "no disponible"
    return f"USD {numero / 1_000_000_000:,.0f} mil millones"


def formatear_numero(valor, decimales=1):
    numero = a_numero(valor)
    return "no disponible" if numero is None else f"{numero:.{decimales}f}"


def formatear_porcentaje(valor, decimales=2):
    numero = a_numero(valor)
    return "no disponible" if numero is None else f"{numero:+.{decimales}f} %"


def nota_simulada(analisis):
    f, ind, lec = analisis["ficha"], analisis["indicadores"], analisis["lectura"]
    fecha_fuente = ("🕒 Dato ficticio | Fuente: simulación local" if str(f.get("fuente", "")).startswith("DATOS DEMO")
                    else f"🕒 Dato: {f.get('fecha_dato') or 'no disponible'} | Fuente: {f.get('fuente') or 'no disponible'}")
    return (f"{FIRMA_VERA}\n"
            "⚠️ SIMULACIÓN · Datos ficticios\n\n"
            f"📊 {f['ticker']} | Precio, riesgo y valuación\n"
            f"💵 Precio: USD {formatear_numero(f.get('precio'), 2)} | Cambio última sesión: "
            f"{formatear_porcentaje(ind.get('cambio_pct'))}\n\n"
            f"💡 Hallazgo principal\n{lec['hallazgo_principal']}\n\n"
            "📍 Contexto de 52 semanas\n"
            f"• Mínimo: USD {formatear_numero(f.get('min_52s'), 2)} | Máximo: USD {formatear_numero(f.get('max_52s'), 2)}\n"
            f"• Posición en el rango: {formatear_numero(ind.get('posicion_rango_52s_pct'))} %\n\n"
            "⚖️ Riesgo\n"
            f"• Beta: {formatear_numero(ind.get('beta'), 2)} | {lec['lectura_riesgo']}\n\n"
            "🏢 Perfil y valuación\n"
            f"• Sector: {f.get('sector') or 'no disponible'} | Capitalización: {formatear_capitalizacion(f.get('cap_mercado_usd'))}\n"
            f"• P/E: {formatear_numero(ind.get('pe_ratio'))}x | {lec['lectura_valuacion']}\n\n"
            f"🔎 Para profundizar\n{lec['pregunta_para_investigar']}\n\n"
            f"{fecha_fuente}\n\nDatos simulados con fines educativos. {DESCARGO}")


def agente_comunicador(analisis):
    if config.MODO_SIMULACION or str(analisis["ficha"].get("fuente", "")).startswith("DATOS DEMO"):
        return nota_simulada(analisis)
    texto, _ = llamar_openai(PROMPT_COMUNICADOR, json.dumps(analisis, ensure_ascii=False), max_tokens=600)
    if DESCARGO not in texto:                      # garantía aunque el modelo lo olvide
        texto += f"\n\n{DESCARGO}"
    return f"{FIRMA_VERA}\n{texto}"
