# Pipeline — orquestación de los CLI de agentes

Código y configuración de los dos harnesses del experimento factorial 2×2 (hito H4,
reescrito en la ventana H6). La arquitectura la fijan
[ADR-009](../decisiones/ADR-009-harnesses-como-cli-y-orquestador-de-roles.md) y
[ADR-010](../decisiones/ADR-010-delegacion-contexto-y-evaluador.md), ambos Aceptados,
que reemplazan a [ADR-005](../decisiones/ADR-005-arquitectura-pipeline-y-model-ids.md):

- **Harness A:** Claude Code CLI (`claude -p`), modelo `claude-opus-5`.
- **Harness B:** Codex CLI (`codex exec`), modelo `gpt-5.6-sol`.
- **Effort `xhigh`** en las 4 celdas; los defaults de cada CLI no coinciden.

> Ninguno de los dos orquestadores se ejecutó todavía contra los CLI de verdad: lo
> validado hasta hoy son los dry-runs de las 6 configs en las 3 etapas, la paridad
> mecánica, las verificaciones de flags contra `claude --help` / `codex exec --help` /
> `codex debug prompt-input` de las versiones instaladas (2.1.233 y 0.146.0), el
> servidor MCP hablado a mano por stdio, y el **bucle de ejecución completo corrido
> contra un CLI simulado** (un script que emite el stream JSON esperado): eso ejercita
> el registro del JSONL, la atribución a subagentes, el handoff bajo `.pipeline/` y el
> corte por código de salida ≠ 0, sin gastar suscripción. Lo que queda es el
> comportamiento de los CLI reales; la corrida piloto es esa validación (ver
> "Pendiente para la piloto").

## Arquitectura

```
pipeline/
├── comun/                      # TODO lo compartido entre celdas (la paridad vive acá)
│   ├── etapas.yaml             # etapas, roles, secuencia y config RAG (única fuente)
│   ├── prompts/                # prompt de sistema + uno por etapa (verbatim)
│   │   └── roles/              # implementador.md, revisor.md
│   ├── rag/indice.py           # índice BM25 determinista sobre el corpus (con tests)
│   ├── rag/servidor_mcp.py     # servidor MCP stdio que expone el índice
│   └── nucleo.py               # config, prompts, pasos, bucle de ejecución, log JSONL
├── harness_a/orquestar.py      # arma la línea de comandos de `claude -p`
├── harness_b/orquestar.py      # arma la línea de comandos de `codex exec`
├── config/<celda>.yaml         # una config declarativa por celda
├── verificar_paridad.py        # chequeo mecánico (correr antes de cada corrida)
├── requirements.txt            # dependencias Python pinneadas (los CLI van aparte)
├── harness_a/correr.py         # pipeline SDK anterior — no se borra (ver abajo)
└── harness_b/correr.py         # ídem
```

**Paridad estructural:** ningún `orquestar.py` define prompts, etapas, parámetros de
RAG ni lógica de carga propios, y tampoco su propio bucle de ejecución: todo eso vive
una sola vez en `comun/` y ambos adaptadores lo consumen vía `comun/nucleo.py`. Lo
único que aporta cada orquestador es `construir_comando` —la traducción a la línea de
comandos de su proveedor—; quién lanza el proceso, escribe el prompt por stdin, lee el
stream, crea `.pipeline/` y registra el JSONL es `nucleo.correr_etapa` /
`nucleo.ejecutar_paso`, idéntico para las dos familias. El stack agéntico que corre
adentro es el nativo de cada CLI (ADR-009, Decisión 1).

## Los dos orquestadores

Cada invocación de rol es una **sesión fresca** del CLI (no se usa `--resume` ni
`codex exec resume`): el estado compartido entre pasos es el repo satélite y el
handoff son archivos bajo `.pipeline/` pasados por puntero en el prompt.

