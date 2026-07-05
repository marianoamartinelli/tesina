# Glosario de términos de dominio

Vocabulario común a toda la especificación. Los términos técnicos se mantienen en su
**forma original** (inglés) cuando es el uso convencional del dominio. Este glosario es la
**referencia única**: si una HU usa un término aquí definido, se interpreta según esta
definición.

> Convención de unidades: en este glosario "unidad mínima" significa **wei** para ETH
> (10⁻¹⁸ ETH) y **unidad de 6 decimales** para USDC (10⁻⁶ USDC). Ver
> `convenciones-monetarias.md`.

---

## Trading y libro de órdenes

- **Par de trading (trading pair):** las dos monedas que se intercambian. En este
  proyecto, el par único es **ETH/USDC-mock**. La primera moneda es la **base**, la
  segunda es la **quote**. Identificadores canónicos del par (ambos denotan el único par
  del sistema; `USDC` denota el activo subyacente USDC-mock):
  - En el **registro interno de trades y los eventos del motor** (épicas 03/05), el campo
    `pair` toma el string **`ETH/USDC`**.
  - En la **superficie de la API HTTP/WebSocket** (épica 09), el par se identifica con el
    campo `symbol` y el string **`ETH-USDC`**.
  - En la **UI** (épicas 10/11), se muestra el texto `ETH/USDC`.

- **Base (base asset):** activo que se compra o vende. Aquí: **ETH**. Las cantidades de
  una orden (`quantity`) se expresan en la base.

- **Quote (quote asset):** activo en el que se denomina el precio. Aquí: **USDC-mock**.
  El precio se expresa en quote por unidad de base (USDC por ETH).

- **Orderbook (libro de órdenes):** estructura que contiene todas las órdenes limit
  abiertas (no ejecutadas totalmente ni canceladas), separadas en dos lados (bids y asks)
  y ordenadas por prioridad precio-tiempo. Es **persistente**: sobrevive a reinicios.

- **Bid:** orden de **compra** (el comprador "puja" por la base). El mejor bid es el de
  **precio más alto**.

- **Ask (u offer):** orden de **venta**. El mejor ask es el de **precio más bajo**.

- **Best bid / best ask (top of book):** la mejor oferta de compra y de venta
  disponibles en cada lado del libro.

- **Spread:** diferencia `best_ask − best_bid`. Si no hay órdenes en algún lado, el
  spread es indefinido. Un spread negativo no puede persistir: implica que hay órdenes
  cruzadas que deben matchear.

- **Profundidad (depth):** cantidad acumulada disponible a cada nivel de precio del
  orderbook.

