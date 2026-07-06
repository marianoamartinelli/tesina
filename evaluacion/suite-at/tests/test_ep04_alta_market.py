"""Épica 04 — HU-04-02 Colocar orden market: tests de aceptación black-box.

Spec: spec/04-gestion-de-ordenes/HU-04-02-colocar-orden-market.md
La forma de tamaño por monto es `quoteOrderQtyMin` (nombre canónico del body de
POST /orders, HU-09-01 RN-4; adoptado por la épica 04 en spec-v1.1, ADR-006 D8).
"""

import pytest

from helpers.errores import assert_error, assert_montos_en_details
from helpers.montos import fee_taker

from comunes_ep04 import (  # noqa: F401 (limpiador es fixture)
    ETH_1,
    P2000,
    Q_MIN,
    abiertas,
    alta_ok,
    assert_balances,
    assert_montos_de_orden,
    buscar_por_client_id,
    cantidad_en_nivel,
    client_order_id,
    cuerpo_orden,
    detalle,
    ejecutado_wei,
    fondear,
    historial,
    items_por_estado,
    limpiador,
    post_orden,
    requerir_lado_vacio,
    requerir_sin_asks_hasta,
    requerir_zona_limpia,
)


@pytest.mark.at("AT-04-02-01")
def test_compra_market_por_monto_que_ejecuta_totalmente(usuario, usuario_b, rpc, api, limpiador):
    """HU-04-02 Escenario 1: Compra market por monto que ejecuta totalmente."""
    # Dado asks resting ajenos suficientes a 2000000000 (1.2 ETH > presupuesto)
    requerir_zona_limpia(api, P2000)
    fondear(usuario_b, rpc, eth_wei=1_200_000_000_000_000_000)
    ask = alta_ok(
        usuario_b,
        cuerpo_orden("SELL", "LIMIT", P2000, 1_200_000_000_000_000_000),
        estado="OPEN",
    )
    limpiador.registrar(usuario_b, ask["orderId"])
    # Y un trader con disponible(USDC) = 5000000000
    fondear(usuario, rpc, usdc_min=5_000_000_000)

    # Cuando coloca BUY MARKET quoteOrderQtyMin="2000000000" (gastar 2000 USDC)
    orden = alta_ok(usuario, cuerpo_orden("BUY", "MARKET", quote_order_qty_min=2_000_000_000))

    # Entonces bloquea R = 2000000000, ejecuta como taker y queda FILLED (RN-5, RN-7)
    assert orden["status"] == "FILLED", orden
    # Y filledWei reporta la base comprada (2000 USDC a 2000.00 = 1 ETH) y
    # executedQuoteMin el USDC efectivamente gastado (RN-14)
    assert ejecutado_wei(orden) == ETH_1
    assert orden["executedQuoteMin"] == "2000000000", orden
    assert_montos_de_orden(orden)
    # Y todo USDC reservado no gastado se libera a disponible (RN-8)
    assert_balances(usuario, "USDC", disp=3_000_000_000, blk=0)
    # Y no queda remanente descansando en el libro
    assert abiertas(usuario) == []


@pytest.mark.at("AT-04-02-02")
def test_venta_market_por_cantidad_que_ejecuta_totalmente(usuario, usuario_b, rpc, api):
    """HU-04-02 Escenario 2: Venta market por cantidad que ejecuta totalmente."""
    # Dado bids resting ajenos suficientes a 1990000000
    requerir_zona_limpia(api, 1_990_000_000)
    fondear(usuario_b, rpc, usdc_min=1_990_000_000)
    alta_ok(usuario_b, cuerpo_orden("BUY", "LIMIT", 1_990_000_000, ETH_1), estado="OPEN")
    # Y un trader con disponible(ETH) = 2 ETH
    fondear(usuario, rpc, eth_wei=2 * ETH_1)

    # Cuando coloca SELL MARKET quantityWei=10^18 (vender 1 ETH)
    orden = alta_ok(usuario, cuerpo_orden("SELL", "MARKET", quantity_wei=ETH_1))

    # Entonces bloquea R = 10^18 wei, ejecuta como taker y queda FILLED (RN-5)
    assert orden["status"] == "FILLED", orden
    assert ejecutado_wei(orden) == ETH_1
    assert_balances(usuario, "ETH", disp=ETH_1, blk=0)
    # Y no queda remanente; la fee se cobra en el USDC recibido (RN-6, HU-05-*):
    # quote_min = 1990000000; fee_taker = ceil(1990000000 x 20 / 10000) = 3980000
    assert abiertas(usuario) == []
    assert_balances(usuario, "USDC", disp=1_990_000_000 - fee_taker(1_990_000_000), blk=0)


