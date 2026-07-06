"""Épica 03 / HU-03-05 — Emisión de eventos de ejecución: tests black-box.

Los eventos lógicos del motor (`trade`, `order-update`, `book-update`) se
observan por su transporte de la épica 09:

- `trade` → canal WS público `trades` (tradeId, priceMin, quantityWei, takerSide,
  sequence) + `GET /market/trades` + `GET /trades` (pata propia con
  `quoteAmountMin`, `role`, `orderId`);
- `order-update` → canal WS privado `orders` (status, filledWei, sequence) y el
  objeto orden REST;
- `book-update` → deltas del canal WS `orderbook` (nuevo total por nivel).

No expuestos por el transporte (se verifican por su efecto): el orden interno de
emisión trade→maker→taker dentro de un cruce (RN-6, conexiones independientes),
los campos `isNewLevel`/`isLevelEmpty` (RN-12; equivalen a nivel nuevo/total "0"
en el delta) y el campo `reason` (RN-5; HU-09-04 RN-4 no lo transporta).
AT-03-05-08 (order-update REJECTED) se declara no automatizable: HU-09-04 RN-5
excluye explícitamente los rechazos del canal privado.
"""

import random

import pytest

from helpers.cuentas import crear_usuario
from helpers.montos import LOT_SIZE, WEI_POR_ETH, a_str, assert_monto, es_monto_valido, quote_min

from tests.comunes_ep03 import (
    abrir_ws,
    abrir_ws_privado,
    assert_secuencia_contigua,
    cancelar_abiertas,
    colocar_limit,
    colocar_market,
    cuerpo_market,
    drenar,
    fondear,
    fondear_lote,
    libro,
    nivel,
    orden_actual,
    post_orden_reintentando_429,
    requerir_lado_vacio,
    requerir_sin_asks_cruzables,
    requerir_sin_bids_cruzables,
    suscribir_publico,
    trades_propios,
)

ETH = WEI_POR_ETH


def _bombear(ws, mensajes: list) -> None:
    """Lee lo pendiente del socket sin bloquear (responde pings del heartbeat).

    Para loops largos (AT-03-05-06): sin esto, los `ping` del servidor quedarían
    sin `pong` durante el loop y el SUT cerraría la conexión (HU-09-03 RN-14).
    """
    while True:
        try:
            mensaje = ws.recibir(timeout=0.05)
        except TimeoutError:
            return
        if mensaje.get("type") == "ping":
            ws.enviar({"type": "pong"})
            continue
        mensajes.append(mensaje)


