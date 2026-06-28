# HU-04-01 — Colocar orden limit

- **Epica:** 04 — Gestión de Órdenes
- **Actor / rol:** Trader autenticado
- **Prioridad:** Alta
- **Dependencias:** HU-04-03 (validaciones de orden), HU-04-05 (ciclo de vida y estados),
  HU-02-* (bloqueo/liberación de fondos, ledger), HU-03-* (matching, orderbook,
  self-trade). Fundaciones (00).
- **Estandares de dominio aplicables:** N/A (operación interna del exchange; sin
  interacción on-chain).

## Historia
Como **trader autenticado**, quiero **colocar una orden limit indicando lado, precio
límite y cantidad**, para **comprar o vender ETH a un precio que yo controlo, con la
garantía de que el sistema reserva mis fondos antes de exponer la orden al mercado**.

## Contexto y alcance
Cubre el alta de una orden `LIMIT`: validación de entrada (delegada en su detalle a
HU-04-03), **reserva (bloqueo) de los fondos correctos antes** de entregar la orden al
matching engine, y el registro del estado resultante (`OPEN`, `PARTIALLY_FILLED` o
`FILLED`). Una orden limit de compra se ejecuta a un precio ≤ al límite; una de venta, a un
precio ≥ al límite. El remanente no ejecutado **descansa** en el orderbook respaldado por
la reserva.

No cubre el algoritmo de cruce ni la prioridad precio-tiempo (HU-03-*), ni el movimiento
contable del fill ni las fees (HU-05-*), ni el contrato exacto de la API (HU-09-*). El
precio se expresa como `priceMin` (USDC-min por 1 ETH) y la cantidad como `quantityWei`
(wei), ambos enteros de unidad mínima serializados como string.

## Reglas de negocio e invariantes
1. **RN-1 (entrada).** Una orden limit requiere `side ∈ {BUY, SELL}`, `type = LIMIT`,
   `priceMin` (entero > 0) y `quantityWei` (entero > 0). `quoteOrderQty` **no** se admite
   en una orden limit (→ `VALIDATION_ERROR`). Acepta opcionalmente `clientOrderId`.
2. **RN-2 (reglas del par).** `priceMin mod 10000 == 0 ∧ priceMin > 0` (si no,
   `INVALID_PRICE_TICK`); `quantityWei mod 10^14 == 0 ∧ quantityWei > 0` (si no,
   `INVALID_LOT_SIZE`); `notional_min = floor(quantityWei × priceMin / 10^18) ≥ 10000000`
   (si no, `BELOW_MIN_NOTIONAL`). Detalle y precedencia: HU-04-03.
3. **RN-3 (reserva BUY).** Para `BUY`, se bloquea en **quote**
   `R = floor(quantityWei × priceMin / 10^18)` USDC-min (= `notional_min`, costo máximo al
   precio límite). Requiere `disponible(USDC) ≥ R`; si no, `INSUFFICIENT_FUNDS`.
4. **RN-4 (reserva SELL).** Para `SELL`, se bloquea en **base** `R = quantityWei` wei.
   Requiere `disponible(ETH) ≥ R`; si no, `INSUFFICIENT_FUNDS`.
5. **RN-5 (sin fee en la reserva).** La reserva de RN-3/RN-4 **no** incluye fee alguna; la
   fee se cobra en el activo recibido al liquidar cada fill (HU-05-*). Ver RE-2 del README.
6. **RN-6 (orden de operaciones).** La secuencia es: validar (RN-1, RN-2) → idempotencia
   (`clientOrderId`) → reservar fondos (RN-3/RN-4) → entregar al matching. La reserva
   ocurre **antes** del matching (RE-1) y nunca después.
7. **RN-7 (marketable limit / taker).** Si al entrar el precio cruza el lado opuesto
   (BUY con `priceMin ≥ best_ask`, o SELL con `priceMin ≤ best_bid`), la orden ejecuta de
   inmediato como **taker** contra los niveles cruzables, en prioridad precio-tiempo
   (HU-03-*). El remanente no ejecutado descansa como **maker** a `priceMin`.
8. **RN-8 (mejor precio ⇒ liberación).** Si una compra ejecuta contra asks a un precio
   **menor** que su límite, consume menos quote que `R`; la diferencia entre lo reservado y
   lo efectivamente consumido se **libera** a disponible (RE-3, INV-3).
9. **RN-9 (resultado de estado).** Tras el matching: sin ejecución ⇒ `OPEN`; ejecución
   parcial con remanente que descansa ⇒ `PARTIALLY_FILLED`; ejecución total ⇒ `FILLED`
   (HU-04-05).
