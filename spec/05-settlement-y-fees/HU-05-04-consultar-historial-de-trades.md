# HU-05-04 — Consultar historial de trades

- **Epica:** 05 — Settlement y Fees
- **Actor / rol:** Trader autenticado (consulta sobre sus propios trades)
- **Prioridad:** Media
- **Dependencias:** HU-05-03 (registro de trades), HU-01-* (autenticación/autorización), HU-04-* (órdenes referenciadas), HU-09-* (contrato HTTP/paginación)
- **Estandares de dominio aplicables:** N/A (consulta sobre datos internos)

## Historia
Como **trader autenticado**, quiero **consultar el historial de mis trades/fills, viendo
para cada uno mi rol (maker/taker), mi lado (compra/venta), el precio, la cantidad, la fee
que pagué y el monto neto recibido**, para **auditar mis ejecuciones, conciliar mis
balances y entender el costo efectivo de mi operatoria**.

## Contexto y alcance
Esta HU define la **consulta del historial de trades desde la perspectiva del usuario
autenticado**. Un trade (HU-05-03) involucra dos cuentas; cada usuario ve **su propia
pata**: su rol (`MAKER`/`TAKER`), su lado (`BUY`/`SELL`), la fee que **él** pagó (en el
activo que recibió) y su monto neto. El historial es de **solo lectura**, paginable y
ordenable por recencia, y **solo expone los trades propios** (no los de otras cuentas ni la
identidad de la contraparte).

**No** cubre: la generación del registro (HU-05-03), el detalle de cómputo de fees
(HU-05-02), ni el contrato HTTP/WS exacto y la estrategia de paginación (épica 09; aquí se
fija la semántica, las unidades y los filtros mínimos). Supuesto: un trade donde el usuario
es comprador y otro donde es vendedor aparecen ambos en su historial, cada uno con la
perspectiva correcta.

## Reglas de negocio e invariantes

1. **RN-1 (autenticación obligatoria).** La consulta requiere credencial válida; sin ella se
   responde `UNAUTHENTICATED` (401). (HU-01-*)
2. **RN-2 (aislamiento por cuenta).** El usuario solo obtiene trades en los que su cuenta es
   `buyerAccountId` **o** `sellerAccountId`. Intentar consultar el historial de otra cuenta
   (p. ej. por `accountId` ajeno) responde `UNAUTHORIZED` (403). El historial nunca incluye
   trades ajenos.
3. **RN-3 (perspectiva del usuario por trade).** Cada entrada se proyecta desde la pata del
   usuario:
   - `role` = `buyerRole` si el usuario es comprador, `sellerRole` si es vendedor.
   - `side` = `BUY` si el usuario es comprador, `SELL` si es vendedor.
   - `feeAsset` y `feeAmount`: si el usuario es **comprador**, `feeAsset = ETH`, `feeAmount
     = feeBaseWei`; si es **vendedor**, `feeAsset = USDC`, `feeAmount = feeQuoteMin`.
   - `netReceived`: si comprador, ETH `= quantityWei − feeBaseWei`; si vendedor, USDC `=
     quoteAmountMin − feeQuoteMin`.
   - `paid` (lo entregado): si comprador, USDC `= quoteAmountMin`; si vendedor, ETH `=
     quantityWei`.
4. **RN-4 (campos de cada entrada).** Cada entrada incluye al menos: `tradeId`, `sequence`/
   `timestamp`, `pair` (`ETH/USDC`), `priceMin`, `quantityWei`, `quoteAmountMin`, `side`,
   `role`, `feeAsset`, `feeAmount`, `netReceived`, `paid`, y la referencia a la **orden
   propia** (`orderId`). **No** se expone la cuenta ni la orden de la contraparte
   (privacidad).
5. **RN-5 (orden determinista).** Por defecto, los resultados se devuelven **ordenados por
   recencia descendente** (`sequence`/`timestamp` de mayor a menor). El orden es estable y
   determinista ante empates (desempate por `sequence`).
