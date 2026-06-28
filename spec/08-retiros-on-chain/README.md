# Épica 08 — Retiros On-Chain

## Objetivo

Procesar de forma segura y conservativa los **retiros** de fondos del exchange hacia
direcciones externas indicadas por el usuario, en la red única **Sepolia**
(chainId `11155111`). Una solicitud de retiro válida **reserva/debita** el balance interno
(principal + previsión de fee de red), el sistema **construye, firma (EIP-155) y
broadcastea** la transacción con `nonce` y `gas` correctos, y luego **sigue las
confirmaciones** hasta finalizar (`CONFIRMED`) o reconciliar el balance ante un fallo
(`FAILED`).

Esta épica, junto con los depósitos (07), es uno de los **dos únicos flujos** que modifican
la suma total de fondos por activo (INV-1): un retiro confirmado **reduce** los fondos
internos exactamente en el principal transferido más el gas consumido por el exchange.

> Ante cualquier conflicto entre esta épica y `00-fundaciones`, **prevalece
> `00-fundaciones`**. Leer primero: `glosario.md`, `activos-y-par-de-trading.md`,
> `convenciones-monetarias.md`, `modelo-de-errores.md`, `invariantes-globales.md`.

---

## Alcance

### Dentro de alcance

- **Solicitud y validación de retiro:** activo (`ETH` | `USDC`), monto (entero de unidad
  mínima) y dirección destino; validación de formato de dirección (EIP-55), monto mínimo,
  positividad y fondos suficientes (incluida la previsión de gas).
- **Débito/reserva atómica:** al aceptar la solicitud se **bloquea** el balance interno
  (principal + previsión de fee de red en ETH) de forma atómica (asientos `WITHDRAWAL_LOCK`
  de la épica 02).
- **Construcción, firma y broadcast:** transacción saliente conforme **EIP-155** (incluye
  `chainId = 11155111` para anti-replay), con `nonce` único/secuencial/contiguo por
  dirección emisora y `gas` correctos. Retiro de **ETH nativo** (transferencia de `value`).
- **Retiro de USDC (ERC-20):** llamada a la función `transfer(address,uint256)` del
  contrato USDC-mock; el **fee de red se paga en ETH** (la transacción ERC-20 consume gas
  pagado en ETH por el exchange).
- **Seguimiento de confirmaciones:** estados `PENDING → BROADCAST → CONFIRMED | FAILED`,
  espera de `CONFIRMACIONES_REQUERIDAS = 12` y **reconciliación** del balance ante fallo
  (liberar/reacreditar lo no consumido) o éxito (consumir el bloqueado, liberar gas no
  usado).

### Fuera de alcance

- **Múltiples redes** (solo Sepolia) y **otros activos** distintos de ETH nativo y el
  USDC-mock configurado.
- **Derivación de claves y firma criptográfica de bajo nivel:** la provee la épica 06
  (BIP-32/39/44, coin type 60). Esta épica **consume** la capacidad de firmar con la clave
  de la dirección emisora; no redefine el esquema HD.
- **Modelo de balances/ledger** (buckets disponible/bloqueado, doble entrada): lo provee la
  épica 02. Esta épica **invoca** los movimientos `WITHDRAWAL_LOCK` / `WITHDRAWAL_SETTLE` /
  `WITHDRAWAL_RELEASE`.
- **Retiros por lotes (batching), aceleración (replace-by-fee/cancel), colas de prioridad y
  optimización de gas de grado producción.** Se asume un retiro = una transacción.
- KYC/AML, screening de direcciones destino, listas de sanciones, límites diarios
  regulatorios.
- Hardening de custodia de producción (HSM, MPC, rotación de claves, air-gapping).

---

## Historias de Usuario

