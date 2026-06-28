# HU-03-05 — Emisión de eventos de ejecución

- **Epica:** 03 — Motor de Matching
- **Actor / rol:** Sistema (motor de matching) / consumidores: settlement (épica 05), API
  WebSocket (épica 09), clientes (épicas 10/11)
- **Prioridad:** Alta
- **Dependencias:** HU-03-03 (matching limit), HU-03-04 (market), HU-03-01 (estructura);
  Épica 05 (consume los fills para liquidar y aporta los montos de fee), Épica 09
  (transporta los eventos). Épica 00 (fundaciones).
- **Estandares de dominio aplicables:** N/A (no on-chain). Aplica convenciones monetarias y
  de serialización de 00-fundaciones.

## Historia
Como motor de matching, quiero emitir, por cada cruce, eventos de ejecución (`trade` y
`order-update`) con precio, cantidad, lados, timestamp, secuencia y referencias, y
actualizar el estado del libro de forma consistente, para alimentar el settlement, el
market data en tiempo real y la trazabilidad determinista de la ejecución.

## Contexto y alcance
Esta HU define **qué eventos** produce el motor cuando ocurre un fill, **qué campos**
llevan, su **orden y secuencia** y su relación con la actualización del libro. Define la
forma lógica (campos y unidades) de los eventos; el **transporte** concreto (canales
WebSocket, esquema REST) lo fija la épica 09. El **cálculo de fees** se realiza en la épica
05; los eventos pueden transportar los montos de fee que la épica 05 produce, pero la
fórmula y el cobro pertenecen a 05. Posar una orden pasiva sin ejecución (HU-03-02) **no**
genera evento de `trade` (puede generar un `book-update` para market data).

## Reglas de negocio e invariantes
1. **RN-1 (un `trade` por cruce maker-taker).** Cada vez que el taker se cruza con **una**
   orden maker se emite **un** evento `trade`. Un taker que consume N makers genera **N**
   eventos `trade`, en el orden de prioridad en que se ejecutaron (HU-03-03 RN-2).
2. **RN-2 (campos del evento `trade`).** El evento `trade` contiene, como mínimo:
   - `tradeId`: identificador único y estable del trade (no se reutiliza).
   - `sequence`: número de **secuencia global** del motor, entero estrictamente monótono
     creciente, sin huecos ni repeticiones, que ordena todos los eventos.
   - `pair`: `"ETH/USDC"`.
   - `priceMin`: precio de ejecución = **precio del maker** (string entero, USDC-min/ETH).
   - `quantityWei`: cantidad base ejecutada (string entero, wei).
   - `quoteAmountMin`: `floor(quantityWei × priceMin / 10^18)` (string entero, USDC-min).
   - `makerOrderId`, `takerOrderId`.
   - `makerSide`, `takerSide` ∈ `{BUY, SELL}` (opuestos entre sí).
   - `makerAccountId`, `takerAccountId` (exposición externa la regula la épica 09).
   - `timestamp`: instante del fill (no se usa para aritmética monetaria).
3. **RN-3 (serialización entera).** Todo monto/precio/cantidad del evento se serializa como
   **string de entero** de unidad mínima, patrón `^(0|[1-9][0-9]*)$`
   (`convenciones-monetarias.md`). Prohibido floats y prohibido número JSON para montos.
4. **RN-4 (consistencia de lados).** En todo `trade`, `makerSide` y `takerSide` son
   opuestos; si `takerSide = BUY` el taker recibe ETH y entrega USDC y viceversa. Esto fija
   el activo recibido por cada parte (insumo del cobro de fees en la épica 05).
