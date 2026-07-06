# HELPERS.md — guía para escribir los tests por épica

Documentación de la API de helpers de la suite AT, dirigida a quienes escriban
`tests/test_epNN_*.py` (épicas 01–09). Leer primero el `README.md` de este
directorio (qué es la suite, cómo se corre) y tener a mano la spec
(`spec/00-fundaciones/` prevalece sobre todo lo demás).

## Principios no negociables

1. **Black-box estricto.** Un test sólo puede observar el SUT por el contrato de
   la épica 09 (REST + WebSocket) y el estado on-chain del anvil local. Nada de
   leer su base de datos, archivos o logs.
2. **El AT-id es la unidad de reporte.** Todo test declara qué ATs verifica con
   `@pytest.mark.at(...)`. Un test sin marker no aporta al reporte.
3. **Montos = strings de entero.** En requests se envían strings (`"2000500000"`);
   en responses se validan con `es_monto_valido`/`assert_monto` y se opera con
   `int` de Python (precisión arbitraria). **Prohibido `float`** para montos.
4. **Usuarios frescos por test.** Cada test crea sus usuarios (`usuario`,
   `usuario_b`, `crear_usuario`): aísla estado y evita el rate limit por cuenta
   (60 req/min por cuenta y endpoint, HU-09-02 RN-12).
5. **El "Dado" lo construye el test.** No asumir estado previo del SUT (la suite
   debe poder correr sobre una instancia limpia, en cualquier orden de tests).

## Convenciones de naming y estructura

- Archivo: `tests/test_epNN_<tema>.py` (p. ej. `test_ep03_matching.py`,
  `test_ep09_contrato.py`). Un archivo por épica; si crece, dividir por tema:
  `test_ep04_alta_de_orden.py`, `test_ep04_cancelacion.py`.
- Función: `test_<resumen_del_escenario>` en español, sin el AT-id en el nombre
  (el AT-id va en el marker).
- Docstring: primera línea `HU-EE-SS Escenario N: <título>.` y el Gherkin de la
  spec mapeado como comentarios `# Dado / # Cuando / # Entonces / # Y` en el
  cuerpo (ver ejemplo completo abajo y `tests/test_ep09_contrato.py`).
- Preferir **un test por AT**. Un test puede declarar varios ATs sólo si un
  mismo flujo los verifica de punta a punta (todos fallan/pasan juntos).

## Configuración (env vars)

| Env var                        | Default | Uso                                          |
|--------------------------------|---------|----------------------------------------------|
| `EXCHANGE_API_URL`             | —       | URL raíz del SUT sin `/api/v1` (obligatoria para correr contra un SUT; sin ella los tests saltan) |
| `EXCHANGE_WS_URL`              | —       | URL del WebSocket (`ws://host/api/v1/ws`, RG-API-11) |
| `EVAL_RPC_URL`                 | `http://127.0.0.1:8545` | nodo anvil del entorno       |
| `EVAL_USDC_ADDRESS`            | —       | dirección del USDC-mock (la imprime `entorno/desplegar-usdc.py`) |
| `SUITE_HTTP_TIMEOUT_SEGUNDOS`  | `10`    | timeout por request HTTP                     |
| `SUITE_WS_TIMEOUT_SEGUNDOS`    | `10`    | timeout por recepción WS                     |
| `SUITE_POLL_TIMEOUT_SEGUNDOS`  | `30`    | timeout default de `esperar_hasta`           |
| `SUITE_POLL_INTERVALO_SEGUNDOS`| `0.5`   | intervalo default de `esperar_hasta`         |
| `SUITE_RESULTADOS_AT`          | `./resultados-at.csv` | destino del reporte por AT     |

## Fixtures (conftest.py)

