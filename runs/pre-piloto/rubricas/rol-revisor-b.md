# Ensayo de la rúbrica `rol-revisor.md` v1.0 sobre `pre-piloto-b`

**Esto no es el veredicto del tesista.** Es un **ensayo del instrumento** sobre una corrida
descartable (ADR-018), hecho por Claude en la sesión del 2026-09-06 para cerrar el componente
8.3 de `runs/pre-piloto/matriz-componentes.md`: verificar que la rúbrica se puede aplicar con la
evidencia que deja el orquestador y registrar dónde no fija lo suficiente. **No entra en ningún
dataset.** El veredicto de registro de las celdas oficiales lo emite el tesista en H8.

- Artefactos: `.pipeline/revision-{backend,web,mobile}.md` del repo satélite congelado
  (`6fb74cd`). Puntos: **3 + 2 + 6 = 11**.
- Estado del repo por paso: snapshots `paso1-implementador` / `paso2-revisor` /
  `paso3-implementador` de `pre-piloto-b/logs/*-snapshots/` (sin `node_modules`: no se ejecutó
  nada desde ellos; ver hallazgo I-4).
- JSONL de cada etapa: `runs/pre-piloto/logs/pre-piloto-b-<etapa>-*.jsonl`, paso `orden: 2`.
- Tiempo de pared del ensayo: **22:52 → 22:57 (5 min)** para 11 puntos y 36 veredictos, con
  el material ya localizado en la sesión (no incluye leer la rúbrica ni ubicar los snapshots).

Abreviaturas en `evidencia`: `p2` = snapshot al cierre del revisor; `p3` = snapshot al cierre
del pase correctivo; `J` = JSONL de la etapa, paso 2.

## Parte A — Censo de puntos

### `revision-backend.md`

| punto | eje | severidad | ancla | referencias | ubicacion | accionable | veracidad | destino | evidencia |
|---|---|---|---|---|---|---|---|---|---|
| 1 | CORRECCION | MAYOR | SPEC | HU-06-02 RN-8; AT-06-02-08 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | Punto: «reintenta incrementando únicamente `address_index`… recalcula el mismo prefijo hasta agotar 2^31 índices». p2 `src/crypto/wallet.ts:156-158` deriva los 5 componentes con `deriveChild`, que lanza `InvalidDerivedKeyError` en cualquier componente (`:80-82`); `:177-183` sólo incrementa `index` del address. Repro citado, confirmado en J: `timeout 2s node … i===44+HARDENED_OFFSET … deriveNextValidAddress(seed,0,h)` → `exit=124`. RN-8 dice «si en algún paso `I_L ≥ n`… se avanza al siguiente índice». p3: `deriveNextValidChild` por componente (`wallet.ts:109-131`), `deriveAddress` itera `components` (`:216-223`), `test/wallet.test.ts` modificado. |
| 2 | CORRECCION | MAYOR | SPEC | Épica 01 RNE-9; HU-01-02 RN-8; HU-01-02 RN-9 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | Punto: «rechaza logins durante parsing/esquema antes de llegar a la única escritura de auditoría… JSON malformado ya rate-limited responde desde el error handler sin ejecutar `auditRateLimited`». p2 `src/app.ts:195` valida antes de `authService.login` (`:196`), único lugar que audita (`auth-service.ts:86,96`); `auditRateLimited` sólo en `preValidation` (`app.ts:166`) y el error handler (`:113-119`) responde 429 sin auditar. Verificación citada, confirmada en J: `app.inject … payload:{email:'victim@example.com'}` → `{"status":422,…,"auditCount":0}`. RNE-9: «Todo intento de autenticación (login exitoso o fallido)… se registran». p3: hook `onResponse` audita todo desenlace de `/api/v1/auth/login` (`app.ts:164-173`), `auth-service.ts` pasa a `auditLoginAttempt`, nuevo `test/login-audit.test.ts`. |
| 3 | CORRECCION | MAYOR | SPEC | 00-fundaciones/modelo-de-errores.md §3.2; HU-09-05 RN-4; HU-09-05 RN-10 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | Punto: «construye `NOT_FOUND` sin `details`». p2 `src/app.ts:144` `new ApiError("NOT_FOUND")`. Catálogo §3.2 fila `NOT_FOUND`: details `{ resource, id }`; RN-4 exige `details` por código. p3 `app.ts:181` `new ApiError("NOT_FOUND", { resource: "route", id: path })`. |

