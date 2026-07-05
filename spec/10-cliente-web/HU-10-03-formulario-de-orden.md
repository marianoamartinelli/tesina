# HU-10-03 — Formulario de orden (limit/market)

- **Epica:** 10 — Cliente Web (React)
- **Actor / rol:** Trader autenticado operando la web
- **Prioridad:** Alta
- **Dependencias:** HU de épica 09 (endpoint de alta de orden y formato de error); épica 04 (validaciones y ciclo de vida); épica 03 (matching); épica 05 (fees/notional); HU-10-05 (balances para estimar fondos). Fundaciones (00).
- **Estandares de dominio aplicables:** N/A on-chain. Aplican parámetros del par (tick/lot/min notional), convenciones monetarias (enteros, floor/ceil), modelo de errores y precedencia de validación.

## Historia
Como trader autenticado, quiero colocar órdenes `LIMIT` o `MARKET` de compra o venta de ETH/USDC desde un formulario con validación inmediata y estimación de costo/fee, para operar con confianza y entender el resultado de cada envío.

## Contexto y alcance
Cubre el formulario de alta de órdenes en el cliente React: selección de lado (BUY/SELL) y tipo (LIMIT/MARKET), ingreso de precio (solo LIMIT) y cantidad, validación del lado del cliente que **replica** las reglas del par para feedback inmediato, conversión exacta de los valores humanos a enteros de unidad mínima (strings) antes de enviar, estimación de notional/fee, envío idempotente con `clientOrderId` y manejo del resultado (aceptación o rechazo por código de error). No cubre el matching, el settlement ni el cálculo autoritativo de fees (backend, épicas 03/05); las estimaciones del cliente son informativas y el servidor es la fuente de verdad (RNE-2).

## Reglas de negocio e invariantes
1. **RN-1 (campos por tipo).** `LIMIT` requiere `side`, `priceMin`, `quantityWei`. `MARKET` requiere `side`, `quantityWei` y **no** acepta precio (el campo precio se oculta/deshabilita). Enviar `LIMIT` sin precio se previene en cliente y, si llegara al backend, devuelve `PRICE_REQUIRED`; `MARKET` con precio devuelve `PRICE_NOT_ALLOWED`.
2. **RN-2 (conversión humano→unidad mínima, sin floats — RNE-1).** Antes de enviar, el cliente convierte:
   - precio humano `USDC/ETH` a `priceMin` desplazando **6** decimales (`2000.50 ⇒ "2000500000"`),
   - cantidad humana `ETH` a `quantityWei` desplazando **18** decimales (`1.5 ⇒ "1500000000000000000"`),
   usando aritmética entera/decimal de precisión fija sobre strings. Prohibido `parseFloat`. El valor enviado matchea `^(0|[1-9][0-9]*)$`.
