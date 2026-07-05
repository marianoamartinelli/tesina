# HU-09-01 — Contrato REST de la API

- **Epica:** 09 — API HTTP/WebSocket
- **Actor / rol:** Trader autenticado / Cliente web/mobile / Sistema (servidor de API)
- **Prioridad:** Alta
- **Dependencias:** HU-09-02 (autenticación/autorización), HU-09-05 (modelo de errores),
  HU-01-* (auth/cuentas), HU-02-* (balances), HU-03-* (orderbook/trades),
  HU-04-* (órdenes), HU-05-* (fees), HU-06-* (dirección de depósito),
  HU-07-* (depósitos), HU-08-* (retiros)
- **Estándares de dominio aplicables:** N/A directo (referencia EIP-55 para direcciones de
  retiro, validada en 08; serialización monetaria de `00-fundaciones`)

## Historia
Como cliente web/mobile del exchange, quiero un **contrato REST** preciso y estable
(recursos, métodos, payloads y status codes) para auth, órdenes, balances, depósitos,
retiros y mercado, para poder integrar la aplicación contra el backend sin ambigüedad y de
forma testeable.

## Contexto y alcance
Esta HU define la **superficie REST**: la lista de endpoints, sus verbos HTTP, el esquema
de request y response, y los status codes de éxito. Las **reglas de negocio** de cada
recurso viven en su épica de dominio (se referencian). **No** define la UX (épicas 10/11)
ni la mecánica interna del matching/settlement. Todos los montos se serializan como string
de entero en unidad mínima (`00-fundaciones/convenciones-monetarias.md` §5). El detalle de
errores está en HU-09-05; aquí solo se citan los códigos relevantes.

Supuestos: ruta base `/api/v1`; `Content-Type: application/json; charset=utf-8` en
requests con cuerpo y en responses con cuerpo; símbolo único del par `ETH-USDC`;
autenticación por token Bearer (HU-09-02).

### Mapa de endpoints (contrato)

| Recurso            | Método | Ruta                                   | Auth | Éxito | Épica |
|--------------------|--------|----------------------------------------|------|-------|-------|
| Registro           | POST   | `/api/v1/auth/register`                | No   | 201   | 01    |
| Login              | POST   | `/api/v1/auth/login`                   | No   | 200   | 01    |
| Perfil propio      | GET    | `/api/v1/me`                           | Sí   | 200   | 01    |
| Balances           | GET    | `/api/v1/balances`                     | Sí   | 200   | 02    |
| Crear orden        | POST   | `/api/v1/orders`                       | Sí   | 201   | 04    |
| Listar órdenes     | GET    | `/api/v1/orders`                       | Sí   | 200   | 04    |
| Detalle de orden   | GET    | `/api/v1/orders/{orderId}`             | Sí   | 200   | 04    |
| Cancelar orden     | DELETE | `/api/v1/orders/{orderId}`             | Sí   | 200   | 04    |
| Trades propios     | GET    | `/api/v1/trades`                       | Sí   | 200   | 05    |
| Dirección depósito | GET    | `/api/v1/deposit-address?asset=ETH`    | Sí   | 200   | 06    |
| Listar depósitos   | GET    | `/api/v1/deposits`                     | Sí   | 200   | 07    |
| Detalle de depósito| GET    | `/api/v1/deposits/{depositId}`         | Sí   | 200   | 07    |
| Crear retiro       | POST   | `/api/v1/withdrawals`                  | Sí   | 202   | 08    |
| Listar retiros     | GET    | `/api/v1/withdrawals`                  | Sí   | 200   | 08    |
| Detalle de retiro  | GET    | `/api/v1/withdrawals/{withdrawalId}`   | Sí   | 200   | 08    |
| Orderbook          | GET    | `/api/v1/market/orderbook?depth=N`     | No   | 200   | 03    |
| Trades recientes   | GET    | `/api/v1/market/trades`                | No   | 200   | 03    |
| Ticker (top-of-book)| GET   | `/api/v1/market/ticker`                | No   | 200   | 03    |

## Reglas de negocio e invariantes

1. **RN-1 (ruta base y símbolo):** todos los recursos cuelgan de `/api/v1`. El campo
   `symbol`, donde aparezca, es siempre `"ETH-USDC"`.
