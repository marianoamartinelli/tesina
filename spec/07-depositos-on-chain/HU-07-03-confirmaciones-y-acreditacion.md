# HU-07-03 — Confirmaciones y acreditación

- **Epica:** 07 — Depósitos On-Chain
- **Actor / rol:** Sistema (servicio de detección / acreditación on-chain); Trader autenticado (consulta el estado/saldo)
- **Prioridad:** Alta
- **Dependencias:** HU-07-01 (detección ETH nativo); HU-07-02 (detección USDC ERC-20); Épica 02 (balances y ledger de doble entrada); Épica 06 (mapeo dirección → cuenta); HU-07-04 (idempotencia y reorgs)
- **Estandares de dominio aplicables:** Red Sepolia chainId 11155111; `CONFIRMACIONES_REQUERIDAS = 12`

## Historia
Como Sistema de acreditación on-chain, quiero esperar el número de confirmaciones requerido antes de acreditar un depósito y luego **sumar el monto al balance disponible** del usuario, para que los fondos entren al exchange solo cuando son seguros (irreversibles en la práctica) y de forma contablemente correcta.

## Contexto y alcance
Esta HU toma un depósito ya **detectado** (HU-07-01 / HU-07-02), espera a que alcance `CONFIRMACIONES_REQUERIDAS = 12` y, una vez confirmado, **acredita** el monto al balance **disponible** del usuario propietario, generando el asiento de ledger de doble entrada correspondiente (vía épica 02). La acreditación es el único evento (junto con los retiros) que cambia la suma total de balances por activo (INV-1).

NO redefine la idempotencia ni el manejo de reorgs (HU-07-04), pero **coopera** con ellos: la acreditación se realiza una sola vez por identidad `(txHash, logIndex)`. El umbral de confirmaciones se mide sobre la cadena canónica de Sepolia. Antes de las 12 confirmaciones, el depósito permanece **PENDIENTE** y los fondos NO están disponibles para operar ni retirar.

## Reglas de negocio e invariantes
1. **RN-1 (cómputo de confirmaciones):** `confirmaciones = max(0, bloque_cabeza − bloque_de_inclusión)`, donde `bloque_de_inclusión` es el número de bloque que incluye la transacción y `bloque_cabeza` es la altura actual de la cadena canónica. (Definición conforme al glosario: una confirmación es cada bloque minado **encima** del bloque de inclusión.)
2. **RN-2 (umbral):** un depósito es **acreditable** sii `confirmaciones ≥ 12` (equivalente: `bloque_cabeza ≥ bloque_de_inclusión + 12`). El valor `CONFIRMACIONES_REQUERIDAS = 12` proviene de 00-fundaciones/activos-y-par-de-trading.md.
3. **RN-3 (estado PENDIENTE):** mientras `confirmaciones < 12`, el depósito está `PENDIENTE`; su monto NO se acredita, NO incrementa `disponible` ni `total`, y NO puede usarse para operar ni retirar.
4. **RN-4 (acreditación al disponible):** al alcanzar `confirmaciones ≥ 12` y no estar ya acreditado, se acredita el monto íntegro del depósito (sin fees: los depósitos no cobran fee) al balance **disponible** del activo correspondiente de la cuenta propietaria. Transición: `disponible(acc, A) += monto`. Por INV-3, `total(acc, A)` aumenta en el mismo monto; `bloqueado` no cambia.
5. **RN-5 (asiento de ledger):** la acreditación registra un asiento de doble entrada en el ledger (vía épica 02) que documenta el depósito con su identidad `(txHash, logIndex)`, activo, monto y cuenta. La reconstrucción de balances desde el ledger debe reproducir la acreditación (INV-8).
6. **RN-6 (conservación, INV-1):** tras acreditar, `Σ_acc total(acc, A) + total(EX, A)` aumenta exactamente en `monto` (el lado "depósitos confirmados" de la conservación). Ningún otro balance cambia por esta operación.
7. **RN-7 (monto exacto):** el monto acreditado es **idéntico** al detectado on-chain, en unidad mínima entera (wei para ETH, unidad de 6 decimales para USDC). No se aplica redondeo ni fee. Prohibido floats.
8. **RN-8 (no acreditar antes de confirmar):** cualquier intento de acreditar/usar un depósito con `confirmaciones < 12` se rechaza con `DEPOSIT_NOT_CONFIRMED` (HTTP 409), con `details = { txHash, confirmations, required }`. **`confirmations` y `required` son enteros JSON (números), no strings**, porque son **conteos** y no montos monetarios (la serialización como string aplica solo a montos/precios; ver `convenciones-monetarias.md` §5). `required` es siempre `12`. No altera balances.
9. **RN-9 (acreditación única):** un depósito se acredita a lo sumo una vez (INV-5). Reintentar acreditar un depósito ya acreditado se gobierna en HU-07-04 (`DEPOSIT_ALREADY_CREDITED`); no produce doble suma.
10. **RN-10 (no-negatividad):** la acreditación nunca puede dejar balances negativos (INV-2); solo suma montos positivos.
11. **RN-11 (consulta de estado):** un Trader autenticado puede consultar el estado de sus depósitos (`PENDIENTE` / `ACREDITADO` / `DESCARTADO`, según la máquina de estados del README) y las confirmaciones actuales. La consulta de una identidad inexistente da `NOT_FOUND` (404); la de un depósito de otra cuenta da `UNAUTHORIZED` (403); sin credencial da `UNAUTHENTICATED` (401). El **orden de precedencia** de estos errores es el de la tabla del README ("Precedencia de validación en consultas de depósitos").
12. **RN-12 (contrato de consulta y formato de `txHash`):** el contrato mínimo del endpoint de consulta es (el envelope HTTP y el registro de rutas los fija la épica 09 — HU-09-01):
    - **Listado:** `GET /api/v1/deposits` → `{ items: [<deposito>...], nextCursor: string|null }`, con filtros opcionales `asset ∈ {ETH, USDC}` y `status ∈ {PENDIENTE, ACREDITADO, DESCARTADO}`, y paginación `limit`/`cursor` (convención de HU-09-01 RN-8). Devuelve **solo** depósitos de la cuenta del token.
    - **Por identidad:** `GET /api/v1/deposits/{depositId}` con `depositId = "<txHash>:<logIndex>"` → el objeto `<deposito>`.
    - **Esquema del objeto `<deposito>`:** `{ depositId, txHash, logIndex, asset, amount, status, confirmations, required, blockNumber, creditedAt?, discardReason? }`, donde: `amount` es **string de entero** en unidad mínima del activo (`amountWei` para ETH / `amountUsdcMin` para USDC; nombre exacto por épica 09); `status ∈ {PENDIENTE, ACREDITADO, DESCARTADO}`; `confirmations`, `required` (= 12), `logIndex` y `blockNumber` son **enteros JSON**; `creditedAt` está presente solo si `ACREDITADO`; `discardReason ∈ {REORG, REVERTED}` solo si `DESCARTADO`.
    - **Formato de `txHash`:** patrón `^0x[0-9a-fA-F]{64}$` (case-insensitive; se normaliza a minúsculas). `logIndex` es entero `≥ 0`. Un `txHash` o `logIndex` mal formado en la consulta se rechaza con `VALIDATION_ERROR` (HTTP 422) con `details.issues`.

