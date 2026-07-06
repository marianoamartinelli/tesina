# HU-08-04 — Seguimiento de confirmaciones

- **Epica:** 08 — Retiros On-Chain
- **Actor / rol:** Sistema (servicio de seguimiento on-chain) y Trader (consulta de estado)
- **Prioridad:** Alta
- **Dependencias:** HU-08-03 (retiro en `BROADCAST` con `txHash`/`nonce`), HU-02-02 (liberación de fondos), HU-02-03 (asientos `WITHDRAWAL_SETTLE`/`WITHDRAWAL_RELEASE`); épica 07 (modelo de confirmaciones compartido)
- **Estandares de dominio aplicables:** Sepolia chainId 11155111, `CONFIRMACIONES_REQUERIDAS = 12`; invariantes INV-1/INV-3/INV-4/INV-8

## Historia
Como Sistema de seguimiento on-chain, quiero **seguir los estados de un retiro** (`PENDING/BROADCAST/CONFIRMED/FAILED`) en función de su inclusión y confirmaciones en Sepolia, y **reconciliar el balance interno** al finalizar (consumir el bloqueado al confirmar, o reacreditar lo no consumido al fallar), para que el balance del usuario refleje fielmente lo que ocurrió on-chain, sin crear ni destruir valor.

## Contexto y alcance
Esta HU cubre la **máquina de estados** del retiro a partir de `BROADCAST`, el **conteo de confirmaciones** (igual que depósitos: `confirmaciones = max(0, bloque_cabeza − bloque_de_inclusión)`, finaliza con `≥ 12`), la **transición a `CONFIRMED`** (receipt `status = 1`) o a `FAILED` (tx no minada/descartada, broadcast permanentemente fallido, o tx minada pero **revertida** con `status = 0`), y la **reconciliación contable** del balance bloqueado en cada caso. Genera los asientos `WITHDRAWAL_SETTLE` (consumo definitivo) y `WITHDRAWAL_RELEASE` (liberación de lo no consumido) de la épica 02.

NO cubre la solicitud (HU-08-01), el bloqueo inicial (HU-08-02), ni la construcción/firma/broadcast (HU-08-03). Comparte con la épica 07 el modelo de confirmaciones y la sensibilidad a reorgs.

Es aquí donde se materializa el efecto de INV-1 para retiros: al `CONFIRMED`, la suma total por activo **disminuye** exactamente en lo que salió del sistema (principal + gas consumido).

## Reglas de negocio e invariantes
1. **RN-1 (máquina de estados con disparadores explícitos):** estados válidos y transiciones:
   - `PENDING → BROADCAST` (HU-08-03: firma + broadcast aceptado por el nodo).
   - `BROADCAST → CONFIRMED` (`confirmaciones ≥ 12`, receipt `status = 1`; y para **USDC**, además evento `Transfer` esperado emitido, RN-2).
   - `BROADCAST → FAILED`, disparado por cualquiera de: (a) tx minada pero **revertida** (`status = 0`); (b) **USDC** con `status = 1` pero **sin** el evento `Transfer` esperado (RN-2/RN-5, HU-08-05 RN-5); (c) tx **descartada** del mempool (dropped: tras reorg, o porque otra tx ocupó el nonce en la cadena canónica) y sin reaparecer; (d) **timeout de inclusión**: `bloque_cabeza − bloque_de_broadcast > MAX_BLOCKS_PENDING (= 50)` sin haberse minado.
   - `PENDING → FAILED`, disparado por: (e) **cancelación del usuario** antes del broadcast (retiro sin `txHash`, ver RN-13); (f) broadcast **definitivamente imposible** (se agotaron `MAX_BROADCAST_RETRIES = 5` reintentos, HU-08-03 RN-8).
   `CONFIRMED` y `FAILED` son **terminales**: no admiten transiciones salientes. Cualquier transición fuera de este grafo → `CONFLICT` (409).
