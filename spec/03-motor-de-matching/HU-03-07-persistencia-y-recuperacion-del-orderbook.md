# HU-03-07 — Persistencia y recuperación del orderbook

- **Epica:** 03 — Motor de Matching
- **Actor / rol:** Sistema (motor de matching) / Operador (reinicio, recuperación)
- **Prioridad:** Alta
- **Dependencias:** HU-03-01 (estructura), HU-03-02 (inserción), HU-03-03/04 (matching),
  HU-03-05 (eventos); Épica 02 (ledger de doble entrada como fuente de verdad de balances).
  Épica 00 (fundaciones, INV-8).
- **Estandares de dominio aplicables:** N/A (no on-chain).

## Historia
Como sistema, quiero persistir el orderbook y poder reconstruirlo de forma consistente tras
un reinicio (planificado o por caída), sin perder ni duplicar órdenes, fills ni eventos,
para que el estado del libro sobreviva y siga cumpliendo los invariantes (INV-7, INV-8).

## Contexto y alcance
Esta HU define la **durabilidad** del orderbook y su **recuperación**: qué se persiste, cómo
se reconstruye y qué propiedades debe cumplir el estado recuperado. No prescribe un motor de
almacenamiento concreto (agnóstico al backend): exige que el estado sea durable y
reconstruible. La fuente de verdad de los **balances** es el **ledger de doble entrada**
(épica 02); el orderbook se persiste de modo que las órdenes abiertas y su prioridad se
reconstruyan idénticas. La atomicidad de cada fill (INV-4) garantiza que un reinicio nunca
deje un fill "a medio aplicar".

## Reglas de negocio e invariantes
1. **RN-1 (durabilidad de órdenes abiertas).** Toda orden `LIMIT` abierta (`OPEN` o
   `PARTIALLY_FILLED`) y su `remainingWei` se persisten de forma durable antes de
   considerarse aceptada/posada hacia el cliente, de modo que sobreviva a un reinicio
   (INV-8). **Definición operativa de durable:** la escritura sobrevive a una **terminación
   abrupta** del proceso del motor (equivalente a `kill -9` / corte de energía): tras
   reiniciar, el dato persistido confirmado sigue presente. El mecanismo concreto (fsync,
   WAL, transacción de base de datos, etc.) es decisión de implementación.
2. **RN-2 (reconstrucción idéntica de la prioridad).** Tras el reinicio, el libro se
   reconstruye preservando, para cada orden: `orderId`, `accountId`, `side`, `price_min`,
   `quantityWei`, `filledWei`, `remainingWei`, `status` y la **secuencia de ingreso `seq`**.
   La prioridad precio-tiempo `(precio, seq)` reconstruida es **idéntica** a la previa
   (HU-03-01 RN-6).
3. **RN-3 (sin pérdida ni duplicación).** La recuperación no pierde ninguna orden abierta ni
   crea duplicados: el conjunto de órdenes abiertas tras el reinicio es **exactamente** el
   previo (mismo cardinal, mismos `orderId`).
4. **RN-4 (no-cruce tras recuperar — INV-7).** El libro reconstruido **no** queda cruzado:
   se sigue cumpliendo `best_bid_price < best_ask_price` cuando ambos lados existen. (Como el
   estado previo no estaba cruzado y la recuperación no altera precios, se preserva.)
5. **RN-5 (respaldo en fondos tras recuperar — INV-7).** Tras la recuperación, para cada
   cuenta y activo, la suma de `remainingWei` (o su quote) de sus órdenes abiertas coincide
   con el `bloqueado` reconstruido desde el ledger; ninguna orden queda sin respaldo ni hay
   bloqueado sin orden.
6. **RN-6 (balances desde el ledger — INV-8).** Los balances `disponible`/`bloqueado` se
   recomputan desde el ledger de doble entrada (épica 02) y reproducen exactamente los
   previos. El orderbook recuperado es consistente con esos balances (RN-5).
7. **RN-7 (atomicidad ante caída — INV-4).** Un reinicio en medio de un fill no deja estado
   parcial: o el fill quedó **completamente** persistido (con su settlement y la
   actualización del libro) o **no** quedó aplicado en absoluto. No hay maker decrementado
   sin su contrapartida ni `trade` persistido sin efecto en el libro.
