# HU-02-03 — Libro contable de movimientos (ledger de doble entrada)

- **Epica:** 02 — Balances y Ledger
- **Actor / rol:** Sistema (motor contable); Operador/auditor como consumidor de auditoría.
- **Prioridad:** Alta
- **Dependencias:** HU-02-02 (las transiciones que generan asientos); HU-02-04 (atomicidad de la escritura); HU-01 (cuentas). Referencia de origen de depósitos/retiros: épicas 07/08. Fundaciones 00.
- **Estandares de dominio aplicables:** N/A on-chain en cuanto a firma/derivación. La **referencia** de un asiento `DEPOSIT` usa la identidad on-chain del depósito `(txHash, logIndex)` definida en `00-fundaciones/invariantes-globales.md` (INV-5) y detallada en la épica 07. Convenciones monetarias (enteros, sin floats).

## Historia
Como sistema contable, quiero registrar **cada** cambio de balance como un asiento de
**doble entrada** inmutable y trazable (con tipo, montos, referencia y timestamp), para
poder **reconstruir** cualquier balance sumando sus asientos y auditar el origen de cada
movimiento de fondos.

## Contexto y alcance
Esta HU define la **estructura del ledger** y la garantía de que todo cambio de balance
deja rastro contable. El ledger es **append-only** (inmutable: no se actualiza ni borra un
asiento; las reversiones se registran como nuevos asientos). Cada asiento agrupa uno o más
**postings** balanceados (doble entrada). No cubre la **presentación** del historial al
usuario (HU-02-05), ni la composición numérica del settlement/fees (épica 05): aquí se fija
el **modelo** y el **enum de tipos**, no las fórmulas de reparto. Todos los montos de
postings son enteros de unidad mínima.

## Reglas de negocio e invariantes
1. **RN-1 (toda mutación deja asiento):** ningún balance (`available` o `locked`, de
   cualquier cuenta, incluida `EX`) cambia sin un asiento que lo respalde. No existen
   mutaciones "silenciosas".
2. **RN-2 (estructura del asiento):** un asiento contiene, como mínimo:
   - `entryId`: identificador con **orden total global** del asiento. Cualquier par de
     asientos del sistema tiene un orden definido y **reproducible** por `entryId`. Su valor
     es **estrictamente creciente** en el tiempo de aplicación a nivel **global** (no por
     cuenta ni por partición). Implementaciones válidas: entero sin signo autoincremental de
     base de datos, o secuencia monotónica del sistema (p. ej. epoch-ms concatenado con un
     número de secuencia). **No** son válidos los identificadores sin orden monotónico
     (p. ej. UUID v4 aleatorio). En la API se **serializa como string** (para no perder
     precisión por encima de 2⁵³). No se reutiliza (RN-5).
   - `type`: uno del enum cerrado `{ DEPOSIT, ORDER_LOCK, ORDER_RELEASE, TRADE_FILL,
     WITHDRAWAL_LOCK, WITHDRAWAL_SETTLE, WITHDRAWAL_RELEASE, REVERSAL }`.
   - `timestamp`: instante de aplicación en UTC, formato ISO-8601 con milisegundos.
   - `reference`: referencia al origen (`orderId`, `withdrawalId`, `tradeId`,
     `{ txHash, logIndex }` para `DEPOSIT`, o `{ reversedEntryId }` para `REVERSAL`), que
     permite trazar el asiento a su causa. Para
     `TRADE_FILL` (y el `ORDER_RELEASE` de surplus asociado), la referencia es el `tradeId`:
     la identidad estable del fill **definida y generada por la épica 05** (`HU-05-03`).
     `fill`, `trade` y `execution` son sinónimos; el identificador canónico es `tradeId`.
   - `postings[]`: lista de líneas, cada una
     `{ account, asset, bucket, direction, amount, kind }` con `bucket ∈ {AVAILABLE, LOCKED}`,
     `direction ∈ {DEBIT, CREDIT}`, `kind ∈ {PRINCIPAL, FEE}` (por defecto `PRINCIPAL`), y
     `amount` string entero **estrictamente positivo** que matchea `^[1-9][0-9]*$` (esto es,
     `amount > 0`: un posting con `amount = "0"` es **inválido** y no debe persistirse — sería
     señal de un bug del motor contable; el patrón `^(0|[1-9][0-9]*)$` aplica a montos de
     **balance**, que sí pueden ser cero, no a montos de posting). Dentro de un `TRADE_FILL`,
     los postings hacia `EX` tienen `kind = FEE`; el resto, `kind = PRINCIPAL`. Para las
     cuentas técnicas `EX` y `EXTERNAL(A)` se usa `bucket = AVAILABLE` por convención (ver
     README §5.1).
