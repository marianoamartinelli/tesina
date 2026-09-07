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
| RV-01 | PASA | Existe sut/.pipeline/revision-backend.md (8620 bytes) idéntico a snapshots/backend/paso2-revisor/.pipeline/revision-backend.md; 10 puntos numerados (L12-117). No vacío. |
| RV-02 | PASA | diff -rq paso1-implementador vs paso2-revisor: Only in paso2-revisor: .pipeline (revision-backend.md). JSONL paso 2: único Write L2982 → /repo/.pipeline/revision-backend.md. Nada fuera de esa ruta. |
| RV-03 | PASA | R6. JSONL logs/backend.jsonl paso_inicio orden=2 L1005 → paso_fin L3117. Una sola escritura sobre revision-backend.md (Write L2982). 0 comandos shell que la escriban. |
| RV-04 | PASA | R7. JSONL paso 2 incluye npm run typecheck (L1093), timeout 900 npm test (L1095), npm run build (L1421), node dist/main.js, npx tsx src/main.ts y curl contra el SUT (p. ej. L1244 GET /health, L1514 register/login). |
| RV-05 | PASA | 0/10 puntos con ancla=NINGUNA. Los 10 citan RN/AT/HU o archivo de spec/. |
| RV-06 | PASA | 0/10 con ubicacion=NINGUNA. Puntos 1-5 y 7-9 ARCHIVO_LINEA; 6 y 10 ARCHIVO. |
| RV-07 | FALLA | 9 pares invertidos (3 adyacentes: 3→4, 5→6, 7→8) sobre buckets de la rúbrica (R2), no las etiquetas del revisor. Secuencia: MAYOR, MAYOR, MENOR, MAYOR, MENOR, MAYOR, MENOR, MAYOR, MAYOR, MENOR. Infractores de orden: puntos 3, 5 y 7 (MENOR) preceden a MAYOR posteriores. |
| RV-08 | PASA | 0/10 con eje=OTRO. Distribución: CORRECCION 8 (1,2,3,4,5,7,8,9); OPERABILIDAD 1 (6); COMPLETITUD 1 (10). |
| RV-09 | PASA | 0/10 con accionable=NO. Los 10 enuncian un cambio. |
| RV-10 | PASA | R8. Sin bloques de código. El preámbulo L3-7 (alcance/completitud/operabilidad) no resume lo ya listado. Sin encabezado de resumen ejecutivo ni conclusiones. |
| RV-11 | PASA | 0/10 con veracidad=FALSO; 0 NO_VERIFICABLE. Los 10 VERDADERO contra paso2-revisor + spec. |
| RV-12 | PASA | 0/10 NO_RESUELTO. Los 10 RESUELTO en el diff paso2-revisor → paso3-implementador (app.ts, config, derivation/bip32, db/accounts, scripts eliminado, bip39, epica-09-rate-limit.test.ts). |

#### Censo de puntos — `backend`

