# HU-04-02 — Colocar orden market

- **Epica:** 04 — Gestión de Órdenes
- **Actor / rol:** Trader autenticado
- **Prioridad:** Alta
- **Dependencias:** HU-04-03 (validaciones), HU-04-05 (estados), HU-02-* (reserva/ledger),
  HU-03-* (matching, barrido del libro, `MARKET_NO_LIQUIDITY`, `SELF_TRADE_BLOCKED`).
  Fundaciones (00).
- **Estandares de dominio aplicables:** N/A (operación interna; sin interacción on-chain).

## Historia
Como **trader autenticado**, quiero **colocar una orden market indicando lado y, o bien la
cantidad de ETH, o bien el monto de USDC**, para **ejecutar de inmediato contra la mejor
liquidez disponible sin fijar un precio**, sabiendo que el sistema valida mis fondos y la
liquidez antes de ejecutar.

## Contexto y alcance
Cubre el alta de una orden `MARKET`: no lleva precio, ejecuta de inmediato contra el lado
opuesto del libro en prioridad precio-tiempo (HU-03-*) y **nunca descansa**
(comportamiento immediate-or-cancel: el remanente no ejecutado se descarta). Admite dos
formas de tamaño: por **cantidad de base** (`quantityWei`) o por **monto de quote**
(`quoteOrderQty`). Exactamente una de las dos debe estar presente.

Cubre validación, reserva de fondos previa, validación de liquidez y el estado final
(`FILLED`, `CANCELLED` con ejecución parcial, o `REJECTED` por falta de liquidez). No
cubre el barrido concreto del libro ni el settlement (HU-03-*/HU-05-*), ni el contrato de
la API (HU-09-*).

## Reglas de negocio e invariantes
1. **RN-1 (entrada).** Una orden market requiere `side ∈ {BUY, SELL}`, `type = MARKET`, y
   **exactamente uno** de `quantityWei` o `quoteOrderQty` (entero > 0). Si faltan ambos o
   están ambos ⇒ `VALIDATION_ERROR`. Si incluye `priceMin` ⇒ `PRICE_NOT_ALLOWED`. Acepta
   opcionalmente `clientOrderId`.
2. **RN-2 (sin tick; lot según forma).** Market no valida tick (no hay precio). Si se usa
   `quantityWei`, debe cumplir lot size: `quantityWei mod 10^14 == 0 ∧ quantityWei > 0`
   (si no, `INVALID_LOT_SIZE`). `quoteOrderQty` no está sujeto a lot ni a tick, pero debe
   ser entero positivo (`^(0|[1-9][0-9]*)$`, > 0).
3. **RN-3 (mínimo notional para market).** El notional estimado debe ser ≥ `10000000`
   (10 USDC), si no `BELOW_MIN_NOTIONAL`:
   - forma `quoteOrderQty`: el estimador es el propio `quoteOrderQty`.
   - forma `quantityWei`: el estimador es `floor(quantityWei × P / 10^18)`, con `P` el
     mejor precio del lado opuesto (best ask para BUY, best bid para SELL) al momento del
     alta. Si el lado opuesto está vacío, no hay precio de referencia: aplica RN-4
     (`MARKET_NO_LIQUIDITY`, la market se rechaza y queda `REJECTED` sin reservar).
4. **RN-4 (liquidez, precondición previa a fondos).** Si el lado opuesto del libro está
   **vacío**, la market no puede ejecutarse: se rechaza con `MARKET_NO_LIQUIDITY` (422) y
   queda `REJECTED`. Esta comprobación es de **solo lectura** y se evalúa **antes** de
   reservar fondos (RE-4 paso 6, antes del paso 7); por eso **nunca** se reserva nada y, ante
   libro vacío + fondos insuficientes, **prevalece** `MARKET_NO_LIQUIDITY` sobre
   `INSUFFICIENT_FUNDS`. La orden se persiste como `REJECTED` (RE-12; aparece en HU-04-07).