| ID        | Título                                          | Resumen (una línea)                                                                              |
|-----------|-------------------------------------------------|-------------------------------------------------------------------------------------------------|
| HU-08-01  | Solicitar retiro                                | El usuario solicita un retiro (activo, monto, dirección); validación de formato, mínimo y fondos. |
| HU-08-02  | Débito y reserva al solicitar                   | Al aceptar la solicitud se bloquea atómicamente el balance (principal + previsión de fee de red). |
| HU-08-03  | Firma EIP-155 y broadcast                       | Construcción, firma EIP-155 (chainId anti-replay) y broadcast; `nonce` y `gas` correctos.        |
| HU-08-04  | Seguimiento de confirmaciones                   | Estados PENDING/BROADCAST/CONFIRMED/FAILED, 12 confirmaciones y reconciliación del balance.       |
| HU-08-05  | Retiro de USDC (ERC-20)                         | Retiro de USDC vía `transfer` del ERC-20; el fee de red se paga en ETH (reserva dual).            |

---

## Dependencias hacia otras épicas

- **Épica 06 — wallet-hd-y-direcciones:** provee la **clave/firma** de la dirección emisora
  (hot wallet) derivada por BIP-32/39/44 con coin type 60 y la ruta estándar de Ethereum
  (`m / 44' / 60' / account' / change / address_index`, con índices hardened en
  `purpose`/`coin_type`/`account`). Esta épica firma con esa clave conforme EIP-155.
- **Épica 02 — balances-y-ledger:** provee los buckets disponible/bloqueado y el ledger de
  doble entrada; esta épica genera los asientos `WITHDRAWAL_LOCK` (al reservar),
  `WITHDRAWAL_SETTLE` (al confirmar) y `WITHDRAWAL_RELEASE` (al fallar/abortar).
- **Épica 01 — cuentas y autenticación:** la solicitud de retiro la realiza una cuenta
  **autenticada**; la autorización limita la operación a los fondos propios.
- **Épica 07 — depósitos on-chain:** comparte el modelo de confirmaciones
  (`CONFIRMACIONES_REQUERIDAS = 12`, conteo por profundidad de bloque) y la sensibilidad a
  reorgs; un retiro es el flujo inverso que **reduce** el lado de la conservación (INV-1).
- **Épica 09 — api-http-websocket:** fija los nombres concretos de endpoints/campos y los
  eventos de actualización de estado; esta épica fija el **contenido**, las **unidades** y
  los **códigos de error**, no los nombres finales de ruta.
- **00 — fundaciones:** glosario, activos/red (Sepolia, chainId `11155111`, coin type 60,
  confirmaciones = 12, ETH=18 decimales, USDC=6 decimales), convenciones monetarias (enteros
  de unidad mínima, prohibición de floats, serialización como string), modelo de errores e
  invariantes globales.

---

## Parámetros y constantes de la épica (config; valores por defecto fijados para evaluación)

