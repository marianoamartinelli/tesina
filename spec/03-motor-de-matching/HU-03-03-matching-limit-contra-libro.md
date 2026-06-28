# HU-03-03 — Matching de orden limit contra el libro

- **Epica:** 03 — Motor de Matching
- **Actor / rol:** Trader autenticado (dispara el alta) / Sistema (motor de matching)
- **Prioridad:** Alta
- **Dependencias:** HU-03-01 (estructura), HU-03-02 (inserción del remanente), HU-03-06
  (prevención de auto-cruce), HU-03-05 (eventos); Épica 02 (fondos), Épica 05 (settlement).
  Épica 00 (fundaciones).
- **Estandares de dominio aplicables:** N/A (no on-chain). Aplica prioridad precio-tiempo y
  convenciones monetarias de 00-fundaciones.

## Historia
Como trader autenticado, quiero que mi orden `LIMIT` entrante se cruce contra el lado
opuesto del libro respetando prioridad precio-tiempo y se ejecute al **precio de la orden
pasiva (maker)**, para obtener fills (totales o parciales) con la mejor prioridad
disponible y, de quedar remanente, dejarlo pasivo en el libro.

## Contexto y alcance
Esta HU define el **algoritmo de cruce** de una orden `LIMIT` entrante (taker) contra el
lado opuesto: qué órdenes son cruzables, en qué orden se consumen, qué cantidad se ejecuta
por cruce, a qué **precio** y qué pasa con los remanentes del taker y del maker. La orden
llega validada (épica 04) y con fondos bloqueados (épica 02). El **cálculo y cobro de
fees** y la aplicación contable atómica del fill son responsabilidad de la épica 05; aquí
se determinan `cantidad`, `precio` y `quote_min` de cada fill y la transición de estados.
La **prevención de auto-cruce** se evalúa según HU-03-06. La emisión de eventos, según
HU-03-05.

## Reglas de negocio e invariantes
1. **RN-1 (condición de cruce).** Una `LIMIT` entrante es cruzable mientras exista, en el
   lado opuesto, una orden con precio compatible:
   - `BUY @ L` cruza contra asks con `ask_price ≤ L`, comenzando por el **best ask** (menor
     precio) y subiendo.
   - `SELL @ L` cruza contra bids con `bid_price ≥ L`, comenzando por el **best bid** (mayor
     precio) y bajando.
2. **RN-2 (recorrido por prioridad precio-tiempo).** El taker consume el lado opuesto en
   orden de prioridad: mejor precio primero; a igual precio, **FIFO por `seq`** (HU-03-01
   RN-6). Se agota por completo la orden maker del frente antes de pasar a la siguiente.
3. **RN-3 (precio de ejecución = precio del maker).** Cada fill se ejecuta al `price_min`
   de la **orden pasiva (maker)**, no al precio límite del taker. La diferencia favorable
   (price improvement) beneficia al taker.
4. **RN-4 (cantidad por fill).** La cantidad de cada fill es
   `q_fill = min(remaining_taker_wei, remaining_maker_wei)`. Tras el fill se actualizan
   ambos: `filledWei += q_fill`, `remainingWei −= q_fill`.
5. **RN-5 (notional del fill).** El monto en quote de cada fill es
   `quote_min = floor(q_fill × maker_price_min / 10^18)` (aritmética entera, `floor`,
   `convenciones-monetarias.md`). El **mismo** `quote_min` aplica a ambas patas (lo que
   paga el comprador = lo que recibe el vendedor, antes de fees).
6. **RN-6 (sin floats; big integers).** El producto `q_fill × maker_price_min` puede
   alcanzar ~`10^30`; se opera con enteros de precisión arbitraria. Prohibido floats.
7. **RN-7 (fin del cruce).** El cruce termina cuando ocurre lo primero de: (a) el taker
   queda con `remaining_taker_wei = 0` (fill total), o (b) no quedan órdenes cruzables en el
   lado opuesto a precio compatible (`best_opuesto` ya no satisface RN-1) o el lado opuesto
   queda vacío.
