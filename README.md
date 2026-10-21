# Mesa Financiera en Telegram 📊🤖

Actividad del diplomado · **Dra. Elda C. Morales**

Un ecosistema de **tres agentes de IA** que trabajan en cadena: el resultado de uno es la entrada del siguiente.
Tú das la orden desde **Telegram**, **Batuta** (el orquestador) dirige y tres especialistas hacen el trabajo:

| Agente | Personalidad | Qué hace |
|---|---|---|
| **Iris** · La Recolectora | Curiosa y meticulosa; jamás inventa un dato | Consulta y valida datos reales de Alpha Vantage |
| **Euler** · El Analista Financiero | Prudente, analítico y metodológicamente estricto | Interpreta precio, trayectoria y riesgo sin recalcular cifras |
| **Vera** · La Editora Financiera | Clara, selectiva y serena | Jerarquiza el hallazgo y redacta la nota final para Telegram |

```
Tú en Telegram: /analiza AAPL
        │
        ▼
 Batuta · Orquestador (mesa/pipeline.py)
        │
        ├─► Iris  · Recolectora ── consulta Alpha Vantage API ──────► ficha JSON
        ├─► Euler · Analista Financiero ─ Python calcula, OpenAI interpreta ─► análisis JSON
        └─► Vera  · Editora Financiera ─ jerarquiza y redacta ───────────────► mensaje en Telegram
```

## Paso cero: crea tu propia copia

👉 **[Usar esta plantilla](https://github.com/new?template_owner=eldamorales&template_name=mesa-financiera-telegram)**
(o el botón verde **Use this template → Create a new repository**). Elige tu usuario, visibilidad **Public** y pulsa *Create repository*.

Tu copia incluye todo, también la carpeta oculta `.github` con las automatizaciones. Ahí guardarás tus llaves y tus cambios.

## Elige tu ruta

| Ruta | Cómo empezar | ¿Computadora encendida? |
|---|---|---|
| **A · Google Colab** | [Abrir el notebook en Colab](https://colab.research.google.com/github/eldamorales/mesa-financiera-telegram/blob/main/notebook/Mesa_Financiera_Telegram.ipynb) | Sí, con la pestaña abierta |
| **B · GitHub Actions** | En tu copia: Settings → Secrets → Actions, y luego Actions → *mesa-financiera* → Run workflow | **No** |
| **C · Claude Code** | claude.ai/code con tu copia, o `claude` en la terminal | No, en la versión web |
| **D · Codex** | Codex en la nube o la CLI; lee `AGENTS.md` | No, en la nube |
| **E · Codespaces o clonar** | En tu copia: **Code → Codespaces → Create codespace on main** | Codespaces: no, mientras lo usas |

Las instrucciones paso a paso están en [`docs/`](docs/): Guía del estudiante y Guía del docente con rúbrica.

## Empezar en 1 minuto, sin llaves
```bash
pip install -r requirements.txt pytest
pytest -q                               # 35 passed
python analizar.py AAPL --simulacion    # la cadena completa con datos ficticios
```

## Clonar en tu computadora (Ruta E)
```bash
git clone https://github.com/TU_USUARIO/mesa-financiera-telegram.git
cd mesa-financiera-telegram
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt pytest
cp .env.example .env                                   # abre .env y pega tus llaves
```

## Llaves necesarias para el modo real
| Secreto | Dónde se obtiene |
|---|---|
| `TELEGRAM_BOT_TOKEN` | @BotFather en Telegram |
| `TELEGRAM_CHAT_ID` | `python obtener_chat_id.py` |
| `OPENAI_API_KEY` | OpenAI Platform; ya debe existir como variable o Secret |
| `ALPHAVANTAGE_API_KEY` | https://www.alphavantage.co/support/#api-key (gratis, 25 consultas al día) |

Dónde guardarlas, según la ruta: **Colab** → panel 🔑 · **Actions** → Settings → Secrets and variables → Actions ·
**Codespaces** → tu perfil → Settings → Codespaces → Codespaces secrets · **Tu computadora** → archivo `.env`.
Nunca las escribas en el código ni las subas a GitHub.

Iris consulta directamente la API de Alpha Vantage y utiliza únicamente `GLOBAL_QUOTE` y
`TIME_SERIES_WEEKLY_ADJUSTED`: una consulta de
cotización, una serie para la acción y una serie de SPY. Python calcula el rango anual,
los rendimientos ajustados, la volatilidad y una beta de 104 semanas frente a SPY.
No se solicitan `OVERVIEW`, P/E, sector ni capitalización porque ese endpoint es premium.

Los datos se validan antes de llamar a OpenAI. Si Alpha Vantage falla o agota su cuota, la
ejecución informa el problema y se detiene: nunca reemplaza una consulta real por simulación.
Euler y Vera reciben sólo la ficha compacta y los indicadores calculados para reducir tokens.

## Seguridad y control de consumo

- El bot se cierra si falta `TELEGRAM_CHAT_ID`; no acepta chats desconocidos por defecto.
- Telegram acepta únicamente el formato exacto `/analiza TICKER`.
- Iris trata la respuesta de Alpha Vantage como datos no confiables, limita las funciones previstas y valida la ficha antes de entregarla a Euler.
- Cada ejecución procesa como máximo 3 análisis. Un ticker repetido espera 60 segundos dentro del mismo proceso.
- `HABILITAR_MODO_REAL=0` funciona como interruptor de emergencia, aunque las llaves estén configuradas.
- La protección completa y sus límites están en [`SEGURIDAD.md`](SEGURIDAD.md).

Para GitHub Actions puedes definir `HABILITAR_MODO_REAL`, `MAX_ANALISIS_POR_RUN` y
`COOLDOWN_SEGUNDOS` en **Settings → Secrets and variables → Actions → Variables**.

> Material educativo. Las notas que generan los agentes **no son recomendaciones de inversión**.