10. **RN-10 (self-trade, caso degenerado).** Si al entrar la orden **lo primero** que
    cruzaría es una orden **propia** (misma cuenta maker y taker) y **no** hubo ningún fill
    previo contra terceros, se rechaza con `SELF_TRADE_BLOCKED` (422). Como esta detección es
    **posterior** a la reserva de fondos (RE-4 paso 8 > paso 7), la reserva ya tomada se
    **revierte atómicamente** antes de responder: `bloqueado −= R; disponible += R`, dejando
    los balances **idénticos** a los previos al alta (INV-2, INV-3). La orden se registra como
    `REJECTED` (RE-12) y no descansa en el libro. El caso de self-trade **tras** fills previos
    se rige por RN-14.
11. **RN-11 (idempotencia).** `clientOrderId` ya usado por la cuenta ⇒
    `DUPLICATE_CLIENT_ORDER_ID` (409), sin crear orden ni reservar (RE-5).
12. **RN-12 (invariantes).** El alta y sus reservas respetan INV-1 (conservación; la
    reserva solo mueve disponible↔bloqueado), INV-2 (no-negatividad; se rechaza **antes**,
    nunca se corrige después), INV-3 (`total = disponible + bloqueado`), INV-7 (el
    remanente abierto queda respaldado por `bloqueado`) e INV-8 (orden y reserva
    persisten).
13. **RN-13 (serialización).** `priceMin`, `quantityWei`, montos reservados y cantidades
    ejecutadas/remanentes se serializan como string `^(0|[1-9][0-9]*)$` (RE-8).
14. **RN-14 (self-trade en barrido tras fills previos, STP).** Si la limit marketable ejecuta
    fills contra órdenes de **terceros** y luego, al continuar el barrido, el siguiente nivel
    cruzable es una orden **propia**, el barrido **se detiene** en la orden propia (RE-11,
    modo *expire-taker*): los fills previos son **definitivos**. El remanente **no** descansa
    (evita un libro cruzado contra la propia orden, INV-7) y se descarta, liberando su reserva
    (RE-3). La orden termina `FILLED` (si completó antes de tocar la propia) o `CANCELLED` con
    `executedQty > 0`; la respuesta es **exitosa** (no 422).
15. **RN-15 (alcance de `clientOrderId`).** La unicidad de `clientOrderId` es **permanente
    por cuenta** (lifetime): no se reutiliza aunque la orden original ya esté `FILLED`,
    `CANCELLED` o `REJECTED`. Dos cuentas distintas pueden usar el mismo `clientOrderId` sin
    conflicto (RE-5).
16. **RN-16 (rate limiting).** El alta está sujeta a control de tasa: superar el límite
    configurado ⇒ `RATE_LIMITED` (429, `details = { retryAfterSeconds }`) sin crear orden ni
    reservar, evaluado antes de la autenticación (RE-4 paso 0, RE-10; límite en HU-09-*).

## Criterios de aceptación (DoD)

### Escenario 1: Alta de compra limit que descansa en el libro [AT-04-01-01]
- Dado un trader autenticado con `disponible(USDC) = 5000000000` (5000 USDC) y `bloqueado(USDC) = 0`
- Y un orderbook sin asks a `priceMin ≤ 2000000000`
- Cuando coloca `side=BUY, type=LIMIT, priceMin="2000000000", quantityWei="1000000000000000000"` (1 ETH @ 2000.00)
- Entonces la orden se acepta y queda en estado `OPEN`
- Y se bloquean `R = floor(10^18 × 2000000000 / 10^18) = 2000000000` USDC-min: `disponible(USDC) = 3000000000`, `bloqueado(USDC) = 2000000000`
- Y `total(USDC)` no cambia (INV-3) y la suma global de USDC no cambia (INV-1)
- Y la orden aparece como abierta con `executedQty = "0"` y `remainingQty = "1000000000000000000"`

### Escenario 2: Alta de venta limit que descansa en el libro [AT-04-01-02]
- Dado un trader autenticado con `disponible(ETH) = 3000000000000000000` (3 ETH)
- Y un orderbook sin bids a `priceMin ≥ 2100000000`
- Cuando coloca `side=SELL, type=LIMIT, priceMin="2100000000", quantityWei="1000000000000000000"` (1 ETH @ 2100.00)
- Entonces la orden queda `OPEN`
- Y se bloquean `R = 1000000000000000000` wei de ETH: `disponible(ETH) = 2000000000000000000`, `bloqueado(ETH) = 1000000000000000000`
- Y no se bloquea ni reserva USDC alguno

