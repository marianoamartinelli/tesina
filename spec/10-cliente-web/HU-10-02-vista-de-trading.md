# HU-10-02 — Vista de trading (orderbook en vivo y últimos trades)

- **Epica:** 10 — Cliente Web (React)
- **Actor / rol:** Trader autenticado operando la web
- **Prioridad:** Alta
- **Dependencias:** HU de épica 09 (snapshot REST del orderbook/trades y canales WebSocket); épica 03 (semántica del orderbook, prioridad precio-tiempo); HU-10-01 (sesión activa). Fundaciones (00).
- **Estandares de dominio aplicables:** N/A on-chain. Aplican convenciones monetarias (sin floats) e invariante INV-7 (integridad del orderbook).

## Historia
Como trader autenticado, quiero ver el orderbook del par ETH/USDC actualizado en vivo y la lista de últimos trades, para evaluar el estado del mercado (mejor bid/ask, spread, profundidad y actividad reciente) antes de operar.

## Contexto y alcance
Cubre la vista de mercado del par único ETH/USDC: render del orderbook (bids y asks por nivel de precio), del top of book (mejor bid/ask y spread) y de la lista de últimos trades, alimentados en tiempo real por WebSocket (épica 09) con un snapshot inicial. Cubre reconexión y resincronización ante caídas o gaps de secuencia. No cubre el formulario de alta de órdenes (HU-10-03) ni la lista de órdenes propias (HU-10-04); aquí los datos son de mercado (agregados, no atribuibles a la cuenta). El cliente solo presenta: el ordenamiento y las cantidades provienen del servidor (RNE-2).

## Reglas de negocio e invariantes
1. **RN-1 (snapshot + suscripción).** Al montar la vista, el cliente obtiene un snapshot del orderbook y de los últimos trades, y se suscribe a los canales WebSocket de orderbook y de trades del par ETH/USDC. Al desmontar, se cancela la suscripción.
2. **RN-2 (ordenamiento del libro — INV-7).** Los **bids** se muestran ordenados por precio **descendente** (mejor bid = precio más alto arriba); los **asks** por precio **ascendente** (mejor ask = precio más bajo arriba). El cliente respeta el orden recibido; no reordena con criterios propios que contradigan la prioridad precio-tiempo.
3. **RN-3 (libro no cruzado — INV-7).** Cuando ambos lados existen, debe cumplirse `best_bid < best_ask`. Si un dato recibido presenta libro cruzado, el cliente lo trata como inconsistencia: descarta el dato y fuerza una resincronización (RNE-6).
4. **RN-4 (spread con enteros).** El spread se calcula como `best_ask − best_bid` en **unidades mínimas enteras** de `priceMin` (no floats). Si falta algún lado, el spread es **indefinido** y se muestra como "—" (coherente con el glosario).
5. **RN-5 (formato de montos sin floats — RNE-1).** Precios (`priceMin`, 6 decimales), cantidades (wei, 18 decimales) y profundidad acumulada se reciben como strings de enteros y se formatean a humano por desplazamiento de coma sobre el string. Prohibido `parseFloat`/`Number` sobre montos para cálculo o display que pierda precisión.
6. **RN-6 (últimos trades y último precio).** La lista de trades muestra precio, cantidad, lado del taker (BUY/SELL) y timestamp, con el **más reciente primero**, acotada a **exactamente 50 entradas** (configurable en producción; **50 es el valor del contrato de evaluación**). Cada trade nuevo recibido por WebSocket se inserta al tope respetando el orden temporal; al superar 50, se descarta el más antiguo. El **primer elemento** de la lista representa el **último precio de trade** (`lastPrice`), que además se muestra destacado en el header de la vista (junto al par ETH/USDC), formateado desde `priceMin` a humano por desplazamiento de coma, con **indicador de dirección**: verde si subió respecto al trade inmediatamente anterior, rojo si bajó, neutro si es igual. El dato proviene del mismo canal WebSocket de trades.
7. **RN-7 (aplicación ordenada de updates).** Los updates incrementales se aplican en el orden de secuencia provisto por la API (épica 09). Si se detecta un **gap** (salto de secuencia) o una llegada fuera de orden no recuperable, el cliente solicita un nuevo snapshot y resincroniza (RNE-5).
8. **RN-8 (reconexión).** Ante desconexión del WebSocket, el cliente muestra un indicador de estado "desactualizado", reintenta la conexión con **backoff según RNE-9** (delay inicial 1 s, factor 2, máximo 30 s, jitter ±500 ms), y al reconectar **resuscribe** y solicita un snapshot fresco antes de volver a mostrar datos "en vivo".
9. **RN-9 (libro vacío).** Si un lado o ambos están vacíos, se muestra el lado vacío como tal (sin filas) y el spread como "—"; no se inventan niveles.
10. **RN-10 (consistencia visual del top of book).** El mejor bid y el mejor ask mostrados coinciden siempre con la primera fila del lado correspondiente tras aplicar el ordenamiento de RN-2.
11. **RN-11 (campo de secuencia y detección de gap).** Los updates del orderbook incluyen un campo `sequence` (entero no negativo, **incrementado en 1** por cada update del canal). El cliente mantiene el último `sequence` aplicado y considera un update **contiguo** cuando `update.sequence == ultimo_sequence + 1`. Detecta **gap** cuando `update.sequence > ultimo_sequence + 1` (y descarta como duplicado/fuera de orden cuando `update.sequence <= ultimo_sequence`). Ante un gap, aplica RN-7 (solicita snapshot y resincroniza). El `sequence` del snapshot inicial fija el punto de partida. (El nombre exacto del campo lo fija la épica 09; la **semántica** —entero contiguo +1— es esta.)

