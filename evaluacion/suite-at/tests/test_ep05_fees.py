"""Épica 05 — HU-05-02 (cálculo de fees maker/taker): tests de aceptación black-box.

Las fees no tienen endpoint propio: se observan en (a) los balances finales de
ambas patas (el neto acreditado = monto recibido - fee), (b) la proyección del
trade en GET /trades (`feeAsset`/`feeAmount`/`netReceived`, HU-05-04 RN-3) y
(c) los campos `feeWei`/`feeUsdcMin` de la orden (HU-09-01 RN-2/RN-5).

Los valores esperados se computan con las fórmulas de referencia de la spec
(helpers/montos.py: `quote_min` con floor, `fee` con ceil, maker 10 bps / taker
20 bps, denominador 10000) y se comparan con igualdad exacta (RN-10, sin epsilon).
"""

import pytest

from comunes_ep05 import (
    PRECIO_2000,
    UN_ETH_WEI,
    UN_LOT_WEI,
    assert_balance,
    assert_pata_propia,
    construir_fill_de_un_lot,
    crear_limit,
    crear_maker,
    entrada_unica,
    esperar_trades,
    fondear_eth,
    fondear_usdc,
    limpiar_ordenes_residuales,  # noqa: F401  (fixture autouse: limpieza del libro)
    orden_de,
)
from helpers.montos import (
    FEE_BPS_MAKER,
    FEE_BPS_TAKER,
    FEE_DENOMINADOR,
    a_int,
    es_monto_valido,
    fee_maker,
    fee_taker,
    quote_min,
)


@pytest.mark.at("AT-05-02-01")
def test_fees_taker_compra_maker_vende_20_10(usuario, usuario_b, rpc):
    """HU-05-02 Escenario 1: Taker compra contra maker vende — fees 20/10.

    - Dado un fill con takerSide = BUY, 1 ETH @ 2000.00, quote_min = 2000000000
    - Cuando se calculan las fees
    - Entonces fee_base = ceil(1e18 × 20 / 10000) = 2000000000000000 wei (taker)
    - Y fee_quote = ceil(2000000000 × 10 / 10000) = 2000000 USDC-min (maker)
    - Y el comprador recibe 998000000000000000 wei y el vendedor 1998000000 USDC-min
    - Y disponible(EX, ETH) += fee_base y disponible(EX, USDC) += fee_quote
    - Y se conserva por activo (INV-1)
    """
    q_wei = UN_ETH_WEI
    quote = quote_min(q_wei, PRECIO_2000)
    fee_base = fee_taker(q_wei)                    # comprador taker: 20 bps (RN-3/RN-4)
    fee_quote = fee_maker(quote)                   # vendedor maker: 10 bps
    assert fee_base == 2_000_000_000_000_000 and fee_quote == 2_000_000  # literales del AT

    # Dado: maker SELL resting de usuario_b; el taker BUY de usuario cruza
    fondear_eth(usuario_b, rpc, q_wei)
    fondear_usdc(usuario, rpc, quote)
    crear_maker(usuario_b, "SELL", PRECIO_2000, q_wei)

    # Cuando
    orden_taker = crear_limit(usuario, "BUY", PRECIO_2000, q_wei)
    items_comprador = esperar_trades(usuario, 1)
    items_vendedor = esperar_trades(usuario_b, 1)

    # Entonces: la fee de cada parte, en el activo que recibe, con su bps de rol
    assert_pata_propia(
        items_comprador[0],
        side="BUY", role="TAKER", price_min=PRECIO_2000, q_wei=q_wei, quote=quote,
        fee_asset="ETH", fee=fee_base, neto=q_wei - fee_base, pagado=quote,
        order_id=orden_taker["orderId"],
    )
    assert_pata_propia(
        items_vendedor[0],
        side="SELL", role="MAKER", price_min=PRECIO_2000, q_wei=q_wei, quote=quote,
        fee_asset="USDC", fee=fee_quote, neto=quote - fee_quote, pagado=q_wei,
    )

    # Y: los netos acreditados a los balances son exactamente monto - fee
    assert_balance(usuario, "ETH", available=q_wei - fee_base, locked=0)
    assert_balance(usuario_b, "USDC", available=quote - fee_quote, locked=0)
    assert q_wei - fee_base == 998_000_000_000_000_000
    assert quote - fee_quote == 1_998_000_000

    # Y: conservación por activo con EX incluida (RN-8): lo no acreditado a los
    # usuarios es exactamente la fee (acreditada a EX, sin superficie REST propia)
    assert (q_wei - fee_base) + fee_base == q_wei
    assert (quote - fee_quote) + fee_quote == quote