3. **RN-3 (tick size).** Validación cliente: `priceMin` múltiplo de `10000` (tick = 0.01 USDC/ETH) y `> 0`; equivale a máx. 2 decimales en el precio humano. Si no se cumple, se bloquea el envío y se anticipa el error `INVALID_PRICE_TICK`.
4. **RN-4 (lot size).** Validación cliente: `quantityWei` múltiplo de `10^14` (lot = 0.0001 ETH) y `> 0`; equivale a máx. 4 decimales en la cantidad humana. Si no, se bloquea y se anticipa `INVALID_LOT_SIZE`.
5. **RN-5 (mínimo notional — LIMIT / MARKET).** Para **LIMIT** se estima `notionalMin = floor(quantityWei × priceMin / 10^18)` (multiplicar antes de dividir, una sola división, big integers). Debe ser `≥ 10000000` (10 USDC); si no, se bloquea el envío y se anticipa `BELOW_MIN_NOTIONAL`. Para **MARKET** el notional no se conoce de antemano (no hay precio límite): el cliente **no** muestra un notional estimado a partir de un precio límite (lo rotula "no disponible" u oculta el campo) y **no** realiza validación de mínimo notional en cliente para MARKET; la validación autoritativa de mínimo para market la hace el backend (épicas 03/04). La estimación de precio medio de ejecución para MARKET se cubre en RN-13.
6. **RN-6 (estimación de fee y clasificación maker/taker).** El cliente muestra una estimación **informativa** de fee, redondeada con `ceil` y cobrada en el activo recibido (`00-fundaciones/convenciones-monetarias.md` §3.3):
   - compra (recibe ETH): `fee_base = ceil(quantityWei × fee_bps / 10000)` en wei;
   - venta (recibe USDC): `fee_quote = ceil(quote_min × fee_bps / 10000)` en USDC-min.
   El **rol estimado** (maker/taker) se determina comparando el precio ingresado contra el **top-of-book visible** (RN-13): (a) **MARKET** ⇒ siempre `taker` (20 bps); (b) **LIMIT BUY** con `priceMin >= best_ask`, o **LIMIT SELL** con `priceMin <= best_bid` ⇒ cruzaría ⇒ `taker` (20 bps); (c) si el lado opuesto del libro está **vacío** (no hay `best_ask` para una compra, o no hay `best_bid` para una venta) ⇒ se usa `taker` como **cota conservadora**; (d) en cualquier otro caso (la orden quedaría en libro) ⇒ `maker` (10 bps). La estimación se rotula explícitamente "estimada"; el valor definitivo lo fija el backend (épica 05).
7. **RN-7 (estimación de fondos requeridos).** El cliente estima los fondos a bloquear: compra LIMIT ⇒ `quote_min` USDC; venta ⇒ `quantityWei` ETH. Si superan el `disponible` mostrado (HU-10-05) se advierte, pero **no** se bloquea el envío localmente: el rechazo autoritativo es `INSUFFICIENT_FUNDS` del servidor (RNE-2, INV-2).
8. **RN-8 (idempotencia — RNE-7).** Cada intento lógico de alta genera un `clientOrderId` único (p. ej. UUID v4). Ante reintento del **mismo** envío (timeout/red), se reutiliza el mismo `clientOrderId`. Si el servidor responde `DUPLICATE_CLIENT_ORDER_ID` (409), el cliente trata el envío como ya recibido (no duplica) y **recupera el estado real** consultando el listado con el **filtro por `clientOrderId`** de la épica 09 (HU-09-01 RN-8): `GET /orders?clientOrderId=<id>`. **No existe** una ruta `GET /orders/{clientOrderId}` (el path param de `/orders/{orderId}` es siempre el `orderId` asignado por el servidor). Este filtro es el mecanismo canónico de recuperación, dado que la respuesta 409 solo trae `clientOrderId` en `details` y no necesariamente el `orderId`.
9. **RN-9 (anti doble submit).** Mientras hay un alta en curso, el botón "Colocar orden" se deshabilita; no se permite un segundo envío hasta resolver.
10. **RN-10 (feedback de resultado).** Ante 200/201 con la orden creada, se muestra confirmación con el estado devuelto (`OPEN`, `PARTIALLY_FILLED` o `FILLED`) y, si hubo fills, el promedio/cantidad ejecutada provistos por la API; el formulario se limpia o queda listo para otra orden.
11. **RN-11 (mapeo de errores por `code` — RNE-3).** Cada `code` del catálogo se mapea a un mensaje claro: `INVALID_SIDE`, `INVALID_ORDER_TYPE`, `PRICE_REQUIRED`, `PRICE_NOT_ALLOWED`, `INVALID_PRICE_TICK`, `INVALID_LOT_SIZE`, `BELOW_MIN_NOTIONAL`, `INSUFFICIENT_FUNDS`, `SELF_TRADE_BLOCKED`, `MARKET_NO_LIQUIDITY`, `DUPLICATE_CLIENT_ORDER_ID`, `RATE_LIMITED`, `UNAUTHENTICATED`, `VALIDATION_ERROR`. Se muestra usando `details` cuando aporta (montos como string).
12. **RN-12 (precedencia coherente y validaciones bloqueantes).** El orden de validación del cliente sigue la precedencia de `00-fundaciones/modelo-de-errores.md` §4 (esquema → enums/combinaciones → reglas del par), de modo que el primer error mostrado coincida con el que devolvería el backend. Las validaciones de **campo** —lado/tipo (RN-1), tick (RN-3), lot (RN-4) y mínimo notional LIMIT (RN-5)— son **bloqueantes del submit**: el botón "Colocar orden" permanece deshabilitado o se muestra el error inline y **no** se llama a la API. La validación de **fondos** (RN-7) es **no bloqueante** en cliente (solo advierte); su rechazo autoritativo es `INSUFFICIENT_FUNDS` del servidor. Ante múltiples violaciones de campo simultáneas, se muestra **primero** la de mayor precedencia según §4 (p. ej. tick antes que lot).
13. **RN-13 (consumo del top-of-book y estimación para MARKET).** El formulario consume el **top-of-book** y la profundidad del orderbook en vivo (compartidos con HU-10-02 o por el mismo canal WebSocket) para: (a) clasificar el rol de fee de una LIMIT (RN-6); y (b) para **MARKET**, calcular de forma **informativa** el **precio medio estimado de ejecución** recorriendo los niveles del lado opuesto del libro hasta cubrir `quantityWei`, acumulando el notional con big integers (sin floats). Si `quantityWei` excede la liquidez visible, se indica que la orden se ejecutaría parcialmente o con slippage desconocido. Toda esta información se rotula explícitamente "estimada"; el valor definitivo lo fija el backend (RNE-2). Si no hay top-of-book disponible, la clasificación de fee usa `taker` como cota conservadora (RN-6c).

