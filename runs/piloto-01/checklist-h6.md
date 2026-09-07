# Checklist H6 — entrada y salida de la corrida piloto

Consolida la deuda de proceso que la ventana de ajuste de la
piloto (H6, única ventana legítima según ADR-004) debe resolver antes de congelar
el protocolo definitivo. La ventana comprende **piloto-01** (corrida completa con
el harness A) y **piloto-02** (smoke end-to-end del harness B). Ningún ítem se
resuelve editando `spec/` (congelada, tag `spec-v1.1`) ni ADRs aceptados: los
cambios van por nueva versión de documento + ADR nuevo donde corresponda.

**Estado al 2026-09-06:** **18 de los 24 ítems de salida cerrados.** La pre-piloto
(2026-08-24) y su cierre (2026-09-06) cerraron el 16 y el 23 por mecanismo, y dejaron el
19 parcialmente medido. Los **6 abiertos son 1, 2, 6, 19, 22 y 24**, y todos necesitan
`piloto-01`; el 24 se **reabrió** el 2026-09-06 al medir que el `--json` de Codex no
registra a los subagentes (H-23, ADR-023).

**Estado al 2026-08-23:** 16 de los 24 ítems cerrados. La sesión del 2026-08-23 cerró
cinco —7, 11, 15, 20 y 13— y volvió a cerrar el 10, que se había reabierto ese mismo día;
los tres ADRs que lo sostienen (**ADR-014, ADR-015 y ADR-016**) quedaron Aceptados en la
sesión.

De las puertas de entrada quedan dos abiertas: la **autenticación**, que es hoy el
**bloqueante duro** —el `claude` del contenedor responde `Not logged in` porque en macOS
la credencial vigente vive en el Keychain y no en el archivo que ADR-015 D3 manda montar—
y el **repo satélite**, que todavía no se creó. Todo lo demás del arranque está
verificado: las tres imágenes construidas, el entorno on-chain arriba con su digest
comprobado, la paridad en verde sobre el commit y el smoke de la suite en 40 passed.
Ningún CLI de agente ejecutó una etapa todavía.

Nota sobre el ítem 10: se reabrió el 2026-08-23 al descubrir que su premisa del lado B
era falsa, y se cerró el mismo día con ADR-014 más los chequeos de paridad que faltaban.

## Entrada — precondiciones verificables antes de iniciar

Los checkboxes de esta sección son **puertas de arranque**: se verifican en el momento
de iniciar la corrida, no de una vez y para siempre. Las anotaciones registran el último
resultado observado.

- [ ] **Paridad:** `pipeline/verificar_paridad.py` termina con exit 0
      (`.venv/bin/python pipeline/verificar_paridad.py`).
      *Verificado el 2026-08-23: exit 0, **117 chequeos** (77 antes de ADR-014/015/017), sobre
      el commit de `pipeline/` sin cambios sin commitear — o sea que el reparo
      «re-correr sobre el commit» quedó saldado. Re-correr igual el día de la corrida:
      esta puerta se verifica al arrancar, no de una vez. Los chequeos nuevos
      cubren la restricción de recuperación web en las dos familias y la envoltura en
      contenedor; su camino negativo se probó rompiéndolos a propósito.*
- [ ] **Manifest:** secciones §1–4 de `runs/piloto-01/manifest.yaml` completas y
      **commiteadas antes de iniciar** (protocolo §3 paso 2), incluidos los campos
      `paridad_verificada`, `entorno_host` y `entorno_onchain` de la plantilla.
      *El manifest existe; los campos que sólo se pueden medir al arrancar (modo de
      auth, digest efectivo de anvil, dirección del USDC-mock, repo satélite, hash de
      paridad sobre el commit) están marcados `PENDIENTE-ARRANQUE:` con el comando que
      los cierra. Falta completarlos y commitearlo.*
- [x] **Autenticación: resuelta y verificada end-to-end el 2026-08-23.** La piloto corre
      sobre la **suscripción** del tesista (ADR-009), inyectada como
      `CLAUDE_CODE_OAUTH_TOKEN` vía `--env-file` (**ADR-017**, que enmienda ADR-015 D3:
      el bind-mount no sirve del lado A en macOS, donde la credencial vigente vive en el
      Keychain y el archivo tenía un token vencido el 2026-06-23). B conserva el
      bind-mount de su `auth.json`.
      *Verificado con el token real cargado: `claude -p` dentro del contenedor responde
      normalmente contra `claude-opus-5`. El `.env` está gitignoreado; sólo se versiona
      `.env.example`.*
      Registrar en el manifest el modo de auth (`suscripción`) — nunca el token.

