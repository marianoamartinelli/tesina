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
| RV-01 | PASA | Existe `snapshots/backend/paso2-revisor/.pipeline/revision-backend.md` (1912 bytes) e idéntico en `sut/.pipeline/revision-backend.md`. Tres puntos de lista de nivel superior (R1); no vacío. |
| RV-02 | PASA | `diff -rq` paso1-implementador vs paso2-revisor: `Only in snapshots/backend/paso2-revisor: .pipeline` (`revision-backend.md`). JSONL paso 2 (`paso_inicio` L274 `orden: 2` rol=revisor → `paso_fin` L356): único `file_change` sobre `/repo/.pipeline/revision-backend.md`. |
| RV-03 | PASA | Una operación de escritura (R6): `file_change` kind=add, item_37, `item.started` L348 + `item.completed` L349 del mismo ítem. Ningún comando con `>`, `>>`, `tee`, `cat >` ni parche sobre esa ruta (L351 es `sed -n` de lectura). |
| RV-04 | PASA | Ejecución de sistema en paso 2 (R7): `npm test` L310 exit=0; `npm run build` L312 exit=0; `npm run rpc:check` L314 exit=0; `curl -i http://127.0.0.1:3107/health` L317 exit=0; `node` inject `createApplication` L334/L339 (JSON 1.100.000 → 500 `INTERNAL_ERROR`, audits 0); `curl eth_getCode` L336 exit=0 `result=0x`. |
| RV-05 | PASA | 0/3 con `ancla=NINGUNA`. Puntos 1–3: `SPEC`. |
| RV-06 | PASA | 0/3 con `ubicacion=NINGUNA`. Puntos 1–3: `ARCHIVO_LINEA`. |
| RV-07 | PASA | Sin inversiones. Severidad de rúbrica (R2; no Alta/Media/Baja del revisor): MAYOR, MAYOR, MAYOR. |
| RV-08 | PASA | 0/3 con `eje=OTRO`. Puntos 1–2 `CORRECCION`; punto 3 `OPERABILIDAD`. |
| RV-09 | PASA | 0/3 con `accionable=NO`. Los tres enuncian un cambio. |
| RV-10 | PASA | Solo la lista de tres puntos; sin resumen ejecutivo ni conclusiones (R8). Sin fences de código. Ningún bloque copiado verbatim de `paso2-revisor/`. |
| RV-11 | PASA | 0 `FALSO`; 0 `NO_VERIFICABLE`; 3 `VERDADERO` (puntos 1–3). |
| RV-12 | PASA | 0 `NO_RESUELTO`; 3 `RESUELTO`. Diff paso2→paso3: `src/app.ts`, `src/wallet/crypto.ts`, `test/app.test.ts`, `test/wallet-crypto.test.ts`, `README.md`, `.env.example`. |

#### Censo de puntos — `backend`

| punto | eje | severidad | ancla | referencias | ubicacion | accionable | veracidad | destino | evidencia |
|-------|-----|-----------|-------|-------------|-----------|------------|-----------|---------|-----------|
| 1 | CORRECCION | MAYOR | SPEC | HU-01-02; RN-8; RN-9; RNE-9; AT-01-02-09; HU-01-01; RN-3; HU-09-05; RN-10; AT-09-05-10 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1: un ítem (artefacto L1) agrupa parser vs rate-limit, BODY_TOO_LARGE→500, registro 500 vs 422 y 404/405; se codea por el de mayor severidad. R2: MAYOR (AT/RN; no INV ni fallo de arranque). Cita: «el parseo del body puede saltarse las precedencias… FST_ERR_CTP_BODY_TOO_LARGE cae como INTERNAL_ERROR… login 61 devuelve 500… no RATE_LIMITED 429… registro 500… ruta/método inválidos 500». paso2 `src/app.ts:71-79` errorHandler mapea lo no AppError y no isFrameworkValidationError a INTERNAL_ERROR; `237-245` no incluye FST_ERR_CTP_BODY_TOO_LARGE; `Fastify()` sin bodyLimit (default 1 MiB); login onRequest `114-116` solo guarda precheck y el 429 vive en el handler `119-125` tras el parser. Spec: HU-01-02 RN-8/RN-9 y AT-01-02-09 (429 paso 0); RNE-9 auditoría; HU-01-01 RN-3 password>128 → 422; HU-09-05 RN-8/RN-10 y AT-09-05-10 404/405. Destino: paso3 `src/app.ts` añade isBodyTooLargeError, 422, enforceLimit+audit y sendRoutingError 404/405; `test/app.test.ts` «cuerpos sobredimensionados…». |
| 2 | CORRECCION | MAYOR | SPEC | HU-06-02; RN-8; AT-06-02-08 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | Cita artefacto L3: retry «sólo funciona si falla transitoriamente la hoja». paso2 `src/wallet/crypto.ts:237-239` loop `candidate+=1` sobre address_index; `262-290` derivePathCandidate retorna null en cualquier nivel (I_L>=n o k_hijo==0) sin avanzar el i de ese CKD. `test/wallet-crypto.test.ts:172-187` invalida `call===6` (hoja). Spec HU-06-02 RN-8 y AT-06-02-08: índice inválido se descarta y se avanza el siguiente i según BIP-32. Destino: paso3 `deriveValidChild` por nivel y tests por purpose/coin/account/change/address_index × I_L>=n y k_hijo==0. |
| 3 | OPERABILIDAD | MAYOR | SPEC | HU-06-04; RN-6; HU-09-01; RN-10 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | Cita artefacto L5: README publica `0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed` como USDC-mock. paso2 `README.md:44-47` (rango citado 42-49). `curl` a `http://127.0.0.1:8545` method=eth_getCode → `{"jsonrpc":"2.0","id":1,"result":"0x"}` (R4). HU-06-04 RN-6 y HU-09-01 RN-10 exigen `tokenAddress` = contrato USDC-mock del entorno. Destino: paso3 README usa placeholder `<DIRECCION_EIP55_DEL_CONTRATO_USDC_MOCK>` y documenta eth_getCode; `.env.example` aclara vacío a propósito. |