| Parámetro                    | Valor por defecto                                  | Notas                                                              |
|------------------------------|----------------------------------------------------|-------------------------------------------------------------------|
| `MIN_WITHDRAWAL_ETH`         | `1000000000000000` wei (= 0.001 ETH)               | Mínimo de retiro de ETH; viola → `WITHDRAWAL_BELOW_MIN`.          |
| `MIN_WITHDRAWAL_USDC`        | `1000000` USDC-min (= 1 USDC)                       | Mínimo de retiro de USDC; viola → `WITHDRAWAL_BELOW_MIN`.         |
| `GAS_LIMIT_ETH`              | `21000`                                            | Gas límite de una transferencia de ETH nativo.                    |
| `GAS_LIMIT_ERC20`            | `100000`                                            | Gas límite (cap) de una llamada `transfer` del ERC-20 USDC-mock.  |
| `CONFIRMACIONES_REQUERIDAS`  | `12`                                               | Confirmaciones para finalizar (`CONFIRMED`). Igual que depósitos. |
| `chainId`                    | `11155111`                                         | Sepolia. Parte de la firma EIP-155 (INV-6).                       |
| `coin_type` (BIP-44)         | `60`                                               | Ethereum (SLIP-44). Derivación de la dirección emisora (épica 06).|
| `GAS_PRICE_WEI`              | `20000000000` wei (= 20 gwei)                      | Precio de gas (wei por unidad de gas) usado para la previsión y para la transacción. Snapshot del retiro. |
| `GAS_PRICE_SOURCE`          | `configured_fixed`                                 | Fuente de `gas_price_wei`. `configured_fixed` = valor fijo de `GAS_PRICE_WEI` (evaluable/determinista). Alternativa no usada en la tesina: `node_estimate_at_request` (llamar `eth_gasPrice` al recibir la solicitud). |
| `TX_TYPE`                   | `legacy` (EIP-155 Type-0)                          | Tipo de transacción: legacy con `gas_price` único. EIP-1559 (Type-2) está fuera de alcance (ver nota de diseño). |
| `MAX_BROADCAST_RETRIES`     | `5`                                                | Reintentos de broadcast tras `BROADCAST_FAILED` antes de declarar el broadcast definitivamente imposible (`PENDING → FAILED`). |
| `MAX_BLOCKS_PENDING`        | `50`                                               | Máximo de bloques (`bloque_cabeza − bloque_de_broadcast`) que una tx `BROADCAST` puede pasar sin ser incluida/confirmada antes de tratarla como descartada (`BROADCAST → FAILED`). |
| Dirección del contrato USDC  | configuración por entorno (única y constante)      | No es un literal de la spec; la consume el retiro ERC-20.         |

> **Previsión de fee de red (gas).** Para una transacción de retiro,
> `fee_red_wei = gas_limit × gas_price_wei`, **multiplicación entera exacta en wei** (sin
> floats, sin división). `gas_limit` es `GAS_LIMIT_ETH` (retiro ETH) o `GAS_LIMIT_ERC20`
> (retiro USDC).
>
> **Ciclo de vida de `gas_price_wei` (fuente única y snapshot).** `gas_price_wei` se toma de
> `GAS_PRICE_WEI` de configuración (`GAS_PRICE_SOURCE = configured_fixed`) **en el momento de
> aceptar la solicitud** (HU-08-01) y se **persiste como snapshot** del retiro junto con la
> reserva (HU-08-02 RN-7). El **mismo** valor snapshotteado se usa para: (a) el chequeo de
> fondos suficientes (HU-08-01 RN-8/RN-9), (b) la composición de la reserva (HU-08-02), (c) el
> `gas_price` de la transacción firmada (HU-08-03 RN-5), y (d) la reconciliación (HU-08-04).
> No se vuelve a estimar entre la reserva y el broadcast: **no existe un flujo de re-reserva**
> y, por tanto, no hay camino de "retiro atascado por gas creciente". Esto hace los cálculos
> deterministas y testeables (un test inyecta un `GAS_PRICE_WEI` conocido).
>
> **`precio_efectivo_wei` (gas realmente pagado).** Es el campo `effectiveGasPrice` del
> transaction receipt. Para las transacciones **legacy (Type-0)** de esta épica,
> `precio_efectivo_wei = gas_price_wei` (el valor fijado en la transacción = el snapshot). El
> gas realmente consumido al confirmar es `gas_usado_wei = gas_usado × precio_efectivo_wei`.
>
> **Garantía `gas_usado_wei ≤ fee_red_wei` (respaldo de la reserva).** Como la transacción es
> legacy con `gas_price = gas_price_wei_snapshot` y `gas_usado ≤ gas_limit`, se cumple
> siempre `gas_usado_wei = gas_usado × gas_price_wei ≤ gas_limit × gas_price_wei = fee_red_wei`.
> Por lo tanto `fee_red_wei − gas_usado_wei ≥ 0` y la diferencia (sobrante de gas) se libera a
> disponible en la reconciliación (HU-08-04). La previsión es un **límite superior** exacto.

