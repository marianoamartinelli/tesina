"""Épica 03 / HU-03-01 — Estructura del orderbook: tests de aceptación black-box.

La estructura interna del libro (lados, niveles, cola FIFO por `seq`) se observa
por sus efectos contractuales: `GET /market/orderbook` (niveles agregados y
ordenados), `GET /market/ticker` (best de cada lado), el **orden de los fills**
(prioridad precio-tiempo) y los balances bloqueados (respaldo INV-7).

El `seq` interno no es observable de forma directa (RT-2: es una clave de orden,
no un stream); lo observable —y lo que fija cada AT— es la **prioridad de
atención** que ese `seq` induce.

Cada test opera en una banda de precios propia y cancela sus órdenes al final.
"""

import random
from concurrent.futures import ThreadPoolExecutor

import pytest

from helpers.cuentas import crear_usuario
from helpers.montos import LOT_SIZE, WEI_POR_ETH, a_str, assert_monto, quote_min

from tests.comunes_ep03 import (
    assert_libro_no_cruzado,
    balances_por_activo,
    cancelar_abiertas,
    colocar_limit,
    cuerpo_market,
    fondear,
    fondear_lote,
    libro,
    nivel,
    orden_actual,
    post_orden_reintentando_429,
    requerir_libro_vacio,
    requerir_sin_asks_cruzables,
    requerir_sin_bids_cruzables,
    ticker,
    trades_propios,
)

ETH = WEI_POR_ETH  # 1 ETH en wei


@pytest.mark.at("AT-03-01-01")
def test_ordenamiento_de_niveles_en_ambos_lados(api, usuario, rpc):
    """HU-03-01 Escenario 1: Ordenamiento de niveles en ambos lados.

    - Dado un orderbook vacío
    - Cuando ingresan como pasivas: SELL 1 ETH @ 2001.00, SELL 1 ETH @ 2000.50,
      BUY 1 ETH @ 1999.00, BUY 1 ETH @ 2000.00
    - Entonces best ask = 2000.50 y el siguiente ask = 2001.00 (RN-3)
    - Y best bid = 2000.00 y el siguiente bid = 1999.00 (RN-2)
    - Y best_bid_price < best_ask_price (libro no cruzado, RN-9)
    """
    # Dado: orderbook vacío (el Dado del Gherkin es global; sin él no hay veredicto)
    requerir_libro_vacio(api)
    # Una misma cuenta puede tener órdenes en ambos lados sin solapar (HU-03-06 RN-10)
    fondear(usuario, rpc, eth_wei=2 * ETH, usdc_min=4_100_000_000)
    try:
        # Cuando: ingresan las cuatro pasivas en este orden
        colocar_limit(usuario, "SELL", 2_001_000_000, ETH, esperado="OPEN")
        colocar_limit(usuario, "SELL", 2_000_500_000, ETH, esperado="OPEN")
        colocar_limit(usuario, "BUY", 1_999_000_000, ETH, esperado="OPEN")
        colocar_limit(usuario, "BUY", 2_000_000_000, ETH, esperado="OPEN")

        # Entonces: asks ascendentes con best 2000.50 (RN-3)
        lib = libro(api)
        assert [p for p, _ in lib["asks"]] == ["2000500000", "2001000000"], lib["asks"]
        # Y: bids descendentes con best 2000.00 (RN-2)
        assert [p for p, _ in lib["bids"]] == ["2000000000", "1999000000"], lib["bids"]
        # Y: 2000000000 < 2000500000 — libro no cruzado (RN-9, INV-7)
        assert_libro_no_cruzado(lib)
    finally:
        cancelar_abiertas(usuario)