@pytest.mark.at("AT-05-02-02")
def test_fees_taker_vende_maker_compra_invertidas(usuario, usuario_b, rpc):
    """HU-05-02 Escenario 2: Taker vende contra maker compra — fees 20/10 invertidas.

    - Dado un fill con takerSide = SELL, 1 ETH @ 2000.00, quote_min = 2000000000
    - Cuando se calculan las fees
    - Entonces fee_quote = ceil(2000000000 × 20 / 10000) = 4000000 (taker = vendedor)
    - Y fee_base = ceil(1e18 × 10 / 10000) = 1000000000000000 wei (maker = comprador)
    - Y el vendedor recibe 1996000000 USDC-min y el comprador 999000000000000000 wei
    - Y se conserva por activo (INV-1)
    """
    q_wei = UN_ETH_WEI
    quote = quote_min(q_wei, PRECIO_2000)
    fee_quote = fee_taker(quote)                   # vendedor taker: 20 bps (RN-4)
    fee_base = fee_maker(q_wei)                    # comprador maker: 10 bps
    assert fee_quote == 4_000_000 and fee_base == 1_000_000_000_000_000  # literales del AT

    # Dado: maker BUY resting de usuario; el taker SELL de usuario_b cruza
    fondear_usdc(usuario, rpc, quote)
    fondear_eth(usuario_b, rpc, q_wei)
    orden_maker = crear_maker(usuario, "BUY", PRECIO_2000, q_wei)

    # Cuando
    orden_taker = crear_limit(usuario_b, "SELL", PRECIO_2000, q_wei)
    items_vendedor = esperar_trades(usuario_b, 1)
    items_comprador = esperar_trades(usuario, 1)

    # Entonces: roles y bps invertidos respecto del escenario 1
    assert_pata_propia(
        items_vendedor[0],
        side="SELL", role="TAKER", price_min=PRECIO_2000, q_wei=q_wei, quote=quote,
        fee_asset="USDC", fee=fee_quote, neto=quote - fee_quote, pagado=q_wei,
        order_id=orden_taker["orderId"],
    )
    assert_pata_propia(
        items_comprador[0],
        side="BUY", role="MAKER", price_min=PRECIO_2000, q_wei=q_wei, quote=quote,
        fee_asset="ETH", fee=fee_base, neto=q_wei - fee_base, pagado=quote,
        order_id=orden_maker["orderId"],
    )

    # Y: netos exactos en balances
    assert_balance(usuario_b, "USDC", available=quote - fee_quote, locked=0)
    assert_balance(usuario, "ETH", available=q_wei - fee_base, locked=0)
    assert quote - fee_quote == 1_996_000_000
    assert q_wei - fee_base == 999_000_000_000_000_000


