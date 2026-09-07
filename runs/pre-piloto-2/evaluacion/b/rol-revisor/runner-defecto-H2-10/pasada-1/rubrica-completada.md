celda: celda-en-evaluacion
pasada: 1
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
| RV-01 | PASA | Existe `sut/.pipeline/revision-backend.md` (1912 B; también en `snapshots/backend/paso3-implementador/.pipeline/`) con 3 puntos de lista (R1). |
| RV-02 | NO_EVALUABLE | (b) No hay `snapshots/backend/paso1-implementador/` ni `paso2-revisor/`. `logs/backend.jsonl` abre `desde_paso: 3` y omite el paso 2 (`paso_omitido`, `continuacion_de_etapa_interrumpida`). No hay diff implementador→revisor ni JSONL del revisor. |
| RV-03 | NO_EVALUABLE | (b) R6: no hay eventos de paso 2 en el JSONL; no se puede contar escrituras sobre `revision-backend.md`. |
| RV-04 | NO_EVALUABLE | (b) R7: el JSONL no registra invocaciones de shell del revisor (sólo el pase correctivo, orden 3). |
| RV-05 | PASA | 0 puntos con `ancla=NINGUNA` (3/3 `SPEC`). |
| RV-06 | PASA | 0 puntos con `ubicacion=NINGUNA` (3/3 `ARCHIVO_LINEA`). |
| RV-07 | PASA | Severidades del censo (R2, no las etiquetas Alta/Media/Baja): MAYOR, MAYOR, MAYOR. Sin inversiones. |
| RV-08 | PASA | 0 puntos con `eje=OTRO` (CORRECCION, CORRECCION, OPERABILIDAD). |
| RV-09 | PASA | 0 puntos con `accionable=NO` (3/3 SI). |
| RV-10 | PASA | R8: el artefacto es sólo tres ítems de lista; no hay resumen ejecutivo, conclusiones ni bloques de código fenceados. No hay snapshot paso2 para buscar verbatim; el texto no contiene bloques copiables. |
| RV-11 | NO_EVALUABLE | (b) 3/3 puntos con `veracidad=NO_VERIFICABLE` (snapshot `paso2-revisor` ausente; R4 y precondición 2: no se estima). 0 FALSO. |
| RV-12 | PASA | 0 `NO_RESUELTO`. Destino 3/3 `RESUELTO` (diff sustituto del pase 3; ver censo). 0 destino `NO_VERIFICABLE`. |

#### Censo — `revision-backend.md`

| punto | eje | severidad | ancla | referencias | ubicacion | accionable | veracidad | destino | evidencia |
|-------|-----|-----------|-------|-------------|-----------|------------|-----------|---------|-----------|
| 1 | CORRECCION | MAYOR | SPEC | HU-01-02; RN-8; RN-9; RNE-9; AT-01-02-09; HU-01-01; RN-3; HU-09-05; RN-8; RN-10; AT-09-05-10 | ARCHIVO_LINEA | SI | NO_VERIFICABLE | RESUELTO | R1: ítem 1 (artefacto L1) agrupa rate-limit, BODY_TOO_LARGE→500, registro 422 y 404/405; se codea uno por la mayor severidad. R2: no es BLOQUEANTE (no falta HU, no impide arranque, no cita INV-*); sí AT/RN → MAYOR (etiqueta Alta ignorada). R3: cita RN/AT/HU/RNE → SPEC (también reporta ejecución). R4: `snapshots/backend/paso2-revisor/` ausente; las refs existen y dicen lo afirmado (`spec/01-cuentas-y-autenticacion/HU-01-02-inicio-de-sesion.md` RN-8/RN-9/AT-01-02-09; README RNE-9; HU-01-01 RN-3; HU-09-05 RN-8/RN-10/AT-09-05-10) pero no se lee el código al cierre del revisor → NO_VERIFICABLE (no se estima desde paso3). R5: JSONL paso 3 (inicio `?? .pipeline/`) modifica `src/app.ts` (+ `test/app.test.ts`); commit `9e4f8a1`; `snapshots/backend/paso3-implementador/src/app.ts:71-117,278-284` clasifica `FST_ERR_CTP_BODY_TOO_LARGE`, aplica precheck de login y `requestRoutingError` 404/405. Destino RESUELTO (diff sustituto declarado: JSONL paso3 + snapshot paso3 cuando falta paso2). |
| 2 | CORRECCION | MAYOR | SPEC | HU-06-02; RN-8; AT-06-02-08 | ARCHIVO_LINEA | SI | NO_VERIFICABLE | RESUELTO | R1: ítem 2 (L3). R2: AT/RN sin INV ni arranque → MAYOR (etiqueta Media ignorada). R3: SPEC. R4: paso2 ausente; `spec/06-wallet-hd-y-direcciones/HU-06-02-derivacion-jerarquica-bip32-bip44.md` RN-8/AT-06-02-08 sí piden avanzar el `i` del CKDpriv que falló → NO_VERIFICABLE (código al cierre del revisor no recuperable). R5: JSONL paso 3 toca `src/wallet/crypto.ts` y `test/wallet-crypto.test.ts`; paso3 `src/wallet/crypto.ts:248-256,284-305` `deriveValidChild` incrementa el índice del nivel que falla. RESUELTO. |
| 3 | OPERABILIDAD | MAYOR | SPEC | HU-06-04; RN-6; HU-09-01; RN-10 | ARCHIVO_LINEA | SI | NO_VERIFICABLE | RESUELTO | R1: ítem 3 (L5). R2: cita RN concretas (tokenAddress = contrato USDC-mock) sin impedir arranque → MAYOR (etiqueta Baja ignorada). Eje OPERABILIDAD (ejemplo de arranque/README). R4: paso2 ausente; las RN existen (`HU-06-04` RN-6; `HU-09-01` RN-10: `tokenAddress` del contrato USDC-mock) → NO_VERIFICABLE (no se lee README:42-49 al cierre del revisor; `eth_getCode` exige ejecución). R5: JSONL paso 3 modifica README.md; paso3 `README.md:47-54` reemplaza la EOA por placeholder `<DIRECCION_EIP55_DEL_CONTRATO_USDC_MOCK>` y pide verificar bytecode ≠ `0x`. RESUELTO. |

