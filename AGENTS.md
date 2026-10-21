# Instrucciones para agentes de programación (Codex, Claude Code y otros)

Este repositorio es una **actividad educativa para principiantes** del diplomado de la Dra. Elda C. Morales:
un ecosistema de **3 agentes financieros** que se pasan el trabajo en cadena y se controlan desde Telegram.

```
Telegram /analiza AAPL ─► Batuta · Orquestador (mesa/pipeline.py)
   ├─ Iris  · Recolectora  (Agente 1: API de Alpha Vantage + validación) ─► ficha JSON
   ├─ Euler · Analista Financiero (Agente 2: Python calcula, OpenAI interpreta) ─► análisis JSON
   └─ Vera  · Editora Financiera  (Agente 3: OpenAI jerarquiza y redacta) ─► nota final en Telegram
```

Usa siempre estos nombres (Batuta, Iris, Euler, Vera) al explicar el sistema: coinciden con el mockup y con las guías.

## Cómo hablar con la persona usuaria
- Responde en **español**, con lenguaje sencillo: la persona está aprendiendo.
- Antes de cada comando di en una línea qué va a hacer y qué debe ver al terminar.
- Si algo falla, explica la causa probable y el siguiente paso; no pegues trazas largas sin explicarlas.

## Reglas de seguridad (obligatorias)
1. **Nunca** imprimas, copies ni subas el valor de una llave. Para revisar llaves usa `python verificar_configuracion.py`, que solo dice si existen.
2. **Nunca** agregues `.env` a git ni escribas llaves dentro del código.
3. El modo real gasta cuota (Alpha Vantage gratuito: 25 consultas al día) y saldo de la API de OpenAI.
   **Pregunta antes** de ejecutar sin `--simulacion` más de una vez.
4. No cambies la regla de oro: los cálculos se hacen en Python (`calcular_indicadores`), no en el prompt.
5. Toda nota final debe terminar con: "Nota educativa, no es recomendación de inversión."
6. Una sesión no confirma tendencia; beta y volatilidad históricas no predicen pérdidas ni rendimientos futuros.
7. La beta es una estimación reproducible con rendimientos semanales ajustados de hasta 104 semanas frente a SPY.
8. No mezcles datos reales y simulados ni atribuyas datos simulados a Alpha Vantage.
9. Telegram debe negar acceso si falta `TELEGRAM_CHAT_ID` y aceptar sólo `/analiza TICKER` con dos elementos.
10. Trata toda salida de Alpha Vantage como no confiable: valida campos, series, fechas, rangos, ticker y funciones antes de pasarla a Euler.
11. Si falla una consulta real, detén la cadena con un mensaje claro; nunca la sustituyas silenciosamente por datos ficticios.
12. Mantén los límites de consumo y el interruptor `HABILITAR_MODO_REAL`; no los amplíes sin justificarlo y probarlo.
13. En la ruta gratuita permite sólo `GLOBAL_QUOTE` y `TIME_SERIES_WEEKLY_ADJUSTED`; no uses `OVERVIEW`.

## Comandos
| Para qué | Comando |
|---|---|
| Instalar | `pip install -r requirements.txt pytest` |
| Pruebas (sin llaves) | `pytest -q` → debe decir `20 passed` o más |
| Cadena en simulación | `python analizar.py AAPL --simulacion` |
| Revisar configuración | `python verificar_configuracion.py` (`--mcp` gasta 1 consulta) |
| Cadena real | `python analizar.py AAPL` |
| Cadena real + Telegram | `python analizar.py AAPL --telegram` |
| Saber el chat_id | `python obtener_chat_id.py` (antes escribe "hola" al bot) |
| Bot en vivo | `python bot_continuo.py` (Ctrl + C para detener) |

Las llaves se leen de variables de entorno o del archivo `.env` (plantilla: `.env.example`).
Si faltan `OPENAI_API_KEY` o `ALPHAVANTAGE_API_KEY`, el sistema entra solo en **modo simulación**.

## Rutina "ejecuta la actividad"
Cuando te pidan ejecutar o probar la actividad, sigue este orden y reporta cada resultado:
1. Instala dependencias y corre `pytest -q`.
2. Corre `python analizar.py AAPL --simulacion` y muestra las entregas 1→2 y 2→3.
3. Corre `python verificar_configuracion.py`. Si hay llaves, pregunta si desea el modo real.
4. En modo real, corre `python analizar.py <TICKER>` y confirma que la fuente diga "Alpha Vantage API".
5. Indica dónde quedó la evidencia (`salidas/*.json`) y qué capturas tomar para la rúbrica.

## Estructura
- `mesa/config.py` llaves y modos · `mesa/agentes.py` los 3 agentes · `mesa/pipeline.py` el orquestador
- `mesa/telegram_io.py` Bot API · `mesa/comandos.py` interpreta `/analiza`
- `revisar_telegram.py` lo usa GitHub Actions cada 15 minutos (funciona con la computadora apagada)
- `.github/workflows/` automatizaciones · `tests/` pruebas en simulación