| punto | eje | severidad | ancla | referencias | ubicacion | accionable | veracidad | destino | evidencia |
|-------|-----|-----------|-------|-------------|-----------|------------|-----------|---------|-----------|
| 1 | CORRECCION | MAYOR | SPEC | HU-06-04; RN-4; RN-9 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1-R5. Artefacto L12-22: «Un chainId/network repetido… saltea… validación»; backend/src/http/app.ts:256-267. paso2-revisor app.ts:256-267: guardas `typeof rawChainId === 'string'` / `typeof rawNetwork === 'string'` (array de query repetida en Fastify no entra). Spec HU-06-04 RN-4: si la consulta especifica chainId distinto de Sepolia ⇒ CHAIN_ID_MISMATCH. Destino paso3: queryValues() y `for (const raw of queryValues(query.chainId))` evalúa cada valor. |
| 2 | CORRECCION | MAYOR | SPEC | HU-09-01; RN-10; HU-06-04; RN-6 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R4/R5. L24-32: tokenAddress sin EIP-55; config/index.ts:127-133 y app.ts:280. paso2 parseAddressEnv sólo `/^0x[0-9a-fA-F]{40}$/` y app.ts:280 emite `deps.config.chain.usdcContractAddress` tal cual. HU-09-01 RN-10 y HU-06-04 RN-6 exigen 0x+40 hex con checksum EIP-55. Destino paso3: parseRequiredAddressEnv normaliza con toChecksumAddress() y rechaza mixed-case cuyo checksum no verifica. |
| 3 | CORRECCION | MENOR | SPEC | 00-fundaciones/activos-y-par-de-trading.md | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R2 MENOR (no AT/RN/INV; no impide arranque). L34-41: default hardcodeado; config/index.ts:46,177. paso2 DEFAULT_USDC_CONTRACT_ADDRESS='0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238' como fallback. Spec activos-y-par-de-trading.md §2.2: «no se fija un valor literal aquí… única y constante por entorno». Destino paso3: se elimina el default; ausencia ⇒ ConfigError al arrancar. |
| 4 | CORRECCION | MAYOR | SPEC | HU-06-02; RN-8; HU-06-03; RN-1; HU-06-01; RN-11 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1 agrupa bucle 2³¹ + tests sólo último nivel; se codea por RN-8. L43-63: derivation.ts:102 `if (error instanceof InvalidChildKeyError) continue;`; InvalidChildKeyError.index en bip32.ts:38-46; assignTx.immediate() deposit-address-service.ts:152. HU-06-02 RN-8: avanzar el i del nivel que falló. deriveAccountAt re-deriva el path: fallo en 44'/60'/0'/0 no depende de address_index. Tests wallet-crypto.test.ts:240-302 stubbean el último nivel. Destino paso3: error.depth; continue sólo si depth===5 && index===address_index; resto INTERNAL_ERROR. |
| 5 | CORRECCION | MENOR | SPEC | 00-fundaciones/modelo-de-errores.md | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R2 MENOR (catálogo, no AT/RN). L65-73: db.ts:92-105 isUniqueConstraintViolation acepta todo SQLITE_CONSTRAINT*; accounts-service.ts:137 mapea a EMAIL_ALREADY_EXISTS. modelo-de-errores.md §3.6: disparador exclusivo «Registro con un email ya existente». Destino paso3: isUniqueConstraintViolationOn(error, 'accounts.email'); el resto se propaga. |
| 6 | OPERABILIDAD | MAYOR | SPEC | HU-06-01; RN-6 | ARCHIVO | SI | VERDADERO | RESUELTO | R4/R5. L75-85: scripts/bootstrap-env.mjs persiste WALLET_ENCRYPTION_KEY en backend/.env junto a DATABASE_PATH por defecto backend/data/exchange.db. paso2 bootstrap-env.mjs:16-31 writeFileSync(.env); package.json start/dev lo invocan. HU-06-01 RN-6: la clave «nunca se persiste junto al material cifrado». Destino paso3: desaparece backend/scripts/; start/dev ya no llaman bootstrap; .env.example documenta el riesgo. |
| 7 | CORRECCION | MENOR | SPEC | HU-06-01; RN-6 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R2 MENOR (RN-6 no exige alfabeto base64 estricto; el parseo laxo es real). L86-91: config/index.ts:114-118 Buffer.from(value,'base64') sin round-trip. Node descarta caracteres inválidos. Destino paso3: regex `^[A-Za-z0-9+/]{43}=?$` + round-trip canónico; si no, issue de clave mal formada. |
| 8 | CORRECCION | MAYOR | SPEC | HU-06-01; RN-3; RN-2; AT-06-03-07 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R4/R5. L93-101: bip39.ts:47 `.trim().replace(/\s+/gu,' ')` usado como password PBKDF2 en L172. HU-06-01 RN-3: password = mnemonic_NFKD sin otra transformación. AT-06-03-07: coincidencia con BIP-44 de referencia. Destino paso3: normalizeMnemonic = NFKD puro; canonicalMnemonicForValidation colapsa espacios sólo para RN-2; seed-store persiste NFKD sin colapsar. |
| 9 | CORRECCION | MAYOR | SPEC | HU-06-03; RN-11; HU-09-02; RN-5 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R4/R5. L103-110: app.ts:304-315 INTERNAL_API_KEY opcional; si falta, loopback basta (si no loopback ⇒ 403 UNAUTHORIZED). HU-06-03 RN-11: consulta «no pública». Destino paso3: INTERNAL_API_KEY siempre (ausente ⇒ UNAUTHORIZED deshabilitada; mismatch ⇒ UNAUTHENTICATED con timingSafeEqual). |
| 10 | COMPLETITUD | MENOR | SPEC | AT-09-02-11; HU-09-02; RN-12 | ARCHIVO | SI | VERDADERO | RESUELTO | R2 MENOR (el revisor afirma comportamiento correcto; falta el test). L111-117: grep AT-09-02-11 en snapshots/backend/paso2-revisor/backend/tests → 0 hits (sólo spec). HU-09-02 RN-12/AT-09-02-11: 60 req/60 s por cuenta y endpoint. SlidingWindowRateLimiter existe. Destino paso3: tests/epica-09-rate-limit.test.ts con test «AT-09-02-11: las primeras 60… 61 responde RATE_LIMITED». |

