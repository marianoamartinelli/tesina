# Épica 07 — Depósitos On-Chain

## Objetivo

Detectar de forma confiable las transferencias on-chain entrantes (ETH nativo y el
ERC-20 USDC-mock) hacia las direcciones de depósito derivadas por la wallet HD,
esperar el número de confirmaciones requerido, y **acreditar** el monto al balance
interno disponible del usuario **una sola vez**, manejando idempotencia,
transacciones revertidas y reorganizaciones de cadena (reorgs).

Esta épica es el puente entre el mundo on-chain (Sepolia) y el ledger interno: todo
incremento del lado "depósitos confirmados" de la conservación de fondos (INV-1)
nace aquí.

---

## Alcance

### Dentro de alcance

- **Detección de ETH nativo:** identificar transacciones cuyo destinatario (`to`) es
  una dirección de depósito conocida y cuyo valor (`value`) es positivo, sobre la red
  única Sepolia (chainId `11155111`).
- **Detección de USDC (ERC-20):** identificar eventos `Transfer` emitidos por el
  contrato USDC-mock configurado, cuyo destinatario (`to`) es una dirección de
  depósito conocida.
- **Confirmaciones:** esperar `CONFIRMACIONES_REQUERIDAS = 12` antes de considerar un
  depósito acreditable.
- **Acreditación:** sumar el monto (en unidad mínima) al balance **disponible** del
  usuario propietario de la dirección, generando el asiento de ledger correspondiente
  (vía épica 02).
- **Idempotencia:** un depósito, identificado por `(txHash, logIndex)` (ERC-20) o
  `(txHash, 0)` (ETH nativo), se acredita **a lo sumo una vez** (INV-5).
- **Reorgs y reversiones:** descartar depósitos cuyo bloque de inclusión queda
  huérfano antes de confirmar, y nunca acreditar transacciones revertidas
  (receipt status `0`).

### Fuera de alcance

- Múltiples redes (solo Sepolia). No hay puentes ni multi-chain.
- Otros activos o tokens distintos de ETH nativo y el USDC-mock configurado.
- Depósitos vía **internal transactions** (movimientos de valor originados por la
  ejecución de un contrato, p. ej. `selfdestruct` o llamadas internas), que no
  aparecen como el campo `to` de una transacción de nivel superior. Supuesto: los
  depósitos se realizan mediante transferencias directas EOA → dirección de depósito.
- Reorgs de profundidad mayor a `CONFIRMACIONES_REQUERIDAS = 12` bloques (se asumen
  imposibles en la práctica para el alcance de la tesina; ver HU-07-04).
- KYC/AML, screening de origen de fondos, listas de sanciones.
- Firma/broadcast de transacciones salientes (eso es la épica 08 — retiros).
- **Umbral mínimo de depósito (dust threshold):** no se define un monto mínimo de depósito
  para ETH ni para USDC; **todo monto positivo es acreditable** (`> 0` en la unidad mínima).
  Esta simplificación es apropiada para la testnet (los tokens no tienen valor económico); un
  exchange de producción definiría un mínimo por activo para evitar el costo operativo de
  depósitos antieconómicos (dust). Se documenta como **decisión explícita**, no como omisión.

---

## Historias de Usuario

| ID        | Título                                   | Resumen (una línea)                                                                 |
|-----------|------------------------------------------|------------------------------------------------------------------------------------|
| HU-07-01  | Detección de depósito de ETH nativo      | Detectar transferencias de ETH nativo entrantes a direcciones de depósito.          |
| HU-07-02  | Detección de depósito USDC (ERC-20)      | Detectar eventos `Transfer` del contrato USDC-mock hacia direcciones de depósito.   |
| HU-07-03  | Confirmaciones y acreditación            | Esperar 12 confirmaciones y acreditar el monto al balance interno del usuario.       |
| HU-07-04  | Idempotencia y reorgs                     | Acreditar cada `(txHash, logIndex)` una sola vez; manejar reorgs y reversiones.      |

---