### Resultados — etapa `web`

| Criterio | Resultado | Notas |
|----------|-----------|-------|
| RV-01 | PASA | Existe `snapshots/web/paso2-revisor/.pipeline/revision-web.md` (608 bytes) e idéntico en `sut/.pipeline/revision-web.md`. Un punto de lista; no vacío. |
| RV-02 | PASA | `diff -rq` paso1 vs paso2: `Only in snapshots/web/paso2-revisor/.pipeline: revision-web.md`. JSONL paso 2 L174–L239: único `file_change` sobre `/repo/.pipeline/revision-web.md`. |
| RV-03 | PASA | Una operación (R6): `file_change` kind=add, `item.started` L231 + `item.completed` L232. L230/L234 son `test -e` / `sed -n` de lectura; sin `>`, `>>`, `tee` ni parche. |
| RV-04 | PASA | R7: `npm test --prefix web && npm run build --prefix web && npm test && npm run build` L205 exit=0; `curl` al cliente `http://127.0.0.1:5173/login` L210; `npm run dev --prefix web` L211; `curl` OPTIONS/POST login L217; `node` inject OPTIONS L225 (204 incondicional). |
| RV-05 | PASA | 0/1 con `ancla=NINGUNA`. Punto 1: `SPEC`. |
| RV-06 | PASA | 0/1 con `ubicacion=NINGUNA`. Punto 1: `ARCHIVO_LINEA` (`src/app.ts:143-144`). |
| RV-07 | PASA | Un solo punto MAYOR; no hay inversión. |
| RV-08 | PASA | 0/1 con `eje=OTRO`. Punto 1: `CORRECCION` (OPTIONS/CORS introducidos en la etapa web). |
| RV-09 | PASA | 0/1 con `accionable=NO`. |
| RV-10 | PASA | Un único ítem de lista; sin resumen/conclusiones; sin fences; sin bloque verbatim del repo (R8). |
| RV-11 | PASA | 0 `FALSO`; 0 `NO_VERIFICABLE`; 1 `VERDADERO`. |
| RV-12 | PASA | 0 `NO_RESUELTO`; 1 `RESUELTO`. Diff paso2→paso3: `src/app.ts` (sendCorsPreflight), `test/app.test.ts` (invalidPreflights). |

#### Censo de puntos — `web`

| punto | eje | severidad | ancla | referencias | ubicacion | accionable | veracidad | destino | evidencia |
|-------|-----|-----------|-------|-------------|-----------|------------|-----------|---------|-----------|
| 1 | CORRECCION | MAYOR | SPEC | HU-09-01; RN-14; AT-09-01-15; HU-09-05; RN-10; AT-09-05-10 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | Cita artefacto L1: OPTIONS `/api/v1/auth/login` y `/api/v1/me` responden 204 «incluso sin headers CORS o cuando Access-Control-Request-Method pide un verbo incorrecto (reproducido con GET sobre login)». paso2 `src/app.ts:143-144` `app.options(..., 204)` incondicional; KNOWN_ROUTES login=POST, me=GET (`26-31`). Spec HU-09-01 RN-14 / AT-09-01-15 y HU-09-05 RN-10 / AT-09-05-10: método no permitido → 405 con `details={method, allowed}`. `grep` OPTIONS/CORS/preflight en `spec/`: 0 coincidencias. Destino: paso3 `sendCorsPreflight` exige Origin no vacío y ACR-Method igual al verbo de la ruta; el resto 405; tests `invalidPreflights`. |