- [ ] **Versiones de CLI pinneadas** en el manifest: `claude --version` y
      `codex --version` (hoy 2.1.233 y 0.146.0), junto a los model IDs y al commit del
      corpus. *Ya registrados en el manifest, medidos en esta máquina el 2026-08-16.*
- [x] **Imágenes de los agentes construidas** (ADR-015), las tres con el mismo tag:
      `docker build -f Dockerfile.base -t tesina/agente-base:piloto-01 .` y las dos capas
      `Dockerfile.a` / `Dockerfile.b` con `--build-arg VERSION_CLI=` de la versión que el
      manifest pinnea. Registrar el **digest efectivo** de cada una en el manifest, con el
      mismo criterio que el pin del anvil (ítem 13).
      *Construidas el 2026-08-23 con tag `piloto-01` y registradas en el manifest:
      base `72a1a49f…`, agente-a `af7f27b1…` (CLI 2.1.241), agente-b `ab065e2f…`
      (CLI 0.146.0). Verificado adentro: los dos CLI responden `--version`, el toolchain
      (node v23.11.1 / npm 10.9.2 / python 3.11.2 / git 2.39.5) es **idéntico en A y B**,
      las tres comparten las mismas 10 capas de base, el usuario es `agente` (uid 1001)
      y hay salida a internet (200 contra el registry de npm).*

- [x] **Entorno on-chain arriba** (`evaluacion/suite-at/entorno/`):
      `docker compose up -d --wait`, luego `desplegar-usdc.py`.
      *Levantado el 2026-08-23: `suite-at-anvil` healthy, anvil 1.5.1-stable, USDC-mock
      desplegado en `0x5FbDB2315678afecb367f032d93F642f64180aa3` (bloque 1). Registrado
      en el manifest.*
      **Corrección:** `fondear.py` **no** es un paso de arranque — toma la dirección de
      la hot wallet del SUT como argumento obligatorio, y esa wallet la genera el agente
      durante la corrida. Se ejecuta al preparar los ATs de retiro, no antes de iniciar.
- [ ] **Harness de evaluación sano:** `evaluacion/suite-at/test_smoke.py` todo
      verde (no requiere SUT ni docker):
      `cd evaluacion/suite-at && ../../.venv/bin/python -m pytest test_smoke.py -q`.
      *Verificado el 2026-08-16: 40 passed.*
- [ ] **Regla de no-exposición presente:** la suite de ATs **no** se corre contra
      el SUT generado durante la generación (protocolo §4;
      `evaluacion/suite-at/README.md`). Sólo el smoke check de avance de etapa.

## Salida — pendientes que la ventana debe resolver

1. - [ ] **Ejecución end-to-end del harness A** con piloto-01: primera corrida real
         (hasta hoy sólo dry-runs). Con ADR-009 es contra `claude -p` bajo
         suscripción, no contra la API. El ítem 17 ya está hecho: el orquestador se
         probó con dry-runs de las 6 configs y con un CLI simulado, nunca contra
         `claude -p` real.
         Fuente: `pipeline/README.md` §"Pendiente para la piloto".
         Decisión esperada: harness A validado de punta a punta o defectos
         registrados y corregidos dentro de la ventana.

2. - [ ] **Smoke end-to-end del harness B** con piloto-02: etapa acotada sobre un
         repo descartable, con manifest e intervenciones marcados como
         descartables. Reformulado por ADR-009 — valida: el sandbox propio de
         `codex exec` con builds reales (`npm install`, `npx tsc`, `expo export`),
         la granularidad del JSONL de `--json`, y la estimación local de costo
         desde tokens contra el dashboard de billing de OpenAI. El fix de `TMPDIR`
         y la semántica de `max_turns` **dejan de aplicar**: eran del `SandboxAgent`.
         **Actualización (2026-08-23, pre-piloto):** el riesgo de red de abajo queda
         **sin objeto** y en su lugar apareció uno peor, ya resuelto: con
         `-s workspace-write` el sandbox nativo de Codex no arranca dentro del
         contenedor (bubblewrap no puede crear user namespaces) y **todo** comando del
         modelo falla sin cortar la corrida. **ADR-019** deja el confinamiento en manos
         del contenedor en las dos familias; con eso no hay política de red que el CLI
         le anuncie al modelo. Verificado además que `codex exec` necesita `CODEX_HOME`
         escribible (hallazgo H-03, `Dockerfile.b` corregido). Ver
         `runs/pre-piloto/hallazgos.md`.

         **Riesgo detectado al implementar el ítem 17:** con `-s workspace-write`,
         `codex debug prompt-input` muestra que el CLI le anuncia al modelo que
         «Network access is restricted», lo que puede impedir `npm install` /
         `pip install` durante la generación. Si el smoke lo confirma, la corrección
         propuesta es `-c sandbox_workspace_write.network_access=true` en las dos
         celdas B.
         Fuente: `pipeline/README.md` §"Pendiente para la piloto".
         Decisión esperada: harness B validado en cada punto o ajustes
         registrados antes de las corridas oficiales.

