# Épica 09 — API HTTP/WebSocket

## Objetivo de la épica

Definir el **contrato de interfaz** que consumen los clientes web (React) y mobile
(React Native/Expo) contra el backend del exchange. La épica especifica la **superficie
observable**: recursos REST (perfil/auth, órdenes, balances, depósitos, retiros,
mercado), sus payloads de request/response y códigos de estado; la **autenticación por
token** y la **autorización** (un usuario solo accede a sus propios recursos); y los
**canales WebSocket** público (orderbook + trades) y privado (órdenes y balances del
usuario). Además, fija la **forma uniforme de los errores** de la API y su mapeo desde el
modelo de errores de dominio.

Esta épica define **el contrato**; el **comportamiento detallado** vive en las épicas de
dominio (01–08). Cuando hay conflicto, prevalece `00-fundaciones`.

---

## Alcance

### Dentro de alcance

- Contrato REST: recursos, métodos HTTP, esquema de request/response, status codes,
  versionado de la ruta base, paginación, idempotencia de alta de orden.
- Autenticación por **token Bearer** en cada request protegida.
- Autorización: aislamiento estricto por cuenta (cada usuario solo ve/opera sus recursos).
- Canal WebSocket **público**: snapshot + actualizaciones incrementales del orderbook y
  stream de trades, con numeración de secuencia para detección de huecos.
- Canal WebSocket **privado autenticado**: actualizaciones de estado de órdenes y de
  balances del usuario.
- Forma uniforme de errores `{ error: { code, message, details } }` y mapeo a HTTP/WS.
- Serialización de todo monto/precio/cantidad/fee/balance como **string de entero** en
  unidad mínima.

### Fuera de alcance

- Reglas de negocio detalladas de cada dominio (matching, settlement, fees, derivación
  on-chain, detección de depósitos, firma de retiros): se **referencian**, no se redefinen.
- KYC/AML, múltiples pares, múltiples redes, tipos de orden avanzados (heredado del alcance
  global del proyecto).
- Hardening de seguridad de producción (rotación de secretos, mTLS, WAF, DDoS).
- Backend específico: la épica es **agnóstica al lenguaje/framework** de servidor. El
  frontend está fijado (React / React Native-Expo) pero su UX se especifica en 10 y 11.

---

## Historias de Usuario

| ID        | Título                                   | Resumen (una línea)                                                                 |
|-----------|------------------------------------------|------------------------------------------------------------------------------------|
| HU-09-01  | Contrato REST                            | Endpoints REST (recursos, métodos, payloads, status codes) de auth, órdenes, balances, depósitos, retiros y mercado. |
| HU-09-02  | Autenticación y autorización de la API   | Token Bearer en las requests y aislamiento por cuenta (cada usuario solo accede a sus recursos). |
| HU-09-03  | WebSocket de mercado (público)           | Snapshot + actualizaciones incrementales del orderbook y stream de trades, con secuencia. |
| HU-09-04  | WebSocket privado del usuario            | Canal autenticado: actualizaciones de estado de órdenes y de balances del usuario.  |
| HU-09-05  | Modelo de errores de la API              | Forma uniforme de las respuestas de error, códigos y mapeo desde el modelo de dominio. |

---

## Dependencias hacia otras épicas

- **00 — Fundaciones:** glosario, activos/par, convenciones monetarias, modelo de errores,
  invariantes globales. **Prevalece sobre esta épica** ante cualquier conflicto.
- **01 — Cuentas y autenticación:** semántica de registro, login, token y autorización
  (esta épica expone su superficie HTTP/WS).
- **02 — Balances y ledger:** semántica de `available`/`locked`/`total` que el endpoint de
  balances y el canal privado serializan.
- **03 — Motor de matching:** orderbook y trades que alimentan los endpoints de mercado y
  el canal público.
- **04 — Gestión de órdenes:** ciclo de vida, validaciones y precedencia de alta/cancelación
  que los endpoints de órdenes exponen.
