# Evaluación del agente

**Set:** test  |  **Modelo:** `Qwen3.6-35B-A3B-4bi`  |  **Fecha:** 2026-11-06  |  **Runs:** 3
**Temperatura:** 0.6  |  **top_p:** 0.95

## Resumen ejecutivo  _3 runs_

| Métrica | Media  [min, max] |
|---|---|
| Leads por run | 70 |
| Accuracy de decisión | 25.7% |
| Accuracy de owner | 25.7% |
| Tasa de escalamiento (revision) | 100.0% |
| Guardia de consistencia activada | 0.0 |
| Fallbacks por límite de pasos | 0.0 |
| Errores de sistema | 70.0 |
| Pasos promedio | 0.00 |
| Latencia promedio | 0.0 s/lead |
| Errores por run | 70.0 |

## Resultado por run

| Run | Acc. decisión | Acc. owner | Dup. F1 | Pasos | Latencia | Errores |
|---|---|---|---|---|---|---|
| 1 | 25.7% | 25.7% | 0% | 0.0 | 0.0s | 70 |
| 2 | 25.7% | 25.7% | 0% | 0.0 | 0.0s | 70 |
| 3 | 25.7% | 25.7% | 0% | 0.0 | 0.0s | 70 |

## Accuracy por case\_type

| case_type | n | correctos | accuracy |
|---|---|---|---|
| cargo_ambiguo | 15 | 0 | 0.0% |
| datos_contradictorios | 15 | 15 | 100.0% |
| duplicado_exacto | 21 | 0 | 0.0% |
| duplicado_fuzzy | 18 | 0 | 0.0% |
| empresa_desconocida | 18 | 18 | 100.0% |
| fuera_icp | 24 | 15 | 62.5% |
| normal | 99 | 6 | 6.1% |

## Matriz de confusión  _(agregada)_

Filas = decisión esperada · Columnas = decisión del agente

| **real \ pred** | **calificado** | **revision** | **descartado** | **duplicado** |
|---|---|---|---|---|
| **calificado** | 0 | 72 | 0 | 0 |
| **revision** | 0 | 54 | 0 | 0 |
| **descartado** | 0 | 45 | 0 | 0 |
| **duplicado** | 0 | 39 | 0 | 0 |

## Detección de duplicados

| Métrica | Valor |
|---|---|
| True positives | 0 |
| False positives | 0 |
| False negatives | 39 |
| Precision | 0.0% |
| Recall | 0.0% |
| F1 | 0.0% |

## Errores (210 en total)

Ver `test_Qwen3.6-35B-A3B-4bi_2026-11-06x3_errors.csv` para el detalle completo.