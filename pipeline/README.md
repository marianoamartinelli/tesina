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
stack agéntico nativo (ADR-005, Decisión 1):

- **A:** toolset nativo de coding del Claude Agent SDK (Read/Write/Edit/Bash/…)
  con `cwd` = repo satélite, `permission_mode="bypassPermissions"` (corrida
  headless) y `setting_sources=[]` (aislado de settings/CLAUDE.md de la máquina).
- **B:** `SandboxAgent` (capabilities default: shell + archivos + `apply_patch`)
  sobre `UnixLocalSandboxClient` con `Manifest(root=<repo satélite>)`: el
  workspace del sandbox **es** el repo satélite en el filesystem del host. Con un
  root custom el SDK marca `workspace_root_owned=False`, por lo que la limpieza
  de la sesión no borra el repo (verificado contra el código de `openai-agents`
  0.17.7). Se corre con `tracing_disabled=True` para no subir trazas a la
  plataforma de OpenAI (el registro del experimento es el JSONL local).

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
  línea (flush línea a línea: una corrida interrumpida conserva todo): evento
  `inicio` (modelo, versión de SDK, SHA-256 de los prompts, config RAG), los
  mensajes/ítems del agente (incluidas las consultas RAG), y `resumen_final`
  (turnos, tokens, duración y costo — ver limitaciones).

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
  los SDKs (`claude-agent-sdk` 0.2.110, `openai-agents` 0.17.7).
- **Costo del harness B**: el OpenAI Agents SDK expone tokens
  (`Usage.input_tokens/output_tokens`) pero no costo monetario; el
  `resumen_final` registra una **estimación** con los precios de ADR-005 (sin
  descuento por caché). Contrastar contra el dashboard de billing en la piloto.
  El harness A sí registra el `total_cost_usd` nativo del SDK.
- **Confinamiento del harness A**: se corre con `permission_mode="bypassPermissions"`
  (headless, sin prompts interactivos); el confinamiento al repo satélite lo da
  el protocolo (repo dedicado + supervisión), no el SO. Evaluar en la piloto si
  `SandboxSettings(enabled=True)` aísla bash sin romper builds que necesitan
  red (npm/pip install). En B, el seatbelt de `UnixLocalSandboxClient` es el
  comportamiento nativo del SDK y puede imponer sus propias restricciones de
  red/paths a los comandos del agente: observar en la piloto si bloquea
  `npm install` o similares.
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
