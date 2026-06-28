# HU-11-06 — Depósitos y retiros en mobile

- **Epica:** 11 — Cliente Mobile (React Native / Expo)
- **Actor / rol:** Trader autenticado
- **Prioridad:** Alta
- **Dependencias:** HU-10-06 (paridad web: depósitos y retiros), épica 09 (endpoints de
  dirección de depósito, solicitud de retiro y seguimiento), épica 06 (wallet HD y
  direcciones), épica 07 (depósitos on-chain), épica 08 (retiros on-chain), HU-11-01 (sesión)
- **Estandares de dominio aplicables:** BIP-32 / BIP-39 / BIP-44 (coin type **60**, path
  `m / 44' / 60' / account' / change / address_index` con índices hardened) para la
  dirección de depósito derivada por el backend; **EIP-55** (checksum de dirección) para
  validar el destino de retiro; **EIP-155** (firma con `chainId`) para la transacción de
  retiro; red **Sepolia** (`chainId = 11155111`); confirmaciones requeridas = **12**.

## Historia
Como trader autenticado, quiero ver mi **dirección de depósito** (con **QR**) y solicitar
**retiros** desde la app mobile con validaciones y **seguimiento del estado on-chain**, para
mover mis fondos desde el celular de forma segura.

## Contexto y alcance
Cubre dos flujos:
- **Depósito:** mostrar la dirección de depósito de la cuenta (derivada por la épica 06,
  BIP-32/39/44, coin type 60) como texto y **QR**, con opción de **copiar**; y el
  **seguimiento** de depósitos entrantes con sus confirmaciones (12) hasta la acreditación
  (épica 07).
- **Retiro:** formulario de destino + monto con validación de dirección (**EIP-55**), mínimo
  de retiro y unidad mínima del activo; envío a la API (épica 09), que dispara la épica 08
  (firma **EIP-155** con `chainId = 11155111`, gestión de nonce, broadcast); y **seguimiento**
  del estado del retiro (incluido `txHash`).

El contrato es **el mismo que el web** (HU-10-06). Diferencias mobile: presentación del QR,
**escaneo de QR** de la dirección destino con la cámara (con permisos), portapapeles y
seguimiento in-app. **El cliente NO firma transacciones, NO maneja claves privadas ni la
mnemonic**: sólo consume la API. La validación on-chain autoritativa la hace el backend.

## Reglas de negocio e invariantes
1. **RN-1 (origen de la dirección de depósito):** la dirección mostrada es la asignada a la
   cuenta por la épica 06 (HD wallet BIP-32/39/44, coin type 60, path
   `m / 44' / 60' / account' / change / address_index` con índices hardened en los niveles
   correspondientes). El cliente la **obtiene de la API** (épica 09); **no** la deriva
   localmente ni accede a la seed/mnemonic.
2. **RN-2 (presentación del depósito):** la dirección se muestra como texto (`0x` + 40 hex
   con checksum **EIP-55**) y como **código QR**, con acción de **copiar** al portapapeles.
   Se indica la red **Sepolia** (`chainId = 11155111`) y el activo. **Una única** dirección
   Ethereum (BIP-44, coin type 60) recibe **tanto ETH nativo como USDC-mock ERC-20** (a la
   misma dirección controlada por el exchange, paridad con HU-10-06); la diferencia entre
   activos la determina el tipo de transacción on-chain, **no** la dirección. **Formato del
   QR (EIP-681):** para que las wallets externas no envíen el activo o la red equivocados, el
   QR se genera como URI EIP-681: para **ETH nativo** `ethereum:<depositAddress>@11155111`;
   para **USDC-mock** `ethereum:<USDC_CONTRACT_ADDRESS>@11155111/transfer?address=<depositAddress>`
   (la dirección del contrato USDC-mock se obtiene de la API junto a la dirección de
   depósito; es configuración por entorno, no un literal). Siempre se muestra **además** el
   address en texto con checksum EIP-55 como respaldo para wallets que no soporten EIP-681.