| Aspecto | Harness A (`claude -p`) | Harness B (`codex exec`) |
|---|---|---|
| Modo headless | `-p --output-format stream-json --verbose` | `exec --json` |
| Modelo / effort | `--model` / `--effort xhigh` | `-m` / `-c model_reasoning_effort="xhigh"` |
| Prompt propio | `--append-system-prompt` (appendea) | `-c developer_instructions=…` (prependea) |
| Prompt del paso | por stdin | por stdin (`-` como prompt) |
| Aislamiento del host | `--setting-sources ""` + `--strict-mcp-config` | `--ignore-user-config` |
| ADR-008 (recuperación web) | `--disallowed-tools WebSearch,WebFetch` | búsqueda web desactivada por default; no se activa |
| RAG (sólo celdas con RAG) | `--mcp-config <archivo>` | `-c mcp_servers.corpus.command/.args` |
| Subagentes en el log | `--forward-subagent-text` | eventos de thread (mapeo sin verificar) |
| Contexto | ventana efectiva 1 000 000 | `-c model_context_window=1000000` (ADR-010 D2) |
| Confinamiento | `--dangerously-skip-permissions` (sin sandbox del SO) | `-s workspace-write` |
| cwd / workspace | `cwd` del proceso = repo satélite | ídem, más `-C <repo>` |

Detalles que no son obvios y están verificados en las versiones instaladas:

- `--verbose` **no es opcional** en A: el CLI rechaza `--print` con
  `--output-format=stream-json` sin él.
- `--permission-mode bypassPermissions` requiere que la sesión se haya lanzado con
  `--dangerously-skip-permissions`, así que se usa directamente ese flag.
- `--disallowed-tools` y `--mcp-config` son variádicos: se les pasa **un solo valor**
  (lista separada por comas en el primero) para que no se traguen los flags
  siguientes.
- En B, el lado derecho de `-c clave=valor` se parsea como TOML: el orquestador lo
  serializa con `json.dumps`, que produce TOML válido para strings, listas y enteros,
  en vez de depender del fallback a literal crudo.
- `codex debug prompt-input` con los `-c` que arma el orquestador muestra el prompt
  compuesto (sistema + rol) como **primer** `input_text` del mensaje `developer`, y
  el resto del scaffolding nativo intacto.

## Cómo correr una etapa

```bash
# verificar paridad ANTES de cada corrida (protocolo §2)
.venv/bin/python pipeline/verificar_paridad.py

# correr una etapa de una celda (ejemplos)
.venv/bin/python pipeline/harness_a/orquestar.py --config pipeline/config/a-con-rag.yaml \
    --repo /ruta/al/repo-satelite --etapa backend

.venv/bin/python pipeline/harness_b/orquestar.py --config pipeline/config/b-con-rag.yaml \
    --repo /ruta/al/repo-satelite --etapa backend
```

- El contrato de CLI es idéntico en ambos:
  `--config <celda>.yaml --repo <repo-satelite> --etapa backend|web|mobile`, más
  `--dry-run`. Cada orquestador rechaza configs del harness ajeno.
- **Tres invocaciones por etapa** (implementador → revisor → implementador), definidas
  en `comun/etapas.yaml`. El avance a la etapa siguiente lo decide el evaluador humano
  según el smoke-check del protocolo, no el orquestador.
- Credenciales: las del `claude` y el `codex` instalados en la máquina (suscripción).
  Ninguno de los dos usa API keys.
- **Registro**: cada etapa escribe
  `<repo-satelite>/../logs/<celda>-<etapa>-<timestamp>.jsonl`, un evento por línea con
  flush inmediato: `inicio` (modelo, effort, versión del CLI, SHA-256 de los prompts,
  config RAG), `paso_inicio`/`paso_fin` por invocación, un `evento_cli` por cada línea
  del stream del CLI —payload completo y verbatim, más el tipo y la atribución a
  subagente— y `fin`. Las consultas RAG las escribe el servidor MCP en un archivo
  aparte, con sufijo `-rag.jsonl`, porque corre como proceso hijo del CLI; el stderr
  de cada invocación va a su propio `-stderr-paso<N>.txt` (a un archivo y no a un
  pipe, para que una etapa larga no trabe al CLI llenando el buffer).
