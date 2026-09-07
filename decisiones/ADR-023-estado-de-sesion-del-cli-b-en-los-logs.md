# ADR-023 — El estado de sesión del CLI de B se persiste en los logs de la corrida

- **Estado:** **Propuesto** — implementado y verificado en la sesión del 2026-09-06;
  pendiente de ratificación del tesista antes de `piloto-01`.
- **Fecha:** 2026-09-06
- **Contexto:** ventana H6, cierre de la corrida pre-piloto
  ([ADR-018](ADR-018-corrida-pre-piloto.md)). Sale de investigar la causa del hallazgo
  H-22 (`runs/pre-piloto/hallazgos.md`): «A delega en subagentes y B no».
- **Reemplaza a:** de [ADR-015](ADR-015-agentes-en-contenedores.md), únicamente la
  regla «los montajes de A y B sólo difieren en el archivo de credenciales», que pasa a
  admitir una segunda diferencia declarada. ADR-015 no se edita; el resto de sus
  decisiones queda intacto.

## Contexto

La pre-piloto concluyó (H-22) que B no había delegado en ninguna etapa: sus 24
`collab_tool_call` del stream `--json` eran todos `wait` con `receiver_thread_ids: []`.
Quedaba abierto si B *no podía* delegar en `codex exec` o si *eligió* no hacerlo.

Medido el 2026-09-06 con dos corridas de control en el contenedor de B (CLI 0.146.0, los
mismos flags del orquestador, effort `low`, pedido explícito de lanzar un subagente):

- `codex features list` con `CODEX_HOME` limpio da **`multi_agent  stable  true`**: la
  delegación está habilitada por default en esa versión.
- El modelo llamó a **`spawn_agent`** y el CLI creó un **segundo thread** cuyo rollout
  tiene `session_meta.source.subagent.thread_spawn.parent_thread_id` apuntando al thread
  principal; el subagente ejecutó `echo hola-subagente` y devolvió la salida real.
- El stream `--json` del thread principal **no emitió la llamada `spawn_agent` ni ningún
  evento del subagente**: registró un único `collab_tool_call` de `wait` con
  `receiver_thread_ids: []` — exactamente lo que la pre-piloto había leído como «no
  delegó».
- `turn.completed.usage` del thread principal (29 932 tokens de entrada, 303 de salida)
  **no incluye** los del subagente (19 927 y 98, en su propio `token_count`).

O sea: B sí puede delegar, y el registro de la pre-piloto no permite saber si lo hizo. El
único registro de los subagentes de B son los **rollouts** que el CLI escribe en
`$CODEX_HOME/sessions/AAAA/MM/DD/rollout-<ts>-<thread>.jsonl`, uno por thread. En la
pre-piloto `CODEX_HOME` vivía adentro del contenedor efímero (`--rm`) y se perdió con
cada paso.

Del lado A no hay problema equivalente: `claude -p --forward-subagent-text` emite los
mensajes de subagente con `parent_tool_use_id`, que es lo que `nucleo.es_de_subagente`
lee (1 736 de 7 612 eventos en la pre-piloto).

## Decisión

1. **B monta `<logs>/sesiones-codex/` en `/home/agente/.codex/sessions`, read-write**, en
   toda invocación de rol (`contenedor.ESTADO_CLI`). Queda al lado del JSONL de la etapa
   y se archiva con él (protocolo §10). El orquestador crea el origen antes de cada paso
   (`contenedor.preparar_montajes`), por el mismo motivo de H-03: si lo crea docker, lo
   crea como `root`.
2. **El destino es hermano de `auth.json`**, no un montaje del `.codex` entero: un montaje
   anidado dentro de otro falla en docker (verificado: `mountpoint … is outside of
   rootfs`), y montar el directorio completo obligaría a copiar el `auth.json` del host,
   que ADR-015 D3 quiere read-only.
3. **A no persiste estado de sesión.** Su stream ya registra a los subagentes; agregar un
   montaje «por simetría» crearía en el contenedor de A un directorio `~/.claude` como
   `root` (el problema de H-03) sin ganar registro.
4. **`verificar_paridad.py`** admite exactamente dos diferencias de montaje entre familias
   —el `auth.json` y el estado de sesión de B— y chequea que el segundo vaya read-write,
   bajo los logs de la corrida y como hermano de `auth.json`. **145 chequeos** (143 antes).
5. **Lectura del fan-out de B (ítem 24 de la checklist H6):** se cuenta sobre los rollouts,
   por `session_meta.thread_source == "subagent"` y `parent_thread_id`; los tokens de cada
   subagente salen del último `token_count` de su rollout y **se suman** al consumo de la
   invocación. El `--json` sigue siendo el registro primario del thread principal.

## Consecuencias

- H-22 queda **corregido**: «B no delegó» pasa a «no se sabe» para la pre-piloto, y el
  consumo registrado para B en `manifest-b.yaml` es una **cota inferior** si hubo
  subagentes.
- El ítem 24 de la checklist H6 sigue abierto hasta que `piloto-01` produzca rollouts;
  el ítem 22 (compactación) gana un oráculo: los rollouts registran los eventos de la
  sesión, incluida la compactación si ocurre — a verificar en la piloto.
- `nucleo.costo_estimado_usd` de B **no** suma todavía los subagentes: se implementa
  cuando la piloto muestre la forma real de esos rollouts, para no inventar el esquema.
- Verificado end-to-end el 2026-09-06: con los dos montajes como los arma el orquestador,
  una invocación real de `codex exec` escribió su rollout en
  `<logs>/sesiones-codex/2026/09/07/rollout-…jsonl` del host y salió con exit 0.
