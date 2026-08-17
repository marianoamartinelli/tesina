"""Épica 05 — HU-05-03 (registro de trades): tests de aceptación black-box.

El registro de trades es interno; su superficie observable es la **proyección por
pata** de GET /trades (HU-09-01 RN-20: tradeId, sequence, timestamp, symbol,
priceMin, quantityWei, quoteAmountMin, side, role, feeAsset, feeAmount,
netReceived, paid, orderId) más el feed público GET /market/trades (tradeId,
priceMin, quantityWei, takerSide, timestamp; HU-09-01 RN-13). Los campos del
registro que el contrato no proyecta directamente (buyerFeeBps, feeBaseWei, ...)
se verifican por su valor inducido: feeAmount de la pata compradora == feeBaseWei,
feeAmount de la vendedora == feeQuoteMin, y los bps por la igualdad exacta con
las fórmulas ceil de referencia (HU-05-03 RN-6).

No automatizables black-box (ver no-automatizables.yaml): AT-05-03-05
(redelivery interno), AT-05-03-06 (falla inyectada) y AT-05-03-07 — este último
porque su "Entonces" exige reconciliar Σ fees contra lo acreditado a la cuenta
EX, que no tiene endpoint en la épica 09 (ADR-011); la mitad automatizable del
escenario (los trades sobreviven al reinicio) no se separa: el AT se reporta
entero.
"""

import pytest

from comunes_ep05 import (
    PRECIO_2000,
    PRECIO_2001,
    UN_ETH_WEI,
    UN_LOT_WEI,
    assert_pata_propia,
    construir_fill_de_un_lot,
    crear_limit,
    crear_maker,
    entrada_unica,
    esperar_trades,
    fondear_eth,
    fondear_usdc,
    limpiar_ordenes_residuales,  # noqa: F401  (fixture autouse: limpieza del libro)
)
from helpers.montos import a_int, es_monto_valido, fee_maker, fee_taker, quote_min


def item_de_market_trades(api, trade_id: str) -> dict:
    """El item de GET /market/trades con ese tradeId (debe existir; RN-13)."""
    resp = api.get("/market/trades", params={"limit": 200})
    assert resp.status_code == 200, resp.text
    cuerpo = resp.json()
    coincidentes = [it for it in cuerpo["items"] if it.get("tradeId") == trade_id]
    assert len(coincidentes) == 1, (
        f"esperaba exactamente 1 trade público con tradeId {trade_id}: {coincidentes!r}"
    )
    return coincidentes[0]