5. **RN-5 (reserva).** Antes de ejecutar se bloquea (RE-1), sobre un **snapshot atómico** del
   lado opuesto tomado al procesar el alta (mismo punto que RN-4, **antes** de bloquear
   fondos; sin dependencia circular: se lee el libro, se calcula `R`, y recién después se
   bloquea — ver RE-1 del README):
   - **BUY por `quoteOrderQty`:** `R = quoteOrderQty` USDC-min.
   - **BUY por `quantityWei`:** `R =` costo en quote de barrer los asks vigentes hasta
     `quantityWei` (snapshot): `R = Σ_niveles floor(wei_consumido_nivel × precio_nivel / 10^18)`.
   - **SELL por `quantityWei`:** `R = quantityWei` wei (ETH).
   - **SELL por `quoteOrderQty`:** `R =` base en wei necesaria para obtener `quoteOrderQty`
     de quote barriendo los bids vigentes (snapshot). Por cada nivel de bid a precio `P_bid`,
     los wei a vender para cubrir el quote restante son
     `q_nivel = ceil(quote_restante × 10^18 / P_bid)` (redondeo **hacia arriba** para no
     quedar corto por sub-unidad; `convenciones-monetarias.md §2.3`). `R` es la suma de los
     `q_nivel` (acotada por la liquidez del snapshot y por `disponible(ETH)`). **Terminación:**
     la orden se considera completa (`FILLED`) cuando se agota la base reservada por el
     snapshot (equivalente a haber vendido los wei necesarios); el quote recibido nunca es
     **menor** que `quoteOrderQty` cuando hay liquidez suficiente (puede excederlo en a lo
     sumo sub-unidad por nivel a causa del `ceil`), y todo sobrante de base no vendida se
     libera (RN-8).
   Requiere `disponible ≥ R` en el activo correspondiente; si no, `INSUFFICIENT_FUNDS`.
6. **RN-6 (fee no se reserva).** La reserva no incluye fee; la fee se cobra en el activo
   recibido por cada fill (HU-05-*). Ver RE-2.
7. **RN-7 (ejecución y descarte del remanente).** La market consume liquidez hasta
   completar su objetivo (`quantityWei` o `quoteOrderQty`) o agotar el lado opuesto. El
   objetivo no alcanzado **no descansa**: se descarta. Estado final:
   - objetivo completado ⇒ `FILLED`;
   - ejecución parcial y luego liquidez agotada ⇒ `CANCELLED` con `executedQty > 0`
     (remanente descartado);
   - cero ejecución por lado vacío ⇒ `REJECTED` con `MARKET_NO_LIQUIDITY`.
8. **RN-8 (liberación del sobrante).** Todo monto reservado no consumido (por mejor precio,
   por descarte del remanente o por redondeo del barrido) se **libera** a disponible
   (RE-3, INV-3).
9. **RN-9 (self-trade).** **Caso degenerado:** si **lo primero** que la market cruzaría es
   una orden **propia** (sin fills previos contra terceros), se rechaza con
   `SELF_TRADE_BLOCKED` (422); como la detección es posterior a la reserva (RE-4 paso 8 >
   paso 7), la reserva tomada se **revierte atómicamente** (`bloqueado −= R; disponible += R`),
   dejando los balances **idénticos** a los previos (INV-2, INV-3), y la orden se registra
   `REJECTED` (RE-12). **Caso con fills previos (STP en barrido):** si la market ejecuta
   contra terceros y luego encuentra una orden propia, el barrido **se detiene** allí (RE-11,
   *expire-taker*): los fills previos son **definitivos**, el remanente se descarta liberando
   su reserva (RN-8) y la orden termina `CANCELLED` con `executedQty > 0` (respuesta exitosa,
   no 422).
10. **RN-10 (idempotencia).** `clientOrderId` repetido ⇒ `DUPLICATE_CLIENT_ORDER_ID` (409),
    sin ejecutar ni reservar (RE-5).
11. **RN-11 (precedencia).** rate limiting → auth → esquema (incl. `PRICE_NOT_ALLOWED`, forma
    única de tamaño) → enums → reglas del par (`INVALID_LOT_SIZE`, `BELOW_MIN_NOTIONAL`) →
    idempotencia → **liquidez de market (lado opuesto vacío ⇒ `MARKET_NO_LIQUIDITY`, antes de
    fondos)** → fondos → barrido (`SELF_TRADE_BLOCKED`, con reserva revertida si aplica)
    (RE-4).
