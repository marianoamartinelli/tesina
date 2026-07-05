# Modelo de errores

Catálogo único de errores de dominio y forma uniforme de la respuesta de error. Toda
épica que rechace una operación debe usar **uno de estos códigos** y la **estructura
estándar**. Los `code` son **estables** (no se renombran) y son parte del criterio de
evaluación: un test puede afirmar "se rechaza con `INSUFFICIENT_FUNDS`".

---

## 1. Forma uniforme de la respuesta de error

Toda respuesta de error (HTTP o mensaje de error por WebSocket) tiene esta estructura:

```json
{
  "error": {
    "code": "INSUFFICIENT_FUNDS",
    "message": "Saldo disponible insuficiente para la operación.",
    "details": {
      "asset": "USDC",
      "required": "10000000",
      "available": "5000000"
    }
  }
}
```

Reglas:

- **`code`** (string, obligatorio): identificador estable en MAYÚSCULAS_CON_GUION_BAJO del
  catálogo de la sección 3. Es lo que se evalúa.
- **`message`** (string, obligatorio): texto legible en español, orientado a diagnóstico.
  **No** se evalúa su literal exacto; solo debe ser coherente con el `code`.
- **`details`** (objeto, opcional): información estructurada del caso. Cuando un error
  reporta montos, estos siguen la **serialización de string entero** de
  `convenciones-monetarias.md`. Las claves de `details` que se esperan por código se
  indican en la sección 3 (columna "details esperado").
- La respuesta de error **no** incluye datos del recurso afectado salvo dentro de
  `details`.
- **Un error por respuesta:** ante múltiples violaciones, se reporta la primera según el
  orden de validación definido por la épica (que debe ser determinista). Opcionalmente,
  errores de validación de esquema pueden listar varias causas dentro de
  `details.issues`.

### 1.1 Mapeo a HTTP

Cada `code` tiene un status HTTP asociado (sección 3). Convención general:

| Familia                                   | HTTP |
|-------------------------------------------|------|
| Autenticación faltante/ inválida          | 401  |
| Autorización denegada                     | 403  |
| Validación de entrada / reglas del par    | 422  |
| Recurso inexistente                       | 404  |
| Método HTTP no permitido sobre ruta existente | 405 |
| Conflicto de estado / idempotencia        | 409  |
| Límite de tasa (rate limit)               | 429  |
| Error interno no clasificado              | 500  |

> Por WebSocket no hay status HTTP; se transmite la misma estructura `{ error: {...} }`
> y el `code` es lo determinante.

---

## 2. Convenciones del catálogo

- Los códigos se agrupan por área pero el **espacio de nombres es plano y global** (un
  `code` no se repite).
- "Cuándo se produce" describe el disparador de forma testeable.
- Las épicas pueden **referenciar** estos códigos y precisar el disparador, pero **no**
  pueden inventar variantes con otro nombre para el mismo caso.

---

## 3. Catálogo de errores de dominio

### 3.1 Autenticación y autorización

| Code                  | HTTP | Cuándo se produce                                                                 | details esperado          |
|-----------------------|------|----------------------------------------------------------------------------------|---------------------------|
| `UNAUTHENTICATED`     | 401  | Falta credencial, o token/clave inválido o expirado.                              | —                         |
| `UNAUTHORIZED`        | 403  | Credencial válida pero sin permiso para la acción: operaciones que actúan explícitamente **a nombre de** otra cuenta (p. ej. crear un retiro para otra cuenta). Los recursos ajenos **referenciados por id** responden 404, ver la nota de §3.4. | `{ resource }`            |
| `RATE_LIMITED`        | 429  | Se superó el límite de solicitudes permitido.                                     | `{ retryAfterSeconds }`   |

### 3.2 Validación general

| Code                | HTTP | Cuándo se produce                                                                   | details esperado            |
|---------------------|------|-------------------------------------------------------------------------------------|-----------------------------|
| `VALIDATION_ERROR`  | 422  | El payload no cumple el esquema: tipo incorrecto, campo faltante, monto que no matchea `^(0\|[1-9][0-9]*)$`, enum inválido **sin código propio** (los enums de `side` y `type` tienen códigos específicos — `INVALID_SIDE` / `INVALID_ORDER_TYPE` — y se evalúan en el paso 3 de §4). | `{ issues: [...] }`         |
| `NOT_FOUND`         | 404  | Recurso genérico inexistente (cuando no aplica un código más específico).            | `{ resource, id }`          |
| `METHOD_NOT_ALLOWED`| 405  | Método HTTP no permitido sobre una **ruta existente** (la ruta existe pero no soporta ese verbo). | `{ method, allowed }`       |