2. **RN-2 (serialización monetaria):** `priceMin`, `quantityWei`, `filledWei`,
   `amountUsdcMin`, `amountMinUnit`, `available`, `locked`, `total`, `feeWei`, `feeUsdcMin` y
   todo otro campo monetario se serializan como **string** que matchea `^(0|[1-9][0-9]*)$`.
   Nunca número JSON. (`00-fundaciones/convenciones-monetarias.md` §5.)
   - **Fee acumulada de una orden (`feeWei`, `feeUsdcMin`):** una orden cobra fee sobre el
     activo que **recibe** (`00-fundaciones/convenciones-monetarias.md` §3.3): una orden
     `BUY` (recibe ETH) acumula `feeWei` y deja `feeUsdcMin = "0"`; una orden `SELL` (recibe
     USDC) acumula `feeUsdcMin` y deja `feeWei = "0"`. Ambos campos suman las fees de **todos**
     los fills parciales hasta el momento y valen `"0"` si la orden aún no tuvo fills.
3. **RN-3 (Content-Type):** las requests con cuerpo deben enviar
   `Content-Type: application/json`. Un cuerpo que no sea JSON válido produce
   `VALIDATION_ERROR` (422). Un `Content-Type` no soportado puede responder 415 con el mismo
   envelope de error.
4. **RN-4 (alta de orden, request):** body `{ clientOrderId, symbol, side, type, priceMin?,
   quantityWei }`. `side ∈ {BUY, SELL}`, `type ∈ {LIMIT, MARKET}`. `priceMin` es
   **obligatorio** para `LIMIT` y **prohibido** para `MARKET`. La validación sigue la
   precedencia determinista de `00-fundaciones/modelo-de-errores.md` §4 (esquema → enums →
   reglas del par → idempotencia → fondos → matching). El comportamiento detallado es de
   HU-04-*.
5. **RN-5 (alta de orden, response 201):** devuelve el objeto orden:
   `{ orderId, clientOrderId, symbol, side, type, priceMin|null, quantityWei, filledWei,
   feeWei, feeUsdcMin, status, createdAt, updatedAt }`. `priceMin` es `null` para `MARKET`.
   `feeWei`/`feeUsdcMin` (ver RN-2) acumulan la fee cobrada por los fills ocurridos hasta el
   momento; valen `"0"` si la orden aún no tuvo fills.
   `status` ∈ `{OPEN, PARTIALLY_FILLED, FILLED, CANCELLED}` según el resultado inmediato del
   matching. `REJECTED` **nunca** aparece en una respuesta 201: toda orden rechazada (por
   validación de esquema/par o por matching, p. ej. `SELF_TRADE_BLOCKED`,
   `MARKET_NO_LIQUIDITY`, `MARKET_BUDGET_INSUFFICIENT`) devuelve un código de error **4xx**
   (HU-09-05), no 201.
   **Estado terminal de MARKET con fill parcial:** una orden `MARKET` que ejecutó
   **parcialmente** (`filledWei > "0"`) y luego agotó la liquidez del lado opuesto o su
   presupuesto queda en estado terminal `CANCELLED`, con el remanente **descartado** (sin
   remanente en el libro; HU-03-04 RN-9, HU-04-05), y así se devuelve en la respuesta 201.
   `CANCELLED` en una respuesta 201 aplica **únicamente** a ese caso. `PARTIALLY_FILLED` es
   un estado **abierto** y **solo** de órdenes `LIMIT` (el remanente permanece resting); una
   `MARKET` nunca queda `PARTIALLY_FILLED`.
6. **RN-6 (idempotencia):** `clientOrderId` es provisto por el cliente y único por cuenta.
   Reutilizarlo devuelve `DUPLICATE_CLIENT_ORDER_ID` (409). (INV de idempotencia de alta;
   detalle en HU-04-*.)
7. **RN-7 (cancelar orden):** `DELETE /orders/{orderId}` devuelve 200 con el objeto orden
   en estado `CANCELLED`. Si la orden ya es `FILLED`/`CANCELLED`/`REJECTED`,
   `ORDER_NOT_CANCELLABLE` (409). Si no existe o no pertenece a la cuenta,
   `ORDER_NOT_FOUND` (404).
