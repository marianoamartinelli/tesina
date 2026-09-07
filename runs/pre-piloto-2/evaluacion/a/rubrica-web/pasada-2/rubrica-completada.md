celda: celda-en-evaluacion
pasada: 2
fecha: 2026-09-07

### Procedimiento de datos de prueba (regla 3.1)

- `POST /api/v1/auth/register` para `eval-web@test.local`, `contraparte@test.local` y `vacio-web@test.local` respondió 409 `EMAIL_ALREADY_EXISTS` (cuentas ya presentes en el backend de la celda). Login con password `EvalWeb123!` → 200 para las tres. Perfil evaluador: accountId `78b3a0bb-809a-42f2-868f-7ba79edf86f1`.
- Fondeo de balances del exchange: `GET /api/v1/balances` → 404 `NOT_FOUND` (épica 02 fuera de alcance del SUT). `entorno/fondear.py` no corre en este workspace (`ModuleNotFoundError: helpers`). Se fondeó on-chain vía `EVAL_RPC_URL` (anvil, cuenta 0 desbloqueada) a las direcciones de depósito (`GET /api/v1/deposit-address`): evaluador `0x3e82bCa885b5fAe2Dd2881c072C83035b8A9E225` (20 ETH, 100000 USDC-mock) y contraparte `0x97eAB5c9946d817C56f8C802fA3e71FC737f28f2` (10 ETH, 100000 USDC-mock); `anvil_mine` 12 bloques. La acreditación en el libro del exchange no existe (épica 07 no implementada). Las filas de HU-10-01 no dependen de esos fondos.
- Automatización: Playwright MCP (navegar, snapshot, click/type, `page.route` para demorar = throttling, abortar = offline, adulterar payload = proxy). Reinicio del SUT no se usó (`SUITE_CMD_REINICIO_SUT=docker restart sut-2a`).

# Rúbrica manual — Épica 10: Cliente Web (React) — v1.2

- **Cobertura:** 78 AT (HU-10-01: 11 · HU-10-02: 11 · HU-10-03: 19 · HU-10-04: 10 ·
  HU-10-05: 11 · HU-10-06: 16) + 1 escenario de integración (`AT-10-E2E-01`, del README de
  la épica, **fuera del conteo de 78** y reportado por separado).
- **Estado:** pre-registrada en H5, antes de la primera corrida (protocolo §9: la suite/
  rúbrica no se modifica después de vista ninguna implementación). **v1.1 (2026-09-06,
  ADR-024 y ADR-025):** re-pre-registrada dentro de la ventana H6 tras el ensayo sobre la
  corrida pre-piloto (descartable), antes de cualquier corrida oficial. Tres cambios, sin
  tocar ningún criterio de veredicto: AT-10-01-06 deja de tener la salida `NO_EVALUABLE`
  (a) porque el rate limit de `/auth/*` es obligatorio desde `spec-v1.2`; AT-10-01-07 fija
  qué request cuenta cuando el cliente no tiene otra pantalla con datos; y un navegador
  automatizado entra a las herramientas permitidas.
- **Rol:** las épicas 10 y 11 se evalúan con rúbrica manual (no black-box automatizado).
  Esta rúbrica es el instrumento único para la épica 10.

## Precondiciones

1. **Backend de la corrida corriendo** (la implementación generada en esa celda, épicas
   01–09), accesible desde el navegador del evaluador. Si el backend no arranca, **todos**
   los AT de esta rúbrica se marcan `NO_EVALUABLE` con una única nota global.
2. **Cliente web de la corrida** compilado y servido (si no compila ni renderiza login,
   todos los AT se marcan `FALLA` con nota global: el artefacto evaluado es el cliente).
3. **Datos de prueba (seed):**
   - Usuario evaluador: `eval-web@test.local` / password conocida, con fondos iniciales
     **10 ETH** y **100000 USDC** (o el mecanismo de fondeo que la implementación provea).
   - Usuario contraparte: `contraparte@test.local`, con fondos equivalentes, operado desde
     una **segunda sesión** (otra ventana/perfil de navegador o llamadas directas a la API
     del backend) para generar liquidez, trades y carreras.
   - Cuenta virgen: `vacio-web@test.local`, sin fondos ni órdenes (para estados vacíos).
