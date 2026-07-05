# HU-10-06 — Depósitos y retiros

- **Epica:** 10 — Cliente Web (React)
- **Actor / rol:** Trader autenticado operando la web
- **Prioridad:** Alta
- **Dependencias:** HU de épica 09 (endpoints de dirección de depósito, alta de retiro, estado de depósitos/retiros y canal WebSocket); épica 06 (derivación de dirección); épica 07 (depósitos/confirmaciones); épica 08 (retiros, firma EIP-155, nonce). Fundaciones (00).
- **Estandares de dominio aplicables:** **EIP-55** (checksum de dirección), **EIP-155** (firma con `chainId`), **Sepolia chainId 11155111**, confirmaciones requeridas = **12**, coin type BIP-44 = 60. (La derivación BIP-32/39/44 ocurre en backend; el cliente la consume.)

## Historia
Como trader autenticado, quiero ver mi dirección de depósito y solicitar retiros mediante un formulario con validaciones, para ingresar fondos al exchange y sacarlos a una dirección externa, siguiendo el estado de cada operación on-chain.

## Contexto y alcance
Cubre dos flujos del cliente React sobre **Sepolia (chainId 11155111)**: (1) **Depósitos** — mostrar la dirección de depósito de la cuenta (ETH nativo y USDC-mock ERC-20 a la misma dirección controlada por el exchange), permitir copiarla y seguir el estado de cada depósito según el enum de la épica 07 (`PENDIENTE` con progreso `n/12` → `ACREDITADO`, o `DESCARTADO`); (2) **Retiros** — formulario con activo, dirección destino y monto, con validaciones de cliente y seguimiento de estado según el enum canónico de la épica 08 (`PENDING` → `BROADCAST` → `CONFIRMED`, con rama terminal `FAILED`). La derivación de claves, la firma EIP-155, el manejo de nonce y la detección/acreditación de depósitos ocurren en el backend (épicas 06–08); el cliente solo consume la API y presenta estados (RNE-2, RNE-8). El **código QR** de la dirección de depósito queda **fuera de alcance** (no se evalúa).