### `revision-web.md`

| punto | eje | severidad | ancla | referencias | ubicacion | accionable | veracidad | destino | evidencia |
|---|---|---|---|---|---|---|---|---|---|
| 1 | CORRECCION | MAYOR | SPEC | HU-10-01 RN-9; HU-10-01 RN-11; AT-10-01-09 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | Punto: «comprueba la sesión solo al montar y no escucha `popstate`… pulsar Atrás deja la URL en `/login` con la pantalla autenticada». p2 `web/src/App.tsx:41-46`: `checkPersistedSession` sólo en el efecto de montaje, sin listener de `popstate`; `session.ts:52-55` emite `popstate`; el render depende de `state`, no de la URL (`App.tsx:53-88`). El escenario de Atrás **no fue ejecutado** por el revisor (J: `build:web`, `test:web`, `npm test`; ningún navegador), se deduce del código. AT-10-01-09 exige redirección a trading al navegar a login con token vigente. Ver hallazgo I-2 sobre RN-11. p3 `App.tsx:44-52` agrega `popstate` → `checkPersistedSession()` cuando `pathname === "/login"`. |
| 2 | CORRECCION | MAYOR | SPEC | HU-10-01 RN-6; AT-10-01-06 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | Punto: «resta uno por cada `setTimeout`». p2 `web/src/LoginPage.tsx:48-50` `setRetrySeconds(current - 1)` por callback, sin deadline. RN-6: «transcurrido ese lapso se rehabilita el botón». p3 `LoginPage.tsx:46-58,95` calcula el restante contra `retryDeadline` y `Date.now()`. |

### `revision-mobile.md`

| punto | eje | severidad | ancla | referencias | ubicacion | accionable | veracidad | destino | evidencia |
|---|---|---|---|---|---|---|---|---|---|
| 1 | CORRECCION | MAYOR | SPEC | HU-11-01 RN-5; HU-11-01 RN-6; AT-11-01-05; AT-11-01-06 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | Punto: «cualquier fallo de `SecureStore.deleteItemAsync` se ignora… el logout explícito espera primero al backend». p2 `AuthContext.tsx:67-70` `catch {}` sobre `sessionStorage.remove()` y marca `guest` en `finally`; `:93-102` `logoutRequest` antes de `handleUnauthenticated`; `restore()` (`:35-47`) reautentica con cualquier token leído. RN-6: «Tras logout no es posible restaurar la sesión». Agrupa 3 problemas del mismo circuito: se cuenta 1, codeado por RN-6 (AT-11-01-06). p3: `session-storage.ts` reescrito (tombstone + reintento con backoff, `:13-41`), `AuthContext.tsx:88-97` borra local **antes** del logout remoto. |
| 2 | CORRECCION | MAYOR | SPEC | HU-11-06 RN-2; AT-11-06-01; AT-11-06-26 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | Punto: «las respuestas no se cancelan ni se validan contra el activo vigente». p2 `DepositScreen.tsx:46-47` `setDeposit(response)` sin id de request ni chequeo del `asset` vigente. RN-2 exige mostrar «el activo» correspondiente. p3 `DepositScreen.tsx:41-63` `latestRequestRef`, descarta respuestas viejas; render `deposit?.asset === asset` (`:139`). |
| 3 | CORRECCION | MAYOR | SPEC | README épica 11 RG-5; HU-11-01 RN-12; AT-11-01-10; AT-11-01-12 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | Punto: «el cierre del socket anterior llama siempre a `scheduleReconnect()`». p2 `usePrivateSocket.ts:99-103`: `onclose` ejecuta `scheduleReconnect()` aunque `current !== socket`; `connect()` (`:56`) no comprueba si ya hay socket. Secuencia enunciada (background→foreground→`onclose` viejo) no ejecutada por el revisor; se sigue del código. RG-5 fija reconexión con backoff; RN-12/AT-11-01-12 tratan la autenticación de la reconexión, no el duplicado (ver I-2). p3 `usePrivateSocket.ts:57` `|| socket` en `connect`, `:100-101` ignora cierres de sockets viejos. |
| 4 | CORRECCION | MAYOR | SPEC | README épica 11 RG-6; HU-10-01 RN-6; AT-10-01-06 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | Punto: «el `finally` de las líneas 60-63 rehabilita inmediatamente el botón, cuyo `disabled`… sólo depende de `submitting`». p2 `LoginScreen.tsx:60-63` y `:111` exactamente eso. RN-6 vía RG-6 (paridad). p3 `LoginScreen.tsx:31-48` `rateLimitedUntil` con deadline; `:146` `disabled={submitting \|\| rateLimitedUntil !== null}`. |
| 5 | OPERABILIDAD | MENOR | EJECUCION | — | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | Punto: «`mobile/app.json:8` declara `newArchEnabled`… `npx --yes expo-doctor@latest` falla… (20/21 checks)». p2 `mobile/app.json:8` `"newArchEnabled": true`. J: `npx --yes expo-doctor@latest` exit 1, salida «20/21 checks passed. 1 checks failed… should NOT have additional property 'newArchEnabled'». No cita id de spec; «condición operativa de la etapa» → EJECUCION, MENOR (el export de la etapa había pasado: J `npm run export:mobile` exit 0). p3 `app.json` sin la línea; J paso 3: `expo-doctor` «21/21 checks passed». |
| 6 | CORRECCION | MAYOR | SPEC | README épica 11 RG-6; HU-10-01 RN-4 | ARCHIVO_LINEA | SI | VERDADERO | RESUELTO | Punto: «sólo ejecuta `setPassword("")` tras éxito y no en la rama de credenciales inválidas». p2 `LoginScreen.tsx:45-49`: `setPassword("")` en `:46` (éxito); rama `INVALID_CREDENTIALS` (`:48-49`) no limpia. RN-4: «la contraseña se limpia». p3 `LoginScreen.tsx:72` `setPassword("")` en esa rama. |