@pytest.mark.at("AT-03-05-01")
def test_fill_total_emite_un_trade_y_dos_order_updates(api, usuario, usuario_b, rpc):
    """HU-03-05 Escenario 1: Un fill total emite un trade y dos order-updates.

    - Dado un maker SELL 1 ETH @ 2150.00 (U2) y un taker BUY 1 ETH @ 2150.00 (U1)
    - Cuando se ejecuta el cruce
    - Entonces se emite un trade con priceMin/quantityWei/quoteAmountMin exactos,
      lados opuestos y referencias correctas a maker y taker (RN-2, RN-4)
    - Y se emiten los order-update de maker y taker, ambos FILLED con remanente 0
      (RN-5)

    El orden de emisión trade → maker → taker (RN-6) es interno al motor: las
    conexiones WS de cada parte son independientes y no ordenables entre sí; se
    verifica el contenido completo de los tres eventos.
    """
    precio = 2_150_000_000
    requerir_sin_asks_cruzables(api, precio)
    requerir_sin_bids_cruzables(api, precio)
    fondear(usuario_b, rpc, eth_wei=ETH)
    fondear(usuario, rpc, usdc_min=2_200_000_000)
    ws_pub = abrir_ws()
    ws_maker = abrir_ws_privado(usuario_b, "orders")
    ws_taker = abrir_ws_privado(usuario, "orders")
    suscribir_publico(ws_pub, "trades")
    try:
        # Dado
        maker = colocar_limit(usuario_b, "SELL", precio, ETH, esperado="OPEN")

        # Cuando
        taker = colocar_limit(usuario, "BUY", precio, ETH, esperado="FILLED")

        # Entonces: el trade con los campos del cruce (RN-2, RN-3)
        trade = ws_pub.recibir_hasta(lambda m: m.get("type") == "trade")
        assert trade["priceMin"] == a_str(precio)
        assert trade["quantityWei"] == a_str(ETH)
        assert trade["takerSide"] == "BUY"  # ⇒ makerSide = SELL (opuestos, RN-4)

        # referencias maker/taker por la pata propia de cada parte (mismo tradeId)
        fill_taker = trades_propios(usuario, order_id=taker["orderId"])[0]
        fill_maker = trades_propios(usuario_b, order_id=maker["orderId"])[0]
        assert fill_taker["tradeId"] == fill_maker["tradeId"] == trade["tradeId"]
        assert fill_taker["role"] == "TAKER" and fill_taker["side"] == "BUY"
        assert fill_maker["role"] == "MAKER" and fill_maker["side"] == "SELL"
        # mismo quote_min para ambas patas (RN-2, RN-10)
        assert (
            assert_monto(fill_taker["quoteAmountMin"])
            == assert_monto(fill_maker["quoteAmountMin"])
            == quote_min(ETH, precio)
        )

        # Y: order-update de cada parte con status FILLED y remanente 0 (RN-5)
        evento_maker = ws_maker.recibir_hasta(
            lambda m: m.get("type") == "order"
            and m.get("orderId") == maker["orderId"]
            and m.get("status") == "FILLED"
        )
        assert evento_maker["filledWei"] == a_str(ETH)
        evento_taker = ws_taker.recibir_hasta(
            lambda m: m.get("type") == "order"
            and m.get("orderId") == taker["orderId"]
            and m.get("status") == "FILLED"
        )
        assert evento_taker["filledWei"] == a_str(ETH)
    finally:
        ws_pub.cerrar()
        ws_maker.cerrar()
        ws_taker.cerrar()
        cancelar_abiertas(usuario, usuario_b)


