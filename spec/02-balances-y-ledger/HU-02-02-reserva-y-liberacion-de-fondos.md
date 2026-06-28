# HU-02-02 — Reserva y liberación de fondos

- **Epica:** 02 — Balances y Ledger
- **Actor / rol:** Sistema (motor de balances), disparado por acciones del trader (alta/cancelación de orden, solicitud de retiro) y por el matching (fills).
- **Prioridad:** Alta
- **Dependencias:** HU-02-01 (modelo de buckets); HU-02-03 (cada bloqueo/liberación genera asiento); HU-02-04 (atomicidad); HU-01 (cuenta); consumida por 04 (órdenes), 05 (settlement), 08 (retiros). Fundaciones 00.
- **Estandares de dominio aplicables:** N/A on-chain. Convenciones monetarias (`00-fundaciones/convenciones-monetarias.md`): aritmética entera, `floor` en conversión base→quote, sin floats.

## Historia
Como sistema de balances, quiero **bloquear** fondos disponibles cuando un usuario crea una
orden o solicita un retiro, y **liberar** o **consumir** ese bloqueo cuando la orden se
cancela o ejecuta (o el retiro se aborta o se confirma), para garantizar que cada
compromiso esté respaldado por fondos reales y que `disponible + bloqueado` se conserve.

## Contexto y alcance
Esta HU define la **mecánica de transición** entre los buckets disponible y bloqueado y el
**consumo** del bloqueado en un settlement. Cubre: cuánto se bloquea por una orden según el
lado, la liberación al cancelar, la liberación del remanente cuando una compra limit
ejecuta a **mejor precio** que su límite, y el consumo al liquidar un fill. **No** define
las fórmulas de reparto del settlement ni las fees (épica 05; aquí se modela el efecto
sobre los buckets), ni las validaciones de tick/lot/min-notional ni la idempotencia de
`clientOrderId` (épicas 03/04; aquí la orden ya llega validada hasta el paso de fondos), ni
las reglas de mínimo de retiro (épica 08). El único error propio de esta HU es
`INSUFFICIENT_FUNDS`.

## Reglas de negocio e invariantes
1. **RN-1 (monto a bloquear por orden — activo y monto por variante):** el **bloqueo** lo
   instancia la épica 04 (alta de orden) y el **consumo** la épica 05 (settlement); esta HU
   fija el principio común (disponible suficiente **antes** de ejecutar) y el activo/monto de
   cada variante. Todo cómputo de notional usa `floor` y aritmética entera (sin floats).
   - **BUY limit** de `q_wei` ETH a `price_min`: se bloquea **quote (USDC)** por el notional
     al precio límite: `lock_quote = floor(q_wei × price_min / 10^18)`.
   - **SELL limit** de `q_wei` ETH: se bloquea **base (ETH)** por la cantidad:
     `lock_base = q_wei`.
   - **MARKET BUY por `quoteOrderQty`** (monto de quote a gastar): se bloquea **quote (USDC)**
     directamente, `R = quoteOrderQty` (sin derivación de notional). Ver HU-04-02 RN-5.
   - **MARKET BUY por `quantityWei`** (cantidad de base a comprar): se bloquea **quote (USDC)**
     por el **costo estimado del barrido** de los asks vigentes hasta `quantityWei`
     (snapshot), `R = Σ_niveles floor(wei_consumido_nivel × precio_nivel / 10^18)`, calculado
     por el matching (HU-04-02 RN-5).
   - **MARKET SELL por `quantityWei`**: se bloquea **base (ETH)**, `R = q_wei` (igual que SELL
     limit).
   - **MARKET SELL por `quoteOrderQty`**: se bloquea **base (ETH)** por los **wei estimados**
     necesarios para obtener `quoteOrderQty` de quote barriendo los bids vigentes (snapshot),
     calculado por el matching (HU-04-02 RN-5).
   - En todas las variantes MARKET, el sobrante reservado y no consumido (por mejor precio,
     por descarte del remanente immediate-or-cancel o por redondeo del barrido) se **libera**
     a disponible (HU-04-02 RN-8; ver RN-6 y RN-4 de esta HU).
2. **RN-2 (precondición de bloqueo, INV-2):** un bloqueo de monto `x` en activo `A` exige
   `available(acc, A) ≥ x`. Si `available(acc, A) < x` ⇒ se rechaza con
   `INSUFFICIENT_FUNDS` (HTTP 422) **antes** de modificar cualquier balance; los buckets
   quedan intactos. `details = { asset, required, available }` con montos como string.
3. **RN-3 (efecto del bloqueo, INV-3):** aplicar un bloqueo de `x` ejecuta atómicamente
   `available(acc,A) −= x; locked(acc,A) += x`. `total(acc,A)` no cambia. Genera asiento
   `ORDER_LOCK` (o `WITHDRAWAL_LOCK` para retiros) — ver HU-02-03.