- **Snapshot por invocación de rol**: al cerrar cada paso —haya terminado bien o
  cortado— el núcleo copia el repo satélite a
  `<...>-snapshots/paso<N>-<rol>/`, al lado del JSONL, excluyendo `.git`,
  `node_modules`, `dist`, `build` y `.expo`, y registra el evento `snapshot`. Es la
  evidencia primaria del eje `veracidad` de `evaluacion/rubricas/rol-revisor.md`
  (su precondición 2 admite «commit, tag o copia que deja el orquestador»); se copia
  en vez de commitear para no escribir en el historial del repo generado, que es
  dato del experimento. Un fallo de la copia se registra y no corta la etapa.
- Si un paso termina con código ≠ 0, el orquestador registra `corte` y no sigue: una
  falla del CLI es una intervención del operador (protocolo §5), no algo que el
  orquestador decida.

### Dry-run (sin invocar a ningún CLI)

```bash
.venv/bin/python pipeline/harness_a/orquestar.py --config pipeline/config/a-con-rag.yaml \
    --repo /tmp/repo-prueba --etapa backend --dry-run
```

Carga config + etapas + prompts + índice RAG e imprime qué ejecutaría: modelo, effort,
prompts con hash, secuencia de pasos con sus archivos de handoff, comando del servidor
MCP y la línea de comandos completa de cada invocación. Verificado para las 6 configs
(4 oficiales + 2 de piloto) en las 3 etapas.

### Smoke check del backend (entorno on-chain)

El criterio de avance de la etapa backend (`etapas.yaml`) es que el backend levante y
responda el health-check que su README documenta. La spec exige verificar
`eth_chainId == 11155111` al iniciar (`spec/07-depositos-on-chain/README.md`): con el
nodo caído aplica **reintentos con backoff** (el proceso puede llegar a servir HTTP
igual), pero un `chainId` distinto ⇒ **terminación con error**. Para que el smoke se
haga con los mismos valores pre-registrados en todas las celdas, el operador levanta el
entorno on-chain de `evaluacion/suite-at/entorno/` antes de verificar el arranque:

```bash
cd evaluacion/suite-at/entorno
docker compose up -d --wait   # nodo anvil en http://127.0.0.1:8545 (chainId 11155111)
python desplegar-usdc.py      # imprime dirección del USDC-mock y bloque de despliegue
```

y configura el SUT según el README del repo satélite con esos valores: URL RPC
`http://127.0.0.1:8545`, la dirección del USDC-mock y el bloque de inicio que imprime
`desplegar-usdc.py`. El entorno on-chain es **infraestructura compartida** (nodo +
contrato mock): usarlo durante la generación **no expone la suite de ATs** — los tests
del holdout nunca entran al repo satélite ni al contexto del agente.

### Monitoreo de consumo durante la corrida

Con suscripciones, el tope vinculante son los **rate limits** de cada proveedor y no el
`costo_max_usd` del protocolo (ADR-009, Consecuencias). Lo que hay para vigilar:

- **A** informa costo nativo: `total_cost_usd` y `modelUsage` viajan en los eventos del
  `stream-json` y quedan verbatim en el JSONL.
- **B** informa tokens (`turn.completed`) pero no USD. `nucleo.costo_estimado_usd`
  estima localmente con los precios de lista verificados el 2026-08-16
  ([`runs/piloto-01/precio-gpt-5-6-sol.md`](../runs/piloto-01/precio-gpt-5-6-sol.md),
  pendiente de ratificación), pero **hoy el orquestador no lo llama**: se computa sobre
  los `evento_cli` ya registrados en el JSONL, por fuera del bucle de ejecución. El
  cableado en vivo espera a que la piloto pinnee los nombres exactos de los campos de
  `turn.completed` (ítem 19); inventarlos ahora sería adivinar el esquema.
  La estimación se hace **por request y se acumula**, nunca sobre el total de la etapa:
  arriba de 272 000 tokens de input OpenAI factura el request *completo* al doble de
  entrada y 1,5x de salida, y con `model_context_window` en 1 000 000 (ADR-010 D2)
  cruzar ese umbral es esperable, no un borde. Un modelo sin precio verificado se
  registra con el motivo en vez de un número, y el estimador devuelve `(None, motivo)`.