3. **RN-3 (doble entrada balanceada, INV-1):** para **cada asiento** y **cada activo**, la
   suma de los `CREDIT` es igual a la suma de los `DEBIT`. Convención de signo: un `CREDIT`
   **aumenta** el bucket de la cuenta destino; un `DEBIT` lo **disminuye**. La contrapartida
   externa de depósitos/retiros usa la cuenta `EXTERNAL(A)`.
4. **RN-4 (efecto por tipo):** cada `type` produce los postings de la tabla del README §5.2:
   - `DEPOSIT`: `CREDIT available(acc,A)` / `DEBIT EXTERNAL(A)`.
   - `ORDER_LOCK` / `WITHDRAWAL_LOCK`: `DEBIT available(acc,A)` / `CREDIT locked(acc,A)`.
   - `ORDER_RELEASE` / `WITHDRAWAL_RELEASE`: `DEBIT locked(acc,A)` / `CREDIT available(acc,A)`.
   - `WITHDRAWAL_SETTLE`: `DEBIT locked(acc,A)` / `CREDIT EXTERNAL(A)`.
   - `TRADE_FILL`: conjunto atómico de postings que consume `locked`, acredita `available`
     a la contraparte y mueve fees a `EX` (composición exacta en épica 05). Los postings de
     fee se sub-clasifican `kind = FEE`.
   - `REVERSAL`: postings exactamente **inversos** a los del asiento que revierte (mismas
     líneas `{ account, asset, bucket, amount, kind }`, cada una con `direction` opuesta:
     `DEBIT` ↔ `CREDIT`), con `reference = { reversedEntryId }` apuntando al `entryId` del
     asiento original. Es el único mecanismo de corrección (RN-5): el asiento original queda
     intacto.
   - **Liberación del excedente por mejor precio (surplus):** cuando una `BUY` limit ejecuta
     a mejor precio que su límite, la liberación del excedente se registra como un asiento
     `ORDER_RELEASE` **independiente** del `TRADE_FILL` (cada `TRADE_FILL` refleja únicamente
     el intercambio efectivo; cada `ORDER_RELEASE` únicamente la liberación). Son **dos
     entidades de ledger separadas** que forman una **unidad lógica atómica**: se persisten en
     una **única transacción de base de datos** y se garantiza que aparecen **ambos completos
     o ninguno** (INV-4 aplicado a múltiples asientos de un mismo settlement). El
     `ORDER_RELEASE` de surplus se emite **solo si `release > 0`** (HU-02-02 RN-6).
5. **RN-5 (inmutabilidad / append-only):** un asiento, una vez escrito, **no se modifica ni
   se elimina**. Cualquier corrección o reversión se hace con un **nuevo** asiento de
   compensación. El `entryId` no se reutiliza.
6. **RN-6 (reconstrucción de balances, INV-8):** para toda cuenta/activo/bucket, el balance
   actual es la suma de `CREDIT` menos `DEBIT` de sus postings:
   `bucket(acc,A) = Σ credits(acc,A,bucket) − Σ debits(acc,A,bucket)`. Reprocesar el ledger
   completo reproduce **exactamente** los balances de HU-02-01.
7. **RN-7 (atomicidad de escritura, INV-4):** un asiento se escribe **completo o nada**: o
   se persisten todos sus postings o ninguno. Nunca queda un asiento con postings faltantes
   ni desbalanceado (violaría RN-3).
8. **RN-8 (idempotencia por referencia en orígenes idempotentes, INV-5):** un asiento
   `DEPOSIT` con identidad `(txHash, logIndex)` se escribe **a lo sumo una vez**. Reprocesar
   la misma identidad **no** crea un segundo asiento ni vuelve a acreditar; se trata como
   `DEPOSIT_ALREADY_CREDITED` (la lógica de acreditación está en la épica 07).
9. **RN-9 (orden total y timestamp):** los asientos tienen un orden total reproducible por
   `entryId`, que **crece monótonamente en el tiempo de aplicación a nivel global** (no solo
   por cuenta ni por partición); el `timestamp` es no decreciente respecto del orden de
   aplicación. Dos asientos no comparten `entryId`. Este orden global es el que usa HU-02-05
   RN-6 (`entryId` desc ante empate de `timestamp`) y debe ser estable entre páginas.
10. **RN-10 (montos y serialización):** todo `amount` de posting es entero de unidad mínima
    **estrictamente positivo**, serializado como string `^[1-9][0-9]*$` (igual que RN-2; el
    patrón `^(0|[1-9][0-9]*)$` aplica a montos de balance, no de posting). Prohibido floats;
    conversiones base→quote con `floor` (una sola división).