| Fixture     | Scope    | Qué da                                                            |
|-------------|----------|-------------------------------------------------------------------|
| `api`       | session  | `ClienteApi` **sin token** (endpoints públicos, registro/login). Salta si no hay `EXCHANGE_API_URL`. |
| `usuario`   | function | `Usuario` fresco: registrado + logueado. `usuario.api` es un `ClienteApi` autenticado; además `usuario.email`, `usuario.password`, `usuario.account_id`, `usuario.token`. |
| `usuario_b` | function | segundo `Usuario` fresco (aislamiento entre cuentas, contrapartes de fills). |
| `ws`        | function | `ConexionWs` nueva (se cierra sola al terminar el test). Salta si no hay `EXCHANGE_WS_URL`. |
| `rpc`       | session  | `ClienteRpc` contra el anvil (chainId 11155111). Salta si el nodo no responde. |

## `helpers.api` — cliente REST

```python
class ClienteApi:
    def __init__(self, base_url: str | None = None, token: str | None = None)
    def con_token(self, token: str) -> ClienteApi     # variante autenticada
    def sin_token(self) -> ClienteApi                 # variante sin Authorization
    def get(self, ruta, params=None, headers=None) -> httpx.Response
    def post(self, ruta, json=None, content=None, headers=None) -> httpx.Response
    def delete(self, ruta, headers=None) -> httpx.Response
    def request(self, metodo, ruta, **kwargs) -> httpx.Response  # PUT/PATCH/etc.
```

- Las rutas son **relativas a `/api/v1`**: `api.get("/balances")`, nunca
  `api.get("/api/v1/balances")`.
- **No lanza** en 4xx/5xx: el test asserta status y envelope explícitamente.
- `post(..., content=b"crudo")` manda un cuerpo no-JSON con
  `Content-Type: application/json` (para `VALIDATION_ERROR` de esquema).

## `helpers.cuentas` — usuarios de prueba

```python
PASSWORD_DEFECTO: str                                  # cumple HU-01-01 RN-3 (8..128)
def email_unico(prefijo="at") -> str                   # xxx@example.com único
def registrar(api, email=None, password=PASSWORD_DEFECTO) -> dict   # cuerpo del 201
def login(api, email, password=PASSWORD_DEFECTO) -> str             # token
def crear_usuario(api, prefijo="at", password=PASSWORD_DEFECTO) -> Usuario
```

`registrar`/`login` **asumen el camino feliz** (assertan 201/200): son para
construir el "Dado". Los tests de error de registro/login llaman a la API
directamente (`api.post("/auth/register", json=...)`).

## `helpers.montos` — dinero en unidad mínima

```python
# constantes del dominio (00-fundaciones)
WEI_POR_ETH = 10**18; USDCMIN_POR_USDC = 10**6
TICK_SIZE = 10_000; LOT_SIZE = 10**14; MIN_NOTIONAL = 10_000_000
FEE_BPS_MAKER = 10; FEE_BPS_TAKER = 20; FEE_DENOMINADOR = 10_000
CHAIN_ID = 11155111; CONFIRMACIONES_REQUERIDAS = 12; SIMBOLO = "ETH-USDC"

def es_monto_valido(valor) -> bool          # string y matchea ^(0|[1-9][0-9]*)$
def assert_monto(valor, campo="monto") -> int  # valida y devuelve int
def a_int(valor) -> int                     # alias de assert_monto
def a_str(valor: int) -> str                # int → string para requests
def eth_a_wei(n) / usdc_a_usdcmin(n) / precio_usdc_a_pricemin(n) -> int
def quote_min(q_wei, price_min) -> int      # floor(q_wei × price_min / 10^18)
def fee(monto_recibido, fee_bps) -> int     # ceil(monto × bps / 10000)
def fee_maker(monto) / fee_taker(monto) -> int
def es_multiplo_de_tick(price_min) / es_multiplo_de_lot(q_wei) -> bool
```

`quote_min` y `fee` son las **fórmulas de referencia de la spec**: usarlas para
computar el valor esperado exacto de un fill/fee y comparar con igualdad estricta
(nunca con tolerancia).

## `helpers.errores` — envelope y catálogo

