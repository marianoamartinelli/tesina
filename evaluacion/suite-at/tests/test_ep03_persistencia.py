"""Épica 03 / HU-03-07 — Persistencia y recuperación del orderbook: tests black-box.

El reinicio del SUT lo orquesta el evaluador vía la env var
``SUITE_CMD_REINICIO_SUT`` (ver ``comunes_ep03.reiniciar_sut``): un comando que
termina el proceso **abruptamente** (kill -9 o equivalente; RN-1 define durable
como sobrevivir a esa terminación) y lo vuelve a levantar. Sin la variable,
estos tests saltan. Tras cada reinicio se renueva la sesión (la spec no exige
que los tokens sobrevivan; los balances y el libro sí, INV-8).

No automatizables (declarados en ``no_automatizables_ep03.yaml``):
AT-03-07-04 y AT-03-07-09 exigen inyectar la caída en un punto interno preciso
(en medio de un fill / entre persistir fills y grabar el estado terminal), sin
superficie black-box para provocarla determinísticamente.
"""

import pytest

from helpers.montos import LOT_SIZE, WEI_POR_ETH, a_str, assert_monto, quote_min

from tests.comunes_ep03 import (
    abrir_ws,
    balances_por_activo,
    cancelar_abiertas,
    colocar_limit,
    fondear,
    libro,
    nivel,
    numero_de_trade,
    orden_actual,
    relogin,
    reiniciar_sut,
    requerir_sin_asks_cruzables,
    requerir_sin_bids_cruzables,
    snapshot_balances,
    trades_propios,
    ultimo_trade_id,
)

ETH = WEI_POR_ETH


@pytest.mark.at("AT-03-07-01")
def test_ordenes_abiertas_sobreviven_al_reinicio_con_su_prioridad(api, usuario, usuario_b, rpc):
    """HU-03-07 Escenario 1: Órdenes abiertas sobreviven al reinicio con su prioridad.

    - Dado bids B1 y B2 BUY 1 ETH @ 2225.00 (en ese orden) y un ask A1 @ 2226.00
    - Cuando el sistema se reinicia y reconstruye el orderbook
    - Entonces las tres órdenes están presentes con los mismos orderId y
      remanentes (RN-1, RN-3)
    - Y la prioridad del nivel 2225.00 sigue siendo B1 antes que B2 (FIFO, RN-2)
    - Y best_bid < best_ask (RN-4)
    """
    precio_bid, precio_ask = 2_225_000_000, 2_226_000_000
    requerir_sin_asks_cruzables(api, precio_bid)
    requerir_sin_bids_cruzables(api, precio_bid)
    fondear(usuario_b, rpc, eth_wei=ETH, usdc_min=4_600_000_000)  # B1, B2 y A1
    fondear(usuario, rpc, eth_wei=ETH)                            # taker post-reinicio
    try:
        # Dado
        b1 = colocar_limit(usuario_b, "BUY", precio_bid, ETH, esperado="OPEN")
        b2 = colocar_limit(usuario_b, "BUY", precio_bid, ETH, esperado="OPEN")
        a1 = colocar_limit(usuario_b, "SELL", precio_ask, ETH, esperado="OPEN")

        # Cuando
        reiniciar_sut(api)
        relogin(usuario)
        relogin(usuario_b)

        # Entonces: mismas órdenes, mismos orderId, mismo remanente (RN-2, RN-3)
        for o in (b1, b2, a1):
            estado = orden_actual(usuario_b, o["orderId"])
            assert estado["status"] == "OPEN" and estado["filledWei"] == "0", estado
        lib = libro(api)
        assert nivel(lib, "bids", precio_bid) == 2 * ETH
        assert nivel(lib, "asks", precio_ask) == ETH
        # Y: no cruzado tras recuperar (RN-4, INV-7)
        assert assert_monto(lib["bids"][0][0]) < assert_monto(lib["asks"][0][0])

        # Y: la prioridad FIFO del nivel se preservó — consumir 1 ETH atiende a B1
        colocar_limit(usuario, "SELL", precio_bid, ETH, esperado="FILLED")
        assert orden_actual(usuario_b, b1["orderId"])["status"] == "FILLED"
        assert orden_actual(usuario_b, b2["orderId"])["status"] == "OPEN"
    finally:
        cancelar_abiertas(usuario, usuario_b)


