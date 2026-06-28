# HU-11-03 — Formulario de orden en mobile (limit / market)

- **Epica:** 11 — Cliente Mobile (React Native / Expo)
- **Actor / rol:** Trader autenticado
- **Prioridad:** Alta
- **Dependencias:** HU-10-03 (paridad web: formulario de orden), épica 09 (endpoint de alta
  de orden), épica 04 (gestión de órdenes), épica 03 (motor de matching), HU-11-01 (sesión)
- **Estandares de dominio aplicables:** N/A (no on-chain). Convenciones monetarias de
  00-fundaciones (tick/lot/min notional, redondeo, serialización).

## Historia
Como trader autenticado, quiero colocar órdenes **limit** y **market** desde la app mobile
con validaciones claras y feedback inmediato, para operar cómodamente desde el celular sin
enviar órdenes inválidas.

## Contexto y alcance
Cubre el formulario de alta de orden en mobile: selección de `side` (BUY/SELL), `type`
(LIMIT/MARKET), `quantity` (ETH) y `price` (USDC/ETH, sólo LIMIT); validación previa en
cliente (tick, lot, mínimo notional, campos requeridos) para **feedback temprano**; envío al
endpoint de la épica 09 con `clientOrderId` para **idempotencia**; y manejo del resultado
(aceptada / fills / rechazada) cubriendo todos los códigos de error del catálogo. El
contrato es **el mismo que el web** (HU-10-03).

Diferencias mobile: teclado numérico, inputs táctiles, **paso de confirmación**, prevención
de doble submit y feedback (toast/bottom-sheet). La validación y el matching **autoritativos
los hace el backend** (épicas 04/03); la validación en cliente **no** los sustituye: si el
backend rechaza, su error prevalece.

## Reglas de negocio e invariantes
1. **RN-1 (campos y combinaciones):** `side ∈ {BUY, SELL}`, `type ∈ {LIMIT, MARKET}`,
   `quantity` en ETH y, sólo para LIMIT, `price` en USDC/ETH. En MARKET el campo `price`
   está deshabilitado/ausente. LIMIT sin precio ⇒ backend `PRICE_REQUIRED`; MARKET con
   precio ⇒ backend `PRICE_NOT_ALLOWED`; `side`/`type` fuera de enum ⇒ `INVALID_SIDE` /
   `INVALID_ORDER_TYPE`.
2. **RN-2 (conversión a unidad mínima, sin floats):** el cliente convierte la entrada humana
   a entero de unidad mínima con aritmética **decimal exacta** (no IEEE-754): ETH → wei
   (×10¹⁸), precio → `price_min` (×10⁶), y envía como **string entero** (`^(0|[1-9][0-9]*)$`).
   La UI limita decimales: precio ≤ 2 (tick 0.01), cantidad ≤ 4 (lot 0.0001).
3. **RN-3 (validaciones de cliente = feedback temprano):** antes de enviar, el cliente
   verifica con las mismas reglas que el backend, en el **mismo orden determinista** que el
   backend para reglas del par (`00-fundaciones/modelo-de-errores.md` §4, paso 4): primero
   **tick**, luego **lot**, luego **notional** (un único error reportado, el primero):
   1. `price_min > 0` ∧ `price_min mod 10000 == 0` (si no, `INVALID_PRICE_TICK`),
   2. `q_wei > 0` ∧ `q_wei mod 10¹⁴ == 0` (si no, `INVALID_LOT_SIZE`),
   3. para LIMIT: `notional = floor(q_wei × price_min / 10¹⁸) ≥ 10000000` (10 USDC; si no,
      `BELOW_MIN_NOTIONAL`).
   Si varios campos son inválidos a la vez, el cliente muestra **el primero** según este
   orden (espejo del backend). Estas validaciones **no reemplazan** al backend; el error del
   backend es autoritativo.
