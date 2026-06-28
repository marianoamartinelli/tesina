# HU-07-02 — Detección de depósito USDC (ERC-20)

- **Epica:** 07 — Depósitos On-Chain
- **Actor / rol:** Sistema (servicio de detección / indexación on-chain)
- **Prioridad:** Alta
- **Dependencias:** Épica 06 (derivación de direcciones de depósito y mapeo dirección → cuenta); HU-07-03 (confirmaciones y acreditación); HU-07-04 (idempotencia y reorgs)
- **Estandares de dominio aplicables:** ERC-20 (evento `Transfer`), red Sepolia chainId 11155111, EIP-55 (formato de direcciones), BIP-32/39/44 (coin type 60, vía épica 06)

## Historia
Como Sistema de detección on-chain, quiero identificar las transferencias del token **USDC-mock** (eventos `Transfer` del contrato ERC-20) cuyo destinatario es una dirección de depósito de un usuario, para registrar cada depósito candidato y poder acreditarlo luego al balance interno una vez confirmado.

## Contexto y alcance
Esta HU cubre **solo la detección y el registro** de transferencias del ERC-20 USDC-mock en Sepolia (chainId `11155111`). A diferencia del ETH nativo, una transferencia ERC-20 se detecta a partir del **evento `Transfer`** emitido por el contrato: se filtran los logs cuya dirección emisora es el **contrato USDC-mock configurado** (parámetro de entorno, único y constante por entorno; no es un literal de la spec) y cuyo destinatario (`to`) es una dirección de depósito conocida.

NO cubre confirmaciones ni acreditación (HU-07-03) ni idempotencia/reorgs (HU-07-04). La identidad on-chain de un depósito ERC-20 es la tupla `(txHash, logIndex)`, donde `logIndex` es el **índice global del log dentro del bloque** —el campo `logIndex` tal como lo devuelven `eth_getTransactionReceipt` y `eth_getLogs`—, conforme a INV-5. Este valor es **block-scoped**: es un índice secuencial dentro del bloque completo (no dentro de la transacción). Dos logs en el mismo bloque siempre tienen `logIndex` distintos, provengan o no de la misma transacción; **no** existe un "logIndex dentro de la transacción" nativo en la interfaz JSON-RPC y no debe calcularse uno propio. USDC-mock tiene **6 decimales**.

## Reglas de negocio e invariantes
1. **RN-1 (firma del evento):** el evento detectado es `Transfer(address indexed from, address indexed to, uint256 value)` del estándar ERC-20. Su `topic0` es `keccak256("Transfer(address,address,uint256)")`, constante `0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef`. Solo se consideran logs con ese `topic0`.
2. **RN-2 (contrato correcto):** solo se consideran logs cuya **dirección emisora del log** es exactamente la dirección del contrato USDC-mock configurada para el entorno. Logs `Transfer` de cualquier otro contrato/token se ignoran.
3. **RN-3 (decodificación del log):** `from` = los 20 bytes menos significativos de `topic1`; `to` = los 20 bytes menos significativos de `topic2`; `value` = el `uint256` del campo `data`. El monto del depósito es `value` en **unidad mínima de USDC (6 decimales)**.
4. **RN-4 (criterio de detección):** un log `Transfer` constituye un depósito de USDC candidato sii: (a) su `topic0` es el de RN-1; (b) su dirección emisora es el contrato USDC-mock (RN-2); (c) `to` es una dirección de depósito registrada por la épica 06 para alguna cuenta; (d) `value > 0`; (e) la transacción contenedora tiene receipt `status == 1` (éxito) y pertenece a la cadena canónica de Sepolia. La pertenencia a Sepolia se garantiza validando que el nodo RPC es Sepolia (`eth_chainId() == 11155111`), no por log/transacción; ver README, sección "Servicio de detección e indexación".
5. **RN-5 (atribución):** la cuenta propietaria es la asignada por la épica 06 a la dirección `to`. La resolución dirección → cuenta es determinista y única.
6. **RN-6 (monto exacto, sin floats):** el monto se almacena/serializa como **entero de unidad mínima** (string `^(0|[1-9][0-9]*)$`), sin floats ni reescalado. USDC = 6 decimales (p. ej. `"10000000"` = 10 USDC).
7. **RN-7 (identidad y unicidad):** el depósito se identifica por `(txHash, logIndex)`, donde `logIndex` es el **índice global del log dentro del bloque** (campo `logIndex` de `eth_getLogs`/`eth_getTransactionReceipt`; block-scoped, ver Contexto), **no** el índice dentro de la transacción. Dos logs `Transfer` distintos (distinto `logIndex`) son **depósitos distintos**, aunque estén en la misma transacción. Reobservar el mismo `(txHash, logIndex)` refiere al mismo depósito.
8. **RN-8 (estado inicial):** un depósito recién detectado queda en estado **`PENDIENTE`** (estado inicial canónico de la máquina de estados del README) con: identidad `(txHash, logIndex)`, `accountId`, `asset = USDC`, `amountUsdcMin`, `blockNumber` (bloque de inclusión) y `confirmaciones` actuales. NO se acredita al balance en esta HU.
9. **RN-9 (reversiones):** una transacción revertida (receipt `status == 0`) no produce logs persistentes acreditables; cualquier log de una tx revertida se ignora.
10. **RN-10 (valor cero):** un evento `Transfer` con `value == 0` no es un depósito (no transfiere USDC); se ignora.
11. **RN-11 (destino no asignado):** un `Transfer` cuyo `to` es una dirección controlada por el exchange pero no asignada a ninguna cuenta no genera depósito atribuible (puede registrarse para auditoría; no incrementa balances de usuario).
12. **INV-5 / INV-8:** la identidad y el estado del depósito son persistentes; reprocesar el mismo `(txHash, logIndex)` no crea un segundo registro.

