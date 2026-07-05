# HU-03-06 — Prevención de auto-cruce (self-trade prevention)

- **Epica:** 03 — Motor de Matching
- **Actor / rol:** Trader autenticado (dispara el alta) / Sistema (motor de matching)
- **Prioridad:** Alta
- **Dependencias:** HU-03-03 (matching limit), HU-03-04 (market), HU-03-01 (estructura);
  Épica 02 (fondos), Épica 04 (alta/validación). Épica 00 (fundaciones, `SELF_TRADE_BLOCKED`).
- **Estandares de dominio aplicables:** N/A (no on-chain).

## Historia
Como trader autenticado, quiero que una orden mía no se ejecute contra otra orden mía (no
hacer self-trade), para no generar trades artificiales contra mí mismo ni alterar el libro
con cruces ficticios, con una política de resolución clara y determinista.

## Contexto y alcance
Esta HU fija la **política de self-trade prevention (STP)** del exchange: qué se considera
auto-cruce y cómo se resuelve. Un **self-trade** ocurre cuando la misma cuenta sería a la
vez maker y taker de un mismo fill (`glosario.md`). El proyecto **fija una** política (no
deja la decisión a la implementación): **rechazo atómico de la orden entrante**
(*cancel-incoming, whole-order*). Aplica tanto a `LIMIT` como a `MARKET`.

Esta política se evalúa en el paso de **matching** (paso 7 de la precedencia de
`modelo-de-errores.md` §4), es decir **después** de auth, esquema, enums, reglas del par,
idempotencia y fondos. La épica 04 entrega la orden ya validada; el motor aplica la STP al
intentar cruzar.

> **Política fijada (convención del proyecto):** si la orden entrante, dada su cantidad (y
> su presupuesto, para `MARKET BUY`), **consumiría** alguna orden pasiva de la **misma
> cuenta**, la orden entrante se **rechaza por completo de forma atómica**
> (`SELF_TRADE_BLOCKED`), **sin aplicar ningún fill** y **sin** posar remanente. Se
> documentan abajo las alternativas consideradas y por qué se descartan.

## Reglas de negocio e invariantes
1. **RN-1 (definición de self-trade).** Hay self-trade si una orden pasiva del lado opuesto
   que la entrante **consumiría** durante su recorrido pertenece al **mismo `accountId`** que
   la entrante.
2. **RN-2 (rango consumible).** El "rango consumible" es el conjunto de órdenes pasivas que
   la entrante ejecutaría según prioridad precio-tiempo (HU-03-03 RN-2) hasta completar su
   cantidad o, para `MARKET BUY`, hasta agotar su presupuesto (HU-03-04 RN-5). Una orden
   propia que la entrante **no alcanzaría a consumir** (queda fuera del rango) **no** dispara
   STP.
3. **RN-3 (política: rechazo atómico de la entrante).** Si dentro del rango consumible
   existe al menos una orden de la misma cuenta, la orden entrante se **rechaza
   íntegramente**: no se aplica ningún fill, no se modifica ninguna orden pasiva (ni propia
   ni de terceros dentro del rango), no se posa remanente. La operación es **atómica**
   (INV-4): el libro y los balances quedan **idénticos** al estado previo.
4. **RN-4 (error y precedencia).** El rechazo se reporta con `SELF_TRADE_BLOCKED` (HTTP
   422), `details.restingOrderId` = el `orderId` de la **orden propia de mayor prioridad**
   dentro del rango consumible. Se evalúa **después** de fondos (`INSUFFICIENT_FUNDS`) y con
   **precedencia inequívoca** sobre los errores de liquidez de `MARKET`
   (`modelo-de-errores.md` §4 paso 7):
   - `SELF_TRADE_BLOCKED` se evalúa **primero**: si el lado opuesto contiene **al menos una**
     orden que la entrante cruzaría (aunque toda esa liquidez sea propia, y aunque esté
     distribuida en varios niveles de precio), el error es `SELF_TRADE_BLOCKED`.
   - `MARKET_NO_LIQUIDITY` solo aplica si el lado opuesto está **completamente vacío** antes
     de evaluar STP (no hay ninguna orden que cruzar).
   - `MARKET_BUDGET_INSUFFICIENT` (HU-03-04 RN-9) aplica cuando el lado opuesto **no** está
     vacío pero el presupuesto no cubre ni 1 lot del mejor maker disponible, **sea de quien
     sea** esa liquidez: con `max_lots = 0` desde el inicio, el rango consumible (RN-2) es
     **vacío**, no hay STP que evaluar y el error es `MARKET_BUDGET_INSUFFICIENT`.

   Un solo error por respuesta.