4. **RN-4 (idempotencia y persistencia por clientOrderId):** el cliente genera un
   `clientOrderId` (UUID v4) cuando el usuario **confirma** el envío y lo **persiste**
   (SecureStore o almacenamiento local) junto al *order intent* (`side`, `type`, `quantity`,
   `price`) y al estado `pendiente` **antes** de enviar el request. Definición operativa de
   **"mismo intento"**: el `clientOrderId` se **mantiene** para reintentos **automáticos**
   mientras la petición no tenga respuesta (error de red/timeout) y se **descarta** (junto al
   registro persistido) cuando: (a) el backend devuelve **cualquier** respuesta definitiva
   (éxito o error de negocio); (b) el usuario **cancela** explícitamente; (c) el formulario
   se cierra y se reabre. Si al abrir la app existe un *order intent* `pendiente` persistido
   (la app fue terminada por el SO entre el envío y la respuesta), el cliente **reutiliza el
   mismo `clientOrderId`** para consultar/reintentar de forma segura y luego limpia el
   registro. Si el backend responde `DUPLICATE_CLIENT_ORDER_ID` (409), la UI lo trata como
   "ya enviada" (no duplica la orden ni lo presenta como fallo duro) y limpia el registro.
5. **RN-5 (precedencia de errores la fija el backend):** orden determinista auth → esquema →
   enums/combinaciones → reglas del par → idempotencia → fondos → matching. La UI muestra el
   **único** error devuelto, con mensaje coherente al `code`.
6. **RN-6 (códigos a manejar):** `VALIDATION_ERROR`, `INVALID_SIDE`, `INVALID_ORDER_TYPE`,
   `PRICE_REQUIRED`, `PRICE_NOT_ALLOWED`, `INVALID_PRICE_TICK`, `INVALID_LOT_SIZE`,
   `BELOW_MIN_NOTIONAL`, `DUPLICATE_CLIENT_ORDER_ID`, `INSUFFICIENT_FUNDS`,
   `SELF_TRADE_BLOCKED`, `MARKET_NO_LIQUIDITY`, `UNAUTHENTICATED`, `RATE_LIMITED`.
7. **RN-7 (resultado exitoso):** la UI refleja el estado devuelto (`OPEN`,
   `PARTIALLY_FILLED`, `FILLED`) y, si hubo fills, muestra cantidad/precio/notional
   formateados sin floats. Da feedback (toast/sheet) y deja el formulario en un estado
   consistente.
8. **RN-8 (market):** una orden MARKET no lleva precio; si no hay liquidez del lado opuesto
   ⇒ `MARKET_NO_LIQUIDITY`. El cliente puede mostrar un notional **estimado** con el best
   price visible, pero el real surge del/los fills devueltos.
9. **RN-9 (fondos insuficientes):** ante `INSUFFICIENT_FUNDS`, la UI muestra `asset`,
   `required` y `available` de `details` (strings enteros) formateados a humano.
10. **RN-10 (confirmación y anti doble-submit):** se requiere confirmación explícita antes
    de enviar; mientras hay un request en vuelo el botón de envío se deshabilita. Un reintento
    tras error usa el mismo `clientOrderId` (RN-4) para no duplicar.
11. **RN-11 (self-trade):** si la orden cruzaría contra una orden propia, el backend responde
    `SELF_TRADE_BLOCKED` (422) y la UI lo informa sin aplicar la orden.
12. **RN-12 (sesión):** ante `UNAUTHENTICATED` (401) al enviar, se limpia la sesión y se
    redirige al login (consistente con HU-11-01, flujo singleton RG-8).
13. **RN-13 (rate limiting):** ante `RATE_LIMITED` (429) con `details.retryAfterSeconds`
    (`00-fundaciones/modelo-de-errores.md` §3.1), la UI informa el límite de tasa y muestra
    el tiempo de espera sugerido en segundos; el formulario **permanece editable** (no se
    descarta la orden) y el reintento **reusa el mismo `clientOrderId`** (RN-4) — no se
    genera uno nuevo.
