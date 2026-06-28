# HU-07-01 — Detección de depósito de ETH nativo

- **Epica:** 07 — Depósitos On-Chain
- **Actor / rol:** Sistema (servicio de detección / indexación on-chain)
- **Prioridad:** Alta
- **Dependencias:** Épica 06 (derivación de direcciones de depósito y mapeo dirección → cuenta); HU-07-03 (confirmaciones y acreditación); HU-07-04 (idempotencia y reorgs)
- **Estandares de dominio aplicables:** BIP-32/39/44 (coin type 60, vía épica 06), red Sepolia chainId 11155111, EIP-55 (formato de direcciones)

## Historia
Como Sistema de detección on-chain, quiero identificar las transferencias de **ETH nativo** entrantes hacia las direcciones de depósito de los usuarios, para registrar cada depósito candidato y poder acreditarlo luego al balance interno una vez confirmado.

## Contexto y alcance
Esta HU cubre **solo la detección y el registro** de transferencias de ETH nativo (no token) en la red única Sepolia (chainId `11155111`). El ETH nativo no emite eventos de log: una transferencia se detecta inspeccionando las transacciones cuyo campo `to` es una dirección de depósito conocida (provista por la épica 06) y cuyo `value` (en wei) es positivo, con receipt status de éxito.

NO cubre la espera de confirmaciones ni la acreditación al balance (HU-07-03), ni la idempotencia/reorgs (HU-07-04); esta HU deja el depósito en estado **observado/pendiente** con su identidad y metadatos. Tampoco cubre depósitos vía internal transactions (movimientos de valor originados dentro de la ejecución de un contrato), que quedan fuera de alcance: el supuesto es que los depósitos llegan como transferencias directas EOA → dirección de depósito.

La identidad on-chain de un depósito de ETH nativo es la tupla `(txHash, 0)` (logIndex fijo en `0`, porque no hay log asociado), conforme a INV-5.

## Reglas de negocio e invariantes
1. **RN-1 (criterio de detección):** una transacción `T` constituye un depósito de ETH nativo candidato sii se cumplen TODAS estas condiciones: (a) `T.to` **no es `null`** (las transacciones de creación de contrato tienen `to = null` y se ignoran); (b) `T.to` es exactamente una dirección de depósito registrada por la épica 06 para alguna cuenta; (c) `T.value > 0` (en wei); (d) el receipt de `T` tiene `status == 1` (éxito); (e) `T` pertenece a la cadena canónica de Sepolia (chainId `11155111`). La pertenencia a Sepolia no se verifica por transacción (las tx entrantes no llevan `chainId` en el receipt) sino validando que el nodo RPC es Sepolia (`eth_chainId() == 11155111`); ver README, sección "Servicio de detección e indexación".
2. **RN-2 (atribución):** la cuenta propietaria del depósito es la cuenta a la que la épica 06 asignó la dirección `T.to`. La resolución dirección → cuenta es determinista y única.
3. **RN-3 (monto exacto, sin floats):** el monto del depósito es `T.value` en **wei**, almacenado y serializado como **entero de unidad mínima** (string con patrón `^(0|[1-9][0-9]*)$`). Prohibido representarlo como float. ETH tiene 18 decimales.
4. **RN-4 (identidad y unicidad):** el depósito se identifica por `(txHash, logIndex)` con `logIndex = 0`. La detección de la misma tupla más de una vez refiere al **mismo** depósito (no se duplica el registro); la deduplicación/idempotencia de acreditación se gobierna en HU-07-04.
5. **RN-5 (estado inicial):** un depósito recién detectado queda en estado **`PENDIENTE`** (estado inicial canónico de la máquina de estados del README) con: identidad `(txHash, 0)`, `accountId`, `asset = ETH`, `amountWei`, `blockNumber` (bloque de inclusión) y `confirmaciones` actuales. NO se acredita al balance en esta HU.
6. **RN-6 (reversiones):** una transacción con receipt `status == 0` (revertida) NO se considera depósito, aunque `T.to` sea una dirección de depósito y `T.value > 0` (en una tx revertida no hay transferencia de valor neta al destino). No se registra como depósito acreditable.
7. **RN-7 (destino no asignado):** una transferencia entrante a una dirección controlada por el exchange pero **no asignada** a ninguna cuenta de usuario no genera un depósito atribuible; se ignora a efectos de acreditación (puede registrarse para auditoría, pero no incrementa ningún balance de usuario).
8. **RN-8 (valor cero):** una transacción con `T.value == 0` hacia una dirección de depósito NO es un depósito (no transfiere ETH); se ignora.
9. **RN-9 (múltiples depósitos):** varias transacciones distintas (distinto `txHash`) hacia la misma dirección de depósito generan **depósitos independientes**, cada uno con su propia identidad.
10. **INV-5 / INV-8:** la identidad y el estado del depósito son persistentes y sobreviven a reinicios; reprocesar el mismo `(txHash, 0)` no crea un segundo registro.

## Criterios de aceptación (DoD)