> **Política de fee del exchange.** En esta tesina **no** se cobra una fee de exchange por
> retiro (las únicas fees del proyecto son maker/taker del trading). El usuario solo soporta
> el **costo de gas de red**, que el exchange paga en ETH y descuenta del balance interno
> del usuario vía la previsión.

> **Nota de diseño — tipo de transacción (legacy vs EIP-1559).** Esta épica usa transacciones
> **legacy EIP-155 (Type-0)** con un único campo `gas_price` (`TX_TYPE = legacy`), por
> simplicidad y determinismo de la reconciliación (`precio_efectivo_wei = gas_price_wei`). Las
> transacciones **EIP-1559 (Type-2)** son el estándar actual en Ethereum y están soportadas
> por Sepolia; usan `maxFeePerGas`/`maxPriorityFeePerGas`, pagan `baseFee + tip` y ofrecen
> mejor predictibilidad de fees y una reconciliación del sobrante de gas más fina
> (`effectiveGasPrice ≤ maxFeePerGas`). Una implementación de producción debería preferir
> Type-2; aquí se descarta para evitar ambigüedad en `precio_efectivo_wei` y mantener la
> aritmética de reserva exacta. Este es el único punto donde Type-0 vs Type-2 importa.

> **Supuesto operacional — ETH on-chain de la dirección emisora.** El gas on-chain lo paga la
> **dirección emisora** (hot wallet) con su ETH **real** en Sepolia, que es independiente de
> los balances internos de los usuarios. Se **asume** que la emisora siempre tiene ETH
> on-chain suficiente para cubrir el gas (operación/recarga de la hot wallet **fuera de
> alcance**). Si el nodo rechazara el broadcast por fondos insuficientes de la emisora, el
> caso se trata como `BROADCAST_FAILED` (HU-08-03 RN-8/RN-13): el retiro queda `PENDING` y se
> reintenta; agotados `MAX_BROADCAST_RETRIES`, transiciona `PENDING → FAILED`.

---

## Estados del retiro (máquina de estados)

```
            (solicitud aceptada,            (firma + broadcast OK)
             balance bloqueado)
   [solicitud] ───────────────▶ PENDING ───────────────────────▶ BROADCAST
                                   │                                 │
                                   │ (firma/broadcast falla          │ (12 confirmaciones,
                                   │  definitivamente, o aborto)     │  receipt status = 1)
                                   ▼                                 ▼
                                 FAILED ◀───────────────────────  CONFIRMED
                                   ▲   (tx minada pero revertida:  (final, éxito)
                                   │    receipt status = 0)
                            (reconciliación del balance:
                             liberar/reacreditar lo no consumido)
```

- **PENDING:** solicitud aceptada; balance **bloqueado** (`WITHDRAWAL_LOCK`); la transacción
  se está construyendo/firmando o aún no fue broadcasteada con éxito.
- **BROADCAST:** transacción firmada (EIP-155, `chainId = 11155111`) y aceptada por el nodo;
  esperando confirmaciones (0..11).
- **CONFIRMED:** alcanzó `≥ 12` confirmaciones con receipt `status = 1` (y, para **USDC**,
  además con el evento `Transfer(from = emisora, to = destino, value = amount_usdc)` emitido
  por el contrato USDC-mock; ver HU-08-04 RN-2 y HU-08-05 RN-5); retiro **final**. Se
  **consume** el bloqueado del principal y del gas realmente usado; se **libera** la
  diferencia de gas no usada (`WITHDRAWAL_SETTLE` + posible `WITHDRAWAL_RELEASE` del sobrante
  de gas).