- **05 — Settlement y fees:** montos de fee y notional que aparecen en órdenes/fills.
- **06 — Wallet HD y direcciones:** dirección de depósito que expone el endpoint de
  depósito.
- **07 — Depósitos on-chain:** estados de depósito y confirmaciones que se listan.
- **08 — Retiros on-chain:** solicitud y estados de retiro que se exponen.

---

## Invariantes y reglas clave de la épica

- **RG-API-1 (ruta base versionada):** todos los recursos REST cuelgan de `/api/v1`. El par
  único se identifica con el símbolo canónico `ETH-USDC`.
- **RG-API-2 (serialización de dinero):** todo monto, precio, cantidad, fee y balance viaja
  como **string de entero decimal** en unidad mínima, patrón `^(0|[1-9][0-9]*)$`. Nunca
  número JSON, decimal, negativo, notación científica ni cero a la izquierda
  (`00-fundaciones/convenciones-monetarias.md` §5). Aplica igual en REST y WebSocket.
- **RG-API-3 (campos y unidades):** cantidades de ETH en wei (`quantityWei`,
  `filledWei`, ...); montos de USDC en unidad de 6 decimales (`amountUsdcMin`, ...); precio
  como `priceMin` (USDC-min por ETH). Cada campo documenta su activo y unidad mínima.
- **RG-API-4 (error uniforme):** toda respuesta de error usa
  `{ error: { code, message, details } }` con `code` estable del catálogo
  (`00-fundaciones/modelo-de-errores.md`). **Un error por respuesta**, el primero según la
  precedencia determinista de la operación.
- **RG-API-5 (autenticación):** los recursos protegidos exigen token Bearer válido; su
  ausencia/invalidez produce `UNAUTHENTICATED` (401). El canal WS privado exige el mismo
  token.
- **RG-API-6 (autorización / aislamiento):** un usuario solo accede a sus propios recursos.
  El acceso cruzado a una orden ajena devuelve `ORDER_NOT_FOUND` (404) para no filtrar
  existencia; los listados nunca incluyen recursos de otra cuenta (INV de privacidad).
- **RG-API-7 (secuencia WebSocket):** los canales emiten primero un **snapshot** y luego
  **deltas** con `sequence` estrictamente creciente y contiguo. La `sequence` es
  **independiente por canal y por símbolo**: `orderbook` tiene su propia secuencia continua,
  `trades` la suya, y los canales privados `orders`, `balances` y `withdrawals` cada uno la
  suya por conexión/suscripción. Un cliente suscrito a varios canales **no** debe comparar
  secuencias entre canales: un hueco se detecta **solo dentro del mismo canal** (un mensaje
  de otro canal con `sequence` distinta no es un hueco). Un hueco dentro de un canal obliga
  al cliente a re-suscribirse a ese canal (re-snapshot).
- **RG-API-11 (endpoint WebSocket):** ambos canales (público y privado) se exponen sobre la
  misma URL base: `wss://<host>/api/v1/ws` (o `ws://` en entorno local de evaluación). El
  servidor puede atender el upgrade WebSocket en el mismo host/puerto que el REST. El canal
  (público vs privado) se determina por el mensaje de suscripción y, para el privado, por la
  autenticación (HU-09-04), no por una URL distinta.
- **RG-API-8 (consistencia con invariantes globales):** lo que la API expone debe ser
  coherente con `00-fundaciones/invariantes-globales.md`: balances no negativos (INV-2),
  `total = disponible + bloqueado` (INV-3), orderbook ordenado por prioridad precio-tiempo y
  no cruzado (INV-7). La API **no** crea ni destruye valor (INV-1): solo refleja estado.
- **RG-API-9 (idempotencia de alta de orden):** el `clientOrderId` provisto por el cliente
  hace idempotente el alta; su reutilización por la misma cuenta devuelve
  `DUPLICATE_CLIENT_ORDER_ID` (409).
- **RG-API-10 (rate limiting):** al superar el límite de tasa se responde `RATE_LIMITED`
  (429) con `details.retryAfterSeconds` y header `Retry-After`.
