# HU-10-05 — Balances por activo (disponible y bloqueado)

- **Epica:** 10 — Cliente Web (React)
- **Actor / rol:** Trader autenticado operando la web
- **Prioridad:** Alta
- **Dependencias:** HU de épica 09 (snapshot REST de balances y canal WebSocket de balances); épica 02 (modelo disponible/bloqueado/total y ledger); HU-10-01 (sesión). Fundaciones (00).
- **Estandares de dominio aplicables:** N/A on-chain. Aplican invariantes INV-2 (no-negatividad) e INV-3 (total = disponible + bloqueado) y convenciones monetarias (sin floats).

## Historia
Como trader autenticado, quiero ver mis balances por activo (ETH y USDC) discriminados en disponible y bloqueado, actualizados en vivo, para conocer cuánto puedo operar o retirar en cada momento.

## Contexto y alcance
Cubre la vista de balances del cliente React para los dos activos del proyecto (ETH y USDC-mock): muestra disponible, bloqueado y total por activo, con carga inicial vía REST y actualizaciones en vivo por WebSocket (al bloquear/liberar por órdenes, al liquidar fills, al acreditar depósitos o procesar retiros). No cubre el detalle del ledger ni los movimientos individuales (épica 02); solo el agregado de balances. El backend es la fuente de verdad de los montos (RNE-2); el cliente solo presenta y recompone `total`.

## Reglas de negocio e invariantes
1. **RN-1 (activos mostrados).** Se muestran exactamente los dos activos del par: **ETH** (18 decimales, wei) y **USDC** (6 decimales). No se inventan otros activos.
2. **RN-2 (campos por activo).** Por cada activo se muestran `disponible`, `bloqueado` y `total`, todos en unidad mínima recibidos como strings de entero.
3. **RN-3 (total recompuesto con enteros — INV-3).** El `total` se calcula como `disponible + bloqueado` mediante **suma de enteros grandes** sobre los strings de unidad mínima (no floats). Si la API también envía `total`, debe coincidir con la suma; ante discrepancia, el cliente trata el dato como inconsistente y resincroniza (RNE-6).
4. **RN-4 (no-negatividad — INV-2).** El cliente nunca muestra `disponible < 0` ni `bloqueado < 0`. Un valor negativo recibido se trata como inconsistencia (se descarta y se resincroniza), no se "corrige" mostrando 0.
5. **RN-5 (formato humano sin floats — RNE-1).** Los valores se formatean a humano por desplazamiento de coma sobre el string (ETH: 18 decimales; USDC: 6 decimales). Prohibido `parseFloat`/`Number` que pierda precisión.
6. **RN-6 (actualización en vivo).** El cliente se suscribe al canal de balances por WebSocket y aplica las actualizaciones recibidas:
   - **bloquear** (por orden **o por retiro solicitado**): `disponible ↓`, `bloqueado ↑`, total constante;
   - **liberar** (cancelación, sobrante tras fill **o retiro fallido/cancelado**): `bloqueado ↓`, `disponible ↑`, total constante;
   - **consumir por fill** (al liquidar): cambia el total por activo;
   - **acreditar depósito**: `disponible ↑`;
   - **retiro confirmado**: `bloqueado ↓` (el monto retenido sale del balance interno; el total por activo baja, coherente con INV-1);
   - **depósito revertido por reorg** (RNE-10): el servidor informa el nuevo balance a la baja; el cliente lo aplica **sin** tratarlo como inconsistencia ni resincronizar.

   En el modelo disponible/bloqueado de la épica 02, un **retiro solicitado** retiene el monto (`disponible ↓ = monto`, `bloqueado ↑ = monto`, total constante) hasta su confirmación on-chain; al confirmarse, el `bloqueado` se consume y el total baja. El `total` mostrado se recalcula en cada update (RN-3).
7. **RN-7 (snapshot inicial + resync).** Al montar, obtiene un snapshot REST; ante desconexión/gap del WebSocket, muestra estado "desactualizado", reintenta con **backoff según RNE-9** y resincroniza con un snapshot fresco antes de volver a "en vivo" (RNE-5).
8. **RN-8 (balance cero).** Un activo sin fondos se muestra con `0` en disponible, bloqueado y total (no se oculta el activo ni se muestra vacío).

## Criterios de aceptación (DoD)