### Resultados — etapa `web`

| Criterio | Resultado | Notas |
|----------|-----------|-------|
| RV-01 | PASA | Existe sut/.pipeline/revision-web.md (7462 bytes) idéntico a snapshots/web/paso2-revisor/.pipeline/revision-web.md; 7 puntos numerados (L18-102). No vacío. |
| RV-02 | FALLA | diff -rq paso1 vs paso2: Only in paso2-revisor: .claude (directorio .claude/worktrees, 0 archivos) además de .pipeline/revision-web.md. Rúbrica: cualquier creación fuera de revision-web.md. JSONL L1324 usa /repo/.claude/worktrees/agent-aefb703021af016e1/web. |
| RV-03 | PASA | R6. JSONL logs/web.jsonl paso_inicio orden=2 L757 → paso_fin L1642. Una sola escritura sobre revision-web.md (Write L1631). Writes a /tmp/mut/run.py no cuentan. 0 bash que escriba el artefacto. |
| RV-04 | PASA | R7. JSONL paso 2: npm run typecheck (L876), npm run build (L880), npm test (L887), npm run test:e2e / vitest e2e (L978, L1497), npm start del backend, curl contra el SUT (L945 /health, L1413 GET /api/v1/me%zz, L1578 barra final). |
| RV-05 | FALLA | 1/7 con ancla=NINGUNA: punto 6 (README.md:12 / e2e; no cita RN/AT/INV/HU ni archivo de spec/). R3. |
| RV-06 | PASA | 0/7 con ubicacion=NINGUNA. Todos ARCHIVO_LINEA. |
| RV-07 | FALLA | 2 pares invertidos (1 adyacente: 3→4). Secuencia de buckets: MAYOR, MAYOR, MENOR, MAYOR, MAYOR, MENOR, MENOR. El punto 3 (MENOR) precede a los MAYOR 4 y 5. |
| RV-08 | FALLA | 1/7 con eje=OTRO: punto 7 (expireSession API muerta; RN-7 ya opera por applyAnonymous). Infractor: 7. |
| RV-09 | PASA | 0/7 con accionable=NO. La sección «Conflicto de spec… (no requiere acción)» (L106-114) está fuera de la lista numerada: no es punto (R1); no entra a RV-09. |
| RV-10 | PASA | R8. Los fences L22-26 y L42-45 son transcripciones HTTP; grep FST_ERR_BAD_URL en paso2-revisor = 0 (no son copia verbatim de un archivo). Preámbulo L7-12 no resume lo listado. «Conflicto de spec» no es resumen de los puntos 1-7 ni conclusiones de ellos. |
| RV-11 | PASA | 0/7 FALSO; 0 NO_VERIFICABLE. Los 7 VERDADERO contra paso2-revisor + spec (punto 2 decidible por lectura de normalizePath + setNotFoundHandler). |
| RV-12 | PASA | 0/7 NO_RESUELTO. Los 7 RESUELTO (frameworkErrors/ignoreTrailingSlash, tests AT-10-01-09/10, parseProfile, quitar Salir, README índice/e2e, borrar expireSession). |

#### Censo de puntos — `web`

