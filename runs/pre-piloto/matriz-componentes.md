# Matriz de componentes — corrida pre-piloto

Qué componente ejercita cada parte de la pre-piloto, con qué evidencia se lo da por
verificado y en qué estado está. Es el instrumento de la corrida: un componente sin
evidencia registrada acá **no** está verificado, por más que la corrida haya terminado.

**Estado al cierre de la pre-piloto (2026-08-24): 37 de 44 componentes verificados.**
De los 7 restantes, 3 son rúbricas manuales que completa el tesista, 1 es su arbitraje,
1 es una decisión suya abierta (el uso del corpus, H-12), 1 es un camino que no llegó a
ocurrir (corte por exit ≠ 0) y 1 tiene residuo declarado (la tarifa de caché del ítem 20).

Estados: `[ ]` sin ejercitar · `[~]` ejercitado con defectos abiertos · `[x]` verificado.

Los defectos que aparezcan se anotan en [`hallazgos.md`](hallazgos.md) y, si tocan
protocolo o metodología, salen por ADR nuevo — nunca editando ADRs aceptados ni `spec/`.

## 1. Orquestación (`pipeline/comun/nucleo.py`)

| # | Componente | Cómo se ejercita | Evidencia | Estado |
|---|---|---|---|---|
| 1.1 | Carga de config, etapas y prompts | dry-run de 2 configs × 3 etapas | exit 0 en las 6; hashes de prompt en el JSONL | [x] verificado 2026-08-23 (en seco) |
| 1.2 | Secuencia de 3 roles por etapa | etapa backend de B, completa | `paso_inicio`/`paso_fin` 1..3 + `fin`, todos exit 0 | [x] 2026-08-24 |
| 1.3 | Sesión fresca por paso | ídem | 3 invocaciones independientes, sin `--resume` | [x] 2026-08-24 |
| 1.4 | Handoff por `.pipeline/` | ídem | `salida_escrita: true` en el paso 2, paso 3 la leyó, sin `handoff_faltante`; la revisión trae 3 puntos con archivo:línea y HU/RN/AT | [x] 2026-08-24 |
| 1.5 | Corte por código de salida ≠ 0 | no ocurrió | los 18 pasos de las 2 celdas salieron con 0; el camino quedó sin ejercitar en real (sí con el CLI simulado) | [~] sin ocurrencia |
| 1.6 | Snapshot por invocación de rol | ídem | 3 snapshots (94, 95, 96 archivos), `ok: true` | [x] 2026-08-24 |
| 1.7 | Repo satélite y layout de logs | `crear-repo-satelite.sh` | 74 archivos, todos bajo `spec/`; `<repo>/../logs/` | [x] verificado 2026-08-23 |

## 2. Contenedores (ADR-015 / ADR-017)

| # | Componente | Cómo se ejercita | Evidencia | Estado |
|---|---|---|---|---|
| 2.1 | Imagen y montajes de A | smoke de 1 invocación | `/repo/spec/` visible, uid=1001(agente) | [x] 2026-08-23 |
| 2.2 | Imagen y montajes de B | ídem | ídem, tras el fix de H-03 | [x] 2026-08-23 |
| 2.3 | Credenciales de A por `--env-file` | smoke de 1 invocación | responde contra `claude-opus-5`, stderr limpio | [x] 2026-08-23 |
| 2.4 | Credenciales de B por bind-mount | ídem | turno completo contra `gpt-5.6-sol` | [x] 2026-08-23 (requirió H-03) |
| 2.5 | Red del contenedor | 2 etapas backend + 1 web, completas | `npm install` resolvió en las dos familias; el nodo del host quedó alcanzable por `--add-host` (H-07 ⇒ ADR-020) | [x] 2026-08-24 |
| 2.6 | No-exposición del holdout | inspección de los montajes efectivos | `evaluacion/` no aparece en ningún `-v` | [x] verificado por `verificar_paridad.py` |

