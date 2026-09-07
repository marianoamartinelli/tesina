celda: celda-en-evaluacion
pasada: 2
fecha: 2026-09-07

# Rúbrica manual — Rol `revisor` del pipeline — v1.1

- **Objeto evaluado:** los archivos `.pipeline/revision-<etapa>.md` que produce el rol
  `revisor` ([ADR-009](../../decisiones/ADR-009-harnesses-como-cli-y-orquestador-de-roles.md)
  Decisión 4; prompt congelado en `pipeline/comun/prompts/roles/revisor.md`), tal como
  quedaron al cierre de la corrida. **Tres artefactos por celda**, uno por etapa
  (`revision-backend.md`, `revision-web.md`, `revision-mobile.md`), según la secuencia
  `implementador` → `revisor` → pase correctivo de `pipeline/comun/etapas.yaml`.
- **Cobertura:** 12 criterios (`RV-01`..`RV-12`) por artefacto — 36 veredictos por celda —
  más un **censo de puntos** (una fila por punto de cada revisión).
- **Estado:** pre-registrada en H6, **antes de ver implementación alguna**. Es el motivo
  del instrumento: una rúbrica ajustada después de leer las revisiones que va a medir
  mide el ajuste, no las revisiones (protocolo §9, que fija el mismo criterio de
  congelamiento para la suite de ATs y las rúbricas de las épicas 10–11).
- **Alcance:** idéntica en las **4 celdas oficiales** y en piloto-01. Si piloto-02 (smoke
  acotado del harness B) produce artefactos de revisión, se codean igual y se reportan
  como descartables, fuera del dataset.
- **Qué mide y qué no:** mide el **artefacto de revisión** — cumplimiento del mandato del
  rol, anclaje de cada punto en la spec, veracidad de lo que afirma y destino en el pase
  correctivo. No mide la implementación (eso lo hacen la suite black-box, el agente
  evaluador white-box y las rúbricas de las épicas 10–11) ni el tamaño del artefacto como
  proxy de calidad (ver "Limitaciones declaradas").
- **Relación con las métricas estáticas:** `.pipeline/` está excluido del cómputo de
  `evaluacion/metricas-estaticas/` (checklist H6, ítem 18). Esta rúbrica es el **único**
  instrumento que mide ese directorio; no hay doble conteo.

## Precondiciones

1. **Artefactos de revisión de la celda**, intactos. El evaluador no los edita ni los
   reformatea: se leen desde la copia de evaluación del repo satélite.
2. **Estado del repo satélite recuperable al cierre de cada invocación de rol** (commit,
   tag o copia que deja el orquestador). Es la evidencia primaria de `veracidad` y de
   `RV-02`/`RV-03`, y es **neutral entre familias**.
   **PENDIENTE-ARRANQUE:** que el orquestador reescrito (checklist H6, ítem 17) lo deje
   así no está verificado al momento de pre-registrar esta rúbrica. Si no queda
   recuperable, esos criterios caen a `NO_EVALUABLE` causa (b) y el eje `veracidad` se
   reporta como no medido, no se estima.
3. **JSONL de cada invocación del rol `revisor`** (registro del orquestador, ADR-003):
   evidencia **secundaria** para `RV-02`/`RV-03`/`RV-04` cuando el diff no alcanza para
   distinguir qué se escribió y cuántas veces. **NO VERIFICADO:** que la granularidad del
   JSONL de `codex exec --json` permita esa lectura del lado B (checklist H6, ítems 2
   y 19); por eso el diff es la evidencia primaria y el JSONL no puede ser la única.
4. **`spec-v1.1`**, para comprobar que las referencias que cada punto cita existen y dicen
   lo que el punto afirma.
5. **Copia descartable del repo satélite** en el estado del cierre de la revisión, para
   ejecutar lo que haga falta al verificar `veracidad`. El repo evaluado no se modifica.
