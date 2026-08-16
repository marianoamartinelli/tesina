# 2026-08-16 — Los harnesses pasan a los CLI; roles y re-pinneo de modelos

- **Hito:** H6 (ventana de la piloto), todavía sin iniciar.
- **Contexto:** primera sesión desde el 2026-07-07. En el medio el proyecto estuvo
  detenido unas cinco semanas y media; el PR #1 de la auditoría quedó mergeado en
  `origin/main`.

## Qué se hizo

Sesión de decisión, no de implementación: el tesista planteó reemplazar los harness
construidos sobre los SDK de agentes por los CLI de cada proveedor (Claude Code y Codex
CLI), para reusar sus suscripciones y salir de la fragilidad de los adaptadores, y sumar
"personalidades" por etapa mediante un orquestador por familia.

La evaluación se hizo contra los CLI instalados, no contra documentación. Lo verificado:

- `claude -p --output-format json` reporta `total_cost_usd` y `modelUsage` por modelo
  **con auth de suscripción** (no había `ANTHROPIC_API_KEY` en el entorno). El costo
  sigue siendo medible sin API key, que era la duda de fondo del planteo.
- `codex exec --json` reporta tokens (`input/cached/cache_write/output/reasoning`) pero
  **no costo en USD** — misma situación que el harness B actual, que ya estima local.
- **Ningún CLI expone un tope de turnos.** Claude Code sí tiene `--max-budget-usd`.
- `-c developer_instructions=…` es la vía de inyección de prompt propio en Codex:
  verificado con `codex debug prompt-input`, aparece como primer `input_text` del mensaje
  `developer`, **antes** del scaffolding nativo, que se conserva íntegro.
- **Codex trae scaffolding multi-agente nativo y activo**: el agente primario se presenta
  como `/root` "in a team of agents", con `spawn_agent`/`followup_task`/`send_message`, y
  un bloque `<multi_agent_mode>` que gatea la delegación proactiva a pedido explícito.
- **La contaminación por config del host es real y medible**: con la config del tesista
  cargada, el prompt de Codex incluía `<apps_instructions>`, `<plugins_instructions>` y
  `<recommended_plugins>`, y `<skills_instructions>` medía 15 485 caracteres; con
  `CODEX_HOME` limpio esos bloques desaparecen y el de skills baja a 5 237.
- **Ventanas de contexto medidas en la herramienta, no en la documentación:** el catálogo
  del propio CLI (`codex debug models`) reporta **272 000** para `gpt-5.6-sol` y también
  para el `gpt-5.5` que ADR-005 había pinneado como "1M contexto"; del lado Claude,
  `modelUsage.contextWindow` de una corrida real de `claude -p --model claude-opus-5`
  bajo suscripción confirma **1 000 000**.

Con eso se escribió **ADR-009 (Propuesto)**, que reemplaza a ADR-005 completo, más la
actualización del índice de `decisiones/` y de `runs/piloto-01/checklist-h6.md`.

## Decisiones

- **Swap completo a los CLI** (ADR-009 D1). El tesista decidió **no elevar a los
  directores** la desviación respecto del objetivo específico 3 del Formulario 1, que
  nombra "Claude Agent SDK y OpenAI Agent SDK": Claude Code es el harness del Agent SDK,
  pero Codex CLI no es el OpenAI Agents SDK. Se planteó explícitamente como condición
  antes de decidir; queda registrado en el ADR como consecuencia asumida y se declara en
  el cap. 4.
- **RAG como servidor MCP stdio único** (D2): el algoritmo BM25 no se toca; cambia la
  entrega. Es mejor paridad que hoy — una implementación en vez de dos.
- **Re-pinneo a `claude-opus-5` y `gpt-5.6-sol`, effort `xhigh` en ambos** (D3). Cierra
  el ítem 8 de la checklist. Se descartó `claude-fable-5`: es el modelo más capaz de
  Anthropic pero a USD 10/50 por millón rompe el pareo por precio de ADR-005.
- **Personalidades = prompts de rol, sin primitivas de sub-agentes de cada vendor** (D4),
  dos roles por etapa (implementador → revisor → pase correctivo), sesión fresca por
  invocación y handoff por archivos de nombre explícito bajo `.pipeline/`. Sin
  paralelismo entre etapas (choca con protocolo §4).
