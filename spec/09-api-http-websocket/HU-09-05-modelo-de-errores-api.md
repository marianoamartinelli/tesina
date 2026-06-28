# HU-09-05 — Modelo de errores de la API

- **Epica:** 09 — API HTTP/WebSocket
- **Actor / rol:** Cliente web/mobile / Sistema (servidor de API)
- **Prioridad:** Alta
- **Dependencias:** HU-09-01 (contrato REST), HU-09-02 (auth), HU-09-03/04 (WebSocket),
  `00-fundaciones/modelo-de-errores.md` (catálogo de dominio, prevalece)
- **Estándares de dominio aplicables:** N/A on-chain (referencia indirecta a EIP-55/EIP-155
  vía códigos `INVALID_ADDRESS`/`CHAIN_ID_MISMATCH`)

## Historia
Como cliente web/mobile, quiero que **todas** las respuestas de error de la API tengan una
**forma uniforme** con un `code` estable y un mapeo claro a HTTP/WS, para poder manejar
errores de modo programático, consistente y testeable.

## Contexto y alcance
Esta HU fija la **superficie de errores de la API**: la estructura del envelope, el mapeo
de cada `code` de dominio a su status HTTP, el comportamiento "un error por respuesta" según
la precedencia determinista, y la forma de los errores por WebSocket. El **catálogo** de
códigos y sus disparadores está en `00-fundaciones/modelo-de-errores.md` y **prevalece**;
aquí no se inventan códigos nuevos, solo se especifica cómo se **exponen** en la API.

## Reglas de negocio e invariantes

1. **RN-1 (envelope uniforme):** toda respuesta de error (HTTP o WS) tiene la forma
   `{ "error": { "code": <string>, "message": <string>, "details": <object?> } }`. `code`
   y `message` obligatorios; `details` opcional.
2. **RN-2 (`code` estable):** `code` es un identificador en `MAYÚSCULAS_CON_GUION_BAJO` del
   catálogo de `00-fundaciones/modelo-de-errores.md` §3. Es **lo que se evalúa**: estable,
   no se renombra ni se inventan variantes para el mismo caso.
3. **RN-3 (`message` libre):** `message` es texto legible en español, coherente con el
   `code`. **No** se evalúa su literal exacto.
4. **RN-4 (`details` estructurado):** `details` sigue, por código, las claves esperadas del
   catálogo (p. ej. `INSUFFICIENT_FUNDS` → `{ asset, required, available }`). Todo monto en
   `details` se serializa como **string de entero** en unidad mínima
   (`00-fundaciones/convenciones-monetarias.md` §5).
5. **RN-5 (un error por respuesta):** ante múltiples violaciones, se reporta **el primero**
   según la precedencia determinista de la operación
   (`00-fundaciones/modelo-de-errores.md` §4: auth → esquema → enums/combinaciones → reglas
   del par → idempotencia → fondos → matching). Opcionalmente, los errores de esquema pueden
   listar varias causas en `details.issues`.
