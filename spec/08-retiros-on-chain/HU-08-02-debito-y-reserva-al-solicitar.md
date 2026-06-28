# HU-08-02 — Débito y reserva al solicitar

- **Epica:** 08 — Retiros On-Chain
- **Actor / rol:** Sistema (servicio de retiros) sobre la cuenta del trader; contabilidad vía épica 02
- **Prioridad:** Alta
- **Dependencias:** HU-08-01 (solicitud validada), HU-02-02 (reserva/liberación de fondos), HU-02-03 (ledger de doble entrada); HU-08-04 (consumo/liberación al confirmar/fallar)
- **Estandares de dominio aplicables:** convenciones monetarias de `00-fundaciones` (enteros de unidad mínima, sin floats); invariantes INV-1/INV-2/INV-3/INV-4

## Historia
Como Sistema de retiros, quiero **bloquear de forma atómica** el balance interno del usuario (el principal a retirar más la previsión de fee de red en ETH) en el momento en que se acepta la solicitud, para garantizar que esos fondos no puedan usarse para otra operación y que el retiro esté **respaldado** desde su creación, sin posibilidad de doble gasto.

## Contexto y alcance
Esta HU define la **mecánica contable** del bloqueo al aceptar un retiro (validado por HU-08-01): qué buckets cambian, en qué activos y de forma **atómica**. Produce el asiento `WITHDRAWAL_LOCK` (épica 02). El principal del retiro y la previsión de gas (en ETH) pasan de **disponible** a **bloqueado**; ningún total por activo cambia todavía (INV-1: un retiro pendiente no saca fondos del sistema).

NO cubre la validación de la solicitud (HU-08-01), ni la firma/broadcast (HU-08-03), ni el consumo definitivo del bloqueado al confirmar ni su liberación al fallar (HU-08-04). El consumo on-chain (que reduce el total y satisface INV-1) ocurre recién en HU-08-04 al alcanzar `CONFIRMED`.

Supuesto clave: la previsión de fee de red **siempre se reserva en ETH** (el gas se paga en ETH), tanto para retiros de ETH como de USDC.

## Reglas de negocio e invariantes
1. **RN-1 (composición de la reserva por activo):**
   - **Retiro de ETH:** se bloquea en ETH `reserva_eth = amount_wei + fee_red_wei` (un solo activo). `fee_red_wei = GAS_LIMIT_ETH × gas_price_wei = 21000 × gas_price_wei`.
   - **Retiro de USDC:** se bloquea en USDC `amount_usdc` **y**, simultáneamente, en ETH `fee_red_wei = GAS_LIMIT_ERC20 × gas_price_wei = 100000 × gas_price_wei` (reserva **dual**). El detalle de la reserva dual se especifica en HU-08-05.