## Reglas de negocio e invariantes
1. **RN-1 (dirección de depósito).** El cliente obtiene y muestra la dirección de depósito de la cuenta como `0x` + 40 hex con **checksum EIP-55**. Ofrece copiar al portapapeles. Advierte que la red es **Sepolia (chainId 11155111)** y que solo se aceptan ETH y el USDC-mock del proyecto (envíos de otras redes/activos no se acreditan). *(El código QR de la dirección queda **fuera de alcance** de esta HU; ver "Contexto y alcance".)*
2. **RN-2 (idempotencia visible de depósitos — INV-5).** Un depósito se identifica por `(txHash, logIndex)` (ERC-20) o `(txHash, 0)` (ETH nativo) y se acredita **a lo sumo una vez**, solo tras **12 confirmaciones**. El cliente muestra cada depósito una sola vez; si el mismo depósito vuelve a aparecer en un re-poll/refetch del listado, no lo duplica ni lo re-suma.
3. **RN-3 (seguimiento de confirmaciones de depósito).** Para cada depósito detectado, el cliente muestra el estado según el enum de la épica 07: `PENDIENTE` (visto, < 12 confirmaciones, indicando `n/12`), `ACREDITADO` (≥ 12 confirmaciones y crédito aplicado), `DESCARTADO` (RN-12). **Mecanismo de actualización:** **no existe un canal WebSocket de depósitos**; el progreso `n/12` y los cambios de estado provienen de la API REST (`GET /deposits`, épicas 07/09) mediante **polling periódico** (p. ej. cada **15 s**) mientras la vista está visible, con refetch al volver a ella (mismo patrón que HU-11-06 RN-3). La **acreditación** (aumento del `disponible`) llega por el canal WebSocket **`balances`** (HU-10-05). El cliente no acredita por su cuenta.
4. **RN-4 (validación de dirección destino — EIP-55).** En el retiro, la dirección destino debe ser `0x` + 40 caracteres hexadecimales con **checksum EIP-55 válido**. Si no, el cliente bloquea el envío anticipando `INVALID_ADDRESS`; de llegar al backend, este responde `INVALID_ADDRESS` (422).
5. **RN-5 (monto de retiro — sin floats, RNE-1).** El monto se convierte de humano a unidad mínima por desplazamiento de coma sobre string (ETH 18 dec; USDC 6 dec) y se envía como string `^(0|[1-9][0-9]*)$`. Debe ser **positivo** y respetar la unidad mínima del activo; si no, se anticipa `WITHDRAWAL_AMOUNT_INVALID`.
6. **RN-6 (mínimo de retiro).** El monto debe ser `≥` el mínimo de retiro del activo. Los mínimos son **constantes del contrato de evaluación fijadas por la épica 08** (HU-08-01 RN-7): **`MIN_WITHDRAWAL_ETH = 1000000000000000` wei (0.001 ETH)** y **`MIN_WITHDRAWAL_USDC = 1000000` USDC-min (1 USDC)**. No existe un endpoint de configuración de activos/retiros: el cliente usa estos valores constantes para el feedback temprano (mismo enfoque que HU-11-06 RN-6) y **muestra el mínimo** junto al campo de monto. Si el monto es menor, el cliente lo anticipa como `WITHDRAWAL_BELOW_MIN`; ante la respuesta del servidor (validación autoritativa), muestra el mínimo formateado desde `details.minWithdrawal`.
7. **RN-7 (fondos suficientes — INV-2).** El monto a retirar más, si aplica, su costo, no puede exceder el disponible (HU-10-05). El cliente advierte si excede el disponible, pero el rechazo autoritativo es `INSUFFICIENT_FUNDS` (422) del servidor (RNE-2).
8. **RN-8 (seguimiento de retiro — enum canónico).** Tras solicitar el retiro, el cliente muestra su estado usando el **enum canónico** de la épica 08 (HU-08-04) / contrato REST de la épica 09: **`PENDING` → `BROADCAST` → `CONFIRMED`**, con la rama terminal **`FAILED`**. La UI mapea cada estado a una etiqueta legible (p. ej. `PENDING` = "solicitado/firmando", `BROADCAST` = "broadcasteado (n/12)", `CONFIRMED` = "confirmado", `FAILED` = "fallido"), en paridad con HU-11-06 RN-8. `CONFIRMED` y `FAILED` son **terminales**; la finalización (`CONFIRMED`) requiere **12** confirmaciones. `FAILED` se alcanza **únicamente** por: (a) broadcast **definitivamente fallido** (agotados los reintentos internos, HU-08-03 RN-8); (b) transacción **descartada** del mempool o **timeout de inclusión** (HU-08-04 RN-1/RN-9); (c) transacción minada pero **revertida** (`status = 0`); o (d) **cancelación del usuario** de un retiro `PENDING` (HU-08-04 RN-13). Una **reorg antes de las 12 confirmaciones NO produce `FAILED`**: el backend recalcula las confirmaciones y el retiro **vuelve a `BROADCAST`** (HU-08-04 RN-9); el cliente refleja el retroceso del contador `n/12` sin tratarlo como error. Al recibir `FAILED` (con la causa en `failureReason`, épica 09), el cliente muestra un mensaje claro con la causa y confirma que el `disponible` fue restaurado (los fondos bloqueados se liberan por reconciliación del backend y el `disponible` vuelve a subir vía canal `balances`, HU-10-05). Como `FAILED` es terminal, **no existe "reintentar el mismo retiro"**: el cliente ofrece **crear un retiro nuevo** con un `clientWithdrawalId` **distinto** (HU-08-01 RN-10, RN-13), sin dejar la UI colgada en `BROADCAST`. **Mecanismo de actualización:** el estado proviene del canal privado WebSocket **`withdrawals`** (épica 09) y/o de `GET /withdrawals/{withdrawalId}`. Cuando la API expone el `txHash`, el cliente lo muestra (enlazable a un explorer de Sepolia) y rotula la red **chainId 11155111**. El cliente no firma ni construye transacciones.
9. **RN-9 (errores on-chain por `code` — RNE-3).** El cliente mapea por `code` los errores de **validación** de la solicitud de retiro: `INVALID_ADDRESS`, `WITHDRAWAL_AMOUNT_INVALID`, `WITHDRAWAL_BELOW_MIN`, `INSUFFICIENT_FUNDS`, `CHAIN_ID_MISMATCH` (la red de la operación no es 11155111) y `CONFLICT` (idempotencia, RN-13). Cada error se muestra con mensaje claro y `details` cuando aporta (montos como string). Los fallos de **firma/broadcast/nonce** (`BROADCAST_FAILED`, `NONCE_CONFLICT`) son pasos **internos del backend con reintentos** (HU-08-03): `POST /withdrawals` es **asíncrono (202)** y esos errores **nunca llegan como respuesta HTTP del alta**. Si el broadcast resulta definitivamente imposible, el cliente observa el retiro con `status = "FAILED"` y la causa en `failureReason` — vía el canal privado `withdrawals` o `GET /withdrawals/{withdrawalId}` — y muestra esa causa (RN-8). El reintento de broadcast es **interno del backend**: no existe (ni se necesita) un endpoint de reintento del lado del cliente.
10. **RN-10 (anti doble submit).** Mientras una solicitud de retiro está en curso, el botón se deshabilita para evitar enviar dos retiros idénticos por doble clic.
11. **RN-11 (red única — RNE-8).** Toda la UX on-chain refiere exclusivamente a **Sepolia (chainId 11155111)**; no se ofrecen otras redes ni se permite seleccionar chainId.
12. **RN-12 (depósito descartado por reorg o reversión — RNE-10).** Un depósito **`ACREDITADO` es terminal**: el backend **nunca** revierte un crédito ya aplicado (HU-07-04 RN-10), por lo que **no existe** un estado "REVERTIDO". El caso real es un depósito **`PENDIENTE`** (aún no acreditado) cuyo bloque queda huérfano por una reorg sin reinclusión, o cuya transacción resulta revertida: pasa a **`DESCARTADO`** con `discardReason ∈ {REORG, REVERTED}` (épica 07, HU-07-03 RN-12 / HU-07-04). El cliente lo muestra como **descartado** con su `(txHash, logIndex)` y la causa; como el monto **nunca se había sumado** al balance (un `PENDIENTE` no acredita), **no hay retroceso de saldo** que aplicar. El cliente sigue siempre al servidor como fuente de verdad (RNE-2).
13. **RN-13 (idempotencia de retiro — análoga a RNE-7).** Cada intento lógico de retiro genera un `clientWithdrawalId` (UUID v4) al abrir el formulario o en el primer envío, y se **reutiliza** en reintentos del mismo flujo (timeout/red). El cliente lo incluye en el payload. Si el backend responde `CONFLICT` (409) porque ya existe un retiro con ese `clientWithdrawalId` para la cuenta, el cliente **no crea un segundo retiro**: muestra el estado del retiro ya registrado (recuperándolo por `clientWithdrawalId` o del listado de retiros). El backend devuelve el `withdrawalId` del retiro creado; el cliente lo conserva para el seguimiento (RN-8). Esto cubre el caso en que el request llega al backend, el retiro se crea y la respuesta se pierde por timeout: un segundo intento **no** genera un segundo retiro por el mismo importe. (RN-10 previene solo el doble clic; RN-13 cubre además la falla de red.)

