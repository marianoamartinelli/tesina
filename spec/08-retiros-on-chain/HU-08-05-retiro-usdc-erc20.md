# HU-08-05 — Retiro de USDC (ERC-20)

- **Epica:** 08 — Retiros On-Chain
- **Actor / rol:** Sistema (servicio de retiros) sobre la cuenta del trader; firma vía épica 06
- **Prioridad:** Alta
- **Dependencias:** HU-08-01 (solicitud), HU-08-02 (reserva dual), HU-08-03 (firma EIP-155/broadcast), HU-08-04 (confirmaciones/reconciliación), épica 06 (clave emisora), épica 02 (balances)
- **Estandares de dominio aplicables:** ERC-20 (`transfer(address,uint256)`), EIP-155 (firma con chainId 11155111), Sepolia chainId 11155111, BIP-32/39/44 (coin type 60, clave emisora vía épica 06)

## Historia
Como Sistema de retiros, quiero ejecutar un retiro de **USDC** mediante la llamada `transfer` del contrato ERC-20 USDC-mock, contemplando que el **fee de red (gas) se paga en ETH**, para enviar tokens USDC al destino del usuario reservando y reconciliando correctamente **dos activos**: el USDC del principal y el ETH del gas.

## Contexto y alcance
Esta HU especializa el flujo de retiro para el activo **USDC**, que es un **token ERC-20** (no nativo): el principal se transfiere invocando `transfer(to, amount)` del contrato USDC-mock, mientras que el **costo de gas se paga en ETH** (como toda transacción de Sepolia). Por eso la reserva (HU-08-02) y la reconciliación (HU-08-04) son **duales**: USDC para el principal y ETH para la previsión de gas. Reutiliza HU-08-01 (validación), HU-08-03 (firma EIP-155, nonce, broadcast) y HU-08-04 (confirmaciones, estados, reconciliación); aquí se fijan las **diferencias específicas** del ERC-20.

NO redefine la validación general (HU-08-01), la máquina de estados ni el conteo de confirmaciones (HU-08-04). La dirección del contrato USDC-mock es **configuración por entorno** (única y constante por entorno), no un literal de la spec.

USDC-mock tiene **6 decimales**: el `amount` del retiro está en **unidad de 6 decimales** (USDC-min) y se pasa como el `uint256` del `transfer`.

