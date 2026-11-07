# Análisis de errores — set test, 3 runs

**Modelo:** Qwen3.6-35B-A3B-4bit  |  **Fecha:** 2026-11-06  |  **Leads:** 70 × 3 = 210 procesados

---

## Tabla de errores

| Lead | case\_type | Esperado | Obtenido | Runs fallidas | Causa (traza) |
|------|-----------|----------|----------|:---:|---|
| #43 | cargo\_ambiguo | calificado | revision | 1/3 (R1) | Modelo respondió con texto plano sin tool\_calls en el paso 1; el loop cayó al fallback step\_limit |
| #45 | cargo\_ambiguo | calificado | revision | 1/3 (R1) | Modelo usó el campo `contenido` ("Informe: Mercado Eléctrico Colombia") como evidencia de `datos_contradictorios` con `pais=Argentina`, violando la regla explícita del system prompt |
| #72 | normal | calificado | duplicado | 3/3 | `buscar_duplicado` detectó fuzzy match 87.5 % > umbral 85 % con Natalia Silva (mismo dominio, apellido distinto). Resultado determinístico; el LLM actuó correctamente según la herramienta |
| #78 | normal | calificado | revision | 1/3 (R1) | Mismo patrón que #43: texto plano en paso 1, step\_limit |
| #80 | normal | calificado | revision | 1/3 (R3) | Texto plano sin tool\_calls en el paso 3 (tras buscar\_duplicado y enriquecer\_empresa); step\_limit con 3 pasos registrados |
| #94 | normal | descartado | revision | 2/3 (R1, R2) | Texto plano en paso 1, step\_limit en dos de tres runs; en R3 el flujo completó correctamente en 4 pasos → descartado |

> Los 9 errores del CSV surgen de las 6 filas anteriores más la multiplicidad de runs: #72 falla en las 3 corridas (3 registros), #94 en 2 corridas (2 registros), el resto 1 vez cada uno (4 registros). Total: 3 + 2 + 4 = 9.

---

## Clasificación por origen