3. **RN-3 (seguimiento y confirmaciones, INV-5):** un depósito entrante muestra
   confirmaciones actuales vs. requeridas (**12**). El backend acredita **sólo** tras 12
   confirmaciones; hasta entonces figura **pendiente** (no acreditado). El cliente refleja el
   estado provisto (incluido `DEPOSIT_NOT_CONFIRMED`); **no** acredita por su cuenta.
   **Mecanismo de actualización en tiempo real:** la **acreditación** del depósito (aumento
   de `disponible`) llega por el canal WebSocket **`balances`** de la épica 09 (HU-09-04
   RN-6), sin acción del usuario. El **progreso de confirmaciones** `X/12` proviene de la
   API REST (`GET /deposits`, épica 07/09): como la épica 09 no define un evento WS dedicado
   a confirmaciones de depósito, el cliente hace **polling periódico** (p. ej. cada **15 s**)
   mientras la pantalla está en **foreground**, y **fuerza un refetch al volver a
   foreground**; en background no consulta (RG-5). El pull-to-refresh también lo fuerza.
4. **RN-4 (idempotencia de depósito, INV-5):** un mismo `(txHash, logIndex)` se acredita **a
   lo sumo una vez**; el cliente muestra el estado del backend sin contar dos veces el mismo
   depósito.
5. **RN-5 (validación de dirección de retiro, EIP-55):** el destino debe ser `0x` + 40
   caracteres hex con **checksum EIP-55 válido**; si no, el backend responde `INVALID_ADDRESS`
   (422). El cliente valida formato y checksum EIP-55 como feedback temprano, pero el backend
   es autoritativo.
6. **RN-6 (validación de monto de retiro):** el monto va en unidad mínima entera (string,
   `^(0|[1-9][0-9]*)$`), `> 0` y múltiplo de la unidad mínima del activo; si no ⇒
   `WITHDRAWAL_AMOUNT_INVALID` (422). Debe ser `≥` **mínimo de retiro del activo**; si no ⇒
   `WITHDRAWAL_BELOW_MIN` (422). Los mínimos (épica 08, HU-08-01 RN-7) son
   **`MIN_WITHDRAWAL_ETH = 1000000000000000` wei (0.001 ETH)** y
   **`MIN_WITHDRAWAL_USDC = 1000000` USDC-min (1 USDC)**. Debe haber `disponible` suficiente;
   si no ⇒ `INSUFFICIENT_FUNDS` (422). La conversión humano→unidad mínima es exacta, **sin
   floats**. El cliente conoce los mínimos para feedback temprano cargándolos de un endpoint
   de configuración de la épica 09 si existe; si no, usa estos valores constantes (la
   validación autoritativa la hace el backend).
7. **RN-7 (el retiro on-chain lo ejecuta el backend, INV-6):** la épica 08 firma con
   **EIP-155** y `chainId = 11155111`, usa un **nonce único y secuencial** por dirección
   emisora y hace el broadcast. El cliente **no** firma ni arma la transacción. Códigos del
   backend a manejar además de los de validación: `CHAIN_ID_MISMATCH` (422), `NONCE_CONFLICT`
   (409), `BROADCAST_FAILED` (502).
8. **RN-8 (seguimiento del retiro):** la UI muestra el estado del retiro usando el **enum
   canónico** de la épica 08 (HU-08-04) / contrato REST de la épica 09 (HU-09-01 RN-11):
   **`PENDING` → `BROADCAST` → `CONFIRMED`**, con la rama terminal **`FAILED`**. La UI mapea
   cada estado a una etiqueta legible (p. ej. `PENDING` = "solicitado/firmando",
   `BROADCAST` = "broadcasteado (n/12)", `CONFIRMED` = "confirmado", `FAILED` = "fallido") y,
   cuando exista, muestra el `txHash` con enlace al explorer de **Sepolia**. `CONFIRMED` y
   `FAILED` son **terminales**; la finalización (`CONFIRMED`) requiere **12** confirmaciones.
   Ante **`FAILED`**, la UI indica que el retiro **no se completará** y que los fondos
   bloqueados se **liberan** por reconciliación del backend (épica 08; el `disponible` vuelve
   a subir vía evento `balances`), sin que el cliente recalcule nada. **Mecanismo de
   actualización:** el estado proviene de la API REST (`GET /withdrawals/{withdrawalId}`); si
   la épica 09 expone un canal privado `withdrawals` (RG-API-7), el cliente se suscribe; si
   no, hace **polling periódico** (p. ej. cada **15 s**) en foreground y **refetch al volver
   a foreground** (RG-5). El cambio de `disponible`/`bloqueado` llega por el canal
   `balances`.