4. **RN-4 (liberación por cancelación):** al cancelar una orden con remanente no ejecutado
   `r` (en el activo bloqueado), se libera ese remanente: `locked(acc,A) −= r;
   available(acc,A) += r`. `total` constante. Genera asiento `ORDER_RELEASE`. La porción ya
   ejecutada no se libera (ya fue consumida por su fill).
5. **RN-5 (consumo por fill, INV-1/INV-4):** al liquidar un fill, el bloqueado del activo
   entregado se **consume** (`locked −= consumido`) y el activo recibido se **acredita** al
   disponible de la contraparte (`available += recibido − fee`), cobrándose la fee a `EX`.
   La suma global por activo se conserva. La composición exacta es de la épica 05; aquí se
   exige que el efecto sobre buckets respete INV-1, INV-3 e INV-4.
6. **RN-6 (liberación por mejor precio):** si una **BUY limit** bloqueó quote según su
   precio límite `price_min` pero ejecuta (total o parcialmente) contra un ask resting a
   precio mejor `price_exec < price_min`, paga `floor(q_fill × price_exec / 10^18)` y se
   **libera** el excedente bloqueado por esa porción:
   `release = floor(q_fill × price_min / 10^18) − floor(q_fill × price_exec / 10^18)`,
   con `release ≥ 0`. (Una **SELL** bloquea base, que es independiente del precio de
   ejecución, por lo que no aplica este ajuste sobre la base.)
   - **Condición de emisión (release = 0):** el asiento `ORDER_RELEASE` se genera **si y solo
     si `release > 0`**. Cuando `price_exec = price_min` (ejecución exactamente al precio
     límite) ⇒ `release = 0` y **no** se crea ningún asiento adicional: el bloqueado pasa
     directamente a consumido por el `TRADE_FILL`, sin paso intermedio de liberación. Esto
     evita un posting con `amount = 0`, prohibido por HU-02-03 RN-2 (`amount > 0`).
   - **Fill parcial a mejor precio:** tras un fill parcial de `q_fill < q_original`, se libera
     `release = floor(q_fill × price_min / 10^18) − floor(q_fill × price_exec / 10^18)`
     (si `> 0`) por la **porción ejecutada**. El bloqueo de la **porción no ejecutada**
     (`q_original − q_fill`) **permanece** bloqueado al **precio original**:
     `locked_rem = floor((q_original − q_fill) × price_min / 10^18)`. Es decir, el remanente
     no se reajusta a `price_exec`. Esto preserva INV-7 (la suma de remanentes bloqueados por
     las órdenes abiertas == `locked`).
7. **RN-7 (no doble liberación / consistencia):** la suma de remanentes bloqueados por las
   órdenes/retiros abiertos de una cuenta es **exactamente** `locked(acc,A)` (INV-7). Nunca
   se libera ni se consume más de lo bloqueado; un balance bloqueado no puede quedar
   negativo (INV-2).
8. **RN-8 (atomicidad y serialización de la transición, INV-4):** cada transición
   (bloquear / liberar / consumir) es atómica: o se aplican todos sus postings o ninguno.
   Operaciones concurrentes sobre el mismo balance se serializan: dos bloqueos que en
   conjunto exceden el disponible no pueden ambos tener éxito.
9. **RN-9 (montos enteros):** todos los montos bloqueados/liberados/consumidos son enteros
   de unidad mínima; las conversiones base→quote usan `floor` con una sola división
   (`multiplicar antes de dividir`); prohibido floats.
10. **RN-10 (bloqueo por retiro):** una solicitud de retiro de `x` en activo `A` bloquea
    `x` (`WITHDRAWAL_LOCK`) si `available(acc,A) ≥ x`; si no, `INSUFFICIENT_FUNDS`. Al
    confirmarse on-chain se consume el bloqueado (`WITHDRAWAL_SETTLE`, sale del sistema); si
    el retiro se aborta antes del débito definitivo, se libera (`WITHDRAWAL_RELEASE`).

## Criterios de aceptacion (DoD)

### Escenario 1: Bloqueo por orden de compra limit [AT-02-02-01]
- Dado un trader con `USDC` disponible `2000000000` (2000 USDC) y bloqueado `0`
- Cuando crea una orden BUY limit de `q_wei = 1000000000000000000` (1 ETH) a `price_min = 2000000000` (2000.00 USDC/ETH)
- Entonces se bloquea `lock_quote = floor(1000000000000000000 × 2000000000 / 10^18) = 2000000000`
- Y `USDC` queda con disponible `"0"` y bloqueado `"2000000000"`
- Y `total` de `USDC` permanece `"2000000000"`