### 3.3 Trading: validación de órdenes

| Code                  | HTTP | Cuándo se produce                                                                       | details esperado                          |
|-----------------------|------|-----------------------------------------------------------------------------------------|-------------------------------------------|
| `INVALID_PRICE_TICK`  | 422  | El precio no es múltiplo del **tick size** (`price_min mod 10000 ≠ 0`) o no es positivo. | `{ priceMin, tickSize }`                  |
| `INVALID_LOT_SIZE`    | 422  | La cantidad no es múltiplo del **lot size** (`q_wei mod 10^14 ≠ 0`) o no es positiva.    | `{ quantityWei, lotSize }`                |
| `BELOW_MIN_NOTIONAL`  | 422  | El notional de la orden es menor al mínimo (`< 10 USDC` = `10000000`).                   | `{ actualNotional, minNotional }`         |
| `INVALID_SIDE`        | 422  | `side` distinto de `BUY`/`SELL`.                                                         | `{ side }`                                |
| `INVALID_ORDER_TYPE`  | 422  | `type` distinto de `LIMIT`/`MARKET`.                                                     | `{ type }`                                |
| `PRICE_REQUIRED`      | 422  | Orden `LIMIT` sin precio.                                                                | —                                         |
| `PRICE_NOT_ALLOWED`   | 422  | Orden `MARKET` con precio especificado.                                                  | —                                         |

### 3.4 Trading: estado y ejecución

| Code                     | HTTP | Cuándo se produce                                                                          | details esperado                     |
|--------------------------|------|--------------------------------------------------------------------------------------------|--------------------------------------|
| `INSUFFICIENT_FUNDS`     | 422  | Balance **disponible** insuficiente para bloquear lo requerido por la orden o el retiro.    | `{ asset, required, available }`     |
| `ORDER_NOT_FOUND`        | 404  | La orden referenciada no existe o no pertenece a la cuenta.                                 | `{ orderId }`                        |
| `ORDER_NOT_CANCELLABLE`  | 409  | Se intenta cancelar una orden que ya está `FILLED`, `CANCELLED` o `REJECTED`.               | `{ orderId, status }`                |
| `SELF_TRADE_BLOCKED`     | 422  | El **rango consumible** de la orden entrante (HU-03-06 RN-2: lo que ejecutaría según prioridad precio-tiempo hasta completar su cantidad o presupuesto) contiene al menos una orden **propia** (misma cuenta como maker y taker). La entrante se rechaza **íntegra**, sin aplicar ningún fill (HU-03-06 RN-3). | `{ restingOrderId }`                 |
| `MARKET_NO_LIQUIDITY`    | 422  | Orden `MARKET` que no encuentra liquidez (lado opuesto vacío) y no puede ejecutarse.        | —                                    |
| `MARKET_BUDGET_INSUFFICIENT` | 422 | `MARKET BUY` cuyo presupuesto reservado **no alcanza para ejecutar ni 1 lot** del mejor maker disponible (lado opuesto **no** vacío, `filledWei = 0`). Se distingue de `MARKET_NO_LIQUIDITY`: aquí **sí** hay liquidez, pero el presupuesto no cubre el costo mínimo. | `{ budgetMin, requiredMin }`        |
| `DUPLICATE_CLIENT_ORDER_ID` | 409 | Se reutiliza un `clientOrderId` ya usado por la cuenta (idempotencia de alta de orden).   | `{ clientOrderId }`                  |

### 3.5 On-chain: depósitos y retiros

| Code                       | HTTP | Cuándo se produce                                                                              | details esperado                 |
|----------------------------|------|------------------------------------------------------------------------------------------------|----------------------------------|
| `INVALID_ADDRESS`          | 422  | La dirección destino no es una dirección Ethereum válida (no es `0x`+40 hex, o checksum EIP-55 incorrecto). | `{ address }`                    |
| `WITHDRAWAL_BELOW_MIN`     | 422  | El monto de retiro es menor al mínimo permitido para el activo.                                 | `{ asset, amount, minWithdrawal }` |
| `WITHDRAWAL_AMOUNT_INVALID`| 422  | Monto de retiro no positivo o que no respeta la unidad mínima del activo.                       | `{ asset, amount }`              |
| `DEPOSIT_ALREADY_CREDITED` | 409  | Se intenta acreditar un depósito (txHash + logIndex) que ya fue acreditado (idempotencia).      | `{ txHash, logIndex }`           |
| `DEPOSIT_NOT_CONFIRMED`    | 409  | Se intenta acreditar/usar un depósito que aún no alcanzó las confirmaciones requeridas.         | `{ txHash, confirmations, required }` |
| `CHAIN_ID_MISMATCH`        | 422  | Una transacción, firma o **solicitud de API** referencia un `chainId`/red distinto de `11155111` (Sepolia). | `{ expected, got }`             |
| `NONCE_CONFLICT`           | 409  | Conflicto de nonce al construir/broadcastear un retiro (nonce ya usado o fuera de secuencia).   | `{ address, nonce }`            |
| `BROADCAST_FAILED`         | 502  | El nodo rechazó el broadcast de la transacción de retiro.                                       | `{ reason }`                    |

