# Arbitraje de la evaluación white-box — pre-piloto-b

Material para el **veredicto de registro**, que firma el tesista (ADR-004 §2.5,
ADR-007 §4). Este archivo no es el veredicto: es la evidencia de las dos pasadas
puesta lado a lado para las discrepancias.

- ATs del alcance evaluados con procedimiento completo: **22**
- Concordancia entre pasadas: **21/22** (95 %)
- Discrepancias a arbitrar: **1**

Los 34 ATs fuera del alcance se emitieron `NO_EVALUABLE / FUNCION_NO_LOCALIZABLE`
en las dos pasadas por instrucción del acotamiento, y no entran al arbitraje.

## AT-06-03-10

| | pasada 1 | pasada 2 |
|---|---|---|
| veredicto | **PASA** | **NO_EVALUABLE** |
| causa | — | OTRO |

**Pasada 1 — justificación:**

> El mecanismo existe por partida doble y con los campos exigidos: evento DepositAddressAssigned persistido en la misma transaccion que la asignacion, y consulta interna no publica del conjunto asignado. Al ser la asignacion eager (AT-06-03-09), toda direccion es conocible desde su asignacion y no hay ventana atada a la consulta del usuario; el consumidor de la epica 07 no existe en el alcance entregado y se deja constancia de ello.

**Pasada 1 — evidencia (6 entradas):**

- `[archivo]` `src/services/wallet-service.ts:71-85` — Tras persistir la fila de la asignacion y dentro de la MISMA transaccion, se inserta en domain_events un evento 'DepositAddressAssigned' cuyo payload es exactamente { accountId, addressIndex, address, chainId } con chainId = CHAIN_ID.
- `[archivo]` `src/crypto/wallet.ts:11 y src/database.ts:127-134` — CHAIN_ID = '11155111'; la tabla domain_events es durable y tiene CHECK (event_type = 'DepositAddressAssigned').
- `[archivo]` `src/services/wallet-service.ts:89-109 y src/database.ts:87-92` — Consulta interna del conjunto asignado: listAssigned() (todas las filas de deposit_addresses ordenadas por address_index) y listAssignedEvents() (todos los eventos DepositAddressAssigned con su payload). Ninguna de las dos esta expuesta en el mapa de rutas publico (src/app.ts:38-45), como pide RN-11
- `[comando]` `instancia descartable M: lectura de domain_events tras las dos altas, sin ninguna llamada a GET /deposit-address` — Dos filas DepositAddressAssigned con payload {'accountId':'b9449419-...','addressIndex':0,'address':'0xE5AEc64d...','chainId':'11155111'} y {'accountId':'03c82329-...','addressIndex':1,'address':'0x8D98fef9...','chainId':'11155111'}: el evento existe desde la asignacion, no desde la consulta del usu
- `[archivo]` `test/app.test.ts:86-93` — Test propio que assertea el payload del evento con los cuatro campos y chainId '11155111'.
- `[comando]` `grep -rniE 'monitor|indexer|indexador|watcher|getLogs|confirmations' sut/src --include='*.ts'` — 0 hallazgos: el monitor de depositos de la epica 07 no forma parte del alcance entregado en esta corrida, por lo que no existe un punto de consumo que inspeccionar; lo verificable del contrato (emision con los cuatro campos, consulta interna no publica y ausencia de ventana) esta presente.

**Pasada 2 — justificación:**

> El lado productor del contrato RN-11 está presente y verificado: el evento se emite con los cuatro campos dentro de la misma transacción que la asignación, y existe la consulta interna del conjunto asignado. El criterio cerrado exige además que el monitor de la épica 07 se alimente de él, y ese monitor no existe en la implementación, de modo que esa conjunción no es confirmable ni refutable (tampoco se observa la condición de FALLA: no hay descubrimiento con ventana). Se registra para arbitraje humano conforme a briefing §5.

**Pasada 2 — evidencia (5 entradas):**

- `[comando]` `grep -rni 'DepositAddressAssigned|deposit_address_assigned|internal/deposit' $COPIA_EVAL --exclude-dir=node_modules --exclude-dir=dist` — hallazgos sólo en src/services/wallet-service.ts (7,72-85,89-108), src/database.ts (127-134), README.md:190 y dos tests; NO existe ninguna ruta /internal/deposit-addresses ni consumidor fuera de los tests
- `[archivo]` `src/services/wallet-service.ts:71-85` — MECANISMO (a) PRESENTE: tras persistir la asignación y dentro de la MISMA transacción, INSERT INTO domain_events (event_type='DepositAddressAssigned') con payload {accountId, addressIndex, address, chainId} — los cuatro campos requeridos
- `[archivo]` `src/services/wallet-service.ts:89-108; src/database.ts:87-92` — MECANISMO (b) PRESENTE como consulta interna en proceso: listAssigned() → getAssignedAddresses() (conjunto completo de direcciones asignadas) y listAssignedEvents(); no se expone como endpoint HTTP
- `[comando]` `lectura sólo lectura de domain_events en la instancia descartable EAGER tras dos altas (sin consultar deposit-address)` — DepositAddressAssigned {"accountId":"7947ffeb…","addressIndex":0,"address":"0x615DB4B7692fdaB5f98d5319b9AB10067b733FE1","chainId":"11155111"} y el análogo para addressIndex 1 — emitidos en el alta, sin ventana respecto de la primera consulta del usuario
- `[comando]` `grep -rni 'eth_getLogs|indexador|confirmaciones|/deposits' $COPIA_EVAL/src ; grep -n '"/api/v1' src/app.ts ; README.md:16-19` — 0 hallazgos: el monitor de depósitos de la épica 07 no existe en la implementación, por lo que no hay punto de consumo que localizar ni ejercitar

**Veredicto arbitrado:** **PASA** (tesista, 2026-09-06)

**Fundamento:** todo lo verificable del contrato dentro del alcance reducido está presente y fue comprobado en ejecución por las dos pasadas (evento `DepositAddressAssigned` con los cuatro campos en la misma transacción; consulta interna no pública del conjunto asignado; sin ventana respecto de la consulta del usuario). La parte no confirmable —que el monitor de la épica 07 lo consuma— lo es por el alcance de la corrida (la épica 07 no se implementó), no por defecto de la implementación. En una corrida oficial el monitor existe y el criterio se aplica entero.

---
