"""Helpers comunes de los tests de la épica 03 (motor de matching).

El motor se observa **exclusivamente black-box** por el contrato de la épica 09:

- colocación de órdenes: ``POST /api/v1/orders`` (el matching es síncrono: la
  respuesta 201 ya refleja los fills inmediatos, HU-09-01 RN-5);
- fills/trades: ``GET /api/v1/trades`` (pata propia, con ``sequence`` y ``role``),
  ``GET /api/v1/market/trades`` y el canal WS público ``trades``;
- orderbook: ``GET /api/v1/market/orderbook`` y el canal WS ``orderbook``
  (snapshot + deltas);
- prioridad precio-tiempo: observable por el **orden de los fills** resultantes;
- fondeo: **depósito on-chain real** acreditado (épicas 06+07, ``helpers.onchain``).

Aislamiento: el orderbook es global, por lo que cada test de la épica opera en
**niveles de precio propios** (bandas que no colisionan entre tests) y limpia sus
órdenes abiertas al final (``cancelar_abiertas``). Los tests que necesitan un
"Dado" global (lado vacío, best-of-book) lo verifican con ``requerir_*`` y saltan
si hay estado residual de otra corrida (mismo criterio que HELPERS.md /
test_ep09_contrato.py: sin el Dado no hay veredicto).

Reinicio del SUT (HU-03-07): no hay superficie REST para reiniciar el SUT, así
que los tests de persistencia usan la env var ``SUITE_CMD_REINICIO_SUT``: un
comando de shell provisto por el evaluador que **termina abruptamente** el
proceso del SUT (equivalente a ``kill -9``, HU-03-07 RN-1) y lo vuelve a
levantar. Sin esa variable, los tests de reinicio saltan.
"""

import os
import secrets
import subprocess

import pytest

from helpers.cuentas import login
from helpers.espera import esperar_hasta
from helpers.montos import SIMBOLO, a_str, assert_monto, es_monto_valido
from helpers.ws import ConexionWs, url_ws_configurada

VAR_REINICIO_SUT = "SUITE_CMD_REINICIO_SUT"


# --------------------------------------------------------------------------------
# Identificadores
# --------------------------------------------------------------------------------


def client_order_id(prefijo: str = "ep03") -> str:
    """clientOrderId único (1..64 ASCII imprimibles, HU-09-01 RN-19)."""
    return f"{prefijo}-{secrets.token_hex(8)}"


def numero_de_trade(trade_id: str) -> int:
    """Extrae el número del ``tradeId`` (formato "T-" + contador, HU-03-05 RN-2)."""
    assert isinstance(trade_id, str) and trade_id.startswith("T-"), (
        f"tradeId sin el formato 'T-<n>' de HU-03-05 RN-2: {trade_id!r}"
    )
    return int(trade_id[2:])


# --------------------------------------------------------------------------------
# Fondeo black-box (depósito on-chain acreditado, épicas 06+07)
# --------------------------------------------------------------------------------


def direccion_deposito(usuario, asset: str) -> str:
    resp = usuario.api.get("/deposit-address", params={"asset": asset})
    assert resp.status_code == 200, resp.text
    return resp.json()["address"]


def fondear(usuario, rpc, eth_wei: int = 0, usdc_min: int = 0) -> None:
    """Fondea el balance interno vía depósito on-chain real y espera la acreditación.

    Hace las transferencias sin confirmar, mina las 12 confirmaciones una sola
    vez y espera que el indexador del SUT acredite ambos activos.
    """
    if eth_wei:
        rpc.depositar_eth(direccion_deposito(usuario, "ETH"), eth_wei, confirmar=False)
    if usdc_min:
        rpc.depositar_usdc(direccion_deposito(usuario, "USDC"), usdc_min, confirmar=False)
    rpc.minar_bloques(12)  # CONFIRMACIONES_REQUERIDAS (activos-y-par §1)

    def _acreditado() -> bool:
        b = balances_por_activo(usuario)
        ok_eth = eth_wei == 0 or assert_monto(b["ETH"]["total"]) >= eth_wei
        ok_usdc = usdc_min == 0 or assert_monto(b["USDC"]["total"]) >= usdc_min
        return ok_eth and ok_usdc

    esperar_hasta(_acreditado, mensaje="el depósito on-chain no se acreditó al balance interno")


