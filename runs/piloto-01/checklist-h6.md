# Checklist H6 — entrada y salida de la corrida piloto

Consolida la deuda de proceso que la ventana de ajuste de la
piloto (H6, única ventana legítima según ADR-004) debe resolver antes de congelar
el protocolo definitivo. La ventana comprende **piloto-01** (corrida completa con
el harness A) y **piloto-02** (smoke end-to-end del harness B). Ningún ítem se
resuelve editando `spec/` (congelada, tag `spec-v1.1`) ni ADRs aceptados: los
cambios van por nueva versión de documento + ADR nuevo donde corresponda.

## Entrada — precondiciones verificables antes de iniciar

- [ ] **Paridad:** `pipeline/verificar_paridad.py` termina con exit 0
      (`.venv/bin/python pipeline/verificar_paridad.py`).
- [ ] **Manifest:** secciones §1–4 de `runs/piloto-01/manifest.yaml` completas y
      **commiteadas antes de iniciar** (protocolo §3 paso 2), incluidos los campos
      `paridad_verificada`, `entorno_host` y `entorno_onchain` de la plantilla.
- [ ] **Autenticación:** con ADR-009 la piloto corre sobre las **suscripciones** del
      tesista (`claude` y `codex` logueados), no sobre API keys. Verificar la sesión de
      cada CLI y registrar en el manifest el modo de auth usado; el dato de consumo de
      la piloto decide suscripción contra API key para las 4 oficiales.
- [ ] **Versiones de CLI pinneadas** en el manifest: `claude --version` y
      `codex --version` (hoy 2.1.233 y 0.146.0), junto a los model IDs y al commit del
      corpus.
- [ ] **Entorno on-chain arriba** (`evaluacion/suite-at/entorno/`):
      `docker compose up -d --wait`, luego `desplegar-usdc.py` y `fondear.py`.
- [ ] **Harness de evaluación sano:** `evaluacion/suite-at/test_smoke.py` todo
      verde (no requiere SUT ni docker):
      `cd evaluacion/suite-at && ../../.venv/bin/python -m pytest test_smoke.py -q`.
- [ ] **Regla de no-exposición presente:** la suite de ATs **no** se corre contra
      el SUT generado durante la generación (protocolo §4;
      `evaluacion/suite-at/README.md`). Sólo el smoke check de avance de etapa.

## Salida — pendientes que la ventana debe resolver

1. - [ ] **Ejecución end-to-end del harness A** con piloto-01: primera corrida real
         (hasta hoy sólo dry-runs). Con ADR-009 es contra `claude -p` bajo
         suscripción, no contra la API, y depende de que el ítem 17 esté hecho.
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
         Fuente: `pipeline/README.md` §"Pendiente para la piloto".
         Decisión esperada: harness B validado en cada punto o ajustes
         registrados antes de las corridas oficiales.

3. - [ ] **Status HTTP del reenvío idempotente de retiros** (los 2 TODO-REVISAR
         abiertos): ratificar el criterio `{200, 202}` quitando las marcas de
         `evaluacion/suite-at/tests/test_ep08_solicitud.py:349` y `:386` y
         documentando el criterio, y/o registrarlo como candidato a reapertura de
         spec (ADR estilo 006) para una eventual `spec-v1.2` — **nunca** editando
         `spec-v1.1`.
         Fuente: `test_ep08_solicitud.py:349,386`.
         Decisión esperada: 0 TODO-REVISAR en la suite al cierre de la ventana.

4. - [ ] **Sobre-declaración F3** (ciclo de vida del SUT): migrar a tests
         black-box condicionales los 10 migrables limpios (AT-04-01-11,
         AT-04-04-12, AT-04-05-13, AT-06-01-07, AT-06-01-08, AT-06-02-06,
         AT-06-03-06, AT-07-04-07, AT-07-04-11, AT-08-03-08); decidir por AT los
         parciales (AT-05-03-07; AT-07-04-01/03); reescribir los motivos de los
         que queden white-box. En el mismo movimiento, actualizar el conteo 66 en
         `no-automatizables.yaml`, `rubrica-white-box.md`,
         `plantilla-resultados.yaml`, `briefing.md`, `evaluacion/README.md`,
         `suite-at/README.md`, `HELPERS.md` y el ADR que complete ADR-007.
         **Deadline duro:** antes de ver implementación alguna (protocolo §9: la
         suite no se modifica después de vista una implementación).
         Fuente: `journal/2026-07-06-agente-evaluador-white-box.md` §Pendientes,
         punto 1.
         Decisión esperada: partición final automatizable/white-box cerrada y
         consistente en los 8 documentos.