- **Se elimina el presupuesto de turnos.** Decisión del tesista durante la sesión;
  `MAX_TURNS` se retira y no se repone en el orquestador. Cierra el ítem 14.
- **No se denegó `Task` en A** para igualar topologías de delegación: la delegación no
  cruza al otro factor, así que no aplica el criterio de ADR-008. Se registra su uso en
  el JSONL y se declara como asimetría.

## Pendientes

- **El tesista:** ratificar o rechazar ADR-009 (patrón ADR-008). Mientras esté
  "Propuesto", ADR-005 sigue vigente y nada del pipeline actual se borra.
- Cuatro ítems nuevos en la checklist H6 (17–20): reescritura del pipeline a los CLI;
  regla de exclusión de `.pipeline/` en las métricas estáticas (**deadline duro: antes
  de la piloto**, misma lógica que el ítem 4); verificaciones de `developer_instructions`
  en `exec` real y de comportamiento ante rate limit; y precio por token de
  `gpt-5.6-sol`.
- Ítems 8 y 14 cerrados; 11 y 12 reformulados por ADR-009.

## Observaciones para el meta-análisis

- **El experimento se desincronizó de su objeto de estudio por estar quieto.** Cinco
  semanas y media de pausa bastaron para que los dos flagships pinneados quedaran una
  generación atrás. El protocolo ya preveía esto para las corridas (ventana de ≤2 semanas entre la
  primera y la última), pero no para la fase preparatoria: la deriva de los modelos
  comerciales también erosiona las decisiones tomadas *antes* de correr. Es un costo de
  la parálisis que ninguna checklist estaba midiendo.
- **Un pareo declarado no es un pareo verificado.** ADR-005 pareó ambos modelos como "1M
  contexto" el 2026-07-05, y hoy la herramienta reporta 272K del lado GPT — también para
  el `gpt-5.5` de aquel pinneo. Una variable declarada como controlada no lo estaba, y
  nadie lo habría notado sin medir. La lección operativa apareció dentro de esta misma
  sesión: la primera versión del ADR verificó el lado B contra la herramienta y el lado A
  contra documentación, y hubo que volver a medir A para que la comparación fuera
  simétrica. Verificar un solo lado de una afirmación de paridad no es verificarla.
- **El defecto de costura reaparece una capa más arriba.** La auditoría del 07-07
  observó que los defectos vivían en las costuras entre componentes, no dentro de ellos.
  Hoy la misma clase de problema apareció entre el experimento y sus herramientas: el
  harness A ya *era* Claude Code (por el preset appendeado) sin que ningún documento lo
  dijera así, y la asimetría de scaffolding A/B que el journal registró como defecto era
  en realidad el síntoma de que un lado usaba el producto y el otro una librería.
- **La contradicción del planteo original resultó productiva.** "Salir de la fragilidad
  de los harness custom" y "construir un orquestador de agentes" se contradicen: un
  orquestador es un harness custom. Nombrarlo permitió separar lo que sí mejora (no
  depender de internals de `agents.sandbox` v0.17.7) de lo que no cambia (seguir
  manteniendo código propio), y acotar el orquestador a lo que no puede vivir en otro
  lado.
- **Los feature flags no son documentación.** `codex features list` muestra
  `personality` y `multi_agent` en `stable=true`, y era tentador citarlos como evidencia
  de que Codex soporta roles. La semántica real de `personality` sigue sin verificarse;
  lo que sí se verificó — el scaffolding `/root` y las herramientas de colaboración —
  salió de inspeccionar el prompt efectivo, no de leer nombres de flags.
- Sobre el trabajo asistido de hoy: la sesión produjo hallazgos que ninguna lectura de
  documentación habría dado (el reporte de costo bajo suscripción, la clave
  `developer_instructions`, el stripping por `CODEX_HOME`), todos por ejecutar los CLI y
  sondear con `--strict-config` y `debug prompt-input` como oráculos. El patrón —
  convertir la herramienta en su propia fuente primaria — es replicable y vale para el
  cap. 4.
