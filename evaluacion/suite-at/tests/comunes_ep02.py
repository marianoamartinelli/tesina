"""Helpers compartidos de los tests de la épica 02 (balances y ledger).

Convenciones de precio de este módulo (el orderbook del SUT es compartido entre
tests; par único ETH-USDC):

- ``PRECIO_BANDA_BAJA``: bids resting que NO deben ejecutar (ningún test de la
  épica deja asks por debajo de la banda de matching).
- ``PRECIO_BANDA_ALTA``: asks resting que NO deben ejecutar.
- ``PRECIO_MATCHING``:   banda central para fills controlados (los valores de la
  spec: 2000.00 USDC/ETH). Todo test que deje una orden resting en esta banda la
  cancela al terminar (``cancelar_si_posible`` en un ``finally``).

El único camino black-box para fondear una cuenta interna es el depósito
on-chain acreditado (épicas 06+07): ``fondear_eth`` / ``fondear_usdc`` depositan
vía el nodo anvil del entorno y esperan la acreditación (HELPERS.md).
"""

import secrets

from helpers.espera import esperar_hasta
from helpers.montos import a_int, a_str, assert_monto

SIMBOLO = "ETH-USDC"

# Bandas de precio (price_min, USDC-min por ETH; múltiplos del tick 10_000).
PRECIO_BANDA_BAJA = 1_000_000_000   # 1000.00 USDC/ETH
PRECIO_BANDA_ALTA = 9_000_000_000   # 9000.00 USDC/ETH
PRECIO_MATCHING = 2_000_000_000     # 2000.00 USDC/ETH (valor canónico de la spec)

# Dirección externa con checksum EIP-55 válido (misma que usa HELPERS.md).
DESTINO_RETIRO = "0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc"

# Intervalo de polling conservador: el rate limit es 60 req/min por cuenta y
# endpoint (HU-09-02 RN-12); a 1.5 s el polling queda en ~40 req/min.
INTERVALO_POLL_SEGUNDOS = 1.5


def nuevo_client_order_id(prefijo: str = "ep02") -> str:
    """clientOrderId único (1..64 ASCII imprimibles, HU-09-01 RN-19)."""
    return f"{prefijo}-{secrets.token_hex(8)}"


# --------------------------------------------------------------------------------
# Balances (HU-02-01)
# --------------------------------------------------------------------------------


def balances_por_activo(usuario) -> dict:
    """GET /balances validando en cada lectura las propiedades transversales:

    - serialización de montos como string ``^(0|[1-9][0-9]*)$`` (HU-02-01 RN-7);
    - no-negatividad (INV-2; implícita en el patrón, que excluye negativos);
    - partición ``total == available + locked`` (INV-3, HU-02-01 RN-5);
    - presencia de exactamente los dos activos del par (HU-02-01 RN-3).

    Devuelve ``{"ETH": item, "USDC": item}``.
    """
    resp = usuario.api.get("/balances")
    assert resp.status_code == 200, (
        f"GET /balances falló: {resp.status_code} {resp.text[:300]}"
    )
    cuerpo = resp.json()
    assert isinstance(cuerpo, list), f"se esperaba un arreglo de balances: {cuerpo!r}"
    por_activo: dict = {}
    for item in cuerpo:
        activo = item["asset"]
        disponible = assert_monto(item["available"], f"{activo}.available")
        bloqueado = assert_monto(item["locked"], f"{activo}.locked")
        total = assert_monto(item["total"], f"{activo}.total")
        assert total == disponible + bloqueado, (
            f"INV-3 violado en {activo}: total {total} != "
            f"available {disponible} + locked {bloqueado}"
        )
        por_activo[activo] = item
    assert set(por_activo) == {"ETH", "USDC"}, (
        f"la respuesta debe enumerar exactamente ETH y USDC (HU-02-01 RN-3): "
        f"{sorted(por_activo)}"
    )
    return por_activo


def balance(usuario, asset: str) -> dict:
    """El item de balance de un activo (ya validado por ``balances_por_activo``)."""
    return balances_por_activo(usuario)[asset]


def total_de(usuario, asset: str) -> int:
    return a_int(balance(usuario, asset)["total"])


# --------------------------------------------------------------------------------
# Fondeo black-box vía depósito on-chain (épicas 06+07)
# --------------------------------------------------------------------------------


def direccion_deposito(usuario, asset: str) -> str:
    resp = usuario.api.get("/deposit-address", params={"asset": asset})
    assert resp.status_code == 200, (
        f"GET /deposit-address falló: {resp.status_code} {resp.text[:300]}"
    )
    return resp.json()["address"]


def fondear_usdc(usuario, rpc, monto_usdcmin: int) -> None:
    """Deposita USDC (mint + transfer + 12 confirmaciones) hasta verlo acreditado.

    Pensado para usuarios frescos (parten de disponible 0): espera
    ``available >= monto`` y el test asserta después el valor exacto.
    """
    direccion = direccion_deposito(usuario, "USDC")
    rpc.depositar_usdc(direccion, monto_usdcmin)
    esperar_hasta(
        lambda: a_int(balance(usuario, "USDC")["available"]) >= monto_usdcmin,
        intervalo=INTERVALO_POLL_SEGUNDOS,
        mensaje=f"el depósito de {monto_usdcmin} USDC-min no se acreditó",
    )


