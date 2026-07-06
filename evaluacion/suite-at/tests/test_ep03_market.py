"""Épica 03 / HU-03-04 — Ejecución de orden market: tests black-box.

Una MARKET siempre es taker, no lleva precio y nunca descansa (RN-1, RN-7). El
presupuesto `B` de una `MARKET BUY` es un parámetro interno motor⇄épica 04
(RN-14): black-box, la épica 04 reserva el costo del barrido del snapshot para
la forma `quantityWei` (HU-04-02 RN-5) —por lo que esa forma nunca agota `B`— y
para la forma `quoteOrderQty` el presupuesto ES el objetivo. Los escenarios de
presupuesto se construyen por la única vía observable: `quoteOrderQty`
(AT-03-04-05) y un best ask cuyo lot cuesta más que el presupuesto (AT-03-04-09).

Los tests MARKET exigen que el lado opuesto contenga sólo la liquidez del
escenario (una MARKET consume el mejor precio global): se verifica el Dado y se
salta ante estado residual.
"""

import pytest

from helpers.errores import assert_error
from helpers.montos import (
    LOT_SIZE,
    WEI_POR_ETH,
    a_str,
    assert_monto,
    fee_taker,
    quote_min,
)

from tests.comunes_ep03 import (
    balances_por_activo,
    cancelar_abiertas,
    colocar_limit,
    colocar_market,
    cuerpo_market,
    fondear,
    libro,
    nivel,
    orden_actual,
    orden_por_client_id,
    requerir_lado_vacio,
    requerir_libro_vacio,
    snapshot_balances,
    trades_propios,
    ultimo_trade_id,
)

ETH = WEI_POR_ETH


