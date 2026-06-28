# HU-08-01 — Solicitar retiro

- **Epica:** 08 — Retiros On-Chain
- **Actor / rol:** Trader autenticado (titular de la cuenta)
- **Prioridad:** Alta
- **Dependencias:** HU-02-01 (consulta de balances), HU-02-02 (reserva/liberación de fondos), HU-08-02 (débito y reserva al solicitar), HU-08-05 (retiro USDC: previsión de gas en ETH); épica 01 (autenticación/autorización)
- **Estandares de dominio aplicables:** EIP-55 (checksum de dirección Ethereum), red Sepolia chainId 11155111; serialización monetaria de `00-fundaciones/convenciones-monetarias.md`

## Historia
Como Trader autenticado, quiero solicitar el retiro de un activo (`ETH` o `USDC`) por un monto a una dirección Ethereum de destino, para sacar mis fondos del exchange hacia una wallet externa, con la garantía de que la solicitud se valida de forma estricta y determinista antes de comprometer mis fondos.

## Contexto y alcance
Esta HU cubre **la recepción y validación** de una solicitud de retiro: autenticación/autorización, validación de esquema, del activo, de la **dirección destino** (formato `0x`+40 hex y checksum EIP-55), del **monto** (positivo, entero de unidad mínima, ≥ mínimo del activo) y de **fondos suficientes** (incluida la previsión de fee de red). Si todas las validaciones pasan, la solicitud se **acepta** y se delega el bloqueo atómico de balance a HU-08-02 y la construcción/firma/broadcast a HU-08-03/HU-08-05.

NO cubre el detalle contable del bloqueo (HU-08-02), ni la firma/broadcast (HU-08-03), ni el seguimiento de confirmaciones/reconciliación (HU-08-04), ni las particularidades del ERC-20 (HU-08-05). Esta HU define el **contrato de validación** y la **precedencia de errores** de la solicitud.

Supuestos: la solicitud llega por la API HTTP autenticada (épica 09 fija nombres de ruta/campo). Activos válidos: `ETH` (base, 18 decimales, wei) y `USDC` (quote, ERC-20, 6 decimales). Red única Sepolia (`chainId = 11155111`).