def fondear_eth(usuario, rpc, monto_wei: int) -> None:
    """Deposita ETH nativo (transfer + 12 confirmaciones) hasta verlo acreditado."""
    direccion = direccion_deposito(usuario, "ETH")
    rpc.depositar_eth(direccion, monto_wei)
    esperar_hasta(
        lambda: a_int(balance(usuario, "ETH")["available"]) >= monto_wei,
        intervalo=INTERVALO_POLL_SEGUNDOS,
        mensaje=f"el depósito de {monto_wei} wei no se acreditó",
    )


# --------------------------------------------------------------------------------
# Órdenes (contrato HU-09-01 RN-4/RN-5/RN-7)
# --------------------------------------------------------------------------------


def crear_orden(usuario, side: str, tipo: str, quantity_wei: int,
                price_min: int | None = None, client_order_id: str | None = None):
    """POST /orders. Devuelve la respuesta cruda (para tests de error)."""
    payload = {
        "clientOrderId": client_order_id or nuevo_client_order_id(),
        "symbol": SIMBOLO,
        "side": side,
        "type": tipo,
        "quantityWei": a_str(quantity_wei),
    }
    if price_min is not None:
        payload["priceMin"] = a_str(price_min)
    return usuario.api.post("/orders", json=payload)


def orden_creada(usuario, side: str, tipo: str, quantity_wei: int,
                 price_min: int | None = None, client_order_id: str | None = None) -> dict:
    """Alta de orden asumiendo camino feliz (201). Devuelve el objeto orden."""
    resp = crear_orden(usuario, side, tipo, quantity_wei, price_min, client_order_id)
    assert resp.status_code == 201, (
        f"alta de orden falló: {resp.status_code} {resp.text[:300]}"
    )
    return resp.json()


def orden_resting(usuario, side: str, quantity_wei: int, price_min: int) -> dict:
    """Alta de orden LIMIT que DEBE quedar pasiva en el libro (Dado de los tests)."""
    orden = orden_creada(usuario, side, "LIMIT", quantity_wei, price_min)
    assert orden["status"] == "OPEN" and orden["filledWei"] == "0", (
        f"la orden debía quedar resting sin fills; llegó status={orden['status']!r}, "
        f"filledWei={orden['filledWei']!r} (¿libro contaminado por otro test?)"
    )
    return orden


def detalle_orden(usuario, order_id: str) -> dict:
    resp = usuario.api.get(f"/orders/{order_id}")
    assert resp.status_code == 200, (
        f"GET /orders/{order_id} falló: {resp.status_code} {resp.text[:300]}"
    )
    return resp.json()


def cancelar_orden(usuario, order_id: str) -> dict:
    """DELETE /orders/{id} asumiendo camino feliz (200, estado CANCELLED)."""
    resp = usuario.api.delete(f"/orders/{order_id}")
    assert resp.status_code == 200, (
        f"cancelación falló: {resp.status_code} {resp.text[:300]}"
    )
    cuerpo = resp.json()
    assert cuerpo["status"] == "CANCELLED", cuerpo
    return cuerpo


def cancelar_si_posible(usuario, order_id: str) -> None:
    """Cleanup best-effort: cancela sin assertar (para ``finally`` de los tests
    que dejan órdenes resting en la banda de matching)."""
    try:
        usuario.api.delete(f"/orders/{order_id}")
    except Exception:
        pass


def pata_propia_del_fill(usuario, order_id: str) -> dict:
    """Primera pata propia del trade de una orden (GET /trades?orderId=...,
    HU-09-01 RN-20): expone feeAsset/feeAmount, la vía black-box para observar
    la fee que el settlement acredita a EX."""
    def _buscar():
        resp = usuario.api.get("/trades", params={"orderId": order_id})
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        return items[0] if items else None

    return esperar_hasta(
        _buscar,
        intervalo=INTERVALO_POLL_SEGUNDOS,
        mensaje=f"sin trade propio para la orden {order_id}",
    )


# --------------------------------------------------------------------------------
# Retiros (contrato HU-09-01 RN-11/RN-18)
# --------------------------------------------------------------------------------


def crear_retiro(usuario, asset: str, amount_min_unit: int, address: str = DESTINO_RETIRO):
    """POST /withdrawals. Devuelve la respuesta cruda."""
    return usuario.api.post(
        "/withdrawals",
        json={"asset": asset, "amountMinUnit": a_str(amount_min_unit), "address": address},
    )


def detalle_retiro(usuario, withdrawal_id: str) -> dict:
    resp = usuario.api.get(f"/withdrawals/{withdrawal_id}")
    assert resp.status_code == 200, (
        f"GET /withdrawals/{withdrawal_id} falló: {resp.status_code} {resp.text[:300]}"
    )
    return resp.json()