4. **Herramientas permitidas** (y ninguna otra):
   - DevTools del navegador: pestañas Network (inspección de payloads, *request blocking*,
     *throttling*, *offline*), Application (storage) y Console; o un **navegador
     automatizado** (p. ej. Playwright) usado con esas mismas capacidades —inspeccionar
     requests, demorarlas, abortarlas o adulterar su payload equivale a Network, throttling,
     offline y proxy—. Se anota en la fila cuándo se usó automatización.
   - Detener/levantar el backend y el nodo RPC (si el entorno de la corrida lo usa) para
     provocar fallos de red y de broadcast.
   - Un proxy interceptor local (p. ej. mitmproxy) para **adulterar datos del servidor**
     cuando un AT exige datos inconsistentes o respuestas que el backend sano no produce
     (se anota en la fila cuando se usó).
   - Un script auxiliar contra la **API pública del backend** para seed masivo (p. ej.
     generar >50 trades). Esto no expone el holdout: no ejecuta la suite de ATs.
5. La suite black-box de las épicas 01–09 **no** se corre durante esta rúbrica (protocolo
   §4, no-exposición del holdout durante la corrida; esta rúbrica se completa en H8, al
   cierre).

## Procedimiento general

- La rúbrica se completa **en H8** (evaluación al cierre) por el **agente evaluador
  tercero** (ADR-026; v1.2 — hasta v1.1, el tesista), en **dos pasadas independientes más
  un arbitraje por agente**, idéntico en las 4 corridas oficiales y la piloto, recorriendo
  las filas **en el orden de este documento** (HU-10-01 → HU-10-06, AT ascendente; el E2E al
  final). No se re-evalúa ni se corrige la implementación después.
- Cada fila se resuelve con **exactamente un** veredicto:
  - **PASA** — todo lo listado en la celda "Verificación" se observó.
  - **FALLA** — la condición se pudo provocar y al menos una verificación no se cumple.
  - **NO_EVALUABLE** — la condición no pudo provocarse, por alguna de estas dos causas
    (indicar cuál en la nota): **(a)** el comportamiento del **backend** del que depende el
    AT no existe o falla (p. ej. no hay canal WebSocket, el endpoint no responde): ese
    defecto ya lo captura la suite black-box de las épicas 01–09 y **no se penaliza dos
    veces**; **(b)** la condición no es provocable con las herramientas permitidas (p. ej.
    inyección WS sin proxy viable, reorg no reproducible en el entorno de la corrida).
- **Nota obligatoria** en toda fila `FALLA` (qué se observó) y `NO_EVALUABLE` (causa a/b y
  dependencia concreta). En `PASA` la nota es opcional.
- **Agregación pre-registrada:** tasa de la épica = `PASA / (PASA + FALLA)`. Los
  `NO_EVALUABLE` se excluyen del denominador y se reportan como conteo aparte en
  `runs/<id>/metricas.md`, discriminados por causa (a/b).
- Verificaciones de **payload** ("el cliente envía X"): se comprueban en DevTools → Network
  sobre el request real. Verificaciones de "no usa floats": sólo por su **resultado
  observable** (valores exactos en pantalla/payload); la inspección de código es evidencia
  complementaria, no sustituye la observación.
- Tiempo máximo por fila: **10 minutos** de intento de provocación; superado, se marca
  `NO_EVALUABLE` causa (b) con nota.

---

## HU-10-01 — Pantalla de login