8. **RN-8 (listar órdenes — paginación):** `GET /orders` acepta `status` (filtro opcional
   por estado), `clientOrderId` (filtro opcional: devuelve los items de la cuenta con ese
   `clientOrderId` — 0 o 1 por la unicidad de RN-6; sin nueva ruta), `limit` (default 50,
   máx 200) y `cursor` (paginación por cursor opaco).
   Devuelve `{ items: [orden...], nextCursor: string|null }`. `limit` inválido (no entero
   positivo o > máx) ⇒ `VALIDATION_ERROR` (422).
   **Ordenamiento:** los `items` se devuelven ordenados por `createdAt` **descendente** (más
   reciente primero); a igual `createdAt`, por `orderId` descendente como desempate estable.
   **Estabilidad del cursor:** el cursor refleja el estado del momento en que se emitió la
   primera página; las órdenes creadas **después** de obtener un cursor **no** aparecen al
   paginar con ese cursor. Las páginas consecutivas no se solapan. `nextCursor: null` indica
   que no hay más páginas.
9. **RN-9 (balances):** `GET /balances` devuelve un arreglo por activo:
   `[{ asset: "ETH", available, locked, total }, { asset: "USDC", available, locked,
   total }]`. Se cumple `total == available + locked` (INV-3) y todos ≥ 0 (INV-2), montos
   en unidad mínima del activo.
10. **RN-10 (dirección de depósito):** `GET /deposit-address?asset=ETH|USDC` devuelve
    `{ asset, address }` con la dirección Ethereum (formato `0x`+40 hex, checksum EIP-55)
    asignada a la cuenta (derivada por HU-06-*). `asset` ausente o distinto de `ETH`/`USDC`
    ⇒ `VALIDATION_ERROR` (422). Como el par on-chain es una sola red (Sepolia), la misma
    dirección puede servir para ambos activos según lo defina 06. Cuando `asset=USDC`, la
    respuesta incluye además `tokenAddress`: la dirección del contrato USDC-mock del entorno
    (formato `0x`+40 hex con checksum EIP-55, HU-06-*); es decir,
    `{ asset, address, tokenAddress }`.
11. **RN-11 (crear retiro):** `POST /withdrawals` body
    `{ asset, amountMinUnit, address, clientWithdrawalId? }`. `asset ∈ {ETH, USDC}`.
    **`amountMinUnit`** es un string entero en la **unidad mínima del activo declarado en
    `asset`**: wei si `asset = ETH`, USDC-min si `asset = USDC` (no se usa el nombre
    genérico `amount` para no ocultar la unidad; RG-API-3). `address` es la dirección
    destino externa (checksum EIP-55). `clientWithdrawalId` (opcional) es la **clave de
    idempotencia** del retiro (HU-08-01 RN-2/RN-10): reenviar la **misma** clave con los
    **mismos** parámetros devuelve el retiro ya existente (no crea otro ni vuelve a bloquear
    fondos); la misma clave con parámetros **distintos** ⇒ `CONFLICT` (409).
    Responde **202 Accepted** con
    `{ withdrawalId, asset, amountMinUnit, address, status, createdAt, updatedAt }`
    (`status` inicial `PENDING`; `createdAt`/`updatedAt` string ISO-8601 UTC), porque el
    procesamiento on-chain (firma EIP-155 + broadcast) es asíncrono (HU-08-*). El enum de
    `status` del retiro es `{PENDING, BROADCAST, CONFIRMED, FAILED}` (máquina de estados de
    HU-08-04). Errores posibles: `INVALID_ADDRESS`, `WITHDRAWAL_BELOW_MIN`,
    `WITHDRAWAL_AMOUNT_INVALID`, `INSUFFICIENT_FUNDS`, `CONFLICT`.
12. **RN-12 (mercado — orderbook):** `GET /market/orderbook?depth=N` devuelve
    `{ symbol, sequence, bids: [[priceMin, quantityWei], ...], asks: [[priceMin,
    quantityWei], ...] }`. `bids` ordenados por `priceMin` **descendente**, `asks`
    **ascendente**; agregados por nivel de precio (INV-7). `depth` default 50, máx 200;
    inválido (no entero positivo o > máx) ⇒ `VALIDATION_ERROR` (422).
    **Lados vacíos:** si un lado no tiene órdenes, su array es `[]` (no hay best bid/ask
    definido en ese lado). El libro **nunca** presenta niveles cruzados. Casos: libro vacío
    ⇒ `{ bids: [], asks: [] }`; solo bids ⇒ `{ bids: [...], asks: [] }`; solo asks ⇒
    `{ bids: [], asks: [...] }`. En todos los casos el status es **200**.
