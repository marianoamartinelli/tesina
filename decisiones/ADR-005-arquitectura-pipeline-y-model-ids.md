# ADR-005 — Arquitectura del pipeline, paridad entre harnesses y pinneo de model IDs

- **Estado:** aceptado (2026-07-05)
- **Contexto:** hito H4 del [ROADMAP](../ROADMAP.md); requisitos de paridad del
  [protocolo pre-registrado](../evaluacion/protocolo.md) §2 (variables controladas).

## Contexto

El factorial 2×2 cruza **modelo** (A: Claude / B: GPT) × **RAG** (sin/con). El factor
"modelo" es en realidad el **pipeline completo** (modelo + SDK de agentes del mismo
proveedor), tal como lo define la propuesta: Claude + Claude Agent SDK vs GPT + OpenAI
Agents SDK. Tres decisiones necesitan cerrarse antes de construir: (1) qué significa
"paridad" entre dos SDKs distintos, (2) cómo se implementa el RAG conmutable sin
contaminar los factores, (3) qué model IDs exactos se pinnean.

## Decisión 1 — Paridad por equivalencia funcional, no por identidad

Cada harness usa el **stack agéntico nativo de su proveedor** en configuración
out-of-the-box: el Claude Agent SDK con sus herramientas nativas de coding (lectura y
escritura de archivos, edición, bash, búsqueda) y el OpenAI Agents SDK con su harness de
coding y sandbox (introducido en 2026: inspección de archivos, ejecución de comandos,
edición de código). **No** se reimplementa un toolset artificial común: eso mediría un
harness inventado por el tesista, no los productos que un equipo real usaría, y es la
comparación que la propuesta pre-registró.

Lo que sí es **idéntico** entre celdas (auditable en `pipeline/`):

1. **Las etapas** y su orden (backend → web → mobile), definidas una sola vez en
   `pipeline/comun/etapas.yaml`.
2. **Los prompts** (de sistema y de etapa), archivos únicos en `pipeline/comun/prompts/`
   que ambos harnesses cargan verbatim; ningún prompt vive dentro del código de un
   harness.
3. **El input**: el repo satélite con la spec pinneada a `spec-v1.0`.
4. **La herramienta RAG** (celdas con RAG): mismo código, mismo índice, mismos
   parámetros (Decisión 2).
5. **Los presupuestos y criterios de intervención** (protocolo, ADR-004).

Consecuencia asumida: las diferencias de tooling nativo entre SDKs quedan **dentro** del
factor "pipeline" y no pueden separarse del modelo. Se declara como limitación en el
cap. 4 (amenazas a la validez); es inherente al diseño pre-registrado, no un defecto de
implementación.

## Decisión 2 — RAG léxico determinista (BM25), sin modelo de embeddings

La base de conocimiento se expone como una herramienta `consultar_corpus(consulta)` que
ambos harnesses registran **sólo** en las celdas `*-con-rag`. La recuperación es
**BM25 puro** (k1=1.5, b=0.75, k=6 pasajes) sobre chunks por sección de los 9 documentos
del corpus congelado (H3), implementado en ~150 líneas de Python sin dependencias
(`pipeline/comun/rag/indice.py`, con tests).

Motivos frente a la alternativa (embeddings + búsqueda vectorial):

- **No introduce un tercer modelo.** Usar embeddings de OpenAI en la celda de Claude (o
  viceversa) contaminaría el aislamiento del factor modelo; usar embeddings de cada
  proveedor en su celda haría el RAG distinto entre celdas, violando protocolo §2.2.
- **Determinismo y reproducibilidad:** misma consulta ⇒ mismos pasajes, siempre; el
  índice se reconstruye bit a bit desde el corpus.
- **Adecuación al corpus:** los documentos son estándares técnicos con vocabulario
  exacto (nombres de campos, rutas de derivación, opcodes); la búsqueda léxica es
  competitiva en ese régimen y la consulta típica del agente incluye esos términos.

Los prompts de etapa **no mencionan la herramienta**: su disponibilidad (con su
descripción propia) es la única diferencia entre celdas con y sin RAG, lo que mantiene
los prompts byte-idénticos entre las 4 celdas.

## Decisión 3 — Model IDs pinneados

| Celda | Model ID exacto | Justificación de pareo |
|-------|-----------------|------------------------|
| A (`a-sin-rag`, `a-con-rag`) | `claude-opus-4-8` | Flagship de Anthropic (tier Opus). 1M contexto. USD 5/M input, 25/M output. |
| B (`b-sin-rag`, `b-con-rag`) | `gpt-5.5` | Flagship de OpenAI. 1M contexto. USD 5/M input, 30/M output. |

Criterio de pareo: **flagship contra flagship**, mismo precio de input, misma ventana de
contexto, ambos son el modelo que cada proveedor recomienda para coding agéntico a la
fecha (verificado 2026-07-05 contra la documentación de precios de ambos proveedores).
Alternativa descartada: tier medio (`claude-sonnet-5` / `gpt-5.4`) — se reserva como
plan B si la corrida piloto muestra que el presupuesto de 200 USD/corrida es
insuficiente con los flagships; ese cambio requeriría ADR de reemplazo **antes** de la
primera corrida oficial (ADR-004).

Los parámetros de generación quedan en el default de cada SDK (out-of-the-box); todo
parámetro no-default que resulte imprescindible se fija idéntico en ambas celdas y se
registra en `pipeline/config/`.

## Consecuencias

- `pipeline/` queda estructurado como: `comun/` (etapas + prompts + RAG, compartido),
  `harness_a/` y `harness_b/` (adaptadores finos por SDK), `config/` (una config
  declarativa por celda: model ID + conmutador RAG + rutas).
- Un script `verificar_paridad.py` chequea mecánicamente antes de cada corrida: que las
  configs sólo difieren en los dos factores, que los prompts referenciados son los
  mismos archivos, y que el corpus/índice coincide con el manifest de H3.
- Versiones de SDK pinneadas en `pipeline/requirements.txt`; se registran junto con los
  model IDs en el manifest de cada corrida.
- La piloto (H6) valida costo y estabilidad; cualquier ajuste posterior sigue la vía de
  ADR-004 (nueva versión + ADR de reemplazo antes de las corridas oficiales).
