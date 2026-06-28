# HU-07-04 — Idempotencia y reorgs

- **Epica:** 07 — Depósitos On-Chain
- **Actor / rol:** Sistema (servicio de detección / acreditación on-chain)
- **Prioridad:** Alta
- **Dependencias:** HU-07-01 (detección ETH nativo); HU-07-02 (detección USDC ERC-20); HU-07-03 (confirmaciones y acreditación); Épica 02 (balances y ledger)
- **Estandares de dominio aplicables:** Red Sepolia chainId 11155111; `CONFIRMACIONES_REQUERIDAS = 12`

## Historia
Como Sistema de acreditación on-chain, quiero garantizar que cada depósito identificado por `(txHash, logIndex)` se acredite **a lo sumo una vez** y manejar correctamente las reorganizaciones de cadena y las transacciones revertidas, para que nunca se produzca una doble acreditación ni se acrediten fondos que la cadena terminó descartando.

## Contexto y alcance
Esta HU implementa el invariante INV-5 (idempotencia de la acreditación) y el manejo de **reorgs** y **reversiones**. Cubre: (a) deduplicación por identidad `(txHash, logIndex)` —con `logIndex = 0` para ETH nativo—; (b) concurrencia (dos procesadores que observan el mismo depósito simultáneamente); (c) reorgs que dejan huérfano el bloque de inclusión **antes** de confirmar; (d) reorgs que reincluyen la transacción en otro bloque; (e) transacciones revertidas.

El umbral de `CONFIRMACIONES_REQUERIDAS = 12` (HU-07-03) es la defensa principal contra reorgs: solo se acredita tras 12 confirmaciones. **Supuesto explícito (fuera de alcance):** no ocurren reorgs de profundidad mayor a 12 bloques; por lo tanto, un depósito ya acreditado se considera irreversible y la spec no modela el "des-acreditar" tras una reorg profunda.