| punto | eje | severidad | ancla | referencias | ubicacion | accionable | veracidad | destino | evidencia |
|-------|-----|-----------|-------|-------------|-----------|------------|-----------|---------|-----------|
| 1 | CORRECCION | MAYOR | SPEC | HU-09-05; RN-1; RN-2; RN-6; HU-09-01; RN-14; 00-fundaciones/modelo-de-errores.md | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1 agrupa FST_ERR_BAD_URL + CORS + 431; se codea por RN-1/RN-2. L18-36: Fastify() app.ts:105-112 sin frameworkErrors; setErrorHandler :181-200 no cubre errores pre-ruteo. HU-09-05 RN-1 envelope `{error:{code,message,details?}}`; RN-2 catálogo cerrado (FST_ERR_BAD_URL no está); RN-6 400 no figura. Destino paso3: frameworkErrors (NOT_FOUND/INTERNAL_ERROR) + clientErrorHandler (VALIDATION_ERROR) con envelope y CORS. |
| 2 | CORRECCION | MAYOR | SPEC | HU-09-01; RN-14 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R4/R5. L38-54: normalizePath app.ts:66-69 recorta barra; setNotFoundHandler :202-221 encuentra la ruta en KNOWN_ROUTES y responde 405 con method ∈ allowed. GET /api/v1/me/ no matchea (ignoreTrailingSlash off) pero normalizePath('/api/v1/me/')==='/api/v1/me' methods=['GET']. HU-09-01 RN-14: 405 = método no permitido sobre ruta existente. Destino paso3: routerOptions.ignoreTrailingSlash: true. |
| 3 | COMPLETITUD | MENOR | SPEC | AT-10-01-09; AT-10-01-10; HU-10-01; RN-11; RN-7 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R2 MENOR (implementación correcta; el AT no queda demostrado). L56-73: web/tests/HU-10-01-login.test.tsx:491 y :517. AT-10-01-09 espera meCalls>=1, satisfecho por TradingPage.tsx:29 authorizedFetch('/me'). AT-10-01-10 aserta estado final en login, no que trading nunca se monte. HU-10-01 RN-11: validar con GET /me. Destino paso3: asertos de checking pendiente y watchTradingMount para que trading no se monte en AT-10-01-10. |
| 4 | CORRECCION | MAYOR | SPEC | HU-10-01; RN-11 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R4/R5. L75-81: web/src/api/auth.ts:56-64 fetchProfile lanza TransportError si faltan campos; SessionProvider.tsx:112-114 lo trata como fallo de red ⇒ anonymous. HU-10-01 RN-11: «si responde 200, la sesión es válida». Destino paso3: parseProfile devuelve null sin lanzar; fetchProfile resuelve {profile} y el bootstrap autentica con profile null. |
| 5 | CORRECCION | MAYOR | SPEC | HU-01-03; RN-1; HU-10-01 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R4/R5. L83-89: TradingPage.tsx:50-52 botón Salir → signOut() local. HU-01-03 RN-1: logout invalida el token vía POST /api/v1/auth/logout. KNOWN_ROUTES del snapshot web/paso2 no incluye logout. Destino paso3: se quita el botón y signOut del contexto; README documenta que no hay cierre de sesión. |
| 6 | OPERABILIDAD | MENOR | NINGUNA |  | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R3 ancla=NINGUNA: cita README.md:12 y tests-e2e, no RN/AT/INV/HU ni archivo de spec/. L91-97: índice «secciones 10 a 15» vs Parte II hasta §16 (README L12 vs L544). tests-e2e/login-e2e.test.tsx:31-42 crea email aleatorio; el curl de trader@example.com en §16 es ajeno al e2e. Destino paso3: índice «secciones 10 a 16» y se elimina el curl superfluo del procedimiento e2e. |
| 7 | OTRO | MENOR | SPEC | RN-7 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R8 eje=OTRO (API muerta; RN-7 ya funciona por applyAnonymous). L99-102: SessionProvider.tsx:47,141,168-169. grep expireSession en web/ paso2: sólo esas tres apariciones (definición + value); tests no la invocan. Destino paso3: se eliminan expireSession y signOut del contexto. |

### Resultados — etapa `mobile`

