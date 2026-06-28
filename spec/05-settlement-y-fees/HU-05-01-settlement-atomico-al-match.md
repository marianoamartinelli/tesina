# HU-05-01 — Settlement atómico al match

- **Epica:** 05 — Settlement y Fees
- **Actor / rol:** Sistema (motor de settlement, disparado por el evento de fill de la épica 03)
- **Prioridad:** Alta
- **Dependencias:** HU-03-* (eventos de ejecución / fills, precio de ejecución), HU-02-* (balances disponible/bloqueado, ledger de doble entrada, cuenta EX), HU-04-* (estados de orden, bloqueo inicial de fondos), HU-05-02 (cálculo de fees aplicado dentro del mismo settlement)
- **Estandares de dominio aplicables:** N/A (settlement interno/contable; no es on-chain)

## Historia
Como **sistema de liquidación**, quiero **aplicar de forma atómica el intercambio de base
(ETH) y quote (USDC) entre comprador y vendedor cada vez que se produce un fill, ajustando
`disponible` y `bloqueado` de ambas cuentas y de la cuenta de fees del exchange**, para
**que cada ejecución redistribuya valor sin crearlo ni destruirlo, sin dejar estados
parciales observables y preservando la conservación de fondos**.

## Contexto y alcance
Esta HU cubre la **mecánica contable atómica** de un fill ya decidido por el motor de
matching: dado un evento de fill con contrapartes, cantidad matcheada `q_wei` y precio de
ejecución `price_min` (= precio de la orden **maker/resting**, por prioridad
precio-tiempo, INV-7), se consume el `bloqueado` de cada parte, se acredita el `disponible`
de la contraparte en el activo opuesto, se cobran las fees (cuyo cálculo detalla HU-05-02)
y se libera el surplus de `bloqueado` por mejora de precio del taker. Todo se aplica
**todo o nada** (INV-4).

**No** cubre: la selección de qué órdenes cruzan ni el cálculo del precio (épica 03), el
bloqueo inicial de fondos al crear la orden (épica 04), las fórmulas de fee en detalle
(HU-05-02, aquí se referencian), ni el formato del registro de trade (HU-05-03). Supuesto:
las órdenes ya pasaron validación y self-trade ya fue bloqueado **antes** del fill
(`SELF_TRADE_BLOCKED`, épica 03), por lo que comprador y vendedor son **cuentas distintas**.

## Reglas de negocio e invariantes

1. **RN-1 (disparador y datos del fill).** El settlement se ejecuta una vez por cada evento
   de fill emitido por el matching (épica 03). El evento aporta:
   - `tradeId` / `sequence` — **identidad estable del fill y clave de idempotencia**,
     asignada por el matching en orden de producción (ver HU-05-03 RN-2/RN-3). `tradeId` es
     el **mismo** a través de redelivery/reintentos del evento.
   - `buyerAccountId`, `sellerAccountId` — cuentas contraparte (distintas, RN-12).
   - `makerOrderId`, `takerOrderId` — órdenes cruzadas.
   - `takerSide` ∈ {`BUY`, `SELL`} — lado de la orden taker; `makerSide` es el opuesto.
   - `takerOrderType` ∈ {`LIMIT`, `MARKET`} — tipo de la orden taker; determina el
     tratamiento del surplus (RN-6).
   - `q_wei` — cantidad base matcheada (> 0, múltiplo de `10^14`).
   - `price_min` — precio de ejecución (= precio de la orden **maker**; > 0, múltiplo de
     `10^4`).
   - `price_limit_taker` — precio límite de la orden taker, **presente si y solo si**
     `takerSide = BUY` y `takerOrderType = LIMIT` (múltiplo de `10^4`, `≥ price_min`); es el
     insumo del cálculo de surplus de RN-6. Para `takerOrderType = MARKET` **no** existe
     `price_limit_taker`.
2. **RN-2 (precio de ejecución = precio maker).** El settlement liquida al `price_min` de
   la orden **maker (resting)**, nunca al límite del taker. El taker puede recibir **mejora
   de precio** respecto de su límite.