## Parte B — Criterios por artefacto

### `backend`

| Criterio | Resultado | Notas |
|---|---|---|
| RV-01 | PASA | existe, 3 puntos |
| RV-02 | PASA | filecmp p1→p2: única diferencia `.pipeline/` (nuevo) |
| RV-03 | PASA | J: un solo `file_change` (`/repo/.pipeline/revision-backend.md`, `kind: add`); ningún `command_execution` que escriba en `.pipeline/` |
| RV-04 | PASA | J: `npm run build` (0), `npm test` (0), `npm start` en `/tmp/backend-review.*` + `curl …/health` (0), `app.inject` con `node -e` |
| RV-05 | PASA | 0 puntos con `ancla = NINGUNA` |
| RV-06 | PASA | 0 puntos con `ubicacion = NINGUNA` |
| RV-07 | PASA | MAYOR, MAYOR, MAYOR: sin inversiones (ver I-1: la escala Alta/Media/Baja del revisor colapsa a un solo bucket) |
| RV-08 | PASA | 0 puntos con `eje = OTRO` |
| RV-09 | PASA | 0 puntos con `accionable = NO` |
| RV-10 | PASA | sin encabezados, sin bloques de código, sin resumen ni conclusiones (grep: 0 fences, 0 `#`) |
| RV-11 | PASA | 0 `FALSO`, 0 `NO_VERIFICABLE` (los dos puntos con verificación ejecutada se apoyan en la salida registrada en J, no en re-ejecución: ver I-4) |
| RV-12 | PASA | 0 `NO_RESUELTO` (3 `RESUELTO`) |

### `web`

| Criterio | Resultado | Notas |
|---|---|---|
| RV-01 | PASA | existe, 2 puntos |
| RV-02 | PASA | filecmp p1→p2: única diferencia `.pipeline/revision-web.md` |
| RV-03 | PASA | J: un solo `file_change` (`add`) |
| RV-04 | PASA | J: `npm run build:web` (0), `npm run test:web` (0), `npm test` (0), arranque del backend con `npm run build && … npm start` |
| RV-05 | PASA | — |
| RV-06 | PASA | — |
| RV-07 | PASA | MAYOR, MAYOR |
| RV-08 | PASA | — |
| RV-09 | PASA | — |
| RV-10 | PASA | 0 fences, 0 encabezados |
| RV-11 | PASA | 0 `FALSO`; punto 1 verificado por lectura del código, no por ejecución del escenario de navegación (I-3) |
| RV-12 | PASA | 2 `RESUELTO` |

