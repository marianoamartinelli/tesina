"""Épica 03 / HU-03-06 — Prevención de auto-cruce (STP): tests black-box.

Política fijada por la spec: **rechazo atómico total de la orden entrante**
(cancel-incoming, whole-order): si el rango consumible contiene al menos una
orden propia, la entrante se rechaza íntegra con `SELF_TRADE_BLOCKED` (422),
sin ningún fill (tampoco contra terceros), sin posar remanente y con los
fondos reservados revertidos (RN-3..RN-7). Se observa por el envelope de error,
`details.restingOrderId`, la inmutabilidad del libro y de los balances, y la
ausencia de trades.
"""

import pytest

from helpers.errores import assert_error
from helpers.montos import WEI_POR_ETH, a_str, assert_monto

from tests.comunes_ep03 import (
    cancelar_abiertas,
    client_order_id,
    colocar_limit,
    cuerpo_market,
    fondear,
    libro,
    nivel,
    orden_actual,
    orden_por_client_id,
    requerir_lado_vacio,
    requerir_sin_asks_cruzables,
    requerir_sin_bids_cruzables,
    snapshot_balances,
    trades_propios,
    ultimo_trade_id,
)

ETH = WEI_POR_ETH


def _enviar_buy_limit(usuario, precio: int, q_wei: int, cid: str | None = None):
    """POST /orders BUY LIMIT sin assertar éxito (para los casos de rechazo STP)."""
    return usuario.api.post(
        "/orders",
        json={
            "clientOrderId": cid or client_order_id(),
            "symbol": "ETH-USDC",
            "side": "BUY",
            "type": "LIMIT",
            "priceMin": a_str(precio),
            "quantityWei": a_str(q_wei),
        },
    )


@pytest.mark.at("AT-03-06-01")
def test_cruce_normal_contra_terceros_sin_self_trade(api, usuario, usuario_b, rpc):
    """HU-03-06 Escenario 1: Cruce normal contra terceros (sin self-trade).

    - Dado un ask SELL 1 ETH @ 2185.00 de la cuenta U2
    - Cuando U1 envía BUY 1 ETH @ 2185.00
    - Entonces el rango consumible no contiene órdenes de U1: no hay STP y el
      cruce se ejecuta normalmente (RN-1, RN-2); la orden de U1 queda FILLED
    """
    precio = 2_185_000_000
    requerir_sin_asks_cruzables(api, precio)
    requerir_sin_bids_cruzables(api, precio)
    fondear(usuario_b, rpc, eth_wei=ETH)
    fondear(usuario, rpc, usdc_min=2_200_000_000)
    try:
        # Dado
        ajena = colocar_limit(usuario_b, "SELL", precio, ETH, esperado="OPEN")

        # Cuando / Entonces
        taker = colocar_limit(usuario, "BUY", precio, ETH, esperado="FILLED")
        assert taker["filledWei"] == a_str(ETH)
        assert orden_actual(usuario_b, ajena["orderId"])["status"] == "FILLED"
    finally:
        cancelar_abiertas(usuario, usuario_b)


@pytest.mark.at("AT-03-06-02")
def test_auto_cruce_en_el_frente_rechazo_atomico(api, usuario, rpc):
    """HU-03-06 Escenario 2: Auto-cruce en el frente — rechazo atómico.

    - Dado que el best ask SELL 1 ETH @ 2190.00 pertenece a U1 (orderId = A)
    - Cuando U1 envía BUY 1 ETH @ 2190.00 (cruzaría A)
    - Entonces se rechaza con SELF_TRADE_BLOCKED (422) y
      details.restingOrderId = A (RN-3, RN-4)
    - Y no hay fills, A queda intacta y la entrante queda REJECTED (RN-5)
    - Y los fondos reservados se liberan; balances idénticos al estado previo (RN-6)
    """
    precio = 2_190_000_000
    requerir_sin_asks_cruzables(api, precio)
    requerir_sin_bids_cruzables(api, precio)
    fondear(usuario, rpc, eth_wei=ETH, usdc_min=2_200_000_000)
    try:
        # Dado
        propia = colocar_limit(usuario, "SELL", precio, ETH, esperado="OPEN")
        antes = snapshot_balances(usuario)
        libro_previo = libro(api)
        trade_previo = ultimo_trade_id(api)

        # Cuando
        cid = client_order_id("ep03-stp2")
        resp = _enviar_buy_limit(usuario, precio, ETH, cid=cid)

        # Entonces: rechazo con la referencia a la orden propia del frente (RN-4)
        err = assert_error(resp, "SELF_TRADE_BLOCKED")
        assert err["details"]["restingOrderId"] == propia["orderId"]

        # Y: sin fills; A intacta; la entrante no está abierta (terminal REJECTED, RN-5)
        assert ultimo_trade_id(api) == trade_previo
        estado_a = orden_actual(usuario, propia["orderId"])
        assert estado_a["status"] == "OPEN" and estado_a["filledWei"] == "0"
        registrada = orden_por_client_id(usuario, cid)
        if registrada is not None:  # se persiste como REJECTED (HU-04-05/HU-04-07)
            assert registrada["status"] == "REJECTED"
        assert nivel(libro(api), "bids", precio) == 0  # no posó remanente (RN-3)

        # Y: balances y libro idénticos al estado previo (RN-6, INV-4)
        assert snapshot_balances(usuario) == antes
        actual = libro(api)
        assert actual["bids"] == libro_previo["bids"] and actual["asks"] == libro_previo["asks"]
    finally:
        cancelar_abiertas(usuario)


