# HU-09-04 — WebSocket privado del usuario

- **Epica:** 09 — API HTTP/WebSocket
- **Actor / rol:** Trader autenticado / Sistema (servidor WS)
- **Prioridad:** Alta
- **Dependencias:** HU-09-02 (autenticación/autorización), HU-09-03 (protocolo WS base),
  HU-09-05 (modelo de errores), HU-02-* (balances), HU-04-* (órdenes), HU-05-* (settlement)
- **Estándares de dominio aplicables:** N/A on-chain

## Historia
Como trader, quiero un canal WebSocket **privado y autenticado** que me notifique en tiempo
real los **cambios de estado de mis órdenes** y de **mis balances**, para reaccionar a
fills y cancelaciones sin hacer polling de la API REST.

## Contexto y alcance
Esta HU define el **contrato del canal privado**: autenticación con token, suscripción a
los streams `orders` y `balances`, formato de cada evento, y el **aislamiento estricto por
cuenta** (cada usuario recibe únicamente sus propios eventos). Los eventos reflejan
transiciones producidas por las épicas de dominio (alta/cancelación/match en 04, settlement
en 05, cambios de balance en 02); esta HU fija cómo se **transmiten**, no cómo se generan.

Supuestos: mensajes JSON de texto; montos como string de entero en unidad mínima
(`00-fundaciones/convenciones-monetarias.md` §5); reusa el protocolo de suscripción de
HU-09-03 pero exige token.

## Reglas de negocio e invariantes

1. **RN-1 (autenticación obligatoria):** el canal privado exige el token Bearer válido del
   usuario (HU-09-02). **Mecanismo canónico (único y normativo):** tras el handshake, el
   cliente envía como **primer** mensaje `{ "type": "auth", "token": "<token>" }`; el
   servidor responde `{ "type": "authenticated" }` si el token es válido. No se usa el token
   en la URL/query (evita exponerlo en logs) ni en headers del upgrade. Si el token es
   ausente/ inválido/ expirado, o no llega un mensaje `auth` válido dentro de **10 s** desde
   la apertura, el servidor responde `{ error: { code: "UNAUTHENTICATED" } }` y **cierra** la
   conexión, sin entregar ningún evento de usuario. Cualquier intento de `subscribe` a un
   canal privado antes de autenticar se rechaza con `UNAUTHENTICATED`.
2. **RN-2 (suscripción):** tras autenticar, el cliente envía
   `{ "type": "subscribe", "channel": "orders"|"balances"|"withdrawals" }` (sin necesidad de
   `symbol`, pues el par es único). El servidor confirma con
   `{ "type": "subscribed", "channel" }`.
3. **RN-3 (aislamiento por cuenta):** el servidor entrega **solo** eventos de la cuenta
   dueña del token. Nunca se filtra `accountId`, orden ni balance de otra cuenta (privacidad;
   coherente con HU-09-02 RN-5/RN-10).
4. **RN-4 (evento de orden):** cada cambio de estado de una orden propia emite
   `{ "type": "order", "orderId", "clientOrderId", "symbol": "ETH-USDC", "side", "type",
   "priceMin"|null, "quantityWei", "filledWei", "feeWei", "feeUsdcMin", "status", "sequence",
   "timestamp" }`. `status ∈ {OPEN, PARTIALLY_FILLED, FILLED, CANCELLED}`. `filledWei` es la
   cantidad acumulada ejecutada; `feeWei`/`feeUsdcMin` acumulan la fee cobrada por los fills
   hasta el momento (BUY acumula `feeWei`, SELL `feeUsdcMin`; el otro es `"0"`; ver HU-09-01
   RN-2). Para una orden `MARKET` parcialmente ejecutada y sin remanente, el último evento
   lleva `status: "CANCELLED"` (estado terminal de MARKET, HU-09-01 RN-5, HU-03-04 RN-9).
