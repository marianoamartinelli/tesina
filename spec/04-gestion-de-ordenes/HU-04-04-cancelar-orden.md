# HU-04-04 — Cancelar orden

- **Epica:** 04 — Gestión de Órdenes
- **Actor / rol:** Trader autenticado (dueño de la orden)
- **Prioridad:** Alta
- **Dependencias:** HU-04-01/02 (alta), HU-04-05 (estados), HU-02-* (liberación de
  fondos), HU-03-* (remoción del orderbook). Fundaciones (00).
- **Estandares de dominio aplicables:** N/A.

## Historia
Como **trader autenticado dueño de una orden abierta**, quiero **cancelarla**, para
**retirar del mercado el remanente no ejecutado y recuperar de inmediato los fondos que
tenía reservados para ese remanente**.

## Contexto y alcance
Cubre la cancelación de una orden propia en estado `OPEN` o `PARTIALLY_FILLED`: remoción
del remanente del orderbook (HU-03-*) y **liberación de la reserva del remanente** a
disponible (HU-02-*), dejando la orden en estado `CANCELLED`. La parte ya ejecutada **no**
se revierte (los fills son definitivos). No son cancelables las órdenes en estado terminal
(`FILLED`, `CANCELLED`, `REJECTED`), ni las market (que nunca descansan; ver nota). Cubre
también el aislamiento por cuenta y las condiciones de carrera con fills concurrentes.

> Nota: una orden `MARKET` nunca llega a un estado cancelable por el usuario (ejecuta y
> termina en el mismo paso); su remanente lo descarta el sistema, no el trader. La
> cancelación de esta HU aplica a órdenes `LIMIT` resting.

## Reglas de negocio e invariantes
1. **RN-1 (cancelables).** Solo se pueden cancelar órdenes propias en estado `OPEN` o
   `PARTIALLY_FILLED`. Cualquier otro estado ⇒ `ORDER_NOT_CANCELLABLE` (409),
   `details = { orderId, status }`.
2. **RN-2 (propiedad).** La orden debe pertenecer a la cuenta que cancela. Si no existe o
   pertenece a otra cuenta ⇒ `ORDER_NOT_FOUND` (404), `details = { orderId }` (no se filtra
   la existencia de órdenes ajenas, RE-7).
3. **RN-3 (liberación del remanente).** Al cancelar, se libera la reserva que respaldaba el
   **remanente no ejecutado** (RE-3): `bloqueado −= s; disponible += s` (INV-3). El sistema
   **rastrea la reserva efectivamente bloqueada por cada orden** (`reservaOrden`), actualizada
   fill a fill (consumo + liberación por mejor precio, HU-04-01 RN-8); al cancelar se libera
   **exactamente** `s = reservaOrden` vigente, **no** un valor recomputado con la fórmula.
   Para órdenes sin fills (o con fills exactamente al precio límite) `reservaOrden` coincide
   con:
   - **LIMIT BUY:** `floor(remainingQty × priceMin / 10^18)` USDC-min.
   - **LIMIT SELL:** `remainingQty` wei.
   En general, tras varios fills a **mejor** precio, `floor(remainingQty × priceMin / 10^18)`
   puede **subestimar** el bloqueado real por subaditividad del `floor`
   (`Σ floor(q_i × p) ≤ floor(Σ q_i × p)`, hasta `(N−1)` unidades con `N` fills); liberar el
   `reservaOrden` rastreado garantiza que el bloqueado de la orden quede en **exactamente 0**,
   sin residuo permanente (INV-3, INV-7). La parte ya consumida por fills previos no se toca.
4. **RN-4 (idempotencia/terminalidad).** Cancelar una orden ya `CANCELLED` (o `FILLED`/
   `REJECTED`) ⇒ `ORDER_NOT_CANCELLABLE` (409); el estado terminal no cambia y no se libera
   nada (ya fue liberado/consumido).
