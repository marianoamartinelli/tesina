# HU-10-06 — Depósitos y retiros

- **Epica:** 10 — Cliente Web (React)
- **Actor / rol:** Trader autenticado operando la web
- **Prioridad:** Alta
- **Dependencias:** HU de épica 09 (endpoints de dirección de depósito, alta de retiro, estado de depósitos/retiros y canal WebSocket); épica 06 (derivación de dirección); épica 07 (depósitos/confirmaciones); épica 08 (retiros, firma EIP-155, nonce). Fundaciones (00).
- **Estandares de dominio aplicables:** **EIP-55** (checksum de dirección), **EIP-155** (firma con `chainId`), **Sepolia chainId 11155111**, confirmaciones requeridas = **12**, coin type BIP-44 = 60. (La derivación BIP-32/39/44 ocurre en backend; el cliente la consume.)

## Historia
Como trader autenticado, quiero ver mi dirección de depósito y solicitar retiros mediante un formulario con validaciones, para ingresar fondos al exchange y sacarlos a una dirección externa, siguiendo el estado de cada operación on-chain.

## Contexto y alcance
Cubre dos flujos del cliente React sobre **Sepolia (chainId 11155111)**: (1) **Depósitos** — mostrar la dirección de depósito de la cuenta (ETH nativo y USDC-mock ERC-20 a la misma dirección controlada por el exchange), permitir copiarla y seguir el estado de cada depósito (pendiente → confirmando n/12 → acreditado); (2) **Retiros** — formulario con activo, dirección destino y monto, con validaciones de cliente y seguimiento de estado (solicitado → firmado/broadcast → confirmaciones → confirmado). La derivación de claves, la firma EIP-155, el manejo de nonce y la detección/acreditación de depósitos ocurren en el backend (épicas 06–08); el cliente solo consume la API y presenta estados (RNE-2, RNE-8). El **código QR** de la dirección de depósito queda **fuera de alcance** (no se evalúa).

