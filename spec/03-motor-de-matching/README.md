# Épica 03 — Motor de Matching

## Objetivo

Especificar el **motor de matching** del único par de trading `ETH/USDC-mock`: la
estructura y mantenimiento del **orderbook**, el cruce de órdenes `LIMIT` y `MARKET`
respetando **prioridad precio-tiempo**, la emisión de **eventos de ejecución**
(trades/fills), la **prevención de auto-cruce** (self-trade) y la **persistencia y
recuperación** del libro tras un reinicio.

El motor es el componente que decide, de forma **determinista**, qué órdenes se cruzan,
en qué cantidad y a qué precio, y deja el libro en un estado íntegro (no cruzado, ordenado
por prioridad y respaldado por fondos bloqueados). Es el insumo del settlement (épica 05),
que aplica contablemente cada fill.

## Alcance

Dentro de alcance:

- **Estructura del orderbook**: lados `bids`/`asks`, niveles de precio ordenados y cola
  **FIFO** por secuencia de ingreso (`seq`) dentro de cada nivel (HU-03-01).
- **Inserción pasiva (resting)** de órdenes `LIMIT` sin contraparte cruzable (HU-03-02).
- **Matching `LIMIT` contra el libro**: cruce por prioridad precio-tiempo, fills totales y
  parciales, **precio de ejecución = precio de la orden pasiva (maker)** (HU-03-03).
- **Ejecución de órdenes `MARKET`**: consumo de liquidez del lado opuesto sin precio
  límite; manejo de libro insuficiente o vacío (HU-03-04).
- **Emisión de eventos de ejecución**: trade y order-update por cada cruce, con precio,
  cantidad, lados, referencias y secuencia monótona; actualización del estado del libro
  (HU-03-05).
- **Prevención de auto-cruce** (self-trade prevention) con **política de resolución
  fijada** (HU-03-06).
- **Persistencia y recuperación** consistente del orderbook tras reinicio (HU-03-07).

Fuera de alcance (de esta épica):

- Tipos de orden avanzados: `stop`, `OCO`, `iceberg`, `trailing`, `post-only`,
  `time-in-force` distintos del comportamiento por defecto. (Solo `LIMIT` y `MARKET`.)
- Múltiples pares de trading (solo `ETH/USDC-mock`).
- Validación de entrada / ciclo de vida administrativo de la orden (alta, consulta,
  cancelación explícita por el usuario, estados): **épica 04**.
- Cálculo y cobro de fees y la liquidación contable del fill: **épica 05**.
- Bloqueo/reserva de fondos y ledger de doble entrada: **épica 02**.
- Contrato de transporte (REST/WebSocket) de los eventos: **épica 09**.

## Historias de Usuario

| ID        | Título                                            | Resumen (una línea)                                                                          |
|-----------|---------------------------------------------------|---------------------------------------------------------------------------------------------|
| HU-03-01  | Estructura del orderbook                          | Representación por lado (bids/asks), niveles de precio ordenados y cola FIFO por `seq`.       |
| HU-03-02  | Inserción de orden limit pasiva (resting)         | Una `LIMIT` sin contraparte cruzable se inserta como pasiva respetando precio-tiempo.        |
| HU-03-03  | Matching de orden limit contra el libro           | Cruce de una `LIMIT` entrante contra el lado opuesto; fills totales/parciales; precio maker. |
| HU-03-04  | Ejecución de orden market                         | Consumo de liquidez del lado opuesto sin precio límite; libro insuficiente/vacío.            |
| HU-03-05  | Emisión de eventos de ejecución                   | Trade/order-update por cada cruce con secuencia monótona; actualiza el estado del libro.     |
| HU-03-06  | Prevención de auto-cruce (self-trade prevention)  | Una orden no se ejecuta contra otra de la misma cuenta; política de resolución fijada.       |
| HU-03-07  | Persistencia y recuperación del orderbook         | El libro se persiste y se reconstruye consistente tras reinicio, sin perder ni duplicar.     |

## Dependencias hacia otras épicas

- **Épica 00 — Fundaciones** (prevalece ante conflicto): glosario, activos y par
  (`activos-y-par-de-trading.md`), convenciones monetarias
  (`convenciones-monetarias.md`), modelo de errores (`modelo-de-errores.md`) e invariantes
  globales (`invariantes-globales.md`).
- **Épica 02 — Balances y ledger**: el motor presupone que la orden entrante llega con sus
  fondos **bloqueados/reservados** (disponible→bloqueado) y que cada fill se consuma vía el
  ledger de doble entrada. La no-negatividad y la conservación las garantiza esa épica.
- **Épica 04 — Gestión de órdenes**: realiza la validación de entrada (auth, esquema,
  enums, reglas del par, idempotencia de `clientOrderId`, fondos) **antes** de entregar la
  orden al motor, y administra el ciclo de vida y la representación de estados.