6. **Herramientas permitidas** (y ninguna otra): lectura del repo satélite y de su
   historia, `diff`/`grep`, ejecución de builds, arranque y tests **del propio repo
   satélite**, y lectura de los JSONL de la corrida.
7. Los `resultados-at.csv` de la celda **no se miran** hasta terminar el censo de esa
   celda (abajo, Procedimiento general). La suite black-box no se corre para esta rúbrica.

## Procedimiento general

- Se completa **en H8**, por el **agente evaluador tercero** (ADR-026; v1.1 — hasta v1.0,
  el tesista), en **dos pasadas independientes más un arbitraje por agente**, recorriendo
  las celdas en el **orden sorteado** (protocolo §7; checklist H6, ítem 15) y, dentro de cada celda,
  las etapas en el orden `backend` → `web` → `mobile` y los puntos en el orden en que
  aparecen en el documento.
- **Orden obligatorio dentro de una celda:** primero el censo (Parte A) y los veredictos
  (Parte B), **después** se abre `resultados-at.csv` de esa celda. El cruce entre el campo
  `referencias` del censo y los resultados de la suite es mecánico y posterior; saber de
  antemano qué ATs fallaron contaminaría el codeo.
- **Todo campo del censo y todo veredicto exige evidencia citada** — cita textual del
  punto (o su rango de líneas en el artefacto) y, cuando el campo lo requiera, archivo +
  línea inspeccionados o comando ejecutado + salida relevante. **Un campo sin evidencia es
  inválido** y se trata como no emitido (mismo criterio evidence-gated que
  [ADR-007](../../decisiones/ADR-007-agente-evaluador-white-box.md) §2).
- **Tiempo máximo de verificación por punto:** 10 minutos (el mismo tope por fila que las
  rúbricas de las épicas 10–11); superado, `veracidad = NO_VERIFICABLE`.
- **Unidad de "punto":** cada elemento de la lista del artefacto que enuncia un problema
  distinto. Si un elemento agrupa varios problemas independientes, se cuenta **uno** y se
  codea por el de mayor severidad, dejándolo dicho en la evidencia. Prosa fuera de la
  lista no es un punto: cuenta para `RV-10`.

## Parte A — Censo de puntos

Una fila por punto de cada artefacto. Vocabulario cerrado; no se admiten valores fuera de
las listas.

| Campo | Valores admitidos | Cómo se determina |
|-------|-------------------|--------------------|
| `punto` | ordinal `1..n` | posición en el documento |
| `eje` | `COMPLETITUD` \| `CORRECCION` \| `INVARIANTES` \| `OPERABILIDAD` \| `OTRO` | los cuatro ejes que el prompt del rol manda cubrir; `OTRO` es todo lo que no cae en ninguno |
| `severidad` | `BLOQUEANTE` \| `MAYOR` \| `MENOR` | `BLOQUEANTE`: falta una HU completa del alcance de la etapa, el artefacto de la etapa no compila/no arranca, o se incumple una `INV-*`. `MAYOR`: incumple un `AT-*` o una `RN-*` concreta sin impedir el arranque. `MENOR`: todo lo demás |
| `ancla` | `SPEC` \| `EJECUCION` \| `NINGUNA` | `SPEC`: cita una `RN-*`, un `AT-*`, una `INV-*`, una HU o un archivo de `spec/`. `EJECUCION`: afirma haber ejecutado algo y reporta el resultado observado. `NINGUNA`: ni una ni otra. **Precedencia:** un punto que cita un id y además reporta ejecución se codea `SPEC` |
| `referencias` | ids citados, separados por `;`; vacío si el punto no cita ninguno | verbatim del punto, p. ej. `AT-03-02-01; INV-4`. Se completa **independientemente de `ancla`**: un punto codeado `EJECUCION` que igual nombra un `AT-*` lo lleva acá, para no perderlo en el cruce con `resultados-at.csv` |
| `ubicacion` | `ARCHIVO_LINEA` \| `ARCHIVO` \| `NINGUNA` | qué señala el punto sobre el repo satélite |
| `accionable` | `SI` \| `NO` | `SI` si enuncia algo a cambiar; `NO` si sólo constata que algo está bien o es una observación sin acción |
| `veracidad` | `VERDADERO` \| `FALSO` \| `NO_VERIFICABLE` | contra el estado del repo satélite **al cierre de la invocación del revisor**. `FALSO` incluye el falso positivo (lo señalado ya cumplía la spec) y la referencia inexistente o que no dice lo que el punto afirma. `NO_VERIFICABLE`: estado no recuperable, o vencido el tope de 10 minutos |
| `destino` | `RESUELTO` \| `NO_RESUELTO` \| `RECHAZADO_CON_CONSTANCIA` \| `NO_VERIFICABLE` | contra el estado al cierre del pase correctivo. `RECHAZADO_CON_CONSTANCIA`: el implementador dejó dicho por qué no lo aplicó (punto 4 de su prompt) |
| `evidencia` | texto | cita del punto + archivo:línea o comando + salida que sostiene `veracidad` y `destino` |