## Reglas de negocio e invariantes
1. **RN-1 (mecanismo de transferencia ERC-20):** el principal de USDC se transfiere invocando `transfer(address to, uint256 amount)` del contrato USDC-mock configurado. La transacción tiene `to = <dirección del contrato USDC-mock>`, `value = 0` (no se envía ETH como valor nativo), y `data` = el ABI-encoding de `transfer(destino_usuario, amount_usdc)` donde `destino_usuario` es la `address` validada (EIP-55) de HU-08-01 y `amount_usdc` el monto en USDC-min.
2. **RN-2 (gas en ETH):** la ejecución de `transfer` consume **gas pagado en ETH** por la dirección emisora del exchange. La previsión es `fee_red_wei = GAS_LIMIT_ERC20 × gas_price_wei = 100000 × gas_price_wei` (multiplicación entera, en wei). USDC **no** paga gas; el gas siempre se paga en ETH.
3. **RN-3 (reserva dual — HU-08-02):** al aceptar el retiro se bloquea **atómicamente** (todo o nada, INV-4): `amount_usdc` en USDC **y** `fee_red_wei` en ETH. Si falta USDC → `INSUFFICIENT_FUNDS` (`asset: "USDC"`); si alcanza USDC pero falta ETH para el gas → `INSUFFICIENT_FUNDS` (`asset: "ETH"`). No se bloquea una pata sin la otra.
4. **RN-4 (firma y broadcast — HU-08-03):** la transacción ERC-20 se firma conforme **EIP-155** con `chainId = 11155111` (INV-6) y la clave de la dirección emisora (épica 06), usando `gas_limit = GAS_LIMIT_ERC20 = 100000` y `nonce` único/secuencial/contiguo por emisora. El costo máximo `gas_limit × gas_price_wei ≤ fee_red_wei` (respaldo de gas).
5. **RN-5 (confirmación exitosa y caso `status = 1` sin `Transfer` — HU-08-04):** el retiro USDC es `CONFIRMED` sii `confirmaciones ≥ 12` **y** el receipt tiene `status = 1` **y** el evento `Transfer(from = emisora, to = destino_usuario, value = amount_usdc)` fue emitido por el **contrato USDC-mock configurado** con el monto correcto. **Si `status = 1` pero el `Transfer` esperado no se emite** (o se emite con `value`/`from`/contrato incorrectos), el retiro **NO** se confirma: se trata como `FAILED` análogo a una revert, con `gas_usado_wei = gas_usado × precio_efectivo_wei` (el gas **sí** se consumió on-chain). Reconciliación (RN-7, revertida): se **reacredita** `amount_usdc` en USDC y se **consume** `gas_usado_wei` en ETH, liberando `fee_red_wei − gas_usado_wei`. Esta regla es la misma que HU-08-04 RN-2/RN-5 (ver AT-08-05-10 y AT-08-04-11).
6. **RN-6 (reconciliación al `CONFIRMED`):** se **consume** del bloqueado `amount_usdc` en USDC (sale al destinatario) y `gas_usado_wei = gas_usado × precio_efectivo_wei` en ETH (sale al validador); se **libera** a disponible `fee_red_wei − gas_usado_wei` en ETH. La suma total de USDC disminuye en `amount_usdc`; la de ETH, en `gas_usado_wei` (HU-08-04 RN-3, HU-08-04 RN-4, INV-1).
7. **RN-7 (reconciliación al `FAILED`):**
   - tx **no minada** / broadcast definitivamente fallido: `gas_usado_wei = 0`; se libera **toda** la reserva: `amount_usdc` en USDC + `fee_red_wei` en ETH a disponible. La suma total de ambos activos **no cambia**.
   - tx **minada pero revertida** (`status = 0`, p. ej. el `transfer` revierte): el USDC **no se transfirió** ⇒ se reacredita `amount_usdc`; el **gas igualmente se consumió** ⇒ se consume `gas_usado_wei` en ETH y se libera `fee_red_wei − gas_usado_wei`. La suma total de USDC no cambia; la de ETH disminuye en `gas_usado_wei`.
8. **RN-8 (decimales y precisión):** `amount_usdc` está en **unidad de 6 decimales** (1 USDC = 10⁶); se pasa tal cual como `uint256` al `transfer`. `fee_red_wei`, `gas_usado_wei` en **wei** (18 decimales). No se mezclan unidades: USDC en USDC-min, gas en wei. Sin floats; serialización string `^(0|[1-9][0-9]*)$`.
9. **RN-9 (conservación cruzada — INV-1):** un retiro USDC afecta a **dos** activos en la conservación: reduce `total(USDC)` en `amount_usdc` (al confirmar) y `total(ETH)` en `gas_usado_wei` (gas pagado por el exchange). Ambos son `retiros_confirmados` de sus respectivos activos. Mientras `PENDING/BROADCAST`, ninguna suma total cambia (solo disponible→bloqueado en ambos activos).
10. **RN-10 (idempotencia y persistencia):** valen las mismas garantías que el flujo general: reserva una sola vez (HU-08-02), no doble firma/broadcast (HU-08-03), reconciliación a lo sumo una vez (HU-08-04), todo persistente y reconstruible (INV-8).

## Criterios de aceptación (DoD)

### Escenario 1: retiro de USDC exitoso (feliz) [AT-08-05-01]
- Dado `acc-1` con `disponible(USDC) = "50000000"` (50 USDC), `disponible(ETH) = "1000000000000000"` (0.001 ETH), `gas_price_wei = "5000000000"` (5 gwei) ⇒ `fee_red_wei = 100000 × 5000000000 = "500000000000000"`
- Cuando solicita y se procesa un retiro de `asset = USDC`, `amount = "25000000"` (25 USDC) a una `address` EIP-55 válida
- Entonces se bloquea `"25000000"` USDC y `"500000000000000"` ETH (reserva dual, RN-3); se firma `transfer(destino, "25000000")` al contrato USDC-mock con `chainId = 11155111`, `gas_limit = 100000`, `value = 0` (RN-1/RN-4)
- Y al alcanzar 12 confirmaciones con `status = 1` y `Transfer` emitido (RN-5), se consume `"25000000"` USDC y el `gas_usado_wei` en ETH, liberando el sobrante de gas (RN-6)