## Reglas de negocio e invariantes
1. **RN-1 (autenticación/autorización):** la solicitud requiere una cuenta autenticada (`accountId`). Sin credencial válida → `UNAUTHENTICATED` (401). El retiro opera **solo** sobre los fondos de la cuenta autenticada; intentar retirar a nombre de otra cuenta → `UNAUTHORIZED` (403). El `details` de `UNAUTHORIZED` sigue el contrato de `modelo-de-errores.md` §3.1 (`{ resource }`): al intentar **crear** un retiro a nombre de otra cuenta, `details = { resource: "account", id: <accountId> }`; al **consultar/operar** un retiro ajeno (ver HU-08-04 RN-10), `details = { resource: "withdrawal", id: <withdrawalId> }`.
2. **RN-2 (esquema):** el payload debe traer `asset`, `amount` y `address` (más, opcionalmente, una clave de idempotencia). `amount` debe ser un **string** que matchee `^(0|[1-9][0-9]*)$` (entero decimal de unidad mínima, sin signo, sin decimales, sin notación científica, sin ceros a la izquierda). Si falta un campo o el tipo/formato es inválido → `VALIDATION_ERROR` (422) con `details.issues`.
3. **RN-3 (activo permitido):** `asset ∈ {ETH, USDC}`. Cualquier otro valor → `VALIDATION_ERROR` (422) (no existe un código `INVALID_ASSET` en el catálogo; el par es único y los activos son fijos).
4. **RN-4 (dirección — formato):** `address` debe matchear `^0x[0-9a-fA-F]{40}$` (prefijo `0x` + 40 hexadecimales = 20 bytes). Si no → `INVALID_ADDRESS` (422) con `details.address`.
5. **RN-5 (dirección — checksum EIP-55):** si `address` contiene **al menos una letra hexadecimal en mayúscula** (es decir, está en forma con checksum mixto), DEBE satisfacer el checksum EIP-55; si el checksum no es correcto → `INVALID_ADDRESS` (422). Una dirección **todo en minúsculas** (sin letras en mayúscula) se acepta y se normaliza a su forma con checksum EIP-55. Una dirección **todo en mayúsculas** que no sea un checksum válido se rechaza con `INVALID_ADDRESS`. (EIP-55 detecta direcciones mal tipeadas mediante el patrón de mayúsculas/minúsculas.)
6. **RN-6 (monto positivo y unidad mínima):** el `amount` representa un entero de **unidad mínima** del activo (wei para ETH; unidad de 6 decimales para USDC). Debe ser **estrictamente positivo** (`amount > 0`). Un `amount = "0"` (o no positivo) → `WITHDRAWAL_AMOUNT_INVALID` (422). Todo entero positivo de unidad mínima respeta por construcción la unidad mínima del activo (no se exige múltiplo de lot/tick: el retiro no es una orden).
7. **RN-7 (monto mínimo):** el monto debe cumplir `amount ≥ MIN_WITHDRAWAL_<asset>`: `MIN_WITHDRAWAL_ETH = 1000000000000000` wei (0.001 ETH) y `MIN_WITHDRAWAL_USDC = 1000000` USDC-min (1 USDC). Si `0 < amount < mínimo` → `WITHDRAWAL_BELOW_MIN` (422) con `details = { asset, amount, minWithdrawal }`.
8. **RN-8 (previsión de fee de red):** la previsión de gas es `fee_red_wei = gas_limit × gas_price_wei` (multiplicación entera exacta en wei). `gas_limit = GAS_LIMIT_ETH = 21000` para retiro de ETH y `GAS_LIMIT_ERC20 = 100000` para retiro de USDC. `gas_price_wei` se toma de `GAS_PRICE_WEI` de configuración (`GAS_PRICE_SOURCE = configured_fixed`, valor por defecto `20000000000` = 20 gwei) **en el momento de la solicitud** y se persiste como **snapshot** del retiro (HU-08-02 RN-7); el mismo valor se reutiliza sin re-estimar en firma/broadcast (HU-08-03) y reconciliación (HU-08-04). La previsión **siempre se cubre en ETH** (el gas se paga en ETH), independientemente del activo retirado.
9. **RN-9 (fondos suficientes):** se exige balance **disponible** suficiente, evaluado por activo:
   - Retiro de **ETH**: `disponible(ETH) ≥ amount_wei + fee_red_wei`. Si no → `INSUFFICIENT_FUNDS` (422) con `details = { asset: "ETH", required, available }` (donde `required = amount_wei + fee_red_wei`).
   - Retiro de **USDC**: `disponible(USDC) ≥ amount_usdc` **y** `disponible(ETH) ≥ fee_red_wei`. Si falta USDC → `INSUFFICIENT_FUNDS` con `asset: "USDC"`; si alcanza USDC pero falta ETH para el gas → `INSUFFICIENT_FUNDS` con `asset: "ETH"`. (El detalle de la reserva dual está en HU-08-05.)
10. **RN-10 (idempotencia de solicitud):** si el payload incluye una clave de idempotencia (`clientWithdrawalId`) ya usada por la cuenta:
    - con **mismos** parámetros (`asset`, `amount`, `address`): la operación es idempotente y devuelve **el mismo** retiro ya creado (mismo identificador), sin crear uno nuevo ni volver a bloquear fondos. Esto vale **cualquiera sea el estado actual** del retiro original (`PENDING`, `BROADCAST`, `CONFIRMED` o `FAILED`): siempre se devuelve el retiro existente, nunca se crea uno nuevo ni se vuelven a bloquear fondos. Para **reintentar** un retiro fallido el cliente debe usar una **clave de idempotencia distinta**;
    - con **parámetros distintos**: se rechaza con `CONFLICT` (409).