- La estimación usa precios de lista **sin descuento por caché**: si las tarifas de
  entrada cacheada y de escritura de caché entran o no, es decisión del tesista.
- La verdad final, en ambos casos, son los dashboards de cada proveedor.

## Roles y handoff

`comun/etapas.yaml` define los dos roles y la secuencia, idénticas para las 3 etapas y
las 4 celdas:

| Paso | Rol | Entrada | Salida |
|---|---|---|---|
| 1 | implementador | prompt de etapa + spec | código en el repo satélite |
| 2 | revisor | prompt de etapa + estado del repo | `.pipeline/revision-<etapa>.md` |
| 3 | implementador | prompt de etapa + puntero a la revisión | código corregido |

El prompt de rol se compone con el de sistema (`nucleo.sistema_compuesto`) y se inyecta
por el mecanismo de cada CLI; el prompt de etapa va como mensaje del usuario. Los roles
**instruyen delegar en subagentes** el trabajo independiente y acotado (ADR-010,
Decisión 1), con texto vendor-neutral y byte-idéntico entre celdas: la delegación la
ejecuta cada CLI con su maquinaria nativa, el orquestador no llama `Task` ni
`spawn_agent`.

El handoff son archivos bajo `.pipeline/` del repo satélite, pasados **por puntero**
(ruta) y no pegando su contenido. El directorio lo crea `nucleo.ejecutar_paso` antes de
cada paso que declara salida —idéntico en las 4 celdas—, así que el agente no tiene que
crearlo ni el resultado depende de que se le ocurra hacerlo. No se usan archivos de carga automática
(`AGENTS.md`, `CLAUDE.md`): Codex carga `AGENTS.md` del workspace y Claude Code no, lo
que inyectaría contexto de forma asimétrica. Si el paso 2 no dejó su archivo, el paso 3
lo registra como `handoff_faltante` y sigue: el orquestador no interpreta la salida del
modelo.

## El conmutador RAG

En celdas con `rag: true`, ambos orquestadores lanzan **el mismo** servidor MCP stdio
(`comun/rag/servidor_mcp.py`, nombre `corpus`), con el mismo comando construido por
`nucleo.comando_servidor_rag`: una sola implementación de la herramienta
`consultar_corpus` para las dos familias (ADR-009, Decisión 2). El nombre, la
descripción, el corpus y el `k` salen de `comun/etapas.yaml`; el algoritmo (BM25 puro,
k1=1.5, b=0.75, k=6 sobre los 9 documentos congelados en H3) no cambió respecto de
ADR-005. Los prompts **no mencionan la herramienta**: su disponibilidad es la única
diferencia entre celdas con y sin RAG. En celdas con `rag: false` el servidor no se
lanza y el índice ni se construye.

Cada consulta queda registrada con su celda, etapa, rol y número de paso en el archivo
`-rag.jsonl` de la corrida.

## Qué garantiza `verificar_paridad.py`

Corre **77 chequeos** y sale con código ≠ 0 si falla cualquiera:

1. Las 4 configs oficiales tienen exactamente los campos
   `{celda, harness, modelo, effort, rag, etapas}` y **sólo difieren** en los factores
   (`celda`, `harness`, `modelo`, `rag`).
2. Los pares (harness, modelo) son exactamente los de ADR-009 Decisión 3
   (`a`/`claude-opus-5`, `b`/`gpt-5.6-sol`), el `effort` es `xhigh` en las 4 y cada
   harness tiene una celda con RAG y una sin.