## Criterios de aceptación (DoD)

### Escenario 1: Carga inicial del orderbook y trades [AT-10-02-01]
- Dado un trader autenticado que abre la vista de trading
- Cuando la vista monta y obtiene el snapshot y se suscribe a los canales WebSocket
- Entonces se renderizan los bids descendentes por precio y los asks ascendentes por precio
- Y se renderiza la lista de últimos trades con el más reciente primero
- Y el mejor bid y el mejor ask coinciden con la primera fila de cada lado

### Escenario 2: Actualización en vivo del libro [AT-10-02-02]
- Dado el orderbook ya cargado y suscripto por WebSocket
- Cuando llega un update que agrega/modifica/elimina un nivel de precio
- Entonces el libro refleja el cambio manteniendo el ordenamiento precio-tiempo (RN-2)
- Y el top of book y el spread se recalculan en consecuencia

### Escenario 3: Nuevo trade se inserta al tope y se respeta el tope de 50 [AT-10-02-03]
- Dado la lista de últimos trades cargada con 50 entradas
- Cuando llega por WebSocket un nuevo trade del par ETH/USDC
- Entonces se inserta como primer elemento (más reciente)
- Y la lista mantiene exactamente 50 elementos: el elemento 51 (el más antiguo) se descarta

### Escenario 4 (borde): cálculo de spread con enteros [AT-10-02-04]
- Dado `best_bid.priceMin = "2000000000"` y `best_ask.priceMin = "2000500000"`
- Cuando se calcula el spread
- Entonces se obtiene `"500000"` (USDC-min) por resta entera, sin floats
- Y se muestra el spread humano equivalente (0.50 USDC) por desplazamiento de coma

### Escenario 5 (borde): un lado vacío deja spread indefinido [AT-10-02-05]
- Dado un orderbook con bids pero **sin** asks
- Cuando se renderiza el top of book
- Entonces el lado ask se muestra vacío
- Y el spread se muestra como "—" (indefinido)

### Escenario 6 (borde): formato de cantidades sin pérdida de precisión [AT-10-02-06]
- Dado un nivel con `quantityWei = "1500000000000000000"` (1.5 ETH)
- Cuando se formatea para mostrar
- Entonces se muestra exactamente `1.5` ETH (no `1.4999999999999998` ni ninguna aproximación de punto flotante), por desplazamiento de 18 decimales sobre el string
- Y para `quantityWei = "100000000000000000"` se muestra exactamente `0.1` ETH (la prohibición de `parseFloat`/`Number` sobre el monto rige por RN-5; aquí se afirma el resultado observable)

### Escenario 7 (error/borde): libro cruzado se descarta y resincroniza [AT-10-02-07]
- Dado un orderbook con `best_bid.priceMin = "2001000000"` (2001.00) y `best_ask.priceMin = "2002000000"` (2002.00)
- Cuando llega un update que establecería `best_ask.priceMin = "2000000000"` (2000.00), dejando `best_ask < best_bid` (libro cruzado, viola INV-7)
- Entonces el cliente descarta ese update sin aplicarlo
- Y muestra el indicador "desactualizado" y solicita un snapshot fresco para resincronizar antes de volver a "en vivo"

### Escenario 8 (error): gap de secuencia fuerza resync [AT-10-02-08]
- Dado que el último update aplicado tuvo `sequence = 41` (RN-11)
- Cuando el siguiente update recibido trae `sequence = 43` (se salteó el 42: gap)
- Entonces el cliente no aplica ese update sobre un estado potencialmente incompleto
- Y solicita un nuevo snapshot y reconstruye el libro a partir del `sequence` del snapshot
- Y un update con `sequence = 41` o menor (duplicado/fuera de orden) se descarta sin aplicarse

### Escenario 9 (error): desconexión y reconexión con resync [AT-10-02-09]
- Dado la vista mostrando datos en vivo
- Cuando el WebSocket se desconecta
- Entonces se muestra el indicador "desactualizado" y el cliente reintenta conectar
- Y al reconectar resuscribe, pide snapshot fresco y recién entonces vuelve a "en vivo"

### Escenario 10 (error): fallo de la carga inicial del snapshot [AT-10-02-10]
- Dado que el trader abre la vista de trading
- Cuando la solicitud del snapshot inicial falla (error de red o respuesta 5xx)
- Entonces se muestra un mensaje de error no técnico y la opción de reintentar
- Y no se muestra un orderbook vacío como si fuera el estado real del mercado

### Escenario 11 (borde): último precio destacado con indicador de dirección [AT-10-02-11]
- Dado que el último trade aplicado tuvo `priceMin = "2000000000"` (2000.00 USDC)
- Cuando llega un nuevo trade con `priceMin = "2000500000"` (2000.50 USDC)
- Entonces el header muestra `lastPrice = 2000.50` USDC con indicador de dirección **verde** (subió respecto al anterior)
- Y si el siguiente trade llega con `priceMin = "2000000000"`, el indicador pasa a **rojo** (bajó)
- Y el primer elemento de la lista de últimos trades coincide con el `lastPrice` mostrado en el header

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-*) pasan
- [ ] Reglas de negocio RN-1..RN-11 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md)
- [ ] (si aplica) Adherencia verificada al estandar on-chain citado
