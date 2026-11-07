# Evaluación del agente

**Set:** dev  |  **Modelo:** `Qwen3.6-35B-A3B-4bit`  |  **Fecha:** 2026-11-06

## Resumen ejecutivo

| Métrica | Valor |
|---|---|
| Leads evaluados | 30 |
| Accuracy de decisión | 96.7% (29/30) |
| Accuracy de owner | 96.7% (29/30) |
| Tasa de escalamiento (revision) | 26.7% |
| Guardia de consistencia activada | 7 veces |
| Pasos promedio | 4.70 |
| Latencia promedio | 15.6 s/lead |
| Latencia total | 467 s (7.8 min) |

## Accuracy por case\_type

| case_type | n | correctos | accuracy |
|---|---|---|---|
| cargo_ambiguo | 3 | 3 | 100.0% |
| datos_contradictorios | 2 | 2 | 100.0% |
| duplicado_exacto | 3 | 3 | 100.0% |
| duplicado_fuzzy | 2 | 2 | 100.0% |
| empresa_desconocida | 2 | 2 | 100.0% |
| fuera_icp | 4 | 4 | 100.0% |
| normal | 14 | 13 | 92.9% |

## Matriz de confusión

Filas = decisión esperada · Columnas = decisión del agente

| **real \ pred** | **calificado** | **revision** | **descartado** | **duplicado** |
|---|---|---|---|---|
| **calificado** | 11 | 1 | 0 | 0 |
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

## Errores (1 leads)

Ver `dev_Qwen3.6-35B-A3B-4bit_2026-11-06_errors.csv` para el detalle completo.

### Errores de decisión (1)

| lead\_id | case\_type | esperado | obtenido | razonamiento del agente |
|---|---|---|---|---|
| 57 | normal | calificado | revision | Score ICP 100 (mineria/Chile/2500empleados/Directora Op.), pero descargó Informe Mercado Eléctrico C… |

### Errores de owner (1)  _(decisión correcta)_

| lead\_id | case\_type | decisión | owner esperado | owner obtenido |
|---|---|---|---|---|
| 57 | normal | revision | Ana Torres | cola_revision |