### `mobile`

| Criterio | Resultado | Notas |
|---|---|---|
| RV-01 | PASA | existe, 6 puntos |
| RV-02 | PASA | filecmp p1→p2: única diferencia `.pipeline/revision-mobile.md` |
| RV-03 | PASA | J: un solo `file_change` (`add`) |
| RV-04 | PASA | J: `npm run build`, `typecheck:mobile`, `test:mobile`, `npm test`, `export:mobile` (todos 0), `expo-doctor` (1) |
| RV-05 | PASA | — |
| RV-06 | PASA | — |
| RV-07 | **FALLA** | 1 inversión: punto 5 (MENOR) precede al punto 6 (MAYOR). El revisor ordenó Alta, Alta, Media, Media, Media, Baja —consistente con su escala—; la inversión la produce el mapeo de la rúbrica (I-1) |
| RV-08 | PASA | punto 5 codeado OPERABILIDAD, no OTRO (I-5) |
| RV-09 | PASA | — |
| RV-10 | PASA | 0 fences, 0 encabezados |
| RV-11 | PASA | 0 `FALSO`; puntos 1 y 3 enuncian secuencias no ejecutadas por el revisor, verificadas por lectura (I-3) |
| RV-12 | PASA | 6 `RESUELTO` |

## Agregación pre-registrada

| artefacto | PASA | FALLA | NO_EVALUABLE | PASA/(PASA+FALLA) |
|---|---|---|---|---|
| backend | 12 | 0 | 0 | 1,00 |
| web | 12 | 0 | 0 | 1,00 |
| mobile | 11 | 1 | 0 | 0,92 |
| **celda** | **35** | **1** | **0** | **0,97** |

Censo (11 puntos): `eje` CORRECCION 10/11, OPERABILIDAD 1/11; `severidad` MAYOR 10/11, MENOR
1/11, BLOQUEANTE 0; `ancla` SPEC 10/11, EJECUCION 1/11; `ubicacion` ARCHIVO_LINEA 11/11;
`accionable` SI 11/11; `veracidad` VERDADERO 11/11; `destino` RESUELTO 11/11.

## Hallazgos sobre el instrumento

- **I-1 — La severidad de la rúbrica no discrimina lo que el revisor discrimina.** El revisor
  usa Alta/Media/Baja y ordena por esa escala; la rúbrica manda codear por sus tres buckets, y
  como casi todo punto cita un `AT-*` o una `RN-*`, **10 de 11 caen en MAYOR**. Efectos: (a)
  `RV-07` mide el orden según una escala que el revisor no usó — en `mobile` da FALLA por un
  punto que el revisor puso último por ser «Baja» pero que cita una RN, precedido por uno sin
  id de spec; (b) la distribución de `severidad` del censo deja de ser informativa. Lo dispara
  `revision-mobile.md` puntos 5 y 6. La rúbrica lo declara como limitación («puede no coincidir
  con la noción de severidad del propio revisor»), pero con esta implementación el efecto no es
  marginal: es la regla. Decisión tomada acá: aplicar la rúbrica tal cual.
- **I-2 — `veracidad` mezcla dos preguntas: si el hecho sobre el código es cierto y si la
  lectura de la spec es correcta.** `FALSO` incluye «la referencia… no dice lo que el punto
  afirma». En `web` punto 1, el hecho (no hay listener de `popstate`) es cierto, pero RN-11
  dice que en una navegación SPA el cliente «igualmente puede confiar en [el token] hasta
  recibir un `UNAUTHENTICATED`», o sea que la revalidación con `GET /me` que el punto exige no
  está mandada por RN-11 (sí lo está la redirección a trading de AT-10-01-09). En `mobile`
  punto 3, RN-12/AT-11-01-12 tratan la autenticación de la reconexión, no el socket duplicado;
  la única referencia que aplica es RG-5. Decisión tomada acá: `VERDADERO` cuando el hecho
  sobre el código es cierto y **al menos una** de las referencias lo sostiene, y anotar el
  resto en `evidencia`. La rúbrica debería fijar si una referencia que no aplica, junto a otra
  que sí, vuelve el punto `FALSO`.
