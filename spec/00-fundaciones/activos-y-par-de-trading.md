# Activos y par de trading

Define con precisión los activos, la red, la representación del precio y los parámetros
del par único. Los valores aquí fijados son **convenciones del proyecto** y constituyen
criterio de evaluación. Cualquier orden o monto que viole estos parámetros debe ser
**rechazado** con el error correspondiente (ver `modelo-de-errores.md`).

---

## 1. Red on-chain

| Parámetro                   | Valor                          |
|-----------------------------|--------------------------------|
| Red                         | **Sepolia** (testnet Ethereum) |
| chainId                     | **11155111**                   |
| Coin type (BIP-44, SLIP-44) | **60** (Ethereum)              |
| Confirmaciones requeridas   | **12** (depósitos y retiros)   |

- Hay **una sola red**. Toda transacción on-chain (depósito o retiro) ocurre en Sepolia.
- La firma de transacciones salientes usa `chainId = 11155111` según **EIP-155**
  (anti-replay; ver `invariantes-globales.md`).
- `CONFIRMACIONES_REQUERIDAS = 12` es el umbral por defecto para considerar un depósito
  acreditable y un retiro finalizado. Es un parámetro de configuración, pero su **valor
  por defecto fijado** para la evaluación es 12.

---

## 2. Activos

### 2.1 ETH — activo base

| Propiedad        | Valor                         |
|------------------|-------------------------------|
| Símbolo          | `ETH`                         |
| Rol en el par    | **base**                      |
| Tipo on-chain    | **nativo** (no es un token)   |
| Decimales        | **18**                        |
| Unidad mínima    | **wei** (1 ETH = 10¹⁸ wei)    |

### 2.2 USDC-mock — activo quote

| Propiedad        | Valor                                       |
|------------------|---------------------------------------------|
| Símbolo          | `USDC` (mock)                               |
| Rol en el par    | **quote**                                   |
| Tipo on-chain    | **ERC-20** desplegado en Sepolia            |
| Decimales        | **6**                                       |
| Unidad mínima    | unidad de 6 decimales (1 USDC = 10⁶ unidades) |

- **USDC-mock** es un contrato ERC-20 desplegado a propósito en testnet. Su dirección de
  contrato es un parámetro de configuración del despliegue (la épica on-chain la consume);
  no se fija un valor literal aquí porque depende del despliegue concreto, pero **es única
  y constante por entorno**.
- USDC-mock **tiene 6 decimales** (igual que el USDC real), no 18. Esto es crítico para
  las conversiones (ver `convenciones-monetarias.md`).

> Glosario de unidades:
> - 1 ETH = 1 000 000 000 000 000 000 wei (10¹⁸).
> - 1 USDC = 1 000 000 unidades mínimas (10⁶).

---

## 3. Par de trading

- **Par único:** `ETH/USDC` (base = ETH, quote = USDC-mock).
- No existen otros pares. Cualquier referencia a "el par", "el mercado" o "el orderbook"
  alude a este par.

### 3.1 Representación del precio

- El **precio se expresa en USDC por 1 ETH** (cuántos USDC cuesta 1 ETH).
- Internamente, el precio se representa como **entero**:
  **unidades mínimas de USDC (6 decimales) por 1 ETH**. Notación: `price_min`.
  - Ejemplo: precio humano `2000.50 USDC/ETH` ⇒ `price_min = 2000.50 × 10⁶ = 2 000 500 000`.
- En la API, el precio viaja como **string del entero `price_min`** (ver
  `convenciones-monetarias.md`).

### 3.2 Conversión cantidad ⇄ notional

Dado un fill de cantidad `q_wei` (ETH, en wei) a precio `price_min` (USDC-min por ETH),
el monto en quote es:

```
quote_min = floor( q_wei × price_min / 10^18 )
```

- `q_wei / 10^18` convierte wei a ETH; multiplicado por `price_min` da USDC-min.
- El `floor` (truncado hacia abajo) y su justificación contable están en
  `convenciones-monetarias.md`. Se usa aritmética **entera exacta** en todo el cálculo.

Ejemplo: `q_wei = 10^18` (1 ETH), `price_min = 2 000 500 000` ⇒
`quote_min = floor(10^18 × 2 000 500 000 / 10^18) = 2 000 500 000` = 2000.50 USDC. ✔

---

## 4. Parámetros del par (convenciones fijadas)

