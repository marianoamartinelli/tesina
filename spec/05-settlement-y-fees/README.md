# Épica 05 — Settlement y Fees

Liquidación interna **atómica** de cada fill producido por el motor de matching y
**cálculo/cobro de fees** maker/taker, con registro inmutable de los trades ejecutados.
Esta épica consume los eventos de ejecución de la épica 03 y opera sobre el modelo de
balances/ledger de la épica 02; no decide *qué* matchea (eso es 03), sino *cómo se
liquida contablemente* cada cruce.

> Ante cualquier conflicto, prevalece `00-fundaciones` sobre esta épica.

---

## 1. Objetivo de la épica

Garantizar que, cuando dos órdenes se cruzan (un fill), el intercambio de **base** (ETH)
y **quote** (USDC-mock) entre comprador y vendedor se aplique **completo o nada** (sin
estado parcial observable), que las **fees maker/taker** se calculen de forma determinista
y en contra del usuario activo (redondeo `ceil`), que dichas fees se acrediten a la
**cuenta de fees del exchange (EX)** y que cada ejecución quede **registrada** de forma
inmutable y auditable. La conservación de fondos por activo (INV-1) debe mantenerse
exactamente: un fill solo **redistribuye** valor entre maker, taker y EX.

---

## 2. Alcance

### Dentro de alcance

- **Settlement interno atómico** del fill: consumo de `bloqueado`, acreditación de
  `disponible` de la contraparte y liberación del remanente bloqueado por mejora de precio
  (price improvement del **taker comprador LIMIT**; el excedente de `bloqueado` de órdenes
  **market** lo libera la épica 04 al terminar la orden, no esta épica — ver HU-05-01 RN-6).
- **Cálculo y aplicación de fees** diferenciadas maker (10 bps) / taker (20 bps), cobradas
  en el **activo recibido** por cada parte, con redondeo `ceil`.
- **Acreditación a la cuenta EX** del exchange (parte de la conservación de fondos).
- **Registro de trades**: una entrada inmutable por fill, con precio, cantidad, notional,
  fees, roles maker/taker y referencias a las órdenes.
- **Consulta del historial de trades/fills** del propio usuario, con montos brutos, fees y
  montos netos.

### Fuera de alcance

- **Qué órdenes cruzan y a qué precio** (prioridad precio-tiempo, selección de niveles):
  pertenece a `03-motor-de-matching`.
- **Bloqueo inicial de fondos al crear la orden** y **ciclo de vida/estados de la orden**:
  pertenece a `04-gestion-de-ordenes` (esta épica solo *consume* y *libera* lo bloqueado).
- **Estructura del ledger de doble entrada y de los balances** (definición): pertenece a
  `02-balances-y-ledger` (esta épica genera asientos conforme a ese modelo).
- **Settlement on-chain** (depósitos/retiros): épicas 07 y 08. El settlement de esta épica
  es **interno** (contable), nunca on-chain.
- **Rebates, fees por volumen, descuentos por tier, fees on-chain (gas)**: no se modelan.

---

## 3. Historias de Usuario

| ID        | Título                                   | Resumen (una línea)                                                                 |
|-----------|------------------------------------------|------------------------------------------------------------------------------------|
| HU-05-01  | Settlement atómico al match              | Al producirse un fill se transfieren base y quote entre comprador y vendedor de forma atómica, ajustando disponible/bloqueado. |
| HU-05-02  | Cálculo de fees maker/taker              | Cálculo y aplicación de fees diferenciadas maker/taker sobre cada fill, con redondeo `ceil`, acreditadas a la cuenta EX. |
| HU-05-03  | Registro de trades                       | Cada ejecución genera un registro de trade inmutable con precio, cantidad, fees, roles y referencias a las órdenes. |
| HU-05-04  | Consultar historial de trades            | El usuario consulta el historial de sus trades/fills con fees y montos netos.       |

---

## 4. Dependencias hacia otras épicas

- **02 — Balances y ledger:** modelo de `disponible`/`bloqueado`, asientos de doble
  entrada y existencia de la cuenta interna de fees del exchange (EX). El settlement
  produce asientos conforme a ese modelo.
- **03 — Motor de matching:** emite los **eventos de ejecución (fills)** que disparan el
  settlement, fijando contrapartes, **cantidad matcheada** `q_wei`, **precio de ejecución**
  (= precio de la orden **maker/resting**, por prioridad precio-tiempo), el **tipo de la
  orden taker** (`takerOrderType` ∈ {LIMIT, MARKET}) y, para taker comprador LIMIT, su
  **precio límite** (`price_limit_taker`). Además asigna la **identidad estable del fill**
  (`tradeId`/`sequence`) usada como clave de idempotencia y de ordenamiento (HU-05-01 RN-1,
  HU-05-03 RN-2/RN-3).
- **04 — Gestión de órdenes:** estados de orden, `clientOrderId`, bloqueo inicial de fondos
  al alta; el settlement actualiza el remanente y dispara transiciones de estado.
- **09 — API HTTP/WebSocket:** nombres de campos y endpoints concretos para la consulta de
  trades y la emisión de eventos de trade (esta épica fija la **semántica y las unidades**).
- **00 — Fundaciones:** glosario, convenciones monetarias, modelo de errores e invariantes.

---

## 5. Invariantes y reglas clave de la épica

> Notación: montos en unidades mínimas enteras (wei para ETH, USDC-min para USDC).
> `q_wei` = cantidad base matcheada; `price_min` = precio de ejecución (precio de la orden
> maker); `EX` = cuenta de fees del exchange.