### Escenario 3 (feliz): Compra limit que ejecuta totalmente como taker [AT-04-01-03]
- Dado un trader autenticado con `disponible(USDC) = 5000000000`
- Y un ask resting de otra cuenta por `1000000000000000000` wei a `priceMin = 2000000000`
- Cuando coloca `side=BUY, type=LIMIT, priceMin="2000000000", quantityWei="1000000000000000000"`
- Entonces la orden ejecuta de inmediato como taker y queda `FILLED`
- Y no queda remanente en el libro ni reserva remanente bloqueada por esta orden
- Y el detalle contable del fill (debito/credito y fees) lo aplica HU-05-* de forma atómica (INV-4)

### Escenario 4 (borde): Compra limit con ejecución parcial; el remanente descansa [AT-04-01-04]
- Dado un trader autenticado con `disponible(USDC) = 5000000000`
- Y un único ask resting ajeno por `400000000000000000` wei (0.4 ETH) a `priceMin = 2000000000`
- Cuando coloca `side=BUY, type=LIMIT, priceMin="2000000000", quantityWei="1000000000000000000"` (1 ETH)
- Entonces 0.4 ETH ejecutan como taker y el remanente `600000000000000000` wei descansa a `2000000000`; la orden queda `PARTIALLY_FILLED` (no `OPEN`, conforme a HU-04-05 RN-3)
- Y la reserva remanente bloqueada en USDC respalda exactamente el remanente: `floor(600000000000000000 × 2000000000 / 10^18) = 1200000000` USDC-min (INV-7)
- Y `executedQty = "400000000000000000"`, `remainingQty = "600000000000000000"`, estado `PARTIALLY_FILLED`

### Escenario 5 (borde): Compra que matchea a mejor precio libera el sobrante reservado [AT-04-01-05]
- Dado un trader autenticado con `disponible(USDC) = 5000000000`
- Y un ask resting ajeno por `1000000000000000000` wei a `priceMin = 1990000000` (mejor que el límite)
- Cuando coloca `side=BUY, type=LIMIT, priceMin="2000000000", quantityWei="1000000000000000000"`
- Entonces se reserva primero `R = 2000000000` USDC-min, la orden ejecuta a `1990000000` consumiendo `floor(10^18 × 1990000000 / 10^18) = 1990000000` USDC-min
- Y el sobrante `2000000000 − 1990000000 = 10000000` USDC-min se **libera** a disponible (RE-3, INV-3)
- Y la orden queda `FILLED`

### Escenario 6 (error): Fondos insuficientes [AT-04-01-06]
- Dado un trader autenticado con `disponible(USDC) = 1000000000` (1000 USDC)
- Cuando coloca `side=BUY, type=LIMIT, priceMin="2000000000", quantityWei="1000000000000000000"` (requiere `R = 2000000000`)
- Entonces la operación se rechaza con `INSUFFICIENT_FUNDS` (HTTP 422)
- Y `details = { asset:"USDC", required:"2000000000", available:"1000000000" }`
- Y no se crea ninguna orden, no se bloquea nada y los balances quedan intactos (INV-2)

### Escenario 7 (error): Self-trade bloqueado (caso degenerado, sin fills previos) [AT-04-01-07]
- Dado un trader autenticado con un ask **propio** resting por `1000000000000000000` wei a `priceMin = 2000000000`
- Y `disponible(USDC) = 5000000000` (≥ `R = floor(10^18 × 2000000000 / 10^18) = 2000000000`, para que la validación de fondos **pase** y el test aísle el self-trade), `bloqueado(USDC) = 0`
- Cuando coloca `side=BUY, type=LIMIT, priceMin="2000000000", quantityWei="1000000000000000000"` que cruzaría su propio ask como **primera** liquidez
- Entonces se rechaza con `SELF_TRADE_BLOCKED` (HTTP 422), `details = { restingOrderId }`
- Y la reserva tomada se **revierte atómicamente**: `disponible(USDC) = 5000000000`, `bloqueado(USDC) = 0` (idénticos a los previos al intento, RN-10, INV-3)
- Y la orden entrante no descansa en el libro; se registra como `REJECTED` (RE-12)

### Escenario 8 (idempotencia): clientOrderId duplicado [AT-04-01-08]
- Dado un trader que ya colocó una orden con `clientOrderId = "abc-123"`
- Cuando coloca otra orden limit con el mismo `clientOrderId = "abc-123"`
- Entonces se rechaza con `DUPLICATE_CLIENT_ORDER_ID` (HTTP 409), `details = { clientOrderId:"abc-123" }`
- Y no se crea una segunda orden ni se reservan fondos adicionales

