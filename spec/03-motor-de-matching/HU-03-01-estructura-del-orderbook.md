# HU-03-01 — Estructura del orderbook

- **Epica:** 03 — Motor de Matching
- **Actor / rol:** Sistema (motor de matching)
- **Prioridad:** Alta
- **Dependencias:** Épica 00 (fundaciones: `activos-y-par-de-trading.md`,
  `invariantes-globales.md`); Épica 02 (balances-y-ledger: fondos bloqueados que respaldan
  cada orden abierta).
- **Estandares de dominio aplicables:** N/A (no on-chain). Aplica la convención de
  **prioridad precio-tiempo** y la representación monetaria entera de 00-fundaciones.

## Historia
Como motor de matching, quiero representar el orderbook del par `ETH/USDC` separado en dos
lados (bids y asks) con niveles de precio ordenados y una cola FIFO por secuencia de ingreso
(`seq`) dentro de cada nivel, para poder aplicar prioridad precio-tiempo de forma
determinista y mantener el libro íntegro y no cruzado.

## Contexto y alcance
Esta HU define **la estructura de datos lógica** del orderbook y sus invariantes de orden,
sin describir todavía el algoritmo de cruce (HU-03-03/04) ni la inserción de una orden
nueva (HU-03-02). Cubre: cómo se ordenan los lados, qué es un nivel de precio, cómo se
desempata a igual precio (FIFO por secuencia de ingreso), qué órdenes viven en el libro y
qué propiedades de integridad deben sostenerse en todo momento. **No** cubre la
persistencia en almacenamiento durable (HU-03-07) ni la emisión de eventos (HU-03-05).

El orderbook contiene **solo órdenes `LIMIT` abiertas** (estados `OPEN` o
`PARTIALLY_FILLED`) con remanente no ejecutado. Las órdenes `MARKET` **nunca** descansan en
el libro (HU-03-04). Cada orden del libro pertenece a una cuenta y tiene fondos bloqueados
que respaldan su remanente (épica 02).

## Reglas de negocio e invariantes
1. **RN-1 (dos lados).** El libro tiene exactamente dos lados para el par `ETH/USDC`:
   `bids` (órdenes `BUY`) y `asks` (órdenes `SELL`). No existen otros pares ni otros lados.
2. **RN-2 (orden de bids).** Los `bids` se ordenan por **precio descendente**: el
   **best bid** es el de `price_min` más alto. A mayor precio, mejor prioridad de compra.
3. **RN-3 (orden de asks).** Los `asks` se ordenan por **precio ascendente**: el
   **best ask** es el de `price_min` más bajo. A menor precio, mejor prioridad de venta.
4. **RN-4 (nivel de precio).** Un **nivel de precio** es el conjunto de órdenes de un lado
   con idéntico `price_min`. Todos los `price_min` del libro son múltiplos del tick size
   (`price_min mod 10000 == 0`, `price_min > 0`); esta validación la garantiza la épica 04
   antes del ingreso (`INVALID_PRICE_TICK`).
5. **RN-5 (FIFO por secuencia de ingreso).** Dentro de un nivel de precio, la prioridad es
   **temporal (FIFO)**: primero se atiende la orden que ingresó antes. El desempate
   determinista es una **secuencia de ingreso** entera, estrictamente monótona y única
   (`seq`), asignada por el motor en el instante en que la orden se vuelve pasiva. La
   secuencia —no el timestamp de reloj de pared— es la clave de desempate, porque dos
   órdenes pueden compartir timestamp pero **nunca** `seq`. `seq` es una **clave de orden**:
   se exige estrictamente monótona y única, pero **no** necesariamente contigua. `seq`
   (prioridad de órdenes) es un contador **independiente** del `sequence` de eventos de
   ejecución (HU-03-05); ver README §"Reglas transversales" RT-2.
6. **RN-6 (clave de prioridad total).** La prioridad total de una orden en su lado es el
   par lexicográfico `(prioridad_de_precio, seq)`: primero el mejor precio (RN-2/RN-3),
   luego el menor `seq`. Esta relación es un **orden total estricto** (sin empates).
