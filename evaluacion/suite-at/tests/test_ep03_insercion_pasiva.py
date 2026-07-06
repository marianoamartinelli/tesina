"""Épica 03 / HU-03-02 — Inserción de orden limit pasiva (resting): tests black-box.

La condición de no-cruce (RN-1), el lado y nivel de inserción (RN-2/RN-3), la
cola FIFO (RN-4), el estado inicial (RN-5) y el respaldo (RN-6) se observan por
`POST /orders` (estado inmediato), `GET /market/orderbook` / `GET /market/ticker`
(posición en el libro), `GET /balances` (respaldo bloqueado) y `GET /market/trades`
(ausencia de trade al posar, RN-9).

AT-03-02-07 (unicidad interna de `orderId` ante una inserción duplicada que
sortea la idempotencia de la épica 04) se declara no automatizable en
`no_automatizables_ep03.yaml`: no hay superficie black-box para inyectar esa
inserción duplicada.
"""

import pytest

from helpers.cuentas import crear_usuario
from helpers.montos import WEI_POR_ETH, a_str, assert_monto, quote_min

from tests.comunes_ep03 import (
    assert_libro_no_cruzado,
    balances_por_activo,
    cancelar_abiertas,
    colocar_limit,
    fondear,
    libro,
    nivel,
    orden_actual,
    requerir_libro_vacio,
    requerir_sin_asks_cruzables,
    requerir_sin_bids_cruzables,
    ticker,
    trades_propios,
    ultimo_trade_id,
)

ETH = WEI_POR_ETH


@pytest.mark.at("AT-03-02-01")
def test_insercion_en_libro_vacio(api, usuario, rpc):
    """HU-03-02 Escenario 1: Inserción en libro vacío.

    - Dado un orderbook con asks vacío
    - Cuando ingresa BUY 1 ETH @ 2030.00 validada y con fondos
    - Entonces se inserta en bids como nivel nuevo, estado OPEN, filledWei "0"
    - Y se convierte en el best bid
    - Y no se emite ningún evento de trade (RN-9)
    """
    # Dado: libro vacío (asks vacío ⇒ no hay contraparte cruzable, RN-1)
    requerir_libro_vacio(api)
    fondear(usuario, rpc, usdc_min=2_100_000_000)
    trade_previo = ultimo_trade_id(api)
    try:
        # Cuando
        orden = colocar_limit(usuario, "BUY", 2_030_000_000, ETH, esperado="OPEN")

        # Entonces: OPEN sin ejecución (RN-5)
        assert orden["filledWei"] == "0"
        # nivel nuevo en bids con la cantidad completa (RN-2, RN-3)
        assert nivel(libro(api), "bids", 2_030_000_000) == ETH
        # Y: best bid (RN-3; libro estaba vacío)
        assert ticker(api)["bestBidPrice"] == "2030000000"
        # Y: sin evento de trade (RN-9): el último trade del mercado no cambió
        assert ultimo_trade_id(api) == trade_previo
    finally:
        cancelar_abiertas(usuario)


@pytest.mark.at("AT-03-02-02")
def test_buy_por_debajo_del_best_ask_se_posa(api, usuario, usuario_b, rpc):
    """HU-03-02 Escenario 2: BUY por debajo del best ask se posa (no cruza).

    - Dado un libro con best_ask = 2036.00
    - Cuando ingresa BUY 1 ETH @ 2035.00
    - Entonces best_ask_price > L ⇒ no cruza y se posa como best bid (RN-1)
    - Y se preserva best_bid < best_ask (RN-7)
    """
    requerir_libro_vacio(api)  # para poder afirmar "best" de ambos lados
    fondear(usuario, rpc, eth_wei=ETH)                # maker del ask
    fondear(usuario_b, rpc, usdc_min=2_100_000_000)   # entrante BUY
    try:
        # Dado
        colocar_limit(usuario, "SELL", 2_036_000_000, ETH, esperado="OPEN")

        # Cuando: L = 2035.00 < best_ask
        colocar_limit(usuario_b, "BUY", 2_035_000_000, ETH, esperado="OPEN")

        # Entonces: se posó como best bid sin cruzar (RN-1)
        t = ticker(api)
        assert t["bestBidPrice"] == "2035000000", t
        assert t["bestAskPrice"] == "2036000000", t
        # Y: libro no cruzado (RN-7, INV-7)
        assert_libro_no_cruzado(libro(api))
    finally:
        cancelar_abiertas(usuario, usuario_b)


