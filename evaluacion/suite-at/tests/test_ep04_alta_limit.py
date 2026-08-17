"""Épica 04 — HU-04-01 Colocar orden limit: tests de aceptación black-box.

Spec: spec/04-gestion-de-ordenes/HU-04-01-colocar-orden-limit.md
Contrato observable: POST /orders, GET /orders*, DELETE /orders/{id},
GET /balances, GET /market/orderbook (épica 09).

AT-04-01-11 (persistencia tras reinicio) se verifica en
tests/test_ep04_persistencia.py, con el reinicio orquestado por el evaluador.
"""

import time

import pytest

from helpers.errores import assert_error, assert_montos_en_details
from helpers.montos import es_monto_valido

from comunes_ep04 import (  # noqa: F401 (limpiador es fixture)
    ETH_1,
    NOTIONAL_MIN,
    P2000,
    Q_MIN,
    abiertas,
    alta_ok,
    assert_balances,
    assert_montos_de_orden,
    bloqueado,
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
    remanente_wei,
    requerir_lado_vacio,
    requerir_sin_asks_hasta,
    requerir_sin_bids_desde,
    requerir_zona_limpia,
)


@pytest.mark.at("AT-04-01-01")
def test_alta_de_compra_limit_que_descansa_en_el_libro(usuario, rpc, api, limpiador):
    """HU-04-01 Escenario 1: Alta de compra limit que descansa en el libro."""
    # Dado un trader con disponible(USDC) = 5000000000 y bloqueado(USDC) = 0
    requerir_sin_asks_hasta(api, P2000)  # y un orderbook sin asks a priceMin <= 2000000000
    fondear(usuario, rpc, usdc_min=5_000_000_000)
    assert_balances(usuario, "USDC", disp=5_000_000_000, blk=0)

    # Cuando coloca BUY LIMIT priceMin=2000000000, quantityWei=10^18 (1 ETH @ 2000.00)
    orden = alta_ok(usuario, cuerpo_orden("BUY", "LIMIT", P2000, ETH_1), estado="OPEN")
    limpiador.registrar(usuario, orden["orderId"])

    # Entonces la orden queda OPEN y se bloquean R = floor(10^18 x 2e9 / 10^18) = 2000000000
    # (RN-3; la reserva es exacta por la nota lot x tick = 10^18 del README)
    assert_balances(usuario, "USDC", disp=3_000_000_000, blk=2_000_000_000)
    # Y total(USDC) no cambia (INV-3, validado dentro de assert_balances)

    # Y la orden aparece como abierta con filledWei = "0" y remainingWei = quantityWei
    item = next(i for i in abiertas(usuario) if i["orderId"] == orden["orderId"])
    assert ejecutado_wei(item) == 0
    assert remanente_wei(item) == ETH_1
    assert_montos_de_orden(item)


@pytest.mark.at("AT-04-01-02")
def test_alta_de_venta_limit_que_descansa_en_el_libro(usuario, rpc, api, limpiador):
    """HU-04-01 Escenario 2: Alta de venta limit que descansa en el libro."""
    # Dado un trader con disponible(ETH) = 3 ETH y un libro sin bids a priceMin >= 2100000000
    requerir_sin_bids_desde(api, 2_100_000_000)
    fondear(usuario, rpc, eth_wei=3 * ETH_1)

    # Cuando coloca SELL LIMIT priceMin=2100000000, quantityWei=10^18 (1 ETH @ 2100.00)
    orden = alta_ok(
        usuario, cuerpo_orden("SELL", "LIMIT", 2_100_000_000, ETH_1), estado="OPEN"
    )
    limpiador.registrar(usuario, orden["orderId"])

    # Entonces queda OPEN y se bloquean R = 10^18 wei de ETH (RN-4)
    assert_balances(usuario, "ETH", disp=2 * ETH_1, blk=ETH_1)
    # Y no se bloquea ni reserva USDC alguno
    assert_balances(usuario, "USDC", disp=0, blk=0)