- **Épica 05 — Settlement y fees**: consume los eventos de fill que emite esta épica para
  liquidar contablemente y cobrar las fees maker/taker.
- **Épica 09 — API HTTP/WebSocket**: transporta hacia los clientes los eventos de
  ejecución y los snapshots/diffs del orderbook que esta épica produce.

## Invariantes y reglas clave de la épica

- **INV-7 (integridad del orderbook + prioridad precio-tiempo)** es el invariante central:
  el libro está ordenado por prioridad precio-tiempo, **nunca queda cruzado**
  (`best_bid < best_ask` cuando ambos lados existen) y todo remanente abierto está
  respaldado por fondos bloqueados.
- **Prioridad precio-tiempo**: mejor precio primero (bid más alto / ask más bajo); a igual
  precio, FIFO por **secuencia de ingreso** monótona asignada por el motor (la secuencia,
  no el timestamp de pared, es el desempate determinista).
- **Precio de ejecución = precio de la orden pasiva (maker)**. La mejora de precio (price
  improvement) beneficia al taker.
- **Conversión y redondeo** (`convenciones-monetarias.md`): `quote_min = floor(q_wei ×
  price_min / 10^18)`; mismo `quote_min` para ambas patas; enteros de unidad mínima; **sin
  floats**. El cobro de fees (ceil) y la liquidación los realiza la épica 05.
- **INV-4 (atomicidad)**: cada fill y la actualización del libro se aplican “todo o nada”;
  no hay estado parcial observable.
- **INV-8 (persistencia y recuperación)**: orderbook, balances y ledger sobreviven al
  reinicio y se reconstruyen de forma consistente, preservando la prioridad y sin perder ni
  duplicar órdenes ni eventos.
- **Determinismo**: ante la misma secuencia de órdenes de entrada, el motor produce
  exactamente los mismos fills, precios, cantidades y estado de libro. Toda regla
  cuantitativa usa aritmética entera exacta sobre unidades mínimas.

## Reglas transversales de la épica

Estas reglas aplican a **todas** las HU de la épica y anclan el determinismo y la
integridad del libro en un modelo de ejecución concreto.

- **RT-1 (modelo de ejecución serializada por par).** El motor es **lógicamente
  single-threaded por par de trading**: en cualquier instante, una sola operación
  (inserción, matching, cancelación entregada por la épica 04) se procesa sobre el
  orderbook `ETH/USDC`. Cada operación se aplica **completa** —incluyendo todos sus fills,
  la emisión de sus eventos y la actualización del libro— **antes** de comenzar la
  siguiente. **No existe interleaving de fills** entre dos órdenes concurrentes. Las
  implementaciones que usen concurrencia deben **serializar** el acceso al libro (lock o
  cola por par) antes de entregar la operación al motor. Sin este modelo, INV-4 (atomicidad)
  e INV-7 (integridad/prioridad) no serían evaluables bajo carga concurrente: el resultado
  de N órdenes enviadas en paralelo debe ser equivalente a **alguna permutación serial
  válida** de esas órdenes, y en todo punto observable el libro cumple INV-7.
- **RT-2 (tres contadores independientes: `seq`, `sequence` de eventos y número de
  trade).** El motor mantiene **tres** contadores enteros **separados**:
  - **`seq` (prioridad de órdenes)** — clave de desempate FIFO dentro de un nivel de precio
    (HU-03-01 RN-5). Se incrementa **solo** cuando una orden se vuelve **pasiva** (se posa
    en el libro). Es estrictamente monótono y único; **no** se exige contigüidad (es una
    clave de orden, no un stream de eventos).
  - **`sequence` (eventos de ejecución)** — numeración global de los eventos `trade` /
    `order-update` / `book-update` (HU-03-05 RN-2/RN-7). Se incrementa al **emitir cada
    evento**; es estrictamente monótono, **contiguo (sin huecos ni repeticiones)** y único.
  - **`sequence` (número de trade)** — contador **propio de los trades** (HU-05-03 RN-3),
    insumo del `tradeId` (`"T-" + sequence`). Es global, estrictamente creciente y comienza
    en 1; bajo operación normal es contiguo, y solo puede quedar un hueco si el settlement
    de un fill se revierte (HU-05-01 AT-05-01-06). Es **independiente** de la numeración de
    eventos del motor y de las secuencias por canal WebSocket (RG-API-7).

  Como son independientes, posar una orden pasiva (que consume un `seq`) **no** consume
  valores de las otras dos secuencias; cada contador avanza **solo** por su propia causa
  (`seq` al posar pasivas, la `sequence` de eventos al emitir cada evento, el número de
  trade al producirse cada fill). Los tres se **persisten** y **retoman** desde su último
  valor tras un reinicio (HU-03-07 RN-8); ninguno reutiliza valores ya asignados.
