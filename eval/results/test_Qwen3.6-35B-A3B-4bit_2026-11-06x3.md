# Evaluación del agente

**Set:** test  |  **Modelo:** `Qwen3.6-35B-A3B-4bit`  |  **Fecha:** 2026-11-06  |  **Runs:** 3
**Temperatura:** 0.6  |  **top_p:** 0.95

## Resumen ejecutivo  _3 runs_

| Métrica | Media  [min, max] |
|---|---|
| Leads por run | 70 |
| Accuracy de decisión  (70 válidos de 70) | 95.7%  [92.9%, 97.1%] |
| Accuracy de owner  (70 válidos de 70) | 97.1%  [94.3%, 98.6%] |
| Tasa de escalamiento (revision) | 28.6%  [27.1%, 31.4%] |
| Guardia de consistencia activada | 0.3  [0.0, 1.0] |
| Fallbacks por límite de pasos | 2.7  [2.0, 4.0] |
| Errores de sistema | 0.0 |
| Pasos promedio | 3.37  [3.27, 3.46] |
| Latencia promedio | 24.7  [18.3, 34.3] s/lead |
| Errores por run | 3.0  [2.0, 5.0] |

## Resultado por run

| Run | Acc. decisión | Acc. owner | Dup. F1 | Pasos | Latencia | Errores |
|---|---|---|---|---|---|---|
| 1 | 92.9% | 94.3% | 96% | 3.3 | 34.3s | 5 |
| 2 | 97.1% | 98.6% | 96% | 3.4 | 21.5s | 2 |
| 3 | 97.1% | 98.6% | 96% | 3.5 | 18.3s | 2 |

## Accuracy por case\_type

| case_type | n | correctos | accuracy |
|---|---|---|---|
| cargo_ambiguo | 15 | 13 | 86.7% |
| datos_contradictorios | 15 | 15 | 100.0% |
| duplicado_exacto | 21 | 21 | 100.0% |
| duplicado_fuzzy | 18 | 18 | 100.0% |
| empresa_desconocida | 18 | 18 | 100.0% |
| fuera_icp | 24 | 24 | 100.0% |
| normal | 99 | 92 | 92.9% |

## Matriz de confusión  _(agregada)_

Filas = decisión esperada · Columnas = decisión del agente

| **real \ pred** | **calificado** | **revision** | **descartado** | **duplicado** | **error_sistema** |
|---|---|---|---|---|---|
| **calificado** | 65 | 4 | 0 | 3 | 0 |
| **revision** | 0 | 54 | 0 | 0 | 0 |
| **descartado** | 0 | 2 | 43 | 0 | 0 |
| **duplicado** | 0 | 0 | 0 | 39 | 0 |

## Detección de duplicados

| Métrica | Valor |
|---|---|
| True positives | 39 |
| False positives | 3 |
| False negatives | 0 |
| Precision | 92.9% |
| Recall | 100.0% |
| F1 | 96.3% |

## Errores (9 en total)

Ver `test_Qwen3.6-35B-A3B-4bit_2026-11-06x3_errors.csv` para el detalle completo.

### Errores de decisión (9)

| run | lead\_id | case\_type | esperado | obtenido | razonamiento |
|---|---|---|---|---|---|
| 1 | 43 | cargo_ambiguo | calificado | revision | Límite de pasos alcanzado sin decisión final.… |
| 1 | 45 | cargo_ambiguo | calificado | revision | Lead no duplicado. Empresa encontrada en sector infraestructura, país Argentina, 650 emple… |
| 1 | 72 | normal | calificado | duplicado | Se ejecutó buscar_duplicado y se detectó un lead existente con similitud fuzzy del 87.5%. … |
| 1 | 78 | normal | calificado | revision | Límite de pasos alcanzado sin decisión final.… |
| 1 | 94 | normal | descartado | revision | Límite de pasos alcanzado sin decisión final.… |
| 2 | 72 | normal | calificado | duplicado | Se ejecutó buscar_duplicado y se encontró un contacto existente en el CRM (ID 3: Natalia S… |
| 2 | 94 | normal | descartado | revision | Límite de pasos alcanzado sin decisión final.… |
| 3 | 72 | normal | calificado | duplicado | Se ejecutó buscar_duplicado y se detectó como duplicado fuzzy (similitud 87.5%) con el lea… |
| 3 | 80 | normal | calificado | revision | Límite de pasos alcanzado sin decisión final.… |

### Errores de owner (6)  _(decisión correcta)_

| run | lead\_id | case\_type | decisión | owner esperado | owner obtenido |
|---|---|---|---|---|---|
| 1 | 43 | cargo_ambiguo | revision | Luis Méndez | cola_revision |
| 1 | 45 | cargo_ambiguo | revision | Ana Torres | cola_revision |
| 1 | 78 | normal | revision | Ana Torres | cola_revision |
| 1 | 94 | normal | revision |  | cola_revision |
| 2 | 94 | normal | revision |  | cola_revision |
| 3 | 80 | normal | revision | Carla Souza | cola_revision |