"""Épica 04 — Persistencia de órdenes y reservas tras reinicio (INV-7, INV-8).

Cubre los tres escenarios de persistencia de la épica: AT-04-01-11 (la orden
abierta y su reserva sobreviven), AT-04-04-12 (la cancelación sobrevive) y
AT-04-05-13 (los estados sobreviven). Todos observan el SUT exclusivamente por
el contrato de la épica 09 (``POST/GET/DELETE /orders``, ``GET /balances``,
``GET /market/orderbook``); el disparo del reinicio lo provee el evaluador vía
``SUITE_CMD_REINICIO_SUT`` (ver ``comunes_reinicio``). Sin esa env var los tests
saltan con motivo explícito.

Tras cada reinicio se renueva la sesión (``relogin``): la spec no exige que los
tokens sobrevivan, pero sí las órdenes, sus prioridades y los balances.

Aislamiento: los tres tests operan en el nivel ``P2000`` con las guardas de
``comunes_ep04`` (``requerir_zona_limpia``) y registran en ``limpiador`` toda
orden que pudiera quedar resting.
"""

import pytest

from helpers.cuentas import crear_usuario

from comunes_ep04 import (  # noqa: F401 (limpiador es fixture)
    NOTIONAL_MIN,
    P2000,
    Q_MIN,
    alta_ok,
    assert_balances,
    bloqueado,
    cancelar_ok,
    cantidad_en_nivel,
    client_order_id,
    cuerpo_orden,
    detalle,
    disponible,
    ejecutado_wei,
    fondear,
    limpiador,
    requerir_zona_limpia,
)
from comunes_reinicio import comando_reinicio, reiniciar_sut, relogin


@pytest.mark.at("AT-04-01-11")
def test_orden_abierta_y_su_reserva_sobreviven_al_reinicio(
    api, usuario, usuario_b, rpc, limpiador
):
    """HU-04-01 Escenario 11 (persistencia): la orden abierta y su reserva sobreviven.

    - Dado un trader con una orden limit OPEN y su reserva bloqueada
    - Cuando el sistema se reinicia y reconstruye estado desde el ledger
    - Entonces la orden sigue OPEN con su prioridad precio-tiempo intacta (INV-7)
    - Y `bloqueado` y `disponible` reconstruidos coinciden exactamente con los
      previos (INV-8)

    La prioridad se observa black-box por el **orden de los fills**: un segundo
    bid en el mismo nivel, colocado después, sólo puede ejecutarse si el primero
    ya se consumió (FIFO por (precio, tiempo), HU-03-01 RN-2).
    """
    comando_reinicio()  # precondición antes del "Dado" caro (depósitos on-chain)
    requerir_zona_limpia(api, P2000)

    # Dado: dos bids en el mismo nivel — el de `usuario` primero
    fondear(usuario, rpc, usdc_min=NOTIONAL_MIN)
    fondear(usuario_b, rpc, usdc_min=NOTIONAL_MIN)
    primero = alta_ok(
        usuario, cuerpo_orden("BUY", "LIMIT", P2000, Q_MIN, client_id=client_order_id("p11-a")),
        estado="OPEN",
    )
    segundo = alta_ok(
        usuario_b, cuerpo_orden("BUY", "LIMIT", P2000, Q_MIN, client_id=client_order_id("p11-b")),
        estado="OPEN",
    )
    limpiador.registrar(usuario, primero["orderId"])
    limpiador.registrar(usuario_b, segundo["orderId"])
    disp_previo, blk_previo = disponible(usuario, "USDC"), bloqueado(usuario, "USDC")
    assert blk_previo >= NOTIONAL_MIN, "la orden OPEN debe tener su reserva bloqueada"

    # Cuando
    reiniciar_sut(api)
    relogin(usuario)
    relogin(usuario_b)

    # Entonces: la orden sigue OPEN, sin ejecución
    reconstruida = detalle(usuario, primero["orderId"])
    assert reconstruida["status"] == "OPEN", reconstruida
    assert ejecutado_wei(reconstruida) == 0, reconstruida

    # Y: disponible y bloqueado reconstruidos idénticos (INV-8, INV-3)
    assert_balances(usuario, "USDC", disp=disp_previo, blk=blk_previo)

    # Y: la prioridad precio-tiempo del nivel se conservó (INV-7) — un SELL de un
    # solo lote atiende al bid colocado primero
    assert cantidad_en_nivel(api, "bids", P2000) == 2 * Q_MIN
    vendedor = crear_usuario(api, prefijo="p11-sell")
    fondear(vendedor, rpc, eth_wei=Q_MIN)
    alta_ok(vendedor, cuerpo_orden("SELL", "LIMIT", P2000, Q_MIN), estado="FILLED")
    assert detalle(usuario, primero["orderId"])["status"] == "FILLED"
    assert detalle(usuario_b, segundo["orderId"])["status"] == "OPEN"