### Escenario 2 (campos de la transacción ERC-20) [AT-08-05-02]
- Dado un retiro de USDC a `destino = 0x52908400098527886E0F7030069857D2E4169EE7` por `amount = "25000000"`
- Cuando se construye la transacción
- Entonces `to = <dirección del contrato USDC-mock configurado>`, `value = "0"`, y `data` es el encoding de `transfer(0x52908400098527886E0F7030069857D2E4169EE7, 25000000)` (RN-1)
- Y **no** se transfiere ETH como `value` nativo (el ETH solo paga gas, RN-2)

### Escenario 3 (borde): USDC alcanza pero falta ETH para el gas [AT-08-05-03]
- Dado `acc-1` con `disponible(USDC) = "50000000"` (50 USDC) y `disponible(ETH) = "100000000000000"` (0.0001 ETH), `fee_red_wei = "500000000000000"`
- Cuando intenta retirar `amount = "25000000"` (25 USDC)
- Entonces se rechaza con `INSUFFICIENT_FUNDS` (`asset: "ETH"`, `required = "500000000000000"`, `available = "100000000000000"`) (RN-3)
- Y **no** se bloquea el USDC (atomicidad de la reserva dual, INV-4)

### Escenario 4 (borde): falta USDC para el principal [AT-08-05-04]
- Dado `acc-1` con `disponible(USDC) = "10000000"` (10 USDC) y ETH suficiente para gas
- Cuando intenta retirar `amount = "25000000"` (25 USDC)
- Entonces se rechaza con `INSUFFICIENT_FUNDS` (`asset: "USDC"`, `required = "25000000"`, `available = "10000000"`) (RN-3)
- Y no se bloquea ETH

### Escenario 4b (borde): ambos activos insuficientes → precede USDC [AT-08-05-04b]
- Dado `acc-1` con `disponible(USDC) = "10000000"` (10 USDC, insuficiente para 25 USDC) **y** `disponible(ETH) = "100000000000000"` (insuficiente para `fee_red_wei = "500000000000000"`)
- Cuando intenta retirar `asset = USDC`, `amount = "25000000"` (25 USDC)
- Entonces se rechaza con `INSUFFICIENT_FUNDS` (`asset: "USDC"`, `required = "25000000"`, `available = "10000000"`), porque la precedencia verifica **USDC antes que ETH** (RN-3, HU-08-01 RN-9)
- Y **no** se bloquea ningún activo (ni USDC ni ETH; atomicidad de la reserva dual, INV-4)

### Escenario 5 (FAILED revertida): el `transfer` revierte, USDC se reacredita y el gas se consume [AT-08-05-05]
- Dado un retiro de USDC en `BROADCAST` con `amount_usdc = "25000000"`, `fee_red_wei = "500000000000000"`, cuya transacción se mina pero **revierte** (`status = 0`), consumiendo `gas_usado_wei = "300000000000000"`
- Cuando se reconcilia como `FAILED`
- Entonces se **reacredita** `"25000000"` USDC a disponible (no se transfirió) y se libera `fee_red_wei − gas_usado_wei = "200000000000000"` en ETH; se **consume** `gas_usado_wei = "300000000000000"` en ETH (gas pagado) (RN-7)
- Y la suma total de USDC **no cambia**; la de ETH disminuye en `"300000000000000"` (RN-9, INV-1)

### Escenario 6 (FAILED no minada): se libera toda la reserva dual [AT-08-05-06]
- Dado un retiro de USDC cuya transacción nunca se mina (descartada / broadcast definitivamente fallido), con `amount_usdc = "25000000"` y `fee_red_wei = "500000000000000"` bloqueados
- Cuando se declara `FAILED`
- Entonces se libera **toda** la reserva: `"25000000"` USDC y `"500000000000000"` ETH vuelven a disponible (`gas_usado_wei = 0`, RN-7)
- Y ninguna suma total por activo cambia (INV-1)