@pytest.mark.at("AT-04-01-03")
def test_compra_limit_que_ejecuta_totalmente_como_taker(usuario, usuario_b, rpc, api):
    """HU-04-01 Escenario 3 (feliz): Compra limit que ejecuta totalmente como taker."""
    # Dado un ask resting de otra cuenta por 1 ETH a 2000000000
    requerir_zona_limpia(api, P2000)
    fondear(usuario_b, rpc, eth_wei=ETH_1)
    alta_ok(usuario_b, cuerpo_orden("SELL", "LIMIT", P2000, ETH_1), estado="OPEN")
    # Y un trader con disponible(USDC) = 5000000000
    fondear(usuario, rpc, usdc_min=5_000_000_000)

    # Cuando coloca BUY LIMIT priceMin=2000000000, quantityWei=10^18
    orden = alta_ok(usuario, cuerpo_orden("BUY", "LIMIT", P2000, ETH_1))

    # Entonces ejecuta de inmediato como taker y queda FILLED (RN-7, RN-9)
    assert orden["status"] == "FILLED", orden
    assert ejecutado_wei(orden) == ETH_1
    # Y no queda remanente en el libro ni reserva remanente bloqueada por esta orden
    assert abiertas(usuario) == []
    assert bloqueado(usuario, "USDC") == 0
    # (el detalle contable del fill —débitos/créditos y fees— es de HU-05-*, INV-4)


@pytest.mark.at("AT-04-01-04")
def test_compra_limit_con_ejecucion_parcial_y_remanente_resting(
    usuario, usuario_b, rpc, api, limpiador
):
    """HU-04-01 Escenario 4 (borde): Compra limit con ejecución parcial; el remanente descansa."""
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

    # Cuando coloca BUY LIMIT por 1 ETH a 2000000000
    orden = alta_ok(usuario, cuerpo_orden("BUY", "LIMIT", P2000, ETH_1))
    limpiador.registrar(usuario, orden["orderId"])

    # Entonces 0.4 ETH ejecutan y el remanente 0.6 ETH descansa; queda PARTIALLY_FILLED
    # (no OPEN, conforme a HU-04-05 RN-3)
    assert orden["status"] == "PARTIALLY_FILLED", orden
    assert ejecutado_wei(orden) == 400_000_000_000_000_000
    assert remanente_wei(orden) == 600_000_000_000_000_000

    # Y la reserva remanente respalda exactamente el remanente (INV-7):
    # floor(6e17 x 2e9 / 1e18) = 1200000000 USDC-min
    assert_balances(usuario, "USDC", disp=3_000_000_000, blk=1_200_000_000)


@pytest.mark.at("AT-04-01-05")
def test_compra_a_mejor_precio_libera_el_sobrante_reservado(usuario, usuario_b, rpc, api):
    """HU-04-01 Escenario 5 (borde): Compra que matchea a mejor precio libera el sobrante."""
    # Dado un ask resting ajeno por 1 ETH a 1990000000 (mejor que el límite)
    requerir_zona_limpia(api, 1_990_000_000)
    fondear(usuario_b, rpc, eth_wei=ETH_1)
    alta_ok(usuario_b, cuerpo_orden("SELL", "LIMIT", 1_990_000_000, ETH_1), estado="OPEN")
    # Y un trader con disponible(USDC) = 5000000000
    fondear(usuario, rpc, usdc_min=5_000_000_000)

    # Cuando coloca BUY LIMIT priceMin=2000000000, quantityWei=10^18
    orden = alta_ok(usuario, cuerpo_orden("BUY", "LIMIT", P2000, ETH_1))

    # Entonces reserva R = 2000000000, ejecuta a 1990000000 consumiendo 1990000000
    # Y el sobrante 10000000 USDC-min se libera a disponible (RN-8, RE-3, INV-3)
    assert orden["status"] == "FILLED", orden
    assert_balances(usuario, "USDC", disp=3_010_000_000, blk=0)


@pytest.mark.at("AT-04-01-06")
def test_fondos_insuficientes_no_crea_orden_ni_bloquea(usuario, rpc):
    """HU-04-01 Escenario 6 (error): Fondos insuficientes."""
    # Dado un trader con disponible(USDC) = 1000000000 (1000 USDC)
    fondear(usuario, rpc, usdc_min=1_000_000_000)

    # Cuando coloca BUY LIMIT 1 ETH @ 2000.00 (requiere R = 2000000000)
    resp = post_orden(usuario, cuerpo_orden("BUY", "LIMIT", P2000, ETH_1))

    # Entonces se rechaza con INSUFFICIENT_FUNDS (422) y details exactos (RN-3)
    err = assert_error(resp, "INSUFFICIENT_FUNDS")
    assert err["details"]["asset"] == "USDC"
    assert err["details"]["required"] == "2000000000"
    assert err["details"]["available"] == "1000000000"
    assert_montos_en_details(err["details"], "required", "available")

    # Y no se crea ninguna orden, no se bloquea nada y los balances quedan intactos (INV-2)
    assert_balances(usuario, "USDC", disp=1_000_000_000, blk=0)
    assert abiertas(usuario) == []
    assert historial(usuario) == []  # el rechazo por fondos no se persiste (RE-12)


