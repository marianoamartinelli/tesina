# Matriz de componentes — corrida pre-piloto

Qué componente ejercita cada parte de la pre-piloto, con qué evidencia se lo da por
verificado y en qué estado está. Es el instrumento de la corrida: un componente sin
evidencia registrada acá **no** está verificado, por más que la corrida haya terminado.

Estados: `[ ]` sin ejercitar · `[~]` ejercitado con defectos abiertos · `[x]` verificado.

Los defectos que aparezcan se anotan en [`hallazgos.md`](hallazgos.md) y, si tocan
protocolo o metodología, salen por ADR nuevo — nunca editando ADRs aceptados ni `spec/`.

## 1. Orquestación (`pipeline/comun/nucleo.py`)

| # | Componente | Cómo se ejercita | Evidencia | Estado |
|---|---|---|---|---|
| 1.1 | Carga de config, etapas y prompts | dry-run de 2 configs × 3 etapas | exit 0 en las 6; hashes de prompt en el JSONL | [x] verificado 2026-08-23 (en seco) |
| 1.2 | Secuencia de 3 roles por etapa | corrida real de la etapa backend | eventos `paso_inicio`/`paso_fin` con orden 1..3 | [ ] |
| 1.3 | Sesión fresca por paso | ídem | 3 procesos distintos, sin `--resume` | [ ] |
| 1.4 | Handoff por `.pipeline/` | paso 2 escribe la revisión, paso 3 la lee | `revision-backend.md` existe; sin `handoff_faltante` | [ ] |
| 1.5 | Corte por código de salida ≠ 0 | sólo si ocurre | evento `corte` y no continúa | [ ] |
| 1.6 | Snapshot por invocación de rol | corrida real | `…-snapshots/pasoN-rol/` con conteo de archivos | [ ] |
| 1.7 | Repo satélite y layout de logs | `crear-repo-satelite.sh` | 74 archivos, todos bajo `spec/`; `<repo>/../logs/` | [x] verificado 2026-08-23 |

## 2. Contenedores (ADR-015 / ADR-017)

| # | Componente | Cómo se ejercita | Evidencia | Estado |
|---|---|---|---|---|
| 2.1 | Imagen y montajes de A | corrida real de A | el CLI corre en `/repo`; escribe en el repo del host | [ ] |
| 2.2 | Imagen y montajes de B | corrida real de B | ídem | [ ] |
| 2.3 | Credenciales de A por `--env-file` | corrida real de A | ninguna respuesta `Not logged in` en stderr | [ ] |
| 2.4 | Credenciales de B por bind-mount | corrida real de B | ídem | [ ] |
| 2.5 | Red del contenedor | `npm install` / `expo export` de las 3 etapas | builds que resuelven dependencias; hosts tocados, al manifest | [ ] |
| 2.6 | No-exposición del holdout | inspección de los montajes efectivos | `evaluacion/` no aparece en ningún `-v` | [x] verificado por `verificar_paridad.py` |

## 3. Modelos y CLI

| # | Componente | Cómo se ejercita | Evidencia | Estado |
|---|---|---|---|---|
| 3.1 | `claude-opus-5` con effort `xhigh` | corrida real de A | evento `inicio` + el CLI no rechaza los flags | [ ] |
| 3.2 | `gpt-5.6-sol` con effort `xhigh` | corrida real de B | ídem | [ ] |
| 3.3 | Sandbox de B con red (`workspace-write`) | etapa backend de B | riesgo abierto: ítem 2 de la checklist H6; si `npm install` falla, `-c sandbox_workspace_write.network_access=true` | [ ] |
| 3.4 | Delegación en subagentes (ADR-010 D1) | corrida real, ambas familias | eventos con `subagente: true` en A; mapeo por decidir en B (ítem 24) | [ ] |
| 3.5 | Restricción de recuperación web (ADR-008) | corrida real, ambas familias | cero eventos `web_search`/`WebFetch` en los JSONL | [ ] |

## 4. RAG por MCP (ADR-009 D2)

