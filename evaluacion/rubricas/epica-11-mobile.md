# Rúbrica manual — Épica 11: Cliente Mobile (React Native / Expo) — v1.0

- **Cobertura:** 94 AT (HU-11-01: 14 · HU-11-02: 10 · HU-11-03: 18 · HU-11-04: 14 ·
  HU-11-05: 12 · HU-11-06: 26).
- **Estado:** pre-registrada en H5, antes de la primera corrida (protocolo §9: la rúbrica
  no se modifica después de vista ninguna implementación).
- **Rol:** las épicas 10 y 11 se evalúan con rúbrica manual (no black-box automatizado).
  Esta rúbrica es el instrumento único para la épica 11.

## Precondiciones

1. **Backend de la corrida corriendo** (implementación de la celda, épicas 01–09),
   accesible desde el dispositivo/emulador (misma red o túnel). Si el backend no arranca,
   **todos** los AT se marcan `NO_EVALUABLE` con nota global.
2. **App mobile de la corrida** ejecutando en **emulador Android o simulador iOS + un
   dispositivo físico si el AT requiere cámara real** (Expo Go o build de desarrollo). Si
   la app no compila ni renderiza el login, todos los AT se marcan `FALLA` con nota global.
3. **Datos de prueba (seed):** los mismos que la rúbrica web (`epica-10-web.md`):
   usuario evaluador (10 ETH / 100000 USDC), usuario contraparte operado desde el cliente
   web o por API para generar liquidez/fills/carreras, y una cuenta virgen.
4. **Herramientas permitidas** (y ninguna otra):
   - Ciclo de vida: app switcher / botón home para background–foreground (≥ **60 s** en
     background para los AT de ciclo de vida, RG-11: umbral en dispositivo real; los mocks
     `simulateDisconnect()` son para los tests propios de la implementación, no para esta
     rúbrica), y task-kill (cerrar la app desde el switcher) para los AT de crash.
   - Red: modo avión del dispositivo/emulador, apagar el backend, apagar el nodo RPC.
   - Proxy interceptor (mitmproxy con el dispositivo apuntado a él) para inspeccionar
     payloads y adulterar datos cuando el AT exige datos que el backend sano no produce.
   - Logs de Metro/Expo y del backend; lector/generador de QR externo para preparar y
     decodificar QRs de prueba (dirección plana, EIP-681 Sepolia, EIP-681 mainnet,
     contenido basura).
   - Script auxiliar contra la API pública del backend para seed masivo.
5. **AT de instrumentación** (definidos en la spec con spies/mocks: AT-11-01-08,
   AT-11-01-11, AT-11-01-13, AT-11-01-14, AT-11-06-17): la evidencia admitida en esta
   rúbrica manual es (i) los **tests propios de la implementación** si existen y cubren
   exactamente esa aserción (ejecutarlos y citar el archivo), y/o (ii) **inspección
   dirigida del código fuente** del cliente + observación de logs. Si ninguna evidencia es
   concluyente → `NO_EVALUABLE` (b) con nota.
6. La suite black-box de las épicas 01–09 no se corre durante esta rúbrica (protocolo §4).

## Procedimiento general

- Se completa **una sola vez por corrida, en H8**, por el **mismo evaluador** (el tesista)
  en las 4 corridas oficiales y la piloto, recorriendo las filas **en el orden de este
  documento** (HU-11-01 → HU-11-06, AT ascendente).
- Veredictos por fila (exactamente uno): **PASA** (todo lo listado se observó), **FALLA**
  (la condición se provocó y algo no se cumple), **NO_EVALUABLE** con causa: **(a)** el
  comportamiento del backend del que depende el AT no existe o falla — ya lo captura la
  suite black-box de 01–09 y **no se penaliza dos veces**; **(b)** la condición no es
  provocable con las herramientas permitidas. Nota obligatoria en `FALLA` y `NO_EVALUABLE`.