3. - [x] **Status HTTP del reenvío idempotente de retiros:** **cerrado, ratificado el
         2026-08-17** (sin ADR: la decisión vive en el propio test).
         El criterio `{200, 202}` quedó ratificado en `test_ep08_solicitud.py` con su
         fundamento en `spec-v1.1` —HU-09-01 RN-11 ata el 202 a la asincronía de la
         *creación*; HU-08-01 RN-10 y sus Escenarios 12/12b no fijan status para el
         reenvío; HU-09-01 RN-21 muestra que la spec asigna status por semántica de
         operación— y la lectura contraria (la columna «Éxito 202» del mapa de
         endpoints de HU-09-01 leída como status de toda respuesta exitosa) quedó
         registrada como candidata a reapertura para una eventual `spec-v1.2`. **0
         TODO-REVISAR** en `evaluacion/` (verificado por grep el 2026-08-16).
         Si el tesista prefiere la lectura contraria, hace falta un ADR estilo 006 —
         **nunca** editar `spec-v1.1`.
         Fuente: `test_ep08_solicitud.py`.

4. - [x] **Sobre-declaración F3** (ciclo de vida del SUT): **cerrado por ADR-011**
         (Aceptado el 2026-08-17). Los 10 migrables limpios
         (AT-04-01-11, AT-04-04-12, AT-04-05-13, AT-06-01-07, AT-06-01-08, AT-06-02-06,
         AT-06-03-06, AT-07-04-07, AT-07-04-11, AT-08-03-08) pasaron a tests black-box
         condicionales sobre `tests/comunes_reinicio.py`, que salta con motivo explícito
         si falta `SUITE_CMD_REINICIO_SUT`; los 3 parciales (AT-05-03-07,
         AT-07-04-01/03) quedan white-box con su razón real. Partición final:
         **465 automatizados / 56 white-box** sobre 521 ATs backend, sin `sin_test`.
         La suite pasa de 449 a 456 funciones de test. La familia F3 de la rúbrica
         quedó vacía y sus 3 sobrevivientes se reclasificaron en F1; rúbrica, briefing
         y plantilla subieron de versión.
         **Deadline duro cumplido:** el cambio entró antes de ver implementación alguna
         (protocolo §9).
         Fuente: `journal/2026-07-06-agente-evaluador-white-box.md` §Pendientes,
         punto 1; `decisiones/ADR-011-particion-automatizable-white-box.md`.

5. - [x] **Mecanismo de importar mnemonic** para los ATs de provisioning de la
         épica 06: **cerrado por ADR-013** (Aceptado el 2026-08-17).
         No se fija convención de entorno para el SUT —la única entrada de
         las 4 corridas es la spec congelada, y una variable inventada ahora mediría
         adherencia a una convención posterior a la generación—: se **ratifica el
         fallback** (F1 para AT-06-01-05/-09/-10; `PRECONDICION_IMPOSIBLE` sin fallback
         para AT-06-03-07) y se fija una convención de **descubrimiento** uniforme y
         acotada, para que el fallback no se dispare con distinto umbral en cada celda.
         Incorporada a la rúbrica como sección nueva referenciada desde esos 4 ATs, sin
         mover ningún criterio de veredicto.
         Residuo: AT-06-03-07 puede resultar evaluable en unas celdas y no en otras, lo
         que lo vuelve no comparable en ese AT — ADR-013 pide sumarlo a
         `analisis/amenazas-validez.md`.
         Fuente: `journal/2026-07-06-agente-evaluador-white-box.md` §Pendientes,
         punto 2; `decisiones/ADR-013-mecanismo-importar-mnemonic.md`.

6. - [ ] **Chequeo espejo con `gpt-5.6-sol`** (re-pinneado por ADR-010 D3) — muestra de
         10 ATs por celda,
         pre-registrado como opcional condicionado a presupuesto): decidir su
         ejecución u omisión según el costo observado en la piloto y registrar la
         decisión en el journal.
         Fuente: ADR-007 §3 ítem 5.
         Decisión esperada: ejecución u omisión, registrada en journal.

