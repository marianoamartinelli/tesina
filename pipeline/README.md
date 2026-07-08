# Pipeline — harness de agentes

Código y configuración de los dos harness del experimento factorial 2×2
(hito H4; arquitectura y model IDs fijados por
[ADR-005](../decisiones/ADR-005-arquitectura-pipeline-y-model-ids.md)):

- **Harness A:** Claude Agent SDK (`claude-agent-sdk`), modelo `claude-opus-4-8`.
- **Harness B:** OpenAI Agents SDK (`openai-agents`, Sandbox Agents), modelo `gpt-5.5`.

## Arquitectura

```
pipeline/
├── comun/                  # TODO lo compartido entre celdas (la paridad vive acá)
│   ├── etapas.yaml         # etapas + prompts referenciados + config RAG (única fuente)
│   ├── prompts/            # prompt de sistema + un prompt por etapa (verbatim)
│   ├── rag/indice.py       # índice BM25 determinista sobre el corpus (con tests)
│   └── nucleo.py           # carga de config/prompts/índice, log JSONL, CLI compartido
├── harness_a/correr.py     # adaptador fino al Claude Agent SDK
├── harness_b/correr.py     # adaptador fino al OpenAI Agents SDK
├── config/<celda>.yaml     # una config declarativa por celda (factores + ruta a etapas)
├── verificar_paridad.py    # chequeo mecánico de paridad (correr antes de cada corrida)
└── requirements.txt        # versiones exactas pinneadas
```

**Paridad estructural:** ningún `correr.py` define prompts, etapas, parámetros de
RAG ni lógica de carga propios; todo eso vive una sola vez en `comun/` y ambos
adaptadores lo consumen vía `comun/nucleo.py`. Cada harness aporta únicamente su
stack agéntico nativo (ADR-005, Decisión 1), y en ambos el prompt de sistema
compartido se **compone** con el scaffolding nativo del SDK — nunca lo reemplaza
(A: preset `claude_code` + `append`; B: prompt base del `SandboxAgent` +
`instructions`):

- **A:** toolset nativo de coding del Claude Agent SDK (Read/Write/Edit/Bash/…)
  con `cwd` = repo satélite, `system_prompt` = preset `claude_code` con el prompt
  compartido en `append` (espejo de la composición base+`instructions` de B),
  `permission_mode="bypassPermissions"` (corrida headless), `setting_sources=[]`
  (aislado de settings/CLAUDE.md de la máquina) y
  `disallowed_tools=["WebSearch", "WebFetch"]`: sin recuperación web indexada,
  para no contaminar el factor RAG
  ([ADR-008](../decisiones/ADR-008-restriccion-recuperacion-web-harness-a.md),
  propuesto — el canal residual por shell con red abierta queda igual en ambos
  harnesses).
- **B:** `SandboxAgent` (capabilities default: shell + archivos + `apply_patch`)
  sobre `UnixLocalSandboxClient` con `Manifest(root=<repo satélite>)`: el
  workspace del sandbox **es** el repo satélite en el filesystem del host. Con un
  root custom el SDK marca `workspace_root_owned=False`, por lo que la limpieza
  de la sesión no borra el repo (verificado contra el código de `openai-agents`
  0.17.7). Se corre con `tracing_disabled=True` para no subir trazas a la
  plataforma de OpenAI (el registro del experimento es el JSONL local). El
  manifest fija `TMPDIR` en `<repo-satelite>/../tmp-sandbox`: el seatbelt de
  macOS deniega escribir el TMPDIR heredado (ver "Pendiente para la piloto").

Único parámetro no-default compartido: `MAX_TURNS = 500` (en `comun/nucleo.py`),
tope de seguridad contra loops descontrolados, aplicado en ambos harnesses.

## Cómo correr una etapa

```bash
# instalar dependencias pinneadas (una vez)
.venv/bin/pip install -r pipeline/requirements.txt

# verificar paridad ANTES de cada corrida (protocolo §2)
.venv/bin/python pipeline/verificar_paridad.py

# correr una etapa de una celda (ejemplos)
cd pipeline/harness_a
../../.venv/bin/python correr.py --config ../config/a-con-rag.yaml \
    --repo /ruta/al/repo-satelite --etapa backend

cd pipeline/harness_b
../../.venv/bin/python correr.py --config ../config/b-con-rag.yaml \
    --repo /ruta/al/repo-satelite --etapa backend
```

- El contrato de CLI es idéntico en ambos harnesses:
  `--config <celda>.yaml --repo <repo-satelite> --etapa backend|web|mobile`
  (más `--dry-run`, ver abajo). Cada `correr.py` rechaza configs del harness ajeno.
- **Una corrida de agente por etapa**: el prompt de la etapa (verbatim desde
  `comun/prompts/`) es el único input; el avance a la etapa siguiente lo decide
  el humano según el smoke-check del protocolo (ADR-004), no el harness.
