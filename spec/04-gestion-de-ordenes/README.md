# Épica 04 — Gestión de Órdenes

## Objetivo de la épica

Especificar el **ciclo de vida completo de una orden desde la perspectiva del usuario
(trader)**: el alta de órdenes `LIMIT` y `MARKET` con validación de entrada y reserva de
fondos previa, la cancelación de órdenes abiertas o parcialmente ejecutadas (con
liberación de la reserva del remanente), la máquina de estados de la orden y sus
transiciones válidas, y las consultas de órdenes abiertas e historial.

Esta épica es una **capa de orquestación**: no decide cómo se cruzan las órdenes (eso es
`03-motor-de-matching`) ni cómo se mueven contablemente los fondos en un fill (eso es
`02-balances-y-ledger` y `05-settlement-y-fees`). Su responsabilidad es: recibir el
pedido, validarlo de forma determinista, **reservar (bloquear) los fondos correctos antes
de enviar la orden al matching**, registrar el estado resultante y exponerlo en consultas.

## Alcance

### Dentro de alcance

- Alta de órdenes **LIMIT** (`side`, `priceMin`, `quantityWei`): validación, reserva de
  fondos y entrega al matching engine.
- Alta de órdenes **MARKET** por **cantidad** (`quantityWei`) o por **monto**
  (`quoteOrderQty`): validación, reserva de fondos, validación de liquidez.
- **Validaciones de orden**: lado/tipo, tick size de precio, lot size de cantidad, mínimo
  notional, positividad, idempotencia por `clientOrderId`, fondos suficientes, y la
  **precedencia determinista** entre ellas.
- **Cancelación** de órdenes `OPEN` / `PARTIALLY_FILLED`; liberación de la reserva del
  remanente; rechazo de cancelaciones de órdenes no cancelables.
- **Máquina de estados** de la orden (`NEW`, `OPEN`, `PARTIALLY_FILLED`, `FILLED`,
  `CANCELLED`, `REJECTED`) y sus transiciones válidas.
- **Consulta de órdenes abiertas** (estado, cantidad ejecutada y remanente).
- **Consulta de historial** de órdenes finalizadas, filtrable por estado y período.

### Fuera de alcance

- Algoritmo de cruce, prioridad precio-tiempo, generación de fills y persistencia del
  orderbook → `03-motor-de-matching`.
- Movimiento contable del fill, cálculo y cobro de fees, atomicidad del settlement →
  `05-settlement-y-fees` y `02-balances-y-ledger`.
- Tipos de orden avanzados (stop, OCO, iceberg, trailing, post-only, time-in-force
  configurable distinto del comportamiento fijado aquí) → fuera del alcance del proyecto.
- Contrato HTTP/WebSocket concreto (rutas, nombres exactos de campos, paginación) →
  `09-api-http-websocket`. Esta épica fija la **semántica**; aquélla, la **forma**.
- KYC/AML, múltiples pares, múltiples redes.

## Historias de Usuario

| ID         | Título                                  | Resumen (una línea)                                                                 |
|------------|-----------------------------------------|------------------------------------------------------------------------------------|
| HU-04-01   | Colocar orden limit                     | El trader coloca una orden limit; se valida y se reservan fondos antes del matching.|
| HU-04-02   | Colocar orden market                    | El trader coloca una orden market por cantidad o monto; se valida fondos y liquidez.|
| HU-04-03   | Validaciones de orden                   | Reglas y precedencia determinista de validación del alta de órdenes.                |
| HU-04-04   | Cancelar orden                          | El trader cancela una orden abierta/parcial; se libera la reserva del remanente.    |
| HU-04-05   | Ciclo de vida y estados                 | Máquina de estados de la orden y transiciones válidas.                              |
| HU-04-06   | Consultar órdenes abiertas              | El trader lista sus órdenes abiertas con estado y remanente.                        |
| HU-04-07   | Consultar historial de órdenes          | El trader lista sus órdenes finalizadas, filtrable por estado/período.              |

## Dependencias hacia otras épicas