12. **RN-12 (invariantes).** Respeta INV-1, INV-2, INV-3, INV-4 (settlement atómico de
    cada fill, HU-05-*) e INV-8.
13. **RN-13 (serialización).** `quantityWei`, `quoteOrderQty`, reservas, ejecutado y fees
    como string `^(0|[1-9][0-9]*)$` (RE-8).
14. **RN-14 (cantidades reportadas).** `executedQty` se expresa siempre en **base** (wei) =
    suma de los `q_wei` de todos los fills (también para órdenes por `quoteOrderQty`). El
    quote efectivamente gastado (BUY) o recibido (SELL) se reporta en `executedQuoteQty`
    (USDC-min) `= Σ floor(q_fill × P_fill / 10^18)` (ver HU-04-05 RN-7 y HU-04-06/07).
15. **RN-15 (alcance de `clientOrderId`).** Unicidad **permanente por cuenta** (lifetime),
    aun tras estado terminal; dos cuentas distintas pueden reusar el mismo valor (RE-5).
16. **RN-16 (rate limiting).** Superar el límite ⇒ `RATE_LIMITED` (429,
    `details = { retryAfterSeconds }`), antes de auth (RE-4 paso 0, RE-10; HU-09-*), sin
    ejecutar ni reservar.

## Criterios de aceptación (DoD)

### Escenario 1: Compra market por monto que ejecuta totalmente [AT-04-02-01]
- Dado un trader autenticado con `disponible(USDC) = 5000000000`
- Y asks resting ajenos suficientes a `priceMin = 2000000000`
- Cuando coloca `side=BUY, type=MARKET, quoteOrderQty="2000000000"` (gastar 2000 USDC)
- Entonces se bloquean `R = 2000000000` USDC-min, la orden ejecuta como taker y queda `FILLED`
- Y todo USDC reservado no gastado (por mejor precio o redondeo) se libera a disponible (RN-8)
- Y `executedQty` reporta la **base** en wei comprada y `executedQuoteQty` el USDC efectivamente gastado (RN-14)
- Y no queda remanente descansando en el libro

### Escenario 2: Venta market por cantidad que ejecuta totalmente [AT-04-02-02]
- Dado un trader autenticado con `disponible(ETH) = 2000000000000000000` (2 ETH)
- Y bids resting ajenos suficientes a `priceMin = 1990000000`
- Cuando coloca `side=SELL, type=MARKET, quantityWei="1000000000000000000"` (vender 1 ETH)
- Entonces se bloquean `R = 1000000000000000000` wei, la orden ejecuta como taker y queda `FILLED`
- Y no queda remanente; la fee se cobra en USDC recibido (HU-05-*)

### Escenario 3 (feliz): Compra market por cantidad, sobrante reservado liberado [AT-04-02-03]
- Dado un trader autenticado con `disponible(USDC) = 5000000000`
- Y un ask resting ajeno por `1000000000000000000` wei a `priceMin = 1990000000`
- Cuando coloca `side=BUY, type=MARKET, quantityWei="1000000000000000000"` (comprar 1 ETH)
- Entonces el matching reserva el costo estimado del barrido y ejecuta `floor(10^18 × 1990000000 / 10^18) = 1990000000` USDC-min
- Y cualquier diferencia entre lo reservado y lo consumido se libera (RN-8, INV-3)
- Y la orden queda `FILLED`

### Escenario 4 (borde): Ejecución parcial por liquidez agotada ⇒ remanente descartado [AT-04-02-04]
- Dado un trader autenticado con `disponible(USDC) = 5000000000`
- Y un único ask resting ajeno por `400000000000000000` wei (0.4 ETH) a `priceMin = 2000000000`
- Cuando coloca `side=BUY, type=MARKET, quantityWei="1000000000000000000"` (comprar 1 ETH)
- Entonces ejecuta 0.4 ETH, agota la liquidez y el remanente (0.6 ETH) se **descarta** (no descansa)
- Y la orden queda `CANCELLED` con `executedQty = "400000000000000000"`
- Y el USDC reservado no consumido se libera a disponible (RN-8)