- **FAILED:** la transacción no llegará a confirmar. Se **reconcilia** el balance: se
  reacredita todo lo no consumido on-chain (`WITHDRAWAL_RELEASE`). Causas y disparadores
  **explícitos** (ver HU-08-04 RN-1/RN-5):
  - `BROADCAST → FAILED`: tx minada pero **revertida** (`status = 0`); o (USDC) `status = 1`
    **sin** el evento `Transfer` esperado; o tx **descartada** del mempool (dropped tras reorg
    o por nonce ocupado) y sin reaparecer; o **timeout** de inclusión (`bloque_cabeza −
    bloque_de_broadcast > MAX_BLOCKS_PENDING`).
  - `PENDING → FAILED`: **cancelación del usuario** antes del broadcast; o broadcast
    **definitivamente imposible** (se agotaron `MAX_BROADCAST_RETRIES` reintentos tras
    `BROADCAST_FAILED`). En ambos casos `gas_usado_wei = 0` y se libera **toda** la reserva.

`CONFIRMED` y `FAILED` son **terminales**.

> **Cancelación de un retiro `PENDING`.** Mientras el retiro **no** fue broadcasteado
> (estado `PENDING`, sin `txHash`), el titular de la cuenta puede **cancelarlo** mediante una
> solicitud explícita: transiciona `PENDING → FAILED` con `WITHDRAWAL_RELEASE` completo
> (libera toda la reserva, `gas_usado_wei = 0`). Un retiro ya en `BROADCAST`/`CONFIRMED`/
> `FAILED` **no** es cancelable → `CONFLICT` (409). (Los nombres de endpoint los fija la
> épica 09; aquí se fija el efecto contable y la transición de estado.)

---

## Invariantes y reglas clave de la épica

- **INV-1 (conservación de fondos).** Un retiro **confirmado** es, junto con los depósitos,
  el único flujo que altera `Σ_acc total(acc, A) + total(EX, A)`. Tras `CONFIRMED`, la suma
  total por activo **disminuye** exactamente en lo que salió del sistema:
  - Retiro de **ETH**: `amount_wei` (al destinatario) `+ gas_usado_wei` (al validador).
  - Retiro de **USDC**: `amount_usdc` en USDC (al destinatario) y `gas_usado_wei` en ETH
    (al validador). Estas son las "fees on-chain que el exchange pagó por los retiros" que
    INV-1 contempla.
  - Un retiro `PENDING`/`BROADCAST` **no** cambia la suma total: solo mueve disponible →
    bloqueado (INV-3).
- **INV-2 (no-negatividad).** Una solicitud que no tenga **disponible** suficiente para
  bloquear el principal y/o la previsión de gas se **rechaza ANTES** con
  `INSUFFICIENT_FUNDS`; nunca se aplica y luego se corrige. `disponible ≥ 0` y
  `bloqueado ≥ 0` en todo momento.
- **INV-3 (partición disponible + bloqueado = total).** Reservar mueve `disponible → bloqueado`
  (total constante); confirmar consume el bloqueado (total baja, sale del sistema); fallar
  libera bloqueado → disponible (total constante respecto del principal no consumido).
- **INV-4 (atomicidad — sentido general).** Tanto la reserva inicial (HU-08-02) como la
  reconciliación final (HU-08-04) se aplican **completas o nada**: no hay estado parcial
  observable (p. ej. débito del principal sin previsión de gas, o liberación a medias).
  `00-fundaciones/invariantes-globales.md` enuncia INV-4 sobre el **settlement de un fill**;
  aquí se aplica en su **sentido general de atomicidad de toda operación de balance**
  (bloqueo / consumo / liberación), consistente con esa definición. Es decir, INV-4 no se
  limita a fills: cubre también las operaciones de retiro de esta épica.
- **INV-6 (anti-replay EIP-155 + unicidad de nonce).** Toda transacción saliente lleva
  `chainId = 11155111`; un `chainId` distinto se rechaza con `CHAIN_ID_MISMATCH`. El `nonce`
  por dirección emisora es **único, secuencial y contiguo** (sin huecos ni repeticiones);
  reutilizar o saltear un nonce es `NONCE_CONFLICT`. **Reconciliación de nonce al arranque:**
  al iniciar/reiniciar el servicio, para cada dirección emisora el nonce operativo se
  determina como `MAX(max_nonce_persistido_en_ledger + 1, eth_getTransactionCount(address,
  "pending"))`; si el nonce del nodo es mayor que el persistido, indica transacciones no
  registradas en el ledger y se reconcilia el estado de los retiros `PENDING`/`BROADCAST` con
  los `txHash` hallados en el mempool/historial del nodo, evitando reasignar un nonce ya
  usado (ver HU-08-03 RN-3/RN-11/RN-14).
