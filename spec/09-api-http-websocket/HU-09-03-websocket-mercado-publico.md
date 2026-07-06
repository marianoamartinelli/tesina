# HU-09-03 — WebSocket de mercado (público)

- **Epica:** 09 — API HTTP/WebSocket
- **Actor / rol:** Cliente web/mobile (anónimo o autenticado) / Sistema (servidor WS)
- **Prioridad:** Alta
- **Dependencias:** HU-09-01 (contrato REST: estructuras compartidas), HU-09-05 (modelo de
  errores), HU-03-* (orderbook persistente, matching, trades)
- **Estándares de dominio aplicables:** N/A on-chain

## Historia
Como cliente web/mobile, quiero suscribirme a un canal WebSocket **público** que me entregue
un **snapshot** inicial del orderbook y luego **actualizaciones incrementales**, junto con
un **stream de trades**, para mostrar el mercado en tiempo real sin polling.

## Contexto y alcance
Esta HU define el **contrato del canal público**: protocolo de suscripción, formato de
snapshot y deltas del orderbook, formato de eventos de trade, y la **numeración de
secuencia** para que el cliente detecte huecos y se re-sincronice. El canal es **público**:
no requiere autenticación y solo expone datos de mercado agregados (nunca identidades de
cuenta). El comportamiento del matching que **genera** estos eventos es de HU-03-*; aquí se
fija cómo se **transmiten**.

Supuestos: un único par `ETH-USDC`. Mensajes JSON de texto. Todos los montos como string de
entero en unidad mínima (`00-fundaciones/convenciones-monetarias.md` §5).

## Reglas de negocio e invariantes

1. **RN-1 (sin autenticación):** el canal público no requiere token. No expone `accountId`,
   `orderId` ni dato alguno que identifique al dueño de una orden; solo precios y cantidades
   agregadas y trades anónimos.
2. **RN-2 (suscripción):** el cliente envía
   `{ "type": "subscribe", "channel": "orderbook"|"trades", "symbol": "ETH-USDC",
   "depth": <n>? }` (`depth` opcional, solo aplica a `orderbook`). El servidor confirma con
   `{ "type": "subscribed", "channel", "symbol" }`.
3. **RN-3 (snapshot inicial — orderbook):** al suscribirse a `orderbook`, el primer mensaje
   es un snapshot:
   `{ "type": "snapshot", "channel": "orderbook", "symbol": "ETH-USDC", "sequence": <n>,
   "bids": [[priceMin, quantityWei], ...], "asks": [[priceMin, quantityWei], ...] }`.
   `bids` ordenados por `priceMin` descendente; `asks` ascendente; agregados por nivel de
   precio (INV-7). Sin niveles cruzados (`best_bid < best_ask`). Si un lado está vacío su
   array es `[]`.
   **Profundidad del snapshot:** el snapshot emite como máximo `depth` niveles por lado, con
   el mismo `depth` (default **50**, máx **200**) del endpoint REST `GET /market/orderbook`.
   Un cliente que necesite más profundidad debe consultar REST. La profundidad limita
   **únicamente** el snapshot inicial: las **deltas** posteriores (RN-4) se emiten para
   **todo** cambio del libro completo, incluso en niveles fuera del top-`depth`. Un cliente
   que mantiene un espejo top-N del libro descarta localmente las entradas de niveles fuera
   de su profundidad.
4. **RN-4 (deltas — orderbook):** tras el snapshot, los cambios se emiten como
   `{ "type": "update", "channel": "orderbook", "symbol", "sequence": <n>, "bids": [...],
   "asks": [...] }` donde cada entrada `[priceMin, quantityWei]` representa el **nuevo total
   del nivel**. `quantityWei == "0"` significa que el nivel fue **eliminado** (sin
   profundidad). El cliente aplica el delta reemplazando el nivel.
   **Atomicidad del delta:** todas las modificaciones de niveles derivadas de un **mismo
   evento de matching** (un fill que barre uno o varios niveles, un alta o una cancelación)
   se emiten en **un único** mensaje `update` (mismo `sequence`, todos los niveles afectados
   en el mismo frame WS). El cliente aplica el delta como una operación atómica y nunca
   observa estados intermedios cruzados o inconsistentes del libro (coherente con INV-4).