@pytest.mark.at("AT-04-02-03")
def test_compra_market_por_cantidad_libera_el_sobrante_reservado(usuario, usuario_b, rpc, api):
    """HU-04-02 Escenario 3 (feliz): Compra market por cantidad, sobrante liberado."""
    # Dado un ask resting ajeno por 1 ETH a 1990000000
    requerir_zona_limpia(api, 1_990_000_000)
    fondear(usuario_b, rpc, eth_wei=ETH_1)
    alta_ok(usuario_b, cuerpo_orden("SELL", "LIMIT", 1_990_000_000, ETH_1), estado="OPEN")
    # Y un trader con disponible(USDC) = 5000000000
    fondear(usuario, rpc, usdc_min=5_000_000_000)

    # Cuando coloca BUY MARKET quantityWei=10^18 (comprar 1 ETH)
    orden = alta_ok(usuario, cuerpo_orden("BUY", "MARKET", quantity_wei=ETH_1))

    # Entonces reserva el costo del barrido (snapshot, RN-5) y ejecuta
    # floor(10^18 x 1990000000 / 10^18) = 1990000000 USDC-min; queda FILLED
    assert orden["status"] == "FILLED", orden
    assert ejecutado_wei(orden) == ETH_1
    # Y cualquier diferencia entre lo reservado y lo consumido se libera (RN-8, INV-3)
    assert_balances(usuario, "USDC", disp=3_010_000_000, blk=0)


@pytest.mark.at("AT-04-02-04")
def test_ejecucion_parcial_por_liquidez_agotada_descarta_remanente(usuario, usuario_b, rpc, api):
    """HU-04-02 Escenario 4 (borde): Ejecución parcial por liquidez agotada."""
    # Dado un único ask resting ajeno por 0.4 ETH a 2000000000
    requerir_zona_limpia(api, P2000)
    fondear(usuario_b, rpc, eth_wei=400_000_000_000_000_000)
    alta_ok(
        usuario_b,
        cuerpo_orden("SELL", "LIMIT", P2000, 400_000_000_000_000_000),
        estado="OPEN",
    )
    # Y un trader con disponible(USDC) = 5000000000
    fondear(usuario, rpc, usdc_min=5_000_000_000)

    # Cuando coloca BUY MARKET quantityWei=10^18 (comprar 1 ETH)
    orden = alta_ok(usuario, cuerpo_orden("BUY", "MARKET", quantity_wei=ETH_1))

    # Entonces ejecuta 0.4 ETH, agota la liquidez y el remanente se descarta:
    # queda CANCELLED con filledWei = 0.4 ETH (RN-7, HU-04-05 RN-6)
    assert orden["status"] == "CANCELLED", orden
    assert ejecutado_wei(orden) == 400_000_000_000_000_000
    assert abiertas(usuario) == []  # no descansa
    # Y el USDC reservado no consumido se libera (RN-8): consumió 0.4 x 2000 = 800 USDC
    assert_balances(usuario, "USDC", disp=4_200_000_000, blk=0)