@pytest.mark.at("AT-05-03-01")
def test_trade_registrado_fill_total_taker_buy(usuario, usuario_b, rpc):
    """HU-05-03 Escenario 1: Trade registrado en un fill total (taker BUY).

    - Dado un fill con takerSide = BUY, 1 ETH @ 2000.00, comprador taker y
      vendedor maker
    - Cuando se completa el settlement atómicamente
    - Entonces se crea UN registro de trade con quantityWei = "1000000000000000000",
      priceMin = "2000000000", quoteAmountMin = "2000000000"
    - Y buyerRole = TAKER, buyerFeeBps = 20, feeBaseWei = "2000000000000000"
    - Y sellerRole = MAKER, sellerFeeBps = 10, feeQuoteMin = "2000000"
    - Y buyerNetBaseWei = "998000000000000000", sellerNetQuoteMin = "1998000000"
    - Y el registro referencia las órdenes y cuentas involucradas (cada pata ve
      la suya: orderId propio; el feed público confirma takerSide)
    """
    q_wei = UN_ETH_WEI
    quote = quote_min(q_wei, PRECIO_2000)
    fee_base = fee_taker(q_wei)                    # buyerFeeBps = 20 (comprador taker)
    fee_quote = fee_maker(quote)                   # sellerFeeBps = 10 (vendedor maker)

    # Dado / Cuando
    fondear_eth(usuario_b, rpc, q_wei)
    fondear_usdc(usuario, rpc, quote)
    orden_maker = crear_maker(usuario_b, "SELL", PRECIO_2000, q_wei)
    orden_taker = crear_limit(usuario, "BUY", PRECIO_2000, q_wei)
    items_comprador = esperar_trades(usuario, 1)
    items_vendedor = esperar_trades(usuario_b, 1)

    # Entonces: exactamente un trade por fill (RN-1), visto desde ambas patas
    assert len(items_comprador) == 1 and len(items_vendedor) == 1
    pata_compradora, pata_vendedora = items_comprador[0], items_vendedor[0]
    assert pata_compradora["tradeId"] == pata_vendedora["tradeId"]

    # Y: la pata compradora proyecta buyerRole/feeBaseWei/buyerNetBaseWei (RN-4)
    assert_pata_propia(
        pata_compradora,
        side="BUY", role="TAKER", price_min=PRECIO_2000, q_wei=q_wei, quote=quote,
        fee_asset="ETH", fee=fee_base, neto=q_wei - fee_base, pagado=quote,
        order_id=orden_taker["orderId"],
    )
    assert pata_compradora["quantityWei"] == "1000000000000000000"
    assert pata_compradora["priceMin"] == "2000000000"
    assert pata_compradora["quoteAmountMin"] == "2000000000"
    assert pata_compradora["feeAmount"] == "2000000000000000"       # feeBaseWei
    assert pata_compradora["netReceived"] == "998000000000000000"   # buyerNetBaseWei
    # buyerFeeBps = 20 inducido: feeBaseWei == ceil(quantityWei × 20 / 10000) y ≠ 10 bps
    assert a_int(pata_compradora["feeAmount"]) == fee_taker(q_wei) != fee_maker(q_wei)

    # Y: la pata vendedora proyecta sellerRole/feeQuoteMin/sellerNetQuoteMin
    assert_pata_propia(
        pata_vendedora,
        side="SELL", role="MAKER", price_min=PRECIO_2000, q_wei=q_wei, quote=quote,
        fee_asset="USDC", fee=fee_quote, neto=quote - fee_quote, pagado=q_wei,
        order_id=orden_maker["orderId"],
    )
    assert pata_vendedora["feeAmount"] == "2000000"                 # feeQuoteMin
    assert pata_vendedora["netReceived"] == "1998000000"            # sellerNetQuoteMin
    assert a_int(pata_vendedora["feeAmount"]) == fee_maker(quote) != fee_taker(quote)

    # Y: el feed público confirma takerSide = BUY para ese tradeId (RN-4)
    publico = item_de_market_trades(usuario.api, pata_compradora["tradeId"])
    assert publico["takerSide"] == "BUY", publico
    assert a_int(publico["priceMin"]) == PRECIO_2000
    assert a_int(publico["quantityWei"]) == q_wei


