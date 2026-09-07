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
| RV-01 | PASA | Existe snapshots/backend/paso2-revisor/.pipeline/revision-backend.md (8620 B) con 10 puntos numerados; sut/.pipeline/revision-backend.md idéntico. No vacío. |
| RV-02 | PASA | diff -rq paso1-implementador vs paso2-revisor: sólo «Only in paso2: .pipeline» (revision-backend.md). JSONL paso2: 1 Write a /repo/.pipeline/revision-backend.md; bash no redirige a esa ruta. |
| RV-03 | PASA | JSONL paso_inicio orden=2 → paso_fin: una única tool_use Write file_path=/repo/.pipeline/revision-backend.md. 0 comandos con >, >>, tee, cat > sobre esa ruta (R6). salida_escrita=true. |
| RV-04 | PASA | ≥1 ejecución del sistema (R7): `npm run typecheck`; `timeout 900 npm test`; `npm run build`; `node dist/main.js`; múltiples `curl` a /health y /api/v1/* (349 bash en el paso 2). |
| RV-05 | PASA | 10/10 puntos con ancla≠NINGUNA (todas SPEC). |
| RV-06 | PASA | 10/10 puntos con ubicacion≠NINGUNA (8 ARCHIVO_LINEA, 2 ARCHIVO: #6 scripts/bootstrap-env.mjs, #10 backend/tests/). |
| RV-07 | FALLA | Inversiones según buckets R2 (BLOQUEANTE>MAYOR>MENOR): secuencia M,M,m,M,m,M,m,M,M,m. 9 pares i<j con sev(i)<sev(j): MENOR #3 precede MAYOR #4,#6,#8,#9; MENOR #5 precede #6,#8,#9; MENOR #7 precede #8,#9. Primera inversión: #3≺#4. |
| RV-08 | PASA | 0 puntos con eje=OTRO (CORRECCION×8, OPERABILIDAD×1, COMPLETITUD×1; #3 OPERABILIDAD). |
| RV-09 | PASA | 10/10 accionable=SI; todos enuncian un cambio (normalizar query, checksum, config, deriva, constraint, bootstrap, base64, PBKDF2, INTERNAL_API_KEY, test AT-09-02-11). |
| RV-10 | PASA | R8: prosa inicial (L3-8) es alcance/completitud/operabilidad, no resume lo ya listado; no hay encabezado de conclusiones; no hay bloques de código. grep de fragmentos del artefacto en paso2-revisor no halla copias verbatim de fuentes. |
| RV-11 | PASA | 0 puntos veracidad=FALSO; 0 NO_VERIFICABLE (10 VERDADERO, contrastados en paso2-revisor + spec/). |
| RV-12 | PASA | 0 NO_RESUELTO; 10/10 RESUELTO (diff paso2→paso3 toca app.ts, config, derivation, db/accounts, elimina scripts/, bip39, tests rate-limit). README §9 declara los diez resueltos. |

#### Censo de puntos — `backend` (10 puntos)

| punto | eje | severidad | ancla | referencias | ubicacion | accionable | veracidad | destino | evidencia |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | CORRECCION | MAYOR | SPEC | HU-06-04 RN-4; RN-9 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1: ítem 1 (revision-backend.md:12-22). «Un chainId/network repetido… saltea por completo la validación». paso2 app.ts:256-267: guardas `typeof rawChainId === 'string'` / `typeof rawNetwork === 'string'`; un array no se valida. asset repetido sí cae a VALIDATION_ERROR (typeof !== string). spec HU-06-04 RN-4: red/chainId distinto de Sepolia ⇒ CHAIN_ID_MISMATCH; RN-9: precedencia red tras esquema. R4: el defecto es estático (Fastify entrega array si el param se repite). R2: incumple RN-4 ⇒ MAYOR. Destino: paso3 app.ts introduce queryValues() y evalúa cada valor (diff paso2→paso3) ⇒ RESUELTO. |
| 2 | CORRECCION | MAYOR | SPEC | HU-09-01 RN-10; HU-06-04 RN-6 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1: ítem 2 (L24-32). paso2 config/index.ts:127-133 parseAddressEnv sólo `^0x[0-9a-fA-F]{40}$` y app.ts:280 emite usdcContractAddress tal cual. HU-09-01 RN-10 y HU-06-04 RN-6 exigen tokenAddress 0x+40 hex con checksum EIP-55. R2: MAYOR. Destino: paso3 parseRequiredAddressEnv llama toChecksumAddress() y rechaza mixed-case inválido ⇒ RESUELTO. |
| 3 | OPERABILIDAD | MENOR | SPEC | 00-fundaciones/activos-y-par-de-trading.md | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1: ítem 3 (L34-41). paso2 config/index.ts:46 DEFAULT_USDC_CONTRACT_ADDRESS y :177 fallback. spec activos-y-par-de-trading.md §2.2: dirección USDC-mock es parámetro de despliegue, «no se fija un valor literal aquí… única y constante por entorno». R2: no es RN-*/AT-*/INV-* ni impide arranque ⇒ MENOR. R3: ancla SPEC por archivo de spec/. Destino: paso3 elimina el default; ausencia ⇒ ConfigError al arrancar; README/.env.example la marcan obligatoria ⇒ RESUELTO. |
| 4 | CORRECCION | MAYOR | SPEC | HU-06-02 RN-8; HU-06-03 RN-1; HU-06-01 RN-11 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1: ítem 4 agrupa hang+tests insuficientes; se codea por el de mayor severidad (L43-63). paso2 derivation.ts:102 `if (error instanceof InvalidChildKeyError) continue;` sin mirar el nivel; bip32.ts:38-46 InvalidChildKeyError.index es el i BIP-32; deriveAccountAt rederiva el path completo. HU-06-02 RN-8 (avanzar el i del nivel que falló), HU-06-03 RN-1 (registrar address_index efectivo), HU-06-01 RN-11 (abortar ante fallo crítico). tests/wallet-crypto.test.ts:240-302 sólo stubbean el último nivel. R2: incumple RN-* ⇒ MAYOR. El ~9 días es accesorio; el bucle 2³¹ es estático. Destino: paso3 sólo continúa si error.depth === ADDRESS_INDEX_DEPTH && error.index === index; resto INTERNAL_ERROR; bip32.ts gana `depth` ⇒ RESUELTO. |
| 5 | CORRECCION | MENOR | SPEC | 00-fundaciones/modelo-de-errores.md | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1: ítem 5 (L65-73). paso2 db.ts:92-105 isUniqueConstraintViolation acepta todo SQLITE_CONSTRAINT*; accounts-service.ts:137 lo mapea a EMAIL_ALREADY_EXISTS. SCHEMA: UNIQUE en deposit_addresses.address_index y .address además de idx_accounts_email. modelo-de-errores.md §3.6 dispara EMAIL_ALREADY_EXISTS sólo por «registro con un email ya existente». R2: el catálogo no es RN-*/AT-*; HU-01-01 RN-8 cubre unicidad de email, no la exclusividad del code ⇒ MENOR. Destino: paso3 isUniqueConstraintViolationOn(error, 'accounts.email'); el resto no se traduce a ese code ⇒ RESUELTO. |
| 6 | CORRECCION | MAYOR | SPEC | HU-06-01 RN-6 | ARCHIVO | SI | VERDADERO | RESUELTO | R1: ítem 6 (L75-85). paso2 backend/scripts/bootstrap-env.mjs escribe WALLET_ENCRYPTION_KEY en backend/.env (mismo árbol que DATABASE_PATH por defecto ./data/exchange.db). package.json start/dev invocan el script. HU-06-01 RN-6: la credencial «nunca se persiste junto al material cifrado». R2: MAYOR. Ubicación ARCHIVO (sin número de línea). Destino: paso3 elimina scripts/; start = `node --env-file-if-exists=.env dist/main.js`; .env.example documenta el riesgo ⇒ RESUELTO. |
| 7 | CORRECCION | MENOR | SPEC | HU-06-01 RN-6 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1: ítem 7 (L87-91). paso2 config/index.ts:114-118: si no es hex, `Buffer.from(value, 'base64')` (Node descarta caracteres inválidos; verificado: cadena con `*` decodifica). RN-6 habla de credencial ausente/incorrecta al descifrar, no de alfabeto estricto ⇒ R2 MENOR (no es incumplimiento nítido de la RN). Destino: paso3 valida base64 canónico con round-trip ⇒ RESUELTO. |
| 8 | CORRECCION | MAYOR | SPEC | HU-06-01 RN-3; AT-06-03-07 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1: ítem 8 (L93-101). paso2 bip39.ts:47 normalizeMnemonic hace NFKD+trim+colapso `\s+`; mnemonicToSeed:172 usa esa forma como password PBKDF2. HU-06-01 RN-3: password = mnemonic_NFKD sin otra transformación. AT-06-03-07: coincidencia con implementación BIP-44 de referencia. R2: MAYOR. Destino: paso3 normalizeMnemonic = sólo NFKD; canonicalMnemonicForValidation colapsa sólo para validar (RN-2) ⇒ RESUELTO. |
| 9 | CORRECCION | MAYOR | SPEC | HU-06-03 RN-11; HU-09-02 RN-5 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1: ítem 9 (L103-110). paso2 app.ts:304-315: sin INTERNAL_API_KEY sólo se chequea loopback; list() de todas las cuentas. HU-06-03 RN-11: consulta interna «no pública». HU-09-02 RN-5 (aislamiento de listados de usuario) se cita como agravante. R2: MAYOR por RN-11. Destino: paso3 exige INTERNAL_API_KEY siempre (timing-safe); si falta, 403 y la ruta queda deshabilitada ⇒ RESUELTO. |
| 10 | COMPLETITUD | MENOR | SPEC | AT-09-02-11; HU-09-02 RN-12 | ARCHIVO | SI | VERDADERO | RESUELTO | R1: ítem 10 (L112-117). paso2 backend/tests/ no contiene AT-09-02-11 ni epica-09-rate-limit.test.ts (sí epica-09-errores y rate limit de épica 01). HU-09-02 RN-12 / AT-09-02-11: 60 req/60 s por cuenta y endpoint ⇒ 429 RATE_LIMITED. El punto afirma que el comportamiento es correcto y falta el test: R2 MENOR (no incumple el AT de producto; falta DoD). Ubicación ARCHIVO (`backend/tests/`). Destino: paso3 añade tests/epica-09-rate-limit.test.ts y lo lista en README §8 ⇒ RESUELTO. |