def fondear_lote(cuentas: list, rpc, eth_wei: int = 0, usdc_min: int = 0) -> None:
    """Fondea varias cuentas con los mismos montos, mina una sola vez y espera todas."""
    for usuario in cuentas:
        if eth_wei:
            rpc.depositar_eth(direccion_deposito(usuario, "ETH"), eth_wei, confirmar=False)
        if usdc_min:
            rpc.depositar_usdc(direccion_deposito(usuario, "USDC"), usdc_min, confirmar=False)
    rpc.minar_bloques(12)
    for usuario in cuentas:
        esperar_hasta(
            lambda u=usuario: (
                (not eth_wei or assert_monto(balances_por_activo(u)["ETH"]["total"]) >= eth_wei)
                and (not usdc_min or assert_monto(balances_por_activo(u)["USDC"]["total"]) >= usdc_min)
            ),
            mensaje=f"el depósito de {usuario.email} no se acreditó",
        )


# --------------------------------------------------------------------------------
# Balances
# --------------------------------------------------------------------------------


def balances_por_activo(usuario) -> dict:
    """GET /balances → {asset: {available, locked, total}} (montos como string)."""
    resp = usuario.api.get("/balances")
    assert resp.status_code == 200, resp.text
    return {b["asset"]: b for b in resp.json()}


def snapshot_balances(usuario) -> dict:
    """Snapshot comparable de balances: {asset: (available, locked, total)} como ints."""
    return {
        asset: (assert_monto(b["available"]), assert_monto(b["locked"]), assert_monto(b["total"]))
        for asset, b in balances_por_activo(usuario).items()
    }


# --------------------------------------------------------------------------------
# Órdenes
# --------------------------------------------------------------------------------


def _assert_montos_de_orden(orden: dict) -> None:
    for campo in ("quantityWei", "filledWei", "feeWei", "feeUsdcMin"):
        if orden.get(campo) is not None:
            assert es_monto_valido(orden[campo]), f"{campo} mal serializado: {orden[campo]!r}"


def colocar_limit(usuario, side: str, price_min: int, q_wei: int, esperado: str | None = None) -> dict:
    """POST /orders LIMIT (201) y devuelve el objeto orden de la respuesta.

    El matching es síncrono (HU-09-01 RN-5): el `status`/`filledWei` devueltos ya
    reflejan el resultado inmediato contra el libro.
    """
    resp = usuario.api.post(
        "/orders",
        json={
            "clientOrderId": client_order_id(),
            "symbol": SIMBOLO,
            "side": side,
            "type": "LIMIT",
            "priceMin": a_str(price_min),
            "quantityWei": a_str(q_wei),
        },
    )
    assert resp.status_code == 201, f"alta LIMIT {side}@{price_min} falló: {resp.text[:300]}"
    orden = resp.json()
    assert orden["side"] == side and orden["type"] == "LIMIT", orden
    assert orden["priceMin"] == a_str(price_min), orden
    assert orden["quantityWei"] == a_str(q_wei), orden
    _assert_montos_de_orden(orden)
    if esperado is not None:
        assert orden["status"] == esperado, (
            f"se esperaba status {esperado!r}, llegó {orden['status']!r}: {orden}"
        )
    return orden