| AT | Verificación manual (preparar → ejecutar → verificar) | Resultado | Notas |
|----|-------------------------------------------------------|-----------|-------|
| AT-10-01-01 | Sin sesión activa, completar credenciales correctas del usuario evaluador y presionar "Ingresar". Verificar: se llama al endpoint de autenticación (Network); al 200 navega a la vista de trading; el valor del token no aparece en la URL ni en el DOM (buscar el token literal con el inspector). | PASA | Sin sesión. POST http://127.0.0.1:3201/api/v1/auth/login 200, body {email:"eval-web@test.local",password:"EvalWeb123!"} → {token:"R4NCR5gxXgnoZlFwYlpklgPkLHdujk2WO_-0UJOuO-M", expiresAt:"2026-09-07T16:11:52.368Z"}. Navegó a /trading (heading ETH/USDC, perfil eval-web@test.local, accountId 78b3a0bb-809a-42f2-868f-7ba79edf86f1). Token en localStorage exchange.web.session.v1; tokenInUrl=false, tokenInDom=false. evidencia/AT-10-01-01-1.png |
| AT-10-01-02a | Enviar un email inexistente + password cualquiera; el backend responde `INVALID_CREDENTIALS` (401). Verificar: mensaje genérico "Email o contraseña incorrectos" (o equivalente que no revele si el email existe), el campo password se limpia, permanece en login. | PASA | POST /api/v1/auth/login email no-existe@test.local → 401 {error:{code:"INVALID_CREDENTIALS",message:"Credenciales inválidas."}}. UI: "Email o contraseña incorrectos"; #password=""; permanece en /login. evidencia/AT-10-01-02a-1.png |
| AT-10-01-02b | Enviar el email del usuario evaluador + password incorrecta (401 `INVALID_CREDENTIALS`). Verificar: **el mismo** mensaje genérico que AT-10-01-02a (comparación textual), password se limpia, permanece en login. | PASA | POST /api/v1/auth/login email eval-web@test.local + password incorrecta → 401 {error:{code:"INVALID_CREDENTIALS"}}. UI el mismo texto que 02a: "Email o contraseña incorrectos"; #password=""; permanece en /login. evidencia/AT-10-01-02b-1.png |
| AT-10-01-03 | Dejar vacío `email` (y luego `password`). Verificar: botón "Ingresar" deshabilitado en ambos casos y **ninguna** llamada a la API (Network limpio). | PASA | Ambos vacíos: botón Ingresar disabled. Solo email: disabled. Solo password: disabled. Network sin requests /api/ ni /auth/. evidencia/AT-10-01-03-1.png, AT-10-01-03-2.png, AT-10-01-03-3.png |
| AT-10-01-04 | Con throttling de red lento (DevTools), presionar "Ingresar" y volver a presionar antes de la respuesta. Verificar: una sola request en Network; el botón muestra estado de carga hasta resolver. | PASA | Throttling: page.route demoró POST /api/v1/auth/login 2 s. Doble click en el mismo tick + segundo click Playwright: una sola request POST /auth/login 200. Durante el vuelo botón "Ingresando…" disabled aria-busy=true. evidencia/AT-10-01-04-1.png |
| AT-10-01-05 | Provocar `VALIDATION_ERROR` (422) real: enviar un email con formato inválido que **pase** la validación local (si el cliente bloquea todo formato inválido, adulterar el payload con el proxy). Verificar: mensajes por campo derivados de `details.issues`; no navega fuera de login. Si no es provocable → NO_EVALUABLE (b). | PASA | Email "no-es-un-email" pasa validación local; backend 401 INVALID_CREDENTIALS (HU-01-02 RN-11, no 422). Proxy (page.route, adulterar payload): POST body {email:12345,password:"CualquierPass1"} → 422 {error:{code:"VALIDATION_ERROR",details:{issues:[{field:"email",message:"El campo \"email\" debe ser un string."}]}}}. UI: mensaje por campo idéntico + "Revisá los datos ingresados."; permanece en /login. evidencia/AT-10-01-05-1.png |
| AT-10-01-06 | Repetir logins fallidos hasta que el backend responda `RATE_LIMITED` (429) con `details.retryAfterSeconds` (60 intentos fallidos desde el mismo origen en 60 s, HU-01-02 RN-9; el script auxiliar contra la API sirve para acumularlos). Verificar: botón deshabilitado, informa el tiempo de espera, y al transcurrir el lapso el botón se rehabilita. Si el backend no responde 429, la fila es FALLA del backend ya capturada por la suite (AT-01-02-09) → NO_EVALUABLE (a) sólo en ese caso. | PASA | Script auxiliar: 60 POST /api/v1/auth/login fallidos (401 INVALID_CREDENTIALS) + 1 desde el cliente. POST /auth/login 429 {error:{code:"RATE_LIMITED",details:{retryAfterSeconds:46}}} header Retry-After:46. UI: botón Ingresar disabled, "Demasiados intentos. Esperá 45 segundos e intentá de nuevo." Tras el lapso: botón habilitado, "Ya podés reintentar." evidencia/AT-10-01-06-1.png, AT-10-01-06-2.png |
| AT-10-01-07 | Con sesión activa en otra pantalla, invalidar el token del lado servidor (reiniciar backend o revocar sesión) y disparar una llamada protegida (navegar/refrescar datos; si el cliente no emite otro request protegido que el chequeo de sesión `GET /me`, ese es el camino que se evalúa). Verificar: al 401 `UNAUTHENTICATED` limpia la sesión local (Application → storage) y redirige a login con aviso de sesión expirada. | PASA | Sesión activa en /trading (heading ETH/USDC, "Cargando perfil…"). Throttling: page.route demoró GET /api/v1/me 4 s; se revocó con POST /api/v1/auth/logout 204. GET /me Authorization Bearer … → 401 {error:{code:"UNAUTHENTICATED",message:"Credencial ausente, inválida o expirada."}}. localStorage vacío; redirige a /login con aviso "Tu sesión expiró, ingresá nuevamente". evidencia/AT-10-01-07-2.png |
| AT-10-01-08 | Apagar el backend (o DevTools → Offline) y enviar credenciales válidas. Verificar: mensaje no técnico ("No se pudo conectar, reintentá" o equivalente), opción de reintentar conservando el email, sin stack traces ni detalles internos. | PASA | Offline: page.route.abort("internetdisconnected") sobre POST /api/v1/auth/login → net::ERR_INTERNET_DISCONNECTED. UI: "No se pudo conectar, reintentá"; botón Reintentar; email conservado eval-web@test.local; HTML sin stack traces ni TransportError ni ERR_INTERNET. Reintentar dispara un segundo POST FAILED y conserva el email. evidencia/AT-10-01-08-1.png |
| AT-10-01-09 | Con token persistido vigente (login previo), navegar manualmente a la ruta de login. Verificar: se ejecuta `GET /me` con `Authorization: Bearer` (Network) y al 200 redirige automáticamente a trading sin pedir credenciales. | PASA | Token persistido vigente. goto /login → GET http://127.0.0.1:3201/api/v1/me 200, header Authorization: Bearer R4NCR5gxXgnoZlFwYlpklgPkLHdujk2WO_-0UJOuO-M. Redirige a /trading (ETH/USDC, eval-web@test.local) sin pedir credenciales; no hay POST /auth/login en esa navegación. evidencia/AT-10-01-09-1.png |
| AT-10-01-10 | Corromper el token persistido (Application → storage: reemplazar por un valor inválido no expirado) y recargar en la ruta de login. Verificar: `GET /me` responde 401, el cliente limpia todo estado de sesión (incluido el token persistido) y muestra el formulario de login. | PASA | localStorage exchange.web.session.v1={token:"token-invalido-no-expirado-AT-10-01-10-xyz",expiresAt:"2026-09-07T16:18:14.848Z"} (no expirado). Recarga /login: GET /api/v1/me Authorization Bearer token-invalido-no-expirado-AT-10-01-10-xyz → 401 {error:{code:"UNAUTHENTICATED"}}. Storage vacío; formulario de login visible; no navega a /trading. evidencia/AT-10-01-10-1.png |

