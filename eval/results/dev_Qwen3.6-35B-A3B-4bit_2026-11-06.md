# Evaluación del agente

**Set:** dev  |  **Modelo:** `Qwen3.6-35B-A3B-4bit`  |  **Fecha:** 2026-11-06  |  **Runs:** 1
**Temperatura:** 0.6  |  **top_p:** 0.95

## Resumen ejecutivo  _1 run_

| Métrica | Valor |
|---|---|
| Leads por run | 30 |
| Accuracy de decisión | 100.0% |
| Accuracy de owner | 100.0% |
| Tasa de escalamiento (revision) | 23.3% |
| Guardia de consistencia activada | 0.0 |
| Fallbacks por límite de pasos | 0.0 |
| Errores de sistema | 0.0 |
| Pasos promedio | 3.47 |
| Latencia promedio | 13.0 s/lead |
| Errores por run | 0.0 |

## Accuracy por case\_type

| case_type | n | correctos | accuracy |
|---|---|---|---|
| cargo_ambiguo | 3 | 3 | 100.0% |
| datos_contradictorios | 2 | 2 | 100.0% |
| duplicado_exacto | 3 | 3 | 100.0% |
| duplicado_fuzzy | 2 | 2 | 100.0% |
| empresa_desconocida | 2 | 2 | 100.0% |
| fuera_icp | 4 | 4 | 100.0% |
| normal | 14 | 14 | 100.0% |

## Matriz de confusión  _(agregada)_

Filas = decisión esperada · Columnas = decisión del agente

| **real \ pred** | **calificado** | **revision** | **descartado** | **duplicado** |
|---|---|---|---|---|
| **calificado** | 12 | 0 | 0 | 0 |
| **revision** | 0 | 7 | 0 | 0 |
| **descartado** | 0 | 0 | 6 | 0 |
| **duplicado** | 0 | 0 | 0 | 5 |

## Detección de duplicados

| Métrica | Valor |
|---|---|
| True positives | 5 |
| False positives | 0 |
| False negatives | 0 |
| Precision | 100.0% |
| Recall | 100.0% |
| F1 | 100.0% |

## Errores (0 en total)

*Sin errores.*