## Dependencias hacia otras épicas

- **Épica 06 — wallet-hd-y-direcciones:** provee las direcciones de depósito derivadas
  (BIP-32/39/44, coin type 60) y el mapeo **dirección → cuenta de usuario**. Sin ese
  mapeo no se puede atribuir un depósito a un usuario.
- **Épica 02 — balances-y-ledger:** provee el modelo de balances (disponible/bloqueado)
  y el ledger de doble entrada donde se registra la acreditación del depósito.
- **00 — fundaciones:** glosario, activos/red (Sepolia, chainId `11155111`,
  confirmaciones = 12, decimales ETH=18, USDC=6), convenciones monetarias (enteros de
  unidad mínima, prohibición de floats), modelo de errores e invariantes globales.

---

## Invariantes y reglas clave de la épica

- **INV-5 (idempotencia de depósitos):** cada identidad de depósito
  `(txHash, logIndex)` —con `logIndex = 0` para ETH nativo— se acredita **≤ 1 vez**,
  sin importar cuántas veces se observe/reprocese el evento.
- **INV-1 (conservación de fondos):** la acreditación de un depósito es el **único**
  flujo (junto con los retiros) que cambia la suma total de balances por activo. Tras
  acreditar, `Σ_acc total(acc, A) + total(EX, A)` aumenta exactamente en el monto del
  depósito.
- **INV-2 / INV-3:** la acreditación incrementa `disponible` (y por ende `total`) del
  usuario; nunca produce balances negativos.
- **INV-8 (persistencia):** los depósitos observados, su estado (pendiente/acreditado)
  y la identidad `(txHash, logIndex)` sobreviven a reinicios; la reconstrucción desde
  el ledger reproduce los balances acreditados.
- **Umbral de confirmaciones:** `CONFIRMACIONES_REQUERIDAS = 12`.
  `confirmaciones = max(0, bloque_cabeza − bloque_de_inclusión)`. Un depósito es
  acreditable sii `confirmaciones ≥ 12` (equivalente: `bloque_cabeza ≥ bloque_de_inclusión + 12`).
- **Montos en unidad mínima entera:** ETH en **wei** (18 decimales), USDC en **unidad
  de 6 decimales**. Prohibido floats. En la API y el ledger, los montos viajan como
  **string de entero** con patrón `^(0|[1-9][0-9]*)$`.
- **Red única:** todo depósito ocurre en Sepolia (chainId `11155111`). La dirección del
  contrato USDC-mock es **configuración por entorno** (única y constante por entorno),
  no un literal de la spec.
- **Reversiones:** una transacción con receipt status `0` (revertida) **no** genera
  depósito acreditable, aunque el `txHash` exista en la cadena.
- **Identidad disjunta ETH/ERC-20 (por qué el centinela `logIndex = 0` es seguro):** los
  espacios de identidades de ETH nativo `(txHash, 0)` y de ERC-20 `(txHash, logIndex_real)`
  son **disjuntos por construcción**. Las direcciones de depósito son **EOAs** (derivadas por
  BIP-44, coin type 60): un EOA no ejecuta código ni emite logs, por lo que ninguna
  transacción detectada como depósito de ETH nativo (`to = EOA de depósito`) puede a la vez
  emitir un log `Transfer`. Para que la clave de idempotencia sea inequívoca aun ante la
  coincidencia de valores `logIndex = 0`, el registro de depósitos **incluye el activo/tipo**
  (`asset ∈ {ETH, USDC}`) además de `(txHash, logIndex)` (ver HU-07-04 RN-1).
- **Finalidad en Ethereum PoS (nota académica):** Sepolia opera bajo Proof of Stake; la
  **finalidad** de checkpoint se alcanza aproximadamente cada 2 épocas (~64 bloques, ~12.8
  min). El umbral `CONFIRMACIONES_REQUERIDAS = 12` es conservador frente a reorgs
  superficiales y **suficiente para el alcance de la tesina** (testnet). Una implementación de
  producción podría además esperar la señal de finalidad del beacon chain (p. ej.
  `eth_getBlockByNumber("finalized")`) como condición más fuerte y definitiva. La spec usa
  exclusivamente el **conteo de confirmaciones** como mecanismo de seguridad, lo cual es
  correcto y suficiente aquí.
