# Invariantes globales

Propiedades que **toda** implementación debe respetar **en todo momento** (o, cuando se
indica, tras completarse cada operación atómica). Son independientes del backend elegido y
constituyen un **criterio central de evaluación**: una corrida que viole cualquiera de
estos invariantes es incorrecta, incluso si pasa tests funcionales individuales.

Cada invariante se expresa de forma **chequeable**: se indica la propiedad, su formulación
formal y cómo verificarla.

> Notación: los montos están en unidades mínimas enteras (wei para ETH, USDC-min para
> USDC). `A` recorre el conjunto de activos `{ETH, USDC}`. `acc` recorre las cuentas de
> usuario. `EX` es la cuenta interna de fees del exchange.

---

## INV-1 — Conservación de fondos (no se crea ni se destruye valor)

**Propiedad.** Para cada activo `A`, la suma de todos los balances internos (usuarios +
cuenta de fees del exchange) es igual a los depósitos confirmados menos los retiros
confirmados (incluidas las fees on-chain que el exchange pagó por los retiros, si se
modelan).

**Formulación.**

```
Para cada activo A:
  Σ_acc total(acc, A) + total(EX, A)
    == Σ depósitos_confirmados(A) − Σ retiros_confirmados(A)
```

Donde `total(x, A) = disponible(x, A) + bloqueado(x, A)`.

**Corolarios.**
- Un **fill no cambia** la suma total por activo: solo redistribuye entre maker, taker y
  `EX` (ver INV-4 y `convenciones-monetarias.md` §3.4).
- Ningún flujo interno (bloqueo, settlement, cobro de fee) puede alterar `Σ total(·, A)`.
  Solo depósitos y retiros (eventos on-chain) lo hacen.

**Cómo verificar.**
- Tras cualquier secuencia de operaciones internas (órdenes, fills, cancelaciones), la
  suma `Σ_acc total(acc, A) + total(EX, A)` debe ser **idéntica** antes y después.
- Reconciliación con el ledger: la suma de asientos del ledger por activo debe reproducir
  exactamente cada balance.

---

## INV-2 — No-negatividad de balances

**Propiedad.** Ningún balance disponible ni bloqueado puede ser negativo, para ninguna
cuenta y ningún activo, en ningún momento observable.

**Formulación.**

```
Para todo acc, para todo A:
  disponible(acc, A) ≥ 0  ∧  bloqueado(acc, A) ≥ 0
```

**Cómo verificar.**
- Toda operación que intente dejar un balance en negativo debe ser **rechazada antes** de
  aplicarse (típicamente con `INSUFFICIENT_FUNDS`), no aplicada y luego "corregida".
- Test: intentar bloquear/retirar más que el disponible falla y deja los balances
  intactos.

---

## INV-3 — Partición disponible + bloqueado = total

**Propiedad.** Para cada cuenta y activo, el total es exactamente la suma de disponible y
bloqueado; no hay un tercer "estado" de fondos.

**Formulación.**

```
Para todo acc, para todo A:
  total(acc, A) == disponible(acc, A) + bloqueado(acc, A)
```

**Reglas de transición (consecuencia).**
- **Bloquear** (al crear orden/retiro): `disponible −= x; bloqueado += x` (total constante).
- **Liberar** (al cancelar / al sobrar tras un fill por mejor precio):
  `bloqueado −= x; disponible += x` (total constante).
- **Consumir** (al liquidar): `bloqueado −= x` y, en la contraparte, `disponible += y` del
  **otro** activo; el total por activo de cada cuenta cambia, pero la suma global se
  conserva (INV-1).

**Cómo verificar.**
- En cualquier snapshot, recomputar `total` desde sus partes y comparar.

---

## INV-4 — Atomicidad del settlement

**Propiedad.** El settlement de un fill se aplica **completo o nada**. No existe un estado
intermedio observable en el que, por ejemplo, se haya debitado la base del vendedor pero
no acreditado al comprador, o se haya cobrado la fee sin mover el principal.

**Formulación.** Un settlement es una transacción `T` que aplica el conjunto de asientos
`{ débito/crédito de base, débito/crédito de quote, fee_base→EX, fee_quote→EX }`. Para
todo observador y todo instante:

```
estado_visible(T) ∈ { antes_de_T_completo, despues_de_T_completo }
```

y nunca un estado parcial de `T`.

**Consecuencias.**
- Si cualquier paso del settlement falla, **se revierte todo** y el fill no se aplica.
- El conjunto de asientos de un fill respeta exactamente las ecuaciones de conservación de
  `convenciones-monetarias.md` §3.4.

**Cómo verificar.**
- Tras cada fill, INV-1, INV-2 e INV-3 se cumplen (no hay ventana donde se rompan).
- Una falla inyectada a mitad del settlement deja el sistema en el estado previo exacto.

---

## INV-5 — Idempotencia de la acreditación de depósitos

