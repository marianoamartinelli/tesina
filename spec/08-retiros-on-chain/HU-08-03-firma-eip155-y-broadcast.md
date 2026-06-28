# HU-08-03 — Firma EIP-155 y broadcast

- **Epica:** 08 — Retiros On-Chain
- **Actor / rol:** Sistema (servicio de firma y broadcast on-chain)
- **Prioridad:** Alta
- **Dependencias:** HU-08-02 (retiro `PENDING` con reserva), épica 06 (clave de la dirección emisora / firma), HU-08-04 (seguimiento de confirmaciones), HU-08-05 (payload del retiro USDC ERC-20)
- **Estandares de dominio aplicables:** EIP-155 (firma con `chainId` anti-replay), Sepolia chainId 11155111, BIP-32/39/44 (coin type 60, derivación de la clave emisora vía épica 06)

## Historia
Como Sistema de firma y broadcast, quiero **construir, firmar conforme EIP-155 y broadcastear** la transacción de un retiro `PENDING` con el `nonce` y el `gas` correctos, para enviar los fondos a la red Sepolia de forma anti-replay (atada a `chainId = 11155111`) y sin conflictos de nonce, dejando el retiro en estado `BROADCAST` para su seguimiento.

## Contexto y alcance
Esta HU cubre la **construcción del payload de transacción**, su **firma EIP-155** (que incluye `chainId = 11155111` en los datos firmados, evitando replay en otra red) y su **broadcast** al nodo de Sepolia, gestionando el **nonce** por dirección emisora (único, secuencial, contiguo) y el **gas** (`gas_limit` y `gas_price`) coherentes con la previsión reservada en HU-08-02. Aplica a retiros de **ETH nativo** (transferencia de `value`); la variante de **USDC (ERC-20 `transfer`)** comparte esta mecánica y se detalla en HU-08-05.

NO cubre la validación de la solicitud (HU-08-01), el bloqueo de balance (HU-08-02), ni el seguimiento de confirmaciones ni la reconciliación de balance (HU-08-04). La firma criptográfica de bajo nivel y la derivación de la clave de la dirección emisora las provee la épica 06; esta HU **consume** esa capacidad.

Supuesto: las transacciones salientes se firman con la clave de una **dirección emisora** (hot wallet) controlada por el exchange, derivada por la épica 06 según BIP-44 (`m / 44' / 60' / account' / change / address_index`, con índices hardened en `purpose`/`coin_type`/`account`).

