# ADR-010 — Delegación en subagentes, techo de contexto del harness B y re-pinneo del evaluador

- **Estado:** **Aceptado** (2026-08-16)
- **Fecha:** 2026-08-16
- **Contexto:** ventana H6, con la piloto todavía sin ejecutar. Surge de la asimetría de
  ventana de contexto que [ADR-009](ADR-009-harnesses-como-cli-y-orquestador-de-roles.md)
  declaró (1 000 000 en A contra 272 000 en B) y de la inconsistencia que su re-pinneo
  dejó abierta en [ADR-007](ADR-007-agente-evaluador-white-box.md).
- **Enmienda a:** ADR-009 Decisión 4 (los prompts de rol pasan a instruir delegación) y
  ADR-007 Decisiones 1 y 3.5 (model IDs del evaluador y del espejo). Ninguno de los dos
  se edita: sus decisiones de fondo siguen vigentes salvo en lo que este ADR reemplaza.

## Decisión 1 — Los prompts de rol instruyen delegación en subagentes

ADR-009 Decisión 4 fijó que los prompts de rol **no** piden delegación, para que ambos
CLI quedaran en su comportamiento por default. Se reemplaza esa parte: los prompts de rol
**instruyen delegar en subagentes** el trabajo que sea independiente y acotado.

Motivo, en orden de peso:

1. **Foco.** El agente principal conserva la tarea general y delega los problemas
   acotados, en vez de arrastrar todo el detalle de cada subtarea en su propio contexto.
2. **Alineación con la literatura que la propuesta releva.** MetaGPT, ChatDev y AgentMesh
   —el estado del arte que el objetivo específico 1 pide relevar— son sistemas
   multi-agente con roles. Un pipeline que delega acerca el artefacto a su marco teórico.
3. **Mitiga el techo de contexto de B** (Decisión 2): si ningún agente concentra todo el
   trabajo, ninguno se acerca al umbral de compactación.

Sigue vigente de ADR-009 Decisión 4 todo lo demás: los roles son **prompts** en
`comun/prompts/roles/`, no primitivas de sub-agentes de cada proveedor; el orquestador no
llama `Task` ni `spawn_agent`; el texto de la instrucción es **vendor-neutral y
byte-idéntico** entre las 4 celdas; la delegación la ejecuta cada CLI con su maquinaria
nativa. La secuencia por etapa (implementador → revisor → pase correctivo) no cambia, ni
la prohibición de paralelismo **entre etapas** (protocolo §4). El paralelismo que esta
decisión habilita es **dentro** de una invocación de rol.

**Asimetría de respuesta a una instrucción idéntica — se declara, no se iguala.** El
bloque `<multi_agent_mode>` de Codex mantiene la delegación apagada hasta que se la pide
explícitamente; Claude Opus 5 delega por default y su proveedor recomienda ponerle tope.
La misma instrucción, por lo tanto, **destraba** a B y **puede amplificar** a A. Queda
dentro del factor "pipeline", como las demás asimetrías de ADR-009, y la piloto debe
medir el fan-out efectivo de cada familia para dimensionarla.

**Registro (ADR-003):** el JSONL debe capturar la actividad de subagentes, no sólo la del
agente principal — en A vía los eventos de subagente del `stream-json` (existe
`--forward-subagent-text`), en B vía los eventos de thread. Verificarlo en la piloto.

**Costo asumido:** delegar aumenta el consumo por minuto de las suscripciones. El tesista
lo asumió explícitamente el 2026-08-16. Sigue siendo relevante para el ítem 7 (los rate
limits son el tope vinculante bajo suscripción), no como objeción a esta decisión.

## Decisión 2 — `model_context_window = 1000000` en el harness B

Se fija `-c model_context_window=1000000` en las invocaciones de `codex exec`, idéntico
en las dos celdas B.

**Qué se verificó** (2026-08-16, `codex-cli` 0.146.0, `gpt-5.6-sol`, un turno con relleno
sintético de 1 030 076 caracteres y un marcador al final):

| Configuración | `input_tokens` | Resultado |
|---|---|---|
| `-c model_context_window=1000000` | 294 318 | completa y devuelve el marcador del final |
| sin override (default del CLI) | 294 318 | **idéntico** |

De ahí, tres conclusiones y un límite nuevo:

- **Los 272 000 del catálogo no son un tope a nivel de request.** La API aceptó 294 318
  tokens de input en un turno, con y sin el override. La lectura de ADR-009 —«asimetría
  de ventana de contexto»— era correcta en el número pero imprecisa en el mecanismo: no
  es que B no *pueda* recibir más.