2. **RN-2 (conteo de confirmaciones y criterio de finalización):** la fórmula es **total**:
   - Mientras la transacción **no** está incluida en ningún bloque canónico (`bloque_de_inclusión = null`, p. ej. en mempool), `confirmaciones = 0` y el estado es `BROADCAST`. `bloque_de_inclusión` se determina cuando el nodo reporta un **receipt** con `blockNumber` para el `txHash`.
   - Con receipt: `confirmaciones = max(0, bloque_cabeza − bloque_de_inclusión)`.

   El retiro es **finalizable** (`CONFIRMED`) sii `confirmaciones ≥ CONFIRMACIONES_REQUERIDAS = 12` (equivalente: `bloque_cabeza ≥ bloque_de_inclusión + 12`) **y** el receipt tiene `status = 1`. **Adicionalmente, para retiros USDC**, la finalización a `CONFIRMED` requiere que el log del receipt contenga el evento `Transfer(from = emisora, to = destino_usuario, value = amount_usdc)` emitido por el contrato **USDC-mock configurado** con el monto correcto; un `status = 1` que **no** emita ese `Transfer` esperado (o lo emita con `value`/`from`/contrato incorrectos) **no** se confirma y se trata como `FAILED` (revertida): ver HU-08-05 RN-5 y AT-08-04-11.
3. **RN-3 (reconciliación al `CONFIRMED` — consumir y liberar gas sobrante):** al confirmar, sea `gas_usado_wei = gas_usado × precio_efectivo_wei` (≤ `fee_red_wei`). **`precio_efectivo_wei`** es el campo `effectiveGasPrice` del transaction receipt; para las transacciones **legacy (Type-0)** de esta épica, `precio_efectivo_wei = gas_price_wei` (el `gas_price` fijado en la tx = el snapshot de HU-08-02, ver README §Previsión de fee). `gas_usado` es el `gasUsed` del receipt (`≤ gas_limit`). Entonces:
   - **Retiro de ETH:** se **consume** del bloqueado `amount_wei + gas_usado_wei` (sale del sistema: principal al destinatario, gas al validador) y se **libera** a disponible la diferencia de gas no usada `fee_red_wei − gas_usado_wei`. Asientos: `WITHDRAWAL_SETTLE` por `amount_wei + gas_usado_wei` y, si la diferencia > 0, `WITHDRAWAL_RELEASE` por `fee_red_wei − gas_usado_wei`.
   - **Retiro de USDC:** se **consume** del bloqueado `amount_usdc` en USDC (sale al destinatario) y `gas_usado_wei` en ETH (sale al validador); se **libera** a disponible `fee_red_wei − gas_usado_wei` en ETH. (Detalle en HU-08-05.)
4. **RN-4 (efecto en la suma total — INV-1):** tras `CONFIRMED`, `Σ_acc total(acc, A) + total(EX, A)` **disminuye** exactamente en lo que salió del sistema: ETH ⇒ `amount_wei + gas_usado_wei` (retiro ETH) o `gas_usado_wei` (retiro USDC); USDC ⇒ `amount_usdc` (retiro USDC). Estos son los `retiros_confirmados(A)` (incluida la fee on-chain de gas) de INV-1.
5. **RN-5 (reconciliación al `FAILED` — reacreditar lo no consumido):** al fallar se **libera/reacredita** todo lo que **no** salió del sistema (asiento `WITHDRAWAL_RELEASE`):
   - Si la tx **no llegó a minarse** (descartada, broadcast permanentemente fallido): `gas_usado_wei = 0`. Se libera **toda** la reserva a disponible: ETH ⇒ `reserva_eth` completa (retiro ETH) o `fee_red_wei` en ETH + `amount_usdc` en USDC (retiro USDC). La suma total por activo **no cambia** (nada salió).
   - Si la tx **se minó pero revirtió** (`status = 0`): el **principal no se transfirió** (se reacredita), pero el **gas igualmente se consumió** on-chain. Se reacredita el principal y se libera `fee_red_wei − gas_usado_wei`; se **consume** `gas_usado_wei` en ETH (sale al validador). La suma total de ETH disminuye solo en `gas_usado_wei`; la de USDC no cambia.