### Resultados — etapa `mobile`

| Criterio | Resultado | Notas |
|----------|-----------|-------|
| RV-01 | PASA | Existe `snapshots/mobile/paso2-revisor/.pipeline/revision-mobile.md` (1454 bytes) e idéntico en `sut/.pipeline/revision-mobile.md`. Dos puntos de lista; no vacío. |
| RV-02 | PASA | `diff -rq` paso1 vs paso2: `Only in snapshots/mobile/paso2-revisor/.pipeline: revision-mobile.md`. JSONL paso 2 L192–L287: único `file_change` sobre `/repo/.pipeline/revision-mobile.md`. |
| RV-03 | PASA | Una operación (R6): `file_change` kind=add, `item.started` L279 + `item.completed` L280. L282 es `sed -n` de lectura. |
| RV-04 | PASA | R7: `npm run typecheck --prefix mobile` L256 exit=0; `npm run build` L257 exit=0; `npm test --prefix mobile -- --runInBand` L259 exit=0; `npm test` L260 exit=0; `npx expo export --platform all` L262 exit=0; loop `npm test` App.test.tsx L272 exit=0. |
| RV-05 | PASA | 0/2 con `ancla=NINGUNA`. Puntos 1–2: `SPEC`. |
| RV-06 | PASA | 0/2 con `ubicacion=NINGUNA`. Puntos 1–2: `ARCHIVO_LINEA`. |
| RV-07 | PASA | Sin inversiones. Rúbrica (R2; no Alta/Baja del revisor): MAYOR, MAYOR. |
| RV-08 | PASA | 0/2 con `eje=OTRO`. Ambos `CORRECCION`. |
| RV-09 | PASA | 0/2 con `accionable=NO`. |
| RV-10 | PASA | Dos ítems de lista; sin resumen/conclusiones; sin fences; sin bloque verbatim del repo (R8). |
| RV-11 | PASA | 0 `FALSO`; 0 `NO_VERIFICABLE`; 2 `VERDADERO`. |
| RV-12 | PASA | 0 `NO_RESUELTO`; 2 `RESUELTO`. Diff paso2→paso3: `mobile/src/session.ts`, `api.ts`, `privateSocket.ts`, `App.tsx`, `LoginScreen.tsx` y tests; `dist-export` regenerado. |

#### Censo de puntos — `mobile`

| punto | eje | severidad | ancla | referencias | ubicacion | accionable | veracidad | destino | evidencia |
|-------|-----|-----------|-------|-------------|-----------|------------|-----------|---------|-----------|
| 1 | CORRECCION | MAYOR | SPEC | HU-11-01; RN-2; RN-4; AT-11-01-01; AT-11-01-02; RG-8; AT-11-01-14 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | Cita artefacto L1: 401 tardío interfiere el login siguiente. paso2 `mobile/src/api.ts:158-161` dispara `onUnauthenticated()` sin token/época; `session.ts:35-69` `establish()` no serializa un `clearSingleton()` arrancado durante `saveToken` y asigna `clearing=null`. Reproducción del flujo equivalente: `establish("B")` + clear a mitad de `saveToken` → `stored=null`, `currentToken()="B"`. Spec HU-11-01 RN-2/RN-4, AT-11-01-01/02 (persistir y restaurar) y RG-8/AT-11-01-14 (401 extra = no-op). Destino: paso3 cola `operationTail`, `clearSingleton(expectedToken)`, api/WS pasan el token. |
| 2 | CORRECCION | MAYOR | SPEC | RG-6; spec/11-cliente-mobile/README.md; HU-10-01; RN-7; AT-10-01-07; HU-11-01 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | Cita artefacto L3: redirección por sesión expirada pierde el aviso. paso2 `mobile/src/App.tsx:39-44` solo `setPhase("anonymous")`; L129 `<LoginScreen>` sin motivo; `LoginScreen.tsx:104` muestra `notice` solo de errores de submit. Spec RG-6 (paridad; HU-11-01 no redefine el aviso) y HU-10-01 RN-7 / AT-10-01-07 literal «Tu sesión expiró, ingresá nuevamente». Destino: paso3 `loginNotice` + `initialNotice` con ese literal (más punto final). |

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