- **Conteos vs. montos en la serialización:** los **montos** (wei, USDC-min) viajan como
  **string de entero**; los **conteos e índices** no monetarios (`confirmations`, `required`,
  `logIndex`, `blockNumber`) viajan como **enteros JSON** (números), no como strings. Ver
  `convenciones-monetarias.md` §5.

---

## Ciclo de vida de un depósito (máquina de estados)

Un depósito atraviesa un conjunto **finito y canónico** de estados. El nombre del estado es
**único** (no se usa la forma con barra "DETECTADO/PENDIENTE"): el estado inicial es
**`PENDIENTE`**. El campo `status` expuesto por la API toma **exactamente uno** de estos
valores: `PENDIENTE`, `ACREDITADO`, `DESCARTADO`.

| Estado       | Significado                                                                                                                  |
|--------------|------------------------------------------------------------------------------------------------------------------------------|
| `PENDIENTE`  | Depósito detectado on-chain, aún no acreditado (`confirmaciones < 12`, o `≥ 12` pero aún no procesado). No incrementa balances. |
| `ACREDITADO` | Depósito confirmado (`confirmaciones ≥ 12`) y sumado al balance disponible. **Terminal** (no hay des-acreditación; HU-07-04 RN-10). |
| `DESCARTADO` | Depósito invalidado: su bloque quedó huérfano por reorg sin reinclusión, o la transacción resultó revertida (`status = 0`). No incrementa balances. |

### Transiciones

| Desde        | Evento                                                                                              | Hacia        | Regla                          |
|--------------|----------------------------------------------------------------------------------------------------|--------------|--------------------------------|
| (inicial)    | Detección de transferencia entrante válida (ETH o USDC) hacia una dirección de depósito             | `PENDIENTE`  | HU-07-01 RN-5 / HU-07-02 RN-8  |
| `PENDIENTE`  | `confirmaciones ≥ 12` y no acreditado aún                                                           | `ACREDITADO` | HU-07-03 RN-4                  |
| `PENDIENTE`  | Bloque de inclusión huérfano por reorg, sin reinclusión                                             | `DESCARTADO` | HU-07-04 RN-5 / RN-12          |
| `PENDIENTE`  | Receipt `status = 0` (revertida) detectado para la identidad                                        | `DESCARTADO` | HU-07-04 RN-7                  |
| `DESCARTADO` | La misma identidad `(txHash, logIndex)` reaparece en la cadena canónica (reinclusión) en `B'` con `status = 1` | `PENDIENTE`  | HU-07-04 RN-12 (recomputa confirmaciones desde `B'`) |

- `ACREDITADO` es **terminal**. `DESCARTADO` es terminal **salvo** reinclusión de la misma
  identidad en la cadena canónica (vuelve a `PENDIENTE`).
- El registro **nunca se elimina** físicamente: un depósito `DESCARTADO` permanece persistido
  (con la causa de descarte) para trazabilidad de auditoría (INV-8).
- Toda transición observable cumple los invariantes globales en cada instante (INV-1, INV-2,
  INV-3).

---

## Servicio de detección e indexación (decisiones de arquitectura)

Estas decisiones fijan el comportamiento operativo del indexador para que las HUs sean
evaluables de forma reproducible.

- **Bloque de inicio y checkpoint (INV-8).** El servicio persiste el número del **último
  bloque procesado** (`last_processed_block`, *checkpoint*). Al iniciar o reiniciar, retoma
  desde `max(BLOQUE_INICIO_CONFIGURADO, last_processed_block + 1)`. `BLOQUE_INICIO_CONFIGURADO`
  es un parámetro de entorno que debe fijarse **como mínimo** al bloque de despliegue del
  contrato USDC-mock (no tiene sentido escanear bloques anteriores a su existencia). El
  servicio procesa los bloques pendientes hasta la cabeza actual y luego **sigue la cabeza**.
  Los bloques ocurridos durante un *downtime* se recuperan al reiniciar (no se pierden
  depósitos); reprocesar bloques ya acreditados es seguro por idempotencia (INV-5).