```python
CATALOGO_CODES: dict[str, int]   # code → status HTTP (33 códigos de la spec)
def validar_envelope(cuerpo: dict) -> dict            # devuelve cuerpo["error"]
def assert_error(respuesta, code, status=None) -> dict     # HTTP
def assert_error_ws(mensaje: dict, code) -> dict           # WebSocket
def assert_montos_en_details(details, *campos) -> None
```

`assert_error` valida (1) envelope `{error:{code,message,details?}}`, (2) status
HTTP (el del catálogo salvo override), (3) `code` exacto — y devuelve el objeto
`error` para asserts sobre `details`. También rechaza typos: un `code` que no
está en el catálogo hace fallar **el test**, no el SUT.

## `helpers.eip55` — direcciones Ethereum

```python
def a_checksum(direccion) -> str            # aplica EIP-55 (referencia)
def es_direccion_valida(direccion) -> bool  # 0x + 40 hex + checksum correcto
def assert_direccion(direccion, campo="address") -> str
def romper_checksum(direccion) -> str       # variante con checksum inválido
RE_TXHASH                                    # ^0x[0-9a-fA-F]{64}$
```

## `helpers.espera` — polling con timeout

```python
def esperar_hasta(condicion, timeout=None, intervalo=None,
                  mensaje="la condición no se cumplió")
```

Re-evalúa `condicion()` hasta valor truthy (lo devuelve) o `TimeoutError`. Los
`AssertionError` dentro de la condición se tratan como "todavía no" (permite
condiciones que reusan helpers con asserts). Usarlo para todo lo asíncrono:
acreditación de depósitos, transiciones de retiros, convergencia REST/WS.

## `helpers.ws` — cliente WebSocket

```python
class ConexionWs:
    def enviar(self, mensaje: dict) -> None
    def recibir(self, timeout=None) -> dict
    def recibir_hasta(self, predicado, timeout=None, descartar_ping=True) -> dict
    def no_debe_llegar(self, predicado, ventana=2.0) -> None
    def autenticar(self, token) -> dict          # {"type":"auth",...} (HU-09-04 RN-1)
    def suscribir(self, canal, symbol="ETH-USDC", depth=None) -> dict
    def desuscribir(self, canal, symbol="ETH-USDC") -> dict
    def cerrar(self) -> None                     # o usar `with ConexionWs() as ws:`
```

- Para canales **privados** (`orders`/`balances`/`withdrawals`): primero
  `ws.autenticar(usuario.token)`, después `ws.suscribir("orders", symbol=None)`.
- `recibir_hasta` responde `pong` a los `ping` del heartbeat automáticamente
  (desactivable con `descartar_ping=False` para testear el heartbeat mismo).
- Verificación de secuencia: acumular mensajes y assertar `sequence` contigua
  **dentro del mismo canal** (RG-API-7; nunca comparar entre canales).

## `helpers.onchain` — control del mundo on-chain (anvil)

```python
class ClienteRpc:
    def __init__(self, url=None, usdc=None)      # defaults: EVAL_RPC_URL / EVAL_USDC_ADDRESS
    def disponible(self) -> bool                 # nodo responde y chainId == 11155111
    def chain_id(self) / numero_de_bloque(self) -> int
    def balance_eth(self, direccion) -> int      # wei
    def balance_usdc(self, direccion, contrato=None) -> int  # USDC-min
    def transaccion(self, tx_hash) / receipt(self, tx_hash) -> dict | None
    def nonce(self, direccion) -> int
    def minar_bloques(self, cantidad=1) -> None  # confirmaciones a demanda
    def enviar_eth(self, hacia, valor_wei, desde=CUENTA_TESORERIA) -> str
    def mint_usdc(self, hacia, monto_usdcmin, contrato=None) -> str
    def transferir_usdc(self, hacia, monto_usdcmin, desde=..., contrato=None) -> str
    def esperar_receipt(self, tx_hash) -> dict
    # helpers de escenario:
    def depositar_eth(self, direccion_deposito, valor_wei, confirmar=True) -> str
    def depositar_usdc(self, direccion_deposito, monto_usdcmin, confirmar=True) -> str
```