## Criterios de aceptación (DoD)

### Escenario 1: acreditación al alcanzar exactamente 12 confirmaciones [AT-07-03-01]
- Dado un depósito ETH `PENDIENTE` de `acc-1` por `amountWei = "1500000000000000000"`, incluido en el bloque `B`, con `disponible(acc-1, ETH) = "0"`
- Y que la cabeza de la cadena avanza hasta `B + 12` (es decir, `confirmaciones = 12`)
- Cuando el servicio evalúa el depósito
- Entonces el depósito pasa a `ACREDITADO` y `disponible(acc-1, ETH)` pasa a `"1500000000000000000"`
- Y `total(acc-1, ETH)` aumenta en `"1500000000000000000"` y `bloqueado` no cambia (INV-3)
- Y se registra el asiento de ledger correspondiente (INV-8)

### Escenario 2 (borde): 11 confirmaciones no alcanzan el umbral [AT-07-03-02]
- Dado el mismo depósito incluido en el bloque `B`
- Y que la cabeza está en `B + 11` (`confirmaciones = 11`)
- Cuando el servicio evalúa el depósito
- Entonces el depósito permanece `PENDIENTE` y NO se acredita
- Y `disponible(acc-1, ETH)` sigue en `"0"`

### Escenario 3 (error): intento de usar/acreditar un depósito no confirmado [AT-07-03-03]
- Dado un depósito con `confirmaciones = 5` (`< 12`)
- Cuando se fuerza/solicita su acreditación o uso
- Entonces se rechaza con `DEPOSIT_NOT_CONFIRMED` (HTTP 409) y `details = { txHash: "0x…", confirmations: 5, required: 12 }` (`confirmations` y `required` como **enteros JSON**, no strings; RN-8)
- Y no se modifica ningún balance