5. **RN-5 (secuencia monotónica):** la `sequence` del canal `orderbook` es **única y global
   del libro** —la misma numeración que expone el snapshot REST `GET /market/orderbook`
   (RN-12)—, entera, estrictamente creciente y **contigua** para todo suscriptor (el
   snapshot trae la `sequence` base vigente; cada update la incrementa en 1). Si el cliente
   detecta un hueco (sequence no contigua), debe descartar su estado y re-suscribirse para
   obtener un nuevo snapshot (RG-API-7).
6. **RN-6 (stream de trades):** al suscribirse a `trades`, el servidor emite por cada fill
   `{ "type": "trade", "channel": "trades", "symbol", "sequence": <n>, "tradeId",
   "priceMin", "quantityWei", "takerSide", "timestamp" }`. `takerSide ∈ {BUY, SELL}`
   indica el lado de la orden taker. `timestamp` ISO-8601 UTC.
7. **RN-7 (un trade por fill):** cada evento `trade` corresponde a un fill atómico (INV-4);
   un fill parcial que produce varios cruces genera un evento por cruce, en orden de
   ejecución (prioridad precio-tiempo, INV-7).
8. **RN-8 (orden de entrega):** los mensajes de una suscripción se entregan en orden de
   `sequence`; el cliente puede confiar en la monotonicidad para ordenar/aplicar.
9. **RN-9 (desuscripción):** el cliente envía
   `{ "type": "unsubscribe", "channel", "symbol" }` y el servidor deja de emitir esa
   suscripción y confirma con `{ "type": "unsubscribed", "channel", "symbol" }`.
10. **RN-10 (mensaje inválido):** un mensaje malformado, con `type` desconocido, `channel`
    no soportado o `symbol` distinto de `ETH-USDC` produce un mensaje de error
    `{ "error": { "code": "VALIDATION_ERROR", ... } }` por el mismo socket, sin cerrar la
    conexión necesariamente (HU-09-05). No existen otros símbolos (par único).
11. **RN-11 (serialización):** `priceMin`, `quantityWei` y todo monto se serializan como
    **string** que matchea `^(0|[1-9][0-9]*)$`. Nunca número JSON.
12. **RN-12 (consistencia con REST):** el snapshot WS con `sequence = N` y el estado que
    devolvería `GET /market/orderbook` en el instante en que el servidor asignó `sequence = N`
    son **equivalentes** (consistencia **fuerte por número de secuencia**, no eventual).
    Aplicar las deltas posteriores (`sequence > N`) sobre ese snapshot reproduce el estado
    actual del libro que devolvería el endpoint REST. Esto hace el invariante testeable:
    tomar el snapshot WS con `sequence = N` y compararlo con el snapshot REST del mismo
    `sequence` debe dar el mismo libro (a igual `depth`).
13. **RN-13 (alcance de la secuencia):** la `sequence` es **independiente por canal y por
    símbolo** (RG-API-7): el canal `orderbook` de `ETH-USDC` tiene su propia secuencia
    continua (la numeración global del libro, RN-5); el canal `trades`, la suya. Un cliente suscrito a ambos **no** debe comparar
    secuencias entre canales: un hueco se detecta **solo dentro del mismo canal**. Recibir un
    mensaje de otro canal con `sequence` distinta **no** constituye un hueco.
