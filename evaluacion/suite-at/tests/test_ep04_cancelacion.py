"""Épica 04 — HU-04-04 Cancelar orden: tests de aceptación black-box.

Spec: spec/04-gestion-de-ordenes/HU-04-04-cancelar-orden.md
Contrato: DELETE /orders/{orderId} (HU-09-01 RN-7).

AT-04-04-12 (persistencia de la cancelación tras reinicio) se verifica en
tests/test_ep04_persistencia.py, con el reinicio orquestado por el evaluador.
"""

import pytest

from helpers.errores import assert_error

from comunes_ep04 import (  # noqa: F401 (limpiador es fixture)
    ETH_1,
    NOTIONAL_MIN,
    P2000,
    Q_MIN,
    abiertas,
    alta_ok,
    assert_balances,
    balances,
    cancelar,
    cancelar_ok,
    cantidad_en_nivel,
    crear_filled,
    crear_rejected_sin_liquidez,
    cuerpo_orden,
    detalle,
    ejecutado_wei,
    esperar_orden,
    fondear,
    limpiador,
    requerir_sin_asks_hasta,
    requerir_zona_limpia,
)


@pytest.mark.at("AT-04-04-01")
def test_cancelar_orden_open_libera_toda_la_reserva(usuario, rpc, api):
    """HU-04-04 Escenario 1: Cancelar una orden OPEN libera toda la reserva."""
    # Dado una orden BUY LIMIT OPEN de 1 ETH @ 2000 con filledWei="0"
    # y bloqueado(USDC) = 2000000000, disponible(USDC) = 3000000000
    requerir_sin_asks_hasta(api, P2000)
    fondear(usuario, rpc, usdc_min=5_000_000_000)
    orden = alta_ok(usuario, cuerpo_orden("BUY", "LIMIT", P2000, ETH_1), estado="OPEN")
    assert_balances(usuario, "USDC", disp=3_000_000_000, blk=2_000_000_000)
    nivel_previo = cantidad_en_nivel(api, "bids", P2000)

    # Cuando cancela la orden
    cancelada = cancelar_ok(usuario, orden["orderId"])

    # Entonces la orden queda CANCELLED y se remueve del orderbook
    assert cancelada["status"] == "CANCELLED"
    assert abiertas(usuario) == []
    assert cantidad_en_nivel(api, "bids", P2000) == nivel_previo - ETH_1

    # Y se liberan 2000000000 USDC-min (RN-3); total y suma global no cambian
    # (INV-1, INV-3: la partición se valida dentro de assert_balances)
    assert_balances(usuario, "USDC", disp=5_000_000_000, blk=0)


@pytest.mark.at("AT-04-04-02")
def test_cancelar_partially_filled_libera_solo_el_remanente(usuario, usuario_b, rpc, api):
    """HU-04-04 Escenario 2: Cancelar una orden PARTIALLY_FILLED libera solo el remanente."""
    # Dado una orden BUY LIMIT de 1 ETH @ 2000 con filledWei=0.4 ETH:
    # bid resting de `usuario` + venta parcial de `usuario_b` como taker
    requerir_zona_limpia(api, P2000)
    fondear(usuario, rpc, usdc_min=2_000_000_000)
    orden = alta_ok(usuario, cuerpo_orden("BUY", "LIMIT", P2000, ETH_1), estado="OPEN")
    fondear(usuario_b, rpc, eth_wei=400_000_000_000_000_000)
    alta_ok(
        usuario_b,
        cuerpo_orden("SELL", "LIMIT", P2000, 400_000_000_000_000_000),
        estado="FILLED",
    )
    orden_parcial = esperar_orden(usuario, orden["orderId"], "PARTIALLY_FILLED")
    assert ejecutado_wei(orden_parcial) == 400_000_000_000_000_000
    # La reserva remanente es floor(6e17 x 2e9 / 1e18) = 1200000000 (consumió 800000000)
    assert_balances(usuario, "USDC", disp=0, blk=1_200_000_000)

    # Cuando cancela la orden
    cancelada = cancelar_ok(usuario, orden["orderId"])

    # Entonces queda CANCELLED con filledWei preservado
    assert ejecutado_wei(cancelada) == 400_000_000_000_000_000

    # Y se liberan 1200000000 USDC-min del remanente; lo ejecutado no se revierte
    assert_balances(usuario, "USDC", disp=1_200_000_000, blk=0)