7. - [x] **Presupuestos: no hay.** **Cerrado por ADR-016** (Aceptado el 2026-08-23),
         que congela el protocolo **v1.2** reemplazando a ADR-012. La corrida termina
         cuando termina el pipeline: se eliminan `costo_max_usd` (200 USD) y
         `tiempo_max_horas` (24 h), y con ellos la regla de cierre por agotamiento y la
         rama presupuestaria del abandono de etapa (§5.7, que queda sólo por
         estancamiento). Costo, tiempo, tokens y turnos **se siguen registrando**: dejan
         de ser topes y pasan a ser variables dependientes — un tope habría censurado
         justamente la variable que el experimento compara entre celdas.
         `presupuesto_proporcional` (60/25/15) queda como referencia descriptiva, no como
         umbral. Riesgo asumido explícitamente por el tesista: una celda puede consumir un
         múltiplo de lo previsto sin que nada la detenga.
         **Residuo, que ya no bloquea:** la decisión suscripción contra API key para las 4
         oficiales se toma con el consumo que mida la piloto y se registra en el journal.
         Fuente: `decisiones/ADR-016-sin-topes-de-presupuesto.md`;
         `evaluacion/protocolo.md` v1.2 §6.

8. - [x] **Flagships y plan B de tier medio:** **resuelto** por ADR-009 Decisión 3
         (2026-08-16, Aceptado) — re-pinneo a `claude-opus-5` y
         `gpt-5.6-sol`, con effort fijado en `xhigh` en ambas familias. Los pinneos de
         ADR-005 (`claude-opus-4-8` / `gpt-5.5`) habían quedado una generación atrás.
         **Residuo:** el precio por token de `gpt-5.6-sol` se verificó contra la
         documentación de OpenAI el 2026-08-16 y quedó registrado en
         `runs/piloto-01/precio-gpt-5-6-sol.md`, pero **sin ratificar** — ver ítem 20,
         que sigue formalmente abierto.

9. - [x] **Protocolo v1.1 + ADR de reemplazo de ADR-004:** **cerrado por ADR-012**
         (Aceptado el 2026-08-17, en conjunto con ADR-011). `evaluacion/protocolo.md`
         quedó reescrito como v1.1 y ADR-012 lo congela reemplazando a ADR-004 sin
         editarlo. Los catorce puntos que este ítem enumeraba están consolidados y
         mapeados uno a uno en la tabla de ADR-012 §2–§3: correcciones a `spec-v1.1` /
         «eventual `spec-v1.2`», factor «modelo» redefinido como Claude Code CLI contra
         Codex CLI, model IDs y `effort` referidos a ADR-009 D3, health-check
         autocontenido y smoke de backend con el entorno on-chain,
         `SUITE_CMD_REINICIO_SUT` y `validar-resultados.py` dentro del procedimiento H8,
         regla de continuación de etapa interrumpida cubriendo el corte por rate limit,
         §6 sin tope de turnos, pre-registro de `rol-revisor.md` y partición 465/56 en
         §9, y §10 con el formato CSV de las tres rúbricas y la exclusión de
         `.pipeline/`.
         §6 queda deliberadamente abierta (`PENDIENTE-PILOTO`): es el ítem 7.
         Fuente: ADR-004; `evaluacion/protocolo.md` v1.1;
         `decisiones/ADR-012-protocolo-experimental-v1-1.md`.

10. - [x] **ADR-008 (restricción de la recuperación web): reabierto y cerrado de nuevo.**
          El ADR fue ratificado el 2026-07-07 y su traslado al lado A está en
          `harness_a/orquestar.py` (`--disallowed-tools WebSearch,WebFetch`).
          **Reabierto el 2026-08-23:** el traslado al lado B descansaba en un default de
          producto que resultó **falso**. Medido sobre `codex-cli` 0.146.0: `web_search`
          no viene en `disabled` —una corrida de control registró dos búsquedas contra
          GitHub— y `apps`/`browser_use`/`computer_use` vienen en `true`, con `codex_apps`
          exponiendo los conectores de la cuenta (el agente leyó el perfil y los repos del
          tesista). `--ignore-user-config` no apaga nada de eso.
          **Cerrado por ADR-014**, Aceptado el 2026-08-23:
          `-c web_search="disabled"` más `--disable apps/browser_use/computer_use` en las
          dos celdas B. Con ambas cosas, la corrida de control no registró ningún
          `web_search` ni `mcp_tool_call`; con los `--disable` solos, las búsquedas
          seguían.
          **Lo que el ítem daba por hecho sin chequeo:** `verificar_paridad.py` no
          inspeccionaba ninguna línea de comandos, en **ninguna** de las dos familias.
          Ahora sí (ADR-014 D2), sobre el comando real que arma cada orquestador y no por
          grep del fuente. Ninguna corrida se había ejecutado, así que no hay dato
          contaminado que descartar.
          Fuente: `decisiones/ADR-008-restriccion-recuperacion-web-harness-a.md`;
          `decisiones/ADR-014-recuperacion-web-en-el-harness-b.md`.