- `depositar_*(direccion, monto)` transfiere hacia la dirección de depósito del
  usuario y mina 12 bloques (`confirmar=True`): al volver, el depósito es
  acreditable; la acreditación del SUT puede demorar su ciclo de polling ⇒
  combinar con `esperar_hasta`.
- Con `confirmar=False` queda `PENDIENTE` (< 12 confirmaciones): para tests de
  `DEPOSIT_NOT_CONFIRMED`, estados intermedios y `confirmations` crecientes.
- Para retiros: inspeccionar la transacción que el SUT broadcastea
  (`transaccion(txHash)`) y assertar `chainId`, `nonce`, `gasPrice == 20 gwei`,
  `gas` (INV-6, épica 08). El `txHash` sale de `GET /withdrawals/{id}` o del
  evento WS `withdrawal`.

## El patrón completo: fondear una cuenta interna

Casi toda la épica 03/04/05 necesita usuarios **con balance interno**. El único
camino black-box es el flujo real de depósito (épicas 06+07):

```python
from helpers.espera import esperar_hasta
from helpers.montos import a_int, usdc_a_usdcmin

def fondear_usdc(usuario, rpc, monto_usdcmin: int) -> None:
    """Deposita USDC hasta verlo acreditado en el balance interno."""
    direccion = usuario.api.get("/deposit-address", params={"asset": "USDC"}).json()["address"]
    rpc.depositar_usdc(direccion, monto_usdcmin)          # transfer + 12 bloques
    esperar_hasta(
        lambda: a_int(_balance(usuario, "USDC")["available"]) >= monto_usdcmin,
        mensaje="el depósito USDC no se acreditó",
    )

def _balance(usuario, asset: str) -> dict:
    balances = usuario.api.get("/balances").json()
    return next(b for b in balances if b["asset"] == asset)
```

(Si varios tests de una épica lo repiten, subirlo a un módulo compartido
`tests/comunes_epNN.py` — no duplicarlo por archivo.)

## Reporte por AT-id

- Marker: `@pytest.mark.at("AT-03-02-01")` o
  `@pytest.mark.at("AT-04-01-02", "AT-04-01-03")` (varios ATs si el flujo los
  verifica juntos).
- En la **colección** se valida cada AT-id contra `catalogo-at.csv`: formato,
  existencia, tipo `backend`, y que no esté declarado en
  `no-automatizables.yaml`. Un marker inválido aborta la corrida con el detalle.
- Al final de la corrida se escribe `resultados-at.csv` (una fila por AT backend)
  y el resumen sale por terminal. Agregación por AT: algún test falló ⇒ `falla`;
  si no, alguno pasó ⇒ `pasa`; si no ⇒ `skip`.

## Declarar un AT no automatizable

Si un AT de 01–09 no es verificable black-box (efecto interno sin superficie
REST/WS/on-chain), se agrega a `no-automatizables.yaml`:

```yaml
- at_id: AT-06-01-02
  motivo: >-
    Known-answer test de la derivación BIP-39: requiere invocar la función
    interna con inputs elegidos; el contrato HTTP/WS no expone esa operación.
    Se evalúa white-box en H8.
  referencia: spec/06-wallet-hd-y-direcciones/HU-06-01-generacion-y-custodia-del-seed.md
```

Reglas: motivo concreto (qué lo hace inobservable **y** por qué vía se evalúa),
nunca "es difícil"; un AT declarado no puede tener tests (el plugin lo rechaza);
la carga de la prueba es alta — si el efecto se puede observar indirectamente
(p. ej. reinicio del SUT orquestado por el evaluador para INV-8), automatizarlo.

## Ejemplo real completo (AT-09-01-11 — creación de retiro, 202)