2. **RN-2 (transición de buckets — bloquear):** por cada activo afectado se aplica `disponible(acc, A) −= x; bloqueado(acc, A) += x`. El **total por activo permanece constante** (`total = disponible + bloqueado`, INV-3). No se modifica `EXTERNAL` ni `EX` (no es un evento on-chain todavía; INV-1 intacto).
3. **RN-3 (atomicidad — todo o nada):** el bloqueo es una operación **atómica** (INV-4). Para un retiro de USDC, el bloqueo del USDC y el de la previsión de gas en ETH se aplican **juntos**: si cualquiera de los dos no puede aplicarse (p. ej. ETH disponible insuficiente al momento del débito), **no se aplica ninguno** y la solicitud se rechaza con `INSUFFICIENT_FUNDS`. No existe estado observable con solo una de las dos patas bloqueada.
4. **RN-4 (verificación de no-negatividad previa):** antes de bloquear se verifica `disponible(acc, A) ≥ x` para cada activo (INV-2). Si no alcanza, se rechaza **antes** de aplicar (`INSUFFICIENT_FUNDS`), dejando los balances **idénticos**. Nunca se deja un disponible negativo para "corregirlo" después.
5. **RN-5 (asiento de ledger):** el bloqueo genera el/los posting(s) `WITHDRAWAL_LOCK` (catálogo de la épica 02), referenciando el `withdrawalId`. Para un retiro de USDC se generan los movimientos correspondientes en **ambos** activos dentro de la **misma** transacción contable (atómica).
6. **RN-6 (conservación):** el bloqueo **no** altera `Σ_acc total(acc, A) + total(EX, A)` para ningún activo (INV-1): solo redistribuye disponible↔bloqueado de la misma cuenta. La reducción de la suma total ocurre únicamente al `CONFIRMED` (HU-08-04).
7. **RN-7 (estado resultante y snapshot de gas):** tras el bloqueo exitoso, el retiro queda en estado `PENDING` con la reserva registrada (`reserva_eth`/`reserva_usdc` y `fee_red_wei`, `gas_limit`, `gas_price_wei`). El `gas_price_wei` se **snapshotea** en este momento desde `GAS_PRICE_WEI` de configuración (`GAS_PRICE_SOURCE = configured_fixed`; ver HU-08-01 RN-8) y es el **mismo** valor que usarán la firma/broadcast (HU-08-03 RN-5) y la reconciliación (HU-08-04): no se vuelve a estimar. Todo persistente (INV-8).
8. **RN-8 (idempotencia con HU-08-01):** el bloqueo se aplica **una sola vez** por retiro. Un reenvío idempotente de la solicitud (misma clave + mismos parámetros, RN-10 de HU-08-01) **no** vuelve a bloquear: devuelve el retiro existente sin segundo `WITHDRAWAL_LOCK`.
9. **RN-9 (concurrencia):** dos solicitudes concurrentes de la misma cuenta que compiten por el mismo disponible se serializan de modo que **a lo sumo** se bloquea hasta el disponible real; la que no alcance se rechaza con `INSUFFICIENT_FUNDS`. Nunca se bloquea más que el disponible (INV-2). La suma de bloqueos comprometidos por retiros en proceso nunca excede el `bloqueado` real del activo (consistente con INV-7/INV-2 para retiros).
10. **RN-10 (sin floats; precisión):** `amount_wei`, `amount_usdc`, `fee_red_wei`, `reserva_eth` se manejan como **enteros de unidad mínima**; `reserva_eth = amount_wei + fee_red_wei` es una **suma entera exacta**; `fee_red_wei` es un **producto entero exacto**. Serialización como string `^(0|[1-9][0-9]*)$`. Prohibido floats.

## Criterios de aceptación (DoD)

### Escenario 1: bloqueo de retiro de ETH (feliz) [AT-08-02-01]
- Dado `acc-1` con `disponible(ETH) = "5000000000000000000"` (5 ETH), `bloqueado(ETH) = "0"`, y `fee_red_wei = "420000000000000"` (21000 × 20 gwei)
- Cuando se acepta un retiro de `amount = "1000000000000000000"` (1 ETH)
- Entonces `reserva_eth = "1000420000000000000"` (1 ETH + previsión de gas), y se aplica `disponible(ETH) −= reserva_eth; bloqueado(ETH) += reserva_eth`
- Y resulta `disponible(ETH) = "3999580000000000000"`, `bloqueado(ETH) = "1000420000000000000"`, `total(ETH) = "5000000000000000000"` (constante, RN-2/RN-6)
- Y se registra un asiento `WITHDRAWAL_LOCK` por `reserva_eth` referenciando el `withdrawalId` (RN-5)

### Escenario 2: bloqueo dual de retiro de USDC (feliz) [AT-08-02-02]
- Dado `acc-1` con `disponible(USDC) = "50000000"` (50 USDC), `disponible(ETH) = "1000000000000000"` (0.001 ETH), y `fee_red_wei = "500000000000000"` (100000 × 5 gwei)
- Cuando se acepta un retiro de `asset = USDC`, `amount = "25000000"` (25 USDC)
- Entonces se bloquean **ambos** activos en la misma transacción: `disponible(USDC) −= "25000000"` y `disponible(ETH) −= "500000000000000"`
- Y resulta `bloqueado(USDC) = "25000000"`, `disponible(USDC) = "25000000"`, `bloqueado(ETH) = "500000000000000"`, `disponible(ETH) = "500000000000000"`
- Y `total(USDC)` y `total(ETH)` permanecen constantes (RN-2/RN-6)

### Escenario 3 (borde): bloqueo que consume exactamente todo el disponible [AT-08-02-03]
- Dado `acc-1` con `disponible(ETH) = "1000420000000000000"` y `fee_red_wei = "420000000000000"`
- Cuando se acepta un retiro de `amount = "1000000000000000000"` (1 ETH)
- Entonces `reserva_eth = "1000420000000000000"` = disponible exacto; tras el bloqueo `disponible(ETH) = "0"`, `bloqueado(ETH) = "1000420000000000000"`
- Y no hay error (la comparación es `disponible ≥ reserva`, RN-4)