- **00-fundaciones** — glosario, activos/par (tick `10000`, lot `10^14`, min notional
  `10000000`), convenciones monetarias (enteros de unidad mínima, `floor`/`ceil`,
  serialización string), modelo de errores e invariantes globales. **Prevalece** ante
  cualquier conflicto.
- **01-cuentas-y-autenticación** — identidad del trader, autenticación y autorización de
  la operación (toda HU de esta épica exige un trader autenticado).
- **02-balances-y-ledger** — bloqueo/liberación de fondos (reserva), partición
  `disponible + bloqueado = total`, asientos del ledger de doble entrada.
- **03-motor-de-matching** — recepción de la orden, prioridad precio-tiempo, generación
  de fills, descarte del remanente market, `SELF_TRADE_BLOCKED`, `MARKET_NO_LIQUIDITY`,
  persistencia del orderbook.
- **05-settlement-y-fees** — efecto contable de cada fill (consumo de la reserva, cobro
  de fees maker/taker) que esta épica desencadena pero no implementa.

## Reglas e invariantes clave de la épica

- **RE-1 — Reserva antes del matching.** Ninguna orden llega al matching engine sin que
  sus fondos hayan sido **bloqueados** previamente. La transición es
  `disponible −= R; bloqueado += R` (INV-3), con `R` la reserva del lado/tipo:
  - **LIMIT BUY:** `R = floor(quantityWei × priceMin / 10^18)` USDC-min (notional al
    precio límite).
  - **LIMIT SELL:** `R = quantityWei` wei (ETH).
  - **MARKET BUY por `quoteOrderQty`:** `R = quoteOrderQty` USDC-min.
  - **MARKET BUY por `quantityWei`:** `R =` costo en quote de barrer los asks vigentes
    hasta `quantityWei` (snapshot del libro; lo calcula el matching, épica 03).
  - **MARKET SELL por `quantityWei`:** `R = quantityWei` wei.
  - **MARKET SELL por `quoteOrderQty`:** `R =` base en wei necesaria para obtener
    `quoteOrderQty` de quote barriendo los bids vigentes (snapshot).

  > **Snapshot atómico (formas que dependen del libro).** Para `MARKET BUY por quantityWei`
  > y `MARKET SELL por quoteOrderQty`, `R` se calcula sobre un **snapshot atómico** del lado
  > opuesto tomado al procesar el alta, en el mismo punto en que se evalúa la precondición de
  > liquidez (RE-4 paso 6) e **inmediatamente antes** de bloquear fondos. **No hay
  > dependencia circular:** primero se lee el libro y se calcula `R`, y recién después se
  > bloquea. El protocolo de snapshot lo provee la épica 03. Si entre el snapshot y la
  > ejecución el libro cambió y hay **menos** liquidez, el remanente no ejecutado se descarta
  > y el sobrante reservado se libera (RE-3, ver RN-8 de HU-04-02). Si `R` resultara
  > insuficiente (resultó más caro de lo estimado), la orden ejecuta solo hasta donde alcanza
  > la reserva y el resto se descarta; nunca se bloquea de más sin haberlo reservado (INV-2).
- **RE-2 — Las fees no se reservan aparte.** La fee se cobra **en el activo recibido** y
  sale de lo recibido en cada fill (`fee_base = ceil(q_wei × fee_bps / 10000)` en ETH para
  el comprador; `fee_quote = ceil(quote_min × fee_bps / 10000)` en USDC para el vendedor).
  Por lo tanto la reserva de RE-1 **no** suma fee alguna.
- **RE-3 — Liberación del sobrante.** Todo monto reservado que no se consuma se **libera**
  (`bloqueado −= s; disponible += s`): al matchear a mejor precio que el límite (BUY), al
  cancelar el remanente, o al descartar el remanente de una market. Conserva el total
  (INV-3) y respeta INV-1 (la reserva nunca creó ni destruyó valor).