@pytest.mark.at("AT-05-02-03")
def test_ceil_efectivo_en_fee_quote_residuo_a_favor_del_exchange(usuario, usuario_b, rpc):
    """HU-05-02 Escenario 3 (borde): `ceil` efectivo en fee_quote — residuo a EX.

    - Dado un fill takerSide = BUY de 1 lot (0.0001 ETH) @ 2000.01
    - Cuando se calcula el notional
    - Entonces quote_min = floor(100000000000000 × 2000010000 / 10^18) = 200001
    - Y fee_quote = ceil(200001 × 10 / 10000) = ceil(200.001) = 201 (maker; la fee
      nominal 200.001 se redondea hacia arriba, el residuo 0.999 queda para EX)
    - Y el vendedor recibe 200001 - 201 = 199800 USDC-min
    - Y fee_base = ceil(100000000000000 × 20 / 10000) = 200000000000 wei (exacto, RN-9)
    - Y el neto del vendedor es >= 0 y la conservación se mantiene (INV-1/INV-2)

    El fill de 1 lot se construye como remanente (una orden de 1 lot solo no pasa
    el mínimo notional al alta): ver comunes_ep05.construir_fill_de_un_lot.
    """
    precio = 2_000_010_000                         # 2000.01, múltiplo de tick
    q_lot = UN_LOT_WEI
    quote_lot = quote_min(q_lot, precio)
    fee_quote_lot = fee_maker(quote_lot)           # vendedor maker en el fill de 1 lot
    fee_base_lot = fee_taker(q_lot)                # comprador taker
    # Literales del AT: ceil efectivo en fee_quote, fee_base exacta
    assert quote_lot == 200_001
    assert fee_quote_lot == 201
    assert fee_base_lot == 200_000_000_000
    assert (q_lot * FEE_BPS_TAKER) % FEE_DENOMINADOR == 0     # el ceil no agrega nada (RN-9)
    assert (quote_lot * FEE_BPS_MAKER) % FEE_DENOMINADOR != 0  # acá el ceil sí es efectivo

    # Dado / Cuando: S1 SELL 51 lots; B1 BUY 50 lots; B2 BUY 50 lots → fill de 1 lot
    s1, b1, b2 = construir_fill_de_un_lot(usuario, usuario_b, rpc, precio)

    # Entonces: la pata del vendedor en el fill de 1 lot registra la fee con ceil
    items_vendedor = esperar_trades(usuario_b, 2)
    fill_lot_vendedor = entrada_unica(items_vendedor, quantityWei=str(q_lot))
    assert_pata_propia(
        fill_lot_vendedor,
        side="SELL", role="MAKER", price_min=precio, q_wei=q_lot, quote=quote_lot,
        fee_asset="USDC", fee=fee_quote_lot, neto=quote_lot - fee_quote_lot, pagado=q_lot,
        order_id=s1["orderId"],
    )
    assert quote_lot - fee_quote_lot == 199_800
    # Y: la pata del comprador (taker) con fee_base exacta en wei
    items_comprador = esperar_trades(usuario, 2)
    fill_lot_comprador = entrada_unica(items_comprador, quantityWei=str(q_lot))
    assert_pata_propia(
        fill_lot_comprador,
        side="BUY", role="TAKER", price_min=precio, q_wei=q_lot, quote=quote_lot,
        fee_asset="ETH", fee=fee_base_lot, neto=q_lot - fee_base_lot, pagado=quote_lot,
        order_id=b2["orderId"],
    )

    # Y: neto >= 0 y conservación exacta también en el fill previo de 50 lots
    # (fee del maker sobre 10000050 también fuerza ceil: 10000.05 → 10001)
    q_50 = 50 * UN_LOT_WEI
    quote_50 = quote_min(q_50, precio)
    assert fee_maker(quote_50) == 10_001
    neto_vendedor_total = (quote_50 - fee_maker(quote_50)) + (quote_lot - fee_quote_lot)
    assert_balance(usuario_b, "USDC", available=neto_vendedor_total, locked=0)
    neto_comprador_eth = (q_50 - fee_taker(q_50)) + (q_lot - fee_base_lot)
    assert_balance(usuario, "ETH", available=neto_comprador_eth, locked=0)
    assert b1["orderId"] != b2["orderId"]


