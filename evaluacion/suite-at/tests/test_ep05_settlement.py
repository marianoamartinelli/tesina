"""Épica 05 — HU-05-01 (settlement atómico al match): tests de aceptación black-box.

El settlement es interno; sus efectos observables por el contrato de la épica 09
son: balances de ambas patas antes/después del fill (GET /balances), el registro
del trade (GET /trades) y el estado de las órdenes (GET /orders/{id}).

Conservación de fondos (INV-1) en versión black-box: la cuenta EX no tiene
superficie REST, así que se verifica que la suma de deltas de los usuarios sea
exactamente ``-fee`` por activo (las fees calculadas con las fórmulas de
referencia de la spec: quote con floor, fee con ceil — helpers/montos.py). Si el
settlement crease o destruyese valor, o cobrase una fee distinta, los balances
finales exactos asertados aquí no cerrarían.

No automatizables black-box (ver tests/no_automatizables_ep05.yaml):
AT-05-01-06 (inyección de falla interna), AT-05-01-07 (redelivery del evento de
fill) y AT-05-01-09 (estado interno inconsistente inalcanzable por contrato).
"""

from concurrent.futures import ThreadPoolExecutor

import pytest

from comunes_ep05 import (
    PRECIO_2000,
    PRECIO_2001,
    PRECIO_2010,
    UN_ETH_WEI,
    assert_balance,
    crear_limit,
    crear_maker,
    crear_market,
    esperar_trades,
    fondear_eth,
    fondear_usdc,
    limpiar_ordenes_residuales,  # noqa: F401  (fixture autouse: limpieza del libro)
    orden_de,
)
from helpers.montos import a_int, fee_maker, fee_taker, quote_min


@pytest.mark.at("AT-05-01-01")
def test_fill_total_taker_compra_liquida_ambas_patas_con_fees(usuario, usuario_b, rpc):
    """HU-05-01 Escenario 1: Fill total — taker compra contra maker vende.

    - Dado un vendedor maker con SELL resting de 1 ETH @ 2000.00 (bloqueado 1 ETH)
    - Y un comprador taker con BUY a límite 2000.00 y bloqueado 2000 USDC
    - Cuando el matching emite el fill por 1 ETH @ 2000.00 (taker = comprador)
    - Entonces quote_min = 2000000000 y ambos bloqueados pasan a 0
    - Y fee_base = 2000000000000000 wei (taker 20 bps) y fee_quote = 2000000 (maker 10 bps)
    - Y el comprador recibe 998000000000000000 wei y el vendedor 1998000000 USDC-min
    - Y la conservación por activo se mantiene (INV-1; suma de deltas = -fees a EX)
    """
    q_wei = UN_ETH_WEI
    quote = quote_min(q_wei, PRECIO_2000)          # RN-3: floor(q_wei × price / 10^18)
    assert quote == 2_000_000_000                  # literal del AT
    fee_base = fee_taker(q_wei)                    # comprador taker: 20 bps en ETH (HU-05-02 RN-3/RN-4)
    fee_quote = fee_maker(quote)                   # vendedor maker: 10 bps en USDC
    assert fee_base == 2_000_000_000_000_000 and fee_quote == 2_000_000  # literales del AT

    # Dado: fondeo black-box exacto (depósito on-chain acreditado, épicas 06+07)
    fondear_eth(usuario_b, rpc, q_wei)             # vendedor maker
    fondear_usdc(usuario, rpc, quote)              # comprador taker
    crear_maker(usuario_b, "SELL", PRECIO_2000, q_wei)
    # bloqueo previo del maker (épica 04): 1 ETH bloqueado respalda la orden
    assert_balance(usuario_b, "ETH", available=0, locked=q_wei)

    # Cuando: el taker cruza (BUY LIMIT al mismo precio) y se liquida el fill
    crear_limit(usuario, "BUY", PRECIO_2000, q_wei)
    esperar_trades(usuario, 1)

    # Entonces: bloqueados en 0 y netos exactos en ambas patas (RN-4/RN-5)
    # Vendedor: entrega q_wei del bloqueado ETH; recibe quote - fee_quote en USDC.
    assert_balance(usuario_b, "ETH", available=0, locked=0)
    assert_balance(usuario_b, "USDC", available=quote - fee_quote, locked=0)
    assert quote - fee_quote == 1_998_000_000
    # Comprador: entrega quote del bloqueado USDC; recibe q_wei - fee_base en ETH.
    assert_balance(usuario, "USDC", available=0, locked=0)
    assert_balance(usuario, "ETH", available=q_wei - fee_base, locked=0)
    assert q_wei - fee_base == 998_000_000_000_000_000

    # Y: conservación por activo (INV-1, RN-8) — suma de deltas de usuarios = -fee:
    # ETH:  (-q_wei) + (q_wei - fee_base) == -fee_base  → fee_base acreditada a EX
    # USDC: (-quote) + (quote - fee_quote) == -fee_quote → fee_quote acreditada a EX
    assert (-q_wei) + (q_wei - fee_base) == -fee_base
    assert (-quote) + (quote - fee_quote) == -fee_quote