| Criterio | Resultado | Notas |
|----------|-----------|-------|
| RV-01 | PASA | Existe sut/.pipeline/revision-mobile.md (8835 bytes) idéntico a snapshots/mobile/paso2-revisor/.pipeline/revision-mobile.md; 10 puntos numerados (L21-118). No vacío. |
| RV-02 | PASA | diff -rq paso1 vs paso2: Only in paso2-revisor/.pipeline: revision-mobile.md. JSONL: único Write L2015 → /repo/.pipeline/revision-mobile.md. |
| RV-03 | PASA | R6. JSONL logs/mobile.jsonl paso_inicio orden=2 L1078 → paso_fin L2025. Una sola escritura sobre revision-mobile.md (Write L2015). 0 bash que la escriba. |
| RV-04 | PASA | R7. JSONL paso 2: npx tsc --noEmit (L1149, L1173, L1728), npx jest / npm test (L1175, L1552, L1981), npx expo export (L1190 web, L1521 android, L1595 ios), npm start del backend y curl (L1443, L1476). |
| RV-05 | FALLA | 1/10 con ancla=NINGUNA: punto 7 (test anti doble-submit; no cita RN/AT/INV/HU ni spec/). Puntos 3 y 8 son EJECUCION (no NINGUNA). Infractor: 7. |
| RV-06 | PASA | 0/10 con ubicacion=NINGUNA. Punto 8 ARCHIVO (tests/setup.ts sin línea); el resto ARCHIVO_LINEA. |
| RV-07 | FALLA | 9 pares invertidos (2 adyacentes: 5→6, 9→10). Secuencia: MAYOR, MAYOR, MENOR, MENOR, MENOR, MAYOR, MENOR, MENOR, MENOR, MAYOR. MENOR 3-5 preceden al MAYOR 6; MENOR 7-9 preceden al MAYOR 10. |
| RV-08 | PASA | 0/10 con eje=OTRO. CORRECCION 5 (1,2,5,6,10); OPERABILIDAD 2 (3,8); COMPLETITUD 3 (4,7,9). |
| RV-09 | PASA | 0/10 con accionable=NO. |
| RV-10 | PASA | R8. Sin fences de código. Preámbulo L7-15 (completitud/operabilidad) no resume los 10 puntos. Sin encabezado de resumen ejecutivo ni conclusiones. |
| RV-11 | PASA | 0/10 FALSO; 0 NO_VERIFICABLE. Los 10 VERDADERO (punto 8: ausencia de asyncUtilTimeout leída en tests/setup.ts; el default 1000 ms es de la librería). |
| RV-12 | PASA | 0/10 NO_RESUELTO. Los 10 RESUELTO (logout backend+cliente, clearSession verificado, guarda e2e, escaneo App.tsx, copy feedback, RATE_LIMITED+tests, guarda onSubmit, asyncUtilTimeout, README AT-11-01-12 no cubierto, parse EIP-55 + red del backend). |

#### Censo de puntos — `mobile`