@pytest.mark.at("AT-05-02-04")
def test_fee_base_exacta_bajo_lot_maker_y_taker(usuario, usuario_b, rpc):
    """HU-05-02 Escenario 4 (borde): fee_base siempre exacta bajo lot.

    - Dado fills con q_wei = 300000000000000 (0.0003 ETH, múltiplo de 10^14)
    - Cuando se calcula fee_base con bps maker (10) o taker (20)
    - Entonces fee_base = q_wei/1000 (maker) = 300000000000 wei, o q_wei/500 (taker)
      = 600000000000 wei, enteros exactos
    - Y el ceil no produce incremento respecto de la división exacta (RN-9)

    Se usa precio 33334.00 para que 3 lots superen el mínimo notional al alta
    (0.0003 ETH × 33334.00 = 10.0002 USDC >= 10 USDC).
    """
    q_wei = 3 * UN_LOT_WEI                          # 0.0003 ETH
    precio = 33_334_000_000                         # 33334.00, múltiplo de tick
    quote = quote_min(q_wei, precio)
    assert quote == 10_000_200                      # >= mínimo notional (10 USDC)

    # fee_base exacta: q_wei múltiplo de 10^14 ⇒ q×10/10000 y q×20/10000 sin residuo
    assert (q_wei * FEE_BPS_MAKER) % FEE_DENOMINADOR == 0
    assert (q_wei * FEE_BPS_TAKER) % FEE_DENOMINADOR == 0
    assert fee_maker(q_wei) == q_wei // 1000 == 300_000_000_000     # literal del AT
    assert fee_taker(q_wei) == q_wei // 500 == 600_000_000_000      # literal del AT

    # Dado: fondos para dos fills de 3 lots (uno con comprador taker, otro maker)
    fondear_eth(usuario_b, rpc, 2 * q_wei)
    fondear_usdc(usuario, rpc, 2 * quote)

    # Cuando: fill A — comprador taker (SELL resting de usuario_b, BUY cruza)
    crear_maker(usuario_b, "SELL", precio, q_wei)
    orden_buy_taker = crear_limit(usuario, "BUY", precio, q_wei)
    esperar_trades(usuario, 1)
    # Cuando: fill B — comprador maker (BUY resting de usuario, SELL cruza)
    orden_buy_maker = crear_maker(usuario, "BUY", precio, q_wei)
    crear_limit(usuario_b, "SELL", precio, q_wei)
    items = esperar_trades(usuario, 2)

    # Entonces: fee_base del comprador exacta según rol, sin incremento por ceil
    pata_taker = entrada_unica(items, orderId=orden_buy_taker["orderId"])
    assert_pata_propia(
        pata_taker,
        side="BUY", role="TAKER", price_min=precio, q_wei=q_wei, quote=quote,
        fee_asset="ETH", fee=q_wei // 500, neto=q_wei - q_wei // 500, pagado=quote,
    )
    pata_maker = entrada_unica(items, orderId=orden_buy_maker["orderId"])
    assert_pata_propia(
        pata_maker,
        side="BUY", role="MAKER", price_min=precio, q_wei=q_wei, quote=quote,
        fee_asset="ETH", fee=q_wei // 1000, neto=q_wei - q_wei // 1000, pagado=quote,
    )

    # Y: el ETH acreditado al comprador refleja exactamente ambas fees exactas
    assert_balance(
        usuario, "ETH",
        available=2 * q_wei - q_wei // 500 - q_wei // 1000, locked=0,
    )