@pytest.mark.at("AT-04-02-05a")
def test_market_buy_sin_asks_es_rechazada_sin_reservar(usuario, rpc, api):
    """HU-04-02 Escenario 5a (error): Sin liquidez — BUY con asks vacíos."""
    # Dado el libro sin asks y un trader con disponible(USDC) = 5000000000
    requerir_lado_vacio(api, "asks")
    fondear(usuario, rpc, usdc_min=5_000_000_000)

    # Cuando coloca BUY MARKET quoteOrderQtyMin="2000000000"
    cid = client_order_id("noliq")
    resp = post_orden(
        usuario, cuerpo_orden("BUY", "MARKET", quote_order_qty_min=2_000_000_000, client_id=cid)
    )

    # Entonces se rechaza con MARKET_NO_LIQUIDITY (422) y la orden queda REJECTED
    assert_error(resp, "MARKET_NO_LIQUIDITY")
    rechazada = buscar_por_client_id(items_por_estado(usuario, "REJECTED"), cid)
    assert rechazada is not None and rechazada["status"] == "REJECTED"

    # Y los balances quedan intactos: la comprobación es previa a fondos y no se
    # reservó nada (RN-4, RE-4 paso 6)
    assert_balances(usuario, "USDC", disp=5_000_000_000, blk=0)


@pytest.mark.at("AT-04-02-05b")
def test_market_sell_sin_bids_es_rechazada_sin_reservar(usuario, rpc, api):
    """HU-04-02 Escenario 5b (error): Sin liquidez — SELL con bids vacíos."""
    # Dado el libro sin bids y un trader con disponible(ETH) = 2 ETH
    requerir_lado_vacio(api, "bids")
    fondear(usuario, rpc, eth_wei=2 * ETH_1)

    # Cuando coloca SELL MARKET quantityWei=10^18
    cid = client_order_id("noliq")
    resp = post_orden(
        usuario, cuerpo_orden("SELL", "MARKET", quantity_wei=ETH_1, client_id=cid)
    )

    # Entonces se rechaza con MARKET_NO_LIQUIDITY (422) y la orden queda REJECTED
    assert_error(resp, "MARKET_NO_LIQUIDITY")
    rechazada = buscar_por_client_id(items_por_estado(usuario, "REJECTED"), cid)
    assert rechazada is not None and rechazada["status"] == "REJECTED"

    # Y disponible/bloqueado de ETH quedan intactos (RN-4)
    assert_balances(usuario, "ETH", disp=2 * ETH_1, blk=0)


@pytest.mark.at("AT-04-02-06")
def test_market_con_precio_especificado_es_rechazada(usuario):
    """HU-04-02 Escenario 6 (error): Market con precio especificado."""
    # Cuando coloca BUY MARKET con quoteOrderQtyMin y priceMin a la vez
    resp = post_orden(
        usuario,
        cuerpo_orden("BUY", "MARKET", price_min=P2000, quote_order_qty_min=2_000_000_000),
    )

    # Entonces se rechaza con PRICE_NOT_ALLOWED (422) (RN-1)
    assert_error(resp, "PRICE_NOT_ALLOWED")

    # Y no se reserva ni se ejecuta nada (rechazo de validación: no se persiste)
    assert abiertas(usuario) == []
    assert historial(usuario) == []


@pytest.mark.at("AT-04-02-07")
def test_market_con_ambos_tamanos_es_rechazada(usuario):
    """HU-04-02 Escenario 7 (error): Ambos tamaños presentes."""
    # Cuando coloca BUY MARKET con quantityWei y quoteOrderQtyMin a la vez
    resp = post_orden(
        usuario,
        cuerpo_orden("BUY", "MARKET", quantity_wei=ETH_1, quote_order_qty_min=2_000_000_000),
    )

    # Entonces se rechaza con VALIDATION_ERROR (422): se exige exactamente uno (RN-1)
    err = assert_error(resp, "VALIDATION_ERROR")
    assert err.get("details", {}).get("issues"), err

    # Y no se reserva ni se ejecuta nada
    assert abiertas(usuario) == []
    assert historial(usuario) == []


@pytest.mark.at("AT-04-02-08")
def test_market_sin_ningun_tamano_es_rechazada(usuario):
    """HU-04-02 Escenario 8 (error): Ningún tamaño presente."""
    # Cuando coloca BUY MARKET sin quantityWei ni quoteOrderQtyMin
    resp = post_orden(usuario, cuerpo_orden("BUY", "MARKET"))

    # Entonces se rechaza con VALIDATION_ERROR (422) (RN-1)
    assert_error(resp, "VALIDATION_ERROR")


