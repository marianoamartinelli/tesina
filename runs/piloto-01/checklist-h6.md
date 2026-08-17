# Checklist H6 — entrada y salida de la corrida piloto

Consolida la deuda de proceso que la ventana de ajuste de la
piloto (H6, única ventana legítima según ADR-004) debe resolver antes de congelar
el protocolo definitivo. La ventana comprende **piloto-01** (corrida completa con
el harness A) y **piloto-02** (smoke end-to-end del harness B). Ningún ítem se
resuelve editando `spec/` (congelada, tag `spec-v1.1`) ni ADRs aceptados: los
cambios van por nueva versión de documento + ADR nuevo donde corresponda.

**Estado al 2026-08-17:** 11 de los 24 ítems de salida cerrados, los cinco que esperaban
ratificación (3, 4, 5, 9 y 12) incluidos: **ADR-011, ADR-012 y ADR-013 quedaron Aceptados
el 2026-08-17**. De los 13 abiertos, once necesitan ejecutar algo
(1, 2, 6, 7, 11, 13, 16, 19, 22, 23, 24: la corrida piloto o el entorno docker), uno es
el sorteo del orden de celdas (15) y uno es la ratificación del precio de `gpt-5.6-sol`
(20). Ningún CLI de agente se ejecutó todavía.

## Entrada — precondiciones verificables antes de iniciar

Los checkboxes de esta sección son **puertas de arranque**: se verifican en el momento
de iniciar la corrida, no de una vez y para siempre. Las anotaciones registran el último
resultado observado.

- [ ] **Paridad:** `pipeline/verificar_paridad.py` termina con exit 0
      (`.venv/bin/python pipeline/verificar_paridad.py`).
      *Verificado el 2026-08-16: exit 0, 77 chequeos, sobre el working tree **sin
      commitear**. Re-correr sobre el commit de `pipeline/`.*
- [ ] **Manifest:** secciones §1–4 de `runs/piloto-01/manifest.yaml` completas y
      **commiteadas antes de iniciar** (protocolo §3 paso 2), incluidos los campos
      `paridad_verificada`, `entorno_host` y `entorno_onchain` de la plantilla.
      *El manifest existe; los campos que sólo se pueden medir al arrancar (modo de
      auth, digest efectivo de anvil, dirección del USDC-mock, repo satélite, hash de
      paridad sobre el commit) están marcados `PENDIENTE-ARRANQUE:` con el comando que
      los cierra. Falta completarlos y commitearlo.*
- [ ] **Autenticación:** con ADR-009 la piloto corre sobre las **suscripciones** del
      tesista (`claude` y `codex` logueados), no sobre API keys. Verificar la sesión de
      cada CLI y registrar en el manifest el modo de auth usado; el dato de consumo de
      la piloto decide suscripción contra API key para las 4 oficiales.
- [ ] **Versiones de CLI pinneadas** en el manifest: `claude --version` y
      `codex --version` (hoy 2.1.233 y 0.146.0), junto a los model IDs y al commit del
      corpus. *Ya registrados en el manifest, medidos en esta máquina el 2026-08-16.*
- [ ] **Entorno on-chain arriba** (`evaluacion/suite-at/entorno/`):
      `docker compose up -d --wait`, luego `desplegar-usdc.py` y `fondear.py`.
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

7. - [ ] **Presupuestos definitivos:** los valores de protocolo §6 (200 USD /
         24 h / tokens sin tope) son provisionales; pinnear los definitivos. Con
         ADR-009 el presupuesto de turnos desaparece (ítem 14) y, si las oficiales
         corren sobre suscripción, `costo_max_usd` deja de ser el tope vinculante:
         pasan a serlo los rate limits, que son asimétricos entre proveedores y no
         se controlan. La piloto mide el consumo real y de ahí sale la decisión
         suscripción contra API key.
         El protocolo v1.1 (ítem 9) deja §6 explícitamente abierto: marca
         `PENDIENTE-PILOTO` los presupuestos definitivos y la decisión
         suscripción-contra-API-key, sin introducir ningún número nuevo.
         Fuente: ADR-004, punto 4 de la Decisión; ADR-009 §Consecuencias;
         `evaluacion/protocolo.md` §6.
         Decisión esperada: presupuestos definitivos en el protocolo y en el
         manifest de cada corrida oficial.

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

10. - [x] **ADR-008 (restricción de WebSearch/WebFetch en el harness A):**
          **resuelto** — ratificado por el tesista el 2026-07-07 en la revisión
          del PR #1; el ADR pasó a Aceptado. La restricción se trasladó al orquestador
          CLI del ítem 17: `harness_a/orquestar.py` pasa
          `--disallowed-tools WebSearch,WebFetch`, y `verificar_paridad.py` lo chequea.
          Fuente: `decisiones/ADR-008-restriccion-recuperacion-web-harness-a.md`.

