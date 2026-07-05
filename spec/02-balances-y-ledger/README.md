# Épica 02 — Balances y Ledger

Contabilidad interna de fondos por usuario y activo. Esta épica define **cómo el exchange
lleva la cuenta del dinero** que custodia: cuánto tiene disponible cada usuario, cuánto
tiene reservado por órdenes o retiros, y el **libro de movimientos** (ledger de doble
entrada) que respalda y permite reconstruir cada balance.

> Ante cualquier conflicto entre esta épica y `00-fundaciones`, **prevalece
> `00-fundaciones`**. Leer primero: `glosario.md`, `convenciones-monetarias.md`,
> `invariantes-globales.md`, `modelo-de-errores.md`.

---

## 1. Objetivo de la épica

Proveer un modelo de **balances** y un **ledger** internos que:

1. Distingan, por cuenta y activo, el saldo **disponible** (usable para operar/retirar) del
   saldo **bloqueado** (reservado por órdenes abiertas o retiros en proceso).
2. Registren **todo** cambio de balance como un **asiento de doble entrada**, inmutable y
   trazable, de modo que cualquier balance pueda **reconstruirse** sumando sus asientos.
3. Garanticen las invariantes financieras globales: **conservación de fondos** (no se crea
   ni se destruye valor), **no-negatividad**, partición `total = disponible + bloqueado` y
   **atomicidad** de cada operación.

Es la base contable que consumen el matching (03), la gestión de órdenes (04), el
settlement y fees (05), los depósitos (07) y los retiros (08).

---

## 2. Alcance

### Dentro de alcance

- Modelo de balances por **cuenta** y **activo** (`ETH`, `USDC`), con buckets
  **disponible** y **bloqueado**, más la **cuenta de fees del exchange** (`EX`).
- Consulta de balances (disponible / bloqueado / total) por activo.
- **Reserva (bloqueo)** y **liberación** de fondos disponibles asociadas al ciclo de vida
  de órdenes y retiros, y **consumo** del bloqueado al liquidar un fill.
- **Ledger de doble entrada**: estructura del asiento (tipo, montos, referencia,
  timestamp, postings balanceados), inmutabilidad y reconstrucción de balances.
- **Atomicidad y consistencia** de las operaciones de balance ante fallos y concurrencia.
- **Historial de movimientos** consultable por el usuario, filtrable por activo / tipo /
  período, con paginación.

### Fuera de alcance (se especifica en otras épicas)

- **Reglas de validación de alta de orden** (tick/lot/min-notional, enums, idempotencia de
  `clientOrderId`): épicas 03/04. Esta épica asume la orden ya validada y solo modela el
  **bloqueo de fondos**.
- **Composición exacta del settlement de un fill** (qué postings y fees por maker/taker y
  fill parcial): épica 05. Esta épica define el **tipo de asiento** `TRADE_FILL` y su forma
  contable (atómica, conservativa), pero no las fórmulas de reparto.
- **Detección y confirmación on-chain de depósitos** (12 confirmaciones, reorgs,
  idempotencia por `(txHash, logIndex)`): épica 07. Aquí solo se modela el asiento
  `DEPOSIT` que **acredita** un depósito ya confirmado.
- **Firma/broadcast/nonce/gas de retiros** (EIP-155): épica 08. Aquí solo se modelan los
  asientos `WITHDRAWAL_LOCK` / `WITHDRAWAL_SETTLE` / `WITHDRAWAL_RELEASE`.
- Contrato concreto de endpoints/paginación HTTP/WS: épica 09 (esta épica fija el
  **contenido** y las **unidades**, no los nombres finales de ruta/campo).

---

## 3. Historias de Usuario de la épica

| ID | Título | Resumen (una línea) |
|----|--------|---------------------|
| `HU-02-01` | Consultar balances | El usuario consulta su balance por activo, discriminando disponible y bloqueado. |
| `HU-02-02` | Reserva y liberación de fondos | El sistema bloquea fondos disponibles (al crear orden/retiro) y los libera (al cancelar/ejecutar), conservando `disponible + bloqueado`. |
| `HU-02-03` | Libro contable de movimientos | Cada cambio de balance genera un asiento de doble entrada trazable (tipo, monto, referencia, timestamp). |
| `HU-02-04` | Atomicidad y consistencia | Las operaciones de balance son atómicas y consistentes ante fallos/concurrencia; no se crean ni destruyen fondos. |
| `HU-02-05` | Historial de movimientos | El usuario consulta el historial de movimientos de su balance, filtrable por activo/tipo/período. |