## HU-10-02 — Vista de trading

Seed previo del bloque: con la contraparte, poblar el libro con ≥3 niveles por lado
(p. ej. bids 2000.00/1999.50/1999.00; asks 2000.50/2001.00/2001.50) y generar ≥3 trades.

| AT | Verificación manual (preparar → ejecutar → verificar) | Resultado | Notas |
|----|-------------------------------------------------------|-----------|-------|
| AT-10-02-01 | Abrir la vista de trading con el libro seedeado. Verificar: bids ordenados por precio **descendente**, asks **ascendente**, lista de trades con el más reciente primero, y best bid/ask coinciden con la primera fila de cada lado. | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-02-02 | Con la vista abierta, desde la contraparte agregar/modificar/cancelar un nivel. Verificar: el libro refleja el cambio sin recargar, mantiene el ordenamiento y recalcula top of book y spread. | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-02-03 | Generar ≥50 trades (script contra la API con la contraparte) y, con la lista llena, generar uno más. Verificar: se inserta como primer elemento y la lista mantiene **exactamente 50** filas (contar en el DOM), descartando el más antiguo. | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-02-04 | Dejar `best_bid = 2000.00` y `best_ask = 2000.50`. Verificar: spread mostrado exactamente `0.50` USDC (resta entera 500000 USDC-min desplazada), sin residuos de float. | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-02-05 | Cancelar todas las órdenes de venta (lado ask vacío). Verificar: el lado ask se muestra vacío (sin filas inventadas) y el spread como "—". | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-02-06 | Seedear un nivel con cantidad `1.5` ETH y otro con `0.1` ETH. Verificar: se muestran exactamente `1.5` y `0.1` (ni `1.4999…8` ni `0.1000…5` ni otra aproximación). | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-02-07 | Con el proxy, inyectar un update WS que deje `best_ask < best_bid` (libro cruzado). Verificar: el cliente NO aplica el update, muestra "desactualizado" y solicita snapshot fresco (Network) antes de volver a "en vivo". Sin proxy viable → NO_EVALUABLE (b). | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-02-08 | Con el proxy, tras un update con `sequence = s`, inyectar uno con `sequence = s+2` (gap) y luego uno con `sequence ≤ s`. Verificar: el gap no se aplica y fuerza snapshot + reconstrucción; el duplicado se descarta sin aplicarse. Sin proxy → NO_EVALUABLE (b). | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-02-09 | Con la vista en vivo, matar la conexión WS (apagar backend o bloquear la URL del WS). Verificar: indicador "desactualizado" y reintentos; al restaurar, resuscribe, pide snapshot fresco (Network) y recién entonces vuelve a "en vivo". | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-02-10 | Bloquear la URL REST del snapshot (DevTools → request blocking) y abrir la vista. Verificar: mensaje de error no técnico con opción de reintentar; NO se muestra un orderbook vacío como si fuera el estado real. | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-02-11 | Generar (contraparte) un trade a `2000.00`, luego uno a `2000.50`, luego uno a `2000.00`. Verificar: el header muestra `lastPrice` 2000.50 con indicador **verde** tras el segundo, **rojo** al tercero; el primer elemento de la lista coincide con el `lastPrice` del header. | NO_EVALUABLE | (b) fuera del alcance de la corrida |

