# HU-04-05 — Ciclo de vida y estados de la orden

- **Epica:** 04 — Gestión de Órdenes
- **Actor / rol:** Sistema (máquina de estados de la orden) / Trader autenticado (observador)
- **Prioridad:** Alta
- **Dependencias:** HU-04-01/02 (alta), HU-04-04 (cancelación), HU-03-* (fills),
  HU-04-03 (rechazos). Fundaciones (00).
- **Estandares de dominio aplicables:** N/A.

## Historia
Como **sistema y como trader que observa sus órdenes**, quiero **una máquina de estados de
la orden bien definida con transiciones válidas explícitas**, para **que el estado de cada
orden sea inequívoco, consistente y auditable en todo momento**.

## Contexto y alcance
Define el conjunto de estados de una orden, las transiciones válidas entre ellos y los
estados terminales. Es la referencia normativa que usan el alta (HU-04-01/02), la
cancelación (HU-04-04), el matching (HU-03-*) y las consultas (HU-04-06/07). No define el
algoritmo de cruce ni el settlement; sí define en qué estado queda la orden tras cada
evento.

Estados: **`NEW`** (transitorio interno: aceptada y con fondos reservados, aún no procesada
por el matching), **`OPEN`** (resting sin ejecución), **`PARTIALLY_FILLED`** (resting con
ejecución parcial), **`FILLED`** (ejecución total), **`CANCELLED`** (remanente removido por
el usuario o descartado por el sistema en market), **`REJECTED`** (rechazada en validación
o por la capa de matching — sin liquidez, self-trade o presupuesto insuficiente; nunca
descansó).

## Reglas de negocio e invariantes
1. **RN-1 (conjunto de estados).** El universo de estados es exactamente
   `{NEW, OPEN, PARTIALLY_FILLED, FILLED, CANCELLED, REJECTED}`. No existen otros.
2. **RN-2 (terminales).** `FILLED`, `CANCELLED` y `REJECTED` son **terminales**: no tienen
   transiciones salientes. Una orden terminal nunca vuelve a cambiar de estado.
3. **RN-3 (transiciones válidas).** Las únicas transiciones permitidas son:

   | Desde               | Hacia               | Disparador                                                        |
   |---------------------|---------------------|------------------------------------------------------------------|
   | (alta)              | `NEW`               | Orden aceptada en validación y fondos reservados                  |
   | (alta)              | `REJECTED`          | Rechazo por validación/idempotencia/fondos, o por la capa de matching (`MARKET_NO_LIQUIDITY` / `SELF_TRADE_BLOCKED` / `MARKET_BUDGET_INSUFFICIENT`). Solo los rechazos de **matching** se persisten como orden `REJECTED` (RN-5, RE-12) |
   | `NEW`               | `OPEN`              | Limit sin ejecución inmediata: descansa en el libro              |
   | `NEW`               | `PARTIALLY_FILLED`  | Limit con ejecución parcial en el ingreso; remanente descansa     |
   | `NEW`               | `FILLED`            | Ejecución total en el ingreso (limit marketable o market)         |
   | `NEW`               | `CANCELLED`         | Market con ejecución parcial y liquidez agotada (remanente descartado) |
   | `OPEN`              | `PARTIALLY_FILLED`  | Primer fill parcial de una orden resting                          |
   | `OPEN`              | `FILLED`            | Fill total de una orden resting                                   |
   | `OPEN`              | `CANCELLED`         | Cancelación del usuario (HU-04-04)                                |
   | `PARTIALLY_FILLED`  | `PARTIALLY_FILLED`  | Fills parciales sucesivos (remanente sigue resting)              |
   | `PARTIALLY_FILLED`  | `FILLED`            | Fill que completa el remanente                                    |
   | `PARTIALLY_FILLED`  | `CANCELLED`         | Cancelación del usuario del remanente (HU-04-04)                  |

4. **RN-4 (transiciones prohibidas).** Cualquier transición no listada en RN-3 es inválida
   y debe rechazarse. En particular, intentar cancelar desde `FILLED`/`CANCELLED`/
   `REJECTED` ⇒ `ORDER_NOT_CANCELLABLE` (409); no hay transición de un terminal a otro.
