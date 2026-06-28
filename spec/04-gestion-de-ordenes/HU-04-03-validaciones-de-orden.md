# HU-04-03 — Validaciones de orden

- **Epica:** 04 — Gestión de Órdenes
- **Actor / rol:** Trader autenticado / Sistema (validador de alta de órdenes)
- **Prioridad:** Alta
- **Dependencias:** HU-04-01 (limit), HU-04-02 (market), HU-02-* (fondos), HU-03-*
  (self-trade, liquidez). Fundaciones (00, en especial `modelo-de-errores.md §4`).
- **Estandares de dominio aplicables:** N/A.

## Historia
Como **trader autenticado**, quiero **que el sistema valide mi orden de forma estricta y
con un orden de evaluación predecible**, para **recibir un único error claro y estable
cuando algo está mal, sin efectos colaterales sobre mis fondos**.

## Contexto y alcance
Centraliza el **conjunto de reglas de validación** del alta de órdenes (limit y market) y,
sobre todo, su **precedencia determinista**: ante múltiples violaciones se reporta **una
sola**, la primera según el orden definido. Esto hace que los tests de aceptación sean
reproducibles y que el `code` devuelto sea estable. Las reglas individuales se comparten
con HU-04-01 y HU-04-02; aquí se fijan los disparadores exactos, los casos de positividad
y la precedencia. No cubre la ejecución del matching ni el settlement.

## Reglas de negocio e invariantes
1. **RN-1 (precedencia, RE-4).** El validador evalúa en este orden y devuelve **el primer**
   error que aplique (un error por respuesta):
   0. **Rate limiting** (capa de red/middleware) → `RATE_LIMITED` (429) si la cuenta supera
      el límite configurado (RE-10; antes de autenticación; límite en HU-09-*).
   1. **Autenticación** → `UNAUTHENTICATED` (401); **autorización** → `UNAUTHORIZED` (403).
      Nota: en esta épica las órdenes se colocan/operan **siempre** en nombre de la cuenta
      autenticada (no hay parámetro `accountId`). Referir una orden ajena devuelve
      `ORDER_NOT_FOUND` (404, RE-7), **no** `UNAUTHORIZED`; `UNAUTHORIZED` (403) se reserva
      para autorizaciones a nivel de cuenta definidas en `01-cuentas-y-autenticación` (p. ej.
      cuenta deshabilitada/suspendida).
   2. **Esquema/tipos** → `VALIDATION_ERROR` (422): campo faltante, tipo incorrecto, monto
      que no matchea `^(0|[1-9][0-9]*)$`, y la regla de forma única de tamaño en market
      (exactamente uno de `quantityWei`/`quoteOrderQty`).
   3. **Enums y combinaciones** → `INVALID_SIDE`, `INVALID_ORDER_TYPE`, `PRICE_REQUIRED`,
      `PRICE_NOT_ALLOWED` (422).
   4. **Reglas del par** → `INVALID_PRICE_TICK`, `INVALID_LOT_SIZE`, `BELOW_MIN_NOTIONAL`
      (422).
   5. **Idempotencia** → `DUPLICATE_CLIENT_ORDER_ID` (409).
   6. **Liquidez de market (precondición de solo lectura)** → `MARKET_NO_LIQUIDITY` (422) si
      la orden es `MARKET` y el lado opuesto está **vacío**; se evalúa **antes** de fondos y
      **sin** reservar (RE-4 paso 6). Por eso prevalece sobre `INSUFFICIENT_FUNDS`.
   7. **Fondos** → `INSUFFICIENT_FUNDS` (422).
   8. **Matching (barrido)** → `SELF_TRADE_BLOCKED` (422); si se detecta tras reservar, la
      reserva se **revierte atómicamente** (HU-04-01 RN-10, HU-04-02 RN-9).
2. **RN-2 (esquema/serialización).** Todo monto/precio/cantidad recibido debe ser string y
   matchear `^(0|[1-9][0-9]*)$` (sin floats, decimales, signo, notación científica ni ceros
   a la izquierda). Si no, `VALIDATION_ERROR` con `details.issues`.
3. **RN-3 (`side`).** `side ∉ {BUY, SELL}` ⇒ `INVALID_SIDE` (422), `details = { side }`.
4. **RN-4 (`type`).** `type ∉ {LIMIT, MARKET}` ⇒ `INVALID_ORDER_TYPE` (422),
   `details = { type }`.
5. **RN-5 (precio según tipo).** `LIMIT` sin `priceMin` ⇒ `PRICE_REQUIRED` (422). `MARKET`
   con `priceMin` ⇒ `PRICE_NOT_ALLOWED` (422).
6. **RN-6 (tick).** Para `LIMIT`: `priceMin mod 10000 == 0 ∧ priceMin > 0`; en caso
   contrario `INVALID_PRICE_TICK` (422), `details = { priceMin, tickSize:"10000" }`. El
   caso `priceMin = 0` también cae en `INVALID_PRICE_TICK` (no es positivo).