### Escenario 2: Bloqueo por orden de venta limit [AT-02-02-02]
- Dado un trader con `ETH` disponible `1000000000000000000` (1 ETH) y bloqueado `0`
- Cuando crea una orden SELL limit de `q_wei = 1000000000000000000` (1 ETH) a `price_min = 2100000000`
- Entonces se bloquea `lock_base = 1000000000000000000` (la cantidad en wei, independiente del precio)
- Y `ETH` queda con disponible `"0"` y bloqueado `"1000000000000000000"`
- Y `total` de `ETH` permanece `"1000000000000000000"`

### Escenario 3 (borde): Bloqueo exacto al disponible [AT-02-02-03]
- Dado un trader con `USDC` disponible `exactamente 2000000000` y bloqueado `0`
- Cuando crea una orden BUY limit cuyo `lock_quote` es `2000000000`
- Entonces el bloqueo tiene éxito (la precondición es `available ≥ x`, no `>`)
- Y `USDC` queda disponible `"0"`, bloqueado `"2000000000"`

### Escenario 4 (error): Fondos insuficientes para bloquear [AT-02-02-04]
- Dado un trader con `USDC` disponible `1999999999` y bloqueado `0`
- Cuando intenta crear una orden BUY limit cuyo `lock_quote` es `2000000000`
- Entonces la operación se rechaza con `code = INSUFFICIENT_FUNDS` y HTTP 422
- Y `details = { asset: "USDC", required: "2000000000", available: "1999999999" }`
- Y los balances quedan **intactos**: disponible `"1999999999"`, bloqueado `"0"` (INV-2: rechazo antes de aplicar)

### Escenario 5: Liberación por cancelación de orden no ejecutada [AT-02-02-05]
- Dado un trader con una orden BUY limit abierta que mantiene bloqueados `2000000000` USDC, sin fills
- Y `USDC` disponible `"500000000"`, bloqueado `"2000000000"`
- Cuando cancela la orden
- Entonces se libera el remanente: `USDC` queda disponible `"2500000000"`, bloqueado `"0"`
- Y `total` de `USDC` no cambió (`"2500000000"`)

### Escenario 6 (borde): Cancelación de orden parcialmente ejecutada [AT-02-02-06]
- Dado un trader con una orden SELL limit de `1000000000000000000` wei (1 ETH), de la cual ya se ejecutaron `400000000000000000` wei en un fill (consumidos), quedando bloqueados `600000000000000000` wei como remanente
- Cuando cancela la orden
- Entonces se libera **solo** el remanente: `ETH` bloqueado disminuye en `600000000000000000` y su disponible aumenta en `600000000000000000`
- Y la porción ya ejecutada (`400000000000000000` wei) **no** se libera (fue consumida por su fill)

### Escenario 7 (borde): Liberación de excedente por ejecución a mejor precio [AT-02-02-07]
- Dado un trader que crea una orden BUY limit de `1000000000000000000` wei (1 ETH) a `price_min = 2010000000` (2010.00), bloqueando `lock_quote = 2010000000`
- Cuando la orden ejecuta totalmente contra un ask resting a `price_exec = 2000000000` (2000.00)
- Entonces paga `floor(1000000000000000000 × 2000000000 / 10^18) = 2000000000` USDC (consumido del bloqueado)
- Y se libera el excedente `release = 2010000000 − 2000000000 = 10000000` (10 USDC) al disponible
- Y se generan **exactamente dos** asientos: **un** `TRADE_FILL` (intercambio efectivo) y **un** `ORDER_RELEASE` (`release = 10000000`), entidades de ledger **separadas** persistidas en una **única transacción** (ver HU-02-03 RN-4)
- Y tras el fill, el bloqueo asociado a esta orden es `"0"`

### Escenario 8 (consumo): Fill consume bloqueado y acredita la contraparte [AT-02-02-08]
- Dado un comprador con `2000000000` USDC bloqueados por una BUY limit de 1 ETH @ 2000.00 (la BUY es la **taker**, entró después), y un vendedor con `1000000000000000000` wei bloqueados por una SELL limit de 1 ETH @ 2000.00 (la SELL es la **maker**, resting)
- Cuando ambas órdenes matchean por 1 ETH a `price_exec = 2000000000`, con `quote_min = floor(1000000000000000000 × 2000000000 / 10^18) = 2000000000`
- Y las fees (convenciones-monetarias §3.3) son: comprador taker que recibe ETH ⇒ `fee_base = ceil(1000000000000000000 × 20 / 10000) = 2000000000000000` wei; vendedor maker que recibe USDC ⇒ `fee_quote = ceil(2000000000 × 10 / 10000) = 2000000` USDC-min
- Entonces el comprador: `locked(USDC) −= 2000000000` y `available(ETH) += (1000000000000000000 − 2000000000000000) = 998000000000000000`
- Y el vendedor: `locked(ETH) −= 1000000000000000000` y `available(USDC) += (2000000000 − 2000000) = 1998000000`
- Y las fees se acreditan a `EX`: `available(EX, ETH) += 2000000000000000` y `available(EX, USDC) += 2000000`
- Y la conservación por activo se cumple exacta: en ETH `1000000000000000000 = 998000000000000000 + 2000000000000000`; en USDC `2000000000 = 1998000000 + 2000000` (INV-1)