8. **RN-8 (remanente del taker → pasivo).** Si al terminar el cruce el taker `LIMIT` aún
   tiene `remaining_taker_wei > 0`, ese remanente se posa como pasivo a su precio límite `L`
   mediante HU-03-02 (estado `PARTIALLY_FILLED` si hubo fills; `OPEN` si no hubo ninguno).
   Esto **no** deja el libro cruzado porque ya no hay contraparte a `L` (RN-7).
9. **RN-9 (estados resultantes).**
   - Taker: `FILLED` si `remaining_taker_wei = 0`; `PARTIALLY_FILLED` si ejecutó algo y
     posa remanente; `OPEN` si no ejecutó nada y se posa completo (este último coincide con
     HU-03-02).
   - Cada maker tocado: `FILLED` si se agotó (`remaining_maker_wei = 0`, se retira del
     libro) o `PARTIALLY_FILLED` si solo se consumió en parte (permanece como best de su
     nivel, conservando su `seq`).
10. **RN-10 (atomicidad por fill — INV-4).** Cada fill (con su settlement en épica 05) se
    aplica de forma atómica; no hay estado parcial observable de un fill. Una secuencia de
    fills de un mismo taker se aplica fill a fill, cada uno atómico.
11. **RN-11 (no-cruce final — INV-7).** Al devolver el control, el libro **no** queda
    cruzado: o el taker se consumió, o su remanente se posó a un precio que ya no cruza.
12. **RN-12 (prevención de auto-cruce).** Si durante el recorrido el taker fuese a
    matchear contra una orden de **su misma cuenta**, se aplica HU-03-06 (self-trade
    prevention) con su política y, según el caso, se rechaza la operación
    (`SELF_TRADE_BLOCKED`). Ver HU-03-06 para el detalle.
13. **RN-13 (conservación — INV-1).** El conjunto de fills solo **redistribuye** fondos
    entre maker, taker y la cuenta de fees `EX` (épica 05); no altera `Σ total(·, A)` por
    activo. El bloqueo/liberación de remanentes mantiene `total = disponible + bloqueado`.
14. **RN-14 (liberación de excedente del taker BUY, por fill).** Cuando un taker `BUY @ L`
    ejecuta contra un `maker_price_min < L` (mejora de precio), la diferencia entre lo
    bloqueado a `L` y lo realmente pagado a `maker_price_min` queda **liberada**
    (bloqueado→disponible). La liberación ocurre **por cada fill individual** (no recién al
    cierre de la orden): el motor reporta en el evento `trade` el `quote_min` real del fill
    (precio maker × cantidad), de modo que la épica 02/05 libere de inmediato la diferencia.
    Para un fill de `q_fill` ejecutado a `maker_price_min`, el excedente liberado es:

    ```
    liberado_fill = floor(q_fill × L / 10^18) − floor(q_fill × maker_price_min / 10^18)  (USDC-min)
    ```

    La suma de `liberado_fill` sobre todos los fills, más el remanente que se reposa a `L`
    (si lo hay), reconstituye exactamente el bloqueo inicial (INV-1, INV-3). La granularidad
    por fill permite al usuario operar de inmediato con los fondos ya liberados.
15. **RN-15 (taker SELL con mejora de precio — sin excedente que liberar).** Un taker
    `SELL @ L` que cruza contra `bid_price > L` recibe **más** USDC que su mínimo
    (`floor(remainingWei × L / 10^18)`), pero su bloqueo está en **base (ETH)**, no en quote:
    bloquea `remainingWei` wei de ETH, que se consumen íntegros al ejecutarse. **No** hay
    excedente de USDC bloqueado que liberar (asimetría con el BUY): el vendedor simplemente
    **recibe** el `quote_min` real (a `bid_price`), que es mayor que su mínimo. Una
    implementación **no** debe intentar liberar USDC inexistente del lado del SELL (violaría
    INV-2/INV-3). El motor reporta el `quote_min` real por fill (a precio maker) igual que en
    RN-5.

## Criterios de aceptacion (DoD)

### Escenario 1: Fill total contra un único maker [AT-03-03-01]
- Dado un libro con un ask maker M: `SELL 1 ETH @ 2000.00` (`price_min = 2000000000`) de la
  cuenta U2