@pytest.mark.at("AT-04-01-07")
def test_self_trade_bloqueado_con_ask_propio_como_unica_liquidez(
    usuario, rpc, api, limpiador
):
    """HU-04-01 Escenario 7 (error): Self-trade bloqueado (ask propio único en el rango)."""
    # Dado un trader con un ask propio resting por 1 ETH a 2000000000
    requerir_zona_limpia(api, P2000)
    fondear(usuario, rpc, eth_wei=ETH_1, usdc_min=5_000_000_000)
    ask = alta_ok(usuario, cuerpo_orden("SELL", "LIMIT", P2000, ETH_1), estado="OPEN")
    limpiador.registrar(usuario, ask["orderId"])
    # Y disponible(USDC) = 5000000000 (la validación de fondos pasa y se aísla el STP)
    assert_balances(usuario, "USDC", disp=5_000_000_000, blk=0)

    # Cuando coloca BUY LIMIT cuyo rango consumible contiene su propio ask
    cid = client_order_id("stp")
    resp = post_orden(usuario, cuerpo_orden("BUY", "LIMIT", P2000, ETH_1, client_id=cid))

    # Entonces se rechaza con SELF_TRADE_BLOCKED (422) y details.restingOrderId
    err = assert_error(resp, "SELF_TRADE_BLOCKED")
    assert err["details"]["restingOrderId"] == ask["orderId"], err

    # Y la reserva tomada se revierte atómicamente (RN-10, INV-3)
    assert_balances(usuario, "USDC", disp=5_000_000_000, blk=0)

    # Y la entrante no descansa; se registra como REJECTED (RE-12) y el ask sigue intacto
    rechazada = buscar_por_client_id(items_por_estado(usuario, "REJECTED"), cid)
    assert rechazada is not None and rechazada["status"] == "REJECTED"
    assert detalle(usuario, ask["orderId"])["status"] == "OPEN"


@pytest.mark.at("AT-04-01-08")
def test_client_order_id_duplicado_es_rechazado(usuario, rpc, api, limpiador):
    """HU-04-01 Escenario 8 (idempotencia): clientOrderId duplicado."""
    # Dado un trader que ya colocó una orden con clientOrderId = "abc-123"
    requerir_sin_asks_hasta(api, P2000)
    fondear(usuario, rpc, usdc_min=NOTIONAL_MIN)
    orden = alta_ok(
        usuario, cuerpo_orden("BUY", "LIMIT", P2000, Q_MIN, client_id="abc-123"),
        estado="OPEN",
    )
    limpiador.registrar(usuario, orden["orderId"])
    bloqueado_previo = bloqueado(usuario, "USDC")

    # Cuando coloca otra orden limit con el mismo clientOrderId
    resp = post_orden(
        usuario, cuerpo_orden("BUY", "LIMIT", P2000, Q_MIN, client_id="abc-123")
    )

    # Entonces se rechaza con DUPLICATE_CLIENT_ORDER_ID (409), details.clientOrderId
    err = assert_error(resp, "DUPLICATE_CLIENT_ORDER_ID")
    assert err["details"]["clientOrderId"] == "abc-123", err

    # Y no se crea una segunda orden ni se reservan fondos adicionales (RN-11, RE-5)
    assert len(abiertas(usuario)) == 1
    assert bloqueado(usuario, "USDC") == bloqueado_previo


@pytest.mark.at("AT-04-01-09")
def test_precio_fuera_de_tick_es_rechazado_sin_reservar(usuario):
    """HU-04-01 Escenario 9 (error): Precio fuera de tick.

    Sin fondeo: la validación del par precede a fondos (RE-4 paso 4 > paso 7,
    verificado en AT-04-03-01), por lo que el resultado es el mismo con o sin
    fondos y el rechazo no toca balances.
    """
    # Cuando coloca BUY LIMIT priceMin=2000005000 (2000.005, no múltiplo de 10000)
    resp = post_orden(usuario, cuerpo_orden("BUY", "LIMIT", 2_000_005_000, ETH_1))

    # Entonces se rechaza con INVALID_PRICE_TICK (422) y details exactos (RN-2)
    err = assert_error(resp, "INVALID_PRICE_TICK")
    assert err["details"]["priceMin"] == "2000005000", err
    assert err["details"]["tickSize"] == "10000", err

    # Y no se reserva nada (la validación del par precede a fondos, RE-4)
    assert_balances(usuario, "USDC", disp=0, blk=0)
    assert_balances(usuario, "ETH", disp=0, blk=0)


