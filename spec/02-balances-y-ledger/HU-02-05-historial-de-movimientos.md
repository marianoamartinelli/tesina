# HU-02-05 — Historial de movimientos

- **Epica:** 02 — Balances y Ledger
- **Actor / rol:** Trader autenticado (cuenta propia)
- **Prioridad:** Media
- **Dependencias:** HU-02-03 (asientos del ledger que se proyectan); HU-02-01 (modelo de balances); HU-01 (autenticación/autorización). Paginación/contrato de API: épica 09. Fundaciones 00.
- **Estandares de dominio aplicables:** N/A on-chain (lectura interna). Convenciones monetarias (montos como string entero). Para movimientos de origen on-chain (`DEPOSIT`/`WITHDRAWAL_SETTLE`) la referencia incluye datos on-chain (`txHash`, `logIndex`) según épicas 07/08.

## Historia
Como trader autenticado, quiero consultar el historial de movimientos de mi balance,
filtrable por activo, tipo y período, para auditar de dónde vienen mis fondos y entender
cada cambio en mi disponible y bloqueado.

## Contexto y alcance
Esta HU expone una **proyección de solo lectura** del ledger (HU-02-03) restringida a los
movimientos que afectan a la cuenta autenticada. Cada ítem del historial corresponde a un
asiento que tiene al menos un posting sobre las cuentas del usuario, mostrando **solo** sus
postings (no los de la contraparte ni los de `EX`/`EXTERNAL`). Soporta filtros por activo,
tipo y rango de fechas, ordenamiento por timestamp descendente por defecto, y paginación.
No permite crear ni modificar movimientos (es lectura); las mutaciones se especifican en
HU-02-02/03. El contrato exacto de paginación lo fija la épica 09; aquí se fija el
**contenido**, los **filtros** y el **orden**.

## Reglas de negocio e invariantes
1. **RN-1 (autenticación/autorización):** requiere credencial válida (`UNAUTHENTICATED` si
   falta o es inválida). El historial devuelto es **solo** el de la cuenta autenticada;
   intentar consultar el de otra cuenta ⇒ `UNAUTHORIZED` (403). Nunca se exponen postings de
   la contraparte ni de cuentas internas (`EX`, `EXTERNAL`).
2. **RN-2 (contenido del ítem):** cada ítem incluye al menos: `entryId` (serializado como
   string; orden total global, ver HU-02-03 RN-2), `type` (del enum de HU-02-03),
   `timestamp` (ISO-8601 UTC con milisegundos), `reference` (origen:
   `orderId` / `withdrawalId` / `tradeId` / `{txHash, logIndex}` /
   `{reversedEntryId}` para `REVERSAL`) y los **postings propios**
   del usuario `{ asset, bucket, direction, amount, kind }` con `amount` como string entero
   positivo `^[1-9][0-9]*$`.
3. **RN-3 (filtro por activo):** filtro opcional `asset ∈ {ETH, USDC}`. Si se indica, solo
   se devuelven ítems con al menos un posting propio en ese activo. Valor fuera de
   `{ETH, USDC}` ⇒ `VALIDATION_ERROR`.
4. **RN-4 (filtro por tipo):** filtro opcional `type` (uno o varios del enum de HU-02-03
   RN-2, incluido `REVERSAL`). Para **varios** tipos, la convención es **parámetros
   repetidos** en el query string
   (`?type=DEPOSIT&type=ORDER_LOCK`); se combinan con **OR** entre sí (un ítem se incluye si
   su `type` coincide con **alguno** de los solicitados) y con **AND** respecto de los demás
   filtros (RN-8). Cualquier valor fuera del enum ⇒ `VALIDATION_ERROR`. (El nombre/forma
   final del parámetro lo fija la épica 09; la convención de unidad y semántica es esta.)
5. **RN-5 (filtro por período):** filtros opcionales `from` y `to` (fechas/instantes
   ISO-8601, UTC). Semántica inclusiva en `from` y exclusiva en `to` (`from ≤ timestamp <
   to`). Si `from > to` ⇒ `VALIDATION_ERROR`. Si `from == to`, el intervalo es **vacío**
   (ningún `timestamp` satisface `from ≤ t < from`) y la consulta retorna **lista vacía**
   con código de éxito (no es un error; aplica RN-9). Formato de fecha inválido ⇒
   `VALIDATION_ERROR`.
6. **RN-6 (orden determinista):** por defecto, orden **descendente** por `timestamp` y, ante
   empate, por `entryId` descendente (orden total reproducible). El orden no depende de la
   paginación.