## Reglas de negocio e invariantes
1. **RN-1 (dirección de depósito).** El cliente obtiene y muestra la dirección de depósito de la cuenta como `0x` + 40 hex con **checksum EIP-55**. Ofrece copiar al portapapeles. Advierte que la red es **Sepolia (chainId 11155111)** y que solo se aceptan ETH y el USDC-mock del proyecto (envíos de otras redes/activos no se acreditan). *(El código QR de la dirección queda **fuera de alcance** de esta HU; ver "Contexto y alcance".)*
2. **RN-2 (idempotencia visible de depósitos — INV-5).** Un depósito se identifica por `(txHash, logIndex)` (ERC-20) o `(txHash, 0)` (ETH nativo) y se acredita **a lo sumo una vez**, solo tras **12 confirmaciones**. El cliente muestra cada depósito una sola vez; si recibe el mismo evento repetido, no lo duplica ni lo re-suma.
3. **RN-3 (seguimiento de confirmaciones de depósito).** Para cada depósito detectado, el cliente muestra el estado: `PENDIENTE` (visto, < 12 confirmaciones, indicando `n/12`), `ACREDITADO` (≥ 12 confirmaciones y crédito aplicado). El progreso `n/12` proviene de la API; el cliente no acredita por su cuenta.
4. **RN-4 (validación de dirección destino — EIP-55).** En el retiro, la dirección destino debe ser `0x` + 40 caracteres hexadecimales con **checksum EIP-55 válido**. Si no, el cliente bloquea el envío anticipando `INVALID_ADDRESS`; de llegar al backend, este responde `INVALID_ADDRESS` (422).
5. **RN-5 (monto de retiro — sin floats, RNE-1).** El monto se convierte de humano a unidad mínima por desplazamiento de coma sobre string (ETH 18 dec; USDC 6 dec) y se envía como string `^(0|[1-9][0-9]*)$`. Debe ser **positivo** y respetar la unidad mínima del activo; si no, se anticipa `WITHDRAWAL_AMOUNT_INVALID`.
6. **RN-6 (mínimo de retiro).** El monto debe ser `≥` el mínimo de retiro del activo. El cliente obtiene los parámetros de retiro (`minWithdrawal` por activo) desde el **endpoint de configuración de activos/retiros de la épica 09**, al montar la vista de retiros o en la carga inicial, y **muestra el mínimo** junto al campo de monto. **Valores de referencia (definidos por la épica 08; contrato de evaluación):** ETH = `0.01` ETH = `"10000000000000000"` wei (10^16); USDC = `10` USDC = `"10000000"` USDC-min (10^7). Si el monto es menor, el cliente lo anticipa como `WITHDRAWAL_BELOW_MIN`; ante la respuesta del servidor, muestra el mínimo formateado desde `details.minWithdrawal`. *(Si la épica 09 aún no expone el endpoint de configuración, se añade como dependencia.)*
7. **RN-7 (fondos suficientes — INV-2).** El monto a retirar más, si aplica, su costo, no puede exceder el disponible (HU-10-05). El cliente advierte si excede el disponible, pero el rechazo autoritativo es `INSUFFICIENT_FUNDS` (422) del servidor (RNE-2).
8. **RN-8 (seguimiento de retiro — EIP-155).** Tras solicitar el retiro, el cliente muestra su ciclo de estados positivo: `SOLICITADO` → `FIRMADO/BROADCAST` → `CONFIRMANDO (n/12)` → `CONFIRMADO`. Además existe un estado terminal de error **`FALLIDO`**, alcanzable desde cualquier estado intermedio cuando: (a) la transacción on-chain revierte (out-of-gas, revert del contrato ERC-20); (b) la transacción no se incluye en un plazo razonable (timeout de inclusión); o (c) una reorg saca la tx del bloque canónico antes de las 12 confirmaciones. El backend notifica `FALLIDO` por WebSocket con la causa en `details`. Al recibirlo, el cliente: muestra un mensaje claro con la causa; **antes** de habilitar el reintento, confirma que el `disponible` fue restaurado (refrescando balances, HU-10-05); y habilita reintentar el **mismo** retiro (RN-13), sin dejar la UI colgada en `CONFIRMANDO`. Cuando la API expone el `txHash`, el cliente lo muestra (enlazable a un explorer de Sepolia) y rotula la red **chainId 11155111**. El cliente no firma ni construye transacciones.
9. **RN-9 (errores on-chain por `code` — RNE-3).** El cliente mapea por `code`: `INVALID_ADDRESS`, `WITHDRAWAL_AMOUNT_INVALID`, `WITHDRAWAL_BELOW_MIN`, `INSUFFICIENT_FUNDS`, `CHAIN_ID_MISMATCH` (la red de la operación no es 11155111), `NONCE_CONFLICT` (conflicto de nonce al construir/broadcastear: el cliente **no reintenta automáticamente** y muestra el retiro como fallido pendiente de acción del usuario), `BROADCAST_FAILED` (502: el backend recibió y **registró** el retiro pero el nodo rechazó el broadcast). Ante `BROADCAST_FAILED` el cliente **no crea un nuevo retiro**: el reintento es sobre el **mismo** retiro ya registrado (usa el `withdrawalId` devuelto por el backend; si la respuesta original se perdió, lo recupera del listado de retiros antes de reintentar; ver RN-13). Cada error se muestra con mensaje claro y `details` cuando aporta (montos como string).
10. **RN-10 (anti doble submit).** Mientras una solicitud de retiro está en curso, el botón se deshabilita para evitar enviar dos retiros idénticos por doble clic.
11. **RN-11 (red única — RNE-8).** Toda la UX on-chain refiere exclusivamente a **Sepolia (chainId 11155111)**; no se ofrecen otras redes ni se permite seleccionar chainId.
12. **RN-12 (depósito revertido por reorg — RNE-10).** El cliente nunca asume que un depósito `ACREDITADO` es permanente. Si el backend revierte un crédito a raíz de una reorg, emite un evento de reversión por WebSocket; el cliente muestra ese depósito como **`REVERTIDO`** con su `(txHash, logIndex)` y aplica el nuevo balance informado por el servidor (HU-10-05), **sin** tratar la baja como inconsistencia ni resincronizar. El cliente sigue siempre al servidor como fuente de verdad (RNE-2).
13. **RN-13 (idempotencia de retiro — análoga a RNE-7).** Cada intento lógico de retiro genera un `clientWithdrawalId` (UUID v4) al abrir el formulario o en el primer envío, y se **reutiliza** en reintentos del mismo flujo (timeout/red). El cliente lo incluye en el payload. Si el backend responde `CONFLICT` (409) porque ya existe un retiro con ese `clientWithdrawalId` para la cuenta, el cliente **no crea un segundo retiro**: muestra el estado del retiro ya registrado (recuperándolo por `clientWithdrawalId` o del listado de retiros). El backend devuelve el `withdrawalId` del retiro creado; el cliente lo conserva para el seguimiento y para el reintento de broadcast (RN-9). Esto cubre el caso en que el request llega al backend, el retiro se crea y la respuesta se pierde por timeout: un segundo intento **no** genera un segundo retiro por el mismo importe. (RN-10 previene solo el doble clic; RN-13 cubre además la falla de red.)

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
- Dado un depósito ya `ACREDITADO` con identidad `(txHash, logIndex)`
- Cuando el canal WebSocket de depósitos envía dos veces el mismo evento con `txHash` y `logIndex` idénticos
- Entonces lo muestra una sola vez (no duplica la fila ni vuelve a sumar el monto)
- Y, si el backend reporta `DEPOSIT_ALREADY_CREDITED` (409), no altera balances en la UI