@pytest.mark.at("AT-05-02-05")
def test_fill_minimo_fees_positivas_y_neto_no_negativo(usuario, usuario_b, rpc):
    """HU-05-02 Escenario 5 (borde): fill mínimo — fees positivas y neto no negativo.

    - Dado un fill de 1 lot (100000000000000 wei) @ 2000.00, quote_min = 200000,
      takerSide = BUY
    - Cuando se calculan las fees
    - Entonces fee_base = ceil(100000000000000 × 20 / 10000) = 200000000000 wei (taker)
    - Y fee_quote = ceil(200000 × 10 / 10000) = 200 USDC-min (maker, exacto)
    - Y comprador neto = 99800000000000 wei >= 0; vendedor neto = 199800 >= 0 (INV-2)

    El fill de 1 lot se construye como remanente (ver construir_fill_de_un_lot).
    """
    q_lot = UN_LOT_WEI
    quote_lot = quote_min(q_lot, PRECIO_2000)
    assert quote_lot == 200_000                     # 0.20 USDC, literal del AT
    fee_base = fee_taker(q_lot)
    fee_quote = fee_maker(quote_lot)
    assert fee_base == 200_000_000_000 and fee_quote == 200  # literales del AT
    assert fee_base > 0 and fee_quote > 0

    # Dado / Cuando
    s1, _b1, b2 = construir_fill_de_un_lot(usuario, usuario_b, rpc, PRECIO_2000)

    # Entonces: netos >= 0 y exactos en la proyección del trade de cada pata
    items_comprador = esperar_trades(usuario, 2)
    pata_comprador = entrada_unica(items_comprador, quantityWei=str(q_lot))
    assert_pata_propia(
        pata_comprador,
        side="BUY", role="TAKER", price_min=PRECIO_2000, q_wei=q_lot, quote=quote_lot,
        fee_asset="ETH", fee=fee_base, neto=q_lot - fee_base, pagado=quote_lot,
        order_id=b2["orderId"],
    )
    assert q_lot - fee_base == 99_800_000_000_000 and q_lot - fee_base >= 0

    items_vendedor = esperar_trades(usuario_b, 2)
    pata_vendedor = entrada_unica(items_vendedor, quantityWei=str(q_lot))
    assert_pata_propia(
        pata_vendedor,
        side="SELL", role="MAKER", price_min=PRECIO_2000, q_wei=q_lot, quote=quote_lot,
        fee_asset="USDC", fee=fee_quote, neto=quote_lot - fee_quote, pagado=q_lot,
        order_id=s1["orderId"],
    )
    assert quote_lot - fee_quote == 199_800 and quote_lot - fee_quote >= 0


@pytest.mark.at("AT-05-02-06")
def test_determinismo_mismas_entradas_mismos_enteros(usuario, usuario_b, rpc):
    """HU-05-02 Escenario 6 (determinismo): mismas entradas, mismos enteros.

    - Dado el mismo fill (q_wei, price_min, takerSide) calculado dos veces
    - Cuando se computan fee_base y fee_quote
    - Entonces ambos resultados son idénticos al entero, sin tolerancia ni epsilon
    - Y ningún valor cruza la API como float (RN-11; black-box: serialización string)

    Black-box: se ejecutan dos fills idénticos (0.005 ETH @ 2000.00, takerSide BUY)
    y se exige que las fees registradas sean el mismo entero entre sí y el mismo
    entero que las fórmulas de referencia de la spec.
    """
    q_wei = 5_000_000_000_000_000                   # 0.005 ETH (notional = mínimo exacto)
    quote = quote_min(q_wei, PRECIO_2000)
    assert quote == 10_000_000

    # Dado: fondos para dos fills idénticos
    fondear_eth(usuario_b, rpc, 2 * q_wei)
    fondear_usdc(usuario, rpc, 2 * quote)

    # Cuando: dos fills con exactamente las mismas entradas (q, precio, roles)
    for _ in range(2):
        crear_maker(usuario_b, "SELL", PRECIO_2000, q_wei)
        crear_limit(usuario, "BUY", PRECIO_2000, q_wei)
    items_comprador = esperar_trades(usuario, 2)
    items_vendedor = esperar_trades(usuario_b, 2)

    # Entonces: los dos trades registran exactamente los mismos enteros de fee/neto
    fees_comprador = {(it["feeAsset"], it["feeAmount"], it["netReceived"]) for it in items_comprador}
    fees_vendedor = {(it["feeAsset"], it["feeAmount"], it["netReceived"]) for it in items_vendedor}
    assert len(fees_comprador) == 1, items_comprador   # idénticos entre sí (al string)
    assert len(fees_vendedor) == 1, items_vendedor

    # Y: idénticos a las fórmulas de referencia (comparación exacta, sin epsilon)
    assert fees_comprador == {("ETH", str(fee_taker(q_wei)), str(q_wei - fee_taker(q_wei)))}
    assert fees_vendedor == {("USDC", str(fee_maker(quote)), str(quote - fee_maker(quote)))}
    # Y: serialización string (proxy black-box de la prohibición de floats, RN-11)
    for it in items_comprador + items_vendedor:
        assert es_monto_valido(it["feeAmount"]), it
        assert es_monto_valido(it["netReceived"]), it