3. **RN-3 (notional compartido).** `quote_min = floor(q_wei × price_min / 10^18)`,
   calculado como big integer (multiplicar antes de dividir; una sola división; `floor`).
   El **mismo** `quote_min` es lo que paga el comprador y lo que recibe el vendedor (antes
   de fees), de modo que el redondeo no crea ni destruye valor (INV-1, convenciones §2.2).
4. **RN-4 (transferencia de base, ETH).** El vendedor entrega `q_wei` desde su `bloqueado`
   de ETH; el comprador recibe `q_wei − fee_base` en su `disponible` de ETH; `fee_base` se
   acredita al `disponible` de ETH de la cuenta EX. (`fee_base` por HU-05-02.)
   - `bloqueado(vendedor, ETH) −= q_wei`
   - `disponible(comprador, ETH) += (q_wei − fee_base)`
   - `disponible(EX, ETH) += fee_base`
5. **RN-5 (transferencia de quote, USDC).** El comprador entrega `quote_min` desde su
   `bloqueado` de USDC; el vendedor recibe `quote_min − fee_quote` en su `disponible` de
   USDC; `fee_quote` se acredita al `disponible` de USDC de la cuenta EX.
   - `bloqueado(comprador, USDC) −= quote_min`
   - `disponible(vendedor, USDC) += (quote_min − fee_quote)`
   - `disponible(EX, USDC) += fee_quote`
6. **RN-6 (liberación de surplus por mejora de precio del taker comprador LIMIT).** El
   surplus se libera **solo** cuando el **comprador es taker con orden LIMIT**
   (`takerSide = BUY` **y** `takerOrderType = LIMIT`) y su precio límite
   `price_limit_taker > price_min`. En ese caso, el exceso bloqueado para esta porción se
   libera:
   - `surplus = floor(q_wei × price_limit_taker / 10^18) − quote_min`
   - `bloqueado(comprador, USDC) −= surplus`; `disponible(comprador, USDC) += surplus`.
   - **Exactitud (sin dust):** por las mismas restricciones de tick (`price_limit_taker`
     múltiplo de `10^4`) y lot (`q_wei` múltiplo de `10^14`), el producto
     `q_wei × price_limit_taker` es divisible por `10^18` **sin residuo**, por lo que
     `floor(q_wei × price_limit_taker / 10^18)` es un **entero exacto** (mismo argumento que
     para `quote_min`, RN-3): el surplus no sufre error de redondeo y la suma de surpluses
     de los fills parciales de una orden LIMIT agota **exactamente** el `bloqueado` original
     al completarse la orden.
   - **Taker comprador MARKET (`takerOrderType = MARKET`):** no hay `price_limit_taker`; el
     settlement del fill **solo consume `quote_min`** de `bloqueado(comprador, USDC)` y
     **no libera surplus por fill**. La liberación del excedente total de `bloqueado`
     (estimado al alta por la épica 04, p. ej. por mejor ask) es **responsabilidad de la
     épica 04** al completarse o cancelarse la orden, **no** de esta épica.
   - **Taker vendedor (taker SELL, LIMIT o MARKET):** no aplica surplus en quote: el
     vendedor bloquea ETH `= q_wei` (o, en market, ETH = cantidad de la orden, consumida
     exacta a lo largo de los fills), que se consume exacto; no genera surplus en esta
     épica.