## HU-10-03 — Formulario de orden

| AT | Verificación manual (preparar → ejecutar → verificar) | Resultado | Notas |
|----|-------------------------------------------------------|-----------|-------|
| AT-10-03-01 | Con fondos suficientes, colocar LIMIT BUY precio `2000.50`, cantidad `1` ETH. Verificar payload (Network): `priceMin="2000500000"`, `quantityWei="1000000000000000000"`, `side="BUY"`, `type="LIMIT"` y un `clientOrderId`; al 201 muestra la orden con su estado (`OPEN`/`PARTIALLY_FILLED`/`FILLED`). | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-03-02 | Colocar MARKET SELL cantidad `0.5` ETH. Verificar: campo precio oculto/deshabilitado; payload con `quantityWei="500000000000000000"`, `type="MARKET"`, `side="SELL"`, `clientOrderId` y **sin** precio; muestra el resultado de ejecución de la API. | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-03-03 | Ingresar precio `2000.50` y cantidad `1.5` y enviar. Verificar en el payload la conversión exacta: `priceMin="2000500000"` y `quantityWei="1500000000000000000"` (sin desvíos de redondeo binario). | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-03-04 | Con top-of-book donde LIMIT BUY 1 ETH @2000.50 quedaría en libro (best_ask > 2000.50). Verificar: notional estimado exactamente `2000.50` USDC; fee maker estimada exactamente `0.001` ETH (`1000000000000000` wei); subiendo el precio hasta cruzar, la fee pasa a exactamente `0.002` ETH (taker). | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-03-05 | Ingresar precio `2000.005` (3 decimales). Verificar: submit bloqueado con error equivalente a `INVALID_PRICE_TICK` y **ninguna** llamada a la API. | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-03-06 | Ingresar cantidad `0.00005` ETH. Verificar: submit bloqueado con error equivalente a `INVALID_LOT_SIZE`, sin llamada a la API. | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-03-07 | Ingresar LIMIT `0.0001` ETH @`2000.00` (notional 0.20 USDC). Verificar: submit bloqueado con error equivalente a `BELOW_MIN_NOTIONAL`, sin llamada a la API. | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-03-08a | En LIMIT, dejar el precio vacío e intentar enviar. Verificar: el cliente lo impide (campo requerido, submit bloqueado), sin llamada a la API; y en MARKET el campo precio está oculto/deshabilitado y no viaja en el payload. | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-03-08b | Con el proxy, adulterar el payload para que una LIMIT llegue **sin precio** al backend (bypass de la validación cliente); el backend responde `PRICE_REQUIRED` (422). Verificar: el cliente muestra el error mapeado por `code` y no navega fuera del formulario. Sin proxy → NO_EVALUABLE (b). | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-03-08c | Igual que 08b pero MARKET **con** precio en el payload; backend responde `PRICE_NOT_ALLOWED` (422). Verificar: error mapeado por `code`, sin salir del formulario. Sin proxy → NO_EVALUABLE (b). | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-03-09 | Colocar una orden cuyo requerido exceda el disponible; backend responde `INSUFFICIENT_FUNDS` (422). Verificar: mensaje de saldo insuficiente mostrando `required` y `available` formateados desde strings; los balances de la UI no cambian. | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-03-10 | Dejar una orden propia en libro y colocar (misma cuenta) la orden que cruzaría contra ella; backend responde `SELF_TRADE_BLOCKED` (422). Verificar: informa que cruzaría contra una orden propia y no se ejecuta. | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-03-11 | Vaciar el lado opuesto y enviar una MARKET; backend responde `MARKET_NO_LIQUIDITY` (422). Verificar: informa la falta de liquidez. | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-03-12 | Enviar un alta y cortar la respuesta (proxy retiene la respuesta u Offline inmediato); reintentar el mismo envío. Verificar (Network): ambos requests llevan el **mismo** `clientOrderId`; ante `DUPLICATE_CLIENT_ORDER_ID` (409) el cliente consulta `GET /orders?clientOrderId=<id>` y muestra **una única** orden con el estado recuperado. No provocable → NO_EVALUABLE (b). | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-03-13 | Con throttling, doble clic en "Colocar orden". Verificar: una sola request; el botón queda deshabilitado hasta resolver. | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-03-14 | Con `best_ask = 2001.00` y `best_bid = 2000.00`: LIMIT BUY @2001.00 → fee estimada **taker** (20 bps); cambiar a @1999.00 → fee estimada **maker** (10 bps); vaciar el lado ask → estimación **taker** (cota conservadora). Verificar las tres transiciones en la UI. | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-03-15 | En MARKET SELL 0.5 ETH, completar cantidad. Verificar: el notional estimado se oculta o se rotula "no disponible" y el cliente NO bloquea el envío por `BELOW_MIN_NOTIONAL` (esa validación queda en el backend). | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-03-16 | Cargar a la vez precio `2000.005` (tick inválido) y cantidad `0.00005` (lot inválido) e intentar enviar. Verificar: submit bloqueado y se muestra **primero** el error de precio (`INVALID_PRICE_TICK`), sin llamada a la API. | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-03-17 | Seedear asks: `0.5 ETH @2000.00` y `1 ETH @2001.00`. En MARKET BUY 1 ETH, verificar: notional estimado exactamente `2000.50` USDC rotulado "estimado"; con cantidad mayor a la liquidez visible, indica ejecución parcial o slippage desconocido. | NO_EVALUABLE | (b) fuera del alcance de la corrida |