11. - [x] **Confinamiento: los agentes corren en contenedores.** **Cerrado por ADR-015**
          (Aceptado el 2026-08-23). El tesista decidió no esperar al dato de la piloto: la
          asimetría —Codex sandboxea el shell por default, Claude Code en headless no— se
          elimina corriendo **las dos familias** en contenedores, sin tocar el sandbox
          nativo de ninguno, así que cada agente sigue viendo el default de su producto.
          Implementado: `pipeline/contenedores/` con `Dockerfile.base` (toolchain
          idéntico) más las capas `Dockerfile.a` / `Dockerfile.b` que sólo instalan su
          CLI, y `pipeline/comun/contenedor.py`, que arma la envoltura **una sola vez**
          para las dos familias — montajes, red, usuario y workdir idénticos por
          construcción.
          **`evaluacion/` no se monta**, así que la no-exposición del holdout (protocolo
          §9) pasa a sostenerla el mecanismo en vez del procedimiento, que era el problema
          real de este ítem. Tampoco se monta `pipeline/` entero: sólo `comun/` y el
          corpus, y el corpus únicamente en las celdas con RAG.
          Credenciales por bind-mount read-only (ADR-015 D3) y **red abierta** en la
          piloto (D4), que registra qué hosts se tocan para decidir una allowlist antes de
          H7. `verificar_paridad.py` chequea la envoltura, que los montajes de A y B sólo
          difieren en el archivo de credenciales, y que ambas capas parten de la misma
          base.
          **Residuo para la piloto:** ninguna imagen se construyó todavía (el daemon de
          Docker estaba abajo), y que los builds de etapa funcionen adentro es parte de lo
          que la piloto valida.
          Fuente: `decisiones/ADR-015-agentes-en-contenedores.md`.

12. - [x] **"Rúbrica del rol revisor del agente":** **implementada y pre-registrada**
          (`evaluacion/rubricas/rol-revisor.md` v1.0, protocolo §9), **ratificada el
          2026-08-17** — no tiene ADR propio: el instrumento lo exige
          ADR-009 Decisión 4 y lo pre-registra el protocolo v1.1 (ítem 9). Mide los tres
          artefactos `.pipeline/revision-<etapa>.md` con un censo de puntos de
          vocabulario cerrado más 12 criterios `RV-01`..`RV-12`, con el mismo
          vocabulario y la misma agregación que las rúbricas de las épicas 10–11.
          No fija umbrales numéricos: no hay datos previos que los justifiquen, así que
          los veredictos son estrictos y la proporción del censo queda como medida
          continua. Si el set de roles cambia en la piloto, se re-pre-registra.
          Dos precondiciones quedan declaradas como no verificadas en el propio
          documento (estado del repo satélite recuperable entre invocaciones de rol;
          granularidad del JSONL de cada familia).
          Fuente: `evaluacion/README.md`; ADR-009 Decisión 4.

13. - [x] **Pin por digest de la imagen de anvil: verificado el 2026-08-23.** El digest
          efectivo de la imagen que `suite-at-anvil` está corriendo —obtenido inspeccionando
          el contenedor, no el ref por el que se hizo pull— es
          `ghcr.io/foundry-rs/foundry@sha256:043752653d5be351c71709091b3db97c4421c907eb40ea294195e7f532aadf46`
          y **coincide** con el que pinnea el compose. Registrado en el manifest
          (`entorno_onchain.version_anvil`), junto a `anvil 1.5.1-stable`.
          Fuente: `evaluacion/suite-at/entorno/docker-compose.yml`;
          `runs/plantillas/manifest.template.yaml` §3.

14. - [x] **Turnos por etapa:** **resuelto** — el tesista decidió el 2026-08-16
          eliminar el presupuesto de turnos. Ningún CLI expone un tope de turnos y no
          se repone en el orquestador; `MAX_TURNS` se retira de
          `pipeline/comun/nucleo.py`. Se cae el tope, **no la métrica**: turnos y
          tokens se siguen registrando (ADR-003), y los topes de costo y tiempo del
          protocolo siguen vigentes. El cambio de protocolo §6 va en el ítem 9.

