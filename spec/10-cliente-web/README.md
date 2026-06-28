# Épica 10 — Cliente Web (React)

## Objetivo de la épica

Especificar el **cliente web en React** que consume la API HTTP/WebSocket del exchange
(épica 09) para que un trader autenticado pueda operar el par único **ETH/USDC-mock**:
iniciar sesión, observar el mercado en vivo (orderbook + últimos trades), colocar y
gestionar órdenes, consultar balances y operar depósitos/retiros on-chain (Sepolia,
chainId `11155111`).

El cliente web es una **capa de presentación**: no contiene lógica de negocio
autoritativa. El **servidor es la única fuente de verdad** para validaciones, matching,
settlement, fees, balances y estado on-chain. Las validaciones del lado del cliente
existen solo para mejorar la UX (feedback inmediato) y **nunca** sustituyen ni relajan
las del backend. Toda discrepancia se resuelve a favor de la respuesta del servidor.

## Alcance

Dentro de alcance (pantallas mínimas):

- **Login** (HU-10-01): autenticación, manejo de credenciales y de expiración de sesión.
- **Vista de trading** (HU-10-02): orderbook en vivo vía WebSocket + últimos trades.
- **Formulario de orden** (HU-10-03): alta de órdenes `LIMIT`/`MARKET` con validación
  del lado del cliente y feedback del resultado.
- **Órdenes abiertas e historial** (HU-10-04): listado de órdenes abiertas con
  cancelación desde la UI e historial paginado.
- **Balances** (HU-10-05): disponible/bloqueado por activo, con actualizaciones en vivo.
- **Depósitos y retiros** (HU-10-06): mostrar dirección de depósito y formulario de
  retiro con validaciones y seguimiento de estado.

Fuera de alcance:

- Lógica de matching, settlement, derivación de claves, firma o broadcast on-chain (viven
  en backend; el cliente solo consume la API de épicas 03–09).
- KYC/AML, múltiples pares, múltiples redes, tipos de orden avanzados (heredado de
  `00-fundaciones`).
- Hardening de seguridad de producción (CSP avanzada, anti-fraude, etc.).
- Definición del contrato de endpoints/canales (lo fija la épica 09; aquí se **consume**).

## Historias de Usuario

| ID        | Título                                | Resumen (una línea)                                                              |
|-----------|---------------------------------------|---------------------------------------------------------------------------------|
| HU-10-01  | Pantalla de login                     | Inicio de sesión web; manejo de credenciales inválidas y expiración de sesión.  |
| HU-10-02  | Vista de trading                      | Orderbook en vivo (WebSocket) y últimos trades del par ETH/USDC.                 |
| HU-10-03  | Formulario de orden                   | Alta de órdenes limit/market con validación cliente y feedback del resultado.   |
| HU-10-04  | Órdenes abiertas e historial          | Listado de órdenes abiertas con cancelación desde la UI e historial paginado.   |
| HU-10-05  | Balances                              | Disponible/bloqueado por activo con actualizaciones en vivo.                     |
| HU-10-06  | Depósitos y retiros                   | Dirección de depósito y formulario de retiro con validaciones y seguimiento.    |

## Dependencias hacia otras épicas

- **09 — API HTTP/WebSocket:** contrato de endpoints REST, canales WebSocket, paginación
  y formato de respuestas/errores. Todo el cliente web consume esta API.
- **01 — Cuentas y autenticación:** semántica de login/sesión que HU-10-01 expone.
- **02 — Balances y ledger:** semántica de disponible/bloqueado que HU-10-05 visualiza.
- **03 — Motor de matching / 04 — Gestión de órdenes:** estados y ciclo de vida de
  órdenes que HU-10-03 y HU-10-04 reflejan.
- **05 — Settlement y fees:** las fees y el notional que HU-10-03 estima.
- **06 — Wallet HD / 07 — Depósitos / 08 — Retiros:** dirección de depósito, estados de
  depósito y retiro que HU-10-06 visualiza.
- **00 — Fundaciones:** glosario, activos/par, convenciones monetarias, modelo de errores
  e invariantes globales (prevalecen ante cualquier conflicto).

## Invariantes y reglas clave de la épica

1. **RNE-1 (formato monetario sin floats).** Todo monto/precio/cantidad/fee/balance se
   recibe y se envía a la API como **string de entero decimal en unidad mínima** que
   matchea `^(0|[1-9][0-9]*)$`. El cliente **nunca** usa floats binarios (IEEE-754) para
   montos: la conversión humano⇄unidad mínima se hace con aritmética de enteros grandes
   (big integers) o decimal de precisión fija, por desplazamiento de coma decimal sobre
   strings. Decimales por activo: ETH/wei = 18, USDC = 6, `priceMin` = 6.
   Ver `00-fundaciones/convenciones-monetarias.md`.
2. **RNE-2 (servidor autoritativo).** Las validaciones del cliente (tick, lot, min
   notional, checksum de dirección, etc.) son réplicas de UX; ante respuesta del servidor,
   prevalece el servidor. El cliente no debe asumir éxito antes de recibir respuesta.
3. **RNE-3 (errores del catálogo).** Toda respuesta `{ error: { code, message, details } }`
   se maneja por su `code` estable (no por el `message`). Los mensajes mostrados al usuario
   se derivan del `code` del catálogo `00-fundaciones/modelo-de-errores.md`.