- **Agregación pre-registrada:** tasa de la épica = `PASA / (PASA + FALLA)`;
  `NO_EVALUABLE` fuera del denominador, reportado aparte por causa (a/b) en
  `runs/<id>/metricas.md`.
- Verificaciones de **payload** se comprueban en el proxy o en el log del backend. La
  ausencia de floats se juzga por su **resultado observable** (valores exactos); la
  inspección de código es complementaria.
- Tiempo máximo por fila: **10 minutos** de intento; superado → `NO_EVALUABLE` (b).

---

## HU-11-01 — Inicio de sesión y persistencia segura del token

| AT | Verificación manual (preparar → ejecutar → verificar) | Resultado | Notas |
|----|-------------------------------------------------------|-----------|-------|
| AT-11-01-01 | Login con credenciales válidas. Verificar: navega a la vista autenticada; el token se persistió en el almacén **cifrado** (evidencia: restauración en cold start del AT-11-01-02 + inspección de código: el token va a SecureStore/Keychain y la password no se escribe en ningún almacenamiento). | | |
| AT-11-01-02 | Con token persistido válido, cerrar la app por completo (task-kill) y reabrir (cold start). Verificar: entra directo a la vista autenticada sin pedir credenciales y **sin** llamada previa de validación al backend (log del backend/proxy: ninguna petición de validación antes de navegar — restauración optimista). | | |
| AT-11-01-03 | Tras logout (o instalación limpia), abrir la app. Verificar: muestra login y no llama a ningún endpoint autenticado (log del backend limpio). | | |
| AT-11-01-04 | Enviar credenciales incorrectas (`INVALID_CREDENTIALS` 401). Verificar: mensaje que no revela si el email existe, no se persiste token (cold start posterior vuelve a login), permanece en login para reintentar. | | |
| AT-11-01-05 | Con sesión activa, invalidar el token del lado servidor (revocar/reiniciar backend) y ejecutar una acción autenticada. Verificar: al 401 borra el token persistido y el estado, y redirige al login. | | |
| AT-11-01-06 | Ejecutar logout. Verificar: vuelve al login; reabrir la app (cold start) NO restaura la sesión (pide credenciales). | | |
| AT-11-01-07 | Dejar email o password vacíos (y luego email con formato inválido) e intentar enviar. Verificar: la UI bloquea el envío con mensaje local y no realiza la petición (log del backend limpio). | | |
| AT-11-01-08 | Instrumentación (precondición 5): verificar que el token sólo va al almacén cifrado. Evidencia: tests propios con spies sobre `SecureStore.setItemAsync` / `AsyncStorage.setItem`, o inspección de código: el token se escribe únicamente vía SecureStore/Keychain; ningún `AsyncStorage.setItem` (u otro almacén en claro) recibe token o password. No concluyente → NO_EVALUABLE (b). | | |
| AT-11-01-09 | En modo avión (o backend caído), enviar credenciales válidas. Verificar: error de **conectividad** (mensaje distinto al de credenciales inválidas), no se persiste token, se permite reintentar. | | |
| AT-11-01-10 | Con sesión activa y token válido, mandar la app a background ≥60 s y volver. Verificar: la sesión se mantiene sin re-autenticación. (La rama "token expirado en el ínterin" se cubre en AT-11-01-12.) | | |
| AT-11-01-11 | Instrumentación (precondición 5): durante un login y navegación posterior, capturar los logs (Metro/console). Verificar: ninguna línea contiene el valor del token ni la password (buscar los valores literales); inspección de código de los puntos de logging como evidencia complementaria. No concluyente → NO_EVALUABLE (b). | | |
| AT-11-01-12 | Con la app en background ≥60 s, invalidar el token en el servidor; volver a foreground (la app reconecta el WS y el handshake/eventos devuelven `UNAUTHENTICATED`). Verificar: limpia la sesión y redirige al login **una sola vez** (sin pantallas de login duplicadas ni navegaciones múltiples), aunque coincidan 401 de REST y WS. | | |
| AT-11-01-13 | Fallo de lectura del almacén seguro (Before First Unlock) — no provocable de forma confiable en emulador. Evidencia: tests propios que simulen la excepción de SecureStore, o inspección de código: la lectura está envuelta en manejo de error que degrada a "sin token" (muestra login) sin loggear datos sensibles ni exponer el error interno. No concluyente → NO_EVALUABLE (b). | | |
| AT-11-01-14 | Con varias pantallas/peticiones autenticadas activas (balances + órdenes + market data), invalidar el token y provocar peticiones concurrentes (p. ej. volver a foreground con reconexión). Verificar: el logout se ejecuta **una sola vez** — una única navegación al login, sin dobles borrados/redirecciones (complementar con inspección del código: flag atómico o promesa singleton, RG-8). | | |

