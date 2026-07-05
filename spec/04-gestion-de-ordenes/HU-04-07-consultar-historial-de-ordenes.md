# HU-04-07 — Consultar historial de órdenes

- **Epica:** 04 — Gestión de Órdenes
- **Actor / rol:** Trader autenticado
- **Prioridad:** Media
- **Dependencias:** HU-04-05 (estados terminales), HU-04-06 (consulta de abiertas),
  HU-01-* (autenticación), HU-09-* (forma del endpoint/paginación). Fundaciones (00).
- **Estandares de dominio aplicables:** N/A.

## Historia
Como **trader autenticado**, quiero **consultar el historial de mis órdenes finalizadas,
filtrable por estado y por período**, para **auditar mi actividad pasada y revisar qué se
ejecutó, qué cancelé y qué fue rechazado**.

## Contexto y alcance
Cubre la consulta de las órdenes **terminales** del trader: `FILLED`, `CANCELLED` y
`REJECTED`. Permite filtrar por `status` (uno o varios estados terminales) y por **período**
(rango temporal). Devuelve, por cada orden, al menos: `orderId`, `clientOrderId` (si lo
hubo), `side`, `type`, `priceMin` (para limit), `quantityWei`/`quoteOrderQty`,
`executedQty`, `remainingQty`, `executedQuoteQty`, `avgExecutionPrice`, `status`, marca de
creación y marca de finalización. El aislamiento por
cuenta es estricto. La forma concreta del endpoint y la paginación se fijan en HU-09-*;
aquí se fija la **semántica**.

## Reglas de negocio e invariantes
1. **RN-1 (conjunto devuelto).** La consulta devuelve órdenes de la cuenta autenticada en
   estado terminal ∈ `{FILLED, CANCELLED, REJECTED}`. **No** incluye `OPEN`,
   `PARTIALLY_FILLED` ni `NEW` (eso es HU-04-06).
2. **RN-2 (aislamiento).** Solo órdenes de la cuenta autenticada (RE-7).
3. **RN-3 (filtro por estado).** Acepta filtrar por uno o varios estados terminales. Un
   `status` solicitado fuera de `{FILLED, CANCELLED, REJECTED}` ⇒ `VALIDATION_ERROR` (422).
   Sin filtro de estado, devuelve los tres.
4. **RN-4 (filtro por período).** Acepta un rango temporal (`from`/`to`, timestamps UTC en
   formato ISO-8601) aplicado a la marca de **finalización** de la orden. Rango con
   `from > to` o fechas mal formadas ⇒ `VALIDATION_ERROR` (422). El rango `[from, to]` es
   **cerrado en ambos extremos**: una orden cuya finalización es exactamente `== from` o
   `== to` **se incluye** en el resultado. Esto aplica tanto a fecha/hora exacta como a
   rangos de días completos si el API acepta solo fechas.
5. **RN-5 (filtros combinables).** `status` y período se combinan con AND: una orden
   aparece solo si satisface todos los filtros presentes.
6. **RN-6 (orden determinista).** El resultado se ordena de forma determinista y
   documentada (por defecto: marca de finalización descendente y, ante empate, `orderId`
   ascendente), para paginación estable.
7. **RN-7 (paginación).** Soporta paginación (límite + cursor/offset, HU-09-*); sin
   duplicados ni omisiones entre páginas bajo el orden de RN-6.
8. **RN-8 (serialización).** Todos los montos (`priceMin`, `quantityWei`, `quoteOrderQty`,
   `executedQty`) se serializan como string `^(0|[1-9][0-9]*)$` (RE-8).
9. **RN-9 (auth).** Requiere trader autenticado; sin credencial ⇒ `UNAUTHENTICATED` (401).
10. **RN-10 (solo lectura, inmutabilidad).** La consulta no modifica estado. Las órdenes
    terminales son inmutables (HU-04-05 RN-2): el historial es estable en el tiempo.
11. **RN-11 (campos por orden terminal).** Cada orden reporta, además de su `status`:
    - `executedQty` (base, wei) y `remainingQty` (porción **no** ejecutada): `FILLED` ⇒
      `remainingQty="0"`; `CANCELLED` ⇒ `remainingQty = quantityWei − executedQty` (la porción
      descartada/cancelada); `REJECTED` ⇒ `remainingQty = quantityWei` (para órdenes por
      cantidad; para market por `quoteOrderQty`, `remainingQty` no aplica y es **`null`** —
      serialización única; nunca `"0"`).
    - `executedQuoteQty` (quote gastado/recibido) y `avgExecutionPrice`
      (`floor(executedQuoteQty × 10^18 / executedQty)`, o **`null`** si `executedQty="0"` —
      serialización única, nunca `"0"`), con la misma definición que HU-04-06 RN-10.
12. **RN-12 (qué REJECTED aparecen).** Solo las órdenes rechazadas por la **capa de matching**
    (`MARKET_NO_LIQUIDITY`, `SELF_TRADE_BLOCKED`, `MARKET_BUDGET_INSUFFICIENT`) se persisten y
    aparecen como `REJECTED`; los rechazos de validación/idempotencia/fondos **no** aparecen
    (no se persisten como órdenes) (HU-04-05 RN-5, RE-12).