- Cuando ingresa de la cuenta U1 `BUY 1 ETH @ 2001.00` (`L = 2001000000`)
- Entonces como `ask_price (2000000000) ≤ L (2001000000)` se cruza (RN-1)
- Y se ejecuta `q_fill = 1 ETH = 1000000000000000000` al **precio del maker** `2000.00`
  (RN-3), con `quote_min = "2000000000"` (RN-5)
- Y el taker U1 queda `FILLED` y el maker M (U2) queda `FILLED` y se retira del libro (RN-9)
- Y U1 recibe mejora de precio: pagó a `2000.00`, no a `2001.00` (RN-3, RN-14)

### Escenario 2: Fill parcial del taker, remanente se posa [AT-03-03-02]
- Dado un libro con un ask maker `SELL 0.4 ETH @ 2000.00` (`remainingWei = 400000000000000000`)
- Cuando ingresa `BUY 1 ETH @ 2001.00`
- Entonces se ejecuta `q_fill = 0.4 ETH` a `2000.00` (`quote_min = "800000000"`), el maker
  queda `FILLED` y se retira (RN-4, RN-9)
- Y el remanente del taker `remainingWei = 600000000000000000` (0.6 ETH) se posa como pasivo
  en `bids @ 2001.00`, estado `PARTIALLY_FILLED` (RN-8)
- Y el libro no queda cruzado (RN-11)

### Escenario 3: Fill parcial del maker, taker se completa [AT-03-03-03]
- Dado un libro con un ask maker `SELL 2 ETH @ 2000.00` (`remainingWei = 2000000000000000000`)
- Cuando ingresa `BUY 1 ETH @ 2000.00` (`L = 2000000000`)
- Entonces se ejecuta `q_fill = 1 ETH` a `2000.00`, el taker queda `FILLED` (RN-4, RN-9)
- Y el maker queda `PARTIALLY_FILLED` con `remainingWei = 1000000000000000000` y permanece
  como best ask, conservando su `seq` (RN-9)

### Escenario 4: Recorrido por prioridad precio-tiempo (varios makers) [AT-03-03-04]
- Dado un libro de asks: A1 `SELL 0.5 ETH @ 2000.00` (`seq=1`), A2 `SELL 0.5 ETH @ 2000.00`
  (`seq=2`), A3 `SELL 1 ETH @ 2000.50` (`seq=3`)
- Cuando ingresa `BUY 1 ETH @ 2001.00`
- Entonces se consume primero A1 (0.5 ETH @ 2000.00), luego A2 (0.5 ETH @ 2000.00) por FIFO
  dentro del nivel (RN-2)
- Y el taker queda `FILLED` con 1 ETH ejecutado; A1 y A2 quedan `FILLED`; A3 **no** se toca
- Y A3 sigue siendo ask a `2000.50` con `seq=3` intacto

### Escenario 5: Cruce a través de múltiples niveles de precio [AT-03-03-05]
- Dado un libro de asks: A1 `SELL 0.5 ETH @ 2000.00`, A2 `SELL 0.5 ETH @ 2000.50`
- Cuando ingresa `BUY 1 ETH @ 2001.00`
- Entonces se ejecuta A1 (0.5 ETH @ **2000.00**, `quote_min = "1000000000"`) y luego A2
  (0.5 ETH @ **2000.50**, `quote_min = floor(5e17 × 2000500000 / 1e18) = "1000250000"`)
  (RN-2, RN-3, RN-5)
- Y cada fill usa el precio de **su** maker, no un precio promedio
- Y el taker queda `FILLED`

### Escenario 6 (borde): Precio límite igual al best opuesto sí cruza [AT-03-03-06]
- Dado un libro con `best_ask = 2000.00` (`2000000000`)
- Cuando ingresa `BUY 1 ETH @ 2000.00` (`L = 2000000000`)
- Entonces cruza porque `ask_price (2000000000) ≤ L` (condición con `≤`, RN-1)
- Y se ejecuta a `2000.00`

### Escenario 7 (borde): No hay contraparte cruzable, se posa completo [AT-03-03-07]
- Dado un libro con `best_ask = 2001.00` (`2001000000`)
- Cuando ingresa `BUY 1 ETH @ 2000.00` (`L = 2000000000`)
- Entonces no cruza (`ask_price (2001000000) > L`) y la orden se posa completa como best bid
  `2000.00`, estado `OPEN` (RN-7, RN-8, deriva a HU-03-02)
