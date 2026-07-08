"""Épica 03 / HU-03-03 — Matching de orden limit contra el libro: tests black-box.

El algoritmo de cruce se observa por: el estado inmediato del `POST /orders`
(matching síncrono, HU-09-01 RN-5), los fills de `GET /trades` (pata propia con
`sequence`, `priceMin`, `quoteAmountMin`), el orderbook resultante y los
balances (`GET /balances`) para las reglas de conservación/liberación
(RN-13/RN-14/RN-15).

Fórmulas de referencia: `quote_min = floor(q × price / 10^18)` (floor, big
integers, convenciones-monetarias §2.2) y `fee = ceil(recibido × bps / 10000)`
(§3.3) vía `helpers.montos`; comparaciones siempre exactas.
"""

import pytest

from helpers.errores import assert_error
from helpers.montos import WEI_POR_ETH, a_str, assert_monto, fee_maker, fee_taker, quote_min

from tests.comunes_ep03 import (
    assert_libro_no_cruzado,
    balances_por_activo,
    cancelar_abiertas,
    client_order_id,
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


@pytest.mark.at("AT-03-03-01")
def test_fill_total_contra_un_unico_maker(api, usuario, usuario_b, rpc):
    """HU-03-03 Escenario 1: Fill total contra un único maker.

    - Dado un ask maker M: SELL 1 ETH @ 2060.00 de U2
    - Cuando U1 envía BUY 1 ETH @ 2061.00
    - Entonces cruza (ask ≤ L, RN-1) y ejecuta 1 ETH al precio del maker (RN-3)
      con quote_min = floor(10^18 × 2060000000 / 10^18) (RN-5)
    - Y taker y maker quedan FILLED; el maker se retira del libro (RN-9)
    - Y U1 recibe mejora de precio: pagó a 2060.00, no a 2061.00 (RN-3, RN-14)

    Valores del escenario (2000.00/2001.00) trasladados a la banda 2060.00/2061.00
    por aislamiento del libro compartido; propiedad invariante al traslado.
    """
    precio_maker, limite = 2_060_000_000, 2_061_000_000
    requerir_sin_asks_cruzables(api, limite)
    requerir_sin_bids_cruzables(api, precio_maker)
    fondear(usuario_b, rpc, eth_wei=ETH)  # U2: maker
    # U1 se fondea EXACTAMENTE con el quote a su límite: el sobrante final delata
    # a qué precio pagó realmente (mejora de precio, RN-14)
    fondeo_taker = quote_min(ETH, limite)
    fondear(usuario, rpc, usdc_min=fondeo_taker)
    try:
        # Dado
        maker = colocar_limit(usuario_b, "SELL", precio_maker, ETH, esperado="OPEN")

        # Cuando
        taker = colocar_limit(usuario, "BUY", limite, ETH, esperado="FILLED")

        # Entonces: fill de 1 ETH al precio del maker (RN-3, RN-5)
        fills = trades_propios(usuario, order_id=taker["orderId"])
        assert len(fills) == 1, fills
        assert assert_monto(fills[0]["priceMin"]) == precio_maker
        assert assert_monto(fills[0]["quantityWei"]) == ETH
        assert assert_monto(fills[0]["quoteAmountMin"]) == quote_min(ETH, precio_maker)

        # Y: ambos FILLED; maker retirado del libro (RN-9, HU-03-01 RN-7)
        assert orden_actual(usuario_b, maker["orderId"])["status"] == "FILLED"
        assert nivel(libro(api), "asks", precio_maker) == 0

        # Y: mejora de precio — pagó quote a 2060, el excedente bloqueado a 2061
        # quedó liberado (RN-14): disponible = fondeo − quote(2060), bloqueado = 0
        balances = balances_por_activo(usuario)
        assert assert_monto(balances["USDC"]["available"]) == fondeo_taker - quote_min(ETH, precio_maker)
        assert assert_monto(balances["USDC"]["locked"]) == 0
    finally:
        cancelar_abiertas(usuario, usuario_b)


@pytest.mark.at("AT-03-03-02")
def test_fill_parcial_del_taker_remanente_se_posa(api, usuario, usuario_b, rpc):
    """HU-03-03 Escenario 2: Fill parcial del taker, remanente se posa.

    - Dado un ask maker SELL 0.4 ETH @ 2065.00
    - Cuando ingresa BUY 1 ETH @ 2066.00
    - Entonces ejecuta 0.4 ETH a 2065.00, el maker queda FILLED y se retira (RN-4, RN-9)
    - Y el remanente 0.6 ETH del taker se posa en bids @ 2066.00, PARTIALLY_FILLED (RN-8)
    - Y el libro no queda cruzado (RN-11)

    Valores del escenario (2000.00/2001.00) trasladados a la banda 2065.00/2066.00
    por aislamiento del libro compartido; propiedad invariante al traslado.
    """
    precio_maker, limite = 2_065_000_000, 2_066_000_000
    requerir_sin_asks_cruzables(api, limite)
    requerir_sin_bids_cruzables(api, precio_maker)
    fondear(usuario_b, rpc, eth_wei=ETH)
    fondear(usuario, rpc, usdc_min=2_100_000_000)
    try:
        # Dado
        maker = colocar_limit(usuario_b, "SELL", precio_maker, 4 * ETH // 10, esperado="OPEN")

        # Cuando
        taker = colocar_limit(usuario, "BUY", limite, ETH, esperado="PARTIALLY_FILLED")

        # Entonces: q_fill = min(1, 0.4) = 0.4 ETH al precio del maker (RN-4, RN-5)
        fills = trades_propios(usuario, order_id=taker["orderId"])
        assert len(fills) == 1
        assert assert_monto(fills[0]["quantityWei"]) == 4 * ETH // 10
        assert assert_monto(fills[0]["quoteAmountMin"]) == quote_min(4 * ETH // 10, precio_maker)
        assert orden_actual(usuario_b, maker["orderId"])["status"] == "FILLED"
        assert nivel(libro(api), "asks", precio_maker) == 0

        # Y: remanente 0.6 posado a L (RN-8)
        assert taker["filledWei"] == a_str(4 * ETH // 10)
        assert nivel(libro(api), "bids", limite) == 6 * ETH // 10

        # Y: no cruzado (RN-11)
        assert_libro_no_cruzado(libro(api))
    finally:
        cancelar_abiertas(usuario, usuario_b)


@pytest.mark.at("AT-03-03-03")
def test_fill_parcial_del_maker_taker_se_completa(api, usuario, usuario_b, rpc):
    """HU-03-03 Escenario 3: Fill parcial del maker, taker se completa.

    - Dado un ask maker SELL 2 ETH @ 2070.00
    - Cuando ingresa BUY 1 ETH @ 2070.00
    - Entonces ejecuta 1 ETH y el taker queda FILLED (RN-4, RN-9)
    - Y el maker queda PARTIALLY_FILLED con remanente 1 ETH y permanece como
      best ask conservando su prioridad (RN-9)

    Valores del escenario (2000.00) trasladados a la banda 2070.00 por
    aislamiento del libro compartido; propiedad invariante al traslado.
    """
    precio = 2_070_000_000
    requerir_libro_vacio(api)  # el "permanece como best ask" exige libro propio
    fondear(usuario_b, rpc, eth_wei=2 * ETH)
    fondear(usuario, rpc, usdc_min=2_100_000_000)
    try:
        # Dado
        maker = colocar_limit(usuario_b, "SELL", precio, 2 * ETH, esperado="OPEN")

        # Cuando
        colocar_limit(usuario, "BUY", precio, ETH, esperado="FILLED")

        # Entonces: maker parcialmente ejecutado, con remanente exacto (RN-9)
        estado_maker = orden_actual(usuario_b, maker["orderId"])
        assert estado_maker["status"] == "PARTIALLY_FILLED"
        assert estado_maker["filledWei"] == a_str(ETH)
        assert assert_monto(estado_maker["quantityWei"]) - assert_monto(estado_maker["filledWei"]) == ETH

        # Y: permanece como best ask con la profundidad remanente
        assert ticker(api)["bestAskPrice"] == a_str(precio)
        assert nivel(libro(api), "asks", precio) == ETH
    finally:
        cancelar_abiertas(usuario, usuario_b)


@pytest.mark.at("AT-03-03-04")
def test_recorrido_por_prioridad_precio_tiempo(api, usuario, usuario_b, rpc):
    """HU-03-03 Escenario 4: Recorrido por prioridad precio-tiempo (varios makers).

    - Dado asks: A1 SELL 0.5 @ 2075.00 (1º), A2 SELL 0.5 @ 2075.00 (2º),
      A3 SELL 1 @ 2075.50 (3º)
    - Cuando ingresa BUY 1 ETH @ 2076.00
    - Entonces consume A1 y luego A2 (FIFO dentro del nivel, RN-2)
    - Y el taker queda FILLED; A1 y A2 FILLED; A3 no se toca y sigue en el libro

    Valores del escenario (2000.00/2000.50/2001.00) trasladados a la banda
    2075.00/2075.50/2076.00 por aislamiento del libro compartido; propiedad
    invariante al traslado.
    """
    precio_nivel, precio_a3, limite = 2_075_000_000, 2_075_500_000, 2_076_000_000
    requerir_sin_asks_cruzables(api, limite)
    requerir_sin_bids_cruzables(api, precio_nivel)
    fondear(usuario_b, rpc, eth_wei=2 * ETH)
    fondear(usuario, rpc, usdc_min=2_100_000_000)
    try:
        # Dado
        a1 = colocar_limit(usuario_b, "SELL", precio_nivel, ETH // 2, esperado="OPEN")
        a2 = colocar_limit(usuario_b, "SELL", precio_nivel, ETH // 2, esperado="OPEN")
        a3 = colocar_limit(usuario_b, "SELL", precio_a3, ETH, esperado="OPEN")

        # Cuando
        taker = colocar_limit(usuario, "BUY", limite, ETH, esperado="FILLED")

        # Entonces: A1 antes que A2 (FIFO por orden de llegada, RN-2): los fills del
        # maker, ordenados por sequence, referencian primero a A1 y luego a A2
        fills_maker = trades_propios(usuario_b)
        propios = [t for t in fills_maker if t["orderId"] in (a1["orderId"], a2["orderId"])]
        assert [t["orderId"] for t in propios] == [a1["orderId"], a2["orderId"]], propios
        assert all(assert_monto(t["priceMin"]) == precio_nivel for t in propios)

        # Y: estados finales; A3 intacta con su nivel completo
        assert taker["status"] == "FILLED"
        assert orden_actual(usuario_b, a1["orderId"])["status"] == "FILLED"
        assert orden_actual(usuario_b, a2["orderId"])["status"] == "FILLED"
        estado_a3 = orden_actual(usuario_b, a3["orderId"])
        assert estado_a3["status"] == "OPEN" and estado_a3["filledWei"] == "0"
        assert nivel(libro(api), "asks", precio_a3) == ETH
    finally:
        cancelar_abiertas(usuario, usuario_b)


@pytest.mark.at("AT-03-03-05")
def test_cruce_a_traves_de_multiples_niveles(api, usuario, usuario_b, rpc):
    """HU-03-03 Escenario 5: Cruce a través de múltiples niveles de precio.

    - Dado asks: A1 SELL 0.5 @ 2080.00, A2 SELL 0.5 @ 2080.50
    - Cuando ingresa BUY 1 ETH @ 2081.00
    - Entonces ejecuta A1 a 2080.00 y luego A2 a 2080.50, cada fill al precio de
      SU maker, no a un precio promedio (RN-2, RN-3, RN-5)
    - Y el taker queda FILLED

    Valores del escenario (2000.00/2000.50/2001.00) trasladados a la banda
    2080.00/2080.50/2081.00 por aislamiento del libro compartido; propiedad
    invariante al traslado.
    """
    p1, p2, limite = 2_080_000_000, 2_080_500_000, 2_081_000_000
    requerir_sin_asks_cruzables(api, limite)
    requerir_sin_bids_cruzables(api, p1)
    fondear(usuario_b, rpc, eth_wei=ETH)
    fondear(usuario, rpc, usdc_min=2_100_000_000)
    try:
        # Dado
        colocar_limit(usuario_b, "SELL", p1, ETH // 2, esperado="OPEN")
        colocar_limit(usuario_b, "SELL", p2, ETH // 2, esperado="OPEN")

        # Cuando
        taker = colocar_limit(usuario, "BUY", limite, ETH, esperado="FILLED")

        # Entonces: dos fills, en orden de prioridad de precio, cada uno con el
        # quote_min de SU maker (floor por fill, RN-5; sin promediar)
        fills = trades_propios(usuario, order_id=taker["orderId"])
        assert len(fills) == 2, fills
        assert [assert_monto(t["priceMin"]) for t in fills] == [p1, p2]
        assert assert_monto(fills[0]["quoteAmountMin"]) == quote_min(ETH // 2, p1)
        assert assert_monto(fills[1]["quoteAmountMin"]) == quote_min(ETH // 2, p2)
        assert taker["status"] == "FILLED"
    finally:
        cancelar_abiertas(usuario, usuario_b)


@pytest.mark.at("AT-03-03-06")
def test_precio_limite_igual_al_best_opuesto_si_cruza(api, usuario, usuario_b, rpc):
    """HU-03-03 Escenario 6 (borde): Precio límite igual al best opuesto sí cruza.

    - Dado un libro con best_ask = 2085.00
    - Cuando ingresa BUY 1 ETH @ 2085.00
    - Entonces cruza porque ask_price ≤ L (condición con ≤, RN-1) y ejecuta a 2085.00

    Valores del escenario (2000.00) trasladados a la banda 2085.00 por
    aislamiento del libro compartido; propiedad invariante al traslado.
    """
    precio = 2_085_000_000
    requerir_sin_asks_cruzables(api, precio)
    requerir_sin_bids_cruzables(api, precio)
    fondear(usuario_b, rpc, eth_wei=ETH)
    fondear(usuario, rpc, usdc_min=2_100_000_000)
    try:
        # Dado
        colocar_limit(usuario_b, "SELL", precio, ETH, esperado="OPEN")

        # Cuando / Entonces: cruza con igualdad de precios (RN-1) al precio maker
        taker = colocar_limit(usuario, "BUY", precio, ETH, esperado="FILLED")
        fills = trades_propios(usuario, order_id=taker["orderId"])
        assert len(fills) == 1 and assert_monto(fills[0]["priceMin"]) == precio
    finally:
        cancelar_abiertas(usuario, usuario_b)


@pytest.mark.at("AT-03-03-07")
def test_sin_contraparte_cruzable_se_posa_completo(api, usuario, usuario_b, rpc):
    """HU-03-03 Escenario 7 (borde): No hay contraparte cruzable, se posa completo.

    - Dado un libro con best_ask = 2091.00
    - Cuando ingresa BUY 1 ETH @ 2090.00
    - Entonces no cruza (ask > L) y se posa completa como bid @ 2090.00, OPEN
      (RN-7, RN-8, deriva a HU-03-02)
    - Y no se emite evento de trade

    Valores del escenario (best_ask 2001.00 / L 2000.00) trasladados a la banda
    2091.00/2090.00 por aislamiento del libro compartido; propiedad invariante
    al traslado.
    """
    precio_ask, limite = 2_091_000_000, 2_090_000_000
    requerir_sin_asks_cruzables(api, precio_ask)  # nuestro ask será el best cruzable
    requerir_sin_bids_cruzables(api, limite)
    fondear(usuario_b, rpc, eth_wei=ETH)
    fondear(usuario, rpc, usdc_min=2_100_000_000)
    try:
        # Dado
        colocar_limit(usuario_b, "SELL", precio_ask, ETH, esperado="OPEN")
        trade_previo = ultimo_trade_id(api)

        # Cuando
        orden = colocar_limit(usuario, "BUY", limite, ETH, esperado="OPEN")

        # Entonces: posada completa, sin ejecución
        assert orden["filledWei"] == "0"
        assert nivel(libro(api), "bids", limite) == ETH
        # Y: sin evento de trade (RN-9 de HU-03-02)
        assert ultimo_trade_id(api) == trade_previo
    finally:
        cancelar_abiertas(usuario, usuario_b)


@pytest.mark.at("AT-03-03-08")
def test_sell_entrante_cruza_bids_por_prioridad_descendente(api, usuario, usuario_b, rpc):
    """HU-03-03 Escenario 8 (borde): SELL entrante cruza bids por prioridad descendente.

    - Dado bids: B1 BUY 1 ETH @ 2095.00, B2 BUY 1 ETH @ 2094.50
    - Cuando ingresa SELL 1.5 ETH @ 2094.50
    - Entonces cruza primero B1 (mejor bid, 1 ETH @ 2095.00) y luego B2
      (0.5 ETH @ 2094.50) (RN-1, RN-2)
    - Y el taker queda FILLED; B1 FILLED; B2 PARTIALLY_FILLED con remanente 0.5 ETH

    Valores del escenario (2000.00/1999.50) trasladados a la banda 2095.00/2094.50
    por aislamiento del libro compartido; propiedad invariante al traslado.
    """
    p1, p2 = 2_095_000_000, 2_094_500_000
    requerir_sin_bids_cruzables(api, p2)
    requerir_sin_asks_cruzables(api, p1)
    fondear(usuario_b, rpc, usdc_min=4_200_000_000)  # B1 + B2
    fondear(usuario, rpc, eth_wei=2 * ETH)
    try:
        # Dado
        b1 = colocar_limit(usuario_b, "BUY", p1, ETH, esperado="OPEN")
        b2 = colocar_limit(usuario_b, "BUY", p2, ETH, esperado="OPEN")

        # Cuando: SELL cruzable contra ambos (bid ≥ L)
        taker = colocar_limit(usuario, "SELL", p2, 3 * ETH // 2, esperado="FILLED")

        # Entonces: primero el mejor bid (2095.00), después 2094.50 (RN-2)
        fills = trades_propios(usuario, order_id=taker["orderId"])
        assert [(assert_monto(t["priceMin"]), assert_monto(t["quantityWei"])) for t in fills] == [
            (p1, ETH),
            (p2, ETH // 2),
        ], fills

        # Y: estados y remanente de B2
        assert orden_actual(usuario_b, b1["orderId"])["status"] == "FILLED"
        estado_b2 = orden_actual(usuario_b, b2["orderId"])
        assert estado_b2["status"] == "PARTIALLY_FILLED"
        assert assert_monto(estado_b2["quantityWei"]) - assert_monto(estado_b2["filledWei"]) == ETH // 2
        assert nivel(libro(api), "bids", p2) == ETH // 2
    finally:
        cancelar_abiertas(usuario, usuario_b)


@pytest.mark.at("AT-03-03-09")
def test_mejora_de_precio_libera_excedente_del_buy(api, usuario, usuario_b, rpc):
    """HU-03-03 Escenario 9 (conservación): Mejora de precio libera excedente del BUY.

    - Dado que U1 envía BUY 1 ETH @ 2101.00 con quote bloqueado a 2101.00
    - Cuando se ejecuta contra un maker a 2100.00
    - Entonces el quote realmente pagado es el de 2100.00, no el de 2101.00
    - Y la diferencia bloqueada de más se libera (bloqueado→disponible) (RN-14)
    - Y se conserva Σ total(·, USDC) (INV-1, RN-13)

    Valores del escenario (2000.00/2001.00) trasladados a la banda 2100.00/2101.00
    por aislamiento del libro compartido; la propiedad (excedente liberado =
    quote(L) − quote(maker), acá 1000000) es invariante al traslado porque la
    separación L − maker = 1.00 se preserva.
    """
    precio_maker, limite = 2_100_000_000, 2_101_000_000
    requerir_sin_asks_cruzables(api, limite)
    requerir_sin_bids_cruzables(api, precio_maker)
    fondear(usuario_b, rpc, eth_wei=ETH)
    fondeo = quote_min(ETH, limite)  # exactamente el bloqueo a L
    fondear(usuario, rpc, usdc_min=fondeo)
    try:
        # Dado / Cuando
        colocar_limit(usuario_b, "SELL", precio_maker, ETH, esperado="OPEN")
        colocar_limit(usuario, "BUY", limite, ETH, esperado="FILLED")

        pagado = quote_min(ETH, precio_maker)
        liberado = fondeo - pagado  # = quote(L) − quote(maker) = 1000000

        # Entonces: pagó al precio maker; el excedente quedó liberado (RN-14, INV-3)
        b_u1 = balances_por_activo(usuario)
        assert assert_monto(b_u1["USDC"]["available"]) == liberado
        assert assert_monto(b_u1["USDC"]["locked"]) == 0

        # Y: conservación de USDC entre las partes y la cuenta de fees (INV-1):
        # el vendedor recibe el mismo quote_min menos su fee (que va al exchange)
        fill_maker = trades_propios(usuario_b)[-1]
        fee = assert_monto(fill_maker["feeAmount"])
        assert fill_maker["feeAsset"] == "USDC"  # maker SELL recibe USDC (§3.3)
        assert fee == fee_maker(pagado)
        b_u2 = balances_por_activo(usuario_b)
        assert assert_monto(b_u2["USDC"]["total"]) == pagado - fee
        # Σ total(U1) + Σ total(U2) + fee(EX) == fondeo inicial (nada se crea/destruye)
        assert assert_monto(b_u1["USDC"]["total"]) + assert_monto(b_u2["USDC"]["total"]) + fee == fondeo
    finally:
        cancelar_abiertas(usuario, usuario_b)


@pytest.mark.at("AT-03-03-10")
def test_auto_cruce_detectado_durante_el_recorrido(api, usuario, rpc):
    """HU-03-03 Escenario 10 (error): Auto-cruce detectado durante el recorrido.

    - Dado un libro cuyo best ask cruzable pertenece a la misma cuenta del taker
    - Cuando el taker intentaría matchear contra esa orden propia
    - Entonces se rechaza con SELF_TRADE_BLOCKED (422) sin aplicar fills (RN-12;
      detalle de la política en HU-03-06)
    """
    precio = 2_105_000_000
    requerir_sin_asks_cruzables(api, precio)
    requerir_sin_bids_cruzables(api, precio)
    fondear(usuario, rpc, eth_wei=ETH, usdc_min=2_200_000_000)
    try:
        # Dado: el best ask cruzable es propio
        propia = colocar_limit(usuario, "SELL", precio, ETH, esperado="OPEN")
        trade_previo = ultimo_trade_id(api)

        # Cuando: la misma cuenta envía la BUY cruzante
        resp = usuario.api.post(
            "/orders",
            json={
                "clientOrderId": client_order_id(),
                "symbol": "ETH-USDC",
                "side": "BUY",
                "type": "LIMIT",
                "priceMin": a_str(precio),
                "quantityWei": a_str(ETH),
            },
        )

        # Entonces: SELF_TRADE_BLOCKED (422), sin fills (RN-12, HU-03-06 RN-3/RN-4)
        err = assert_error(resp, "SELF_TRADE_BLOCKED")
        assert err["details"]["restingOrderId"] == propia["orderId"]
        assert ultimo_trade_id(api) == trade_previo
        assert orden_actual(usuario, propia["orderId"])["status"] == "OPEN"
        assert nivel(libro(api), "asks", precio) == ETH
    finally:
        cancelar_abiertas(usuario)


@pytest.mark.at("AT-03-03-11")
def test_liberacion_acumulada_de_excedente_en_buy_multifill(api, usuario, usuario_b, rpc):
    """HU-03-03 Escenario 11 (conservación): Liberación acumulada en BUY multi-fill.

    - Dado U1 con BUY 1 ETH @ 2111.00 y quote bloqueado a L
    - Y asks: A1 SELL 0.5 @ 2110.00, A2 SELL 0.5 @ 2110.50
    - Cuando ejecuta a través de ambos niveles (RN-2, RN-3)
    - Entonces cada fill libera su excedente
      liberado_fill = floor(q×L/10^18) − floor(q×maker/10^18) (RN-14)
    - Y el total pagado + excedente liberado reconstituye el bloqueo inicial
      (INV-1, INV-3); el taker queda FILLED

    Valores del escenario (2000.00/2000.50/2001.00) trasladados a la banda
    2110.00/2110.50/2111.00 por aislamiento del libro compartido; la propiedad
    (excedente por fill = quote(L) − quote(maker), acá 500000 y 250000) es
    invariante al traslado porque las separaciones de precio se preservan.
    """
    p1, p2, limite = 2_110_000_000, 2_110_500_000, 2_111_000_000
    requerir_sin_asks_cruzables(api, limite)
    requerir_sin_bids_cruzables(api, p1)
    fondear(usuario_b, rpc, eth_wei=ETH)
    fondeo = quote_min(ETH, limite)  # bloqueo exacto a L
    fondear(usuario, rpc, usdc_min=fondeo)
    try:
        # Dado
        colocar_limit(usuario_b, "SELL", p1, ETH // 2, esperado="OPEN")
        colocar_limit(usuario_b, "SELL", p2, ETH // 2, esperado="OPEN")

        # Cuando
        taker = colocar_limit(usuario, "BUY", limite, ETH, esperado="FILLED")

        # Entonces: quote_min por fill al precio de su maker (RN-5)
        fills = trades_propios(usuario, order_id=taker["orderId"])
        assert len(fills) == 2
        pagado_1 = assert_monto(fills[0]["quoteAmountMin"])
        pagado_2 = assert_monto(fills[1]["quoteAmountMin"])
        assert pagado_1 == quote_min(ETH // 2, p1)
        assert pagado_2 == quote_min(ETH // 2, p2)

        # excedente liberado por fill (fórmula RN-14) y total
        liberado_1 = quote_min(ETH // 2, limite) - pagado_1
        liberado_2 = quote_min(ETH // 2, limite) - pagado_2
        liberado_total = fondeo - (pagado_1 + pagado_2)
        assert liberado_total == liberado_1 + liberado_2  # suma por fill == total (RN-14)

        # Y: disponible(U1, USDC) aumentó exactamente el excedente; nada quedó bloqueado
        balances = balances_por_activo(usuario)
        assert assert_monto(balances["USDC"]["available"]) == liberado_total
        assert assert_monto(balances["USDC"]["locked"]) == 0

        # Y: el ETH recibido descuenta la fee taker por fill (ceil, §3.3) — el
        # bloqueo inicial se reconstituye entre pagado y liberado (INV-1, INV-3)
        fee_eth = fee_taker(ETH // 2) + fee_taker(ETH // 2)
        assert assert_monto(balances["ETH"]["available"]) == ETH - fee_eth
        assert taker["status"] == "FILLED"
    finally:
        cancelar_abiertas(usuario, usuario_b)


@pytest.mark.at("AT-03-03-12")
def test_sell_con_mejora_de_precio_no_libera_usdc(api, usuario, usuario_b, rpc):
    """HU-03-03 Escenario 12 (conservación): SELL con mejora de precio no libera USDC.

    - Dado un libro con best_bid = 2115.00
    - Cuando U1 envía SELL 1 ETH @ 2114.50 (bloquea 1 ETH, no USDC)
    - Entonces cruza al precio del maker 2115.00 y RECIBE ese quote_min, no el de
      su límite (RN-3, RN-15)
    - Y no hay transición bloqueado→disponible en USDC del vendedor: su bloqueo
      estaba en ETH y se consumió íntegro (RN-15, INV-2, INV-3)

    Valores del escenario (best_bid 2000.00 / L 1999.50) trasladados a la banda
    2115.00/2114.50 por aislamiento del libro compartido; propiedad invariante
    al traslado.
    """
    precio_maker, limite = 2_115_000_000, 2_114_500_000
    requerir_sin_bids_cruzables(api, limite)
    requerir_sin_asks_cruzables(api, precio_maker)
    fondear(usuario_b, rpc, usdc_min=2_200_000_000)  # maker BUY
    fondear(usuario, rpc, eth_wei=ETH)               # U1: SOLO ETH (USDC = 0)
    try:
        # Dado
        colocar_limit(usuario_b, "BUY", precio_maker, ETH, esperado="OPEN")

        # Cuando
        taker = colocar_limit(usuario, "SELL", limite, ETH, esperado="FILLED")

        # Entonces: recibió el quote del maker (mejora), no el de su límite (RN-3, RN-15)
        fills = trades_propios(usuario, order_id=taker["orderId"])
        recibido_bruto = assert_monto(fills[0]["quoteAmountMin"])
        assert recibido_bruto == quote_min(ETH, precio_maker)
        assert recibido_bruto > quote_min(ETH, limite)  # mejora de precio efectiva

        # Y: nada de USDC estuvo/quedó bloqueado; el total de USDC del vendedor es
        # exactamente lo recibido neto de fee taker (no se "liberó" USDC inexistente:
        # de otro modo total > recibido_neto violaría INV-1/INV-2)
        balances = balances_por_activo(usuario)
        recibido_neto = recibido_bruto - fee_taker(recibido_bruto)
        assert assert_monto(balances["USDC"]["locked"]) == 0
        assert assert_monto(balances["USDC"]["available"]) == recibido_neto
        assert assert_monto(balances["USDC"]["total"]) == recibido_neto
        # el bloqueo en ETH se consumió íntegro (RN-15)
        assert assert_monto(balances["ETH"]["total"]) == 0
    finally:
        cancelar_abiertas(usuario, usuario_b)