## HU-11-02 — Vista de trading

Seed previo del bloque: igual que en la rúbrica web (≥3 niveles por lado, ≥3 trades).

| AT | Verificación manual (preparar → ejecutar → verificar) | Resultado | Notas |
|----|-------------------------------------------------------|-----------|-------|
| AT-11-02-01 | Abrir la vista de trading. Verificar: bids por precio descendente, asks ascendente; best bid/ask y spread = resta entera exacta; precios/cantidades formateados a humano sin residuos de float. | | |
| AT-11-02-02 | Desde la contraparte, modificar la cantidad de un nivel. Verificar: la vista actualiza ese nivel sin recargar, conserva el orden y recalcula best bid/ask y spread. | | |
| AT-11-02-03 | Con la lista de trades en 50 entradas (seed por script), generar un trade nuevo. Verificar: aparece al tope (cronológico descendente), la lista mantiene **exactamente 50** (se descarta el más antiguo), montos con precio a 2 decimales y cantidad a 4. | | |
| AT-11-02-04 | Vaciar un lado del libro (cancelar todos los asks). Verificar: spread mostrado como "—", la vista no se rompe ni inventa valores. | | |
| AT-11-02-05 | Seedear un nivel con `5` ETH (`5000000000000000000` wei > 2⁵³). Verificar: se muestra exactamente `5.0000` (4 decimales), sin pérdida de precisión. | | |
| AT-11-02-06 | Con la vista suscrita, mandar la app a background ≥60 s (la conexión se cierra) y volver a foreground; mientras estaba en background, cambiar el libro desde la contraparte. Verificar: al volver reconecta, pide snapshot fresco (log del backend/proxy) y muestra el estado actualizado antes de aplicar deltas. | | |
| AT-11-02-07 | Con el stream activo, apagar el backend. Verificar: indicador "reconectando" y reintentos; al levantar el backend, solicita snapshot y vuelve a "en vivo". | | |
| AT-11-02-08 | Con el proxy, inyectar un delta con `sequence = s + 2` (hueco) en el mismo canal. Verificar: descarta el delta, re-solicita snapshot y reemplaza el estado local antes de seguir aplicando deltas. Sin proxy → NO_EVALUABLE (b). | | |
| AT-11-02-09 | Hacer pull-to-refresh en la vista. Verificar: se solicita un snapshot fresco (log/proxy) y la vista se actualiza. | | |
| AT-11-02-10 | Seedear un nivel `price_min = 2000500000`, `q_wei = 100000000000000`. Verificar: precio mostrado `2000.50` (exactamente 2 decimales) y cantidad `0.0001` (exactamente 4); nunca más decimales que tick (2) y lot (4). | | |

## HU-11-03 — Formulario de orden

