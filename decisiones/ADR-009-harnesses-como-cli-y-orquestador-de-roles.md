# ADR-009 — Los harnesses pasan a ser los CLI de cada proveedor; orquestador de roles

- **Estado:** **Propuesto** (2026-08-16) — pendiente de ratificación del tesista
- **Fecha:** 2026-08-16
- **Contexto:** ventana H6 (única ventana legítima de ajuste según
  [ADR-004](ADR-004-protocolo-experimental-preregistrado.md)), con la corrida piloto
  todavía sin ejecutar.
- **Reemplaza a:** [ADR-005](ADR-005-arquitectura-pipeline-y-model-ids.md) — este ADR
  restatea sus tres decisiones. Las Decisiones 1 y 2 cambian de mecanismo conservando el
  criterio; la Decisión 3 re-pinnea los model IDs a los flagships vigentes (y con eso
  cierra el ítem 8 de la checklist H6).
- **No afecta a:** [ADR-008](ADR-008-restriccion-recuperacion-web-harness-a.md), cuyo
  criterio se traslada al mecanismo equivalente del CLI (Decisión 5).

## Contexto

ADR-005 construyó los harnesses sobre los SDK de agentes de cada proveedor:
`claude-agent-sdk` en A y `openai-agents` (`SandboxAgent`) en B. Con la piloto sin
correr —ninguna ejecución end-to-end contra la API hasta hoy— aparecen tres motivos
para revisar esa base antes de gastar la ventana H6 en ella:

1. **Reuso de suscripciones.** Los CLI se autentican con la suscripción del tesista;
   los SDK requieren API keys facturadas aparte.
2. **Fragilidad de los adaptadores.** El adaptador B depende de internals verificados
   leyendo el fuente de `agents.sandbox` v0.17.7 (`workspace_root_owned`, perfil
   seatbelt, `TMPDIR`), documentados como tales en `harness_b/correr.py:117-135`. Un
   contrato de línea de comandos + JSONL es una superficie más estable que esa.
3. **Asimetría de scaffolding ya registrada.** El journal del 2026-07-07 la anotó como
   defecto de costura: A perdía su scaffolding nativo mientras B conservaba el suyo. El
   harness A la mitigó appendeando el preset `claude_code`
   (`harness_a/correr.py:104`), es decir, **el harness A ya es el harness de Claude
   Code invocado por librería**. El cambio de fondo está en B.

## Evidencia verificada (2026-08-16, `claude` 2.1.233 / `codex-cli` 0.146.0)

Todo lo que sigue se comprobó ejecutando los CLI en esta máquina; nada se infiere de
documentación.

| Capacidad | Claude Code | Codex CLI |
|---|---|---|
| Modo headless | `-p --output-format stream-json` | `exec --json` (JSONL de eventos) |
| Costo en USD | **Sí**, con auth de suscripción: `total_cost_usd` + `modelUsage` por modelo | **No**: `turn.completed` da tokens (`input/cached/cache_write/output/reasoning`), sin USD |
| Tope de gasto nativo | `--max-budget-usd` | no expone |
| Tope de turnos | no expone | no expone |
| Inyección de prompt propio | `--append-system-prompt` | `-c developer_instructions=…` |
| RAG por MCP stdio | `--mcp-config` + `--strict-mcp-config` | `-c mcp_servers.<n>.command=…` |
| Aislamiento de la config del host | `--setting-sources`, `--strict-mcp-config` | `--ignore-user-config` |
| Sandbox del shell | permission modes; sin sandbox por default en headless | `-s read-only\|workspace-write\|danger-full-access`, con sandbox por default |
| Delegación a sub-agentes | herramienta `Task`, nativa | herramientas `spawn_agent`/`followup_task`/… con agente primario `/root`, nativas y gateadas por `<multi_agent_mode>` a pedido explícito |
| Effort | `--effort low\|medium\|high\|xhigh\|max` | `-c model_reasoning_effort=…`, mismos cinco niveles más `ultra` (con delegación automática); **default del flagship: `low`** |
| Ventana de contexto del flagship | 1 000 000 | 272 000 (`codex debug models`) |

Dos verificaciones instrumentales, hechas con `codex debug prompt-input` (que renderiza
el prompt visible por el modelo):

- `developer_instructions` aparece como primer `input_text` del mensaje `developer`,
  **antes** del scaffolding nativo (skills, permisos), que se conserva íntegro.