## 3. Modelos y CLI

| # | Componente | Cómo se ejercita | Evidencia | Estado |
|---|---|---|---|---|
| 3.1 | `claude-opus-5` con effort `xhigh` | smoke de 1 invocación | `result` con `total_cost_usd`, 7 turnos, exit 0 | [x] 2026-08-23 |
| 3.2 | `gpt-5.6-sol` con effort `xhigh` | ídem | `turn.completed` con usage, exit 0 | [x] 2026-08-23 |
| 3.3 | Confinamiento de B | smoke de 1 invocación | bwrap no crea namespaces ⇒ B sin shell (H-04); resuelto por ADR-019: sin sandbox nativo, shell exit 0 | [x] 2026-08-23 |
| 3.4 | Delegación en subagentes (ADR-010 D1) | 3 etapas × 2 celdas | A: 1 736/7 612 eventos de subagente. B: 24 `collab_tool_call`, **todos sin receptores** — no delegó (H-22, cierra el ítem 24) | [x] mapeo resuelto |
| 3.5 | Restricción de recuperación web (ADR-008) | 3 etapas × 2 celdas | A: `web_search_requests: 0`. B: **cero** items `web_search` | [x] 2026-08-24 |

## 4. RAG por MCP (ADR-009 D2)

| # | Componente | Cómo se ejercita | Evidencia | Estado |
|---|---|---|---|---|
| 4.1 | Servidor MCP stdio adentro del contenedor | smoke en ambas familias | A: `mcp__corpus__consultar_corpus`. B: `mcp_tool_call server=corpus` | [x] 2026-08-23 |
| 4.2 | Consultas reales al corpus | etapa backend completa | **cero consultas en las dos familias** pese a la épica 06 en el alcance (H-12); el mecanismo funciona: en el smoke, pedido explícitamente, respondió en ambas | [~] hallazgo abierto |
| 4.3 | Resolución del corpus adentro | ídem | sin `FileNotFoundError` | [x] 2026-08-23 |
| 4.4 | Índice BM25 determinista | dry-run | 175 chunks indexados | [x] verificado 2026-08-23 |

## 5. Registro (ADR-003)

| # | Componente | Cómo se ejercita | Evidencia | Estado |
|---|---|---|---|---|
| 5.1 | Esquema del stream de A | 3 etapas de A | tipos confirmados; **varios `result` por invocación** con el mismo acumulado (H-11) y sus `parent_tool_use_id` en null; subagentes atribuidos en los mensajes | [x] cierra el ítem 19 del lado A |
| 5.2 | Esquema del JSONL de B | 3 etapas de B | `turn.completed.usage` = `input_tokens`, `cached_input_tokens`, `cache_write_input_tokens`, `output_tokens`, `reasoning_output_tokens`; items `command_execution`, `mcp_tool_call`, `agent_message` | [x] cierra el ítem 19 del lado B |
| 5.3 | `serializar` no pierde información | 1 107 payloads de B | **0 degradados a `str()`** (cierra el ítem 16) | [x] 2026-08-24 |
| 5.4 | stderr por paso a archivo | etapa backend | un archivo por paso, vacíos en el camino feliz | [x] 2026-08-24 |
| 5.5 | Costo: `total_cost_usd` de A | 3 etapas de A | `costo_por_sesion` agrupa por `session_id` y no suma duplicados: **USD 142,20** en total (H-11 resuelto) | [x] 2026-08-24 |
| 5.6 | Costo: estimador local de B | 3 etapas de B | corregido (H-14): sin tramo largo sobre agregados y con entrada cacheada separada. Da una **cota superior** de USD 262 mientras la tarifa de caché no se ratifique (ítem 20) | [x] con residuo del ítem 20 |

## 6. Evaluación black-box (H5 / ADR-011)

