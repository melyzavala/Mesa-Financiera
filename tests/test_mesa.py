"""Pruebas en modo simulación: verifican la cadena sin llaves ni internet.  Ejecutar: pytest -q"""
import json
import os

import pytest

os.environ["MODO_SIMULACION"] = "1"

from mesa import agentes, config, pipeline as pl          # noqa: E402
from mesa import comandos                                  # noqa: E402


@pytest.fixture(autouse=True)
def simulacion(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "MODO_SIMULACION", True)
    monkeypatch.setattr(config, "CARPETA_SALIDAS", str(tmp_path))


def test_formula_posicion_rango_52_semanas():
    ind = agentes.calcular_indicadores({"precio": "250.5", "max_52s": "300", "min_52s": "200", "beta": "0.7"})
    assert ind["posicion_rango_52s_pct"] == 50.5          # (250.5-200)/(300-200)*100
    assert ind["distancia_max_52s_pct"] == -16.5
    assert ind["avance_desde_min_52s_pct"] == 25.2
    assert ind["recuperacion_hasta_max_52s_pct"] == 19.8
    assert ind["zona_rango_52s"] == "zona media"
    assert ind["semaforo_beta"].startswith("🟢")


@pytest.mark.parametrize("precio, zona", [
    (110, "cerca del mínimo"), (130, "zona baja"), (150, "zona media"),
    (170, "zona alta"), (190, "cerca del máximo"),
])
def test_clasificacion_del_rango_52_semanas(precio, zona):
    ind = agentes.calcular_indicadores({"precio": precio, "min_52s": 100, "max_52s": 200})
    assert ind["zona_rango_52s"] == zona


@pytest.mark.parametrize("beta, color", [(0.5, "🟢"), (0.8, "🟡"), (1.2, "🟡"), (1.3, "🔴"), (None, "⚪")])
def test_semaforo_beta(beta, color):
    assert agentes.calcular_indicadores({"beta": beta})["semaforo_beta"].startswith(color)


def test_datos_faltantes_no_rompen_el_calculo():
    ind = agentes.calcular_indicadores({"precio": None, "max_52s": "100", "min_52s": "100"})
    assert ind["posicion_rango_52s_pct"] is None


def test_extraer_json_con_texto_alrededor():
    assert agentes.extraer_json('Aquí tienes: {"a": 1} listo')["a"] == 1
    with pytest.raises(ValueError):
        agentes.extraer_json("sin json")


@pytest.mark.parametrize("entrada, esperado", [(" aapl ", "AAPL"), ("brk.b", "BRK.B")])
def test_ticker_valido(entrada, esperado):
    assert pl.normalizar_ticker(entrada) == esperado


@pytest.mark.parametrize("entrada", ["", "AAPL; rm -rf", "ACCIONMUYLARGAXYZ"])
def test_ticker_invalido(entrada):
    with pytest.raises(ValueError):
        pl.normalizar_ticker(entrada)


def test_cadena_completa_output_es_input():
    avisos = []
    r = pl.pipeline("msft", avisar=avisos.append)
    assert r["entrega_2_analisis"]["ficha"] == r["entrega_1_ficha"]       # 1 → 2
    assert r["entrega_1_ficha"]["ticker"] in r["entrega_3_nota"]          # 2 → 3
    assert agentes.DESCARGO in r["entrega_3_nota"]
    assert any("Entrega 1→2" in a for a in avisos) and any("Entrega 2→3" in a for a in avisos)
    with open(r["archivo"], encoding="utf-8") as f:
        assert json.load(f)["ticker"] == "MSFT"


def test_mcp_caido_usa_respaldo_demo(monkeypatch):
    monkeypatch.setattr(config, "MODO_SIMULACION", False)

    def falla(*args, **kwargs):
        raise ConnectionError("sin red")
    monkeypatch.setattr(agentes, "llamar_openai", falla)
    ficha, herramientas = agentes.agente_recolector("AAPL")
    assert "DEMO" in ficha["fuente"] and herramientas == []


