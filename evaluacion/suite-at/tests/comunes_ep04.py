"""Helpers compartidos de los tests de la épica 04 (gestión de órdenes).

Todo acceso al SUT es black-box por el contrato REST de la épica 09:
``POST/GET/DELETE /orders``, ``GET /balances``, ``GET /market/orderbook``.
El fondeo usa el único camino permitido: depósito on-chain acreditado
(``helpers/onchain.py`` + ``esperar_hasta``; ver HELPERS.md).

TODO-REVISAR — discrepancias entre la épica 04 y la épica 09 que estos helpers
absorben (la épica 04 fija la semántica; la 09, la forma; no siempre coinciden):

1. HU-04-* llama ``executedQty`` a la cantidad ejecutada en base (wei); el objeto
   orden de HU-09-01 RN-5 la llama ``filledWei``. ``ejecutado_wei()`` acepta
   cualquiera de los dos nombres (mismo significado normativo).
2. HU-04-06/HU-04-07 exigen ``remainingQty``, ``executedQuoteQty`` y
   ``avgExecutionPrice`` en las consultas; HU-09-01 RN-5 no los incluye en el
   objeto orden. ``remanente_wei()`` usa ``remainingQty`` si está presente y si
   no lo deriva de ``quantityWei − ejecutado``. Los ATs que assertan un *valor*
   de ``executedQuoteQty``/``avgExecutionPrice`` exigen el campo (AT-04-06-09).
3. HU-04-02 define la forma de tamaño ``quoteOrderQty`` para MARKET; el body de
   HU-09-01 RN-4 no la lista. Se envía con ese nombre (el único que la spec usa).
4. HU-04-07 RN-4 exige filtros de período en el historial; HU-09-01 RN-8 no
   define parámetros temporales para ``GET /orders``. Se usan ``from``/``to``
   por analogía con HU-09-01 RN-20 (``GET /trades``).
5. La épica 04 separa "órdenes abiertas" (HU-04-06) de "historial" (HU-04-07),
   pero la épica 09 expone un único ``GET /orders`` con filtro ``status``. Las
   consultas semánticas se implementan como unión de consultas por estado.
"""

import secrets

import pytest

from helpers.errores import assert_error
from helpers.espera import esperar_hasta
from helpers.montos import SIMBOLO, a_int, a_str, es_monto_valido

# --- Constantes de escenario (valores del Gherkin de la épica 04) -----------------

ETH_1 = 10**18                 # 1 ETH en wei
Q_MIN = 5 * 10**15             # 0.005 ETH: notional exactamente 10 USDC a 2000.00
P2000 = 2_000_000_000          # 2000.00 USDC/ETH en price_min
NOTIONAL_MIN = 10_000_000      # 10 USDC en USDC-min (mínimo notional del par)

ESTADOS_ABIERTOS = ("OPEN", "PARTIALLY_FILLED")
ESTADOS_TERMINALES = ("FILLED", "CANCELLED", "REJECTED")

# Campos monetarios que puede traer un objeto orden (unión épica 04 + épica 09).
CAMPOS_MONETARIOS_ORDEN = (
    "priceMin",
    "quantityWei",
    "quoteOrderQty",
    "filledWei",
    "executedQty",
    "remainingQty",
    "executedQuoteQty",
    "avgExecutionPrice",
    "feeWei",
    "feeUsdcMin",
)


def client_order_id(prefijo: str = "ep04") -> str:
    """clientOrderId único (la unicidad es por cuenta, HU-04-01 RN-15 / RE-5)."""
    return f"{prefijo}-{secrets.token_hex(6)}"


# --- Balances ----------------------------------------------------------------------

def balances(usuario) -> dict[str, dict]:
    """GET /balances como dict asset -> {available, locked, total} (HU-09-01 RN-9)."""
    resp = usuario.api.get("/balances")
    assert resp.status_code == 200, resp.text
    return {b["asset"]: b for b in resp.json()}


def disponible(usuario, asset: str) -> int:
    fila = balances(usuario).get(asset)
    return a_int(fila["available"]) if fila else 0


def bloqueado(usuario, asset: str) -> int:
    fila = balances(usuario).get(asset)
    return a_int(fila["locked"]) if fila else 0


def assert_balances(usuario, asset: str, *, disp: int, blk: int) -> None:
    """Asserta disponible y bloqueado exactos de un activo (comparación entera)."""
    fila = balances(usuario).get(asset)
    disp_real = a_int(fila["available"]) if fila else 0
    blk_real = a_int(fila["locked"]) if fila else 0
    assert disp_real == disp, f"{asset}.available: esperado {disp}, llegó {disp_real}"
    assert blk_real == blk, f"{asset}.locked: esperado {blk}, llegó {blk_real}"
    if fila:
        # INV-3: total == available + locked (partición de fondos).
        assert a_int(fila["total"]) == disp_real + blk_real, fila


