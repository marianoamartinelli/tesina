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
| [ADR-004](ADR-004-protocolo-experimental-preregistrado.md) | Protocolo experimental pre-registrado y congelado antes de las corridas | Reemplazado por ADR-012 |
| [ADR-005](ADR-005-arquitectura-pipeline-y-model-ids.md) | Arquitectura del pipeline, paridad entre harnesses y pinneo de model IDs | Reemplazado por ADR-009 |
| [ADR-006](ADR-006-reapertura-controlada-spec-v1.1.md) | Reapertura controlada de la spec (17 decisiones cerradas) y re-freeze como spec-v1.1 | Aceptado |
| [ADR-007](ADR-007-agente-evaluador-white-box.md) | Agente evaluador LLM para los 66 ATs no automatizables (rúbrica white-box) | Aceptado (model IDs y runtime enmendados por ADR-010; partición 66 → 56 por ADR-011) |
| [ADR-008](ADR-008-restriccion-recuperacion-web-harness-a.md) | Restricción de WebSearch/WebFetch en el harness A (paridad del factor RAG) | Aceptado |
| [ADR-009](ADR-009-harnesses-como-cli-y-orquestador-de-roles.md) | Los harnesses pasan a ser los CLI de cada proveedor; orquestador de roles; re-pinneo de model IDs | Aceptado (D4 enmendada por ADR-010) |
| [ADR-010](ADR-010-delegacion-contexto-y-evaluador.md) | Delegación en subagentes, techo de contexto del harness B y re-pinneo del evaluador white-box | Aceptado |
| [ADR-011](ADR-011-particion-automatizable-white-box.md) | Partición final automatizable / white-box de los ATs backend (465 / 56) | Aceptado |
| [ADR-012](ADR-012-protocolo-experimental-v1-1.md) | Protocolo experimental v1.1 (reemplaza a ADR-004) | Aceptado |
| [ADR-013](ADR-013-mecanismo-importar-mnemonic.md) | Mecanismo de import del mnemonic en la evaluación white-box | Aceptado |

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

> **Nota (2026-08-16, tercera sesión del día; ratificados el 2026-08-17):** la ventana H6
> produjo **ADR-011, ADR-012 y ADR-013**, los tres **Aceptados** — ADR-011 y ADR-012 en
> conjunto, porque la v1.1 del protocolo cita la partición. ADR-012 congela `evaluacion/protocolo.md` **v1.1**, que ya
> aplica las correcciones textuales que la nota del 2026-07-07 dejaba pendientes para
> esta ventana (`spec-v1.1` en §2.1 y §3 paso 1; «eventual `spec-v1.2`» en §8 punto 3) y
> redefine el factor «modelo» como Claude Code CLI contra Codex CLI. ADR-011 mueve la
> frontera automatizable/white-box de 455/66 a **465/56** sobre los 521 ATs backend, lo
> que enmienda el conjunto de ADR-007 sin editarlo. ADR-013 ratifica el fallback de los
> cuatro ATs de import de mnemonic de la épica 06 y fija su convención de descubrimiento.
> Si alguno se rechaza, el documento vivo que congela vuelve a su versión previa: el
> propio ADR declara el camino de vuelta.