@pytest.mark.at("AT-04-04-12")
def test_cancelacion_sobrevive_al_reinicio(api, usuario, rpc):
    """HU-04-04 Escenario 12 (persistencia): la cancelación sobrevive al reinicio.

    - Dado una orden recién CANCELLED con su reserva liberada
    - Cuando el sistema se reinicia y reconstruye desde el ledger
    - Entonces la orden sigue CANCELLED, ausente del orderbook, y los balances
      reconstruidos coinciden (INV-8)
    """
    comando_reinicio()
    requerir_zona_limpia(api, P2000)

    # Dado: orden colocada y cancelada; la reserva volvió a `disponible`
    fondear(usuario, rpc, usdc_min=NOTIONAL_MIN)
    orden = alta_ok(
        usuario, cuerpo_orden("BUY", "LIMIT", P2000, Q_MIN, client_id=client_order_id("p12")),
        estado="OPEN",
    )
    cancelada = cancelar_ok(usuario, orden["orderId"])
    assert cancelada["status"] == "CANCELLED"
    disp_previo, blk_previo = disponible(usuario, "USDC"), bloqueado(usuario, "USDC")

    # Cuando
    reiniciar_sut(api)
    relogin(usuario)

    # Entonces: sigue CANCELLED
    reconstruida = detalle(usuario, orden["orderId"])
    assert reconstruida["status"] == "CANCELLED", reconstruida

    # Y: ausente del orderbook (el nivel quedó vacío: la zona estaba limpia)
    assert cantidad_en_nivel(api, "bids", P2000) == 0

    # Y: balances reconstruidos idénticos (la liberación de la reserva persistió)
    assert_balances(usuario, "USDC", disp=disp_previo, blk=blk_previo)


@pytest.mark.at("AT-04-05-13")
def test_estados_de_orden_sobreviven_al_reinicio(api, usuario, usuario_b, rpc, limpiador):
    """HU-04-05 Escenario 13 (persistencia): los estados sobreviven al reinicio.

    - Dado órdenes en distintos estados (OPEN, PARTIALLY_FILLED, FILLED, CANCELLED)
    - Cuando el sistema se reinicia y reconstruye desde el ledger/registro
    - Entonces cada orden conserva su estado y `filledWei`; las abiertas mantienen
      prioridad precio-tiempo (INV-7, INV-8)
    """
    comando_reinicio()
    requerir_zona_limpia(api, P2000)

    # Dado: las cuatro órdenes de `usuario`, todas en el nivel P2000.
    # `usuario` necesita 10 USDC por la FILLED + 20 por la parcial + 10 por la
    # abierta + 10 por la cancelada = 50; `usuario_b` vende 3 lotes (dos para
    # armar el "Dado" y uno para la prueba de prioridad posterior al reinicio).
    # Ambos fondeos llevan un lote/decena de margen.
    fondear(usuario, rpc, usdc_min=6 * NOTIONAL_MIN)
    fondear(usuario_b, rpc, eth_wei=4 * Q_MIN)

    # FILLED: `usuario_b` deja un ask y `usuario` lo cruza como taker
    alta_ok(usuario_b, cuerpo_orden("SELL", "LIMIT", P2000, Q_MIN), estado="OPEN")
    llena = alta_ok(
        usuario, cuerpo_orden("BUY", "LIMIT", P2000, Q_MIN, client_id=client_order_id("p13-f")),
        estado="FILLED",
    )

    # PARTIALLY_FILLED: bid de dos lotes, ejecutado a la mitad por `usuario_b`
    parcial = alta_ok(
        usuario,
        cuerpo_orden("BUY", "LIMIT", P2000, 2 * Q_MIN, client_id=client_order_id("p13-p")),
        estado="OPEN",
    )
    limpiador.registrar(usuario, parcial["orderId"])
    alta_ok(usuario_b, cuerpo_orden("SELL", "LIMIT", P2000, Q_MIN), estado="FILLED")

    # OPEN: bid posterior en el mismo nivel (queda detrás del remanente de `parcial`)
    abierta = alta_ok(
        usuario, cuerpo_orden("BUY", "LIMIT", P2000, Q_MIN, client_id=client_order_id("p13-o")),
        estado="OPEN",
    )
    limpiador.registrar(usuario, abierta["orderId"])

    # CANCELLED
    a_cancelar = alta_ok(
        usuario, cuerpo_orden("BUY", "LIMIT", P2000, Q_MIN, client_id=client_order_id("p13-c")),
        estado="OPEN",
    )
    cancelada = cancelar_ok(usuario, a_cancelar["orderId"])

    esperado = {
        llena["orderId"]: ("FILLED", Q_MIN),
        parcial["orderId"]: ("PARTIALLY_FILLED", Q_MIN),
        abierta["orderId"]: ("OPEN", 0),
        cancelada["orderId"]: ("CANCELLED", 0),
    }
    for order_id, (estado, filled) in esperado.items():
        actual = detalle(usuario, order_id)
        assert (actual["status"], ejecutado_wei(actual)) == (estado, filled), actual

    # Cuando
    reiniciar_sut(api)
    relogin(usuario)
    relogin(usuario_b)

    # Entonces: cada orden conserva estado y filledWei
    for order_id, (estado, filled) in esperado.items():
        actual = detalle(usuario, order_id)
        assert actual["status"] == estado, actual
        assert ejecutado_wei(actual) == filled, actual

    # Y: las abiertas conservan su prioridad — el nivel tiene el remanente de
    # `parcial` (1 lote) más `abierta` (1 lote), y el próximo SELL atiende primero
    # al remanente de `parcial`, que entró antes (INV-7)
    assert cantidad_en_nivel(api, "bids", P2000) == 2 * Q_MIN
    alta_ok(usuario_b, cuerpo_orden("SELL", "LIMIT", P2000, Q_MIN), estado="FILLED")
    assert detalle(usuario, parcial["orderId"])["status"] == "FILLED"
    assert detalle(usuario, abierta["orderId"])["status"] == "OPEN"