# --- Fondeo black-box (patrón de HELPERS.md) ----------------------------------------

def direccion_deposito(usuario, asset: str) -> str:
    resp = usuario.api.get("/deposit-address", params={"asset": asset})
    assert resp.status_code == 200, resp.text
    return resp.json()["address"]


def fondear(usuario, rpc, eth_wei: int = 0, usdc_min: int = 0) -> None:
    """Fondea la cuenta interna vía depósito on-chain real (épicas 06+07).

    Deposita, mina las 12 confirmaciones y espera la acreditación del SUT.
    Los montos son deltas: se espera hasta ver `disponible` incrementado.
    """
    objetivo_eth = disponible(usuario, "ETH") + eth_wei
    objetivo_usdc = disponible(usuario, "USDC") + usdc_min
    if eth_wei:
        rpc.depositar_eth(direccion_deposito(usuario, "ETH"), eth_wei)
    if usdc_min:
        rpc.depositar_usdc(direccion_deposito(usuario, "USDC"), usdc_min)
    esperar_hasta(
        lambda: disponible(usuario, "ETH") >= objetivo_eth
        and disponible(usuario, "USDC") >= objetivo_usdc,
        mensaje="el depósito de fondeo no se acreditó al balance interno",
    )


# --- Alta y consulta de órdenes ------------------------------------------------------

def _monto(valor) -> str:
    """int -> string de monto; los strings se envían tal cual (para casos inválidos)."""
    return valor if isinstance(valor, str) else a_str(valor)


def cuerpo_orden(
    side,
    tipo,
    price_min=None,
    quantity_wei=None,
    quote_order_qty=None,
    client_id: str | None = None,
    symbol: str = SIMBOLO,
) -> dict:
    """Body de POST /orders (HU-09-01 RN-4; clientOrderId obligatorio por RN-19).

    Nota: HU-04-01/02 RN-1 dicen que `clientOrderId` es opcional, pero HU-09-01
    RN-19 lo exige (ausente => VALIDATION_ERROR). TODO-REVISAR: discrepancia;
    los tests siempre lo envían (único por cuenta).
    """
    cuerpo = {
        "clientOrderId": client_id or client_order_id(),
        "symbol": symbol,
        "side": side,
        "type": tipo,
    }
    if price_min is not None:
        cuerpo["priceMin"] = _monto(price_min)
    if quantity_wei is not None:
        cuerpo["quantityWei"] = _monto(quantity_wei)
    if quote_order_qty is not None:
        cuerpo["quoteOrderQty"] = _monto(quote_order_qty)
    return cuerpo


def post_orden(usuario, cuerpo: dict):
    return usuario.api.post("/orders", json=cuerpo)


def alta_ok(usuario, cuerpo: dict, estado: str | None = None) -> dict:
    """POST /orders esperando 201; opcionalmente asserta el status resultante."""
    resp = post_orden(usuario, cuerpo)
    assert resp.status_code == 201, resp.text
    orden = resp.json()
    assert orden.get("orderId"), orden
    if estado is not None:
        assert orden["status"] == estado, orden
    return orden


def detalle(usuario, order_id: str) -> dict:
    resp = usuario.api.get(f"/orders/{order_id}")
    assert resp.status_code == 200, resp.text
    return resp.json()


def items_por_estado(usuario, estado: str, extra_params: dict | None = None) -> list[dict]:
    """GET /orders?status=<estado> agotando la paginación por cursor (RN-8)."""
    params: dict = {"status": estado, "limit": 200}
    if extra_params:
        params.update(extra_params)
    items: list[dict] = []
    cursor = None
    for _ in range(20):  # tope defensivo de páginas
        pagina = dict(params)
        if cursor:
            pagina["cursor"] = cursor
        resp = usuario.api.get("/orders", params=pagina)
        assert resp.status_code == 200, resp.text
        cuerpo = resp.json()
        items.extend(cuerpo["items"])
        cursor = cuerpo.get("nextCursor")
        if not cursor:
            break
    return items


def abiertas(usuario) -> list[dict]:
    """Órdenes activas (HU-04-06 RN-1): estado en {OPEN, PARTIALLY_FILLED}."""
    return [i for e in ESTADOS_ABIERTOS for i in items_por_estado(usuario, e)]