- Con la config del host cargada, el prompt incluía bloques ajenos al experimento
  (`<apps_instructions>`, `<plugins_instructions>`, `<recommended_plugins>`) y
  `<skills_instructions>` de 15 485 caracteres; con `CODEX_HOME` limpio esos bloques
  desaparecen y el de skills baja a 5 237. La contaminación por config del host es
  real y medible, y justifica la Decisión 5.

## Decisión 1 — El harness de cada familia es el CLI de su proveedor

Reemplaza a ADR-005 Decisión 1, **conservando su criterio**: stack agéntico nativo de
cada proveedor, en configuración out-of-the-box, sin reimplementar un toolset artificial
común. Cambia sólo la encarnación de ese criterio:

| Celda | Harness |
|-------|---------|
| `a-sin-rag`, `a-con-rag` | `claude -p` (Claude Code CLI) |
| `b-sin-rag`, `b-con-rag` | `codex exec` (Codex CLI) |

Es la comparación producto-contra-producto: el agente de coding que cada proveedor
publica como su oferta principal, que es lo que un equipo real adoptaría — el mismo
argumento con el que ADR-005 justificó rechazar un toolset común.

Lo que sigue siendo **idéntico** entre celdas, auditable en `pipeline/`:

1. Las etapas y su orden (backend → web → mobile), definidas una sola vez en
   `comun/etapas.yaml`.
2. Los prompts —de sistema, de etapa y de rol— como archivos únicos en
   `comun/prompts/`, cargados verbatim por ambos orquestadores.
3. El input: el repo satélite con la spec pinneada a `spec-v1.1` (ADR-006).
4. La herramienta RAG: mismo servidor, mismo índice, mismos parámetros (Decisión 2).
5. Los presupuestos y criterios de intervención (protocolo, ADR-004 y su reemplazo).

**Asimetrías que quedan dentro del factor "pipeline"** y se declaran como limitación en
el cap. 4, sin igualarlas artificialmente:

- **Reporte de costo:** A lo informa nativo; B se estima localmente desde tokens con los
  precios del proveedor, como ya hace `comun/nucleo.py`.
- **Confinamiento:** B sandboxea el shell por default, A no en modo headless.
- **Delegación:** ambos CLI traen primitivas de sub-agentes nativas, con políticas de
  activación distintas (las de Codex están gateadas a pedido explícito). No se
  deshabilitan en ninguno: son parte del stack nativo, no cruzan al otro factor, y su
  uso efectivo **se registra en el JSONL** para el meta-análisis (ADR-003).
- **Punto de inserción del prompt propio:** A appendea, B prependea. Se declara como
  equivalencia funcional, no como identidad.

## Decisión 2 — El RAG se entrega como un único servidor MCP stdio

Se mantiene sin cambios el **algoritmo** de ADR-005 Decisión 2 y su justificación:
BM25 puro (k1=1.5, b=0.75, k=6 pasajes) sobre chunks por sección de los 9 documentos del
corpus congelado (H3), sin modelo de embeddings, determinista y reconstruible bit a bit.
`comun/rag/indice.py` y sus tests no se tocan.

Cambia el **mecanismo de entrega**: en vez de dos integraciones distintas (servidor MCP
in-process en A vía `create_sdk_mcp_server`, `function_tool` en B), se expone un único
servidor MCP stdio que envuelve `indice.py`, consumido por los dos CLI:

- A: `--mcp-config <archivo>` + `--strict-mcp-config`.
- B: `-c mcp_servers.corpus.command=…`.

Esto **mejora** la paridad respecto del diseño anterior: una sola implementación de la
herramienta, una sola descripción (la de `etapas.yaml`), y un único punto donde se
registran las consultas (`consulta_rag`) para el meta-análisis. Los prompts siguen sin
mencionar la herramienta: su disponibilidad es la única diferencia entre celdas con y
sin RAG, y los prompts quedan byte-idénticos entre las 4 celdas.

## Decisión 3 — Re-pinneo a los flagships vigentes

Reemplaza a ADR-005 Decisión 3, **conservando su criterio de pareo**: flagship contra
flagship, el modelo que cada proveedor recomienda para coding agéntico. Los pinneos de
2026-07-05 (`claude-opus-4-8` / `gpt-5.5`) quedaron una generación atrás en las 5 semanas
que la piloto estuvo detenida, y esto también resuelve el ítem 8 de la checklist H6.