14. **RN-14 (fallo de red):** si el envío de la orden no obtiene respuesta del backend (fallo
    de red/timeout), la UI muestra un error de **conectividad** (distinto de los errores de
    negocio), el estado local de la orden **no** cambia y se permite reintentar reusando el
    **mismo `clientOrderId`** (RN-4), evitando duplicados.

## Criterios de aceptación (DoD)

### Escenario 1: Alta LIMIT válida que queda en el libro [AT-11-03-01]
- Dado un trader autenticado con fondos suficientes
- Cuando envía una orden LIMIT BUY de `q_wei = 5000000000000000` (0.005 ETH) a
  `price_min = 2000000000` (2000.00), confirmando el envío
- Entonces el backend la acepta y la UI muestra estado `OPEN`
- Y los montos se muestran formateados sin floats

### Escenario 2: Alta LIMIT que cruza y se ejecuta [AT-11-03-02]
- Dado liquidez disponible del lado opuesto
- Cuando el trader envía una orden LIMIT que cruza el spread
- Entonces la UI muestra el estado devuelto (`FILLED` o `PARTIALLY_FILLED`)
- Y muestra los fills (cantidad/precio/notional) formateados sin floats

### Escenario 3: Alta MARKET con liquidez [AT-11-03-03]
- Dado un trader autenticado y un orderbook con liquidez del lado opuesto
- Cuando envía una orden MARKET SELL (sin precio) y confirma
- Entonces el backend la ejecuta contra los mejores precios y la UI refleja los fills
- Y no se envía ningún campo `price`

### Escenario 4 (borde): Precio fuera de tick [AT-11-03-04]
- Dado el formulario LIMIT
- Cuando el usuario ingresa un precio con 3 decimales (p. ej. 2000.005 ⇒
  `price_min = 2000005000`, `mod 10000 ≠ 0`)
- Entonces el cliente bloquea el envío con feedback de tick inválido
- Y si igualmente llega al backend, éste responde `INVALID_PRICE_TICK` y la UI lo muestra

### Escenario 5 (borde): Cantidad fuera de lot [AT-11-03-05]
- Dado el formulario
- Cuando el usuario ingresa una cantidad de 5 decimales (0.00005 ETH ⇒ `q_wei = 50000000000000`,
  `mod 10¹⁴ ≠ 0`)
- Entonces el cliente bloquea el envío con feedback de lot inválido
- Y el backend, de recibirla, responde `INVALID_LOT_SIZE`

### Escenario 6 (borde): Por debajo del mínimo notional [AT-11-03-06]
- Dado una orden LIMIT con `q_wei = 100000000000000` (0.0001 ETH) y `price_min = 2000000000`
  (notional = 200000 USDC-min = 0.2 USDC < 10 USDC)
- Cuando el usuario intenta enviarla
- Entonces el cliente la marca por debajo del mínimo notional
- Y el backend responde `BELOW_MIN_NOTIONAL` si llega a recibirla

### Escenario 7 (error): LIMIT sin precio [AT-11-03-07]
- Dado `type = LIMIT` sin precio
- Cuando se intenta enviar
- Entonces el backend responde `PRICE_REQUIRED` (422) y la UI lo informa

### Escenario 8 (error): MARKET con precio [AT-11-03-08]
- Dado `type = MARKET` con un precio especificado
- Cuando se envía
- Entonces el backend responde `PRICE_NOT_ALLOWED` (422) y la UI lo informa

### Escenario 9 (error): Fondos insuficientes [AT-11-03-09]
- Dado un trader sin disponible suficiente para la orden
- Cuando envía la orden
- Entonces el backend responde `INSUFFICIENT_FUNDS` (422) con `details {asset, required,
  available}`
- Y la UI muestra esos montos formateados a humano

### Escenario 10 (error): Market sin liquidez [AT-11-03-10]
- Dado un orderbook con el lado opuesto vacío
- Cuando el trader envía una orden MARKET
- Entonces el backend responde `MARKET_NO_LIQUIDITY` (422) y la UI lo informa