### Escenario 4 (atomicidad/error): retiro de USDC con ETH insuficiente para gas no bloquea nada [AT-08-02-04]
- Dado `acc-1` con `disponible(USDC) = "50000000"` (50 USDC) y `disponible(ETH) = "100000000000000"` (0.0001 ETH), `fee_red_wei = "500000000000000"`
- Cuando se intenta aceptar un retiro de `amount = "25000000"` (25 USDC)
- Entonces como `disponible(ETH) < fee_red_wei`, **no se aplica ninguna** de las dos patas (RN-3): el USDC NO se bloquea y el ETH tampoco
- Y se rechaza con `INSUFFICIENT_FUNDS` (`asset: "ETH"`), y los balances quedan **idénticos** al estado previo (RN-4)

### Escenario 5 (error): ETH insuficiente para principal + gas no bloquea nada [AT-08-02-05]
- Dado `acc-1` con `disponible(ETH) = "1000000000000000000"` (1 ETH) y `fee_red_wei = "420000000000000"`
- Cuando se intenta retirar `amount = "1000000000000000000"` (1 ETH)
- Entonces `reserva_eth = "1000420000000000000" > disponible(ETH)`; no se bloquea nada y se rechaza con `INSUFFICIENT_FUNDS` (`asset: "ETH"`, `required = "1000420000000000000"`, `available = "1000000000000000000"`)
- Y `disponible(ETH)` y `bloqueado(ETH)` quedan intactos (RN-4)

### Escenario 6 (conservación): el bloqueo no cambia la suma total por activo [AT-08-02-06]
- Dado `acc-1` con `disponible(ETH) = "5000000000000000000"` (5 ETH), `bloqueado(ETH) = "0"`, `total(ETH) = "5000000000000000000"`; y sea `S_ETH = Σ_acc total(acc, ETH) + total(EX, ETH)` la suma total de ETH antes de la operación (mismo setup que AT-08-02-01)
- Cuando se acepta un retiro de `amount_wei = "1000000000000000000"` con `fee_red_wei = "420000000000000"` (`reserva_eth = "1000420000000000000"`)
- Entonces para `acc-1`: `disponible(ETH) = "3999580000000000000"`, `bloqueado(ETH) = "1000420000000000000"`, `total(ETH) = "5000000000000000000"` (sin cambio, RN-2)
- Y la suma total `S_ETH` después es **idéntica** a la de antes (INV-1, RN-6): solo se movió disponible→bloqueado dentro de `acc-1`; ninguna otra cuenta ni `EX` cambia
- Y análogamente para `USDC` con el setup de AT-08-02-02: `S_USDC` no cambia
- Verificación (black-box): sumar `disponible + bloqueado` de todas las cuentas (+ `EX`) por activo antes y después → misma suma; la reconciliación con el ledger reproduce los balances exactos (INV-8)

### Escenario 7 (idempotencia): reenvío idempotente no vuelve a bloquear [AT-08-02-07]
- Dado un retiro ya aceptado con `clientWithdrawalId = "w-123"` que bloqueó `reserva_eth`
- Cuando se reenvía la solicitud idempotente (misma clave + mismos parámetros)
- Entonces NO se aplica un segundo `WITHDRAWAL_LOCK` ni se reduce de nuevo el disponible (RN-8): los balances no cambian respecto del primer bloqueo

### Escenario 8 (concurrencia): dos retiros que compiten por el mismo disponible [AT-08-02-08]
- Dado `acc-1` con `disponible(ETH) = "1000420000000000000"` (alcanza para exactamente un retiro de 1 ETH + gas)
- Cuando se solicitan **concurrentemente** dos retiros de `amount = "1000000000000000000"` (1 ETH) cada uno
- Entonces **a lo sumo uno** se acepta y bloquea; el otro se rechaza con `INSUFFICIENT_FUNDS` (RN-9)
- Y nunca se bloquea más que el disponible: no hay `bloqueado(ETH) > total(ETH)` ni `disponible(ETH) < 0` (INV-2/INV-3)

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-08-02-01..08) pasan
- [ ] Reglas de negocio RN-1..RN-10 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md (`INSUFFICIENT_FUNDS` con `asset/required/available`)
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md (reserva = suma/producto entero exacto; sin floats; string de unidad mínima)
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md): INV-1 (suma total constante en el bloqueo), INV-2 (no-negatividad, rechazo previo), INV-3 (partición), INV-4 (atomicidad del bloqueo, incl. reserva dual), INV-8 (persistencia)
- [ ] Adherencia verificada: la previsión de gas se reserva en ETH para ambos activos (modelo de fee de red de la épica)