def test_agentes_reales_encadenan_con_openai_simulado(monkeypatch):
    """Imita las respuestas de OpenAI para revisar el camino 'real' sin gastar llaves."""
    monkeypatch.setattr(config, "MODO_SIMULACION", False)

    def openai_falso(system, mensaje, usar_mcp=False, max_tokens=900):
        if usar_mcp:
            return ('{"nombre":"IBM","sector":"Tech","precio":"250.5","cambio_pct":"-0.8%",'
                    '"pe_ratio":"40.1","beta":"0.7","max_52s":"300","min_52s":"200"}', ["GLOBAL_QUOTE"])
        if "Analista" in system:
            datos = json.loads(mensaje)
            assert datos["indicadores"]["posicion_rango_52s_pct"] == 50.5   # recibió la entrega 1
            return ('{"hallazgo_principal":"a","lectura_riesgo":"b","lectura_valuacion":"c",'
                    '"dato_pendiente":"d","pregunta_para_investigar":"e"}'), []
        assert '"hallazgo_principal": "a"' in mensaje                       # recibió la entrega 2
        return "IBM: nota sin descargo", []

    monkeypatch.setattr(agentes, "llamar_openai", openai_falso)
    r = pl.pipeline("IBM", avisar=lambda t: None)
    assert r["herramientas_mcp"] == ["GLOBAL_QUOTE"]
    assert r["entrega_1_ficha"]["fuente"] == "Alpha Vantage vía MCP"
    assert r["entrega_3_nota"].endswith(agentes.DESCARGO)                   # el descargo se garantiza


def test_bot_ignora_chats_ajenos_y_responde_ayuda(monkeypatch):
    enviados = []
    monkeypatch.setattr(comandos, "enviar", lambda chat, texto: enviados.append((chat, texto)))
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "111")
    assert comandos.atender({"chat": {"id": 999}, "text": "/analiza AAPL"}) is None
    assert enviados[-1][1] == "Este bot es privado."
    comandos.atender({"chat": {"id": 111}, "text": "hola"})
    assert "Mesa Financiera" in enviados[-1][1]
    r = comandos.atender({"chat": {"id": 111}, "text": "/analiza aapl"})
    assert r["ticker"] == "AAPL" and agentes.DESCARGO in enviados[-1][1]


def test_revision_de_github_actions_atiende_y_confirma(monkeypatch):
    """Simula la corrida de GitHub Actions: 4 mensajes pendientes, límite de 3 por revisión."""
    import revisar_telegram as rt
    pendientes = [{"update_id": i, "message": {"chat": {"id": 111}, "text": t}}
                  for i, t in enumerate(["/analiza AAPL", "hola", "/analiza MSFT", "/analiza NVDA"], start=10)]
    confirmados, enviados = [], []
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "111")
    monkeypatch.setattr(config, "MAX_ANALISIS_POR_RUN", 3)
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "token-de-prueba")
    monkeypatch.setattr(rt, "verificar_bot", lambda: "bot_prueba")
    monkeypatch.setattr(rt, "preparar_polling", lambda: None)
    monkeypatch.setattr(rt, "obtener_mensajes", lambda: pendientes)
    monkeypatch.setattr(rt, "confirmar_leidos", confirmados.append)
    monkeypatch.setattr(comandos, "enviar", lambda chat, texto: enviados.append(texto))
    rt.main()
    assert confirmados == [10, 11, 12]                      # NVDA queda para la siguiente revisión
    assert sum(agentes.DESCARGO in t for t in enviados) == 2  # AAPL y MSFT recibieron su nota


def test_revision_sin_token_termina_sin_error(monkeypatch, capsys):
    """Una copia de la plantilla sin Secrets no debe marcar error en Actions cada 10 minutos."""
    import revisar_telegram as rt
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "")
    rt.main()
    assert "nada que revisar" in capsys.readouterr().out


def test_los_agentes_se_presentan_con_su_nombre():
    """Los nombres del mockup (Batuta, Iris, Euler, Vera) aparecen en Telegram."""
    avisos = []
    r = pl.pipeline("AAPL", avisar=avisos.append)
    texto = "\n".join(avisos)
    for nombre in ("Batuta", "Iris", "Euler", "Vera"):
        assert nombre in texto
    assert r["entrega_3_nota"].startswith(agentes.FIRMA_VERA)


def test_nota_financiera_simulada_es_trazable_y_no_recomienda():
    r = pl.pipeline("AAPL", avisar=lambda t: None)
    nota = r["entrega_3_nota"]
    for texto in ("Hallazgo principal", "Contexto de 52 semanas", "Perfil y valuación",
                  "Capitalización", "Fuente: simulación local", "+1.20 %"):
        assert texto in nota
    assert "Alpha Vantage vía MCP" not in nota
    assert len(nota) <= 1300


def test_falla_mcp_no_gasta_en_euler_ni_vera(monkeypatch):
    monkeypatch.setattr(config, "MODO_SIMULACION", False)
    llamadas = []

    def openai_falso(*args, **kwargs):
        llamadas.append(kwargs.get("usar_mcp", False))
        raise ConnectionError("sin red")

    monkeypatch.setattr(agentes, "llamar_openai", openai_falso)
    r = pl.pipeline("AAPL", avisar=lambda t: None)
    assert llamadas == [True]
    assert "Fuente: simulación local" in r["entrega_3_nota"]