@pytest.mark.at("AT-05-03-02")
def test_trade_registrado_fill_total_taker_sell(usuario, usuario_b, rpc):
    """HU-05-03 Escenario 2: Trade registrado en un fill total (taker SELL).

    - Dado un fill con takerSide = SELL, 1 ETH @ 2000.00, vendedor taker y
      comprador maker
    - Cuando se completa el settlement
    - Entonces el trade tiene sellerRole = TAKER, sellerFeeBps = 20,
      feeQuoteMin = "4000000"
    - Y buyerRole = MAKER, buyerFeeBps = 10, feeBaseWei = "1000000000000000"
    - Y buyerNetBaseWei = "999000000000000000", sellerNetQuoteMin = "1996000000"
    - Y makerSide = BUY, coherente con takerSide = SELL (la pata maker es la
      compradora; el feed público reporta takerSide = SELL)
    """
    q_wei = UN_ETH_WEI
    quote = quote_min(q_wei, PRECIO_2000)

    # Dado / Cuando: maker BUY resting de usuario; taker SELL de usuario_b
    fondear_usdc(usuario, rpc, quote)
    fondear_eth(usuario_b, rpc, q_wei)
    orden_maker = crear_maker(usuario, "BUY", PRECIO_2000, q_wei)
    orden_taker = crear_limit(usuario_b, "SELL", PRECIO_2000, q_wei)
    items_vendedor = esperar_trades(usuario_b, 1)
    items_comprador = esperar_trades(usuario, 1)

    pata_vendedora, pata_compradora = items_vendedor[0], items_comprador[0]
    assert pata_vendedora["tradeId"] == pata_compradora["tradeId"]

    # Entonces: vendedor taker con 20 bps sobre la quote
    assert_pata_propia(
        pata_vendedora,
        side="SELL", role="TAKER", price_min=PRECIO_2000, q_wei=q_wei, quote=quote,
        fee_asset="USDC", fee=fee_taker(quote), neto=quote - fee_taker(quote), pagado=q_wei,
        order_id=orden_taker["orderId"],
    )
    assert pata_vendedora["feeAmount"] == "4000000"                 # feeQuoteMin
    assert pata_vendedora["netReceived"] == "1996000000"            # sellerNetQuoteMin

    # Y: comprador maker con 10 bps sobre la base
    assert_pata_propia(
        pata_compradora,
        side="BUY", role="MAKER", price_min=PRECIO_2000, q_wei=q_wei, quote=quote,
        fee_asset="ETH", fee=fee_maker(q_wei), neto=q_wei - fee_maker(q_wei), pagado=quote,
        order_id=orden_maker["orderId"],
    )
    assert pata_compradora["feeAmount"] == "1000000000000000"       # feeBaseWei
    assert pata_compradora["netReceived"] == "999000000000000000"   # buyerNetBaseWei

    # Y: makerSide = BUY coherente con takerSide = SELL (RN-4/RN-6): la pata con
    # role MAKER es la de side BUY, y el feed público reporta takerSide = SELL.
    assert pata_compradora["role"] == "MAKER" and pata_compradora["side"] == "BUY"
    publico = item_de_market_trades(usuario.api, pata_vendedora["tradeId"])
    assert publico["takerSide"] == "SELL", publico


