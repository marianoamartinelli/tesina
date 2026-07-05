# HU-04-06 — Consultar órdenes abiertas

- **Epica:** 04 — Gestión de Órdenes
- **Actor / rol:** Trader autenticado
- **Prioridad:** Media
- **Dependencias:** HU-04-01/02 (alta), HU-04-05 (estados), HU-01-* (autenticación),
  HU-09-* (forma del endpoint/paginación). Fundaciones (00).
- **Estandares de dominio aplicables:** N/A.

## Historia
Como **trader autenticado**, quiero **consultar mis órdenes abiertas con su estado y
cantidad remanente**, para **saber qué tengo expuesto en el mercado y poder decidir si
cancelo o espero**.

## Contexto y alcance
Cubre la consulta de las órdenes **activas** del trader: las que están en estado `OPEN` o
`PARTIALLY_FILLED`. Devuelve, por cada orden, al menos: `orderId`, `clientOrderId` (si lo
hubo), `side`, `type`, `priceMin` (para limit), `quantityWei`, `executedQty`,
`remainingQty`, `executedQuoteQty`, `avgExecutionPrice`, `status` y marca temporal de
creación. No incluye órdenes terminales (eso
es HU-04-07). El aislamiento por cuenta es estricto. La forma concreta del endpoint y la
paginación se fijan en HU-09-*; aquí se fija la **semántica**.

## Reglas de negocio e invariantes
1. **RN-1 (conjunto devuelto).** La consulta devuelve exactamente las órdenes de la cuenta
   autenticada cuyo estado ∈ `{OPEN, PARTIALLY_FILLED}`. No incluye `FILLED`, `CANCELLED`,
   `REJECTED` ni `NEW` transitorio.
2. **RN-2 (aislamiento).** Solo se devuelven órdenes **de la cuenta autenticada**; nunca de
   terceros (RE-7).
3. **RN-3 (remanente).** Cada orden reporta `remainingQty = quantityWei − executedQty` y
   `executedQty`; ambos coherentes con su estado (en `OPEN`, `executedQty = "0"` y
   `remainingQty = quantityWei`).
4. **RN-4 (orden determinista).** El resultado se ordena de forma **determinista** (por
   defecto: `createdAt` descendente y, ante empate, por `orderId` ascendente —comparación
   **numérica** si `orderId` es entero secuencial, **lexicográfica** si es UUID; el tipo de
   `orderId` se fija en HU-09-*). Si el tipo de `orderId` no garantizara un orden estable, se
   usa como desempate secundario el timestamp de ingreso al sistema con precisión de
   nanosegundos, para que la paginación sea estable.
5. **RN-5 (paginación).** Soporta paginación (límite + cursor/offset según HU-09-*). El
   conjunto total es consistente: una orden no aparece dos veces ni se pierde entre páginas
   bajo el orden de RN-4.
6. **RN-6 (serialización).** Todos los montos (`priceMin`, `quantityWei`, `executedQty`,
   `remainingQty`) se serializan como string `^(0|[1-9][0-9]*)$` (RE-8). Nunca como número
   JSON ni con decimales.
7. **RN-7 (auth).** Requiere trader autenticado; sin credencial ⇒ `UNAUTHENTICATED` (401).
8. **RN-8 (consistencia con el libro, INV-7).** El `remainingQty` de cada orden abierta
   coincide con el remanente respaldado por `bloqueado` para esa orden.
9. **RN-9 (solo lectura).** La consulta no modifica estado alguno (no mueve fondos, no
   cambia estados, no genera asientos).
10. **RN-10 (precio promedio y quote ejecutado).** Cada orden reporta:
    - `executedQuoteQty` = quote efectivamente gastado (BUY) o recibido (SELL)
      `= Σ floor(q_fill × P_fill / 10^18)` USDC-min (suma sobre todos los fills);
    - `avgExecutionPrice` = `floor(executedQuoteQty × 10^18 / executedQty)` USDC-min por ETH
      (precio promedio **ponderado** real, que puede diferir del `priceMin` límite cuando hubo
      fills a distintos precios). Si `executedQty = "0"`, `avgExecutionPrice` es **`null`**
      (serialización única; **nunca** `"0"`). Cuando no son `null`, ambos se serializan como
      string (RN-6). Sin este dato el trader no puede conciliar el USDC gastado con el ETH
      obtenido cuando barrió varios niveles.