13. **RN-13 (mercado — trades):** `GET /market/trades?limit=N` devuelve
    `{ symbol, items: [{ tradeId, priceMin, quantityWei, takerSide, timestamp }, ...] }`
    ordenados del más reciente al más antiguo. `takerSide ∈ {BUY, SELL}`. `limit` default 50,
    máx 200; `limit` inválido (cero, negativo, no entero, o > máx) ⇒ `VALIDATION_ERROR`
    (422). Si no hubo trades, `items` es `[]` con status **200**.
14. **RN-14 (recurso inexistente / método):** una ruta inexistente bajo `/api/v1` devuelve
    `NOT_FOUND` (404) con el envelope de error; un método no permitido sobre una ruta
    existente devuelve `METHOD_NOT_ALLOWED` (405) con el envelope de error y
    `details = { method, allowed }` (`method` es el verbo rechazado; `allowed` la lista de
    verbos soportados por la ruta). (`code` del catálogo de `00-fundaciones`.)
15. **RN-15 (estabilidad del contrato):** los nombres de campo y los `status` de orden son
    estables (parte del criterio de evaluación). Los timestamps se serializan como string
    ISO-8601 UTC. La API **no** acepta más precisión que la unidad mínima en los montos
    (`00-fundaciones/convenciones-monetarias.md` §5).
16. **RN-16 (mercado — ticker / top-of-book):** `GET /market/ticker` (público, sin token)
    devuelve `{ symbol, bestBidPrice, bestAskPrice, lastPrice, lastQuantityWei, timestamp }`.
    `bestBidPrice`/`bestAskPrice` son el mejor precio de cada lado (`priceMin`, USDC-min por
    ETH) o `null` si ese lado del libro está **vacío**. `lastPrice` es el `priceMin` del
    último trade y `lastQuantityWei` su cantidad en wei; ambos son `null` si **no** hubo
    trades aún. `timestamp` es ISO-8601 UTC del último trade (o del instante de la consulta si
    no hubo trades). Cuando ambos lados tienen profundidad, `bestBidPrice < bestAskPrice`
    (INV-7, sin cruce). Todos los montos no nulos son strings que matchean `^(0|[1-9][0-9]*)$`.
17. **RN-17 (listar depósitos):** `GET /deposits` (Auth: Sí) devuelve
    `{ items: [...], nextCursor: string|null }` con paginación por cursor análoga a RN-8
    (`limit` default 50, máx 200; `cursor` opaco; `limit` inválido ⇒ `VALIDATION_ERROR`),
    ordenados por `createdAt` descendente, con filtros opcionales `asset ∈ {ETH, USDC}` y
    `status` (HU-07-03 RN-12). Cada item es
    `{ depositId, txHash, logIndex, asset, amountMinUnit, status, confirmations, required,
    blockNumber, createdAt, updatedAt, creditedAt?, discardReason? }`, con
    `depositId = "<txHash>:<logIndex>"` (HU-07-03 RN-12); `amountMinUnit` como string entero
    en la unidad mínima del activo; `status ∈ {PENDIENTE, ACREDITADO, DESCARTADO}` (enum
    canónico de la épica 07, en español a propósito); `confirmations`, `required` (= 12,
    HU-07-03 RN-8), `logIndex` y `blockNumber` como **enteros JSON** (conteos, no montos;
    convenciones §5); `creditedAt` presente **solo** si `ACREDITADO`;
    `discardReason ∈ {REORG, REVERTED}` **solo** si `DESCARTADO`.
    `GET /deposits/{depositId}` devuelve el mismo objeto item (200) para un depósito de la
    cuenta; errores y precedencia según HU-07-03 RN-11/RN-12. Solo incluye depósitos de la
    cuenta autenticada (HU-09-02 RN-5).
