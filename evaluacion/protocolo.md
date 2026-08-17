# Protocolo experimental pre-registrado — v1.1

- **Estado:** esta versión reemplaza a la **v1.0**, congelada por
  [ADR-004](../decisiones/ADR-004-protocolo-experimental-preregistrado.md) (2026-07-05).
  La congela [ADR-012](../decisiones/ADR-012-protocolo-experimental-v1-1.md), **Aceptado**
  el 2026-08-17: rige desde esa fecha y antes de la primera corrida oficial. ADR-004
  no se edita; ADR-012 enumera qué de su Decisión se conserva y qué se reemplaza, y lleva
  el detalle cambio por cambio de v1.0 → v1.1.
- **Ventana de ajuste:** la única prevista por ADR-004 punto 2 — los defectos que revele
  la **corrida piloto** (H6). Esta versión consolida esa ventana. Si la piloto revela
  defectos adicionales, se produce una v1.2 más un ADR que reemplace a ADR-012,
  **antes** de la primera corrida oficial. Durante las corridas oficiales (H7) el
  protocolo es **inmutable**.
- **Propósito:** fijar, antes de cualquier corrida, las reglas que hacen comparables a
  las 4 celdas del factorial 2×2: cuándo interviene el humano y cómo se clasifica cada
  intervención, en qué orden se construye, con qué presupuestos, qué se registra y cómo.
  Todo criterio definido "sobre la marcha" invalidaría la comparación entre celdas.

---

## 1. Diseño experimental (referencia)

Factorial 2×2 — factor **modelo** (A: **Claude Code CLI**, `claude -p`; B: **Codex CLI**,
`codex exec`) × factor **RAG** (sin / con corpus de BIPs y EIPs). El factor "modelo" es
la comparación producto-contra-producto entre los dos agentes de coding que cada
proveedor publica como su oferta principal
([ADR-009](../decisiones/ADR-009-harnesses-como-cli-y-orquestador-de-roles.md)
Decisión 1); en v1.0 este factor estaba definido sobre los SDK de agentes de cada
proveedor.

Cuatro corridas oficiales (`a-sin-rag`, `a-con-rag`, `b-sin-rag`, `b-con-rag`) más la
**ventana piloto (H6)**, descartable, que comprende dos corridas: **`piloto-01`**
(corrida completa con el harness A) y **`piloto-02`** (smoke end-to-end del harness B
sobre una etapa acotada). Ninguna de las dos entra en el dataset; sus manifests e
intervenciones se marcan como descartables.

Variables dependientes (según la propuesta): tasa de ATs superados por AT-id,
intervenciones humanas por causa raíz, alucinaciones de dominio, métricas estáticas,
adherencia a estándares on-chain.

## 2. Variables controladas (constantes entre celdas)

Idénticos en las 4 corridas oficiales, pinneados en el manifest de cada corrida
**antes** de iniciarla:

1. **La spec:** el commit del tag `spec-v1.1`
   ([ADR-006](../decisiones/ADR-006-reapertura-controlada-spec-v1.1.md)). Es el único
   contenido del repo satélite al arrancar.
2. **El corpus RAG** (sólo celdas con RAG): mismo commit de `corpus/` para ambas, servido
   por un único servidor MCP stdio compartido por las dos familias (ADR-009 Decisión 2).
3. **El pipeline:** mismas etapas y mismo orden; mismos prompts de sistema, de etapa y de
   **rol**; mismo set de roles y misma secuencia por etapa (`implementador` → `revisor` →
   pase correctivo), definidos una sola vez en `pipeline/comun/etapas.yaml` y
   `pipeline/comun/prompts/` (ADR-009 Decisión 4;
   [ADR-010](../decisiones/ADR-010-delegacion-contexto-y-evaluador.md) Decisión 1); mismas
   herramientas habilitadas. Sólo cambian la familia de harness y el conmutador RAG. La
   paridad se verifica mecánicamente con `pipeline/verificar_paridad.py` antes de cada
   corrida.
4. **Los model IDs y el `effort`:** exactos, pinneados por ADR-009 Decisión 3
   (`claude-opus-5` en A, `gpt-5.6-sol` en B; `effort: xhigh` en ambas familias, porque
   los defaults de los CLI no coinciden). El manifest registra además la **versión exacta
   de cada CLI** (ADR-009 Decisión 5) y, en las celdas B, `model_context_window`
   (ADR-010 Decisión 2).