## Criterios de aceptación (DoD)

### Escenario 1: Listar órdenes abiertas con estado y remanente [AT-04-06-01]
- Dado un trader con una orden `OPEN` (1 ETH, `executedQty="0"`) y una `PARTIALLY_FILLED` (1 ETH, `executedQty="400000000000000000"`)
- Cuando consulta sus órdenes abiertas
- Entonces recibe ambas órdenes con su `status`, `executedQty` y `remainingQty` correctos
- Y la `PARTIALLY_FILLED` muestra `remainingQty="600000000000000000"` (RN-3)

### Escenario 2 (borde): Sin órdenes abiertas [AT-04-06-02]
- Dado un trader sin órdenes activas
- Cuando consulta sus órdenes abiertas
- Entonces recibe una lista vacía (no un error)

### Escenario 3 (filtro): Excluye órdenes terminales [AT-04-06-03]
- Dado un trader con órdenes `FILLED`, `CANCELLED` y `REJECTED`, además de una `OPEN`
- Cuando consulta sus órdenes abiertas
- Entonces recibe **solo** la orden `OPEN`; ninguna terminal aparece (RN-1)

### Escenario 4 (aislamiento): No devuelve órdenes ajenas [AT-04-06-04]
- Dado un trader A con una orden `OPEN` y un trader B con otra orden `OPEN`
- Cuando A consulta sus órdenes abiertas
- Entonces recibe solo la suya; la de B no aparece (RN-2)

### Escenario 5 (paginación/orden): Resultado estable y paginado [AT-04-06-05]
- Dado un trader con N órdenes abiertas (N mayor que el tamaño de página)
- Cuando consulta página por página con el orden por defecto (`createdAt` desc, `orderId` asc en empate)
- Entonces cada orden aparece exactamente una vez a lo largo de las páginas, sin duplicados ni omisiones (RN-4, RN-5)

### Escenario 6 (error): No autenticado [AT-04-06-06]
- Dado un cliente sin credencial válida
- Cuando consulta órdenes abiertas
- Entonces se rechaza con `UNAUTHENTICATED` (401)

### Escenario 7 (serialización): Montos como string entero [AT-04-06-07]
- Dado un trader con una orden abierta `priceMin="2000000000"`, `quantityWei="1000000000000000000"`
- Cuando consulta sus órdenes abiertas
- Entonces todos los campos monetarios viajan como string `^(0|[1-9][0-9]*)$` (p. ej. `"2000000000"`), nunca como número JSON ni con decimales (RN-6), con la única excepción de `avgExecutionPrice = null` cuando `executedQty = "0"` (RN-10)

### Escenario 8 (solo lectura): La consulta no altera estado [AT-04-06-08]
- Dado un trader con balances y órdenes en cierto estado
- Cuando consulta sus órdenes abiertas repetidas veces
- Entonces balances, estados y orderbook permanecen idénticos (RN-9)

### Escenario 9 (precio promedio): `avgExecutionPrice` refleja el precio ponderado real [AT-04-06-09]
- Dado una orden `BUY LIMIT` `priceMin="2000000000"`, `quantityWei="2000000000000000000"` (2 ETH) que ejecutó como taker 1 ETH en dos niveles: `400000000000000000` wei a `1980000000` y `600000000000000000` wei a `1990000000`, y cuyo remanente de 1 ETH descansa (`PARTIALLY_FILLED`)
- Cuando consulta sus órdenes abiertas
- Entonces `executedQty="1000000000000000000"` y `executedQuoteQty = "1986000000"` (`floor(0.4·10^18 × 1980000000 / 10^18)=792000000` más `floor(0.6·10^18 × 1990000000 / 10^18)=1194000000`)
- Y `avgExecutionPrice = floor(1986000000 × 10^18 / 1000000000000000000) = "1986000000"`, **distinto** del `priceMin` límite `"2000000000"` (RN-10)

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-04-06-01 .. AT-04-06-09) pasan
- [ ] Reglas de negocio RN-1..RN-10 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md (`UNAUTHENTICATED`)
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md (montos string entero)
- [ ] Sin violacion de invariantes globales (INV-7 consistencia remanente/bloqueado; consulta de solo lectura)
- [ ] (si aplica) Adherencia verificada al estandar on-chain citado — N/A