7. **RN-7 (contenido del libro).** El libro contiene únicamente órdenes `LIMIT` con estado
   `OPEN` o `PARTIALLY_FILLED` y `remainingWei > 0`. Una orden que pasa a `FILLED`,
   `CANCELLED` o `REJECTED` se retira del libro de inmediato y deja de tener prioridad.
8. **RN-8 (remanente de la orden).** Cada orden del libro expone, como mínimo:
   `orderId`, `accountId`, `side`, `price_min`, `quantityWei` (cantidad original),
   `filledWei` (acumulado ejecutado) y `remainingWei = quantityWei − filledWei`, todos como
   enteros de unidad mínima (wei). La prioridad del nivel se computa sobre `remainingWei`.
9. **RN-9 (no cruce — INV-7).** El libro **no puede quedar cruzado**: si existen ambos
   lados, debe cumplirse `best_bid_price < best_ask_price`. Un par de niveles cruzados
   (`best_bid_price ≥ best_ask_price`) es un estado inválido que el matching (HU-03-03/04)
   resuelve antes de devolver el control; nunca es observable en reposo.
10. **RN-10 (respaldo en fondos — INV-7).** Para toda orden abierta, los fondos que
    respaldan su `remainingWei` están **bloqueados** en la cuenta dueña:
    - una `BUY` bloquea **exactamente** `floor(remainingWei × price_min / 10^18)` USDC-min
      (el notional a su precio límite). **No** se bloquean fees anticipadas: la fee del
      comprador se cobra en el activo **recibido** (ETH) y se deduce del producto del fill
      al liquidar (`convenciones-monetarias.md` §3.3), por lo que no requiere bloqueo
      adicional de quote.
    - una `SELL` bloquea base (`remainingWei` wei de ETH); su fee se cobra en el USDC
      recibido al liquidar, sin bloqueo adicional.

    El motor no crea ni libera fondos; solo mantiene la correspondencia. El detalle del
    asiento contable lo aplica la épica 02/05.
11. **RN-11 (unicidad de `orderId`).** Dentro del libro no hay dos órdenes con el mismo
    `orderId`. El `orderId` es estable durante toda la vida de la orden.
12. **RN-12 (serialización).** Toda cantidad/precio expuestos por la estructura se
    serializan como **string de entero** de unidad mínima, patrón `^(0|[1-9][0-9]*)$`
    (`convenciones-monetarias.md`). Prohibido floats.
13. **RN-13 (lados independientes y vacíos).** Cada lado puede estar vacío de forma
    independiente. Si un lado está vacío, su best price es **indefinido** (no `0`); el
    spread es indefinido si falta cualquiera de los dos best.

## Criterios de aceptacion (DoD)

### Escenario 1: Ordenamiento de niveles en ambos lados [AT-03-01-01]
- Dado un orderbook vacío
- Cuando ingresan como pasivas estas órdenes (en este orden): `SELL 1 ETH @ 2001.00`,
  `SELL 1 ETH @ 2000.50`, `BUY 1 ETH @ 1999.00`, `BUY 1 ETH @ 2000.00`
- Entonces el **best ask** es `2000.50` (`price_min = 2000500000`) y el siguiente ask es
  `2001.00` (`2001000000`)
- Y el **best bid** es `2000.00` (`2000000000`) y el siguiente bid es `1999.00`
  (`1999000000`)
- Y se cumple `best_bid_price (2000000000) < best_ask_price (2000500000)` (libro no
  cruzado, RN-9)

### Escenario 2: FIFO dentro de un mismo nivel de precio [AT-03-01-02]
- Dado un orderbook vacío
- Cuando ingresan tres `SELL 1 ETH @ 2000.00` de distintas órdenes en el orden A, luego B,
  luego C (mismo `price_min = 2000000000`)
- Entonces las tres comparten nivel de precio y reciben secuencias de ingreso
  estrictamente crecientes `seq(A) < seq(B) < seq(C)`
- Y la prioridad de atención dentro del nivel es A, luego B, luego C (FIFO, RN-5)
- Y la clave de prioridad total `(precio, seq)` no produce empates (RN-6)

### Escenario 3 (borde): Un lado vacío — best price indefinido [AT-03-01-03]
- Dado un orderbook con `asks` poblado y `bids` vacío
- Cuando se consulta el estado del libro
- Entonces `best_bid` es **indefinido** (no `0` ni `null` numérico que se confunda con un
  precio) y el spread es **indefinido** (RN-13)