@pytest.mark.at("AT-05-01-02")
def test_fill_total_taker_vende_liquida_ambas_patas_con_fees(usuario, usuario_b, rpc):
    """HU-05-01 Escenario 2: Fill total — taker vende contra maker compra.

    - Dado un comprador maker con BUY resting de 1 ETH @ 2000.00 (bloqueado 2000 USDC)
    - Y un vendedor taker con SELL a límite 2000.00 y bloqueado 1 ETH
    - Cuando el matching emite el fill (taker = vendedor)
    - Entonces quote_min = 2000000000 y ambos bloqueados pasan a 0
    - Y fee_quote = 4000000 (vendedor taker, 20 bps) y fee_base = 1000000000000000
      (comprador maker, 10 bps)
    - Y el comprador recibe 999000000000000000 wei y el vendedor 1996000000 USDC-min
    - Y se preserva la conservación por activo con EX incluida (INV-1)
    """
    q_wei = UN_ETH_WEI
    quote = quote_min(q_wei, PRECIO_2000)
    fee_quote = fee_taker(quote)                   # vendedor taker: 20 bps en USDC
    fee_base = fee_maker(q_wei)                    # comprador maker: 10 bps en ETH
    assert fee_quote == 4_000_000 and fee_base == 1_000_000_000_000_000  # literales del AT

    # Dado
    fondear_usdc(usuario, rpc, quote)              # comprador maker
    fondear_eth(usuario_b, rpc, q_wei)             # vendedor taker
    crear_maker(usuario, "BUY", PRECIO_2000, q_wei)
    assert_balance(usuario, "USDC", available=0, locked=quote)

    # Cuando
    crear_limit(usuario_b, "SELL", PRECIO_2000, q_wei)
    esperar_trades(usuario_b, 1)

    # Entonces
    assert_balance(usuario_b, "ETH", available=0, locked=0)
    assert_balance(usuario_b, "USDC", available=quote - fee_quote, locked=0)
    assert quote - fee_quote == 1_996_000_000
    assert_balance(usuario, "USDC", available=0, locked=0)
    assert_balance(usuario, "ETH", available=q_wei - fee_base, locked=0)
    assert q_wei - fee_base == 999_000_000_000_000_000

    # Y: conservación (INV-1): deltas de usuarios = -fees hacia EX, por activo
    assert (-q_wei) + (q_wei - fee_base) == -fee_base
    assert (-quote) + (quote - fee_quote) == -fee_quote


