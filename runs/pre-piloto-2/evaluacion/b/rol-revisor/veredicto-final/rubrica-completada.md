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
| RV-01 | PASA | Existe sut/.pipeline/revision-backend.md y snapshots/backend/paso2-revisor/.pipeline/revision-backend.md (1912 bytes, 3 puntos de lista). No vacío ni en otra ruta. |
| RV-02 | PASA | Hash-diff paso1-implementador → paso2-revisor: único alta .pipeline/revision-backend.md; 0 archivos cambiados fuera. JSONL paso 2 (L274-L356) file_change sólo /repo/.pipeline/revision-backend.md. |
| RV-03 | PASA | R6: una sola escritura. JSONL item.completed file_change L349 kind=add path=/repo/.pipeline/revision-backend.md. L351 es sed -n lectura. Ningún shell con >, >>, tee ni parche sobre esa ruta. |
| RV-04 | PASA | R7: L310 npm test (42 pass); L312 npm run build; L318 npm start (escucha :3107); L317 curl /health 200; L334 y L339 node dist/src/app.js inject. Hay ejecución del sistema. |
| RV-05 | PASA | 0/3 puntos con ancla=NINGUNA. Puntos 1-3 ancla=SPEC (RN/AT/HU/RNE citados). |
| RV-06 | PASA | 0/3 con ubicacion=NINGUNA. P1 src/app.ts:71-79,114-125,237-245; P2 src/wallet/crypto.ts:237-239,262-290 y test/wallet-crypto.test.ts:172-187; P3 README.md:42-49. Todos ARCHIVO_LINEA. |
| RV-07 | PASA | R2: buckets de la rúbrica, no Alta/Media/Baja del revisor. Severidades codeadas MAYOR, MAYOR, MAYOR (P3 es RN-6/RN-10). Sin inversión. |
| RV-08 | PASA | 0/3 con eje=OTRO. P1-P2 CORRECCION; P3 OPERABILIDAD (ejemplo operativo del README). |
| RV-09 | PASA | 0/3 accionable=NO. Los tres enuncian corrección (orden del parser; retry CKDpriv; placeholder USDC). |
| RV-10 | PASA | R8: el artefacto son tres ítems de lista, sin encabezado de resumen/conclusiones y sin bloques ```. No hay prosa fuera de la lista. |
| RV-11 | PASA | 0/3 veracidad=FALSO; 0 NO_VERIFICABLE. Los tres VERDADERO (código+spec+reproducción /tmp y eth_getCode 0x). |
| RV-12 | PASA | 0/3 NO_RESUELTO. P1-P3 RESUELTO en paso3 (src/app.ts, src/wallet/crypto.ts, README.md/.env.example). Snapshot paso3 presente. |

#### Censo de puntos

| punto | eje | severidad | ancla | referencias | ubicacion | accionable | veracidad | destino | evidencia |
|---|---|---|---|---|---|---|---|---|---|
| 1 | CORRECCION | MAYOR | SPEC | HU-01-02; RN-8; RN-9; RNE-9; AT-01-02-09; HU-01-01; RN-3; HU-09-05; RN-8; RN-10; AT-09-05-10 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1: un ítem agrupa rate-limit/auditoría/registro/404-405; se codea uno por la mayor severidad. R2: MAYOR (AT/RN, no INV ni arranque). Artefacto revision-backend.md:1. paso2-revisor/src/app.ts:71-79 setErrorHandler cae a INTERNAL_ERROR; :114-125 precheck login en onRequest y 429 recién en el handler; :237-245 isFrameworkValidationError no incluye FST_ERR_CTP_BODY_TOO_LARGE. Spec: HU-01-02 RN-8/RN-9 y AT-01-02-09 (RATE_LIMITED 429 + Retry-After antes del esquema); RNE-9 (auditoría de login, reason RATE_LIMITED); HU-01-01 RN-3 (password fuera de 8-128 → VALIDATION_ERROR 422); HU-09-05 RN-8/RN-10 y AT-09-05-10 (404/405). Reproducción copia /tmp/rev-backend-p2 (npm install + npm run build + inject): JSON ~1.1e6 chars → REGISTER 500 INTERNAL_ERROR; POST /api/v1/auth/login tras 60 fallos 500 y audits n=0; PUT /api/v1/auth/login 500; POST /api/v1/foo 500. Destino paso2→paso3: src/app.ts añade isBodyTooLargeError, writeAudit RATE_LIMITED/VALIDATION_ERROR y requestRoutingError 404/405; test/app.test.ts 'cuerpos sobredimensionados respetan rate limit, validación, auditoría y routing'. |
| 2 | CORRECCION | MAYOR | SPEC | HU-06-02; RN-8; AT-06-02-08 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | Artefacto revision-backend.md:3. paso2-revisor/src/wallet/crypto.ts:237-239 reintenta incrementando solo address_index; :262-290 derivePathCandidate retorna null si I_L >= n o k_hijo == 0 en cualquier paso del path. test/wallet-crypto.test.ts:172-187 inyecta HMAC inválido solo si call === 6 (la hoja). Spec HU-06-02 RN-8 y AT-06-02-08: si el CKDpriv falla se avanza el i de ese paso, conforme a BIP-32. Destino paso3: deriveValidChild reintenta en el nivel que falla; test cubre purpose/coin type/account/change/address_index × (I_L >= n \| k_hijo == 0). |
| 3 | OPERABILIDAD | MAYOR | SPEC | HU-06-04; RN-6; HU-09-01; RN-10 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R2: MAYOR porque cita RN concretas del contrato tokenAddress (no es solo estilo de docs). Artefacto revision-backend.md:5. paso2-revisor/README.md:42-49 export USDC_TOKEN_ADDRESS="0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed". paso2-revisor/src/app.ts:173 si asset=USDC response.tokenAddress = config.usdcTokenAddress. Spec HU-06-04 RN-6 y HU-09-01 RN-10: tokenAddress es la dirección del contrato USDC-mock del entorno. curl 127.0.0.1:8545 eth_getCode params [0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed, latest] → {"result":"0x"}. Destino paso3: README.md reemplaza la EOA por placeholder <DIRECCION_EIP55_DEL_CONTRATO_USDC_MOCK> y documenta eth_getCode; .env.example deja USDC_TOKEN_ADDRESS vacío. |

### Resultados — etapa `web`

| Criterio | Resultado | Notas |
|----------|-----------|-------|
| RV-01 | PASA | Existe sut/.pipeline/revision-web.md y snapshots/web/paso2-revisor/.pipeline/revision-web.md (608 bytes, 1 punto). |
| RV-02 | PASA | Hash-diff paso1 → paso2: único alta .pipeline/revision-web.md. JSONL L228 creó y unlink :memory: durante la sesión; el cierre del paso no lo conserva. file_change sólo revision-web.md. |
| RV-03 | PASA | R6: una escritura. JSONL L232 file_change add /repo/.pipeline/revision-web.md. L230 test -e (MISSING) y L234 sed son lecturas. |
| RV-04 | PASA | R7: L205 npm test --prefix web && npm run build --prefix web && npm test && npm run build; L211 npm run dev (Vite :5173); L210/L217 curl al SUT; L225 node dist inject OPTIONS. Hay ejecución. |
| RV-05 | PASA | 0/1 ancla=NINGUNA. Punto 1 ancla=SPEC (HU-09-01 RN-14 / AT-09-01-15; HU-09-05 RN-10 / AT-09-05-10). |
| RV-06 | PASA | 0/1 ubicacion=NINGUNA. Señala src/app.ts:143-144 → ARCHIVO_LINEA. |
| RV-07 | PASA | Un solo punto MAYOR. Sin inversión posible. |
| RV-08 | PASA | 0/1 eje=OTRO. Punto 1 CORRECCION (405 vs 204 en verbos no contractuales). |
| RV-09 | PASA | 0/1 accionable=NO. Pide reservar 204 al preflight válido y devolver 405 en el resto. |
| RV-10 | PASA | R8: un único ítem de lista, sin resumen/conclusiones ni bloques de código copiados. |
| RV-11 | PASA | 0/1 FALSO. VERDADERO: inject en /tmp/rev-web-p2 reproduce 204 incluso con ACR-Method GET; spec exige 405. |
| RV-12 | PASA | 0/1 NO_RESUELTO. paso3 src/app.ts:143-148 + sendCorsPreflight (204 sólo Origin+método admitido; si no 405). test/app.test.ts invalidPreflights. |

#### Censo de puntos

| punto | eje | severidad | ancla | referencias | ubicacion | accionable | veracidad | destino | evidencia |
|---|---|---|---|---|---|---|---|---|---|
| 1 | CORRECCION | MAYOR | SPEC | HU-09-01; RN-14; AT-09-01-15; HU-09-05; RN-10; AT-09-05-10 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | Artefacto revision-web.md:1. paso2-revisor/src/app.ts:143-144 app.options("/api/v1/auth/login") y app.options("/api/v1/me") responden 204 sin mirar CORS. Reproducción /tmp/rev-web-p2 inject: OPTIONS /api/v1/auth/login sin headers → 204; con Origin + Access-Control-Request-Method GET → 204; OPTIONS /api/v1/me → 204. Spec HU-09-01 RN-14 / AT-09-01-15 y HU-09-05 RN-10 / AT-09-05-10: método no permitido en ruta existente → 405 METHOD_NOT_ALLOWED details {method, allowed}. Login admite POST, no GET. Destino paso3 src/app.ts:143-148 sendCorsPreflight(request, reply, "POST"\|"GET"): 204 sólo si Origin no vacío y ACR-Method coincide; si no sendRoutingError 405. test/app.test.ts agrega invalidPreflights (sin headers, ACR-Method GET sobre login, etc.). |

### Resultados — etapa `mobile`

| Criterio | Resultado | Notas |
|----------|-----------|-------|
| RV-01 | PASA | Existe sut/.pipeline/revision-mobile.md y snapshots/mobile/paso2-revisor/.pipeline/revision-mobile.md (1454 bytes, 2 puntos). |
| RV-02 | PASA | Hash-diff paso1 → paso2: único alta .pipeline/revision-mobile.md; 0 cambios fuera. JSONL L280 file_change sólo esa ruta. |
| RV-03 | PASA | R6: una escritura. JSONL L280 file_change add /repo/.pipeline/revision-mobile.md. L282 sed es lectura. |
| RV-04 | PASA | R7: L256 npm run typecheck --prefix mobile; L257 npm run build; L259 npm test --prefix mobile; L260 npm test; L262 npx expo export --platform all. Hay ejecución del sistema. |
| RV-05 | PASA | 0/2 ancla=NINGUNA. P1 SPEC (HU-11-01 RN/AT, RG-8); P2 SPEC (RG-6, HU-10-01 RN-7 / AT-10-01-07). |
| RV-06 | PASA | 0/2 ubicacion=NINGUNA. P1 api.ts:158-161 y session.ts:35-69; P2 App.tsx:39-44. ARCHIVO_LINEA. |
| RV-07 | PASA | R2: ambos MAYOR (P2 viola AT-10-01-07 vía RG-6; la etiqueta Baja se ignora). MAYOR luego MAYOR: sin inversión. |
| RV-08 | PASA | 0/2 eje=OTRO. Ambos CORRECCION (carrera de sesión; aviso de expiración). |
| RV-09 | PASA | 0/2 accionable=NO. P1 pide asociar 401 a token/época y serializar alta/borrado; P2 conservar motivo y renderizar el aviso. |
| RV-10 | PASA | R8: dos ítems de lista, sin resumen ejecutivo/conclusiones ni bloques ```. No hay prosa fuera de la lista. |
| RV-11 | PASA | 0/2 FALSO; 0 NO_VERIFICABLE. P1 reproducido (stored=null, memory=B); P2 confirmado por código y ausencia del aviso en paso2. |
| RV-12 | PASA | 0/2 NO_RESUELTO. P1: session.ts cola+expectedToken, api.ts/privateSocket.ts pasan token. P2: App.tsx loginNotice + LoginScreen initialNotice. Snapshot paso3 presente. |