18. **RN-18 (listar retiros):** `GET /withdrawals` (Auth: Sí) devuelve
    `{ items: [...], nextCursor: string|null }` con la misma paginación por cursor de RN-17,
    ordenados por `createdAt` descendente. Cada item es
    `{ withdrawalId, asset, amountMinUnit, address, txHash|null, confirmations, status,
    failureReason, createdAt, updatedAt }`. `status ∈ {PENDING, BROADCAST, CONFIRMED,
    FAILED}` (HU-08-04); `txHash` es `null` mientras el retiro no se broadcasteó;
    `confirmations` es **entero JSON** (conteo, no monto; convenciones §5).
    `failureReason: string|null` es el **código de causa** cuando `status = FAILED` y `null`
    en cualquier otro estado; enum (causas de la máquina de estados de la épica 08,
    HU-08-03/HU-08-04):
    - `BROADCAST_FAILED` — el broadcast falló definitivamente (se agotaron
      `MAX_BROADCAST_RETRIES`, HU-08-03).
    - `TX_DROPPED` — la transacción fue descartada del mempool sin reaparecer, o venció el
      timeout de inclusión (`MAX_BLOCKS_PENDING`, HU-08-04).
    - `TX_REVERTED` — la transacción fue minada pero revertida (receipt `status = 0`; o,
      para USDC, `status = 1` sin el evento `Transfer` esperado — HU-08-04).
    - `USER_CANCELLED` — el usuario canceló el retiro antes del broadcast (épica 08).
    `GET /withdrawals/{withdrawalId}` devuelve el **mismo** objeto item (200) para un retiro
    de la cuenta; un retiro inexistente o de otra cuenta ⇒ `NOT_FOUND` (404) (HU-09-02 RN-7,
    para no filtrar existencia). Solo incluye retiros de la cuenta autenticada.
19. **RN-19 (formato de `clientOrderId`):** `clientOrderId` es un string de **1 a 64**
    caracteres ASCII imprimibles (rango `0x20`–`0x7E`, sin caracteres de control). Un
    `clientOrderId` ausente, vacío, de más de 64 caracteres o con caracteres fuera de rango
    ⇒ `VALIDATION_ERROR` (422), evaluado en el paso de esquema (antes de la idempotencia,
    `00-fundaciones/modelo-de-errores.md` §4). Esta restricción hace reproducible la prueba
    de `DUPLICATE_CLIENT_ORDER_ID` (RN-6).
20. **RN-20 (historial de trades propios):** `GET /trades` (Auth: Sí) devuelve
    `{ items: [...], nextCursor: string|null }` con paginación **cursor-based (keyset)** por
    la `sequence` del trade (HU-05-04 RN-6): la primera página trae los trades más recientes
    (`sequence` descendente); `nextCursor` es el cursor (opaco, derivado de la `sequence`
    del último item devuelto) o `null` si no hay más páginas; `limit` default 50, máx 200
    (`limit` inválido ⇒ `VALIDATION_ERROR`, 422). Filtros opcionales: `from`/`to`
    (timestamps ISO-8601 UTC, RN-15) y `orderId` **propio**; un `orderId` ajeno o
    inexistente devuelve **lista vacía**, nunca 404 (HU-05-04 RN-7). Cada item proyecta la
    **pata propia** del trade (HU-05-04 RN-3/RN-4, sin exponer la contraparte):
    `{ tradeId, sequence, timestamp, symbol, priceMin, quantityWei, quoteAmountMin, side,
    role, feeAsset, feeAmount, netReceived, paid, orderId }`. `symbol` es `"ETH-USDC"`
    (nombre API del par, RN-1); `sequence` es **entero JSON** (conteo, no monto);
    `timestamp` string ISO-8601 UTC; montos como string entero (RN-2);
    `side ∈ {BUY, SELL}`, `role ∈ {MAKER, TAKER}`, `feeAsset ∈ {ETH, USDC}`.

## Criterios de aceptación (DoD)

### Escenario 1: Registro de cuenta [AT-09-01-01]
- Dado un email no registrado y una contraseña válida
- Cuando el cliente hace `POST /api/v1/auth/register` con `{ email, password }` y
  `Content-Type: application/json`
- Entonces la respuesta es **201** con cuerpo `{ accountId, email, createdAt }`
- Y no se expone la contraseña ni hash alguno en la respuesta

### Escenario 2: Login devuelve token [AT-09-01-02]
- Dado una cuenta registrada
- Cuando el cliente hace `POST /api/v1/auth/login` con credenciales correctas
- Entonces la respuesta es **200** con un token de sesión (string) utilizable como
  `Authorization: Bearer <token>` en endpoints protegidos
- Y con credenciales incorrectas responde `INVALID_CREDENTIALS` (401) sin revelar si el
  email existe

### Escenario 3: Perfil propio [AT-09-01-03]
- Dado un token válido
- Cuando el cliente hace `GET /api/v1/me`
- Entonces la respuesta es **200** con `{ accountId, email, createdAt }` de la cuenta dueña
  del token

