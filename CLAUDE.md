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