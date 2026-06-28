# HU-05-03 — Registro de trades

- **Epica:** 05 — Settlement y Fees
- **Actor / rol:** Sistema (registrador de trades, dentro del settlement disparado por el fill)
- **Prioridad:** Alta
- **Dependencias:** HU-05-01 (settlement atómico), HU-05-02 (fees), HU-03-* (eventos de fill, roles maker/taker), HU-02-* (ledger), HU-04-* (órdenes referenciadas)
- **Estandares de dominio aplicables:** N/A (registro contable interno)

## Historia
Como **sistema**, quiero **generar un registro de trade inmutable por cada fill, con
precio, cantidad, notional, fees, roles maker/taker, montos netos y referencias a las
órdenes y cuentas involucradas**, para **disponer de una fuente de verdad auditable de
cada ejecución, reconciliable con el ledger y consultable por los usuarios**.

## Contexto y alcance
Esta HU define el **modelo del registro de trade** que se crea atómicamente junto con el
settlement (HU-05-01). Un fill ⇒ exactamente un trade. El registro es **append-only**
(inmutable), persistente (INV-8) y consistente con los asientos del ledger. Cada trade
tiene una **identidad estable** (`tradeId`) que también sirve de clave de idempotencia del
settlement (HU-05-01 RN-10) y de ordenamiento determinista.

**No** cubre: la consulta/paginación del historial por el usuario (HU-05-04), el cálculo
de las fees (HU-05-02, aquí se almacenan los resultados), ni el contrato HTTP/WS concreto
(épica 09, aquí se fija la semántica y las unidades de cada campo). Todos los montos del
registro se almacenan y serializan como **enteros de unidad mínima** (string en API).

## Reglas de negocio e invariantes

1. **RN-1 (un trade por fill).** Cada evento de fill emitido por el matching produce
   **exactamente un** registro de trade, creado dentro de la misma transacción atómica del
   settlement (INV-4). Si el settlement se revierte, el trade **no** se registra.
2. **RN-2 (identidad estable, unicidad y generación).** El `tradeId` es **asignado por el
   matching engine** (épica 03) al producir el fill y viaja en el evento de fill (HU-05-01
   RN-1); el settlement lo **adopta sin modificarlo** como identidad del trade y **clave de
   idempotencia** (HU-05-01 RN-10).
   - **Formato:** string `"T-" + sequence` (p. ej. `"T-1"`, `"T-2"`, …), **determinístico**.
   - Es **único** (dos fills distintos nunca comparten `tradeId`), **estable** (idéntico a
     través de redelivery/reintentos) y **no reutilizable**. El reproceso idempotente de un
     fill (HU-05-01 RN-10) **no** crea un segundo registro con el mismo `tradeId`.
   - Como deriva de `sequence` (entero monótono persistido junto al ledger, RN-3), el
     `tradeId` se **reconstruye** tras reinicio sin depender de un almacén volátil; **no** se
     usan UUID aleatorios (no reconstruibles desde el ledger).
3. **RN-3 (orden determinista — secuencia y timestamp).**
   - `sequence`: entero **global, estrictamente creciente, comenzando en 1**, asignado por el
     matching en **orden de producción de fills**. Bajo operación normal es **contiguo** (sin
     huecos); si el settlement de un fill se revierte (AT-05-01-06) puede quedar un hueco,
     pero el siguiente trade exitoso siempre tiene un `sequence` **estrictamente mayor** que
     el anterior. Es el insumo del `tradeId` (RN-2) y la clave de ordenamiento canónica. (Con
     par único, "global" y "por par" coinciden; se fija **global** para eliminar ambigüedad.)
   - `timestamp`: **entero de epoch UNIX en milisegundos (ms), UTC**, serializado como
     **string de entero** en la API. La fuente de reloj es el reloj del sistema en el momento
     en que **comienza** la transacción de settlement. **No** se garantizan timestamps únicos
     por trade; el desempate de orden es **siempre por `sequence`** (HU-05-04 RN-5).
   - Ambos permiten ordenar los trades de forma determinista y reproducible tras reinicio
     (INV-8).