@pytest.mark.at("AT-05-01-03")
def test_fill_parcial_deja_remanente_bloqueado(usuario, usuario_b, rpc):
    """HU-05-01 Escenario 3 (borde): Fill parcial — el remanente sigue bloqueado.

    - Dado un maker SELL resting de 1 ETH @ 2000.00 (bloqueado 1 ETH)
    - Cuando entra un taker BUY que matchea solo 0.4 ETH @ 2000.00
    - Entonces se liquidan exactamente 0.4 ETH con quote_min = 800000000
    - Y bloqueado(vendedor, ETH) queda en 600000000000000000 (orden PARTIALLY_FILLED)
    - Y no se exige mínimo notional sobre el fill parcial (RN-11)
    - Y la conservación se mantiene para la porción liquidada (INV-1)
    """
    q_maker = UN_ETH_WEI
    q_fill = 400_000_000_000_000_000               # 0.4 ETH
    quote = quote_min(q_fill, PRECIO_2000)
    assert quote == 800_000_000                    # literal del AT
    fee_base = fee_taker(q_fill)                   # comprador taker
    fee_quote = fee_maker(quote)                   # vendedor maker

    # Dado
    fondear_eth(usuario_b, rpc, q_maker)
    fondear_usdc(usuario, rpc, quote)              # exacto para 0.4 ETH @ 2000.00
    maker = crear_maker(usuario_b, "SELL", PRECIO_2000, q_maker)

    # Cuando: taker BUY por 0.4 ETH (notional 800 USDC >= mínimo al alta)
    crear_limit(usuario, "BUY", PRECIO_2000, q_fill)
    esperar_trades(usuario, 1)

    # Entonces: se liquidó exactamente la porción matcheada (RN-11)
    # Vendedor: 0.6 ETH remanente sigue bloqueado; recibió el neto quote del fill.
    assert_balance(usuario_b, "ETH", available=0, locked=q_maker - q_fill)
    assert q_maker - q_fill == 600_000_000_000_000_000
    assert_balance(usuario_b, "USDC", available=quote - fee_quote, locked=0)
    # Y: la orden maker queda PARTIALLY_FILLED con filledWei exacto
    maker_actual = orden_de(usuario_b, maker["orderId"])
    assert maker_actual["status"] == "PARTIALLY_FILLED", maker_actual
    assert a_int(maker_actual["filledWei"]) == q_fill

    # Comprador: recibió el neto de la porción; su bloqueado quote se consumió entero.
    assert_balance(usuario, "ETH", available=q_fill - fee_base, locked=0)
    assert_balance(usuario, "USDC", available=0, locked=0)

    # Y: conservación de la porción liquidada (INV-1): deltas usuarios = -fees
    assert (-q_fill) + (q_fill - fee_base) == -fee_base
    assert (-quote) + (quote - fee_quote) == -fee_quote