6. **RN-6 (paginación cursor-based).** La paginación **DEBE ser cursor-based (keyset)**,
   usando `sequence` como **cursor opaco**; la paginación offset-based (`LIMIT/OFFSET`)
   **está prohibida** para el historial de trades porque no garantiza estabilidad ante
   inserciones concurrentes de nuevos trades (un nuevo trade insertado entre páginas
   desplazaría los registros y provocaría duplicados u omisiones).
   - **Patrón:** la primera página devuelve los trades más recientes (`ORDER BY sequence DESC
     LIMIT N`); las siguientes usan `cursor = sequence_del_último_trade_devuelto` con
     `WHERE sequence < cursor ORDER BY sequence DESC LIMIT N`.
   - **Tamaño de página:** por defecto `N = 50`, máximo `N = 200`. La épica 09 fija el
     contrato de wire exacto **dentro de estos límites** (HU-09-01 RN-20); el mecanismo
     cursor-based y la garantía de estabilidad son **normativos de esta épica**.
   - **Estabilidad real:** dos páginas consecutivas **no omiten ni duplican** entradas aunque
     se inserten nuevos trades entre páginas (los nuevos trades tienen `sequence` mayores y
     solo aparecerían "antes" del cursor, nunca desplazando los ya paginados).
7. **RN-7 (filtros mínimos).** Se admiten, al menos, filtros por rango temporal
   (`from`/`to`, timestamps **ISO-8601 UTC** — HU-09-01 RN-15/RN-20) y por `orderId`
   **propio** (todos los fills de una orden del usuario). Filtrar por un `orderId` que **no pertenece** a la cuenta autenticada (sea
   inexistente o de otra cuenta) devuelve una **lista vacía** — la **misma** respuesta que
   cualquier filtro sin coincidencias y que el historial vacío (RN-11) —, **nunca** un
   `ORDER_NOT_FOUND` ni la exposición de fills ajenos. (Responder `404` solo para órdenes
   ajenas revelaría su existencia —*order ID enumeration*—; y responderlo también para
   filtros vacíos sería incoherente con RN-11. La **lista vacía uniforme** es no-reveladora,
   coherente con RN-11 y produce un resultado esperado **único** y testeable.)
8. **RN-8 (consistencia con el registro y los balances).**
   - (a) **Verificable solo con datos de la épica 05:** los montos mostrados coinciden
     **exactamente** con el registro de HU-05-03; la suma de `netReceived` en ETH de todos
     los trades en los que el usuario es comprador reproduce el ETH total acreditado por
     settlement, y la suma de `paid` en USDC reproduce el USDC total debitado por esos fills
     (y simétricamente para la pata opuesta cuando el usuario es vendedor).
   - (b) **Dependiente de la épica 04 (nota, fuera del DoD de esta épica):** el cuadre
     **completo** del balance del usuario requiere además los bloqueos iniciales y las
     liberaciones por cancelación/mejora de precio de la épica 04 (INV-1/INV-3).
9. **RN-9 (solo lectura).** La consulta no modifica estado alguno; es idempotente y no
   altera balances, órdenes ni trades.
10. **RN-10 (serialización).** Todos los montos (`priceMin`, `quantityWei`,
    `quoteAmountMin`, `feeAmount`, `netReceived`, `paid`) se serializan como string entero de
    unidad mínima (`^(0|[1-9][0-9]*)$`); sin floats (convenciones §5).
11. **RN-11 (historial vacío).** Una cuenta sin trades devuelve una lista vacía (no es un
    error); con metadatos de paginación coherentes (p. ej. total 0).

## Criterios de aceptacion (DoD)

### Escenario 1: El usuario consulta su historial (perspectiva comprador taker) [AT-05-04-01]
- Dado un trader autenticado que fue **comprador taker** en un trade con `quantityWei =
  1000000000000000000`, `priceMin = 2000000000`, `quoteAmountMin = 2000000000`,
  `feeBaseWei = 2000000000000000`
- Cuando consulta su historial de trades
- Entonces la entrada muestra `side = "BUY"`, `role = "TAKER"`, `priceMin = "2000000000"`,
  `quantityWei = "1000000000000000000"`
- Y `feeAsset = "ETH"`, `feeAmount = "2000000000000000"`,
  `netReceived = "998000000000000000"` (ETH), `paid = "2000000000"` (USDC)
- Y la entrada referencia su propio `orderId`, sin exponer la contraparte

### Escenario 2: Misma cuenta, perspectiva vendedor maker [AT-05-04-02]
- Dado el mismo trader que en otro trade fue **vendedor maker** con `quantityWei =
  1000000000000000000`, `priceMin = 2000000000`, `quoteAmountMin = 2000000000`,
  `feeQuoteMin = 2000000`
- Cuando consulta su historial
- Entonces esa entrada muestra `side = "SELL"`, `role = "MAKER"`, `feeAsset = "USDC"`,
  `feeAmount = "2000000"`, `netReceived = "1998000000"` (USDC), `paid =
  "1000000000000000000"` (ETH)
- Y ambas entradas (esta y la de AT-05-04-01) aparecen en el mismo historial, cada una con
  su perspectiva