4. **RN-4 (campos obligatorios del registro).** Cada trade contiene, como mínimo:
   - `tradeId` — identidad estable.
   - `sequence` / `timestamp` — ordenamiento (RN-3).
   - `pair` — string canónico `"ETH/USDC"` (par único; `USDC` denota el activo subyacente
     USDC-mock, ver glosario). Es el **único** valor posible.
   - `priceMin` — precio de ejecución (= precio del maker), entero string.
   - `quantityWei` — `q_wei` ejecutado, entero string (múltiplo de `10^14`).
   - `quoteAmountMin` — `quote_min = floor(q_wei × priceMin / 10^18)`, entero string.
   - `takerSide` ∈ {`BUY`, `SELL`} — lado de la orden taker.
   - `makerSide` ∈ {`BUY`, `SELL`} — lado de la orden maker; **siempre el opuesto de
     `takerSide`** (`takerSide = BUY` ⇒ `makerSide = SELL` y viceversa). Es un campo
     **derivado** (puede no persistirse): se expone en la API/serialización por conveniencia
     y debe ser coherente con `takerSide` (RN-6).
   - `makerOrderId`, `takerOrderId` — órdenes maker y taker. `buyOrderId`, `sellOrderId` —
     órdenes del comprador y del vendedor, **relacionadas de forma determinista** con las
     anteriores: si `takerSide = BUY` ⇒ `buyOrderId = takerOrderId` y `sellOrderId =
     makerOrderId`; si `takerSide = SELL` ⇒ `buyOrderId = makerOrderId` y `sellOrderId =
     takerOrderId`. (Si el modelo persiste solo `makerOrderId`/`takerOrderId`,
     `buyOrderId`/`sellOrderId` se **derivan** de `takerSide` al serializar; nunca pueden ser
     incoherentes entre sí.)
   - `buyerAccountId`, `sellerAccountId`.
   - `feeBaseWei` — fee cobrada al comprador en ETH (HU-05-02), entero string.
   - `feeQuoteMin` — fee cobrada al vendedor en USDC (HU-05-02), entero string.
   - `buyerFeeBps`, `sellerFeeBps` ∈ {10, 20}; `buyerRole`, `sellerRole` ∈ {`MAKER`,
     `TAKER`}.
   - `buyerNetBaseWei = quantityWei − feeBaseWei`; `sellerNetQuoteMin = quoteAmountMin −
     feeQuoteMin` (montos netos, enteros string).
5. **RN-5 (coherencia de roles).** Exactamente una de las partes es `MAKER` y la otra
   `TAKER`; `buyerRole ≠ sellerRole`. Si `takerSide = BUY` ⇒ `buyerRole = TAKER`,
   `buyerFeeBps = 20`, `sellerRole = MAKER`, `sellerFeeBps = 10`; si `takerSide = SELL` ⇒
   inverso (coherente con HU-05-02 RN-4). `buyerAccountId ≠ sellerAccountId`.
6. **RN-6 (coherencia aritmética y estructural).** En todo registro debe cumplirse:
   `quoteAmountMin = floor(quantityWei × priceMin / 10^18)`,
   `feeBaseWei = ceil(quantityWei × buyerFeeBps / 10000)`,
   `feeQuoteMin = ceil(quoteAmountMin × sellerFeeBps / 10000)`,
   `0 ≤ feeBaseWei ≤ quantityWei`, `0 ≤ feeQuoteMin ≤ quoteAmountMin`;
   además `makerSide ≠ takerSide` (lados opuestos) y la relación
   `buyOrderId`/`sellOrderId` ↔ `makerOrderId`/`takerOrderId` según `takerSide` (RN-4).
7. **RN-7 (inmutabilidad).** Un trade registrado **no** se modifica ni se borra. Cualquier
   corrección se modela como un nuevo asiento/registro, nunca editando el existente
   (append-only).
8. **RN-8 (reconciliación con el ledger — INV-1).** La suma de `feeBaseWei` de todos los
   trades == acreditado histórico a `EX` en ETH; la suma de `feeQuoteMin` == acreditado a
   `EX` en USDC. La suma de movimientos de base/quote de los trades reproduce los asientos
   de settlement del ledger.
9. **RN-9 (persistencia — INV-8).** El conjunto de trades sobrevive a reinicios; tras
   recuperar, los `tradeId`/`sequence` y los montos son idénticos a los previos.
10. **RN-10 (serialización).** Todos los montos (`priceMin`, `quantityWei`,
    `quoteAmountMin`, `feeBaseWei`, `feeQuoteMin`, netos) se serializan como string entero de
    unidad mínima (`^(0|[1-9][0-9]*)$`); los enums (`takerSide`, roles) como string; sin
    floats (convenciones §5).
11. **RN-11 (emisión de evento — fuera del DoD de esta épica).** El alta de un trade **puede**
    emitir un evento (WebSocket público de market data y/o privado por cuenta); el **contrato
    y la evaluación del evento pertenecen a la épica 09**, no a esta épica (no hay criterio de
    aceptación en HU-05-03 que lo verifique). Si se emite, sus **unidades y semántica** son
    las de RN-4. Esta regla es **informativa** para la épica 09 y **no** se evalúa en el
    holdout de la épica 05.

## Criterios de aceptacion (DoD)

### Escenario 1: Trade registrado en un fill total (taker BUY) [AT-05-03-01]
- Dado un fill con `takerSide = BUY`, `q_wei = 1000000000000000000`, `priceMin =
  2000000000`, comprador taker y vendedor maker
- Cuando se completa el settlement (HU-05-01) atómicamente
- Entonces se crea **un** registro de trade con `quantityWei = "1000000000000000000"`,
  `priceMin = "2000000000"`, `quoteAmountMin = "2000000000"`
