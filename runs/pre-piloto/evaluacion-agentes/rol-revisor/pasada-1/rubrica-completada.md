celda: celda-en-evaluacion
pasada: 1
fecha: 2026-09-06

# Rúbrica manual — Rol `revisor` del pipeline — v1.0

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

- Se completa **en H8**, por el **mismo evaluador** (el tesista), recorriendo las celdas
  en el **orden sorteado** (protocolo §7; checklist H6, ítem 15) y, dentro de cada celda,
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
| RV-01 | PASA | Existe snapshots/backend/paso2-revisor/.pipeline/revision-backend.md (1529 B, 3 puntos de lista). sut/.pipeline/revision-backend.md identico. JSONL L174 paso_inicio orden=2 rol=revisor; L251 paso_fin codigo_salida=0 salida_escrita=true. |
| RV-02 | PASA | diff -rq paso1-implementador vs paso2-revisor: solo aparece .pipeline/ (con revision-backend.md). package-lock.json mismo contenido (cmp identico). JSONL un file_change completed L244 kind=add /repo/.pipeline/revision-backend.md; git status L241 .pipeline vacio antes de escribir; L246 lee el md. Nada fuera de la ruta de salida. |
| RV-03 | PASA | R6: una sola operacion de escritura. JSONL item.started+item.completed del mismo id item_35 file_change kind=add sobre /repo/.pipeline/revision-backend.md (L244 completed). Ningun comando con >, >>, tee, cat > ni parche adicional sobre esa ruta (los sed/nl posteriores solo leen). |
| RV-04 | PASA | R7: JSONL paso 2 ejecuto el sistema: L219 npm run build exit=0; L220 npm test (vitest, tests passing); L227 curl /health y /api/v1/foo; L228 npm start (abortado); L232 node inject buildApp login sin password; L239 timeout 2s node deriveNextValidAddress. |
| RV-05 | PASA | 0 puntos con ancla=NINGUNA. 3/3 SPEC (puntos 1-3). |
| RV-06 | PASA | 0 puntos con ubicacion=NINGUNA. 3/3 ARCHIVO_LINEA. |
| RV-07 | PASA | Buckets rubricados: 1 MAYOR, 2 MAYOR, 3 MENOR. Sin inversiones. (Etiquetas Alta/Media/Baja del revisor ignoradas; R2). |
| RV-08 | PASA | 0 puntos con eje=OTRO. 3/3 CORRECCION (mandato del rol). |
| RV-09 | PASA | 0 puntos con accionable=NO. 3/3 SI. |
| RV-10 | PASA | R8: sin resumen ejecutivo ni conclusiones; sin bloques fenceados. Tres items de lista, sin prosa extra. No hay bloque de codigo copiado verbatim del repo. |
| RV-11 | PASA | 0 puntos con veracidad=FALSO. 3/3 VERDADERO. 0 NO_VERIFICABLE. |
| RV-12 | PASA | 0 puntos NO_RESUELTO. 3/3 RESUELTO (wallet.ts+test; app.ts+auth-service+login-audit.test.ts; NOT_FOUND con details). Snapshot paso3 presente. |

#### Censo de puntos — etapa `backend`