### Escenario 7 (confirmación con `Transfer` correcto) [AT-08-05-07]
- Dado un retiro de USDC `BROADCAST` con `amount_usdc = "25000000"`
- Cuando la transacción se mina con `status = 1` y emite `Transfer(from = emisora, to = destino, value = 25000000)` desde el contrato USDC-mock, alcanzando 12 confirmaciones
- Entonces el retiro pasa a `CONFIRMED` y la reconciliación consume `"25000000"` USDC + `gas_usado_wei` ETH, liberando el sobrante de gas (RN-5/RN-6)

### Escenario 8 (anti-replay y nonce — reutiliza HU-08-03) [AT-08-05-08]
- Dado un retiro de USDC a firmar desde la dirección emisora con nonce esperado `12`
- Cuando se firma y broadcastea
- Entonces la transacción ERC-20 lleva `chainId = 11155111` (EIP-155) y `nonce = 12` (único/secuencial/contiguo), igual que cualquier retiro (RN-4, INV-6)
- Y un `chainId` distinto se rechaza con `CHAIN_ID_MISMATCH`; un nonce ya usado, con `NONCE_CONFLICT`

### Escenario 9 (precisión de decimales): USDC en 6 decimales, gas en wei [AT-08-05-09]
- Dado un retiro de `amount = "1234567"` (1.234567 USDC, exacto en 6 decimales)
- Cuando se construye el `transfer`
- Entonces el `uint256` pasado es `1234567` (USDC-min), sin reescalar a 18 decimales ni a float (RN-8)
- Y la previsión de gas se computa por separado en wei (`100000 × gas_price_wei`), sin mezclar unidades

### Escenario 10 (status = 1 sin el evento Transfer esperado → FAILED) [AT-08-05-10]
- Dado un retiro de USDC en `BROADCAST` con `amount_usdc = "25000000"`, `fee_red_wei = "500000000000000"`, cuya transacción se mina con `status = 1` y alcanza 12 confirmaciones, pero el contrato USDC-mock **no** emite el `Transfer(from = emisora, to = destino, value = 25000000)` esperado (p. ej. bug del mock, o se llamó a una función equivocada), consumiendo `gas_usado_wei = "300000000000000"`
- Cuando se evalúa la confirmación (RN-5)
- Entonces el retiro **NO** pasa a `CONFIRMED`: se declara `FAILED` (análogo a revert), se **reacredita** `"25000000"` USDC a disponible y se **consume** `gas_usado_wei = "300000000000000"` en ETH (el gas se pagó aunque el token no se transfirió), liberando `fee_red_wei − gas_usado_wei = "200000000000000"` en ETH (RN-5/RN-7)
- Y la suma total de USDC **no cambia**; la de ETH disminuye en `"300000000000000"` (RN-9, INV-1). (Mismo caso, visto desde el seguimiento general, en HU-08-04 AT-08-04-11.)

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-08-05-01..-04, -04b, -05..-09, -10) pasan
- [ ] Reglas de negocio RN-1..RN-10 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md (`INSUFFICIENT_FUNDS` por activo, `CHAIN_ID_MISMATCH`, `NONCE_CONFLICT`, `BROADCAST_FAILED`)
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md (USDC en 6 decimales/USDC-min, gas en wei; sin floats; sin mezclar unidades; montos como string)
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md): INV-1 (conservación cruzada USDC/ETH), INV-2/INV-3 (reserva dual no-negativa y partición), INV-4 (atomicidad de reserva y reconciliación duales), INV-6 (chainId/nonce), INV-8 (persistencia)
- [ ] Adherencia verificada al estándar on-chain citado: ERC-20 `transfer(address,uint256)`; EIP-155 chainId 11155111; clave emisora BIP-32/39/44 coin type 60 (épica 06); contrato USDC-mock por configuración