| punto | eje | severidad | ancla | referencias | ubicacion | accionable | veracidad | destino | evidencia |
|-------|-----|-----------|-------|-------------|-----------|------------|-----------|---------|-----------|
| 1 | CORRECCION | MAYOR | SPEC | HU-09-01; HU-01-03; RN-1; RN-2; HU-11-01; RN-6; AT-11-01-06 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1 agrupa backend sin ruta + cliente que no llama logout; se codea por RN-1. L21-36: DepositScreen.tsx:120-130 signOut(); SessionProvider.tsx:178 endSession sólo clearSession. backend app.ts:57-64 KNOWN_ROUTES sin /auth/logout. HU-09-01 mapa: Logout POST /api/v1/auth/logout 204. HU-01-03 RN-1: invalidación inmediata. HU-11-01 RN-6 / AT-11-01-06 exigen logout. Destino paso3: sessions.revoke + ruta POST /auth/logout; cliente logout() best-effort antes de borrar. |
| 2 | CORRECCION | MAYOR | SPEC | AT-11-01-06; HU-11-01; RN-6 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R4/R5. L38-49: secure-storage.ts:83-89 clearSession traga errores de deleteItemAsync; endSession (SessionProvider.tsx:104-113) pasa a anonymous igual. restore :127-145 restauraría el token. AT-11-01-06: «reabrir la app no restaura la sesión». Destino paso3: clearSession verifica re-lectura, tombstone y devuelve 'cleared'\|'failed'; logout explícito no se da por bueno si failed. |
| 3 | OPERABILIDAD | MENOR | EJECUCION |  | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R3 ancla=EJECUCION (reporta `npm run test:e2e` → Tests: 2 failed / ECONNREFUSED). L51-58: tests-e2e/deposit-e2e.test.tsx:23-24 `/^https?:\/\//u.test(API_BASE_URL)` pero config.ts:13-17 defaultea a http://localhost:3000/api/v1 ⇒ configured siempre true. Destino paso3: la guarda mira process.env.EXPO_PUBLIC_API_BASE_URL. |
| 4 | COMPLETITUD | MENOR | SPEC | AT-11-01-08 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R4/R5. L60-67: login-security.test.tsx:41 mock virtual de @react-native-async-storage/async-storage (no es dependencia; ningún import); spies :97-107 siempre 0. Escaneo estático :114-134 recorre sólo mobile/src/ (deja fuera App.tsx e index.ts, que de hecho no usan AsyncStorage). Destino paso3: appSourceFiles() cubre App.tsx, index.ts y src/; el test exige esas rutas. |
| 5 | CORRECCION | MENOR | SPEC | AT-11-06-01 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1 agrupa catch ausente + copied que no se resetea en refresh; MENOR (AT-11-06-01 exige la opción de copiar, no el detalle de feedback). L69-75: DepositScreen.tsx:102-107 `void onCopy()` sin catch; copied se resetea en :49/:97 (cambio de activo) no en load(..., 'refresh') :115. Destino paso3: resetCopyFeedback en load; onCopy con try/catch y MESSAGE_COPY_FAILED. |
| 6 | CORRECCION | MAYOR | SPEC | HU-10-01; RN-6; RG-6 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R4/R5. L77-83: LoginScreen.tsx:120-123 si retryAfterSeconds falta o es 0, retryAfter=0 y el botón no se deshabilita. HU-10-01 RN-6 (paridad RG-6): deshabilitar el reintento durante la espera. grep RATE_LIMITED en mobile/tests paso2: 0 hits. Destino paso3: FALLBACK_RETRY_AFTER_SECONDS=60 y describe RATE_LIMITED en login-screen.test.tsx. |
| 7 | COMPLETITUD | MENOR | NINGUNA |  | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R3 ancla=NINGUNA: no cita RN/AT/INV/HU ni spec/. L85-91: login-screen.test.tsx:99-119 segundo fireEvent.press con Pressable disabled (LoginScreen.tsx:219 disabled=submitting) no distingue disabled vs guarda onSubmit L85. Destino paso3: el test invoca onPress directo salteando disabled y cubre la guarda. |
| 8 | OPERABILIDAD | MENOR | EJECUCION |  | ARCHIVO | SI | VERDADERO | RESUELTO | R3 ancla=EJECUCION (reporta 4 tests fallidos bajo carga y 160/160 sin carga). L93-99: tests/setup.ts no llama configure({asyncUtilTimeout}). El default de @testing-library/react-native es 1000 ms (hecho de librería, no exige correr la suite). Destino paso3: configure({ asyncUtilTimeout: 10000 }). |
| 9 | COMPLETITUD | MENOR | SPEC | AT-11-01-12; HU-11-01; RN-12; HU-09-03; HU-09-04 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R4/R5. L101-109: no hay cliente WS en mobile/src; handleUnauthenticated (SessionProvider.tsx:181) sólo lo invocan tests. README paso2 L864 lista AT-11-01-12 como cubierto; describe en session-provider.test.tsx:229 lo presenta como AT-11-01-12. Destino paso3: tabla §24 marca AT-11-01-12 «NO cubierto»; el describe pasa a «RN-12 (parcial)» y declara que no cubre el AT. |
| 10 | CORRECCION | MAYOR | SPEC | HU-09-01; RN-10; HU-11-06; RN-2 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1 agrupa parseo laxo + network/chainId ignorados; se codea por RN-10. L111-118: deposits.ts:29-31 parseDepositAddress sólo exige address string no vacío; network/chainId se parsean :36-37 y no se usan; DepositScreen imprime NETWORK_NAME/CHAIN_ID de config.ts:21. HU-09-01 RN-10: 0x+40 hex EIP-55; HU-11-06 RN-2: indicar la red correcta. Destino paso3: isValidEip55Address en la frontera; la pantalla usa data.network/data.chainId y corta si chainId ≠ 11155111. |

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