def colocar_market(usuario, side: str, q_wei: int | None = None, quote_order_qty: int | None = None,
                   esperado: str | None = None) -> dict:
    """POST /orders MARKET (201, sin priceMin) por cantidad base o por monto quote."""
    cuerpo: dict = {
        "clientOrderId": client_order_id(),
        "symbol": SIMBOLO,
        "side": side,
        "type": "MARKET",
    }
    if q_wei is not None:
        cuerpo["quantityWei"] = a_str(q_wei)
    if quote_order_qty is not None:
        cuerpo["quoteOrderQty"] = a_str(quote_order_qty)
    resp = usuario.api.post("/orders", json=cuerpo)
    assert resp.status_code == 201, f"alta MARKET {side} falló: {resp.text[:300]}"
    orden = resp.json()
    assert orden["side"] == side and orden["type"] == "MARKET", orden
    assert orden.get("priceMin") is None, f"MARKET debe devolver priceMin null: {orden}"
    _assert_montos_de_orden(orden)
    if esperado is not None:
        assert orden["status"] == esperado, (
            f"se esperaba status {esperado!r}, llegó {orden['status']!r}: {orden}"
        )
    return orden


def post_orden_reintentando_429(usuario, cuerpo: dict):
    """POST /orders reintentando ante RATE_LIMITED (429).

    Para los tests masivos (≥ 100/500 órdenes, AT-03-01-05 / AT-03-05-06): el
    rate limit de la épica 09 no forma parte del veredicto sobre el motor. Un
    429 ocurre antes de procesar (HU-04-* RE-4 paso 0), así que el reintento no
    duplica efectos.
    """
    resultado: dict = {}

    def _post():
        resp = usuario.api.post("/orders", json=cuerpo)
        if resp.status_code == 429:
            return None  # esperar y reintentar
        resultado["resp"] = resp
        return True

    esperar_hasta(_post, timeout=120, mensaje="POST /orders persistentemente rate-limited")
    return resultado["resp"]


def cuerpo_market(side: str, q_wei: int | None = None, quote_order_qty: int | None = None) -> dict:
    """Cuerpo de una MARKET para los tests de error (que assertan el envelope)."""
    cuerpo: dict = {
        "clientOrderId": client_order_id(),
        "symbol": SIMBOLO,
        "side": side,
        "type": "MARKET",
    }
    if q_wei is not None:
        cuerpo["quantityWei"] = a_str(q_wei)
    if quote_order_qty is not None:
        cuerpo["quoteOrderQty"] = a_str(quote_order_qty)
    return cuerpo


def orden_actual(usuario, order_id: str) -> dict:
    resp = usuario.api.get(f"/orders/{order_id}")
    assert resp.status_code == 200, resp.text
    orden = resp.json()
    _assert_montos_de_orden(orden)
    return orden


def orden_por_client_id(usuario, cid: str) -> dict | None:
    """Busca una orden por clientOrderId (HU-09-01 RN-8: devuelve 0 o 1 items)."""
    resp = usuario.api.get("/orders", params={"clientOrderId": cid})
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) <= 1, items
    return items[0] if items else None


def cancelar_abiertas(*usuarios) -> None:
    """Limpieza final: cancela toda orden abierta (OPEN/PARTIALLY_FILLED) de cada usuario.

    Tolerante a fallas: la limpieza no debe enmascarar el veredicto del test.
    """
    for usuario in usuarios:
        try:
            for estado in ("OPEN", "PARTIALLY_FILLED"):
                resp = usuario.api.get("/orders", params={"status": estado, "limit": 200})
                if resp.status_code != 200:
                    continue
                for item in resp.json().get("items", []):
                    usuario.api.delete(f"/orders/{item['orderId']}")
        except Exception:
            pass  # best-effort


# --------------------------------------------------------------------------------
# Mercado (orderbook / trades / ticker)
# --------------------------------------------------------------------------------


def libro(api, depth: int = 200) -> dict:
    """GET /market/orderbook (200), con reintento ante RATE_LIMITED (429)."""
    def _get():
        resp = api.get("/market/orderbook", params={"depth": depth})
        if resp.status_code == 429:
            return None  # reintentar: el rate limit no es un veredicto del matching
        assert resp.status_code == 200, resp.text
        return resp.json()

    return esperar_hasta(_get, mensaje="GET /market/orderbook no respondió 200")