## Criterios de aceptacion (DoD)

### Escenario 1: Asiento de depósito acreditado [AT-02-03-01]
- Dado un depósito confirmado de `1000000000` USDC (1000 USDC) para la cuenta `A`, con identidad `(txHash="0xabc...", logIndex=3)`
- Cuando se acredita
- Entonces se genera un asiento `type = DEPOSIT`, `reference = { txHash: "0xabc...", logIndex: 3 }`, con `timestamp` ISO-8601
- Y sus postings son `CREDIT available(A, USDC) 1000000000` y `DEBIT EXTERNAL(USDC) 1000000000`
- Y por el activo `USDC` la suma de CREDIT es igual a la suma de DEBIT (asiento balanceado)

### Escenario 2: Asiento de bloqueo por orden [AT-02-03-02]
- Dado un trader `A` con `USDC` disponible `2000000000`
- Cuando crea una orden BUY que bloquea `2000000000` USDC (`orderId = "ord-1"`)
- Entonces se genera un asiento `type = ORDER_LOCK`, `reference = { orderId: "ord-1" }`
- Y sus postings son `DEBIT available(A, USDC) 2000000000` y `CREDIT locked(A, USDC) 2000000000`
- Y el asiento está balanceado por activo (DEBIT == CREDIT en USDC)

### Escenario 3: Asiento de liberación por cancelación [AT-02-03-03]
- Dado el `ORDER_LOCK` del escenario anterior, sin fills
- Cuando la orden `ord-1` se cancela
- Entonces se genera un asiento `type = ORDER_RELEASE`, `reference = { orderId: "ord-1" }`
- Y sus postings son `DEBIT locked(A, USDC) 2000000000` y `CREDIT available(A, USDC) 2000000000`

### Escenario 4: Asiento atómico de fill con fees hacia EX [AT-02-03-04]
- Dado un fill de 1 ETH (`1000000000000000000` wei) a `price_min = 2000000000` entre comprador `A` (**taker**) y vendedor `B` (**maker**), con `tradeId = "T-1"`
- Y `quote_min = floor(1000000000000000000 × 2000000000 / 10^18) = 2000000000`
- Y las fees (convenciones-monetarias §3.3): `A` taker recibe ETH ⇒ `fee_base = ceil(1000000000000000000 × 20 / 10000) = 2000000000000000` wei; `B` maker recibe USDC ⇒ `fee_quote = ceil(2000000000 × 10 / 10000) = 2000000` USDC-min
- Cuando se liquida
- Entonces se genera **un único** asiento `type = TRADE_FILL`, `reference = { tradeId: "T-1" }`, con estos **seis postings** (todos `amount > 0`):
  1. `DEBIT locked(A, USDC) 2000000000` — `kind = PRINCIPAL`
  2. `CREDIT available(A, ETH) 998000000000000000` (`= 1000000000000000000 − 2000000000000000`) — `kind = PRINCIPAL`
  3. `DEBIT locked(B, ETH) 1000000000000000000` — `kind = PRINCIPAL`
  4. `CREDIT available(B, USDC) 1998000000` (`= 2000000000 − 2000000`) — `kind = PRINCIPAL`
  5. `CREDIT available(EX, ETH) 2000000000000000` — `kind = FEE`
  6. `CREDIT available(EX, USDC) 2000000` — `kind = FEE`
- Y por **cada** activo la suma de CREDIT es igual a la de DEBIT (INV-1/INV-4): ETH ⇒ `1000000000000000000 = 998000000000000000 + 2000000000000000`; USDC ⇒ `2000000000 = 1998000000 + 2000000`
- Nota: estos valores son **derivables** de `00-fundaciones/convenciones-monetarias.md §3.3` y de `00-fundaciones/activos-y-par-de-trading.md §5` (fee_bps maker 10 / taker 20); son independientes de la composición de la épica 05 para los parámetros de fee fijados en fundaciones

### Escenario 5 (consistencia): Reconstrucción de balances desde el ledger [AT-02-03-05]
- Dado un ledger con una secuencia arbitraria de asientos para la cuenta `A`
- Cuando se reconstruyen los balances sumando `CREDIT − DEBIT` por cuenta/activo/bucket
- Entonces el resultado coincide **exactamente** con `available`/`locked`/`total` reportados por HU-02-01 (INV-8)
- Y reprocesar el ledger una segunda vez produce los **mismos** balances (determinismo)