11. - [ ] **Confinamiento del harness A** (reformulado por ADR-009): con los CLI la
          asimetría se invierte — Codex sandboxea el shell por default
          (`-s workspace-write`) y Claude Code en headless no. Probar el permission
          mode y las deny rules de A, y verificar que el repo satélite y los logs
          queden fuera del árbol de la tesina.
          **Estado tras el ítem 17:** el orquestador A usa
          `--dangerously-skip-permissions` (el binario 2.1.233 rechaza
          `--permission-mode bypassPermissions` si la sesión no se lanzó con ese flag),
          o sea sin sandbox del SO: `Bash` y `Read` pueden leer fuera del cwd, incluida
          `evaluacion/` — la condición de no-exposición del holdout (protocolo §9) hoy
          la sostiene sólo el procedimiento. Falta probarlo con el CLI real y decidir si
          se agrega confinamiento del lado A o se declara la asimetría.
          Decisión esperada: confinamiento decidido y registrado; asimetría A/B
          igualada o declarada como amenaza (ver `analisis/amenazas-validez.md`).

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

13. - [ ] **Pin por digest de la imagen de anvil:** el compose pinnea por digest
          (el tag `ghcr.io/foundry-rs/foundry:stable` a secas es flotante);
          verificar en la piloto que la imagen efectiva corresponde a ese digest
          y registrarla en el manifest (`entorno_onchain.version_anvil`, vía
          `docker inspect --format '{{index .RepoDigests 0}}' ...`).
          Fuente: `evaluacion/suite-at/entorno/docker-compose.yml`;
          `runs/plantillas/manifest.template.yaml` §3.
          Decisión esperada: digest verificado y versión efectiva registrada.

14. - [x] **Turnos por etapa:** **resuelto** — el tesista decidió el 2026-08-16
          eliminar el presupuesto de turnos. Ningún CLI expone un tope de turnos y no
          se repone en el orquestador; `MAX_TURNS` se retira de
          `pipeline/comun/nucleo.py`. Se cae el tope, **no la métrica**: turnos y
          tokens se siguen registrando (ADR-003), y los topes de costo y tiempo del
          protocolo siguen vigentes. El cambio de protocolo §6 va en el ítem 9.

15. - [ ] **Sorteo del orden de las 4 celdas** antes de H7, registrado en el
          journal (mitigación del efecto aprendizaje del evaluador).
          Fuente: `evaluacion/protocolo.md` §7.
          Decisión esperada: orden sorteado una única vez y asentado en journal.

16. - [ ] **Serialización de eventos exóticos:** revisar en los JSONL de la
          piloto que la degradación a `str()` de `comun.nucleo.serializar` no
          pierda información relevante para el meta-análisis.
          Fuente: `pipeline/comun/nucleo.py` (`serializar`); `pipeline/README.md`
          §"Pendiente para la piloto".
          Decisión esperada: serialización ratificada o ajustada antes de las
          oficiales.

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
          Fuente: ADR-009 §Evidencia verificada y §Consecuencias.

20. - [ ] **Precio por token de `gpt-5.6-sol`:** **verificado y registrado, pendiente de
          ratificación del tesista.** `runs/piloto-01/precio-gpt-5-6-sol.md` documenta,
          contra dos páginas de la documentación de OpenAI consultadas el 2026-08-16,
          dos tramos: contexto corto (≤ 272 000 tokens de input) a USD 5/M entrada y
          30/M salida, y contexto largo (> 272 000) a 10/M y 45/M, con el recargo
          aplicado al request completo. Consecuencia: el pareo por precio de ADR-009 D3
          se sostiene en el tramo corto (entrada idéntica, salida 20 % más cara en B —
          la misma asimetría que ADR-005 ya había aceptado) y **no** se sostiene en el
          largo (2.00x entrada, 1.80x salida); ese tramo no es hipotético, el turno de
          294 318 tokens de ADR-010 D2 ya cayó dentro. La tabla se cargó en
          `nucleo.PRECIOS_USD_POR_MTOK` con decisión de tramo por request.
          Tildar este ítem —o rechazar el dato, en cuyo caso vuelve el centinela
          `PRECIO_PENDIENTE`— es del tesista. Bloquea las corridas oficiales, no la
          piloto.
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

23. - [ ] **Techo de 1 048 576 caracteres por input en el CLI de Codex** (verificado:
          `turn/start` rechaza con `input_too_large` / `max_chars`, independiente de los
          tokens). Los prompts de etapa y de rol están muy por debajo, pero el archivo de
          handoff bajo `.pipeline/` puede crecer: si un `revisor` produce una revisión
          enorme, el pase correctivo puede chocar con el techo. Vigilar en la piloto y, si
          aparece, acotar el tamaño del handoff por prompt (idéntico en las 4 celdas).
          **Mitigado parcialmente por el ítem 17:** el prompt transporta la **ruta** del
          archivo de handoff, no su contenido, así que el techo sólo se alcanzaría si el
          rol decide leerlo y citarlo entero.
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
          Fuente: ADR-010 Decisión 1.