---

## 4. Dependencias

- **Épica 01 (cuentas y autenticación):** existe una `accountId` autenticada; toda consulta
  y toda operación de balance se asocia a una cuenta. La autorización (acceso solo a los
  balances propios) usa los mecanismos de la épica 01.
- **Fundaciones (00):** glosario, convenciones monetarias (enteros de unidad mínima,
  redondeo, serialización como string), modelo de errores e invariantes globales.

Épicas que **dependen de** esta (consumidoras): 03 (matching), 04 (órdenes), 05
(settlement/fees), 07 (depósitos), 08 (retiros), 09 (API), 10/11 (clientes).

---

## 5. Modelo conceptual (común a las HUs)

### 5.1 Cuentas contables y buckets

- Para cada cuenta de usuario `acc` y activo `A ∈ {ETH, USDC}` existen dos **buckets**:
  - `available(acc, A)` — disponible.
  - `locked(acc, A)` — bloqueado.
  - `total(acc, A) = available(acc, A) + locked(acc, A)`.
- La **cuenta de fees del exchange** `EX` acumula las fees cobradas (bucket disponible por
  activo). Forma parte de la conservación (INV-1).
- Cuenta contable **externa** `EXTERNAL(A)`: contrapartida de doble entrada que representa
  el mundo on-chain. Los depósitos **acreditan** al usuario y **debitan** `EXTERNAL`; los
  retiros liquidados hacen lo inverso. Así, la suma de **todos** los postings de un asiento
  es 0 por activo (doble entrada pura) y, a la vez, se cumple INV-1:
  `Σ_acc total(acc,A) + total(EX,A) = depósitos_confirmados(A) − retiros_confirmados(A) = −total(EXTERNAL,A)`.
- **Cuentas técnicas (`EX` y `EXTERNAL(A)`):** son cuentas de contabilidad interna con un
  **único bucket implícito**; **no** aplica la partición `available`/`locked` de las cuentas
  de usuario. Por convención, los postings contra `EX` y `EXTERNAL(A)` usan `bucket =
  AVAILABLE`. Las invariantes **INV-2** (no-negatividad de ambos buckets) e **INV-3**
  (`total = available + locked`) se exigen **solo sobre las cuentas de usuario**. `EX`
  participa de INV-1 (entra en la suma `Σ`); `EXTERNAL(A)` **no** entra en esa suma: es la
  contrapartida que cierra la doble entrada y cuyo saldo (negativo) iguala `depósitos −
  retiros`.
- **Gas de retiros ETH:** el gas de cada transacción de retiro lo paga el exchange desde su
  **reserva operativa**, externa al modelo de balances de usuario (no custodiada aquí). Por
  lo tanto, `WITHDRAWAL_SETTLE` consume del `locked` del usuario **exactamente** el monto del
  retiro solicitado, y `EXTERNAL(ETH)` aumenta exactamente ese mismo monto. El gas **no**
  altera INV-1, **no** aparece en el ledger de usuario ni se carga a `EX`. (Coordinado con la
  épica 08.)

### 5.2 Tipos de movimiento (enum estable del ledger)

Catálogo cerrado de tipos de asiento usado por HU-02-03 y filtrable en HU-02-05:

| Tipo | Disparador | Efecto en buckets |
|------|------------|-------------------|
| `DEPOSIT` | Acreditación de un depósito confirmado (épica 07). | `available(acc,A) +=`; `EXTERNAL(A) −=`. |
| `ORDER_LOCK` | Alta de orden que requiere reservar fondos (épica 04). | `available(acc,A) −=`; `locked(acc,A) +=`. |
| `ORDER_RELEASE` | Cancelación de orden, o remanente liberado tras fill por mejor precio. | `locked(acc,A) −=`; `available(acc,A) +=`. |
| `TRADE_FILL` | Settlement atómico de un fill (épica 05): redistribuye base/quote y cobra fee. | Seis efectos en **dos cuentas** y **dos activos**: **Comprador:** `locked(buyer,USDC) −= quote_paid`; `available(buyer,ETH) += q_fill − fee_base`. **Vendedor:** `locked(seller,ETH) −= q_fill`; `available(seller,USDC) += quote_paid − fee_quote`. **Exchange:** `available(EX,ETH) += fee_base`; `available(EX,USDC) += fee_quote`. |
| `WITHDRAWAL_LOCK` | Solicitud de retiro aceptada (épica 08). | `available(acc,A) −=`; `locked(acc,A) +=`. |
| `WITHDRAWAL_SETTLE` | Retiro confirmado on-chain (épica 08). | `locked(acc,A) −=`; `EXTERNAL(A) +=`. |
| `WITHDRAWAL_RELEASE` | Retiro abortado/fallido antes del débito definitivo. | `locked(acc,A) −=`; `available(acc,A) +=`. |
| `REVERSAL` | Corrección/reversión de un asiento previo (HU-02-03 RN-4/RN-5). | Postings exactamente **inversos** a los del asiento revertido (`reference = { reversedEntryId }`); el original queda intacto. |

> Las **fees** se registran como postings hacia `EX` **dentro** del asiento `TRADE_FILL`
> (sub-clasificación `kind = FEE`), nunca como un asiento separado, para preservar la
> atomicidad (INV-4). La composición detallada la fija la épica 05.

> **Liberación de excedente por mejor precio (surplus).** Cuando una `BUY` limit ejecuta a
> mejor precio que su límite, el excedente bloqueado se libera como un asiento
> `ORDER_RELEASE` **independiente** del `TRADE_FILL` (cada `TRADE_FILL` refleja solo el
> intercambio efectivo; cada `ORDER_RELEASE` solo la liberación). Ambos asientos forman una
> **unidad lógica atómica** y se persisten en una **única transacción de base de datos**: o
> aparecen ambos completos o ninguno (INV-4 aplicado a múltiples asientos de un mismo
> settlement). El `ORDER_RELEASE` de surplus se genera **solo si** `release > 0` (ver
> HU-02-02 RN-6).

> **Identificador del fill.** La `reference` de un `TRADE_FILL` (y del `ORDER_RELEASE` de
> surplus asociado) es el `tradeId`: la identidad estable del fill que **genera la épica 05**
> (`HU-05-03`). `fill`, `trade` y `execution` son sinónimos en esta especificación; el
> identificador canónico es `tradeId`.

### 5.3 Reglas de transición (consecuencia de INV-2 / INV-3)

- **Bloquear:** requiere `available ≥ x`; si no, se rechaza con `INSUFFICIENT_FUNDS`
  **antes** de aplicar (nunca se deja un balance negativo y luego se corrige).
- **Liberar:** `locked −= x; available += x`. `total` constante.
- **Consumir (settlement):** `locked −= x` en el activo entregado; `available += y` en el
  **otro** activo recibido (menos fee). La suma global por activo se conserva (INV-1).

---

## 6. Invariantes y reglas clave de la épica

- **INV-1 (conservación):** ninguna operación interna (bloqueo, liberación, settlement,
  fee) altera `Σ_acc total(acc,A) + total(EX,A)`. Solo `DEPOSIT` y `WITHDRAWAL_SETTLE` la
  modifican (eventos on-chain).
- **INV-2 (no-negatividad):** `available ≥ 0` y `locked ≥ 0` siempre; rechazo previo, no
  corrección posterior.
- **INV-3 (partición):** `total = available + locked` por cuenta y activo en todo snapshot.
- **INV-4 (atomicidad):** todo asiento (en particular `TRADE_FILL`) se aplica completo o no
  se aplica; no hay estado parcial observable.
- **INV-8 (persistencia):** balances y ledger sobreviven a reinicios; los balances se
  **reconstruyen** exactamente sumando los postings del ledger.
- **Dinero:** todos los montos son **enteros de unidad mínima** (wei para ETH; unidad de 6
  decimales para USDC). Prohibido floats binarios. En la API se serializan como **string**
  de entero decimal con patrón `^(0|[1-9][0-9]*)$`. Ver `convenciones-monetarias.md`.
- **Errores:** se usan exclusivamente los `code` del catálogo de
  `00-fundaciones/modelo-de-errores.md` (en esta épica, principalmente
  `INSUFFICIENT_FUNDS`, `UNAUTHENTICATED`, `UNAUTHORIZED`, `VALIDATION_ERROR`).