| AT | Verificación manual (preparar → ejecutar → verificar) | Resultado | Notas |
|----|-------------------------------------------------------|-----------|-------|
| AT-11-03-01 | LIMIT BUY `0.005` ETH @`2000.00`, confirmar el envío (paso de confirmación). Verificar: la UI muestra `OPEN` y montos formateados exactos. | | |
| AT-11-03-02 | Con liquidez del lado opuesto (contraparte), enviar una LIMIT que cruce el spread. Verificar: muestra el estado devuelto (`FILLED`/`PARTIALLY_FILLED`) y los fills (cantidad/precio/notional) formateados exactos. | | |
| AT-11-03-03 | Con liquidez opuesta, enviar MARKET SELL y confirmar. Verificar: se ejecuta contra los mejores precios, la UI refleja los fills y el payload **no** contiene campo `price` (proxy/log del backend). | | |
| AT-11-03-04 | Ingresar precio `2000.005` (3 decimales). Verificar: el cliente bloquea con feedback de tick inválido; si el payload se fuerza al backend (proxy), responde `INVALID_PRICE_TICK` y la UI lo muestra. | | |
| AT-11-03-05 | Ingresar cantidad `0.00005` (5 decimales). Verificar: bloqueo con feedback de lot inválido; forzado al backend, `INVALID_LOT_SIZE` mostrado. | | |
| AT-11-03-06 | LIMIT `0.0001` ETH @`2000.00` (notional 0.2 USDC). Verificar: el cliente la marca por debajo del mínimo notional; forzada al backend, `BELOW_MIN_NOTIONAL` mostrado. | | |
| AT-11-03-07 | LIMIT sin precio. Verificar: si el cliente bloquea, lo hace con feedback de precio requerido; si el payload llega al backend (proxy), responde `PRICE_REQUIRED` (422) y la UI lo informa. FALLA si el envío sale sin precio y el error no se muestra. | | |
| AT-11-03-08 | MARKET con precio en el payload (requiere proxy: el campo debería estar deshabilitado). Verificar: el backend responde `PRICE_NOT_ALLOWED` (422) y la UI lo informa; sin proxy, verificar al menos que el campo está deshabilitado/ausente y anotar. Sin proxy → NO_EVALUABLE (b) para la rama 422. | | |
| AT-11-03-09 | Orden que excede el disponible; backend responde `INSUFFICIENT_FUNDS` (422). Verificar: la UI muestra `asset`, `required` y `available` de `details` formateados a humano. | | |
| AT-11-03-10 | Lado opuesto vacío + MARKET. Verificar: el backend responde `MARKET_NO_LIQUIDITY` (422) y la UI informa la falta de liquidez. | | |
| AT-11-03-11 | Reenviar un alta ya aceptada con el mismo `clientOrderId` (retener la respuesta con el proxy y reintentar, o replay del request). Verificar: `DUPLICATE_CLIENT_ORDER_ID` (409) tratado como "ya enviada", sin segunda orden (el listado muestra una sola). No provocable → NO_EVALUABLE (b). | | |
| AT-11-03-12 | Doble tap rápido en "Enviar" (con red lenta o proxy retardando). Verificar: un único request (log del backend) y una sola orden creada; botón deshabilitado durante el vuelo. | | |
| AT-11-03-13 | Con una orden propia en libro, enviar la orden que cruzaría contra ella. Verificar: `SELF_TRADE_BLOCKED` (422) con `details.restingOrderId`; la UI lo informa y la orden no se aplica. | | |
| AT-11-03-14 | Ingresar cantidad `0.0001` y precio `2000.50` y enviar. Verificar en el payload: `quantityWei="100000000000000"` y `priceMin="2000500000"` como strings exactos. | | |
| AT-11-03-15 | Invalidar el token y enviar una orden. Verificar: al 401 la app limpia la sesión y redirige al login (flujo de HU-11-01). | | |
| AT-11-03-16 | Provocar `RATE_LIMITED` (429) enviando altas en ráfaga (script con el mismo usuario si hace falta). Verificar: mensaje de límite de tasa con `retryAfterSeconds`, el formulario permanece editable (la orden no se descarta) y el reintento reusa el **mismo** `clientOrderId` (proxy). Backend sin rate limit → NO_EVALUABLE (a). | | |
| AT-11-03-17 | En modo avión (o backend caído), enviar una orden. Verificar: error de **conectividad** (distinto de los de negocio), el estado local no cambia, y el reintento reusa el **mismo** `clientOrderId` (proxy al restaurar la red). | | |
| AT-11-03-18 | Enviar una orden con la respuesta retenida (proxy) y hacer task-kill de la app antes de que llegue; reabrir. Verificar: la app detecta el *order intent* `pendiente` persistido y consulta/reintenta con el **mismo** `clientOrderId`; si ya estaba aceptada, trata el 409 `DUPLICATE_CLIENT_ORDER_ID` como "ya enviada" y limpia el registro. No provocable → NO_EVALUABLE (b). | | |