6. **RN-6 (atomicidad de la reconciliación):** la reconciliación (consumir/liberar) es **atómica** (INV-4): se aplica completa o nada. No hay estado observable con el principal consumido pero el gas sin reconciliar, ni con liberación parcial.
7. **RN-7 (idempotencia de la finalización):** un retiro se **reconcilia a lo sumo una vez**. Observar el mismo evento de confirmación/falla múltiples veces (o reprocesar tras reinicio, INV-8) **no** consume ni libera dos veces. Una vez en estado terminal (`CONFIRMED`/`FAILED`), reprocesar es un no-op contable.
8. **RN-8 (no finalizar antes de 12 confirmaciones):** con `0 ≤ confirmaciones < 12` el retiro permanece en `BROADCAST` y **no** se consume el bloqueo. Intentar finalizar/consultar como confirmado un retiro con `confirmaciones < 12` no lo finaliza (estado sigue `BROADCAST`).
9. **RN-9 (reorg antes de confirmar; tx descartada):** si el bloque de inclusión queda **huérfano** por una reorg antes de alcanzar 12 confirmaciones, el `confirmaciones` se recalcula contra la nueva cadena canónica (puede volver a `0` o quedar el retiro nuevamente sin inclusión → `bloque_de_inclusión = null`, vuelve a `BROADCAST`/pendiente de re-inclusión). Nunca se finaliza un retiro cuyo bloque de inclusión no es canónico. (Reorgs de profundidad > 12 se asumen fuera de alcance, igual que en la épica 07.) **Tx descartada (dropped):** si tras la reorg la transacción **no** está en la cadena canónica **ni** en el mempool (p. ej. el nonce fue ocupado por otra tx en la cadena canónica, o fue expulsada del mempool), o si transcurre el **timeout** `bloque_cabeza − bloque_de_broadcast > MAX_BLOCKS_PENDING (= 50)` sin reinclusión, la tx se trata como **descartada**: se aplica la reconciliación de `FAILED` **no minada** (`gas_usado_wei = 0`, `WITHDRAWAL_RELEASE` completo, RN-5) y el retiro transiciona `BROADCAST → FAILED`. La suma total por activo no cambia (nada salió).
10. **RN-10 (consulta de estado y serialización):** el trader autenticado puede consultar el estado de **sus** retiros (`status`, `txHash`, `confirmaciones`, montos como string). Los **montos** se serializan como **string** de entero (`^(0|[1-9][0-9]*)$`); el campo **`confirmaciones` se serializa como entero JSON** (número, no string), ya que es un conteo de bloques (acotado, pequeño) y **no** un monto monetario sujeto a la convención de string de `convenciones-monetarias.md`. Consultar un retiro inexistente → `NOT_FOUND` (404), `details = { resource: "withdrawal", id }`; consultar el de **otra cuenta** → **también `NOT_FOUND` (404)**, `details = { resource: "withdrawal", id }` (respuesta indistinguible de la de un retiro inexistente: no se revela la existencia de recursos ajenos; nunca `UNAUTHORIZED`; HU-08-01 RN-1).
11. **RN-11 (no-negatividad y partición):** en toda transición, `disponible ≥ 0` y `bloqueado ≥ 0` (INV-2) y `total = disponible + bloqueado` (INV-3). El consumo nunca deja un bloqueado negativo.
12. **RN-12 (sin floats; precisión; respaldo no negativo):** `amount`, `fee_red_wei`, `gas_usado_wei`, `fee_red_wei − gas_usado_wei` se manejan como **enteros de unidad mínima**; `gas_usado_wei = gas_usado × precio_efectivo_wei` es un **producto entero**; las restas son **exactas**. Serialización string `^(0|[1-9][0-9]*)$`. Prohibido floats. **Invariante derivada (respaldo del gas):** por ser transacciones legacy (Type-0) con `gas_price = gas_price_wei_snapshot` (HU-08-03 RN-5) y `gas_usado ≤ gas_limit`, se cumple siempre `gas_usado_wei = gas_usado × gas_price_wei ≤ gas_limit × gas_price_wei = fee_red_wei`; por lo tanto `fee_red_wei − gas_usado_wei ≥ 0` y la liberación del sobrante de gas nunca es negativa.
13. **RN-13 (cancelación de un retiro `PENDING`):** el **titular** de la cuenta puede cancelar un retiro propio **solo** mientras esté en `PENDING` y **sin** `txHash` (no broadcasteado). La superficie REST de esta operación es **`POST /api/v1/withdrawals/{withdrawalId}/cancel`**, fijada por la épica 09 (HU-09-01 RN-21: éxito 200 con el objeto retiro en `status = "FAILED"` y `failureReason = "USER_CANCELLED"`). La cancelación transiciona `PENDING → FAILED` con `gas_usado_wei = 0` y `WITHDRAWAL_RELEASE` de **toda** la reserva (la suma total por activo no cambia). Cancelar un retiro en `BROADCAST`/`CONFIRMED`/`FAILED` → `CONFLICT` (409) (no es cancelable). Cancelar un retiro de otra cuenta → `NOT_FOUND` (404), `details = { resource: "withdrawal", id }` (no se revela la existencia del recurso ajeno; nunca `UNAUTHORIZED`). La cancelación reusa la reconciliación de `FAILED` no minada (RN-5) y es idempotente respecto del estado terminal (RN-7).