## Parte B — Criterios por artefacto

Los doce criterios se resuelven **sobre el censo de ese artefacto** (`RV-05`..`RV-09`,
`RV-11`, `RV-12`) o sobre observación directa (`RV-01`..`RV-04`, `RV-10`). Cada uno tiene
**exactamente un** veredicto:

- **PASA** — la condición se cumple.
- **FALLA** — la condición no se cumple. La nota lleva el **conteo** de puntos
  infractores y sus ordinales (la proporción es la medida comparable; el veredicto es el
  registro).
- **NO_EVALUABLE** — por una de dos causas, indicada en la nota: **(a)** el artefacto no
  existe o la invocación del revisor no llegó a cerrar (en ese caso `RV-01` es `FALLA` y
  los once restantes `NO_EVALUABLE` (a), con una única nota global); **(b)** el registro
  necesario no está disponible (estado del repo no recuperable, JSONL sin la granularidad
  requerida).

| Criterio | Qué exige | Verificación y veredicto cerrado |
|----------|-----------|-----------------------------------|
| RV-01 | El artefacto existe en la ruta indicada y no está vacío | Existe `.pipeline/revision-<etapa>.md` con al menos un punto. **FALLA** si no existe, está vacío o quedó en otra ruta |
| RV-02 | La sesión no modificó nada fuera de su archivo de salida | Diff del repo satélite entre el cierre del paso `implementador` y el cierre del paso `revisor`; JSONL como evidencia secundaria. **FALLA** si hay cualquier creación o modificación fuera de `.pipeline/revision-<etapa>.md` |
| RV-03 | El archivo se escribió una sola vez, al final | Una única operación de escritura sobre el archivo en el JSONL de la invocación. **FALLA** con dos o más. **NO_EVALUABLE** (b) si el JSONL no distingue operaciones de escritura |
| RV-04 | La sesión ejecutó el sistema para comprobar sus afirmaciones | Al menos una invocación de shell que compile, arranque o corra tests del repo satélite. **FALLA** si no hay ninguna. **NO_EVALUABLE** (b) si el JSONL no registra invocaciones de shell |
| RV-05 | Todo punto está anclado | **FALLA** si algún punto tiene `ancla = NINGUNA` |
| RV-06 | Todo punto está localizado | **FALLA** si algún punto tiene `ubicacion = NINGUNA` |
| RV-07 | Los puntos están ordenados de mayor a menor severidad | Sin inversiones: ningún punto de severidad menor precede a uno de severidad mayor, con los tres buckets del censo. **FALLA** ante la primera inversión (la nota lleva el conteo total) |
| RV-08 | Todo punto cae dentro del mandato del rol | **FALLA** si algún punto tiene `eje = OTRO` |
| RV-09 | Todo punto es accionable | **FALLA** si algún punto tiene `accionable = NO` |
| RV-10 | El artefacto no trae relleno | **FALLA** si contiene resumen ejecutivo, conclusiones, o un bloque de código copiado verbatim de un archivo del repo satélite (se busca el bloque en el repo **en el estado al cierre de la invocación del revisor**, el mismo que usan `RV-02` y `veracidad`) |
| RV-11 | Lo que el artefacto afirma es cierto | **FALLA** si algún punto tiene `veracidad = FALSO`. **NO_EVALUABLE** (b) si todos los puntos quedaron `NO_VERIFICABLE` |
| RV-12 | El circuito cierra sobre el artefacto | **FALLA** si algún punto quedó `NO_RESUELTO`. **NO_EVALUABLE** (b) si el estado posterior al pase correctivo no es recuperable. Mide el **circuito** `revisor` + pase correctivo, no sólo al revisor |

