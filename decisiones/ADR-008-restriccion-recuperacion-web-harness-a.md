# ADR-008 — Restricción de recuperación web en el harness A (WebSearch/WebFetch)

- **Estado:** **Propuesto** (se ratifica o rechaza en la ventana de la corrida piloto,
  H6 — la decisión la toma el tesista al revisar el PR)
- **Fecha:** 2026-07-07
- **Contexto:** complementa a [ADR-005](ADR-005-arquitectura-pipeline-y-model-ids.md)
  (Decisión 1: stack nativo out-of-the-box) sin editarlo; surge de la auditoría de
  consistencia pre-piloto (hallazgo pipeline/paridad-02).

## Contexto

El toolset default de Claude Code (harness A) incluye **WebSearch** y **WebFetch**:
herramientas de recuperación con motor de búsqueda indexado, de primera clase. El
`SandboxAgent` del harness B sólo trae Filesystem + Shell + Compaction — no tiene
ninguna herramienta dedicada de recuperación web.

Esto crea dos problemas de distinta naturaleza:

1. **Asimetría general de toolsets A/B.** Ya está asumida y pre-registrada: ADR-005
   Decisión 1 declara que las diferencias de tooling nativo entre SDKs quedan dentro
   del factor "pipeline" y se reportan como limitación en el cap. 4. **Este ADR no
   cubre eso** y no lo cambia.
2. **Contaminación del factor RAG** — lo que este ADR sí cubre y ADR-005 no: una celda
   `a-sin-rag` podría recuperar los BIPs/EIPs del corpus desde internet con una
   herramienta dedicada de búsqueda indexada, diluyendo el contraste con/sin RAG — el
   factor que el experimento mide. El conmutador RAG (ADR-005, Decisión 2) presupone
   que la disponibilidad de `consultar_corpus` es la única vía de recuperación
   dedicada que varía entre celdas.

## Decisión

Agregar `disallowed_tools=["WebSearch", "WebFetch"]` en `construir_opciones` de
`pipeline/harness_a/correr.py`, idéntico en las dos celdas A.

Con eso ambos harnesses quedan con el **mismo canal residual** de acceso a internet:
el shell con red abierta (`curl` y equivalentes). Ese canal **no se bloquea** en
ninguno de los dos, porque hacerlo rompería `npm install` / `pip install`, que las
etapas necesitan; queda declarado como **limitación residual** en el cap. 4 (amenazas
a la validez del factor RAG).

## Alternativa descartada

Mantener el toolset A totalmente out-of-the-box (lectura estricta de ADR-005) e
**instrumentar el conteo** de usos de WebSearch/WebFetch en el log JSONL,
declarándolo como amenaza a la validez en el análisis. Se descarta porque medir la
contaminación no la evita: una sola recuperación exitosa de un BIP/EIP en una celda
sin RAG compromete el contraste de esa celda, y el costo de prevenirla (una opción
de configuración) es mínimo frente al de censurar o reinterpretar una corrida oficial.

## Consecuencias

- La opción no-default (`disallowed_tools`) se registra en el manifest de cada corrida
  (`runs/plantillas/`), junto con las demás opciones del harness.
- `pipeline/README.md` queda actualizado (bullet del harness A en Arquitectura y
  limitación residual del canal por shell).
- **No se edita ADR-005**: la asimetría general de toolsets sigue asumida tal como
  está; este ADR sólo cierra la vía de recuperación indexada que contamina el factor
  RAG.
- Si el ADR se rechaza en la ventana H6, se revierte el cambio en
  `pipeline/harness_a/correr.py` y se adopta la alternativa descartada (conteo +
  declaración como amenaza).