@pytest.mark.at("AT-03-07-02")
def test_fill_parcial_remanente_persistido(api, usuario, usuario_b, rpc):
    """HU-03-07 Escenario 2: Fill parcial — remanente persistido correctamente.

    - Dado un maker SELL 2 ETH @ 2230.00 parcialmente ejecutado hasta remanente
      1 ETH (PARTIALLY_FILLED)
    - Cuando el sistema se reinicia
    - Entonces la orden se reconstruye con PARTIALLY_FILLED, filledWei = 1 ETH y
      remanente 1 ETH, conservando su seq (RN-2): sigue al frente de su nivel
    """
    precio = 2_230_000_000
    requerir_sin_asks_cruzables(api, precio)
    requerir_sin_bids_cruzables(api, precio)
    fondear(usuario_b, rpc, eth_wei=3 * ETH)          # maker + segunda ask
    fondear(usuario, rpc, usdc_min=4_600_000_000)     # dos takers de 1 ETH
    try:
        # Dado: fill parcial de 1 ETH sobre el maker, y una segunda ask posterior
        # en el mismo nivel (para poder observar que el maker conserva su seq)
        maker = colocar_limit(usuario_b, "SELL", precio, 2 * ETH, esperado="OPEN")
        colocar_limit(usuario, "BUY", precio, ETH, esperado="FILLED")
        segunda = colocar_limit(usuario_b, "SELL", precio, ETH, esperado="OPEN")

        # Cuando
        reiniciar_sut(api)
        relogin(usuario)
        relogin(usuario_b)

        # Entonces: remanente y estado reconstruidos exactos (RN-2)
        estado = orden_actual(usuario_b, maker["orderId"])
        assert estado["status"] == "PARTIALLY_FILLED"
        assert estado["filledWei"] == a_str(ETH)
        assert assert_monto(estado["quantityWei"]) - assert_monto(estado["filledWei"]) == ETH
        assert nivel(libro(api), "asks", precio) == 2 * ETH  # 1 (maker) + 1 (segunda)

        # Y: conservó su seq — el próximo taker consume el remanente del maker
        # ANTES que la segunda ask del nivel (prioridad (precio, seq), RN-2)
        colocar_limit(usuario, "BUY", precio, ETH, esperado="FILLED")
        assert orden_actual(usuario_b, maker["orderId"])["status"] == "FILLED"
        assert orden_actual(usuario_b, segunda["orderId"])["status"] == "OPEN"
    finally:
        cancelar_abiertas(usuario, usuario_b)


