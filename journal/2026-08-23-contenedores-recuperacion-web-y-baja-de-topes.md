# 2026-08-23 — Contenedores, la recuperación web de B y la baja de los topes de presupuesto

- **Hito:** H6 (ventana de la piloto), todavía sin iniciar. Ningún CLI de agente se
  ejecutó.
- **Contexto:** sesión con Claude Code que arranca preguntando en qué quedó el proyecto y
  termina cerrando la última deuda de escritorio de H6. Cierra la sesión del 2026-08-17.

## Qué se hizo

**Diagnóstico.** El working tree traía un cambio del 2026-08-17 sin commitear
(`pipeline/README.md` + `harness_b/orquestar.py`) que documentaba, con evidencia medida
sobre `codex-cli` 0.146.0, que **el supuesto de ADR-009 Decisión 5 es falso**: la
búsqueda web de Codex no viene desactivada por default —una corrida de control registró
dos `web_search` contra GitHub— y `apps`/`browser_use`/`computer_use` vienen en `true`,
con `codex_apps` exponiendo los conectores de la cuenta (el agente leyó el perfil y los
repos del tesista). El cambio no estaba en ningún journal ni ADR.

**Cuestionario de arranque.** Se le presentaron al tesista las seis decisiones que
faltaban para arrancar prolijo. Respuestas: ADR nuevo para la corrección de D5; ratificar
el precio de `gpt-5.6-sol`; versionar `AGENTS.md`; sortear el orden de celdas ahora;
**los agentes corren en contenedores, en las dos familias, independientemente del
sandboxing nativo de cada CLI**; y **no hay protocolo de corte** — la corrida termina
cuando termina el pipeline y el consumo se mide, no se topea. Las dos últimas abrieron
trabajo estructural que la checklist no preveía, así que sobre la contenerización se
preguntaron tres cosas más: base común con capa por CLI, credenciales por bind-mount
read-only, y red abierta en la piloto.

**Tres ADRs, todos Aceptados el mismo día.**

- **ADR-014** corrige la afirmación fáctica de ADR-009 D5 sobre el lado B: el traslado de
  ADR-008 pasa a ser explícito (`-c web_search="disabled"` más `--disable
  apps/browser_use/computer_use`), y su Decisión 2 obliga a verificarlo. Ninguna corrida
  se había ejecutado: el costo del hallazgo es cero, y sólo porque la piloto seguía
  detenida.
- **ADR-015** contenedoriza las dos familias, con lo que **elimina** la asimetría de
  confinamiento que ADR-009 D1 declaraba como limitación aceptada. Cierra el ítem 11.
- **ADR-016** congela el protocolo **v1.2** reemplazando a ADR-012: se van
  `costo_max_usd`, `tiempo_max_horas` y la regla de cierre por agotamiento. Cierra el
  ítem 7.

**Implementación.** `pipeline/contenedores/` con `Dockerfile.base` (toolchain idéntico)
más dos capas finas que sólo instalan su CLI, y `pipeline/comun/contenedor.py`, que arma
la envoltura una sola vez para las dos familias. Los orquestadores quedaron cableados,
`verificar_paridad.py` pasó de **77 a 113 chequeos**, y el protocolo, la checklist, el
manifest de piloto-01, su plantilla, los dos README, el ROADMAP y
`analisis/amenazas-validez.md` se actualizaron en consecuencia.

**Sorteo del orden de las 4 celdas** (ítem 15), una sola vez y reproducible —semilla
`sha256(ba0d92b)`, orden alfabético como lista de partida—:
**`b-sin-rag` → `a-sin-rag` → `b-con-rag` → `a-con-rag`**.

**Estado de H6:** de 11 ítems cerrados se pasó a **15 de 24**. Los 9 abiertos (1, 2, 6,
13, 16, 19, 22, 23, 24) **necesitan todos ejecutar la piloto o el entorno docker**: no
queda deuda de escritorio.

## Decisiones

- **La corrección de D5 va por ADR y no sólo por journal.** Lo falsificado es una
  afirmación de un ADR Aceptado; sin ADR, `decisiones/` —la carpeta que la tesis cita
  como registro— seguiría afirmando algo que la medición contradice. El precedente del
  ítem 3 (cerrado sin ADR) no aplicaba: ahí no había ADR aceptado diciendo lo contrario.