Estos valores son **constantes del proyecto**. Toda orden debe satisfacerlos; si no, se
rechaza con el error indicado.

| Parámetro          | Valor humano        | Valor en unidades mínimas        | Error si se viola      |
|--------------------|---------------------|----------------------------------|------------------------|
| **Tick size**      | `0.01 USDC/ETH`     | `10 000` (USDC-min por ETH)      | `INVALID_PRICE_TICK`   |
| **Lot size**       | `0.0001 ETH`        | `100 000 000 000 000` = 10¹⁴ wei | `INVALID_LOT_SIZE`     |
| **Cantidad mínima**| `0.0001 ETH`        | `10¹⁴` wei (= 1 lot)             | `INVALID_LOT_SIZE`     |
| **Mínimo notional**| `10 USDC`           | `10 000 000` (USDC-min)          | `BELOW_MIN_NOTIONAL`   |

### 4.1 Tick size (incremento mínimo de precio)

- Todo precio de orden limit debe ser un **múltiplo entero del tick size**:
  `price_min mod 10 000 == 0`.
- Equivale a permitir como máximo **2 decimales** en el precio humano (USDC/ETH).
- El precio debe ser **estrictamente positivo** (`price_min > 0`).
- Si `price_min` no es múltiplo de `10 000` o no es positivo ⇒ `INVALID_PRICE_TICK`.

### 4.2 Lot size (incremento mínimo de cantidad)

- Toda cantidad de orden debe ser un **múltiplo entero del lot size**:
  `q_wei mod 10^14 == 0`.
- Equivale a permitir como máximo **4 decimales** en la cantidad humana (ETH).
- La cantidad debe ser **estrictamente positiva** (`q_wei > 0`).
- Si `q_wei` no es múltiplo de `10^14` o no es positivo ⇒ `INVALID_LOT_SIZE`.

### 4.3 Cantidad mínima de orden

- La cantidad mínima coincide con **1 lot = 0.0001 ETH = 10¹⁴ wei**. (Toda cantidad
  válida por lot size ya es ≥ cantidad mínima, salvo el caso `q_wei = 0`, cubierto por la
  exigencia de positividad.)

### 4.4 Mínimo notional

- El notional de una orden **limit** se calcula con su precio límite:
  `notional_min = floor(q_wei × price_min / 10^18)`.
- Debe cumplirse `notional_min ≥ 10 000 000` (10 USDC). Si no ⇒ `BELOW_MIN_NOTIONAL`.
- Para una orden **market**, el notional no se conoce de antemano (no tiene precio). La
  validación de mínimo notional para market se realiza, según la épica de matching, sobre
  la cantidad mínima (1 lot) y/o sobre el notional estimado con el mejor precio disponible;
  la regla concreta se fija en `04-gestion-de-ordenes` / `03-motor-de-matching`. A nivel
  fundacional, **el mínimo notional de 10 USDC es la convención** que esas épicas
  instancian.

### 4.5 Ejemplos de validación

| Caso                                         | `q_wei`            | `price_min`     | Resultado                         |
|----------------------------------------------|--------------------|-----------------|-----------------------------------|
| Compra 1 ETH @ 2000.00                        | 10¹⁸               | 2 000 000 000   | ✔ válida (notional 2000 USDC)      |
| Precio con 3 decimales (2000.005)             | 10¹⁸               | 2 000 005 000   | ✘ `INVALID_PRICE_TICK`            |
| Cantidad con 5 decimales (0.00005 ETH)        | 5×10¹³             | 2 000 000 000   | ✘ `INVALID_LOT_SIZE`              |
| 0.0001 ETH @ 2000.00 (notional 0.2 USDC)      | 10¹⁴               | 2 000 000 000   | ✘ `BELOW_MIN_NOTIONAL`            |
| 0.005 ETH @ 2000.00 (notional 10 USDC)        | 5×10¹⁵             | 2 000 000 000   | ✔ válida (notional exacto = mín)   |
| Precio cero                                   | 10¹⁸               | 0               | ✘ `INVALID_PRICE_TICK`            |

---

## 5. Fees del par (referencia)

Las fees maker/taker se definen como convención del proyecto y se detallan en
`05-settlement-y-fees`. Valores por defecto fijados:

| Fee   | Valor    | bps  |
|-------|----------|------|
| Maker | 0.10 %   | 10   |
| Taker | 0.20 %   | 20   |

El cálculo y la dirección de redondeo de las fees están en `convenciones-monetarias.md`.