@pytest.mark.at("AT-04-02-09")
def test_market_con_fondos_insuficientes_es_rechazada(usuario, usuario_b, rpc, api, limpiador):
    """HU-04-02 Escenario 9 (error): Fondos insuficientes."""
    # Dado un ask resting ajeno cruzable (lado opuesto no vacío, para que el
    # resultado sea únicamente INSUFFICIENT_FUNDS y no MARKET_NO_LIQUIDITY)
    requerir_zona_limpia(api, P2000)
    fondear(usuario_b, rpc, eth_wei=ETH_1)
    ask = alta_ok(usuario_b, cuerpo_orden("SELL", "LIMIT", P2000, ETH_1), estado="OPEN")
    limpiador.registrar(usuario_b, ask["orderId"])
    # Y un trader con disponible(USDC) = 1000000000
    fondear(usuario, rpc, usdc_min=1_000_000_000)

    # Cuando coloca BUY MARKET quoteOrderQtyMin="2000000000"
    resp = post_orden(usuario, cuerpo_orden("BUY", "MARKET", quote_order_qty_min=2_000_000_000))

    # Entonces se rechaza con INSUFFICIENT_FUNDS (422) y details exactos (RN-5)
    err = assert_error(resp, "INSUFFICIENT_FUNDS")
    assert err["details"]["asset"] == "USDC"
    assert err["details"]["required"] == "2000000000"
    assert err["details"]["available"] == "1000000000"
    assert_montos_en_details(err["details"], "required", "available")

    # Y no se ejecuta ni se mantiene reserva (INV-2); el ask ajeno queda intacto
    assert_balances(usuario, "USDC", disp=1_000_000_000, blk=0)
    assert ejecutado_wei(detalle(usuario_b, ask["orderId"])) == 0


@pytest.mark.at("AT-04-02-10")
def test_market_por_monto_debajo_del_minimo_notional(usuario):
    """HU-04-02 Escenario 10 (error): Monto por debajo del mínimo notional.

    Sin fondeo: las reglas del par (paso 4) preceden a fondos (paso 7, RN-11).
    """
    # Cuando coloca BUY MARKET quoteOrderQtyMin="9999999" (9.999999 USDC < 10 USDC)
    resp = post_orden(usuario, cuerpo_orden("BUY", "MARKET", quote_order_qty_min=9_999_999))

    # Entonces se rechaza con BELOW_MIN_NOTIONAL (422) y details exactos (RN-3)
    err = assert_error(resp, "BELOW_MIN_NOTIONAL")
    assert err["details"]["actualNotional"] == "9999999", err
    assert err["details"]["minNotional"] == "10000000", err


@pytest.mark.at("AT-04-02-11")
def test_market_por_cantidad_fuera_de_lot_size(usuario):
    """HU-04-02 Escenario 11 (error): Cantidad fuera de lot size."""
    # Cuando coloca SELL MARKET quantityWei="50000000000000" (0.00005 ETH)
    resp = post_orden(
        usuario, cuerpo_orden("SELL", "MARKET", quantity_wei=50_000_000_000_000)
    )

    # Entonces se rechaza con INVALID_LOT_SIZE (422) y details exactos (RN-2)
    err = assert_error(resp, "INVALID_LOT_SIZE")
    assert err["details"]["quantityWei"] == "50000000000000", err
    assert err["details"]["lotSize"] == "100000000000000", err