## Criterios de aceptación (DoD)

### Escenario 1: Alta de orden LIMIT válida [AT-10-03-01]
- Dado un trader autenticado con fondos suficientes
- Y un formulario LIMIT BUY con precio humano `2000.50` y cantidad `1` ETH
- Cuando coloca la orden
- Entonces el cliente envía `priceMin="2000500000"`, `quantityWei="1000000000000000000"`, `side="BUY"`, `type="LIMIT"` y un `clientOrderId`
- Y al recibir 201 muestra la orden con su estado (`OPEN`/`PARTIALLY_FILLED`/`FILLED`)

### Escenario 2: Alta de orden MARKET válida [AT-10-03-02]
- Dado un trader autenticado y un formulario MARKET SELL con cantidad `0.5` ETH
- Cuando coloca la orden
- Entonces el campo de precio está oculto/deshabilitado y no se envía precio
- Y el cliente envía `quantityWei="500000000000000000"`, `type="MARKET"`, `side="SELL"` y un `clientOrderId`
- Y al recibir respuesta muestra el resultado de ejecución provisto por la API

### Escenario 3 (borde): conversión exacta humano→unidad mínima [AT-10-03-03]
- Dado un precio humano `2000.50` y una cantidad humana `1.5`
- Cuando el cliente convierte a unidad mínima
- Entonces obtiene `priceMin="2000500000"` (6 decimales) y `quantityWei="1500000000000000000"` (18 decimales)
- Y la conversión se realiza por desplazamiento de coma sobre strings, sin `parseFloat`

### Escenario 4 (borde): estimación de notional y fee con enteros [AT-10-03-04]
- Dado LIMIT BUY `quantityWei="1000000000000000000"` (1 ETH) a `priceMin="2000500000"`
- Y un top-of-book donde esta orden quedaría en libro (rol estimado `maker`)
- Cuando se calcula la estimación
- Entonces el `notionalMin` mostrado es exactamente `"2000500000"` (2000.50 USDC)
- Y la fee maker estimada en ETH es exactamente `"1000000000000000"` wei (= `ceil(10^18 × 10 / 10000)`)
- Y si el rol estimado fuera `taker`, la fee en ETH sería exactamente `"2000000000000000"` wei (= `ceil(10^18 × 20 / 10000)`)
- Y todos los valores mostrados son exactos, sin aproximaciones de punto flotante (la exigencia de big integers —multiplicar antes de dividir, `ceil` para fee— rige por RN-5/RN-6)