@pytest.mark.at("AT-03-02-03")
def test_sell_por_encima_del_best_bid_se_posa(api, usuario, usuario_b, rpc):
    """HU-03-02 Escenario 3: SELL por encima del best bid se posa (no cruza).

    - Dado un libro con best_bid = 2040.00
    - Cuando ingresa SELL 1 ETH @ 2040.50
    - Entonces best_bid_price < L ⇒ no cruza y se posa como best ask (RN-1)
    - Y el libro no queda cruzado (RN-7)
    """
    requerir_libro_vacio(api)
    fondear(usuario, rpc, usdc_min=2_100_000_000)   # maker del bid
    fondear(usuario_b, rpc, eth_wei=ETH)            # entrante SELL
    try:
        # Dado
        colocar_limit(usuario, "BUY", 2_040_000_000, ETH, esperado="OPEN")

        # Cuando: L = 2040.50 > best_bid
        colocar_limit(usuario_b, "SELL", 2_040_500_000, ETH, esperado="OPEN")

        # Entonces
        t = ticker(api)
        assert t["bestAskPrice"] == "2040500000", t
        assert t["bestBidPrice"] == "2040000000", t
        # Y: no cruzado (RN-7)
        assert_libro_no_cruzado(libro(api))
    finally:
        cancelar_abiertas(usuario, usuario_b)


@pytest.mark.at("AT-03-02-04")
def test_insercion_al_final_de_la_cola_fifo(api, usuario, usuario_b, rpc):
    """HU-03-02 Escenario 4 (borde): Inserción al final de la cola FIFO de un nivel.

    - Dado un nivel bids @ 2045.00 con O1 y O2 previas (seq(O1) < seq(O2))
    - Cuando ingresa O3 BUY @ 2045.00 que no cruza
    - Entonces O3 queda última en prioridad temporal del nivel (RN-4): al consumir
      el nivel, se atiende O1, luego O2 y recién después O3

    El valor de `seq` no es observable (README RT-2: clave de orden interna); la
    posición al final de la cola se verifica por el orden de los fills.
    """
    precio = 2_045_000_000
    requerir_sin_asks_cruzables(api, precio)
    requerir_sin_bids_cruzables(api, precio)
    taker = crear_usuario(api, "ep03-fifo")
    fondear(usuario, rpc, usdc_min=4_200_000_000)     # O1 y O2
    fondear(usuario_b, rpc, usdc_min=2_100_000_000)   # O3
    fondear(taker, rpc, eth_wei=3 * ETH)
    try:
        # Dado: O1 y O2 ya en el nivel
        o1 = colocar_limit(usuario, "BUY", precio, ETH, esperado="OPEN")
        o2 = colocar_limit(usuario, "BUY", precio, ETH, esperado="OPEN")

        # Cuando: ingresa O3 (no cruza: no hay asks ≤ 2045)
        o3 = colocar_limit(usuario_b, "BUY", precio, ETH, esperado="OPEN")
        assert nivel(libro(api), "bids", precio) == 3 * ETH

        # Entonces: consumir 2 ETH del nivel atiende O1 y O2; O3 sigue intacta (RN-4)
        colocar_limit(taker, "SELL", precio, 2 * ETH, esperado="FILLED")
        assert orden_actual(usuario, o1["orderId"])["status"] == "FILLED"
        assert orden_actual(usuario, o2["orderId"])["status"] == "FILLED"
        o3_estado = orden_actual(usuario_b, o3["orderId"])
        assert o3_estado["status"] == "OPEN" and o3_estado["filledWei"] == "0"

        # Y: el siguiente consumo atiende a O3 (estaba al final de la cola)
        colocar_limit(taker, "SELL", precio, ETH, esperado="FILLED")
        assert orden_actual(usuario_b, o3["orderId"])["status"] == "FILLED"
    finally:
        cancelar_abiertas(usuario, usuario_b, taker)