| Origen | Leads | Instancias de error (runs) |
|--------|:-----:|:--------------------------:|
| Error de orquestación | 4 (#43, #78, #80, #94) | 5 |
| Error de herramienta determinística | 1 (#72) | 3 |
| Error de juicio del LLM | 1 (#45) | 1 |
| **Total** | **6** | **9** |

### Error de orquestación — respuesta sin tool\_calls, fallback step\_limit

**Leads #43, #78, #80 y #94.** En alguna de sus corridas el modelo emitió una respuesta de texto plano sin `tool_calls` en lugar de llamar a la siguiente herramienta. El loop interpreta esa respuesta como fin de turno: al no haber `final_args`, activa el fallback que registra `step_limit → revision`. La etiqueta `step_limit` es engañosa porque el límite de pasos no se alcanzó; el problema real es que el loop no maneja el caso de respuesta sin herramienta. El comportamiento es no reproducible: las corridas del mismo lead que sí completan el flujo producen la decisión correcta.

### Error de herramienta determinística — falla igual en todas las corridas

**Lead #72** es el único error de este tipo. `buscar_duplicado` siempre devuelve `es_duplicado=True` porque el ratio de similitud (87.5 %) supera el umbral `_FUZZY_EMAIL_THRESHOLD = 85`. El LLM interpreta correctamente el resultado y registra `duplicado`. El error no está en el juicio del modelo sino en que el umbral es demasiado bajo para distinguir a dos personas distintas que comparten dominio de empresa.

### Error de juicio del LLM — regla ignorada

**Lead #45**: el modelo invocó todas las herramientas correctamente y obtuvo `score=80` (calificado), pero luego razonó que el contenido descargado ("Informe: Mercado Eléctrico Colombia") contradice el país del lead (Argentina) y registró `revision` con `motivo=datos_contradictorios`. El system prompt dice explícitamente "El contenido descargado no es criterio de decisión", pero el modelo ignoró la regla en esa corrida.

### Ground truth dudoso

Ninguno. Los 6 leads tienen una causa identificable y el ground truth es consistente con el comportamiento correcto del agente en las corridas que sí aciertan.

---

## Accuracy de decisión (95,7 %) vs. accuracy de owner (97,1 %)

La accuracy de owner es más alta porque **el lead #72 produce errores de decisión sin producir errores de owner**.

Cuando `buscar_duplicado` detecta a Natalia Sánchez como duplicada de Natalia Silva (CRM contact #3), el owner del contacto existente en el CRM es `Ana Torres`. La decisión correcta también habría sido `calificado` con owner `Ana Torres` (empresa en Argentina → `ROUTING["Argentina"] = "Ana Torres"`). Los dos caminos convergen en el mismo owner, así que el error de decisión no arrastra error de owner.

Resultado por run:

| Run | Errores de decisión | Errores de owner | Acc. decisión | Acc. owner |
|:---:|:---:|:---:|:---:|:---:|
| R1 | 5 (#43, #45, #72, #78, #94) | 4 (#43, #45, #78, #94) | 65/70 = 92,9 % | 66/70 = 94,3 % |
| R2 | 2 (#72, #94)                | 1 (#94)               | 68/70 = 97,1 % | 69/70 = 98,6 % |
| R3 | 2 (#72, #80)                | 1 (#80)               | 68/70 = 97,1 % | 69/70 = 98,6 % |
| **Media** | — | — | **95,7 %** | **97,1 %** |

Las 3 instancias de #72 cuentan en el denominador de decisión pero no en el de owner, explicando la diferencia de ~1,4 puntos porcentuales.

---

## Lead #72 en detalle

### Lead inbound

| Campo | Valor |
|-------|-------|
| ID | 72 |
| Nombre | Natalia Sánchez |
| Email | natalia.sanchez@patagoniawind.com |
| Cargo | Jefa de Área |
| Empresa | Patagonia Wind S.A. |
| País | Argentina |
| Contenido | Webinar: Energías Renovables en Chile |

### Contacto CRM con el que hizo match

| Campo | Valor |
|-------|-------|
| ID CRM | 3 |
| Nombre | Natalia Silva |
| Email | natalia.silva@patagoniawind.com |
| Cargo | Director de Operaciones |
| Empresa | Patagonia Wind S.A. |
| País | Argentina |
| Owner | Ana Torres |

### Similitud

```
natalia.sanchez@patagoniawind.com
natalia.silva@patagoniawind.com
─────────────────────────────────
fuzz.ratio = 87,5 %  >  umbral _FUZZY_EMAIL_THRESHOLD = 85 %
```

Los dos emails comparten `natalia.s` al inicio y `@patagoniawind.com` al final (27 de 33 / 31 caracteres). La diferencia — `anchez` vs `ilva` — es suficiente para que dos personas distintas de la misma empresa superen el umbral de 85 %.

**Consecuencia:** `buscar_duplicado` siempre devuelve `es_duplicado=True` para este par, el modelo nunca llega a enriquecer ni puntuar el lead, y la decisión es siempre `duplicado`. El error es **reproducible** (3/3) y **determinístico**.

**Posible corrección** (sin tocar src/): subir `_FUZZY_EMAIL_THRESHOLD` a ~90–92 en la próxima versión del agente, o agregar un criterio de nombre para desambiguar matches fuzzy del mismo dominio.

---

## Backlog v2

Tres mejoras derivadas del análisis anterior, ordenadas por impacto estimado.

### 1. Re-prompt cuando no hay tool\_calls

Cuando el loop detecta que la respuesta del modelo no contiene `tool_calls` (y el lead aún no tiene `final_args`), reenviar el turno con un mensaje de sistema que indique al modelo que debe llamar a una herramienta antes de concluir. Limitar a 1 reintento por paso para evitar bucles infinitos. Esto eliminaría los 5 errores de orquestación sin cambiar la lógica de decisión.

### 2. Etiqueta de fallback `sin_tool_call`

Si tras el re-prompt el modelo sigue sin emitir `tool_calls`, registrar el fallback con la etiqueta `sin_tool_call` (en vez de `step_limit`). Permite distinguir en las métricas de eval cuándo el agente paró por límite real de pasos y cuándo paró porque el modelo nunca arrancó el flujo.

### 3. Deduplicación por dominio exacto + fuzzy de nombre completo

Reemplazar el fuzzy de email como criterio único por una lógica en dos etapas: (1) exigir dominio idéntico como condición necesaria, (2) aplicar fuzzy sobre el nombre completo (no el email) con umbral más alto (~90 %). Un match requiere ambas condiciones. Esto resolvería el falso positivo del lead #72 (Natalia Sánchez vs. Natalia Silva) sin afectar los duplicados reales del set.