## Reglas de negocio e invariantes
1. **RN-1 (identidad única):** la identidad de un depósito es `(txHash, logIndex)`; para ETH nativo, `logIndex = 0` (HU-07-01); para USDC ERC-20, `logIndex` es el **índice global del log `Transfer` dentro del bloque** (block-scoped, HU-07-02 RN-7), no el índice dentro de la transacción. Esta identidad es la clave de idempotencia. **Disjunción ETH/ERC-20 (por qué `logIndex = 0` es un centinela seguro):** los espacios `(txHash, 0)` de ETH nativo y `(txHash, logIndex_real)` de ERC-20 son **disjuntos por construcción** —las direcciones de depósito son EOAs y un EOA no emite logs, así que una tx detectada como depósito de ETH nativo no puede a la vez emitir un `Transfer`—. Para que la clave sea inequívoca aun ante valores `logIndex = 0` coincidentes, **el registro de idempotencia incluye una columna de activo/tipo** (`asset ∈ {ETH, USDC}`): la clave efectiva es `(asset, txHash, logIndex)` o, equivalentemente, una restricción UNIQUE sobre `(txHash, logIndex)` por tabla/tipo de depósito.
2. **RN-2 (acreditación única, INV-5):** para toda identidad de depósito `d`, `veces_acreditado(d) ≤ 1`. La verificación "¿ya acreditado?" + "acreditar" debe ser **atómica** (no hay ventana de doble acreditación). **Mecanismo exigido (no es válido implementarlo solo en la capa de aplicación):** la atomicidad se garantiza mediante una operación de exclusión mutua en la **capa de persistencia**, por ejemplo (a) una restricción **UNIQUE** sobre `(asset, txHash, logIndex)` con un `INSERT ... ON CONFLICT DO NOTHING` (el INSERT falla/no inserta si la identidad ya existe, y se retorna el estado previo), o (b) el check+insert dentro de una **única transacción de base de datos serializable** (p. ej. `SELECT ... FOR UPDATE`). Un check-then-act sin serialización en código de aplicación es **incorrecto** (race condition ⇒ doble acreditación, viola INV-5).
3. **RN-3 (reproceso de un depósito ya acreditado):** reprocesar/reobservar una identidad ya acreditada NO vuelve a sumar al balance. Si la operación es una solicitud explícita de acreditación, se responde/registra `DEPOSIT_ALREADY_CREDITED` (HTTP 409) con `details = { txHash, logIndex }`; este resultado **no** altera balances y no es un fallo del sistema (es la respuesta idempotente esperada).
4. **RN-4 (concurrencia):** si dos procesos intentan acreditar la misma identidad simultáneamente, exactamente uno acredita y el otro obtiene el resultado idempotente (`DEPOSIT_ALREADY_CREDITED`); el balance se incrementa una sola vez (INV-5).
5. **RN-5 (reorg antes de confirmar):** si el bloque de inclusión de un depósito `PENDIENTE` (con `confirmaciones < 12`) queda huérfano por una reorg, el depósito pasa a **`DESCARTADO`** (`discardReason = REORG`) y **no** se acredita. Si la transacción no reaparece en la cadena canónica, el depósito no incrementa ningún balance a efectos contables; el registro persiste como `DESCARTADO` para trazabilidad (RN-12, INV-8).
6. **RN-6 (reorg con reinclusión):** si tras la reorg la transacción se reincluye en un bloque distinto `B'` con receipt `status = 1`, las confirmaciones se recomputan desde `B'` (`confirmaciones = max(0, bloque_cabeza − B')`). La identidad `(txHash, logIndex)` se mantiene; el depósito se acredita **una sola vez** cuando `B'` alcanza 12 confirmaciones (no se acredita dos veces por haber sido visto en `B` y en `B'`). El caso de reinclusión con `status = 0` se rige por RN-13.
7. **RN-7 (transacción revertida):** una identidad asociada a una transacción con receipt `status == 0` no es acreditable (coherente con HU-07-01 RN-6 y HU-07-02 RN-9). Si una observación previa la había marcado `PENDIENTE`, pasa a **`DESCARTADO`** (`discardReason = REVERTED`).
8. **RN-8 (persistencia de la idempotencia, INV-8):** el registro de identidades ya acreditadas es persistente: tras un reinicio, reprocesar bloques no reacredita depósitos ya acreditados.
9. **RN-9 (conservación, INV-1):** como la acreditación es única, la suma de depósitos acreditados coincide exactamente con el lado "depósitos confirmados" de INV-1; no hay sobreconteo por reprocesos ni reorgs.
10. **RN-10 (no des-acreditación tras 12 confirmaciones):** por el supuesto de la sección de alcance, un depósito ya acreditado (que pasó las 12 confirmaciones) no se revierte; la spec no define un flujo de "des-acreditar".
11. **RN-11 (detección de reorgs):** al avanzar la cabeza de la cadena al bloque `B_new`, el servicio verifica que `B_new.parentHash == hash(B_cabeza_anterior)`. Si **no** coincide, hay una reorg: el servicio retrocede bloque a bloque comparando `parentHash` hasta encontrar el **ancestro común**, y reevalúa todos los depósitos `PENDIENTE` cuyo `blockNumber` quedó fuera de la cadena canónica (RN-5/RN-13). Alternativamente, el servicio puede verificar periódicamente los hashes de los últimos `CONFIRMACIONES_REQUERIDAS` bloques almacenados vía `eth_getBlockByNumber(n, false)` y detectar discrepancias. Procesar solo bloques nuevos sin verificar `parentHash` es **incorrecto** (no detectaría reorgs y violaría RN-5).
12. **RN-12 (estado `DESCARTADO` y reactivación):** un depósito invalidado (por reorg sin reinclusión, RN-5; o por reversión, RN-7) pasa al estado terminal **`DESCARTADO`** y **no se elimina** físicamente del registro (trazabilidad de auditoría, INV-8); es visible en la consulta del usuario con su `discardReason ∈ {REORG, REVERTED}`. Si la **misma** identidad `(txHash, logIndex)` reaparece luego en la cadena canónica con `status = 1` (reinclusión, RN-6), el registro `DESCARTADO` se **reactiva** a `PENDIENTE` con el nuevo `blockNumber = B'`, recomputando confirmaciones desde `B'`. La reactivación no rompe la idempotencia: la acreditación sigue ocurriendo a lo sumo una vez para esa identidad (INV-5).
13. **RN-13 (reorg con reinclusión revertida):** si tras una reorg la transacción se reincluye en `B'` con receipt `status = 0` (revertida en la nueva inclusión), el depósito **se descarta** (`DESCARTADO`, `discardReason = REVERTED`) y **no** se acredita, con independencia de que en el bloque huérfano `B` previo tuviera `status = 1`. Es la combinación de RN-6 (reinclusión) y RN-7 (reversión).