### Escenario 5 (error de validación cliente): tick inválido bloquea envío [AT-10-03-05]
- Dado un precio humano `2000.005` (3 decimales ⇒ `priceMin="2000005000"`, no múltiplo de 10000)
- Cuando el usuario intenta colocar la orden
- Entonces el cliente bloquea el envío y muestra el error equivalente a `INVALID_PRICE_TICK`
- Y no se realiza la llamada a la API

### Escenario 6 (error de validación cliente): lot inválido bloquea envío [AT-10-03-06]
- Dado una cantidad humana `0.00005` ETH (`quantityWei="50000000000000"`, no múltiplo de 10^14)
- Cuando el usuario intenta colocar la orden
- Entonces el cliente bloquea el envío y muestra el error equivalente a `INVALID_LOT_SIZE`
- Y no se realiza la llamada a la API

### Escenario 7 (error de validación cliente): notional por debajo del mínimo [AT-10-03-07]
- Dado LIMIT con `quantityWei="100000000000000"` (0.0001 ETH) a `priceMin="2000000000"` (2000.00)
- Cuando el usuario intenta colocar la orden
- Entonces el notional estimado `= "200000"` (0.20 USDC) `< 10000000`
- Y el cliente bloquea el envío y muestra el error equivalente a `BELOW_MIN_NOTIONAL`

### Escenario 8a (validación cliente): LIMIT sin precio bloquea el envío [AT-10-03-08a]
- Dado un formulario LIMIT sin precio cargado
- Cuando el usuario intenta enviar
- Entonces el cliente lo impide (campo de precio requerido; submit bloqueado)
- Y no se realiza ninguna llamada a la API
- Y, simétricamente, en MARKET el campo de precio está oculto/deshabilitado y no se envía precio

### Escenario 8b (manejo de servidor): backend rechaza LIMIT sin precio [AT-10-03-08b]
- Dado que la validación de cliente se omite (prueba de integración) y el payload de una LIMIT sin precio llega al backend
- Cuando la API responde `{ error: { code: "PRICE_REQUIRED" } }` (422)
- Entonces el cliente muestra el error mapeado por `code` (RN-11) y no navega fuera del formulario

### Escenario 8c (manejo de servidor): backend rechaza MARKET con precio [AT-10-03-08c]
- Dado que la validación de cliente se omite (prueba de integración) y el payload de una MARKET con precio llega al backend
- Cuando la API responde `{ error: { code: "PRICE_NOT_ALLOWED" } }` (422)
- Entonces el cliente muestra el error mapeado por `code` (RN-11) y no navega fuera del formulario

### Escenario 9 (error de servidor): fondos insuficientes [AT-10-03-09]
- Dado un trader con disponible inferior al requerido
- Cuando coloca la orden y la API responde `{ error: { code: "INSUFFICIENT_FUNDS", details: { asset, required, available } } }` (422)
- Entonces el cliente muestra "Saldo insuficiente" con `required` y `available` (strings de unidad mínima formateados)
- Y los balances no se alteran en la UI (INV-2): se respeta la respuesta del servidor

### Escenario 10 (error de servidor): self-trade bloqueado [AT-10-03-10]
- Dado que la orden cruzaría contra una orden propia
- Cuando la API responde `{ error: { code: "SELF_TRADE_BLOCKED", details: { restingOrderId } } }` (422)
- Entonces el cliente informa que la orden cruzaría contra una orden propia y no se ejecuta

### Escenario 11 (error de servidor): market sin liquidez [AT-10-03-11]
- Dado un MARKET cuando el lado opuesto del libro está vacío
- Cuando la API responde `{ error: { code: "MARKET_NO_LIQUIDITY" } }` (422)
- Entonces el cliente informa que no hay liquidez para ejecutar la orden market