@pytest.mark.at("AT-03-04-01")
def test_market_sell_ejecuta_total_contra_varios_bids(api, usuario, usuario_b, rpc):
    """HU-03-04 Escenario 1: MARKET SELL ejecuta total contra varios bids.

    - Dado bids: B1 BUY 0.6 ETH @ 2120.00 (1º), B2 BUY 0.5 ETH @ 2119.50 (2º)
    - Cuando ingresa MARKET SELL 1 ETH
    - Entonces consume B1 (0.6 @ 2120.00) y luego B2 (0.4 @ 2119.50) por
      prioridad descendente (RN-2, RN-3), a precio del maker (RN-4)
    - Y el taker queda FILLED; B1 FILLED; B2 PARTIALLY_FILLED con 0.1 ETH
    """
    p1, p2 = 2_120_000_000, 2_119_500_000
    requerir_lado_vacio(api, "bids")  # la MARKET consume el mejor bid global
    fondear(usuario_b, rpc, usdc_min=2_400_000_000)
    fondear(usuario, rpc, eth_wei=ETH)
    try:
        # Dado
        b1 = colocar_limit(usuario_b, "BUY", p1, 6 * ETH // 10, esperado="OPEN")
        b2 = colocar_limit(usuario_b, "BUY", p2, ETH // 2, esperado="OPEN")

        # Cuando
        taker = colocar_market(usuario, "SELL", q_wei=ETH, esperado="FILLED")
        assert taker["filledWei"] == a_str(ETH)

        # Entonces: fills a precio de cada maker, en orden de prioridad (RN-2..RN-4)
        fills = trades_propios(usuario, order_id=taker["orderId"])
        assert [(assert_monto(t["priceMin"]), assert_monto(t["quantityWei"])) for t in fills] == [
            (p1, 6 * ETH // 10),
            (p2, 4 * ETH // 10),
        ], fills
        assert assert_monto(fills[0]["quoteAmountMin"]) == quote_min(6 * ETH // 10, p1)
        assert assert_monto(fills[1]["quoteAmountMin"]) == quote_min(4 * ETH // 10, p2)

        # Y: estados finales; B2 permanece con el remanente
        assert orden_actual(usuario_b, b1["orderId"])["status"] == "FILLED"
        estado_b2 = orden_actual(usuario_b, b2["orderId"])
        assert estado_b2["status"] == "PARTIALLY_FILLED"
        assert assert_monto(estado_b2["quantityWei"]) - assert_monto(estado_b2["filledWei"]) == ETH // 10
        assert nivel(libro(api), "bids", p2) == ETH // 10
    finally:
        cancelar_abiertas(usuario, usuario_b)


@pytest.mark.at("AT-03-04-02")
def test_market_buy_ejecuta_total_contra_varios_asks(api, usuario, usuario_b, rpc):
    """HU-03-04 Escenario 2: MARKET BUY ejecuta total contra varios asks.

    - Dado asks: A1 SELL 1 ETH @ 2125.00, A2 SELL 1 ETH @ 2125.50 y presupuesto
      reservado suficiente (la épica 04 reserva el costo del barrido, HU-04-02 RN-5)
    - Cuando ingresa MARKET BUY 2 ETH
    - Entonces consume A1 y A2 al precio de cada maker; costo total ≤ B (RN-4, RN-5)
    - Y el taker queda FILLED; el excedente de la reserva se libera (RN-10)
    """
    p1, p2 = 2_125_000_000, 2_125_500_000
    requerir_lado_vacio(api, "asks")
    fondear(usuario_b, rpc, eth_wei=2 * ETH)
    fondeo = 4_300_000_000  # > costo total 4250.50 USDC
    fondear(usuario, rpc, usdc_min=fondeo)
    try:
        # Dado
        colocar_limit(usuario_b, "SELL", p1, ETH, esperado="OPEN")
        colocar_limit(usuario_b, "SELL", p2, ETH, esperado="OPEN")

        # Cuando
        taker = colocar_market(usuario, "BUY", q_wei=2 * ETH, esperado="FILLED")
        assert taker["filledWei"] == a_str(2 * ETH)

        # Entonces: un fill por maker, cada uno a su precio (RN-4)
        fills = trades_propios(usuario, order_id=taker["orderId"])
        assert [assert_monto(t["priceMin"]) for t in fills] == [p1, p2]
        costo_total = quote_min(ETH, p1) + quote_min(ETH, p2)
        assert sum(assert_monto(t["quoteAmountMin"]) for t in fills) == costo_total

        # Y: lo reservado y no consumido quedó liberado (RN-10, INV-3)
        balances = balances_por_activo(usuario)
        assert assert_monto(balances["USDC"]["locked"]) == 0
        assert assert_monto(balances["USDC"]["available"]) == fondeo - costo_total
        # el ETH recibido descuenta la fee taker por fill (ceil, convenciones §3.3)
        assert assert_monto(balances["ETH"]["available"]) == 2 * ETH - 2 * fee_taker(ETH)
    finally:
        cancelar_abiertas(usuario, usuario_b)


@pytest.mark.at("AT-03-04-03")
def test_market_parcial_por_libro_agotado(api, usuario, usuario_b, rpc):
    """HU-03-04 Escenario 3 (borde): MARKET parcial por libro agotado.

    - Dado asks con liquidez total 0.8 ETH: A1 0.5 @ 2130.00, A2 0.3 @ 2130.50
    - Cuando ingresa MARKET BUY 1 ETH con presupuesto suficiente
    - Entonces ejecuta 0.8 ETH y el remanente 0.2 se DESCARTA (no se posa, RN-7)
    - Y la orden queda terminal CANCELLED con filledWei 0.8 ETH, sin error HTTP
      (RN-9; el `reason = MARKET_EXHAUSTED` viaja en el order-update interno,
      HU-03-05 RN-5 — el objeto orden REST no lo transporta)
    - Y la reserva no consumida se libera (RN-10)
    """
    p1, p2 = 2_130_000_000, 2_130_500_000
    requerir_lado_vacio(api, "asks")
    fondear(usuario_b, rpc, eth_wei=ETH)
    fondeo = 1_800_000_000
    fondear(usuario, rpc, usdc_min=fondeo)
    try:
        # Dado: 0.8 ETH de liquidez total
        colocar_limit(usuario_b, "SELL", p1, ETH // 2, esperado="OPEN")
        colocar_limit(usuario_b, "SELL", p2, 3 * ETH // 10, esperado="OPEN")

        # Cuando: 201 (hubo ejecución), estado terminal CANCELLED (RN-9)
        taker = colocar_market(usuario, "BUY", q_wei=ETH, esperado="CANCELLED")

        # Entonces: ejecutó exactamente la liquidez disponible; remanente descartado
        assert taker["filledWei"] == a_str(8 * ETH // 10)
        lib = libro(api)
        assert lib["asks"] == [], lib["asks"]          # el libro quedó agotado
        assert nivel(lib, "bids", p1) == 0             # y la MARKET no se posó (RN-7)

        pagado = quote_min(ETH // 2, p1) + quote_min(3 * ETH // 10, p2)
        # Y: la reserva no consumida se liberó íntegra (RN-10, INV-3)
        balances = balances_por_activo(usuario)
        assert assert_monto(balances["USDC"]["locked"]) == 0
        assert assert_monto(balances["USDC"]["available"]) == fondeo - pagado
    finally:
        cancelar_abiertas(usuario, usuario_b)


@pytest.mark.at("AT-03-04-04")
def test_market_sin_liquidez_lado_opuesto_vacio(api, usuario):
    """HU-03-04 Escenario 4 (error): MARKET sin liquidez (lado opuesto vacío).

    - Dado un libro con asks vacío
    - Cuando ingresa MARKET BUY 1 ETH
    - Entonces se rechaza con MARKET_NO_LIQUIDITY (422), terminal REJECTED,
      cero fills (RN-8)
    - Y la reserva se libera íntegra; balances intactos (INV-2, INV-3): la
      comprobación es previa a fondos (HU-04-02 RN-4), no requiere balance
    """
    # Dado: asks vacío (precondición global de una MARKET BUY)
    requerir_lado_vacio(api, "asks")
    antes = snapshot_balances(usuario)  # cuenta fresca, sin fondeo
    cid = "ep03-mkt-noliq"

    # Cuando
    resp = usuario.api.post("/orders", json={**cuerpo_market("BUY", q_wei=ETH), "clientOrderId": cid})

    # Entonces: MARKET_NO_LIQUIDITY (422), precedencia paso 7 de modelo-de-errores §4
    assert_error(resp, "MARKET_NO_LIQUIDITY")

    # Y: terminal REJECTED, cero fills, sin remanente en el libro (RN-8, RN-9)
    registrada = orden_por_client_id(usuario, cid)
    if registrada is not None:  # HU-04-02 RN-4: se persiste como REJECTED
        assert registrada["status"] == "REJECTED"
        assert registrada["filledWei"] == "0"
    assert libro(api)["asks"] == []

    # Y: balances idénticos (nada se reservó ni se ejecutó, INV-2/INV-3)
    assert snapshot_balances(usuario) == antes


@pytest.mark.at("AT-03-04-05")
def test_market_buy_detenida_por_presupuesto(api, usuario, usuario_b, rpc):
    """HU-03-04 Escenario 5 (borde): MARKET BUY detenida por presupuesto.

    - Dado asks: A1 SELL 1 ETH @ 2135.00, A2 SELL 1 ETH @ 2135.50 y presupuesto
      B = quote(A1) + 500 USDC
    - Cuando ingresa una MARKET BUY acotada por ese presupuesto
    - Entonces ejecuta A1 completo y de A2 toma la máxima cantidad múltiplo de
      lot cuyo quote_min ≤ B_rem: q' = max_lots × lot (fórmula RN-5)
    - Y la ejecución se detiene por presupuesto (A2 conserva liquidez); A2 queda
      PARTIALLY_FILLED con remainingWei = 1 ETH − q', conservando su nivel

    TODO-REVISAR: el AT estipula un B entregado al motor menor al costo del
    barrido y estado terminal CANCELLED + reason MARKET_BUDGET_EXHAUSTED. Ese B
    no es construible black-box: para la forma `quantityWei` la épica 04 reserva
    SIEMPRE el costo del barrido del snapshot (HU-04-02 RN-5) y la forma
    `quoteOrderQty` completa su objetivo al agotar el presupuesto ⇒ FILLED
    (HU-04-02 RN-7, AT-04-02-01). Aquí se verifica la mecánica normativa de
    HU-03-04 RN-5 (max_lots, q', detención por presupuesto) vía `quoteOrderQty`;
    el estado CANCELLED por presupuesto queda para evaluación white-box.
    """
    p1, p2 = 2_135_000_000, 2_135_500_000
    requerir_lado_vacio(api, "asks")
    fondear(usuario_b, rpc, eth_wei=2 * ETH)
    fondeo = 2_700_000_000
    fondear(usuario, rpc, usdc_min=fondeo)

    presupuesto = quote_min(ETH, p1) + 500_000_000  # consume A1 y deja B_rem = 500 USDC
    try:
        # Dado
        a1 = colocar_limit(usuario_b, "SELL", p1, ETH, esperado="OPEN")
        a2 = colocar_limit(usuario_b, "SELL", p2, ETH, esperado="OPEN")

        # Cuando: MARKET BUY con techo de gasto = presupuesto (RN-5, RN-14)
        taker = colocar_market(usuario, "BUY", quote_order_qty=presupuesto)
        # TODO-REVISAR: para la forma quoteOrderQty detenida por presupuesto con
        # residuo sub-lot, HU-04-02 RN-7/AT-04-02-01 sugiere FILLED (objetivo
        # gastado) y HU-03-04 RN-9 sugiere CANCELLED (presupuesto agotado con
        # filledWei > 0); la spec no fija cuál prevalece ⇒ se aceptan ambos
        # estados terminales y se verifica la mecánica cuantitativa, que es única.
        assert taker["status"] in ("FILLED", "CANCELLED"), taker

        # Entonces: q' por la fórmula directa de RN-5 (big integers)
        b_rem = 500_000_000
        max_lots = (b_rem * ETH) // (p2 * LOT_SIZE)
        q_prima = max_lots * LOT_SIZE
        assert quote_min(q_prima, p2) <= b_rem                       # entra en B_rem
        assert quote_min(q_prima + LOT_SIZE, p2) > b_rem             # el siguiente lot no

        fills = trades_propios(usuario, order_id=taker["orderId"])
        assert [(assert_monto(t["priceMin"]), assert_monto(t["quantityWei"])) for t in fills] == [
            (p1, ETH),
            (p2, q_prima),
        ], fills
        assert taker["filledWei"] == a_str(ETH + q_prima)

        # Y: se detuvo por presupuesto, no por libro (A2 conserva liquidez), y A2
        # permanece en su nivel con el remanente exacto (RN-9)
        estado_a2 = orden_actual(usuario_b, a2["orderId"])
        assert estado_a2["status"] == "PARTIALLY_FILLED"
        assert assert_monto(estado_a2["quantityWei"]) - assert_monto(estado_a2["filledWei"]) == ETH - q_prima
        assert nivel(libro(api), "asks", p2) == ETH - q_prima
        assert orden_actual(usuario_b, a1["orderId"])["status"] == "FILLED"

        # Y: el gasto respetó el techo y el resto quedó liberado (RN-10)
        gastado = quote_min(ETH, p1) + quote_min(q_prima, p2)
        assert gastado <= presupuesto
        balances = balances_por_activo(usuario)
        assert assert_monto(balances["USDC"]["locked"]) == 0
        assert assert_monto(balances["USDC"]["available"]) == fondeo - gastado
    finally:
        cancelar_abiertas(usuario, usuario_b)


@pytest.mark.at("AT-03-04-06")
def test_precio_en_market_rechazado_antes_del_motor(usuario):
    """HU-03-04 Escenario 6 (borde): precio enviado en MARKET es rechazado antes del motor.

    - Dado un cliente que envía MARKET BUY 1 ETH con un price presente
    - Cuando la épica 04 valida el payload
    - Entonces se rechaza con PRICE_NOT_ALLOWED (422) y la orden no llega al
      motor (RN-1): no hace falta libro ni fondos (precedencia §4 paso 3)
    """
    # Cuando
    cuerpo = cuerpo_market("BUY", q_wei=ETH)
    cuerpo["priceMin"] = "2000000000"
    resp = usuario.api.post("/orders", json=cuerpo)

    # Entonces
    assert_error(resp, "PRICE_NOT_ALLOWED")


@pytest.mark.at("AT-03-04-07")
def test_market_de_un_lot_exacto(api, usuario, usuario_b, rpc):
    """HU-03-04 Escenario 7 (borde): MARKET de 1 lot exacto contra liquidez suficiente.

    - Dado un libro con profundidad ≥ 1 lot en el best ask
    - Cuando ingresa MARKET BUY de exactamente 1 lot (10^14 wei) con presupuesto
      suficiente
    - Entonces ejecuta q_fill = 1 lot al precio del maker con
      quote_min = floor(10^14 × P / 10^18) y queda FILLED (RN-4)

    TODO-REVISAR: el Dado del AT (best_ask = 2000.00) hace que 1 lot valga
    0.2 USDC < mínimo notional, y la épica 04 rechazaría la MARKET con
    BELOW_MIN_NOTIONAL antes del motor (HU-04-02 RN-3). Para observar la regla
    del motor black-box se usa un precio que satisface el mínimo:
    P = 100000.00 USDC/ETH ⇒ 1 lot = 10 USDC exactos (≥ mínimo).
    """
    precio = 100_000_000_000  # 100000.00 USDC/ETH, múltiplo de tick
    requerir_libro_vacio(api)  # el best ask debe ser el del escenario
    fondear(usuario_b, rpc, eth_wei=ETH // 100)          # 0.01 ETH de profundidad
    costo_lot = quote_min(LOT_SIZE, precio)              # = 10 USDC exactos
    fondear(usuario, rpc, usdc_min=costo_lot)
    try:
        # Dado
        colocar_limit(usuario_b, "SELL", precio, ETH // 100, esperado="OPEN")

        # Cuando
        taker = colocar_market(usuario, "BUY", q_wei=LOT_SIZE, esperado="FILLED")

        # Entonces: 1 lot al precio del maker, quote por la fórmula floor (RN-4)
        assert taker["filledWei"] == a_str(LOT_SIZE)
        fills = trades_propios(usuario, order_id=taker["orderId"])
        assert len(fills) == 1
        assert assert_monto(fills[0]["quantityWei"]) == LOT_SIZE
        assert assert_monto(fills[0]["quoteAmountMin"]) == costo_lot
        balances = balances_por_activo(usuario)
        assert assert_monto(balances["USDC"]["total"]) == 0  # gastó exactamente el lot
        assert assert_monto(balances["ETH"]["available"]) == LOT_SIZE - fee_taker(LOT_SIZE)
    finally:
        cancelar_abiertas(usuario, usuario_b)


@pytest.mark.at("AT-03-04-08")
def test_auto_cruce_de_una_market(api, usuario, rpc):
    """HU-03-04 Escenario 8 (error): auto-cruce de una MARKET.

    - Dado que el único ask del libro pertenece a la misma cuenta que envía la
      MARKET BUY
    - Cuando el motor evalúa el cruce
    - Entonces aplica HU-03-06 y rechaza con SELF_TRADE_BLOCKED (422), sin fills
      (RN-12)
    """
    precio = 2_140_000_000
    requerir_lado_vacio(api, "asks")
    fondear(usuario, rpc, eth_wei=ETH, usdc_min=2_200_000_000)
    try:
        # Dado: la única liquidez opuesta es propia
        propia = colocar_limit(usuario, "SELL", precio, ETH, esperado="OPEN")
        trade_previo = ultimo_trade_id(api)
        antes = snapshot_balances(usuario)

        # Cuando
        resp = usuario.api.post("/orders", json=cuerpo_market("BUY", q_wei=ETH))

        # Entonces: STP, sin fills, orden propia y balances intactos (RN-12, INV-4)
        err = assert_error(resp, "SELF_TRADE_BLOCKED")
        assert err["details"]["restingOrderId"] == propia["orderId"]
        assert ultimo_trade_id(api) == trade_previo
        assert orden_actual(usuario, propia["orderId"])["status"] == "OPEN"
        assert snapshot_balances(usuario) == antes
    finally:
        cancelar_abiertas(usuario)


@pytest.mark.at("AT-03-04-09")
def test_market_buy_sin_presupuesto_para_un_lot(api, usuario, usuario_b, rpc):
    """HU-03-04 Escenario 9 (error): MARKET BUY sin presupuesto para ni 1 lot.

    - Dado un best ask cuyo costo de 1 lot excede el presupuesto B del taker
    - Cuando el motor evalúa la ejecución (max_lots = 0, RN-5)
    - Entonces no ejecuta nada y rechaza con MARKET_BUDGET_INSUFFICIENT (422),
      details = { budgetMin, requiredMin } (RN-9)
    - Y la reserva se libera íntegra; libro y balances idénticos (INV-2, INV-3)
    - Y NO se reporta MARKET_NO_LIQUIDITY (sí hay liquidez)

    Construcción black-box del caso defensivo: el presupuesto observable es un
    `quoteOrderQty` (HU-04-02 RN-5) que debe ser ≥ mínimo notional (10 USDC);
    con un best ask a 100001.00 USDC/ETH, 1 lot cuesta 10.0001 USDC > 10 USDC.
    """
    precio = 100_001_000_000  # 100001.00 USDC/ETH
    presupuesto = 10_000_000  # 10 USDC: mínimo notional exacto, no cubre 1 lot
    requerir_libro_vacio(api)  # el best ask debe ser el del escenario
    fondear(usuario_b, rpc, eth_wei=ETH // 100)
    fondear(usuario, rpc, usdc_min=presupuesto)
    try:
        # Dado
        ajena = colocar_limit(usuario_b, "SELL", precio, ETH // 100, esperado="OPEN")
        antes = snapshot_balances(usuario)
        trade_previo = ultimo_trade_id(api)

        # Cuando: max_lots = floor(B × 10^18 / (P × lot)) = 0 (RN-5)
        assert (presupuesto * ETH) // (precio * LOT_SIZE) == 0
        cid = "ep03-mkt-budget"
        resp = usuario.api.post(
            "/orders",
            json={**cuerpo_market("BUY", quote_order_qty=presupuesto), "clientOrderId": cid},
        )

        # Entonces: MARKET_BUDGET_INSUFFICIENT con los montos del caso (RN-9)
        err = assert_error(resp, "MARKET_BUDGET_INSUFFICIENT")
        assert err["details"]["budgetMin"] == a_str(presupuesto)
        assert err["details"]["requiredMin"] == a_str(quote_min(LOT_SIZE, precio))

        # Y: cero fills, reserva liberada íntegra, libro intacto (INV-2, INV-3, INV-4)
        assert ultimo_trade_id(api) == trade_previo
        assert snapshot_balances(usuario) == antes
        assert orden_actual(usuario_b, ajena["orderId"])["status"] == "OPEN"
        assert nivel(libro(api), "asks", precio) == ETH // 100
        registrada = orden_por_client_id(usuario, cid)
        if registrada is not None:  # terminal REJECTED (HU-04-02 RN-7)
            assert registrada["status"] == "REJECTED"
            assert registrada["filledWei"] == "0"
    finally:
        cancelar_abiertas(usuario, usuario_b)


@pytest.mark.at("AT-03-04-10")
def test_market_con_mezcla_de_liquidez_propia_y_de_terceros(api, usuario, usuario_b, rpc):
    """HU-03-04 Escenario 10 (error): MARKET con mezcla de liquidez propia y de terceros.

    - Dado asks al mismo nivel: A1 de U2 (1º) y A2 de U1 (2º)
    - Cuando U1 envía MARKET BUY 1 ETH (rango consumible = {A1, A2})
    - Entonces se rechaza TODA la entrante con SELF_TRADE_BLOCKED (422) y
      details.restingOrderId = A2 (RN-12, HU-03-06 RN-7)
    - Y A1 (de tercero) tampoco se ejecuta; el libro queda idéntico (INV-4)
    """
    precio = 2_145_000_000
    requerir_lado_vacio(api, "asks")
    fondear(usuario_b, rpc, eth_wei=ETH)                      # U2: A1
    fondear(usuario, rpc, eth_wei=ETH, usdc_min=2_200_000_000)  # U1: A2 + fondos del BUY
    try:
        # Dado: A1 ajena primero, A2 propia después, mismo nivel
        a1 = colocar_limit(usuario_b, "SELL", precio, ETH // 2, esperado="OPEN")
        a2 = colocar_limit(usuario, "SELL", precio, ETH // 2, esperado="OPEN")
        libro_previo = libro(api)
        trade_previo = ultimo_trade_id(api)

        # Cuando
        resp = usuario.api.post("/orders", json=cuerpo_market("BUY", q_wei=ETH))

        # Entonces: rechazo íntegro, señalando la orden propia del rango (RN-12)
        err = assert_error(resp, "SELF_TRADE_BLOCKED")
        assert err["details"]["restingOrderId"] == a2["orderId"]

        # Y: A1 tampoco se ejecutó; libro idéntico, sin trades (INV-4, HU-03-06 RN-7)
        assert ultimo_trade_id(api) == trade_previo
        assert orden_actual(usuario_b, a1["orderId"])["status"] == "OPEN"
        assert orden_actual(usuario, a2["orderId"])["status"] == "OPEN"
        despues = libro(api)
        assert despues["bids"] == libro_previo["bids"]
        assert despues["asks"] == libro_previo["asks"]
    finally:
        cancelar_abiertas(usuario, usuario_b)
