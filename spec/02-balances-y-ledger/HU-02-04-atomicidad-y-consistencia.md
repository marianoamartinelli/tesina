# HU-02-04 — Atomicidad y consistencia de balances

- **Epica:** 02 — Balances y Ledger
- **Actor / rol:** Sistema (motor de balances/ledger).
- **Prioridad:** Alta
- **Dependencias:** HU-02-02 (transiciones), HU-02-03 (asientos), HU-02-01 (lectura); HU-01 (cuentas). Consumida por 03/04/05/07/08. Fundaciones 00.
- **Estandares de dominio aplicables:** N/A on-chain. Aplican invariantes globales (`00-fundaciones/invariantes-globales.md`: INV-1, INV-2, INV-3, INV-4, INV-8) y convenciones monetarias.

## Historia
Como sistema, quiero que toda operación sobre balances sea **atómica** (todo o nada) y
**consistente** ante fallos y concurrencia, para que nunca se creen ni se destruyan fondos,
nunca quede un balance negativo y el estado tras un reinicio sea reconstruible y correcto.

## Contexto y alcance
Esta HU agrupa las garantías **transversales** de integridad del subsistema de balances:
atomicidad de cada operación (bloqueo, liberación, settlement), conservación de fondos,
no-negatividad, aislamiento ante concurrencia y recuperación tras reinicio. No introduce
operaciones nuevas: especifica **cómo deben comportarse** las de HU-02-02/03 bajo fallos y
carga concurrente. Es, en gran medida, la materialización chequeable de INV-1, INV-2, INV-3,
INV-4 e INV-8 dentro de esta épica.

## Reglas de negocio e invariantes
1. **RN-1 (atomicidad, INV-4):** toda operación de balance se aplica como una transacción
   única: o se persisten **todos** sus postings y los cambios de balance asociados, o
   **ninguno**. No existe estado intermedio observable (p. ej. débito de una pata sin el
   crédito de la otra).
2. **RN-2 (conservación, INV-1):** ninguna operación interna (bloqueo, liberación,
   settlement, cobro de fee) altera `Σ_acc total(acc,A) + total(EX,A)` para ningún activo.
   Solo `DEPOSIT` (la aumenta) y `WITHDRAWAL_SETTLE` (la disminuye) la modifican. La
   reconciliación contra `EXTERNAL(A)` debe cerrar exactamente.
3. **RN-3 (no-negatividad por rechazo previo, INV-2):** toda operación que dejaría
   `available < 0` o `locked < 0` se **rechaza antes** de aplicarse (típicamente
   `INSUFFICIENT_FUNDS`); nunca se aplica para luego "corregir". Los balances quedan
   intactos tras un rechazo.
4. **RN-4 (partición, INV-3):** tras cada operación, `total = available + locked` por cuenta
   y activo. Las transiciones mantienen `total` (bloquear/liberar) o lo cambian solo por
   consumo/settlement conservando la suma global.
5. **RN-5 (aislamiento / serialización ante concurrencia):** operaciones concurrentes que
   tocan el mismo balance —**incluida la cuenta de fees `EX`**— se comportan como si se
   hubieran ejecutado en **algún orden secuencial** (serializable respecto del balance
   afectado). En particular: (a) dos bloqueos concurrentes cuya suma excede el disponible no
   pueden ambos tener éxito (a lo sumo uno); (b) la cuenta `EX` acumula fees de **todos** los
   fills concurrentes de **todas** las cuentas y es una *hot account*: dos fills paralelos no
   pueden leer el mismo `disponible(EX, A)` y acreditar cada uno su fee sobre ese mismo
   snapshot (se perderían fees); las acreditaciones a `EX` se serializan igual que cualquier
   otro balance.
6. **RN-6 (rollback ante fallo):** si cualquier paso de una operación falla (error de
   persistencia, validación interna, caída), se **revierte** todo lo ya aplicado de esa
   operación, dejando el estado exactamente como antes de iniciarla.
7. **RN-7 (durabilidad y persistencia, INV-8):** una operación confirmada sobrevive a un
   reinicio. Tras reiniciar, los balances se **reconstruyen** desde el ledger y coinciden
   con los previos; las órdenes abiertas siguen respaldadas por su `locked`.