### Escenario 6 (inmutabilidad): Corrección vía asiento de compensación [AT-02-03-06]
- Dado un asiento ya persistido con `entryId = E1`
- Cuando se requiere revertir su efecto
- Entonces **no** se modifica ni elimina `E1`
- Y se escribe un **nuevo** asiento `E2` con `type = REVERSAL`, postings exactamente inversos a los de `E1` y `reference = { reversedEntryId: E1 }` (RN-4), manteniendo `E1` intacto y `E1.entryId ≠ E2.entryId`

### Escenario 7 (idempotencia): Reprocesar el mismo depósito no duplica asiento [AT-02-03-07]
- Dado un asiento `DEPOSIT` ya escrito para la identidad `(txHash="0xabc...", logIndex=3)`
- Cuando se reprocesa el mismo evento on-chain con idéntica identidad
- Entonces **no** se crea un segundo asiento `DEPOSIT`
- Y el balance acreditado sigue siendo el de una sola acreditación (INV-5); la situación se reporta como `DEPOSIT_ALREADY_CREDITED`

### Escenario 8 (error/borde): Asiento desbalanceado es inválido [AT-02-03-08]
- Dado un intento de escribir un asiento cuyos postings, para algún activo, tienen `Σ CREDIT ≠ Σ DEBIT`
- Cuando el motor contable valida el asiento antes de persistir
- Entonces el asiento se **rechaza** y **no** se persiste (no se permite un ledger desbalanceado; violaría INV-1)
- Y ningún balance cambia

### Escenario 9 (atomicidad): Fallo a mitad de escritura no deja asiento parcial [AT-02-03-09]
- Dado un asiento `TRADE_FILL` con varios postings en proceso de escritura
- Cuando ocurre una falla luego de persistir algunos postings pero antes de completar el asiento
- Entonces, al recuperarse, **no** queda un asiento parcial: o el asiento completo está presente o está ausente (INV-4)
- Y los balances reconstruidos siguen cumpliendo INV-1, INV-2 e INV-3

### Escenario 10 (fill parcial): TRADE_FILL consume solo una fracción del locked del maker [AT-02-03-10]
- Dado un vendedor maker `B` con una SELL limit de 2 ETH abierta (`locked(B, ETH) = 2000000000000000000`) y un comprador taker `A` cuya BUY ejecuta solo `1000000000000000000` wei (1 ETH) a `price_min = 2000000000` (`tradeId = "T-2"`)
- Y `quote_min = 2000000000`; `fee_base = ceil(10^18 × 20 / 10000) = 2000000000000000`; `fee_quote = ceil(2000000000 × 10 / 10000) = 2000000`
- Cuando se liquida el fill parcial
- Entonces el `TRADE_FILL` consume **solo** `1000000000000000000` wei del `locked` del vendedor (`DEBIT locked(B, ETH) 1000000000000000000`), acredita `available(A, ETH) 998000000000000000`, `DEBIT locked(A, USDC) 2000000000`, `CREDIT available(B, USDC) 1998000000`, y los postings `kind = FEE` `CREDIT available(EX, ETH) 2000000000000000` y `CREDIT available(EX, USDC) 2000000`
- Y el `locked` residual del vendedor es `2000000000000000000 − 1000000000000000000 = 1000000000000000000` (el remanente sigue abierto)
- Y **no** se genera ningún `ORDER_RELEASE` para el remanente del vendedor (una SELL bloquea base, independiente del precio; el remanente solo se liberaría al cancelar — HU-02-02 RN-4)
- Y el asiento está balanceado por activo y el `locked` residual reconstruido cumple INV-3/INV-7

### Escenario 11 (atomicidad multi-asiento): TRADE_FILL + ORDER_RELEASE de surplus, todo o nada [AT-02-03-11]
- Dado un fill de una BUY limit que ejecuta a mejor precio (genera un `TRADE_FILL` y un `ORDER_RELEASE` de surplus con `release > 0`, ver HU-02-02 RN-6)
- Cuando se inyecta una falla **entre** la escritura del `TRADE_FILL` y la del `ORDER_RELEASE` (ver HU-02-04 AT-02-04-02 para el mecanismo de inyección)
- Entonces se revierten **ambos** asientos (rollback total de la transacción): no queda el `TRADE_FILL` sin su `ORDER_RELEASE`
- Y `locked(comprador, USDC)` no queda inflado por el surplus no liberado; los balances vuelven al estado exacto previo al fill (INV-4, INV-7)

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptacion (AT-*) pasan
- [ ] Reglas de negocio RN-1..RN-10 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md)
- [ ] (si aplica) Adherencia verificada al estandar on-chain citado — referencia `(txHash, logIndex)` de `DEPOSIT` conforme a INV-5 / épica 07
