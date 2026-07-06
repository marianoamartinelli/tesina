# HU-03-04 — Ejecución de orden market

- **Epica:** 03 — Motor de Matching
- **Actor / rol:** Trader autenticado (dispara el alta) / Sistema (motor de matching)
- **Prioridad:** Alta
- **Dependencias:** HU-03-01 (estructura), HU-03-03 (mecánica de cruce reutilizada),
  HU-03-06 (auto-cruce), HU-03-05 (eventos); Épica 02 (fondos), Épica 04 (validación de
  entrada y reserva), Épica 05 (settlement). Épica 00 (fundaciones).
- **Estandares de dominio aplicables:** N/A (no on-chain). Aplica prioridad precio-tiempo y
  convenciones monetarias de 00-fundaciones.

## Historia
Como trader autenticado, quiero enviar una orden `MARKET` (sin precio límite) que consuma
liquidez del lado opuesto al mejor precio disponible hasta completar mi cantidad o agotar
el libro, para ejecutar de inmediato sin tener que fijar un precio.

## Contexto y alcance
Esta HU define la ejecución de una orden `MARKET`: siempre es **taker**, **no** tiene
precio límite, **no** descansa nunca en el libro y su remanente no ejecutado se **descarta**
(no se posa). Reutiliza el recorrido por prioridad precio-tiempo de HU-03-03, removiendo la
condición de precio (cualquier nivel del lado opuesto es cruzable). Cubre: ejecución total,
ejecución parcial por libro insuficiente, libro vacío (sin liquidez), y el límite por
**presupuesto reservado** para `MARKET BUY`. La validación de entrada (`type`, ausencia de
precio → `PRICE_NOT_ALLOWED` si se envía precio; lot size; mínimo notional estimado) la
realiza la épica 04; la reserva de fondos, la épica 02; las fees y el settlement, la épica
05.

La orden `MARKET` llega al motor con una **cantidad base objetivo** `quantityWei` (ETH,
wei) —la de la forma por cantidad, o la base que la épica 04 **precomputa** sobre el
snapshot para un `MARKET SELL` por monto (HU-04-02 RN-5)— y, para un `MARKET BUY`, un
**presupuesto en quote** `B` (USDC-min) reservado por la épica 02/04 que acota la
ejecución (no se puede gastar más quote del reservado). Un `MARKET BUY` **por monto**
(`quoteOrderQtyMin`, HU-04-02) llega **sin** cantidad objetivo: su única cota es `B`.

## Reglas de negocio e invariantes
1. **RN-1 (siempre taker, sin precio).** Una `MARKET` no lleva `price_min`. Si el payload
   incluye precio, la épica 04 la rechaza con `PRICE_NOT_ALLOWED` (no llega al motor). La
   `MARKET` siempre consume liquidez (taker), nunca la provee.
2. **RN-2 (cruzabilidad sin condición de precio).** Una `MARKET BUY` cruza contra **todos**
   los asks existentes; una `MARKET SELL` contra **todos** los bids existentes. No hay
   filtro de precio: cualquier nivel del lado opuesto es cruzable.
3. **RN-3 (recorrido por prioridad precio-tiempo).** Se consume el lado opuesto desde el
   mejor precio (ask más bajo para BUY; bid más alto para SELL) y, dentro de un nivel,
   **FIFO por `seq`** (HU-03-01 RN-6, HU-03-03 RN-2).
4. **RN-4 (precio y cantidad por fill).** Igual que HU-03-03: precio de ejecución = precio
   del **maker**; `q_fill = min(remaining_taker_wei, remaining_maker_wei)`;
   `quote_min = floor(q_fill × maker_price_min / 10^18)` (`floor`, enteros, sin floats).