8. **RN-8 (recuperación sin asientos parciales, INV-4):** tras un reinicio que interrumpió
   una operación en curso, el estado recuperado **no** contiene asientos parciales ni
   balances incoherentes: la operación interrumpida quedó **completamente aplicada** o
   **completamente ausente**.
9. **RN-9 (idempotencia de orígenes idempotentes, INV-5):** reprocesar un evento idempotente
   (p. ej. la acreditación de un depósito por `(txHash, logIndex)`) **no** produce un doble
   efecto sobre los balances.
10. **RN-10 (consistencia post-condición verificable):** después de **cualquier** secuencia
    de operaciones, deben cumplirse simultáneamente INV-1, INV-2, INV-3; cualquier violación
    indica un defecto y debe ser detectable por reconciliación ledger↔balances.
11. **RN-11 (contrato de aislamiento por cuenta/activo):** el subsistema garantiza
    aislamiento a nivel de `(account, asset)`: para un mismo par, la **verificación de
    disponible** y la **aplicación de cambios de bucket** se serializan sin entrelazado de
    estados intermedios. El **mecanismo** de implementación es decisión del implementador
    —p. ej. lock pesimista de fila (`SELECT ... FOR UPDATE`), transacción de BD con nivel de
    aislamiento `SERIALIZABLE`, lock optimista con reintento, o un actor/canal en memoria—,
    pero el **comportamiento observable debe ser equivalente a una ejecución serial**. Para
    los tests de concurrencia (AT-02-04-04/05) se exige un nivel de aislamiento equivalente a
    `SERIALIZABLE` sobre el balance afectado (o un lock que lo garantice).

## Criterios de aceptacion (DoD)

### Escenario 1: Conservación tras un fill (no se crea ni destruye valor) [AT-02-04-01]
- Dado un sistema con `Σ total(·, ETH) = S_eth` y `Σ total(·, USDC) = S_usdc` (incluyendo `EX`)
- Cuando se liquida un fill entre dos cuentas (con sus fees a `EX`)
- Entonces tras el settlement `Σ total(·, ETH) = S_eth` y `Σ total(·, USDC) = S_usdc` (idénticas; INV-1)
- Y la reconciliación contra `EXTERNAL(A)` sigue cerrando

### Escenario 2: Atomicidad del settlement (todo o nada) [AT-02-04-02]
> Test de **integración** con prerrequisito de infraestructura: requiere un **mecanismo de inyección de fallo** explícito. Mecanismo de referencia: una implementación de repositorio **configurable** que lanza una excepción **después de persistir el N-ésimo posting** del asiento (p. ej. N = 3 de los 6 postings del `TRADE_FILL`), o una **violación de constraint** de la BD en el 4.º posting. La operación corre dentro de una transacción única.
- Dado un fill cuyo settlement implica consumir `locked`, acreditar `available` a la contraparte y mover fees a `EX` (6 postings; ver AT-02-03-04)
- Cuando el repositorio configurado lanza la excepción tras persistir el 3.º posting (antes de completar el asiento)
- Entonces la transacción hace **rollback** y el settlement se revierte por completo: ni el consumo ni los créditos ni las fees quedan aplicados; no queda ningún posting de ese asiento persistido
- Y los balances vuelven al estado exacto previo al fill (INV-4); no hay estado parcial observable

### Escenario 3 (no-negatividad): Rechazo previo deja balances intactos [AT-02-04-03]
- Dado un trader con `USDC` disponible `1000000` (1 USDC)
- Cuando intenta una operación que requeriría bloquear `10000000` (10 USDC)
- Entonces se rechaza con `INSUFFICIENT_FUNDS` **antes** de aplicar (INV-2)
- Y `USDC` permanece disponible `"1000000"`, bloqueado `"0"`