### Escenario 3 (orden y paginación cursor-based): recencia descendente y páginas estables [AT-05-04-03]
- Dado un trader con 3 trades de `sequence` `s1 < s2 < s3` y tamaño de página `N = 2`
- Cuando consulta la primera página (sin cursor)
- Entonces recibe `[s3, s2]` (recencia descendente) y un cursor `= s2`
- Cuando consulta la página siguiente con `cursor = s2`
  (`WHERE sequence < s2 ORDER BY sequence DESC LIMIT 2`)
- Entonces recibe `[s1]`, **sin** repetir ni omitir entradas respecto de la primera página
  (RN-6)
- Y si entre ambas consultas se inserta un nuevo trade `s4 > s3`, **no** aparece en la
  segunda página (su `sequence` es mayor que el cursor): la paginación permanece estable

### Escenario 4 (filtro): por `orderId` propio devuelve todos sus fills [AT-05-04-04]
- Dado un trader **comprador taker** cuya orden BUY `O-9` (0.9 ETH @ 2000.00) se ejecutó en
  3 fills parciales de `0.3 ETH` cada uno (3 trades), con `quoteAmountMin = 600000000` y
  `feeBaseWei = 600000000000000` por fill
- Cuando consulta el historial filtrando por `orderId = "O-9"`
- Entonces se devuelven exactamente esos 3 trades, todos con `orderId = "O-9"` en su pata,
  `side = "BUY"`, `role = "TAKER"`
- Y por trade `netReceived = "299400000000000000"` (ETH) y `paid = "600000000"` (USDC)
- Y la suma reproduce el efecto neto de la orden (RN-8a): `Σ netReceived =
  "898200000000000000"` (ETH recibido) y `Σ paid = "1800000000"` (USDC entregado)

### Escenario 5 (borde): historial vacío [AT-05-04-05]
- Dado un trader autenticado que nunca ejecutó un trade
- Cuando consulta su historial
- Entonces recibe una **lista vacía** (no un error) con metadatos de paginación coherentes
  (total 0) (RN-11)

### Escenario 6 (error): sin autenticación [AT-05-04-06]
- Dado un cliente sin credencial válida (token ausente o expirado)
- Cuando intenta consultar el historial de trades
- Entonces se rechaza con `UNAUTHENTICATED` (401) y no se devuelve dato alguno (RN-1)

### Escenario 7 (error): intento de ver trades de otra cuenta [AT-05-04-07]
- Dado un trader autenticado como cuenta A
- Cuando consulta el historial por el endpoint del contrato de la épica 09
  (`GET /api/v1/trades`, HU-09-01 RN-20), que **no** admite indicar otra cuenta en la ruta
- Entonces el aislamiento es **por diseño**: la respuesta contiene solo la pata propia de A
  (RN-2) y no existe forma de solicitar el historial de la cuenta B
- Y si una implementación expusiera además un endpoint con `accountId` en la ruta (fuera
  del contrato), pedir la cuenta B ajena con credencial de A se rechaza con `UNAUTHORIZED`
  (403) sin filtrar ninguna entrada de B (RN-2)

### Escenario 8 (filtro): `orderId` ajeno o inexistente devuelve lista vacía [AT-05-04-08]
- Dado un trader autenticado como cuenta A y un `orderId` que **no** pertenece a A (de la
  cuenta B, o inexistente)
- Cuando filtra su historial por ese `orderId`
- Entonces se devuelve una **lista vacía** (no un error), **idéntica** a cualquier filtro sin
  coincidencias y al historial vacío (RN-11), **sin** exponer ningún fill de B ni revelar si
  el `orderId` existe (RN-7)

### Escenario 9 (serialización): montos como string entero [AT-05-04-09]
- Dado cualquier entrada del historial
- Cuando se serializa la respuesta
- Entonces todos los montos viajan como string que matchea `^(0|[1-9][0-9]*)$`, nunca como
  número JSON, decimal ni notación científica (RN-10)
- Y `feeAsset` ∈ {`ETH`, `USDC`}, `side` ∈ {`BUY`, `SELL`}, `role` ∈ {`MAKER`, `TAKER`}

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptacion (AT-05-04-01 .. AT-05-04-09) pasan
- [ ] Reglas de negocio RN-1..RN-11 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md (UNAUTHENTICATED,
      UNAUTHORIZED; el filtro por `orderId` ajeno/inexistente devuelve lista vacía, no error)
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md), en
      particular consistencia con INV-1/INV-3 (conciliación con balances)
- [ ] (si aplica) Adherencia verificada al estandar on-chain citado — N/A (consulta interna)