## Reglas de negocio e invariantes
1. **RN-1 (precondición de estado):** solo se firma/broadcastea un retiro en estado `PENDING` con su reserva ya aplicada (HU-08-02). Intentar firmar un retiro en otro estado (`CONFIRMED`/`FAILED`/`BROADCAST` ya emitido) es una transición inválida → `CONFLICT` (409) y no genera una segunda transacción.
2. **RN-2 (chainId — EIP-155, anti-replay):** la transacción se firma **conforme EIP-155**, incluyendo `chainId = 11155111` en los datos firmados (INV-6). Si por configuración errónea el `chainId` a firmar **no** es `11155111`, la firma se **rechaza** antes de broadcastear con `CHAIN_ID_MISMATCH` (422), `details = { expected: "11155111", got: <valor> }`. **Nunca** se broadcastea una transacción con `chainId ≠ 11155111`.
3. **RN-3 (nonce — unicidad y secuencia):** el `nonce` se asigna **por dirección emisora**; debe ser **único, secuencial y contiguo** (sin huecos ni repeticiones), igual al siguiente nonce esperado de esa dirección (INV-6). La asignación de nonce está **serializada** por dirección emisora para evitar que dos retiros tomen el mismo nonce.
4. **RN-4 (conflicto de nonce):** si al construir o broadcastear se detecta que el `nonce` ya fue usado por una transacción anterior, o que quedaría un hueco (fuera de secuencia), es un conflicto → `NONCE_CONFLICT` (409), `details = { address, nonce }`. El retiro permanece `PENDING` (re-procesable con el nonce correcto); **no** se consume el bloqueo ni se duplica la transacción.
5. **RN-5 (gas correcto — `gas_price` = snapshot exacto):** la transacción usa `gas_limit` acorde al tipo (`GAS_LIMIT_ETH = 21000` para ETH; `GAS_LIMIT_ERC20 = 100000` para ERC-20, ver HU-08-05) y `gas_price = gas_price_wei_snapshot`, **el mismo** `gas_price_wei` registrado en la reserva (HU-08-02 RN-7). Esto garantiza: (a) el costo máximo `gas_limit × gas_price_wei_snapshot = fee_red_wei` está respaldado **exactamente** por la reserva (no hay sub-reserva ni sobre-reserva); (b) determinismo evaluable: la transacción firmada contiene el `gas_price` exacto snapshotteado. La transacción es **legacy (Type-0, `TX_TYPE = legacy`)** con un único campo `gas_price`; EIP-1559 está fuera de alcance. **No** se re-estima ni se re-reserva el gas entre la reserva y el broadcast.
6. **RN-6 (campos de la transacción ETH nativo):** para un retiro de ETH, la transacción tiene `to = address` (destino del retiro, ya validado/normalizado EIP-55), `value = amount_wei`, `data` vacío, `nonce` (RN-3), `gas_limit` y `gas_price` (RN-5), `chainId = 11155111` (RN-2). Todos los montos enteros en wei.
7. **RN-7 (firma con la clave emisora):** la transacción se firma con la clave privada de la **dirección emisora** del exchange, provista por la épica 06 (derivación BIP-32/39/44, coin type 60). La firma resultante es válida y verificable, y produce el `txHash`.
8. **RN-8 (broadcast y reintentos):** la transacción firmada se envía al nodo de Sepolia. Si el nodo la **acepta**, el retiro pasa a `BROADCAST` y se registra su `txHash` y `nonce`. Si el nodo la **rechaza** (error de red, payload inválido para el nodo, o **fondos on-chain insuficientes de la dirección emisora**, ver RN-13), → `BROADCAST_FAILED` (502), `details = { reason }`; el retiro permanece `PENDING` (**reintentable**) y **no** se libera ni consume el bloqueo en esta HU. El broadcast se reintenta hasta `MAX_BROADCAST_RETRIES = 5` veces; **agotados** los reintentos sin éxito, el broadcast se considera **definitivamente imposible** y el retiro transiciona `PENDING → FAILED` con reconciliación de liberación total (`gas_usado_wei = 0`, `WITHDRAWAL_RELEASE` completo; ver HU-08-04 RN-1/RN-5).
9. **RN-9 (idempotencia del broadcast):** un mismo retiro no debe producir **dos** transacciones distintas con dos nonces distintos para el mismo principal. Si una transacción ya fue broadcasteada (el retiro está en `BROADCAST`), reintentar broadcastea **la misma** transacción firmada (mismo `nonce`/`txHash`), no una nueva. Reenviar la misma transacción ya conocida al nodo no es un error (es idempotente a nivel de red).
10. **RN-10 (no altera balances):** firmar y broadcastear **no** modifica los balances internos (siguen `bloqueado` desde HU-08-02). El total por activo no cambia hasta `CONFIRMED` (INV-1). El consumo/liberación lo decide HU-08-04 según el resultado on-chain.
11. **RN-11 (persistencia del nonce y del txHash):** la asociación retiro ↔ (`nonce`, `txHash`, dirección emisora) es **persistente** (INV-8): tras un reinicio no se reasigna un nonce ya usado ni se firma una segunda transacción para un retiro ya broadcasteado.
12. **RN-12 (sin floats):** `value`, `gas_limit`, `gas_price`, `nonce` se manejan como **enteros**; los montos en wei como string `^(0|[1-9][0-9]*)$`. Prohibido floats.
13. **RN-13 (ETH on-chain de la emisora — supuesto operacional):** el gas on-chain lo paga la **dirección emisora** (hot wallet) con su ETH **real** en Sepolia, independiente de los balances internos del usuario. Se **asume** que la emisora siempre tiene ETH on-chain suficiente (operación/recarga de la hot wallet **fuera de alcance** de la tesina). Si el nodo rechaza el broadcast por **fondos insuficientes de la emisora**, se trata como `BROADCAST_FAILED` (RN-8): el retiro queda `PENDING` y se reintenta; agotados `MAX_BROADCAST_RETRIES`, transiciona `PENDING → FAILED` (HU-08-04). Este modo de falla **no** requiere un AT de evaluación dedicado; queda documentado como supuesto.
14. **RN-14 (reconciliación de nonce al arranque):** al iniciar/reiniciar el servicio, para cada dirección emisora el nonce operativo se determina como `MAX(max_nonce_persistido_en_ledger + 1, eth_getTransactionCount(address, "pending"))`. Si el nonce del nodo es **mayor** que el persistido, indica transacciones propias no registradas en el ledger; antes de asignar nuevos nonces se **reconcilia** el estado de los retiros `PENDING`/`BROADCAST` con los `txHash` hallados en el mempool/historial del nodo. Así no se reasigna un nonce ya usado (`NONCE_CONFLICT`, RN-4) ni se firma una segunda transacción para un retiro ya broadcasteado (RN-9/RN-11), preservando INV-6 e INV-8 a través de reinicios.