7. **RN-7 (lot).** Cuando hay `quantityWei` (siempre en limit; en market por cantidad):
   `quantityWei mod 10^14 == 0 ∧ quantityWei > 0`; si no, `INVALID_LOT_SIZE` (422),
   `details = { quantityWei, lotSize:"100000000000000" }`. El caso `quantityWei = 0`
   también cae en `INVALID_LOT_SIZE`.
8. **RN-8 (mínimo notional).** Para `LIMIT`:
   `notional_min = floor(quantityWei × priceMin / 10^18) ≥ 10000000`; si no,
   `BELOW_MIN_NOTIONAL` (422), `details = { notionalMin, minNotional:"10000000" }`. Para
   `MARKET`: notional estimado según HU-04-02 RN-3 ≥ `10000000`.
9. **RN-9 (positividad como subcaso).** No existen códigos separados de "no positivo": un
   precio ≤ 0 se canaliza por `INVALID_PRICE_TICK` y una cantidad ≤ 0 por
   `INVALID_LOT_SIZE`; un `quoteOrderQty ≤ 0` o que no matchea el patrón cae en
   `VALIDATION_ERROR`.
10. **RN-10 (idempotencia).** `clientOrderId` repetido por la cuenta ⇒
    `DUPLICATE_CLIENT_ORDER_ID` (409), evaluado **después** de las reglas del par y **antes**
    de la precondición de liquidez y de fondos. La unicidad es **permanente por cuenta**
    (lifetime): no se reutiliza aunque la orden original esté en estado terminal. El alcance
    es **por cuenta** (índice `(accountId, clientOrderId)`): dos cuentas distintas pueden usar
    el mismo `clientOrderId` sin conflicto (RE-5).
11. **RN-11 (sin efectos colaterales).** Cualquier rechazo de validación deja balances,
    reservas y orderbook **intactos** (INV-2): no se bloquea, no se crea orden con estado
    distinto de `REJECTED` para auditoría, no se emite fill.
12. **RN-12 (estabilidad de `code`).** Los `code` provienen del catálogo de
    `00-fundaciones/modelo-de-errores.md` y son estables; `message` es libre pero coherente
    con el `code`.

## Criterios de aceptación (DoD)

### Escenario 1: Precedencia — tick gana sobre fondos [AT-04-03-01]
- Dado un trader autenticado con `disponible(USDC) = 0`
- Cuando coloca `side=BUY, type=LIMIT, priceMin="2000005000", quantityWei="1000000000000000000"` (precio fuera de tick **y** sin fondos)
- Entonces se reporta **solo** `INVALID_PRICE_TICK` (regla del par precede a fondos, RN-1)
- Y no se reporta `INSUFFICIENT_FUNDS`

### Escenario 2 (error): Lado inválido [AT-04-03-02]
- Dado un trader autenticado
- Cuando coloca una orden con `side="LONG"`
- Entonces se rechaza con `INVALID_SIDE` (422), `details = { side:"LONG" }`

### Escenario 3 (error): Tipo de orden inválido [AT-04-03-03]
- Dado un trader autenticado
- Cuando coloca una orden con `type="STOP"`
- Entonces se rechaza con `INVALID_ORDER_TYPE` (422), `details = { type:"STOP" }`

### Escenario 4 (error): Limit sin precio [AT-04-03-04]
- Dado un trader autenticado
- Cuando coloca `side=BUY, type=LIMIT, quantityWei="1000000000000000000"` sin `priceMin`
- Entonces se rechaza con `PRICE_REQUIRED` (422)

### Escenario 5 (error): Market con precio [AT-04-03-05]
- Dado un trader autenticado
- Cuando coloca `side=BUY, type=MARKET, quoteOrderQty="2000000000", priceMin="2000000000"`
- Entonces se rechaza con `PRICE_NOT_ALLOWED` (422)

### Escenario 6 (error): Precio fuera de tick [AT-04-03-06]
- Dado un trader autenticado
- Cuando coloca `type=LIMIT, priceMin="2000005000"` (no múltiplo de 10000)
- Entonces se rechaza con `INVALID_PRICE_TICK` (422), `details = { priceMin:"2000005000", tickSize:"10000" }`

### Escenario 7 (error): Cantidad fuera de lot [AT-04-03-07]
- Dado un trader autenticado
- Cuando coloca `type=LIMIT, priceMin="2000000000", quantityWei="50000000000000"` (0.00005 ETH)
- Entonces se rechaza con `INVALID_LOT_SIZE` (422), `details = { quantityWei:"50000000000000", lotSize:"100000000000000" }`

### Escenario 8 (error): Notional por debajo del mínimo [AT-04-03-08]
- Dado un trader autenticado con fondos suficientes
- Cuando coloca `type=LIMIT, priceMin="2000000000", quantityWei="100000000000000"` (0.0001 ETH @ 2000 ⇒ notional `200000` = 0.2 USDC)
- Entonces se rechaza con `BELOW_MIN_NOTIONAL` (422), `details = { notionalMin:"200000", minNotional:"10000000" }`