#### Censo de puntos

| punto | eje | severidad | ancla | referencias | ubicacion | accionable | veracidad | destino | evidencia |
|---|---|---|---|---|---|---|---|---|---|
| 1 | CORRECCION | MAYOR | SPEC | HU-11-01; RN-2; RN-4; AT-11-01-01; AT-11-01-02; RG-8; AT-11-01-14 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | Artefacto revision-mobile.md:1. paso2-revisor/mobile/src/api.ts:158-161 dispara onUnauthenticated() ante 401 sin identificar el token de la request. session.ts:35-69 establish() espera clearing sólo al inicio, luego saveToken y pisa clearing=null / ended=false; clearSingleton() no recibe época. Reproducción del mismo algoritmo (establish("B") con saveToken pendiente + clearSingleton + resolver save/clear): stored=null memory=B events=[cleared]. Spec HU-11-01 RN-2/RN-4 y AT-11-01-01/02 (persistir y restaurar el token del login); RG-8 / AT-11-01-14 (logout singleton, no borrar la sesión nueva). Destino paso3: api.ts onUnauthenticated(token); session.ts cola + clearSingleton(expectedToken); privateSocket.ts pasa this.options.token. |
| 2 | CORRECCION | MAYOR | SPEC | RG-6; HU-10-01; RN-7; AT-10-01-07; HU-11-01 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R2: MAYOR por AT-10-01-07 / RN-7 vía paridad; la etiqueta Baja del revisor no se usa. Artefacto revision-mobile.md:3. paso2-revisor/mobile/src/App.tsx:39-44 callback de SessionManager sólo setToken(null)+setPhase("anonymous"). LoginScreen.tsx no recibe motivo; grep paso2 mobile/ sin 'sesión expiró' ni initialNotice. Spec: RG-6 de spec/11-cliente-mobile/README.md (paridad salvo diferencias explícitas); HU-10-01 RN-7 y AT-10-01-07 exigen el aviso «Tu sesión expiró, ingresá nuevamente»; HU-11-01 RN-5 redirige al login pero no redefine el aviso. Destino paso3: App.tsx loginNotice = reason==='expired' ? 'Tu sesión expiró, ingresá nuevamente.' : null; LoginScreen initialNotice={loginNotice}. |

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