5. **El evaluador humano:** el tesista, en todas las corridas.
6. **Este protocolo:** criterios de intervención, presupuestos y registro.
7. **La ventana temporal:** las 4 corridas oficiales se ejecutan en una ventana corta
   (objetivo: ≤ 2 semanas entre la primera y la última) para minimizar la deriva de los
   modelos comerciales.

## 3. Secuencia de una corrida (idéntica ×5)

1. **Crear el repo satélite limpio** (`tesina-run-<id>`) que contiene únicamente la
   spec pinneada a `spec-v1.1`. Registrar el hash del commit inicial.
2. **Completar y commitear el manifest** (secciones 1–4 de
   `runs/plantillas/manifest.template.yaml`) antes de que el agente ejecute nada.
3. **Ejecutar el pipeline** con la configuración de la celda, en el orden de
   construcción de la sección 4.
4. **Registrar cada intervención humana en el momento** (sección 5), en
   `runs/<id>/intervenciones.md`.
5. **Cerrar la corrida:** completar la sección 5 del manifest (timestamps, costo,
   tokens, total de intervenciones) y **congelar el repo satélite** (sólo lectura).
   Cualquier corrección posterior invalida la medición.
6. **Evaluar** (H8, posterior e independiente), en este orden:
   1. Levantar el entorno on-chain y arrancar el SUT congelado con el contrato de
      arranque (`suite-at/entorno/README.md`), incluida la exportación de
      **`SUITE_CMD_REINICIO_SUT`** — comando provisto por el evaluador que mata el
      proceso del SUT, preserva su persistencia y lo relevanta. Es **precondición dura**:
      21 ATs de persistencia (INV-8) dependen de él y sin él la corrida viola la regla
      `skip = 0` de una evaluación H8 válida
      ([ADR-011](../decisiones/ADR-011-particion-automatizable-white-box.md)).
   2. Correr **una sola vez** la suite black-box (465 ATs con test) →
      `runs/<id>/resultados-at.csv`, que lleva una fila por cada uno de los 521 ATs
      backend: los 465 con su resultado y los 56 como `no_automatizado`.
   3. Correr el **agente evaluador white-box** sobre los 56 ATs no automatizables
      ([ADR-007](../decisiones/ADR-007-agente-evaluador-white-box.md); modelos y runtime
      re-pinneados por ADR-010 Decisión 3): dos pasadas independientes, cada una validada
      mecánicamente con `agente-evaluador/validar-resultados.py` **antes** del arbitraje.
      El humano arbitra las discrepancias con la evidencia de ambas y firma
      `veredicto-final.yaml`, que se valida con el mismo script (`--final`).
   4. Completar las **rúbricas manuales** sobre copias por corrida y exportarlas a CSV
      (§10, incluida la regla de orden dentro de una celda).
   5. Medir las **métricas estáticas** (`metricas-estaticas/medir.sh`) sobre el repo
      satélite congelado.
   6. Volcar el resumen a `runs/<id>/metricas.md` y escribir la entrada de journal de la
      corrida.

## 4. Orden de construcción y avance de etapa

- **Orden fijo:** `backend` (épicas 01–09) → `cliente web` (épica 10) → `cliente
  mobile` (épica 11). El mismo en las 5 corridas. El orquestador no auto-avanza de
  etapa: el avance lo gatea el evaluador humano (ADR-009 Decisión 4).

### 4.1 Criterio de avance (smoke check)

Se pasa a la etapa siguiente cuando el agente declara la etapa completa **y** el
artefacto arranca:

| Etapa | Smoke check |
|-------|-------------|
| `backend` | el proceso levanta contra el entorno on-chain y responde el **endpoint de health-check que el propio agente eligió, expuso y documentó** en el README del repo satélite |
| `web` | el cliente web compila y renderiza el login |
| `mobile` | la app mobile compila y corre en Expo |