8. **RN-8 (continuidad de secuencias — RN-7 de HU-03-05).** Tras el reinicio, `sequence`
   global y `tradeId` **continúan** desde el último valor persistido: no se reutilizan ni se
   reinician valores ya emitidos (monótonos y únicos a través de reinicios).
9. **RN-9 (idempotencia de recuperación).** Ejecutar la recuperación más de una vez (p. ej.
   reinicio repetido) produce el **mismo** estado; no duplica órdenes ni reaplica fills ya
   aplicados.
10. **RN-10 (consistencia con eventos ya emitidos).** Un `trade` que fue persistido/emitido
    antes del reinicio no se vuelve a emitir como nuevo (dedup por `tradeId`); su efecto ya
    está reflejado en el libro recuperado (HU-03-05 RN-9).
11. **RN-11 (serialización entera en la persistencia).** Los montos persistidos son enteros
    de unidad mínima (o string de entero), nunca floats binarios
    (`convenciones-monetarias.md`).
12. **RN-12 (determinismo de la recuperación).** Dado el mismo estado persistido, la
    reconstrucción es única y reproducible.
13. **RN-13 (recuperación del estado terminal de órdenes `MARKET`).** Una orden `MARKET`
    **nunca** descansa en el libro (HU-03-04 RN-7), por lo que no hay registro de ella en el
    orderbook persistido; su estado terminal vive en la épica 04 y en el ledger. Si la caída
    ocurre **después** de que algunos fills de una `MARKET` se persistieron pero **antes** de
    grabar su estado terminal, éste se **reconstruye infiriéndolo** a partir de los fills
    persistidos (atómicos, INV-4/RN-7) y de su `quantityWei` original:
    - `filledWei = quantityWei` ⇒ `FILLED`.
    - `0 < filledWei < quantityWei` ⇒ `CANCELLED` (remanente de market no ejecutable), con
      `reason` `MARKET_EXHAUSTED` o `MARKET_BUDGET_EXHAUSTED` según corresponda (si el motivo
      no se persistió, se usa el genérico de remanente no ejecutable).
    - `filledWei = 0` (ningún fill persistido) ⇒ la orden no produjo efecto: se reconstruye
      como `REJECTED` (sin liquidez/presupuesto) o `CANCELLED` con `filledWei = 0`, de forma
      **consistente** con lo que indique el ledger; nunca queda en limbo.

    Esta inferencia es determinista y consistente con el ledger sin requerir que la `MARKET`
    figure en el orderbook.

## Criterios de aceptacion (DoD)

### Escenario 1: Órdenes abiertas sobreviven al reinicio con su prioridad [AT-03-07-01]
- Dado un libro con bids: B1 `BUY 1 ETH @ 2000.00` (`seq=1`), B2 `BUY 1 ETH @ 2000.00`
  (`seq=2`); y un ask A1 `SELL 1 ETH @ 2001.00` (`seq=3`)
- Cuando el sistema se reinicia y reconstruye el orderbook
- Entonces las tres órdenes están presentes con los mismos `orderId` y `remainingWei`
  (RN-1, RN-3)
- Y la prioridad del nivel `bids @ 2000.00` sigue siendo B1 antes que B2 (FIFO por `seq`,
  RN-2)
- Y `best_bid (2000.00) < best_ask (2001.00)` (RN-4)

### Escenario 2: Fill parcial — remanente persistido correctamente [AT-03-07-02]
- Dado un maker `SELL 2 ETH @ 2000.00` que fue parcialmente ejecutado hasta
  `remainingWei = "1000000000000000000"` (1 ETH), estado `PARTIALLY_FILLED`
- Cuando el sistema se reinicia
- Entonces la orden se reconstruye con `status = "PARTIALLY_FILLED"`,
  `filledWei = "1000000000000000000"`, `remainingWei = "1000000000000000000"`, conservando
  su `seq` (RN-2)