@pytest.mark.at("AT-05-02-07")
def test_fees_serializadas_como_string_entero(usuario, usuario_b, rpc):
    """HU-05-02 Escenario 7 (serialización/error): fee como string entero.

    - Dado un fill liquidado con fee_base = 2000000000000000 y fee_quote = 2000000
    - Cuando estos valores cruzan la API (historial de trades y objeto orden)
    - Entonces se serializan como "2000000000000000" y "2000000" (string que
      matchea ^(0|[1-9][0-9]*)$), nunca como número JSON, decimal ni científica
    - Y una representación inválida (número JSON, "2e6", "0.002", "-1") sería
      incumplimiento de convenciones-monetarias §5 (es_monto_valido la rechaza)
    """
    q_wei = UN_ETH_WEI
    quote = quote_min(q_wei, PRECIO_2000)

    # Dado: el fill canónico 1 ETH @ 2000.00 (taker BUY)
    fondear_eth(usuario_b, rpc, q_wei)
    fondear_usdc(usuario, rpc, quote)
    orden_maker = crear_maker(usuario_b, "SELL", PRECIO_2000, q_wei)
    orden_taker = crear_limit(usuario, "BUY", PRECIO_2000, q_wei)
    items_comprador = esperar_trades(usuario, 1)
    items_vendedor = esperar_trades(usuario_b, 1)

    # Entonces: en el historial, la fee de cada pata es exactamente el string canónico
    assert items_comprador[0]["feeAmount"] == "2000000000000000", items_comprador[0]
    assert items_vendedor[0]["feeAmount"] == "2000000", items_vendedor[0]
    for it in (items_comprador[0], items_vendedor[0]):
        assert es_monto_valido(it["feeAmount"]), it
        assert es_monto_valido(it["netReceived"]), it

    # Y: en el objeto orden, la fee acumulada va en el activo recibido y como string
    # (HU-09-01 RN-2: BUY acumula feeWei y deja feeUsdcMin = "0"; SELL al revés)
    taker_final = orden_de(usuario, orden_taker["orderId"])
    assert taker_final["feeWei"] == "2000000000000000", taker_final
    assert taker_final["feeUsdcMin"] == "0", taker_final
    maker_final = orden_de(usuario_b, orden_maker["orderId"])
    assert maker_final["feeUsdcMin"] == "2000000", maker_final
    assert maker_final["feeWei"] == "0", maker_final
    for campo in ("feeWei", "feeUsdcMin"):
        assert es_monto_valido(taker_final[campo]) and es_monto_valido(maker_final[campo])

    # Y: es_monto_valido rechaza las representaciones inválidas del AT (autochequeo
    # de la vara con la que se midió lo anterior)
    assert not es_monto_valido(2_000_000)     # número JSON
    assert not es_monto_valido("2e6")         # notación científica
    assert not es_monto_valido("0.002")       # decimal
    assert not es_monto_valido("-1")          # negativo
    assert a_int(taker_final["feeWei"]) == fee_taker(q_wei)