## HU-11-04 — Órdenes abiertas e historial

| AT | Verificación manual (preparar → ejecutar → verificar) | Resultado | Notas |
|----|-------------------------------------------------------|-----------|-------|
| AT-11-04-01 | Seed: órdenes `OPEN` y `PARTIALLY_FILLED` propias. Abrir la pantalla de órdenes. Verificar: lista las abiertas con id, side, type, price, cantidad, ejecutado/remanente y estado; montos formateados exactos. | | |
| AT-11-04-02 | Cancelar una orden `OPEN` (con su confirmación). Verificar: pasa a `CANCELLED`, desaparece de "abiertas" y aparece en "historial". | | |
| AT-11-04-03 | Con una `OPEN` visible, generar un fill parcial desde la contraparte. Verificar: la fila pasa a `PARTIALLY_FILLED` y actualiza el remanente en vivo, sin recargar. | | |
| AT-11-04-04 | Completar esa orden desde la contraparte. Verificar: pasa a `FILLED` y se mueve de abiertas a historial. | | |
| AT-11-04-05 | Seed: más órdenes terminadas que una página (script). Hacer scroll al final o "cargar más". Verificar: solicita la página siguiente y la anexa en orden cronológico descendente. | | |
| AT-11-04-06 | Carrera: congelar la vista (modo avión breve o proxy bloqueando WS) mientras la contraparte llena una orden visible; intentar cancelarla. Verificar: `ORDER_NOT_CANCELLABLE` (409) con `details {orderId, status}` y la UI muestra que ya no es cancelable. | | |
| AT-11-04-07 | Con el proxy, reescribir el `orderId` de una cancelación por uno inexistente. Verificar: `ORDER_NOT_FOUND` (404) con `details {orderId}` (misma respuesta que para una orden ajena) y la UI lo informa por su `code`. Sin proxy → NO_EVALUABLE (b). | | |
| AT-11-04-08 | Doble cancelación: cancelar la misma orden desde dos sesiones (mobile + web con la misma cuenta, la segunda con la vista congelada). Verificar: la segunda recibe `ORDER_NOT_CANCELLABLE` y la UI mantiene `CANCELLED` como estado final, sin presentarlo como fallo duro. | | |
| AT-11-04-09 | Doble tap rápido en "cancelar" (red lenta/proxy retardando). Verificar: un único request de cancelación (log del backend). | | |
| AT-11-04-10 | Con la pantalla abierta, background ≥60 s; mientras tanto, cambiar el estado de una orden desde la contraparte; volver a foreground. Verificar: re-sincroniza (refetch + re-suscripción, visible en el log del backend) y muestra el estado actual. | | |
| AT-11-04-11 | Pull-to-refresh en la pantalla de órdenes. Verificar: recarga las órdenes abiertas y la primera página del historial (dos requests en el log). | | |
| AT-11-04-12 | Invalidar el token y disparar un listado o cancelación. Verificar: al 401 limpia la sesión y redirige al login. | | |
| AT-11-04-13 | En modo avión (o backend caído), intentar cancelar una orden cancelable. Verificar: error de conectividad (distinto de los de negocio), la orden NO se marca cancelada localmente, y se puede reintentar al volver la red. | | |
| AT-11-04-14 | Con la pantalla mobile abierta, crear una orden nueva (u operar una no listada) desde **otra sesión** (web/API, misma cuenta). Verificar: al llegar el evento WS de un `orderId` no listado, el cliente no lo ignora: dispara un refetch de abiertas y la orden aparece; para terminales no visibles, el historial se actualiza en el próximo pull-to-refresh o resync por foreground. | | |