7. **RN-7 (atomicidad — INV-4).** Todos los asientos de RN-4, RN-5 y RN-6 conforman **una
   sola transacción**: o se aplican todos o ninguno. No existe instante observable con la
   base movida y la quote no, ni con principal movido y fee no cobrada. Ante cualquier
   falla, rollback total al estado previo exacto.
   - **Orden canónico de asientos** (para reproducibilidad y reconciliación automática del
     ledger con el registro de trades, HU-05-03 RN-8): primero la pata **ETH**, luego la
     pata **USDC**, y el surplus al final. Cada asiento lleva un `type` enumerado:
     1. `SELL_ETH_DEBIT` — `bloqueado(vendedor, ETH) −= q_wei`.
     2. `BUY_ETH_CREDIT` — `disponible(comprador, ETH) += (q_wei − fee_base)`.
     3. `FEE_ETH_CREDIT_EX` — `disponible(EX, ETH) += fee_base`.
     4. `BUY_QUOTE_DEBIT` — `bloqueado(comprador, USDC) −= quote_min`.
     5. `SELL_QUOTE_CREDIT` — `disponible(vendedor, USDC) += (quote_min − fee_quote)`.
     6. `FEE_QUOTE_CREDIT_EX` — `disponible(EX, USDC) += fee_quote`.
     7. `SURPLUS_RELEASE` — (solo si aplica RN-6) `bloqueado(comprador, USDC) −= surplus`,
        `disponible(comprador, USDC) += surplus`.
   - Dos implementaciones que liquiden el mismo fill generan los asientos en este mismo
     orden y con estos mismos `type`. La codificación concreta en el ledger de doble
     entrada la fija la épica 02; el orden lógico y los `type` son normativos de esta
     épica.
8. **RN-8 (conservación — INV-1).** Para el fill se cumple, por construcción:
   `q_wei = (q_wei − fee_base) + fee_base` (ETH) y
   `quote_min = (quote_min − fee_quote) + fee_quote` (USDC). La suma `Σ total(·, ETH)` y
   `Σ total(·, USDC)` (usuarios + EX) es idéntica antes y después del fill.
9. **RN-9 (no-negatividad e identidad de balance — INV-2/INV-3).** Antes de aplicar, debe
   verificarse que `bloqueado(vendedor, ETH) ≥ q_wei` y `bloqueado(comprador, USDC) ≥
   quote_min` (garantizado por el bloqueo previo de la orden). `total = disponible +
   bloqueado` se preserva en cada cuenta/activo. Si la precondición no se cumple, el
   settlement no se aplica y se reporta `INTERNAL_ERROR` (rotura de invariante; no debería
   ocurrir si el bloqueo previo fue correcto).
10. **RN-10 (idempotencia por identidad de fill).** El `tradeId` llega en el evento de fill
    (RN-1) y es estable a través de redelivery/reintentos (HU-05-03 RN-2). Antes de aplicar,
    el settlement verifica si ya existe un trade registrado con ese `tradeId`; si existe, es
    un **no-op idempotente**: no repite asientos ni cobra fees de nuevo. Útil ante
    reintentos/reinicios/redelivery del evento.
11. **RN-11 (fill parcial).** El settlement liquida exactamente la `q_wei` matcheada del
    fill (que puede ser menor que la cantidad de cualquiera de las dos órdenes). El
    remanente de cada orden permanece `bloqueado` y abierto; un fill parcial **no** exige
    cumplir el mínimo notional (este aplica al alta de orden, no a cada fill).
12. **RN-12 (cuentas distintas).** Comprador y vendedor son cuentas distintas (self-trade
    se bloqueó antes en épica 03). El settlement no contempla maker = taker.
13. **RN-13 (persistencia — INV-8).** Los asientos del settlement se persisten en el ledger
    de doble entrada (épica 02); tras un reinicio, recomputar balances desde el ledger
    reproduce el estado post-fill.
14. **RN-14 (sin floats).** Todos los cálculos usan enteros de unidad mínima (big
    integers). Prohibido IEEE-754 para montos/precios/fees/balances (convenciones §1.1).

## Criterios de aceptación (DoD)

### Escenario 1: Fill total — taker compra contra maker vende [AT-05-01-01]
- Dado un vendedor maker con una orden SELL resting de `q_wei = 1000000000000000000`
  (1 ETH) a `price_min = 2000000000` (2000.00 USDC/ETH), con `bloqueado(vendedor, ETH) =
  1000000000000000000`
- Y un comprador taker con orden BUY a límite ≥ 2000.00 y `bloqueado(comprador, USDC) =
  2000000000` para esta porción
- Cuando el matching emite un fill por `q_wei = 1000000000000000000` a `price_min =
  2000000000` (taker = comprador)