@pytest.mark.at("AT-05-01-04")
def test_mejora_de_precio_taker_comprador_libera_surplus(usuario, usuario_b, rpc):
    """HU-05-01 Escenario 4 (borde): Mejora de precio del taker comprador — surplus.

    - Dado un maker SELL resting a 2000.00 por 1 ETH
    - Y un comprador taker BUY LIMIT con límite 2010.00, que bloqueó 2010000000 USDC-min
    - Cuando se ejecuta el fill por 1 ETH al precio del maker (2000.00; RN-2)
    - Entonces quote_min = 2000000000 se consume del bloqueado del comprador
    - Y el surplus 10000000 (10 USDC) se libera: pasa de bloqueado a disponible (RN-6)
    - Y total(comprador, USDC) disminuye exactamente en 2000000000 (el surplus no
      altera el total; la fee del taker BUY se cobra en ETH, no en USDC)
    - Y total(comprador, ETH) aumenta en el neto 998000000000000000 (INV-1)
    """
    q_wei = UN_ETH_WEI
    bloqueado_alta = quote_min(q_wei, PRECIO_2010)   # lo que bloquea la épica 04 al alta
    quote = quote_min(q_wei, PRECIO_2000)            # lo efectivamente pagado (precio maker)
    surplus = bloqueado_alta - quote                 # RN-6 (exacto, sin dust: tick × lot)
    assert (bloqueado_alta, quote, surplus) == (2_010_000_000, 2_000_000_000, 10_000_000)
    fee_base = fee_taker(q_wei)

    # Dado: fondeo exacto del límite del taker (2010 USDC) y del maker (1 ETH)
    fondear_eth(usuario_b, rpc, q_wei)
    fondear_usdc(usuario, rpc, bloqueado_alta)
    crear_maker(usuario_b, "SELL", PRECIO_2000, q_wei)

    # Cuando: taker BUY LIMIT @ 2010.00 cruza al precio del maker (2000.00)
    crear_limit(usuario, "BUY", PRECIO_2010, q_wei)
    esperar_trades(usuario, 1)

    # Entonces: el comprador pagó exactamente quote_min; el surplus quedó disponible
    # (bloqueado 0): total(USDC) = 2010000000 - 2000000000 = 10000000, todo disponible.
    assert_balance(usuario, "USDC", available=surplus, locked=0)
    # Y: total(comprador, ETH) aumenta en el neto recibido (fee del taker en ETH)
    assert_balance(usuario, "ETH", available=q_wei - fee_base, locked=0)
    assert q_wei - fee_base == 998_000_000_000_000_000

    # Y: la pata del vendedor liquida al precio maker, como en el fill sin mejora
    assert_balance(usuario_b, "ETH", available=0, locked=0)
    assert_balance(usuario_b, "USDC", available=quote - fee_maker(quote), locked=0)


@pytest.mark.at("AT-05-01-05")
def test_sweep_dos_makers_produce_dos_settlements_independientes(usuario, usuario_b, rpc):
    """HU-05-01 Escenario 5 (borde): Sweep — un taker barre dos makers, dos settlements.

    - Dado dos makers SELL resting: M1 0.3 ETH @ 2000.00 (más prioridad) y
      M2 0.3 ETH @ 2001.00
    - Cuando entra un taker BUY por 0.6 ETH con límite 2001.00
    - Entonces se generan dos fills independientes (F1 vs M1 @ 2000.00, F2 vs M2 @ 2001.00),
      cada uno con su settlement atómico
    - Y cada settlement preserva INV-1/INV-2/INV-3/INV-4 por separado
    - Y la suma de quote_min consumidos del comprador es 600000000 + 600300000 = 1200300000
    """
    q_m = 300_000_000_000_000_000                   # 0.3 ETH por maker
    quote_f1 = quote_min(q_m, PRECIO_2000)
    quote_f2 = quote_min(q_m, PRECIO_2001)
    assert quote_f1 == 600_000_000 and quote_f2 == 600_300_000  # literales del AT
    bloqueado_alta = quote_min(2 * q_m, PRECIO_2001)  # taker BUY 0.6 @ 2001.00
    assert bloqueado_alta == 1_200_600_000

    # Dado: ambos makers desde la misma cuenta vendedora (dos órdenes maker distintas)
    fondear_eth(usuario_b, rpc, 2 * q_m)
    fondear_usdc(usuario, rpc, bloqueado_alta)
    crear_maker(usuario_b, "SELL", PRECIO_2000, q_m)   # M1: mejor precio, más prioridad
    crear_maker(usuario_b, "SELL", PRECIO_2001, q_m)   # M2

    # Cuando: el taker barre ambos niveles
    crear_limit(usuario, "BUY", PRECIO_2001, 2 * q_m)
    items = esperar_trades(usuario, 2)

    # Entonces: dos fills independientes, cada uno liquidado a su precio maker
    assert len(items) == 2, items
    precios = sorted(a_int(it["priceMin"]) for it in items)
    assert precios == [PRECIO_2000, PRECIO_2001], items
    assert {a_int(it["quantityWei"]) for it in items} == {q_m}, items
    assert len({it["tradeId"] for it in items}) == 2, items

    # Y: suma de quote_min consumidos = 1200300000; el surplus de F1 (300000, por
    # mejora de precio 2001→2000) volvió a disponible (RN-6) ⇒ total del comprador
    # disminuye exactamente en lo pagado.
    consumido = quote_f1 + quote_f2
    assert consumido == 1_200_300_000
    assert_balance(usuario, "USDC", available=bloqueado_alta - consumido, locked=0)
    fee_eth = fee_taker(q_m) + fee_taker(q_m)        # fee por fill (RN-12 de HU-05-02)
    assert_balance(usuario, "ETH", available=2 * q_m - fee_eth, locked=0)

    # Y: la pata del vendedor recibe el neto de cada fill por separado (INV-1 por fill)
    neto_vendedor = (quote_f1 - fee_maker(quote_f1)) + (quote_f2 - fee_maker(quote_f2))
    assert_balance(usuario_b, "ETH", available=0, locked=0)
    assert_balance(usuario_b, "USDC", available=neto_vendedor, locked=0)