| Celda | Model ID | Justificación |
|-------|----------|---------------|
| A | `claude-opus-5` | Flagship de Anthropic para coding agéntico. USD 5/M entrada, 25/M salida; ventana 1M. |
| B | `gpt-5.6-sol` | «Latest frontier agentic coding model» según el catálogo del propio CLI (`codex debug models`, 0.146.0). Ventana 272K. |

Alternativa descartada para A: `claude-fable-5` es el modelo más capaz de Anthropic pero
cuesta USD 10/M entrada y 50/M salida — rompe el pareo por precio que ADR-005 fijó y no
es el que el proveedor posiciona como default de coding.

**Effort fijado explícitamente en `xhigh` en las dos familias.** Es la primera vez que el
pareo necesita este parámetro: los CLI exponen effort y sus defaults **no coinciden**
(`gpt-5.6-sol` trae `default_reasoning_level: low`), así que dejar el default en ambos
sería introducir una diferencia sistemática entre celdas. `xhigh` existe en las dos
familias y es el nivel que cada proveedor recomienda para coding agéntico.

**Asimetría de ventana de contexto — se declara, no se iguala.** ADR-005 pareó ambos
modelos como «1M contexto». El catálogo del CLI de Codex reporta hoy **272 000** tanto
para `gpt-5.6-sol` como para el `gpt-5.5` originalmente pinneado, contra 1M en A. Con
una spec de 57 HUs, es una diferencia que puede afectar cuántas veces cada harness
compacta contexto. Va a `analisis/amenazas-validez.md` como amenaza al pareo, y la
piloto debe registrar los eventos de compactación de ambos.

**Pendiente antes de congelar (bloquea las corridas oficiales, no la piloto):** el precio
por token de `gpt-5.6-sol` **no se pudo verificar desde una fuente primaria** — el
catálogo del CLI expone ventana y niveles de effort pero no precios. La paridad de precio
del criterio de ADR-005 queda sin verificar de ese lado, y de ahí sale además la
estimación de `costo_estimado_usd` del harness B. Verificar contra la documentación de
precios de OpenAI y registrar el dato antes de la primera corrida oficial.

## Decisión 4 — Orquestador por familia; personalidades como prompts de rol

Un orquestador por familia (`pipeline/harness_a/orquestar.py`,
`pipeline/harness_b/orquestar.py`), ambos delgados sobre `comun/`. Su única
responsabilidad es **invocar el CLI**: elegir prompt de sistema, de etapa y de rol;
fijar modelo, effort, herramientas y cwd; y registrar el JSONL. No implementa lógica de
agente, no interpreta la salida del modelo y no decide avance de etapa.

**Personalidades = archivos de prompt de rol**, no primitivas de sub-agentes de cada
proveedor. Un rol es un archivo en `comun/prompts/roles/`, inyectado por el mecanismo
equivalente de cada CLI (`--append-system-prompt` en A, `developer_instructions` en B).
Motivo: apoyar el diseño en `--agents` de Claude contra `spawn_agent` de Codex sería
exactamente el "harness inventado por el tesista" que ADR-005 Decisión 1 rechazó,
movido de capa. Los prompts de rol **no piden delegación**, con lo cual ambos CLI
quedan en su comportamiento por default.

Set de roles inicial, **dos por etapa**:

| Rol | Entrada | Salida |
|-----|---------|--------|
| `implementador` | prompt de etapa + spec | código en el repo satélite |
| `revisor` | prompt de etapa + estado del repo | `.pipeline/revision-<etapa>.md` |

Secuencia por etapa: `implementador` → `revisor` → `implementador` (pase correctivo que
recibe por puntero el archivo de revisión). Cada invocación es una **sesión fresca** del
CLI; el estado compartido es el repo satélite, y el handoff son archivos de nombre
explícito bajo `.pipeline/`, pasados por puntero en el prompt. **No** se usan archivos
de carga automática (`AGENTS.md`, `CLAUDE.md`) como handoff: Codex carga `AGENTS.md` del
workspace y Claude Code no, lo que inyectaría contexto de forma asimétrica.

Consecuencias del set de roles:

- El rol `revisor` **es** el ítem 12 de la checklist H6 ("rúbrica del rol revisor"): si
  el rol entra, la rúbrica se construye y pre-registra antes de H7. Son la misma
  decisión.
- El paralelismo entre etapas queda **excluido**: el protocolo §4 fija orden backend →
  web → mobile con avance gateado por el evaluador humano. El orquestador no auto-avanza
  de etapa.