4. **RNE-4 (sesión).** Ante `UNAUTHENTICATED` (401) en cualquier llamada protegida, el
   cliente limpia la sesión local y redirige a login. El token de sesión nunca se registra
   en logs ni se expone en la UI.
5. **RNE-5 (tiempo real).** Las vistas en vivo (orderbook, trades, órdenes, balances) se
   alimentan por WebSocket (épica 09). Ante desconexión, el cliente muestra estado
   "desactualizado", reintenta la conexión y **resincroniza** con un snapshot al
   reconectar (no asume continuidad de secuencia tras un gap).
6. **RNE-6 (consistencia de invariantes verificables en presentación).** El cliente nunca
   muestra un estado que viole los invariantes globales **que puede verificar con los datos
   que recibe**: (a) `total = disponible + bloqueado` (INV-3); (b) balances no negativos,
   `disponible ≥ 0` y `bloqueado ≥ 0` (INV-2); (c) orderbook no cruzado, `best_bid <
   best_ask` cuando ambos lados existen, y el orden precio-tiempo del libro recibido (INV-7,
   primera condición observable). Si un dato recibido viola alguna de estas condiciones, se
   trata como inconsistencia: se descarta y se resincroniza con un snapshot fresco. En
   cambio, la condición de **respaldo de fondos por orden** de INV-7 (que el `bloqueado`
   cubra el remanente de cada orden abierta) **no es verificable desde el frontend** —el
   cliente no tiene acceso al ledger ni al desglose de `bloqueado` por orden— y es
   responsabilidad exclusiva del backend; el cliente confía en los datos recibidos (RNE-2).
7. **RNE-7 (idempotencia de alta de orden).** El cliente genera un `clientOrderId` por
   intento lógico de alta y lo **reutiliza** en reintentos del mismo envío, apoyándose en
   `DUPLICATE_CLIENT_ORDER_ID` para no duplicar órdenes (ver HU-10-03).
8. **RNE-8 (red on-chain única).** Toda la UX on-chain (HU-10-06) refiere exclusivamente a
   **Sepolia, chainId `11155111`**; direcciones con checksum **EIP-55**; confirmaciones
   requeridas = **12**. Ver `00-fundaciones/activos-y-par-de-trading.md`.
9. **RNE-9 (política de reconexión WebSocket).** Ante desconexión de cualquier canal en
   vivo, el cliente reintenta la conexión con **backoff exponencial**: delay inicial
   **1 s**, factor multiplicador **2**, delay máximo **30 s**, con **jitter** uniforme de
   **±500 ms** aplicado a cada delay (secuencia base 1 s, 2 s, 4 s, 8 s, 16 s, 30 s, 30 s…).
   Estas constantes son el **contrato de evaluación**; en producción son configurables. Esta
   política rige para HU-10-02 (RN-8), HU-10-04 (canal de órdenes) y HU-10-05 (RN-7).
10. **RNE-10 (servidor como fuente de verdad del estado on-chain; reorgs).** El cliente
   nunca asume que un estado on-chain es permanente: sigue siempre al servidor (RNE-2). Si
   un depósito previamente `ACREDITADO` es **revertido** por el backend a raíz de una
   reorganización de la cadena (en Sepolia los tiempos de bloque son cortos y las reorgs
   superficiales son posibles), el backend emite un evento de reversión por WebSocket; el
   cliente muestra ese depósito como `REVERTIDO` con su `(txHash, logIndex)` y aplica el
   nuevo balance informado por el servidor, **sin** tratar la baja de balance como
   inconsistencia ni disparar una resincronización por aparente violación de invariantes
   (ver HU-10-06 RN-12 y HU-10-05 RN-6).

## Escenarios de integración entre HUs

Además de los criterios de aceptación por HU, la épica define al menos un flujo
**end-to-end** que verifica la integración de datos entre componentes (no reemplaza a los
AT por HU). El identificador `AT-10-E2E-*` es trazable como cualquier otro AT.

### AT-10-E2E-01 — Ciclo completo de trading

- Dado un usuario con credenciales válidas
- Cuando inicia sesión (HU-10-01) y es dirigido a la vista de trading
- Y observa el orderbook y los últimos trades en vivo (HU-10-02)
- Y coloca una orden `LIMIT BUY` válida con `clientOrderId` (HU-10-03) que queda `OPEN`
- Entonces la orden aparece en "órdenes abiertas" (HU-10-04)
- Y el balance de USDC refleja el bloqueo del notional (disponible↓, bloqueado↑, total
  constante) en la vista de balances (HU-10-05)
- Cuando el usuario cancela la orden (HU-10-04)
- Entonces la orden pasa a `CANCELLED` y se mueve al historial (HU-10-04)
- Y el balance de USDC refleja la liberación (bloqueado↓, disponible↑) (HU-10-05)
- Cuando solicita un retiro de USDC válido (HU-10-06)
- Entonces el balance refleja el bloqueo del retiro y el retiro avanza por su ciclo de
  estados (`SOLICITADO` → … → `CONFIRMADO`)
- Y, ante `UNAUTHENTICATED` en cualquier paso protegido, el cliente limpia la sesión y
  vuelve a login (HU-10-01, RNE-4)