**El health-check no viene de la spec.** La spec no define ningún endpoint de
health-check; es el prompt de etapa del backend el que le pide al agente exponer uno
simple (p. ej. `GET /health`), elegir su ruta y documentarla
(`pipeline/comun/prompts/etapa-1-backend.md`; `smoke_check` de
`pipeline/comun/etapas.yaml`). El criterio es idéntico en las 4 celdas porque el prompt
lo es. Si el agente no documentó ninguna ruta, el smoke check **no se puede ejecutar** y
la etapa no cumple el criterio de avance: es un **D1** (§5.2) y la intervención mínima es
señalar que falta lo que el prompt de etapa pide.

### 4.2 Procedimiento del smoke de backend

1. Levantar el entorno on-chain de evaluación: `docker compose up -d --wait` y
   `desplegar-usdc.py` (`suite-at/entorno/`).
2. Configurar el SUT con el **contrato de arranque** de `suite-at/entorno/README.md`:
   URL del nodo RPC, dirección del USDC-mock y bloque de inicio del indexador.
3. Arrancarlo y pedir el health-check documentado.

El entorno es necesario para que el arranque sea concluyente: la épica 07 exige que el
servicio de indexación verifique `eth_chainId() == 11155111` **al iniciar y antes de
procesar cualquier bloque**, y que termine con error si no coincide
(`spec/07-depositos-on-chain/README.md`, "Verificación del `chainId` del nodo"). Un
backend levantado sin nodo no ejercita ese camino. El entorno usado para el smoke es
**descartable**: la evaluación de H8 parte de una cadena limpia (`docker compose down &&
up` + redespliegue del mock, `suite-at/README.md` §4).

Este procedimiento **no viola la regla de no-exposición**: no interviene la suite de ATs
ni se le reporta al agente ningún resultado de evaluación; sólo se comprueba que el
proceso levanta.

### 4.3 No-exposición del holdout y etapas incompletas

- **Regla de no-exposición del holdout:** durante la corrida, el evaluador **no** ejecuta
  la suite de tests de aceptación ni adelanta al agente resultados de evaluación. La
  suite corre una sola vez por corrida, al cierre (H8). Motivo: usar el holdout como
  feedback durante la generación lo convierte en set de entrenamiento y sesga la métrica
  principal.
- Una etapa cerrada como **incompleta** (por presupuesto o estancamiento, sección 5.7) no
  bloquea las siguientes: se continúa con lo que exista, registrando el estado en el
  manifest (`notas`) y en el journal. Los ATs de lo faltante simplemente fallarán en H8.

## 5. Política de intervención humana

### 5.1 Definición

**Intervención** es toda acción del evaluador que altera el curso del pipeline más allá
de la operación mecánica del harness. Son intervenciones:

- (a) un prompt correctivo o aclaratorio al agente;
- (b) responder una pregunta que el agente formula;
- (c) editar manualmente código, configuración o archivos generados;
- (d) reiniciar/reintentar una etapa o sub-tarea, incluida la **continuación de una etapa
  interrumpida** (§5.8);
- (e) cualquier decisión de configuración tomada a mitad de corrida.

**No** son intervenciones (no se registran como INT, aunque sí en notas si son
llamativas): aprobar prompts de permiso del harness sin modificar nada, esperar a que
termine una tarea, avanzar a la etapa siguiente cuando se cumplió el criterio de la
sección 4.

### 5.2 Disparadores — cuándo SÍ se interviene

Sólo ante un **bloqueo objetivo**, definido como cualquiera de:

- **D1.** El agente declara terminada una tarea/etapa pero el artefacto no compila, no
  arranca o falla el smoke check de la sección 4.
- **D2.** El agente queda detenido: espera input, entra en bucle (≥ 2 iteraciones
  consecutivas sin diff nuevo sobre el repo), o la invocación del CLI **termina antes de
  que el paso de la secuencia se complete** (error del harness, corte por rate limit,
  caída del proceso).
- **D3.** El agente se desvía del alcance de forma que impide continuar: ignora una
  épica completa, inventa alcance no pedido que reemplaza al pedido, o modifica la spec
  (la spec es inmutable: cualquier edición del agente sobre `spec/` se revierte y se
  registra).
- **D4.** El agente solicita explícitamente una decisión o aclaración.

### 5.3 Cuándo NO se interviene

- **Calidad subóptima que no bloquea** (código feo, duplicado, sin tests propios,
  decisiones de diseño discutibles): no se toca; lo capturan las métricas de H8.