## Criterios de aceptación (DoD)

### Escenario 1: reproceso de un depósito ya acreditado no duplica [AT-07-04-01]
- Dado un depósito con identidad `(txHash, logIndex)` ya `ACREDITADO`, con `disponible(acc-1, A) = "10000000"` tras la acreditación
- Cuando el servicio reprocesa el mismo `(txHash, logIndex)` (p. ej. al reindexar el bloque)
- Entonces NO se vuelve a sumar al balance: `disponible(acc-1, A)` sigue en `"10000000"`
- Y, si fue una solicitud explícita de acreditación, se responde `DEPOSIT_ALREADY_CREDITED` (HTTP 409) con `details = { txHash, logIndex }`

### Escenario 2 (concurrencia): doble acreditación simultánea [AT-07-04-02]
- Dado un depósito confirmado (`≥ 12`) aún no acreditado, identidad `(txHash, logIndex)`, monto `m`
- Y un **harness de concurrencia determinístico**: dos workers (goroutines/threads/procesos) que comparten el mismo store, lanzados con una barrera de sincronización (p. ej. `sync.WaitGroup`/latch) para que ambos invoquen la acreditación de la misma identidad lo más simultáneamente posible
- Cuando ambos intentan acreditarlo a la vez
- Entonces **exactamente uno** acredita (suma `m` una vez) y el otro obtiene `DEPOSIT_ALREADY_CREDITED`, por la exclusión mutua en persistencia exigida por RN-2 (UNIQUE / transacción serializable)
- Y el balance del usuario se incrementa exactamente en `m` (no `2m`) — INV-5
- Y repetir el harness `N` veces produce siempre el mismo resultado (determinismo)

### Escenario 3 (idempotencia ETH nativo con logIndex 0) [AT-07-04-03]
- Dado un depósito de ETH nativo con identidad `(txHash, 0)` ya acreditado
- Cuando se reprocesa la transacción (mismo `txHash`, `logIndex = 0`)
- Entonces no hay segunda acreditación; el balance permanece igual
- Y la identidad sigue siendo `(txHash, 0)` (RN-1)

### Escenario 4 (reorg antes de confirmar): bloque huérfano [AT-07-04-04]
- Dado un depósito `PENDIENTE` con `confirmaciones = 4`, incluido en el bloque `B`
- Cuando una reorg deja a `B` huérfano y la transacción NO reaparece en la cadena canónica
- Entonces el depósito se invalida/descarta y nunca se acredita (RN-5)
- Y ningún balance de usuario se modifica

### Escenario 5 (reorg con reinclusión): recuento de confirmaciones desde el nuevo bloque [AT-07-04-05]
- Dado un depósito `PENDIENTE` con `confirmaciones = 3`, incluido originalmente en `B`
- Cuando una reorg reincluye la misma transacción en el bloque `B'` (≠ `B`) con `status = 1`
- Entonces las confirmaciones se recomputan desde `B'` (`confirmaciones = max(0, cabeza − B')`)
- Y al alcanzar `B' + 12` el depósito se acredita **una sola vez** para la identidad `(txHash, logIndex)` (RN-6)
- Y si el depósito había sido marcado `DESCARTADO` por el bloque huérfano, la reinclusión lo **reactiva** a `PENDIENTE` con `blockNumber = B'` (RN-12)