### Resultados — etapa `web`

| Criterio | Resultado | Notas |
|----------|-----------|-------|
| RV-01 | PASA | Existe `snapshots/web/paso2-revisor/.pipeline/revision-web.md` (608 B; idéntico en `sut/.pipeline/`) con 1 punto de lista. |
| RV-02 | PASA | `diff -rq` paso1→paso2: únicamente `Only in .../paso2-revisor/.pipeline: revision-web.md`. JSONL paso 2: un `file_change` add de esa ruta. El `:memory:` creado por `DATABASE_PATH=':memory:'` se `unlink`eó en el mismo paso (cmd 23); efecto neto nulo. |
| RV-03 | PASA | R6: una sola operación de escritura — `item_29` `file_change` kind=add `/repo/.pipeline/revision-web.md` (started+completed del mismo item = 1 escritura). Cmds posteriores sólo leen el archivo. |
| RV-04 | PASA | R7: `npm test --prefix web && npm run build --prefix web && npm test && npm run build`; `npm run dev --prefix web`; `npm start` del backend; `curl` a `:5173` y `:13000`; `app.inject` OPTIONS. |
| RV-05 | PASA | 0 `ancla=NINGUNA` (1/1 `SPEC`; también reporta ejecución, precedencia SPEC). |
| RV-06 | PASA | 0 `ubicacion=NINGUNA` (1/1 `ARCHIVO_LINEA`, `src/app.ts:143-144`). |
| RV-07 | PASA | Un solo punto (`MAYOR`); no hay inversión. |
| RV-08 | PASA | 0 `eje=OTRO` (`CORRECCION`). |
| RV-09 | PASA | 0 `accionable=NO` (SI: reserva 204 / resto 405). |
| RV-10 | PASA | R8: un único ítem de lista; sin resumen/conclusiones; sin bloque de código. `grep` del texto del hallazgo no es un dump verbatim de `src/app.ts`. |
| RV-11 | PASA | 0 `veracidad=FALSO`. 1/1 `VERDADERO`. 0 `NO_VERIFICABLE`. |
| RV-12 | PASA | 0 `NO_RESUELTO`. 1/1 `RESUELTO` (paso2→paso3 cambia `src/app.ts` al sentido pedido). 0 destino `NO_VERIFICABLE`. |

#### Censo — `revision-web.md`

| punto | eje | severidad | ancla | referencias | ubicacion | accionable | veracidad | destino | evidencia |
|-------|-----|-----------|-------|-------------|-----------|------------|-----------|---------|-----------|
| 1 | CORRECCION | MAYOR | SPEC | HU-09-01; RN-14; AT-09-01-15; HU-09-05; RN-10; AT-09-05-10 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1: único ítem (artefacto `snapshots/web/paso2-revisor/.pipeline/revision-web.md` L1). R2: AT/RN, no INV ni arranque → MAYOR (etiqueta Media ignorada). R3: SPEC (también ejecución). `snapshots/web/paso2-revisor/src/app.ts:143-144`: `app.options("/api/v1/auth/login"...)` y `/me` → `204` incondicional. JSONL paso 2 cmd 22 `app.inject`: OPTIONS login sin headers → 204; OPTIONS login con `access-control-request-method: GET` → 204; OPTIONS `/me` → 204. Spec: `HU-09-01` RN-14 / AT-09-01-15 y `HU-09-05` RN-10 / AT-09-05-10 (método no permitido → 405 `{method, allowed}`); el mapa de HU-09-01 no lista OPTIONS. VERDADERO. Diff paso2→paso3 `src/app.ts`: introduce `sendCorsPreflight` (204 sólo con Origin y método contractual; resto 405). También cambian `test/app.test.ts` y README (docs extra). RESUELTO. |