**Propiedad.** Un depósito on-chain se acredita al balance interno **a lo sumo una vez**,
sin importar cuántas veces se observe/reprocese el mismo evento on-chain.

**Identidad del depósito.** Un depósito se identifica unívocamente por la tupla
`(txHash, logIndex)` (para transferencias ERC-20) o `(txHash, 0)` (para ETH nativo). Dos
observaciones con la misma identidad refieren al **mismo** depósito.

**Formulación.**

```
Para toda identidad de depósito d:
  veces_acreditado(d) ≤ 1
```

**Reglas.**
- La acreditación solo ocurre cuando el depósito alcanzó `CONFIRMACIONES_REQUERIDAS = 12`
  (si no, `DEPOSIT_NOT_CONFIRMED`).
- Reprocesar un depósito ya acreditado **no** vuelve a acreditar (responde/registra
  `DEPOSIT_ALREADY_CREDITED`; no es un error que altere balances).

**Cómo verificar.**
- Procesar el mismo `(txHash, logIndex)` N veces incrementa el balance **una sola vez**.
- La suma de depósitos acreditados coincide con el lado de depósitos de INV-1.

---

## INV-6 — Anti-replay on-chain (EIP-155) y unicidad de nonce

**Propiedad.** Cada transacción saliente (retiro) se firma con `chainId = 11155111`
(EIP-155) y usa un **nonce único y secuencial** por dirección emisora, de modo que no
puede ser replayada en otra red ni reutilizada en la misma.

**Formulación.**

```
Toda transacción saliente tx:
  tx.chainId == 11155111
  ∧ nonce(tx) es único por dirección emisora
  ∧ los nonces usados por una dirección forman una secuencia sin huecos ni repeticiones
```

**Reglas.**
- Construir una firma o transacción con un `chainId` distinto de `11155111` es inválido
  (`CHAIN_ID_MISMATCH`).
- Reutilizar o saltear un nonce es un conflicto (`NONCE_CONFLICT`).

**Cómo verificar.**
- Inspeccionar las transacciones firmadas: todas llevan `chainId = 11155111`.
- La lista de nonces por dirección emisora es estrictamente creciente y contigua.

---

## INV-7 — Integridad del orderbook y prioridad precio-tiempo

**Propiedad.** En todo momento el orderbook está ordenado por prioridad precio-tiempo y no
contiene niveles cruzados; los fondos que respaldan cada orden abierta están efectivamente
bloqueados.

**Formulación.**

```
∀ orden abierta O de la cuenta acc:
  bloqueado(acc, asset(O)) cubre el remanente no ejecutado de O
∧ best_bid < best_ask  (si ambos lados existen: el libro no queda cruzado tras matchear)
∧ dentro de un nivel de precio, el orden de atención es FIFO por secuencia de
  ingreso (seq): un entero estrictamente monótono y único que el motor asigna a
  la orden en el instante en que se vuelve pasiva. El timestamp de reloj de pared
  NO es la clave de desempate (dos órdenes pueden compartir timestamp, nunca seq)
```

**Cómo verificar.**
- La suma de remanentes bloqueados por órdenes abiertas de una cuenta == su `bloqueado`
  por ese activo (junto con retiros en proceso).
- Tras procesar una orden entrante, no quedan órdenes cruzables sin matchear.
- Dos órdenes al mismo precio se ejecutan en orden de su `seq` (secuencia de ingreso
  al libro asignada por el motor al posarse), no por timestamp de reloj de pared.

---

## INV-8 — Persistencia y recuperación

**Propiedad.** El orderbook, los balances y el ledger son **persistentes**: tras un
reinicio, el estado reconstruido es consistente con el previo y sigue satisfaciendo
INV-1..INV-7.

**Cómo verificar.**
- Reiniciar el sistema y recomputar balances desde el ledger reproduce los balances
  previos.
- Las órdenes abiertas siguen abiertas con su prioridad intacta.

---

## Resumen (checklist de evaluación)

| ID    | Invariante                                              | Se chequea sobre…                         |
|-------|--------------------------------------------------------|-------------------------------------------|
| INV-1 | Conservación de fondos por activo                       | Σ balances = depósitos − retiros          |
| INV-2 | No-negatividad de disponible y bloqueado               | Cada balance ≥ 0                          |
| INV-3 | disponible + bloqueado = total                          | Cada cuenta/activo                        |
| INV-4 | Atomicidad del settlement                              | Cada fill: todo o nada                    |
| INV-5 | Idempotencia de acreditación de depósitos              | (txHash, logIndex) acreditado ≤ 1 vez     |
| INV-6 | Anti-replay EIP-155 + unicidad de nonce                | chainId=11155111, nonces únicos/contiguos |
| INV-7 | Integridad del orderbook + prioridad precio-tiempo     | Orden, no-cruce, respaldo en bloqueado    |
| INV-8 | Persistencia y recuperación                            | Estado consistente tras reinicio          |