11. **RN-11 (precedencia de validación — determinista):** el primer error según este orden es el que se reporta (un error por respuesta):
    1. Autenticación (`UNAUTHENTICATED`) → autorización (`UNAUTHORIZED`).
    2. Esquema/tipos del payload, incl. patrón de `amount` (`VALIDATION_ERROR`).
    3. Activo permitido (`VALIDATION_ERROR` si `asset ∉ {ETH, USDC}`).
    4. Dirección: formato y checksum (`INVALID_ADDRESS`).
    5. Monto positivo / unidad mínima (`WITHDRAWAL_AMOUNT_INVALID`).
    6. Monto mínimo (`WITHDRAWAL_BELOW_MIN`).
    7. Idempotencia (`CONFLICT` ante clave reusada con distintos parámetros).
    8. Fondos suficientes (`INSUFFICIENT_FUNDS`).
12. **RN-12 (no compromete fondos si rechaza):** si la solicitud se rechaza por cualquier causa, **no** se bloquea ni debita ningún balance (INV-2): los balances quedan idénticos al estado previo. El bloqueo solo ocurre si la solicitud es aceptada (HU-08-02).
13. **RN-13 (sin floats; unidades explícitas):** todos los montos (`amount`, `required`, `available`, `minWithdrawal`, previsión de gas) se manejan como **enteros de unidad mínima** y se serializan como **string** con patrón `^(0|[1-9][0-9]*)$`. Prohibido floats.

## Criterios de aceptación (DoD)

### Escenario 1: solicitud de retiro de ETH válida (feliz) [AT-08-01-01]
- Dado un trader autenticado `acc-1` con `disponible(ETH) = "5000000000000000000"` (5 ETH) y `gas_price_wei = "20000000000"` (20 gwei), por lo que `fee_red_wei = 21000 × 20000000000 = "420000000000000"`
- Cuando solicita retirar `asset = ETH`, `amount = "1000000000000000000"` (1 ETH) a `address = 0x52908400098527886E0F7030069857D2E4169EE7` (checksum EIP-55 válido)
- Entonces la solicitud se **acepta** (no se devuelve error) y se crea un retiro en estado `PENDING`
- Y `required = amount + fee_red_wei = "1000420000000000000"` ≤ `disponible(ETH)`, por lo que pasa la validación de fondos (RN-9)
- Y el bloqueo efectivo del balance lo realiza HU-08-02

### Escenario 2: solicitud de retiro de USDC válida (feliz) [AT-08-01-02]
- Dado `acc-1` con `disponible(USDC) = "50000000"` (50 USDC) y `disponible(ETH) = "1000000000000000"` (0.001 ETH), `gas_price_wei = "5000000000"` (5 gwei) ⇒ `fee_red_wei = 100000 × 5000000000 = "500000000000000"`
- Cuando solicita retirar `asset = USDC`, `amount = "25000000"` (25 USDC) a una dirección EIP-55 válida
- Entonces se valida `disponible(USDC) = "50000000" ≥ amount = "25000000"` y `disponible(ETH) = "1000000000000000" ≥ fee_red_wei = "500000000000000"` (RN-9)
- Y la solicitud se **acepta** y se crea un retiro `PENDING`

### Escenario 3a (borde): monto exactamente igual al mínimo pasa [AT-08-01-03a]
- Dado `acc-1` con fondos suficientes
- Cuando solicita retirar `asset = ETH`, `amount = "1000000000000000"` (= `MIN_WITHDRAWAL_ETH`, 0.001 ETH)
- Entonces la validación de mínimo **pasa** (la comparación es `amount ≥ mínimo`, RN-7) y la solicitud se acepta