## HU-11-05 — Balances

| AT | Verificación manual (preparar → ejecutar → verificar) | Resultado | Notas |
|----|-------------------------------------------------------|-----------|-------|
| AT-11-05-01 | Abrir la pantalla de balances con fondos en ETH y USDC. Verificar: por activo se ven `disponible`, `bloqueado` y `total`, formateados exactos sin floats. | | |
| AT-11-05-02 | Llevar USDC a `disponible = 1500` / `bloqueado = 500` (orden que bloquee 500 USDC). Verificar: `total` mostrado equivale exactamente a `2000` USDC (suma entera; INV-3). | | |
| AT-11-05-03 | Con la pantalla visible, crear (desde el formulario o desde otra sesión de la misma cuenta) una orden que bloquee fondos. Verificar: `disponible` baja y `bloqueado` sube por el evento WS, con `total` constante. | | |
| AT-11-05-04 | Cancelar esa orden (HU-11-04). Verificar: `bloqueado` baja y `disponible` sube en vivo, `total` constante. | | |
| AT-11-05-05 | Acreditar un depósito (12 confirmaciones, según el entorno de la corrida). Verificar: el `disponible` del activo aumenta por el monto acreditado al llegar el evento. Entorno on-chain no operable → NO_EVALUABLE. | | |
| AT-11-05-06 | Con balance ETH de `12` ETH (`12000000000000000000` wei > 2⁵³). Verificar: se muestra el valor humano exacto (`12` / `12.0…`), sin pérdida por punto flotante. | | |
| AT-11-05-07 | Pull-to-refresh en balances. Verificar: refetch del GET de balances (log del backend) y vista actualizada. | | |
| AT-11-05-08 | Con la pantalla de balances, background ≥60 s; cambiar los balances desde otra sesión; volver a foreground. Verificar: re-sincroniza (refetch + re-suscripción WS) y muestra el estado actual. | | |
| AT-11-05-09 | Invalidar el token y disparar el GET de balances. Verificar: al 401 limpia la sesión y redirige al login. | | |
| AT-11-05-10 | Con la cuenta virgen (o un activo en 0). Verificar: se muestra `0` formateado correctamente, sin valores inválidos ni negativos. | | |
| AT-11-05-11 | En modo avión (o backend caído), abrir/refrescar balances. Verificar: error de conectividad (distinto de los de negocio), conserva el último estado conocido sin inventar valores, y permite reintentar con pull-to-refresh. | | |
| AT-11-05-12 | Con `bloqueado > 0` por una orden abierta y/o un retiro en proceso. Verificar: si la API expone el desglose (`lockedByOrders`/`lockedByWithdrawals`), la vista muestra ambos componentes; si no, muestra un texto/ícono informativo indicando que el bloqueado puede incluir órdenes y retiros. | | |

## HU-11-06 — Depósitos y retiros

QRs de prueba a preparar de antemano: (Q1) address plano EIP-55 válido; (Q2) URI EIP-681
`ethereum:<addr>@11155111`; (Q3) URI EIP-681 mainnet `ethereum:<addr>@1`; (Q4) contenido
basura (URL/texto). El escaneo se hace con dispositivo físico o cámara simulada del
emulador.