### Resultados — etapa `web`

| Criterio | Resultado | Notas |
|----------|-----------|-------|
| RV-01 | PASA | Existe snapshots/web/paso2-revisor/.pipeline/revision-web.md (7462 B) con 7 puntos numerados. No vacío. La sección «Conflicto de spec» (L106-114) no es punto (R1: prosa fuera de la lista → RV-10). |
| RV-02 | FALLA | diff -rq paso1 vs paso2: además de `.pipeline/revision-web.md` aparece el directorio `.claude/worktrees/` (creación fuera del archivo de salida). JSONL: Write a /tmp/mut/* (fuera del repo) y 1 Write al artefacto; el leftover `.claude` queda en el snapshot de cierre. |
| RV-03 | PASA | JSONL paso 2: una sola Write sobre /repo/.pipeline/revision-web.md (otras Write/Edit son /tmp/mut/run.py). 0 redirecciones shell al artefacto (R6). |
| RV-04 | PASA | R7: `npm run typecheck`; `npm run build`; `npm test`; `npm run test:e2e`; `npm start` del backend; `curl` login/me/CORS; `npm run dev` (152 bash). |
| RV-05 | FALLA | 1 punto con ancla=NINGUNA: #6 (README índice/e2e; no cita RN/AT/INV/HU ni archivo de spec/; R3). Los otros 6 son SPEC. |
| RV-06 | PASA | 7/7 ubicacion≠NINGUNA (todas ARCHIVO_LINEA: app.ts, tests, auth.ts, TradingPage, README.md:12, SessionProvider). |
| RV-07 | FALLA | Secuencia R2: M,M,m,M,M,m,m. 2 pares invertidos: MENOR #3 precede MAYOR #4 y #5. Primera inversión: #3≺#4. |
| RV-08 | FALLA | 1 punto eje=OTRO: #7 (expireSession API muerta; no cae en COMPLETITUD/CORRECCION/INVARIANTES/OPERABILIDAD). |
| RV-09 | PASA | 7/7 accionable=SI (el «Conflicto de spec» no es punto y declara no requerir acción). |
| RV-10 | PASA | R8: bloques HTTP (FST_ERR_BAD_URL / METHOD_NOT_ALLOWED) no aparecen en fuentes del paso2 (sólo en el propio artefacto). Intro L1-12 no resume la lista. «### Conflicto de spec detectado» no es conclusiones de lo listado ni código verbatim. |
| RV-11 | PASA | 0 FALSO; 0 NO_VERIFICABLE (7 VERDADERO). |
| RV-12 | PASA | 0 NO_RESUELTO; 7/7 RESUELTO (frameworkErrors+ignoreTrailingSlash, tests AT-10-01-09/10, parseProfile, quita Salir/expireSession, README §16). |

#### Censo de puntos — `web` (7 puntos)

| punto | eje | severidad | ancla | referencias | ubicacion | accionable | veracidad | destino | evidencia |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | CORRECCION | MAYOR | SPEC | HU-09-05 RN-1; RN-2; RN-6; HU-09-01 RN-14 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1: ítem 1 (revision-web.md:18-36). paso2 web/backend app.ts Fastify({logger, trustProxy, bodyLimit}) L106-112 sin frameworkErrors; setErrorHandler L181-200 no cubre errores pre-ruteo. HU-09-05 RN-1 envelope `{error:{code,message,details?}}`; RN-2 catálogo cerrado (FST_ERR_BAD_URL no está); RN-6 tabla sin HTTP 400; HU-09-01 RN-14 ruta inexistente ⇒ NOT_FOUND 404. R2: MAYOR. R4: ausencia de frameworkErrors es estática; el cuerpo Fastify citado es el default del framework. Destino: paso3 frameworkErrors + clientErrorHandler serializan el envelope y aplican CORS ⇒ RESUELTO. |
| 2 | CORRECCION | MAYOR | SPEC | HU-09-01 RN-14 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1: ítem 2 (L38-54). paso2 app.ts:66-69 normalizePath recorta `/`; setNotFoundHandler L202-221: si el path normalizado está en KNOWN_ROUTES ⇒ METHOD_NOT_ALLOWED. Sin ignoreTrailingSlash, GET /api/v1/me/ no matchea, cae al 404-handler y sale 405 con method GET ∈ allowed [GET]. HU-09-01 RN-14: 405 = verbo no permitido sobre ruta existente. R2: MAYOR. Estático. Destino: paso3 routerOptions.ignoreTrailingSlash: true ⇒ RESUELTO. |
| 3 | COMPLETITUD | MENOR | SPEC | AT-10-01-09; AT-10-01-10; RN-11; RN-7 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1: ítem 3 (L56-73). paso2 HU-10-01-login.test.tsx:491 meCalls.length>=1; :517 asertos finales. TradingPage.tsx:29 llama GET /me; SessionProvider.tsx:70-122 es el bootstrap RN-11. Si el bootstrap no llamara /me y confiara en el token, TradingPage igual dispara /me: AT-10-01-09 se satisface y AT-10-01-10 acaba en login vía RN-7 (TradingPage.tsx:33-35) sin prohibir el montaje transitorio. R2: la implementación de producción es correcta (el propio punto lo dice) ⇒ MENOR. Destino: paso3 reescribe ambos tests con meGate/watchTradingMount (causalidad) ⇒ RESUELTO. |
| 4 | CORRECCION | MAYOR | SPEC | HU-10-01 RN-11 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1: ítem 4 (L75-81). paso2 auth.ts:56-64 fetchProfile lanza TransportError si falta un campo; SessionProvider.tsx:112-114 trata el resto como fallo de red ⇒ anonymous + CONNECTION_ERROR. HU-10-01 RN-11: «si responde 200, la sesión es válida»; sólo UNAUTHENTICATED/ausencia/expiración local invalidan. R2: MAYOR. Destino: paso3 parseProfile devuelve null; fetchProfile resuelve `{profile}` sin lanzar ante 200 incompleto; bootstrap autentica igual ⇒ RESUELTO. |
| 5 | CORRECCION | MAYOR | SPEC | HU-01-03 RN-1; HU-10-01 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1: ítem 5 (L83-89). paso2 TradingPage.tsx:50-52 botón Salir → signOut(); SessionProvider.tsx:137-139 applyAnonymous local, sin POST /auth/logout. KNOWN_ROUTES paso2 sin /auth/logout. HU-01-03 RN-1 exige invalidar el token vía POST /api/v1/auth/logout; HU-10-01 no cubre logout. R2: MAYOR por RN-1. Destino: paso3 quita el botón, signOut y expireSession del contexto; README §15 lo documenta ⇒ RESUELTO. |
| 6 | OPERABILIDAD | MENOR | NINGUNA |  | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1: ítem 6 (L91-97). README.md:12 «secciones 10 a 15» pero Parte II llega a §16 (L544 Tests e2e). §16 (L584-585) pide curl trader@example.com; tests-e2e/login-e2e.test.tsx:31-42 crea email aleatorio. R3: no cita RN/AT/INV/HU ni archivo de spec/ ⇒ ancla NINGUNA. R2: MENOR. Destino: paso3 índice «secciones 10 a 16»; el procedimiento e2e ya no pide el curl de registro (L615-621) ⇒ RESUELTO. |
| 7 | OTRO | MENOR | SPEC | RN-7 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1: ítem 7 (L99-102). paso2 SessionProvider.tsx:47,141,168-169 define expireSession y lo pone en el value; ningún call site (grep expireSession sólo esas líneas; tests no la usan). RN-7 lo aplica authorizedFetch vía applyAnonymous('SESSION_EXPIRED'). Eje OTRO: API muerta, no es hueco de HU ni error vs spec ni invariante ni arranque. R2: MENOR. Destino: paso3 elimina expireSession y signOut del contexto ⇒ RESUELTO. |

### Resultados — etapa `mobile`

| Criterio | Resultado | Notas |
|----------|-----------|-------|
| RV-01 | PASA | Existe snapshots/mobile/paso2-revisor/.pipeline/revision-mobile.md (8835 B) con 10 puntos numerados. No vacío. |
| RV-02 | PASA | diff -rq paso1 vs paso2: sólo «Only in paso2/.pipeline: revision-mobile.md». `.claude` ya existía en paso1 (arrastre de web); el paso 2 no crea ni modifica nada fuera del artefacto. |
| RV-03 | PASA | JSONL paso 2: una única Write a /repo/.pipeline/revision-mobile.md. 0 redirecciones shell al artefacto (R6). bash sólo hace `head` de revision-web.md (lectura). |
| RV-04 | PASA | R7: `npx tsc --noEmit`; `npx jest --ci` / `npm test`; `npx expo export` web/android/ios; `npm run test:e2e`; `curl` deposit-address (202 bash). |
| RV-05 | FALLA | 1 punto con ancla=NINGUNA: #7 (test anti doble-submit; no cita RN/AT/INV/HU ni spec/). #3 y #8 son EJECUCION (válido). Resto SPEC. |
| RV-06 | PASA | 10/10 ubicacion≠NINGUNA (todas ARCHIVO_LINEA). |
| RV-07 | FALLA | Secuencia R2: M,M,m,m,m,M,m,m,m,M. 9 pares invertidos: MENOR #3–#5 preceden MAYOR #6 y #10; MENOR #7–#9 preceden MAYOR #10. Primera inversión: #3≺#6. |
| RV-08 | PASA | 0 puntos eje=OTRO. |
| RV-09 | PASA | 10/10 accionable=SI. |
| RV-10 | PASA | R8: intro L1-16 es alcance/completitud/operabilidad, no resume la lista; sin conclusiones; sin bloques de código copiados del repo (el artefacto cita rutas:línea, no listings). |
| RV-11 | PASA | 0 FALSO; 0 NO_VERIFICABLE (10 VERDADERO). |
| RV-12 | PASA | 0 NO_RESUELTO; 10/10 RESUELTO (logout backend+cliente, clearSession verificado, guarda e2e, escaneo raíz, copy feedback, RATE_LIMITED+tests, pressBypassingDisabled, asyncUtilTimeout, README AT-11-01-12 no cubierto, parse EIP-55 + red del backend). |

#### Censo de puntos — `mobile` (10 puntos)

| punto | eje | severidad | ancla | referencias | ubicacion | accionable | veracidad | destino | evidencia |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | CORRECCION | MAYOR | SPEC | HU-09-01; HU-01-03 RN-1; RN-2; HU-11-01 RN-6; AT-11-01-06 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1: ítem 1 (revision-mobile.md:21-36). paso2 DepositScreen.tsx:120-130 signOut(); SessionProvider.tsx:178 endSession→clearSession local, sin POST /auth/logout. app.ts KNOWN_ROUTES L57-64 sin logout. HU-09-01 mapa: Logout POST /api/v1/auth/logout Auth Sí 204. HU-01-03 RN-1/RN-2 invalidación inmediata. HU-11-01 RN-6 y AT-11-01-06 exigen el logout (no se puede quitar el botón, a diferencia del web). R2: MAYOR. Destino: paso3 implementa POST /auth/logout (sessions.revoke CAS) y signOut llama logout() antes del borrado local (auth.ts + SessionProvider) ⇒ RESUELTO. |
| 2 | CORRECCION | MAYOR | SPEC | AT-11-01-06; HU-11-01 RN-6 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1: ítem 2 (L38-49). paso2 secure-storage.ts:83-89 clearSession traga errores de deleteItemAsync y no rechaza; endSession L104-113 pasa a anonymous igual. restore L127-145 restaura si el token sigue. AT-11-01-06: «reabrir la app no restaura la sesión»; RN-6: tras logout no es posible restaurar. R2: MAYOR. Destino: paso3 clearSession verifica re-lectura, lápida no restaurable, devuelve cleared\|failed; endSession no da el logout por bueno si failed ⇒ RESUELTO. |
| 3 | OPERABILIDAD | MENOR | EJECUCION |  | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1: ítem 3 (L51-58). paso2 tests-e2e/deposit-e2e.test.tsx:23 `/^https?:\/\//u.test(API_BASE_URL)`; config.ts:13-17 DEFAULT http://localhost:3000/api/v1 ⇒ configured siempre true. README §24 (L887) «se saltea sola si no se le indica un backend». R3: no cita id de spec/; afirma ejecución (ECONNREFUSED) ⇒ EJECUCION. R4: la inalcanzabilidad del skip es estática. R2: MENOR. Destino: paso3 `configured` mira process.env.EXPO_PUBLIC_API_BASE_URL (L29) ⇒ RESUELTO. |
| 4 | COMPLETITUD | MENOR | SPEC | AT-11-01-08 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1: ítem 4 (L60-67). paso2 login-security.test.tsx:41 jest.mock async-storage virtual:true; :97-107 spies length===0; :114-134 sourceFiles sólo `src/` (join __dirname,..,..,src). App.tsx/index.ts quedan fuera. El paquete no es dependencia. AT-11-01-08 pide spies sobre AsyncStorage. R2: la garantía real es el escaneo; el mock inerte no rompe el producto ⇒ MENOR. Destino: paso3 recorre App.tsx, index.ts y src/ y aserta que el escaneo incluye la raíz ⇒ RESUELTO. |
| 5 | CORRECCION | MENOR | SPEC | AT-11-06-01 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1: ítem 5 (L69-75). paso2 DepositScreen.tsx:102-107 void onCopy() sin catch; copied se resetea al cambiar activo (L97) pero load(..., 'refresh') L115 no llama setCopied(false). AT-11-06-01 exige «opción de copiar»; no detalla error de clipboard ni reset post-refresh ⇒ R2 MENOR. Destino: paso3 catch + MESSAGE_COPY_FAILED; resetCopyFeedback en refresh/cambio de activo ⇒ RESUELTO. |
| 6 | CORRECCION | MAYOR | SPEC | HU-10-01 RN-6; RG-6 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1: ítem 6 (L77-83). paso2 LoginScreen.tsx:120-123 setRetryAfter(seconds>0 ? seconds : 0) ⇒ botón no se deshabilita (disabled = submitting \|\| retryAfter>0, L138/219). grep RATE_LIMITED en mobile/tests: 0 matches. spec/11 README RG-6 paridad; HU-10-01 RN-6 deshabilita el reintento durante la espera. R3: RG-* de README de épica cuenta SPEC. R2: MAYOR. Destino: paso3 FALLBACK_RETRY_AFTER_SECONDS=60; tests RATE_LIMITED en login-screen.test.tsx ⇒ RESUELTO. |
| 7 | COMPLETITUD | MENOR | NINGUNA |  | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1: ítem 7 (L85-91). paso2 login-screen.test.tsx:99-119 segundo fireEvent.press con Pressable disabled (LoginScreen.tsx:219 submitting); la guarda L85 `if (submitting \|\| retryAfter>0) return` no se invoca. R3: el punto no cita RN/AT/HU/spec/ ⇒ ancla NINGUNA. R2: MENOR (calidad de test; el AT de no duplicar envío sí se observa vía disabled). Destino: paso3 añade pressBypassingDisabled() que ejercita la guarda ⇒ RESUELTO. |
| 8 | OPERABILIDAD | MENOR | EJECUCION |  | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1: ítem 8 (L93-99). paso2 tests/setup.ts importa @testing-library/react-native sin configure(); no hay asyncUtilTimeout (default 1000 ms). Cita fallos bajo carga en deposit-address.test.tsx:76 y otros. R3: ancla EJECUCION (corrida con expo export en paralelo). La ausencia de timeout es estática. R2: MENOR. Destino: paso3 configure({ asyncUtilTimeout: 10000 }) ⇒ RESUELTO. |
| 9 | COMPLETITUD | MENOR | SPEC | AT-11-01-12; HU-11-01 RN-12; HU-09-03; HU-09-04 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1: ítem 9 (L101-109). No hay cliente WS en mobile/src (handleUnauthenticated SessionProvider.tsx:181 sólo se exporta; callers en tests). README §24 L864 lista AT-11-01-12 como cubierto; describe en session-provider.test.tsx:229. RN-12 handshake con token no está implementado (backend sin HU-09-03/04). R2: no falta la HU entera; el accionable es trazabilidad honesta ⇒ MENOR. Destino: paso3 README §18/§24 marca AT-11-01-12 NO cubierto, bloqueado por épica 09 ⇒ RESUELTO. |
| 10 | CORRECCION | MAYOR | SPEC | HU-09-01 RN-10; HU-11-06 RN-2 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | R1: ítem 10 agrupa parseo laxo + network/chainId ignorados; mayor severidad (L111-118). paso2 deposits.ts:29-31 address sólo string no vacío; :36-37 parsean network/chainId; DepositScreen.tsx:149-150 imprime CHAIN_ID/NETWORK_NAME de config.ts:21. HU-09-01 RN-10: 0x+40 hex checksum EIP-55; HU-11-06 RN-2 indicar la red correcta. R2: MAYOR. Destino: paso3 isValidEip55Address en la frontera; pantalla usa chainId/network del backend y corta si chainId ≠ 11155111 ⇒ RESUELTO. |

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