### Resultados — etapa `backend`

| Criterio | Resultado | Notas |
|----------|-----------|-------|
| RV-01 | PASA | Existe `.pipeline/revision-backend.md` (paso2 y `sut/`) con tres puntos de lista (L1–L3); no vacío ni otra ruta. |
| RV-02 | PASA | `diff -rq` paso1→paso2: solo aparece `.pipeline/` con `revision-backend.md`. JSONL paso 2 (L174–251): un `file_change` add de esa ruta; `git status` = `?? .pipeline/`. |
| RV-03 | PASA | Una operación de escritura (R6): `item_35` add de `/repo/.pipeline/revision-backend.md` (started+completed del mismo id). CMD28 es lectura (`sed -n`). |
| RV-04 | PASA | R7: `npm run build`, `npm test` (vitest), `npm start`, `curl` a `/health` y `/api/v1/foo`, `node` + `buildApp` inject. JSONL registra las shells. |
| RV-05 | PASA | 0/3 con `ancla=NINGUNA` (todos SPEC). |
| RV-06 | PASA | 0/3 con `ubicacion=NINGUNA` (todos ARCHIVO_LINEA). |
| RV-07 | PASA | Sin inversiones (R2): MAYOR, MENOR, MENOR. |
| RV-08 | PASA | 0/3 con `eje=OTRO`. |
| RV-09 | PASA | 0/3 con `accionable=NO`. |
| RV-10 | PASA | R8: sin resumen ejecutivo/conclusiones ni bloques de código verbatim. |
| RV-11 | PASA | 0/3 `FALSO`; 0 `NO_VERIFICABLE`. |
| RV-12 | PASA | 0/3 `NO_RESUELTO`. paso3 aplica wallet (1), auditoría login (2) y `NOT_FOUND` details (3). |

#### Censo de puntos — `backend`

| punto | eje | severidad | ancla | referencias | ubicacion | accionable | veracidad | destino | evidencia |
|-------|-----|-----------|-------|-------------|-----------|------------|-----------|---------|-----------|
| 1 | CORRECCION | MAYOR | SPEC | HU-06-02; RN-8; AT-06-02-08 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | Artefacto L1. paso2 `src/crypto/wallet.ts:156-185` + `test/wallet.test.ts:89-100`: `InvalidDerivedKeyError` en cualquier componente se reintenta solo con `address_index`. Spec RN-8/AT-06-02-08 (BIP-32 avanza el `i` del paso). R4 lectura (bucle 2^31 si falla `44'`). Diff paso2→paso3: `deriveNextValidChild` por componente + tests por paso. R1: un punto. |
| 2 | COMPLETITUD | MENOR | SPEC | RNE-9; HU-01-02; RN-8; RN-9 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | Artefacto L2. paso2 `src/app.ts:111-119,188-198` y `auth-service.ts:75-123`: VALIDATION_ERROR y RATE_LIMITED-en-parseo no escriben `auth_audit`. RNE-9 pide auditar todo intento; RN-8/RN-9 no son RN de auditoría y AT-01-02-13 ya cubre éxito/INVALID_CREDENTIALS → MENOR (R2). R1: agrupa dos huecos. Diff: `onResponse`+`loginAuditOutcome` + `login-audit.test.ts`. |
| 3 | CORRECCION | MENOR | SPEC | 00-fundaciones/modelo-de-errores.md; HU-09-05; RN-4; RN-10 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | Artefacto L3. paso2 `src/app.ts:139-145` `new ApiError("NOT_FOUND")` sin details; `errors.ts:44-50` omite el campo. Catálogo §3.2 lista `{resource,id}` pero §1/RN-1 details opcional; AT-09-05-10/RN-10 no exigen details en 404 → MENOR. VERDADERO (R4). Diff: `details: { resource: "route", id: path }`. |