@pytest.mark.at("AT-04-01-10")
def test_notional_exactamente_igual_al_minimo_es_valido(usuario, rpc, api, limpiador):
    """HU-04-01 Escenario 10 (borde): Notional exactamente igual al mínimo es válido."""
    # Dado un trader con disponible(USDC) >= 10000000
    requerir_sin_asks_hasta(api, P2000)
    fondear(usuario, rpc, usdc_min=NOTIONAL_MIN)

    # Cuando coloca BUY LIMIT 0.005 ETH @ 2000.00 (notional 10000000 = 10 USDC)
    orden = alta_ok(usuario, cuerpo_orden("BUY", "LIMIT", P2000, Q_MIN), estado="OPEN")
    limpiador.registrar(usuario, orden["orderId"])

    # Entonces la orden se acepta (el notional iguala el mínimo, no es menor)
    # Y se bloquean 10000000 USDC-min
    assert_balances(usuario, "USDC", disp=0, blk=NOTIONAL_MIN)


@pytest.mark.at("AT-04-01-12")
def test_quote_order_qty_min_no_se_admite_en_limit(usuario):
    """HU-04-01 Escenario 12 (error): `quoteOrderQtyMin` no se admite en limit."""
    # Cuando coloca BUY LIMIT con priceMin, quantityWei y ademas quoteOrderQtyMin
    resp = post_orden(
        usuario,
        cuerpo_orden("BUY", "LIMIT", P2000, ETH_1, quote_order_qty_min=2_000_000_000),
    )

    # Entonces se rechaza con VALIDATION_ERROR (422); details.issues lo indica (RN-1)
    err = assert_error(resp, "VALIDATION_ERROR")
    assert err.get("details", {}).get("issues"), err

    # Y no se reserva nada ni se crea orden (RN-11 de HU-04-03)
    assert abiertas(usuario) == []
    assert historial(usuario) == []


@pytest.mark.at("AT-04-01-13")
def test_orden_propia_dentro_del_rango_consumible_rechazo_integro(
    usuario, usuario_b, rpc, api, limpiador
):
    """HU-04-01 Escenario 13 (borde): Orden propia dentro del rango consumible."""
    # Dado dos asks cruzables a 2000000000: el primero ajeno (0.4 ETH) y el
    # segundo propio (0.6 ETH), en ese orden FIFO
    requerir_zona_limpia(api, P2000)
    fondear(usuario_b, rpc, eth_wei=400_000_000_000_000_000)
    fondear(usuario, rpc, eth_wei=600_000_000_000_000_000, usdc_min=5_000_000_000)
    ask_ajeno = alta_ok(
        usuario_b,
        cuerpo_orden("SELL", "LIMIT", P2000, 400_000_000_000_000_000),
        estado="OPEN",
    )
    limpiador.registrar(usuario_b, ask_ajeno["orderId"])
    ask_propio = alta_ok(
        usuario,
        cuerpo_orden("SELL", "LIMIT", P2000, 600_000_000_000_000_000),
        estado="OPEN",
    )
    limpiador.registrar(usuario, ask_propio["orderId"])
    assert_balances(usuario, "USDC", disp=5_000_000_000, blk=0)

    # Cuando coloca BUY LIMIT 1 ETH @ 2000 (rango consumible = ambos asks)
    cid = client_order_id("stp13")
    resp = post_orden(usuario, cuerpo_orden("BUY", "LIMIT", P2000, ETH_1, client_id=cid))

    # Entonces se rechaza íntegra y atómicamente con SELF_TRADE_BLOCKED, sin
    # ningún fill, tampoco contra el ask ajeno (RN-10, RN-14, RE-11)
    err = assert_error(resp, "SELF_TRADE_BLOCKED")
    assert err["details"]["restingOrderId"] == ask_propio["orderId"], err

    # Y la reserva se revierte y el libro queda idéntico (ambos asks intactos)
    assert_balances(usuario, "USDC", disp=5_000_000_000, blk=0)
    assert detalle(usuario_b, ask_ajeno["orderId"])["status"] == "OPEN"
    assert ejecutado_wei(detalle(usuario_b, ask_ajeno["orderId"])) == 0
    assert detalle(usuario, ask_propio["orderId"])["status"] == "OPEN"
    assert cantidad_en_nivel(api, "asks", P2000) == ETH_1

    # Y la orden queda REJECTED con filledWei = "0" (RE-12)
    rechazada = buscar_por_client_id(items_por_estado(usuario, "REJECTED"), cid)
    assert rechazada is not None and rechazada["status"] == "REJECTED"
    assert ejecutado_wei(rechazada) == 0


