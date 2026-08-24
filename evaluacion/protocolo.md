# Protocolo experimental pre-registrado — v1.5

- **Estado:** esta versión reemplaza a la **v1.1**, congelada por
  [ADR-012](../decisiones/ADR-012-protocolo-experimental-v1-1.md) (2026-08-17), que a su
  vez había reemplazado a la v1.0 de
  [ADR-004](../decisiones/ADR-004-protocolo-experimental-preregistrado.md) (2026-07-05).
  La congela [ADR-016](../decisiones/ADR-016-sin-topes-de-presupuesto.md), **Aceptado**
  el 2026-08-23: rige desde esa fecha y antes de la primera corrida oficial. Ni ADR-004
  ni ADR-012 se editan. **Único cambio de v1.1 → v1.2:** §6 pierde los topes de
  presupuesto y §5.7 pierde la rama de abandono por agotamiento; todo lo demás se
  conserva verbatim.
- **Ventana de ajuste:** la única prevista por ADR-004 punto 2 — los defectos que revele
  la **corrida piloto** (H6). Si la piloto revela defectos adicionales, se produce una
  v1.3 más un ADR que reemplace a ADR-016, **antes** de la primera corrida oficial.
  Durante las corridas oficiales (H7) el protocolo es **inmutable**.
- **Propósito:** fijar, antes de cualquier corrida, las reglas que hacen comparables a
  las 4 celdas del factorial 2×2: cuándo interviene el humano y cómo se clasifica cada
  intervención, en qué orden se construye, qué se mide y qué se registra.
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
6. **Este protocolo:** criterios de intervención, medición y registro.
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
| `web` | el **build de producción** que el README del SUT documente termina con **exit 0** |
| `mobile` | **`npx expo export --platform android`** termina con **exit 0** |

**El health-check no viene de la spec.** La spec no define ningún endpoint de
health-check; es el prompt de etapa del backend el que le pide al agente exponer uno
simple (p. ej. `GET /health`), elegir su ruta y documentarla
(`pipeline/comun/prompts/etapa-1-backend.md`; `smoke_check` de
`pipeline/comun/etapas.yaml`). El criterio es idéntico en las 4 celdas porque el prompt
lo es. Si el agente no documentó ninguna ruta, el smoke check **no se puede ejecutar** y
la etapa no cumple el criterio de avance: es un **D1** (§5.2) y la intervención mínima es
señalar que falta lo que el prompt de etapa pide.

Los criterios de `web` y `mobile` los fija
[ADR-020](../decisiones/ADR-020-nodo-onchain-y-smoke-ejecutable.md), que reemplaza los
enunciados de v1.2 («compila y renderiza login», «compila y corre en Expo»): no eran
ejecutables —no hay emulador ni en el contenedor del agente ni en el host— y por lo tanto
no podían aplicarse igual en las 4 celdas. `expo export` compila el bundle de verdad y
falla si el código no compila. Lo que se verifica sigue siendo que el artefacto exista y
compile; si además *funciona* lo dicen las rúbricas en H8.

Durante la generación, el agente alcanza el nodo on-chain del host por
`http://host.docker.internal:8545` (ADR-020 Decisión 1 y 2): la red del contenedor es
propia y `127.0.0.1` no llega. El prompt de etapa de backend se lo informa, aclarando que
la URL sigue siendo configuración.

**Dónde se ejecuta cada smoke:** dentro del **contenedor de la corrida**, con la misma
imagen que generó el artefacto y el repo satélite montado
([ADR-021](../decisiones/ADR-021-smoke-y-evaluacion-dentro-del-contenedor.md)). El agente
construye en linux/arm64 y `node_modules` queda poblado con binarios de esa plataforma:
en la pre-piloto, el build del cliente web de B **falla en el host**
(`@rollup/rollup-linux-arm64-gnu` no encontrado) y **pasa en el contenedor** en 508 ms.
Lo mismo vale para el SUT de H8, que corre en contenedor con su puerto publicado mientras
la suite y el agente evaluador siguen corriendo en el host.

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
- Una etapa cerrada como **incompleta** (por estancamiento, sección 5.7) no
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
- **Abandono de etapa:** si la etapa no alcanza el criterio de avance tras acumular
  3 estancamientos, se cierra como incompleta y se continúa (sección 4). La rama por
  agotamiento de presupuesto que traía la v1.1 **se elimina**: no hay topes (ADR-016,
  sección 6). El abandono mide falta de progreso, no consumo.

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