- Entonces `quote_min = floor(1000000000000000000 × 2000000000 / 10^18) = 2000000000`
- Y `bloqueado(vendedor, ETH)` pasa a `0` y `bloqueado(comprador, USDC)` pasa a `0`
- Y las fees (HU-05-02): `fee_base = 2000000000000000` wei (comprador taker, 20 bps en ETH)
  y `fee_quote = 2000000` USDC-min (vendedor maker, 10 bps en USDC)
- Y el comprador recibe en `disponible` de ETH `1000000000000000000 − 2000000000000000 =
  998000000000000000` y el vendedor recibe en `disponible` de USDC
  `2000000000 − 2000000 = 1998000000`
- Y `disponible(EX, ETH) += 2000000000000000` y `disponible(EX, USDC) += 2000000`
- Y `Σ total(·, ETH)` y `Σ total(·, USDC)` (usuarios + EX) son idénticas antes y después
  (INV-1)

### Escenario 2: Fill total — taker vende contra maker compra [AT-05-01-02]
- Dado un comprador maker con orden BUY resting de `q_wei = 1000000000000000000` a
  `price_min = 2000000000`, con `bloqueado(comprador, USDC) = 2000000000`
- Y un vendedor taker con orden SELL a límite ≤ 2000.00 y `bloqueado(vendedor, ETH) =
  1000000000000000000`
- Cuando el matching emite un fill por `q_wei = 1000000000000000000` a `price_min =
  2000000000` (taker = vendedor)
- Entonces `quote_min = 2000000000`
- Y `bloqueado(vendedor, ETH)` pasa a `0` y `bloqueado(comprador, USDC)` pasa a `0`
- Y las fees (HU-05-02): `fee_quote = 4000000` USDC-min (vendedor taker, 20 bps) y
  `fee_base = 1000000000000000` wei (comprador maker, 10 bps)
- Y el comprador (maker) recibe en `disponible` de ETH
  `1000000000000000000 − 1000000000000000 = 999000000000000000` y el vendedor (taker) recibe
  en `disponible` de USDC `2000000000 − 4000000 = 1996000000`
- Y `disponible(EX, ETH) += 1000000000000000` y `disponible(EX, USDC) += 4000000`
- Y se preserva la conservación por activo (INV-1) con EX incluida

### Escenario 3 (borde): Fill parcial — el remanente sigue bloqueado [AT-05-01-03]
- Dado un maker SELL resting de `q_wei = 1000000000000000000` (1 ETH) a `price_min =
  2000000000`, con `bloqueado(vendedor, ETH) = 1000000000000000000`
- Cuando entra un taker BUY que matchea solo `q_wei = 400000000000000000` (0.4 ETH) a
  `price_min = 2000000000`
- Entonces se liquidan exactamente `0.4 ETH` con `quote_min = floor(400000000000000000 ×
  2000000000 / 10^18) = 800000000` (800 USDC)
- Y `bloqueado(vendedor, ETH)` queda en `600000000000000000` (0.6 ETH remanente, orden en
  `PARTIALLY_FILLED`)
- Y no se exige mínimo notional sobre este fill parcial aunque su notional sea cualquier
  valor ≥ 0
- Y la conservación se mantiene para la porción liquidada (INV-1)

### Escenario 4 (borde): Mejora de precio del taker comprador — surplus liberado [AT-05-01-04]
- Dado un maker SELL resting a `price_min = 2000000000` (2000.00) por `q_wei =
  1000000000000000000`
- Y un comprador taker cuya orden BUY **LIMIT** (`takerOrderType = LIMIT`) tiene límite
  `price_limit_taker = 2010000000` (2010.00), por lo que bloqueó
  `floor(1000000000000000000 × 2010000000 / 10^18) = 2010000000` USDC para esta porción
- Cuando se ejecuta el fill por `q_wei = 1000000000000000000` al `price_min = 2000000000`
  (precio del maker)
- Entonces `quote_min = 2000000000` se consume del `bloqueado` del comprador
- Y el surplus `surplus = 2010000000 − 2000000000 = 10000000` (10 USDC) se libera:
  `bloqueado(comprador, USDC) −= 10000000` y `disponible(comprador, USDC) += 10000000`