## Criterios de aceptación (DoD)

### Escenario 1: firma EIP-155 y broadcast de retiro de ETH (feliz) [AT-08-03-01]
- Dado un retiro `PENDING` de `acc-1`: `asset = ETH`, `amount = "1000000000000000000"` (1 ETH), `address = 0x52908400098527886E0F7030069857D2E4169EE7`, reserva ya aplicada, y el siguiente nonce esperado de la dirección emisora es `7`
- Cuando el servicio construye, firma y broadcastea la transacción
- Entonces la transacción firmada tiene `to = 0x52908400098527886E0F7030069857D2E4169EE7`, `value = "1000000000000000000"`, `nonce = 7`, `gas_limit = 21000`, `chainId = 11155111` (RN-2/RN-3/RN-6)
- Y el nodo la acepta, se registra `txHash` y el retiro pasa a `BROADCAST` (RN-8)
- Y los balances internos **no** cambian (siguen bloqueados, RN-10)

### Escenario 2 (anti-replay): chainId siempre 11155111 [AT-08-03-02]
- Dado cualquier retiro a firmar
- Cuando se construye la firma
- Entonces el `chainId` firmado es **exactamente** `11155111` (Sepolia), conforme EIP-155 (RN-2, INV-6)
- Y una transacción firmada para otra red (p. ej. `chainId = 1`) **no** se broadcastea: se rechaza con `CHAIN_ID_MISMATCH` (`expected = "11155111"`, `got = "1"`)

### Escenario 3 (nonce secuencial): retiros sucesivos de la misma emisora [AT-08-03-03]
- Dado que la dirección emisora tiene nonce esperado `7` y hay tres retiros `PENDING` a procesar
- Cuando se firman y broadcastean en orden
- Entonces toman nonces `7`, `8`, `9` respectivamente: **únicos, secuenciales y contiguos** (RN-3, INV-6)
- Y la lista de nonces usados por la emisora es estrictamente creciente y sin huecos

### Escenario 4 (error): conflicto de nonce [AT-08-03-04]
- Dado un retiro cuyo nonce candidato `7` ya fue usado por una transacción confirmada/pendiente de la misma emisora
- Cuando se intenta broadcastear con `nonce = 7`
- Entonces se rechaza con `NONCE_CONFLICT` (409), `details = { address, nonce: "7" }` (RN-4)
- Y el retiro permanece `PENDING`, sin consumir el bloqueo ni duplicar transacción

### Escenario 5 (concurrencia): dos retiros de la misma emisora no toman el mismo nonce [AT-08-03-05]
- Dado dos retiros `PENDING` de la misma dirección emisora procesados **concurrentemente**, con nonce esperado `7`
- Cuando ambos intentan asignar nonce
- Entonces la asignación serializada otorga `7` a uno y `8` al otro (RN-3); **nunca** ambos `7`
- Y no se produce un hueco en la secuencia de nonces