### Escenario 1: detección de un depósito de ETH nativo válido [AT-07-01-01]
- Dado que la épica 06 asignó la dirección `0xAbC...` (válida EIP-55) a la cuenta `acc-1`
- Y que en Sepolia (chainId `11155111`) se incluye una transacción `T` con `T.to = 0xAbC...`, `T.value = "1500000000000000000"` (1.5 ETH en wei) y receipt `status = 1`
- Cuando el servicio de detección procesa el bloque que incluye a `T`
- Entonces se registra un depósito con identidad `(txHash(T), 0)`, `accountId = acc-1`, `asset = ETH`, `amountWei = "1500000000000000000"` y estado `PENDIENTE`
- Y NO se modifica el balance de `acc-1` en esta etapa (la acreditación es HU-07-03)

### Escenario 2 (borde): múltiples depósitos a la misma dirección [AT-07-01-02]
- Dado que `0xAbC...` está asignada a `acc-1`
- Y que se incluyen dos transacciones distintas `T1` (`value = "1000000000000000000"`) y `T2` (`value = "2000000000000000000"`) con `T1.to = T2.to = 0xAbC...` y ambas con `status = 1`
- Cuando el servicio procesa ambas
- Entonces se registran **dos** depósitos independientes con identidades `(txHash(T1), 0)` y `(txHash(T2), 0)`
- Y los montos `"1000000000000000000"` y `"2000000000000000000"` se conservan exactos como enteros de wei

### Escenario 3 (borde): monto exacto en wei sin pérdida de precisión [AT-07-01-03]
- Dado un depósito de `T.value = "1000000000000000001"` wei (1 ETH + 1 wei) hacia una dirección de depósito de `acc-1`
- Cuando se detecta
- Entonces `amountWei` se registra como `"1000000000000000001"` (string entero), sin redondeo ni conversión a float
- Y el valor no se trunca ni se reescala (ETH = 18 decimales)

### Escenario 4 (error/ignorar): transacción revertida [AT-07-01-04]
- Dado que se incluye una transacción `T` con `T.to` = dirección de depósito de `acc-1`, `T.value = "500000000000000000"` y receipt `status = 0` (revertida)
- Cuando el servicio procesa el bloque
- Entonces NO se registra un depósito acreditable para `T` (RN-6)
- Y el balance de `acc-1` no se ve afectado en ninguna etapa posterior

### Escenario 5 (borde): transferencia de valor cero [AT-07-01-05]
- Dado que se incluye una transacción `T` con `T.to` = dirección de depósito de `acc-1` y `T.value = "0"`
- Cuando el servicio procesa el bloque
- Entonces NO se registra un depósito (RN-8), porque no hubo transferencia de ETH

### Escenario 6 (borde): destino es una dirección del exchange no asignada a ningún usuario [AT-07-01-06]
- Dado que la dirección `0xDef...` es controlada por el exchange pero NO está asignada a ninguna cuenta de usuario por la épica 06
- Y que llega una transacción con `to = 0xDef...` y `value > 0`
- Cuando el servicio procesa el bloque
- Entonces NO se genera un depósito atribuible a un usuario (RN-7) y ningún balance de usuario cambia

### Escenario 7 (idempotencia de detección): reprocesar el mismo bloque [AT-07-01-07]
- Dado un depósito ya detectado con identidad `(txHash(T), 0)` para `acc-1`
- Cuando el servicio reprocesa el mismo bloque (p. ej. tras un reinicio, INV-8)
- Entonces NO se crea un segundo registro para `(txHash(T), 0)`: la detección es idempotente respecto de la identidad
- Y el estado y los metadatos del depósito permanecen consistentes

### Escenario 8 (atribución correcta a distintas cuentas) [AT-07-01-08]
- Dado que `0xA...` está asignada a `acc-1` y `0xB...` a `acc-2`
- Y que llegan `Ta` (`to = 0xA...`) y `Tb` (`to = 0xB...`), ambas con `value > 0` y `status = 1`
- Cuando el servicio procesa el bloque
- Entonces el depósito de `Ta` se atribuye a `acc-1` y el de `Tb` a `acc-2` (RN-2), sin cruces

### Escenario 9 (borde): transacción de creación de contrato (`to = null`) [AT-07-01-09]
- Dado que se incluye una transacción `T` de **creación de contrato**, con `T.to = null` y `T.value > 0`
- Cuando el servicio procesa el bloque
- Entonces NO se registra ningún depósito (RN-1(a)): `to = null` no coincide con ninguna dirección de depósito y se ignora sin error
- Y ningún balance de usuario cambia

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-07-01-01..09) pasan
- [ ] Reglas de negocio RN-1..RN-9 e invariantes INV-5, INV-8 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md (montos en wei como string entero, sin floats)
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md): INV-5, INV-8
- [ ] Adherencia verificada al estándar on-chain citado (Sepolia chainId 11155111; direcciones EIP-55; mapeo de derivación BIP-44 coin type 60 vía épica 06)
