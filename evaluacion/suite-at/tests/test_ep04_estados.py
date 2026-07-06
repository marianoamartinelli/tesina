"""Épica 04 — HU-04-05 Ciclo de vida y estados de la orden: tests black-box.

Spec: spec/04-gestion-de-ordenes/HU-04-05-ciclo-de-vida-y-estados.md
Las transiciones se observan por el `status` de las respuestas del alta y de
las consultas (`NEW` es transitorio interno y nunca observable, RN-11).

AT-04-05-13 y AT-04-05-14 (persistencia/recuperación tras reinicio) están
declarados en tests/no_automatizables_ep04.yaml.
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
    crear_filled,
    crear_rejected_sin_liquidez,
    cuerpo_orden,
    detalle,
    ejecutado_wei,
    esperar_orden,
    fondear,
    historial,
    limpiador,
    post_orden,
    remanente_wei,
    requerir_sin_asks_hasta,
    requerir_zona_limpia,
)


@pytest.mark.at("AT-04-05-01")
def test_limit_sin_match_queda_open(usuario, rpc, api, limpiador):
    """HU-04-05 Escenario 1: Limit sin match ⇒ OPEN."""
    # Dado un trader que coloca una limit válida sin contraparte cruzable
    requerir_sin_asks_hasta(api, P2000)
    fondear(usuario, rpc, usdc_min=NOTIONAL_MIN)

    # Cuando se procesa el alta
    orden = alta_ok(usuario, cuerpo_orden("BUY", "LIMIT", P2000, Q_MIN))
    limpiador.registrar(usuario, orden["orderId"])

    # Entonces la orden queda OPEN con filledWei="0" y remainingWei=quantityWei
    # (NEW es transitorio interno y no observable, RN-11)
    assert orden["status"] == "OPEN", orden
    assert ejecutado_wei(orden) == 0
    assert remanente_wei(orden) == Q_MIN
    assert detalle(usuario, orden["orderId"])["status"] == "OPEN"


@pytest.mark.at("AT-04-05-02")
def test_limit_con_match_parcial_queda_partially_filled(usuario, usuario_b, rpc, api, limpiador):
    """HU-04-05 Escenario 2: Limit con match parcial ⇒ NEW→PARTIALLY_FILLED."""
    # Dado solo 0.4 ETH cruzables (ask ajeno)
    requerir_zona_limpia(api, P2000)
    fondear(usuario_b, rpc, eth_wei=400_000_000_000_000_000)
    alta_ok(
        usuario_b,
        cuerpo_orden("SELL", "LIMIT", P2000, 400_000_000_000_000_000),
        estado="OPEN",
    )
    fondear(usuario, rpc, usdc_min=2_000_000_000)

    # Cuando coloca una limit de 1 ETH
    orden = alta_ok(usuario, cuerpo_orden("BUY", "LIMIT", P2000, ETH_1))
    limpiador.registrar(usuario, orden["orderId"])

    # Entonces ejecuta 0.4 ETH y queda PARTIALLY_FILLED, remanente resting (RN-3)
    assert orden["status"] == "PARTIALLY_FILLED", orden
    assert ejecutado_wei(orden) == 400_000_000_000_000_000


@pytest.mark.at("AT-04-05-03")
def test_limit_marketable_total_queda_filled(usuario, usuario_b, rpc, api):
    """HU-04-05 Escenario 3: Limit marketable total ⇒ NEW→FILLED."""
    # Dado liquidez suficiente cruzable
    # Cuando el trader coloca una limit que ejecuta completamente al entrar
    orden = crear_filled(usuario, usuario_b, rpc, api)

    # Entonces la orden queda FILLED con filledWei == quantityWei, sin remanente
    assert orden["status"] == "FILLED"
    assert ejecutado_wei(orden) == Q_MIN
    assert remanente_wei(orden) == 0
    assert abiertas(usuario) == []


@pytest.mark.at("AT-04-05-04")
def test_market_total_queda_filled_y_nunca_descansa(usuario, usuario_b, rpc, api):
    """HU-04-05 Escenario 4: Market total ⇒ NEW→FILLED."""
    # Dado liquidez suficiente (ask ajeno de 0.005 ETH a 2000)
    requerir_zona_limpia(api, P2000)
    fondear(usuario_b, rpc, eth_wei=Q_MIN)
    alta_ok(usuario_b, cuerpo_orden("SELL", "LIMIT", P2000, Q_MIN), estado="OPEN")
    fondear(usuario, rpc, usdc_min=NOTIONAL_MIN)

    # Cuando coloca una market que completa su objetivo
    orden = alta_ok(usuario, cuerpo_orden("BUY", "MARKET", quantity_wei=Q_MIN))

    # Entonces la orden queda FILLED y nunca descansó en el libro (RN-6)
    assert orden["status"] == "FILLED", orden
    assert ejecutado_wei(orden) == Q_MIN
    assert abiertas(usuario) == []


@pytest.mark.at("AT-04-05-05")
def test_market_parcial_queda_cancelled_con_remanente_descartado(usuario, usuario_b, rpc, api):
    """HU-04-05 Escenario 5 (borde): Market parcial ⇒ NEW→CANCELLED."""
    # Dado liquidez insuficiente para completar la market (solo 0.4 ETH)
    requerir_zona_limpia(api, P2000)
    fondear(usuario_b, rpc, eth_wei=400_000_000_000_000_000)
    alta_ok(
        usuario_b,
        cuerpo_orden("SELL", "LIMIT", P2000, 400_000_000_000_000_000),
        estado="OPEN",
    )
    fondear(usuario, rpc, usdc_min=800_000_000)  # costo del snapshot: 0.4 x 2000

    # Cuando se procesa la market por 1 ETH
    orden = alta_ok(usuario, cuerpo_orden("BUY", "MARKET", quantity_wei=ETH_1))

    # Entonces ejecuta lo disponible, descarta el remanente y queda CANCELLED
    # con filledWei > 0 (RN-6)
    assert orden["status"] == "CANCELLED", orden
    assert ejecutado_wei(orden) == 400_000_000_000_000_000
    assert abiertas(usuario) == []


@pytest.mark.at("AT-04-05-06")
def test_market_sin_liquidez_queda_rejected_persistida(usuario, api):
    """HU-04-05 Escenario 6 (error): Market sin liquidez ⇒ REJECTED persistido."""
    # Dado el lado opuesto vacío
    # Cuando el trader coloca una market
    # Entonces se rechaza con MARKET_NO_LIQUIDITY y la orden queda REJECTED, sin
    # fills ni reserva, y SE PERSISTE (aparece en HU-04-07) por ser un rechazo de
    # la capa de matching (RN-5, RE-12) — todo dentro del constructor:
    rechazada = crear_rejected_sin_liquidez(usuario, api)
    assert ejecutado_wei(rechazada) == 0

    # Y sin reserva alguna (la precondición es previa a fondos; usuario sin fondeo)
    assert_balances(usuario, "ETH", disp=0, blk=0)
    assert_balances(usuario, "USDC", disp=0, blk=0)
    assert abiertas(usuario) == []


@pytest.mark.at("AT-04-05-07")
def test_falla_de_validacion_no_se_persiste_como_orden(usuario):
    """HU-04-05 Escenario 7 (error): Falla de validación ⇒ no se persiste como orden."""
    # Dado un alta que viola una regla del par (INVALID_LOT_SIZE)
    resp = post_orden(usuario, cuerpo_orden("BUY", "LIMIT", P2000, 50_000_000_000_000))

    # Cuando se procesa el alta
    assert_error(resp, "INVALID_LOT_SIZE")

    # Entonces no se reserva nada ni hay fills; el rechazo de validación no se
    # persiste como orden y no aparece en el historial (RN-5, RE-12)
    assert_balances(usuario, "USDC", disp=0, blk=0)
    assert abiertas(usuario) == []
    assert historial(usuario) == []


@pytest.mark.at("AT-04-05-08")
def test_resting_open_a_partially_filled_a_filled(usuario, usuario_b, rpc, api):
    """HU-04-05 Escenario 8: Resting OPEN→PARTIALLY_FILLED→FILLED."""
    # Dado una orden OPEN de 1 ETH
    requerir_zona_limpia(api, P2000)
    fondear(usuario, rpc, usdc_min=2_000_000_000)
    orden = alta_ok(usuario, cuerpo_orden("BUY", "LIMIT", P2000, ETH_1), estado="OPEN")
    fondear(usuario_b, rpc, eth_wei=ETH_1)

    # Cuando un taker la ejecuta primero por 0.4 ETH
    alta_ok(
        usuario_b,
        cuerpo_orden("SELL", "LIMIT", P2000, 400_000_000_000_000_000),
        estado="FILLED",
    )
    parcial = esperar_orden(usuario, orden["orderId"], "PARTIALLY_FILLED")
    assert ejecutado_wei(parcial) == 400_000_000_000_000_000

    # Y luego por 0.6 ETH
    alta_ok(
        usuario_b,
        cuerpo_orden("SELL", "LIMIT", P2000, 600_000_000_000_000_000),
        estado="FILLED",
    )

    # Entonces transiciona OPEN → PARTIALLY_FILLED → FILLED con filledWei
    # monótona creciente hasta quantityWei (RN-7)
    final = esperar_orden(usuario, orden["orderId"], "FILLED")
    assert ejecutado_wei(final) == ETH_1
    assert remanente_wei(final) == 0


@pytest.mark.at("AT-04-05-09")
def test_cancelacion_open_a_cancelled(usuario, rpc, api):
    """HU-04-05 Escenario 9: Cancelación OPEN→CANCELLED."""
    # Dado una orden OPEN
    requerir_sin_asks_hasta(api, P2000)
    fondear(usuario, rpc, usdc_min=NOTIONAL_MIN)
    orden = alta_ok(usuario, cuerpo_orden("BUY", "LIMIT", P2000, Q_MIN), estado="OPEN")

    # Cuando el dueño la cancela
    cancelada = cancelar_ok(usuario, orden["orderId"])

    # Entonces queda CANCELLED y se libera la reserva (HU-04-04)
    assert cancelada["status"] == "CANCELLED"
    assert_balances(usuario, "USDC", disp=NOTIONAL_MIN, blk=0)


@pytest.mark.at("AT-04-05-10")
def test_cancelacion_partially_filled_a_cancelled(usuario, usuario_b, rpc, api):
    """HU-04-05 Escenario 10: Cancelación PARTIALLY_FILLED→CANCELLED."""
    # Dado una orden PARTIALLY_FILLED (bid de 1 ETH con fill parcial de 0.4)
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

    # Cuando el dueño la cancela
    cancelada = cancelar_ok(usuario, orden["orderId"])

    # Entonces queda CANCELLED con filledWei preservado y se libera el remanente
    assert ejecutado_wei(cancelada) == 400_000_000_000_000_000
    assert_balances(usuario, "USDC", disp=1_200_000_000, blk=0)


@pytest.mark.at("AT-04-05-11")
def test_transicion_prohibida_desde_terminal(usuario, usuario_b, rpc, api):
    """HU-04-05 Escenario 11 (error): Transición prohibida desde terminal."""
    # Dado una orden FILLED
    orden = crear_filled(usuario, usuario_b, rpc, api)

    # Cuando se intenta cancelarla (transición FILLED→CANCELLED)
    resp = cancelar(usuario, orden["orderId"])

    # Entonces se rechaza con ORDER_NOT_CANCELLABLE (409) y el estado permanece
    # FILLED (RN-2, RN-4)
    assert_error(resp, "ORDER_NOT_CANCELLABLE")
    assert detalle(usuario, orden["orderId"])["status"] == "FILLED"


@pytest.mark.at("AT-04-05-12")
def test_estado_terminal_inmutable(usuario, rpc, api):
    """HU-04-05 Escenario 12 (invariante): Estado terminal inmutable."""
    # Dado órdenes en estados terminales CANCELLED y REJECTED
    rechazada = crear_rejected_sin_liquidez(usuario, api)
    requerir_sin_asks_hasta(api, P2000)
    fondear(usuario, rpc, usdc_min=NOTIONAL_MIN)
    abierta = alta_ok(usuario, cuerpo_orden("BUY", "LIMIT", P2000, Q_MIN), estado="OPEN")
    cancelada = cancelar_ok(usuario, abierta["orderId"])
    saldo_previo = balances(usuario)

    # Cuando ocurre un evento posterior (intento de cancelación) sobre cada una
    for orden in (cancelada, rechazada):
        resp = cancelar(usuario, orden["orderId"])
        # Entonces la transición se rechaza y el estado no cambia (RN-2, RN-9)
        assert_error(resp, "ORDER_NOT_CANCELLABLE")
        actual = detalle(usuario, orden["orderId"])
        assert actual["status"] == orden["status"], actual
        assert ejecutado_wei(actual) == ejecutado_wei(orden)

    # Y no se mueven fondos asociados a esas órdenes
    assert balances(usuario) == saldo_previo