@pytest.mark.at("AT-04-02-12a")
def test_venta_market_por_monto_que_completa_el_objetivo(usuario, usuario_b, rpc, api, limpiador):
    """HU-04-02 Escenario 12a (borde): Venta market por monto que completa el objetivo."""
    # Dado bids resting ajenos suficientes a 1500000000 (1.4 ETH de profundidad)
    requerir_lado_vacio(api, "bids")  # el bid ajeno debe ser la única liquidez
    requerir_sin_asks_hasta(api, 1_500_000_000)
    fondear(usuario_b, rpc, usdc_min=2_100_000_000)  # 1.4 x 1500 = 2100 USDC
    bid = alta_ok(
        usuario_b,
        cuerpo_orden("BUY", "LIMIT", 1_500_000_000, 1_400_000_000_000_000_000),
        estado="OPEN",
    )
    limpiador.registrar(usuario_b, bid["orderId"])
    # Y un trader con disponible(ETH) = 2 ETH
    fondear(usuario, rpc, eth_wei=2 * ETH_1)

    # Cuando coloca SELL MARKET quoteOrderQtyMin="2000000000" (recibir ~2000 USDC)
    orden = alta_ok(usuario, cuerpo_orden("SELL", "MARKET", quote_order_qty_min=2_000_000_000))

    # Entonces reserva por snapshot q = ceil(2000000000 x 10^18 / 1500000000) =
    # 1333333333333333334 wei y ejecuta esa base (RN-5); queda FILLED
    assert orden["status"] == "FILLED", orden
    assert ejecutado_wei(orden) == 1_333_333_333_333_333_334
    # Y el USDC recibido cumple el objetivo exacto por el ceil de +1 wei (RN-5):
    # executedQuoteMin = floor(1333333333333333334 x 1500000000 / 10^18) = 2000000000
    assert orden["executedQuoteMin"] == "2000000000", orden
    # Y el sobrante de ETH reservado no vendido se libera (RN-8)
    assert_balances(usuario, "ETH", disp=2 * ETH_1 - 1_333_333_333_333_333_334, blk=0)


@pytest.mark.at("AT-04-02-12b")
def test_venta_market_por_monto_con_liquidez_insuficiente(usuario, usuario_b, rpc, api):
    """HU-04-02 Escenario 12b (borde): Venta market por monto con liquidez insuficiente."""
    # Dado un único bid resting ajeno por 0.4 ETH a 1500000000
    requerir_lado_vacio(api, "bids")
    requerir_sin_asks_hasta(api, 1_500_000_000)
    fondear(usuario_b, rpc, usdc_min=600_000_000)  # 0.4 x 1500 = 600 USDC
    alta_ok(
        usuario_b,
        cuerpo_orden("BUY", "LIMIT", 1_500_000_000, 400_000_000_000_000_000),
        estado="OPEN",
    )
    # Y un trader con disponible(ETH) = 2 ETH
    fondear(usuario, rpc, eth_wei=2 * ETH_1)

    # Cuando coloca SELL MARKET quoteOrderQtyMin="2000000000"
    orden = alta_ok(usuario, cuerpo_orden("SELL", "MARKET", quote_order_qty_min=2_000_000_000))

    # Entonces el snapshot solo cubre 0.4 ETH: vende todo, agota la liquidez y el
    # remanente del objetivo se descarta: CANCELLED (RN-7, RN-14)
    assert orden["status"] == "CANCELLED", orden
    assert ejecutado_wei(orden) == 400_000_000_000_000_000
    # executedQuoteMin = floor(4e17 x 1.5e9 / 1e18) = 600000000
    assert orden["executedQuoteMin"] == "600000000", orden
    # Y el ETH reservado no vendido se libera a disponible (RN-8)
    assert_balances(usuario, "ETH", disp=2 * ETH_1 - 400_000_000_000_000_000, blk=0)
    assert abiertas(usuario) == []