7. **RN-7 (paginación estable):** la consulta es paginable. El `limit` es un **entero en el
   rango `[1, 100]`**, con **default `20`**; un `limit` inválido (no entero, `≤ 0`, o `> 100`)
   ⇒ `VALIDATION_ERROR`. La paginación es **estable**: dado un ledger sin cambios, recorrer
   todas las páginas devuelve cada ítem exactamente una vez, sin duplicados ni omisiones.
   - **Mecanismo (normativo):** dado que el ledger es **append-only** y se recorre en orden
     descendente, para garantizar estabilidad en un ledger **activo** la paginación **DEBE**
     implementarse mediante **cursor anclado al `entryId`** (no por offset numérico, que es
     inestable: una nueva entrada al frente desplaza todos los ítems y provoca repeticiones u
     omisiones). Un cursor `after=<entryId>` devuelve los asientos con `entryId` estrictamente
     **menor** (en orden descendente), sin verse afectado por nuevas entradas. La épica 09
     implementa este cursor.
   - **Consistencia ante escrituras concurrentes:** una sesión de paginación **no** garantiza
     visibilidad de asientos escritos **después** de la primera página; los asientos nuevos
     (más recientes, con `entryId` mayor) no aparecen en páginas ya recorridas porque el
     cursor avanza hacia `entryId` menores. El conjunto recorrido es así **completo y sin
     duplicados** respecto del corte fijado por el cursor inicial.
8. **RN-8 (combinación de filtros):** los filtros se combinan con **AND** (activo y tipo y
   período). Sin filtros, se devuelven todos los movimientos propios (paginados).
9. **RN-9 (resultado vacío no es error):** una consulta válida sin coincidencias devuelve
   una lista **vacía** (no un error 404).
10. **RN-10 (solo lectura / consistencia):** la consulta no muta estado. Los montos
    coinciden con los postings persistidos (HU-02-03) y son consistentes con la
    reconstrucción de balances de HU-02-01 (INV-8). Prohibido floats; montos siempre string
    entero de unidad mínima.

## Criterios de aceptacion (DoD)

### Escenario 1: Historial completo sin filtros [AT-02-05-01]
- Dado un trader autenticado con exactamente estos cuatro movimientos propios aplicados en orden:
  1. `DEPOSIT` `3000000000` USDC el `2026-06-01T10:00:00.000Z` (`reference = { txHash: "0xa1", logIndex: 0 }`)
  2. `ORDER_LOCK` `2000000000` USDC el `2026-06-02T11:00:00.000Z` (`reference = { orderId: "ord-1" }`)
  3. `TRADE_FILL` el `2026-06-03T12:00:00.000Z` (`reference = { tradeId: "T-1" }`), con sus postings propios
  4. `ORDER_RELEASE` `10000000` USDC el `2026-06-04T13:00:00.000Z` (`reference = { orderId: "ord-1" }`)
- Cuando consulta su historial sin filtros
- Entonces recibe exactamente **4** ítems, cada uno con `entryId`, `type`, `timestamp` ISO-8601, `reference` y sus postings propios con `amount` como string `^[1-9][0-9]*$`
- Y vienen ordenados por `timestamp` descendente (y `entryId` desc ante empate): `ORDER_RELEASE`, `TRADE_FILL`, `ORDER_LOCK`, `DEPOSIT`

### Escenario 2: Filtro por activo [AT-02-05-02]
- Dado un trader con movimientos en `ETH` y en `USDC`
- Cuando consulta con `asset = USDC`
- Entonces solo recibe ítems que tienen al menos un posting propio en `USDC`
- Y ningún ítem cuyos postings propios sean exclusivamente en `ETH`

### Escenario 3: Filtro por tipo [AT-02-05-03]
- Dado un trader con asientos de varios tipos
- Cuando consulta con `type = DEPOSIT`
- Entonces solo recibe ítems con `type = DEPOSIT`
- Y cada uno trae su `reference` `{ txHash, logIndex }`

### Escenario 4: Filtro por período (inclusivo/exclusivo) [AT-02-05-04]
- Dado movimientos en `2026-06-01T00:00:00.000Z`, `2026-06-15T12:00:00.000Z` y `2026-06-30T00:00:00.000Z`
- Cuando consulta con `from = 2026-06-01T00:00:00.000Z` y `to = 2026-06-30T00:00:00.000Z`
- Entonces recibe los movimientos del 1 y del 15 (`from ≤ timestamp < to`)
- Y **no** recibe el del 30 (límite superior exclusivo)