## Criterios de aceptación (DoD)

### Escenario 1: Mostrar dirección de depósito con checksum EIP-55 [AT-10-06-01]
- Dado un trader autenticado en la sección de depósitos
- Cuando el cliente obtiene la dirección de depósito de la cuenta
- Entonces la muestra como `0x` + 40 hex con checksum EIP-55
- Y ofrece copiarla y advierte que la red es Sepolia (chainId 11155111) y solo ETH/USDC-mock

### Escenario 2: Seguimiento de un depósito hasta acreditarse (12 confirmaciones) [AT-10-06-02]
- Dado un depósito detectado con `(txHash, logIndex)` y 3 confirmaciones
- Cuando el cliente recibe el estado de la API
- Entonces muestra `PENDIENTE 3/12`
- Y al alcanzar 12 confirmaciones y aplicarse el crédito, muestra `ACREDITADO`
- Y el balance del activo se incrementa (reflejado por HU-10-05)

### Escenario 3 (idempotencia): el mismo depósito no se duplica [AT-10-06-03]
- Dado un depósito ya listado como `ACREDITADO` con identidad `(txHash, logIndex)`
- Cuando el cliente vuelve a obtener el listado por polling de `GET /deposits` (o el usuario refresca la vista) y el mismo depósito aparece nuevamente con `txHash` y `logIndex` idénticos
- Entonces lo muestra una sola vez (no duplica la fila ni vuelve a sumar el monto) (RN-2/RN-3)
- Y, si el backend reporta `DEPOSIT_ALREADY_CREDITED` (409) ante un reproceso, no altera balances en la UI