@pytest.mark.at("AT-03-07-03")
def test_balances_y_respaldo_consistentes_tras_recuperar(api, usuario, rpc):
    """HU-03-07 Escenario 3: Balances y respaldo consistentes tras recuperar.

    - Dado un estado con varias órdenes abiertas y sus fondos bloqueados
    - Cuando se reinicia y se recomputan los balances desde el ledger (épica 02)
    - Entonces disponible/bloqueado reproducen exactamente los previos (RN-6)
    - Y por cuenta/activo, la suma de respaldos de órdenes abiertas == bloqueado
      atribuible a órdenes (RN-5, INV-7)
    """
    precio_bid, precio_ask = 2_235_000_000, 2_236_000_000
    requerir_sin_asks_cruzables(api, precio_bid)
    requerir_sin_bids_cruzables(api, precio_ask)
    fondear(usuario, rpc, eth_wei=ETH, usdc_min=2_300_000_000)
    try:
        # Dado: dos órdenes abiertas (lados sin solapar) con fondos bloqueados
        colocar_limit(usuario, "BUY", precio_bid, ETH, esperado="OPEN")
        colocar_limit(usuario, "SELL", precio_ask, 7 * ETH // 10, esperado="OPEN")
        antes = snapshot_balances(usuario)

        # Cuando
        reiniciar_sut(api)
        relogin(usuario)

        # Entonces: balances idénticos a los previos (RN-6, INV-8)
        assert snapshot_balances(usuario) == antes

        # Y: bloqueado == respaldo exacto de las órdenes abiertas (RN-5, INV-7):
        # BUY ⇒ floor(remaining × price / 10^18) USDC-min; SELL ⇒ remaining wei
        balances = balances_por_activo(usuario)
        assert assert_monto(balances["USDC"]["locked"]) == quote_min(ETH, precio_bid)
        assert assert_monto(balances["ETH"]["locked"]) == 7 * ETH // 10
    finally:
        cancelar_abiertas(usuario)


@pytest.mark.at("AT-03-07-05")
def test_continuidad_de_sequence_y_trade_id(api, usuario, usuario_b, rpc):
    """HU-03-07 Escenario 5 (borde): Continuidad de sequence y tradeId.

    - Dado que antes del reinicio el último sequence del libro fue S y el último
      tradeId fue T
    - Cuando tras el reinicio se produce un nuevo evento
    - Entonces el nuevo evento usa sequence = S + 1 (contiguo a través del
      reinicio, RN-8) y un tradeId nuevo distinto de T, sin reutilizar valores

    Superficies: la `sequence` del libro es la numeración global que expone
    `GET /market/orderbook` (HU-09-03 RN-5); el número de trade viaja en el
    `tradeId` ("T-" + contador, HU-03-05 RN-2). El `seq` de prioridad es interno
    (RT-2); su continuidad se observa por la prioridad preservada (AT-03-07-02).
    """
    precio = 2_240_000_000
    requerir_sin_asks_cruzables(api, precio)
    requerir_sin_bids_cruzables(api, precio - 1_000_000)
    fondear(usuario_b, rpc, eth_wei=ETH)              # maker
    fondear(usuario, rpc, usdc_min=3_500_000_000)     # 2 takers de 0.5 + pasiva de 0.5
    try:
        # Dado: un fill previo (fija el último tradeId T) y el sequence S del libro
        colocar_limit(usuario_b, "SELL", precio, ETH, esperado="OPEN")
        colocar_limit(usuario, "BUY", precio, ETH // 2, esperado="FILLED")
        numero_t = numero_de_trade(ultimo_trade_id(api))
        secuencia_s = libro(api)["sequence"]
        assert isinstance(secuencia_s, int)

        # Cuando
        reiniciar_sut(api)
        relogin(usuario)
        relogin(usuario_b)

        # Entonces: el sequence retoma desde S (sin hueco ni reinicio del contador)
        assert libro(api)["sequence"] == secuencia_s

        # el primer evento del libro tras el reinicio usa S + 1 (RN-8)
        colocar_limit(usuario, "BUY", precio - 1_000_000, ETH // 2, esperado="OPEN")
        assert libro(api)["sequence"] == secuencia_s + 1

        # y el próximo trade usa un tradeId nuevo, el siguiente del contador
        # (contiguo bajo operación normal, HU-05-03 / README RT-2)
        colocar_limit(usuario, "BUY", precio, ETH // 2, esperado="FILLED")
        nuevo = numero_de_trade(ultimo_trade_id(api))
        assert nuevo == numero_t + 1
    finally:
        cancelar_abiertas(usuario, usuario_b)


@pytest.mark.at("AT-03-07-06")
def test_reinicio_repetido_produce_el_mismo_estado(api, usuario, usuario_b, rpc):
    """HU-03-07 Escenario 6 (idempotencia): Reinicio repetido produce el mismo estado.

    - Dado un estado persistido P (órdenes abiertas + un fill parcial aplicado)
    - Cuando se ejecuta la recuperación dos veces seguidas
    - Entonces el estado reconstruido es idéntico ambas veces: mismas órdenes,
      misma prioridad, mismos balances; sin duplicados ni fills reaplicados
      (RN-9, RN-12)
    """
    precio_bid, precio_ask = 2_245_000_000, 2_246_000_000
    requerir_sin_asks_cruzables(api, precio_bid)
    requerir_sin_bids_cruzables(api, precio_ask)
    fondear(usuario_b, rpc, eth_wei=ETH, usdc_min=2_300_000_000)
    fondear(usuario, rpc, eth_wei=ETH)
    try:
        # Dado: estado P con una orden abierta por lado y un fill parcial
        bid = colocar_limit(usuario_b, "BUY", precio_bid, ETH, esperado="OPEN")
        ask = colocar_limit(usuario_b, "SELL", precio_ask, ETH, esperado="OPEN")
        colocar_limit(usuario, "SELL", precio_bid, 4 * ETH // 10, esperado="FILLED")

        def estado():
            lib = libro(api)
            return {
                "libro": (lib["bids"], lib["asks"], lib["sequence"]),
                "bid": orden_actual(usuario_b, bid["orderId"]),
                "ask": orden_actual(usuario_b, ask["orderId"]),
                "balances_maker": snapshot_balances(usuario_b),
                "balances_taker": snapshot_balances(usuario),
            }

        previo = estado()

        # Cuando: reinicio sobre reinicio
        reiniciar_sut(api)
        relogin(usuario)
        relogin(usuario_b)
        primero = estado()

        reiniciar_sut(api)
        relogin(usuario)
        relogin(usuario_b)
        segundo = estado()

        # Entonces: idéntico ambas veces e igual al estado previo (RN-9, RN-12):
        # sin órdenes duplicadas, sin fills reaplicados, sin balances alterados
        assert primero == previo
        assert segundo == previo
    finally:
        cancelar_abiertas(usuario, usuario_b)


@pytest.mark.at("AT-03-07-07")
def test_no_se_reemite_un_trade_ya_persistido(api, usuario, usuario_b, rpc):
    """HU-03-07 Escenario 7 (integridad): No se re-emite un trade ya persistido.

    - Dado un trade con tradeId = X persistido y reflejado en el libro antes del
      reinicio
    - Cuando el sistema se recupera
    - Entonces X no se vuelve a emitir como evento nuevo y su efecto ya está en
      el libro recuperado (RN-10, HU-03-05 RN-9)
    """
    precio = 2_250_000_000
    requerir_sin_asks_cruzables(api, precio)
    requerir_sin_bids_cruzables(api, precio)
    fondear(usuario_b, rpc, eth_wei=ETH)
    fondear(usuario, rpc, usdc_min=2_300_000_000)
    try:
        # Dado: un fill completo, ya reflejado en el libro (nivel consumido)
        maker = colocar_limit(usuario_b, "SELL", precio, ETH, esperado="OPEN")
        taker = colocar_limit(usuario, "BUY", precio, ETH, esperado="FILLED")
        trade_x = trades_propios(usuario, order_id=taker["orderId"])[0]["tradeId"]

        # Cuando
        reiniciar_sut(api)
        relogin(usuario)
        relogin(usuario_b)

        # Entonces: un suscriptor nuevo al canal trades NO recibe X como evento
        with abrir_ws() as ws:
            respuesta = ws.suscribir("trades")
            assert respuesta.get("type") == "subscribed", respuesta
            ws.no_debe_llegar(
                lambda m: m.get("type") == "trade" and m.get("tradeId") == trade_x,
                ventana=3.0,
            )

        # Y: X figura exactamente una vez en el historial público (sin duplicar)
        resp = api.get("/market/trades", params={"limit": 200})
        assert resp.status_code == 200, resp.text
        repeticiones = [t for t in resp.json()["items"] if t["tradeId"] == trade_x]
        assert len(repeticiones) == 1, repeticiones

        # Y: su efecto ya está en el libro recuperado (maker consumido, nivel vacío)
        assert orden_actual(usuario_b, maker["orderId"])["status"] == "FILLED"
        assert nivel(libro(api), "asks", precio) == 0
    finally:
        cancelar_abiertas(usuario, usuario_b)


@pytest.mark.at("AT-03-07-08")
def test_persistencia_sin_floats(api, usuario, rpc):
    """HU-03-07 Escenario 8 (borde): Persistencia sin floats.

    - Dado el estado persistido del orderbook y del ledger
    - Cuando se inspeccionan los montos almacenados
    - Entonces todos son enteros de unidad mínima, nunca floats binarios (RN-11)

    Verificación black-box (la inspección directa del almacenamiento es
    white-box): se persiste una orden con cantidad y precio que **no** son
    representables exactamente en IEEE-754 doble (mantisa impar > 2^53). Si la
    implementación pasara esos montos por un float en la persistencia, el valor
    releído tras el reinicio cambiaría; se exige igualdad exacta.
    """
    # 9876543 lots: 9876543×5^14 es impar y > 2^53 ⇒ no representable en float64
    cantidad = 9_876_543 * LOT_SIZE
    # (14400000000000001)×10^4: parte impar > 2^53 ⇒ no representable en float64
    precio = 14_400_000_000_000_001 * 10_000
    # guardas del propio test: los valores elegidos efectivamente se corrompen
    # al pasar por un double (si no, el test no probaría nada)
    assert int(float(cantidad)) != cantidad
    assert int(float(precio)) != precio
    assert cantidad % LOT_SIZE == 0 and precio % 10_000 == 0  # válidos para el par

    requerir_sin_bids_cruzables(api, precio)
    fondeo = 9_880_000 * LOT_SIZE  # 988 ETH
    fondear(usuario, rpc, eth_wei=fondeo)
    try:
        # Dado: la orden persistida con montos hostiles a float
        orden = colocar_limit(usuario, "SELL", precio, cantidad, esperado="OPEN")

        # Cuando
        reiniciar_sut(api)
        relogin(usuario)

        # Entonces: los montos releídos son EXACTAMENTE los persistidos (RN-11)
        estado = orden_actual(usuario, orden["orderId"])
        assert estado["quantityWei"] == a_str(cantidad)
        assert estado["priceMin"] == a_str(precio)
        assert nivel(libro(api), "asks", precio) == cantidad
        balances = balances_por_activo(usuario)
        assert assert_monto(balances["ETH"]["locked"]) == cantidad
        assert assert_monto(balances["ETH"]["available"]) == fondeo - cantidad
    finally:
        cancelar_abiertas(usuario)