> **Recursos ajenos referenciados por id:** referenciar por id un recurso de otra cuenta
> (orden, retiro, depósito) responde el error *not found* correspondiente
> (`ORDER_NOT_FOUND`, o `NOT_FOUND` con `details.resource`; HTTP 404), **no**
> `UNAUTHORIZED`, para no revelar la existencia del recurso (*resource enumeration*).
> `UNAUTHORIZED` (403) queda reservado para operaciones que actúan explícitamente **a
> nombre de** otra cuenta (p. ej. un `accountId` ajeno como parámetro de una escritura).

> **Tipos en `details` de `DEPOSIT_NOT_CONFIRMED`:** `confirmations` y `required` son
> **enteros JSON** (números), **no** strings, porque son **conteos** y no montos monetarios.
> La serialización como string de entero (ver `convenciones-monetarias.md` §5) aplica solo a
> montos/precios. `txHash` es un string `^0x[0-9a-fA-F]{64}$`; `logIndex` (en
> `DEPOSIT_ALREADY_CREDITED`) es un entero `≥ 0`.

### 3.6 Cuentas

| Code                     | HTTP | Cuándo se produce                                                          | details esperado     |
|--------------------------|------|----------------------------------------------------------------------------|----------------------|
| `EMAIL_ALREADY_EXISTS`   | 409  | Registro con un email ya existente.                                         | `{ email }`          |
| `INVALID_CREDENTIALS`    | 401  | Login con credenciales incorrectas. (No revela si el email existe.)         | —                    |
| `ACCOUNT_NOT_FOUND`      | 404  | Cuenta inexistente.                                                         | `{ accountId }`      |

### 3.7 Genéricos / sistema

| Code               | HTTP | Cuándo se produce                                                  | details esperado |
|--------------------|------|--------------------------------------------------------------------|------------------|
| `CONFLICT`         | 409  | Conflicto de estado no cubierto por un código específico.           | `{ reason }`     |
| `INTERNAL_ERROR`   | 500  | Falla interna no clasificada. **No** filtra detalles sensibles.    | —                |

---

## 4. Precedencia de validación (determinismo)

Cuando una operación puede fallar por varias razones, el orden de evaluación debe ser
**determinista**. Orden recomendado (de antes hacia después) para el alta de una orden:

1. Autenticación (`UNAUTHENTICATED`) → autorización (`UNAUTHORIZED`).
2. Esquema/tipos del payload (`VALIDATION_ERROR`).
3. Enums y combinaciones (`INVALID_SIDE`, `INVALID_ORDER_TYPE`, `PRICE_REQUIRED`,
   `PRICE_NOT_ALLOWED`).
4. Reglas del par sobre los valores (`INVALID_PRICE_TICK`, `INVALID_LOT_SIZE`,
   `BELOW_MIN_NOTIONAL`).
5. Idempotencia (`DUPLICATE_CLIENT_ORDER_ID`).
6. Fondos (`INSUFFICIENT_FUNDS`).
7. Reglas de matching, en este orden: `SELF_TRADE_BLOCKED` (se evalúa sobre el **rango
   consumible** de la entrante — HU-03-06 RN-2 —: si contiene al menos una orden propia,
   la entrante se rechaza íntegra, aunque **toda** la liquidez cruzable sea propia) →
   `MARKET_NO_LIQUIDITY` (lado opuesto completamente vacío; solo `MARKET`) →
   `MARKET_BUDGET_INSUFFICIENT` (`MARKET BUY` con lado opuesto **no** vacío cuyo
   presupuesto no alcanza para ejecutar ni 1 lot del mejor maker disponible; en ese caso
   el rango consumible resulta vacío, por lo que no hay STP que evaluar).

Cada épica que defina una operación debe declarar (o heredar) su orden de precedencia para
que los tests de aceptación sean reproducibles.