5. - [ ] **Mecanismo de importar mnemonic** para los ATs de provisioning de la
         épica 06 (la spec no fija el mecanismo; la rúbrica hoy da fallback
         F1 + `PRECONDICION_IMPOSIBLE`).
         Fuente: `journal/2026-07-06-agente-evaluador-white-box.md` §Pendientes,
         punto 2.
         Decisión esperada: convención de entorno fijada (o fallback ratificado),
         registrada donde corresponda.

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
         Fuente: ADR-004, punto 4 de la Decisión; ADR-009 §Consecuencias.
         Decisión esperada: presupuestos definitivos en el protocolo v1.1 y en el
         manifest de cada corrida oficial.

8. - [x] **Flagships y plan B de tier medio:** **resuelto** por ADR-009 Decisión 3
         (2026-08-16, Aceptado) — re-pinneo a `claude-opus-5` y
         `gpt-5.6-sol`, con effort fijado en `xhigh` en ambas familias. Los pinneos de
         ADR-005 (`claude-opus-4-8` / `gpt-5.5`) habían quedado una generación atrás.
         **Queda vivo un residuo:** verificar el precio por token de `gpt-5.6-sol`
         contra la documentación de OpenAI (el catálogo del CLI no lo expone), porque
         de ahí sale la paridad de precio del pareo y la estimación de costo del
         harness B. Bloquea las corridas oficiales, no la piloto.

9. - [ ] **Protocolo v1.1 + ADR de reemplazo de ADR-004**, consolidando:
         referencias a `spec-v1.1` en §2.1 y §3 paso 1; §8 punto 3 → "eventual
         `spec-v1.2`"; health-check autocontenido en §4 (cosmético);
         `SUITE_CMD_REINICIO_SUT` como parte del procedimiento H8;
         `validar-resultados.py` como paso previo al arbitraje de pasadas del
         agente evaluador; regla de continuación de etapa interrumpida
         (re-invocar el orquestador sobre el estado actual del repo, sesión fresca
         del CLI sin resume, clasificada D2 + intervención tipo (d); los cortes por
         tope de turnos —`error_max_turns` en A, `MaxTurnsExceeded` en B— dejan de
         existir con ADR-009 y la regla debe cubrir en cambio el corte por rate
         limit); procedimiento del smoke de backend con el entorno
         on-chain; formato CSV de las rúbricas en §10; incorporación del agente
         evaluador white-box ya prevista (ADR-007 §5); y constancia de que la
         ventana H6 comprendió piloto-01 (A completa) y piloto-02 (B smoke).
         **Sumado por ADR-009 (2026-08-16):** §1 y §2 punto 3 definen el factor
         «modelo» como «Claude / Claude Agent SDK» vs «GPT / OpenAI Agents SDK» — pasa
         a ser Claude Code CLI vs Codex CLI; §2 punto 4 refiere los model IDs a
         ADR-005 (hoy ADR-009); §6 pierde el presupuesto de turnos y gana la salvedad
         de que, bajo suscripción, el tope vinculante son los rate limits y no
         `costo_max_usd`; §10 suma la regla de exclusión de `.pipeline/` en las
         métricas estáticas (ítem 18).
         Fuente: ADR-004; `evaluacion/protocolo.md`; ADR-006; ADR-007 §5; ADR-009.
         Decisión esperada: protocolo v1.1 congelado por ADR nuevo antes de la
         primera corrida oficial.

10. - [x] **ADR-008 (restricción de WebSearch/WebFetch en el harness A):**
          **resuelto** — ratificado por el tesista el 2026-07-07 en la revisión
          del PR #1; el ADR pasó a Aceptado y el código de
          `pipeline/harness_a/correr.py` ya es consistente con la decisión.
          Fuente: `decisiones/ADR-008-restriccion-recuperacion-web-harness-a.md`.

11. - [ ] **Confinamiento del harness A** (reformulado por ADR-009): con los CLI la
          asimetría se invierte — Codex sandboxea el shell por default
          (`-s workspace-write`) y Claude Code en headless no. Probar el permission
          mode y las deny rules de A, y verificar que el repo satélite y los logs
          queden fuera del árbol de la tesina.
          Decisión esperada: confinamiento decidido y registrado; asimetría A/B
          igualada o declarada como amenaza (ver `analisis/amenazas-validez.md`).

