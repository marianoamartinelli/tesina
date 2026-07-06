"""Utilidades compartidas de los tests de la épica 09 (NO es un archivo de tests).

Concentra la construcción de los "Dado" de la épica: fondeo por depósito
on-chain real (épicas 06/07), armado determinista de liquidez sobre el libro
compartido (barrido de un lado, precios dominantes) y helpers de protocolo WS
(drenaje, colección de eventos, espejo del orderbook, secuencias contiguas).

Sólo se usa la superficie black-box del SUT: REST + WebSocket de la épica 09 y
el anvil local (HELPERS.md, principio 1). El libro y el historial de trades son
globales al SUT: cada test debe dejar el libro como lo encontró (cancelar sus
órdenes resting) y, cuando necesita un lado en un estado exacto, barrerlo acá.
"""

import re
import secrets

from helpers.cuentas import crear_usuario
from helpers.espera import esperar_hasta
from helpers.montos import (
    LOT_SIZE,
    MIN_NOTIONAL,
    SIMBOLO,
    TICK_SIZE,
    WEI_POR_ETH,
    a_int,
    a_str,
    quote_min,
)

# Precio de trabajo de referencia: 2000 USDC por ETH, en price_min (USDC-min/ETH).
# Múltiplo de TICK_SIZE (activos-y-par §4.1).
PRECIO_BASE = 2_000_000_000

# Dirección externa con checksum EIP-55 válido (destino de retiros de prueba).
DESTINO_RETIRO = "0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc"

# Timestamps: string ISO-8601 UTC (HU-09-01 RN-15). Se aceptan sufijos Z o +00:00.
RE_ISO8601_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|\+00:00)$")

# Campos del objeto orden del contrato REST (HU-09-01 RN-5).
CAMPOS_ORDEN = {
    "orderId", "clientOrderId", "symbol", "side", "type", "priceMin",
    "quantityWei", "filledWei", "feeWei", "feeUsdcMin", "status",
    "createdAt", "updatedAt",
}


def es_timestamp_utc(valor) -> bool:
    """True sii `valor` es un string ISO-8601 UTC (RN-15)."""
    return isinstance(valor, str) and RE_ISO8601_UTC.fullmatch(valor) is not None


def es_entero_json(valor) -> bool:
    """True sii `valor` es un entero JSON (no bool, no string): para conteos
    como `sequence`, `confirmations`, `blockNumber` (convenciones-monetarias §5)."""
    return isinstance(valor, int) and not isinstance(valor, bool)


def id_cliente(prefijo: str = "c") -> str:
    """clientOrderId único (1..64 ASCII imprimibles, HU-09-01 RN-19)."""
    return f"{prefijo}-{secrets.token_hex(6)}"


# ------------------------------------------------------------------------------
# Balances y fondeo (el único camino black-box: depósito on-chain real, épica 07)
# ------------------------------------------------------------------------------


def balances_por_activo(usuario) -> dict:
    """GET /balances como dict asset -> {available, locked, total} (crudo)."""
    resp = usuario.api.get("/balances")
    assert resp.status_code == 200, resp.text
    return {b["asset"]: b for b in resp.json()}


def direccion_de_deposito(usuario, asset: str) -> str:
    resp = usuario.api.get("/deposit-address", params={"asset": asset})
    assert resp.status_code == 200, resp.text
    return resp.json()["address"]


def fondear_usdc(usuario, rpc, monto_usdcmin: int) -> None:
    """Acredita `monto_usdcmin` al balance interno vía depósito on-chain real
    (transfer ERC-20 + 12 confirmaciones + polling de acreditación del SUT)."""
    previo = a_int(balances_por_activo(usuario)["USDC"]["available"])
    rpc.depositar_usdc(direccion_de_deposito(usuario, "USDC"), monto_usdcmin)
    esperar_hasta(
        lambda: a_int(balances_por_activo(usuario)["USDC"]["available"])
        >= previo + monto_usdcmin,
        mensaje="el depósito USDC no se acreditó al balance interno",
    )