- **Errores funcionales no bloqueantes** (un endpoint que devuelve un campo mal, un
  cálculo incorrecto): no se corrigen aunque el evaluador los note; los captura el
  holdout. Intervenir acá sería optimizar la celda a mano.
- **Anticipación:** no se interviene "porque se ve venir" un problema; sólo ante D1–D4
  consumados.

### 5.4 Contenido permitido de una intervención

Para no contaminar la comparación ni el holdout:

- La intervención **mínima suficiente** para desbloquear, en este orden de preferencia:
  (a) señalar el error observable (mensaje de compilación, stack trace); (b) señalar la
  sección/HU/RN de la spec pertinente; (c) instrucción correctiva concreta; (d) edición
  manual (último recurso; se registra el diff).
- **Prohibido:** citar o parafrasear escenarios de aceptación como "tests que van a
  correrse", revelar resultados de evaluación, aportar conocimiento de dominio que la
  celda no tiene (en particular, explicar contenido de BIPs/EIPs a una celda sin RAG:
  si el agente no lo sabe y la spec no lo fija, ese fallo **es un dato**, no un
  problema a resolver).
- Si el bloqueo proviene de una **ambigüedad o defecto real de la spec**, aplica la
  sección 8 (no se resuelve ad hoc para una sola celda).

### 5.5 Registro

Cada intervención se registra **en el momento** en `runs/<id>/intervenciones.md` según
`runs/plantillas/intervenciones.template.md`: timestamp, etapa/componente, categoría de
causa raíz, disparador (D1–D4), descripción, prompt textual usado, respuesta del agente,
referencias (AT/HU/INV/commit).

### 5.6 Clasificación por causa raíz (cascada determinista)

Las 8 categorías provienen del marco metodológico de la propuesta. Cada intervención
recibe **exactamente una** categoría, la **primera que aplique** recorriendo esta
cascada (de la más específica de dominio a la más genérica):

| Orden | Cat. | Se asigna si el defecto raíz…                                                                 |
|-------|------|------------------------------------------------------------------------------------------------|
| 1º    | 8    | involucra estándares on-chain: BIP-32/39/44, EIP-155, EIP-55, ERC-20 mal aplicados, inventados o desactualizados |
| 2º    | 7    | involucra lógica financiera o invariantes del matching: unidades, redondeo, fees, INV-1..8, prioridad precio-tiempo |
| 3º    | 6    | es de UI/UX: render, navegación, formularios, estados visuales (épicas 10–11)                    |
| 4º    | 5    | es un fallo de **integración entre componentes** (backend↔web↔mobile, contrato API mal consumido) |
| 5º    | 3    | es **pérdida de contexto**: el agente olvida/contradice decisiones o artefactos propios de etapas previas |
| 6º    | 4    | es una **alucinación general** (API/librería/archivo inexistente) no cubierta por 8              |
| 7º    | 2    | es código que **no compila o no funciona** sin causa más específica identificable                |
| 8º    | 1    | es una **mala interpretación de la especificación** (la spec fija X sin ambigüedad; el agente hizo Y) |

Regla de desempate adicional: se clasifica por la **causa raíz** diagnosticada, no por el
síntoma (un build roto porque el agente usó una librería inexistente es 4, no 2; un
cálculo de fee con floats es 7 aunque compile).

### 5.7 Estancamiento y abandono de etapa

- **Estancamiento:** 3 intervenciones consecutivas con la misma causa raíz sobre el
  mismo defecto sin progreso observable ⇒ se abandona ese defecto (se deja como está) y
  se registra en el log. No se insiste: el costo de insistir distorsiona la métrica de
  intervenciones.
- **Abandono de etapa:** si la etapa no alcanza el criterio de avance tras agotar el
  presupuesto proporcional (sección 6) o acumula 3 estancamientos, se cierra como
  incompleta y se continúa (sección 4).

### 5.8 Continuación de una etapa interrumpida