### Escenario 9 (error): Precio fuera de tick [AT-04-01-09]
- Dado un trader autenticado con fondos suficientes
- Cuando coloca `side=BUY, type=LIMIT, priceMin="2000005000", quantityWei="1000000000000000000"` (2000.005, no múltiplo de 10000)
- Entonces se rechaza con `INVALID_PRICE_TICK` (HTTP 422), `details = { priceMin:"2000005000", tickSize:"10000" }`
- Y no se reserva nada (la validación del par precede a fondos, RE-4)

### Escenario 10 (borde): Notional exactamente igual al mínimo es válido [AT-04-01-10]
- Dado un trader autenticado con `disponible(USDC) ≥ 10000000`
- Cuando coloca `side=BUY, type=LIMIT, priceMin="2000000000", quantityWei="5000000000000000"` (0.005 ETH @ 2000 ⇒ notional `10000000` = 10 USDC)
- Entonces la orden se acepta (el notional iguala el mínimo, no es menor)
- Y se bloquean `10000000` USDC-min

### Escenario 11 (persistencia): La orden abierta y su reserva sobreviven al reinicio [AT-04-01-11]
- Dado un trader con una orden limit `OPEN` y su reserva bloqueada
- Cuando el sistema se reinicia y reconstruye estado desde el ledger
- Entonces la orden sigue `OPEN` con su prioridad precio-tiempo intacta (INV-7)
- Y `bloqueado` y `disponible` reconstruidos coinciden exactamente con los previos (INV-8)

### Escenario 12 (error): `quoteOrderQty` no se admite en limit [AT-04-01-12]
- Dado un trader autenticado con fondos suficientes
- Cuando coloca `side=BUY, type=LIMIT, priceMin="2000000000", quantityWei="1000000000000000000", quoteOrderQty="2000000000"`
- Entonces se rechaza con `VALIDATION_ERROR` (HTTP 422); `details.issues` indica que `quoteOrderQty` no es un campo permitido en una orden `LIMIT` (RN-1)
- Y no se reserva nada ni se crea orden

### Escenario 13 (borde): Self-trade tras fills previos detiene el barrido (STP) [AT-04-01-13]
- Dado un trader autenticado con `disponible(USDC) = 5000000000`
- Y dos asks cruzables a `priceMin = 2000000000`: el primero **ajeno** por `400000000000000000` wei (0.4 ETH) y el segundo **propio** por `600000000000000000` wei (0.6 ETH)
- Cuando coloca `side=BUY, type=LIMIT, priceMin="2000000000", quantityWei="1000000000000000000"` (1 ETH)
- Entonces ejecuta 0.4 ETH contra el ask ajeno (fill **definitivo**) y, al encontrar su propio ask, **detiene** el barrido (RN-14, RE-11)
- Y el remanente `600000000000000000` wei **no** descansa: se descarta y su reserva se libera (RE-3)
- Y la orden queda `CANCELLED` con `executedQty = "400000000000000000"`; la respuesta es exitosa (no 422)

### Escenario 14 (idempotencia): `clientOrderId` no reutilizable tras estado terminal [AT-04-01-14]
- Dado un trader cuya orden con `clientOrderId = "k-1"` ya está `FILLED` (terminal)
- Cuando coloca una nueva orden con el mismo `clientOrderId = "k-1"`
- Entonces se rechaza con `DUPLICATE_CLIENT_ORDER_ID` (HTTP 409); la unicidad es permanente por cuenta (RN-15, RE-5)
- Y no se crea una segunda orden ni se reservan fondos

### Escenario 15 (rate limiting): Exceso de solicitudes [AT-04-01-15]
- Dado un trader que supera el límite de tasa configurado para el alta de órdenes (HU-09-*)
- Cuando envía una orden adicional por encima del límite
- Entonces se rechaza con `RATE_LIMITED` (HTTP 429), `details = { retryAfterSeconds }` (RN-16, RE-10)
- Y no se crea ninguna orden ni se reserva nada (se evalúa antes de la autenticación, RE-4 paso 0)

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-04-01-01 .. AT-04-01-15) pasan
- [ ] Reglas de negocio RN-1..RN-16 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md (floor en notional, sin floats)
- [ ] Sin violacion de invariantes globales (INV-1, INV-2, INV-3, INV-4, INV-7, INV-8)
- [ ] (si aplica) Adherencia verificada al estandar on-chain citado — N/A