- **Contenedores en las dos familias, sin tocar el sandbox nativo de ninguna.** El
  contenedor es una capa exterior, así que cada agente sigue viendo el default de su
  producto. Se descartó una imagen única con los dos CLI: cada agente vería el binario
  del competidor en su `PATH`, que es entorno observable por el modelo.
- **El holdout no se monta.** Es el motivo por el que ADR-015 cierra el ítem 11: la
  no-exposición de `evaluacion/` (protocolo §9) pasa a sostenerla el mecanismo en vez del
  procedimiento. Tampoco se monta `pipeline/` entero, sólo `comun/` y el corpus:
  `config/` y el verificador son instrumentos del experimento, no insumos del agente.
- **Sin topes, con medición completa.** Un tope de costo habría **censurado la variable
  que el experimento compara**. Se asume explícitamente el riesgo de que una celda
  consuma un múltiplo de lo previsto. `presupuesto_proporcional` (60/25/15) sobrevive
  como referencia descriptiva, no como umbral, y el abandono de etapa queda sólo por
  criterio de progreso.
- **La versión del CLI se mide al arrancar, no antes.** El manifest tenía pinneado
  `claude 2.1.233` del 2026-08-16; el host ya está en 2.1.241. El campo pasó a
  `PENDIENTE-ARRANQUE` y es el número que además se hornea en la imagen.

## Pendientes y próximos pasos

Para arrancar piloto-01, todo manual: **construir las tres imágenes** (nunca se
construyeron: el daemon de Docker estaba abajo), levantar el entorno on-chain
(`compose up -d --wait`, `desplegar-usdc.py`, `fondear.py`), verificar la sesión de las
dos suscripciones, y completar y commitear los campos `PENDIENTE-ARRANQUE:` del manifest
—ahora incluyen los digests de las imágenes junto al de anvil.

## Observaciones para el meta-análisis

- **El default de producto es una fuente primaria más, y hay que ejecutarlo.** En la
  sección de evidencia de ADR-009 todo se había medido corriendo los CLI salvo una
  afirmación, la del default de `web_search`, escrita por inferencia. Fue la única que
  resultó falsa. La regla que queda: ningún default se declara satisfactorio sin
  ejecutarlo.
- **Un verificador que no chequea el mecanismo da confianza en vez de quitarla.** El
  ítem 10 estaba tildado desde julio afirmando que ADR-008 se había trasladado a los
  CLI, pero `verificar_paridad.py` no inspeccionaba ninguna línea de comandos, en
  **ninguna** de las dos familias. Es la misma clase de falso verde que la sesión del
  2026-08-17 anotó, dos sesiones seguidas: la primera vez el verificador validaba
  invariantes obsoletos, esta vez no validaba nada. Los chequeos nuevos leen el comando
  que arma cada orquestador y no su fuente, justamente para que un flag escrito pero
  nunca pasado no pase el chequeo.
- **Contenerizar destapó dependencias que la envoltura no podía asumir.** El servidor MCP
  del RAG lo lanza el CLI, así que corre **adentro**: hubo que montarle el corpus (que
  vive fuera de `pipeline/`), montar el directorio de logs para que su JSONL sobreviva al
  contenedor, e instalar `mcp`/`PyYAML` en la imagen. Nada de eso estaba en el ADR que
  aprobó la contenerización, y el dry-run fue lo que lo hizo visible antes de la corrida.
- **Una decisión del tesista puede eliminar una amenaza en vez de mitigarla.** La
  asimetría de confinamiento y el cierre por presupuesto pasaron a estado *mitigada* con
  el mecanismo que las vuelve imposibles, no con un procedimiento que las compensa. Las
  dos venían declaradas como limitaciones a discutir en el capítulo 4.
- **`AGENTS.md` era `CLAUDE.md` pasado por sed**, con dos referencias reales rotas al
  paso ("Codex.ai/code", "artifacts de Codex.ai publicados"). Se corrigieron antes de
  versionarlo, y el archivo ahora declara explícitamente que los agentes del experimento
  nunca lo ven — que es la razón por la que ADR-009 D4 prohíbe usar esos archivos como
  handoff del pipeline.