- Credenciales: harness A requiere `ANTHROPIC_API_KEY`; harness B, `OPENAI_API_KEY`.
- **Registro**: cada etapa escribe
  `<repo-satelite>/../logs/<celda>-<etapa>-<timestamp>.jsonl` con un evento por
  línea (flush línea a línea: una corrida interrumpida conserva todo lo emitido):
  evento `inicio` (modelo, versión de SDK, SHA-256 de los prompts, config RAG),
  los mensajes/ítems del agente (incluidas las consultas RAG; en B, además, un
  `uso_parcial` por pedido a la API) y `resumen_final` al cierre — también al
  agotar `max_turns`, en ambos harnesses. Sólo un error inesperado del harness
  deja como último evento un `error_harness` sin resumen.

### Smoke check del backend (entorno on-chain)

El criterio de avance de la etapa backend (`etapas.yaml`) es que el backend
levante y responda el health-check que su README documenta. La spec exige
verificar `eth_chainId == 11155111` al iniciar
(`spec/07-depositos-on-chain/README.md`): con el nodo caído aplica **reintentos
con backoff** (el proceso puede llegar a servir HTTP igual), pero un `chainId`
distinto ⇒ **terminación con error**. Para que el smoke se haga con los mismos
valores pre-registrados en todas las celdas, el operador levanta el entorno
on-chain de `evaluacion/suite-at/entorno/` antes de verificar el arranque:

```bash
cd evaluacion/suite-at/entorno
docker compose up -d --wait   # nodo anvil en http://127.0.0.1:8545 (chainId 11155111)
python desplegar-usdc.py      # imprime dirección del USDC-mock y bloque de despliegue
```

y configura el SUT según el README del repo satélite con esos valores: URL RPC
`http://127.0.0.1:8545`, la dirección del USDC-mock y el bloque de inicio que
imprime `desplegar-usdc.py`. El entorno on-chain es **infraestructura
compartida** (nodo + contrato mock): usarlo durante la generación **no expone la
suite de ATs** — los tests del holdout nunca entran al repo satélite ni al
contexto del agente.

### Monitoreo de presupuesto durante la corrida

El tope operativo principal es `costo_max_usd = 200` por corrida (ADR-004); el
operador lo vigila sobre el JSONL en vivo:

- **B**: eventos `uso_parcial` (uno por pedido a la API) con tokens acumulados y
  `costo_estimado_usd` — misma estimación y salvedad que `resumen_final`
  (precios planos de ADR-005, sin descuento por caché). Si la corrida se corta
  antes del resumen, el último `uso_parcial` preserva el costo consumido.
- **A**: el `usage` de cada evento `mensaje` de tipo `AssistantMessage` es **por
  llamada a la API, no acumulado**: para monitorear hay que acumular sobre el
  JSONL (p. ej. `tail` + suma). El `total_cost_usd` nativo del SDK recién llega
  en el `ResultMessage` final.
- La verdad final, en ambos casos, son los **dashboards de billing** de cada
  proveedor.

### Dry-run (sin API keys)

```bash
python correr.py --config ../config/a-con-rag.yaml --repo /tmp/repo-prueba \
    --etapa backend --dry-run
```

Carga config + etapas + prompts + índice RAG, construye las opciones/el agente
reales del SDK y muestra qué ejecutaría (modelo, prompts con hash, herramienta
RAG, workspace), sin llamar a ninguna API. Verificado para las 4 celdas.

## El conmutador RAG

En celdas con `rag: true`, ambos harnesses registran una herramienta
`consultar_corpus(consulta: str) -> str` que llama a
`IndiceCorpus.desde_directorio(corpus).formatear(consulta, k=6)` — la
implementación es **una sola función** en `comun/nucleo.py`
(`funcion_consultar_corpus`); cada SDK sólo la envuelve con su mecanismo nativo
(A: servidor MCP in-process, nombre calificado `mcp__corpus__consultar_corpus`;
B: `function_tool` con `name_override`/`description_override`). El nombre, la
descripción, el corpus y el `k` salen de `comun/etapas.yaml` (clave `rag`). Los
prompts **no mencionan la herramienta**: su disponibilidad es la única
diferencia entre celdas con y sin RAG (ADR-005, Decisión 2). En celdas con
`rag: false` la herramienta no se registra y el índice ni se construye.

## Qué garantiza `verificar_paridad.py`

Sale con código ≠ 0 si se rompe cualquiera de estas condiciones:

1. Las 4 configs oficiales tienen exactamente los campos
   `{celda, harness, modelo, rag, etapas}` y **sólo difieren** en los factores
   (`celda`, `harness`, `modelo`, `rag`).
2. Los pares (harness, modelo) son exactamente los de ADR-005
   (`a`/`claude-opus-4-8`, `b`/`gpt-5.5`) y cada harness tiene una celda con
   RAG y una sin.