6. **RN-6 (mapeo HTTP):** cada `code` mapea a su status HTTP del catálogo. Tabla de
   referencia (subconjunto vigente para esta API):

   | code                        | HTTP |
   |-----------------------------|------|
   | `UNAUTHENTICATED`           | 401  |
   | `INVALID_CREDENTIALS`       | 401  |
   | `UNAUTHORIZED`              | 403  |
   | `VALIDATION_ERROR`          | 422  |
   | `INVALID_PRICE_TICK`        | 422  |
   | `INVALID_LOT_SIZE`          | 422  |
   | `BELOW_MIN_NOTIONAL`        | 422  |
   | `INVALID_SIDE`              | 422  |
   | `INVALID_ORDER_TYPE`        | 422  |
   | `PRICE_REQUIRED`            | 422  |
   | `PRICE_NOT_ALLOWED`         | 422  |
   | `INSUFFICIENT_FUNDS`        | 422  |
   | `SELF_TRADE_BLOCKED`        | 422  |
   | `MARKET_NO_LIQUIDITY`       | 422  |
   | `INVALID_ADDRESS`           | 422  |
   | `WITHDRAWAL_BELOW_MIN`      | 422  |
   | `WITHDRAWAL_AMOUNT_INVALID` | 422  |
   | `CHAIN_ID_MISMATCH`         | 422  |
   | `NOT_FOUND`                 | 404  |
   | `ORDER_NOT_FOUND`           | 404  |
   | `ACCOUNT_NOT_FOUND`         | 404  |
   | `METHOD_NOT_ALLOWED`        | 405  |
   | `ORDER_NOT_CANCELLABLE`     | 409  |
   | `DUPLICATE_CLIENT_ORDER_ID` | 409  |
   | `EMAIL_ALREADY_EXISTS`      | 409  |
   | `DEPOSIT_ALREADY_CREDITED`  | 409  |
   | `DEPOSIT_NOT_CONFIRMED`     | 409  |
   | `NONCE_CONFLICT`            | 409  |
   | `CONFLICT`                  | 409  |
   | `RATE_LIMITED`              | 429  |
   | `BROADCAST_FAILED`          | 502  |
   | `INTERNAL_ERROR`            | 500  |

7. **RN-7 (errores por WebSocket):** por WS no hay status HTTP; se transmite el mismo
   envelope `{ error: { code, message, details? } }` por el socket. El `code` es lo
   determinante (`00-fundaciones/modelo-de-errores.md` §1.1).
8. **RN-8 (rate limit):** `RATE_LIMITED` (429) incluye `details.retryAfterSeconds` (entero,
   como número del objeto details según catálogo) y header HTTP `Retry-After`.
9. **RN-9 (no fuga de información):** `INTERNAL_ERROR` (500) **no** filtra detalles
   sensibles (stack traces, secretos, internals). Los errores de auth no revelan si el
   email/token existió (coherente con `INVALID_CREDENTIALS`/`UNAUTHENTICATED`).
10. **RN-10 (recurso/método):** una ruta inexistente bajo `/api/v1` ⇒ `NOT_FOUND` (404) con
    envelope; un método no permitido sobre una ruta existente ⇒ `METHOD_NOT_ALLOWED` (405)
    con envelope y `details = { method, allowed }` (`code` del catálogo de
    `00-fundaciones/modelo-de-errores.md`). El cuerpo de error nunca expone el recurso
    afectado salvo dentro de `details`.
11. **RN-11 (no contradice invariantes):** los errores que protegen invariantes deben
    dispararse **antes** de mutar estado: `INSUFFICIENT_FUNDS` rechaza antes de dejar un
    balance negativo (INV-2); `DUPLICATE_CLIENT_ORDER_ID`/`DEPOSIT_ALREADY_CREDITED`
    preservan idempotencia (INV-5); `CHAIN_ID_MISMATCH`/`NONCE_CONFLICT` protegen el
    anti-replay (INV-6). La respuesta de error **no** altera balances ni el orderbook.

## Criterios de aceptación (DoD)

### Escenario 1: Envelope uniforme [AT-09-05-01]
- Dado cualquier operación que falle
- Cuando el servidor responde con error
- Entonces el cuerpo tiene exactamente la forma
  `{ "error": { "code", "message", "details"? } }` con `code` y `message` presentes

### Escenario 2: Mapeo de código a HTTP [AT-09-05-02]
- Dado un alta de orden con balance insuficiente
- Cuando el servidor la rechaza
- Entonces el status HTTP es **422** y `error.code == "INSUFFICIENT_FUNDS"` con
  `details = { asset, required, available }`, todos los montos como strings

### Escenario 3 (precedencia): Un error por respuesta [AT-09-05-03]
- Dado un alta de orden que viola **varias** reglas a la vez (p. ej. `side` inválido **y**
  precio fuera de tick **y** fondos insuficientes), enviada con token válido