- **I-3 — «Comportamiento que verificaste que falla» contra «comportamiento deducido del
  código».** El prompt del rol admite las dos cosas; la rúbrica codea `EJECUCION` sólo si el
  punto «afirma haber ejecutado algo y reporta el resultado observado», y `veracidad` se
  verifica «contra el estado del repo». Tres puntos (`web` 1, `mobile` 1 y 3) enuncian una
  secuencia de UI/red como hecho («pulsar Atrás deja…», «un cold start vuelve a autenticar»,
  «agenda un tercer socket») sin haberla ejecutado —J no registra navegador ni emulador— y son
  verificables sólo por lectura. Decisión tomada acá: `VERDADERO` por lectura, dicho en
  `evidencia`. La rúbrica no distingue ese caso de una verificación ejecutada, y es la
  diferencia que el prompt del rol pide («verificá los hallazgos antes de incorporarlos»).
- **I-4 — La precondición 2 se cumple a medias: el snapshot recupera el estado, no un
  entorno ejecutable.** `nucleo.snapshot_paso` excluye `node_modules`, `dist` y `build`, así
  que la precondición 5 («copia descartable… para ejecutar lo que haga falta») no se puede
  satisfacer desde el snapshot sin reinstalar dependencias. En este ensayo, los dos puntos con
  verificación ejecutada (`backend` 1 y 2) se verificaron con la **salida registrada en el
  JSONL de la propia sesión del revisor**, que la rúbrica sólo admite como evidencia
  secundaria de `RV-02..04`, no de `veracidad`. Decidir antes de H8: o el evaluador
  reinstala en la copia (tiempo por punto contra el tope de 10 min), o se admite el JSONL como
  evidencia de `veracidad` para afirmaciones de ejecución.
- **I-5 — `eje` sin regla para lo operativo que no está en el README del SUT.** El punto 5 de
  `mobile` (esquema de `app.json` inválido para el SDK, `expo-doctor` falla, pero el export
  pasa) no es completitud, corrección ni invariante; OPERABILIDAD se define como «¿arranca y se
  configura como el README dice?», y esto no lo dice el README. Decisión tomada acá:
  OPERABILIDAD (no OTRO), porque afecta la configuración del artefacto. Es el único punto sin
  referencia a la spec, y a la vez el único que el revisor **sí** ejecutó y citó con salida.
- **I-6 — Unidad de punto: los puntos agrupan.** `mobile` punto 1 enuncia tres problemas
  (fallo de borrado ignorado, orden remoto→local del logout, restauración optimista) y el
  pase correctivo los atacó con dos cambios distintos (`session-storage.ts` y `AuthContext.tsx`).
  La regla «se cuenta uno y se codea por el de mayor severidad» está fijada y se aplicó; lo
  que no está fijado es `destino` cuando el pase corrige **parte** de un punto agrupado. Acá
  no ocurrió (los tres cambiaron), pero es previsible.
- **I-7 — `RESUELTO` no está definido.** Se interpretó como «el pase correctivo cambió lo
  señalado en el sentido que el punto pide» (diff p2→p3 leído), **no** como «la spec ahora se
  cumple»: eso último exigiría ejecutar tests que el snapshot no permite correr (I-4). La
  rúbrica debería decir cuál de las dos es, porque `RV-12` («el circuito cierra») cambia de
  sentido según la lectura.
- **I-8 — RV-03 y RV-04 son evaluables del lado B, con una salvedad.** El JSONL de
  `codex exec --json` distingue `file_change` (`kind: add/update`) y `command_execution` con
  `exit_code`, así que la precondición 3 («NO VERIFICADO» para B) queda verificada en la
  granularidad que estos dos criterios piden. La salvedad: un comando de shell que escriba el
  archivo (`cat > .pipeline/…`) no aparece como `file_change`; hay que grepear también los
  `command_execution`. En las tres etapas de B no hubo ninguno.
- **I-9 — Ningún `NO_EVALUABLE`, ningún `NO_VERIFICABLE`, ningún tope de 10 minutos
  alcanzado.** Con 11 puntos localizados por archivo:línea y el JSONL a mano, el instrumento
  corre completo en ~5 minutos de escritura (más la lectura previa del material, no medida). El costo por celda oficial escala con los puntos, y los
  artefactos de A tienen otra forma (secciones `##` con prosa, no lista): la regla «prosa
  fuera de la lista no es un punto» no está probada contra ese formato en este ensayo.