@pytest.mark.at("AT-05-01-08")
def test_fills_sucesivos_sobre_mismo_maker_consumen_sin_solaparse(usuario, usuario_b, rpc):
    """HU-05-01 Escenario 8 (secuencia): Fills sucesivos sobre el mismo maker.

    - Dado un maker SELL resting de 1 ETH @ 2000.00
    - Cuando dos órdenes taker BUY generan fills de 0.6 y 0.4 ETH, en secuencia
    - Entonces cada settlement consume del bloqueado(maker, ETH) su porción sin
      solaparse (0.6e18 y luego 0.4e18, dejando 0)
    - Y nunca se consume más q_wei del que el maker tenía bloqueado (INV-2)
    - Y al finalizar, la suma total por activo es idéntica al estado previo (INV-1)

    Nota: las dos órdenes taker salen de la misma cuenta compradora; la identidad
    de la cuenta taker no interviene en el consumo del bloqueado del maker.
    (La ejecución concurrente de estos fills se cubre en AT-05-01-11.)
    """
    q_maker = UN_ETH_WEI
    q_f1 = 600_000_000_000_000_000                  # 0.6 ETH
    q_f2 = 400_000_000_000_000_000                  # 0.4 ETH
    quote_f1 = quote_min(q_f1, PRECIO_2000)
    quote_f2 = quote_min(q_f2, PRECIO_2000)

    # Dado
    fondear_eth(usuario_b, rpc, q_maker)
    fondear_usdc(usuario, rpc, quote_f1 + quote_f2)
    crear_maker(usuario_b, "SELL", PRECIO_2000, q_maker)
    assert_balance(usuario_b, "ETH", available=0, locked=q_maker)

    # Cuando: primer fill (0.6 ETH)
    crear_limit(usuario, "BUY", PRECIO_2000, q_f1)
    esperar_trades(usuario, 1)
    # Entonces: consumió exactamente su porción; el resto sigue bloqueado (sin solape)
    assert_balance(usuario_b, "ETH", available=0, locked=q_maker - q_f1)

    # Cuando: segundo fill (0.4 ETH)
    crear_limit(usuario, "BUY", PRECIO_2000, q_f2)
    esperar_trades(usuario, 2)
    # Entonces: bloqueado(maker, ETH) queda exactamente en 0 (nunca negativo, INV-2:
    # la serialización ^(0|[1-9][0-9]*)$ de /balances ya excluye negativos en toda
    # lectura intermedia).
    assert_balance(usuario_b, "ETH", available=0, locked=0)

    # Y: conservación al finalizar (INV-1): deltas de usuarios = -fees por activo
    fee_eth = fee_taker(q_f1) + fee_taker(q_f2)
    fee_usdc = fee_maker(quote_f1) + fee_maker(quote_f2)
    assert_balance(usuario, "ETH", available=q_maker - fee_eth, locked=0)
    assert_balance(usuario, "USDC", available=0, locked=0)
    assert_balance(usuario_b, "USDC", available=quote_f1 + quote_f2 - fee_usdc, locked=0)
    assert (-q_maker) + (q_maker - fee_eth) == -fee_eth
    assert (-(quote_f1 + quote_f2)) + (quote_f1 + quote_f2 - fee_usdc) == -fee_usdc


