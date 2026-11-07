# Lead Triage Agent

Agente de IA para triage de leads inbound B2B (contexto: info de negocios
sobre minería, energía e infraestructura en LatAm).

## Objetivo
Por cada lead: detectar duplicados en CRM, enriquecer empresa, puntuar ICP,
asignar owner (SDR), redactar primer correo, o escalar a humano si hay dudas.

## Stack
- Python 3.11, SDK `openai` apuntando a oMLX local (http://127.0.0.1:8000/v1)
- SQLite como CRM simulado, Pydantic para validar, Streamlit para dashboard
- Modelo: Qwen3.6-35B-A3B-4bit
- Autenticación con API key vía variable OMLX_API_KEY en .env (nunca hardcodeada)

## Principios
- El LLM decide QUÉ herramienta usar; los cálculos (score ICP, routing) son
  funciones Python determinísticas, nunca inventados por el LLM.
- Todo dato es sintético y ficticio. Nada de empresas ni personas reales.
- Cada decisión del agente se registra con su razonamiento (trazabilidad).
- Código simple y legible: es un proyecto de portafolio que debo poder explicar.
- Explícame brevemente cada cambio antes de hacerlo.

## Estructura
src/agent/ (loop, tools), data/, eval/, app/ (Streamlit)

## Decisiones de diseño (no revertir)
- El LLM orquesta; los datos se mueven por código. Las herramientas leen
  de la DB por lead_id en vez de recibir valores copiados por el LLM.
- El owner es determinístico: lo calcula registrar_decision, no el LLM.
- Guardia de consistencia en registrar_decision: rechaza decisiones u owners
  que contradigan los resultados de las herramientas.
- "revision" requiere un motivo de una lista cerrada; el contenido descargado
  no es criterio.
- Evaluación: dev (30) para iterar, test (70) una sola vez con el prompt congelado.
- Temperatura explícita 0.6 / top_p 0.95 (Qwen3 en modo pensamiento); no usar 0.

## Estado actual
- Fases 0-3 completas: datos sintéticos, herramientas, loop con guardia,
  evaluación dev/test con --runs, errores modelo vs sistema separados.
- Dev --runs 1: 100% decisión, 100% owner.
- Próximo: dev --runs 3 → tag prompt-v1 → test --runs 3 (una sola vez).
- Después: Fase 4 (borrador de correo + dashboard Streamlit).

## Comandos
- Tests: pytest -v
- Eval: python eval/run_eval.py --set dev|test --runs 3 --model <id>