@pytest.mark.at("AT-04-04-03")
def test_cancelar_sell_libera_eth_del_remanente(usuario, usuario_b, rpc, api):
    """HU-04-04 Escenario 3 (venta): Cancelar SELL libera ETH del remanente."""
    # Dado una orden SELL LIMIT de 1 ETH con filledWei=0.3 ETH y bloqueado(ETH)=0.7
    requerir_zona_limpia(api, 2_100_000_000)
    fondear(usuario, rpc, eth_wei=ETH_1)
    orden = alta_ok(
        usuario, cuerpo_orden("SELL", "LIMIT", 2_100_000_000, ETH_1), estado="OPEN"
    )
    fondear(usuario_b, rpc, usdc_min=630_000_000)  # 0.3 x 2100 = 630 USDC
    alta_ok(
        usuario_b,
        cuerpo_orden("BUY", "LIMIT", 2_100_000_000, 300_000_000_000_000_000),
        estado="FILLED",
    )
    esperar_orden(usuario, orden["orderId"], "PARTIALLY_FILLED")
    assert_balances(usuario, "ETH", disp=0, blk=700_000_000_000_000_000)

    # Cuando cancela la orden
    cancelada = cancelar_ok(usuario, orden["orderId"])

    # Entonces queda CANCELLED y se liberan 700000000000000000 wei a disponible (RN-3)
    assert cancelada["status"] == "CANCELLED"
    assert_balances(usuario, "ETH", disp=700_000_000_000_000_000, blk=0)


@pytest.mark.at("AT-04-04-04")
def test_cancelar_una_orden_filled_es_rechazado(usuario, usuario_b, rpc, api):
    """HU-04-04 Escenario 4 (error): Cancelar una orden FILLED."""
    # Dado un trader con una orden FILLED
    orden = crear_filled(usuario, usuario_b, rpc, api)
    saldo_previo = balances(usuario)

    # Cuando intenta cancelarla
    resp = cancelar(usuario, orden["orderId"])

    # Entonces se rechaza con ORDER_NOT_CANCELLABLE (409) y details exactos (RN-1)
    err = assert_error(resp, "ORDER_NOT_CANCELLABLE")
    assert err["details"]["orderId"] == orden["orderId"], err
    assert err["details"]["status"] == "FILLED", err

    # Y no se libera nada (ya fue consumida)
    assert balances(usuario) == saldo_previo


@pytest.mark.at("AT-04-04-05")
def test_cancelar_una_orden_ya_cancelled_es_rechazado(usuario, rpc, api):
    """HU-04-04 Escenario 5 (error): Cancelar una orden ya CANCELLED."""
    # Dado un trader con una orden CANCELLED
    requerir_sin_asks_hasta(api, P2000)
    fondear(usuario, rpc, usdc_min=NOTIONAL_MIN)
    orden = alta_ok(usuario, cuerpo_orden("BUY", "LIMIT", P2000, Q_MIN), estado="OPEN")
    cancelar_ok(usuario, orden["orderId"])
    saldo_previo = balances(usuario)

    # Cuando intenta cancelarla de nuevo
    resp = cancelar(usuario, orden["orderId"])

    # Entonces se rechaza con ORDER_NOT_CANCELLABLE (409), details.status="CANCELLED"
    err = assert_error(resp, "ORDER_NOT_CANCELLABLE")
    assert err["details"]["orderId"] == orden["orderId"], err
    assert err["details"]["status"] == "CANCELLED", err

    # Y los balances no cambian (RN-4)
    assert balances(usuario) == saldo_previo