5. **RN-5 (atomicidad).** La transición a `CANCELLED`, la remoción del libro y la
   liberación de fondos ocurren de forma **atómica**: no hay estado observable con la orden
   removida pero los fondos aún bloqueados, ni viceversa (consistente con INV-3/INV-4).
6. **RN-6 (carrera con fill total).** Si entre la solicitud y su aplicación la orden se
   llena por completo (`FILLED`), la cancelación falla con `ORDER_NOT_CANCELLABLE` (409); el
   fill prevalece y no se libera nada.
7. **RN-7 (carrera con fill parcial).** Si concurre un fill parcial, la cancelación libera
   la reserva del remanente **vigente al momento de aplicarse** (post-fill), no la del
   remanente original. El resultado es consistente: lo ejecutado quedó liquidado, lo no
   ejecutado se liberó.
8. **RN-8 (conservación).** La cancelación es un flujo interno que **no** altera
   `Σ total(·, A)` (INV-1): solo mueve `bloqueado → disponible` dentro de la misma cuenta
   y activo.
9. **RN-9 (auth).** Requiere trader autenticado; sin credencial ⇒ `UNAUTHENTICATED` (401).
10. **RN-10 (persistencia).** El estado `CANCELLED` y la liberación de fondos persisten y
    se reconstruyen desde el ledger tras un reinicio (INV-8).

## Criterios de aceptación (DoD)

### Escenario 1: Cancelar una orden OPEN libera toda la reserva [AT-04-04-01]
- Dado un trader con una orden `BUY LIMIT` `OPEN`, `priceMin="2000000000"`, `quantityWei="1000000000000000000"`, `executedQty="0"`
- Y `bloqueado(USDC) = 2000000000`, `disponible(USDC) = 3000000000`
- Cuando cancela la orden
- Entonces la orden queda `CANCELLED` y se remueve del orderbook
- Y se liberan `2000000000` USDC-min: `bloqueado(USDC) = 0`, `disponible(USDC) = 5000000000`
- Y `total(USDC)` y la suma global no cambian (INV-1, INV-3)

### Escenario 2: Cancelar una orden PARTIALLY_FILLED libera solo el remanente [AT-04-04-02]
- Dado un trader con una orden `BUY LIMIT` `PARTIALLY_FILLED`, `priceMin="2000000000"`, `quantityWei="1000000000000000000"`, `executedQty="400000000000000000"` (0.4 ETH ya comprados)
- Y la reserva remanente bloqueada en USDC es `floor(600000000000000000 × 2000000000 / 10^18) = 1200000000`
- Cuando cancela la orden
- Entonces la orden queda `CANCELLED` con `executedQty="400000000000000000"`
- Y se liberan `1200000000` USDC-min del remanente; la parte ejecutada no se revierte

### Escenario 3 (venta): Cancelar SELL libera ETH del remanente [AT-04-04-03]
- Dado un trader con una orden `SELL LIMIT` `PARTIALLY_FILLED`, `quantityWei="1000000000000000000"`, `executedQty="300000000000000000"`, `bloqueado(ETH) = 700000000000000000`
- Cuando cancela la orden
- Entonces queda `CANCELLED` y se liberan `700000000000000000` wei a disponible (RN-3)

### Escenario 4 (error): Cancelar una orden FILLED [AT-04-04-04]
- Dado un trader con una orden `FILLED`
- Cuando intenta cancelarla
- Entonces se rechaza con `ORDER_NOT_CANCELLABLE` (409), `details = { orderId, status:"FILLED" }`
- Y no se libera nada (ya fue consumida)

### Escenario 5 (error): Cancelar una orden ya CANCELLED [AT-04-04-05]
- Dado un trader con una orden `CANCELLED`
- Cuando intenta cancelarla de nuevo
- Entonces se rechaza con `ORDER_NOT_CANCELLABLE` (409), `details = { orderId, status:"CANCELLED" }`
- Y los balances no cambian (RN-4)