### Escenario 4: Alta de orden limit (feliz) [AT-09-01-04]
- Dado un token válido y balance suficiente
- Cuando el cliente hace `POST /api/v1/orders` con
  `{ "clientOrderId": "c-1", "symbol": "ETH-USDC", "side": "BUY", "type": "LIMIT",
  "priceMin": "2000500000", "quantityWei": "1000000000000000000" }`
- Entonces la respuesta es **201** con el objeto orden incluyendo `orderId`,
  `status ∈ {OPEN, PARTIALLY_FILLED, FILLED}` (nunca `REJECTED`), `priceMin": "2000500000"`,
  `quantityWei": "1000000000000000000"`, `filledWei`, `feeWei` y `feeUsdcMin` como strings
- Y si la orden quedó `OPEN` sin fills, `filledWei == "0"`, `feeWei == "0"` y
  `feeUsdcMin == "0"`; si tuvo fills, `feeWei` (BUY recibe ETH) acumula la fee y
  `feeUsdcMin == "0"`
- Y todos los montos de la respuesta son strings que matchean `^(0|[1-9][0-9]*)$`

### Escenario 5: Alta de orden market (borde: sin precio) [AT-09-01-05]
- Dado un token válido y liquidez en el lado opuesto
- Cuando el cliente envía `{ clientOrderId, symbol: "ETH-USDC", side: "SELL",
  type: "MARKET", quantityWei: "100000000000000" }` **sin** `priceMin`
- Entonces la respuesta es **201** con el objeto orden y `priceMin: null`
- Y enviar `type: "MARKET"` **con** `priceMin` produce `PRICE_NOT_ALLOWED` (422)
- Y enviar `type: "LIMIT"` **sin** `priceMin` produce `PRICE_REQUIRED` (422)

### Escenario 6: Detalle de orden [AT-09-01-06]
- Dado una orden propia con `orderId` conocido
- Cuando el cliente hace `GET /api/v1/orders/{orderId}`
- Entonces la respuesta es **200** con el objeto orden completo y sus montos como strings

### Escenario 7: Listado de órdenes con paginación [AT-09-01-07]
- Dado una cuenta con más órdenes que el `limit` solicitado
- Cuando el cliente hace `GET /api/v1/orders?status=OPEN&limit=2`
- Entonces la respuesta es **200** con `{ items: [...], nextCursor: "<cursor>" }`,
  `items.length ≤ 2`, todas en estado `OPEN` y pertenecientes a la cuenta
- Y los `items` están ordenados por `createdAt` **descendente** (el primero es el más
  reciente)
- Y al repetir con `?cursor=<cursor>` se obtiene la página siguiente sin solapamiento
- Y si entre la primera y la segunda llamada paginada se crea una orden nueva, esa orden
  **no** aparece al paginar con el cursor previo (cursor estable, RN-8)
- Y `limit=0` o `limit=500` (> máx) produce `VALIDATION_ERROR` (422)

### Escenario 8: Cancelación de orden [AT-09-01-08]
- Dado una orden propia en estado `OPEN`
- Cuando el cliente hace `DELETE /api/v1/orders/{orderId}`
- Entonces la respuesta es **200** con la orden en estado `CANCELLED`
- Y cancelar una orden ya `FILLED` produce `ORDER_NOT_CANCELLABLE` (409) con
  `details.status`

### Escenario 9: Balances [AT-09-01-09]
- Dado un token válido
- Cuando el cliente hace `GET /api/v1/balances`
- Entonces la respuesta es **200** con un arreglo que incluye `ETH` y `USDC`, cada uno con
  `available`, `locked`, `total` como strings en unidad mínima
- Y para cada activo se cumple `total == available + locked` (INV-3) y todos ≥ 0 (INV-2)

### Escenario 10: Dirección de depósito [AT-09-01-10]
- Dado un token válido
- Cuando el cliente hace `GET /api/v1/deposit-address?asset=ETH`
- Entonces la respuesta es **200** con `{ asset: "ETH", address: "0x..." }` y `address`
  con formato `0x` + 40 hex y checksum EIP-55
- Y `?asset=BTC` (no soportado) produce `VALIDATION_ERROR` (422)

