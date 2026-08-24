# ADR-014 — La recuperación web del harness B no venía desactivada: mecanismo explícito

- **Estado:** **Aceptado** (ratificado por el tesista el 2026-08-23)
- **Fecha:** 2026-08-23
- **Contexto:** ventana H6, con la corrida piloto todavía sin ejecutar. Ningún CLI de
  agente corrió: el hallazgo sale de invocaciones de control del CLI de Codex, no de una
  corrida del experimento.
- **Reemplaza a:** la afirmación fáctica de
  [ADR-009](ADR-009-harnesses-como-cli-y-orquestador-de-roles.md) **Decisión 5** sobre el
  lado B — «Codex trae la búsqueda web desactivada por default y no se activa, lo que
  satisface ADR-008 del lado B». ADR-009 no se edita; el resto de su Decisión 5
  (`--setting-sources`/`--strict-mcp-config` en A, `--ignore-user-config` en B, pinneo de
  versiones en el manifest) se conserva sin cambios.
- **No cambia el criterio de:** [ADR-008](ADR-008-restriccion-recuperacion-web-harness-a.md),
  que sigue siendo la fuente: la recuperación web se restringe para que la disponibilidad
  del corpus sea la única diferencia entre celdas con y sin RAG. Lo que cambia es que del
  lado B ese criterio **necesita mecanismo propio** en vez de descansar en un default.

## Contexto

ADR-009 Decisión 5 dio por satisfecho ADR-008 en la familia B apoyándose en un default
del producto. La afirmación no se verificó ejecutando el CLI: es la única de esa sección
de evidencia que se escribió por inferencia. El ítem 10 de la checklist H6 la dio por
cerrada en consecuencia.

## Evidencia (2026-08-17, `codex-cli` 0.146.0)

Medido ejecutando el CLI en la máquina del tesista:

- `web_search` es una clave de config de tipo string con valores válidos
  `disabled|cached|indexed|live`, y **su default no es `disabled`**. Sin pasar `--search`
  y con `--ignore-user-config`, una corrida de control registró **dos items `web_search`
  completados contra GitHub**. `--search` sólo sube el nivel a `live`.
- `codex features list` con un `CODEX_HOME` limpio —o sea, default del producto y no
  config del host— reporta `apps`, `browser_use` y `computer_use` en `true`. `apps`
  expone el servidor MCP `codex_apps` con los conectores atados a la cuenta: en esa misma
  corrida el agente llamó `github.search`, `github.get_profile` y
  `github.search_repositories`, devolviendo el perfil y la lista de repos del tesista.
- `--ignore-user-config` no desactiva ninguna de las tres features.
- **Hacen falta las dos cosas.** Con los `--disable` solos, las búsquedas web siguen
  ocurriendo. Con `-c web_search="disabled"` **más** los tres `--disable`, la corrida de
  control no registró ningún `web_search` ni `mcp_tool_call`.

## Decisión

### 1. El traslado de ADR-008 al lado B es explícito

`harness_b/orquestar.py` pasa, en toda invocación de rol y en las dos celdas B:

- `-c web_search="disabled"`
- `--disable apps`, `--disable browser_use`, `--disable computer_use`

Las cuatro banderas van en el módulo, no en la config por celda: son constantes del
factor pipeline, no del 2×2.

### 2. Los mecanismos de ADR-008 se verifican, en las dos familias

`verificar_paridad.py` chequea la línea de comandos efectiva que cada orquestador arma
para las 4 celdas: `--disallowed-tools WebSearch,WebFetch` en A, y las cuatro banderas
del punto 1 en B. Hasta hoy el verificador no inspeccionaba ninguna línea de comandos: el
ítem 10 de la checklist afirmaba un traslado que ningún chequeo sostenía, en ninguna de
las dos familias.

### 3. El límite se declara: esto restringe herramientas, no red

Un agente con shell y salida a internet —necesaria para `npm install` y `expo export`—
puede recuperar de la web igual, en A y en B. Con la contenerización de
[ADR-015](ADR-015-agentes-en-contenedores.md) la red del contenedor queda abierta en la
piloto, así que el canal sigue vivo y simétrico. Va a `analisis/amenazas-validez.md`.

## Consecuencias

- **Una celda ya no podía haber sido "sin recuperación".** Si `b-sin-rag` hubiera corrido
  antes de este ADR, la única diferencia entre celdas con y sin RAG no habría sido el
  corpus. Ninguna corrida se ejecutó, así que no hay dato contaminado que descartar: el
  costo del hallazgo es cero y sólo porque la piloto seguía sin arrancar.
- **`codex_apps` es contaminación por config de la cuenta, no del host.** ADR-009
  Decisión 5 midió la contaminación del prompt y la cerró con `--ignore-user-config`. Los
  conectores llegan por la cuenta autenticada, que `--ignore-user-config` preserva a
  propósito para no romper `auth.json`. Es un canal que el ADR anterior no consideró.
- El ítem 10 de la checklist H6 se reabre y se cierra con este ADR más los chequeos del
  punto 2.
- **Regla que queda para el resto de la ventana:** ningún default de producto se declara
  satisfactorio sin ejecutarlo. En la sección de evidencia de ADR-009 esta era la única
  afirmación inferida, y es la única que resultó falsa.

## Alternativas consideradas

- **Sólo los `--disable`, sin `web_search`.** Rechazada por medición: las búsquedas web
  siguen ocurriendo.
- **`CODEX_HOME` limpio.** Rechazada por el mismo motivo que ADR-009 Decisión 5:
  `auth.json` vive ahí y vaciarlo rompe la autenticación por suscripción.
- **Dejarlo en el journal, sin ADR.** Rechazada: lo falsificado es una afirmación de un
  ADR **Aceptado**. Sin este documento, `decisiones/` —la carpeta que la tesis cita como
  registro de decisiones— seguiría afirmando algo que la medición contradice.