5. **RN-5 (eventos `order-update`/fill por orden afectada).** Por cada `trade` se emiten
   actualizaciones de las **dos** órdenes afectadas (maker y taker), cada una con:
   `orderId`, `accountId`, `role ∈ {MAKER, TAKER}`, `lastFillQtyWei`, `lastFillPriceMin`,
   `cumulativeFilledWei`, `remainingWei`, `status` resultante, `tradeId` (referencia),
   `sequence`, `timestamp`. Los campos de fee (`feeAsset`, `feeAmountMin`/`feeAmountWei`)
   los completa la épica 05.
   - **Enum de `status`:** `OPEN` | `PARTIALLY_FILLED` | `FILLED` | `CANCELLED` | `REJECTED`
     (los cinco estados terminales/abiertos del glosario; incluye `REJECTED`, ver RN-13).
   - **Campo `reason` (opcional):** acompaña los estados terminales que no son `FILLED`,
     para distinguir el motivo sin cambiar el `status`. Valores:
     - en `CANCELLED`: `MARKET_EXHAUSTED` (remanente `MARKET` por libro agotado, HU-03-04
       RN-9 b) o `MARKET_BUDGET_EXHAUSTED` (remanente `MARKET BUY` por presupuesto, HU-03-04
       RN-9 c). La cancelación **explícita por el usuario** (`USER_CANCELLED`) la origina la
       épica 04, no el motor.
     - en `REJECTED`: el `code` del rechazo de matching (`SELF_TRADE_BLOCKED`,
       `MARKET_NO_LIQUIDITY`, `MARKET_BUDGET_INSUFFICIENT`).
   - Un `order-update` de rechazo (RN-13) o de cancelación de remanente `MARKET` **no** lleva
     `tradeId` propio (no nace de un `trade`); sí lleva `sequence` y `timestamp`.
6. **RN-6 (orden de emisión determinista).** Para cada cruce el orden de emisión es:
   `trade` → `order-update(maker)` → `order-update(taker)`. Entre cruces sucesivos de un
   mismo taker, los `trade` se emiten en el orden de ejecución. Toda la emisión es
   reproducible para la misma entrada (determinismo).
7. **RN-7 (monotonía y unicidad de `sequence` y `tradeId`).** `sequence` (contador de
   **eventos**: `trade` / `order-update` / `book-update`) es global, estrictamente creciente
   y **contiguo** (sin huecos ni repeticiones); `tradeId` es único. Tras un reinicio no se
   reutilizan valores ya emitidos (continúan desde el último persistido; HU-03-07). El
   `sequence` de eventos es un contador **independiente** del `seq` de prioridad de órdenes
   (HU-03-01 RN-5): posar una pasiva consume `seq` pero **no** `sequence`, y emitir eventos
   consume `sequence` pero **no** `seq` (README RT-2).
8. **RN-8 (acoplamiento con la actualización del libro — INV-4/INV-7).** La emisión del
   `trade` y la actualización del estado del libro (decremento de remanentes, retiro de
   makers agotados, posado del remanente del taker) ocurren de forma **atómica y
   consistente**: el estado del libro tras el evento refleja exactamente los fills emitidos;
   no hay evento sin efecto en el libro ni efecto en el libro sin su evento.
9. **RN-9 (idempotencia de consumo).** Un consumidor (settlement, market data) puede
   deduplicar por `tradeId`/`sequence`: reprocesar el mismo `tradeId` no debe duplicar el
   efecto. El motor no emite dos veces el mismo `tradeId`.
10. **RN-10 (conservación informada — INV-1).** Los montos del `trade`
    (`quantityWei`, `quoteAmountMin`) son los que la épica 05 usa para redistribuir sin
    crear ni destruir valor; el mismo `quoteAmountMin` aplica a ambas patas (antes de fees).
11. **RN-11 (sin trade al posar).** Posar una orden pasiva sin ejecución (HU-03-02) no
    emite `trade`; a lo sumo un `book-update`. Cancelaciones y altas administrativas las
    cubre la épica 04.
12. **RN-12 (evento `book-update`).** El motor produce un evento `book-update` —forma lógica;
    el transporte concreto lo fija la épica 09— **por cada nivel de precio afectado** cuando
    cambia la profundidad del libro al **posar** o **retirar/decrementar** órdenes. Campos
    mínimos:
    - `pair`: `"ETH/USDC"`.
    - `side` ∈ `{BUY, SELL}` (lado del nivel afectado).
    - `priceMin`: precio del nivel (string entero, USDC-min/ETH).
    - `aggregatedRemainingWei`: nueva profundidad **total** del nivel tras el cambio (suma de
      `remainingWei` de las órdenes del nivel; string entero, wei). Es `"0"` si el nivel
      quedó vacío.
    - `isNewLevel` (bool): el nivel no existía antes de esta operación.
    - `isLevelEmpty` (bool): el nivel quedó vacío y se elimina del lado.
    - `sequence`, `timestamp` (igual semántica que en `trade`).

    **Condición de emisión:** se emite **un** `book-update` por cada nivel cuya profundidad
    agregada cambió en la operación (inserción de pasiva, decremento por fill, retiro de
    maker agotado, descarte no aplica porque la `MARKET` no toca su propio lado). Posar una
    pasiva que crea o engrosa un nivel emite **exactamente uno** (RN-11). Un fill que
    consume varios niveles emite uno por nivel tocado. El contenido detallado del snapshot/
    diff de market data y su entrega pertenecen a la épica 09.