### Escenario 4 (concurrencia): Dos operaciones que exceden el disponible [AT-02-04-04]
> Test de **integración** con prerrequisito de infraestructura: protocolo de **contención determinista**. Mecanismo de referencia: una **barrera de sincronización** (barrier / countdown latch) que obliga a ambas operaciones a alcanzar su *check de disponible* **antes** de que cualquiera aplique su cambio. Nivel de aislamiento equivalente a `SERIALIZABLE` sobre el balance (RN-11). El test es **determinista** (no probabilístico) gracias a la barrera; basta una iteración.
- Dado un trader con `USDC` disponible `2000000000` y bloqueado `0`
- Cuando dos bloqueos de `2000000000` cada uno se liberan simultáneamente desde la barrera (ambos leyeron `disponible = 2000000000` antes de aplicar)
- Entonces exactamente **uno** tiene éxito y el otro se rechaza con `INSUFFICIENT_FUNDS` (RN-5/RN-11)
- Y en ningún instante observable `available` queda negativo ni `locked > total`
- Y el estado final (`disponible "0"`, `bloqueado "2000000000"`, `total "2000000000"`) es equivalente a haber ejecutado los bloqueos en algún orden secuencial

### Escenario 5 (concurrencia): Fill y cancelación concurrentes sobre la misma orden [AT-02-04-05]
> Test de **integración**: misma barrera de sincronización que AT-02-04-04, aplicada al remanente bloqueado de una orden; el `fill` y la `cancelación` alcanzan la barrera antes de mutar el `locked`. Alternativa de caja blanca: `T1` (fill) toma el lock de fila del balance y aún no committea; cuando `T2` (cancelación) intenta el mismo lock, **espera** a `T1` (o falla por timeout) y al reanudar ve el remanente ya consumido.
- Dada una orden abierta con remanente bloqueado
- Cuando, liberados desde la barrera, llegan un fill que la ejecuta y una cancelación
- Entonces solo **uno** de los efectos se aplica al remanente: o se consume por el fill o se libera por la cancelación, nunca ambos sobre la misma cantidad
- Y no se libera ni se consume más de lo bloqueado (INV-2/INV-7); la suma global se conserva (INV-1)

### Escenario 6 (persistencia): Reconstrucción de balances tras reinicio [AT-02-04-06]
- Dado un sistema con balances y ledger poblados (depósitos, órdenes, fills, retiros)
- Cuando se reinicia el sistema
- Entonces los balances reconstruidos desde el ledger coinciden **exactamente** con los previos al reinicio (INV-8)
- Y las órdenes abiertas siguen respaldadas por el `locked` correspondiente

### Escenario 7 (recuperación): Sin asientos parciales tras caída a mitad de operación [AT-02-04-07]
> Test de **integración** con prerrequisito de infraestructura: la "caída" se materializa como **interrupción del proceso** durante una transacción no committeada (p. ej. abortar el proceso, o forzar el rollback de la transacción en curso, después de persistir parte de los postings pero antes del commit). Como la unidad atómica es la transacción de BD, una caída antes del commit no deja datos.
- Dado un sistema que es interrumpido mientras aplicaba una operación de balance (p. ej. un `TRADE_FILL`), con la transacción **sin committear**
- Cuando se recupera tras el reinicio y se reconstruyen los balances desde el ledger
- Entonces la operación interrumpida está **completamente aplicada** (si alcanzó el commit) o **completamente ausente** (si no; nunca a medias; INV-4/INV-8)
- Y se cumplen INV-1, INV-2 e INV-3 sobre el estado recuperado

### Escenario 8 (idempotencia): Reprocesar depósito no duplica efecto [AT-02-04-08]
- Dado un depósito ya acreditado con identidad `(txHash, logIndex)`
- Cuando el mismo evento se procesa N veces adicionales
- Entonces el balance se incrementa **una sola vez** en total (INV-5)
- Y `Σ total(·, A)` refleja un único crédito por ese depósito

### Escenario 9 (post-condición global): Invariantes tras secuencia arbitraria [AT-02-04-09]
- Dada una secuencia arbitraria de operaciones válidas e inválidas (altas, cancelaciones, fills, retiros, depósitos)
- Cuando finaliza la secuencia
- Entonces se verifican simultáneamente INV-1 (conservación), INV-2 (no-negatividad) e INV-3 (`total = disponible + bloqueado`)
- Y la reconciliación ledger↔balances cierra exactamente para `ETH` y `USDC` (RN-10)

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptacion (AT-*) pasan
- [ ] Reglas de negocio RN-1..RN-11 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md)
- [ ] (si aplica) Adherencia verificada al estandar on-chain citado — N/A