@pytest.mark.at("AT-04-01-14")
def test_client_order_id_no_reutilizable_tras_estado_terminal(usuario, usuario_b, rpc, api):
    """HU-04-01 Escenario 14 (idempotencia): `clientOrderId` no reutilizable tras terminal."""
    # Dado un trader cuya orden con clientOrderId = "k-1" ya está FILLED (terminal)
    requerir_zona_limpia(api, P2000)
    fondear(usuario_b, rpc, eth_wei=Q_MIN)
    fondear(usuario, rpc, usdc_min=NOTIONAL_MIN)
    alta_ok(usuario_b, cuerpo_orden("SELL", "LIMIT", P2000, Q_MIN), estado="OPEN")
    orden = alta_ok(
        usuario, cuerpo_orden("BUY", "LIMIT", P2000, Q_MIN, client_id="k-1"),
        estado="FILLED",
    )
    bloqueado_previo = bloqueado(usuario, "USDC")

    # Cuando coloca una nueva orden con el mismo clientOrderId = "k-1"
    # (la idempotencia, paso 5, precede a fondos, paso 7: no requiere re-fondear)
    resp = post_orden(usuario, cuerpo_orden("BUY", "LIMIT", P2000, Q_MIN, client_id="k-1"))

    # Entonces se rechaza con DUPLICATE_CLIENT_ORDER_ID (409): unicidad permanente
    # por cuenta (RN-15, RE-5)
    assert_error(resp, "DUPLICATE_CLIENT_ORDER_ID")

    # Y no se crea una segunda orden ni se reservan fondos
    assert abiertas(usuario) == []
    assert bloqueado(usuario, "USDC") == bloqueado_previo
    assert detalle(usuario, orden["orderId"])["status"] == "FILLED"


@pytest.mark.at("AT-04-01-15")
def test_exceso_de_solicitudes_de_alta_es_rate_limited(usuario):
    """HU-04-01 Escenario 15 (rate limiting): Exceso de solicitudes.

    Umbral: 60 requests/min por cuenta y endpoint (HU-09-02 RN-12). Se envían
    cuerpos que fallan por tick para no persistir órdenes: el control de tasa es
    de capa de red (RE-4 paso 0) y cuenta la request igual.
    """
    # Dado un trader que supera el límite de tasa del alta de órdenes
    inicio = time.monotonic()
    respuestas = [
        post_orden(usuario, cuerpo_orden("BUY", "LIMIT", 2_000_005_000, ETH_1))
        for _ in range(61)
    ]
    codigos = [r.status_code for r in respuestas]

    if 429 not in codigos:
        if time.monotonic() - inicio > 55:
            pytest.skip("las 61 requests no entraron en la ventana de 60 s del rate limit")
        pytest.fail(f"61 requests a POST /orders sin RATE_LIMITED: {sorted(set(codigos))}")

    # Cuando envía una orden por encima del límite
    primera_429 = codigos.index(429)

    # Entonces se rechaza con RATE_LIMITED (429) y details.retryAfterSeconds (RN-16, RE-10)
    err = assert_error(respuestas[primera_429], "RATE_LIMITED")
    retry = err["details"]["retryAfterSeconds"]
    assert isinstance(retry, int) and not isinstance(retry, bool), err  # conteo: entero JSON

    # Y no se crea ninguna orden ni se reserva nada (RE-4 paso 0): los cuerpos
    # violan el tick (nunca se persisten, RE-12) y los balances quedan intactos.
    # No se consulta GET /orders acá: HU-09-02 RN-12 no aclara si comparte la
    # cuota del endpoint con POST /orders y la cuenta ya está limitada.
    assert_balances(usuario, "USDC", disp=0, blk=0)