Si una invocación del CLI termina antes de que el paso de la secuencia se complete, la
etapa se continúa **re-invocando al orquestador sobre el estado actual del repo
satélite**, con una **sesión fresca** del CLI (sin `resume` ni reanudación de sesión) y
los mismos prompts de sistema, de etapa y de rol del paso interrumpido. Se clasifica como
disparador **D2** e intervención de tipo **(d)**, y se registra como cualquier otra
(§5.5), anotando en qué paso de la secuencia ocurrió el corte.

- **Por qué sesión fresca:** reanudar la sesión introduciría entre celdas una diferencia
  de contexto acumulado que ningún mecanismo iguala entre los dos CLI. El handoff del
  pipeline ya es el estado del repo satélite más los archivos bajo `.pipeline/`
  (ADR-009 Decisión 4), que sobreviven al corte.
- **Causa esperable del corte: el rate limit** de la suscripción (§6). Los cortes por
  tope de turnos que preveía el diseño anterior (`error_max_turns` en A,
  `MaxTurnsExceeded` en B) **dejaron de existir**: ningún CLI expone un tope de turnos y
  el experimento corre sin presupuesto de turnos (ADR-009 §Consecuencias).
- **PENDIENTE-PILOTO:** el comportamiento efectivo de cada CLI ante un rate limit a mitad
  de etapa —si pausa y retoma, o si corta— **no está verificado** (checklist H6, ítem 19).
  La regla aplica igual en ambos casos: si el CLI pausa y retoma solo, no hubo corte y no
  hay intervención que registrar.
- Estas continuaciones cuentan para el estancamiento y el abandono de etapa (§5.7) como
  cualquier otra intervención.

## 6. Presupuestos por corrida

Valores **provisionales** (ver el pendiente al pie): la corrida piloto los valida y los
definitivos quedan pinneados en el ADR de reemplazo (si cambian) y en el manifest de
cada corrida oficial.

| Concepto            | Tope por corrida | Nota                                                        |
|---------------------|------------------|-------------------------------------------------------------|
| `costo_max_usd`     | 200 USD          | Tope operativo bajo API key; bajo suscripción **no** es vinculante (ver salvedad). |
| `tiempo_max_horas`  | 24 h activas     | ~3 jornadas de sesión del evaluador, excluye esperas largas. |
| `tokens_max`        | — (sin tope)     | Se registra como métrica.                                    |

- **No hay tope de turnos.** Ningún CLI expone uno y el orquestador no lo repone; el
  tesista decidió el 2026-08-16 correr sin presupuesto de turnos (ADR-009
  §Consecuencias). Se cae el tope, **no la métrica**: turnos y tokens se siguen
  registrando por invocación en el JSONL de la corrida (ADR-003).
- **Salvedad bajo suscripción.** ADR-009 hace correr los harnesses sobre las
  suscripciones del tesista. En ese modo `costo_max_usd` deja de ser el tope operativo
  vinculante y pasan a serlo los **rate limits** de cada proveedor, que son asimétricos,
  no están bajo control del experimento y presionan la ventana de ≤ 2 semanas de §7. El
  costo se sigue registrando como métrica —nativo en A (`total_cost_usd`), estimado
  localmente desde tokens en B (ADR-009 Decisión 1)—, no como tope.
- Presupuesto proporcional orientativo por etapa: backend 60 % / web 25 % / mobile 15 %
  (los mismos valores que `presupuesto_proporcional` de `pipeline/comun/etapas.yaml`).
- Al agotarse un tope, la corrida se cierra en el estado en que esté (sección 4) y se
  registra el motivo del cierre en el manifest.

**PENDIENTE-PILOTO — presupuestos definitivos.** Esta versión **no** pinnea los valores
definitivos: dependen del consumo real que mida la piloto y de la decisión
**suscripción contra API key** para las 4 corridas oficiales, que se toma con ese dato
(ADR-004 punto 4; checklist H6, ítem 7; ADR-009 §Consecuencias). Se fijan antes de la
primera corrida oficial, en el manifest de cada corrida y —si difieren de la tabla— en
una versión posterior de este documento con su ADR de reemplazo. Escribir hoy un número
sería inventarlo.

## 7. Orden y ventana de las corridas oficiales

- El **orden de ejecución** de las 4 celdas se sortea **una vez**, antes de la primera
  corrida oficial, y se registra en el journal (mitigación transparente del efecto
  aprendizaje del evaluador; con n=1 por celda no lo elimina — se discute como amenaza a
  la validez en el cap. 4).