## HU-10-04 — Órdenes abiertas e historial

| AT | Verificación manual (preparar → ejecutar → verificar) | Resultado | Notas |
|----|-------------------------------------------------------|-----------|-------|
| AT-10-04-01 | Seed: una orden `OPEN` (t1) y luego otra que la contraparte llena parcialmente (`PARTIALLY_FILLED`, t2). Abrir "órdenes abiertas". Verificar: sólo esas dos, con columnas de RN-2 (incl. `avgExecutionPrice`), orden por creación descendente (t2 primero), remanente = cantidad − ejecutada, montos sin residuos de float, y la `OPEN` con `avgExecutionPrice = "--"`. | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-04-02 | Con la vista abierta y una orden `OPEN` visible, generar un fill parcial desde la contraparte. Verificar: la fila pasa a `PARTIALLY_FILLED`, actualiza ejecutada/remanente/`avgExecutionPrice` sin recargar, y permanece en abiertas. | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-04-03 | Completar esa orden desde la contraparte (fill total). Verificar: desaparece de abiertas y aparece en historial como `FILLED` con `avgExecutionPrice` poblado. | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-04-04 | Cancelar una orden `OPEN` propia desde la UI (respuesta exitosa). Verificar: pasa a `CANCELLED`, se mueve a historial y el botón "Cancelar" ya no aparece para ella. (Balances se verifican en HU-10-05/E2E, no acá.) | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-04-05 | Carrera: con una orden `OPEN` visible, **bloquear el WS** (request blocking) para congelar la vista; llenarla por completo desde la contraparte; presionar "Cancelar". El backend responde `ORDER_NOT_CANCELLABLE` (409) con el estado real. Verificar: informa que ya no es cancelable, muestra el estado real y refresca la fila sin reintentar solo. | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-04-06 | Con el proxy, reescribir el `orderId` de una cancelación por uno inexistente; backend responde `ORDER_NOT_FOUND` (404) (misma respuesta para ajenas). Verificar: informa el error y refresca el listado; ninguna orden ajena se altera. Sin proxy → NO_EVALUABLE (b). | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-04-07 | Con throttling, doble clic en "Cancelar" de la misma orden. Verificar: una sola request; botón deshabilitado hasta resolver. | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-04-08 | Seed: más órdenes terminadas que una página (generar por script). Verificar: "cargar más" (o equivalente) pide la página siguiente con el parámetro de continuación devuelto por la API y la agrega; cuando la API no devuelve continuación, el control se deshabilita/indica fin. | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-04-09 | Con la cuenta virgen, abrir el historial. Verificar: estado vacío explícito (sin filas), no un error. | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-04-10 | Provocar una orden `REJECTED` persistida: enviar MARKET con el lado opuesto vacío (`MARKET_NO_LIQUIDITY`). Abrir historial. Verificar: aparece `REJECTED` con ejecutada = 0, remanente = cantidad, `avgExecutionPrice = "--"`, motivo si la API lo provee, y sin botón "Cancelar". | NO_EVALUABLE | (b) fuera del alcance de la corrida |

## HU-10-05 — Balances