- Cuando se procesa
- Entonces se reporta **solo el primero** según la precedencia
  (`00-fundaciones/modelo-de-errores.md` §4): aquí `INVALID_SIDE` (enum) antes que
  `INVALID_PRICE_TICK` (regla del par) y antes que `INSUFFICIENT_FUNDS` (fondos)
- Y la respuesta contiene un único `code`

### Escenario 4 (precedencia auth): Auth antes que esquema [AT-09-05-04]
- Dado una request a un recurso protegido con payload inválido y **sin** token
- Cuando se procesa
- Entonces el `code` es `UNAUTHENTICATED` (401), no `VALIDATION_ERROR`

### Escenario 5: VALIDATION_ERROR con issues [AT-09-05-05]
- Dado un alta de orden cuyo `quantityWei` viola `^(0|[1-9][0-9]*)$` (p. ej. `"1.5"`)
- Cuando se procesa
- Entonces el `code` es `VALIDATION_ERROR` (422) y `details.issues` describe la(s)
  causa(s), incluyendo el campo ofensor

### Escenario 6: Montos en details como string [AT-09-05-06]
- Dado un retiro por debajo del mínimo
- Cuando se rechaza con `WITHDRAWAL_BELOW_MIN` (422)
- Entonces `details = { asset, amount, minWithdrawal }` con `amount` y `minWithdrawal` como
  strings que matchean `^(0|[1-9][0-9]*)$`, nunca números JSON

### Escenario 7 (WebSocket): Mismo envelope sin status HTTP [AT-09-05-07]
- Dado una suscripción WS con un mensaje inválido (canal no soportado)
- Cuando el servidor responde por el socket
- Entonces el mensaje es `{ error: { code: "VALIDATION_ERROR", message, details? } }` sin
  status HTTP; el `code` es lo determinante

### Escenario 8 (rate limit): 429 con Retry-After [AT-09-05-08]
- Dado que se supera el límite de tasa
- Cuando llega otra request
- Entonces el status es **429**, `error.code == "RATE_LIMITED"`,
  `details.retryAfterSeconds` presente y header `Retry-After` presente

### Escenario 9 (error de sistema): 500 sin fuga [AT-09-05-09]
- Dado una falla interna no clasificada
- Cuando el servidor responde
- Entonces el status es **500**, `error.code == "INTERNAL_ERROR"` y `message`/`details`
  **no** exponen stack traces, secretos ni internals

### Escenario 10 (ruta/método): NOT_FOUND y 405 [AT-09-05-10]
- Dado la ruta base `/api/v1`
- Cuando se llama a una ruta inexistente
- Entonces el status es **404** con `error.code == "NOT_FOUND"`
- Y un método no permitido sobre una ruta existente responde **405** con
  `error.code == "METHOD_NOT_ALLOWED"` y `details = { method, allowed }`

### Escenario 11 (estabilidad): code del catálogo, message libre [AT-09-05-11]
- Dado un conjunto de operaciones inválidas, una por cada `code` relevante del catálogo
  (`00-fundaciones/modelo-de-errores.md`)
- Cuando la implementación rechaza cada una
- Entonces el `code` devuelto y su status HTTP coinciden **exactamente** con los del catálogo
  (la evaluación compara contra el catálogo, no contra otra implementación), mientras que el
  literal de `message` no se evalúa
- Y ningún `code` devuelto está fuera del catálogo (espacio de nombres cerrado)

### Escenario 12 (invariante): El error no muta estado [AT-09-05-12]
- Dado un alta de orden que será rechazada por `INSUFFICIENT_FUNDS`
- Cuando se procesa
- Entonces los balances de la cuenta quedan **idénticos** a antes de la request (INV-2: se
  rechaza antes de mutar; INV-1: la suma global no cambia) y no se crea orden alguna

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-*) pasan
- [ ] Reglas de negocio RN-1..RN-11 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md)
- [ ] (si aplica) Adherencia verificada al estandar on-chain citado (códigos
      `INVALID_ADDRESS`/`CHAIN_ID_MISMATCH` coherentes con EIP-55/EIP-155)