12. - [ ] **"Rúbrica del rol revisor del agente":** ADR-009 Decisión 4 introduce un rol
          `revisor` en el set de roles, así que el instrumento **se construye y
          pre-registra** antes de H7 — no es ya una decisión abierta sino una
          consecuencia del set de roles. Si el set de roles cambia en la piloto, este
          ítem lo sigue.
          Fuente: `evaluacion/README.md` §"Contenido pendiente de decisión (H6)";
          ADR-009 Decisión 4.

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
          Fuente: `pipeline/comun/nucleo.py:174`; `pipeline/README.md`
          §"Pendiente para la piloto".
          Decisión esperada: serialización ratificada o ajustada antes de las
          oficiales.

### Ítems abiertos por ADR-009 (2026-08-16)

17. - [ ] **Reescritura del pipeline a los CLI:** `harness_a/orquestar.py` y
          `harness_b/orquestar.py` sobre `comun/`; servidor MCP stdio único para el
          RAG; prompts de rol en `comun/prompts/roles/`; `verificar_paridad.py`
          reescrito contra los nuevos invariantes; baja de `correr.py` (ambos) y de
          `requirements.txt`. No se borra nada del pipeline SDK hasta que la piloto
          valide el reemplazo.
          Fuente: ADR-009 Decisiones 1, 2 y 4.

18. - [ ] **Regla de scoping de las métricas estáticas: el tooling de H5 excluye
          `.pipeline/`** (los artefactos de handoff entre roles). **Deadline duro:
          antes de la piloto** — ajustar el alcance de una métrica después de ver una
          implementación viola el mismo criterio de congelamiento del protocolo §9,
          igual que el ítem 4. Se pre-registra en el protocolo v1.1 (ítem 9).
          Fuente: ADR-009 Decisión 4 y Consecuencias.

19. - [ ] **Verificaciones de los CLI que la piloto debe cerrar:** que
          `-c developer_instructions=…` llega efectivamente al modelo en un
          `codex exec` real (hoy sólo verificado con el oráculo
          `codex debug prompt-input`), y el comportamiento de ambos CLI ante un rate
          limit a mitad de etapa (¿pausan? ¿cortan?), que con suscripciones es la
          restricción vinculante en lugar del tope de costo.
          Fuente: ADR-009 §Evidencia verificada y §Consecuencias.

20. - [ ] **Precio por token de `gpt-5.6-sol`:** verificar contra la documentación de
          OpenAI y registrarlo (residuo del ítem 8; alimenta la paridad de precio del
          pareo y la estimación de costo del harness B). Bloquea las corridas
          oficiales, no la piloto.
          Fuente: ADR-009 Decisión 3.

21. - [x] **Modelos del agente evaluador y del chequeo espejo:** **resuelto** por
          ADR-010 Decisión 3 — juez white-box `claude-opus-4-8` → **`claude-opus-5`**,
          espejo `gpt-5.5` → **`gpt-5.6-sol`**, y el runtime pasa del Claude Agent SDK a
          `claude -p`. Restaura el diseño original de ADR-007 (juez == generador de la
          celda A), bajo el cual se pre-registraron sus cinco mitigaciones de
          self-preference. El briefing congelado no se toca. Queda por aplicarlo a
          `evaluacion/agente-evaluador/` al implementar el ítem 17.

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
          Fuente: ADR-010 Decisión 2.
          Decisión esperada: efecto del parámetro medido, y la asimetría de compactación
          A/B cerrada o declarada como limitación antes de H7.

23. - [ ] **Techo de 1 048 576 caracteres por input en el CLI de Codex** (verificado:
          `turn/start` rechaza con `input_too_large` / `max_chars`, independiente de los
          tokens). Los prompts de etapa y de rol están muy por debajo, pero el archivo de
          handoff bajo `.pipeline/` puede crecer: si un `revisor` produce una revisión
          enorme, el pase correctivo puede chocar con el techo. Vigilar en la piloto y, si
          aparece, acotar el tamaño del handoff por prompt (idéntico en las 4 celdas).
          Fuente: ADR-010 Decisión 2.

24. - [ ] **Fan-out efectivo de la delegación en cada familia.** ADR-010 D1 instruye
          delegación con texto byte-idéntico, pero la instrucción cae sobre un modelo que
          ya delega por default (A) y sobre otro cuyo `<multi_agent_mode>` la mantiene
          apagada hasta que se la piden (B). Medir cuántos subagentes abre cada familia y
          con qué profundidad. Si la diferencia es desproporcionada, **no** se tunea la
          instrucción por familia (rompería la paridad de prompts): se declara, o se pone
          un tope numérico idéntico en el texto compartido vía ADR antes de H7.
          Además: verificar que el JSONL capture la actividad de subagentes y no sólo la
          del agente principal (en A, `--forward-subagent-text`; en B, eventos de thread).
          Fuente: ADR-010 Decisión 1.