@pytest.mark.at("AT-04-02-13")
def test_self_trade_en_market_con_bid_propio_como_unica_liquidez(usuario, rpc, api, limpiador):
    """HU-04-02 Escenario 13 (error): Self-trade en market (bid propio única liquidez)."""
    # Dado un trader con disponible(ETH) = 2 ETH y un bid propio resting como
    # única liquidez del lado opuesto
    requerir_lado_vacio(api, "bids")
    requerir_sin_asks_hasta(api, P2000)
    fondear(usuario, rpc, eth_wei=2 * ETH_1, usdc_min=2_000_000_000)
    bid = alta_ok(usuario, cuerpo_orden("BUY", "LIMIT", P2000, ETH_1), estado="OPEN")
    limpiador.registrar(usuario, bid["orderId"])
    assert_balances(usuario, "ETH", disp=2 * ETH_1, blk=0)

    # Cuando coloca SELL MARKET quantityWei=10^18 cuyo rango contiene su propio bid
    cid = client_order_id("stp")
    resp = post_orden(
        usuario, cuerpo_orden("SELL", "MARKET", quantity_wei=ETH_1, client_id=cid)
    )

    # Entonces se rechaza con SELF_TRADE_BLOCKED (422), details.restingOrderId
    err = assert_error(resp, "SELF_TRADE_BLOCKED")
    assert err["details"]["restingOrderId"] == bid["orderId"], err

    # Y la reserva tomada se revierte atómicamente (RN-9, INV-3)
    assert_balances(usuario, "ETH", disp=2 * ETH_1, blk=0)

    # Y la orden se registra como REJECTED (RE-12); el bid propio sigue resting
    rechazada = buscar_por_client_id(items_por_estado(usuario, "REJECTED"), cid)
    assert rechazada is not None and rechazada["status"] == "REJECTED"
    assert detalle(usuario, bid["orderId"])["status"] == "OPEN"


@pytest.mark.at("AT-04-02-14")
def test_market_con_orden_propia_dentro_del_rango_consumible(
    usuario, usuario_b, rpc, api, limpiador
):
    """HU-04-02 Escenario 14 (borde): Orden propia dentro del rango consumible."""
    # Dado dos bids cruzables a 2000000000: el primero ajeno (0.4 ETH) y el
    # segundo propio (0.6 ETH), en ese orden FIFO
    requerir_lado_vacio(api, "bids")
    requerir_sin_asks_hasta(api, P2000)
    fondear(usuario_b, rpc, usdc_min=800_000_000)  # 0.4 x 2000 = 800 USDC
    fondear(usuario, rpc, eth_wei=2 * ETH_1, usdc_min=1_200_000_000)  # 0.6 x 2000
    bid_ajeno = alta_ok(
        usuario_b,
        cuerpo_orden("BUY", "LIMIT", P2000, 400_000_000_000_000_000),
        estado="OPEN",
    )
    limpiador.registrar(usuario_b, bid_ajeno["orderId"])
    bid_propio = alta_ok(
        usuario,
        cuerpo_orden("BUY", "LIMIT", P2000, 600_000_000_000_000_000),
        estado="OPEN",
    )
    limpiador.registrar(usuario, bid_propio["orderId"])
    assert_balances(usuario, "ETH", disp=2 * ETH_1, blk=0)

    # Cuando coloca SELL MARKET quantityWei=10^18 (rango consumible = ambos bids)
    cid = client_order_id("stp14")
    resp = post_orden(
        usuario, cuerpo_orden("SELL", "MARKET", quantity_wei=ETH_1, client_id=cid)
    )

    # Entonces se rechaza íntegra y atómicamente con SELF_TRADE_BLOCKED, sin
    # ningún fill, tampoco contra el bid ajeno (RN-9, RE-11)
    err = assert_error(resp, "SELF_TRADE_BLOCKED")
    assert err["details"]["restingOrderId"] == bid_propio["orderId"], err

    # Y la reserva se revierte; el libro queda idéntico (ambos bids intactos)
    assert_balances(usuario, "ETH", disp=2 * ETH_1, blk=0)
    assert detalle(usuario_b, bid_ajeno["orderId"])["status"] == "OPEN"
    assert ejecutado_wei(detalle(usuario_b, bid_ajeno["orderId"])) == 0
    assert detalle(usuario, bid_propio["orderId"])["status"] == "OPEN"
    assert cantidad_en_nivel(api, "bids", P2000) == ETH_1

    # Y la orden queda REJECTED con filledWei = "0" (RE-12)
    rechazada = buscar_por_client_id(items_por_estado(usuario, "REJECTED"), cid)
    assert rechazada is not None and rechazada["status"] == "REJECTED"
    assert ejecutado_wei(rechazada) == 0