@pytest.mark.at("AT-04-04-06")
def test_cancelar_una_orden_rejected_es_rechazado(usuario, api):
    """HU-04-04 Escenario 6 (error): Cancelar una orden REJECTED."""
    # Dado un registro de orden REJECTED (que nunca llegó al libro): rechazo de
    # la capa de matching persistido (MARKET_NO_LIQUIDITY, RE-12)
    rechazada = crear_rejected_sin_liquidez(usuario, api)

    # Cuando se intenta cancelarla
    resp = cancelar(usuario, rechazada["orderId"])

    # Entonces se rechaza con ORDER_NOT_CANCELLABLE (409), details.status="REJECTED"
    err = assert_error(resp, "ORDER_NOT_CANCELLABLE")
    assert err["details"]["orderId"] == rechazada["orderId"], err
    assert err["details"]["status"] == "REJECTED", err


@pytest.mark.at("AT-04-04-07")
def test_cancelar_orden_inexistente(usuario):
    """HU-04-04 Escenario 7 (error): Orden inexistente."""
    # Cuando cancela un orderId que no existe
    order_id = "00000000-0000-4000-8000-000000000000"
    resp = cancelar(usuario, order_id)

    # Entonces se rechaza con ORDER_NOT_FOUND (404), details.orderId (RN-2)
    err = assert_error(resp, "ORDER_NOT_FOUND")
    assert "orderId" in (err.get("details") or {}), err


@pytest.mark.at("AT-04-04-08")
def test_cancelar_orden_de_otra_cuenta(usuario, usuario_b, rpc, api, limpiador):
    """HU-04-04 Escenario 8 (error): Orden de otra cuenta."""
    # Dado un trader A y una orden OPEN perteneciente a la cuenta B
    requerir_sin_asks_hasta(api, P2000)
    fondear(usuario_b, rpc, usdc_min=NOTIONAL_MIN)
    orden_b = alta_ok(usuario_b, cuerpo_orden("BUY", "LIMIT", P2000, Q_MIN), estado="OPEN")
    limpiador.registrar(usuario_b, orden_b["orderId"])
    blk_previo_b = balances(usuario_b)

    # Cuando A intenta cancelar la orden de B
    resp = cancelar(usuario, orden_b["orderId"])

    # Entonces se rechaza con ORDER_NOT_FOUND (404): no se revela que la orden
    # existe (RE-7; no UNAUTHORIZED)
    assert_error(resp, "ORDER_NOT_FOUND")

    # Y la orden de B permanece OPEN e intacta (INV-3 de B sin cambios)
    assert detalle(usuario_b, orden_b["orderId"])["status"] == "OPEN"
    assert balances(usuario_b) == blk_previo_b


@pytest.mark.at("AT-04-04-09")
def test_cancelar_pierde_contra_un_fill_total_ya_aplicado(usuario, usuario_b, rpc, api):
    """HU-04-04 Escenario 9 (secuencia): Cancelar pierde contra un fill total ya aplicado."""
    # Dado una orden de `usuario` que YA fue marcada FILLED: bid resting llenado
    # por completo por un taker antes de procesar la cancelación
    requerir_zona_limpia(api, P2000)
    fondear(usuario, rpc, usdc_min=NOTIONAL_MIN)
    orden = alta_ok(usuario, cuerpo_orden("BUY", "LIMIT", P2000, Q_MIN), estado="OPEN")
    fondear(usuario_b, rpc, eth_wei=Q_MIN)
    alta_ok(usuario_b, cuerpo_orden("SELL", "LIMIT", P2000, Q_MIN), estado="FILLED")
    esperar_orden(usuario, orden["orderId"], "FILLED")  # el fill se aplicó antes
    saldo_previo = balances(usuario)

    # Cuando llega la solicitud de cancelación
    resp = cancelar(usuario, orden["orderId"])

    # Entonces se rechaza con ORDER_NOT_CANCELLABLE (409); el fill prevalece
    err = assert_error(resp, "ORDER_NOT_CANCELLABLE")
    assert err["details"]["status"] == "FILLED", err

    # Y no se libera ni se duplica fondo alguno (INV-1, INV-4, RN-6)
    assert balances(usuario) == saldo_previo
    assert detalle(usuario, orden["orderId"])["status"] == "FILLED"