14. **RN-14 (heartbeat / detección de conexión muerta):** el servidor envía periódicamente
    el mensaje JSON de aplicación `{ "type": "ping" }` (intervalo recomendado **30 s**) y el
    cliente debe responder `{ "type": "pong" }` dentro de **10 s**. Si el servidor no recibe
    `pong` dentro de la ventana, **cierra** la conexión y libera las suscripciones
    asociadas. El `ping` JSON de aplicación es **obligatorio** (mecanismo normativo y
    testeable del contrato); los frames de control ping/pong de WebSocket RFC 6455 quedan
    **permitidos como mecanismo adicional**, pero **nunca como sustituto** del `ping` JSON.
    Aplica también al canal privado (HU-09-04).
15. **RN-15 (bootstrap REST + WS — sincronización sin depender del snapshot WS):** para
    inicializar una copia local del libro usando el snapshot REST (p. ej. con más
    profundidad), el cliente: (1) se suscribe al canal `orderbook` por WS y **acumula** las
    deltas en un buffer; (2) consulta `GET /market/orderbook?depth=N` y obtiene `sequence = S`;
    (3) aplica el snapshot REST como base; (4) aplica del buffer las deltas con `sequence > S`
    y **descarta** las de `sequence ≤ S`; (5) continúa aplicando deltas en vivo. Este
    procedimiento es determinista y reproduce el mismo libro que el flujo de snapshot WS puro.

## Criterios de aceptación (DoD)

### Escenario 1: Snapshot inicial del orderbook [AT-09-03-01]
- Dado un orderbook con órdenes en ambos lados
- Cuando un cliente envía `{ type: "subscribe", channel: "orderbook", symbol: "ETH-USDC" }`
- Entonces recibe primero `{ type: "subscribed", ... }` y luego un `snapshot` con `bids` y
  `asks` agregados por nivel, `bids` descendente, `asks` ascendente, y un `sequence` inicial
- Y `best_bid < best_ask` (libro no cruzado, INV-7)
- Y todos los `priceMin`/`quantityWei` son strings que matchean `^(0|[1-9][0-9]*)$`

### Escenario 2: Actualización incremental al ingresar una orden [AT-09-03-02]
- Dado un cliente suscrito al orderbook que ya recibió el snapshot con `sequence = s`
- Cuando ingresa una nueva orden limit que agrega profundidad a un nivel de bid
- Entonces el cliente recibe un `update` con `sequence = s+1` que contiene ese nivel con su
  **nuevo total** `quantityWei`
- Y aplicar el delta sobre el snapshot reproduce el estado del libro

### Escenario 3 (borde): Eliminación de un nivel [AT-09-03-03]
- Dado un nivel de precio con una sola orden abierta
- Cuando esa orden se cancela o se llena por completo y el nivel queda sin profundidad
- Entonces el cliente recibe un `update` con ese `priceMin` y `quantityWei: "0"`
- Y el cliente elimina ese nivel de su copia local

### Escenario 4: Stream de trades [AT-09-03-04]
- Dado un cliente suscrito al canal `trades`
- Cuando se produce un fill por cruce de una orden taker BUY contra un ask resting
- Entonces el cliente recibe `{ type: "trade", tradeId, priceMin, quantityWei,
  takerSide: "BUY", timestamp, sequence }` con montos como strings

### Escenario 5 (borde): Varios cruces en orden de prioridad [AT-09-03-05]
- Dado un orderbook con dos asks al mismo nivel (FIFO) y otro nivel peor
- Cuando una orden taker BUY grande cruza ambos niveles
- Entonces el cliente recibe un evento `trade` por cada cruce, en orden de prioridad
  precio-tiempo (INV-7), con `sequence` creciente y contigua

### Escenario 6 (error de sincronía): Detección de hueco de secuencia [AT-09-03-06]
- Dado un cliente que recibió hasta `sequence = s` **en el canal `orderbook`**
- Cuando, por pérdida de mensajes, el siguiente mensaje **del mismo canal** trae
  `sequence = s+2` (hueco)
- Entonces el cliente debe descartar su estado y re-suscribirse a ese canal, y el servidor
  responde con un nuevo `snapshot` con `sequence` actualizada (RG-API-7)