13. **RN-13 (`order-update` para rechazos de matching).** Cuando el motor **rechaza** una
    orden en la fase de matching (`SELF_TRADE_BLOCKED`, `MARKET_NO_LIQUIDITY`,
    `MARKET_BUDGET_INSUFFICIENT`), emite un `order-update` con `status = "REJECTED"`,
    `filledWei = 0`, `cumulativeFilledWei = "0"`, `remainingWei = quantityWei` original,
    `reason` = el `code` del rechazo, `sequence` y `timestamp`; **sin** `tradeId` y **sin**
    `trade` asociado. Este evento cierra el ciclo de vida de la orden para los consumidores
    (settlement, UI), evitando que la vean "pendiente" indefinidamente. Es el único caso en
    que un `order-update` se emite sin un `trade` previo además de la cancelación de remanente
    `MARKET` (RN-5).

## Criterios de aceptacion (DoD)

### Escenario 1: Un fill total emite un trade y dos order-updates [AT-03-05-01]
- Dado un maker `SELL 1 ETH @ 2000.00` (U2) y un taker entrante `BUY 1 ETH @ 2000.00` (U1)
- Cuando se ejecuta el cruce
- Entonces se emite un `trade` con `priceMin = "2000000000"`,
  `quantityWei = "1000000000000000000"`, `quoteAmountMin = "2000000000"`,
  `makerSide = "SELL"`, `takerSide = "BUY"`, `makerOrderId`/`takerOrderId` correctos (RN-2)
- Y se emiten dos `order-update`: maker (U2) `status = "FILLED"`, `remainingWei = "0"`;
  taker (U1) `status = "FILLED"`, `remainingWei = "0"` (RN-5)
- Y el orden de emisión es `trade`, `order-update(maker)`, `order-update(taker)` (RN-6)

### Escenario 2: Taker contra dos makers emite dos trades [AT-03-05-02]
- Dado asks A1 `SELL 0.5 ETH @ 2000.00` (`seq=1`) y A2 `SELL 0.5 ETH @ 2000.50` (`seq=2`)
- Cuando ingresa `BUY 1 ETH @ 2001.00`
- Entonces se emiten **dos** `trade` (RN-1): T1 (`priceMin="2000000000"`,
  `quantityWei="500000000000000000"`, `quoteAmountMin="1000000000"`) y T2
  (`priceMin="2000500000"`, `quantityWei="500000000000000000"`,
  `quoteAmountMin="1000250000"`)
- Y `sequence(T1) < sequence(T2)` y ambos `sequence` son contiguos respecto del resto (RN-7)
- Y los `order-update` del taker reflejan `cumulativeFilledWei` creciente:
  `"500000000000000000"` tras T1 y `"1000000000000000000"` (FILLED) tras T2 (RN-5)

### Escenario 3: Fill parcial — order-update con remanente [AT-03-05-03]
- Dado un maker `SELL 2 ETH @ 2000.00` y un taker `BUY 1 ETH @ 2000.00`
- Cuando se ejecuta el cruce
- Entonces el `order-update` del maker reporta `status = "PARTIALLY_FILLED"`,
  `cumulativeFilledWei = "1000000000000000000"`, `remainingWei = "1000000000000000000"`
- Y el `order-update` del taker reporta `status = "FILLED"`, `remainingWei = "0"` (RN-5)