## Criterios de aceptación (DoD)

### Escenario 1: detección de un depósito USDC válido [AT-07-02-01]
- Dado que la épica 06 asignó la dirección `0xAbC...` a la cuenta `acc-1`
- Y que el contrato USDC-mock configurado emite un evento `Transfer` con `to = 0xAbC...` y `value = "10000000"` (10 USDC, 6 decimales) en una transacción con receipt `status = 1` en Sepolia
- Cuando el servicio de detección procesa los logs del bloque
- Entonces se registra un depósito con identidad `(txHash, logIndex)` del log, `accountId = acc-1`, `asset = USDC`, `amountUsdcMin = "10000000"` y estado `PENDIENTE`
- Y NO se modifica el balance de `acc-1` en esta etapa

### Escenario 2 (borde): dos logs Transfer en la misma transacción [AT-07-02-02]
- Dado que `0xAbC...` (de `acc-1`) y `0xDef...` (de `acc-2`) son direcciones de depósito
- Y que una única transacción emite dos eventos `Transfer` del contrato USDC-mock: uno con `to = 0xAbC...`, `value = "5000000"` con `logIndex = 3` y otro con `to = 0xDef...`, `value = "7000000"` con `logIndex = 5` (índices **globales del bloque**, tal como los reporta el nodo; pueden NO ser consecutivos si hay logs intermedios de otros contratos/eventos en el bloque)
- Cuando el servicio procesa los logs
- Entonces se registran **dos** depósitos independientes: `(txHash, 3)` → `acc-1` por `"5000000"` y `(txHash, 5)` → `acc-2` por `"7000000"`
- Y ambas identidades difieren solo en `logIndex` (que es block-scoped, RN-7)

### Escenario 3 (borde): monto con máxima precisión de 6 decimales [AT-07-02-03]
- Dado un `Transfer` hacia la dirección de depósito de `acc-1` con `value = "1"` (0.000001 USDC, 1 unidad mínima)
- Cuando se detecta
- Entonces `amountUsdcMin` se registra como `"1"` (string entero), sin redondeo ni conversión a float
- Y se preserva exactamente la unidad mínima (6 decimales)

### Escenario 4 (error/ignorar): Transfer de un contrato distinto al USDC-mock [AT-07-02-04]
- Dado un evento `Transfer` con `to` = dirección de depósito de `acc-1` y `value > 0`, pero emitido por un contrato ERC-20 **distinto** del USDC-mock configurado
- Cuando el servicio procesa los logs
- Entonces el log se ignora y NO se registra depósito (RN-2)
- Y el balance de `acc-1` no se ve afectado

### Escenario 5 (error/ignorar): log con topic0 distinto de Transfer [AT-07-02-05]
- Dado un log emitido por el contrato USDC-mock cuyo `topic0` NO es `0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef` (p. ej. `Approval`)
- Cuando el servicio procesa los logs
- Entonces el log se ignora (RN-1) y no se registra depósito

### Escenario 6 (borde): transferencia de valor cero [AT-07-02-06]
- Dado un evento `Transfer` del USDC-mock con `to` = dirección de depósito de `acc-1` y `value = "0"`
- Cuando el servicio procesa los logs
- Entonces NO se registra un depósito (RN-10)

### Escenario 7 (error/ignorar): transacción revertida [AT-07-02-07]
- Dado un evento `Transfer` cuyo `to` es dirección de depósito de `acc-1`, pero la transacción contenedora tiene receipt `status = 0` (revertida)
- Cuando el servicio procesa el bloque
- Entonces NO se registra un depósito acreditable (RN-9)

### Escenario 8 (idempotencia de detección): reprocesar el mismo log [AT-07-02-08]
- Dado un depósito ya detectado con identidad `(txHash, logIndex)` para `acc-1`
- Cuando el servicio reprocesa el mismo bloque/log (p. ej. tras un reinicio, INV-8)
- Entonces NO se crea un segundo registro para `(txHash, logIndex)`: la detección es idempotente respecto de la identidad

### Escenario 9 (borde): destino no asignado a ningún usuario [AT-07-02-09]
- Dado un `Transfer` del USDC-mock con `to` = dirección controlada por el exchange pero NO asignada a ninguna cuenta
- Cuando el servicio procesa los logs
- Entonces NO se genera un depósito atribuible a un usuario (RN-11) y ningún balance de usuario cambia

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-07-02-01..09) pasan
- [ ] Reglas de negocio RN-1..RN-11 e invariantes INV-5, INV-8 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md (USDC en unidad de 6 decimales como string entero, sin floats)
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md): INV-5, INV-8
- [ ] Adherencia verificada al estándar on-chain citado (ERC-20 `Transfer`, `topic0` canónico; contrato USDC-mock por configuración; Sepolia chainId 11155111; direcciones EIP-55)
