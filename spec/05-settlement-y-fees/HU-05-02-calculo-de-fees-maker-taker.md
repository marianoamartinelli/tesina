# HU-05-02 — Cálculo de fees maker/taker

- **Epica:** 05 — Settlement y Fees
- **Actor / rol:** Sistema (cálculo de fees, dentro del settlement disparado por el fill de la épica 03)
- **Prioridad:** Alta
- **Dependencias:** HU-05-01 (settlement atómico que aplica las fees), HU-03-* (fill: roles maker/taker, `q_wei`, `price_min`), HU-02-* (cuenta de fees del exchange EX, balances)
- **Estandares de dominio aplicables:** N/A (cálculo contable interno)

## Historia
Como **sistema de settlement**, quiero **calcular y aplicar fees diferenciadas maker (10
bps) y taker (20 bps) sobre cada fill, cobradas en el activo que recibe cada parte, con
redondeo determinista `ceil`, y acreditarlas a la cuenta de fees del exchange**, para
**que el exchange perciba su comisión de forma exacta, reproducible y siempre en contra
del usuario activo, sin romper la conservación de fondos**.

## Contexto y alcance
Esta HU define **cómo se computan los enteros de fee** que HU-05-01 acredita a EX y
descuenta del monto recibido por cada parte. En todo fill hay **exactamente un maker y un
taker**: el maker paga 10 bps y el taker 20 bps. La fee se cobra **en el activo recibido**
por cada parte (comprador recibe ETH → fee en wei; vendedor recibe USDC → fee en
USDC-min) y se redondea hacia arriba (`ceil`), de modo que el residuo sub-unidad queda a
favor de EX y nunca del usuario (convenciones §3.3).

**No** cubre: la aplicación de los asientos ni la atomicidad (HU-05-01), el precio de
ejecución (épica 03), ni el registro del trade (HU-05-03). Supuesto: `q_wei` es múltiplo
de `10^14` (lot) y `price_min` múltiplo de `10^4` (tick), por lo que `quote_min` es exacto
(ver HU-05-01 RN-3).

## Reglas de negocio e invariantes

1. **RN-1 (tasas fijadas).** `fee_bps_maker = 10` (0.10 %), `fee_bps_taker = 20` (0.20 %).
   Denominador fijo `10000`. Son constantes del proyecto (activos-y-par §5); no varían por
   volumen, tier ni usuario.
2. **RN-2 (un maker y un taker por fill).** El evento de fill identifica qué orden es maker
   (resting) y cuál es taker (entrante). El comprador y el vendedor son cada uno maker **o**
   taker, nunca ambos, y nunca el mismo (self-trade bloqueado, épica 03).
3. **RN-3 (fee en el activo recibido).**
   - **Comprador** (recibe ETH): `fee_base = ceil(q_wei × fee_bps_comprador / 10000)`, en
     **wei**, donde `fee_bps_comprador = 20` si el comprador es taker, `10` si es maker.
   - **Vendedor** (recibe USDC): `fee_quote = ceil(quote_min × fee_bps_vendedor / 10000)`,
     en **USDC-min**, donde `fee_bps_vendedor = 20` si el vendedor es taker, `10` si es
     maker.
4. **RN-4 (mapeo de roles por lado del taker).**
   - Si `takerSide = BUY` (taker compra contra maker que vende): comprador = **taker** (20
     bps en ETH), vendedor = **maker** (10 bps en USDC).
   - Si `takerSide = SELL` (taker vende contra maker que compra): vendedor = **taker** (20
     bps en USDC), comprador = **maker** (10 bps en ETH).
5. **RN-5 (redondeo `ceil`, fórmula exacta).** `ceil(a × b / c)` se calcula con enteros
   como `(a × b + c − 1) div c` (o equivalente exacto), sin floats. `a × b` se computa como
   big integer antes de dividir.
6. **RN-6 (cota del neto, no-negatividad).** Como `fee_bps < 10000`, siempre
   `0 ≤ fee ≤ monto_recibido`. Por lo tanto el neto que recibe cada parte es ≥ 0:
   - Comprador recibe `q_wei − fee_base ≥ 0` en ETH.
   - Vendedor recibe `quote_min − fee_quote ≥ 0` en USDC. (INV-2)