5. **RN-5 (presupuesto en quote para BUY).** Para `MARKET BUY`, la ejecución está acotada
   por el presupuesto reservado `B` (USDC-min). Antes de aplicar un fill por `q_fill` a
   `maker_price_min`, su `quote_min` debe poder pagarse con el presupuesto remanente
   `B_rem`. Si el `quote_min` del siguiente maker completo no entra en `B_rem`, el motor
   toma del maker la **máxima cantidad** `q'` que sea múltiplo del lot size (`10^14` wei) y
   cuyo `quote_min = floor(q' × maker_price_min / 10^18)` no exceda `B_rem`. La cantidad se
   deriva con la **fórmula directa** (todos los operandos son big integers):

   ```
   max_lots = floor( B_rem × 10^18 / (maker_price_min × lot_size) )
   q'       = max_lots × lot_size          (lot_size = 10^14)
   ```

   Esta fórmula garantiza que `q'` es el mayor múltiplo de `lot_size` cuyo `quote_min` no
   excede `B_rem` (el siguiente lot ya lo excedería). Si `max_lots = 0` (ni 1 lot entra), la
   ejecución se detiene sin tomar nada de ese maker.

   *Verificación:* `B_rem = 500000000`, `maker_price_min = 2000500000`, `lot_size = 10^14`
   ⇒ `max_lots = floor(500000000 × 10^18 / (2000500000 × 10^14)) = 2499` ⇒
   `q' = 249900000000000000`, `quote_min = floor(q' × 2000500000 / 10^18) = 499924950 ≤
   500000000` (el lot 2500 daría `500125000 > 500000000`).
6. **RN-6 (condición de fin).** El cruce termina cuando ocurre lo primero de: (a)
   `remaining_taker_wei = 0` (cantidad objetivo completa; no aplica a un `MARKET BUY` por
   monto, que no lleva cantidad objetivo), (b) el lado opuesto queda **vacío** (libro
   agotado), o (c) para BUY, el presupuesto `B` no alcanza para tomar ni 1 lot más (RN-5).
7. **RN-7 (no descansa; remanente se descarta).** Una `MARKET` **nunca** se posa en el
   libro (HU-03-01 RN-7). El remanente no ejecutado por agotamiento de libro o presupuesto
   se **descarta** (no se rest-ea, no se reintenta).
8. **RN-8 (libro opuesto vacío → sin liquidez).** Si al ingresar la `MARKET` el lado
   opuesto está **vacío** (no hay ninguna orden), no puede ejecutarse: se rechaza con
   `MARKET_NO_LIQUIDITY` (422), terminal `REJECTED`, **cero fills**. La reserva de fondos se
   libera íntegra (épica 02). (Precedencia: paso 7 de `modelo-de-errores.md` §4.)
9. **RN-9 (estados resultantes — objetivo precomputado; el ciclo de vida lo fija la
   épica 04, HU-04-02 RN-7).** El **objetivo efectivo** de una `MARKET` queda fijado al
   admitirla (épica 04, sobre el mismo snapshot con el que se calcula la reserva,
   HU-04-02 RN-5): en las formas **por cantidad** —incluido el `MARKET SELL` por monto,
   cuya base precomputada llega al motor como `quantityWei`— el objetivo es esa cantidad
   base; en un `MARKET BUY` **por monto** (`quoteOrderQtyMin`) el objetivo es **agotar el
   presupuesto `B`** (ejecutar hasta que `B_rem` no alcance para tomar ni 1 lot más,
   RN-5, RN-6 c). Estados:
   - `FILLED` si el objetivo se ejecuta **completo**: `remaining_taker_wei = 0` en las
     formas por cantidad; o, en `MARKET BUY` por monto, detención por RN-6 c con
     `filledWei > 0` (presupuesto agotado = objetivo completado; el residuo sub-lot de `B`
     se libera, RN-10). En este caso el `order-update` **no** lleva `reason` (HU-03-05
     RN-5).
   - Si se ejecutó **parte** del objetivo (`filledWei > 0`) y la ejecución se detuvo
     **antes** de completarlo: el remanente se descarta y la orden queda en estado terminal
     `CANCELLED`. El `order-update` reporta `reason` distinguiendo el motivo:
     `MARKET_EXHAUSTED` si el lado opuesto se agotó (RN-6 b) o `MARKET_BUDGET_EXHAUSTED` si
     una orden **por cantidad** se detuvo por presupuesto (RN-6 c) antes de completar su
     cantidad objetivo (caso defensivo: bajo HU-04-02 RN-5 la reserva de la forma por
     cantidad cubre el costo del barrido del snapshot, pero el motor no asume esa
     validación previa, RN-14). Si ambas condiciones se alcanzan en el mismo punto,
     prevalece `MARKET_EXHAUSTED`. **No** es un error HTTP (hubo ejecución); ver HU-03-05
     RN-5.
   - `REJECTED` con `MARKET_NO_LIQUIDITY` (422) solo en el caso de cero liquidez: lado
     opuesto **vacío** (RN-8), `filledWei = 0`.
   - `REJECTED` con `MARKET_BUDGET_INSUFFICIENT` (422) para `MARKET BUY` cuando el lado
     opuesto **no** está vacío pero el presupuesto `B` **no alcanza para ejecutar ni 1 lot**
     del mejor maker disponible (`max_lots = 0` desde el inicio, RN-5), de modo que
     `filledWei = 0`. Se distingue de `MARKET_NO_LIQUIDITY` (sí hay liquidez) y del
     `CANCELLED` (que exige `filledWei > 0`). La reserva se libera **íntegra**.
     `details = { budgetMin: B, requiredMin: quote_min de 1 lot del best ask }`.
     (Caso defensivo: normalmente la épica 04 lo evita por `BELOW_MIN_NOTIONAL` al admitir;
     el motor debe ser determinista igual y no asumir esa validación previa.)
   - Cada maker tocado: `FILLED` o `PARTIALLY_FILLED` igual que HU-03-03 RN-9.
