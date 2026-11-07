# Evaluación del agente

**Set:** dev  |  **Modelo:** `Qwen3.6-35B-A3B-4bit`  |  **Fecha:** 2026-11-06  |  **Runs:** 3
**Temperatura:** 0.6  |  **top_p:** 0.95

## Resumen ejecutivo  _3 runs_

| Métrica | Media  [min, max] |
|---|---|
| Leads por run | 30 |
| Accuracy de decisión | 100.0% |
| Accuracy de owner | 100.0% |
| Tasa de escalamiento (revision) | 23.3% |
| Guardia de consistencia activada | 0.0 |
| Fallbacks por límite de pasos | 0.0 |
| Errores de sistema | 0.0 |
| Pasos promedio | 3.57  [3.53, 3.60] |
| Latencia promedio | 18.3  [10.1, 34.4] s/lead |
| Errores por run | 0.0 |

## Resultado por run

| Run | Acc. decisión | Acc. owner | Dup. F1 | Pasos | Latencia | Errores |
|---|---|---|---|---|---|---|
| 1 | 100.0% | 100.0% | 100% | 3.6 | 10.1s | 0 |
| 2 | 100.0% | 100.0% | 100% | 3.6 | 10.4s | 0 |
| 3 | 100.0% | 100.0% | 100% | 3.5 | 34.4s | 0 |

## Accuracy por case\_type

| case_type | n | correctos | accuracy |
|---|---|---|---|
| cargo_ambiguo | 9 | 9 | 100.0% |
| datos_contradictorios | 6 | 6 | 100.0% |
| duplicado_exacto | 9 | 9 | 100.0% |
| duplicado_fuzzy | 6 | 6 | 100.0% |
| empresa_desconocida | 6 | 6 | 100.0% |
| fuera_icp | 12 | 12 | 100.0% |
| normal | 42 | 42 | 100.0% |

## Matriz de confusión  _(agregada)_

Filas = decisión esperada · Columnas = decisión del agente

| **real \ pred** | **calificado** | **revision** | **descartado** | **duplicado** |
|---|---|---|---|---|
| **calificado** | 36 | 0 | 0 | 0 |
| **revision** | 0 | 21 | 0 | 0 |
| **descartado** | 0 | 0 | 18 | 0 |
| **duplicado** | 0 | 0 | 0 | 15 |

## Detección de duplicados

| Métrica | Valor |
|---|---|
| True positives | 15 |
| False positives | 0 |
| False negatives | 0 |
| Precision | 100.0% |
| Recall | 100.0% |
| F1 | 100.0% |

## Errores (0 en total)

*Sin errores.*