@pytest.mark.at("AT-03-06-03")
def test_orden_propia_dentro_del_rango_tras_una_de_terceros(api, usuario, usuario_b, rpc):
    """HU-03-06 Escenario 3 (borde): Orden propia dentro del rango, tras una de terceros.

    - Dado asks al mismo nivel 2195.00: A1 de U2 (1º) y A2 de U1 (2º)
    - Cuando U1 envía BUY 1 ETH @ 2195.00 (rango consumible = {A1, A2})
    - Entonces se rechaza TODA la entrante con SELF_TRADE_BLOCKED y
      details.restingOrderId = A2 (RN-2, RN-3, RN-7)
    - Y A1 (de U2) NO se ejecuta; el libro queda idéntico (INV-4)
    """
    precio = 2_195_000_000
    requerir_sin_asks_cruzables(api, precio)
    requerir_sin_bids_cruzables(api, precio)
    fondear(usuario_b, rpc, eth_wei=ETH)
    fondear(usuario, rpc, eth_wei=ETH, usdc_min=2_300_000_000)
    try:
        # Dado
        a1 = colocar_limit(usuario_b, "SELL", precio, ETH // 2, esperado="OPEN")
        a2 = colocar_limit(usuario, "SELL", precio, ETH // 2, esperado="OPEN")
        libro_previo = libro(api)
        trade_previo = ultimo_trade_id(api)

        # Cuando: la entrante consumiría A1 y A2 (1 ETH = 0.5 + 0.5)
        resp = _enviar_buy_limit(usuario, precio, ETH)

        # Entonces: rechazo íntegro señalando la propia (no la de mayor prioridad
        # del nivel, que es ajena) (RN-4)
        err = assert_error(resp, "SELF_TRADE_BLOCKED")
        assert err["details"]["restingOrderId"] == a2["orderId"]

        # Y: A1 tampoco se ejecutó (RN-7); libro idéntico (RN-3, INV-4)
        assert ultimo_trade_id(api) == trade_previo
        assert orden_actual(usuario_b, a1["orderId"])["status"] == "OPEN"
        assert orden_actual(usuario, a2["orderId"])["status"] == "OPEN"
        actual = libro(api)
        assert actual["bids"] == libro_previo["bids"] and actual["asks"] == libro_previo["asks"]
    finally:
        cancelar_abiertas(usuario, usuario_b)


@pytest.mark.at("AT-03-06-04")
def test_orden_propia_fuera_del_rango_no_dispara_stp(api, usuario, usuario_b, rpc):
    """HU-03-06 Escenario 4 (borde): Orden propia fuera del rango consumible.

    - Dado asks: A1 SELL 1 ETH @ 2200.00 de U2 y A2 SELL 1 ETH @ 2200.50 de U1
    - Cuando U1 envía BUY 1 ETH @ 2200.00
    - Entonces el rango consumible es solo {A1} (A2 no es cruzable a L): no hay
      self-trade (RN-2)
    - Y la entrante ejecuta contra A1 y queda FILLED; A2 sigue intacta
    """
    p1, p2 = 2_200_000_000, 2_200_500_000
    requerir_sin_asks_cruzables(api, p2)
    requerir_sin_bids_cruzables(api, p1)
    fondear(usuario_b, rpc, eth_wei=ETH)
    fondear(usuario, rpc, eth_wei=ETH, usdc_min=2_300_000_000)
    try:
        # Dado
        a1 = colocar_limit(usuario_b, "SELL", p1, ETH, esperado="OPEN")
        a2 = colocar_limit(usuario, "SELL", p2, ETH, esperado="OPEN")

        # Cuando: L = 2200.00 < precio de A2 ⇒ A2 fuera del rango (RN-2)
        taker = colocar_limit(usuario, "BUY", p1, ETH, esperado="FILLED")

        # Entonces: ejecutó 1 ETH contra A1, al precio de A1
        fills = trades_propios(usuario, order_id=taker["orderId"])
        assert len(fills) == 1 and assert_monto(fills[0]["priceMin"]) == p1
        assert orden_actual(usuario_b, a1["orderId"])["status"] == "FILLED"

        # Y: A2 propia sigue en el libro, sin tocar
        estado_a2 = orden_actual(usuario, a2["orderId"])
        assert estado_a2["status"] == "OPEN" and estado_a2["filledWei"] == "0"
        assert nivel(libro(api), "asks", p2) == ETH
    finally:
        cancelar_abiertas(usuario, usuario_b)


@pytest.mark.at("AT-03-06-05")
def test_limit_propia_no_cruzable_se_posa_con_ordenes_propias_del_otro_lado(api, usuario, rpc):
    """HU-03-06 Escenario 5 (borde): LIMIT propia no cruzable se posa con órdenes
    propias del otro lado.

    - Dado que U1 ya tiene SELL 1 ETH @ 2206.00 en asks
    - Cuando U1 envía BUY 1 ETH @ 2205.00 (L < 2206.00, no cruza)
    - Entonces no hay rango consumible y la BUY se posa normalmente; tener
      órdenes propias en ambos lados sin solapar es lícito (RN-8, RN-10)
    """
    precio_ask, precio_bid = 2_206_000_000, 2_205_000_000
    requerir_sin_asks_cruzables(api, precio_bid)
    requerir_sin_bids_cruzables(api, precio_ask)
    fondear(usuario, rpc, eth_wei=ETH, usdc_min=2_300_000_000)
    try:
        # Dado
        venta = colocar_limit(usuario, "SELL", precio_ask, ETH, esperado="OPEN")

        # Cuando: BUY propia que NO cruza su propio ask
        compra = colocar_limit(usuario, "BUY", precio_bid, ETH, esperado="OPEN")

        # Entonces: ambas conviven abiertas, cada una en su lado (RN-10)
        lib = libro(api)
        assert nivel(lib, "asks", precio_ask) == ETH
        assert nivel(lib, "bids", precio_bid) == ETH
        assert orden_actual(usuario, venta["orderId"])["status"] == "OPEN"
        assert orden_actual(usuario, compra["orderId"])["status"] == "OPEN"
    finally:
        cancelar_abiertas(usuario)


@pytest.mark.at("AT-03-06-06")
def test_market_con_contraparte_propia(api, usuario, rpc):
    """HU-03-06 Escenario 6: MARKET con contraparte propia.

    - Dado que el único ask del libro pertenece a U1 (orderId = A)
    - Cuando U1 envía MARKET BUY 1 ETH
    - Entonces se rechaza con SELF_TRADE_BLOCKED (422),
      details.restingOrderId = A, sin fills (RN-8)
    - Y NO se reporta MARKET_NO_LIQUIDITY: hay liquidez, sólo que es propia
      (RN-4, precedencia)
    """
    precio = 2_210_000_000
    requerir_lado_vacio(api, "asks")  # "el único ask del libro"
    fondear(usuario, rpc, eth_wei=ETH, usdc_min=2_300_000_000)
    try:
        # Dado
        propia = colocar_limit(usuario, "SELL", precio, ETH, esperado="OPEN")
        trade_previo = ultimo_trade_id(api)

        # Cuando
        resp = usuario.api.post("/orders", json=cuerpo_market("BUY", q_wei=ETH))

        # Entonces: STP con precedencia sobre MARKET_NO_LIQUIDITY (RN-4);
        # assert_error exige el code exacto, por lo que descarta NO_LIQUIDITY
        err = assert_error(resp, "SELF_TRADE_BLOCKED")
        assert err["details"]["restingOrderId"] == propia["orderId"]
        assert ultimo_trade_id(api) == trade_previo
        assert orden_actual(usuario, propia["orderId"])["status"] == "OPEN"
    finally:
        cancelar_abiertas(usuario)


@pytest.mark.at("AT-03-06-07")
def test_atomicidad_e_idempotencia_del_rechazo(api, usuario, rpc):
    """HU-03-06 Escenario 7 (integridad): Atomicidad e idempotencia del rechazo.

    - Dado un libro con una orden propia en el rango consumible de la entrante
    - Cuando se procesa la entrante (incluso reintentada)
    - Entonces cada intento deja libro y balances exactamente iguales al estado
      previo (RN-3, INV-4), sin fills ni eventos trade
    - Y el restingOrderId reportado es siempre el mismo (determinismo, RN-9)
    """
    precio = 2_215_000_000
    requerir_sin_asks_cruzables(api, precio)
    requerir_sin_bids_cruzables(api, precio)
    fondear(usuario, rpc, eth_wei=ETH, usdc_min=2_300_000_000)
    try:
        # Dado
        propia = colocar_limit(usuario, "SELL", precio, ETH, esperado="OPEN")
        antes = snapshot_balances(usuario)
        libro_previo = libro(api)
        trade_previo = ultimo_trade_id(api)

        resting_ids = []
        for _ in range(2):  # el reintento usa otro clientOrderId (la idempotencia
            # de alta es de la épica 04; acá se verifica el determinismo del motor)
            # Cuando
            resp = _enviar_buy_limit(usuario, precio, ETH)

            # Entonces: mismo rechazo, sin efectos (RN-3, RN-9, INV-4)
            err = assert_error(resp, "SELF_TRADE_BLOCKED")
            resting_ids.append(err["details"]["restingOrderId"])
            assert snapshot_balances(usuario) == antes
            actual = libro(api)
            assert actual["bids"] == libro_previo["bids"]
            assert actual["asks"] == libro_previo["asks"]
            assert ultimo_trade_id(api) == trade_previo

        # Y: determinismo del restingOrderId (RN-9)
        assert resting_ids == [propia["orderId"], propia["orderId"]]
    finally:
        cancelar_abiertas(usuario)


@pytest.mark.at("AT-03-06-08")
def test_lado_opuesto_con_varios_niveles_todos_propios(api, usuario, rpc):
    """HU-03-06 Escenario 8 (borde): Lado opuesto con varios niveles, todos propios.

    - Dado que TODO el lado de asks pertenece a U1: A1 SELL 0.5 @ 2220.00 (1º) y
      A2 SELL 0.5 @ 2220.50 (2º)
    - Cuando U1 envía MARKET BUY 1 ETH (rango consumible = {A1, A2})
    - Entonces se rechaza con SELF_TRADE_BLOCKED (422) y
      details.restingOrderId = A1 (la propia de MAYOR prioridad) (RN-3, RN-4)
    - Y NO se reporta MARKET_NO_LIQUIDITY; el libro queda idéntico (INV-4)
    """
    p1, p2 = 2_220_000_000, 2_220_500_000
    requerir_lado_vacio(api, "asks")  # todo el lado debe ser propio
    fondear(usuario, rpc, eth_wei=ETH, usdc_min=2_300_000_000)
    try:
        # Dado
        a1 = colocar_limit(usuario, "SELL", p1, ETH // 2, esperado="OPEN")
        a2 = colocar_limit(usuario, "SELL", p2, ETH // 2, esperado="OPEN")
        libro_previo = libro(api)

        # Cuando
        resp = usuario.api.post("/orders", json=cuerpo_market("BUY", q_wei=ETH))

        # Entonces: STP (no NO_LIQUIDITY) con la propia de mayor prioridad (RN-4)
        err = assert_error(resp, "SELF_TRADE_BLOCKED")
        assert err["details"]["restingOrderId"] == a1["orderId"]

        # Y: sin fills; libro idéntico (INV-4)
        assert orden_actual(usuario, a1["orderId"])["status"] == "OPEN"
        assert orden_actual(usuario, a2["orderId"])["status"] == "OPEN"
        actual = libro(api)
        assert actual["bids"] == libro_previo["bids"] and actual["asks"] == libro_previo["asks"]
    finally:
        cancelar_abiertas(usuario)