5. **RN-5 (transiciones de orden):** se emite un evento ante cada transición observable:
   alta aceptada (`OPEN`), fill parcial (`PARTIALLY_FILLED` con `filledWei` creciente), fill
   total (`FILLED`), cancelación (`CANCELLED`). **No** existe evento WS `REJECTED`: toda orden
   rechazada por validación de esquema/par o por matching retorna su código de error por la
   respuesta **REST** (HU-09-01 / HU-09-05) y nunca llega al libro, por lo que no produce
   evento por el canal privado. El canal `orders` solo emite las transiciones
   `OPEN`/`PARTIALLY_FILLED`/`FILLED`/`CANCELLED`.
6. **RN-6 (evento de balance):** cada cambio de balance propio emite
   `{ "type": "balance", "asset": "ETH"|"USDC", "available", "locked", "total", "reason",
   "refId"|null, "sequence", "timestamp" }`. Se cumple `total == available + locked` (INV-3)
   y `available ≥ 0 ∧ locked ≥ 0` (INV-2) en cada evento. `reason` indica la causa del cambio
   con enum acotado: `{ ORDER_PLACED, ORDER_CANCELLED, ORDER_FILLED, DEPOSIT_CREDITED,
   WITHDRAWAL_INITIATED, WITHDRAWAL_CONFIRMED, WITHDRAWAL_FAILED }`. `refId` correlaciona con
   el recurso origen (`orderId` para causas de orden, `withdrawalId` para causas de retiro,
   `depositId` para `DEPOSIT_CREDITED`) o `null` si no aplica. La liberación del remanente
   o presupuesto no consumido de una `MARKET` que termina `CANCELLED` (HU-09-01 RN-5) usa
   `reason: "ORDER_CANCELLED"` con `refId = orderId`.
7. **RN-7 (consistencia con conservación):** los eventos reflejan, no alteran, el estado.
   La secuencia de eventos de balance es coherente con INV-1 (un fill solo redistribuye:
   bloqueado→consumido y crédito en el otro activo; la suma global no cambia). La fee
   cobrada nunca deja un neto negativo (`00-fundaciones/convenciones-monetarias.md` §3.3).
8. **RN-8 (secuencia):** los eventos del canal privado llevan `sequence` estrictamente
   creciente y contiguo, **independiente por canal** (`orders`, `balances`, `withdrawals`
   cada uno la suya) por conexión/suscripción (RG-API-7, HU-09-03 RN-13). Un hueco se detecta
   **solo dentro del mismo canal** y obliga a re-sincronizar (vía reconsulta REST o
   re-suscripción); un mensaje de otro canal con `sequence` distinta no es un hueco. La
   numeración es **por conexión**: tras una reconexión, el cliente re-sincroniza su estado
   por REST y trata la numeración del canal como **nueva** (las `sequence` de la conexión
   anterior **no** son comparables con las de la nueva).
9. **RN-9 (orden de eventos en un fill):** ante un fill, los eventos `order` y `balance`
   asociados reflejan el resultado **después** del settlement atómico (INV-4): no se observa
   un estado parcial (p. ej. balance debitado pero orden sin actualizar).
10. **RN-10 (serialización):** todos los montos (`priceMin`, `quantityWei`, `filledWei`,
    `available`, `locked`, `total`) se serializan como **string** que matchea
    `^(0|[1-9][0-9]*)$`. Nunca número JSON.
11. **RN-11 (idempotencia de aplicación en cliente):** los eventos llevan `orderId`/`asset`
    y `sequence` suficientes para que el cliente aplique el último estado de forma
    idempotente (reaplicar un evento ya visto no corrompe el estado local).
12. **RN-12 (desuscripción/cierre):** el cliente puede `unsubscribe` de un canal; al cerrar
    la conexión cesa toda entrega. Reabrir requiere re-autenticar.
13. **RN-13 (expiración de token en sesión activa):** si el token expira mientras la conexión
    WS privada está abierta, el servidor emite `{ error: { code: "UNAUTHENTICATED" } }` y
    **cierra** la conexión (código de cierre WS `4001` o equivalente). El cliente debe
    reconectar y re-autenticar (RN-1) con un token fresco. Esto extiende a la sesión WS la
    regla REST de token expirado (HU-09-02 RN-3).