5. **RN-5 (estado de la orden entrante).** La orden rechazada por STP queda en estado
   terminal `REJECTED`; **no** ingresa al libro y no aparece como abierta.
6. **RN-6 (liberación de fondos).** Como no se ejecuta nada, los fondos reservados por la
   épica 02 para la orden entrante se **liberan** íntegros (bloqueado→disponible); no hay
   cambio neto de balances (INV-1, INV-2, INV-3).
7. **RN-7 (no se consume liquidez de terceros).** Bajo esta política, aunque el rango
   consumible incluya órdenes de **otras** cuentas con mejor prioridad que la propia, **no**
   se ejecutan: el rechazo es del **conjunto** de la orden entrante. (Esta es la elección
   conservadora declarada; ver "Alternativas".)
8. **RN-8 (aplicable a LIMIT y MARKET).** La política rige igual para `LIMIT` cruzante y
   para `MARKET`. Para una `LIMIT` que **no** sería cruzable (se posaría sin tocar el libro),
   no hay rango consumible y por lo tanto **no** hay STP: la orden se posa normalmente,
   aunque la cuenta ya tenga órdenes en el otro lado a precios no cruzados.
9. **RN-9 (determinismo).** Dada la misma orden y el mismo libro, la decisión de STP y el
   `restingOrderId` reportado son únicos y reproducibles.
10. **RN-10 (la cuenta puede tener órdenes en ambos lados).** Tener órdenes propias en
    ambos lados del libro es **lícito** mientras no se crucen (precios no solapados). La STP
    solo actúa cuando una entrante **cruzaría** una propia.

### Alternativas consideradas (descartadas, documentadas para trazabilidad)
- *Cancel-remainder del taker tras matchear terceros*: ejecutaría primero contra otras
  cuentas y cancelaría el remanente al toparse con la propia. Descartada por introducir un
  resultado mixto (a veces éxito con fills, a veces error) que complica "un error por
  respuesta" y la atomicidad.
- *Cancel-resting (cancelar la orden propia pasiva)*: alteraría órdenes ya colocadas por la
  cuenta de forma implícita. Descartada por efectos colaterales sorpresivos.
- *Skip (saltear la orden propia y seguir con la siguiente)*: rompe estrictamente la
  prioridad precio-tiempo. Descartada.
- *Decrement-both*: complejidad innecesaria para un exchange simplificado.

## Criterios de aceptacion (DoD)

### Escenario 1: Cruce normal contra terceros (sin self-trade) [AT-03-06-01]
- Dado un libro con un ask `SELL 1 ETH @ 2000.00` de la cuenta **U2**
- Cuando la cuenta **U1** envía `BUY 1 ETH @ 2000.00`
- Entonces como el rango consumible no contiene órdenes de U1, **no** hay STP: el cruce se
  ejecuta normalmente (RN-1, RN-2) y la orden de U1 queda `FILLED`

### Escenario 2: Auto-cruce en el frente — rechazo atómico [AT-03-06-02]
- Dado un libro cuyo **best ask** `SELL 1 ETH @ 2000.00` pertenece a la cuenta **U1**
  (`orderId = A`)
- Cuando **U1** envía `BUY 1 ETH @ 2000.00` (cruzaría A)
- Entonces se rechaza con `SELF_TRADE_BLOCKED` (422), `details.restingOrderId = "A"` (RN-3,
  RN-4)
- Y no se aplica ningún fill, la orden A queda intacta, la entrante queda `REJECTED` (RN-5)
- Y los fondos reservados para la entrante se liberan; balances idénticos al estado previo
  (RN-6)

### Escenario 3 (borde): Orden propia dentro del rango, tras una de terceros [AT-03-06-03]
- Dado asks: A1 `SELL 0.5 ETH @ 2000.00` de **U2** (`seq=1`) y A2 `SELL 0.5 ETH @ 2000.00`
  de **U1** (`seq=2`, `orderId = A2`)