5. **RN-5 (REJECTED ⇒ sin fondos retenidos; persistencia selectiva).** Una orden `REJECTED`
   **nunca** termina con fondos bloqueados de forma permanente: las rechazadas por
   validación/idempotencia/fondos nunca llegaron a reservar; `MARKET_NO_LIQUIDITY` se evalúa
   **antes** de reservar (RE-4 paso 6); `SELF_TRADE_BLOCKED` se detecta tras reservar pero la
   reserva se **revierte atómicamente** (HU-04-01 RN-10, HU-04-02 RN-9);
   `MARKET_BUDGET_INSUFFICIENT` se detecta en el matching con `filledWei = 0` y la reserva se
   libera **íntegra** (HU-03-04 RN-9). Nunca produjo fills ni descansó en el libro (INV-2).
   **Persistencia (normativa):** se persisten como orden `REJECTED` —y aparecen en el
   historial (HU-04-07)— **solo** las rechazadas por la **capa de matching**
   (`MARKET_NO_LIQUIDITY`, `SELF_TRADE_BLOCKED`, `MARKET_BUDGET_INSUFFICIENT`); las
   rechazadas en validación, idempotencia o fondos (`VALIDATION_ERROR`, `INVALID_PRICE_TICK`,
   `INVALID_LOT_SIZE`, `BELOW_MIN_NOTIONAL`, `DUPLICATE_CLIENT_ORDER_ID`,
   `INSUFFICIENT_FUNDS`, …) **no** se persisten como órdenes (solo devuelven el error)
   (RE-12).
6. **RN-6 (market IOC).** Una orden market solo puede terminar en `FILLED` (objetivo
   completo), `CANCELLED` (parcial + remanente descartado) o `REJECTED` sin ejecución alguna
   (`MARKET_NO_LIQUIDITY`, `SELF_TRADE_BLOCKED` o `MARKET_BUDGET_INSUFFICIENT`); nunca en
   `OPEN` ni en `PARTIALLY_FILLED` persistente (RE-6).
7. **RN-7 (monotonía y unidad de ejecutado).** `executedQty` es monótona no decreciente y
   nunca excede `quantityWei` (o el objetivo de la market). Se expresa **siempre en base
   (wei)**: es la suma de los `q_wei` de todos los fills, también para órdenes market por
   `quoteOrderQty`. En `FILLED`, `executedQty == quantityWei` para órdenes por cantidad (para
   market por `quoteOrderQty`, `FILLED` significa objetivo de quote alcanzado, HU-04-02 RN-5).
   En `OPEN`, `executedQty = "0"`. El quote gastado/recibido se reporta aparte en
   `executedQuoteQty` (HU-04-06/07), **no** en `executedQty`.
8. **RN-8 (coherencia con reserva, INV-7).** Mientras la orden esté en `OPEN` o
   `PARTIALLY_FILLED`, su `remainingQty` (= `quantityWei − executedQty`) está respaldado por
   `bloqueado`. Al pasar a un terminal, el bloqueado asociado se ha consumido (fills) o
   liberado (cancelación/descarte).
9. **RN-9 (atomicidad de la transición).** Cada cambio de estado es atómico y consistente
   con los movimientos de fondos asociados (INV-3, INV-4): no hay estado observable
   incoherente entre el estado de la orden y los balances.
10. **RN-10 (persistencia).** El estado de cada orden persiste y se reconstruye desde el
    ledger/registro de órdenes tras un reinicio (INV-8); las órdenes `OPEN`/
    `PARTIALLY_FILLED` siguen abiertas con su prioridad intacta (INV-7).
11. **RN-11 (atomicidad del alta y recuperación de `NEW`).** El alta —reserva de fondos,
    entrega al matching y registro del estado resultante— es **atómica** (INV-4). Por lo
    tanto `NEW` es un estado **transitorio interno** que **nunca** es durable ni observable:
    no lo devuelve ninguna consulta (HU-04-06 RN-1) y **nunca** persiste a través de un
    reinicio. Tras recuperar (INV-8), una orden se encuentra **o bien** en su estado
    resultante (`OPEN`, `PARTIALLY_FILLED`, `FILLED`, `CANCELLED`, `REJECTED`) con su reserva
    consistente, **o bien** no existe (el alta no se había confirmado) y **no** quedó ninguna
    reserva tomada. No hay ventana en la que una orden quede en `NEW` con fondos bloqueados
    pero sin orden visible (evita fondos bloqueados indefinidamente, INV-2, INV-3).

## Criterios de aceptación (DoD)

### Escenario 1: Limit sin match ⇒ OPEN [AT-04-05-01]
- Dado un trader que coloca una limit válida sin contraparte cruzable
- Cuando se procesa el alta
- Entonces la orden queda `OPEN` con `executedQty="0"` y `remainingQty=quantityWei`
- (Nota: el estado `NEW` es transitorio interno y **no** es observable vía consultas externas, RN-11)

### Escenario 2: Limit con match parcial ⇒ NEW→PARTIALLY_FILLED [AT-04-05-02]
- Dado un trader que coloca una limit de 1 ETH con solo 0.4 ETH cruzables
- Cuando se procesa el alta
- Entonces ejecuta 0.4 ETH y queda `PARTIALLY_FILLED` con `executedQty="400000000000000000"`, remanente resting