| AT | Verificación manual (preparar → ejecutar → verificar) | Resultado | Notas |
|----|-------------------------------------------------------|-----------|-------|
| AT-10-05-01 | Abrir la vista de balances con fondos seedeados. Verificar: ETH y USDC con disponible/bloqueado/total, formateados exactos (ETH 18 dec, USDC 6 dec). | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-05-02 | Llevar USDC a `disponible = 5` y `bloqueado = 10` (colocando una orden que bloquee 10 USDC). Verificar: total mostrado exactamente `15` USDC y, si la API envía `total`, coincide con la suma. | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-05-03 | Con la vista abierta y USDC `disponible=20 / bloqueado=0`, colocar (otra pestaña, misma cuenta) una orden que bloquee 10 USDC. Verificar: sin recargar, `disponible=10`, `bloqueado=10`, total constante `20`. | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-05-04 | Partiendo de USDC `bloqueado=2000.50 / disponible=0` y ETH `disponible=0`, ejecutar como **taker** la compra de 1 ETH @2000.50 (contraparte con la orden en libro). Verificar al llegar el update: USDC `bloqueado=0` y ETH `disponible` exactamente `0.998` ETH (`998000000000000000` wei = 1 ETH − fee taker 20 bps), con INV-2/INV-3 intactos. | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-05-05 | Acreditar un depósito (según el entorno de la corrida: enviar tx a la dirección de depósito y alcanzar 12 confirmaciones; en nodo local, minar bloques). Verificar: con la vista abierta, el disponible del activo sube por el monto acreditado y el total lo refleja. Entorno on-chain no operable → NO_EVALUABLE (a/b según el caso). | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-05-06 | Con la cuenta virgen (o un activo en 0), abrir balances. Verificar: el activo se muestra con `0` en disponible, bloqueado y total (no se oculta). | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-05-07a | Con el proxy, inyectar un update WS con `disponible = "-1"` en ETH. Verificar: el cliente lo descarta (no muestra negativos, tampoco lo "corrige" a 0) y solicita snapshot fresco. Sin proxy → NO_EVALUABLE (b). | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-05-07b | Con el proxy, inyectar `disponible="5000000"`, `bloqueado="10000000"`, `total="14999999"`. Verificar: descarta el dato inconsistente (no rompe INV-3) y resincroniza con snapshot. Sin proxy → NO_EVALUABLE (b). | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-05-08 | Matar el WS de balances. Verificar: indicador "desactualizado", reintentos (backoff), y al reconectar pide snapshot fresco antes de volver a "en vivo". | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-05-09 | Con USDC `disponible=50 / bloqueado=0`, solicitar un retiro de 25 USDC. Verificar: sin refrescar, `disponible=25`, `bloqueado=25`, total constante `50`. | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-05-10 | Bloquear el GET del snapshot de balances y abrir la vista. Verificar: mensaje de error con opción de reintentar; NO se muestran los activos en `0` como si fueran reales. | NO_EVALUABLE | (b) fuera del alcance de la corrida |

## HU-10-06 — Depósitos y retiros