1. **Precio de ejecución = precio de la orden maker (resting).** Por prioridad
   precio-tiempo (INV-7), el fill se liquida al precio de la orden que ya estaba en el
   libro. El taker puede obtener **mejora de precio**; el surplus de `bloqueado` se libera.
2. **Notional del fill (compartido por ambas patas):**
   `quote_min = floor(q_wei × price_min / 10^18)` (multiplicar antes de dividir, una sola
   división, `floor`). El mismo `quote_min` lo paga el comprador y lo recibe el vendedor
   (antes de fees) ⇒ el redondeo **no crea ni destruye valor** (INV-1).
   - Bajo las restricciones de **tick** (`price_min` múltiplo de `10^4`) y **lot** (`q_wei`
     múltiplo de `10^14`), el producto `q_wei × price_min` es siempre divisible por `10^18`,
     por lo que `quote_min` resulta **exacto**; el `floor` se mantiene como regla normativa.
3. **Fee en el activo recibido, redondeo `ceil` (en contra del usuario):**
   - Comprador (recibe ETH): `fee_base = ceil(q_wei × fee_bps_comprador / 10000)` (wei).
   - Vendedor (recibe USDC): `fee_quote = ceil(quote_min × fee_bps_vendedor / 10000)`
     (USDC-min).
   - `fee_bps = 10` si la parte es **maker**, `20` si es **taker**. Denominador fijo `10000`.
   - En todo fill hay **exactamente un maker y un taker**: una parte paga 10 bps y la otra
     20 bps. El residuo sub-unidad queda a favor de EX, nunca del usuario.
4. **Conservación exacta por construcción (INV-1):**
   - ETH: `q_wei = (q_wei − fee_base) [al comprador] + fee_base [a EX]`.
   - USDC: `quote_min = (quote_min − fee_quote) [al vendedor] + fee_quote [a EX]`.
   - EX forma parte de la suma conservada; un fill nunca altera `Σ total(·, A)`.
5. **Atomicidad del settlement (INV-4):** el conjunto de asientos
   `{débito/crédito base, débito/crédito quote, fee_base→EX, fee_quote→EX, liberación de
   surplus}` se aplica **todo o nada**, en un **orden canónico** (ETH → USDC → surplus) con
   un `type` enumerado por asiento (ver HU-05-01 RN-7) para la reconciliación automática del
   ledger. No hay estado parcial observable.
6. **No-negatividad (INV-2/INV-3):** `0 ≤ fee ≤ monto_recibido` (porque `fee_bps < 10000`),
   por lo que ningún neto es negativo; los balances `disponible`/`bloqueado` nunca quedan
   negativos. `total = disponible + bloqueado` se preserva por parte.
7. **Idempotencia del settlement por identidad de fill:** cada fill tiene una identidad
   estable (`tradeId`); reprocesarlo (reinicio, reintento) **no** vuelve a liquidar ni a
   cobrar fees.
8. **Sin floats:** todo cálculo de notional, fees y netos usa enteros (big integers); todo
   monto cruza la API como **string de entero** en unidad mínima (`^(0|[1-9][0-9]*)$`).
9. **Registro inmutable y persistente (INV-8):** cada fill produce **una** entrada de trade
   append-only; trades, balances y ledger se reconstruyen tras reinicio.
10. **Determinismo:** dadas las mismas entradas (`q_wei`, `price_min`, roles), el notional,
    las fees y los netos son los **mismos enteros** en cualquier implementación.
11. **Aislamiento/serialización bajo concurrencia.** Los settlements de fills que afectan a
    la misma `accountId` (como maker o taker) o a la cuenta `EX` deben ejecutarse bajo
    **aislamiento serializable** o con **lock pesimista a nivel de cuenta/activo** (p. ej.
    `SELECT ... FOR UPDATE` sobre el balance), o mediante un **único actor/cola por cuenta**
    (settlement single-threaded). Esto evita la doble lectura del mismo `bloqueado` por dos
    fills concurrentes (que rompería INV-2). INV-4 (atomicidad) **no** basta por sí solo bajo
    `READ COMMITTED`. (Ver HU-05-01 AT-05-01-11.)
12. **Identidad del fill (`tradeId`/`sequence`).** Cada fill llega con una identidad estable
    `tradeId = "T-" + sequence`, donde esa `sequence` es el **número de trade** (contador
    propio de los trades, HU-05-03 RN-3), **independiente** de la numeración de eventos del
    motor (README 03 RT-2) y de las secuencias por canal WebSocket (RG-API-7). Es asignada
    por el matching, persistida junto al ledger, determinística y reconstruible tras
    reinicio; es la **clave de idempotencia** del settlement y la **clave de ordenamiento**
    del historial (ver HU-05-03 RN-2/RN-3).

---

## 6. Referencias a fundaciones

- `00-fundaciones/glosario.md` — maker/taker, fill, settlement, fee, notional, cuenta EX.
- `00-fundaciones/activos-y-par-de-trading.md` — decimales, precio, tick/lot/min notional, fees por defecto.
- `00-fundaciones/convenciones-monetarias.md` — enteros, `floor`/`ceil`, conservación §3.4, serialización.
- `00-fundaciones/modelo-de-errores.md` — códigos y estructura de error uniforme.
- `00-fundaciones/invariantes-globales.md` — INV-1..INV-8.
