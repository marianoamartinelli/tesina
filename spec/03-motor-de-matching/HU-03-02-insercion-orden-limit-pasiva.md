# HU-03-02 — Inserción de orden limit pasiva (resting)

- **Epica:** 03 — Motor de Matching
- **Actor / rol:** Trader autenticado (dispara el alta) / Sistema (motor de matching)
- **Prioridad:** Alta
- **Dependencias:** HU-03-01 (estructura del orderbook); Épica 02 (bloqueo de fondos);
  Épica 04 (validación de entrada y alta de orden). Épica 00 (fundaciones).
- **Estandares de dominio aplicables:** N/A (no on-chain). Aplica prioridad precio-tiempo y
  convenciones monetarias de 00-fundaciones.

## Historia
Como trader autenticado, quiero que mi orden `LIMIT` sin contraparte cruzable quede
**pasiva (resting)** en el orderbook en la posición que le corresponde por prioridad
precio-tiempo, para proveer liquidez y poder ser matcheada como maker por órdenes futuras.

## Contexto y alcance
Esta HU cubre **únicamente** el caso en que una orden `LIMIT` entrante **no cruza** el
libro (no hay contraparte ejecutable a su precio) y por lo tanto se inserta completa como
pasiva. El caso en que sí cruza (total o parcialmente) lo trata HU-03-03; el remanente que
una orden cruzante deja en el libro reutiliza **esta** lógica de inserción. La orden llega
**ya validada** por la épica 04 (auth, esquema, enums, tick/lot/min-notional, idempotencia
de `clientOrderId`, fondos suficientes) y con sus fondos **bloqueados** por la épica 02.

Una orden `MARKET` **nunca** se inserta como pasiva (HU-03-04). El motor asigna a la orden
recién posada su **secuencia de ingreso** `seq` y la ubica al final de la cola FIFO de su
nivel de precio.

## Reglas de negocio e invariantes
1. **RN-1 (condición de no-cruce).** Una orden `LIMIT` entrante se inserta como pasiva si y
   solo si **no es cruzable** contra el lado opuesto en el instante de ingreso:
   - `BUY @ L` no cruza si no hay asks, o si `best_ask_price > L`.
   - `SELL @ L` no cruza si no hay bids, o si `best_bid_price < L`.
   Si es cruzable, aplica HU-03-03 (matching) y solo el **remanente** no ejecutado puede
   posarse mediante esta HU.
2. **RN-2 (lado de inserción).** Una `BUY` se inserta en `bids`; una `SELL` en `asks`
   (HU-03-01 RN-1).
3. **RN-3 (ubicación por precio).** La orden se ubica en el **nivel de precio** igual a su
   `L` (`price_min`). Si el nivel no existe, se crea respetando el orden del lado (bids
   descendente, asks ascendente — HU-03-01 RN-2/RN-3).
4. **RN-4 (cola FIFO — tail).** Dentro de su nivel, la orden se agrega **al final** de la
   cola FIFO: recibe un `seq` estrictamente mayor al de toda orden ya presente, por lo que
   queda **última** en prioridad temporal de ese nivel (HU-03-01 RN-5/RN-6).
5. **RN-5 (estado inicial).** Una orden recién posada sin ejecución previa queda en estado
   `OPEN` con `filledWei = 0` y `remainingWei = quantityWei`. Si proviene del remanente de
   una orden parcialmente ejecutada (HU-03-03), queda en `PARTIALLY_FILLED` con
   `remainingWei = quantityWei − filledWei > 0`.
6. **RN-6 (respaldo en fondos — INV-7).** Al quedar pasiva, el `remainingWei` debe estar
   respaldado por fondos **bloqueados** (épica 02): una `SELL` bloquea `remainingWei` wei
   de ETH; una `BUY` bloquea el quote correspondiente a su precio límite. El motor no
   bloquea ni libera fondos; verifica que el respaldo exista.
7. **RN-7 (no cruza tras posarse — INV-7).** Insertar la orden **no** debe dejar el libro
   cruzado: por RN-1, su precio no cruza el best opuesto, de modo que se preserva
   `best_bid_price < best_ask_price`.
8. **RN-8 (idempotencia de alta).** La unicidad de la orden (no duplicar por reintento) la
   garantiza la épica 04 vía `clientOrderId` (`DUPLICATE_CLIENT_ORDER_ID`); el motor no
   inserta dos veces la misma orden ni le asigna dos `seq`.
9. **RN-9 (sin evento de trade).** Posar una orden pasiva **no** genera evento de
   `trade`/fill (no hubo ejecución). Puede generar un evento de actualización del libro
   (book update) para market data (épica 09); la emisión de trades es exclusiva de fills
   (HU-03-05).