@pytest.mark.at("AT-03-01-02")
def test_fifo_dentro_de_un_mismo_nivel_de_precio(api, usuario, usuario_b, rpc):
    """HU-03-01 Escenario 2: FIFO dentro de un mismo nivel de precio.

    - Dado un orderbook vacío (en la banda del test)
    - Cuando ingresan tres SELL 1 ETH @ 2005.00 en el orden A, B, C
    - Entonces comparten nivel y la prioridad de atención es A, luego B, luego C (RN-5)
    - Y la clave (precio, seq) no produce empates (RN-6): cada fill agota una sola
      orden, en orden estricto de llegada

    La monotonía de `seq` es interna; lo observable es la prioridad FIFO que
    induce, verificada consumiendo el nivel de a 1 ETH.
    """
    precio = 2_005_000_000  # banda propia del test
    requerir_sin_bids_cruzables(api, precio)
    requerir_sin_asks_cruzables(api, precio)
    fondear(usuario, rpc, eth_wei=3 * ETH)                # maker: A, B, C
    fondear(usuario_b, rpc, usdc_min=4_100_000_000)       # taker: 2 × 2005 USDC + margen
    try:
        # Cuando: A, luego B, luego C al mismo nivel
        orden_a = colocar_limit(usuario, "SELL", precio, ETH, esperado="OPEN")
        orden_b = colocar_limit(usuario, "SELL", precio, ETH, esperado="OPEN")
        orden_c = colocar_limit(usuario, "SELL", precio, ETH, esperado="OPEN")
        assert nivel(libro(api), "asks", precio) == 3 * ETH  # comparten nivel (RN-4)

        # Entonces: el primer taker de 1 ETH consume exactamente A (FIFO, RN-5)
        colocar_limit(usuario_b, "BUY", precio, ETH, esperado="FILLED")
        assert orden_actual(usuario, orden_a["orderId"])["status"] == "FILLED"
        assert orden_actual(usuario, orden_b["orderId"])["status"] == "OPEN"
        assert orden_actual(usuario, orden_c["orderId"])["status"] == "OPEN"

        # Y: el segundo taker consume exactamente B; C sigue intacta (sin empates, RN-6)
        colocar_limit(usuario_b, "BUY", precio, ETH, esperado="FILLED")
        assert orden_actual(usuario, orden_b["orderId"])["status"] == "FILLED"
        orden_c_final = orden_actual(usuario, orden_c["orderId"])
        assert orden_c_final["status"] == "OPEN"
        assert orden_c_final["filledWei"] == "0"
    finally:
        cancelar_abiertas(usuario, usuario_b)


@pytest.mark.at("AT-03-01-03")
def test_lado_vacio_best_price_indefinido(api, usuario, rpc):
    """HU-03-01 Escenario 3 (borde): Un lado vacío — best price indefinido.

    - Dado un orderbook con asks poblado y bids vacío
    - Cuando se consulta el estado del libro
    - Entonces best_bid es indefinido (null, no 0) y el spread es indefinido (RN-13)
    - Y best_ask existe y es el ask de menor price_min
    """
    # Dado: libro vacío + solo asks (RN-13: lados independientes)
    requerir_libro_vacio(api)
    fondear(usuario, rpc, eth_wei=2 * ETH)
    try:
        colocar_limit(usuario, "SELL", 2_010_000_000, ETH, esperado="OPEN")
        colocar_limit(usuario, "SELL", 2_011_000_000, ETH, esperado="OPEN")

        # Cuando / Entonces: bids vacío ⇒ bestBidPrice null (no "0"; HU-09-01 RN-16)
        t = ticker(api)
        assert t["bestBidPrice"] is None, t
        # Y: best_ask existe y es el de menor price_min
        assert t["bestAskPrice"] == "2010000000", t

        lib = libro(api)
        assert lib["bids"] == [], lib
        assert [p for p, _ in lib["asks"]] == ["2010000000", "2011000000"], lib["asks"]
    finally:
        cancelar_abiertas(usuario)