### Escenario 5a (error): Sin liquidez — BUY con asks vacíos [AT-04-02-05a]
- Dado un trader autenticado con `disponible(USDC) = 5000000000` y `bloqueado(USDC) = 0`
- Y el libro **sin asks** (lado opuesto de un BUY vacío)
- Cuando coloca `side=BUY, type=MARKET, quoteOrderQty="2000000000"`
- Entonces se rechaza con `MARKET_NO_LIQUIDITY` (HTTP 422) y la orden queda `REJECTED`
- Y `bloqueado(USDC) = 0` y `disponible(USDC) = 5000000000` quedan **intactos**: la comprobación es previa a fondos, no se reservó nada (RN-4, RE-4 paso 6)

### Escenario 5b (error): Sin liquidez — SELL con bids vacíos [AT-04-02-05b]
- Dado un trader autenticado con `disponible(ETH) = 2000000000000000000` y `bloqueado(ETH) = 0`
- Y el libro **sin bids** (lado opuesto de un SELL vacío)
- Cuando coloca `side=SELL, type=MARKET, quantityWei="1000000000000000000"`
- Entonces se rechaza con `MARKET_NO_LIQUIDITY` (HTTP 422) y la orden queda `REJECTED`
- Y `bloqueado(ETH) = 0` y `disponible(ETH) = 2000000000000000000` quedan **intactos** (RN-4)

### Escenario 6 (error): Market con precio especificado [AT-04-02-06]
- Dado un trader autenticado
- Cuando coloca `side=BUY, type=MARKET, quoteOrderQty="2000000000", priceMin="2000000000"`
- Entonces se rechaza con `PRICE_NOT_ALLOWED` (HTTP 422)
- Y no se reserva ni se ejecuta nada

### Escenario 7 (error): Ambos tamaños presentes [AT-04-02-07]
- Dado un trader autenticado
- Cuando coloca `side=BUY, type=MARKET, quantityWei="1000000000000000000", quoteOrderQty="2000000000"`
- Entonces se rechaza con `VALIDATION_ERROR` (HTTP 422), `details.issues` indica que se exige exactamente uno
- Y no se reserva ni se ejecuta nada

### Escenario 8 (error): Ningún tamaño presente [AT-04-02-08]
- Dado un trader autenticado
- Cuando coloca `side=BUY, type=MARKET` sin `quantityWei` ni `quoteOrderQty`
- Entonces se rechaza con `VALIDATION_ERROR` (HTTP 422)

### Escenario 9 (error): Fondos insuficientes [AT-04-02-09]
- Dado un trader autenticado con `disponible(USDC) = 1000000000`
- Cuando coloca `side=BUY, type=MARKET, quoteOrderQty="2000000000"`
- Entonces se rechaza con `INSUFFICIENT_FUNDS` (HTTP 422), `details = { asset:"USDC", required:"2000000000", available:"1000000000" }`
- Y no se ejecuta ni se mantiene reserva (INV-2)

### Escenario 10 (error): Monto por debajo del mínimo notional [AT-04-02-10]
- Dado un trader autenticado con fondos suficientes
- Cuando coloca `side=BUY, type=MARKET, quoteOrderQty="9999999"` (9.999999 USDC < 10 USDC)
- Entonces se rechaza con `BELOW_MIN_NOTIONAL` (HTTP 422), `details = { notionalMin:"9999999", minNotional:"10000000" }`
- Y no se reserva ni se ejecuta

### Escenario 11 (error): Cantidad fuera de lot size [AT-04-02-11]
- Dado un trader autenticado con fondos suficientes
- Cuando coloca `side=SELL, type=MARKET, quantityWei="50000000000000"` (0.00005 ETH, no múltiplo de 10^14)
- Entonces se rechaza con `INVALID_LOT_SIZE` (HTTP 422), `details = { quantityWei:"50000000000000", lotSize:"100000000000000" }`