### Escenario 3b (borde): monto 1 wei por debajo del mínimo falla [AT-08-01-03b]
- Dado `acc-1` con fondos suficientes
- Cuando solicita retirar `asset = ETH`, `amount = "999999999999999"` (1 wei por debajo de `MIN_WITHDRAWAL_ETH`)
- Entonces se rechaza con `WITHDRAWAL_BELOW_MIN` (422) y `details = { asset: "ETH", amount: "999999999999999", minWithdrawal: "1000000000000000" }` (RN-7)
- Y no se bloquea ningún fondo (RN-12)

### Escenario 4 (borde): dirección destino en minúsculas se acepta y se normaliza [AT-08-01-04]
- Dado un trader autenticado con fondos suficientes
- Cuando solicita un retiro a `address = 0x52908400098527886e0f7030069857d2e4169ee7` (todo en minúsculas, sin checksum mixto)
- Entonces la dirección se **acepta** (RN-5) y se normaliza a su forma con checksum EIP-55 `0x52908400098527886E0F7030069857D2E4169EE7`
- Y la solicitud continúa la validación de monto y fondos

### Escenario 5 (error): dirección con checksum EIP-55 inválido [AT-08-01-05]
- Dado un trader autenticado con fondos suficientes
- Cuando solicita un retiro a `address = 0x52908400098527886E0F7030069857D2E4169Ee7` (mezcla de mayúsculas/minúsculas que NO satisface el checksum EIP-55)
- Entonces se rechaza con `INVALID_ADDRESS` (422) y `details.address` con el valor recibido (RN-5)
- Y no se bloquea ningún fondo (RN-12)

### Escenario 6 (error): dirección con longitud o prefijo inválidos [AT-08-01-06]
- Dado un trader autenticado
- Cuando solicita un retiro a `address = 0x1234` (no son 40 hex) o a `address = 52908400098527886E0F7030069857D2E4169EE7` (sin prefijo `0x`) o con caracteres no hexadecimales
- Entonces se rechaza con `INVALID_ADDRESS` (422) (RN-4), antes de evaluar monto o fondos

### Escenario 7 (error): monto no positivo [AT-08-01-07]
- Dado un trader autenticado con dirección válida
- Cuando solicita `asset = ETH`, `amount = "0"`
- Entonces se rechaza con `WITHDRAWAL_AMOUNT_INVALID` (422) (RN-6), porque el monto no es positivo
- Y no se bloquea ningún fondo

### Escenario 8 (error): monto con formato inválido (no matchea el patrón) [AT-08-01-08]
- Dado un trader autenticado
- Cuando solicita `amount = "1.5"` (decimal) o `amount = "1e18"` (notación científica) o `amount = "-5"` (negativo) o `amount = "01"` (cero a la izquierda) o `amount = 1000` (número JSON, no string)
- Entonces se rechaza con `VALIDATION_ERROR` (422) con `details.issues` (RN-2), por violar `^(0|[1-9][0-9]*)$`
- Y esto se evalúa **antes** que dirección, mínimo o fondos (RN-11)

### Escenario 9 (error): activo no soportado [AT-08-01-09]
- Dado un trader autenticado
- Cuando solicita `asset = "BTC"` (o cualquier valor fuera de `{ETH, USDC}`)
- Entonces se rechaza con `VALIDATION_ERROR` (422) (RN-3)

### Escenario 10 (error): fondos insuficientes en ETH para principal + gas [AT-08-01-10]
- Dado `acc-1` con `disponible(ETH) = "1000000000000000000"` (1 ETH) y `fee_red_wei = "420000000000000"`
- Cuando solicita retirar `asset = ETH`, `amount = "1000000000000000000"` (1 ETH, igual a todo su disponible)
- Entonces `required = amount + fee_red_wei = "1000420000000000000" > disponible(ETH)` y se rechaza con `INSUFFICIENT_FUNDS` (422), `details = { asset: "ETH", required: "1000420000000000000", available: "1000000000000000000" }` (RN-9)
- Y no se bloquea ningún fondo (RN-12)