@pytest.mark.at("AT-03-02-05")
def test_remanente_de_orden_cruzante_se_posa(api, usuario, usuario_b, rpc):
    """HU-03-02 Escenario 5 (borde): Remanente de una orden cruzante se posa.

    - Dado que una BUY 1 ETH @ 2050.50 cruzó y ejecutó 0.4 ETH contra el libro
    - Cuando ya no hay asks cruzables a su precio
    - Entonces su remanente 0.6 ETH se posa en bids @ 2050.50 con estado
      PARTIALLY_FILLED (RN-5)
    - Y el remanente queda respaldado por fondos bloqueados (RN-6)
    """
    precio_maker = 2_050_000_000
    limite = 2_050_500_000
    requerir_sin_asks_cruzables(api, limite)
    requerir_sin_bids_cruzables(api, precio_maker)
    fondear(usuario, rpc, eth_wei=ETH)                 # maker SELL 0.4
    fondear(usuario_b, rpc, usdc_min=2_100_000_000)    # taker BUY 1
    try:
        # Dado: un único ask cruzable de 0.4 ETH
        colocar_limit(usuario, "SELL", precio_maker, 4 * ETH // 10, esperado="OPEN")

        # Cuando: la BUY cruza 0.4 y ya no quedan asks a su precio
        orden = colocar_limit(usuario_b, "BUY", limite, ETH, esperado="PARTIALLY_FILLED")

        # Entonces: remanente 0.6 ETH posado a su precio límite (RN-5, HU-03-03 RN-8)
        assert orden["filledWei"] == a_str(4 * ETH // 10)
        remanente = assert_monto(orden["quantityWei"]) - assert_monto(orden["filledWei"])
        assert remanente == 6 * ETH // 10
        assert nivel(libro(api), "bids", limite) == remanente

        # Y: respaldo bloqueado del remanente a su precio límite (RN-6, HU-03-01 RN-10)
        balances = balances_por_activo(usuario_b)
        assert assert_monto(balances["USDC"]["locked"]) == quote_min(remanente, limite)
    finally:
        cancelar_abiertas(usuario, usuario_b)


@pytest.mark.at("AT-03-02-06")
def test_precio_igual_al_best_opuesto_cruza_no_se_posa(api, usuario, usuario_b, rpc):
    """HU-03-02 Escenario 6 (borde): Precio límite igual al best opuesto cruza.

    - Dado un libro con best_ask = 2055.00
    - Cuando ingresa BUY 1 ETH @ 2055.00 (L == best_ask)
    - Entonces la orden sí es cruzable (best_ask ≤ L): aplica HU-03-03 y no se
      posa antes de intentar el cruce (RN-1)
    """
    precio = 2_055_000_000
    requerir_sin_asks_cruzables(api, precio)
    requerir_sin_bids_cruzables(api, precio)
    fondear(usuario, rpc, eth_wei=ETH)
    fondear(usuario_b, rpc, usdc_min=2_100_000_000)
    try:
        # Dado
        maker = colocar_limit(usuario, "SELL", precio, ETH, esperado="OPEN")

        # Cuando: L exactamente igual al best ask
        entrante = colocar_limit(usuario_b, "BUY", precio, ETH, esperado="FILLED")

        # Entonces: cruzó (no se posó): hay fill al precio del maker y no quedó
        # nivel bids @ 2055 en el libro
        assert entrante["filledWei"] == a_str(ETH)
        assert nivel(libro(api), "bids", precio) == 0
        assert orden_actual(usuario, maker["orderId"])["status"] == "FILLED"
        fills = trades_propios(usuario_b, order_id=entrante["orderId"])
        assert len(fills) == 1 and assert_monto(fills[0]["priceMin"]) == precio
    finally:
        cancelar_abiertas(usuario, usuario_b)