### Escenario 4: acreditación de un depósito USDC [AT-07-03-04]
- Dado un depósito USDC `PENDIENTE` de `acc-2` por `amountUsdcMin = "10000000"` (10 USDC), incluido en `B`, con `disponible(acc-2, USDC) = "2500000"`
- Y que la cabeza llega a `B + 12`
- Cuando el servicio evalúa el depósito
- Entonces `disponible(acc-2, USDC)` pasa a `"12500000"` (suma exacta de enteros, 6 decimales)
- Y el monto acreditado es idéntico al detectado, sin fee ni redondeo (RN-4, RN-7)

### Escenario 5 (borde): confirmaciones muy por encima del umbral [AT-07-03-05]
- Dado un depósito `PENDIENTE` incluido en `B`
- Y que la cabeza está en `B + 50` (`confirmaciones = 50`) sin que el depósito se haya acreditado aún
- Cuando el servicio evalúa el depósito
- Entonces se acredita exactamente una vez (≥ 12 cumplido) por el monto detectado
- Y posteriores evaluaciones no vuelven a acreditar (RN-9; ver HU-07-04)

### Escenario 6 (conservación, INV-1): la suma global aumenta solo por el depósito [AT-07-03-06]
- Dado el estado global `S0 = Σ_acc total(acc, ETH) + total(EX, ETH)` antes de acreditar
- Cuando se acredita un depósito ETH de monto `m`
- Entonces el nuevo estado global es exactamente `S0 + m` (ningún otro balance se mueve)
- Y la reconciliación con el ledger reproduce ese incremento (INV-1, INV-8)

### Escenario 7 (consulta de estado por el usuario) [AT-07-03-07]
- Dado un Trader autenticado dueño de `acc-1` con un depósito en `confirmaciones = 8`
- Cuando hace `GET /api/v1/deposits/{depositId}` (o `GET /api/v1/deposits`) de sus depósitos
- Entonces ve el depósito como `status = "PENDIENTE"` con `confirmations = 8` y `required = 12` (**enteros JSON**, RN-8/RN-12), y los campos del esquema de RN-12 (`depositId`, `txHash`, `logIndex`, `asset`, `amount`, `blockNumber`)
- Y al alcanzar 12 confirmaciones y acreditarse, lo ve como `status = "ACREDITADO"` (con `creditedAt` presente)

### Escenario 8 (error de autorización: depósito de otra cuenta) [AT-07-03-08]
- Dado un Trader autenticado dueño de `acc-1`
- Y que existe un depósito perteneciente a `acc-2` con identidad `(txHash, logIndex)`
- Cuando hace `GET /api/v1/deposits/{depositId}` de ese depósito de `acc-2`
- Entonces se rechaza con `UNAUTHORIZED` (HTTP 403)
- Y ningún dato del depósito de `acc-2` se filtra fuera del envelope de error

### Escenario 9 (error de autenticación: sin credencial) [AT-07-03-09]
- Dado un cliente **sin credencial válida** (token ausente, inválido o expirado)
- Cuando hace `GET /api/v1/deposits` o `GET /api/v1/deposits/{depositId}`
- Entonces se rechaza con `UNAUTHENTICATED` (HTTP 401), por precedencia antes que cualquier otra validación (README, tabla de precedencia)

### Escenario 10 (error: depósito inexistente) [AT-07-03-10]
- Dado un Trader autenticado dueño de `acc-1`
- Cuando consulta `GET /api/v1/deposits/{depositId}` con una identidad `(txHash, logIndex)` bien formada que **no existe** en el sistema
- Entonces se rechaza con `NOT_FOUND` (HTTP 404) y `details = { resource: "deposit", id: "<txHash>:<logIndex>" }`

### Escenario 11 (error: `txHash` mal formado) [AT-07-03-11]
- Dado un Trader autenticado
- Cuando consulta un depósito con un `txHash` que **no** matchea `^0x[0-9a-fA-F]{64}$` (p. ej. longitud incorrecta) o un `logIndex` no entero
- Entonces se rechaza con `VALIDATION_ERROR` (HTTP 422) con `details.issues` (RN-12), por precedencia antes que `NOT_FOUND`/`UNAUTHORIZED`

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-07-03-01..11) pasan
- [ ] Reglas de negocio RN-1..RN-12 verificadas (en especial el cómputo de confirmaciones y el umbral 12)
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md (`DEPOSIT_NOT_CONFIRMED`, `NOT_FOUND`, `VALIDATION_ERROR`, `UNAUTHORIZED`, `UNAUTHENTICATED`) y a la precedencia del README
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md (acreditación de monto íntegro, sin fee, sin floats)
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md): INV-1, INV-2, INV-3, INV-5, INV-8
- [ ] Adherencia verificada al estándar on-chain citado (Sepolia chainId 11155111; `CONFIRMACIONES_REQUERIDAS = 12`)
