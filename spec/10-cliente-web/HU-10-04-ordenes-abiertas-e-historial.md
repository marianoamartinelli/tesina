# HU-10-04 — Órdenes abiertas e historial

- **Epica:** 10 — Cliente Web (React)
- **Actor / rol:** Trader autenticado operando la web
- **Prioridad:** Alta
- **Dependencias:** HU de épica 09 (listado/paginación de órdenes, endpoint de cancelación, canal WebSocket de órdenes); épica 04 (ciclo de vida y estados); HU-10-03 (alta de órdenes). Fundaciones (00).
- **Estandares de dominio aplicables:** N/A on-chain. Aplican estados de orden, modelo de errores y convenciones monetarias (sin floats).

## Historia
Como trader autenticado, quiero ver mis órdenes abiertas con la posibilidad de cancelarlas desde la UI y consultar el historial de mis órdenes pasadas, para controlar mi exposición y revisar mi actividad.

## Contexto y alcance
Cubre dos vistas relacionadas del cliente React: (1) órdenes abiertas (`OPEN` y `PARTIALLY_FILLED`) de la cuenta, con cantidades ejecutada/remanente y acción de cancelar; (2) historial paginado de órdenes terminadas (`FILLED`, `CANCELLED`, `REJECTED`). Los datos se cargan vía REST y se actualizan en vivo por WebSocket (eventos de orden/fill). La cancelación se delega a la API; el estado y la liberación de fondos son autoritativos del backend (épicas 02/04). No cubre el alta (HU-10-03) ni el detalle de settlement por fill (épica 05).

## Reglas de negocio e invariantes
1. **RN-1 (clasificación por estado).** "Órdenes abiertas" lista únicamente `OPEN` y `PARTIALLY_FILLED`. "Historial" lista `FILLED`, `CANCELLED` y `REJECTED`. Una orden que pasa a estado terminal se mueve de abiertas a historial.
2. **RN-2 (columnas).** Cada fila muestra: `orderId`, `side`, `type`, `priceMin` (o "market"), `quantityWei`, cantidad ejecutada, remanente (`quantityWei − ejecutada`), **precio promedio de ejecución** (`avgPriceMin`), `status` y timestamp de creación. El **precio promedio de ejecución** es el monto total ejecutado en quote dividido por la cantidad ejecutada en base, expresado como `priceMin` (string), provisto por la épica 09; para órdenes sin ningún fill (ejecutada = 0) se muestra `"--"`. Es la información más relevante post-trade para MARKET y fills parciales a múltiples precios. Los montos se formatean desde unidad mínima sin floats (RNE-1).
3. **RN-3 (remanente respaldado — INV-7).** El remanente mostrado de una orden abierta corresponde a lo que sigue bloqueado en balances (HU-10-05); el cliente no muestra remanentes que contradigan el bloqueado informado por el servidor (RNE-6).
4. **RN-4 (actualización en vivo).** Vía WebSocket, los eventos de fill/cambio de estado actualizan la fila correspondiente (ejecutada, remanente, status). Al alcanzar un estado terminal, la orden se reubica en historial sin recargar toda la vista.
5. **RN-5 (cancelar — solo cancelables).** El botón "Cancelar" está habilitado solo para `OPEN`/`PARTIALLY_FILLED`. Al cancelar, el cliente llama al endpoint de cancelación (épica 09). Ante éxito, la orden pasa a `CANCELLED` y el remanente bloqueado se libera (reflejado en HU-10-05 por su propio canal).
6. **RN-6 (cancelación no cancelable — concurrencia).** Si la orden ya está `FILLED`/`CANCELLED`/`REJECTED` al momento de cancelar (carrera con un fill), la API responde `ORDER_NOT_CANCELLABLE` (409) con `{ orderId, status }`; el cliente informa el estado real y refresca la fila, sin reintentar a ciegas.
7. **RN-7 (orden inexistente o ajena).** Si la orden no existe **o pertenece a otra cuenta**, la API responde **siempre** `ORDER_NOT_FOUND` (404): la respuesta es indistinguible entre ambos casos para no revelar la existencia de órdenes ajenas (paridad con HU-11-04 RN-3); nunca `UNAUTHORIZED`. El cliente informa y refresca el listado. El cliente nunca opera sobre órdenes de otra cuenta.
8. **RN-8 (anti doble submit de cancelación).** Mientras una cancelación está en curso para una orden, su botón se deshabilita para evitar doble envío.
9. **RN-9 (paginación del historial).** El historial se pagina según el contrato de la épica 09. El cliente es agnóstico al modelo concreto (cursor opaco o número de página): en cada solicitud envía el **parámetro de continuación devuelto por la API en la respuesta anterior** (p. ej. `nextCursor`), tratándolo como opaco. Solicita la siguiente página bajo demanda, no asume un total fijo, y marca "no hay más resultados" cuando la API deja de devolver un parámetro de continuación.
10. **RN-10 (historial vacío).** Si la cuenta no tiene órdenes terminadas, el historial muestra un estado vacío explícito (sin filas), no un error.
11. **RN-11 (orden de presentación).** Las órdenes abiertas se ordenan por **timestamp de creación descendente** (más reciente primero). El historial también se presenta por **timestamp de creación descendente** dentro de cada página (respetando el orden devuelto por la API de la épica 09). Este orden es observable y debe ser idéntico entre implementaciones.

