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
| [ADR-005](ADR-005-arquitectura-pipeline-y-model-ids.md) | Arquitectura del pipeline, paridad entre harnesses y pinneo de model IDs | Reemplazado por ADR-009 |
| [ADR-006](ADR-006-reapertura-controlada-spec-v1.1.md) | Reapertura controlada de la spec (17 decisiones cerradas) y re-freeze como spec-v1.1 | Aceptado |
| [ADR-007](ADR-007-agente-evaluador-white-box.md) | Agente evaluador LLM para los 66 ATs no automatizables (rúbrica white-box) | Aceptado (model IDs y runtime enmendados por ADR-010) |
| [ADR-008](ADR-008-restriccion-recuperacion-web-harness-a.md) | Restricción de WebSearch/WebFetch en el harness A (paridad del factor RAG) | Aceptado |
| [ADR-009](ADR-009-harnesses-como-cli-y-orquestador-de-roles.md) | Los harnesses pasan a ser los CLI de cada proveedor; orquestador de roles; re-pinneo de model IDs | Aceptado (D4 enmendada por ADR-010) |
| [ADR-010](ADR-010-delegacion-contexto-y-evaluador.md) | Delegación en subagentes, techo de contexto del harness B y re-pinneo del evaluador white-box | Aceptado |

> **Nota (2026-07-07):** las referencias textuales a `spec-v1.0` como input de las
> corridas en ADR-001, ADR-005 y `evaluacion/protocolo.md` §2.1 y §3 paso 1 quedan
> **superadas por ADR-006**: el tag vigente es `spec-v1.1`. Además, el «eventual
> `spec-v1.1`» de `protocolo.md` §8 punto 3 debe leerse «eventual `spec-v1.2`».
> Ambas correcciones textuales se aplicarán en la revisión del protocolo de la
> ventana H6 (ADR-004). El estado de ADR-001 permanece «Aceptado» porque su decisión de
> fondo sigue vigente; ADR-005 fue reemplazado por ADR-009 el 2026-08-16 (ver la nota
> siguiente).

> **Nota (2026-08-16):** **ADR-009 reemplaza a ADR-005 por completo** (harnesses como
> CLI de cada proveedor, RAG por servidor MCP stdio único, re-pinneo de model IDs a
> `claude-opus-5` / `gpt-5.6-sol`, prompts de rol y baja del presupuesto de turnos).
> Ratificado por el tesista el mismo día. El contenido de ADR-005 no se edita: sólo
> cambia su estado. Las referencias a ADR-005 en documentos vivos (`pipeline/README.md`,
> `evaluacion/protocolo.md`, `analisis/amenazas-validez.md`) deben leerse contra ADR-009;
> la corrección del protocolo va por su propia revisión (checklist H6, ítem 9).

> **Nota (2026-08-16, segunda sesión del día):** **ADR-010** enmienda dos ADRs aceptados
> sin editarlos. De **ADR-009** reemplaza sólo la parte de la Decisión 4 que decía que los
> prompts de rol no piden delegación: ahora sí la instruyen. De **ADR-007** reemplaza los
> model IDs (juez `claude-opus-4-8` → `claude-opus-5`; espejo `gpt-5.5` → `gpt-5.6-sol`) y
> el runtime (Claude Agent SDK → `claude -p`), lo que **restaura** su diseño original de
> juez == generador de la celda A. El briefing del evaluador y las cinco mitigaciones de
> self-preference de ADR-007 §3 siguen intactos.