@pytest.mark.at("AT-05-03-03")
def test_sweep_registra_un_trade_por_fill(usuario, usuario_b, rpc):
    """HU-05-03 Escenario 3 (borde): Un fill por cada porción de un sweep.

    - Dado un taker BUY que barre dos makers SELL (M1 @ 2000.00 por 0.3 ETH,
      M2 @ 2001.00 por 0.3 ETH)
    - Cuando se ejecutan los dos fills
    - Entonces se registran DOS trades con tradeId y sequence distintos;
      sequence(trade2) > sequence(trade1), ambos positivos, y
      tradeId = "T-" + sequence en cada uno (RN-2/RN-3)
    - Y el primero tiene priceMin "2000000000", quantityWei "300000000000000000",
      quoteAmountMin "600000000"; el segundo priceMin "2001000000",
      quoteAmountMin "600300000"
    - Y ambos referencian el mismo takerOrderId y distinto makerOrderId
    """
    q_m = 300_000_000_000_000_000                   # 0.3 ETH por maker

    # Dado
    fondear_eth(usuario_b, rpc, 2 * q_m)
    fondear_usdc(usuario, rpc, quote_min(2 * q_m, PRECIO_2001))
    m1 = crear_maker(usuario_b, "SELL", PRECIO_2000, q_m)
    m2 = crear_maker(usuario_b, "SELL", PRECIO_2001, q_m)

    # Cuando: el taker barre M1 y luego M2 (prioridad precio-tiempo)
    orden_taker = crear_limit(usuario, "BUY", PRECIO_2001, 2 * q_m)
    items_comprador = esperar_trades(usuario, 2)
    items_vendedor = esperar_trades(usuario_b, 2)

    # Entonces: dos trades distintos, ordenados por sequence (historial descendente)
    assert len(items_comprador) == 2
    fill_1 = entrada_unica(items_comprador, priceMin=str(PRECIO_2000))   # vs M1, primero
    fill_2 = entrada_unica(items_comprador, priceMin=str(PRECIO_2001))   # vs M2, segundo
    assert fill_1["tradeId"] != fill_2["tradeId"]
    assert isinstance(fill_1["sequence"], int) and isinstance(fill_2["sequence"], int)
    assert 0 < fill_1["sequence"] < fill_2["sequence"]                   # RN-3
    assert fill_1["tradeId"] == f"T-{fill_1['sequence']}"                # RN-2
    assert fill_2["tradeId"] == f"T-{fill_2['sequence']}"

    # Y: montos exactos de cada porción
    assert fill_1["quantityWei"] == "300000000000000000"
    assert fill_1["quoteAmountMin"] == "600000000"
    assert fill_2["quantityWei"] == "300000000000000000"
    assert fill_2["quoteAmountMin"] == "600300000"

    # Y: mismo takerOrderId (la orden propia del comprador en ambas patas) y
    # distinto makerOrderId (cada pata vendedora referencia su orden maker)
    assert fill_1["orderId"] == orden_taker["orderId"] == fill_2["orderId"]
    pata_m1 = entrada_unica(items_vendedor, priceMin=str(PRECIO_2000))
    pata_m2 = entrada_unica(items_vendedor, priceMin=str(PRECIO_2001))
    assert pata_m1["orderId"] == m1["orderId"]
    assert pata_m2["orderId"] == m2["orderId"]
    assert pata_m1["orderId"] != pata_m2["orderId"]
    # las patas vendedoras corresponden a los mismos dos trades
    assert {pata_m1["tradeId"], pata_m2["tradeId"]} == {fill_1["tradeId"], fill_2["tradeId"]}