### Escenario 1: Carga inicial de balances [AT-10-05-01]
- Dado un trader autenticado
- Cuando abre la vista de balances y se obtiene el snapshot
- Entonces se muestran ETH y USDC con disponible, bloqueado y total
- Y los montos se formatean desde unidad mínima sin floats (ETH 18 dec, USDC 6 dec)

### Escenario 2: Total recompuesto con enteros [AT-10-05-02]
- Dado USDC con `disponible="5000000"` y `bloqueado="10000000"`
- Cuando el cliente calcula el total
- Entonces obtiene `total="15000000"` (15 USDC) por suma entera de strings
- Y, si la API envía `total`, coincide con el calculado

### Escenario 3: Actualización en vivo al bloquear fondos por una orden [AT-10-05-03]
- Dado USDC con `disponible="20000000"` y `bloqueado="0"`
- Cuando el usuario coloca una orden que bloquea `10000000` y llega el update por WebSocket
- Entonces se muestra `disponible="10000000"`, `bloqueado="10000000"`
- Y el total permanece en `"20000000"` (INV-3: total constante al bloquear)

### Escenario 4: Actualización en vivo al liquidarse un fill [AT-10-05-04]
- Dado USDC con `bloqueado="2000500000"`, `disponible="0"`; y ETH con `disponible="0"`
- Cuando un fill de compra de 1 ETH a `priceMin="2000500000"` se liquida (rol taker, fee 20 bps) y llega el update por WebSocket
- Entonces USDC pasa a `bloqueado="0"` (se consumió el notional) y ETH a `disponible="998000000000000000"` (= 10^18 − ceil(10^18 × 20 / 10000) = 10^18 − 2000000000000000)
- Y los totales por activo respetan INV-2 (no-negatividad) e INV-3 (total = disponible + bloqueado), sin floats

### Escenario 5: Actualización en vivo al acreditarse un depósito [AT-10-05-05]
- Dado ETH con `disponible="0"`
- Cuando un depósito confirmado se acredita y llega el update por WebSocket
- Entonces el disponible de ETH aumenta por el monto acreditado
- Y el total refleja el nuevo disponible

### Escenario 6 (borde): balance cero [AT-10-05-06]
- Dado un activo sin fondos
- Cuando se renderiza la vista
- Entonces se muestra `0` en disponible, bloqueado y total para ese activo (no se oculta)

### Escenario 7a (error/borde): update con disponible negativo se descarta [AT-10-05-07a]
- Dado un update que establecería el `disponible` de ETH en `"-1"` (negativo, viola INV-2)
- Cuando el cliente lo recibe
- Entonces descarta el dato inconsistente (no muestra negativos)
- Y solicita un snapshot fresco para resincronizar

### Escenario 7b (error/borde): update con total incoherente se descarta [AT-10-05-07b]
- Dado un update con `disponible="5000000"`, `bloqueado="10000000"` pero `total="14999999"` (≠ 15000000, viola INV-3)
- Cuando el cliente lo recibe
- Entonces descarta el dato inconsistente (no rompe INV-3)
- Y solicita un snapshot fresco para resincronizar

### Escenario 8 (error): reconexión del canal de balances [AT-10-05-08]
- Dado la vista mostrando balances en vivo
- Cuando el WebSocket se desconecta
- Entonces se muestra el indicador "desactualizado" y el cliente reintenta conectar (backoff RNE-9)
- Y al reconectar pide snapshot fresco y recién entonces vuelve a "en vivo"

### Escenario 9: Actualización en vivo al solicitar un retiro [AT-10-05-09]
- Dado USDC con `disponible="50000000"` y `bloqueado="0"`
- Cuando el usuario solicita un retiro de `25000000` (25 USDC) y llega el update por WebSocket
- Entonces se muestra `disponible="25000000"`, `bloqueado="25000000"`
- Y el total permanece en `"50000000"` (INV-3: total constante al retener el retiro)
- Y el cambio se refleja sin necesidad de refrescar (evita intentar un segundo retiro por fondos ya reservados)

### Escenario 10 (error): fallo de carga del snapshot inicial de balances [AT-10-05-10]
- Dado que el trader abre la vista de balances
- Cuando la solicitud REST del snapshot falla (error de red o 5xx)
- Entonces se muestra un mensaje de error y la opción de reintentar
- Y no se muestran los activos con saldo `0` como si fueran los balances reales

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-*) pasan
- [ ] Reglas de negocio RN-1..RN-8 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md)
- [ ] (si aplica) Adherencia verificada al estandar on-chain citado