| # | Componente | Cómo se ejercita | Evidencia | Estado |
|---|---|---|---|---|
| 4.1 | Servidor MCP stdio adentro del contenedor | ambas celdas (las dos tienen RAG) | el CLI lista `consultar_corpus` sin error de arranque | [ ] |
| 4.2 | Consultas reales al corpus | la épica 06 del alcance (BIP-32/39/44) | líneas en `…-rag.jsonl` con celda/etapa/rol/paso | [ ] |
| 4.3 | Resolución del corpus adentro | ídem | sin `FileNotFoundError: /corpus/documentos` | [ ] |
| 4.4 | Índice BM25 determinista | dry-run | 175 chunks indexados | [x] verificado 2026-08-23 |

## 5. Registro (ADR-003)

| # | Componente | Cómo se ejercita | Evidencia | Estado |
|---|---|---|---|---|
| 5.1 | Esquema del stream de A | corrida real de A | tipos de evento observados, al journal (ítem 19 H6) | [ ] |
| 5.2 | Esquema del JSONL de B | corrida real de B | nombres exactos de los campos de tokens de `turn.completed` (ítem 19) | [ ] |
| 5.3 | `serializar` no pierde información | inspección del JSONL contra el stream crudo | ningún payload degradado a `str()` (ítem 16) | [ ] |
| 5.4 | stderr por paso a archivo | corrida real | `…-stderr-pasoN.txt` por invocación | [ ] |
| 5.5 | Costo: `total_cost_usd` de A | corrida real de A | campo presente en los eventos finales | [ ] |
| 5.6 | Costo: estimador local de B | post-proceso del JSONL de B | `costo_estimado_usd` contra el dashboard de OpenAI (ítem 20) | [ ] |

## 6. Evaluación black-box (H5 / ADR-011)

| # | Componente | Cómo se ejercita | Evidencia | Estado |
|---|---|---|---|---|
| 6.1 | Entorno on-chain y contrato de arranque | smoke de backend + evaluación | anvil healthy, USDC-mock desplegado | [x] verificado 2026-08-23 |
| 6.2 | Selección por alcance | `evaluacion/pre-piloto/seleccionar.py` | 78 ATs = 56 black-box (53 funciones) + 22 white-box, 0 sin cubrir | [x] verificado 2026-08-23 |
| 6.3 | Suite contra un SUT real | correr los 53 nodeids contra el backend generado | `resultados-at.csv` de la pre-piloto | [ ] |
| 6.4 | `SUITE_CMD_REINICIO_SUT` | los ATs de persistencia del alcance | ningún skip por falta de la variable | [ ] |
| 6.5 | Helpers contra una implementación ajena | ídem 6.3 | fallas del harness distinguidas de fallas del SUT | [ ] |

## 7. Evaluación white-box (ADR-007 / ADR-010 D3)

| # | Componente | Cómo se ejercita | Evidencia | Estado |
|---|---|---|---|---|
| 7.1 | Briefing y rúbrica white-box | 2 pasadas sobre los 22 ATs del alcance | `pasada-1.yaml`, `pasada-2.yaml` | [ ] |
| 7.2 | Validador mecánico | `validar-resultados.py` sobre cada pasada | exit 0 antes del arbitraje | [ ] |
| 7.3 | Arbitraje humano y veredicto final | discrepancias entre pasadas | `veredicto-final.yaml` validado con `--final` | [ ] |
| 7.4 | Tasa de discrepancia entre pasadas | conteo | dato para calibrar el costo de H8 | [ ] |

## 8. Rúbricas manuales y métricas estáticas

| # | Componente | Cómo se ejercita | Evidencia | Estado |
|---|---|---|---|---|
| 8.1 | Rúbrica web (épica 10) | ítems de `HU-10-01` | CSV de veredictos | [ ] |
| 8.2 | Rúbrica mobile (épica 11) | `HU-11-01` + `AT-11-06-01`/`-26` | ídem | [ ] |
| 8.3 | Rúbrica del rol revisor | la revisión de cada etapa + snapshots | CSV de veredictos | [ ] |
| 8.4 | Métricas estáticas | `medir.sh` sobre los dos repos satélite | `metricas-estaticas.csv` | [ ] |

## 9. Protocolo

| # | Componente | Cómo se ejercita | Evidencia | Estado |
|---|---|---|---|---|
| 9.1 | Smoke check de avance de etapa | las 3 etapas de cada celda | health-check documentado y respondiendo | [ ] |
| 9.2 | Registro de intervenciones y clasificación | cada intervención, en el momento | `intervenciones.md` con causa raíz | [ ] |
| 9.3 | Cierre y congelamiento de la corrida | al terminar cada celda | manifest §5 completo | [ ] |