### Escenario 4: Retiro válido y seguimiento de estado [AT-10-06-04]
- Dado un trader con disponible suficiente
- Y un formulario de retiro USDC, dirección destino con checksum EIP-55 válido, monto `25` USDC
- Cuando solicita el retiro
- Entonces el cliente envía `amountMinUnit="25000000"`, la dirección destino y un `clientWithdrawalId` (RN-13) al endpoint de retiro
- Y muestra el ciclo `PENDING` → `BROADCAST` (con progreso `n/12`) → `CONFIRMED` con sus etiquetas de UI (RN-8)
- Y muestra el `txHash` (enlazable a explorer de Sepolia) cuando la API lo expone

### Escenario 5 (error): dirección destino con checksum inválido [AT-10-06-05]
- Dado una dirección `0x` + 40 hex con checksum EIP-55 incorrecto
- Cuando el usuario intenta retirar
- Entonces el cliente bloquea el envío anticipando `INVALID_ADDRESS`
- Y, de llegar al backend, este responde `{ error: { code: "INVALID_ADDRESS", details: { address } } }` (422)

### Escenario 6 (error): monto que no respeta la unidad mínima [AT-10-06-06]
- Dado un monto de retiro no positivo o con más precisión que la unidad mínima del activo
- Cuando el usuario intenta retirar
- Entonces el cliente lo bloquea anticipando `WITHDRAWAL_AMOUNT_INVALID`
- Y no envía un monto que no matchee `^(0|[1-9][0-9]*)$`

### Escenario 7 (error): monto por debajo del mínimo de retiro [AT-10-06-07]
- Dado un retiro de USDC por `"500000"` (0.5 USDC), menor al mínimo `MIN_WITHDRAWAL_USDC = 1000000` (1 USDC) (RN-6)
- Cuando el usuario intenta retirar, el cliente lo anticipa como `WITHDRAWAL_BELOW_MIN` y, de llegar al backend, la API responde `{ error: { code: "WITHDRAWAL_BELOW_MIN", details: { asset: "USDC", amount: "500000", minWithdrawal: "1000000" } } }` (422)
- Entonces el cliente informa el mínimo requerido (1 USDC) formateado desde `minWithdrawal`

### Escenario 8 (error): fondos insuficientes para retirar [AT-10-06-08]
- Dado un monto mayor al disponible del activo
- Cuando la API responde `{ error: { code: "INSUFFICIENT_FUNDS", details: { asset, required, available } } }` (422)
- Entonces el cliente muestra el faltante y no altera balances en la UI (INV-2)

### Escenario 9 (error): broadcast definitivamente fallido observado como FAILED [AT-10-06-09]
- Dado un retiro **aceptado** por el backend (`POST /withdrawals` respondió **202** con su `withdrawalId`) cuyo broadcast falla de forma **definitiva** en el backend (agotados los reintentos internos, HU-08-03 RN-8; el error del nodo **no** llega como respuesta HTTP del alta)
- Cuando el cliente observa el retiro con `status = "FAILED"` y la causa en `failureReason`, vía el canal privado `withdrawals` o `GET /withdrawals/{withdrawalId}` (RN-9)
- Entonces informa que el envío on-chain falló, mostrando la causa (`failureReason`)
- Y confirma que el `disponible` fue restaurado (canal `balances`, HU-10-05) y, por ser `FAILED` terminal, ofrece crear un retiro **nuevo** con un `clientWithdrawalId` **distinto** (RN-8); el reintento de broadcast es interno del backend y no existe un endpoint de reintento

### Escenario 10 (error/borde): chainId distinto de Sepolia [AT-10-06-10]
- Dado un contexto donde la operación reporta una red distinta de `11155111`
- Cuando la API responde `{ error: { code: "CHAIN_ID_MISMATCH", details: { expected: "11155111", got } } }` (422)
- Entonces el cliente informa que solo se opera en Sepolia (chainId 11155111)
- Y no ofrece cambiar de red