- El set se valida en la piloto y se congela antes de H7.

## Decisión 5 — Aislamiento, reproducibilidad y traslado de ADR-008

- **A:** `--setting-sources` vacío y `--strict-mcp-config`, para que no entren settings,
  `CLAUDE.md`, plugins ni MCP de la máquina del tesista. `--disallowed-tools WebSearch
  WebFetch` traslada ADR-008 sin cambio de criterio.
- **B:** `--ignore-user-config` en cada invocación. **No** se usa un `CODEX_HOME` limpio:
  `auth.json` vive ahí y vaciarlo rompe la autenticación; `--ignore-user-config` ignora
  la config preservando las credenciales. Codex trae la búsqueda web desactivada por
  default y no se activa, lo que satisface ADR-008 del lado B.
- **Pinneo en el manifest de cada corrida:** versión exacta de cada CLI, además de los
  model IDs y del commit del corpus.

## Alternativas descartadas

- **Swap sólo en A, B sigue en SDK.** Evitaría desviarse del texto de la propuesta, pero
  conserva y agrava la asimetría de scaffolding que el journal del 07-07 registró como
  defecto, y no da el reuso de suscripción en B.
- **No hacer el swap.** Se mantiene la dependencia de internals de `agents.sandbox`
  v0.17.7 y se pierde el reuso de suscripciones. Sin validación end-to-end hundida que
  proteger, el costo de cambiar hoy es el más bajo que va a estar.
- **Igualar las topologías de delegación** deshabilitando `Task` en A. Se descarta por
  el criterio de ADR-008: restringir una capacidad nativa se justifica cuando contamina
  el *otro* factor, y la delegación no cruza factores.

## Consecuencias

- `pipeline/` se reestructura: `comun/` (etapas, prompts incluidos los de rol, RAG con
  su servidor MCP stdio) + `harness_a/orquestar.py` y `harness_b/orquestar.py` +
  `config/` por celda. `verificar_paridad.py` se reescribe contra los nuevos
  invariantes; `correr.py` de ambos harnesses y `pipeline/requirements.txt` (SDKs) se
  retiran.
- **`MAX_TURNS` se retira** de `comun/nucleo.py`. Ningún CLI expone un tope de turnos, y
  el tesista decidió el 2026-08-16 no reponerlo en el orquestador: se corre sin
  presupuesto de turnos. Esto **cierra el ítem 14** de la checklist H6. Se cae el tope,
  **no la métrica**: el orquestador sigue registrando turnos y tokens (ADR-003), y los
  topes de costo y tiempo del protocolo siguen vigentes. El cambio de §6 del protocolo lo
  formaliza el ADR que reemplace a ADR-004 (ítem 9).
- **Regla de scoping de métricas estáticas, a pre-registrar en el protocolo v1.1:** el
  tooling de métricas de H5 excluye `.pipeline/` del cómputo. Debe quedar fijada antes
  de la piloto: ajustar el alcance de una métrica después de ver una implementación
  viola el mismo criterio de congelamiento del protocolo §9.
- **Presupuesto:** con suscripciones, `costo_max_usd = 200` deja de ser el tope
  operativo vinculante y pasan a serlo los rate limits, que son asimétricos entre
  proveedores y no están bajo control del experimento. Es una **amenaza a la validez
  nueva** (`analisis/amenazas-validez.md`) y presiona la ventana de ≤2 semanas del
  protocolo §7. La piloto mide el consumo real y con ese dato se decide suscripción
  contra API key para las 4 oficiales.
- **Desviación de la propuesta aprobada, asumida por el tesista:** el objetivo
  específico 3 del Formulario 1 nombra "Claude Agent SDK y OpenAI Agent SDK". Claude
  Code es el harness del Agent SDK, pero **Codex CLI no es el OpenAI Agents SDK**. La
  desviación se planteó explícitamente y el tesista decidió el 2026-08-16 no elevarla a
  los directores. Queda registrada acá y se declara en el cap. 4.
- **Verificaciones que la piloto debe cerrar,** por haberse comprobado con el oráculo
  `codex debug prompt-input` y no en una corrida real: que `developer_instructions`
  llega efectivamente al modelo en `codex exec`, y el comportamiento de ambos CLI ante
  un rate limit a mitad de etapa (¿pausan? ¿cortan?).
- Si el ADR se rechaza, se vuelve a los harnesses SDK tal como están en el commit
  813e774: nada de lo actual se borra hasta que la piloto valide el reemplazo.