## 6. Consumo: se mide, no se topea

**No hay topes de presupuesto.** Una corrida se cierra cuando las tres etapas completan
su secuencia, o por los criterios de progreso de §5.7 — que miden falta de progreso, no
consumo. Lo fija [ADR-016](../decisiones/ADR-016-sin-topes-de-presupuesto.md), que
elimina la tabla de topes de la v1.1 (`costo_max_usd` 200 USD, `tiempo_max_horas` 24 h) y
la regla de cierre por agotamiento.

Motivo: de los tres topes de la v1.1, uno ya no aplicaba —bajo suscripción
`costo_max_usd` no es vinculante y el tope real son los rate limits, asimétricos y fuera
del control del experimento (ADR-009 §Consecuencias)—, otro nunca tuvo valor
(`tokens_max`) y el tercero era un número sin fundamento empírico. Y un tope de costo
habría **censurado la variable que el experimento compara**: si una celda gasta el doble
que otra, ese es el resultado.

Lo que se registra por invocación y por etapa, en el JSONL de la corrida (ADR-003):

| Métrica | Fuente |
|---------|--------|
| Costo en USD | Nativo en A (`total_cost_usd`, `modelUsage`); estimado localmente desde tokens en B (ADR-009 Decisión 1) |
| Tokens | `input` / `cached` / `cache_write` / `output` / `reasoning` |
| Turnos | Por invocación de rol |
| Tiempo de reloj | Por invocación y por etapa |

- **No hay tope de turnos.** Ningún CLI expone uno y el orquestador no lo repone (ADR-009
  §Consecuencias). Se cae el tope, **no la métrica**.
- **`presupuesto_proporcional` no es presupuesto.** El reparto backend 60 % / web 25 % /
  mobile 15 % de `pipeline/comun/etapas.yaml` queda como **referencia descriptiva** para
  el análisis —qué fracción del esfuerzo total se fue en cada etapa, comparable entre
  celdas—, no como umbral operativo: ya no gatea el abandono de etapa.
- **Suscripción contra API key** para las 4 corridas oficiales sigue abierta y ya no
  bloquea: se decide con el consumo que mida la piloto y se registra en el journal
  (checklist H6, ítem 7).
- **Riesgo asumido:** una celda puede consumir un múltiplo de lo previsto sin que nada la
  detenga. Se acepta explícitamente; cortar destruiría la comparabilidad de la celda
  cortada, que para el experimento es peor que el costo.

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
  (ADR-001). Desde [ADR-015](../decisiones/ADR-015-agentes-en-contenedores.md) esto lo
  sostiene el **mecanismo** y no el procedimiento: toda invocación de rol ocurre dentro
  de un contenedor que monta el repo satélite y nada más del árbol de la tesina, en las
  dos familias. Además, cada CLI se invoca aislado de la config del host (ADR-009
  Decisión 5), y la recuperación web queda desactivada por mecanismo explícito en ambas
  familias ([ADR-014](../decisiones/ADR-014-recuperacion-web-en-el-harness-b.md)) —
  con la salvedad, declarada en los dos ADRs, de que eso restringe herramientas y no red:
  el contenedor sale a internet sin restricción, por igual en A y B.
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
| Configuración de la celda, insumos pinneados (spec, corpus, model IDs, `effort`, versión de cada CLI, `model_context_window` en B), imágenes de contenedor por digest | `runs/<id>/manifest.yaml` §1–4 | Antes de iniciar          |
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