def historial(usuario, periodo: dict | None = None) -> list[dict]:
    """Órdenes terminales (HU-04-07 RN-1): {FILLED, CANCELLED, REJECTED}.

    `periodo` (opcional): {"from": iso, "to": iso} aplicado a cada consulta
    (TODO-REVISAR 4 del docstring del módulo).
    """
    return [i for e in ESTADOS_TERMINALES for i in items_por_estado(usuario, e, periodo)]


def buscar_por_id(items: list[dict], order_id: str) -> dict | None:
    return next((i for i in items if i.get("orderId") == order_id), None)


def buscar_por_client_id(items: list[dict], client_id: str) -> dict | None:
    return next((i for i in items if i.get("clientOrderId") == client_id), None)


def esperar_orden(usuario, order_id: str, *estados: str) -> dict:
    """Espera (polling, sin sleeps fijos) a que la orden esté en uno de `estados`."""
    def _condicion():
        orden = detalle(usuario, order_id)
        return orden if orden["status"] in estados else None

    return esperar_hasta(
        _condicion, mensaje=f"la orden {order_id} no llegó a {estados}"
    )


# --- Cancelación ---------------------------------------------------------------------

def cancelar(usuario, order_id: str):
    return usuario.api.delete(f"/orders/{order_id}")


def cancelar_ok(usuario, order_id: str) -> dict:
    """DELETE /orders/{id} esperando 200 con la orden en CANCELLED (HU-09-01 RN-7)."""
    resp = cancelar(usuario, order_id)
    assert resp.status_code == 200, resp.text
    orden = resp.json()
    assert orden["status"] == "CANCELLED", orden
    return orden


# --- Campos del objeto orden (ver TODO-REVISAR 1 y 2 del docstring) ------------------

def ejecutado_wei(orden: dict) -> int:
    """Cantidad ejecutada en base (wei): `executedQty` (ep. 04) o `filledWei` (ep. 09)."""
    if orden.get("executedQty") is not None:
        return a_int(orden["executedQty"])
    return a_int(orden["filledWei"])


def remanente_wei(orden: dict) -> int:
    """Remanente en base: `remainingQty` si está; si no, quantityWei − ejecutado."""
    if orden.get("remainingQty") is not None:
        return a_int(orden["remainingQty"])
    return a_int(orden["quantityWei"]) - ejecutado_wei(orden)


def assert_montos_de_orden(orden: dict) -> None:
    """Todo campo monetario presente y no nulo es string ^(0|[1-9][0-9]*)$ (RE-8)."""
    for campo in CAMPOS_MONETARIOS_ORDEN:
        if campo in orden and orden[campo] is not None:
            assert es_monto_valido(orden[campo]), (
                f"{campo} mal serializado: {orden[campo]!r}"
            )


# --- Orderbook público: niveles y guardas del "Dado" ---------------------------------

def libro(api) -> dict:
    resp = api.get("/market/orderbook", params={"depth": 200})
    assert resp.status_code == 200, resp.text
    return resp.json()


def cantidad_en_nivel(api, lado: str, price_min: int) -> int:
    """Cantidad agregada (wei) resting en el nivel `price_min` de `lado`."""
    return sum(
        a_int(cantidad)
        for precio, cantidad in libro(api)[lado]
        if a_int(precio) == price_min
    )


def requerir_lado_vacio(api, lado: str) -> None:
    """pytest.skip si el lado del libro no está vacío (el Dado no es construible)."""
    niveles = libro(api)[lado]
    if niveles:
        pytest.skip(
            f"el Dado exige {lado} vacíos y hay liquidez residual de otros tests: {niveles[:3]}"
        )


def requerir_sin_asks_hasta(api, price_min: int) -> None:
    """pytest.skip si existe algún ask con precio <= price_min (cruzaría un BUY)."""
    cruzables = [n for n in libro(api)["asks"] if a_int(n[0]) <= price_min]
    if cruzables:
        pytest.skip(f"el Dado exige asks > {price_min} y hay: {cruzables[:3]}")


def requerir_sin_bids_desde(api, price_min: int) -> None:
    """pytest.skip si existe algún bid con precio >= price_min (cruzaría un SELL)."""
    cruzables = [n for n in libro(api)["bids"] if a_int(n[0]) >= price_min]
    if cruzables:
        pytest.skip(f"el Dado exige bids < {price_min} y hay: {cruzables[:3]}")


def requerir_zona_limpia(api, price_min: int) -> None:
    """Sin asks <= price_min ni bids >= price_min: órdenes a ese precio descansan."""
    requerir_sin_asks_hasta(api, price_min)
    requerir_sin_bids_desde(api, price_min)


