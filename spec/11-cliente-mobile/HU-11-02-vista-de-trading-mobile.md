# HU-11-02 — Vista de trading en mobile (orderbook y últimos trades)

- **Epica:** 11 — Cliente Mobile (React Native / Expo)
- **Actor / rol:** Trader (vista de mercado del par ETH/USDC)
- **Prioridad:** Alta
- **Dependencias:** HU-10-02 (paridad web: vista de trading), épica 09 (WebSocket de
  market data), épica 03 (motor de matching / orderbook)
- **Estandares de dominio aplicables:** N/A (no on-chain)

## Historia
Como trader, quiero ver el **orderbook en vivo** y los **últimos trades** del par
ETH/USDC-mock adaptados a la pantalla del celular, para evaluar el mercado y decidir mis
órdenes desde mobile.

## Contexto y alcance
Cubre la vista de trading mobile que **consume el mismo stream de market data** que el web
(HU-10-02), definido por la épica 09 (WebSocket): niveles de bids y asks (profundidad),
best bid/ask y spread, y los últimos trades, todo **en vivo**. El cliente sólo **renderiza**
lo recibido: no recalcula matching ni infiere prioridad (la fija el backend, INV-7).

El foco mobile son las diferencias respecto del web: layout vertical compacto, manejo del
**ciclo de vida** (suspender/reanudar la suscripción al ir a background/foreground),
**reconexión** del WebSocket con resync, indicador de estado de conexión y
**pull-to-refresh**. No cubre la colocación de órdenes (HU-11-03) ni el matching (épica 03).

## Reglas de negocio e invariantes
1. **RN-1:** La vista consume el stream de market data (orderbook + trades) de la épica 09
   (WebSocket), con el **mismo contrato** que el web. El cliente no recalcula ni reordena la
   lógica de matching; sólo refleja el estado recibido.
2. **RN-2:** Todos los precios/cantidades llegan como **string de entero de unidad mínima**
   (`^(0|[1-9][0-9]*)$`). El cliente los formatea a humano con aritmética exacta:
   ETH = `q_wei / 10¹⁸` (cantidad), precio = `price_min / 10⁶` (USDC/ETH). **Prohibido**
   parsear con `float`/`Number`/`parseFloat` montos que excedan 2⁵³; usar **BigInt** o
   decimal de precisión fija. **Regla de presentación (decimales fijos con padding):** el
   **precio** se muestra con **exactamente 2 decimales** (tick 0.01; p. ej. `2000` →
   `2000.00`, `2000.5` → `2000.50`) y la **cantidad** con **exactamente 4 decimales** (lot
   0.0001; p. ej. `5` → `5.0000`, `0.0001` → `0.0001`). Nunca se muestran más decimales que
   los permitidos por tick (2) y lot (4).
3. **RN-3:** El orderbook se presenta según prioridad precio-tiempo (INV-7): **bids**
   ordenados por precio **descendente**, **asks** por precio **ascendente**; el cliente
   refleja el orden provisto por el backend, no lo reordena por su cuenta.
4. **RN-4:** `best_bid`, `best_ask` y `spread = best_ask − best_bid` se derivan con
   **aritmética entera exacta** sobre `price_min`. Si falta un lado del libro, el spread es
   **indefinido** y se muestra como "—".
5. **RN-5:** Actualizaciones en vivo: ante cada mensaje (snapshot y/o deltas, según épica
   09) la vista refleja el nuevo estado conservando el orden. **Mecanismo de detección de
   deltas fuera de secuencia:** cada mensaje del canal lleva el campo **`sequence`** (entero
   estrictamente creciente y **contiguo** por canal/suscripción; épica 09, HU-09-03 RN-5 y
   RG-API-7). El cliente mantiene el último `sequence` procesado y, si recibe un mensaje con
   `sequence ≠ lastSequence + 1` (hueco), **descarta** el delta y **re-solicita un snapshot**
   (resync) **antes** de procesar cualquier delta posterior. La detección de hueco es
   **sólo dentro del mismo canal** (no se comparan secuencias entre `orderbook` y `trades`).
6. **RN-6 (ciclo de vida):** al pasar a background, la app puede suspender/cerrar la
   suscripción WebSocket para ahorrar recursos. Al volver a foreground, **reconecta** y
   **re-sincroniza** (snapshot fresco) **antes** de aplicar nuevos deltas.
7. **RN-7 (reconexión):** ante caída del WebSocket, el cliente reconecta con backoff y, al
   reconectar, solicita snapshot. Muestra un **indicador de estado de conexión** (en vivo /
   reconectando / desconectado). Los parámetros de backoff son los de **RG-10** del README
   (delay inicial 1 s, factor 2×, máximo 30 s, jitter ±500 ms).
8. **RN-8 (últimos trades):** se muestran los últimos **N = 50** trades (paridad con el web,
   HU-10-02 RN-6: 50 es el valor del contrato de evaluación, configurable en producción) con
   precio, cantidad, lado/agresor (taker) y timestamp, en orden **cronológico descendente**,
   formateados sin floats (RN-2). Cada trade nuevo se inserta al tope; al superar 50, se
   descarta el más antiguo.