- Y recibir un mensaje de **otro** canal (p. ej. `trades`) con una `sequence` distinta **no**
  se interpreta como hueco (la secuencia es por canal, RN-13)

### Escenario 7: Canal público sin autenticación [AT-09-03-07]
- Dado un cliente **sin** token
- Cuando se suscribe al canal público `orderbook`/`trades`
- Entonces la suscripción es aceptada y recibe los datos de mercado
- Y ningún mensaje del canal público contiene `accountId` ni `orderId` ni identidad de
  dueño de orden

### Escenario 8: Desuscripción [AT-09-03-08]
- Dado un cliente suscrito a `trades`
- Cuando envía `{ type: "unsubscribe", channel: "trades", symbol: "ETH-USDC" }`
- Entonces recibe `{ type: "unsubscribed", ... }` y deja de recibir eventos `trade`

### Escenario 9 (error): Mensaje de suscripción inválido [AT-09-03-09]
- Dado una conexión WS abierta
- Cuando el cliente envía `{ type: "subscribe", channel: "candles", symbol: "ETH-USDC" }`
  (canal no soportado) o `symbol: "BTC-USDC"` (par inexistente)
- Entonces recibe `{ error: { code: "VALIDATION_ERROR", ... } }` por el mismo socket
- Y no se crea ninguna suscripción

### Escenario 10: Reconexión produce nuevo snapshot [AT-09-03-10]
- Dado un cliente que se desconecta y reconecta
- Cuando vuelve a suscribirse al `orderbook`
- Entonces recibe un nuevo `snapshot` completo con la `sequence` vigente, no un delta
  parcial

### Escenario 11: Profundidad del snapshot WS [AT-09-03-11]
- Dado un orderbook con más de 50 niveles activos por lado
- Cuando un cliente envía `{ type: "subscribe", channel: "orderbook", symbol: "ETH-USDC",
  depth: 50 }`
- Entonces el `snapshot` recibido trae a lo sumo 50 niveles por lado (RN-3)
- Y suscribirse sin `depth` aplica el default 50; `depth > 200` produce
  `{ error: { code: "VALIDATION_ERROR" } }` por el socket
- Y las deltas posteriores **no** se recortan por `depth`: se emiten para todo cambio del
  libro (también en niveles fuera del top-50); el cliente que mantiene un espejo top-50
  descarta localmente los niveles fuera de su profundidad (RN-3)

### Escenario 12: Heartbeat ping/pong [AT-09-03-12]
- Dado una conexión WS abierta
- Cuando el servidor envía `{ type: "ping" }` y el cliente **no** responde `{ type: "pong" }`
  dentro de la ventana (10 s)
- Entonces el servidor cierra la conexión y libera las suscripciones (RN-14)
- Y un cliente que sí responde `pong` mantiene la conexión y sus suscripciones

### Escenario 13: Bootstrap REST + WS [AT-09-03-13]
- Dado un cliente que se suscribe al canal `orderbook` y acumula deltas en buffer
- Cuando consulta `GET /market/orderbook?depth=100` y obtiene `sequence = S`, aplica el
  snapshot REST y luego aplica del buffer solo las deltas con `sequence > S`
- Entonces su copia local del libro es idéntica a la que obtendría por el snapshot WS puro
  más sus deltas (RN-15)

### Escenario 14: Atomicidad de la delta de un fill multi-nivel [AT-09-03-14]
- Dado un orderbook con varios niveles de ask y un cliente suscrito a `orderbook`
- Cuando una orden taker BUY grande barre **varios** niveles de ask en un solo evento de
  matching
- Entonces el cliente recibe **un único** mensaje `update` (mismo `sequence`) con **todos**
  los niveles afectados, y nunca observa un estado intermedio cruzado (RN-4, INV-4)

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-*) pasan
- [ ] Reglas de negocio RN-1..RN-15 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md)
- [ ] (si aplica) Adherencia verificada al estandar on-chain citado (N/A)