- La ventana piloto (`piloto-01` + `piloto-02`), además de debuggear protocolo/harness,
  funciona como **entrenamiento del evaluador** para amortiguar ese efecto.
- Ventana objetivo: ≤ 2 semanas entre la primera y la última corrida oficial. Los rate
  limits de las suscripciones (§6) presionan esta ventana y pueden forzar a excederla;
  si ocurre, se registra en el journal y se discute como amenaza a la validez, no se
  ajusta el protocolo retroactivamente.

## 8. Ambigüedades o defectos de la spec descubiertos mid-run

Si durante una corrida se descubre un defecto de la spec que **bloquea** (una HU
imposible de implementar como está escrita, una contradicción real):

1. Se registra la intervención (categoría según cascada; típicamente 1 con nota de
   "defecto de spec").
2. La decisión que desbloquea se documenta en el journal **y se aplica idéntica a las
   4 celdas** (a las ya corridas sólo si el defecto invalida su medición — peor caso que
   se evita con la piloto).
3. La spec taggeada **no se edita** durante la ventana de corridas; las correcciones se
   acumulan para un eventual `spec-v1.2` posterior al experimento. La reapertura
   controlada que produjo `spec-v1.1` (ADR-006) ocurrió **antes** de la piloto y con la
   spec todavía no vista por ningún agente; esa condición ya no se repite.

## 9. Aislamiento y no-contaminación

- Los agentes de las corridas **sólo ven el repo satélite** (la spec). Nunca ven
  `journal/`, `runs/`, `analisis/`, `evaluacion/`, ni los repos de otras celdas
  (ADR-001). Del lado de la máquina del tesista, cada CLI se invoca aislado de la config
  del host (ADR-009 Decisión 5).
- El evaluador no reutiliza prompts correctivos entre celdas salvo que el disparador sea
  idéntico; cuando lo sea, usa la misma redacción (paridad también en las
  intervenciones). El log de intervenciones de cada celda documenta el texto exacto.
- La suite de ATs (H5) se construye **antes** de la primera corrida y no se modifica
  después de vista ninguna implementación. La frontera automatizable/white-box
  (**465 automatizados / 56 white-box** sobre los 521 ATs backend) quedó cerrada por
  ADR-011 dentro de la ventana H6, por ese mismo criterio.
- Los **instrumentos manuales** están pre-registrados y no se editan (los veredictos se
  vuelcan siempre en una copia por corrida): `rubricas/epica-10-web.md` y
  `rubricas/epica-11-mobile.md` en **H5**; `rubricas/rol-revisor.md` en **H6**, por ser
  consecuencia del set de roles de ADR-009 Decisión 4. `rol-revisor.md` lleva una
  cláusula de re-pre-registro acotada a la piloto: si ahí cambia el set de roles o el
  prompt del rol, la rúbrica se corrige y se vuelve a pre-registrar **antes** de H7.
- Los criterios de las **métricas estáticas** también están pre-registrados, incluido su
  alcance (§10.3).

## 10. Qué se registra, dónde

| Qué                                    | Dónde                              | Cuándo                    |
|----------------------------------------|-------------------------------------|---------------------------|
| Configuración de la celda, insumos pinneados (spec, corpus, model IDs, `effort`, versión de cada CLI, `model_context_window` en B), presupuestos | `runs/<id>/manifest.yaml` §1–4 | Antes de iniciar          |
| Eventos de cada invocación del CLI: turnos, tokens, costo, consultas al RAG, actividad de subagentes | JSONL del orquestador (`<repo-satélite>/../logs/<celda>-<etapa>-<timestamp>.jsonl` y su `-rag.jsonl`), copiado a `runs/<id>/` al cerrar — las trazas del agente son insumo del conteo de alucinaciones (`alucinaciones.md` §1) | Durante la corrida        |
| Intervenciones (INT-NN)                | `runs/<id>/intervenciones.md`       | En el momento             |
| Cierre (timestamps, costo, tokens)     | `runs/<id>/manifest.yaml` §5        | Al cerrar la corrida      |
| Suite black-box (465 ATs)              | `runs/<id>/resultados-at.csv`       | En H8                     |
| Agente evaluador white-box (56 ATs)    | `runs/<id>/no-automatizables/pasada-1.yaml`, `pasada-2.yaml`, `veredicto-final.yaml` | En H8 |
| Rúbricas de épicas 10–11 completadas   | `runs/<id>/rubricas/` + `runs/<id>/resultados-rubricas.csv` | En H8    |
| Rúbrica del rol `revisor` completada   | `runs/<id>/rubricas/rol-revisor.md` + `runs/<id>/resultados-rubrica-revisor.csv` + `runs/<id>/censo-revision.csv` | En H8 |
| Métricas estáticas                     | `runs/<id>/metricas-estaticas.csv`  | En H8                     |
| Alucinaciones de dominio               | `runs/<id>/alucinaciones.md`        | En H8                     |
| Resumen de métricas de evaluación      | `runs/<id>/metricas.md`             | En H8                     |
| Narrativa y observaciones              | `journal/AAAA-MM-DD-<id>.md`        | Al cierre de cada sesión  |
| Decisiones estructurales sobrevenidas  | ADR nuevo                           | Cuando ocurran            |