15. - [x] **Sorteo del orden de las 4 celdas: hecho el 2026-08-23.** Orden sorteado:
          **1. `b-sin-rag` → 2. `a-sin-rag` → 3. `b-con-rag` → 4. `a-con-rag`.**
          Reproducible: `random.Random(int(sha256(<commit>), 16)).shuffle(celdas)` con el
          orden alfabético como lista de partida y el commit `ba0d92b` (HEAD al momento
          del sorteo) como semilla. Se sortea **una sola vez** y no se re-sortea: queda
          asentado acá y en el journal del día.
          Fuente: `evaluacion/protocolo.md` §7.

16. - [x] **Serialización de eventos exóticos: cerrado por mecanismo el 2026-08-24.**
          Medido sobre las tres etapas de `pre-piloto-b`: **0 de 1 107** payloads
          degradados a `str()` por `comun.nucleo.serializar`; el JSONL conserva los
          eventos verbatim (`runs/pre-piloto/matriz-componentes.md`, componente 5.3).
          Lo que el JSONL de B **no** trae no es un problema de serialización sino de
          emisión del CLI: ver ítem 24 y H-23.
          Fuente: `pipeline/comun/nucleo.py` (`serializar`); `pipeline/README.md`
          §"Pendiente para la piloto".

### Ítems abiertos por ADR-009 (2026-08-16)

17. - [x] **Reescritura del pipeline a los CLI: implementada**, sin ADR nuevo (la
          decisión es ADR-009 Decisiones 1, 2 y 4, ya Aceptada). Quedaron escritos
          `harness_a/orquestar.py` y `harness_b/orquestar.py` —delgados sobre `comun/`:
          sólo arman su línea de comando, el bucle de pasos vive en
          `nucleo.correr_etapa`—, el servidor MCP stdio único del RAG
          (`comun/rag/servidor_mcp.py`, misma implementación para las dos familias), los
          prompts de rol en `comun/prompts/roles/`, `etapas.yaml` con `roles` y
          `secuencia`, y `verificar_paridad.py` reescrito a **77 chequeos** contra los
          invariantes de ADR-009/ADR-010. `requirements.txt` pinnea `mcp==1.28.1`,
          PyYAML y pytest, y ya no los dos SDK.
          **Residuos:** (a) la validación end-to-end contra los CLI reales son los ítems
          1 y 2 — hasta hoy sólo dry-runs de las 6 configs, un CLI simulado y el camino
          negativo del verificador; (b) los dos `correr.py` del pipeline SDK siguen en el
          árbol por ADR-009 pero **no corren**: importan `MAX_TURNS` y
          `funcion_consultar_corpus`, que `comun/nucleo.py` ya no exporta, así que el
          camino de vuelta real es el commit `813e774` que ADR-009 fija, no el working
          tree. **Resuelto el 2026-08-17:** se los deja donde están —ADR-009
          §Consecuencias prohíbe borrarlos hasta que la piloto valide el reemplazo— y su
          estado queda documentado en las tres capas: cabecera de cada archivo,
          `requirements.txt` y `pipeline/README.md` §"El pipeline SDK anterior".
          (c) **Snapshot del repo satélite al cierre de cada invocación de rol:**
          **resuelto el 2026-08-17.** `comun.nucleo.snapshot_paso` copia el repo a
          `<...>-snapshots/paso<N>-<rol>/`, al lado del JSONL, con `.git`,
          `node_modules`, `dist`, `build` y `.expo` excluidos, y registra el evento
          `snapshot`; se toma también cuando el paso cortó, que es el estado que pide la
          regla de continuación (protocolo v1.1 §5.8). Se eligió la copia sobre el
          commit para no escribir en el historial del repo generado, y sobre
          re-pre-registrar la rúbrica porque su precondición 2 ya admite «copia que deja
          el orquestador». Al vivir en el núcleo es idéntico en las 4 celdas por
          construcción. Verificado con un árbol de juguete (exclusiones efectivas); la
          corrida real lo ejercita en la piloto.
          Fuente: ADR-009 Decisiones 1, 2 y 4; `pipeline/README.md`.