### Escenario 12a (borde): Venta market por monto que completa el objetivo [AT-04-02-12a]
- Dado un trader autenticado con `disponible(ETH) = 2000000000000000000` (2 ETH)
- Y bids resting ajenos **suficientes** a `priceMin = 1500000000` (1500.00 USDC/ETH)
- Cuando coloca `side=SELL, type=MARKET, quoteOrderQty="2000000000"` (recibir ~2000 USDC vendiendo ETH)
- Entonces el matching reserva en ETH la base necesaria por snapshot: `q_nivel = ceil(2000000000 × 10^18 / 1500000000) = 1333333333333333334` wei (RN-5)
- Y ejecuta esa base; el USDC recibido es `executedQuoteQty = floor(1333333333333333334 × 1500000000 / 10^18) = 2000000000` (= objetivo; el `ceil` agregó 1 wei de base para no quedar corto)
- Y la orden queda `FILLED` con `executedQty = "1333333333333333334"`; el sobrante de ETH reservado no vendido (si lo hubiera) se libera (RN-8)

### Escenario 12b (borde): Venta market por monto con liquidez insuficiente [AT-04-02-12b]
- Dado un trader autenticado con `disponible(ETH) = 2000000000000000000`
- Y un **único** bid resting ajeno por `400000000000000000` wei (0.4 ETH) a `priceMin = 1500000000`
- Cuando coloca `side=SELL, type=MARKET, quoteOrderQty="2000000000"`
- Entonces el snapshot solo cubre 0.4 ETH: se reserva `R = 400000000000000000` wei, se vende todo, se agota la liquidez y el remanente del objetivo se **descarta**
- Y la orden queda `CANCELLED` con `executedQty = "400000000000000000"` y `executedQuoteQty = floor(400000000000000000 × 1500000000 / 10^18) = "600000000"` (RN-7, RN-14)
- Y el ETH reservado no vendido se libera a disponible (RN-8)

### Escenario 13 (error): Self-trade en market, caso degenerado [AT-04-02-13]
- Dado un trader autenticado con `disponible(ETH) = 2000000000000000000`, `bloqueado(ETH) = 0`, y un bid **propio** resting como **única** liquidez del lado opuesto
- Cuando coloca `side=SELL, type=MARKET, quantityWei="1000000000000000000"` que cruzaría su propio bid como primera liquidez
- Entonces se rechaza con `SELF_TRADE_BLOCKED` (HTTP 422), `details = { restingOrderId }`
- Y la reserva tomada se **revierte atómicamente**: `disponible(ETH) = 2000000000000000000`, `bloqueado(ETH) = 0` (idénticos a los previos, RN-9, INV-3)
- Y la orden se registra como `REJECTED` (RE-12)

### Escenario 14 (borde): Self-trade tras fills previos detiene el barrido (STP) [AT-04-02-14]
- Dado un trader autenticado con `disponible(ETH) = 2000000000000000000`
- Y dos bids cruzables a `priceMin = 2000000000`: el primero **ajeno** por `400000000000000000` wei (0.4 ETH) y el segundo **propio** por `600000000000000000` wei
- Cuando coloca `side=SELL, type=MARKET, quantityWei="1000000000000000000"` (vender 1 ETH)
- Entonces ejecuta 0.4 ETH contra el bid ajeno (fill **definitivo**) y, al encontrar su propio bid, **detiene** el barrido (RN-9, RE-11)
- Y el remanente `600000000000000000` wei se **descarta** y su reserva se libera (RN-8)
- Y la orden queda `CANCELLED` con `executedQty = "400000000000000000"`; la respuesta es exitosa (no 422)

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-04-02-01 .. AT-04-02-14, incluidos 05a/05b y 12a/12b) pasan
- [ ] Reglas de negocio RN-1..RN-16 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md (floor en notional/barrido, sin floats)
- [ ] Sin violacion de invariantes globales (INV-1, INV-2, INV-3, INV-4, INV-8)
- [ ] (si aplica) Adherencia verificada al estandar on-chain citado — N/A