## Criterios de aceptación (DoD)

### Escenario 1: Listado de órdenes abiertas [AT-10-04-01]
- Dado un trader autenticado con dos órdenes: una `OPEN` creada en `t1` y una `PARTIALLY_FILLED` creada en `t2`, con `t2 > t1`
- Cuando abre la vista de órdenes abiertas
- Entonces se listan solo esas órdenes con sus columnas (RN-2), incluida la columna de precio promedio de ejecución
- Y aparecen ordenadas por timestamp de creación descendente: la de `t2` antes que la de `t1` (RN-11)
- Y las cantidades se muestran formateadas desde unidad mínima sin floats
- Y el remanente mostrado = `quantityWei − ejecutada`
- Y la orden `OPEN` sin fills muestra `avgPriceMin = "--"`

### Escenario 2: Actualización en vivo por fill parcial [AT-10-04-02]
- Dado una orden `OPEN` listada con `avgPriceMin = "--"`
- Cuando llega por WebSocket un fill parcial de esa orden
- Entonces la fila pasa a `PARTIALLY_FILLED`, actualiza ejecutada, remanente y `avgPriceMin` (precio promedio provisto por la API)
- Y permanece en órdenes abiertas

### Escenario 3: Orden pasa a terminal y se mueve a historial [AT-10-04-03]
- Dado una orden `PARTIALLY_FILLED` listada en abiertas
- Cuando un fill la completa (`FILLED`)
- Entonces deja de aparecer en órdenes abiertas
- Y aparece en el historial con estado `FILLED` y su `avgPriceMin` (precio promedio de ejecución) poblado

### Escenario 4: Cancelación exitosa desde la UI [AT-10-04-04]
- Dado una orden `OPEN` de la cuenta
- Cuando el usuario presiona "Cancelar" y la API responde éxito
- Entonces la orden pasa a `CANCELLED` y se mueve a historial
- Y el botón "Cancelar" ya no aparece para esa orden
- (El impacto en balances —liberación del remanente bloqueado— se verifica en HU-10-05 y en el escenario de integración AT-10-E2E-01 del README, no en este AT)

### Escenario 5 (error/concurrencia): cancelar una orden ya ejecutada [AT-10-04-05]
- Dado una orden `OPEN` que se completa por un fill justo antes de cancelar
- Cuando el usuario presiona "Cancelar" y la API responde `{ error: { code: "ORDER_NOT_CANCELLABLE", details: { orderId, status: "FILLED" } } }` (409)
- Entonces el cliente informa que la orden ya no es cancelable y muestra su estado real
- Y refresca la fila sin reintentar la cancelación automáticamente

### Escenario 6 (error): cancelar orden inexistente o ajena [AT-10-04-06]
- Dado un `orderId` que no existe o no pertenece a la cuenta
- Cuando el usuario intenta cancelarla y la API responde `ORDER_NOT_FOUND` (404) — la misma respuesta en ambos casos, sin revelar la existencia de órdenes ajenas (RN-7)
- Entonces el cliente informa el error correspondiente y refresca el listado
- Y no se altera ninguna orden ajena

### Escenario 7 (borde): anti doble submit de cancelación [AT-10-04-07]
- Dado una cancelación en curso para una orden
- Cuando el usuario vuelve a presionar "Cancelar" en esa misma orden
- Entonces el segundo clic se ignora y el botón permanece deshabilitado hasta resolver

### Escenario 8: Paginación del historial [AT-10-04-08]
- Dado un historial con más resultados que una página
- Cuando el usuario solicita la siguiente página
- Entonces el cliente pide la página siguiente según el contrato de la épica 09 y la agrega al listado
- Y cuando la API indica que no hay más resultados, se deshabilita "cargar más"

### Escenario 9 (borde): historial vacío [AT-10-04-09]
- Dado una cuenta sin órdenes terminadas
- Cuando abre el historial
- Entonces se muestra un estado vacío explícito (sin filas) y no un error

### Escenario 10 (borde): orden REJECTED en historial [AT-10-04-10]
- Dado una cuenta con una orden `REJECTED` persistida por un rechazo **del matching** (p. ej. una MARKET rechazada por `MARKET_NO_LIQUIDITY`, o una orden rechazada por `SELF_TRADE_BLOCKED`; los rechazos de validación/fondos **no** se persisten como orden, HU-04-05 RN-5)
- Cuando el usuario abre el historial
- Entonces aparece la orden con estado `REJECTED`, ejecutada = `0` y remanente = `quantityWei`
- Y `avgPriceMin = "--"` (nunca tuvo fills) y se muestra el motivo de rechazo si la API lo provee
- Y el botón "Cancelar" no aparece para órdenes `REJECTED`

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-*) pasan
- [ ] Reglas de negocio RN-1..RN-11 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md)
- [ ] (si aplica) Adherencia verificada al estandar on-chain citado