3. Las 4 configs resuelven al **mismo** `etapas.yaml`, cuya secuencia de roles es
   implementador → revisor → implementador, y los 6 prompts que referencia (sistema,
   3 etapas, 2 roles) existen y no están vacíos.
4. Los prompts que el CLI recibiría —sistema, etapa y rol, ya compuestos por el mismo
   código que usan los orquestadores— son **byte-idénticos** entre las 4 celdas en las
   3 etapas.
5. Los prompts de rol traen la instrucción de delegación de ADR-010, y ningún prompt
   nombra herramientas o productos de un proveedor ni menciona el RAG.
6. El RAG es un único servidor MCP con la misma config y el mismo comando en las dos
   familias, y ni ese comando ni el bucle de ejecución de los pasos se reimplementan
   en un orquestador (ninguno de los dos contiene un `Popen` propio); las celdas sin
   RAG no registran la herramienta.
7. Los parámetros BM25 de `etapas.yaml` coinciden con las constantes de
   `comun/rag/indice.py`.
8. Los SHA-256 de `corpus/documentos/*` coinciden con el manifest congelado de H3
   (`corpus/manifest.md`), sin archivos de más ni de menos.

Estado al 2026-08-16: los 77 chequeos pasan, y el camino negativo se probó sobre copias
del repo con seis adulteraciones distintas (model ID viejo, `effort` distinto en una
celda, prompt de rol sin la instrucción de delegación, prompt de rol nombrando un
proveedor y la herramienta RAG, un documento del corpus modificado, y un orquestador con
su propio bucle `Popen`): las seis dan exit 1 nombrando el chequeo exacto que se rompió.

## Pendiente para la piloto (H6)

Lo que **no** se puede validar sin ejecutar los CLI de verdad. Los ítems numerados son
de [`runs/piloto-01/checklist-h6.md`](../runs/piloto-01/checklist-h6.md):

- **Ejecución real end-to-end** de ambos orquestadores, con `config/piloto-01.yaml` (A)
  y `config/piloto-02.yaml` (B), las dos descartables.
- **Ítem 19 — verificaciones de los CLI:** que `-c developer_instructions=…` llega
  efectivamente al modelo en un `codex exec` real (hoy sólo verificado con el oráculo
  `codex debug prompt-input`), y qué hace cada CLI ante un rate limit a mitad de etapa.
- **Ítem 20 — precio por token de `gpt-5.6-sol`:** verificado contra la documentación
  de OpenAI y cargado en `nucleo.PRECIOS_USD_POR_MTOK`, a la espera de ratificación. Lo
  que la piloto valida es la estimación contra el dashboard de billing (ítem 2), no el
  precio de lista.
- **Ítem 22 — compactación de B con historia larga:** el efecto de
  `model_context_window=1000000` no está verificado; hay que correr una etapa cuya
  historia supere los ≈258 400 tokens y registrar si compacta.
- **Ítem 23 — techo de 1 048 576 caracteres por input en Codex:** si un revisor produce
  una revisión enorme, el pase correctivo puede chocar con ese límite. Como el handoff
  se pasa por puntero y no pegado, el riesgo es que el propio CLI lo lea entero.
- **Ítem 24 — fan-out de la delegación:** medir cuántos subagentes abre cada familia y
  verificar que el JSONL los capture. En A la atribución sale de `parent_tool_use_id`
  con `--forward-subagent-text`; en B el mapeo de los eventos de thread a subagentes
  **no está verificado** y `nucleo.es_de_subagente` devuelve `None`.
- **Confinamiento y red en B (NO VERIFICADO):** `codex exec --help` (0.146.0) no
  documenta su modo de sandbox por default, así que el orquestador fija
  `-s workspace-write`, el mínimo que permite al implementador escribir en su
  workspace. En ese modo el propio CLI le anuncia al modelo que *"Network access is
  restricted"* (verificado con `codex debug prompt-input -c sandbox_mode=…`), lo que
  puede impedir instalar dependencias (`npm install`, `pip install`). Si la piloto lo
  confirma, la corrección es habilitar la red del sandbox
  (`-c sandbox_workspace_write.network_access=true`) y declarar la asimetría de
  confinamiento con A, que corre sin sandbox del SO.