## Criterios de aceptación (DoD)

### Escenario 1: Listar historial sin filtros [AT-04-07-01]
- Dado un trader con órdenes `FILLED`, `CANCELLED` y `REJECTED`
- Cuando consulta su historial sin filtros
- Entonces recibe las tres órdenes con su `status`, `executedQty` y marcas temporales

### Escenario 2 (filtro): Solo FILLED [AT-04-07-02]
- Dado un trader con órdenes `FILLED`, `CANCELLED` y `REJECTED`
- Cuando consulta su historial filtrando `status=FILLED`
- Entonces recibe únicamente las órdenes `FILLED` (RN-3, RN-5)

### Escenario 3 (filtro): Por período [AT-04-07-03]
- Dado órdenes finalizadas en distintas fechas
- Cuando consulta con `from`/`to` que cubren solo parte del rango
- Entonces recibe únicamente las órdenes cuya finalización cae dentro del rango inclusivo (RN-4)

### Escenario 4 (filtro combinado): Estado + período [AT-04-07-04]
- Dado órdenes `FILLED` y `CANCELLED` en distintas fechas
- Cuando consulta `status=CANCELLED` y un período acotado
- Entonces recibe solo las `CANCELLED` finalizadas dentro del período (RN-5)

### Escenario 5 (exclusión): No incluye abiertas [AT-04-07-05]
- Dado un trader con órdenes `OPEN`/`PARTIALLY_FILLED` además de terminales
- Cuando consulta su historial
- Entonces las abiertas **no** aparecen (RN-1)

### Escenario 6 (aislamiento): No devuelve órdenes ajenas [AT-04-07-06]
- Dado un trader A con historial y un trader B con historial
- Cuando A consulta su historial
- Entonces recibe solo el suyo (RN-2)

### Escenario 7 (paginación): Resultado estable y paginado [AT-04-07-07]
- Dado un trader con muchas órdenes terminales
- Cuando pagina con el orden por defecto (finalización desc, `orderId` asc en empate)
- Entonces cada orden aparece exactamente una vez, sin duplicados ni omisiones (RN-6, RN-7)

### Escenario 8 (borde): Historial vacío [AT-04-07-08]
- Dado un trader sin órdenes terminales
- Cuando consulta su historial
- Entonces recibe una lista vacía (no un error)

### Escenario 9 (error): Filtro de estado inválido [AT-04-07-09]
- Dado un trader autenticado
- Cuando consulta con `status=OPEN` (no terminal) o `status=FOO`
- Entonces se rechaza con `VALIDATION_ERROR` (422), `details.issues` indica el valor inválido (RN-3)

### Escenario 10 (error): Rango temporal inválido [AT-04-07-10]
- Dado un trader autenticado
- Cuando consulta con `from` posterior a `to`, o con fechas mal formadas
- Entonces se rechaza con `VALIDATION_ERROR` (422) (RN-4)

### Escenario 11 (error): No autenticado [AT-04-07-11]
- Dado un cliente sin credencial válida
- Cuando consulta el historial
- Entonces se rechaza con `UNAUTHENTICATED` (401)

### Escenario 12 (serialización + inmutabilidad): Montos string y resultado estable [AT-04-07-12]
- Dado una orden `FILLED` con `executedQty="1000000000000000000"`
- Cuando consulta el historial dos veces en momentos distintos
- Entonces los montos viajan como string `^(0|[1-9][0-9]*)$` y la orden terminal aparece idéntica en ambas consultas (RN-8, RN-10)

### Escenario 13 (rechazos persistidos): Self-trade y sin-liquidez aparecen como REJECTED [AT-04-07-13]
- Dado un trader cuyas órdenes fueron rechazadas por la capa de matching: una por `SELF_TRADE_BLOCKED` y otra por `MARKET_NO_LIQUIDITY`
- Cuando consulta su historial (sin filtro, o con `status=REJECTED`)
- Entonces **ambas** aparecen con `status="REJECTED"`, preservando la trazabilidad de auditoría (RN-12, HU-04-05 RN-5, RE-12)

### Escenario 14 (rechazos no persistidos): Rechazos de validación/fondos no aparecen [AT-04-07-14]
- Dado un trader cuyos intentos fallaron por `INVALID_PRICE_TICK`, `BELOW_MIN_NOTIONAL` e `INSUFFICIENT_FUNDS`
- Cuando consulta su historial
- Entonces **ninguno** de esos intentos aparece como orden (no se persisten; RN-12, HU-04-05 RN-5, RE-12)

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-04-07-01 .. AT-04-07-14) pasan
- [ ] Reglas de negocio RN-1..RN-12 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md (`VALIDATION_ERROR`, `UNAUTHENTICATED`)
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md (montos string entero)
- [ ] Sin violacion de invariantes globales (consulta de solo lectura; órdenes terminales inmutables)
- [ ] (si aplica) Adherencia verificada al estandar on-chain citado — N/A