14. **RN-14 (canal de retiros):** la suscripción `withdrawals` entrega, en cada transición de
    estado de un retiro propio, el evento
    `{ "type": "withdrawal", "withdrawalId", "asset", "amountMinUnit", "address",
    "status", "txHash"|null, "confirmations", "failureReason", "sequence", "timestamp" }`.
    `status ∈ {PENDING, BROADCAST, CONFIRMED, FAILED}` (HU-08-04); `txHash` es `null` hasta el
    broadcast; `confirmations` es **entero JSON** (conteo, no monto; convenciones §5);
    `failureReason` es el **código de causa** cuando `status = FAILED` y `null` en cualquier
    otro estado (enum de HU-09-01 RN-18: `BROADCAST_FAILED`, `TX_DROPPED`, `TX_REVERTED`,
    `USER_CANCELLED`; HU-08-03/HU-08-04). Esto permite conocer de forma reactiva el
    resultado on-chain (incluido el fallo `FAILED` y su causa) sin polling de
    `GET /withdrawals/{withdrawalId}`. El aislamiento por cuenta (RN-3) aplica igual que a
    `orders`/`balances`.
15. **RN-15 (heartbeat):** el canal privado usa el mismo mecanismo ping/pong de HU-09-03
    RN-14 (ping del servidor cada ~30 s; cierre si no hay `pong` en ~10 s).

## Criterios de aceptación (DoD)

### Escenario 1: Autenticación y suscripción [AT-09-04-01]
- Dado un token válido de la cuenta A
- Cuando A abre la conexión WS y envía como primer mensaje
  `{ type: "auth", token: "<token>" }`, recibe `{ type: "authenticated" }`, y luego envía
  `{ type: "subscribe", channel: "orders" }` y `{ type: "subscribe", channel: "balances" }`
- Entonces recibe `{ type: "subscribed", channel: "orders" }` y
  `{ type: "subscribed", channel: "balances" }`

### Escenario 2 (error): Sin token válido [AT-09-04-02]
- Dado el canal privado
- Cuando un cliente abre la conexión y envía `{ type: "auth", token: "<inválido/expirado>" }`,
  o intenta `{ type: "subscribe", channel: "orders" }` **sin** enviar `auth`, o no envía
  ningún `auth` dentro de los 10 s de apertura
- Entonces recibe `{ error: { code: "UNAUTHENTICATED" } }` y el servidor cierra la conexión,
  sin entregar ningún evento de usuario (RN-1)

### Escenario 3: Evento de orden al aceptar el alta [AT-09-04-03]
- Dado A suscrito a `orders`
- Cuando A crea una orden limit que queda resting
- Entonces A recibe un evento `order` con `status: "OPEN"`, `filledWei: "0"`,
  `feeWei: "0"`, `feeUsdcMin: "0"` y los montos como strings

### Escenario 4: Transición por fill parcial y total [AT-09-04-04]
- Dado una orden limit propia `OPEN` por `quantityWei: "1000000000000000000"` (1 ETH)
- Cuando se ejecuta un fill parcial de `400000000000000000` (0.4 ETH) y luego el resto
- Entonces A recibe primero un evento `order` con `status: "PARTIALLY_FILLED"` y
  `filledWei: "400000000000000000"`, y luego otro con `status: "FILLED"` y
  `filledWei: "1000000000000000000"`
- Y los eventos llegan con `sequence` creciente y contigua

### Escenario 5: Evento de balance al bloquear y al liquidar [AT-09-04-05]
- Dado A suscrito a `balances` con `USDC` disponible
- Cuando A crea una orden BUY que bloquea USDC y luego se llena
- Entonces A recibe un evento `balance` de `USDC` con `locked` aumentado al crear la orden
  (`reason: "ORDER_PLACED"`, `refId` = `orderId`), y, tras el fill, eventos `balance`
  (`reason: "ORDER_FILLED"`, `refId` = `orderId`) que reflejan el consumo del bloqueado y el
  crédito de `ETH` (menos la fee)
- Y en cada evento `total == available + locked` (INV-3) y todos ≥ 0 (INV-2)