### Escenario 11 (idempotencia): Reintento con el mismo clientOrderId [AT-11-03-11]
- Dado un alta que ya fue aceptada por el backend con un `clientOrderId` dado
- Cuando el cliente reintenta el envío con el **mismo** `clientOrderId`
- Entonces el backend responde `DUPLICATE_CLIENT_ORDER_ID` (409)
- Y la UI lo trata como "ya enviada" sin crear una segunda orden

### Escenario 12 (concurrencia): Doble tap en enviar [AT-11-03-12]
- Dado el formulario completo
- Cuando el usuario toca "Enviar" dos veces rápidamente
- Entonces se realiza un único request (botón deshabilitado durante el request en vuelo)
- Y no se crean dos órdenes

### Escenario 13 (error): Self-trade bloqueado [AT-11-03-13]
- Dado una orden propia descansando en el libro
- Cuando el trader envía una orden que cruzaría contra esa orden propia
- Entonces el backend responde `SELF_TRADE_BLOCKED` (422) con `details {restingOrderId}`
- Y la UI lo informa y no aplica la orden

### Escenario 14 (borde): Conversión exacta sin floats [AT-11-03-14]
- Dado entrada humana cantidad `0.0001` y precio `2000.50`
- Cuando el cliente convierte a unidad mínima
- Entonces envía `quantityWei = "100000000000000"` y `priceMin = "2000500000"` como strings
- Y la conversión no usa floats binarios

### Escenario 15 (error): Token expirado al enviar [AT-11-03-15]
- Dado un trader cuyo token expiró
- Cuando envía una orden y el backend responde `UNAUTHENTICATED` (401)
- Entonces la app limpia la sesión y redirige al login (consistente con HU-11-01)

### Escenario 16 (error): Límite de tasa (RATE_LIMITED) [AT-11-03-16]
- Dado un trader que envía requests a una tasa que supera el límite
- Cuando el backend responde `RATE_LIMITED` (429) con `details {retryAfterSeconds}`
- Entonces la UI muestra un mensaje de límite de tasa con el tiempo de espera sugerido
- Y el formulario permanece editable (no se descarta la orden)
- Y un reintento reusa el **mismo** `clientOrderId` (no se genera uno nuevo)

### Escenario 17 (error): Fallo de red al enviar la orden [AT-11-03-17]
- Dado un trader que envía una orden sin conectividad o con el backend caído
- Cuando la petición de alta falla por red (no hay respuesta del backend)
- Entonces la UI muestra un error de conectividad (distinto de los errores de negocio)
- Y el estado local de la orden no cambia
- Y se permite reintentar reusando el **mismo** `clientOrderId` (sin duplicar)

### Escenario 18 (recuperación): Crash entre envío y respuesta [AT-11-03-18]
- Dado un *order intent* con `clientOrderId` persistido en estado `pendiente` antes del envío
- Cuando el SO termina la app (memory pressure/kill) después de enviar pero antes de recibir
  respuesta, y el usuario reabre la app
- Entonces el cliente detecta el registro `pendiente` y consulta/reintenta con el **mismo**
  `clientOrderId`
- Y si la orden ya había sido aceptada, el backend responde `DUPLICATE_CLIENT_ORDER_ID`
  (409) y la UI lo trata como "ya enviada", luego limpia el registro

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-*) pasan
- [ ] Reglas de negocio RN-1..RN-14 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md (incl.
      `RATE_LIMITED` 429 con `retryAfterSeconds`, AT-11-03-16)
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md
- [ ] Invariantes globales: el cliente **refleja** los estados/fondos que el backend
      garantiza; INV-1, INV-4, INV-7 e INV-8 (y demás) son responsabilidad del backend — el
      cliente no los garantiza (00-fundaciones/invariantes-globales.md)
- [ ] (si aplica) Adherencia verificada al estandar on-chain citado
