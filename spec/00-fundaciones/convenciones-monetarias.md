# Convenciones monetarias

Reglas **obligatorias** para representar, operar, redondear y serializar dinero. Son
transversales a todas las épicas y forman parte del criterio de evaluación: una
implementación que viole estas reglas es incorrecta aunque "los tests felices pasen".

---

## 1. Representación: enteros de la unidad mínima

- **Todo monto y todo precio se representa como un entero** en la **unidad mínima** del
  activo correspondiente.
  - **ETH:** wei. `1 ETH = 10¹⁸ wei`.
  - **USDC-mock:** unidad de 6 decimales. `1 USDC = 10⁶ unidades`.
  - **Precio (`price_min`):** unidades mínimas de USDC por **1 ETH**. `2000.50 USDC/ETH =
    2 000 500 000`.
- Los enteros deben ser de **precisión arbitraria** o, como mínimo, de un ancho que no
  desborde en ningún cálculo intermedio. El producto `q_wei × price_min` puede alcanzar el
  orden de `10^18 × 10^12 = 10^30`, que **excede 64 bits** (máx. ~`1.8 × 10^19`). Por lo
  tanto:
  - **Prohibido** usar enteros de 64 bits "a secas" para los productos intermedios sin
    salvaguarda de overflow.
  - Se debe usar **big integers** (enteros de precisión arbitraria) o un esquema de
    multiplicación de 128/256 bits que garantice exactitud.

### 1.1 Prohibición de floats binarios

- **PROHIBIDO** usar tipos de punto flotante binario (`float`, `double`, IEEE-754) para
  representar, almacenar, transmitir o calcular montos, precios, fees o balances.
- Motivo: los floats binarios no pueden representar exactamente fracciones decimales
  (p. ej. `0.1`), lo que introduce errores de redondeo no determinísticos y rompe la
  conservación de fondos.
- Permitido: enteros (big integers) y, si se necesita una representación decimal, tipos
  **decimales de precisión fija** (decimal de base 10 con escala fija), siempre que el
  resultado final almacenado/serializado sea el **entero de unidad mínima**.
- La verificación es testeable: ningún monto cruza la frontera de la API ni se persiste
  como número de punto flotante; siempre como entero/string de entero.

---

## 2. Aritmética y conversiones

### 2.1 Regla general

- Toda operación monetaria se realiza con **aritmética entera exacta** sobre unidades
  mínimas. No se hacen divisiones que pierdan precisión salvo en los puntos de
  **redondeo explícito** definidos abajo.

### 2.2 Conversión base ⇄ quote (cantidad ⇄ notional)

Para un fill de `q_wei` ETH (wei) a precio `price_min` (USDC-min por ETH), el monto en
quote es:

```
quote_min = floor( q_wei × price_min / 10^18 )
```

- Se calcula primero el producto exacto `q_wei × price_min` (big integer) y **luego** se
  divide por `10^18` truncando hacia abajo (`floor`).
- El mismo `quote_min` se usa para **ambas** patas del fill (lo que paga el comprador =
  lo que recibe el vendedor, antes de fees). Esto evita que el redondeo cree o destruya
  valor.

### 2.3 Operación inversa (si se requiere)

Cuando se necesita derivar una cantidad a partir de un monto quote y un precio (p. ej.,
en validaciones de market por monto), se usa también `floor`, y la épica que la utilice
debe documentar explícitamente la dirección del redondeo. **Por defecto: `floor`.**

---

## 3. Política de redondeo

### 3.1 Principio rector (no negociable)

> **El redondeo es siempre determinista, nunca crea valor dentro del sistema y nunca
> beneficia al usuario activo a costa del exchange o de la contraparte.**

De este principio se derivan dos reglas concretas:

### 3.2 Redondeo de conversiones: `floor` (truncado hacia abajo)

- Todas las conversiones base⇄quote usan `floor` (sección 2.2).
- Como el `quote_min` es compartido por ambas patas del fill, el `floor` **no rompe la
  conservación**: el comprador paga exactamente lo que el vendedor recibe (antes de fees).
  El residuo sub-unidad (< 1 unidad mínima de USDC) simplemente no se cobra; no se crea ni
  se acredita a nadie.

### 3.3 Redondeo de fees: `ceil` (hacia arriba, en contra del usuario)

- La fee se calcula sobre el monto que el trader **recibe** en cada fill, y se redondea
  **hacia arriba** (`ceil`), de modo que el exchange nunca cobra **menos** que la fee
  nominal (el residuo sub-unidad queda a favor del exchange, no del usuario):

```
fee = ceil( monto_recibido × fee_bps / 10000 )
```

- `fee_bps` = 10 (maker) o 20 (taker). Denominador fijo `10000`.
- Lado y activo del cobro de la fee (convención del proyecto):
  - **Comprador (recibe ETH):** `fee_base = ceil( q_wei × fee_bps / 10000 )`, cobrada en
    **wei**.
  - **Vendedor (recibe USDC):** `fee_quote = ceil( quote_min × fee_bps / 10000 )`, cobrada
    en **USDC-min**.