```python
import pytest

from helpers.eip55 import romper_checksum
from helpers.errores import assert_error
from helpers.espera import esperar_hasta
from helpers.montos import a_int, es_monto_valido

DESTINO_RETIRO = "0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc"  # EIP-55 válido


@pytest.mark.at("AT-09-01-11")
def test_crear_retiro_responde_202_asincrono(usuario, rpc):
    """HU-09-01 Escenario 11: Creación de retiro (asíncrono, 202).

    - Dado un token válido y balance disponible suficiente
    - Cuando POST /api/v1/withdrawals {asset: USDC, amountMinUnit: "25000000", address}
    - Entonces 202 con {withdrawalId, asset, amountMinUnit, address, status: PENDING,
      createdAt, updatedAt}
    - Y una address con checksum EIP-55 inválido produce INVALID_ADDRESS (422)
    - Y un amountMinUnit mayor al disponible produce INSUFFICIENT_FUNDS (422)
    """
    # Dado: balance disponible suficiente (30 USDC vía depósito on-chain real)
    direccion_deposito = usuario.api.get(
        "/deposit-address", params={"asset": "USDC"}
    ).json()["address"]
    rpc.depositar_usdc(direccion_deposito, 30_000_000)     # 30 USDC + 12 confirmaciones
    esperar_hasta(
        lambda: any(
            b["asset"] == "USDC" and a_int(b["available"]) >= 30_000_000
            for b in usuario.api.get("/balances").json()
        ),
        mensaje="el depósito USDC no se acreditó al balance interno",
    )

    # Cuando: retiro de 25 USDC (unidad mínima) a una dirección externa válida
    resp = usuario.api.post(
        "/withdrawals",
        json={"asset": "USDC", "amountMinUnit": "25000000", "address": DESTINO_RETIRO},
    )

    # Entonces: 202 Accepted con el objeto retiro en PENDING
    assert resp.status_code == 202, resp.text
    retiro = resp.json()
    assert retiro["status"] == "PENDING"
    assert retiro["asset"] == "USDC"
    assert retiro["amountMinUnit"] == "25000000"
    assert es_monto_valido(retiro["amountMinUnit"])
    assert retiro["withdrawalId"]
    assert isinstance(retiro["createdAt"], str) and isinstance(retiro["updatedAt"], str)

    # Y: checksum EIP-55 inválido ⇒ INVALID_ADDRESS (422)
    resp = usuario.api.post(
        "/withdrawals",
        json={"asset": "USDC", "amountMinUnit": "1000000",
              "address": romper_checksum(DESTINO_RETIRO)},
    )
    assert_error(resp, "INVALID_ADDRESS")

    # Y: monto mayor al disponible ⇒ INSUFFICIENT_FUNDS (422) con montos string
    resp = usuario.api.post(
        "/withdrawals",
        json={"asset": "USDC", "amountMinUnit": "99000000000", "address": DESTINO_RETIRO},
    )
    err = assert_error(resp, "INSUFFICIENT_FUNDS")
    assert es_monto_valido(err["details"]["available"])
```

## Gotchas frecuentes

- **`sequence`, `confirmations`, `blockNumber`, `logIndex`, `limit`, `depth` son
  enteros JSON**, no strings (convenciones-monetarias §5): assertar
  `isinstance(x, int)`. Sólo los montos van como string.
- **Comparaciones exactas.** Nunca `abs(a - b) < eps`: los enteros de unidad
  mínima se comparan con `==` (y las fórmulas de referencia dan el valor exacto).
- **Precedencia de errores.** Al testear un error específico, dejar válido todo
  lo que lo precede (modelo-de-errores §4): p. ej. para `INSUFFICIENT_FUNDS`
  mandar esquema/enums/tick/lot/notional correctos.
- **Un depósito on-chain tarda**: `depositar_*` deja la cadena lista, pero el
  indexador del SUT corre por polling ⇒ siempre `esperar_hasta` la acreditación
  antes del "Cuando".
- **No compartir `clientOrderId` entre tests**: son únicos por cuenta; con
  usuarios frescos por test no hay colisión.
- **WS privado**: `auth` debe ser el **primer** mensaje (HU-09-04 RN-1); para
  probar aislamiento usar `ws.no_debe_llegar(...)` con ventana corta.