7. **RN-7 (acreditación a EX).** `fee_base` se acredita al `disponible` de ETH de EX y
   `fee_quote` al `disponible` de USDC de EX, dentro del mismo settlement atómico de
   HU-05-01. EX forma parte de la conservación (INV-1).
8. **RN-8 (conservación exacta — INV-1, convenciones §3.4).**
   `q_wei = (q_wei − fee_base) + fee_base` y `quote_min = (quote_min − fee_quote) +
   fee_quote`. El cobro de fee **no** altera `Σ total(·, A)`; solo redistribuye hacia EX.
9. **RN-9 (exactitud de `fee_base` bajo lot).** Como `q_wei` es múltiplo de `10^14`,
   `q_wei × 10 / 10000 = q_wei/1000` y `q_wei × 20 / 10000 = q_wei/500` son **enteros
   exactos**; por ende `fee_base` nunca sufre redondeo (el `ceil` no agrega nada). El
   redondeo `ceil` puede ser efectivo en `fee_quote` (depende de `quote_min`).
10. **RN-10 (determinismo).** Dadas `q_wei`, `quote_min` y los roles, `fee_base` y
    `fee_quote` son los **mismos enteros** en toda implementación correcta. Comparaciones
    exactas, sin epsilon.
11. **RN-11 (sin floats).** Prohibido IEEE-754 para tasas, montos o fees; todo en enteros
    de unidad mínima / big integers (convenciones §1.1). Las fees viajan por la API como
    string de entero (`^(0|[1-9][0-9]*)$`).
12. **RN-12 (fee sobre fill parcial).** La fee se calcula sobre el `q_wei`/`quote_min`
    **del fill** (la porción efectivamente ejecutada), no sobre la cantidad total de la
    orden. Una orden que se llena en N fills paga la suma de las fees de cada fill.

## Tabla de mapeo de roles y fees

| `takerSide` | Comprador | bps comprador (ETH) | Vendedor | bps vendedor (USDC) |
|-------------|-----------|---------------------|----------|---------------------|
| `BUY`       | taker     | 20                  | maker    | 10                  |
| `SELL`      | maker     | 10                  | taker    | 20                  |

## Criterios de aceptacion (DoD)

### Escenario 1: Taker compra contra maker vende — fees 20/10 [AT-05-02-01]
- Dado un fill con `takerSide = BUY`, `q_wei = 1000000000000000000` (1 ETH),
  `price_min = 2000000000` (2000.00), `quote_min = 2000000000`
- Cuando se calculan las fees
- Entonces `fee_base = ceil(1000000000000000000 × 20 / 10000) = 2000000000000000` wei
  (0.002 ETH, taker)
- Y `fee_quote = ceil(2000000000 × 10 / 10000) = 2000000` USDC-min (2.00 USDC, maker)
- Y el comprador recibe `1000000000000000000 − 2000000000000000 = 998000000000000000` wei
- Y el vendedor recibe `2000000000 − 2000000 = 1998000000` USDC-min
- Y `disponible(EX, ETH) += 2000000000000000` y `disponible(EX, USDC) += 2000000`
- Y se conserva por activo: ETH `998000000000000000 + 2000000000000000 =
  1000000000000000000`; USDC `1998000000 + 2000000 = 2000000000` (INV-1)

### Escenario 2: Taker vende contra maker compra — fees 20/10 invertidas [AT-05-02-02]
- Dado un fill con `takerSide = SELL`, `q_wei = 1000000000000000000`,
  `price_min = 2000000000`, `quote_min = 2000000000`
- Cuando se calculan las fees
- Entonces `fee_quote = ceil(2000000000 × 20 / 10000) = 4000000` USDC-min (4.00 USDC, taker
  = vendedor)
- Y `fee_base = ceil(1000000000000000000 × 10 / 10000) = 1000000000000000` wei (0.001 ETH,
  maker = comprador)
- Y el vendedor recibe `2000000000 − 4000000 = 1996000000` USDC-min
- Y el comprador recibe `1000000000000000000 − 1000000000000000 = 999000000000000000` wei
- Y `disponible(EX, ETH) += 1000000000000000` y `disponible(EX, USDC) += 4000000`
- Y se conserva por activo (INV-1)