- Y `total(comprador, USDC)` disminuye **exactamente** en `quote_min = 2000000000` (lo
  efectivamente pagado); el surplus `10000000` pasa de `bloqueado` a `disponible` y **no**
  altera `total(comprador, USDC)`. La fee del comprador (taker BUY) se cobra en **ETH**
  (`fee_base`), **no** en USDC, por lo que no hay componente de fee sobre `total(USDC)`
- Y `total(comprador, ETH)` aumenta en el **neto recibido** `1000000000000000000 −
  fee_base = 998000000000000000` (con `fee_base = 2000000000000000` acreditado a EX); el
  comprador recibe ETH al mejor precio (2000.00) y conserva los 10 USDC liberados (INV-1)

### Escenario 5 (borde): Sweep — un taker barre dos makers, dos settlements [AT-05-01-05]
- Dado dos makers SELL resting: M1 de `q_wei = 300000000000000000` a `price_min =
  2000000000` (más prioridad) y M2 de `q_wei = 300000000000000000` a `price_min =
  2001000000`
- Cuando entra un taker BUY por `q_wei = 600000000000000000` con límite ≥ 2001.00
- Entonces se generan **dos** eventos de fill independientes: F1 (vs M1 @ 2000.00) y F2
  (vs M2 @ 2001.00), cada uno con su settlement atómico
- Y cada settlement preserva INV-1/INV-2/INV-3/INV-4 por separado
- Y la suma de `quote_min` consumidos del comprador es `floor(0.3e18 × 2000000000/1e18) +
  floor(0.3e18 × 2001000000/1e18) = 600000000 + 600300000 = 1200300000` USDC

### Escenario 6 (atomicidad/error): Falla a mitad del settlement — rollback total [AT-05-01-06]
- Dado un fill válido en curso (taker BUY vs maker SELL, 1 ETH @ 2000.00)
- Cuando ocurre una falla (p. ej. de persistencia) **después** de debitar la base del
  vendedor pero **antes** de acreditar la quote al vendedor
- Entonces la transacción se revierte por completo: `bloqueado(vendedor, ETH)`,
  `bloqueado(comprador, USDC)` y todos los `disponible` y la cuenta EX quedan **exactamente**
  como antes del fill
- Y no existe ningún snapshot intermedio observable con base movida y quote sin mover (INV-4)
- Y se reporta `INTERNAL_ERROR`; el fill puede reintentarse de forma idempotente (RN-10)
- **Mecanismo de prueba esperado:** inyección de falla en la capa de persistencia (mock que
  lanza excepción tras el primer asiento), o reinicio del proceso a mitad de la operación en
  vuelo, o verificación a nivel de transacción ACID. Lo **observable externamente** es: tras
  el intento fallido, los balances son idénticos al estado previo al fill y **no** existe
  registro de trade asociado (verificable junto con AT-05-01-07 idempotencia y AT-05-03-06
  no-trade-sin-settlement). Si la implementación usa transacciones ACID, el estado
  intermedio no es observable y la propiedad se cumple por construcción.

### Escenario 7 (idempotencia): Reproceso del mismo fill no duplica asientos [AT-05-01-07]
- Dado un fill con `tradeId = T-123` ya liquidado correctamente
- Cuando el mismo `tradeId = T-123` se reprocesa (reinicio, reintento, redelivery del
  evento)
- Entonces no se generan nuevos asientos ni se cobran fees otra vez (no-op idempotente)
- Y los balances de comprador, vendedor y EX permanecen iguales que tras el primer
  settlement
- Y la suma de trades registrados (HU-05-03) sigue conteniendo `T-123` una sola vez

### Escenario 8 (secuencia): Fills sucesivos sobre el mismo maker preservan conservación y límite de bloqueado [AT-05-01-08]
- Dado un maker SELL resting de `q_wei = 1000000000000000000` a `price_min = 2000000000`
- Cuando dos takers BUY generan fills que consumen `0.6 ETH` y `0.4 ETH` del mismo maker,
  procesados **uno tras otro (en secuencia)** por el settlement
- Entonces cada settlement consume del `bloqueado(maker, ETH)` su porción sin solaparse
  (`0.6e18` y luego `0.4e18`, dejando `0`)