### Resultados — etapa `web`

| Criterio | Resultado | Notas |
|----------|-----------|-------|
| RV-01 | PASA | Existe `.pipeline/revision-web.md` (paso2 y `sut/`) con dos puntos (L1, L3). |
| RV-02 | PASA | `diff -rq` paso1→paso2: solo `revision-web.md` nuevo en `.pipeline/`. JSONL L105–155: un add de esa ruta. |
| RV-03 | PASA | Una escritura (R6): `item_22` add. CMD19/20 son lecturas (`test -e`, `nl -ba`). |
| RV-04 | PASA | R7: `npm run build:web`, `npm run test:web` (14 tests), `npm test`, `npm run build && npm start`, `fetch` a `:3107/api/v1`. |
| RV-05 | PASA | 0/2 con `ancla=NINGUNA`. |
| RV-06 | PASA | 0/2 con `ubicacion=NINGUNA`. |
| RV-07 | PASA | Sin inversiones: MAYOR, MAYOR. |
| RV-08 | PASA | 0/2 con `eje=OTRO`. |
| RV-09 | PASA | 0/2 con `accionable=NO`. |
| RV-10 | PASA | R8: sin relleno (dos ítems de lista, sin fences ni resumen). |
| RV-11 | PASA | 0/2 `FALSO`; 0 `NO_VERIFICABLE`. |
| RV-12 | PASA | 0/2 `NO_RESUELTO`. paso3: `popstate` en `App.tsx`; deadline de rate-limit en `LoginPage.tsx`. |

#### Censo de puntos — `web`

| punto | eje | severidad | ancla | referencias | ubicacion | accionable | veracidad | destino | evidencia |
|-------|-----|-----------|-------|-------------|-----------|------------|-----------|---------|-----------|
| 1 | CORRECCION | MAYOR | SPEC | HU-10-01; RN-9; RN-11; AT-10-01-09 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | Artefacto L1. paso2 `web/src/App.tsx:41-50` sin `popstate`; `session.ts:52-55` sí lo emite; login hace `pushState("/trading")` y deja state `authenticated`. Back → URL `/login` con pantalla autenticada, sin `GET /me`. HU-10-01 RN-9/AT-10-01-09. R4 lectura. Diff: listener `popstate` → `checkPersistedSession` si pathname es `/login`. |
| 2 | CORRECCION | MAYOR | SPEC | HU-10-01; RN-6; AT-10-01-06 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | Artefacto L3. paso2 `LoginPage.tsx:46-52` decrementa `retrySeconds` un tick por `setTimeout(1000)`; `disabled` si `retrySeconds>0`. RN-6/AT-10-01-06: rehabilitar al transcurrir el lapso (reloj, no callbacks). R4. Diff: `retryDeadline = Date.now()+seconds*1000` y remaining contra el reloj. |


### Resultados — etapa `mobile`