### Escenario 6 (error/ignorar): transacción revertida no acreditable [AT-07-04-06]
- Dado una observación `PENDIENTE` asociada a una transacción que resulta con receipt `status = 0` (revertida)
- Cuando el servicio evalúa la identidad
- Entonces la observación se descarta y la identidad nunca se acredita (RN-7)
- Y un intento explícito de acreditarla no incrementa balances

### Escenario 7 (idempotencia persistente tras reinicio, INV-8) [AT-07-04-07]
- Dado un depósito ya `ACREDITADO` antes de un reinicio del sistema
- Cuando el sistema reinicia y reprocesa los bloques históricos
- Entonces el depósito NO se reacredita (el registro de identidades acreditadas es persistente)
- Y los balances reconstruidos desde el ledger coinciden con los previos al reinicio (INV-1, INV-8)

### Escenario 8 (conservación bajo N reprocesos) [AT-07-04-08]
- Dado un depósito de monto `m` con identidad `(txHash, logIndex)`
- Cuando se procesa la misma identidad `N` veces (N ≥ 1)
- Entonces el balance se incrementa exactamente en `m` (una sola vez) sin importar `N`
- Y la suma de depósitos acreditados es consistente con el lado "depósitos confirmados" de INV-1 (RN-9)

### Escenario 9 (reorg con reinclusión revertida): tx reaparece con `status = 0` [AT-07-04-09]
- Dado un depósito `PENDIENTE` con identidad `(txHash, logIndex)` que en el bloque (luego huérfano) `B` tenía `status = 1`
- Cuando una reorg reincluye la misma transacción en `B'` (≠ `B`) pero con receipt `status = 0` (revertida)
- Entonces el depósito pasa a `DESCARTADO` (`discardReason = REVERTED`) y **no** se acredita, pese a que en `B` tenía `status = 1` (RN-13)
- Y ningún balance de usuario se modifica

### Escenario 10 (detección de reorg por `parentHash`) [AT-07-04-10]
- Dado que el último bloque procesado almacenado es `B_prev` con su `hash` persistido
- Cuando la cabeza avanza a `B_new` y `B_new.parentHash ≠ hash(B_prev)`
- Entonces el servicio detecta la reorg, retrocede comparando `parentHash` hasta el ancestro común y reevalúa los depósitos `PENDIENTE` afectados (RN-11)
- Y un avance normal donde `B_new.parentHash == hash(B_prev)` no dispara ninguna reevaluación

### Escenario 11 (reanudación desde checkpoint sin reacreditar, INV-8) [AT-07-04-11]
- Dado un servicio con checkpoint persistido en el bloque `N` y un depósito ya `ACREDITADO` incluido en un bloque `≤ N`
- Cuando el servicio reinicia y reanuda el escaneo desde `max(BLOQUE_INICIO_CONFIGURADO, N + 1)`, procesando `N+1..N+k`
- Entonces los depósitos ya acreditados (en bloques `≤ N`) **no** se reacreditan, y el checkpoint avanza a `N+k`
- Y los nuevos depósitos en `N+1..N+k` se detectan normalmente (no se pierden bloques del downtime)

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-07-04-01..11) pasan
- [ ] Reglas de negocio RN-1..RN-13 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md (`DEPOSIT_ALREADY_CREDITED`, y `DEPOSIT_NOT_CONFIRMED` heredado de HU-07-03)
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md (montos en unidad mínima entera, sin floats)
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md): INV-5 (idempotencia), INV-1 (conservación), INV-8 (persistencia)
- [ ] Adherencia verificada al estándar on-chain citado (Sepolia chainId 11155111; umbral de 12 confirmaciones como defensa anti-reorg)