### Escenario 11: Creación de retiro (asíncrono, 202) [AT-09-01-11]
- Dado un token válido y balance disponible suficiente
- Cuando el cliente hace `POST /api/v1/withdrawals` con
  `{ "asset": "USDC", "amountMinUnit": "25000000", "address": "0x<checksum EIP-55>" }`
  (25 USDC, unidad mínima USDC)
- Entonces la respuesta es **202 Accepted** con `{ withdrawalId, asset,
  amountMinUnit: "25000000", address, status: "PENDING", createdAt, updatedAt }` con
  `createdAt`/`updatedAt` como strings ISO-8601 UTC
- Y un retiro de ETH `{ "asset": "ETH", "amountMinUnit": "1000000000000000000", "address":
  ... }` interpreta `amountMinUnit` como **wei** (1 ETH) y responde igualmente **202**
- Y una `address` con checksum EIP-55 inválido produce `INVALID_ADDRESS` (422)
- Y un `amountMinUnit` mayor al disponible produce `INSUFFICIENT_FUNDS` (422)

### Escenario 12: Listar depósitos y retiros [AT-09-01-12]
- Dado un token válido
- Cuando el cliente hace `GET /api/v1/deposits` y `GET /api/v1/withdrawals`
- Entonces ambas respuestas son **200** con `{ items: [...], nextCursor }` que contienen solo
  recursos de la cuenta dueña del token
- Y cada depósito tiene `{ depositId, txHash, logIndex, asset, amountMinUnit, status ∈
  {PENDIENTE, ACREDITADO, DESCARTADO}, confirmations, required, blockNumber, createdAt,
  updatedAt }` (RN-17), con `depositId = "<txHash>:<logIndex>"`, `amountMinUnit` como string
  y `confirmations`/`required`/`logIndex`/`blockNumber` como **enteros JSON**
  (`required` = 12); `creditedAt` presente solo si `ACREDITADO` y
  `discardReason ∈ {REORG, REVERTED}` solo si `DESCARTADO`
- Y cada retiro tiene `{ withdrawalId, asset, amountMinUnit, address, txHash|null,
  confirmations, status ∈ {PENDING, BROADCAST, CONFIRMED, FAILED}, failureReason,
  createdAt, updatedAt }` (RN-18), con `amountMinUnit` como string, `confirmations` como
  **entero JSON** y `failureReason` no nulo **solo** si `FAILED`
- Y `GET /api/v1/withdrawals/{withdrawalId}` de un retiro propio devuelve **200** con ese
  mismo objeto; de un retiro inexistente o ajeno devuelve `NOT_FOUND` (404)

### Escenario 13: Orderbook de mercado (público) [AT-09-01-13]
- Dado que existen órdenes abiertas en ambos lados
- Cuando un cliente (sin token) hace `GET /api/v1/market/orderbook?depth=10`
- Entonces la respuesta es **200** con `{ symbol: "ETH-USDC", sequence, bids, asks }`
- Y `bids` están ordenados por `priceMin` descendente y `asks` ascendente, sin niveles
  cruzados (`best_bid < best_ask`) (INV-7)
- Y cada nivel es `[priceMin, quantityWei]` con ambos como strings

### Escenario 14: Trades recientes (público) [AT-09-01-14]
- Dado que hubo fills
- Cuando un cliente hace `GET /api/v1/market/trades?limit=5`
- Entonces la respuesta es **200** con `items` ordenados del más reciente al más antiguo
  (`items.length ≤ 5`), cada uno `{ tradeId, priceMin, quantityWei, takerSide, timestamp }`
- Y `?limit=0` y `?limit=999` (> máx 200) producen `VALIDATION_ERROR` (422)
- Y si no hubo trades, `items` es `[]` con status **200**

### Escenario 15 (error): Ruta inexistente y método no permitido [AT-09-01-15]
- Dado la ruta base `/api/v1`
- Cuando el cliente hace `GET /api/v1/foo` (ruta inexistente)
- Entonces la respuesta es **404** con envelope `{ error: { code: "NOT_FOUND", ... } }`
- Y un `PUT /api/v1/balances` (método no permitido sobre ruta existente) responde **405**
  con envelope `{ error: { code: "METHOD_NOT_ALLOWED", details: { method, allowed } } }`