10. **RN-10 (atomicidad y conservación — INV-4, INV-1).** Cada fill (con su settlement,
    épica 05) es atómico; el conjunto de fills solo redistribuye fondos (no cambia
    `Σ total(·, A)`). El presupuesto/reserva no consumido se libera (bloqueado→disponible).
11. **RN-11 (no-cruce final — INV-7).** Como la `MARKET` no se posa, el libro no puede
    quedar cruzado por su causa; el lado propio no recibe orden nueva.
12. **RN-12 (auto-cruce).** Si la `MARKET` fuese a matchear contra una orden de la misma
    cuenta, se aplica HU-03-06 (self-trade prevention). Ver HU-03-06.
13. **RN-13 (mínimo notional de market).** El control de mínimo notional (10 USDC) para
    `MARKET` lo realiza la épica 04 al admitir la orden (estimación con el mejor precio
    disponible y/o cantidad mínima de 1 lot), según `activos-y-par-de-trading.md` §4.4; el
    motor no re-valida el mínimo notional, solo ejecuta.
14. **RN-14 (presupuesto `B` como entrada del motor).** El presupuesto `B` (USDC-min) de un
    `MARKET BUY` lo **calcula y reserva** la épica 04/02 al admitir la orden (la fórmula de
    `B` pertenece a esas épicas); el motor lo **recibe como parámetro de entrada** junto con
    la orden y lo trata como el **techo de gasto** en USDC-min. El motor **no** recalcula ni
    revalida `B`: solo verifica que cada `quote_min` ejecutado no haga superar `B`
    acumulado (RN-5). Un `MARKET SELL` **no** lleva presupuesto en quote (bloquea base): su
    única cota es la cantidad `quantityWei` y la liquidez del libro.

## Criterios de aceptacion (DoD)

### Escenario 1: MARKET SELL ejecuta total contra varios bids [AT-03-04-01]
- Dado un libro de bids: B1 `BUY 0.6 ETH @ 2000.00` (`seq=1`), B2 `BUY 0.5 ETH @ 1999.50`
  (`seq=2`)
- Cuando ingresa `MARKET SELL 1 ETH` (`quantityWei = 1000000000000000000`)
- Entonces consume B1 (0.6 ETH @ **2000.00**, `quote_min = "1200000000"`) y luego B2
  (0.4 ETH @ **1999.50**, `quote_min = "799800000"`) por prioridad descendente (RN-2, RN-3)
- Y el taker queda `FILLED`; B1 `FILLED` (se retira); B2 `PARTIALLY_FILLED` con
  `remainingWei = "100000000000000000"` (0.1 ETH)

### Escenario 2: MARKET BUY ejecuta total contra varios asks [AT-03-04-02]
- Dado un libro de asks: A1 `SELL 1 ETH @ 2000.00`, A2 `SELL 1 ETH @ 2000.50`, y presupuesto
  reservado `B = 4001 USDC = "4001000000"`