### Escenario 11 (error): retiro de USDC con USDC suficiente pero sin ETH para el gas [AT-08-01-11]
- Dado `acc-1` con `disponible(USDC) = "50000000"` (50 USDC) y `disponible(ETH) = "0"`, `fee_red_wei = "500000000000000"`
- Cuando solicita retirar `asset = USDC`, `amount = "25000000"` (25 USDC)
- Entonces aunque el USDC alcanza, falta ETH para el gas y se rechaza con `INSUFFICIENT_FUNDS` (422), `details.asset = "ETH"`, `required = fee_red_wei`, `available = "0"` (RN-9)

### Escenario 12 (idempotencia): reenvío con la misma clave y mismos parámetros [AT-08-01-12]
- Dado que `acc-1` ya creó un retiro con `clientWithdrawalId = "w-123"`, `asset = ETH`, `amount = "1000000000000000000"`, `address = 0x52908400098527886E0F7030069857D2E4169EE7`
- Cuando reenvía exactamente la misma solicitud con `clientWithdrawalId = "w-123"`
- Entonces NO se crea un segundo retiro ni se bloquea fondo adicional: se devuelve el **mismo** retiro ya existente (mismo identificador) (RN-10)

### Escenario 12b (idempotencia en estado terminal): reenvío de una clave de un retiro ya FAILED [AT-08-01-12b]
- Dado que `acc-1` tiene un retiro con `clientWithdrawalId = "w-123"` ya en estado **terminal** `FAILED` (la reserva ya fue liberada)
- Cuando reenvía exactamente la misma solicitud con `clientWithdrawalId = "w-123"` y los mismos parámetros
- Entonces se devuelve el **mismo** retiro `FAILED` (mismo identificador) sin crear uno nuevo ni volver a bloquear fondos (RN-10)
- Y para reintentar el retiro el cliente debería usar una **clave de idempotencia distinta** (en cuyo caso se evalúa como una solicitud nueva)

### Escenario 13 (error de idempotencia): misma clave, parámetros distintos [AT-08-01-13]
- Dado que `acc-1` ya usó `clientWithdrawalId = "w-123"` para retirar 1 ETH
- Cuando reenvía con `clientWithdrawalId = "w-123"` pero `amount = "2000000000000000000"` (2 ETH)
- Entonces se rechaza con `CONFLICT` (409) (RN-10) y no se crea ni modifica ningún retiro

### Escenario 14 (error): solicitud sin autenticación [AT-08-01-14]
- Dado un cliente sin credencial válida (o token expirado)
- Cuando intenta solicitar cualquier retiro
- Entonces se rechaza con `UNAUTHENTICATED` (401) (RN-1), antes de cualquier otra validación (RN-11)

### Escenario 15 (precedencia): payload con múltiples violaciones [AT-08-01-15]
- Dado un trader autenticado
- Cuando solicita `asset = "BTC"`, `amount = "0"`, `address = "0x1234"` (activo inválido + monto cero + dirección inválida, todo a la vez)
- Entonces se reporta **solo** `VALIDATION_ERROR` (activo/esquema), por ser el primero en el orden de precedencia (RN-11), y no se evalúan dirección, monto ni fondos

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-08-01-01, -02, -03a, -03b, -04..-12, -12b, -13..-15) pasan
- [ ] Reglas de negocio RN-1..RN-13 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md (`UNAUTHENTICATED`, `UNAUTHORIZED`, `VALIDATION_ERROR`, `INVALID_ADDRESS`, `WITHDRAWAL_AMOUNT_INVALID`, `WITHDRAWAL_BELOW_MIN`, `INSUFFICIENT_FUNDS`, `CONFLICT`) con precedencia determinista
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md (montos en unidad mínima como string entero; previsión de gas por multiplicación entera; sin floats)
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md): INV-2 (rechazo previo, sin balances negativos), INV-3
- [ ] Adherencia verificada al estándar on-chain citado: dirección EIP-55; red Sepolia chainId 11155111