### Escenario 4: Retiro válido y seguimiento de estado [AT-10-06-04]
- Dado un trader con disponible suficiente
- Y un formulario de retiro USDC, dirección destino con checksum EIP-55 válido, monto `25` USDC
- Cuando solicita el retiro
- Entonces el cliente envía `amountUsdcMin="25000000"`, la dirección destino y un `clientWithdrawalId` (RN-13) al endpoint de retiro
- Y muestra el ciclo `SOLICITADO` → `FIRMADO/BROADCAST` → `CONFIRMANDO (n/12)` → `CONFIRMADO`
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
- Dado un retiro de USDC por `5000000` (5 USDC), menor al mínimo de `10000000` (10 USDC) (RN-6)
- Cuando el usuario intenta retirar, el cliente lo anticipa como `WITHDRAWAL_BELOW_MIN` y, de llegar al backend, la API responde `{ error: { code: "WITHDRAWAL_BELOW_MIN", details: { asset: "USDC", amount: "5000000", minWithdrawal: "10000000" } } }` (422)
- Entonces el cliente informa el mínimo requerido (10 USDC) formateado desde `minWithdrawal`

### Escenario 8 (error): fondos insuficientes para retirar [AT-10-06-08]
- Dado un monto mayor al disponible del activo
- Cuando la API responde `{ error: { code: "INSUFFICIENT_FUNDS", details: { asset, required, available } } }` (422)
- Entonces el cliente muestra el faltante y no altera balances en la UI (INV-2)

### Escenario 9 (error): broadcast rechazado por el nodo [AT-10-06-09]
- Dado un retiro ya **registrado** por el backend (con `withdrawalId` conocido) que no pudo broadcastearse
- Cuando el backend responde `{ error: { code: "BROADCAST_FAILED", details: { reason } } }` (502)
- Entonces el cliente informa que el envío on-chain falló
- Y el reintento se hace sobre el **mismo** retiro (usando el `withdrawalId` ya devuelto), **sin** crear uno nuevo (RN-9)
- Y si no dispusiera del `withdrawalId` (respuesta original perdida), primero lo recupera del listado de retiros antes de reintentar

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
- Entonces el cliente envía `amountWei="100000000000000000"` (18 decimales) y un `clientWithdrawalId`
- Y el ciclo de estados `SOLICITADO` → `FIRMADO/BROADCAST` → `CONFIRMANDO (n/12)` → `CONFIRMADO` se muestra igual que para USDC

### Escenario 13 (error): retiro FALLIDO y reintento tras restaurar disponible [AT-10-06-13]
- Dado un retiro en estado `CONFIRMANDO`
- Cuando el backend notifica por WebSocket el estado `FALLIDO` con la causa en `details` (revert on-chain, timeout de inclusión o reorg)
- Entonces el cliente muestra `FALLIDO` con un mensaje claro de la causa
- Y antes de habilitar el reintento confirma que el `disponible` fue restaurado (refrescando balances, HU-10-05)
- Y habilita reintentar el **mismo** retiro (RN-8/RN-13), sin dejar la UI colgada en `CONFIRMANDO`

### Escenario 14 (error): conflicto de nonce durante el retiro [AT-10-06-14]
- Dado un retiro aceptado en validación
- Cuando el backend responde `{ error: { code: "NONCE_CONFLICT", details: { address, nonce } } }` (409)
- Entonces el cliente muestra un mensaje informativo **sin reintentar automáticamente**
- Y el retiro se muestra como fallido pendiente de acción del usuario (RN-9)

### Escenario 15 (idempotencia/concurrencia): reintento de retiro reutiliza clientWithdrawalId [AT-10-06-15]
- Dado una solicitud de retiro enviada con `clientWithdrawalId` cuyo resultado no llegó (timeout de red)
- Cuando el cliente reintenta el **mismo** retiro con el **mismo** `clientWithdrawalId`
- Y la API responde `{ error: { code: "CONFLICT", details: { reason } } }` (409) por `clientWithdrawalId` ya registrado
- Entonces el cliente **no** crea un segundo retiro
- Y muestra el estado del retiro ya registrado (recuperado por `clientWithdrawalId` o del listado de retiros), sin duplicar el importe (RN-13)

### Escenario 16 (borde): depósito ACREDITADO revertido por reorg [AT-10-06-16]
- Dado un depósito previamente mostrado como `ACREDITADO` con identidad `(txHash, logIndex)`
- Cuando el backend emite por WebSocket un evento de reversión por reorg (RNE-10)
- Entonces el cliente muestra ese depósito como `REVERTIDO` con su `(txHash, logIndex)`
- Y aplica el nuevo balance informado por el servidor (HU-10-05), sin tratar la baja como inconsistencia ni resincronizar por aparente violación de invariantes

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-*) pasan
- [ ] Reglas de negocio RN-1..RN-13 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md)
- [ ] Adherencia verificada a los estandares on-chain citados (EIP-55, EIP-155, Sepolia chainId 11155111, 12 confirmaciones)