18. - [x] **Regla de scoping de las métricas estáticas: `.pipeline/` excluido.**
          Implementada en `evaluacion/metricas-estaticas/medir.sh`, agregando el
          directorio a la lista `EXCL_DIRS` que alimenta a los cuatro consumidores
          (cloc, lizard, jscpd y el `find` de manifiestos), y documentada en el README
          de la carpeta. **Deadline duro cumplido:** entró antes de la piloto, igual que
          el ítem 4. Se pre-registra en el protocolo v1.1 (ítem 9).
          Verificado con las tres herramientas pinneadas contra un árbol de juguete: el
          `ignore` de jscpd es load-bearing (jscpd escanea directorios ocultos por
          default).
          Fuente: ADR-009 Decisión 4 y Consecuencias.

19. - [ ] **Verificaciones de los CLI que la piloto debe cerrar:** que
          `-c developer_instructions=…` llega efectivamente al modelo en un
          `codex exec` real (hoy sólo verificado con el oráculo
          `codex debug prompt-input`, que lo muestra como primer `input_text` del
          mensaje `developer`), y el comportamiento de ambos CLI ante un rate
          limit a mitad de etapa (¿pausan? ¿cortan?), que con suscripciones es la
          restricción vinculante en lugar del tope de costo.
          Se suman los nombres exactos de los campos de tokens de `turn.completed`:
          `nucleo.costo_estimado_usd` no está cableada en vivo justamente porque
          adivinar ese esquema sería inventarlo.
          **Medido en la pre-piloto (2026-08-24) y su cierre (2026-09-06):**
          (a) campos de `turn.completed.usage` pinneados —`input_tokens`,
          `cached_input_tokens`, `cache_write_input_tokens`, `output_tokens`,
          `reasoning_output_tokens`— y el estimador corregido sobre ellos (H-14);
          (b) `-c developer_instructions` llega al modelo en `codex exec` real: en el
          paso `revisor` de las tres etapas de B el único `file_change` fue el archivo de
          revisión y el modelo anunció «ninguna modificará archivos», que es el punto 1
          del prompt del rol; (c) el rate limit a mitad de etapa **no ocurrió**: A emitió
          11 `rate_limit_event`, todos `allowed`, y B ninguno — el comportamiento ante el
          corte sigue sin medir. Queda abierto por (c) y porque el consumo de B no incluye
          a sus subagentes (H-23).
          Fuente: ADR-009 §Evidencia verificada y §Consecuencias.

20. - [x] **Precio por token de `gpt-5.6-sol`: ratificado el 2026-08-23** por el
          tesista. Queda vigente la tabla de dos tramos de
          `runs/piloto-01/precio-gpt-5-6-sol.md`, verificada contra la documentación de
          OpenAI el 2026-08-16: contexto corto (≤ 272 000 tokens de input) a USD 5/M
          entrada y 30/M salida; contexto largo (> 272 000) a 10/M y 45/M, con el recargo
          aplicado al **request completo**. `nucleo.PRECIOS_USD_POR_MTOK` decide tramo por
          request; el centinela `PRECIO_PENDIENTE` no vuelve.
          **Consecuencia que queda declarada, no resuelta:** el pareo por precio de
          ADR-009 D3 se sostiene en el tramo corto y **no** en el largo (2.00× entrada,
          1.80× salida), y ese tramo no es hipotético — el turno de 294 318 tokens de
          ADR-010 D2 ya cae dentro. Sumado a `analisis/amenazas-validez.md` el
          2026-08-23.
          Fuente: ADR-009 Decisión 3; `runs/piloto-01/precio-gpt-5-6-sol.md`.

21. - [x] **Modelos del agente evaluador y del chequeo espejo:** **resuelto** por
          ADR-010 Decisión 3 — juez white-box `claude-opus-4-8` → **`claude-opus-5`**,
          espejo `gpt-5.5` → **`gpt-5.6-sol`**, y el runtime pasa del Claude Agent SDK a
          `claude -p`. Restaura el diseño original de ADR-007 (juez == generador de la
          celda A), bajo el cual se pre-registraron sus cinco mitigaciones de
          self-preference. El briefing congelado no se toca. **Aplicado** a
          `evaluacion/agente-evaluador/`: `modelo_evaluador` en `plantilla-resultados.yaml`
          y el README nuevo de la carpeta, que documenta el runtime y el espejo; no
          queda referencia viva al SDK.