| AT | Verificación manual (preparar → ejecutar → verificar) | Resultado | Notas |
|----|-------------------------------------------------------|-----------|-------|
| AT-11-06-01 | Abrir la pantalla de depósito. Verificar: dirección `0x` + 40 hex con checksum EIP-55 válido (recomputar con herramienta externa), **QR** visible, acción de copiar funcional (pegar y comparar), y aclaración de red Sepolia (11155111) y activo. | | |
| AT-11-06-02 | Provocar un depósito entrante (según entorno). Verificar: figura **pendiente** con `X/12` actualizado por polling (~15 s) y/o pull-to-refresh; al llegar a 12 y acreditarse, pasa a **acreditado** sin acción del usuario (evento `balances`); si estaba en background, se refleja al volver a foreground. Entorno no operable → NO_EVALUABLE. | | |
| AT-11-06-03 | Con un depósito < 12 confirmaciones, inspeccionar la respuesta de `GET /deposits` (proxy). Verificar: `status="PENDIENTE"` con `confirmations < 12` (y `confirmations`/`required` como **enteros JSON**, no strings); la UI no suma ese monto al disponible. | | |
| AT-11-06-04 | Con un depósito ya acreditado, esperar re-polls / forzar refetch. Verificar: la acreditación no se repite; la UI sigue mostrando **un único** depósito acreditado (identidad `(txHash, logIndex)`), sin re-sumar. | | |
| AT-11-06-05 | Retiro válido: destino EIP-55 válido + monto válido, confirmar. Verificar: el backend acepta la solicitud, la UI muestra el retiro en seguimiento y, cuando existe, el `txHash` con enlace al explorer de Sepolia. | | |
| AT-11-06-06 | Ingresar un destino con checksum EIP-55 incorrecto (una letra con caso cambiado) o que no sea `0x`+40 hex. Verificar: feedback temprano de dirección inválida; forzado al backend (proxy), responde `INVALID_ADDRESS` (422) con `details.address`. | | |
| AT-11-06-07 | Solicitar un retiro con monto no positivo o con más precisión que la unidad mínima. Verificar: `WITHDRAWAL_AMOUNT_INVALID` (422) informado por la UI (o bloqueo temprano equivalente; forzar al backend con proxy para ver el 422). | | |
| AT-11-06-08 | Retiro de ETH por `0.000999999999999999` (1 wei bajo el mínimo 0.001 ETH) o USDC por `0.999999`. Verificar: `WITHDRAWAL_BELOW_MIN` (422) con `details {asset, amount, minWithdrawal}` informado; se admite (y anota) el feedback temprano del cliente antes de enviar. | | |
| AT-11-06-09 | Retiro con monto válido mayor al disponible. Verificar: `INSUFFICIENT_FUNDS` (422) con `details {asset, required, available}` mostrados formateados a humano. | | |
| AT-11-06-10 | Si el backend puede apuntarse a una red ≠ Sepolia (o inyectando la respuesta): ante `CHAIN_ID_MISMATCH` (422) con `details {expected, got}`, verificar que la UI lo informa por su `code` (el cliente no firma ni arma la tx). No provocable → NO_EVALUABLE. | | |
| AT-11-06-11 | Provocar conflicto de nonce (tx externa desde la hot wallet con el nonce en uso, si el entorno lo permite) tras un 202. Verificar: ningún error HTTP llega al alta; el cliente observa `PENDING`/`BROADCAST` (si el backend lo resuelve) o `FAILED` con `failureReason`; ante `FAILED` informa la causa y ofrece retiro **nuevo** con `clientWithdrawalId` distinto. No provocable → NO_EVALUABLE. | | |
| AT-11-06-12 | Retiro aceptado (202) con el **nodo RPC apagado** hasta agotar los reintentos internos. Verificar: el cliente observa `status="FAILED"` con la causa en `failureReason`, informa que el envío falló y ofrece crear un retiro **nuevo** con `clientWithdrawalId` distinto (sin duplicar el original). No provocable → NO_EVALUABLE. | | |
| AT-11-06-13 | Con permiso de cámara concedido, escanear Q1 (address plano) y luego Q2 (EIP-681 @11155111). Verificar: en ambos casos extrae el address, rellena el campo destino y lo valida con EIP-55 antes de permitir el envío. | | |
| AT-11-06-14 | Denegar el permiso de cámara e intentar escanear. Verificar: la UI informa la falta de permiso y permite el **ingreso manual** de la dirección. | | |
| AT-11-06-15 | Doble tap rápido en "Retirar" (red lenta/proxy retardando). Verificar: un único request (log del backend) y un solo retiro creado. | | |
| AT-11-06-16 | Ingresar monto humano `0.5` USDC y enviar. Verificar en el payload: `"500000"` como string entero. | | |
| AT-11-06-17 | Instrumentación (precondición 5): (a) inspeccionar en el proxy las respuestas/requests de los endpoints consumidos por depósito/retiro: sin campos `mnemonic`/`seed`/`privateKey`; (b) recorrer las pantallas de depósito/retiro: no renderizan frases mnemónicas de 12/24 palabras ni claves privadas; (c) tests propios de la implementación (contrato/snapshot/spy de red) como evidencia si existen. No concluyente → NO_EVALUABLE (b). | | |
| AT-11-06-18 | Invalidar el token y disparar una petición de depósito o retiro. Verificar: al 401 limpia la sesión y redirige al login. | | |
| AT-11-06-19 | Escanear Q3 (EIP-681 con `@1`, mainnet). Verificar: error explícito de **red incorrecta** (no es Sepolia) y el campo destino **no** se modifica. | | |
| AT-11-06-20 | Escanear Q4 (contenido que no es una dirección Ethereum válida). Verificar: la UI indica que el QR no contiene una dirección válida, el campo no se modifica y se puede reintentar o ingresar manualmente. | | |
| AT-11-06-21 | Cuenta con USDC suficiente pero **sin ETH** para gas: abrir el modal de confirmación de un retiro USDC. Verificar: el modal muestra activo, monto, destino, red Sepolia y la **fee de red estimada en ETH** (gas 100000 × gas price), con advertencia explícita de que se requiere ETH para el gas, **antes** de confirmar; al confirmar igualmente, `INSUFFICIENT_FUNDS` con `details.asset="ETH"` informado. | | |
| AT-11-06-22 | Enviar un retiro con la respuesta retenida (proxy) y hacer task-kill; reabrir la app. Verificar: detecta el `clientWithdrawalId` pendiente persistido y reintenta con la **misma** clave y mismos parámetros; el backend devuelve el **mismo** retiro (sin doble bloqueo); con parámetros distintos respondería `CONFLICT` (409) informado; luego limpia el registro. No provocable → NO_EVALUABLE (b). | | |
| AT-11-06-23 | Provocar `DEPOSIT_ALREADY_CREDITED` (409, reproceso de un depósito acreditado; puede requerir proxy o reprocesamiento del backend). Verificar: la UI lo trata como informativo — muestra el depósito **acreditado**, no re-suma el monto y no lo presenta como error. No provocable → NO_EVALUABLE. | | |
| AT-11-06-24 | Con un retiro en seguimiento que el backend reconcilia como `FAILED` (misma provocación que AT-11-06-12/13 web). Verificar: la UI lo muestra **fallido** con el enum canónico y refleja la liberación de los fondos (el disponible vuelve a subir vía `balances`), sin recalcular nada. No provocable → NO_EVALUABLE. | | |
| AT-11-06-25 | En modo avión (o backend caído), confirmar un retiro válido. Verificar: error de conectividad (distinto de los de negocio), el estado local no cambia y el reintento reusa el **mismo** `clientWithdrawalId` (proxy al volver la red). | | |
| AT-11-06-26 | En la pantalla de depósito de **USDC-mock**, decodificar el QR con un lector externo. Verificar: codifica exactamente `ethereum:<tokenAddress>@11155111/transfer?address=<depositAddress>` con el `tokenAddress` devuelto por `GET /deposit-address?asset=USDC`; y además se muestra el address en texto con checksum EIP-55 como respaldo. | | |