def fondear_eth(usuario, rpc, monto_wei: int) -> None:
    """Acredita `monto_wei` de ETH al balance interno vía depósito on-chain real."""
    previo = a_int(balances_por_activo(usuario)["ETH"]["available"])
    rpc.depositar_eth(direccion_de_deposito(usuario, "ETH"), monto_wei)
    esperar_hasta(
        lambda: a_int(balances_por_activo(usuario)["ETH"]["available"])
        >= previo + monto_wei,
        mensaje="el depósito ETH no se acreditó al balance interno",
    )


# ------------------------------------------------------------------------------
# Órdenes
# ------------------------------------------------------------------------------


def crear_orden(
    usuario,
    side: str,
    tipo: str,
    price_min: int | None = None,
    quantity_wei: int | None = None,
    client_order_id: str | None = None,
) -> dict:
    """POST /orders por el camino feliz (asserta 201) y devuelve el objeto orden.

    Los tests de error del alta llaman a la API directamente.
    """
    cuerpo: dict = {
        "clientOrderId": client_order_id or id_cliente(),
        "symbol": SIMBOLO,
        "side": side,
        "type": tipo,
    }
    if price_min is not None:
        cuerpo["priceMin"] = a_str(price_min)
    if quantity_wei is not None:
        cuerpo["quantityWei"] = a_str(quantity_wei)
    resp = usuario.api.post("/orders", json=cuerpo)
    assert resp.status_code == 201, (
        f"alta de orden falló: {resp.status_code} {resp.text[:300]}"
    )
    return resp.json()


def cancelar_silencioso(usuario, order_id) -> None:
    """Limpieza best-effort: cancela una orden propia ignorando el resultado
    (la orden puede haberse llenado o cancelado ya). Higiene del libro compartido."""
    try:
        usuario.api.delete(f"/orders/{order_id}")
    except Exception:
        pass


# ------------------------------------------------------------------------------
# Libro (orderbook compartido): lectura, precios seguros y barrido de lados
# ------------------------------------------------------------------------------


def libro(api, depth: int = 200) -> dict:
    resp = api.get("/market/orderbook", params={"depth": depth})
    assert resp.status_code == 200, resp.text
    return resp.json()


def mejor_bid(api) -> int | None:
    bids = libro(api, depth=1)["bids"]
    return a_int(bids[0][0]) if bids else None


def mejor_ask(api) -> int | None:
    asks = libro(api, depth=1)["asks"]
    return a_int(asks[0][0]) if asks else None