# --- Constructores de escenario ("Dado" de varios ATs) --------------------------------

def crear_filled(usuario, usuario_b, rpc, api, client_id: str | None = None) -> dict:
    """Deja a `usuario` con una orden BUY LIMIT FILLED de 0.005 ETH @ 2000.00.

    `usuario_b` aporta el ask contraparte (0.005 ETH); `usuario` la cruza como
    taker (HU-04-01 RN-7). Fondea a ambos por depósito on-chain.
    """
    requerir_zona_limpia(api, P2000)
    fondear(usuario_b, rpc, eth_wei=Q_MIN)
    fondear(usuario, rpc, usdc_min=NOTIONAL_MIN)
    alta_ok(usuario_b, cuerpo_orden("SELL", "LIMIT", P2000, Q_MIN), estado="OPEN")
    return alta_ok(
        usuario, cuerpo_orden("BUY", "LIMIT", P2000, Q_MIN, client_id=client_id),
        estado="FILLED",
    )


def crear_cancelled(usuario, rpc, api, *, fondear_usdc: bool = True) -> dict:
    """Deja a `usuario` con una orden BUY LIMIT CANCELLED (bid resting + cancel)."""
    requerir_sin_asks_hasta(api, P2000)
    if fondear_usdc:
        fondear(usuario, rpc, usdc_min=NOTIONAL_MIN)
    orden = alta_ok(usuario, cuerpo_orden("BUY", "LIMIT", P2000, Q_MIN), estado="OPEN")
    return cancelar_ok(usuario, orden["orderId"])


def crear_rejected_sin_liquidez(usuario, api, client_id: str | None = None) -> dict:
    """Deja a `usuario` con una orden REJECTED persistida por MARKET_NO_LIQUIDITY.

    SELL MARKET con bids vacíos: la precondición de liquidez (RE-4 paso 6) se
    evalúa antes de fondos, así que no requiere fondeo alguno. El rechazo de la
    capa de matching se persiste como orden REJECTED (RE-12, HU-04-05 RN-5).
    """
    requerir_lado_vacio(api, "bids")
    cid = client_id or client_order_id("rej")
    resp = post_orden(usuario, cuerpo_orden("SELL", "MARKET", quantity_wei=Q_MIN, client_id=cid))
    assert_error(resp, "MARKET_NO_LIQUIDITY")
    item = buscar_por_client_id(items_por_estado(usuario, "REJECTED"), cid)
    assert item is not None, "la orden rechazada por matching no se persistió como REJECTED"
    assert item["status"] == "REJECTED", item
    return item


def construir_trio_terminal(usuario, usuario_b, rpc, api, usdc_extra: int = 0) -> dict:
    """FILLED + CANCELLED + REJECTED para `usuario` (Dado de HU-04-06/07).

    No deja nada resting en el libro. Fondea una sola vez: 20 USDC (+ extra)
    para `usuario` y 0.005 ETH para `usuario_b`.
    """
    requerir_lado_vacio(api, "bids")
    requerir_sin_asks_hasta(api, P2000)
    rejected = crear_rejected_sin_liquidez(usuario, api)  # sin fondos: previa a todo
    fondear(usuario, rpc, usdc_min=2 * NOTIONAL_MIN + usdc_extra)
    fondear(usuario_b, rpc, eth_wei=Q_MIN)
    alta_ok(usuario_b, cuerpo_orden("SELL", "LIMIT", P2000, Q_MIN), estado="OPEN")
    filled = alta_ok(usuario, cuerpo_orden("BUY", "LIMIT", P2000, Q_MIN), estado="FILLED")
    abierta = alta_ok(usuario, cuerpo_orden("BUY", "LIMIT", P2000, Q_MIN), estado="OPEN")
    cancelled = cancelar_ok(usuario, abierta["orderId"])
    return {"filled": filled, "cancelled": cancelled, "rejected": rejected}


# --- Limpieza de órdenes resting (no contaminar el libro para otros tests) -----------

class Limpiador:
    """Registra órdenes que podrían quedar resting y las cancela al final."""

    def __init__(self):
        self._pendientes: list[tuple[object, str]] = []

    def registrar(self, usuario, order_id: str) -> None:
        self._pendientes.append((usuario, order_id))

    def limpiar(self) -> None:
        for usuario, order_id in self._pendientes:
            try:
                usuario.api.delete(f"/orders/{order_id}")  # best-effort
            except Exception:
                pass


@pytest.fixture
def limpiador():
    """Cancela al terminar el test toda orden registrada (aunque el test falle)."""
    instancia = Limpiador()
    yield instancia
    instancia.limpiar()