- Y `best_ask` existe y es el ask de menor `price_min`

### Escenario 4 (borde): Prioridad se recomputa sobre el remanente [AT-03-01-04]
- Dado un nivel `BUY @ 2000.00` con dos órdenes: O1 (`seq` menor, `remainingWei = 0.5 ETH`
  = `500000000000000000`) y O2 (`seq` mayor, `remainingWei = 1 ETH` =
  `1000000000000000000`)
- Cuando se evalúa la prioridad del nivel
- Entonces O1 mantiene prioridad sobre O2 por menor `seq`, independientemente de la
  cantidad (RN-5, RN-8)
- Y ambos `remainingWei` se exponen como string de entero de unidad mínima (RN-12)

### Escenario 5 (integridad): El libro nunca queda cruzado en reposo [AT-03-01-05]
- Dado un libro concreto con bids `BUY 1 ETH @ 2000.00` (`2000000000`) y `BUY 0.5 ETH @
  1999.00` (`1999000000`) y asks `SELL 1 ETH @ 2001.00` (`2001000000`) y `SELL 0.5 ETH @
  2002.00` (`2002000000`)
- Cuando ambos lados tienen al menos una orden
- Entonces se verifica `best_bid_price (2000000000) < best_ask_price (2001000000)` (INV-7,
  RN-9) y no existe ningún par (bid, ask) con `bid_price ≥ ask_price` sin haber matcheado
- Y (property-based) ejecutando un generador de **≥ 500 órdenes** aleatorias `LIMIT`/`MARKET`
  e inspeccionando el libro tras **cada** operación, en todos los estados resultantes se
  cumple `best_bid_price < best_ask_price` (cuando ambos lados existen) y no hay par
  `(bid_i, ask_j)` con `bid_i.price ≥ ask_j.price` (INV-7)

### Escenario 6 (integridad): Respaldo en fondos bloqueados [AT-03-01-06]
- Dado un orderbook con varias órdenes abiertas de una cuenta `acc`
- Cuando se suma el respaldo requerido por el `remainingWei` de cada orden de `acc` por
  activo, usando: para cada `SELL`, `remainingWei` wei de ETH; para cada `BUY`,
  `floor(remainingWei × price_min / 10^18)` USDC-min (RN-10, sin fees anticipadas)
- Entonces esa suma es exactamente igual al `bloqueado(acc, activo)` atribuible a órdenes
  (RN-10, INV-7), sin órdenes “huérfanas” sin respaldo ni fondos bloqueados sin orden
- Ejemplo: una `BUY 1 ETH @ 2000.00` abierta implica `bloqueado(acc, USDC)` atribuible =
  `floor(10^18 × 2000000000 / 10^18) = 2000000000`

### Escenario 7 (borde): Solo viven órdenes abiertas [AT-03-01-07]
- Dado un nivel con una orden que se ejecuta totalmente (pasa a `FILLED`)
- Cuando concluye su ejecución
- Entonces esa orden se retira del libro de inmediato y ya no participa de la prioridad
  (RN-7)
- Y ninguna orden en estado `FILLED`, `CANCELLED` o `REJECTED` permanece en el libro

### Escenario 8 (integridad): Ejecución serializada — sin interleaving [AT-03-01-08]
- Dado un conjunto de N órdenes (`LIMIT`/`MARKET`) entregadas al motor "en paralelo"
  (concurrentemente) sobre el mismo par `ETH/USDC`
- Cuando el motor las procesa bajo el modelo de ejecución serializada (README RT-1)
- Entonces el estado final del libro es **equivalente a alguna permutación serial válida**
  de esas N órdenes (no hay interleaving de fills entre dos órdenes)
- Y en **todo** punto observable el libro cumple INV-7 (no cruzado, prioridad `(precio, seq)`)
  y cada fill aplicado es atómico (INV-4)

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-*) pasan
- [ ] Reglas de negocio RN-1..RN-13 verificadas (incluida la independencia de contadores
      `seq`/`sequence`, README RT-2, y el modelo de ejecución serializada, README RT-1)
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md), en
      particular INV-7
- [ ] (si aplica) Adherencia verificada al estandar on-chain citado — N/A
