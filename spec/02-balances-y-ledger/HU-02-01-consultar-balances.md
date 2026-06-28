# HU-02-01 — Consultar balances

- **Epica:** 02 — Balances y Ledger
- **Actor / rol:** Trader autenticado (cuenta propia)
- **Prioridad:** Alta
- **Dependencias:** HU-01 (cuentas y autenticación: identidad `accountId` y autorización); Fundaciones 00.
- **Estandares de dominio aplicables:** N/A on-chain. Aplican convenciones monetarias (`00-fundaciones/convenciones-monetarias.md`): enteros de unidad mínima y serialización como string.

## Historia
Como trader autenticado, quiero consultar mi balance por activo discriminando el saldo
**disponible** y el **bloqueado**, para saber con cuánto puedo operar o retirar y cuánto
tengo reservado por órdenes o retiros en proceso.

## Contexto y alcance
Esta HU cubre la **lectura** del estado de balances de la cuenta autenticada: por cada
activo del sistema (`ETH`, `USDC`) devuelve `disponible`, `bloqueado` y `total`. La
respuesta siempre incluye **ambos** activos, aun cuando los saldos sean cero. No cubre la
mutación de balances (HU-02-02), ni el detalle de los asientos que los originan (HU-02-03 /
HU-02-05): es una **proyección** del estado actual. Los montos se reportan como **string de
entero en unidad mínima**; el cliente (web/mobile) los formatea a unidades humanas solo
para presentación.

## Reglas de negocio e invariantes
1. **RN-1 (autenticación):** la consulta requiere credencial válida. Sin credencial o con
   credencial inválida/expirada ⇒ `UNAUTHENTICATED` (401).
2. **RN-2 (autorización / aislamiento):** un usuario solo puede leer **sus propios**
   balances. El endpoint **resuelve la cuenta a partir de la credencial** y **no** acepta
   una `accountId` ajena como parámetro de consulta (la cuenta nunca se toma del payload del
   cliente). Si un cliente intenta forzar el acceso a otra cuenta `B` —p. ej. manipulando un
   identificador en la ruta o usando un endpoint administrativo que reciba `accountId`—, la
   capa de autorización (épica 01) responde `UNAUTHORIZED` (403) y no devuelve dato alguno de
   `B`.
3. **RN-3 (activos cubiertos):** la respuesta enumera **siempre** los dos activos del par,
   `ETH` y `USDC`, aun con saldo `"0"`. No se omiten activos sin fondos.
4. **RN-4 (campos por activo):** por cada activo se reportan exactamente
   `available` (disponible), `locked` (bloqueado) y `total`.
5. **RN-5 (partición, INV-3):** para todo activo, `total == available + locked`. El servidor
   computa `total` desde sus partes; no se acepta inconsistencia.
6. **RN-6 (no-negatividad, INV-2):** `available ≥ 0` y `locked ≥ 0` para todo activo en toda
   respuesta.
7. **RN-7 (unidad y serialización):** todos los montos están en **unidad mínima** (wei para
   ETH; unidad de 6 decimales para USDC) y se serializan como **string** que matchea
   `^(0|[1-9][0-9]*)$`. Nunca número JSON, decimales, signo ni notación científica.
8. **RN-8 (consistencia de lectura):** la respuesta es un **snapshot coherente**: los tres
   valores de un activo provienen del mismo estado (no mezcla lecturas de instantes
   distintos que violen RN-5).
9. **RN-9 (reconstruible desde el ledger, INV-8):** los valores reportados coinciden con la
   suma de los postings del ledger de la cuenta para cada bucket/activo.

## Criterios de aceptacion (DoD)

### Escenario 1: Consulta con fondos en ambos buckets [AT-02-01-01]
- Dado un trader autenticado cuya cuenta tiene `ETH`: disponible `1500000000000000000` (1.5 ETH) y bloqueado `0`
- Y `USDC`: disponible `3000000000` (3000 USDC) y bloqueado `2000000000` (2000 USDC reservados por una orden)
- Cuando consulta sus balances
- Entonces la respuesta incluye `ETH` con `available="1500000000000000000"`, `locked="0"`, `total="1500000000000000000"`
- Y `USDC` con `available="3000000000"`, `locked="2000000000"`, `total="5000000000"`
- Y todos los montos son strings que matchean `^(0|[1-9][0-9]*)$`