- **El override no fue lo que habilitó ese turno**, y por lo tanto **su efecto real no
  está verificado**. Lo que `model_context_window` gobierna, junto con
  `effective_context_window_percent: 95`, es el umbral en el que el harness
  **auto-compacta** al acumular historia entre turnos: ≈ 258 400 con el default,
  ≈ 950 000 con el override. Un turno único no ejercita eso, porque no hay historia que
  compactar.
- **Se fija igual**, porque el costo de fijarlo es nulo y el beneficio esperado —que B no
  compacte antes que A— es exactamente la asimetría que se quiere cerrar. Pero se declara
  como **hipótesis a validar**: la piloto debe correr una etapa cuya historia supere los
  258 400 tokens y verificar si el harness compacta o no (checklist H6, ítem 22).
- **Límite duro nuevo, verificado:** el CLI rechaza en `turn/start` cualquier input de más
  de **1 048 576 caracteres** (`input_too_large`, `max_chars`), independientemente de los
  tokens. Los prompts de etapa y de rol están muy por debajo, pero un archivo de handoff
  bajo `.pipeline/` podría crecer: si un rol produce una revisión enorme, el pase
  correctivo puede chocar con este techo. La piloto debe vigilarlo.

No hay cambio equivalente en A: su ventana efectiva ya es 1 000 000 (medida en
`modelUsage.contextWindow`).

## Decisión 3 — El evaluador white-box y su espejo se re-pinnean

ADR-009 re-pinneó los modelos **generadores** pero no tocó ADR-007, que dejó el juez
white-box en `claude-opus-4-8` y el chequeo espejo opcional en `gpt-5.5`. Se re-pinnean:

| Rol | ADR-007 (2026-07-06) | Este ADR |
|-----|----------------------|----------|
| Agente evaluador white-box | `claude-opus-4-8` | `claude-opus-5` |
| Chequeo de concordancia espejo (opcional) | `gpt-5.5` | `gpt-5.6-sol` |

**Esto restaura el diseño original de ADR-007, no lo cambia.** Cuando ADR-007 se escribió,
el juez (`claude-opus-4-8`) era el **mismo modelo** que generaba en la celda A, y las
cinco mitigaciones de su Decisión 3 —copia sin `.git`, rúbrica evidence-gated, doble
pasada, auditoría humana del 100 %, espejo del otro proveedor— se diseñaron contra
exactamente ese escenario. El re-pinneo de ADR-009 había roto esa correspondencia por
omisión: dejaba un juez de una generación anterior. Volver a `claude-opus-5` reinstala el
supuesto bajo el que las mitigaciones fueron pre-registradas, y el espejo vuelve a ser el
flagship vigente del otro proveedor.

**Runtime del evaluador.** ADR-007 Decisión 1 dice que el agente se ejecuta «headless con
el Claude Agent SDK ya instalado en `pipeline/`». ADR-009 retira ese SDK, así que el
evaluador pasa a ejecutarse con **`claude -p`**, que da las mismas herramientas que la
evaluación white-box necesita (lectura de archivos y bash). El briefing congelado en
`evaluacion/agente-evaluador/briefing.md` **no se toca**: sigue pasándose verbatim en las
4 celdas.

Todo lo demás de ADR-007 sigue vigente sin cambios: veredictos condicionados a evidencia,
doble pasada independiente, arbitraje y auditoría humana del 100 %, y el carácter de
instrumento del agente (el evaluador de registro sigue siendo el tesista).

## Consecuencias

- `comun/prompts/roles/` incorpora la instrucción de delegación, verbatim e idéntica entre
  celdas; `verificar_paridad.py` debe chequearla como chequea los demás prompts.
- Las invocaciones de `codex exec` llevan `-c model_context_window=1000000`, y el manifest
  de cada corrida lo registra junto al model ID, el `effort` y la versión del CLI.
- `analisis/amenazas-validez.md` suma la asimetría de respuesta a la instrucción de
  delegación y corrige la de ventana de contexto (el número era correcto, el mecanismo no).
- La checklist H6 gana la validación de compactación multi-turno y el control del techo de
  1 MiB por input; el ítem 21 (modelos del evaluador) queda cerrado por la Decisión 3.
- **Nada de esto está implementado**: la reescritura del pipeline sigue siendo el ítem 17.
  Este ADR fija qué debe implementar esa reescritura.
- Si la piloto muestra que el fan-out de A es desproporcionado frente al de B, la
  corrección **no** es tunear la instrucción por familia —eso rompería la paridad de
  prompts— sino declarar la diferencia y, si se decidiera acotarla, hacerlo con un tope
  numérico idéntico en el texto compartido, vía ADR nuevo antes de H7.