### Escenario 6 (error): Cancelar una orden REJECTED [AT-04-04-06]
- Dado un registro de orden `REJECTED` (que nunca llegó al libro)
- Cuando se intenta cancelarla
- Entonces se rechaza con `ORDER_NOT_CANCELLABLE` (409), `details = { orderId, status:"REJECTED" }`

### Escenario 7 (error): Orden inexistente [AT-04-04-07]
- Dado un trader autenticado
- Cuando cancela `orderId` que no existe
- Entonces se rechaza con `ORDER_NOT_FOUND` (404), `details = { orderId }`

### Escenario 8 (error): Orden de otra cuenta [AT-04-04-08]
- Dado un trader A autenticado y una orden `OPEN` perteneciente a la cuenta B
- Cuando A intenta cancelar la orden de B
- Entonces se rechaza con `ORDER_NOT_FOUND` (404) (no se revela que la orden existe, RE-7)
- Y la orden de B permanece `OPEN` e intacta

### Escenario 9 (secuencia): Cancelar pierde contra un fill total ya aplicado [AT-04-04-09]
- Dado un trader con una orden que **ya** fue marcada `FILLED` (el fill total se aplicó en el ledger **antes** de procesar la cancelación)
- Cuando llega la solicitud de cancelación
- Entonces se rechaza con `ORDER_NOT_CANCELLABLE` (409); el fill prevalece y no se libera ni se duplica fondo alguno (INV-1, INV-4, RN-6)

### Escenario 10 (secuencia): Cancelar tras un fill parcial ya aplicado libera el remanente vigente [AT-04-04-10]
- Dado un trader con una orden de 1 ETH que **ya** recibió un fill parcial de 0.4 ETH y ahora está `PARTIALLY_FILLED` (el fill se aplicó **antes** de la cancelación)
- Cuando se procesa la cancelación
- Entonces la orden queda `CANCELLED` con `executedQty="400000000000000000"`
- Y se libera la reserva del remanente **vigente** (`reservaOrden` post-fill), no la original (RN-3, RN-7)

### Escenario 11 (error): No autenticado [AT-04-04-11]
- Dado un cliente sin credencial válida
- Cuando intenta cancelar una orden
- Entonces se rechaza con `UNAUTHENTICATED` (401)

### Escenario 12 (persistencia): La cancelación sobrevive al reinicio [AT-04-04-12]
- Dado una orden recién `CANCELLED` con su reserva liberada
- Cuando el sistema se reinicia y reconstruye desde el ledger
- Entonces la orden sigue `CANCELLED`, ausente del orderbook, y los balances reconstruidos coinciden (INV-8)

### Escenario 13 (borde): Cancelar tras varios fills a mejor precio deja el bloqueado en 0 [AT-04-04-13]
- Dado una orden `BUY LIMIT` `priceMin="2000000000"`, `quantityWei="1000000000000000000"` (1 ETH), con reserva inicial `reservaOrden = 2000000000` USDC-min
- Y dos fills parciales a **mejor** precio: `300000000000000000` wei (0.3 ETH) a `1990000000` y `300000000000000000` wei (0.3 ETH) a `1990000000` (consumo y liberación por mejor precio actualizan `reservaOrden` fill a fill, HU-04-01 RN-8)
- Y la orden queda `PARTIALLY_FILLED` con `executedQty="600000000000000000"` y remanente `400000000000000000` wei
- Cuando cancela la orden
- Entonces se libera **exactamente** el `reservaOrden` vigente y el `bloqueado(USDC)` de esa orden queda en **0** (sin residuo por subaditividad del `floor`, RN-3, INV-3, INV-7)

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-04-04-01 .. AT-04-04-13) pasan
- [ ] Reglas de negocio RN-1..RN-10 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md (`ORDER_NOT_CANCELLABLE`, `ORDER_NOT_FOUND`)
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md (liberación exacta del remanente)
- [ ] Sin violacion de invariantes globales (INV-1, INV-3, INV-4, INV-8)
- [ ] (si aplica) Adherencia verificada al estandar on-chain citado — N/A
