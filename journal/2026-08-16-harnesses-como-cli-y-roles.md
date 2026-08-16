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

## Cierre de la sesión: ADR-009 aceptado y propagado

El tesista ratificó ADR-009 el mismo día. ADR-005 pasó a «Reemplazado por ADR-009» (sin
editar su contenido) y se propagó la decisión a los documentos vivos: `README.md`,
`ROADMAP.md` (H4 y H6), `pipeline/README.md` (banner de estado: el código sigue siendo el
de SDK hasta el ítem 17), `runs/README.md`, `evaluacion/README.md` (la rúbrica del rol
revisor deja de ser decisión abierta), `evaluacion/metricas-estaticas/README.md`
(`.pipeline/` a la lista de exclusiones), `analisis/amenazas-validez.md` (cuatro amenazas
nuevas y cuatro filas actualizadas) y la checklist H6. `evaluacion/protocolo.md` **no se
tocó**: está pre-registrado y su corrección va por el ítem 9.

Un hallazgo colateral: al re-pinnear los modelos generadores quedó al descubierto que
ADR-007 sigue fijando el juez white-box en `claude-opus-4-8` y el espejo en `gpt-5.5`. No
es incorrecto —el juez ya no es el mismo modelo que genera en A, lo que en principio
*reduce* el self-preference—, pero necesita decisión explícita: es el ítem 21 nuevo.

**Los 10 artifacts publicados de claude.ai no se pudieron actualizar:** no aparecen en el
listado de esta cuenta (ni como propios ni como compartidos) y `WebFetch` los reporta como
inexistentes o no compartidos. Los HTML fuente vivían en el scratchpad de la sesión del
2026-07-06, que ya no existe en disco. Queda pendiente resolver desde qué cuenta se
publicaron antes de poder redeployarlos.

## Pendientes

- **Los 10 artifacts de claude.ai:** varios quedaron desactualizados por ADR-009 (sobre
  todo "Doc técnica — Pipelines A y B", "H4 — Pipeline" y "Doc técnica — Arquitectura
  RAG"). Requieren resolver el acceso y, sin los HTML fuente, reconstruirlos.
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

## Segundo tramo del día — ADR-010

El tesista aportó una lectura del techo de contexto de B: no sería una limitación de
`gpt-5.6-sol` sino un enforcement del harness de Codex, y la vía para esquivarlo sería
instruir delegación fuerte en subagentes, de modo que ni el principal ni sus hijos se
acerquen al umbral. Su argumento de fondo no es el contexto sino el foco: el agente
principal conserva la tarea general y delega problemas acotados.

Antes de escribir nada se probó la config. Tres hallazgos:

- **Un turno con 294 318 tokens de input completa, y el modelo lee un marcador plantado
  al final.** O sea que los 272 000 del catálogo **no son un tope a nivel de request**.
- **Da idéntico con y sin `-c model_context_window=1000000`.** El override no fue lo que
  habilitó ese turno; lo que ese parámetro gobierna, junto con
  `effective_context_window_percent: 95`, es el umbral de **auto-compactación** entre
  turnos (≈ 258 400 por default, ≈ 950 000 con override), y un turno único no lo
  ejercita. Se fija igual —el costo es nulo— pero declarado como hipótesis a validar.
- **Límite duro nuevo:** el CLI rechaza en `turn/start` cualquier input de más de
  **1 048 576 caracteres** (`input_too_large`), independiente de los tokens. Apareció al
  primer intento del test, con 1 367 963.

Con eso se escribió **ADR-010 (Aceptado)**: los prompts de rol pasan a instruir
delegación (enmienda ADR-009 D4), se fija `model_context_window=1000000` en B, y el
evaluador white-box y su espejo se re-pinnean a `claude-opus-5` / `gpt-5.6-sol` con
runtime `claude -p` (enmienda ADR-007, cierra el ítem 21). La checklist queda con 24
ítems; los nuevos 22, 23 y 24 son las tres verificaciones que la piloto debe cerrar.

### Observaciones para el meta-análisis

- **La hipótesis del usuario era correcta en el diagnóstico y equivocada en el
  mecanismo**, y sólo medir lo distinguió. El techo existe, pero no donde parecía: no
  limita lo que la API acepta, limita cuándo el harness decide compactar. Si hubiéramos
  escrito el ADR con la explicación intuitiva, habríamos pinneado un parámetro
  afirmando un efecto que no probamos — y sonaría igual de convincente.
- **La contraprueba costó lo mismo que la prueba y cambió la conclusión.** Correr el
  test sólo con el override habría "confirmado" que funciona. El segundo run, idéntico
  salvo por la ausencia del flag, es el que convirtió una confirmación en un hallazgo.
  Barato y decisivo: vale como patrón para el resto del proyecto.
- **El límite de 1 MiB apareció por accidente**, al pasarme de tamaño en el primer
  intento. No estaba en ningún catálogo ni en ninguna ayuda de la CLI; sólo emerge
  cuando se lo cruza. Es un recordatorio de que la superficie efectiva de una
  herramienta no coincide con su superficie documentada — el mismo tema que ya venía
  apareciendo con las ventanas de contexto y los defaults de effort.
- **Segunda decisión del día que revierte una anterior del mismo día.** ADR-009 D4 fijó
  que los prompts no pidieran delegación; ADR-010 D1 la instruye. No es inconsistencia:
  es que la primera se tomó sin el dato del techo de contexto y sin que el tesista
  hubiera explicitado que la orquestación multi-agente le interesa como diseño y no
  como parche. La trazabilidad ADR por ADR permite ver exactamente qué información
  nueva movió la decisión, que es justamente lo que ADR-003 buscaba.