- **El repo satélite tiene que ser un repositorio git para B:** `codex exec --help`
  (0.146.0) documenta `--skip-git-repo-check` como *"Allow running Codex outside a Git
  repository"*, o sea que por default hay un chequeo. El orquestador **no** pasa ese
  flag: el repo satélite es un repo git propio por ADR-001, y saltear el chequeo
  ocultaría un error de setup. Confirmar en la piloto que con el repo inicializado no
  hay fricción; A no tiene un requisito equivalente.
- **`--mcp-config` en A (NO VERIFICADO end-to-end):** el archivo que genera el
  orquestador usa la forma `{"mcpServers": {"corpus": {"command", "args"}}}`, pero no
  hay manera de comprobar que el CLI conecta el servidor sin lanzar `claude -p`: los
  subcomandos `claude mcp *` no aceptan `--mcp-config`. El servidor sí está probado por
  stdio de forma independiente.
- **Confinamiento del harness A:** se corre con `--dangerously-skip-permissions`; el
  confinamiento al repo satélite lo da el protocolo (repo dedicado + supervisión), no
  el SO. Es además una **condición de no-exposición del holdout** (protocolo §9): sin
  sandbox, Bash y Read pueden leer fuera del cwd, incluida `evaluacion/`. Si la
  asimetría de confinamiento A/B no se iguala, se declara como limitación en la tesis.
- **Ítem 16 — serialización de eventos exóticos:** `nucleo.serializar` degrada a
  `str()` lo que no reconoce; revisar en los logs de la piloto que no se pierda
  información relevante.
- **Granularidad del log:** hoy se registra **cada** línea del stream de cada CLI, con
  el payload completo. Si el volumen resulta impracticable para el meta-análisis, se
  ajusta después de ver los logs de la piloto.

## El pipeline SDK anterior

`harness_a/correr.py` y `harness_b/correr.py` implementan la arquitectura de ADR-005
(Claude Agent SDK / OpenAI Agents SDK). **No se borran hasta que la piloto valide el
reemplazo** (ADR-009, Consecuencias): son el camino de vuelta si la reescritura no
funciona. No comparten código con los orquestadores nuevos salvo `comun/`, así que
quedaron desactualizados respecto de `comun/nucleo.py` (que ya no exporta `MAX_TURNS`
ni `funcion_consultar_corpus`) y **no corren tal como están**; su encabezado lo dice.

`requirements.txt` sí se actualizó: pinnea `mcp==1.28.1` (el servidor MCP del RAG, que
antes entraba como transitiva de `claude-agent-sdk`), PyYAML y pytest, y ya no pinnea
los dos SDK. Los paquetes siguen instalados en el `.venv`, así que el camino de vuelta
no se rompe mientras el venv no se recree.

## Principios de diseño (paridad entre condiciones)

1. **Sólo varían los dos factores:** modelo subyacente y disponibilidad de RAG. Todo lo
   demás —etapas, roles, prompts, herramienta RAG, presupuestos— es equivalente entre
   celdas y auditable en este directorio.
2. **Model IDs y effort pinneados** por ADR-009 Decisión 3; se registran junto con la
   versión exacta de cada CLI en el manifest de cada corrida.
3. **Asimetrías que no se igualan artificialmente** (ADR-009 Decisión 1 y ADR-010): el
   reporte de costo, el confinamiento del shell, el punto de inserción del prompt propio
   y la respuesta de cada familia a la instrucción de delegación. Se declaran como
   limitación en el cap. 4 y se miden en la piloto.
4. **RAG conmutable** por configuración, sin cambiar el resto del pipeline.
5. Todo cambio al pipeline posterior a la corrida piloto y anterior a las oficiales se
   registra en el journal; después de la primera corrida oficial, el pipeline queda
   **congelado** hasta terminar las 4.