- Y nunca se consume más `q_wei` del que el maker tenía bloqueado (INV-2)
- Y al finalizar, `Σ total(·, A)` por activo es idéntica al estado previo a ambos fills
- (La ejecución **concurrente** de estos mismos fills se cubre en AT-05-01-11.)

### Escenario 9 (invariante/error): Precondición de bloqueo no satisfecha [AT-05-01-09]
- Dado un evento de fill que pediría consumir `q_wei` mayor que `bloqueado(vendedor, ETH)`
  (estado inconsistente que no debería ocurrir si el bloqueo previo fue correcto)
- Cuando el settlement valida la precondición RN-9 antes de aplicar
- Entonces **no** aplica ningún asiento, deja los balances intactos y reporta
  `INTERNAL_ERROR`
- Y se preserva INV-2 (ningún balance queda negativo) e INV-4 (no hay aplicación parcial)

### Escenario 10 (borde): Taker BUY market — consumo sin liberar surplus por fill [AT-05-01-10]
- Dado un comprador taker con orden **MARKET BUY** (`takerOrderType = MARKET`, **sin**
  `price_limit_taker`) para la cual la épica 04 bloqueó `bloqueado(comprador, USDC) =
  2010000000` (estimación al alta, p. ej. por mejor ask)
- Y dos makers SELL resting: M1 de `q_wei = 500000000000000000` (0.5 ETH) a `price_min =
  2000000000` y M2 de `q_wei = 500000000000000000` a `price_min = 2001000000`
- Cuando el matching emite dos fills: F1 (vs M1, `q_wei = 500000000000000000` @ 2000.00) y
  F2 (vs M2, `q_wei = 500000000000000000` @ 2001.00)
- Entonces F1 consume `quote_min = floor(500000000000000000 × 2000000000 / 10^18) =
  1000000000` y F2 consume `quote_min = floor(500000000000000000 × 2001000000 / 10^18) =
  1000500000` de `bloqueado(comprador, USDC)`
- Y **ningún** fill libera surplus (no hay `price_limit_taker`, RN-6): tras ambos fills
  `bloqueado(comprador, USDC) = 2010000000 − 1000000000 − 1000500000 = 9500000` permanece
  bloqueado
- Y la liberación de ese remanente (`9500000`) es **responsabilidad de la épica 04** al
  terminar la orden market (no de esta épica)
- Y cada fill preserva la conservación por activo con EX incluida (INV-1)

### Escenario 11 (concurrencia): Dos settlements simultáneos sobre el mismo maker se serializan [AT-05-01-11]
- Dado un maker SELL resting de `q_wei = 1000000000000000000` a `price_min = 2000000000`,
  con `bloqueado(maker, ETH) = 1000000000000000000`
- Y dos fills F1 (`0.6 ETH`) y F2 (`0.4 ETH`) contra ese maker cuyos settlements se
  **inician simultáneamente** (dos hilos/procesos)
- Cuando ambos settlements intentan consumir `bloqueado(maker, ETH)` a la vez
- Entonces el sistema **serializa** el acceso al balance del maker (aislamiento
  SERIALIZABLE o lock pesimista a nivel de cuenta/activo —p. ej. `SELECT ... FOR UPDATE`—,
  o un único actor/cola por cuenta): uno consume `0.6e18` y el otro `0.4e18`, dejando
  `bloqueado(maker, ETH) = 0`
- Y **nunca** se consume más `q_wei` del bloqueado (no hay doble lectura del mismo saldo;
  INV-2)
- Y el resultado (balances y asientos) es **idéntico** al de la ejecución secuencial de
  AT-05-01-08 (`Σ total(·, A)` por activo idéntica al estado previo a ambos fills; INV-1/INV-4)

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptacion (AT-05-01-01 .. AT-05-01-11) pasan
- [ ] Reglas de negocio RN-1..RN-14 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md), en
      particular INV-1 (conservación), INV-2/INV-3 (balances), INV-4 (atomicidad), INV-8
      (persistencia)
- [ ] (si aplica) Adherencia verificada al estandar on-chain citado — N/A (settlement interno)
