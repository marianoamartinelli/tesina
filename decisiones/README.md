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
| [ADR-009](ADR-009-harnesses-como-cli-y-orquestador-de-roles.md) | Los harnesses pasan a ser los CLI de cada proveedor; orquestador de roles; re-pinneo de model IDs | Aceptado (D4 enmendada por ADR-010; D5 corregida por ADR-014; la asimetría de confinamiento de D1, eliminada por ADR-015) |
| [ADR-010](ADR-010-delegacion-contexto-y-evaluador.md) | Delegación en subagentes, techo de contexto del harness B y re-pinneo del evaluador white-box | Aceptado |
| [ADR-011](ADR-011-particion-automatizable-white-box.md) | Partición final automatizable / white-box de los ATs backend (465 / 56) | Aceptado |
| [ADR-012](ADR-012-protocolo-experimental-v1-1.md) | Protocolo experimental v1.1 (reemplaza a ADR-004) | Reemplazado por ADR-016 |
| [ADR-013](ADR-013-mecanismo-importar-mnemonic.md) | Mecanismo de import del mnemonic en la evaluación white-box | Aceptado |
| [ADR-014](ADR-014-recuperacion-web-en-el-harness-b.md) | La recuperación web del harness B no venía desactivada: mecanismo explícito | Aceptado |
| [ADR-015](ADR-015-agentes-en-contenedores.md) | Los agentes corren en contenedores, con toolchain común y capa por CLI | Aceptado (D3 enmendada por ADR-017 del lado A) |
| [ADR-016](ADR-016-sin-topes-de-presupuesto.md) | No hay topes de presupuesto: la corrida termina cuando termina el pipeline | Aceptado |
| [ADR-017](ADR-017-credenciales-por-entorno-en-el-harness-a.md) | Las credenciales del harness A se inyectan por entorno, no por bind-mount | Aceptado |
| [ADR-018](ADR-018-corrida-pre-piloto.md) | Corrida pre-piloto sobre un universo reducido de la spec, antes de la piloto | Aceptado |
| [ADR-019](ADR-019-confinamiento-por-contenedor-en-ambas-familias.md) | El confinamiento es el contenedor: B corre sin su sandbox nativo | Aceptado |
| [ADR-020](ADR-020-nodo-onchain-y-smoke-ejecutable.md) | El agente alcanza el nodo on-chain; los criterios de avance de web y mobile son ejecutables | Aceptado |
| [ADR-021](ADR-021-smoke-y-evaluacion-dentro-del-contenedor.md) | El artefacto se ejecuta donde se construyó: smoke y SUT de H8 en contenedor | Aceptado |
| [ADR-022](ADR-022-alcance-de-las-metricas-estaticas.md) | Las métricas estáticas no cuentan la spec ni los lockfiles | Aceptado |
| [ADR-023](ADR-023-estado-de-sesion-del-cli-b-en-los-logs.md) | El estado de sesión del CLI de B (rollouts, único registro de sus subagentes) se persiste en los logs de la corrida | Aceptado |
| [ADR-024](ADR-024-reapertura-controlada-spec-v1.2-rate-limiting.md) | Reapertura controlada de la spec y re-freeze como `spec-v1.2`: rate limiting de `/auth/*` obligatorio y determinista (60 por origen en 60 s) | Aceptado |
| [ADR-025](ADR-025-protocolo-v1-6-cierre-de-la-ventana-h6.md) | Protocolo v1.6: RAG disponible e instruido, `duracion_min` no-métrica, suscripción con continuación estándar, emulador Android, rúbrica web v1.1 | Aceptado |
| [ADR-026](ADR-026-evaluacion-gestionada-por-agentes.md) | La evaluación es gestionada íntegramente por agentes: Grok Build (`grok-4.6`) ejecuta todo paso con juicio en dos pasadas + arbitraje; el humano es operador | Aceptado |

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

> **Nota (2026-08-23):** tres ADRs más de la ventana H6, los tres **Aceptados** el mismo
> día. **ADR-014** corrige una afirmación fáctica de ADR-009 Decisión 5: medido sobre
> `codex-cli` 0.146.0, la búsqueda web de Codex **no** viene desactivada por default y
> `apps`/`browser_use`/`computer_use` vienen encendidas, así que el traslado de ADR-008 al
> lado B necesita mecanismo explícito. Ninguna corrida se había ejecutado, así que no hay
> dato contaminado. **ADR-015** contenedoriza las dos familias y con eso elimina la
> asimetría de confinamiento que ADR-009 D1 declaraba como limitación (cierra el ítem 11
> de la checklist H6). **ADR-016** congela `evaluacion/protocolo.md` **v1.2** reemplazando
> a ADR-012: se eliminan los topes de presupuesto —la corrida termina cuando termina el
> pipeline— y costo, tiempo y tokens quedan como variables dependientes en vez de topes
> (cierra el ítem 7). Como en la ventana anterior, el contenido de los ADRs reemplazados
> no se edita: sólo cambia su estado.

> **Nota (2026-08-23, segunda sesión del día):** **ADR-017** enmienda la Decisión 3 de
> ADR-015 sin editarla, y sale de la primera invocación real de un CLI dentro del
> contenedor: `claude -p` respondió `Not logged in` porque en macOS la credencial vigente
> vive en el Keychain, mientras que `~/.claude/.credentials.json` —el archivo que D3
> mandaba montar— tenía un token vencido. A pasa a autenticarse con
> `CLAUDE_CODE_OAUTH_TOKEN` (de `claude setup-token`) vía `--env-file`; B conserva el
> bind-mount de su `auth.json`, que sí es un archivo vigente. Es una asimetría de
> plataforma, no de diseño, y se declara en `analisis/amenazas-validez.md`.

> **Nota (2026-08-23, tercera sesión del día):** **ADR-018** agrega una corrida
> **pre-piloto** —dos celdas descartables, una por familia— antes de `piloto-01`. No
> reemplaza nada: el protocolo v1.2, la spec y la partición 465/56 siguen igual. Su
> objeto es que cada componente del pipeline y de la evaluación se ejecute al menos una
> vez sobre un universo reducido de la spec (6 HU de backend, 2 de cliente), para que la
> piloto no se gaste depurando infraestructura. Su Decisión 5 fija además qué se puede
> corregir en `evaluacion/` después de ver una implementación —defectos del harness sí,
> el criterio de un AT no—, regla que vale también para la piloto.

> **Nota (2026-08-23, sobre ADR-019):** sale del primer intento real de que el agente B
> ejecute comandos dentro del contenedor. `-s workspace-write` hacía que **todos**
> fallaran —bubblewrap no puede crear user namespaces con el seccomp por default de
> Docker— sin cortar la corrida: la degradaba en silencio. B pasa a correr sin sandbox
> nativo, con el contenedor como único confinamiento, que es el régimen que A ya tenía y
> la dirección que ADR-015 había fijado. Enmienda la fila «Confinamiento» de la tabla de
> ADR-009 sin editarlo, y deja sin objeto el riesgo de red del ítem 2 de la checklist H6.