def cantidad_para_notional(price_min: int, notional_min: int = 2 * MIN_NOTIONAL) -> int:
    """Cantidad (wei, múltiplo de lot) cuyo notional a `price_min` es ≥ `notional_min`
    (por defecto 2× el mínimo de 10 USDC, activos-y-par §4.4)."""
    q = -(-notional_min * WEI_POR_ETH // price_min)  # ceil
    return -(-q // LOT_SIZE) * LOT_SIZE              # ceil a múltiplo de lot


def precio_dominante(api) -> int:
    """Precio (tick-aligned) estrictamente superior al mejor bid vigente.

    Un bid a este precio queda top-of-book; un ask a este precio no cruza bids.
    Para cruces deterministas usarlo con el lado ask previamente barrido.
    """
    bb = mejor_bid(api)
    if bb is None:
        return PRECIO_BASE
    return max(PRECIO_BASE, bb + 10 * TICK_SIZE)


def precio_bid_seguro(api) -> int:
    """Precio para un bid que quede resting (estrictamente menor al mejor ask)."""
    ba = mejor_ask(api)
    if ba is None:
        return 1_000_000_000  # 1000 USDC: sin asks, ningún bid cruza
    p = min(1_000_000_000, ba - 10 * TICK_SIZE)
    assert p >= TICK_SIZE, f"no hay lugar debajo del mejor ask ({ba}) para un bid resting"
    return p


def _cancelar_remanente(usuario, orden: dict) -> None:
    if orden["status"] in ("OPEN", "PARTIALLY_FILLED"):
        cancelar_silencioso(usuario, orden["orderId"])


def barrer_asks(api, rpc) -> None:
    """Deja el lado ask del libro vacío comprando toda su profundidad.

    Usa un usuario barrendero fresco por pasada (evita self-trade y el rate
    limit por cuenta). Necesario para construir "Dado" deterministas: sin asks,
    un ask propio nuevo es el único/mejor ask del libro.
    """
    for _ in range(10):
        asks = libro(api)["asks"]
        if not asks:
            return
        total_q = sum(a_int(q) for _, q in asks)
        p_max = a_int(asks[-1][0])
        # cantidad ≥ profundidad total y ≥ min notional al precio límite
        q = max(total_q, cantidad_para_notional(p_max))
        barrendero = crear_usuario(api, "at09-barre")
        fondear_usdc(barrendero, rpc, quote_min(q, p_max) + MIN_NOTIONAL)
        orden = crear_orden(barrendero, "BUY", "LIMIT", price_min=p_max, quantity_wei=q)
        _cancelar_remanente(barrendero, orden)  # el sobrante no debe quedar como bid
    raise AssertionError("no se pudo vaciar el lado ask del libro en 10 pasadas")


def barrer_bids(api, rpc) -> None:
    """Deja el lado bid del libro vacío vendiéndole toda su profundidad."""
    for _ in range(10):
        bids = libro(api)["bids"]
        if not bids:
            return
        total_q = sum(a_int(q) for _, q in bids)
        p_min = a_int(bids[-1][0])  # bids descendentes: el último es el peor
        q = max(total_q, cantidad_para_notional(p_min))
        barrendero = crear_usuario(api, "at09-barre")
        fondear_eth(barrendero, rpc, q)
        orden = crear_orden(barrendero, "SELL", "LIMIT", price_min=p_min, quantity_wei=q)
        _cancelar_remanente(barrendero, orden)  # el sobrante no debe quedar como ask
    raise AssertionError("no se pudo vaciar el lado bid del libro en 10 pasadas")


def colocar_ask_dominante(usuario, api, rpc, q_wei: int | None = None, precio: int | None = None):
    """Ask resting del `usuario` que queda como MEJOR ask del libro.

    Requiere el lado ask barrido (barrer_asks) para que sea determinista: el
    próximo taker BUY a ese precio cruza contra este ask y contra ningún otro.
    Devuelve (orden, price_min, q_wei). Fondea el ETH necesario.
    """
    p = precio if precio is not None else precio_dominante(api)
    q = q_wei if q_wei is not None else cantidad_para_notional(p)
    fondear_eth(usuario, rpc, q)
    orden = crear_orden(usuario, "SELL", "LIMIT", price_min=p, quantity_wei=q)
    assert orden["status"] == "OPEN", orden
    return orden, p, q


def tomar_con_buy(usuario, rpc, p: int, q_wei: int) -> dict:
    """Taker BUY LIMIT a precio `p` por `q_wei` (fondea el USDC necesario)."""
    fondear_usdc(usuario, rpc, quote_min(q_wei, p) + MIN_NOTIONAL)
    return crear_orden(usuario, "BUY", "LIMIT", price_min=p, quantity_wei=q_wei)


# ------------------------------------------------------------------------------
# WebSocket: drenaje, colección, secuencias y espejo del orderbook
# ------------------------------------------------------------------------------


def drenar(ws, ventana: float = 2.0) -> list[dict]:
    """Recibe todo lo que llegue durante `ventana` segundos (respondiendo los
    ping del heartbeat) y lo devuelve. No falla si no llega nada."""
    mensajes: list[dict] = []
    try:
        while True:
            m = ws.recibir(timeout=ventana)
            if m.get("type") == "ping":
                ws.enviar({"type": "pong"})
                continue
            mensajes.append(m)
    except TimeoutError:
        return mensajes


def recolectar_hasta(ws, predicado_fin, timeout: float | None = None) -> list[dict]:
    """Acumula mensajes (sin pings) hasta que uno cumpla `predicado_fin`
    inclusive; lo acumulado se devuelve completo. TimeoutError si no llega."""
    mensajes: list[dict] = []

    def pred(m):
        mensajes.append(m)
        return predicado_fin(m)

    ws.recibir_hasta(pred, timeout=timeout)
    return mensajes


def assert_secuencia_contigua(mensajes: list[dict], contexto: str = "canal") -> None:
    """`sequence` de los mensajes de UN MISMO canal: enteros JSON, estrictamente
    crecientes y contiguos (RG-API-7; HU-09-03 RN-5, HU-09-04 RN-8)."""
    seqs = []
    for m in mensajes:
        assert "sequence" in m, f"{contexto}: mensaje sin sequence: {m!r}"
        assert es_entero_json(m["sequence"]), (
            f"{contexto}: sequence debe ser entero JSON, llegó {m['sequence']!r}"
        )
        seqs.append(m["sequence"])
    for previo, siguiente in zip(seqs, seqs[1:]):
        assert siguiente == previo + 1, (
            f"{contexto}: sequence no contigua: {previo} → {siguiente} (todas: {seqs})"
        )


def contiene_clave(obj, claves: set[str]) -> bool:
    """True si alguna clave de `claves` aparece en cualquier nivel del objeto JSON."""
    if isinstance(obj, dict):
        if any(k in obj for k in claves):
            return True
        return any(contiene_clave(v, claves) for v in obj.values())
    if isinstance(obj, list):
        return any(contiene_clave(v, claves) for v in obj)
    return False


def espejo_de_snapshot(snapshot: dict) -> dict:
    """Copia local del libro a partir de un snapshot (WS o REST):
    {"bids": {price_min:int -> q_wei:int}, "asks": {...}}."""
    return {
        lado: {a_int(p): a_int(q) for p, q in snapshot[lado]}
        for lado in ("bids", "asks")
    }


def aplicar_delta(espejo: dict, delta: dict) -> None:
    """Aplica un mensaje `update` sobre el espejo: cada entrada [priceMin,
    quantityWei] es el NUEVO total del nivel; "0" elimina el nivel (RN-4)."""
    for lado in ("bids", "asks"):
        for p, q in delta.get(lado, []):
            precio, cantidad = a_int(p), a_int(q)
            if cantidad == 0:
                espejo[lado].pop(precio, None)
            else:
                espejo[lado][precio] = cantidad


def niveles_top(espejo: dict, lado: str, n: int) -> list[tuple[int, int]]:
    """Top-`n` niveles de un lado del espejo, en el orden del contrato
    (bids descendente, asks ascendente; HU-09-01 RN-12)."""
    reverso = lado == "bids"
    return sorted(espejo[lado].items(), key=lambda kv: kv[0], reverse=reverso)[:n]


def assert_espejos_equivalentes(e1: dict, e2: dict, profundidad: int) -> None:
    """Compara dos espejos del libro hasta `profundidad` niveles por lado."""
    for lado in ("bids", "asks"):
        n1 = niveles_top(e1, lado, profundidad)
        n2 = niveles_top(e2, lado, profundidad)
        assert n1 == n2, f"espejos difieren en {lado}: {n1} != {n2}"


def niveles_bid_frescos(espejo: dict, precio_base: int, n: int) -> list[int]:
    """`n` precios tick-aligned ≤ `precio_base` que NO existen como nivel bid en
    el espejo (para observar niveles nuevos/eliminados sin interferencia)."""
    niveles: list[int] = []
    p = precio_base
    while len(niveles) < n:
        assert p >= TICK_SIZE, "no quedan precios positivos para niveles frescos"
        if p not in espejo["bids"]:
            niveles.append(p)
        p -= TICK_SIZE
    return niveles