@pytest.mark.at("AT-03-05-02")
def test_taker_contra_dos_makers_emite_dos_trades(api, usuario, usuario_b, rpc):
    """HU-03-05 Escenario 2: Taker contra dos makers emite dos trades.

    - Dado asks A1 SELL 0.5 @ 2155.00 (1º) y A2 SELL 0.5 @ 2155.50 (2º)
    - Cuando ingresa BUY 1 ETH @ 2156.00
    - Entonces se emiten dos trade (RN-1), en orden de ejecución, con
      sequence(T1) < sequence(T2) contiguos en el canal (RN-7)
    - Y los order-update del taker muestran cumulativeFilledWei creciente:
      0.5 ETH tras T1 y 1 ETH (FILLED) tras T2 (RN-5)
    """
    p1, p2, limite = 2_155_000_000, 2_155_500_000, 2_156_000_000
    requerir_sin_asks_cruzables(api, limite)
    requerir_sin_bids_cruzables(api, p1)
    fondear(usuario_b, rpc, eth_wei=ETH)
    fondear(usuario, rpc, usdc_min=2_200_000_000)
    ws_pub = abrir_ws()
    ws_taker = abrir_ws_privado(usuario, "orders")
    suscribir_publico(ws_pub, "trades")
    try:
        # Dado
        colocar_limit(usuario_b, "SELL", p1, ETH // 2, esperado="OPEN")
        colocar_limit(usuario_b, "SELL", p2, ETH // 2, esperado="OPEN")

        # Cuando
        taker = colocar_limit(usuario, "BUY", limite, ETH, esperado="FILLED")

        # Entonces: dos trades en orden de ejecución con sequence contigua (RN-1, RN-7)
        t1 = ws_pub.recibir_hasta(lambda m: m.get("type") == "trade")
        t2 = ws_pub.recibir_hasta(lambda m: m.get("type") == "trade")
        assert (t1["priceMin"], t1["quantityWei"]) == (a_str(p1), a_str(ETH // 2))
        assert (t2["priceMin"], t2["quantityWei"]) == (a_str(p2), a_str(ETH // 2))
        assert t1["tradeId"] != t2["tradeId"]
        assert isinstance(t1["sequence"], int) and isinstance(t2["sequence"], int)
        assert t2["sequence"] == t1["sequence"] + 1  # creciente y contigua en el canal

        # quoteAmountMin por fill (pata propia): floor por fill, sin promediar (RN-2)
        fills = trades_propios(usuario, order_id=taker["orderId"])
        assert [assert_monto(f["quoteAmountMin"]) for f in fills] == [
            quote_min(ETH // 2, p1),
            quote_min(ETH // 2, p2),
        ]

        # Y: order-updates del taker con acumulado creciente (RN-5)
        parcial = ws_taker.recibir_hasta(
            lambda m: m.get("type") == "order"
            and m.get("orderId") == taker["orderId"]
            and m.get("status") == "PARTIALLY_FILLED"
        )
        assert parcial["filledWei"] == a_str(ETH // 2)
        total = ws_taker.recibir_hasta(
            lambda m: m.get("type") == "order"
            and m.get("orderId") == taker["orderId"]
            and m.get("status") == "FILLED"
        )
        assert total["filledWei"] == a_str(ETH)
        assert total["sequence"] > parcial["sequence"]
    finally:
        ws_pub.cerrar()
        ws_taker.cerrar()
        cancelar_abiertas(usuario, usuario_b)


@pytest.mark.at("AT-03-05-03")
def test_fill_parcial_order_update_con_remanente(api, usuario, usuario_b, rpc):
    """HU-03-05 Escenario 3: Fill parcial — order-update con remanente.

    - Dado un maker SELL 2 ETH @ 2160.00 y un taker BUY 1 ETH @ 2160.00
    - Cuando se ejecuta el cruce
    - Entonces el order-update del maker reporta PARTIALLY_FILLED con acumulado
      1 ETH y remanente 1 ETH; el del taker, FILLED con remanente 0 (RN-5)
    """
    precio = 2_160_000_000
    requerir_sin_asks_cruzables(api, precio)
    requerir_sin_bids_cruzables(api, precio)
    fondear(usuario_b, rpc, eth_wei=2 * ETH)
    fondear(usuario, rpc, usdc_min=2_200_000_000)
    ws_maker = abrir_ws_privado(usuario_b, "orders")
    try:
        # Dado
        maker = colocar_limit(usuario_b, "SELL", precio, 2 * ETH, esperado="OPEN")

        # Cuando
        taker = colocar_limit(usuario, "BUY", precio, ETH, esperado="FILLED")

        # Entonces: evento del maker con acumulado y remanente exactos (RN-5)
        evento = ws_maker.recibir_hasta(
            lambda m: m.get("type") == "order"
            and m.get("orderId") == maker["orderId"]
            and m.get("status") == "PARTIALLY_FILLED"
        )
        assert evento["filledWei"] == a_str(ETH)
        assert assert_monto(evento["quantityWei"]) - assert_monto(evento["filledWei"]) == ETH

        # y el taker cerró FILLED con remanente 0 (respuesta síncrona del alta)
        assert taker["status"] == "FILLED"
        assert assert_monto(taker["quantityWei"]) - assert_monto(taker["filledWei"]) == 0
    finally:
        ws_maker.cerrar()
        cancelar_abiertas(usuario, usuario_b)


@pytest.mark.at("AT-03-05-04")
def test_posar_pasiva_no_emite_trade_si_book_update(api, usuario, rpc):
    """HU-03-05 Escenario 4 (borde): Posar pasiva no emite trade, sí un book-update.

    - Dado un libro sin nivel bids @ 2165.00 (y sin asks cruzables)
    - Cuando ingresa BUY 1 ETH @ 2165.00 (no cruza, se posa — HU-03-02)
    - Entonces no se emite ningún trade (RN-11)
    - Y se emite exactamente un book-update para el nivel con su profundidad
      (RN-12; el delta trae el nuevo total; "nivel nuevo" ≡ no estaba en el
      snapshot — el transporte de la épica 09 no expone isNewLevel)
    - Y agregar una segunda orden al mismo nivel emite un delta con
      profundidad previa + nueva
    """
    precio = 2_165_000_000
    requerir_sin_asks_cruzables(api, precio)
    requerir_sin_bids_cruzables(api, precio)
    fondear(usuario, rpc, usdc_min=4_400_000_000)
    ws_pub = abrir_ws()
    snapshot = suscribir_publico(ws_pub, "orderbook")
    suscribir_publico(ws_pub, "trades")
    assert nivel(snapshot, "bids", precio) == 0  # el nivel no existe aún
    secuencia_base = snapshot["sequence"]
    try:
        # Cuando: primera pasiva (crea el nivel)
        colocar_limit(usuario, "BUY", precio, ETH, esperado="OPEN")
        mensajes = drenar(ws_pub)
        updates = [m for m in mensajes if m.get("channel") == "orderbook" and m.get("type") == "update"]
        trades = [m for m in mensajes if m.get("channel") == "trades"]

        # Entonces: ningún trade (RN-11) y exactamente un book-update (RN-12)
        assert trades == [], trades
        assert len(updates) == 1, updates
        assert updates[0]["sequence"] == secuencia_base + 1
        assert nivel(updates[0], "bids", precio) == ETH  # profundidad total del nivel

        # Y: la segunda pasiva al mismo nivel reporta el nuevo total agregado
        colocar_limit(usuario, "BUY", precio, ETH // 2, esperado="OPEN")
        mensajes = drenar(ws_pub)
        updates = [m for m in mensajes if m.get("channel") == "orderbook" and m.get("type") == "update"]
        trades = [m for m in mensajes if m.get("channel") == "trades"]
        assert trades == [] and len(updates) == 1
        assert nivel(updates[0], "bids", precio) == ETH + ETH // 2
    finally:
        ws_pub.cerrar()
        cancelar_abiertas(usuario)


@pytest.mark.at("AT-03-05-05")
def test_serializacion_entera_de_todos_los_montos(api, usuario, usuario_b, rpc):
    """HU-03-05 Escenario 5 (borde): Serialización entera de todos los montos.

    - Dado cualquier trade emitido
    - Cuando se inspeccionan sus campos monetarios en todas las superficies
      (evento WS, GET /market/trades, GET /trades)
    - Entonces todos son strings ^(0|[1-9][0-9]*)$: sin floats, sin notación
      científica, sin número JSON, sin ceros a la izquierda (RN-3)
    """
    precio = 2_170_000_000
    requerir_sin_asks_cruzables(api, precio)
    requerir_sin_bids_cruzables(api, precio)
    fondear(usuario_b, rpc, eth_wei=ETH)
    fondear(usuario, rpc, usdc_min=2_200_000_000)
    ws_pub = abrir_ws()
    suscribir_publico(ws_pub, "trades")
    try:
        # Dado: un fill
        colocar_limit(usuario_b, "SELL", precio, ETH, esperado="OPEN")
        taker = colocar_limit(usuario, "BUY", precio, ETH, esperado="FILLED")

        # Cuando / Entonces: evento WS del canal trades
        trade_ws = ws_pub.recibir_hasta(lambda m: m.get("type") == "trade")
        assert es_monto_valido(trade_ws["priceMin"]), trade_ws
        assert es_monto_valido(trade_ws["quantityWei"]), trade_ws
        assert isinstance(trade_ws["sequence"], int)  # conteo: entero JSON (convenciones §5)
        assert isinstance(trade_ws["timestamp"], str)

        # trades públicos REST
        resp = api.get("/market/trades", params={"limit": 1})
        assert resp.status_code == 200, resp.text
        item = resp.json()["items"][0]
        assert es_monto_valido(item["priceMin"]) and es_monto_valido(item["quantityWei"]), item

        # pata propia REST (incluye quoteAmountMin y fees)
        fill = trades_propios(usuario, order_id=taker["orderId"])[0]
        for campo in ("priceMin", "quantityWei", "quoteAmountMin", "feeAmount", "netReceived", "paid"):
            assert es_monto_valido(fill[campo]), (campo, fill[campo])
    finally:
        ws_pub.cerrar()
        cancelar_abiertas(usuario, usuario_b)


@pytest.mark.at("AT-03-05-06")
def test_unicidad_de_trade_id_y_sequence(api, rpc):
    """HU-03-05 Escenario 6 (integridad): Unicidad de tradeId y sequence.

    - Dado el log de eventos al procesar ≥ 100 órdenes mixtas LIMIT/MARKET
    - Cuando se inspecciona ese log (canales WS `trades` y `orderbook`)
    - Entonces no hay dos trades con el mismo tradeId y las sequence de cada
      canal son estrictamente crecientes y contiguas, sin huecos ni
      repeticiones (RN-7, RN-9)

    La `sequence` global interna del motor se transporta por canal (RG-API-7);
    la contigüidad se verifica por canal, nunca entre canales.
    """
    rng = random.Random(20260706)
    vendedores = [crear_usuario(api, "ep03-ev-v") for _ in range(2)]
    compradores = [crear_usuario(api, "ep03-ev-c") for _ in range(2)]
    fondear_lote(vendedores, rpc, eth_wei=1 * ETH)
    fondear_lote(compradores, rpc, usdc_min=2_000_000_000)
    ws_pub = abrir_ws()
    snapshot = suscribir_publico(ws_pub, "orderbook")
    suscribir_publico(ws_pub, "trades")
    mensajes: list = []
    try:
        # Cuando: 100 órdenes mixtas en una banda propia [3200, 3202]
        for i in range(100):
            vendedor = i % 2 == 0
            cuenta = (vendedores if vendedor else compradores)[(i // 2) % 2]
            side = "SELL" if vendedor else "BUY"
            cantidad = rng.randrange(40, 101) * LOT_SIZE
            if i % 10 == 9:
                resp = post_orden_reintentando_429(cuenta, cuerpo_market(side, q_wei=cantidad))
                assert resp.status_code == 201 or (
                    resp.status_code == 422
                    and resp.json()["error"]["code"] == "MARKET_NO_LIQUIDITY"
                ), f"op {i}: {resp.text[:200]}"
            else:
                precio = 3_200_000_000 + rng.randrange(0, 201) * 10_000
                resp = post_orden_reintentando_429(
                    cuenta,
                    {
                        "clientOrderId": f"ep03-ev-{i}",
                        "symbol": "ETH-USDC",
                        "side": side,
                        "type": "LIMIT",
                        "priceMin": a_str(precio),
                        "quantityWei": a_str(cantidad),
                    },
                )
                assert resp.status_code == 201, f"op {i}: {resp.text[:200]}"
            _bombear(ws_pub, mensajes)  # vaciar el buffer y responder pings (RN-14)

        # Entonces: recolectar el log de eventos emitidos
        mensajes += drenar(ws_pub, ventana=3.0)
        trades = [m for m in mensajes if m.get("channel") == "trades" and m.get("type") == "trade"]
        assert trades, "las 100 órdenes mixtas no produjeron ningún trade"

        # unicidad de tradeId (RN-7, RN-9: el motor nunca re-emite un tradeId)
        ids = [t["tradeId"] for t in trades]
        assert len(ids) == len(set(ids)), "tradeId repetido en el stream"

        # sequence por canal: estrictamente creciente y contigua (RN-7)
        assert_secuencia_contigua(trades, "trades")
        eventos_libro = [snapshot] + [
            m for m in mensajes if m.get("channel") == "orderbook" and m.get("type") == "update"
        ]
        assert_secuencia_contigua(eventos_libro, "orderbook")
    finally:
        ws_pub.cerrar()
        cancelar_abiertas(*(vendedores + compradores))


@pytest.mark.at("AT-03-05-07")
def test_estado_del_libro_consistente_con_los_eventos(api, usuario, usuario_b, rpc):
    """HU-03-05 Escenario 7 (integridad): Estado del libro consistente con los eventos.

    - Dado un cruce que ejecuta q_fill contra un maker
    - Cuando se emite su trade y se aplican los order-update
    - Entonces el remanente del maker en el libro es exactamente
      remanente_previo − q_fill, y al llegar a 0 el maker se retira (RN-8, INV-7)
    - Y no existe trade sin efecto en el libro ni cambio de libro sin su evento
    """
    precio = 2_175_000_000
    requerir_sin_asks_cruzables(api, precio)
    requerir_sin_bids_cruzables(api, precio)
    fondear(usuario_b, rpc, eth_wei=2 * ETH)
    fondear(usuario, rpc, usdc_min=4_400_000_000)
    ws_pub = abrir_ws()
    try:
        # Dado: maker con 2 ETH de profundidad, y la suscripción al libro
        maker = colocar_limit(usuario_b, "SELL", precio, 2 * ETH, esperado="OPEN")
        snapshot = suscribir_publico(ws_pub, "orderbook")
        suscribir_publico(ws_pub, "trades")
        assert nivel(snapshot, "asks", precio) == 2 * ETH

        # Cuando: fill parcial de 0.8 ETH
        q_fill = 8 * ETH // 10
        colocar_limit(usuario, "BUY", precio, q_fill, esperado="FILLED")

        mensajes = drenar(ws_pub)
        trades = [m for m in mensajes if m.get("channel") == "trades"]
        updates = [m for m in mensajes if m.get("channel") == "orderbook"]
        assert len(trades) == 1 and assert_monto(trades[0]["quantityWei"]) == q_fill
        # Entonces: el delta refleja exactamente remanente_previo − q_fill (RN-8)
        assert len(updates) == 1
        assert nivel(updates[0], "asks", precio) == 2 * ETH - q_fill
        # y el snapshot REST coincide con el evento (sin efecto sin evento)
        assert nivel(libro(api), "asks", precio) == 2 * ETH - q_fill
        assert orden_actual(usuario_b, maker["orderId"])["filledWei"] == a_str(q_fill)

        # Cuando: se consume el resto → el maker llega a 0 y se retira (INV-7)
        colocar_limit(usuario, "BUY", precio, 2 * ETH - q_fill, esperado="FILLED")
        mensajes = drenar(ws_pub)
        updates = [m for m in mensajes if m.get("channel") == "orderbook"]
        assert len(updates) == 1
        assert nivel(updates[0], "asks", precio) == 0  # nivel eliminado (delta "0")
        assert nivel(libro(api), "asks", precio) == 0
        assert orden_actual(usuario_b, maker["orderId"])["status"] == "FILLED"
    finally:
        ws_pub.cerrar()
        cancelar_abiertas(usuario, usuario_b)


@pytest.mark.at("AT-03-05-09")
def test_order_update_cancelled_tras_agotar_el_libro_en_market(api, usuario, usuario_b, rpc):
    """HU-03-05 Escenario 9 (borde): order-update CANCELLED tras agotar el libro en MARKET.

    - Dado asks con liquidez total 0.8 ETH (A1 0.5 @ 2180.00, A2 0.3 @ 2180.50)
    - Cuando ingresa MARKET BUY 1 ETH con presupuesto suficiente y el remanente
      se descarta (HU-03-04 AT-03-04-03)
    - Entonces, además de los trades de A1 y A2, se emite un order-update del
      taker con status CANCELLED y acumulado 0.8 ETH (RN-5, RN-13; el campo
      `reason = MARKET_EXHAUSTED` es del evento interno — HU-09-04 RN-4 no lo
      transporta por WS)
    """
    p1, p2 = 2_180_000_000, 2_180_500_000
    requerir_lado_vacio(api, "asks")
    fondear(usuario_b, rpc, eth_wei=ETH)
    fondear(usuario, rpc, usdc_min=1_800_000_000)
    ws_pub = abrir_ws()
    ws_taker = abrir_ws_privado(usuario, "orders")
    suscribir_publico(ws_pub, "trades")
    try:
        # Dado
        colocar_limit(usuario_b, "SELL", p1, ETH // 2, esperado="OPEN")
        colocar_limit(usuario_b, "SELL", p2, 3 * ETH // 10, esperado="OPEN")

        # Cuando
        taker = colocar_market(usuario, "BUY", q_wei=ETH, esperado="CANCELLED")

        # Entonces: los dos trades del barrido, en orden de prioridad
        t1 = ws_pub.recibir_hasta(lambda m: m.get("type") == "trade")
        t2 = ws_pub.recibir_hasta(lambda m: m.get("type") == "trade")
        assert (t1["priceMin"], t1["quantityWei"]) == (a_str(p1), a_str(ETH // 2))
        assert (t2["priceMin"], t2["quantityWei"]) == (a_str(p2), a_str(3 * ETH // 10))

        # Y: el order-update terminal del taker: CANCELLED con acumulado 0.8 ETH y
        # remanente descartado 0.2 ETH (quantityWei − filledWei) (RN-5)
        evento = ws_taker.recibir_hasta(
            lambda m: m.get("type") == "order"
            and m.get("orderId") == taker["orderId"]
            and m.get("status") == "CANCELLED"
        )
        assert evento["filledWei"] == a_str(8 * ETH // 10)
        assert assert_monto(evento["quantityWei"]) - assert_monto(evento["filledWei"]) == 2 * ETH // 10
    finally:
        ws_pub.cerrar()
        ws_taker.cerrar()
        cancelar_abiertas(usuario, usuario_b)