### Escenario 3 (borde): `ceil` efectivo en `fee_quote` — residuo a favor de EX [AT-05-02-03]
- Dado un fill con `takerSide = BUY`, `q_wei = 100000000000000` (0.0001 ETH, 1 lot),
  `price_min = 2000010000` (2000.01, múltiplo de tick)
- Cuando se calcula el notional
- Entonces `quote_min = floor(100000000000000 × 2000010000 / 10^18) = 200001` USDC-min
- Y, siendo el vendedor maker, `fee_quote = ceil(200001 × 10 / 10000) = ceil(200001/1000) =
  ceil(200.001) = 201` USDC-min (la fee nominal `200.001` se redondea **hacia arriba**, el
  residuo `0.999` queda para EX)
- Y el vendedor recibe `200001 − 201 = 199800` USDC-min
- Y `fee_base = ceil(100000000000000 × 20 / 10000) = 200000000000` wei (exacto; el `ceil`
  no agrega nada, RN-9)
- Y el neto del vendedor es ≥ 0 y la conservación se mantiene (INV-1/INV-2)

### Escenario 4 (borde): `fee_base` siempre exacto bajo lot [AT-05-02-04]
- Dado cualquier fill con `q_wei` múltiplo de `10^14` (p. ej. `q_wei = 300000000000000`,
  0.0003 ETH)
- Cuando se calcula `fee_base` con bps maker (10) o taker (20)
- Entonces `fee_base = q_wei/1000` (maker) o `q_wei/500` (taker) es entero exacto; para
  `q_wei = 300000000000000`: maker `= 300000000000` wei, taker `= 600000000000` wei
- Y el `ceil` no produce incremento alguno respecto de la división exacta (RN-9)

### Escenario 5 (borde): fill mínimo — fees positivas y neto no negativo [AT-05-02-05]
- Dado un fill de `q_wei = 100000000000000` (1 lot) a `price_min = 2000000000`,
  `quote_min = 200000` (0.20 USDC), `takerSide = BUY`
- Cuando se calculan las fees
- Entonces `fee_base = ceil(100000000000000 × 20 / 10000) = 200000000000` wei (taker)
- Y `fee_quote = ceil(200000 × 10 / 10000) = 200` USDC-min (maker; `200000/1000 = 200`,
  exacto)
- Y comprador neto `= 100000000000000 − 200000000000 = 99800000000000` wei ≥ 0; vendedor
  neto `= 200000 − 200 = 199800` USDC-min ≥ 0 (INV-2)

### Escenario 6 (determinismo): mismas entradas, mismos enteros [AT-05-02-06]
- Dado el mismo fill (`q_wei`, `price_min`, `takerSide`) calculado dos veces o por dos
  implementaciones distintas
- Cuando se computan `fee_base` y `fee_quote`
- Entonces ambos resultados son **idénticos** al entero, sin tolerancia ni epsilon
- Y ningún valor intermedio ni final se representa como float (RN-11)

### Escenario 7 (serialización/error): fee serializada como string entero [AT-05-02-07]
- Dado un fill liquidado con `fee_base = 2000000000000000` y `fee_quote = 2000000`
- Cuando estos valores cruzan la API (en el evento de trade o el registro de HU-05-03)
- Entonces se serializan como `"2000000000000000"` y `"2000000"` (string que matchea
  `^(0|[1-9][0-9]*)$`), nunca como número JSON, decimal ni notación científica
- Y una representación inválida (`2000000` numérico, `"2e6"`, `"0.002"`, `"-1"`) se
  considera incumplimiento de las convenciones monetarias

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptacion (AT-05-02-01 .. AT-05-02-07) pasan
- [ ] Reglas de negocio RN-1..RN-12 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md (fees `ceil`,
      denominador 10000, sin floats)
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md), en
      particular INV-1 (conservación con EX) e INV-2 (neto ≥ 0)
- [ ] (si aplica) Adherencia verificada al estandar on-chain citado — N/A (cálculo interno)