### Escenario 4 (borde): Posar pasiva no emite trade, sí un book-update [AT-03-05-04]
- Dado un libro con `best_ask = 2001.00` y sin nivel `bids @ 2000.00`
- Cuando ingresa `BUY 1 ETH @ 2000.00` (no cruza, se posa — HU-03-02)
- Entonces **no** se emite ningún evento `trade` (RN-11)
- Y se emite **exactamente un** `book-update` con `side = "BUY"`, `priceMin = "2000000000"`,
  `aggregatedRemainingWei = "1000000000000000000"`, `isNewLevel = true`,
  `isLevelEmpty = false` (RN-12)
- Y si la `BUY` se hubiera agregado a un nivel ya existente, el `book-update` traería
  `isNewLevel = false` y `aggregatedRemainingWei` = profundidad previa + `1000000000000000000`

### Escenario 5 (borde): Serialización entera de todos los montos [AT-03-05-05]
- Dado cualquier `trade` emitido
- Cuando se inspeccionan sus campos monetarios (`priceMin`, `quantityWei`,
  `quoteAmountMin`)
- Entonces todos son strings que matchean `^(0|[1-9][0-9]*)$`, sin floats, sin notación
  científica, sin número JSON, sin ceros a la izquierda (RN-3)

### Escenario 6 (integridad): Unicidad de `tradeId` y `sequence` emitidos por el motor [AT-03-05-06]
- Dado el log completo de eventos que emite el motor al procesar una secuencia de **≥ 100**
  órdenes mixtas `LIMIT`/`MARKET`
- Cuando se inspecciona ese log
- Entonces **no** existen dos eventos `trade` con el mismo `tradeId`, y los `sequence` de
  todos los eventos forman una secuencia **estrictamente creciente y contigua** sin huecos ni
  repeticiones (RN-7, RN-9)
- Y el motor nunca emite dos veces el mismo `tradeId`
- Nota: la **deduplicación del consumidor** ante una reentrega del bus (épica 09) usa este
  `tradeId`/`sequence`, pero el comportamiento del consumidor se evalúa en la épica 09, no
  aquí (RN-9 garantiza la unicidad en origen)

### Escenario 7 (integridad): Estado del libro consistente con los eventos [AT-03-05-07]
- Dado un cruce que ejecuta `q_fill` contra un maker
- Cuando se emite su `trade` y se aplican los `order-update`
- Entonces el `remainingWei` del maker en el libro es exactamente
  `remaining_previo − q_fill`, y si llega a `0` el maker se retira del libro (RN-8, INV-7)
- Y no existe `trade` emitido cuyo efecto no esté reflejado en el libro ni cambio de libro
  sin su evento

### Escenario 8 (borde): order-update REJECTED por rechazo de matching [AT-03-05-08]
- Dado un libro cuyo **best ask** `SELL 1 ETH @ 2000.00` pertenece a la cuenta **U1**
  (`quantityWei` entrante `= "1000000000000000000"`)
- Cuando **U1** envía `BUY 1 ETH @ 2000.00` y el motor la rechaza por `SELF_TRADE_BLOCKED`
  (HU-03-06)
- Entonces se emite un `order-update` para la entrante con `status = "REJECTED"`,
  `cumulativeFilledWei = "0"`, `remainingWei = "1000000000000000000"`,
  `reason = "SELF_TRADE_BLOCKED"`, **sin** `tradeId` (RN-13)
- Y **no** se emite ningún `trade` (RN-13)

### Escenario 9 (borde): order-update CANCELLED tras agotar el libro en MARKET [AT-03-05-09]
- Dado un libro de asks con liquidez total `0.8 ETH` (A1 `SELL 0.5 ETH @ 2000.00`, A2
  `SELL 0.3 ETH @ 2000.50`)
- Cuando ingresa `MARKET BUY 1 ETH` con presupuesto suficiente y el remanente se descarta
  (HU-03-04 AT-03-04-03)
- Entonces, además de los `trade` de A1 y A2, se emite un `order-update` para el taker con
  `status = "CANCELLED"`, `cumulativeFilledWei = "800000000000000000"`,
  `remainingWei = "200000000000000000"`, `reason = "MARKET_EXHAUSTED"` (RN-5, RN-13)

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-*) pasan
- [ ] Reglas de negocio RN-1..RN-13 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md (montos como
      string entero; mismo `quoteAmountMin` por fill)
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md),
      en particular INV-1, INV-4, INV-7
- [ ] (si aplica) Adherencia verificada al estandar on-chain citado — N/A