### Escenario 9 (concurrencia): Dos bloqueos que juntos exceden el disponible [AT-02-02-09]
- Dado un trader con `USDC` disponible `2000000000` y bloqueado `0`
- Cuando envía **dos** órdenes BUY limit en paralelo, cada una con `lock_quote = 2000000000`
- Entonces exactamente **una** se bloquea con éxito y la otra se rechaza con `INSUFFICIENT_FUNDS`
- Y nunca se llega a `USDC` disponible negativo ni a `locked > total` (INV-2/INV-3)
- Y `total` de `USDC` permanece `"2000000000"`

### Escenario 10 (error): Retiro sin fondos suficientes [AT-02-02-10]
- Dado un trader con `ETH` disponible `500000000000000000` (0.5 ETH) y bloqueado `0`
- Cuando solicita un retiro de `600000000000000000` wei (0.6 ETH)
- Entonces se rechaza con `code = INSUFFICIENT_FUNDS` (HTTP 422) y `details = { asset: "ETH", required: "600000000000000000", available: "500000000000000000" }` (los tres campos, conforme al catálogo de 00-fundaciones/modelo-de-errores.md §3.4)
- Y los balances quedan intactos (no se crea `WITHDRAWAL_LOCK`)

### Escenario 11 (retiro): Bloqueo, consumo y liberación de retiro [AT-02-02-11]
- Dado un trader con `ETH` disponible `1000000000000000000` (1 ETH)
- Cuando solicita un retiro de `400000000000000000` wei aceptado
- Entonces se bloquea: disponible `"600000000000000000"`, bloqueado `"400000000000000000"` (`WITHDRAWAL_LOCK`)
- Y si el retiro se **confirma** on-chain, el bloqueado se consume y `total(ETH)` baja en `400000000000000000` (`WITHDRAWAL_SETTLE`, sale del sistema)
- Y si en cambio el retiro se **aborta** antes del débito, el bloqueado se libera al disponible y `total(ETH)` vuelve a `"1000000000000000000"` (`WITHDRAWAL_RELEASE`)

### Escenario 12 (borde): Ejecución exactamente al precio límite ⇒ sin ORDER_RELEASE [AT-02-02-12]
- Dado un trader que crea una orden BUY limit de `1000000000000000000` wei (1 ETH) a `price_min = 2000000000` (2000.00), bloqueando `lock_quote = 2000000000`
- Cuando la orden ejecuta totalmente contra un ask resting a `price_exec = price_min = 2000000000`
- Entonces `release = floor(10^18 × 2000000000 / 10^18) − floor(10^18 × 2000000000 / 10^18) = 0`
- Y **no** se genera ningún asiento `ORDER_RELEASE` (RN-6: solo si `release > 0`); el bloqueado pasa directamente a consumido por el `TRADE_FILL`
- Y el ledger sigue balanceado por activo y se cumple INV-1 (no hay posting con `amount = 0`)

### Escenario 13 (borde): Fill parcial a mejor precio, remanente al precio original [AT-02-02-13]
- Dado un trader que crea una orden BUY limit de `q_original = 2000000000000000000` wei (2 ETH) a `price_min = 2010000000` (2010.00), bloqueando `lock_quote = floor(2000000000000000000 × 2010000000 / 10^18) = 4020000000`
- Cuando ejecuta **parcialmente** `q_fill = 1000000000000000000` wei (1 ETH) contra un ask resting a `price_exec = 2000000000` (2000.00)
- Entonces paga `floor(10^18 × 2000000000 / 10^18) = 2000000000` USDC (consumido del bloqueado)
- Y se libera `release = floor(10^18 × 2010000000 / 10^18) − floor(10^18 × 2000000000 / 10^18) = 2010000000 − 2000000000 = 10000000` (10 USDC) al disponible (asiento `ORDER_RELEASE`, `release > 0`)
- Y el bloqueo de la **porción no ejecutada** (1 ETH) permanece al **precio original**: `locked_rem = floor(1000000000000000000 × 2010000000 / 10^18) = 2010000000`
- Y se verifica que `locked(USDC)` tras el fill es `4020000000 − 2000000000 − 10000000 = 2010000000 == locked_rem` (INV-7)
- [ ] Todos los escenarios de aceptacion (AT-*) pasan
- [ ] Reglas de negocio RN-1..RN-10 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md)
- [ ] (si aplica) Adherencia verificada al estandar on-chain citado — N/A