## Criterios de aceptación (DoD)

### Escenario 1: retiro de ETH confirmado con gas sobrante liberado (feliz) [AT-08-04-01]
- Dado un retiro de ETH en `BROADCAST`: `amount_wei = "1000000000000000000"` (1 ETH), `reserva_eth = "1000420000000000000"`, `fee_red_wei = "420000000000000"`, y al confirmar `gas_usado_wei = "420000000000000"` (gas usado = previsión exacta)
- Cuando alcanza `confirmaciones = 12` con receipt `status = 1`
- Entonces pasa a `CONFIRMED`; se consume del bloqueado `amount_wei + gas_usado_wei = "1000420000000000000"` (`WITHDRAWAL_SETTLE`); como `fee_red_wei − gas_usado_wei = "0"`, no hay liberación de sobrante (RN-3)
- Y la suma total de ETH disminuye en `"1000420000000000000"` (RN-4, INV-1)

### Escenario 2 (borde): gas usado menor que la previsión, se libera la diferencia (pata ERC-20) [AT-08-04-02]
- Dado un retiro de **USDC (ERC-20)** en `BROADCAST` con `amount_usdc = "25000000"` (25 USDC), `gas_price_wei_snapshot = "5000000000"` (5 gwei), `gas_limit = GAS_LIMIT_ERC20 = 100000`, `fee_red_wei = "500000000000000"` (= `100000 × 5000000000`); y al confirmar el receipt reporta `gasUsed = 60000` y `effectiveGasPrice = "5000000000"`, por lo que `precio_efectivo_wei = "5000000000"` (= snapshot, Type-0) y `gas_usado_wei = 60000 × 5000000000 = "300000000000000"` (gas real < previsión: una llamada ERC-20 consume gas variable `≤ gas_limit`; a diferencia de una transferencia de ETH nativo, que consume exactamente `21000 = GAS_LIMIT_ETH` y no genera sobrante)
- Cuando alcanza 12 confirmaciones con `status = 1` y el evento `Transfer` esperado (RN-2)
- Entonces se consume del bloqueado `amount_usdc = "25000000"` en USDC y `gas_usado_wei = "300000000000000"` en ETH (`WITHDRAWAL_SETTLE`) y se **libera** a disponible `fee_red_wei − gas_usado_wei = "200000000000000"` en ETH (`WITHDRAWAL_RELEASE`) (RN-3)
- Y la suma total de USDC disminuye en `"25000000"` y la de ETH **solo** en `"300000000000000"` (lo realmente salido, RN-4)
- Y `total(ETH)` de la cuenta = lo que ya tenía − `"300000000000000"`, con el sobrante de gas `"200000000000000"` devuelto a disponible

### Escenario 3 (borde): aún no alcanza 12 confirmaciones [AT-08-04-03]
- Dado un retiro `BROADCAST` con `confirmaciones = 11` y `status = 1`
- Cuando el servicio evalúa su finalización
- Entonces el retiro **permanece** en `BROADCAST` y no se consume el bloqueo (RN-8)
- Y al llegar a `confirmaciones = 12` recién entonces pasa a `CONFIRMED`

### Escenario 4 (FAILED por broadcast definitivamente imposible) [AT-08-04-04]
- Dado un retiro de ETH `PENDING` con `reserva_eth = "1000420000000000000"` bloqueada, cuyo broadcast falló `MAX_BROADCAST_RETRIES = 5` veces consecutivas con `BROADCAST_FAILED` (broadcast definitivamente imposible, HU-08-03 RN-8) y nunca se minó
- Cuando, agotados los reintentos, el sistema transiciona el retiro `PENDING → FAILED` (RN-1 disparador (f))
- Entonces `gas_usado_wei = 0`; se **libera toda** la reserva a disponible: `disponible(ETH) += "1000420000000000000"`, `bloqueado(ETH) −= "1000420000000000000"` (`WITHDRAWAL_RELEASE`) (RN-5)
- Y la suma total de ETH **no cambia** (nada salió del sistema; INV-1)