- Cuando ingresa `MARKET BUY 2 ETH` (`quantityWei = 2000000000000000000`)
- Entonces consume A1 (1 ETH @ **2000.00**, `quote_min = "2000000000"`) y A2 (1 ETH @
  **2000.50**, `quote_min = "2000500000"`); costo total `"4000500000"` ≤ `B` (RN-4, RN-5)
- Y el taker queda `FILLED`; el excedente del presupuesto `B − 4000500000 = "500000"` se
  libera (RN-10)

### Escenario 3 (borde): MARKET parcial por libro agotado [AT-03-04-03]
- Dado un libro de asks con liquidez total `0.8 ETH`: A1 `SELL 0.5 ETH @ 2000.00`, A2
  `SELL 0.3 ETH @ 2000.50`
- Cuando ingresa `MARKET BUY 1 ETH` con presupuesto suficiente
- Entonces ejecuta `0.8 ETH` (A1 y A2 completos) y el remanente `0.2 ETH` **se descarta**
  (no se posa, RN-7)
- Y la orden queda terminal `CANCELLED` con `filledWei = "800000000000000000"` (RN-9), sin
  error HTTP (hubo ejecución)
- Y se emite un `order-update` para el taker con `status = "CANCELLED"`,
  `cumulativeFilledWei = "800000000000000000"`, `remainingWei = "200000000000000000"` y
  `reason = "MARKET_EXHAUSTED"` (RN-9, HU-03-05 RN-5)
- Y la reserva no consumida se libera (RN-10)

### Escenario 4 (error): MARKET sin liquidez (lado opuesto vacío) [AT-03-04-04]
- Dado un libro con `asks` vacío
- Cuando ingresa `MARKET BUY 1 ETH`
- Entonces se rechaza con `MARKET_NO_LIQUIDITY` (HTTP 422), terminal `REJECTED`, cero fills
  (RN-8)
- Y la reserva de fondos se libera íntegra; balances intactos (INV-2, INV-3)

### Escenario 5 (borde): MARKET BUY detenida por presupuesto [AT-03-04-05]
- Dado un libro de asks: A1 `SELL 1 ETH @ 2000.00` (1 ETH), A2 `SELL 1 ETH @ 2000.50`
- Cuando ingresa una `MARKET BUY` **por monto** con `quoteOrderQtyMin = "2500000000"`
  (2500 USDC; presupuesto reservado `B = "2500000000"`, HU-04-02 RN-5)
- Entonces ejecuta A1 (1 ETH @ 2000.00, `quote_min = "2000000000"`); del presupuesto quedan
  `B_rem = "500000000"` (500 USDC)
- Y de A2 toma la máxima cantidad múltiplo de lot cuyo `quote_min ≤ 500000000`: `0.2499 ETH`
  (`q' = 249900000000000000`, `quote_min = floor(q' × 2000500000 / 10^18) = "499924950"` ≤
  500000000) (RN-5)
- Y la ejecución se detiene por presupuesto (RN-6 c) con el **objetivo completado** (agotar
  `B`): la orden queda terminal **`FILLED`** con `filledWei = "1249900000000000000"`, quote
  gastado `2000000000 + 499924950 = "2499924950"` y el residuo sub-lot `"75050"` liberado
  (RN-9, RN-10, HU-04-02 RN-7)
- Y A2 **permanece** en el libro con `status = "PARTIALLY_FILLED"`,
  `remainingWei = "750100000000000000"` (1 ETH − `q'`), conservando su `seq` original y su
  posición como best ask del nivel `@ 2000.50`
- Y se emite un `order-update` para el taker con `status = "FILLED"`,
  `cumulativeFilledWei = "1249900000000000000"` y **sin** `reason` (el objetivo se
  completó, RN-9, HU-03-05 RN-5)

### Escenario 6 (borde): precio enviado en MARKET es rechazado antes del motor [AT-03-04-06]
- Dado un cliente que envía `MARKET BUY 1 ETH` con un `price` presente
- Cuando la épica 04 valida el payload
- Entonces se rechaza con `PRICE_NOT_ALLOWED` (422) y la orden **no** llega al motor (RN-1)