### Escenario 11 (borde): anti doble submit del retiro [AT-10-06-11]
- Dado una solicitud de retiro en curso
- Cuando el usuario vuelve a presionar "Retirar"
- Entonces el segundo clic se ignora y el botón permanece deshabilitado hasta resolver
- Y no se generan dos retiros por el mismo importe por doble clic

### Escenario 12: Retiro de ETH (activo nativo, 18 decimales) [AT-10-06-12]
- Dado un trader con ETH disponible suficiente
- Y un formulario de retiro ETH, dirección destino con checksum EIP-55 válido, monto humano `0.1` ETH
- Cuando solicita el retiro
- Entonces el cliente envía `amountMinUnit="100000000000000000"` (18 decimales) y un `clientWithdrawalId`
- Y el ciclo de estados `PENDING` → `BROADCAST` (con progreso `n/12`) → `CONFIRMED` se muestra igual que para USDC (RN-8)

### Escenario 13 (error): retiro FAILED y creación de un retiro nuevo [AT-10-06-13]
- Dado un retiro en estado `BROADCAST` (mostrado como "broadcasteado (n/12)")
- Cuando el backend lo reconcilia como `FAILED` (tx revertida, tx descartada/timeout de inclusión o broadcast definitivamente fallido; HU-08-04 RN-1) y el cliente lo recibe con la causa en `failureReason` por el canal `withdrawals` o `GET /withdrawals/{withdrawalId}`
- Entonces el cliente muestra `FAILED` con un mensaje claro de la causa
- Y confirma que el `disponible` fue restaurado (refrescando balances o vía canal `balances`, HU-10-05)
- Y, por ser `FAILED` **terminal** (no existe reintentar el mismo retiro), ofrece **crear un retiro nuevo** con un `clientWithdrawalId` **distinto** (RN-8/RN-13), sin dejar la UI colgada en `BROADCAST`

### Escenario 14 (error): conflicto de nonce durante el retiro [AT-10-06-14]
- Dado un retiro aceptado en validación (`POST /withdrawals` respondió 202)
- Cuando el backend detecta un conflicto de nonce al construir/broadcastear (`NONCE_CONFLICT`, HU-08-03 RN-4) — paso **interno con reintentos** que **no** llega como respuesta HTTP al cliente —
- Entonces el cliente solo observa el estado del retiro por el canal `withdrawals` o `GET /withdrawals/{withdrawalId}`: sigue en `PENDING`/`BROADCAST` si el backend lo resuelve, o pasa a `FAILED` con la causa en `failureReason` si el broadcast resulta definitivamente imposible (RN-9)
- Y ante `FAILED` la UI muestra la causa **sin reintentar automáticamente** y ofrece crear un retiro nuevo con `clientWithdrawalId` distinto (RN-8)

### Escenario 15 (idempotencia/concurrencia): reintento de retiro reutiliza clientWithdrawalId [AT-10-06-15]
- Dado una solicitud de retiro enviada con `clientWithdrawalId` cuyo resultado no llegó (timeout de red)
- Cuando el cliente reintenta el **mismo** retiro con el **mismo** `clientWithdrawalId`
- Y la API responde `{ error: { code: "CONFLICT", details: { reason } } }` (409) por `clientWithdrawalId` ya registrado
- Entonces el cliente **no** crea un segundo retiro
- Y muestra el estado del retiro ya registrado (recuperado por `clientWithdrawalId` o del listado de retiros), sin duplicar el importe (RN-13)

### Escenario 16 (borde): depósito PENDIENTE descartado por reorg [AT-10-06-16]
- Dado un depósito previamente mostrado como `PENDIENTE n/12` con identidad `(txHash, logIndex)`
- Cuando un re-poll de `GET /deposits` lo devuelve con `status = "DESCARTADO"` y `discardReason = "REORG"` (o `"REVERTED"`) (RN-12, épica 07)
- Entonces el cliente lo muestra como **descartado** con su `(txHash, logIndex)` y la causa
- Y el balance disponible **no cambia** (el monto nunca se había acreditado: no hay retroceso de saldo), sin tratar el descarte como inconsistencia; un depósito `ACREDITADO` es terminal y nunca se revierte (HU-07-04 RN-10)

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-*) pasan
- [ ] Reglas de negocio RN-1..RN-13 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md)
- [ ] Adherencia verificada a los estandares on-chain citados (EIP-55, EIP-155, Sepolia chainId 11155111, 12 confirmaciones)