- **Idempotencia del retiro.** (a) La **solicitud** admite una clave de idempotencia
  opcional del cliente: un reenvío con la misma clave y mismos parámetros devuelve el
  **mismo** retiro sin doble débito, **independientemente de su estado actual** (`PENDING`,
  `BROADCAST`, `CONFIRMED` o `FAILED`); la misma clave con parámetros distintos es `CONFLICT`.
  Para reintentar un retiro fallido el cliente debe usar una **clave de idempotencia
  distinta** (ver HU-08-01 RN-10). (b) El **broadcast** de un mismo retiro no genera dos
  transacciones distintas para el mismo nonce. (c) La **confirmación** consume/reconcilia el
  retiro **a lo sumo una vez** aunque el evento on-chain se observe múltiples veces.
- **INV-8 (persistencia y recuperación).** El retiro, su estado, su identidad on-chain
  (`txHash`, `nonce`, dirección emisora) y la reserva asociada **sobreviven a reinicios**; el
  estado se reconstruye desde el ledger y desde el seguimiento on-chain sin doble débito ni
  doble crédito.
- **Dinero en unidad mínima entera.** ETH en **wei** (18 decimales), USDC en **unidad de 6
  decimales**. Previsión de gas = `gas_limit × gas_price_wei` (multiplicación entera). En la
  API y el ledger los montos viajan como **string de entero** con patrón `^(0|[1-9][0-9]*)$`.
  **Prohibido** floats.

---

## Errores aplicables (del catálogo 00-fundaciones/modelo-de-errores.md)

| Code                        | HTTP | Uso en esta épica                                                                                  |
|-----------------------------|------|----------------------------------------------------------------------------------------------------|
| `UNAUTHENTICATED`           | 401  | Solicitud/consulta de retiro sin credencial válida.                                                |
| `UNAUTHORIZED`              | 403  | Operar sobre un retiro de otra cuenta.                                                              |
| `VALIDATION_ERROR`          | 422  | Payload mal formado: monto que no matchea `^(0\|[1-9][0-9]*)$`, `asset` fuera de `{ETH, USDC}`, campos faltantes. |
| `INVALID_ADDRESS`           | 422  | Dirección destino no es `0x`+40 hex o checksum EIP-55 incorrecto.                                  |
| `WITHDRAWAL_AMOUNT_INVALID` | 422  | Monto de retiro no positivo (p. ej. `"0"`) o que no respeta la unidad mínima del activo.            |
| `WITHDRAWAL_BELOW_MIN`      | 422  | Monto menor al mínimo del activo (`MIN_WITHDRAWAL_ETH` / `MIN_WITHDRAWAL_USDC`).                    |
| `INSUFFICIENT_FUNDS`        | 422  | Disponible insuficiente para bloquear principal y/o previsión de gas (ETH). En USDC: falta USDC o ETH para gas. |
| `CHAIN_ID_MISMATCH`         | 422  | Transacción/firma con `chainId ≠ 11155111`.                                                         |
| `NONCE_CONFLICT`            | 409  | Nonce ya usado o fuera de secuencia al construir/broadcastear.                                      |
| `BROADCAST_FAILED`          | 502  | El nodo rechazó el broadcast de la transacción.                                                     |
| `CONFLICT`                  | 409  | Reuso de clave de idempotencia con parámetros distintos; transición de estado inválida.            |
| `NOT_FOUND`                 | 404  | Consulta de un retiro inexistente.                                                                  |
| `INTERNAL_ERROR`            | 500  | Falla interna no clasificada (no filtra detalles sensibles).                                        |