### Escenario 12 (idempotencia/concurrencia): reintento reutiliza clientOrderId [AT-10-03-12]
- Dado un alta enviada cuyo resultado no llegó (timeout de red)
- Cuando el cliente reintenta el **mismo** envío con el **mismo** `clientOrderId`
- Y la API responde `{ error: { code: "DUPLICATE_CLIENT_ORDER_ID", details: { clientOrderId } } }` (409)
- Entonces el cliente no crea una segunda orden
- Y recupera el estado real consultando el listado filtrado por `clientOrderId`: `GET /orders?clientOrderId=<id>` (épica 09, HU-09-01 RN-8) (RN-8)
- Y muestra una única orden con el estado recuperado (sin duplicado)

### Escenario 13 (borde): anti doble submit [AT-10-03-13]
- Dado un alta en curso
- Cuando el usuario vuelve a presionar "Colocar orden"
- Entonces el segundo clic se ignora y el botón permanece deshabilitado hasta resolver el primero

### Escenario 14 (estimación): el rol de fee depende del top-of-book [AT-10-03-14]
- Dado un top-of-book con `best_ask.priceMin = "2001000000"` (2001.00) y `best_bid.priceMin = "2000000000"` (2000.00)
- Cuando el usuario configura una LIMIT BUY con `priceMin = "2001000000"` (≥ best_ask: cruzaría)
- Entonces la fee estimada usa **taker** (20 bps) (RN-6b)
- Y cuando cambia el precio a `priceMin = "1999000000"` (< best_ask: quedaría en libro)
- Entonces la fee estimada pasa a usar **maker** (10 bps) (RN-6d)
- Y si el lado ask estuviera vacío, la estimación usaría **taker** como cota conservadora (RN-6c)

### Escenario 15 (borde): MARKET no muestra notional estimado ni valida mínimo notional en cliente [AT-10-03-15]
- Dado un formulario MARKET SELL con cantidad `0.5` ETH
- Cuando el usuario completa la cantidad
- Entonces el campo de notional estimado se oculta o se rotula "no disponible" (no hay precio límite)
- Y el cliente no bloquea el envío por `BELOW_MIN_NOTIONAL` (la validación de mínimo para MARKET es autoritativa del backend) (RN-5)

### Escenario 16 (precedencia): múltiples validaciones de campo simultáneas [AT-10-03-16]
- Dado una LIMIT con precio de tick inválido (`priceMin="2000005000"`, 3 decimales) **y** cantidad de lot inválido (`quantityWei="50000000000000"`, no múltiplo de 10^14) al mismo tiempo
- Cuando el usuario intenta colocar la orden
- Entonces el submit se bloquea y se muestra **primero** el error de precio (`INVALID_PRICE_TICK`), en coherencia con la precedencia de `00-fundaciones/modelo-de-errores.md` §4 (reglas del par: tick antes que lot) (RN-12)
- Y no se realiza ninguna llamada a la API

### Escenario 17 (estimación): precio medio estimado de ejecución de una MARKET [AT-10-03-17]
- Dado un orderbook con asks: nivel 1 `priceMin="2000000000"` por `quantityWei="500000000000000000"` (0.5 ETH) y nivel 2 `priceMin="2001000000"` por `quantityWei="1000000000000000000"` (1 ETH)
- Y una MARKET BUY de `quantityWei="1000000000000000000"` (1 ETH)
- Cuando se calcula la estimación informativa recorriendo niveles con big integers
- Entonces el notional acumulado estimado es `floor(0.5 ETH × 2000.00) + floor(0.5 ETH × 2001.00)` = `"1000000000" + "1000500000"` = `"2000500000"` USDC-min (2000.50 USDC)
- Y el precio medio estimado se muestra rotulado "estimado" (sin floats)
- Y si la cantidad excediera la liquidez visible, se indica ejecución parcial o slippage desconocido (RN-13)

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-*) pasan
- [ ] Reglas de negocio RN-1..RN-13 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md)
- [ ] (si aplica) Adherencia verificada al estandar on-chain citado