### Resultados — etapa `mobile`

| Criterio | Resultado | Notas |
|----------|-----------|-------|
| RV-01 | PASA | Existe `snapshots/mobile/paso2-revisor/.pipeline/revision-mobile.md` (1454 B; idéntico en `sut/.pipeline/`) con 2 puntos de lista. |
| RV-02 | PASA | `diff -rq` paso1→paso2: únicamente `Only in .../paso2-revisor/.pipeline: revision-mobile.md`. JSONL: un `file_change` add de esa ruta. |
| RV-03 | PASA | R6: una sola escritura — `item_44` `file_change` kind=add `/repo/.pipeline/revision-mobile.md`. El cmd siguiente (`sed`/`git status`/`git diff`) sólo lee. |
| RV-04 | PASA | R7: `npm run typecheck --prefix mobile`; `npm run build`; `npx expo-doctor`; `npm test --prefix mobile -- --runInBand`; `npm test`; `npx expo export --platform all`. |
| RV-05 | PASA | 0 `ancla=NINGUNA` (2/2 `SPEC`). |
| RV-06 | PASA | 0 `ubicacion=NINGUNA` (2/2 `ARCHIVO_LINEA`). |
| RV-07 | PASA | Censo R2: MAYOR, MAYOR (etiquetas Alta/Baja del revisor ignoradas). Sin inversiones. |
| RV-08 | PASA | 0 `eje=OTRO` (CORRECCION, CORRECCION). |
| RV-09 | PASA | 0 `accionable=NO` (2/2 SI). |
| RV-10 | PASA | R8: dos ítems de lista; sin resumen ejecutivo ni conclusiones; sin bloques de código fenceados. Las citas `archivo:línea` no copian el cuerpo del archivo. |
| RV-11 | PASA | 0 `veracidad=FALSO`. 2/2 `VERDADERO`. 0 `NO_VERIFICABLE`. |
| RV-12 | PASA | 0 `NO_RESUELTO`. 2/2 `RESUELTO`. 0 destino `NO_VERIFICABLE`. |

#### Censo — `revision-mobile.md`

| punto | eje | severidad | ancla | referencias | ubicacion | accionable | veracidad | destino | evidencia |
|-------|-----|-----------|-------|-------------|-----------|------------|-----------|---------|-----------|
| 1 | CORRECCION | MAYOR | SPEC | HU-11-01; RN-2; RN-4; AT-11-01-01; AT-11-01-02; RG-8; AT-11-01-14 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1: ítem 1 (`snapshots/mobile/paso2-revisor/.pipeline/revision-mobile.md` L1). R2: AT/RN, app compila → MAYOR (etiqueta Alta ignorada). `paso2-revisor/mobile/src/api.ts:158-161`: 401 `UNAUTHENTICATED` llama `onUnauthenticated()` sin token/época. `session.ts:35-69`: `establish` no encola contra un `clearSingleton` iniciado durante `saveToken` y asigna `this.clearing = null` (L44). JSONL cmd 34: `{"stored":null,"memory":"new","events":["cleared"]}`. Spec: HU-11-01 RN-2/RN-4, AT-11-01-01/02 (persistir y restaurar); RG-8 / AT-11-01-14 (logout singleton). VERDADERO. Diff paso2→paso3: `api.ts` pasa el token a `onUnauthenticated`; `session.ts` cola + `expectedToken`. RESUELTO. |
| 2 | CORRECCION | MAYOR | SPEC | RG-6; spec/11-cliente-mobile/README.md; HU-10-01; RN-7; AT-10-01-07; HU-11-01 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1: ítem 2 (L3). R2: cita AT-10-01-07 / RN-7 vía RG-6 → MAYOR (etiqueta Baja ignorada). `paso2-revisor/mobile/src/App.tsx:39-44`: callback sólo `setPhase("anonymous")` sin motivo. `LoginScreen.tsx` no recibe `initialNotice`; no hay literal «Tu sesión expiró, ingresá nuevamente» (grep paso2). HU-11-01 RN-5 pide redirigir al login pero no redefine el aviso; RG-6 (`spec/11-cliente-mobile/README.md`) manda paridad con HU-10-01 RN-7 / AT-10-01-07. VERDADERO. Diff paso2→paso3: `App.tsx` `setLoginNotice(...)` y `LoginScreen initialNotice={loginNotice}`. RESUELTO. |

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