| punto | eje | severidad | ancla | referencias | ubicacion | accionable | veracidad | destino | evidencia |
|---|---|---|---|---|---|---|---|---|---|
| 1 | CORRECCION | MAYOR | SPEC | HU-06-02; RN-8; AT-06-02-08 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1: artefacto L1 (unico item Alta). Cita: `src/crypto/wallet.ts:156-183` captura InvalidDerivedKeyError de cualquier componente del path pero reintenta solo address_index; repro I_L>=n en 44' abortado por timeout; cobertura solo ultimo child (`test/wallet.test.ts:89-100`). paso2-revisor/src/crypto/wallet.ts:156-158 deriveAddress recorre [...BIP44_ETHEREUM_PREFIX, addressIndex] via deriveChild; :80 lanza InvalidDerivedKeyError si I_L>=n; deriveNextValidAddress:177-185 incrementa address_index hasta MAX_ADDRESS_INDEX=2^31-1. Un fallo en un componente fijo hace fallar todos los indices. Spec HU-06-02 RN-8 (L65-68) y AT-06-02-08 (L170-177): si I_L>=n o k_hijo==0 se descarta ese indice y se avanza, determinista. R3 SPEC (cita HU/RN/AT; el timeout no cambia ancla). R2 MAYOR (incumple RN/AT; el artefacto arranca: JSONL L220 npm test exit 0). R4 VERDADERO por lectura del bucle (no hace falta reejecutar el timeout). R5 RESUELTO: diff paso2->paso3 wallet.ts introduce deriveNextValidChild por componente; wallet.test.ts cubre inyeccion en purpose/coinType/account/change/addressIndex. |
| 2 | CORRECCION | MAYOR | SPEC | RNE-9; HU-01-02; RN-8; RN-9 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1: artefacto L2; agrupa VALIDATION_ERROR sin auditar y RATE_LIMITED en parsing sin auditRateLimited; un punto, severidad del mayor (ambos MAYOR). Cita: `src/app.ts:111-119,194-197` rechaza logins en parsing/esquema antes de la unica escritura (`src/services/auth-service.ts:75-97,114-123`); JSON malformado ya rate-limited sale del error handler sin auditRateLimited. Verificado: login sin password -> 422 VALIDATION_ERROR y auth_audit 0 filas. paso2 app.ts:111-118 error handler envia RATE_LIMITED por pendingPublicRateLimit sin auditar; :194-197 login llama validateCredentialsBody (:44-62, lanza VALIDATION_ERROR si falta password) antes de authService.login; login() audita solo INVALID_CREDENTIALS/SUCCESS (:85-96); auditRateLimited (:110-112) solo desde enforcePublicRateLimit (:162-166), que no corre si el parseo JSON falla. Spec Epica 01 RNE-9 (README L136-140): todo intento de login (exito o fallo) con reason RATE_LIMITED etc.; HU-01-02 RN-8/RN-9 (L69-84) fijan rate limit antes del esquema. R3 SPEC. R2 MAYOR. R4 VERDADERO (codigo + el inject del revisor coincide con el camino 422/auditCount=0, verificable estaticamente). R5 RESUELTO: paso3 centraliza auditLoginAttempt en onResponse de app.ts y cubre VALIDATION_ERROR/RATE_LIMITED; test/login-audit.test.ts nuevo. |
| 3 | CORRECCION | MENOR | SPEC | 00-fundaciones/modelo-de-errores.md; HU-09-05; RN-4; RN-10 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1: artefacto L3. Cita: `src/app.ts:139-145` NOT_FOUND sin details; GET /api/v1/foo solo code y message; pide details={resource,id} segun catalogo §3.2 y HU-09-05 RN-4/RN-10. paso2 app.ts:139-145 setNotFoundHandler: si la ruta no esta en KNOWN_ROUTES, `new ApiError("NOT_FOUND")` sin details; errors.ts:44-50 omite details si no hay. Catalogo 00-fundaciones/modelo-de-errores.md §3.2 L90: NOT_FOUND details esperado {resource, id}. HU-09-05 RN-4 (L33-36): details sigue claves del catalogo; RN-1 (L25-27) details opcional; RN-10 (L89-93) para ruta inexistente exige NOT_FOUND con envelope (details explicitos solo para METHOD_NOT_ALLOWED); AT-09-05-10 (L158-163) no exige details en 404. R2 MENOR: no es INV ni arranque; RN-10/AT no mandan {resource,id} y RN-1 deja details opcional (la etiqueta Baja del revisor no se usa). R3 SPEC. R4 VERDADERO: el 404 sale sin details (lectura; el curl del revisor L227 mostro solo code/message, confirmable en codigo). R5 RESUELTO: paso3 app.ts NOT_FOUND con {resource:"route", id: path}. |

### Resultados — etapa `web`