- Cuando **U1** envía `BUY 1 ETH @ 2000.00` (rango consumible = {A1, A2})
- Entonces, como A2 (propia) está en el rango consumible, se rechaza **toda** la entrante
  con `SELF_TRADE_BLOCKED`, `details.restingOrderId = "A2"` (RN-2, RN-3, RN-7)
- Y A1 (de U2) **no** se ejecuta; el libro queda idéntico (RN-3, INV-4)

### Escenario 4 (borde): Orden propia fuera del rango consumible — no dispara STP [AT-03-06-04]
- Dado asks: A1 `SELL 1 ETH @ 2000.00` de **U2** (`seq=1`) y A2 `SELL 1 ETH @ 2000.50` de
  **U1** (`seq=2`)
- Cuando **U1** envía `BUY 1 ETH @ 2000.00` (`L = 2000000000`)
- Entonces el rango consumible es solo {A1} (A2 está a `2000.50 > L`, no cruzable): **no**
  hay self-trade (RN-2)
- Y la entrante se ejecuta contra A1 (1 ETH @ 2000.00) y queda `FILLED`; A2 (propia) sigue
  intacta en el libro

### Escenario 5 (borde): LIMIT propia no cruzable se posa con órdenes propias del otro lado [AT-03-06-05]
- Dado que **U1** ya tiene `SELL 1 ETH @ 2001.00` en `asks`
- Cuando **U1** envía `BUY 1 ETH @ 2000.00` (`L = 2000000000 < 2001000000`, no cruza)
- Entonces no hay rango consumible (no cruza) y la `BUY` se **posa** normalmente como best
  bid; tener órdenes propias en ambos lados sin solapar es lícito (RN-8, RN-10)

### Escenario 6: MARKET con contraparte propia [AT-03-06-06]
- Dado que el único ask del libro `SELL 1 ETH @ 2000.00` pertenece a **U1** (`orderId = A`)
- Cuando **U1** envía `MARKET BUY 1 ETH`
- Entonces el rango consumible contiene A (propia): se rechaza con `SELF_TRADE_BLOCKED`
  (422), `details.restingOrderId = "A"`, sin fills (RN-8)
- Y **no** se reporta `MARKET_NO_LIQUIDITY` (sí hay liquidez, solo que es propia)

### Escenario 7 (integridad): Atomicidad e idempotencia del rechazo [AT-03-06-07]
- Dado un libro con una orden propia en el rango consumible de la entrante
- Cuando se procesa la entrante (incluso si se reintenta)
- Entonces cada intento rechazado deja libro y balances exactamente iguales al estado previo
  (RN-3, INV-4) y no produce fills ni eventos `trade`
- Y el `restingOrderId` reportado es siempre el mismo (determinismo, RN-9)

### Escenario 8 (borde): Lado opuesto con varios niveles, todos propios — STP, no NO_LIQUIDITY [AT-03-06-08]
- Dado que **todo** el lado de asks pertenece a **U1**: A1 `SELL 0.5 ETH @ 2000.00`
  (`seq=1`, `orderId = A1`) y A2 `SELL 0.5 ETH @ 2000.50` (`seq=2`)
- Cuando **U1** envía `MARKET BUY 1 ETH` (o `BUY 1 ETH @ 2001.00`), cuyo rango consumible es
  {A1, A2}, ambas propias
- Entonces se rechaza con `SELF_TRADE_BLOCKED` (422), `details.restingOrderId = "A1"` (la
  propia de **mayor prioridad**), sin fills (RN-3, RN-4)
- Y **no** se reporta `MARKET_NO_LIQUIDITY`: hay liquidez en el lado opuesto aunque sea toda
  propia (RN-4, precedencia)
- Y el libro queda idéntico (INV-4)

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-*) pasan
- [ ] Reglas de negocio RN-1..RN-10 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md
      (`SELF_TRADE_BLOCKED`, precedencia §4 paso 7)
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md),
      en particular INV-2, INV-3, INV-4
- [ ] (si aplica) Adherencia verificada al estandar on-chain citado — N/A