def nivel(libro_: dict, lado: str, price_min: int) -> int:
    """Profundidad agregada (wei) del nivel `price_min` en `bids`/`asks`; 0 si no existe."""
    for precio, cantidad in libro_[lado]:
        if assert_monto(precio) == price_min:
            return assert_monto(cantidad)
    return 0


def assert_libro_no_cruzado(libro_: dict) -> None:
    """INV-7 / HU-03-01 RN-9: bids desc, asks asc y best_bid < best_ask si ambos existen."""
    precios_bid = [assert_monto(p) for p, _ in libro_["bids"]]
    precios_ask = [assert_monto(p) for p, _ in libro_["asks"]]
    assert precios_bid == sorted(precios_bid, reverse=True), "bids no descendentes (HU-03-01 RN-2)"
    assert precios_ask == sorted(precios_ask), "asks no ascendentes (HU-03-01 RN-3)"
    if precios_bid and precios_ask:
        # Con ambos lados ordenados, best_bid < best_ask ⇔ no existe par (bid, ask) cruzado.
        assert precios_bid[0] < precios_ask[0], (
            f"libro cruzado: best_bid {precios_bid[0]} ≥ best_ask {precios_ask[0]} (INV-7)"
        )


def ticker(api) -> dict:
    resp = api.get("/market/ticker")
    assert resp.status_code == 200, resp.text
    return resp.json()


def ultimo_trade_id(api) -> str | None:
    """tradeId del trade más reciente del mercado (None si no hubo trades)."""
    resp = api.get("/market/trades", params={"limit": 1})
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    return items[0]["tradeId"] if items else None


def trades_propios(usuario, order_id: str | None = None) -> list:
    """GET /trades (pata propia) ordenados por `sequence` ascendente (orden de ejecución)."""
    params: dict = {"limit": 200}
    if order_id is not None:
        params["orderId"] = order_id
    resp = usuario.api.get("/trades", params=params)
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    for item in items:
        assert isinstance(item["sequence"], int), (
            f"sequence debe ser entero JSON (convenciones §5): {item['sequence']!r}"
        )
    return sorted(items, key=lambda t: t["sequence"])


# --------------------------------------------------------------------------------
# Precondiciones globales (el "Dado" no se puede construir ⇒ skip, no veredicto)
# --------------------------------------------------------------------------------


def requerir_libro_vacio(api) -> dict:
    libro_ = libro(api)
    if libro_["bids"] or libro_["asks"]:
        pytest.skip(
            "el orderbook global no está vacío (estado residual ajeno al test): "
            "no se puede construir el Dado del escenario"
        )
    return libro_


def requerir_lado_vacio(api, lado: str) -> None:
    if libro(api)[lado]:
        pytest.skip(
            f"el lado {lado} del orderbook global no está vacío (estado residual): "
            "no se puede construir el Dado del escenario"
        )


def requerir_sin_asks_cruzables(api, limite: int) -> None:
    """Para un BUY @ limite: no debe existir un ask ajeno con price ≤ limite (HU-03-03 RN-1)."""
    cruzables = [p for p, _ in libro(api)["asks"] if assert_monto(p) <= limite]
    if cruzables:
        pytest.skip(f"hay asks residuales cruzables a ≤ {limite}: el Dado no se cumple")


def requerir_sin_bids_cruzables(api, limite: int) -> None:
    """Para un SELL @ limite: no debe existir un bid ajeno con price ≥ limite."""
    cruzables = [p for p, _ in libro(api)["bids"] if assert_monto(p) >= limite]
    if cruzables:
        pytest.skip(f"hay bids residuales cruzables a ≥ {limite}: el Dado no se cumple")