@pytest.mark.at("AT-05-01-10")
def test_market_buy_consume_quote_min_por_fill_sin_surplus(usuario, usuario_b, rpc):
    """HU-05-01 Escenario 10 (borde): Taker BUY market — consumo sin surplus por fill.

    - Dado un comprador taker MARKET BUY (sin price_limit_taker) con USDC disponible
      2010000000 y dos makers SELL: M1 0.5 ETH @ 2000.00 y M2 0.5 ETH @ 2001.00
    - Cuando el matching emite F1 (0.5 @ 2000.00) y F2 (0.5 @ 2001.00)
    - Entonces F1 consume 1000000000 y F2 consume 1000500000 del bloqueado del comprador
    - Y ningún fill libera surplus (RN-6): el settlement solo consume quote_min
    - Y la liberación del excedente bloqueado es responsabilidad de la épica 04 al
      terminar la orden market (no de esta épica)

    Observabilidad black-box: la orden MARKET termina de forma atómica respecto del
    contrato REST (el 201 ya trae el estado terminal, HU-09-01 RN-5), por lo que el
    remanente bloqueado *entre* los fills y su liberación por la épica 04 no son
    snapshots alcanzables desde afuera. Lo verificable es el estado final: el total
    de USDC del comprador disminuye EXACTAMENTE en quote_f1 + quote_f2 = 2000500000
    (si el settlement hubiera liberado surplus por fill o consumido el bloqueado
    estimado, el número no cerraría) y el bloqueado termina en 0.

    TODO-REVISAR: la premisa del AT ("la épica 04 bloqueó 2010000000, estimación por
    mejor ask") no coincide con épica 04 README RE-1, que fija para MARKET BUY por
    cantidad R = costo exacto de barrer el snapshot de asks (= 2000500000 aquí). El
    estado final observable asertado abajo es el mismo bajo ambas lecturas.
    """
    q_m = 500_000_000_000_000_000                   # 0.5 ETH por maker
    quote_f1 = quote_min(q_m, PRECIO_2000)
    quote_f2 = quote_min(q_m, PRECIO_2001)
    assert quote_f1 == 1_000_000_000 and quote_f2 == 1_000_500_000  # literales del AT
    disponible_inicial = 2_010_000_000              # el disponible del AT

    # Dado
    fondear_eth(usuario_b, rpc, 2 * q_m)
    fondear_usdc(usuario, rpc, disponible_inicial)
    crear_maker(usuario_b, "SELL", PRECIO_2000, q_m)   # M1
    crear_maker(usuario_b, "SELL", PRECIO_2001, q_m)   # M2

    # Cuando: MARKET BUY por 1 ETH (sin priceMin)
    orden = crear_market(usuario, "BUY", 2 * q_m)
    assert orden["priceMin"] is None, orden
    items = esperar_trades(usuario, 2)

    # Entonces: dos fills, cada uno consumió exactamente su quote_min al precio maker
    assert {(a_int(it["priceMin"]), a_int(it["paid"])) for it in items} == {
        (PRECIO_2000, quote_f1),
        (PRECIO_2001, quote_f2),
    }, items

    # Y: estado final exacto — total USDC del comprador bajó en quote_f1+quote_f2 y
    # el bloqueado quedó en 0 (excedente liberado por la épica 04 al terminar la orden)
    consumido = quote_f1 + quote_f2
    assert_balance(usuario, "USDC", available=disponible_inicial - consumido, locked=0)
    assert disponible_inicial - consumido == 9_500_000
    # La orden market terminó FILLED por la cantidad completa
    assert orden["status"] == "FILLED", orden
    assert a_int(orden["filledWei"]) == 2 * q_m

    # Y: conservación por fill con EX incluida (INV-1): pata vendedora exacta
    fee_eth = fee_taker(q_m) + fee_taker(q_m)
    neto_vendedor = (quote_f1 - fee_maker(quote_f1)) + (quote_f2 - fee_maker(quote_f2))
    assert_balance(usuario, "ETH", available=2 * q_m - fee_eth, locked=0)
    assert_balance(usuario_b, "ETH", available=0, locked=0)
    assert_balance(usuario_b, "USDC", available=neto_vendedor, locked=0)