### Escenario 6 (error): broadcast rechazado por el nodo [AT-08-03-06]
- Dado un retiro `PENDING` correctamente firmado (chainId y nonce válidos)
- Cuando el nodo rechaza el broadcast (p. ej. error de red o payload no aceptado)
- Entonces se reporta `BROADCAST_FAILED` (502), `details = { reason }` (RN-8)
- Y el retiro permanece `PENDING` (reintentable) y el bloqueo de balance no se libera ni se consume (RN-8/RN-10)

### Escenario 7 (gas respaldado exactamente): la transacción usa el `gas_price` snapshotteado [AT-08-03-07]
- Dado un retiro de ETH con `gas_price_wei_snapshot = "20000000000"` (20 gwei) y `fee_red_wei = "420000000000000"` reservado (`21000 × 20000000000`)
- Cuando se construye la transacción con `gas_limit = 21000`
- Entonces la transacción usa `gas_price = "20000000000"` = `gas_price_wei_snapshot` (RN-5), por lo que `21000 × 20000000000 = "420000000000000" = fee_red_wei`: el gas comprometido está respaldado **exactamente** por la reserva (ni sub- ni sobre-reserva)
- Y **no** existe un flujo de re-estimación/re-reserva: como `gas_price` es el snapshot, no hay posibilidad de sub-reserva por gas creciente entre la reserva y el broadcast

### Escenario 8 (idempotencia/persistencia): reinicio no reasigna nonce ni re-firma [AT-08-03-08]
- Dado un retiro ya en `BROADCAST` con `nonce = 7` y `txHash = 0x…`
- Cuando el sistema se reinicia (INV-8) y reanuda el procesamiento
- Entonces NO se firma una segunda transacción para ese retiro ni se reasigna su nonce; se conserva `(nonce = 7, txHash)` (RN-9/RN-11)
- Y un nuevo retiro de la misma emisora toma `nonce = 8`, manteniendo la contigüidad

### Escenario 9a (error): intentar firmar un retiro ya en `BROADCAST` [AT-08-03-09a]
- Dado un retiro ya en estado `BROADCAST` (`txHash`/`nonce` ya emitidos)
- Cuando se intenta firmarlo/broadcastearlo de nuevo como si fuera `PENDING`
- Entonces se rechaza con `CONFLICT` (409) por transición inválida (RN-1); no se genera **ninguna** nueva transacción ni se reasigna nonce, y el estado no cambia (la idempotencia de RN-9 solo re-emite la **misma** tx ya conocida)

### Escenario 9b (error): intentar firmar un retiro ya `CONFIRMED` [AT-08-03-09b]
- Dado un retiro ya en estado `CONFIRMED` (terminal)
- Cuando se intenta firmarlo/broadcastearlo de nuevo
- Entonces se rechaza con `CONFLICT` (409) por transición inválida (RN-1) y no se genera ninguna transacción ni cambia el estado

### Escenario 9c (error): intentar firmar un retiro ya `FAILED` [AT-08-03-09c]
- Dado un retiro ya en estado `FAILED` (terminal)
- Cuando se intenta firmarlo/broadcastearlo de nuevo
- Entonces se rechaza con `CONFLICT` (409) por transición inválida (RN-1) y no se genera ninguna transacción ni cambia el estado

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-08-03-01..-08, -09a, -09b, -09c) pasan
- [ ] Reglas de negocio RN-1..RN-14 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md (`CHAIN_ID_MISMATCH`, `NONCE_CONFLICT`, `BROADCAST_FAILED`, `CONFLICT`)
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md (`value`/`gas` enteros, montos como string; sin floats)
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md): INV-6 (chainId = 11155111, nonce único/secuencial/contiguo), INV-1 (balances no cambian al broadcastear), INV-8 (persistencia de nonce/txHash)
- [ ] Adherencia verificada al estándar on-chain citado: EIP-155 (chainId 11155111 en la firma); clave emisora derivada por BIP-32/39/44 coin type 60 (épica 06)