- **RE-4 — Precedencia de validación determinista** (deriva de
  `00-fundaciones/modelo-de-errores.md §4`; esta épica la **instancia** con dos precisiones
  de dominio: la precondición de liquidez de market se evalúa **antes** de reservar fondos, y
  la detección de self-trade ocurre **durante** el barrido, posterior a la reserva. Un solo
  error por respuesta, el primero que aplique):
  0. **rate limiting** (capa de red/middleware): si la cuenta supera el límite ⇒
     `RATE_LIMITED` (429), antes de cualquier otra evaluación y sin crear orden ni reservar
     (RE-10; el límite concreto en HU-09-*);
  1. autenticación (`UNAUTHENTICATED`) → autorización (`UNAUTHORIZED`);
  2. esquema/tipos del payload (`VALIDATION_ERROR`, incl. patrón `^(0|[1-9][0-9]*)$` y forma
     única de tamaño en market);
  3. enums y combinaciones (`INVALID_SIDE`, `INVALID_ORDER_TYPE`, `PRICE_REQUIRED`,
     `PRICE_NOT_ALLOWED`);
  4. reglas del par (`INVALID_PRICE_TICK`, `INVALID_LOT_SIZE`, `BELOW_MIN_NOTIONAL`);
  5. idempotencia (`DUPLICATE_CLIENT_ORDER_ID`);
  6. **liquidez de market (precondición de solo lectura):** si la orden es `MARKET` y el lado
     opuesto del libro está **vacío** ⇒ `MARKET_NO_LIQUIDITY` (422). Se evalúa **antes** de
     reservar fondos (lectura del libro sin mover balances); la orden queda `REJECTED` **sin**
     haber reservado nada. Por eso, ante libro vacío + fondos insuficientes, **prevalece**
     `MARKET_NO_LIQUIDITY` (no `INSUFFICIENT_FUNDS`);
  7. fondos (`INSUFFICIENT_FUNDS`);
  8. matching durante el barrido: `SELF_TRADE_BLOCKED` (422). Si se detecta tras haber
     reservado (paso 7), la reserva se **revierte atómicamente** antes de responder (ver
     RE-11 y HU-04-01/02).

  > Nota de precedencia: la única diferencia respecto del orden recomendado por
  > `00-fundaciones §4` (que ubica todo "matching" al final) es haber separado la
  > **precondición de liquidez** (`MARKET_NO_LIQUIDITY` por lado vacío, paso 6, de solo
  > lectura y previa a fondos) de la **detección de self-trade** durante el barrido (paso 8).
  > Esto es legítimo —`00-fundaciones §4` declara su orden como *recomendado* y habilita a
  > cada épica a instanciarlo— y necesario para que un `REJECTED` por falta de liquidez nunca
  > deje fondos reservados (coherente con HU-04-05 RN-5). Se coloca tras la idempotencia
  > (paso 5) porque ésta es un chequeo barato a nivel de solicitud que debe preceder a la
  > lectura del estado del mercado.
- **RE-5 — Idempotencia de alta.** Si el trader envía un `clientOrderId` ya usado por su
  cuenta, el alta se rechaza con `DUPLICATE_CLIENT_ORDER_ID` (409) y **no** crea una
  segunda orden ni reserva fondos. La unicidad es **permanente por cuenta** (lifetime): un
  `clientOrderId` **no** se puede reutilizar aunque la orden original ya esté en estado
  terminal (`FILLED`, `CANCELLED` o `REJECTED`). El **alcance** es por cuenta: dos cuentas
  distintas pueden usar el mismo `clientOrderId` sin conflicto (el índice de unicidad es
  `(accountId, clientOrderId)`, no global).
- **RE-6 — Estados y terminalidad.** Estados: `NEW` (transitorio interno), `OPEN`,
  `PARTIALLY_FILLED`, `FILLED`, `CANCELLED`, `REJECTED`. `FILLED`, `CANCELLED` y `REJECTED`
  son **terminales** (sin transiciones salientes). Las market son **immediate-or-cancel**:
  nunca descansan; su remanente no ejecutado se descarta (`CANCELLED` si hubo ejecución
  parcial; `REJECTED` con `MARKET_NO_LIQUIDITY` si no hubo ninguna).
- **RE-7 — Aislamiento por cuenta.** Un trader solo puede consultar/cancelar **sus**
  órdenes. Referir una orden ajena o inexistente devuelve `ORDER_NOT_FOUND` (404), sin
  filtrar la existencia de órdenes de terceros.