@pytest.mark.at("AT-03-01-04")
def test_prioridad_se_recomputa_sobre_el_remanente(api, usuario, usuario_b, rpc):
    """HU-03-01 Escenario 4 (borde): Prioridad se recomputa sobre el remanente.

    - Dado un nivel BUY @ 2015.00 con O1 (seq menor, remanente 0.5 ETH tras fill
      parcial) y O2 (seq mayor, remanente 1 ETH)
    - Cuando se evalúa la prioridad del nivel (consumiendo 0.5 ETH)
    - Entonces O1 mantiene prioridad por menor seq, independientemente de la
      cantidad (RN-5, RN-8): O1 se completa y O2 no se toca
    - Y los remanentes se exponen como string de entero (RN-12)
    """
    precio = 2_015_000_000
    requerir_sin_bids_cruzables(api, precio)
    requerir_sin_asks_cruzables(api, precio)
    fondear(usuario, rpc, usdc_min=4_100_000_000)   # maker de O1 y O2
    fondear(usuario_b, rpc, eth_wei=ETH)            # taker SELL
    try:
        # Dado: O1 con fill parcial de 0.5 ETH (remanente 0.5) y luego O2 de 1 ETH
        orden_1 = colocar_limit(usuario, "BUY", precio, ETH, esperado="OPEN")
        colocar_limit(usuario_b, "SELL", precio, ETH // 2, esperado="FILLED")
        o1 = orden_actual(usuario, orden_1["orderId"])
        assert o1["status"] == "PARTIALLY_FILLED"
        # remanente = quantityWei − filledWei, ambos strings bien serializados (RN-8, RN-12)
        assert o1["filledWei"] == a_str(ETH // 2)
        assert assert_monto(o1["quantityWei"]) - assert_monto(o1["filledWei"]) == ETH // 2

        orden_2 = colocar_limit(usuario, "BUY", precio, ETH, esperado="OPEN")

        # Cuando: se consumen 0.5 ETH del nivel
        colocar_limit(usuario_b, "SELL", precio, ETH // 2, esperado="FILLED")

        # Entonces: O1 (seq menor) se completa aunque su remanente era menor que el
        # de O2 (la prioridad no depende de la cantidad, RN-5)
        assert orden_actual(usuario, orden_1["orderId"])["status"] == "FILLED"
        o2 = orden_actual(usuario, orden_2["orderId"])
        assert o2["status"] == "OPEN"
        assert o2["filledWei"] == "0"
    finally:
        cancelar_abiertas(usuario, usuario_b)


@pytest.mark.at("AT-03-01-05")
def test_libro_nunca_cruzado_en_reposo_property(api, rpc):
    """HU-03-01 Escenario 5 (integridad): El libro nunca queda cruzado en reposo.

    - Dado un libro concreto con dos bids y dos asks
    - Entonces best_bid < best_ask y no existe par (bid, ask) cruzado (RN-9, INV-7)
    - Y (property-based) tras cada una de ≥ 500 órdenes aleatorias LIMIT/MARKET,
      el libro cumple INV-7 en todos los estados observables en reposo

    Generador determinista (semilla fija) sobre una banda propia [3000, 3010]:
    6 cuentas sólo-SELL y 6 sólo-BUY (así ninguna orden dispara STP) para
    respetar además el rate limit por cuenta (HU-09-02).
    """
    rng = random.Random(20260705)  # reproducible
    vendedores = [crear_usuario(api, "ep03-ob-v") for _ in range(6)]
    compradores = [crear_usuario(api, "ep03-ob-c") for _ in range(6)]
    fondear_lote(vendedores, rpc, eth_wei=1 * ETH)
    fondear_lote(compradores, rpc, usdc_min=3_000_000_000)
    cuentas = [c for par in zip(vendedores, compradores) for c in par]
    try:
        # Dado (caso concreto del Gherkin): dos bids y dos asks no cruzados
        colocar_limit(compradores[0], "BUY", 3_000_000_000, 100 * LOT_SIZE, esperado="OPEN")
        colocar_limit(compradores[1], "BUY", 2_999_000_000, 50 * LOT_SIZE, esperado="OPEN")
        colocar_limit(vendedores[0], "SELL", 3_010_000_000, 100 * LOT_SIZE, esperado="OPEN")
        colocar_limit(vendedores[1], "SELL", 3_011_000_000, 50 * LOT_SIZE, esperado="OPEN")
        lib = libro(api)
        assert_libro_no_cruzado(lib)  # incluye: ningún par (bid_i, ask_j) con bid ≥ ask

        # Y (property-based): ≥ 500 órdenes aleatorias, libro íntegro tras cada una
        for i in range(500):
            cuenta = cuentas[i % len(cuentas)]
            es_vendedor = cuenta in vendedores
            side = "SELL" if es_vendedor else "BUY"
            cantidad = rng.randrange(40, 201) * LOT_SIZE  # notional ≥ 12 USDC (≥ mínimo)
            if rng.random() < 0.85:
                precio = 3_000_000_000 + rng.randrange(0, 1001) * 10_000  # tick múltiplo
                resp = post_orden_reintentando_429(
                    cuenta,
                    {
                        "clientOrderId": f"ep03-prop-{i}",
                        "symbol": "ETH-USDC",
                        "side": side,
                        "type": "LIMIT",
                        "priceMin": a_str(precio),
                        "quantityWei": a_str(cantidad),
                    },
                )
                assert resp.status_code == 201, f"op {i}: {resp.text[:200]}"
            else:
                resp = post_orden_reintentando_429(cuenta, cuerpo_market(side, q_wei=cantidad))
                # Una MARKET puede no encontrar liquidez: es un resultado válido del
                # generador (HU-03-04 RN-8); cualquier otro error es una falla real.
                assert resp.status_code == 201 or (
                    resp.status_code == 422
                    and resp.json()["error"]["code"] == "MARKET_NO_LIQUIDITY"
                ), f"op {i}: {resp.text[:200]}"

            # inspección del libro tras CADA operación (estado en reposo, RT-1)
            assert_libro_no_cruzado(libro(cuenta.api))
    finally:
        cancelar_abiertas(*cuentas)


@pytest.mark.at("AT-03-01-06")
def test_respaldo_en_fondos_bloqueados(api, usuario, rpc):
    """HU-03-01 Escenario 6 (integridad): Respaldo en fondos bloqueados.

    - Dado un orderbook con varias órdenes abiertas de una cuenta
    - Cuando se suma el respaldo requerido por el remanente de cada orden:
      SELL ⇒ remainingWei de ETH; BUY ⇒ floor(remainingWei × price_min / 10^18)
      USDC-min, sin fees anticipadas (RN-10)
    - Entonces esa suma es exactamente el bloqueado por activo (INV-7): la cuenta
      es fresca, así que todo bloqueado es atribuible a órdenes
    """
    eth_fondeado = 1 * ETH
    usdc_fondeado = 4_100_000_000
    fondear(usuario, rpc, eth_wei=eth_fondeado, usdc_min=usdc_fondeado)
    try:
        # Dado: tres órdenes abiertas (los lados no se solapan: 2021 > 2020, sin cruce)
        colocar_limit(usuario, "SELL", 2_021_000_000, 7 * ETH // 10, esperado="OPEN")
        colocar_limit(usuario, "BUY", 2_020_000_000, ETH, esperado="OPEN")
        colocar_limit(usuario, "BUY", 2_019_500_000, ETH // 2, esperado="OPEN")

        # Cuando: respaldo esperado con las fórmulas de referencia (RN-10, sin fees)
        respaldo_eth = 7 * ETH // 10
        respaldo_usdc = quote_min(ETH, 2_020_000_000) + quote_min(ETH // 2, 2_019_500_000)

        # Entonces: bloqueado == respaldo, exacto por activo (INV-7, INV-3)
        balances = balances_por_activo(usuario)
        assert assert_monto(balances["ETH"]["locked"]) == respaldo_eth
        assert assert_monto(balances["USDC"]["locked"]) == respaldo_usdc
        assert assert_monto(balances["ETH"]["available"]) == eth_fondeado - respaldo_eth
        assert assert_monto(balances["USDC"]["available"]) == usdc_fondeado - respaldo_usdc
    finally:
        cancelar_abiertas(usuario)


@pytest.mark.at("AT-03-01-07")
def test_solo_viven_ordenes_abiertas(api, usuario, usuario_b, rpc):
    """HU-03-01 Escenario 7 (borde): Solo viven órdenes abiertas.

    - Dado un nivel con una orden que se ejecuta totalmente (pasa a FILLED)
    - Cuando concluye su ejecución
    - Entonces la orden se retira del libro de inmediato (RN-7)
    - Y ninguna orden FILLED o CANCELLED permanece en el libro
    """
    precio = 2_025_000_000
    requerir_sin_bids_cruzables(api, precio)
    requerir_sin_asks_cruzables(api, precio)
    fondear(usuario, rpc, eth_wei=2 * ETH)
    fondear(usuario_b, rpc, usdc_min=2_100_000_000)
    try:
        # Dado: un maker que se ejecutará por completo
        maker = colocar_limit(usuario, "SELL", precio, ETH, esperado="OPEN")
        assert nivel(libro(api), "asks", precio) == ETH

        # Cuando: se llena por completo
        colocar_limit(usuario_b, "BUY", precio, ETH, esperado="FILLED")

        # Entonces: FILLED y retirada del libro de inmediato (RN-7)
        assert orden_actual(usuario, maker["orderId"])["status"] == "FILLED"
        assert nivel(libro(api), "asks", precio) == 0

        # Y: una orden CANCELLED tampoco permanece en el libro
        pasiva = colocar_limit(usuario, "SELL", precio, ETH, esperado="OPEN")
        assert nivel(libro(api), "asks", precio) == ETH
        resp = usuario.api.delete(f"/orders/{pasiva['orderId']}")
        assert resp.status_code == 200 and resp.json()["status"] == "CANCELLED", resp.text
        assert nivel(libro(api), "asks", precio) == 0
    finally:
        cancelar_abiertas(usuario, usuario_b)


@pytest.mark.at("AT-03-01-08")
def test_ejecucion_serializada_sin_interleaving(api, rpc):
    """HU-03-01 Escenario 8 (integridad): Ejecución serializada — sin interleaving.

    - Dado N órdenes LIMIT entregadas al motor en paralelo sobre el mismo par
    - Cuando el motor las procesa (README RT-1: serialización por par)
    - Entonces el estado final es equivalente a una permutación serial válida:
      Σ fills BUY == Σ fills SELL == Σ cantidades de los trades (sin fills a
      medias ni duplicados) y la conservación por activo se sostiene (INV-1)
    - Y en todo punto observable el libro cumple INV-7 (no cruzado)

    Black-box no se puede enumerar la permutación interna; sí se verifica que el
    resultado sea **consistente con alguna serialización**: cada fill es atómico
    (filled ≤ quantity, sumas cuadradas entre patas) y el libro nunca se observa
    cruzado durante la ráfaga.
    """
    vendedores = [crear_usuario(api, "ep03-ser-v") for _ in range(3)]
    compradores = [crear_usuario(api, "ep03-ser-c") for _ in range(3)]
    fondear_lote(vendedores, rpc, eth_wei=1 * ETH)
    fondear_lote(compradores, rpc, usdc_min=500_000_000)  # 500 USDC
    rng = random.Random(1108)
    cantidad = 100 * LOT_SIZE  # 0.01 ETH por orden (notional ~31 USDC)
    precios_sell = [3_100_000_000, 3_101_000_000, 3_102_000_000]
    precios_buy = [3_101_000_000, 3_102_000_000, 3_103_000_000, 3_104_000_000]

    def enviar(cuenta, side, precio, idx):
        return cuenta.api.post(
            "/orders",
            json={
                "clientOrderId": f"ep03-ser-{idx}",
                "symbol": "ETH-USDC",
                "side": side,
                "type": "LIMIT",
                "priceMin": a_str(precio),
                "quantityWei": a_str(cantidad),
            },
        )

    tareas = []
    for i in range(24):
        if i % 2 == 0:
            cuenta = vendedores[(i // 2) % 3]
            tareas.append((cuenta, "SELL", rng.choice(precios_sell), i))
        else:
            cuenta = compradores[(i // 2) % 3]
            tareas.append((cuenta, "BUY", rng.choice(precios_buy), i))
    rng.shuffle(tareas)

    try:
        # Cuando: las 24 órdenes se entregan concurrentemente
        with ThreadPoolExecutor(max_workers=12) as pool:
            futuros = [pool.submit(enviar, c, s, p, i) for c, s, p, i in tareas]
            # Y: en plena ráfaga, el libro nunca se observa cruzado (INV-7, RT-1)
            while not all(f.done() for f in futuros):
                assert_libro_no_cruzado(libro(api))
            respuestas = [f.result() for f in futuros]

        # Entonces: ninguna orden quedó a medias en el borde (todas aceptadas: no
        # hay STP posible —cada cuenta opera un solo lado— ni falta de fondos)
        ordenes = []
        for resp in respuestas:
            assert resp.status_code == 201, resp.text[:200]
            ordenes.append(resp.json())

        # Estado final: releer cada orden (pudo recibir fills posteriores a su alta);
        # la cuenta emisora quedó registrada en la tarea por índice de clientOrderId
        por_client_id = {t[3]: t[0] for t in tareas}
        suma_fill_buy = suma_fill_sell = 0
        for o in ordenes:
            idx = int(o["clientOrderId"].split("-")[-1])
            cuenta = por_client_id[idx]
            final = orden_actual(cuenta, o["orderId"])
            filled = assert_monto(final["filledWei"])
            assert 0 <= filled <= assert_monto(final["quantityWei"]), final  # atomicidad INV-4
            if final["side"] == "BUY":
                suma_fill_buy += filled
            else:
                suma_fill_sell += filled
        assert suma_fill_buy == suma_fill_sell, "las patas ejecutadas no cuadran (INV-1/INV-4)"

        # Σ cantidades de trades (dedup por tradeId entre las patas) == Σ fills por lado
        trades = {}
        fees = {"ETH": 0, "USDC": 0}
        for cuenta in vendedores + compradores:
            for t in trades_propios(cuenta):
                trades[t["tradeId"]] = assert_monto(t["quantityWei"])
                fees[t["feeAsset"]] += assert_monto(t["feeAmount"])
        assert sum(trades.values()) == suma_fill_buy, "trades ≠ fills (evento sin efecto o viceversa)"

        # Conservación por activo (INV-1): Σ totales de usuarios + fees cobradas == depósitos
        total_eth = sum(
            assert_monto(balances_por_activo(u)["ETH"]["total"]) for u in vendedores + compradores
        )
        total_usdc = sum(
            assert_monto(balances_por_activo(u)["USDC"]["total"]) for u in vendedores + compradores
        )
        assert total_eth + fees["ETH"] == 3 * ETH, "no se conserva ETH (INV-1)"
        assert total_usdc + fees["USDC"] == 3 * 500_000_000, "no se conserva USDC (INV-1)"

        # Y: el libro final queda íntegro
        assert_libro_no_cruzado(libro(api))
    finally:
        cancelar_abiertas(*(vendedores + compradores))
