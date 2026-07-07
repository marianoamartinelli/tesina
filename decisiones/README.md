# Decisiones (ADRs)

Registro de decisiones estructurales del proyecto, en formato Architecture Decision
Record. Cada ADR es **inmutable una vez aceptado**: si una decisión se revierte o
cambia, se escribe un ADR nuevo que la reemplaza y se actualiza el estado del viejo a
`Reemplazado por ADR-NNN` (sin reescribir su contenido).

## Convención

- Archivo: `ADR-NNN-titulo-en-kebab-case.md`, numeración secuencial de tres dígitos.
- Estructura: **Estado** (Propuesto/Aceptado/Reemplazado) · **Fecha** · **Contexto** ·
  **Decisión** · **Consecuencias**.
- Ámbito: decisiones que condicionan el experimento o la estructura del trabajo
  (metodología, herramientas, protocolo, alcance). Las observaciones del día a día van
  a `journal/`, no acá.

## Índice

| ADR | Título | Estado |
|-----|--------|--------|
| [ADR-001](ADR-001-implementaciones-en-repos-separados.md) | Implementaciones generadas en repos separados por corrida | Aceptado |
| [ADR-002](ADR-002-tesis-en-latex.md) | Documento de tesina en LaTeX versionado en el repo | Aceptado |
| [ADR-003](ADR-003-registro-exhaustivo-para-metaanalisis.md) | Registro exhaustivo: journal por sesión + ADRs + manifests | Aceptado |
| [ADR-004](ADR-004-protocolo-experimental-preregistrado.md) | Protocolo experimental pre-registrado y congelado antes de las corridas | Aceptado |
| [ADR-005](ADR-005-arquitectura-pipeline-y-model-ids.md) | Arquitectura del pipeline, paridad entre harnesses y pinneo de model IDs | Aceptado |
| [ADR-006](ADR-006-reapertura-controlada-spec-v1.1.md) | Reapertura controlada de la spec (17 decisiones cerradas) y re-freeze como spec-v1.1 | Aceptado |
| [ADR-007](ADR-007-agente-evaluador-white-box.md) | Agente evaluador LLM para los 66 ATs no automatizables (rúbrica white-box) | Aceptado |
| [ADR-008](ADR-008-restriccion-recuperacion-web-harness-a.md) | Restricción de WebSearch/WebFetch en el harness A (paridad del factor RAG) | Propuesto |

> **Nota (2026-07-07):** las referencias textuales a `spec-v1.0` como input de las
> corridas en ADR-001, ADR-005 y `evaluacion/protocolo.md` §2.1 y §3 paso 1 quedan
> **superadas por ADR-006**: el tag vigente es `spec-v1.1`. Además, el «eventual
> `spec-v1.1`» de `protocolo.md` §8 punto 3 debe leerse «eventual `spec-v1.2`».
> Ambas correcciones textuales se aplicarán en la revisión del protocolo de la
> ventana H6 (ADR-004); los estados de ADR-001/ADR-005 permanecen «Aceptado» porque
> sus decisiones de fondo siguen vigentes.