- **Nivel de precio (price level):** conjunto de órdenes con el mismo precio en un lado
  del libro; dentro del nivel rige la prioridad temporal (FIFO por `seq`, ver "Prioridad
  precio-tiempo").

---

## Órdenes

- **Orden limit:** orden con **precio límite** explícito. Una compra limit se ejecuta a
  un precio **≤** al límite; una venta limit a un precio **≥** al límite. Si no matchea
  totalmente, el remanente queda en el orderbook.

- **Orden market:** orden **sin precio**, que se ejecuta contra el mejor precio
  disponible del lado opuesto hasta completar la cantidad o agotar la liquidez. No queda
  en el orderbook (el remanente no ejecutado se descarta/cancela según las reglas de la
  épica de matching).

- **Lado (side):** `BUY` (compra) o `SELL` (venta).

- **Maker:** orden (o parte de orden) que **provee liquidez**: estaba en el orderbook y es
  matcheada por una orden entrante. Paga la **fee maker**.

- **Taker:** orden (o parte de orden) que **consume liquidez**: cruza contra órdenes ya
  existentes en el libro al entrar. Paga la **fee taker**. Una orden market siempre es
  taker.

- **Prioridad precio-tiempo (price-time priority):** regla de ordenamiento del matching.
  Primero se atiende la mejor prioridad de **precio** (bid más alto / ask más bajo); a
  igual precio, se atiende primero la orden con **menor secuencia de ingreso (`seq`)**: un
  entero estrictamente monótono y único que el motor asigna a cada orden en el instante en
  que se vuelve pasiva (se posa en el libro). La **secuencia (`seq`) —no el timestamp de
  reloj de pared— es el desempate determinista**, porque dos órdenes pueden compartir
  timestamp pero nunca `seq`. El timestamp de pared puede existir como dato informativo de
  la orden, pero no es clave de prioridad.

- **Fill (ejecución):** evento en el que dos órdenes (una maker, una taker) se cruzan e
  intercambian una cantidad a un precio. Genera el settlement correspondiente.

- **Fill total:** la orden se ejecuta por su cantidad completa y deja de estar abierta.

- **Fill parcial:** la orden se ejecuta por una parte de su cantidad; el remanente sigue
  abierto (en el caso limit) o se descarta (caso market).

- **Estado de orden (order status):** situación en el ciclo de vida. Conjunto de estados
  de referencia: `OPEN` (abierta, sin ejecutar), `PARTIALLY_FILLED` (con fills
  parciales; para `LIMIT` es un estado **abierto**), `FILLED` (ejecutada totalmente),
  `CANCELLED` (cancelada por el usuario, o remanente `MARKET` descartado por liquidez o
  presupuesto agotados — estado terminal de una `MARKET` con fill parcial), `REJECTED`
  (rechazada en validación o por el matching, nunca ingresó al libro).

- **Self-trade:** situación en la que la misma cuenta sería simultáneamente maker y taker
  de un mismo fill. Está **bloqueada** (ver `SELF_TRADE_BLOCKED`).

---

## Balances, ledger y settlement

- **Balance disponible (available):** fondos que la cuenta puede usar libremente (operar,
  retirar). Disminuye al bloquear fondos para una orden o un retiro.

- **Balance bloqueado (locked / on-hold):** fondos reservados por órdenes abiertas o
  retiros en proceso. No se pueden usar para otra cosa hasta que se liberen o se
  consuman.

- **Balance total:** `disponible + bloqueado` por activo. Invariante:
  `disponible ≥ 0`, `bloqueado ≥ 0` y `total = disponible + bloqueado`.

- **Settlement (liquidación interna):** aplicación contable de un fill: debitar/acreditar
  base y quote a maker y taker, y cobrar las fees. Es **atómico**: ocurre por completo o
  no ocurre (ver invariantes).

- **Ledger (libro mayor):** registro inmutable y auditable de todos los movimientos
  internos de fondos (depósitos, bloqueos, settlements, fees, retiros). Permite
  reconstruir cualquier balance sumando sus asientos. Usa **doble entrada** (todo
  movimiento tiene contrapartida).

- **Fee:** comisión que cobra el exchange por un fill. Se distingue **fee maker** y **fee
  taker** (esta última usualmente mayor). Se expresa en **basis points (bps)**:
  1 bps = 0.01% = 1/10000.

- **Cuenta de fees del exchange:** cuenta interna donde se acumulan las fees cobradas. Su
  identificador en el sistema es **`EX`**. No pertenece a ningún usuario y entra en la
  conservación de fondos (INV-1).

- **Notional:** valor de una orden o fill expresado en la quote:
  `notional = quantity_base × price` (en USDC). Se usa para el mínimo notional.

---

## On-chain / wallet

- **HD wallet (Hierarchical Deterministic wallet):** wallet jerárquica determinística
  (BIP-32) de la que se derivan múltiples pares de claves a partir de una única semilla.

- **Seed / mnemonic:** frase mnemónica (BIP-39, típicamente 12 o 24 palabras) que codifica
  la entropía de la que se deriva la **seed** binaria, raíz de toda la HD wallet. Es el
  secreto maestro: quien la posee controla todos los fondos derivados.

- **Derivation path (ruta de derivación):** ruta jerárquica que identifica una clave
  dentro de la HD wallet, según BIP-44:
  `m / 44' / coin_type' / account' / change / address_index`.
  Para Ethereum, `coin_type = 60`.

- **Coin type:** índice de moneda del estándar SLIP-44 / BIP-44. **Ethereum = 60**.

- **Dirección (address):** dirección Ethereum (20 bytes, representada como `0x` + 40
  caracteres hexadecimales, con checksum EIP-55). Identifica una cuenta on-chain.

- **Depósito:** transferencia on-chain entrante (ETH o el ERC-20 USDC-mock) hacia una
  dirección controlada por el exchange y asignada a una cuenta de usuario. Una vez
  **confirmada**, se acredita al balance interno disponible.

- **Retiro (withdrawal):** envío on-chain de fondos del exchange hacia una dirección
  externa indicada por el usuario. Implica firmar y broadcastear una transacción.

- **Confirmación (confirmation):** cada bloque minado **encima** del bloque que incluye
  una transacción. Un depósito se considera confirmado cuando alcanza el número de
  confirmaciones requerido (ver `activos-y-par-de-trading.md` /
  `07-depositos-on-chain`).

- **Reorg (reorganización de cadena):** evento en que la cadena canónica cambia y bloques
  previamente vistos quedan huérfanos. Puede revertir transacciones ya observadas; por
  eso se exigen N confirmaciones antes de acreditar.

- **Nonce:** contador secuencial de transacciones **por dirección emisora** en Ethereum.
  Cada transacción saliente usa el siguiente nonce; evita doble gasto y replay, y fija el
  orden de inclusión.

- **Gas:** unidad de costo de cómputo on-chain. Una transacción paga
  `gas_usado × precio_de_gas` en ETH al validador. Afecta los retiros (el exchange paga
  el gas).

- **chainId:** identificador numérico de la red Ethereum. **Sepolia = 11155111**. Forma
  parte de la firma EIP-155.

- **EIP-155:** estándar de firma de transacciones que incluye el `chainId` en los datos
  firmados, evitando **replay** de una transacción de una red en otra.

- **EIP-55:** estándar de checksum de direcciones Ethereum mediante mayúsculas/minúsculas
  en los caracteres hexadecimales. Permite detectar direcciones mal tipeadas.

- **BIP-32 / BIP-39 / BIP-44:** estándares de wallets jerárquicas determinísticas (BIP-32),
  frases mnemónicas (BIP-39) y estructura de rutas de derivación multi-cuenta (BIP-44).

- **ERC-20:** estándar de tokens fungibles en Ethereum (interfaz `transfer`,
  `balanceOf`, `Transfer`, etc.). USDC-mock es un ERC-20 con 6 decimales.

- **Testnet / Sepolia:** red de pruebas de Ethereum. Sepolia es la red única usada en
  este proyecto; sus monedas no tienen valor económico real.

---

## Identificadores y serialización

- **Unidad mínima (minor unit):** entero indivisible de un activo. ETH: **wei**
  (1 ETH = 10¹⁸ wei). USDC-mock: **unidad de 6 decimales** (1 USDC = 10⁶ unidades).

- **Monto serializado:** en la API, todo monto/precio se transmite como **string de un
  entero** en unidades mínimas (p. ej. `"1500000000"` = 1500 USDC). Nunca como número
  decimal de punto flotante. Ver `convenciones-monetarias.md`.

- **tradeId:** identificador único e inmutable de un fill liquidado (un fill ⇒ un trade).
  Sirve como **clave de idempotencia** del settlement. Formato: string `"T-" + sequence`,
  donde `sequence` es el **número de trade**: un entero global estrictamente creciente
  (desde 1) asignado en orden de producción de fills por el motor de matching
  (`05-settlement-y-fees`, HU-05-03 RN-3). Es un contador **propio de los trades**,
  independiente de la numeración de eventos del motor (HU-03-05) y de las secuencias por
  canal de la API (épica 09, RG-API-7). Bajo operación normal es contiguo; puede quedar un
  hueco si el settlement de un fill se revierte. Se persiste junto al ledger
  (reconstruible tras reinicio) y **nunca** se reutiliza.

- **AT-id:** identificador de un test de aceptación (`AT-<epica>-<huSeq>-<NN>`), unidad de
  trazabilidad de la evaluación. Ver `README.md`.