@pytest.mark.at("AT-05-01-11")
def test_settlements_concurrentes_sobre_mismo_maker_se_serializan(usuario, usuario_b, rpc):
    """HU-05-01 Escenario 11 (concurrencia): settlements simultáneos se serializan.

    - Dado un maker SELL resting de 1 ETH @ 2000.00 (bloqueado 1 ETH)
    - Y dos fills F1 (0.6 ETH) y F2 (0.4 ETH) contra ese maker iniciados simultáneamente
    - Cuando ambos settlements intentan consumir bloqueado(maker, ETH) a la vez
    - Entonces el sistema serializa el acceso: uno consume 0.6e18 y el otro 0.4e18,
      dejando bloqueado(maker, ETH) = 0
    - Y nunca se consume más q_wei del bloqueado (INV-2)
    - Y el resultado es idéntico al de la ejecución secuencial de AT-05-01-08 (INV-1/INV-4)

    Aproximación black-box: las dos órdenes taker se envían en paralelo (dos hilos);
    la simultaneidad interna exacta de los settlements no es controlable desde el
    contrato, pero el AT exige que el resultado observable sea el secuencial, que es
    lo que se asserta (una doble lectura del mismo bloqueado dejaría números que no
    cierran o balances imposibles).
    """
    q_maker = UN_ETH_WEI
    q_f1 = 600_000_000_000_000_000
    q_f2 = 400_000_000_000_000_000
    quote_total = quote_min(q_f1, PRECIO_2000) + quote_min(q_f2, PRECIO_2000)

    # Dado
    fondear_eth(usuario_b, rpc, q_maker)
    fondear_usdc(usuario, rpc, quote_total)
    crear_maker(usuario_b, "SELL", PRECIO_2000, q_maker)

    # Cuando: dos taker BUY lanzados simultáneamente (dos hilos)
    def _orden_buy(q_wei):
        return usuario.api.post(
            "/orders",
            json={
                "clientOrderId": f"ep05-conc-{q_wei}",
                "symbol": "ETH-USDC",
                "side": "BUY",
                "type": "LIMIT",
                "priceMin": str(PRECIO_2000),
                "quantityWei": str(q_wei),
            },
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futuros = [pool.submit(_orden_buy, q_f1), pool.submit(_orden_buy, q_f2)]
        respuestas = [f.result() for f in futuros]
    for resp in respuestas:
        assert resp.status_code == 201, f"alta concurrente falló: {resp.status_code} {resp.text[:300]}"

    esperar_trades(usuario, 2)

    # Entonces: bloqueado(maker, ETH) = 0 exacto, sin sobre-consumo (INV-2)
    assert_balance(usuario_b, "ETH", available=0, locked=0)

    # Y: resultado idéntico al secuencial de AT-05-01-08 (mismos enteros finales)
    fee_eth = fee_taker(q_f1) + fee_taker(q_f2)
    fee_usdc = fee_maker(quote_min(q_f1, PRECIO_2000)) + fee_maker(quote_min(q_f2, PRECIO_2000))
    assert_balance(usuario, "ETH", available=q_maker - fee_eth, locked=0)
    assert_balance(usuario, "USDC", available=0, locked=0)
    assert_balance(usuario_b, "USDC", available=quote_total - fee_usdc, locked=0)