- **Avance de la cabeza y reconexión.** El servicio avanza la cabeza por **polling** periódico
  (`eth_blockNumber` / `eth_getBlockByNumber`) **o** por **suscripción** a `newHeads` (la
  elección es de implementación; ambas son válidas). Ante fallo de conectividad con el nodo RPC
  (timeout, nodo caído, error RPC), aplica **reintentos con backoff exponencial** (N reintentos
  configurable; valor por defecto recomendado: 5) y registra un evento de error en el log de
  sistema. Durante el período de fallo **no se pierden bloques**: al reconectarse, el servicio
  retoma desde el checkpoint persistido.
- **Verificación del `chainId` del nodo.** Al iniciar y antes de procesar cualquier bloque, y
  nuevamente al reconectar, el servicio verifica `eth_chainId() == 11155111` (Sepolia). Si el
  nodo responde con un `chainId` distinto, el servicio **rechaza la conexión y termina con
  error** (`CHAIN_ID_MISMATCH`) y no acredita ningún depósito. Esta es la implementación
  concreta del criterio "pertenece a la cadena de Sepolia" de HU-07-01 RN-1(e) y HU-07-02
  RN-4(e): para depósitos **entrantes** no existe un `chainId` por transacción, por lo que la
  garantía de red proviene de **validar el nodo**, no la transacción individual.
- **Detección de reorgs.** El mecanismo concreto está en HU-07-04 RN-11 (comparación de
  `parentHash` al avanzar la cabeza, con retroceso hasta el ancestro común).

---

## Errores aplicables (del catálogo 00-fundaciones/modelo-de-errores.md)

| Code                       | HTTP | Uso en esta épica                                                              |
|----------------------------|------|--------------------------------------------------------------------------------|
| `DEPOSIT_NOT_CONFIRMED`    | 409  | Se intenta acreditar/usar un depósito con `confirmaciones < 12`.               |
| `DEPOSIT_ALREADY_CREDITED` | 409  | Se intenta acreditar un `(txHash, logIndex)` ya acreditado (idempotencia).      |
| `NOT_FOUND`                | 404  | Consulta de un depósito inexistente por su identidad.                           |
| `VALIDATION_ERROR`         | 422  | Parámetros de consulta mal formados (p. ej. `txHash`/`logIndex` inválidos).     |
| `UNAUTHENTICATED`          | 401  | Consulta de depósitos sin credencial válida.                                    |
| `UNAUTHORIZED`             | 403  | Consulta de depósitos de otra cuenta.                                           |
| `CHAIN_ID_MISMATCH`        | 422  | El nodo RPC configurado no es Sepolia (`eth_chainId() ≠ 11155111`); el servicio no acredita. |

---

## Precedencia de validación en consultas de depósitos

Cuando una consulta de depósito puede fallar por varias razones, el orden de evaluación es
**determinista** (consistente con `00-fundaciones/modelo-de-errores.md` §4). Toda HU y AT que
ejerza errores de consulta se rige por esta tabla:

1. **`UNAUTHENTICATED`** (401) — falta credencial o token inválido/expirado.
2. **`VALIDATION_ERROR`** (422) — parámetros mal formados (p. ej. `txHash` que no matchea
   `^0x[0-9a-fA-F]{64}$`, o `logIndex` no entero `≥ 0`).
3. **`NOT_FOUND`** (404) — no existe ningún depósito con esa identidad en el sistema.
4. **`UNAUTHORIZED`** (403) — el depósito existe pero pertenece a otra cuenta.

El contrato de la consulta (endpoint, esquema del recurso depósito) está en HU-07-03
(RN-11/RN-12) y el envelope HTTP en la épica 09 (HU-09-01).