### 10.1 Formato CSV de las rúbricas manuales

Las copias completadas de cada rúbrica son la **fuente primaria** (auditable); los CSV
son el formato máquina-legible que consume la consolidación de `analisis/dataset/`. Los
valores admitidos de cada campo son los del instrumento correspondiente; el esquema
normativo vive en `rubricas/README.md`.

| CSV | Filas | Columnas |
|-----|-------|----------|
| `resultados-rubricas.csv` | una por AT en el orden del documento: 78 + `AT-10-E2E-01` de web y 94 de mobile (173) | `at_id`, `resultado`, `detalle`, `fuera_de_catalogo` |
| `resultados-rubrica-revisor.csv` | una por (etapa, criterio): 3 etapas × 12 criterios = 36 | `etapa`, `criterio`, `resultado`, `detalle` |
| `censo-revision.csv` | una por punto de cada artefacto de revisión (cantidad dependiente de la corrida) | `etapa`, `punto`, `eje`, `severidad`, `ancla`, `referencias`, `ubicacion`, `accionable`, `veracidad`, `destino`, `evidencia` |

`resultado` usa el vocabulario `PASA` / `FALLA` / `NO_EVALUABLE` en los tres
instrumentos, y `detalle` es obligatorio en `FALLA` y `NO_EVALUABLE`. Los nombres de
columna se alinean con los de `resultados-at.csv` de la suite black-box para que la
consolidación sea mecánica.

### 10.2 Orden de completado dentro de una celda (H8)

El censo y los veredictos de `rol-revisor.md` de una celda se completan **antes** de que
el evaluador abra `runs/<id>/resultados-at.csv` de esa misma celda. Correr la suite es
mecánico; leerla no: conocer qué ATs fallaron antes de codear la revisión contaminaría el
codeo. El cruce entre el campo `referencias` del censo y `resultados-at.csv` se hace
después, ya con el censo cerrado.

### 10.3 Alcance de las métricas estáticas: exclusión de `.pipeline/`

Las métricas estáticas **excluyen `.pipeline/` del cómputo**. Ese directorio contiene los
artefactos de handoff entre roles del orquestador (p. ej. `revision-<etapa>.md`, ADR-009
Decisión 4), que son mecánica del pipeline y no producto generado; contarlos mediría el
pipeline y además introduciría un sesgo por celda, porque el volumen de handoff depende
de cuánto escriba el rol `revisor` de cada familia.

La exclusión es **por directorio** —alcanza a cualquier archivo bajo `.pipeline/`, sea
markdown, código o manifiesto— y rige idéntica en las 4 celdas, para cloc, lizard, jscpd
y el conteo de dependencias directas. La regla se fija **antes** de la piloto y de ver
implementación alguna, por el mismo criterio de congelamiento que §9 aplica a la suite de
ATs y a las rúbricas (ADR-009 §Consecuencias). Está implementada y verificada en
`metricas-estaticas/medir.sh`; los criterios completos, en el README §1.1 de esa carpeta.

`rubricas/rol-revisor.md` es el **único** instrumento que mide `.pipeline/`, con lo cual
no hay doble conteo entre las métricas estáticas y esa rúbrica.