### Escenario 7 (borde): MARKET de 1 lot exacto contra liquidez suficiente [AT-03-04-07]
- Dado un libro con `best_ask = 100000.00` (`price_min = 100000000000`, múltiplo de tick) y
  profundidad ≥ 1 lot; a ese precio 1 lot vale exactamente el mínimo notional
  (`floor(10^14 × 100000000000 / 10^18) = 10000000` = 10 USDC), por lo que la épica 04
  admite la orden (RN-13, HU-04-02 RN-3)
- Cuando ingresa `MARKET BUY 0.0001 ETH` (`quantityWei = 100000000000000` = 1 lot) con
  presupuesto suficiente
- Entonces ejecuta `q_fill = 100000000000000` a `100000.00`,
  `quote_min = floor(10^14 × 100000000000 / 10^18) = "10000000"` y queda `FILLED` (RN-4)

### Escenario 8 (error): auto-cruce de una MARKET [AT-03-04-08]
- Dado que el único ask del libro pertenece a la **misma cuenta** que envía la `MARKET BUY`
- Cuando el motor evalúa el cruce
- Entonces aplica HU-03-06 y rechaza con `SELF_TRADE_BLOCKED` (422), sin fills (RN-12;
  detalle en HU-03-06)

### Escenario 9 (error): MARKET BUY sin presupuesto para ni 1 lot [AT-03-04-09]
- Dado un libro con best ask A1 `SELL 1 ETH @ 2000.00` (de U2), y un `MARKET BUY` de U1
  cuyo presupuesto entregado al motor es `B = "100000"` (0.1 USDC)
- Y que el costo de **1 lot** del best ask es `floor(10^14 × 2000000000 / 10^18) = "200000"`
  USDC-min, mayor que `B`
- Cuando el motor evalúa la ejecución (`max_lots = floor(100000 × 10^18 / (2000000000 ×
  10^14)) = 0`, RN-5)
- Entonces no ejecuta nada (`filledWei = 0`) y rechaza con `MARKET_BUDGET_INSUFFICIENT`
  (HTTP 422), terminal `REJECTED`, `details = { budgetMin: "100000", requiredMin: "200000" }`
  (RN-9)
- Y la reserva se libera **íntegra**; el libro queda intacto (A1 sin tocar); balances
  idénticos (INV-2, INV-3)
- Y **no** se reporta `MARKET_NO_LIQUIDITY` (sí hay liquidez, solo que el presupuesto no la
  cubre)
- Y el error aplica **sea de quien sea** la liquidez del lado opuesto: con `max_lots = 0` el
  rango consumible es vacío y no hay STP que evaluar (HU-03-06 RN-2/RN-4)
- Nota: caso defensivo de determinismo; normalmente la épica 04 lo evita por
  `BELOW_MIN_NOTIONAL` al admitir (RN-9)

### Escenario 10 (error): MARKET con mezcla de liquidez propia y de terceros [AT-03-04-10]
- Dado asks: A1 `SELL 0.5 ETH @ 2000.00` de **U2** (`seq=1`) y A2 `SELL 0.5 ETH @ 2000.00`
  de **U1** (`seq=2`, `orderId = A2`)
- Cuando **U1** envía `MARKET BUY 1 ETH` (rango consumible = {A1, A2}, presupuesto
  suficiente)
- Entonces, como A2 (propia) cae dentro del rango consumible, se rechaza **toda** la entrante
  con `SELF_TRADE_BLOCKED` (422), `details.restingOrderId = "A2"`, **sin** fills (RN-12,
  HU-03-06 RN-7)
- Y A1 (de tercero) **tampoco** se ejecuta; el libro queda idéntico (atomicidad, INV-4)

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-*) pasan
- [ ] Reglas de negocio RN-1..RN-14 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md
      (`MARKET_NO_LIQUIDITY`, `MARKET_BUDGET_INSUFFICIENT`, `PRICE_NOT_ALLOWED`,
      `SELF_TRADE_BLOCKED`)
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md (floor, sin
      floats, big integers)
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md),
      en particular INV-1, INV-4, INV-7
- [ ] (si aplica) Adherencia verificada al estandar on-chain citado — N/A