| Criterio | Resultado | Notas |
|----------|-----------|-------|
| RV-01 | PASA | Existe snapshots/web/paso2-revisor/.pipeline/revision-web.md (991 B, 2 puntos). sut/.pipeline/revision-web.md identico. JSONL L105 paso_inicio orden=2; L155 paso_fin codigo_salida=0 salida_escrita=true. |
| RV-02 | PASA | diff -rq paso1 vs paso2: Only in paso2-revisor/.pipeline: revision-web.md. JSONL file_change completed L150 kind=add /repo/.pipeline/revision-web.md. git status previo L146 ?? .pipeline/ (revision-backend.md ya existia); no hay otros cambios de contenido en el snapshot. |
| RV-03 | PASA | R6: una sola escritura. file_change item_22 add revision-web.md (L150 completed). L148 test -e reporto absent antes de escribir; L152 nl -ba solo lee. Sin redirects de shell sobre esa ruta. |
| RV-04 | PASA | R7: L133 npm run build:web (vite production) exit=0; L134 npm run test:web (14 tests); L135 npm test backend; L142 fetch register/login/me contra 127.0.0.1:3107; L143 npm run build && npm start (servidor). |
| RV-05 | PASA | 0 puntos con ancla=NINGUNA. 2/2 SPEC. |
| RV-06 | PASA | 0 puntos con ubicacion=NINGUNA. 2/2 ARCHIVO_LINEA. |
| RV-07 | PASA | Buckets: 1 MAYOR, 2 MAYOR. Sin inversiones. |
| RV-08 | PASA | 0 puntos eje=OTRO. 2/2 CORRECCION. |
| RV-09 | PASA | 0 puntos accionable=NO. 2/2 SI. |
| RV-10 | PASA | R8: dos items de lista (L1 y L3) sin resumen/conclusiones ni bloques de codigo. Sin prosa fuera de la lista (L2 en blanco). |
| RV-11 | PASA | 0 FALSO. 2/2 VERDADERO. 0 NO_VERIFICABLE. |
| RV-12 | PASA | 0 NO_RESUELTO. 2/2 RESUELTO (App.tsx+App.test.tsx popstate/GET /me; LoginPage.tsx+LoginPage.test.tsx deadline). Snapshot paso3 presente. |

#### Censo de puntos — etapa `web`

| punto | eje | severidad | ancla | referencias | ubicacion | accionable | veracidad | destino | evidencia |
|---|---|---|---|---|---|---|---|---|---|
| 1 | CORRECCION | MAYOR | SPEC | HU-10-01; RN-9; RN-11; AT-10-01-09 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1: artefacto L1. Cita: `web/src/App.tsx:41-50` valida sesion solo al montar y no escucha popstate, aunque `web/src/session.ts:52-55` lo emite; atras deja URL /login con pantalla autenticada sin GET /me ni redirigir a /trading. paso2 App.tsx:41-46 useEffect solo checkPersistedSession + SESSION_EXPIRED_EVENT, sin popstate; handleAuthenticated:48-50 navigate("/trading")+setState(authenticated). session.ts:52-55 navigate hace pushState/replaceState y dispatch PopStateEvent. Tras login, history queda /login luego /trading; Back cambia URL a /login sin revalidar. Spec HU-10-01 RN-9 (L24) sesion activa en login redirige a trading; RN-11 (L26) valida GET /me al cargar; AT-10-01-09 (L87-91) navegar a login con token vigente y GET /me 200 redirige a trading. R3 SPEC. R2 MAYOR. R4 VERDADERO por lectura (no hay listener popstate). R5 RESUELTO: paso3 App.tsx agrega listener popstate que llama checkPersistedSession al entrar a /login; App.test.tsx cubre AT-10-01-09 SPA. |
| 2 | CORRECCION | MAYOR | SPEC | HU-10-01; RN-6; AT-10-01-06 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1: artefacto L3 (2o item de lista; L2 en blanco no es punto). Cita: `web/src/LoginPage.tsx:46-52` resta uno por setTimeout; pestana suspendida descuenta un segundo al reanudar y deja Ingresar deshabilitado tras retryAfterSeconds. paso2 LoginPage.tsx:46-52 useEffect encadena un setTimeout(1000) que hace current-1; :115 disabled incluye retrySeconds>0. Un solo timer pendiente: si la pestana se congela, al volver solo baja 1. Spec HU-10-01 RN-6 (L21) y AT-10-01-06 (L68-72): transcurrido el lapso de details.retryAfterSeconds se rehabilita el boton. R3 SPEC. R2 MAYOR. R4 VERDADERO: el codigo cuenta callbacks, no Date.now. R5 RESUELTO: paso3 introduce retryDeadline=Date.now()+seconds*1000 y remaining por reloj; LoginPage.test.tsx avanza el reloj 30s con un tick y espera boton habilitado. |

### Resultados — etapa `mobile`