### Escenario 9 (error): Monto no entero / float / patrón inválido [AT-04-03-09]
- Dado un trader autenticado
- Cuando coloca `type=LIMIT, priceMin="2000.50", quantityWei="1e18"` (decimal y notación científica)
- Entonces se rechaza con `VALIDATION_ERROR` (422) y `details.issues` lista los campos que no matchean `^(0|[1-9][0-9]*)$`
- Y ningún monto cruza la frontera de la API como número de punto flotante

### Escenario 10 (borde): Precio cero ⇒ tick [AT-04-03-10]
- Dado un trader autenticado
- Cuando coloca `type=LIMIT, priceMin="0", quantityWei="1000000000000000000"`
- Entonces se rechaza con `INVALID_PRICE_TICK` (422) (precio no positivo, RN-6, RN-9)

### Escenario 11 (borde): Cero a la izquierda rechazado [AT-04-03-11]
- Dado un trader autenticado
- Cuando coloca `priceMin="02000000000"` (cero a la izquierda)
- Entonces se rechaza con `VALIDATION_ERROR` (422) (no matchea `^(0|[1-9][0-9]*)$`, RN-2)

### Escenario 12 (precedencia): Idempotencia gana sobre fondos [AT-04-03-12]
- Dado un trader que ya usó `clientOrderId="dup-1"` y ahora tiene `disponible(USDC) = 0`
- Cuando reenvía una orden válida en forma con `clientOrderId="dup-1"`
- Entonces se reporta `DUPLICATE_CLIENT_ORDER_ID` (409) y **no** `INSUFFICIENT_FUNDS` (RN-1, RN-10)

### Escenario 13 (precedencia): Fondos gana sobre matching [AT-04-03-13]
- Dado un trader autenticado con `disponible(USDC) = 0` y un ask resting ajeno cruzable
- Cuando coloca una orden BUY válida en forma y reglas del par pero sin fondos
- Entonces se reporta `INSUFFICIENT_FUNDS` (422) y **no** se evalúa el matching (RN-1)

### Escenario 14 (error): No autenticado [AT-04-03-14]
- Dado un cliente sin credencial válida
- Cuando intenta colocar cualquier orden
- Entonces se rechaza con `UNAUTHENTICATED` (401) **antes** de cualquier otra validación (RN-1)

### Escenario 15 (sin efectos colaterales): Rechazo no toca balances [AT-04-03-15]
- Dado un trader con `disponible(USDC) = 5000000000` y `bloqueado(USDC) = 0`
- Cuando coloca una orden que falla cualquier validación (p. ej. `INVALID_PRICE_TICK`)
- Entonces los balances quedan exactamente igual (`disponible = 5000000000`, `bloqueado = 0`)
- Y no se crea ninguna orden abierta ni se emite fill (RN-11, INV-2)

### Escenario 16 (borde): Cantidad cero ⇒ lot [AT-04-03-16]
- Dado un trader autenticado
- Cuando coloca `type=LIMIT, priceMin="2000000000", quantityWei="0"`
- Entonces se rechaza con `INVALID_LOT_SIZE` (422) (cantidad no positiva, RN-7, RN-9)

### Escenario 17 (borde): Monto negativo rechazado [AT-04-03-17]
- Dado un trader autenticado
- Cuando coloca `quantityWei="-100"` (negativo)
- Entonces se rechaza con `VALIDATION_ERROR` (422) (no matchea el patrón, RN-2)

### Escenario 18 (autorización): Operar sobre otra cuenta no expone `UNAUTHORIZED` [AT-04-03-18]
- Dado un trader A autenticado
- Cuando intenta referir/operar una orden de la cuenta B (el alta es siempre en nombre de A; no hay parámetro `accountId`)
- Entonces el acceso a un recurso ajeno devuelve `ORDER_NOT_FOUND` (404, RE-7), **no** `UNAUTHORIZED`
- Y `UNAUTHORIZED` (403) queda reservado para autorizaciones a nivel de cuenta de `01-cuentas-y-autenticación` (p. ej. cuenta deshabilitada): es **N/A** para el alta de órdenes de esta épica (RN-1)

### Escenario 19 (idempotencia, alcance por cuenta): Dos cuentas, mismo `clientOrderId` [AT-04-03-19]
- Dado un trader A con una orden exitosa con `clientOrderId="shared"`
- Cuando un trader B coloca una orden válida con el mismo `clientOrderId="shared"`
- Entonces la orden de B se **acepta** sin `DUPLICATE_CLIENT_ORDER_ID` (el alcance de unicidad es por cuenta, no global, RN-10, RE-5)

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-04-03-01 .. AT-04-03-19) pasan
- [ ] Reglas de negocio RN-1..RN-12 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md (códigos y precedencia §4)
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md (sin floats; patrón de serialización)
- [ ] Sin violacion de invariantes globales (INV-2 en rechazos; sin efectos colaterales)
- [ ] (si aplica) Adherencia verificada al estandar on-chain citado — N/A