3. Las 4 configs resuelven al **mismo** `etapas.yaml` y los prompts que ese
   archivo referencia existen y no están vacíos (⇒ mismos archivos de prompt
   para las 4 celdas).
4. Los parámetros BM25 de `etapas.yaml` coinciden con las constantes de
   `comun/rag/indice.py` (k1=1.5, b=0.75, k=6).
5. Los SHA-256 de `corpus/documentos/*` coinciden con el manifest congelado de
   H3 (`corpus/manifest.md`), sin archivos de más ni de menos.

Estado al cierre de H4: los 39 chequeos pasan; el camino negativo (config
adulterada ⇒ exit 1) fue probado y revertido.

## Pendiente para la piloto (H6)

Lo que **no** se pudo validar sin API keys (todo marcado con
`# PENDIENTE-PILOTO:` en el código donde corresponde):

- **Ejecución real end-to-end** de ambos harnesses: ningún `correr.py` llamó
  todavía a una API; sólo se validaron los dry-runs, la construcción de
  opciones/agentes y las firmas contra la doc oficial y el código instalado de
  los SDKs (`claude-agent-sdk` 0.2.110, `openai-agents` 0.17.7). La ventana
  piloto cubre ambos harnesses: `config/piloto-01.yaml` (A) y
  `config/piloto-02.yaml` (B), las dos descartables.
- **Costo del harness B**: el OpenAI Agents SDK expone tokens
  (`Usage.input_tokens/output_tokens`) pero no costo monetario; los eventos
  `uso_parcial` y el `resumen_final` registran una **estimación** con los
  precios de ADR-005 (sin descuento por caché). Contrastar contra el dashboard
  de billing en la piloto. El harness A sí registra el `total_cost_usd` nativo
  del SDK.
- **Confinamiento del harness A**: se corre con `permission_mode="bypassPermissions"`
  (headless, sin prompts interactivos); el confinamiento al repo satélite lo da
  el protocolo (repo dedicado + supervisión), no el SO. Ese confinamiento es
  además una **condición de no-exposición del holdout** (protocolo §9): sin
  sandbox, el Bash y la tool Read de A pueden leer fuera de su cwd, incluida
  `evaluacion/`. Evaluar en la piloto `SandboxSettings(enabled=True)` — aísla
  sólo los comandos Bash; la restricción de lectura de la tool Read va por deny
  rules de permisos, no por el sandbox — verificando que no rompa builds que
  necesitan red (npm/pip install). Si la asimetría de confinamiento A/B no se
  iguala, se declara como limitación en la tesis.
- **Seatbelt de B**: verificado contra el código del SDK y probado bajo el
  seatbelt: la red **no** está bloqueada (el perfil arranca con `(allow
  default)` y no tiene reglas de red, así que TCP directo y `npm install`
  funcionan) y **docker sí funciona** (el connect al socket es una operación de
  red permitida). El riesgo específico es `$TMPDIR`: el perfil deniega
  `file-write*` sobre el TMPDIR heredado (`/var/folders/…`, bajo `/private`) y
  las herramientas node que usan `os.tmpdir()` sin fallback (metro/expo,
  node-gyp, postinstall scripts) fallarían con EPERM; `npm install` puro y
  pip/Python no se ven afectados. Mitigado fijando `TMPDIR` a
  `<repo-satelite>/../tmp-sandbox` vía el manifest del sandbox — a validar en
  piloto-02 (npm install, npx tsc, expo export).
- **Semántica de `max_turns`**: en A un turno es un intercambio
  usuario/asistente; en B, una invocación al modelo dentro del loop. `MAX_TURNS=500`
  es un tope de seguridad holgado en ambos, pero la equivalencia exacta se
  observará en la piloto (los cortes reales los dan los presupuestos de ADR-004).
- **Streaming/level de detalle de los logs**: en B se registran los
  `RunItemStreamEvent` (mensajes, tool calls, outputs) y se omiten los deltas
  token a token por volumen; en A se registran los mensajes completos del
  stream de `query()`. Ajustar granularidad si la piloto muestra que falta o
  sobra detalle para el meta-análisis.
- **Serialización de eventos exóticos**: `comun.nucleo.serializar` degrada a
  `str()` cualquier objeto no dataclass/pydantic; revisar en los logs de la
  piloto que no se pierda información relevante.

## Principios de diseño (paridad entre condiciones)

1. **Sólo varían los dos factores:** modelo subyacente y disponibilidad de RAG.
   Todo lo demás — etapas, prompts, herramienta RAG, presupuestos — es
   equivalente entre celdas y auditable en este directorio.
2. **Model IDs pinneados** por ADR-005; se registran junto con las versiones de
   SDK en el manifest de cada corrida.
3. **RAG conmutable** por configuración, sin cambiar el resto del pipeline.
4. Todo cambio al pipeline posterior a la corrida piloto y anterior a las
   oficiales se registra en el journal; después de la primera corrida oficial,
   el pipeline queda **congelado** hasta terminar las 4.