### Escenario 16 (error): Cuerpo no JSON / monto mal serializado [AT-09-01-16]
- Dado un token válido
- Cuando el cliente hace `POST /api/v1/orders` con un cuerpo que no es JSON válido
- Entonces la respuesta es `VALIDATION_ERROR` (422) con `details.issues`
- Y enviar `priceMin: 2000500000` como **número JSON** (no string), o `priceMin: "1.5"`, o
  `quantityWei: "-100"`, o `quantityWei: "0100000000000000"` (cero a la izquierda) también
  produce `VALIDATION_ERROR` (422) por violar `^(0|[1-9][0-9]*)$`
- Y un `clientOrderId` vacío (`""`) o de más de 64 caracteres o con caracteres de control
  produce `VALIDATION_ERROR` (422) en el paso de esquema (RN-19)

### Escenario 17 (concurrencia/idempotencia): clientOrderId duplicado [AT-09-01-17]
- Dado que la cuenta ya creó una orden con `clientOrderId: "c-1"`
- Cuando reenvía `POST /api/v1/orders` con el mismo `clientOrderId: "c-1"`
- Entonces la respuesta es `DUPLICATE_CLIENT_ORDER_ID` (409) con `details.clientOrderId`
- Y no se crea una segunda orden (la suma de balances no cambia por el reintento; INV-1)

### Escenario 18: Paginación de depósitos/retiros [AT-09-01-18]
- Dado una cuenta con más depósitos que el `limit` solicitado
- Cuando el cliente hace `GET /api/v1/deposits?limit=2`
- Entonces la respuesta es **200** con `items.length ≤ 2`, ordenados por `createdAt`
  descendente, y `nextCursor` no nulo si hay más páginas
- Y repetir con `?cursor=<cursor>` devuelve la página siguiente sin solapamiento
- Y `limit=0` o `limit=500` (> máx) produce `VALIDATION_ERROR` (422)
- Y lo mismo aplica a `GET /api/v1/withdrawals`

### Escenario 19: Ticker / top-of-book (público) [AT-09-01-19]
- Dado un orderbook con órdenes en ambos lados y al menos un trade previo
- Cuando un cliente (sin token) hace `GET /api/v1/market/ticker`
- Entonces la respuesta es **200** con `{ symbol: "ETH-USDC", bestBidPrice, bestAskPrice,
  lastPrice, lastQuantityWei, timestamp }`, todos los montos como strings
- Y `bestBidPrice < bestAskPrice` (libro no cruzado, INV-7) (RN-16)

### Escenario 20 (borde): Ticker y orderbook con lados vacíos [AT-09-01-20]
- Dado un orderbook **sin** órdenes en el lado ask (solo bids) y sin trades previos
- Cuando el cliente hace `GET /api/v1/market/ticker`
- Entonces la respuesta es **200** con `bestAskPrice: null`, `bestBidPrice` no nulo,
  `lastPrice: null` y `lastQuantityWei: null` (RN-16)
- Y `GET /api/v1/market/orderbook?depth=10` devuelve **200** con `asks: []` y `bids` no vacío;
  con el libro totalmente vacío devuelve `{ bids: [], asks: [] }` (RN-12)

### Escenario 21 (error): Orden MARKET sin liquidez [AT-09-01-21]
- Dado un orderbook con el lado SELL (asks) **vacío**
- Cuando el cliente envía una orden `MARKET BUY` válida en esquema y con fondos suficientes
- Entonces la respuesta es `MARKET_NO_LIQUIDITY` (422) con el envelope de error estándar
- Y los balances de la cuenta quedan **idénticos** a antes de la request (INV-1, INV-2) y
  **no** se crea ninguna orden ni queda remanente en el libro

### Escenario 22 (borde): MARKET con fill parcial y liquidez agotada [AT-09-01-22]
- Dado un orderbook cuyo lado opuesto solo alcanza para ejecutar **parte** de la cantidad
  pedida
- Cuando el cliente envía una orden `MARKET` por una cantidad mayor a la liquidez disponible
- Entonces la respuesta es **201** con `status: "CANCELLED"`, `filledWei > "0"` y
  `filledWei < quantityWei`
- Y la orden **no** queda en el libro (remanente descartado): `CANCELLED` es el estado
  **terminal** de esa orden MARKET (RN-5, HU-03-04 RN-9)

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-*) pasan
- [ ] Reglas de negocio RN-1..RN-20 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md)
- [ ] (si aplica) Adherencia verificada al estandar on-chain citado (EIP-55 en direcciones)