### Escenario 3: Balances y respaldo consistentes tras recuperar [AT-03-07-03]
- Dado un estado con varias órdenes abiertas y sus fondos bloqueados
- Cuando se reinicia y se recomputan los balances desde el ledger (épica 02)
- Entonces `disponible`/`bloqueado` reproducen exactamente los previos (RN-6)
- Y para cada cuenta/activo, la suma de respaldos de órdenes abiertas == `bloqueado`
  atribuible a órdenes (RN-5, INV-7)

### Escenario 4 (borde): Caída en medio de un fill — atomicidad [AT-03-07-04]
- Dado un fill en curso (settlement no completado) cuando ocurre la caída
- Cuando el sistema se recupera
- Entonces el fill quedó **aplicado por completo** o **no aplicado**, nunca parcial (RN-7,
  INV-4)
- Y los invariantes INV-1, INV-2, INV-3, INV-7 se cumplen en el estado recuperado
- Cómo inducir la caída (reproducibilidad): simular la terminación abrupta mediante
  **inyección de fallo** —abortar el proceso (equivalente a `kill -9`) tras el primer paso
  del settlement, usando un hook de test o una simulación de I/O— y luego reiniciar y
  verificar INV-1..INV-7 (RN-1, RN-7)

### Escenario 5 (borde): Continuidad de sequence y tradeId [AT-03-07-05]
- Dado que antes del reinicio el último `sequence` emitido fue `S` y el último `tradeId`
  asignado fue `T`
- Cuando tras el reinicio se produce un nuevo evento
- Entonces el nuevo evento usa `sequence = S + 1` (el **siguiente entero contiguo**, sin
  hueco a través del reinicio, coherente con RN-8 y HU-03-05 RN-7 "sin huecos") y un
  `tradeId` nuevo distinto de `T`; no se reutiliza ningún valor previo (RN-8)
- Y el contador `seq` de prioridad de órdenes (independiente de `sequence`, README RT-2)
  también retoma desde su último valor persistido sin reutilizar (RN-2, RN-8)

### Escenario 6 (idempotencia): Reinicio repetido produce el mismo estado [AT-03-07-06]
- Dado un estado persistido P
- Cuando se ejecuta la recuperación dos veces seguidas (reinicio sobre reinicio)
- Entonces el estado reconstruido es idéntico ambas veces: mismas órdenes, misma prioridad,
  mismos balances; sin duplicados ni fills reaplicados (RN-9, RN-12)

### Escenario 7 (integridad): No se re-emite un trade ya persistido [AT-03-07-07]
- Dado un `trade` con `tradeId = X` persistido y reflejado en el libro antes del reinicio
- Cuando el sistema se recupera
- Entonces `X` **no** se vuelve a emitir como evento nuevo y su efecto ya está en el libro
  recuperado (RN-10, HU-03-05 RN-9)

### Escenario 8 (borde): Persistencia sin floats [AT-03-07-08]
- Dado el estado persistido del orderbook y del ledger
- Cuando se inspeccionan los montos almacenados
- Entonces todos son enteros de unidad mínima (o string de entero), nunca floats binarios
  (RN-11)

### Escenario 9 (borde): Recuperación del estado terminal de una MARKET [AT-03-07-09]
- Dado un `MARKET BUY 1 ETH` que alcanzó a persistir fills por `0.8 ETH`
  (`filledWei = "800000000000000000"`) antes de la caída, sin haber grabado su estado
  terminal, con el resto del libro agotado
- Cuando el sistema se recupera
- Entonces el estado de la `MARKET` se **infiere** de los fills persistidos: como
  `0 < filledWei < quantityWei`, queda `CANCELLED` con `reason = "MARKET_EXHAUSTED"` (RN-13)
- Y si en cambio `filledWei = quantityWei` se infiere `FILLED`; si `filledWei = 0` (ningún
  fill) se reconstruye consistente con el ledger (`REJECTED`/`CANCELLED` con `filledWei = 0`),
  nunca en limbo (RN-13)
- Y la `MARKET` **no** aparece en el orderbook recuperado (HU-03-04 RN-7)

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-*) pasan
- [ ] Reglas de negocio RN-1..RN-13 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md),
      en particular INV-4, INV-7, INV-8
- [ ] (si aplica) Adherencia verificada al estandar on-chain citado — N/A