- Y `buyerRole = "TAKER"`, `buyerFeeBps = 20`, `feeBaseWei = "2000000000000000"`
- Y `sellerRole = "MAKER"`, `sellerFeeBps = 10`, `feeQuoteMin = "2000000"`
- Y `buyerNetBaseWei = "998000000000000000"`, `sellerNetQuoteMin = "1998000000"`
- Y el registro referencia `makerOrderId`, `takerOrderId`, `buyOrderId`, `sellOrderId`,
  `buyerAccountId`, `sellerAccountId`

### Escenario 2: Trade registrado en un fill total (taker SELL) [AT-05-03-02]
- Dado un fill con `takerSide = SELL`, `q_wei = 1000000000000000000`, `priceMin =
  2000000000`, vendedor taker y comprador maker
- Cuando se completa el settlement
- Entonces el trade tiene `sellerRole = "TAKER"`, `sellerFeeBps = 20`, `feeQuoteMin =
  "4000000"`
- Y `buyerRole = "MAKER"`, `buyerFeeBps = 10`, `feeBaseWei = "1000000000000000"`
- Y `buyerNetBaseWei = "999000000000000000"`, `sellerNetQuoteMin = "1996000000"`
- Y `makerSide = "BUY"`, coherente con `takerSide = "SELL"`

### Escenario 3 (borde): Un fill por cada porción de un sweep [AT-05-03-03]
- Dado un taker BUY que barre dos makers SELL (M1 @ 2000.00 por 0.3 ETH, M2 @ 2001.00 por
  0.3 ETH)
- Cuando se ejecutan los dos fills
- Entonces se registran **dos** trades distintos con `tradeId` y `sequence` distintos;
  `sequence(trade2) > sequence(trade1)`, ambos enteros positivos, y `tradeId = "T-" +
  sequence` en cada uno
- Y el primero tiene `priceMin = "2000000000"`, `quantityWei = "300000000000000000"`,
  `quoteAmountMin = "600000000"`; el segundo `priceMin = "2001000000"`,
  `quoteAmountMin = "600300000"`
- Y ambos referencian el mismo `takerOrderId` y distinto `makerOrderId`

### Escenario 4 (borde): coherencia aritmética con `ceil` efectivo [AT-05-03-04]
- Dado un fill `takerSide = BUY`, `q_wei = 100000000000000` (1 lot), `priceMin =
  2000010000`
- Cuando se registra el trade
- Entonces `quoteAmountMin = "200001"`, `feeQuoteMin = "201"` (maker, `ceil(200001×10/10000)`),
  `feeBaseWei = "200000000000"` (taker)
- Y se cumple RN-6: `200001 = floor(100000000000000 × 2000010000 / 10^18)`,
  `201 = ceil(200001 × 10 / 10000)`, `0 ≤ 201 ≤ 200001`
- Y `sellerNetQuoteMin = "199800"`, `buyerNetBaseWei = "99800000000000"`

### Escenario 5 (idempotencia): reproceso de fill no duplica el trade [AT-05-03-05]
- Dado un fill ya registrado con `tradeId = "T-500"`
- Cuando el mismo fill se reprocesa (reinicio/reintento)
- Entonces **no** se crea un segundo registro: existe exactamente un trade con `tradeId =
  "T-500"` (RN-2)
- Y sus campos y montos son idénticos a los del primer registro

### Escenario 6 (atomicidad): settlement revertido no deja trade [AT-05-03-06]
- Dado un settlement que falla a mitad y se revierte (HU-05-01 AT-05-01-06)
- Cuando se inspecciona el registro de trades
- Entonces **no** existe ningún trade asociado a ese fill (el registro es parte de la misma
  transacción atómica, RN-1/INV-4)

### Escenario 7 (persistencia/reconciliación): reinicio y suma de fees a EX [AT-05-03-07]
- Dado un conjunto de N trades registrados
- Cuando el sistema se reinicia y reconstruye estado desde el ledger
- Entonces los N trades persisten con `tradeId`/`sequence` y montos idénticos (INV-8)
- Y `Σ feeBaseWei` == acreditado total a `EX` en ETH y `Σ feeQuoteMin` == acreditado total
  a `EX` en USDC (RN-8, INV-1)

### Escenario 8 (serialización/error): montos como string entero [AT-05-03-08]
- Dado un trade con `quantityWei = 1000000000000000000` y `feeQuoteMin = 2000000`
- Cuando el registro se serializa hacia la API/evento
- Entonces todos los montos viajan como string que matchea `^(0|[1-9][0-9]*)$`
  (`"1000000000000000000"`, `"2000000"`), nunca como número JSON, decimal ni `1e18`
- Y un valor con float, signo o ceros a la izquierda se considera inválido (convenciones §5)

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptacion (AT-05-03-01 .. AT-05-03-08) pasan
- [ ] Reglas de negocio RN-1..RN-11 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md), en
      particular INV-1 (reconciliación con EX), INV-4 (atomicidad del registro), INV-8
      (persistencia)
- [ ] (si aplica) Adherencia verificada al estandar on-chain citado — N/A (registro interno)