- **RE-8 — Dinero entero y serializado.** Todo `priceMin`, `quantityWei`, `quoteOrderQty`,
  cantidad ejecutada/remanente, notional, reserva y fee es **entero de unidad mínima** y
  viaja en la API como **string** `^(0|[1-9][0-9]*)$`. Prohibido floats binarios.
- **RE-9 — Respaldo de remanentes (INV-7).** El `bloqueado` de una cuenta cubre en todo
  momento el remanente no ejecutado de todas sus órdenes abiertas (más los retiros en
  proceso). Cancelar/llenar ajusta reserva y remanente de forma consistente. La épica
  **rastrea la reserva efectivamente bloqueada por cada orden** (`reservaOrden`), actualizada
  fill a fill; la liberación en cancelación libera ese saldo exacto (no un valor recomputado
  por fórmula), evitando residuos por subaditividad del `floor` (ver HU-04-04 RN-3).
- **RE-10 — Rate limiting.** Toda operación de alta y de cancelación está sujeta a control de
  tasa. Si la cuenta supera el límite configurado, se rechaza con `RATE_LIMITED` (429,
  `details = { retryAfterSeconds }`) **sin** crear orden, reservar fondos ni alterar estado.
  Se evalúa en la capa de red/middleware, **antes** de la autenticación (RE-4 paso 0). El
  límite concreto (requests por segundo por cuenta) se fija en `09-api-http-websocket`.
- **RE-11 — Prevención de self-trade (STP) en el barrido.** El modo de STP de esta épica es
  **cancelar el remanente del taker** (*expire-taker*): durante el barrido, cuando el
  siguiente maker cruzable es una orden **propia** del taker, el barrido **se detiene** en esa
  orden y los fills previos contra terceros son **definitivos**. El remanente no ejecutado
  **no** descansa (para no dejar un libro cruzado/bloqueado contra la propia orden, INV-7) y
  se descarta, liberando su reserva (RE-3). Resultado:
  - **sin** fills previos (la orden propia es la primera liquidez cruzable) ⇒
    `SELF_TRADE_BLOCKED` (422), orden `REJECTED`, reserva (si se tomó) revertida atómicamente;
  - **con** fills previos contra terceros ⇒ la orden termina `FILLED` (si completó antes de
    tocar la propia) o `CANCELLED` con `executedQty > 0` (remanente descartado); la respuesta
    es **exitosa** (no un error 422).
- **RE-12 — Persistencia de rechazos.** Solo las órdenes rechazadas por la **capa de
  matching** se persisten como `REJECTED` y aparecen en el historial (HU-04-07):
  `MARKET_NO_LIQUIDITY` (libro vacío, RE-4 paso 6) y `SELF_TRADE_BLOCKED` (barrido, RE-4 paso
  8). Los rechazos de validación, idempotencia y fondos (RE-4 pasos 1–5 y 7, p. ej.
  `INVALID_PRICE_TICK`, `DUPLICATE_CLIENT_ORDER_ID`, `INSUFFICIENT_FUNDS`) **no** se persisten
  como órdenes: solo devuelven el error, sin dejar registro de orden.

> **Nota (división exacta `lot × tick`).** Como `lot_size = 10^14` wei y `tick_size = 10^4`
> USDC-min cumplen `lot_size × tick_size = 10^18`, para **toda orden válida** (`quantityWei`
> múltiplo de `10^14`, `priceMin` múltiplo de `10^4`) el producto `quantityWei × priceMin` es
> divisible **exactamente** por `10^18`: `floor(quantityWei × priceMin / 10^18)` no deja
> residuo. Esto aplica a la reserva `LIMIT BUY`, al mínimo notional y a la liberación en
> cancelación. En cambio, las cantidades de **fill intermedias** (p. ej. el último nivel de
> un barrido) pueden **no** estar alineadas a lot; allí `floor()` sí puede producir residuo y
> debe aplicarse con rigor (big-integer; `00-fundaciones/convenciones-monetarias.md`).

> Ante cualquier conflicto entre esta épica y `00-fundaciones`, **prevalece
> `00-fundaciones`**.