# --------------------------------------------------------------------------------
# WebSocket (épica 09; canales público `orderbook`/`trades` y privado `orders`/`balances`)
# --------------------------------------------------------------------------------


def abrir_ws() -> ConexionWs:
    if not url_ws_configurada():
        pytest.skip("EXCHANGE_WS_URL no configurada: no hay SUT WebSocket")
    return ConexionWs()


def abrir_ws_privado(usuario, *canales: str) -> ConexionWs:
    """Conexión autenticada y suscrita a canales privados (HU-09-04 RN-1/RN-2)."""
    ws = abrir_ws()
    respuesta = ws.autenticar(usuario.token)
    assert respuesta.get("type") == "authenticated", respuesta
    for canal in canales:
        respuesta = ws.suscribir(canal, symbol=None)
        assert respuesta.get("type") == "subscribed", respuesta
    return ws


def suscribir_publico(ws: ConexionWs, canal: str, depth: int | None = None) -> dict:
    respuesta = ws.suscribir(canal, depth=depth)
    assert respuesta.get("type") == "subscribed", respuesta
    if canal == "orderbook":
        # El primer mensaje tras subscribed es el snapshot (HU-09-03 RN-3).
        return ws.recibir_hasta(lambda m: m.get("type") == "snapshot")
    return respuesta


def drenar(ws: ConexionWs, ventana: float = 2.0) -> list:
    """Acumula mensajes hasta `ventana` segundos de silencio (responde los ping)."""
    mensajes: list = []
    while True:
        try:
            mensaje = ws.recibir(timeout=ventana)
        except TimeoutError:
            return mensajes
        if mensaje.get("type") == "ping":
            ws.enviar({"type": "pong"})
            continue
        mensajes.append(mensaje)


def assert_secuencia_contigua(mensajes: list, canal: str) -> None:
    """RG-API-7 / HU-03-05 RN-7: `sequence` estrictamente creciente y contigua
    dentro de un mismo canal (nunca se compara entre canales)."""
    secuencias = [m["sequence"] for m in mensajes if m.get("channel") == canal]
    for s in secuencias:
        assert isinstance(s, int), f"sequence debe ser entero JSON: {s!r}"
    for previo, siguiente in zip(secuencias, secuencias[1:]):
        assert siguiente == previo + 1, (
            f"hueco/repetición de sequence en el canal {canal}: {previo} → {siguiente}"
        )


# --------------------------------------------------------------------------------
# Reinicio del SUT (HU-03-07) — orquestado por el evaluador
# --------------------------------------------------------------------------------


def reiniciar_sut(api) -> None:
    """Reinicia el SUT con el comando del evaluador y espera a que vuelva a responder.

    El comando debe terminar el proceso **abruptamente** (kill -9 o equivalente,
    HU-03-07 RN-1: definición operativa de durabilidad) y volver a levantarlo.
    """
    comando = os.environ.get(VAR_REINICIO_SUT, "").strip()
    if not comando:
        pytest.skip(
            f"{VAR_REINICIO_SUT} no configurada: los tests de persistencia (HU-03-07) "
            "requieren que el evaluador provea el comando de reinicio abrupto del SUT"
        )
    resultado = subprocess.run(comando, shell=True, capture_output=True, text=True, timeout=120)
    assert resultado.returncode == 0, (
        f"el comando de reinicio del SUT falló ({resultado.returncode}): "
        f"{resultado.stderr[:300]}"
    )

    def _responde() -> bool:
        try:
            return api.get("/market/ticker").status_code == 200
        except Exception:
            return False

    esperar_hasta(_responde, timeout=90, mensaje="el SUT no volvió a responder tras el reinicio")


def relogin(usuario) -> None:
    """Renueva la sesión tras un reinicio (la spec no exige que los tokens sobrevivan)."""
    usuario.token = login(usuario.api.sin_token(), usuario.email, usuario.password)
    usuario.api = usuario.api.con_token(usuario.token)