10. **RN-10 (determinismo).** Dada la misma orden y el mismo estado de libro, la posición
    de inserción (nivel y posición FIFO) es única y reproducible.

## Criterios de aceptacion (DoD)

### Escenario 1: Inserción en libro vacío [AT-03-02-01]
- Dado un orderbook con `asks` vacío
- Cuando ingresa `BUY 1 ETH @ 2000.00` (`quantityWei = 1000000000000000000`,
  `price_min = 2000000000`), ya validada y con fondos bloqueados
- Entonces la orden se inserta en `bids` como nivel nuevo `2000.00`, estado `OPEN`,
  `filledWei = "0"`, `remainingWei = "1000000000000000000"`
- Y se convierte en el **best bid**
- Y **no** se emite ningún evento de trade (RN-9)

### Escenario 2: BUY por debajo del best ask se posa (no cruza) [AT-03-02-02]
- Dado un libro con `best_ask = 2001.00` (`2001000000`)
- Cuando ingresa `BUY 1 ETH @ 2000.00` (`L = 2000000000`)
- Entonces, como `best_ask_price (2001000000) > L (2000000000)`, la orden **no cruza** y se
  posa como best bid `2000.00` (RN-1)
- Y se preserva `best_bid_price (2000000000) < best_ask_price (2001000000)` (RN-7)

### Escenario 3: SELL por encima del best bid se posa (no cruza) [AT-03-02-03]
- Dado un libro con `best_bid = 2000.00` (`2000000000`)
- Cuando ingresa `SELL 1 ETH @ 2000.50` (`L = 2000500000`)
- Entonces, como `best_bid_price (2000000000) < L (2000500000)`, la orden **no cruza** y se
  posa como best ask `2000.50` (RN-1)
- Y el libro no queda cruzado (RN-7)

### Escenario 4 (borde): Inserción al final de la cola FIFO de un nivel existente [AT-03-02-04]
- Dado un nivel `bids @ 2000.00` con dos órdenes previas O1 y O2 tales que
  `seq(O1) < seq(O2)`
- Cuando ingresa O3 `BUY @ 2000.00` que no cruza
- Entonces O3 se agrega al **final** del nivel y recibe `seq(O3) > seq(O2)` (estrictamente
  mayor; no se asume contigüidad ni un valor exacto, ya que `seq` es una clave de orden y no
  un stream de eventos — README RT-2, HU-03-01 RN-5)
- Y la prioridad de atención del nivel queda O1, O2, O3 (RN-4)

### Escenario 5 (borde): Remanente de una orden cruzante se posa [AT-03-02-05]
- Dado que una `BUY 1 ETH @ 2001.00` cruzó y ejecutó `0.4 ETH` contra el libro (HU-03-03)
- Cuando ya no hay asks cruzables a su precio
- Entonces su remanente `remainingWei = 600000000000000000` (0.6 ETH) se posa como pasiva
  en `bids @ 2001.00` con estado `PARTIALLY_FILLED` (RN-5)
- Y el remanente queda respaldado por fondos bloqueados (RN-6)

### Escenario 6 (borde): Precio límite exactamente igual al best opuesto cruza, no se posa [AT-03-02-06]
- Dado un libro con `best_ask = 2000.00` (`2000000000`)
- Cuando ingresa `BUY 1 ETH @ 2000.00` (`L = 2000000000`)
- Entonces la orden **sí es cruzable** (`best_ask_price (2000000000) ≤ L`), por lo que
  **no** aplica esta HU sino HU-03-03; no se posa antes de intentar el cruce (RN-1)

### Escenario 7 (integridad): Unicidad de `orderId` en el libro [AT-03-02-07]
- Dado un `orderId` ya presente en el libro
- Cuando el motor recibiera una segunda inserción con el **mismo** `orderId` (p. ej. por un
  fallo interno o un reintento que sorteó la idempotencia de épica 04)
- Entonces el libro contiene **exactamente una** instancia de ese `orderId`: la inserción
  duplicada se rechaza y no se asigna un segundo `seq` (HU-03-01 RN-11)
- Y nota de trazabilidad: la **prevención** del duplicado en el borde externo es de la épica
  04 vía `clientOrderId` (`DUPLICATE_CLIENT_ORDER_ID`, RN-8, 409); esta HU verifica la
  garantía **interna** del motor (HU-03-01 RN-11), no la respuesta HTTP de la épica 04

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-*) pasan
- [ ] Reglas de negocio RN-1..RN-10 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md), en
      particular INV-7
- [ ] (si aplica) Adherencia verificada al estandar on-chain citado — N/A