@pytest.mark.at("AT-05-03-04")
def test_registro_coherente_con_ceil_efectivo(usuario, usuario_b, rpc):
    """HU-05-03 Escenario 4 (borde): coherencia aritmética con `ceil` efectivo.

    - Dado un fill takerSide = BUY de 1 lot (100000000000000 wei) @ 2000.01
    - Cuando se registra el trade
    - Entonces quoteAmountMin = "200001", feeQuoteMin = "201" (maker,
      ceil(200001×10/10000)), feeBaseWei = "200000000000" (taker)
    - Y se cumple RN-6: 200001 = floor(q × price / 10^18), 201 = ceil(200001×10/10000),
      0 <= 201 <= 200001
    - Y sellerNetQuoteMin = "199800", buyerNetBaseWei = "99800000000000"

    El fill de 1 lot se construye como remanente (HU-05-01 RN-11; ver
    comunes_ep05.construir_fill_de_un_lot).
    """
    precio = 2_000_010_000                          # 2000.01
    q_lot = UN_LOT_WEI

    # Coherencia aritmética esperada (RN-6), con las fórmulas de referencia:
    quote_lot = quote_min(q_lot, precio)
    fee_quote = fee_maker(quote_lot)
    fee_base = fee_taker(q_lot)
    assert quote_lot == (q_lot * precio) // 10**18 == 200_001
    assert fee_quote == -(-(quote_lot * 10) // 10_000) == 201
    assert fee_base == -(-(q_lot * 20) // 10_000) == 200_000_000_000
    assert 0 <= fee_base <= q_lot and 0 <= fee_quote <= quote_lot

    # Dado / Cuando
    s1, _b1, b2 = construir_fill_de_un_lot(usuario, usuario_b, rpc, precio)

    # Entonces: el registro proyectado en cada pata cumple RN-6 con esos enteros
    pata_vendedora = entrada_unica(esperar_trades(usuario_b, 2), quantityWei=str(q_lot))
    assert pata_vendedora["quoteAmountMin"] == "200001"
    assert pata_vendedora["feeAmount"] == "201"                     # feeQuoteMin
    assert pata_vendedora["netReceived"] == "199800"                # sellerNetQuoteMin
    assert pata_vendedora["role"] == "MAKER" and pata_vendedora["side"] == "SELL"
    assert pata_vendedora["orderId"] == s1["orderId"]

    pata_compradora = entrada_unica(esperar_trades(usuario, 2), quantityWei=str(q_lot))
    assert pata_compradora["quoteAmountMin"] == "200001"
    assert pata_compradora["feeAmount"] == "200000000000"           # feeBaseWei
    assert pata_compradora["netReceived"] == "99800000000000"       # buyerNetBaseWei
    assert pata_compradora["role"] == "TAKER" and pata_compradora["side"] == "BUY"
    assert pata_compradora["orderId"] == b2["orderId"]
    # mismo trade visto de ambos lados
    assert pata_compradora["tradeId"] == pata_vendedora["tradeId"]


@pytest.mark.at("AT-05-03-08")
def test_montos_del_trade_serializados_como_string(usuario, usuario_b, rpc):
    """HU-05-03 Escenario 8 (serialización/error): montos como string entero.

    - Dado un trade con quantityWei = 1000000000000000000 y feeQuoteMin = 2000000
    - Cuando el registro se serializa hacia la API
    - Entonces todos los montos viajan como string que matchea ^(0|[1-9][0-9]*)$
      ("1000000000000000000", "2000000"), nunca número JSON, decimal ni 1e18
    - Y un valor con float, signo o ceros a la izquierda sería inválido
      (convenciones §5; es_monto_valido aplica exactamente ese patrón)
    """
    q_wei = UN_ETH_WEI
    quote = quote_min(q_wei, PRECIO_2000)

    # Dado: el fill canónico (1 ETH @ 2000.00, taker BUY ⇒ feeQuoteMin = 2000000)
    fondear_eth(usuario_b, rpc, q_wei)
    fondear_usdc(usuario, rpc, quote)
    crear_maker(usuario_b, "SELL", PRECIO_2000, q_wei)
    crear_limit(usuario, "BUY", PRECIO_2000, q_wei)
    pata_compradora = esperar_trades(usuario, 1)[0]
    pata_vendedora = esperar_trades(usuario_b, 1)[0]

    # Entonces: strings canónicos exactos (== compara también la forma, sin ceros
    # a la izquierda ni signo; es_monto_valido rechaza números JSON tras el parseo)
    assert pata_compradora["quantityWei"] == "1000000000000000000"
    assert pata_vendedora["feeAmount"] == "2000000"                 # feeQuoteMin
    campos_monetarios = ("priceMin", "quantityWei", "quoteAmountMin", "feeAmount", "netReceived", "paid")
    for pata in (pata_compradora, pata_vendedora):
        for campo in campos_monetarios:
            assert es_monto_valido(pata[campo]), (campo, pata[campo])
        # sequence es conteo: entero JSON, no string (convenciones §5)
        assert isinstance(pata["sequence"], int) and not isinstance(pata["sequence"], bool)
        assert isinstance(pata["timestamp"], str)

    # Y: también en el feed público del trade (HU-09-01 RN-13)
    publico = item_de_market_trades(usuario.api, pata_compradora["tradeId"])
    assert es_monto_valido(publico["priceMin"]) and es_monto_valido(publico["quantityWei"])

    # Y: el patrón rechaza float/signo/ceros a la izquierda (autochequeo de la vara)
    assert not es_monto_valido(10**18)        # número JSON
    assert not es_monto_valido("1e18")        # notación científica
    assert not es_monto_valido("+2000000")    # signo
    assert not es_monto_valido("02000000")    # cero a la izquierda
