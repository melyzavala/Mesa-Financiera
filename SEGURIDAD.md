# Seguridad de Mesa Financiera

Este proyecto educativo aplica defensa por capas a tres superficies: Telegram, los datos externos del MCP y el consumo de servicios pagados. Las medidas reducen riesgo; no garantizan seguridad absoluta.

| Riesgo | Control aplicado | Evidencia verificable |
|---|---|---|
| Acceso de un chat desconocido | Denegación por defecto si falta `TELEGRAM_CHAT_ID` y comparación exacta del chat | `test_bot_deniega_si_falta_chat_id` |
| Comandos ambiguos o texto añadido | Formato exacto `/analiza TICKER` y validación del ticker | `test_comando_exige_formato_exacto` |
| Prompt injection en datos externos | Iris recibe la instrucción de tratar el MCP como datos; después Python valida campos y texto | `test_ficha_mcp_rechaza_inyeccion_y_rango_imposible` |
| Herramientas MCP imprevistas | Lista permitida para cotización y series semanales ajustadas; máximo tres llamadas | `test_herramientas_mcp_tienen_lista_y_limite` |
| Datos incoherentes | Contrato JSON, conversión numérica, coincidencia de ticker y controles de rangos básicos | `test_ficha_mcp_se_normaliza_y_rechaza_campos_extra` |
| Consumo accidental | Máximo de 3 análisis por corrida, espera por ticker repetido e interruptor de modo real | pruebas de configuración y `test_cooldown_evitar_solicitud_duplicada` |
| Exposición de credenciales | Variables de entorno, `.env` ignorado, resumen enmascarado y credenciales de checkout no persistentes | `test_resumen_no_expone_secretos` y workflows |

## Configuración recomendada

```text
HABILITAR_MODO_REAL=1
MAX_ANALISIS_POR_RUN=3
COOLDOWN_SEGUNDOS=60
```

Para detener inmediatamente las consultas reales, cambia `HABILITAR_MODO_REAL` a `0`. El sistema usará simulación incluso si las llaves siguen presentes.

## Límites conocidos

- El enfriamiento se conserva sólo durante el proceso actual. GitHub Actions inicia un proceso nuevo cada 15 minutos, por lo que el límite principal entre ejecuciones es `MAX_ANALISIS_POR_RUN` y la cuota del proveedor.
- La validación textual bloquea patrones claros de inyección, pero ningún filtro de texto cubre todas las variantes. El contrato de campos y la ausencia de acciones en Euler y Vera reducen el impacto restante.
- El repositorio no controla el presupuesto de la cuenta de OpenAI ni la cuota de Alpha Vantage. Esos límites deben configurarse y supervisarse en cada proveedor.
- La lista de herramientas se valida después de la respuesta. El servidor MCP sigue siendo un servicio externo y debe conservar permisos mínimos.

## Verificación local sin llaves

```bash
pip install -r requirements.txt pytest
pytest -q
python analizar.py AAPL --simulacion
```

El resultado esperado es al menos 20 pruebas aprobadas y una nota marcada como simulación, con fuente local y sin llamadas a OpenAI, Alpha Vantage o Telegram.