| Criterio | Resultado | Notas |
|----------|-----------|-------|
| RV-01 | PASA | Existe snapshots/mobile/paso2-revisor/.pipeline/revision-mobile.md (3431 B, 6 puntos). sut/.pipeline/revision-mobile.md identico. JSONL L194 paso_inicio orden=2; L345 paso_fin codigo_salida=0 salida_escrita=true. |
| RV-02 | PASA | diff -rq paso1 vs paso2: Only in paso2-revisor/.pipeline: revision-mobile.md. JSONL file_change completed L340 kind=add /repo/.pipeline/revision-mobile.md. git status L318/L337 ?? .pipeline/ (backend+web ya estaban); L342 lee el md. Snapshot sin otros diffs. |
| RV-03 | PASA | R6: una sola escritura. file_change item_73 add revision-mobile.md (L340 completed). L342 sed -n solo lee. Sin >, >>, tee ni parches extra sobre esa ruta. |
| RV-04 | PASA | R7: L311 npm run build; L312 npm run typecheck:mobile; L313 npm run test:mobile (20 tests); L314 npm test; L316 npm run export:mobile (expo export android/ios); L333 npx expo-doctor@latest. |
| RV-05 | PASA | 0 puntos con ancla=NINGUNA. SPEC: 1,2,3,4,6; EJECUCION: 5 (expo-doctor; R3). |
| RV-06 | PASA | 0 puntos con ubicacion=NINGUNA. 6/6 ARCHIVO_LINEA. |
| RV-07 | FALLA | 1 inversion: punto 5 (MENOR, extra property app.json / expo-doctor, sin AT/RN y el export pasa) precede al punto 6 (MAYOR, RN-4 via RG-6). Orden rubricado: MAYOR, MAYOR, MAYOR, MAYOR, MENOR, MAYOR. R2 usa buckets de la rubrica, no Alta/Media/Baja. |
| RV-08 | PASA | 0 puntos eje=OTRO. CORRECCION: 1,2,4,6; OPERABILIDAD: 3,5. |
| RV-09 | PASA | 0 puntos accionable=NO. 6/6 SI. |
| RV-10 | PASA | R8: seis items de lista (L1,3,5,7,9,11) sin resumen ejecutivo, conclusiones ni bloques fenceados. Prosa vacia entre items no es punto (R1) ni relleno de resumen. |
| RV-11 | PASA | 0 FALSO. 6/6 VERDADERO. 0 NO_VERIFICABLE. |
| RV-12 | PASA | 0 NO_RESUELTO. 6/6 RESUELTO (AuthContext+session-storage; DepositScreen; usePrivateSocket; LoginScreen rate-limit y password; app.json sin newArchEnabled; tests asociados). Snapshot paso3 presente. |

#### Censo de puntos — etapa `mobile`