| Criterio | Resultado | Notas |
|----------|-----------|-------|
| RV-01 | PASA | Existe `.pipeline/revision-mobile.md` (paso2 y `sut/`) con seis puntos (L1, L3, L5, L7, L9, L11). |
| RV-02 | PASA | `diff -rq` paso1→paso2: solo `revision-mobile.md` nuevo. JSONL L194–345: un add de esa ruta; sin cambios de fuente. |
| RV-03 | PASA | Una escritura (R6): `item_73` add. CMD68 es lectura (`sed -n`). |
| RV-04 | PASA | R7: `npm run build`, `typecheck:mobile` (tsc), `test:mobile` (20 tests), `npm test`, `export:mobile` (Android+iOS). JSONL registra las shells. |
| RV-05 | PASA | 0/6 con `ancla=NINGUNA` (cinco SPEC, uno EJECUCION). |
| RV-06 | PASA | 0/6 con `ubicacion=NINGUNA`. |
| RV-07 | FALLA | 2 inversiones adyacentes / 3 pares (R2): pto 3 MENOR ≺ pto 4 MAYOR; pto 3 MENOR ≺ pto 6 MAYOR; pto 5 MENOR ≺ pto 6 MAYOR. Orden: MAYOR, MAYOR, MENOR, MAYOR, MENOR, MAYOR. |
| RV-08 | PASA | 0/6 con `eje=OTRO`. |
| RV-09 | PASA | 0/6 con `accionable=NO`. |
| RV-10 | PASA | R8: sin resumen/conclusiones ni bloques de código copiados verbatim. |
| RV-11 | PASA | 0/6 `FALSO`; 0 `NO_VERIFICABLE`. |
| RV-12 | PASA | 0/6 `NO_RESUELTO`. paso3 toca AuthContext/session-storage, DepositScreen, usePrivateSocket, LoginScreen y `app.json` en el sentido pedido. |

#### Censo de puntos — `mobile`

| punto | eje | severidad | ancla | referencias | ubicacion | accionable | veracidad | destino | evidencia |
|-------|-----|-----------|-------|-------------|-----------|------------|-----------|---------|-----------|
| 1 | CORRECCION | MAYOR | SPEC | HU-11-01; RN-5; RN-6; AT-11-01-05; AT-11-01-06 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | Artefacto L1. paso2 `AuthContext.tsx:62-75` swallow de `deleteItemAsync`; logout `:93-103` espera al backend primero. `session-storage.ts:16-18` = `deleteItemAsync`. RN-5/6 y AT-11-01-05/06 exigen borrar el token persistido. R1: un punto. R4. Diff: logout local primero; tombstone+retry en `session-storage.ts`. |
| 2 | CORRECCION | MAYOR | SPEC | HU-11-06; RN-2; AT-11-06-01; AT-11-06-26 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | Artefacto L3. paso2 `DepositScreen.tsx:41-63` `setDeposit(response)` sin generación; cambio de activo no cancela. RN-2/AT-11-06-01/26: QR del activo vigente (USDC con `tokenAddress`). R4. Diff: `latestRequestRef` + `deposit?.asset===asset`; test de respuestas fuera de orden. |
| 3 | CORRECCION | MENOR | SPEC | RG-5; HU-11-01; RN-12; AT-11-01-10; AT-11-01-12 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | Artefacto L5. paso2 `usePrivateSocket.ts:99-117`: `onclose` siempre `scheduleReconnect()`; foreground `connect()` sin generación → socket huérfano. Código VERDADERO (R4). MENOR (R2): RG-5 no es RN-*; RN-12/AT-11-01-10/12 no prohíben duplicados. Diff: `onclose` ignora generaciones viejas; `connect()` no abre si ya hay `socket`. |
| 4 | CORRECCION | MAYOR | SPEC | RG-6; HU-10-01; RN-6; AT-10-01-06 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | Artefacto L7. paso2 `LoginScreen.tsx:50-54,60-63,109-113`: muestra `retryAfterSeconds` pero `disabled` solo `submitting`. RG-6 + HU-10-01 RN-6/AT-10-01-06. R4. Diff: `rateLimitedUntil` deadline y botón deshabilitado si `submitting` o cooldown activo. |
| 5 | OPERABILIDAD | MENOR | EJECUCION |  | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | Artefacto L9. paso2 `mobile/app.json:8` `newArchEnabled: true` (Expo ^57). Ancla EJECUCION (R3): no cita spec. expo-doctor 20/21 y el mensaje citado coinciden. No BLOQUEANTE: `export:mobile` compiló. Diff: se elimina la propiedad. |
| 6 | CORRECCION | MAYOR | SPEC | RG-6; HU-10-01; RN-4 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | Artefacto L11. paso2 `LoginScreen.tsx:43-60` `setPassword("")` solo en éxito, no en `INVALID_CREDENTIALS`. RG-6 + HU-10-01 RN-4 / AT-10-01-02. R4. Diff: `setPassword("")` en esa rama. |