| # | Componente | Cómo se ejercita | Evidencia | Estado |
|---|---|---|---|---|
| 6.1 | Entorno on-chain y contrato de arranque | smoke de backend + evaluación | anvil healthy, USDC-mock desplegado | [x] verificado 2026-08-23 |
| 6.2 | Selección por alcance | `evaluacion/pre-piloto/seleccionar.py` | 78 ATs = 56 black-box (53 funciones) + 22 white-box, 0 sin cubrir | [x] verificado 2026-08-23 |
| 6.3 | Suite contra un SUT real | 53 nodeids contra el backend de B | 47 pasa / 7 falla / 2 skip; las 7 fallas son 404 de épicas fuera del alcance (H-18) | [x] 2026-08-24 |
| 6.4 | `SUITE_CMD_REINICIO_SUT` | ATs de persistencia del alcance | `docker restart` (ADR-021) funciona; el readiness probe estaba roto y se corrigió (H-16): de timeout 121 s a pasar en 3,25 s | [x] 2026-08-24 |
| 6.5 | Helpers contra una implementación ajena | ídem 6.3 | se distinguieron: 2 defectos del harness (H-16, H-17) y 7 falsos positivos por alcance (H-18); **cero** defectos reales del SUT | [x] 2026-08-24 |

## 7. Evaluación white-box (ADR-007 / ADR-010 D3)

| # | Componente | Cómo se ejercita | Evidencia | Estado |
|---|---|---|---|---|
| 7.1 | Briefing y rúbrica white-box | 2 pasadas × 2 celdas | las 4 con 56 items y evidencia citada; el tope de esfuerzo no es verificable (H-19) | [x] 2026-08-24 |
| 7.2 | Validador mecánico | sobre las 4 pasadas | **OK** en las 4, sin una violación del contrato | [x] 2026-08-24 |
| 7.3 | Arbitraje humano y veredicto final | 1 discrepancia (AT-06-03-10 en B) | material preparado en `no-automatizables-b/arbitraje.md`; **el veredicto lo firma el tesista** (ADR-004 §2.5) | [~] pendiente del tesista |
| 7.4 | Tasa de discrepancia entre pasadas | 4 pasadas | **43/44 (97,7 %)** → del orden de 5 arbitrajes en las 4 celdas oficiales | [x] 2026-08-24 |

## 8. Rúbricas manuales y métricas estáticas

| # | Componente | Cómo se ejercita | Evidencia | Estado |
|---|---|---|---|---|
| 8.1 | Rúbrica web (épica 10) | ítems de `HU-10-01` | CSV de veredictos | [ ] |
| 8.2 | Rúbrica mobile (épica 11) | `HU-11-01` + `AT-11-06-01`/`-26` | ídem | [ ] |
| 8.3 | Rúbrica del rol revisor | la revisión de cada etapa + snapshots | CSV de veredictos | [ ] |
| 8.4 | Métricas estáticas | `medir.sh` sobre el backend de B | corre tras instalar el toolchain; contaba la spec y los lockfiles (H-20 ⇒ ADR-022): 32 648 → 5 301 loc | [x] 2026-08-24 |

## 9. Protocolo

| # | Componente | Cómo se ejercita | Evidencia | Estado |
|---|---|---|---|---|
| 9.1 | Smoke check de avance de etapa | backend de A y de B, web de B | backends: `GET /health` OK (el de A informa `chainId: 11155111`, o sea que verificó la red). Web de B: falla en el host y pasa en contenedor (H-15 ⇒ ADR-021) | [x] 3 de 6 etapas |
| 9.2 | Registro de intervenciones y clasificación | smoke de B | INT-01 registrada en el momento con su clasificación | [x] 2026-08-24 |
| 9.3 | Cierre y congelamiento de la corrida | las 2 celdas | manifest §5 completo con costo, tokens y turnos por etapa; logs archivados en `logs/`; repos en sólo lectura con su hash final registrado | [x] 2026-08-24 |