9. **RN-9 (escaneo de QR, diferencia mobile):** al escanear un QR de dirección con la cámara
   se rellena el campo destino. El contenido del QR se interpreta así:
   - **URI EIP-681** (`ethereum:<address>[@<chainId>][/...][?params]`): el cliente **extrae
     el address** del prefijo `ethereum:` (descartando `/transfer`, parámetros, etc.). Si el
     URI incluye `@chainId`, **valida que sea `11155111`** (Sepolia); si difiere (p. ej.
     `@1` = mainnet), muestra un error explícito ("Red incorrecta: el QR corresponde a otra
     red, no a Sepolia") y **no** rellena el campo.
   - **Address plano** (`0x` + 40 hex): se valida sólo con **EIP-55** (RN-5).
   - **Contenido que no es una dirección Ethereum válida** (URL, texto arbitrario, código de
     barras): la UI informa que el QR no contiene una dirección válida, **no** modifica el
     campo destino y permite reintentar o ingresar la dirección manualmente.
   En todos los casos el address resultante se valida con EIP-55 antes de permitir el envío.
   Requiere permiso de cámara.
10. **RN-10 (confirmación, gas y anti doble-envío):** se requiere confirmación explícita del
    retiro antes de enviar; el botón se deshabilita mientras hay un request en vuelo. El
    **modal de confirmación** muestra: activo y monto a retirar; dirección destino; red
    (**Sepolia**); y la **fee de red estimada en ETH** (`fee_red_wei = gas_limit ×
    gas_price_wei`, con `gas_limit = 21000` para ETH y `100000` para USDC; HU-08-01 RN-8),
    obtenida de la API o estimación configurable. **El gas siempre se paga en ETH,
    independientemente del activo retirado**: para retiros de **USDC-mock** el modal incluye
    una **advertencia explícita** de que se requiere **ETH disponible para el gas**, evitando
    un `INSUFFICIENT_FUNDS` con `asset = ETH` no anticipado.
11. **RN-11 (sesión):** ante `UNAUTHENTICATED` (401), limpia la sesión y redirige al login
    (flujo singleton RG-8).
12. **RN-12 (secreto):** el cliente **nunca** muestra ni solicita la mnemonic, la seed ni
    claves privadas; esos secretos no salen del backend.
13. **RN-13 (idempotencia y persistencia del retiro — `clientWithdrawalId`):** el cliente
    genera un `clientWithdrawalId` (UUID v4) por intento de retiro y lo **persiste** junto al
    *withdrawal intent* (`asset`, `amount`, `address`) en SecureStore **antes** de enviar el
    request (épica 08, HU-08-01 RN-10 soporta esta clave de idempotencia). Al recibir una
    respuesta exitosa o un error **definitivo**, borra el registro. Si al abrir la app existe
    un `clientWithdrawalId` **pendiente** (la app fue terminada entre el envío y la
    respuesta), lo **reutiliza** al reintentar. Reenviar con la **misma** clave y **mismos**
    parámetros devuelve el **mismo** retiro (idempotente, sin doble bloqueo); con
    **parámetros distintos** el backend responde `CONFLICT` (409). Análogo al patrón de
    `clientOrderId` en HU-11-03 RN-4.
14. **RN-14 (`DEPOSIT_ALREADY_CREDITED`):** si el backend responde `DEPOSIT_ALREADY_CREDITED`
    (409) con `details {txHash, logIndex}` ante una consulta o reproceso de un depósito ya
    acreditado (idempotencia, INV-5), la UI lo trata como **estado informativo no
    destructivo**: muestra el depósito como **acreditado**, **no** suma el monto por segunda
    vez y **no** lo presenta como error al usuario.

## Criterios de aceptación (DoD)

### Escenario 1: Mostrar dirección de depósito con QR [AT-11-06-01]
- Dado un trader autenticado en la pantalla de depósito
- Cuando la app obtiene su dirección de depósito de la API (épica 09)
- Entonces muestra la dirección (`0x` + 40 hex, checksum EIP-55), su **QR** y la opción de
  copiar
- Y aclara que la red es Sepolia (`chainId = 11155111`) y el activo correspondiente

### Escenario 2: Seguimiento de un depósito hasta acreditación [AT-11-06-02]
- Dado un depósito entrante observado por el backend
- Cuando aún tiene menos de 12 confirmaciones
- Entonces la UI lo muestra como **pendiente** con `X/12` confirmaciones, obtenidas por
  polling REST en foreground (cada ~15 s) y/o pull-to-refresh (RN-3)
- Y cuando alcanza 12 confirmaciones y el backend lo acredita, la UI lo muestra como
  **acreditado** al recibir el evento del canal WebSocket `balances` (HU-09-04 RN-6), sin
  acción del usuario; si la app estaba en background, el estado acreditado se refleja al
  volver a foreground (resync de balances, HU-11-05)

### Escenario 3 (borde): Depósito sin confirmaciones suficientes [AT-11-06-03]
- Dado un depósito con menos de 12 confirmaciones
- Cuando el cliente consulta su estado
- Entonces el backend lo reporta como no acreditado (`DEPOSIT_NOT_CONFIRMED` o estado
  pendiente equivalente)
- Y la UI no suma ese monto al balance disponible

### Escenario 4 (idempotencia): Mismo depósito no se cuenta dos veces [AT-11-06-04]
- Dado un depósito identificado por `(txHash, logIndex)` ya acreditado
- Cuando el backend reprocesa/observa nuevamente el mismo evento
- Entonces la acreditación no se repite (INV-5) y la UI sigue mostrando un único depósito
  acreditado

### Escenario 5: Retiro válido aceptado y en seguimiento [AT-11-06-05]
- Dado un trader con `disponible` suficiente
- Cuando solicita un retiro con dirección destino válida (EIP-55) y monto válido, y confirma
- Entonces el backend acepta la solicitud (épica 08: firma EIP-155 con `chainId = 11155111`)
- Y la UI muestra el retiro en seguimiento y, cuando exista, el `txHash` con enlace al
  explorer de Sepolia

### Escenario 6 (error): Dirección destino inválida (EIP-55) [AT-11-06-06]
- Dado un destino con checksum EIP-55 incorrecto o que no es `0x` + 40 hex
- Cuando el trader intenta retirar
- Entonces el cliente lo marca como dirección inválida (feedback temprano)
- Y el backend, de recibirla, responde `INVALID_ADDRESS` (422) con `details {address}`

### Escenario 7 (error): Monto de retiro inválido [AT-11-06-07]
- Dado un monto no positivo o que no respeta la unidad mínima del activo
- Cuando se solicita el retiro
- Entonces el backend responde `WITHDRAWAL_AMOUNT_INVALID` (422) y la UI lo informa

### Escenario 8 (error): Monto por debajo del mínimo de retiro [AT-11-06-08]
- Dado un retiro de ETH con `amount = "999999999999999"` (1 wei por debajo de
  `MIN_WITHDRAWAL_ETH = 1000000000000000` = 0.001 ETH) — análogamente, USDC con
  `amount = "999999"` por debajo de `MIN_WITHDRAWAL_USDC = 1000000` = 1 USDC (HU-08-01 RN-7)
- Cuando se solicita el retiro
- Entonces el backend responde `WITHDRAWAL_BELOW_MIN` (422) con
  `details {asset, amount, minWithdrawal}` (p. ej. `minWithdrawal = "1000000000000000"`) y la
  UI lo informa
- Y el cliente puede marcarlo como feedback temprano antes de enviar (RN-6)

### Escenario 9 (error): Fondos insuficientes para retirar [AT-11-06-09]
- Dado un monto válido mayor al `disponible`
- Cuando se solicita el retiro
- Entonces el backend responde `INSUFFICIENT_FUNDS` (422) con `details {asset, required,
  available}`
- Y la UI muestra esos montos formateados a humano

### Escenario 10 (error): chainId incorrecto [AT-11-06-10]
- Dado que el **backend** detecta que la transacción de retiro no corresponde a
  `chainId = 11155111` (la construcción/firma on-chain es responsabilidad del backend, RN-7)
  y responde `CHAIN_ID_MISMATCH` (422) con `details {expected, got}`
- Cuando el **cliente recibe** esa respuesta
- Entonces la UI lo informa con el `code` devuelto (el cliente no firma ni arma la tx)

### Escenario 11 (error): Conflicto de nonce [AT-11-06-11]
- Dado que el **backend** detecta un conflicto de nonce al construir/broadcastear el retiro
  (nonce ya usado o fuera de secuencia, RN-7) y responde `NONCE_CONFLICT` (409) con
  `details {address, nonce}`
- Cuando el **cliente recibe** esa respuesta
- Entonces la UI lo informa con el `code` devuelto (el cliente no gestiona nonces)

### Escenario 12 (error): Broadcast fallido [AT-11-06-12]
- Dado un retiro cuya transacción es rechazada por el nodo al broadcastear
- Cuando ocurre el fallo
- Entonces el backend responde `BROADCAST_FAILED` (502) con `details {reason}`
- Y la UI lo informa como reintentable (sin duplicar el retiro)

### Escenario 13: Escanear QR rellena el destino [AT-11-06-13]
- Dado el formulario de retiro y permiso de cámara concedido
- Cuando el usuario escanea un QR con una dirección Ethereum (address plano o URI EIP-681
  `ethereum:0x...@11155111`)
- Entonces el cliente extrae el address (RN-9) y rellena el campo destino
- Y se valida con EIP-55 antes de permitir el envío

### Escenario 14 (borde): Permiso de cámara denegado [AT-11-06-14]
- Dado que el usuario deniega el permiso de cámara
- Cuando intenta escanear un QR
- Entonces la UI informa la falta de permiso y permite el **ingreso manual** de la dirección

### Escenario 15 (concurrencia): Doble tap en retirar [AT-11-06-15]
- Dado un formulario de retiro válido y confirmado
- Cuando el usuario toca "Retirar" dos veces rápidamente
- Entonces se envía un único request (botón deshabilitado durante el request en vuelo)
- Y no se crean dos retiros

### Escenario 16 (borde): Conversión exacta del monto sin floats [AT-11-06-16]
- Dado un monto humano `0.5` USDC
- Cuando el cliente lo convierte a unidad mínima
- Entonces envía `"500000"` como string entero (sin floats binarios)

### Escenario 17 (seguridad): No se exponen secretos [AT-11-06-17]
- Dado cualquier pantalla de depósito o retiro
- Cuando se ejercitan las pantallas y la API consumida, con verificaciones automatizables:
- Entonces (a) **test de contrato**: ningún endpoint de la épica 09 consumido incluye campos
  de `mnemonic`/`seed`/`privateKey` en su request o response;
- Y (b) **test de render/snapshot**: ningún componente de depósito/retiro renderiza
  elementos con frases de 12/24 palabras mnemónicas ni claves privadas;
- Y (c) **spy de red**: los requests salientes no contienen campos de mnemonic/seed/clave
  privada (se distingue lo verificado en el cliente de lo garantizado por el contrato de API)

### Escenario 18 (error): Token expirado [AT-11-06-18]
- Dado un trader cuyo token expiró
- Cuando una petición de depósito o retiro recibe `UNAUTHENTICATED` (401)
- Entonces la app limpia la sesión y redirige al login

### Escenario 19 (error): QR con red incorrecta (mainnet) es rechazado [AT-11-06-19]
- Dado el formulario de retiro y permiso de cámara concedido
- Cuando el usuario escanea un QR EIP-681 con chainId de mainnet (`ethereum:0x...@1`)
- Entonces la UI muestra un error explícito de **red incorrecta** (no es Sepolia, RN-9)
- Y el campo destino **no** se modifica

### Escenario 20 (borde): QR con contenido inválido [AT-11-06-20]
- Dado el formulario de retiro y permiso de cámara concedido
- Cuando el usuario escanea un QR cuyo contenido **no** es una dirección Ethereum válida
  (URL, texto arbitrario, código de barras; no cumple `0x` + 40 hex EIP-55)
- Entonces la UI indica que el QR no contiene una dirección válida (RN-9)
- Y el campo destino no se modifica y el usuario puede reintentar o ingresar manualmente

### Escenario 21 (borde): Gas en el modal de retiro de USDC [AT-11-06-21]
- Dado un retiro de **USDC-mock** con `disponible(USDC)` suficiente pero **sin ETH**
  suficiente para el gas
- Cuando se abre el modal de confirmación del retiro
- Entonces el modal muestra el activo, monto, destino, red Sepolia y la **fee de red
  estimada en ETH** (`fee_red_wei`), con una **advertencia explícita** de que se requiere ETH
  para el gas, **antes** de que el usuario confirme (RN-10)
- Y si el usuario confirma igualmente, el backend responde `INSUFFICIENT_FUNDS` con
  `details.asset = "ETH"` (HU-08-01 RN-9) y la UI lo informa

### Escenario 22 (idempotencia/recuperación): clientWithdrawalId persistido y crash [AT-11-06-22]
- Dado un *withdrawal intent* con `clientWithdrawalId` persistido en SecureStore antes del
  envío (RN-13)
- Cuando el SO termina la app después de enviar pero antes de recibir respuesta, y el usuario
  reabre la app
- Entonces el cliente detecta el `clientWithdrawalId` pendiente y reintenta con la **misma**
  clave y **mismos** parámetros
- Y el backend devuelve el **mismo** retiro (idempotente, sin doble bloqueo); si los
  parámetros difirieran, responde `CONFLICT` (409) y la UI lo informa; luego limpia el registro

### Escenario 23 (idempotencia depósito): DEPOSIT_ALREADY_CREDITED [AT-11-06-23]
- Dado un depósito ya acreditado identificado por `(txHash, logIndex)`
- Cuando el backend responde `DEPOSIT_ALREADY_CREDITED` (409) con `details {txHash, logIndex}`
  ante una consulta o reproceso
- Entonces la UI muestra el depósito en estado **acreditado**, **no** suma el monto por
  segunda vez y **no** lo presenta como error (RN-14, INV-5)

### Escenario 24 (seguimiento): Retiro que pasa a FAILED [AT-11-06-24]
- Dado un retiro en seguimiento que el backend reconcilia como **`FAILED`** (épica 08)
- Cuando el cliente recibe el estado `FAILED`
- Entonces la UI lo muestra como **fallido** (no se completará) usando el enum canónico (RN-8)
- Y refleja la **liberación** de los fondos bloqueados (el `disponible` vuelve a subir vía
  evento `balances`), sin recalcular nada por su cuenta

### Escenario 25 (error): Fallo de red al solicitar el retiro [AT-11-06-25]
- Dado un formulario de retiro válido y confirmado, y el backend caído o sin conectividad
- Cuando la petición `POST /withdrawals` no obtiene respuesta (fallo de red)
- Entonces la UI muestra un error de conectividad (distinto de los errores de negocio)
- Y el estado local no cambia; el reintento reusa el **mismo** `clientWithdrawalId` (RN-13)
  para no duplicar el retiro

### Escenario 26 (depósito): QR EIP-681 de USDC-mock [AT-11-06-26]
- Dado la pantalla de depósito para **USDC-mock** con la dirección y la dirección del
  contrato USDC obtenidas de la API
- Cuando se genera el QR
- Entonces el QR codifica el URI EIP-681
  `ethereum:<USDC_CONTRACT_ADDRESS>@11155111/transfer?address=<depositAddress>` (RN-2)
- Y se muestra **además** el address en texto con checksum EIP-55 como respaldo

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-*) pasan
- [ ] Reglas de negocio RN-1..RN-14 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md (incl.
      `DEPOSIT_ALREADY_CREDITED` 409 y `CONFLICT` 409 por idempotencia de retiro)
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md
- [ ] Estados del retiro según el enum canónico de épica 08/09 (`PENDING`/`BROADCAST`/
      `CONFIRMED`/`FAILED`)
- [ ] Invariantes globales: el cliente **refleja** la idempotencia de depósitos (INV-5) y el
      anti-replay EIP-155 / unicidad de nonce (INV-6), garantizados por el backend (épicas
      06–08); el cliente **no** firma, no maneja nonces ni acredita por su cuenta
      (00-fundaciones/invariantes-globales.md)
- [ ] Adherencia verificada a los estandares on-chain citados (BIP-32/39/44 coin type 60,
      EIP-55, EIP-155 con chainId 11155111, confirmaciones = 12, EIP-681 para QR)