### Escenario 5: Combinación de filtros (AND) [AT-02-05-05]
- Dado un trader con exactamente estos movimientos: `DEPOSIT` `1000000000` USDC el `2026-06-01T10:00:00.000Z`; `TRADE_FILL` (afecta USDC y ETH) el `2026-06-05T15:00:00.000Z`; `TRADE_FILL` (solo postings propios en ETH) el `2026-06-10T09:00:00.000Z`
- Cuando consulta con `asset = USDC`, `type = TRADE_FILL`, `from = 2026-06-01T00:00:00.000Z` y `to = 2026-06-07T00:00:00.000Z`
- Entonces recibe **exactamente 1** ítem: el `TRADE_FILL` del `2026-06-05` (cumple las tres condiciones simultáneamente, AND)
- Y **no** recibe el `DEPOSIT` (no es `TRADE_FILL`) ni el `TRADE_FILL` del `2026-06-10` (fuera del período y sin posting propio en USDC)

### Escenario 6 (borde): Paginación estable [AT-02-05-06]
- Dado un trader con 25 movimientos y un `limit = 10`
- Cuando recorre las páginas sucesivas (sin cambios en el ledger entre páginas)
- Entonces obtiene 10 + 10 + 5 ítems, sin duplicados ni omisiones
- Y el orden global (timestamp desc, entryId desc) se mantiene a través de las páginas

### Escenario 7 (borde): Resultado vacío [AT-02-05-07]
- Dado un trader sin movimientos del tipo solicitado
- Cuando consulta con `type = WITHDRAWAL_SETTLE` y no existe ninguno
- Entonces recibe una lista **vacía** y un código de éxito (no `NOT_FOUND`)

### Escenario 8 (error): Filtro de activo inválido [AT-02-05-08]
- Dado un trader autenticado
- Cuando consulta con `asset = BTC` (fuera de `{ETH, USDC}`)
- Entonces se rechaza con `code = VALIDATION_ERROR` (HTTP 422) y `details.issues` describe el campo inválido

### Escenario 9 (error): Rango de fechas inválido [AT-02-05-09]
- Dado un trader autenticado
- Cuando consulta con `from = 2026-07-01T00:00:00.000Z` y `to = 2026-06-01T00:00:00.000Z` (`from > to`)
- Entonces se rechaza con `code = VALIDATION_ERROR` (HTTP 422)
- Y no se devuelve ningún movimiento

### Escenario 10 (error): Sin autenticación [AT-02-05-10]
- Dado un cliente sin credencial válida
- Cuando intenta consultar el historial
- Entonces se rechaza con `code = UNAUTHENTICATED` (HTTP 401)

### Escenario 11 (autorización): No se filtran movimientos ajenos [AT-02-05-11]
- Dado un trader autenticado como cuenta `A` y un fill entre `A` y `B`
- Cuando `A` consulta su historial y aparece el `TRADE_FILL` correspondiente
- Entonces el ítem muestra **solo** los postings de `A`
- Y no expone los postings de `B`, de `EX` ni de `EXTERNAL`; un intento de pedir el historial de `B` ⇒ `UNAUTHORIZED` (403)

### Escenario 12 (borde): Rango vacío `from == to` ⇒ lista vacía, no error [AT-02-05-12]
- Dado un trader autenticado con movimientos en distintas fechas
- Cuando consulta con `from = to = 2026-06-15T12:00:00.000Z`
- Entonces se devuelve una **lista vacía** con código de **éxito** (no `VALIDATION_ERROR`): el intervalo `from ≤ t < to` es vacío (RN-5/RN-9)

### Escenario 13 (error): `limit` fuera de rango [AT-02-05-13]
- Dado un trader autenticado
- Cuando consulta con un `limit` inválido, en estos sub-casos:
  - (a) `limit = 0` ⇒ `VALIDATION_ERROR` (HTTP 422)
  - (b) `limit = -1` ⇒ `VALIDATION_ERROR` (HTTP 422)
  - (c) `limit = 101` (mayor que el máximo `100`) ⇒ `VALIDATION_ERROR` (HTTP 422)
- Entonces en cada sub-caso `details.issues` indica el campo `limit` y la restricción `[1, 100]` violada (RN-7)

### Escenario 14: Filtro por múltiples tipos (OR entre tipos) [AT-02-05-14]
- Dado un trader con movimientos de tipos `DEPOSIT`, `ORDER_LOCK`, `TRADE_FILL` y `WITHDRAWAL_SETTLE`
- Cuando consulta con `type=DEPOSIT&type=ORDER_LOCK` (parámetros repetidos)
- Entonces solo recibe ítems con `type = DEPOSIT` **o** `type = ORDER_LOCK`
- Y ningún ítem de otro tipo (`TRADE_FILL`, `WITHDRAWAL_SETTLE`) (RN-4/RN-8)

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptacion (AT-*) pasan
- [ ] Reglas de negocio RN-1..RN-10 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md)
- [ ] (si aplica) Adherencia verificada al estandar on-chain citado — N/A (referencias `txHash`/`logIndex` de movimientos on-chain según 07/08)