| AT | Verificación manual (preparar → ejecutar → verificar) | Resultado | Notas |
|----|-------------------------------------------------------|-----------|-------|
| AT-10-06-01 | Abrir la sección de depósitos. Verificar: dirección `0x` + 40 hex con checksum **EIP-55 válido** (recomputar con una herramienta externa, p. ej. `ethers.getAddress`), botón copiar funcional, y advertencia de red Sepolia (chainId 11155111) y de que sólo se aceptan ETH/USDC-mock. | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-06-02 | Provocar un depósito con pocas confirmaciones (según entorno). Verificar: se muestra `PENDIENTE n/12` (progreso por polling REST) y, al llegar a 12 y acreditarse, pasa a `ACREDITADO` y el balance sube (HU-10-05). Entorno no operable → NO_EVALUABLE. | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-06-03 | Con un depósito `ACREDITADO` listado, esperar ≥2 ciclos de polling y refrescar la vista. Verificar: sigue apareciendo **una sola vez** (misma identidad `(txHash, logIndex)`), sin re-sumar el monto; si el backend reporta `DEPOSIT_ALREADY_CREDITED` (409), los balances de la UI no cambian. | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-06-04 | Retiro USDC: dirección destino EIP-55 válida, monto `25`. Verificar payload: `amountMinUnit="25000000"` + `clientWithdrawalId`; la UI muestra el ciclo `PENDING` → `BROADCAST (n/12)` → `CONFIRMED` con etiquetas legibles y el `txHash` enlazado a un explorer de Sepolia cuando la API lo expone. | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-06-05 | Ingresar una dirección `0x`+40 hex con el checksum EIP-55 alterado (una letra con caso cambiado). Verificar: el cliente bloquea el envío anticipando `INVALID_ADDRESS` (y si se fuerza al backend por proxy, responde 422 `INVALID_ADDRESS`). | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-06-06 | Ingresar monto `0` (y luego un USDC con 7 decimales). Verificar: bloqueo anticipando `WITHDRAWAL_AMOUNT_INVALID`; nunca viaja un monto que no matchee `^(0\|[1-9][0-9]*)$`. | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-06-07 | Retiro USDC de `0.5` (< mínimo 1 USDC). Verificar: el cliente lo anticipa como `WITHDRAWAL_BELOW_MIN` mostrando el mínimo; si llega al backend, muestra el mínimo formateado desde `details.minWithdrawal` (1 USDC). | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-06-08 | Retiro por un monto mayor al disponible; backend responde `INSUFFICIENT_FUNDS` (422). Verificar: muestra el faltante (`required`/`available` formateados) y los balances de la UI no cambian. | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-06-09 | Provocar broadcast definitivamente fallido: solicitar un retiro válido (202) con el **nodo RPC apagado** hasta agotar reintentos del backend. Verificar: el cliente observa `FAILED` con `failureReason` (canal `withdrawals` o GET), informa la causa, el disponible se restaura (balances) y ofrece **crear un retiro nuevo** con `clientWithdrawalId` distinto (sin botón de "reintentar el mismo"). No provocable → NO_EVALUABLE. | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-06-10 | Si es posible apuntar el backend a una red distinta de Sepolia (o inyectar la respuesta): ante `CHAIN_ID_MISMATCH` (422) verificar que informa que sólo se opera en Sepolia (11155111) y que no ofrece cambiar de red. No provocable → NO_EVALUABLE. | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-06-11 | Con throttling, doble clic en "Retirar". Verificar: una sola request (un solo retiro creado); botón deshabilitado hasta resolver. | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-06-12 | Retiro ETH: destino EIP-55 válido, monto humano `0.1`. Verificar payload `amountMinUnit="100000000000000000"` + `clientWithdrawalId`, y el mismo ciclo `PENDING` → `BROADCAST (n/12)` → `CONFIRMED` que para USDC. | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-06-13 | Con un retiro en `BROADCAST`, provocar su fallo (tx revertida / descartada / timeout de inclusión, según entorno). Verificar: la UI muestra `FAILED` con causa clara, el disponible se restaura y se ofrece crear un retiro **nuevo** con `clientWithdrawalId` distinto (la UI no queda colgada en `BROADCAST`). No provocable → NO_EVALUABLE. | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-06-14 | Provocar conflicto de nonce (enviar desde la hot wallet una tx externa con el nonce en uso, si el entorno lo permite). Verificar: no llega ningún error HTTP al cliente; éste sólo observa el estado (`PENDING`/`BROADCAST`, o `FAILED` con `failureReason`); ante `FAILED` no reintenta automáticamente y ofrece retiro nuevo. No provocable → NO_EVALUABLE. | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-06-15 | Enviar un retiro y cortar la respuesta (proxy retiene / Offline); reintentar el mismo retiro. Verificar (Network): mismo `clientWithdrawalId` en ambos; ante `CONFLICT` (409) no se crea un segundo retiro y se muestra el estado del ya registrado (recuperado por `clientWithdrawalId` o del listado). No provocable → NO_EVALUABLE (b). | NO_EVALUABLE | (b) fuera del alcance de la corrida |
| AT-10-06-16 | Con un depósito `PENDIENTE n/12` visible, provocar una reorg/reversión en el nodo local (p. ej. anvil snapshot/revert) para que el re-poll lo devuelva `DESCARTADO` con `discardReason` `REORG`/`REVERTED`. Verificar: se muestra descartado con su `(txHash, logIndex)` y la causa; el disponible **no cambia** y no se dispara resincronización por inconsistencia. No provocable → NO_EVALUABLE. | NO_EVALUABLE | (b) fuera del alcance de la corrida |

## Escenario de integración (fuera del conteo de 78; se reporta por separado)

| AT | Verificación manual (preparar → ejecutar → verificar) | Resultado | Notas |
|----|-------------------------------------------------------|-----------|-------|
| AT-10-E2E-01 | Ciclo completo con el usuario evaluador: (1) login → llega a trading; (2) orderbook y trades en vivo visibles; (3) colocar LIMIT BUY válida con `clientOrderId` que quede `OPEN`; (4) aparece en abiertas; (5) balances: USDC disponible↓ / bloqueado↑ / total constante; (6) cancelar → `CANCELLED` en historial; (7) balances: bloqueado↓ / disponible↑; (8) solicitar retiro USDC válido → bloqueo reflejado y ciclo `PENDING`→`BROADCAST`→`CONFIRMED`; (9) invalidar el token y disparar una llamada protegida → limpia sesión y vuelve a login. Verificar cada eslabón en orden; FALLA si cualquiera se rompe (anotar cuál). | NO_EVALUABLE | (b) fuera del alcance de la corrida |