9. **RN-9:** Pull-to-refresh fuerza un resync manual (snapshot fresco).
10. **RN-10:** La vista muestra sólo market data agregada/anónima; **no** expone datos de
    cuentas ni órdenes de otros usuarios.

## Criterios de aceptación (DoD)

### Escenario 1: Render inicial del orderbook y spread [AT-11-02-01]
- Dado que la app se suscribe al stream de market data (épica 09)
- Cuando recibe el snapshot inicial del orderbook
- Entonces muestra los bids ordenados por precio descendente y los asks por precio
  ascendente
- Y muestra best bid, best ask y `spread = best_ask − best_bid` calculado con enteros
- Y todos los precios/cantidades se muestran formateados a humano sin floats

### Escenario 2: Actualización en vivo de un nivel [AT-11-02-02]
- Dado un orderbook ya renderizado
- Cuando llega un delta que modifica la cantidad de un nivel de precio
- Entonces la vista actualiza ese nivel conservando el orden precio-tiempo
- Y best bid/ask y spread se recalculan en consecuencia

### Escenario 3: Últimos trades en vivo (tope de 50) [AT-11-02-03]
- Dado el stream de trades activo con la lista al límite de **50** entradas (RN-8)
- Cuando llega un nuevo trade (precio, cantidad, agresor, timestamp)
- Entonces aparece al tope de la lista de últimos trades (orden cronológico descendente)
- Y la lista mantiene **exactamente 50** entradas, descartando el más antiguo
- Y sus montos se muestran formateados sin floats (precio 2 decimales, cantidad 4 decimales)

### Escenario 4 (borde): Un lado del libro vacío [AT-11-02-04]
- Dado un orderbook con un solo lado (p. ej. sin asks)
- Cuando se renderiza la vista
- Entonces el spread se muestra como "—" (indefinido)
- Y la vista no se rompe ni muestra valores inventados

### Escenario 5 (borde): Formato exacto de montos grandes [AT-11-02-05]
- Dado un nivel con cantidad en wei mayor a 2⁵³ (p. ej. `"5000000000000000000"` = 5 ETH y
  superiores)
- Cuando se formatea para mostrar
- Entonces el valor humano mostrado es **exactamente `5.0000` ETH** (4 decimales, RN-2),
  sin pérdida por punto flotante
- Y se usa BigInt/decimal de precisión fija para la conversión

### Escenario 6 (ciclo de vida): Background suspende y foreground re-sincroniza [AT-11-02-06]
- Dado la vista de trading activa y suscrita, con un **mock del WebSocket** que simula el
  cierre de conexión al pasar a background (RG-11)
- Cuando la app pasa a background (la suscripción se cierra) y luego vuelve a foreground
- Entonces al reanudar reconecta y solicita un snapshot fresco
- Y aplica deltas sólo después de re-sincronizar

### Escenario 7 (reconexión): Caída del WebSocket [AT-11-02-07]
- Dado el stream activo
- Cuando el WebSocket se cae
- Entonces el cliente muestra el indicador "reconectando" y reintenta con backoff
- Y al reconectar solicita un snapshot y vuelve al estado "en vivo"

### Escenario 8 (borde): Resync por deltas fuera de secuencia [AT-11-02-08]
- Dado un orderbook en vivo cuyo último mensaje procesado tenía `sequence = s`
- Cuando llega un delta con `sequence = s + 2` (hueco; falta `s + 1`) en el mismo canal
- Entonces el cliente **descarta** ese delta, solicita un nuevo snapshot y reemplaza el
  estado local por el snapshot antes de continuar aplicando deltas (RN-5)

### Escenario 9: Pull-to-refresh fuerza resync [AT-11-02-09]
- Dado la vista de trading visible
- Cuando el usuario hace pull-to-refresh
- Entonces el cliente solicita un snapshot fresco y actualiza la vista

### Escenario 10 (borde): Formato según tick y lot [AT-11-02-10]
- Dado un nivel con `price_min = 2000500000` y `q_wei = 100000000000000` (0.0001 ETH)
- Cuando se formatea para mostrar
- Entonces el precio se muestra como `2000.50` (2 decimales) y la cantidad como `0.0001`
  (4 decimales)
- Y no se muestran más decimales que los permitidos por tick (2) y lot (4)

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-*) pasan
- [ ] Reglas de negocio RN-1..RN-10 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md
- [ ] Invariantes globales: el cliente **refleja** sin reordenar la prioridad precio-tiempo
      del orderbook (**INV-7**), que es responsabilidad del backend; INV-1, INV-4, INV-5,
      INV-6 e INV-8 también son del backend — el cliente no los garantiza
      (00-fundaciones/invariantes-globales.md)
- [ ] (si aplica) Adherencia verificada al estandar on-chain citado