22. - [ ] **Compactación del harness B con historia larga (multi-turno).** ADR-010 D2
          fija `-c model_context_window=1000000`, pero su efecto **no está verificado**.
          Lo que sí se verificó el 2026-08-16: un turno único con 294 318 tokens de input
          completa **con y sin** el override, o sea que los 272 000 del catálogo **no son
          un tope a nivel de request**; lo que el parámetro gobierna, junto con
          `effective_context_window_percent: 95`, es el umbral de **auto-compactación** al
          acumular historia entre turnos (≈ 258 400 por default, ≈ 950 000 con el
          override), y un turno único no ejercita eso.
          A verificar en la piloto: correr una etapa cuya historia supere los 258 400
          tokens y registrar si el harness compacta. Si compacta igual, el override es
          inocuo pero inútil y la asimetría vuelve a estar viva.
          **Se suma una discrepancia sin resolver:** `codex debug models` reporta
          `context_window` y `max_context_window` = 272 000 para `gpt-5.6-sol`, mientras
          que la página del modelo de OpenAI dice 1 050 000. Que el 272 000 del CLI
          coincida exactamente con el umbral de facturación del tramo corto sugiere que
          el catálogo pinnea el límite de precio y no la capacidad del modelo. Toca la
          asimetría de ventana que ADR-009 D3 declaró (1 000 000 contra 272 000).
          Fuente: ADR-010 Decisión 2; `runs/piloto-01/precio-gpt-5-6-sol.md`.
          Decisión esperada: efecto del parámetro medido, y la asimetría de compactación
          A/B cerrada o declarada como limitación antes de H7.
          **Pre-piloto (2026-08-24):** ninguna compactación observable en el `--json` de B
          ni en el stream de A (sin `compact_boundary`). Pero el `--json` de B no es un
          oráculo válido para esto: no emite eventos de sesión. Con ADR-023 los rollouts
          de B quedan en los logs y la piloto puede leer ahí si compactó.

23. - [x] **Techo de 1 048 576 caracteres por input en el CLI de Codex** (verificado:
          `turn/start` rechaza con `input_too_large` / `max_chars`, independiente de los
          tokens). Los prompts de etapa y de rol están muy por debajo, pero el archivo de
          handoff bajo `.pipeline/` puede crecer: si un `revisor` produce una revisión
          enorme, el pase correctivo puede chocar con el techo. Vigilar en la piloto y, si
          aparece, acotar el tamaño del handoff por prompt (idéntico en las 4 celdas).
          **Mitigado parcialmente por el ítem 17:** el prompt transporta la **ruta** del
          archivo de handoff, no su contenido, así que el techo sólo se alcanzaría si el
          rol decide leerlo y citarlo entero.
          **Cerrado el 2026-09-06 con el dato de la pre-piloto:** 0 errores
          `input_too_large` en las 9 invocaciones de B; los handoffs más grandes fueron los
          de A (9 072 bytes, `revision-mobile.md`), dos órdenes de magnitud bajo el techo.
          Se vigila igual en la piloto, sin acción pendiente.
          Fuente: ADR-010 Decisión 2.

24. - [ ] **Fan-out efectivo de la delegación en cada familia.** ADR-010 D1 instruye
          delegación con texto byte-idéntico, pero la instrucción cae sobre un modelo que
          ya delega por default (A) y sobre otro cuyo `<multi_agent_mode>` la mantiene
          apagada hasta que se la piden (B). Medir cuántos subagentes abre cada familia y
          con qué profundidad. Si la diferencia es desproporcionada, **no** se tunea la
          instrucción por familia (rompería la paridad de prompts): se declara, o se pone
          un tope numérico idéntico en el texto compartido vía ADR antes de H7.
          Además: verificar que el JSONL capture la actividad de subagentes y no sólo la
          del agente principal. En A ya está resuelto: el orquestador pasa
          `--forward-subagent-text` y `nucleo.evento_cli` deriva `subagente` de
          `parent_tool_use_id`. En B ese campo no existe y el derivador devuelve `None`:
          **qué evento del JSONL de `codex exec --json` identifica a un subagente es
          justamente lo que la piloto tiene que pinnear.**
          **Medido el 2026-09-06 (H-23): ninguno.** `codex exec --json` no emite el
          `spawn_agent` ni la actividad del subagente; sólo un `collab_tool_call` de
          `wait` con `receiver_thread_ids: []`, que es lo que la pre-piloto leyó como «B
          no delegó» (H-22, corregido). El registro está en los rollouts de
          `$CODEX_HOME/sessions/` (`session_meta.thread_source == "subagent"`,
          `parent_thread_id`), que la pre-piloto perdió y que **ADR-023** persiste en los
          logs. El fan-out de B se mide en la piloto sobre esos rollouts; A ya está
          medido (1 736 de 7 612 eventos).
          Fuente: ADR-010 Decisión 1; ADR-023.