### Escenario 5 (FAILED revertida): tx minada con status = 0 [AT-08-04-05]
- Dado un retiro de ETH `BROADCAST` con `amount_wei = "1000000000000000000"`, `fee_red_wei = "420000000000000"`, cuya transacción se mina pero **revierte** (`status = 0`), consumiendo `gas_usado_wei = "210000000000000"`
- Cuando se reconcilia como `FAILED`
- Entonces se **reacredita** el principal `"1000000000000000000"` y se libera `fee_red_wei − gas_usado_wei = "210000000000000"`; se **consume** `gas_usado_wei = "210000000000000"` en ETH (gas pagado al validador) (RN-5)
- Y la suma total de ETH disminuye **solo** en `"210000000000000"` (el gas), no en el principal (RN-5)

### Escenario 6 (atomicidad observable como invariante black-box) [AT-08-04-06]
- Dado cualquier retiro que se reconcilia (consumo + liberación de sobrante, o liberación total)
- Cuando se consulta su estado y balances vía API en cualquier momento (antes, durante o después de la reconciliación)
- Entonces **nunca** es observable un estado **parcial**: para un retiro `CONFIRMED`, `disponible + bloqueado` del activo refleja exactamente el consumo (principal + `gas_usado_wei`) y la liberación del sobrante; para un retiro `FAILED`, la reserva fue liberada **completa**; no existe un estado observable con el principal consumido pero el gas sin reconciliar, ni con liberación a medias (RN-6, INV-4)
- Y en todo snapshot se cumplen INV-1, INV-2 e INV-3
- Nota: la prueba de **fault injection** a mitad de la reconciliación (forzar excepción entre `WITHDRAWAL_SETTLE` y `WITHDRAWAL_RELEASE`) es una prueba de **integración interna** dependiente de implementación, fuera del alcance de los AT de evaluación black-box; el criterio evaluable es la **ausencia de estado parcial observable** descrita arriba

### Escenario 7 (idempotencia): observar la confirmación varias veces [AT-08-04-07]
- Dado un retiro ya `CONFIRMED` y reconciliado
- Cuando el servicio observa nuevamente el mismo evento de confirmación (o reprocesa tras reinicio, INV-8)
- Entonces NO se consume ni libera de nuevo: la finalización es **idempotente** (RN-7); los balances no cambian respecto de la primera reconciliación

### Escenario 8 (reorg antes de confirmar) [AT-08-04-08]
- Dado un retiro `BROADCAST` con `confirmaciones = 5`, cuyo bloque de inclusión queda **huérfano** por una reorg
- Cuando se recalcula contra la nueva cadena canónica
- Entonces `confirmaciones` se recalcula (puede volver a `0` o quedar sin inclusión, `bloque_de_inclusión = null`) y el retiro **no** se finaliza hasta re-incluirse y alcanzar 12 confirmaciones (RN-9)
- Y el bloqueo de balance permanece intacto mientras tanto

### Escenario 8b (reorg con tx descartada → FAILED) [AT-08-04-08b]
- Dado un retiro de ETH `BROADCAST` con `reserva_eth = "1000420000000000000"` cuyo bloque de inclusión queda huérfano por una reorg y, tras ella, la transacción **no** reaparece en la cadena canónica **ni** en el mempool (dropped: el nonce fue ocupado por otra tx), o se supera el timeout `bloque_cabeza − bloque_de_broadcast > MAX_BLOCKS_PENDING = 50`
- Cuando el sistema detecta la tx descartada
- Entonces transiciona `BROADCAST → FAILED` y aplica la reconciliación de no minada: `gas_usado_wei = 0`, se libera **toda** la reserva (`WITHDRAWAL_RELEASE`) (RN-9/RN-5)
- Y la suma total de ETH **no cambia** (nada salió; INV-1)

### Escenario 9 (consulta): el trader consulta el estado de su retiro [AT-08-04-09]
- Dado un retiro de `acc-1` en `BROADCAST` con receipt ya presente y `confirmaciones = 4`
- Cuando `acc-1` (autenticado) consulta su retiro
- Entonces obtiene `status = BROADCAST`, `txHash`, `confirmaciones = 4` (entero JSON, **sin** comillas) y los montos como string (RN-10)
- Y si otro usuario `acc-2` consulta ese retiro → `NOT_FOUND` (404), `details = { resource: "withdrawal", id }` (misma respuesta que para un retiro inexistente: no se revela la existencia del recurso ajeno); y consultar un `withdrawalId` inexistente → `NOT_FOUND` (404), `details = { resource: "withdrawal", id }`