- Y no se emite evento de trade

### Escenario 8 (borde): SELL entrante cruza bids por prioridad descendente [AT-03-03-08]
- Dado un libro de bids: B1 `BUY 1 ETH @ 2000.00`, B2 `BUY 1 ETH @ 1999.50`
- Cuando ingresa `SELL 1.5 ETH @ 1999.50` (`L = 1999500000`)
- Entonces cruza primero B1 (mejor bid, 1 ETH @ **2000.00**), luego B2 (0.5 ETH @
  **1999.50**) por prioridad de precio descendente (RN-1, RN-2)
- Y el taker `SELL` queda `FILLED`; B1 `FILLED`; B2 `PARTIALLY_FILLED` con
  `remainingWei = 500000000000000000`

### Escenario 9 (conservación): Mejora de precio libera excedente del BUY [AT-03-03-09]
- Dado que U1 envía `BUY 1 ETH @ 2001.00` con quote bloqueado para `2001.00`
- Cuando se ejecuta contra un maker a `2000.00`
- Entonces el `quote_min` realmente pagado es `"2000000000"` (a `2000.00`), no `2001.00`
- Y la diferencia bloqueada de más (`2001000000 − 2000000000 = 1000000`) se libera
  (bloqueado→disponible) por la épica 02/05 (RN-14)
- Y se conserva `Σ total(·, USDC)` (INV-1, RN-13)

### Escenario 10 (error): Auto-cruce detectado durante el recorrido [AT-03-03-10]
- Dado un libro cuyo best ask cruzable pertenece a la **misma cuenta** del taker entrante
- Cuando el taker intentaría matchear contra esa orden propia
- Entonces se aplica la política de HU-03-06 y la operación se rechaza con
  `SELF_TRADE_BLOCKED` (422), sin aplicar fills (RN-12; detalle y casos en HU-03-06)

### Escenario 11 (conservación): Liberación acumulada de excedente en BUY multi-fill [AT-03-03-11]
- Dado que U1 envía `BUY 1 ETH @ 2001.00` (`L = 2001000000`) con quote bloqueado a `L`:
  `floor(10^18 × 2001000000 / 10^18) = "2001000000"`
- Y un libro de asks: A1 `SELL 0.5 ETH @ 2000.00`, A2 `SELL 0.5 ETH @ 2000.50`
- Cuando se ejecuta a través de ambos niveles (RN-2, RN-3)
- Entonces fill 1 (A1): `quote_min = "1000000000"`, excedente liberado
  `= floor(5×10^17 × 2001000000/10^18) − 1000000000 = 1000500000 − 1000000000 = "500000"`
- Y fill 2 (A2): `quote_min = "1000250000"`, excedente liberado
  `= 1000500000 − 1000250000 = "250000"`
- Y total pagado `= "2000250000"`, excedente total liberado `= 2001000000 − 2000250000 =
  "750000"` (= 500000 + 250000); `disponible(U1, USDC)` aumenta en `"750000"` (RN-14, INV-1,
  INV-3)
- Y el taker queda `FILLED`

### Escenario 12 (conservación): SELL con mejora de precio no libera USDC [AT-03-03-12]
- Dado un libro con `best_bid = 2000.00` (`2000000000`)
- Cuando U1 envía `SELL 1 ETH @ 1999.50` (`L = 1999500000`, bloquea 1 ETH = `10^18` wei)
- Entonces cruza a precio del maker `2000.00` (`bid_price > L`) y el `quote_min` **recibido**
  es `floor(10^18 × 2000000000 / 10^18) = "2000000000"`, no `1999500000` (RN-3, RN-15)
- Y **no** hay transición bloqueado→disponible en USDC del lado del vendedor: su bloqueo
  estaba en ETH y se consumió íntegro (RN-15; no se libera USDC inexistente, INV-2, INV-3)

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-*) pasan
- [ ] Reglas de negocio RN-1..RN-15 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md (floor,
      mismo `quote_min` por fill, sin floats)
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md),
      en particular INV-1, INV-4, INV-7
- [ ] (si aplica) Adherencia verificada al estandar on-chain citado — N/A