- Garantías:
  - `0 ≤ fee ≤ monto_recibido` siempre (porque `fee_bps < 10000`), por lo que el neto
    nunca es negativo.
  - Determinismo total: dos implementaciones que apliquen estas fórmulas obtienen el
    **mismo** entero.

### 3.4 Conservación bajo settlement (consecuencia)

Para un fill de `q_wei` ETH a `quote_min` USDC entre un comprador y un vendedor:

```
ETH:   q_wei (sale del vendedor) = (q_wei − fee_base) (al comprador) + fee_base (al exchange)
USDC:  quote_min (sale del comprador) = (quote_min − fee_quote) (al vendedor) + fee_quote (al exchange)
```

Ambas igualdades son **exactas por construcción** ⇒ se respeta la conservación de fondos
(ver `invariantes-globales.md`). El detalle por estado (maker/taker, fill parcial) lo
instancia `05-settlement-y-fees`, pero la **forma del redondeo es esta**.

### 3.5 Resumen de direcciones de redondeo

| Cálculo                                   | Dirección | Beneficiario del residuo |
|-------------------------------------------|-----------|--------------------------|
| Conversión base→quote (`quote_min`)       | `floor`   | nadie (no se crea valor) |
| Fee maker/taker                           | `ceil`    | exchange (contra usuario)|

---

## 4. Cómo evitar la pérdida de precisión

1. **Operar siempre en unidades mínimas enteras**; convertir a humano solo para
   presentación en el frontend.
2. **Multiplicar antes de dividir.** Calcular `q_wei × price_min` completo y dividir al
   final; nunca dividir primero (perdería dígitos).
3. **Una sola división por cálculo**, en el punto de redondeo documentado.
4. **Big integers** para los productos intermedios (pueden superar 64 bits).
5. **No reconstruir** montos a partir de valores humanos con decimales; el entero de
   unidad mínima es la fuente de verdad.
6. **No comparar montos con tolerancia (epsilon):** las comparaciones son exactas entre
   enteros.

---

## 5. Serialización en la API

- **Todos** los montos, precios, cantidades, fees y balances se serializan como
  **strings que contienen un entero decimal** en unidades mínimas, sin separadores, sin
  signo `+`, sin decimales y sin notación científica.
  - Válidos: `"0"`, `"1500000000"`, `"100000000000000"`.
  - Inválidos: `1500000000` (número JSON), `"1.5"`, `"1,500"`, `"1e9"`, `"-5"` (los
    montos no son negativos), `"01"` (sin ceros a la izquierda).
- **Por qué string y no número JSON:** los números JSON se interpretan habitualmente como
  IEEE-754 de doble precisión, que **pierde exactitud** por encima de 2⁵³ (~`9.0 × 10^15`).
  Un balance de ETH en wei supera fácilmente ese umbral. El string entero evita toda
  ambigüedad.
- **Convención de nombres / unidades en el contrato de API:** cada campo monetario debe
  documentar su activo y que está en unidad mínima. Convención recomendada para campos:
  - cantidades de ETH en wei (p. ej. `quantityWei`),
  - montos de USDC en unidades de 6 decimales (p. ej. `amountUsdcMin`),
  - precio como `priceMin` (USDC-min por ETH).
  (Los nombres exactos de campos los fija `09-api-http-websocket`; la **unidad** es esta.)
- **Validación de entrada:** todo monto/precio recibido por la API debe matchear el patrón
  de entero decimal no negativo `^(0|[1-9][0-9]*)$`. Si no, se rechaza con error de
  validación (`VALIDATION_ERROR` o el específico del dominio, ver `modelo-de-errores.md`).
- **Redondeo en la frontera:** la API **no** acepta más precisión que la unidad mínima.
  No existen "decimales del decimal": el cliente envía enteros de unidad mínima y el
  servidor opera sobre ellos sin re-redondear la entrada.
- **Solo los montos van como string:** la serialización como **string de entero** aplica
  **únicamente a montos, precios, fees y balances** (valores monetarios). Los **conteos e
  índices no monetarios** —p. ej. `confirmations`, `required`, `logIndex`, `blockNumber`,
  `sequence`, `depth`, `limit`— se serializan como **enteros JSON** (números), no como
  strings, ya que no sufren el problema de precisión de IEEE-754 en sus rangos y son
  comparaciones de enteros pequeños. No mezclar ambas convenciones.

---

## 6. Tabla de referencia rápida

| Concepto                        | Valor / fórmula                                   |
|---------------------------------|---------------------------------------------------|
| 1 ETH                           | `10^18` wei                                       |
| 1 USDC                          | `10^6` unidades mínimas                           |
| Precio `2000.50 USDC/ETH`       | `price_min = 2 000 500 000`                       |
| Notional de un fill             | `quote_min = floor(q_wei × price_min / 10^18)`    |
| Fee (maker/taker)               | `ceil(monto_recibido × fee_bps / 10000)`          |
| `fee_bps`                       | maker `10`, taker `20` (denominador `10000`)      |
| Serialización                   | string entero de unidad mínima, `^(0|[1-9][0-9]*)$` |