### Escenario 9b (consulta en mempool, aún sin receipt): confirmaciones = 0 [AT-08-04-09b]
- Dado un retiro de `acc-1` en `BROADCAST` cuya transacción está en el **mempool** y aún **no** tiene receipt (`bloque_de_inclusión = null`)
- Cuando `acc-1` consulta su retiro
- Entonces obtiene `status = BROADCAST` y `confirmaciones = 0` (entero JSON), conforme a la fórmula total de RN-2 (sin receipt ⇒ `confirmaciones = 0`)

### Escenario 10 (error): transición de estado inválida [AT-08-04-10]
- Dado un retiro ya `CONFIRMED` (terminal)
- Cuando se intenta forzar una transición a `FAILED` (o re-`BROADCAST`)
- Entonces se rechaza con `CONFLICT` (409) (RN-1) y el estado no cambia

### Escenario 11 (USDC con status = 1 pero sin el evento Transfer esperado → FAILED) [AT-08-04-11]
- Dado un retiro de **USDC** `BROADCAST` con `amount_usdc = "25000000"`, `fee_red_wei = "500000000000000"`, cuya transacción se mina con receipt `status = 1` y alcanza 12 confirmaciones, pero el contrato USDC-mock **no** emite el evento `Transfer(from = emisora, to = destino, value = 25000000)` esperado (p. ej. bug del mock o llamada a función equivocada), `gas_usado_wei = "300000000000000"`
- Cuando se evalúa la confirmación
- Entonces el retiro **NO** pasa a `CONFIRMED` (RN-2): se trata como `FAILED` (revertida), análogo a `status = 0` (RN-5, HU-08-05 RN-5): se **reacredita** `"25000000"` USDC, se **consume** `gas_usado_wei = "300000000000000"` en ETH (el gas sí se pagó) y se libera `fee_red_wei − gas_usado_wei = "200000000000000"` en ETH
- Y la suma total de USDC **no cambia**; la de ETH disminuye en `"300000000000000"` (RN-4/RN-5, INV-1)

### Escenario 12 (cancelación de un retiro PENDING por el usuario) [AT-08-04-12]
- Dado un retiro de ETH de `acc-1` en `PENDING` **sin** `txHash` (aún no broadcasteado), con `reserva_eth = "1000420000000000000"` bloqueada
- Cuando `acc-1` solicita **cancelarlo** (RN-13)
- Entonces transiciona `PENDING → FAILED` con `gas_usado_wei = 0` y se libera **toda** la reserva (`WITHDRAWAL_RELEASE`): `disponible(ETH) += "1000420000000000000"`, `bloqueado(ETH) −= "1000420000000000000"`
- Y la suma total de ETH **no cambia** (INV-1)
- Y cancelar un retiro ya en `BROADCAST`/`CONFIRMED`/`FAILED` → `CONFLICT` (409); cancelar el de otra cuenta → `NOT_FOUND` (404), `details = { resource: "withdrawal", id }` (RN-13)

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-08-04-01..-08, -08b, -09, -09b, -10, -11, -12) pasan
- [ ] Reglas de negocio RN-1..RN-13 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md (`CONFLICT`, `NOT_FOUND` con `{resource,id}`; retiros ajenos referenciados por id ⇒ `NOT_FOUND`, nunca `UNAUTHORIZED`)
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md (gas usado = producto entero; restas exactas; montos como string; sin floats)
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md): INV-1 (la suma total baja exactamente en lo salido al `CONFIRMED`; no cambia si nada salió), INV-2/INV-3 (no-negatividad y partición en cada transición), INV-4 (atomicidad de la reconciliación), INV-8 (persistencia y reconciliación idempotente tras reinicio)
- [ ] Adherencia verificada al estándar on-chain citado: confirmaciones = 12; Sepolia chainId 11155111; receipt `status` (1 = éxito, 0 = revertida); `effectiveGasPrice`/`gasUsed` del receipt (`precio_efectivo_wei = gas_price_wei` para Type-0); para USDC, evento `Transfer` esperado como condición de `CONFIRMED`