### Escenario 2 (borde): Cuenta recién creada, sin movimientos [AT-02-01-02]
- Dado un trader autenticado cuya cuenta nunca recibió depósitos ni operó
- Cuando consulta sus balances
- Entonces la respuesta lista **ambos** activos
- Y `ETH` reporta `available="0"`, `locked="0"`, `total="0"`
- Y `USDC` reporta `available="0"`, `locked="0"`, `total="0"`

### Escenario 3 (borde): Partición total = disponible + bloqueado [AT-02-01-03]
- Dado un trader autenticado con `USDC` disponible `4500000` y bloqueado `5500000`
- Cuando consulta sus balances
- Entonces `USDC.total` es `"10000000"`
- Y se cumple `total == available + locked` para cada activo de la respuesta

### Escenario 4 (borde): Saldos grandes que exceden 2^53 [AT-02-01-04]
- Dado un trader autenticado con `ETH` disponible `123456789012345678901` (≈ 123.45 ETH, > 2⁵³ en wei)
- Cuando consulta sus balances
- Entonces `ETH.available` se devuelve como string exacto `"123456789012345678901"` sin pérdida de precisión
- Y el valor **no** se serializa como número JSON

### Escenario 5 (error): Sin autenticación [AT-02-01-05]
- Dado un cliente sin credencial válida (ausente, inválida o expirada)
- Cuando intenta consultar balances
- Entonces la operación se rechaza con `code = UNAUTHENTICATED` y HTTP 401
- Y no se devuelve ningún balance

### Escenario 6 (error): Acceso a balances ajenos [AT-02-01-06]
- Dado un trader autenticado como cuenta `A`
- Cuando intenta consultar los balances de otra cuenta `B` forzando su identificador (ruta/endpoint administrativo que reciba `accountId = B`)
- Entonces la operación se rechaza con `code = UNAUTHORIZED` y HTTP 403 (capa de autorización, épica 01)
- Y no se filtra ningún dato de la cuenta `B`
- Nota: el endpoint estándar de balances no acepta `accountId` ajena (RN-2); la cuenta se infiere de la credencial. Este escenario verifica la **negación** de cualquier vía que intente seleccionar otra cuenta.

### Escenario 7 (consistencia): Coincide con la reconstrucción del ledger [AT-02-01-07]
- Dado un trader autenticado `A` con esta secuencia concreta de asientos aplicados en orden:
  1. `DEPOSIT` de `5000000000` USDC (5000 USDC) ⇒ `available(USDC) = 5000000000`.
  2. `ORDER_LOCK` de `2000000000` USDC (`orderId = "ord-1"`) ⇒ `available(USDC) = 3000000000`, `locked(USDC) = 2000000000`.
  3. `TRADE_FILL` (`tradeId = "T-1"`) como **comprador taker** que consume `2000000000` USDC del bloqueado y acredita `1` ETH neto de fee taker: `fee_base = ceil(1000000000000000000 × 20 / 10000) = 2000000000000000` wei ⇒ `available(ETH) += 998000000000000000`, `locked(USDC) −= 2000000000`.
- Cuando se consultan sus balances y, en paralelo, se reconstruyen sumando los postings del ledger por bucket/activo
- Entonces la consulta reporta exactamente: `USDC` `available="3000000000"`, `locked="0"`, `total="3000000000"`; `ETH` `available="998000000000000000"`, `locked="0"`, `total="998000000000000000"`
- Y esos valores coinciden **exactamente** con la reconstrucción `Σ CREDIT − Σ DEBIT` por bucket/activo del ledger (INV-8)

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptacion (AT-*) pasan
- [ ] Reglas de negocio RN-1..RN-9 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md)
- [ ] (si aplica) Adherencia verificada al estandar on-chain citado — N/A