### Escenario 6: Cancelación reflejada [AT-09-04-06]
- Dado una orden propia `OPEN`
- Cuando A la cancela vía `DELETE /orders/{orderId}`
- Entonces A recibe un evento `order` con `status: "CANCELLED"` y un evento `balance`
  (`reason: "ORDER_CANCELLED"`, `refId` = `orderId`) que libera el bloqueado correspondiente
  (bloqueado→disponible, total constante, INV-3)

### Escenario 7 (aislamiento): Eventos solo del dueño [AT-09-04-07]
- Dado A y B suscritos al canal privado con sus respectivos tokens
- Cuando ocurre un fill entre una orden de A (maker) y una de B (taker)
- Entonces A recibe únicamente sus eventos `order`/`balance` y B únicamente los suyos;
  ninguno recibe eventos del otro

### Escenario 8 (atomicidad): Estado posterior al settlement [AT-09-04-08]
- Dado un fill que afecta orden y balances de A
- Cuando A recolecta **todos** los eventos del canal privado desde el envío de la orden hasta
  recibir el evento `order` con `status: "FILLED"`
- Entonces (1) el cambio de `filledWei` en el evento `order` y los cambios de
  `available`/`locked` en los eventos `balance` posteriores son mutuamente consistentes según
  INV-3; y (2) **no** existe ningún evento `balance` que reduzca `locked` sin el
  correspondiente incremento de `filledWei` en el evento `order` del mismo fill (estado
  posterior al settlement atómico, INV-4)

### Escenario 9 (borde): Hueco de secuencia [AT-09-04-09]
- Dado A recibió eventos hasta `sequence = s` **en el canal `orders`**
- Cuando detecta que el siguiente evento **del mismo canal** trae `sequence = s+2` (hueco)
- Entonces A debe re-sincronizar (reconsultar REST o re-suscribirse); el contrato garantiza
  que tras re-sincronizar el estado es consistente
- Y un evento de **otro** canal (`balances`/`withdrawals`) con `sequence` distinta no se
  interpreta como hueco (secuencia por canal, RN-8)

### Escenario 10 (idempotencia de cliente): Reaplicar evento [AT-09-04-10]
- Dado A recibió un evento `order` con `orderId: X`, `status: "FILLED"`, `sequence: s`
- Cuando, por una retransmisión **dentro de la misma conexión**, recibe de nuevo un evento
  con `sequence ≤ s` para `X`
- Entonces aplicar el estado es idempotente: la copia local de la orden X no se corrompe ni
  retrocede de estado (RN-11)
- Y tras una **reconexión** la numeración del canal es **nueva** (no comparable con la de
  la conexión anterior): el cliente re-sincroniza por REST y no compara `sequence` entre
  conexiones (RN-8)

### Escenario 11 (seguridad): Expiración de token en sesión activa [AT-09-04-11]
- Dado A autenticada en el canal privado con un token de TTL corto
- Cuando el token expira con la conexión aún abierta
- Entonces el servidor emite `{ error: { code: "UNAUTHENTICATED" } }` y cierra el socket
  (código de cierre `4001` o equivalente); A debe reconectar y re-autenticar con un token
  fresco (RN-13)

### Escenario 12 (retiros): Canal de retiros refleja el ciclo de vida [AT-09-04-12]
- Dado A suscrito a `withdrawals`
- Cuando A solicita un retiro (`POST /withdrawals`, HU-09-01) y este avanza on-chain
- Entonces A recibe un evento `withdrawal` en cada transición: `PENDING` (al aceptar),
  `BROADCAST` (con `txHash` no nulo), y finalmente `CONFIRMED` o `FAILED`, con
  `amountMinUnit` como string y `confirmations` como **entero JSON** (RN-14)
- Y `failureReason` es no nulo (enum de HU-09-01 RN-18) **solo** en el evento con
  `status: "FAILED"`; en cualquier otro estado es `null` (RN-14)
- Y A **no** recibe eventos de retiros de otra cuenta (aislamiento, RN-3)

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-*) pasan
- [ ] Reglas de negocio RN-1..RN-15 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md)
- [ ] (si aplica) Adherencia verificada al estandar on-chain citado (N/A)