### Escenario 3: Limit marketable total ⇒ NEW→FILLED [AT-04-05-03]
- Dado liquidez suficiente cruzable
- Cuando el trader coloca una limit que ejecuta completamente al entrar
- Entonces la orden queda `FILLED` con `executedQty == quantityWei`, sin remanente

### Escenario 4: Market total ⇒ NEW→FILLED [AT-04-05-04]
- Dado liquidez suficiente
- Cuando el trader coloca una market que completa su objetivo
- Entonces la orden queda `FILLED` y nunca descansó en el libro

### Escenario 5 (borde): Market parcial ⇒ NEW→CANCELLED (remanente descartado) [AT-04-05-05]
- Dado liquidez insuficiente para completar la market
- Cuando se procesa la market
- Entonces ejecuta lo disponible, descarta el remanente y queda `CANCELLED` con `executedQty>0` (RN-6)

### Escenario 6 (error): Market sin liquidez ⇒ REJECTED persistido [AT-04-05-06]
- Dado el lado opuesto vacío
- Cuando el trader coloca una market
- Entonces se rechaza con `MARKET_NO_LIQUIDITY` y la orden queda `REJECTED`, sin fills ni reserva
- Y **se persiste** como orden `REJECTED` (aparece en HU-04-07), por ser un rechazo de la capa de matching (RN-5, RE-12)

### Escenario 7 (error): Falla de validación ⇒ no se persiste como orden [AT-04-05-07]
- Dado un alta que viola una regla del par (p. ej. `INVALID_LOT_SIZE`)
- Cuando se procesa el alta
- Entonces no se reserva nada y no hay fills; el rechazo de validación **no** se persiste como orden (solo devuelve el error), por lo que **no** aparece en el historial (RN-5, RE-12)

### Escenario 8: Resting OPEN→PARTIALLY_FILLED→FILLED [AT-04-05-08]
- Dado una orden `OPEN` de 1 ETH
- Cuando un taker la ejecuta primero por 0.4 ETH y luego por 0.6 ETH
- Entonces transiciona `OPEN → PARTIALLY_FILLED → FILLED`, con `executedQty` monótona creciente hasta `quantityWei` (RN-7)

### Escenario 9: Cancelación OPEN→CANCELLED [AT-04-05-09]
- Dado una orden `OPEN`
- Cuando el dueño la cancela
- Entonces queda `CANCELLED` y se libera la reserva (HU-04-04)

### Escenario 10: Cancelación PARTIALLY_FILLED→CANCELLED [AT-04-05-10]
- Dado una orden `PARTIALLY_FILLED`
- Cuando el dueño la cancela
- Entonces queda `CANCELLED` con `executedQty` preservado y se libera el remanente

### Escenario 11 (error): Transición prohibida desde terminal [AT-04-05-11]
- Dado una orden `FILLED`
- Cuando se intenta cancelarla (transición `FILLED→CANCELLED`)
- Entonces se rechaza con `ORDER_NOT_CANCELLABLE` (409) y el estado permanece `FILLED` (RN-2, RN-4)

### Escenario 12 (invariante): Estado terminal inmutable [AT-04-05-12]
- Dado cualquier orden en `FILLED`, `CANCELLED` o `REJECTED`
- Cuando ocurre cualquier evento posterior (cancelación, intento de fill)
- Entonces el estado **no** cambia y no se mueven fondos asociados a esa orden (RN-2, RN-9)

### Escenario 13 (persistencia): Estados sobreviven al reinicio [AT-04-05-13]
- Dado órdenes en distintos estados (`OPEN`, `PARTIALLY_FILLED`, `FILLED`, `CANCELLED`)
- Cuando el sistema se reinicia y reconstruye desde el ledger/registro
- Entonces cada orden conserva su estado y `executedQty`; las abiertas mantienen prioridad precio-tiempo (INV-7, INV-8)

### Escenario 14 (recuperación): `NEW` nunca sobrevive a un reinicio [AT-04-05-14]
- Dado un alta en curso (reserva + entrega al matching) interrumpida por un reinicio
- Cuando el sistema se recupera desde el ledger/registro (INV-8)
- Entonces **ninguna** orden queda en `NEW`: o bien figura en su estado resultante con la reserva consistente, o bien no existe y **no** quedó reserva tomada (RN-11)
- Y ninguna consulta devuelve `NEW` (HU-04-06 RN-1), ni antes ni después del reinicio

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-04-05-01 .. AT-04-05-14) pasan
- [ ] Reglas de negocio RN-1..RN-11 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md (`ORDER_NOT_CANCELLABLE`, `MARKET_NO_LIQUIDITY`)
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md (executedQty/remainingQty enteros)
- [ ] Sin violacion de invariantes globales (INV-2, INV-3, INV-4, INV-7, INV-8)
- [ ] (si aplica) Adherencia verificada al estandar on-chain citado — N/A