| punto | eje | severidad | ancla | referencias | ubicacion | accionable | veracidad | destino | evidencia |
|---|---|---|---|---|---|---|---|---|---|
| 1 | CORRECCION | MAYOR | SPEC | HU-11-01; RN-5; RN-6; AT-11-01-05; AT-11-01-06 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1: artefacto L1; agrupa swallow de deleteItemAsync y logout que espera al backend primero (un punto, MAYOR). Cita: AuthContext.tsx:62-75 ignora fallo de SecureStore.deleteItemAsync y marca sesion eliminada; logout:93-103 espera al backend; si fallan remoto y borrado local el token queda y un cold start reautentica; aun con logout remoto se restaura el token revocado antes del primer 401. paso2 AuthContext.tsx:66-75 try/catch vacio alrededor de sessionStorage.remove() y anyway limpia memoria; logout:93-103 await logoutRequest y recien despues handleUnauthenticated. session-storage.ts:16-18 remove = deleteItemAsync sin reintento. Spec HU-11-01 RN-6 (L48-49) y AT-11-01-06 (L117-122): logout borra token del almacen seguro y memoria; reabrir no restaura. RN-5/AT-11-01-05: UNAUTHENTICATED borra el persistido. RN-11 cubre fallo de LECTURA, no de delete. R3 SPEC. R2 MAYOR. R4 VERDADERO. R5 RESUELTO: paso3 handleUnauthenticated await sessionStorage.remove() sin tragar; logout borra local primero; session-storage.ts reintenta overwrite+delete con tombstone signed-out. |
| 2 | CORRECCION | MAYOR | SPEC | HU-11-06; RN-2; AT-11-06-01; AT-11-06-26 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1: artefacto L3. Cita: DepositScreen.tsx:41-63 cada cambio dispara carga sin cancelar ni validar activo vigente; respuesta ETH tardia puede pisar USDC (o viceversa). paso2 load():41-59 await getDepositAddress(asset) y setDeposit(response) sin request id; useEffect:61-63 void load() al cambiar asset. Spec HU-11-06 RN-2 (L42-54): QR EIP-681 segun activo (ETH vs USDC con tokenAddress); AT-11-06-01 (L152-157) aclara el activo correspondiente; AT-11-06-26 (L339-346) URI USDC con tokenAddress. Mostrar QR del activo anterior bajo el selector viola RN-2. R3 SPEC. R2 MAYOR. R4 VERDADERO. R5 RESUELTO: paso3 latestRequestRef ignora respuestas stale; selectAsset invalida; render exige deposit.asset===asset; app.test.tsx cambia en el diff. |
| 3 | OPERABILIDAD | MAYOR | SPEC | RG-5; HU-11-01; RN-12; AT-11-01-10; AT-11-01-12 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1: artefacto L5. Cita: usePrivateSocket.ts:99-117 onclose del socket anterior llama siempre scheduleReconnect() aunque connect() ya instalo uno nuevo en AppState=active; background->foreground rapido->onclose viejo agenda un tercer socket. paso2 :99-103 onclose: if (current===socket) socket=null; luego scheduleReconnect() siempre (aunque current!==socket). AppState active:106-109 foreground=true; connect() crea socket nuevo sin cerrar el programado. scheduleReconnect:45-54 no chequea generacion. Spec HU-11 README RG-5 (L100-102): suspender en background y reconectar/resync en foreground; HU-11-01 RN-12 (L73-77) handshake con el mismo token; AT-11-01-10/12 ciclo de vida/reconexion. El defecto de sockets duplicados es real (lectura). R3 SPEC. R2 MAYOR (cita RN/AT de ciclo de vida; no impide arranque). R4 VERDADERO del codigo. R5 RESUELTO: paso3 onclose retorna si current!==socket; connect() no abre otro si ya hay socket. |
| 4 | CORRECCION | MAYOR | SPEC | RG-6; HU-10-01; RN-6; AT-10-01-06 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1: artefacto L7. Cita: LoginScreen.tsx:50-54 muestra retryAfterSeconds pero finally:60-63 rehabilita el boton; disabled:109-113 solo depende de submitting. Paridad RG-6 vs HU-10-01 RN-6 / AT-10-01-06. paso2 :50-54 setError con segundos; :60-63 submittingRef=false; setSubmitting(false); Pressable disabled={submitting} :111. No hay cooldown. Spec HU-11 README RG-6 (L103-104) paridad observable con HU-10-01; HU-10-01 RN-6 y AT-10-01-06 deshabilitan reintento durante retryAfterSeconds. R3 SPEC. R2 MAYOR. R4 VERDADERO. R5 RESUELTO: paso3 rateLimitedUntil deadline; disabled si submitting o rateLimitedUntil!==null; submit no envia en cooldown. |
| 5 | OPERABILIDAD | MENOR | EJECUCION |  | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1: artefacto L9. Cita: `mobile/app.json:8` declara newArchEnabled, no admitida por esquema Expo SDK 57; expo-doctor falla `should NOT have additional property 'newArchEnabled'` (20/21). Pide eliminar/reemplazar. No cita RN/AT/HU/spec (R3 -> EJECUCION, no NINGUNA). paso2 mobile/app.json:8 `"newArchEnabled": true`; package.json expo ^57.0.16. R2 MENOR: no es INV ni AT/RN; el artefacto SI compila/exporta (JSONL L311 npm run build, L312 typecheck:mobile, L316 npm run export:mobile exit 0) asi que no es BLOQUEANTE. R4 VERDADERO: la propiedad extra esta en app.json:8 (lectura). El chequeo expo-doctor es el metodo de descubrimiento; el estado senalado se verifica en el archivo. R5 RESUELTO: paso3 app.json elimina newArchEnabled. |
| 6 | CORRECCION | MAYOR | SPEC | RG-6; HU-10-01; RN-4 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1: artefacto L11. Cita: LoginScreen.tsx:43-60 solo setPassword("") tras exito, no en INVALID_CREDENTIALS. RG-6 paridad con HU-10-01 RN-4 (limpiar password, conservar email). paso2 :45-49 try login; setPassword("") solo en el camino feliz; catch INVALID_CREDENTIALS:48-49 setError sin limpiar password. Spec HU-10-01 RN-4 (L19) y AT-10-01-02a (L41-42): el campo password se limpia; HU-11 README RG-6 exige paridad salvo diferencias explicitas (HU-11-01 RN-3/AT-11-01-04 no exceptuan este punto). R3 SPEC. R2 MAYOR (RN concreta via RG-6). R4 VERDADERO. R5 RESUELTO: paso3 catch INVALID_CREDENTIALS hace setPassword(""). Nota RV-07: este MAYOR queda despues del punto 5 MENOR. |

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