@pytest.mark.at("AT-04-04-10")
def test_cancelar_tras_fill_parcial_libera_el_remanente_vigente(usuario, usuario_b, rpc, api):
    """HU-04-04 Escenario 10 (secuencia): Cancelar tras un fill parcial ya aplicado."""
    # Dado una orden de 1 ETH que YA recibió un fill parcial de 0.4 ETH y está
    # PARTIALLY_FILLED (el fill se aplicó antes de la cancelación)
    requerir_zona_limpia(api, P2000)
    fondear(usuario, rpc, usdc_min=2_000_000_000)
    orden = alta_ok(usuario, cuerpo_orden("BUY", "LIMIT", P2000, ETH_1), estado="OPEN")
    fondear(usuario_b, rpc, eth_wei=400_000_000_000_000_000)
    alta_ok(
        usuario_b,
        cuerpo_orden("SELL", "LIMIT", P2000, 400_000_000_000_000_000),
        estado="FILLED",
    )
    esperar_orden(usuario, orden["orderId"], "PARTIALLY_FILLED")

    # Cuando se procesa la cancelación
    cancelada = cancelar_ok(usuario, orden["orderId"])

    # Entonces la orden queda CANCELLED con filledWei="400000000000000000"
    assert ejecutado_wei(cancelada) == 400_000_000_000_000_000

    # Y se libera la reserva del remanente vigente (reservaOrden post-fill = 1200000000),
    # no la original (RN-3, RN-7): disponible = 2000000000 - 800000000 consumidos
    assert_balances(usuario, "USDC", disp=1_200_000_000, blk=0)


@pytest.mark.at("AT-04-04-11")
def test_cancelar_sin_autenticacion(api):
    """HU-04-04 Escenario 11 (error): No autenticado."""
    # Dado un cliente sin credencial válida
    # Cuando intenta cancelar una orden
    resp = api.delete("/orders/00000000-0000-4000-8000-000000000000")

    # Entonces se rechaza con UNAUTHENTICATED (401) (RN-9)
    assert_error(resp, "UNAUTHENTICATED")


@pytest.mark.at("AT-04-04-13")
def test_cancelar_tras_fills_a_mejor_precio_deja_bloqueado_en_cero(
    usuario, usuario_b, rpc, api
):
    """HU-04-04 Escenario 13 (borde): Cancelar tras varios fills a mejor precio."""
    # Dado dos asks ajenos de 0.3 ETH a 1990000000 (mejor que el límite 2000000000)
    requerir_zona_limpia(api, P2000)
    fondear(usuario_b, rpc, eth_wei=600_000_000_000_000_000)
    alta_ok(
        usuario_b,
        cuerpo_orden("SELL", "LIMIT", 1_990_000_000, 300_000_000_000_000_000),
        estado="OPEN",
    )
    alta_ok(
        usuario_b,
        cuerpo_orden("SELL", "LIMIT", 1_990_000_000, 300_000_000_000_000_000),
        estado="OPEN",
    )
    # Y una orden BUY LIMIT 1 ETH @ 2000 con reserva inicial 2000000000 que
    # ejecuta dos fills a mejor precio al ingresar (consumo + liberación por
    # mejor precio actualizan reservaOrden fill a fill, HU-04-01 RN-8)
    fondear(usuario, rpc, usdc_min=5_000_000_000)
    orden = alta_ok(usuario, cuerpo_orden("BUY", "LIMIT", P2000, ETH_1))
    assert orden["status"] == "PARTIALLY_FILLED", orden
    assert ejecutado_wei(orden) == 600_000_000_000_000_000

    # Cuando cancela la orden
    cancelar_ok(usuario, orden["orderId"])

    # Entonces se libera exactamente el reservaOrden vigente y el bloqueado de
    # esa orden queda en 0, sin residuo por subaditividad del floor (RN-3, INV-3,
    # INV-7). Consumido: 2 x floor(3e17 x 1.99e9 / 1e18) = 1194000000
    assert_balances(usuario, "USDC", disp=5_000_000_000 - 1_194_000_000, blk=0)
    assert abiertas(usuario) == []