## Agregación pre-registrada

- **Por artefacto y por celda:** `PASA / (PASA + FALLA)`, con los `NO_EVALUABLE` excluidos
  del denominador y reportados aparte, discriminados por causa (a/b) — el mismo criterio
  de agregación que las rúbricas de las épicas 10–11.
- **Del censo** se reportan, por artefacto y por celda: cantidad de puntos y, como
  **proporciones sobre esa cantidad**, la distribución de `eje`, `severidad`, `ancla`,
  `ubicacion`, `accionable`, `veracidad` y `destino`.
- **Cruce posterior:** el campo `referencias` permite cruzar mecánicamente los puntos que
  citan un `AT-*` con `runs/<id>/resultados-at.csv`. Es un análisis derivado, no un
  criterio de esta rúbrica, y se hace después de cerrar el censo de la celda.

## Cláusula de re-pre-registro

El instrumento mide la salida del prompt de rol congelado en
`pipeline/comun/prompts/roles/revisor.md` y la secuencia de `pipeline/comun/etapas.yaml`.
Si la piloto cambia el set de roles, la secuencia o ese prompt, la rúbrica se corrige y se
**vuelve a pre-registrar antes de H7** (checklist H6, ítem 12: "si el set de roles cambia
en la piloto, este ítem lo sigue"). Vista la primera implementación, queda fija para todo
el experimento, como los demás instrumentos de `evaluacion/`.

## Limitaciones declaradas

- **Los conteos absolutos no son comparables entre celdas.** Una revisión de 2 puntos
  sobre una implementación buena puede valer más que una de 20 sobre una mala. Comparan
  las **proporciones** del censo y los veredictos de la Parte B; el conteo de puntos
  describe, no ordena.
- **`RV-12` mide el circuito**, no sólo al revisor: un punto correcto que el pase
  correctivo ignora cuenta como `NO_RESUELTO`.
- **`RV-11` y `RV-12` son indulgentes con lo no verificable:** pasan si ningún punto es
  `FALSO` / `NO_RESUELTO`, aunque parte de los puntos hayan quedado `NO_VERIFICABLE`. Es
  deliberado —un veredicto no se apoya en lo que no se pudo comprobar— y por eso la nota
  lleva siempre cuántos puntos quedaron sin verificar.
- **`RV-07` codifica la severidad con los tres buckets de esta rúbrica**, que pueden no
  coincidir con la noción de severidad del propio revisor. La operacionalización es parte
  del instrumento pre-registrado, no una lectura de su intención.
- **La delegación en subagentes no es criterio.** El prompt del rol la instruye
  ([ADR-010](../../decisiones/ADR-010-delegacion-contexto-y-evaluador.md) Decisión 1) pero
  condicionada a que haya trabajo independiente y acotado; un veredicto sobre ella
  penalizaría a una sesión que legítimamente no tenía qué delegar. El fan-out efectivo se
  mide aparte (checklist H6, ítem 24).
