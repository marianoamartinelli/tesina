"""Épica 09 — HU-09-03 (WebSocket de mercado, público): tests black-box.

Cubre AT-09-03-01..14, más AT-09-05-07 (envelope de error por WS, mismo flujo
que AT-09-03-09).

Contrato central: subscribe/subscribed, snapshot inicial + deltas con `sequence`
única y global del libro (la misma numeración que el snapshot REST, RN-5/RN-12),
stream de trades con secuencia propia (RN-13), heartbeat ping/pong (RN-14).
"""

import time

import pytest
from websockets.exceptions import ConnectionClosed

from comunes_ep09 import (
    aplicar_delta,
    assert_espejos_equivalentes,
    assert_secuencia_contigua,
    barrer_asks,
    cancelar_silencioso,
    cantidad_para_notional,
    colocar_ask_dominante,
    contiene_clave,
    crear_orden,
    drenar,
    es_entero_json,
    es_timestamp_utc,
    espejo_de_snapshot,
    fondear_eth,
    fondear_usdc,
    libro,
    niveles_bid_frescos,
    precio_bid_seguro,
    precio_dominante,
    tomar_con_buy,
)
from helpers.cuentas import crear_usuario
from helpers.errores import assert_error_ws
from helpers.montos import SIMBOLO, TICK_SIZE, a_int, a_str, es_monto_valido, quote_min
from helpers.ws import ConexionWs


def _snapshot_tras_subscribe(ws, depth: int | None = None) -> dict:
    """Suscribe a `orderbook` y devuelve el snapshot inicial (RN-2/RN-3)."""
    respuesta = ws.suscribir("orderbook", depth=depth)
    assert respuesta.get("type") == "subscribed", respuesta
    snapshot = ws.recibir_hasta(lambda m: m.get("type") == "snapshot")
    assert snapshot.get("channel") == "orderbook", snapshot
    return snapshot


@pytest.mark.at("AT-09-03-01")
def test_snapshot_inicial_del_orderbook_ordenado_y_serializado(api, ws, usuario, usuario_b, rpc):
    """HU-09-03 Escenario 1: Snapshot inicial del orderbook.

    - Dado un orderbook con órdenes en ambos lados
    - Cuando un cliente envía {type: subscribe, channel: orderbook, symbol: ETH-USDC}
    - Entonces recibe primero {type: subscribed} y luego un snapshot con bids/asks
      agregados por nivel, bids descendente, asks ascendente, y un sequence inicial
    - Y best_bid < best_ask (libro no cruzado, INV-7)
    - Y todos los priceMin/quantityWei son strings que matchean ^(0|[1-9][0-9]*)$
    """
    # Dado: liquidez en ambos lados construida por el test
    p_ask = precio_dominante(api)
    q_ask = cantidad_para_notional(p_ask)
    fondear_eth(usuario, rpc, q_ask)
    ask = crear_orden(usuario, "SELL", "LIMIT", price_min=p_ask, quantity_wei=q_ask)
    p_bid = precio_bid_seguro(api)
    q_bid = cantidad_para_notional(p_bid)
    fondear_usdc(usuario_b, rpc, quote_min(q_bid, p_bid) + 10_000_000)
    bid = crear_orden(usuario_b, "BUY", "LIMIT", price_min=p_bid, quantity_wei=q_bid)

    try:
        # Cuando (a mano, para verificar el ORDEN subscribed → snapshot)
        ws.enviar({"type": "subscribe", "channel": "orderbook", "symbol": SIMBOLO})
        m1 = ws.recibir_hasta(
            lambda m: m.get("type") in ("subscribed", "snapshot") or "error" in m
        )
        # Entonces: primero la confirmación...
        assert m1.get("type") == "subscribed", f"antes del snapshot debe llegar subscribed: {m1!r}"
        assert m1.get("channel") == "orderbook" and m1.get("symbol") == SIMBOLO, m1

        # ... y luego el snapshot
        m2 = ws.recibir_hasta(lambda m: True)
        assert m2.get("type") == "snapshot", m2
        assert m2.get("symbol") == SIMBOLO
        assert es_entero_json(m2.get("sequence")), m2

        bids, asks = m2["bids"], m2["asks"]
        assert bids and asks, "el Dado garantiza ambos lados"
        for nivel in bids + asks:
            precio, cantidad = nivel
            assert es_monto_valido(precio) and es_monto_valido(cantidad), nivel
        precios_bid = [a_int(p) for p, _ in bids]
        precios_ask = [a_int(p) for p, _ in asks]
        assert precios_bid == sorted(precios_bid, reverse=True), "bids no descendentes"
        assert precios_ask == sorted(precios_ask), "asks no ascendentes"
        # Y: libro no cruzado (INV-7)
        assert precios_bid[0] < precios_ask[0], "libro cruzado"
    finally:
        cancelar_silencioso(usuario, ask["orderId"])
        cancelar_silencioso(usuario_b, bid["orderId"])


@pytest.mark.at("AT-09-03-02")
def test_update_incremental_al_ingresar_orden_con_sequence_contigua(api, ws, usuario, rpc):
    """HU-09-03 Escenario 2: Actualización incremental al ingresar una orden.

    - Dado un cliente suscrito al orderbook que recibió el snapshot con sequence = s
    - Cuando ingresa una nueva orden limit que agrega profundidad a un nivel de bid
    - Entonces recibe un update con sequence = s+1 con ese nivel y su nuevo total
    - Y aplicar el delta sobre el snapshot reproduce el estado del libro (RN-12)
    """
    # Dado: suscripción con profundidad completa para poder espejar el libro
    snapshot = _snapshot_tras_subscribe(ws, depth=200)
    s = snapshot["sequence"]
    espejo = espejo_de_snapshot(snapshot)

    # Cuando: bid nuevo en un nivel fresco (no cruza: precio < mejor ask)
    (p,) = niveles_bid_frescos(espejo, precio_bid_seguro(api), 1)
    q = cantidad_para_notional(p)
    fondear_usdc(usuario, rpc, quote_min(q, p) + 10_000_000)
    orden = crear_orden(usuario, "BUY", "LIMIT", price_min=p, quantity_wei=q)

    try:
        # Entonces: update contiguo con el NUEVO TOTAL del nivel (RN-4/RN-5)
        update = ws.recibir_hasta(lambda m: m.get("type") == "update")
        assert update.get("channel") == "orderbook", update
        assert update["sequence"] == s + 1, (s, update)
        niveles = {a_int(pp): a_int(qq) for pp, qq in update.get("bids", [])}
        assert niveles.get(p) == q, update

        # Y: snapshot + delta == estado actual del libro por REST (mismo sequence)
        aplicar_delta(espejo, update)
        rest = libro(api, depth=200)
        assert rest["sequence"] == s + 1, rest["sequence"]
        assert_espejos_equivalentes(espejo, espejo_de_snapshot(rest), profundidad=200)
    finally:
        cancelar_silencioso(usuario, orden["orderId"])


@pytest.mark.at("AT-09-03-03")
def test_eliminacion_de_nivel_se_emite_con_quantity_cero(api, ws, usuario, rpc):
    """HU-09-03 Escenario 3 (borde): Eliminación de un nivel.

    - Dado un nivel de precio con una sola orden abierta
    - Cuando esa orden se cancela y el nivel queda sin profundidad
    - Entonces el cliente recibe un update con ese priceMin y quantityWei: "0"
    - Y el cliente elimina ese nivel de su copia local
    """
    # Dado: nivel fresco con una única orden propia
    snapshot = _snapshot_tras_subscribe(ws, depth=200)
    espejo = espejo_de_snapshot(snapshot)
    (p,) = niveles_bid_frescos(espejo, precio_bid_seguro(api), 1)
    q = cantidad_para_notional(p)
    fondear_usdc(usuario, rpc, quote_min(q, p) + 10_000_000)
    orden = crear_orden(usuario, "BUY", "LIMIT", price_min=p, quantity_wei=q)
    alta = ws.recibir_hasta(lambda m: m.get("type") == "update")
    aplicar_delta(espejo, alta)
    assert espejo["bids"].get(p) == q, alta

    # Cuando: se cancela la única orden del nivel
    resp = usuario.api.delete(f"/orders/{orden['orderId']}")
    assert resp.status_code == 200, resp.text

    # Entonces: update con quantityWei "0" para ese nivel (RN-4)
    update = ws.recibir_hasta(
        lambda m: m.get("type") == "update"
        and any(a_int(pp) == p for pp, _ in m.get("bids", []))
    )
    entrada = next(e for e in update["bids"] if a_int(e[0]) == p)
    assert entrada[1] == "0", update

    # Y: aplicar el delta elimina el nivel de la copia local
    aplicar_delta(espejo, update)
    assert p not in espejo["bids"]


@pytest.mark.at("AT-09-03-04")
def test_stream_de_trades_emite_el_fill_con_taker_side(api, ws, usuario, usuario_b, rpc):
    """HU-09-03 Escenario 4: Stream de trades.

    - Dado un cliente suscrito al canal trades
    - Cuando se produce un fill por cruce de una orden taker BUY contra un ask resting
    - Entonces recibe {type: trade, tradeId, priceMin, quantityWei, takerSide: BUY,
      timestamp, sequence} con montos como strings
    """
    # Dado: ask resting determinista (único ask del libro) y suscripción a trades
    barrer_asks(api, rpc)
    _, p, q = colocar_ask_dominante(usuario, api, rpc)
    respuesta = ws.suscribir("trades")
    assert respuesta.get("type") == "subscribed", respuesta

    # Cuando: taker BUY cruza el ask
    tomar_con_buy(usuario_b, rpc, p, q)

    # Entonces
    evento = ws.recibir_hasta(lambda m: m.get("type") == "trade")
    assert evento.get("channel") == "trades", evento
    assert evento.get("symbol") == SIMBOLO, evento
    assert evento.get("tradeId"), evento
    assert evento["priceMin"] == a_str(p) and evento["quantityWei"] == a_str(q), evento
    assert es_monto_valido(evento["priceMin"]) and es_monto_valido(evento["quantityWei"])
    assert evento["takerSide"] == "BUY", evento
    assert es_timestamp_utc(evento["timestamp"]), evento
    assert es_entero_json(evento["sequence"]), evento


@pytest.mark.at("AT-09-03-05")
def test_varios_cruces_emiten_un_trade_por_fill_en_orden_de_prioridad(api, ws, usuario, usuario_b, rpc):
    """HU-09-03 Escenario 5 (borde): Varios cruces en orden de prioridad.

    - Dado un orderbook con dos asks al mismo nivel (FIFO) y otro nivel peor
    - Cuando una orden taker BUY grande cruza ambos niveles
    - Entonces recibe un evento trade por cada cruce, en orden de prioridad
      precio-tiempo (INV-7), con sequence creciente y contigua
    """
    # Dado: nivel p1 con dos asks FIFO (cantidades distintas para distinguirlos)
    # y nivel p2 (peor) con un tercer ask
    barrer_asks(api, rpc)
    p1 = precio_dominante(api)
    p2 = p1 + 10 * TICK_SIZE
    q1 = cantidad_para_notional(p1)
    q2 = 2 * q1
    q3 = q1
    fondear_eth(usuario, rpc, q1 + q3)
    fondear_eth(usuario_b, rpc, q2)
    crear_orden(usuario, "SELL", "LIMIT", price_min=p1, quantity_wei=q1)      # 1º en FIFO
    crear_orden(usuario_b, "SELL", "LIMIT", price_min=p1, quantity_wei=q2)    # 2º en FIFO
    crear_orden(usuario, "SELL", "LIMIT", price_min=p2, quantity_wei=q3)      # nivel peor

    respuesta = ws.suscribir("trades")
    assert respuesta.get("type") == "subscribed", respuesta

    # Cuando: taker BUY que barre los dos niveles completos
    taker = crear_usuario(api, "at09-taker")
    tomar_con_buy(taker, rpc, p2, q1 + q2 + q3)

    # Entonces: un trade por cruce, en orden precio-tiempo
    e1 = ws.recibir_hasta(lambda m: m.get("type") == "trade")
    e2 = ws.recibir_hasta(lambda m: m.get("type") == "trade")
    e3 = ws.recibir_hasta(lambda m: m.get("type") == "trade")
    assert (a_int(e1["priceMin"]), a_int(e1["quantityWei"])) == (p1, q1), e1  # mejor precio, 1º FIFO
    assert (a_int(e2["priceMin"]), a_int(e2["quantityWei"])) == (p1, q2), e2  # mismo nivel, 2º FIFO
    assert (a_int(e3["priceMin"]), a_int(e3["quantityWei"])) == (p2, q3), e3  # nivel peor al final
    assert all(e["takerSide"] == "BUY" for e in (e1, e2, e3))

    # Y: sequence creciente y contigua dentro del canal trades
    assert_secuencia_contigua([e1, e2, e3], contexto="canal trades")


@pytest.mark.at("AT-09-03-06")
def test_secuencia_por_canal_y_resincronizacion_con_nuevo_snapshot(api, ws, usuario, usuario_b, rpc):
    """HU-09-03 Escenario 6 (error de sincronía): Detección de hueco de secuencia.

    - Dado un cliente que recibió hasta sequence = s en el canal orderbook
    - Cuando (ante un hueco) descarta su estado y se re-suscribe a ese canal
    - Entonces el servidor responde con un nuevo snapshot con sequence actualizada
    - Y un mensaje de otro canal (trades) con sequence distinta NO es un hueco:
      la secuencia es por canal (RN-13) — se verifica que cada canal mantiene su
      numeración contigua propia aun con mensajes intercalados

    Nota: la pérdida de mensajes no puede inyectarse black-box; se verifica el
    contrato del servidor que hace posible la recuperación (RG-API-7).
    """
    # Dado: suscripto a orderbook y a trades a la vez
    barrer_asks(api, rpc)
    snapshot = _snapshot_tras_subscribe(ws)
    respuesta = ws.suscribir("trades")
    assert respuesta.get("type") == "subscribed", respuesta

    # Cuando: actividad que genera mensajes en ambos canales (alta + fill)
    _, p, q = colocar_ask_dominante(usuario, api, rpc)
    tomar_con_buy(usuario_b, rpc, p, q)
    mensajes = drenar(ws, ventana=3.0)

    # Entonces: cada canal mantiene su secuencia contigua propia; los mensajes
    # intercalados del otro canal no rompen (ni "salvan") la numeración
    del_libro = [m for m in mensajes if m.get("channel") == "orderbook"]
    de_trades = [m for m in mensajes if m.get("channel") == "trades"]
    assert del_libro and de_trades, mensajes
    assert_secuencia_contigua([snapshot] + del_libro, contexto="canal orderbook")
    assert_secuencia_contigua(de_trades, contexto="canal trades")

    # Y: re-suscribirse produce un snapshot nuevo con la sequence vigente
    ultimo = ([snapshot] + del_libro)[-1]["sequence"]
    assert ws.desuscribir("orderbook").get("type") == "unsubscribed"
    snapshot2 = _snapshot_tras_subscribe(ws)
    assert snapshot2["sequence"] >= ultimo, (snapshot2["sequence"], ultimo)


@pytest.mark.at("AT-09-03-07")
def test_canal_publico_sin_token_y_sin_identidades(api, ws, usuario, usuario_b, rpc):
    """HU-09-03 Escenario 7: Canal público sin autenticación.

    - Dado un cliente sin token
    - Cuando se suscribe al canal público orderbook/trades
    - Entonces la suscripción es aceptada y recibe los datos de mercado
    - Y ningún mensaje del canal público contiene accountId ni orderId ni
      identidad de dueño de orden (RN-1)
    """
    # Dado / Cuando: la conexión `ws` no está autenticada
    barrer_asks(api, rpc)
    snapshot = _snapshot_tras_subscribe(ws)
    respuesta = ws.suscribir("trades")
    assert respuesta.get("type") == "subscribed", respuesta

    # ... con actividad de mercado real (alta + fill)
    _, p, q = colocar_ask_dominante(usuario, api, rpc)
    tomar_con_buy(usuario_b, rpc, p, q)

    # Entonces: llegan datos de mercado
    mensajes = drenar(ws, ventana=3.0)
    assert any(m.get("type") == "update" for m in mensajes), mensajes
    assert any(m.get("type") == "trade" for m in mensajes), mensajes

    # Y: nada identifica cuentas ni órdenes en ningún nivel del payload
    for m in [snapshot] + mensajes:
        assert not contiene_clave(m, {"accountId", "orderId", "clientOrderId", "email"}), m


@pytest.mark.at("AT-09-03-08")
def test_desuscripcion_detiene_los_eventos_del_canal(api, ws, usuario, usuario_b, rpc):
    """HU-09-03 Escenario 8: Desuscripción.

    - Dado un cliente suscrito a trades
    - Cuando envía {type: unsubscribe, channel: trades, symbol: ETH-USDC}
    - Entonces recibe {type: unsubscribed} y deja de recibir eventos trade
    """
    # Dado
    respuesta = ws.suscribir("trades")
    assert respuesta.get("type") == "subscribed", respuesta

    # Cuando
    respuesta = ws.desuscribir("trades")

    # Entonces: confirmación...
    assert respuesta.get("type") == "unsubscribed", respuesta
    assert respuesta.get("channel") == "trades", respuesta

    # ... y un fill posterior ya no llega por el socket
    barrer_asks(api, rpc)  # (genera trades: tampoco deben llegar)
    _, p, q = colocar_ask_dominante(usuario, api, rpc)
    tomar_con_buy(usuario_b, rpc, p, q)
    ws.no_debe_llegar(lambda m: m.get("type") == "trade", ventana=3.0)


@pytest.mark.at("AT-09-03-09", "AT-09-05-07")
def test_suscripcion_ws_invalida_recibe_error_por_el_socket(ws):
    """HU-09-03 Escenario 9 / HU-09-05 Escenario 7: Mensaje de suscripción inválido.

    - Dado una conexión WS abierta
    - Cuando envía subscribe con canal no soportado ("candles") o symbol inexistente
    - Entonces recibe { error: { code: "VALIDATION_ERROR", message, details? } } por
      el mismo socket, sin status HTTP (el code es lo determinante, HU-09-05 RN-7)
    - Y no se crea ninguna suscripción
    """
    # Cuando: canal no soportado
    respuesta = ws.suscribir("candles")
    # Entonces: envelope de error por el mismo socket (sin status HTTP)
    assert_error_ws(respuesta, "VALIDATION_ERROR")

    # Cuando: par inexistente (el par es único, ETH-USDC)
    respuesta = ws.suscribir("orderbook", symbol="BTC-USDC")
    assert_error_ws(respuesta, "VALIDATION_ERROR")

    # Y: no se creó suscripción (no llega snapshot/subscribed en una ventana corta)
    ws.no_debe_llegar(
        lambda m: m.get("type") in ("subscribed", "snapshot"), ventana=2.0
    )


@pytest.mark.at("AT-09-03-10")
def test_reconexion_produce_un_snapshot_completo_nuevo(ws):
    """HU-09-03 Escenario 10: Reconexión produce nuevo snapshot.

    - Dado un cliente que se desconecta y reconecta
    - Cuando vuelve a suscribirse al orderbook
    - Entonces recibe un nuevo snapshot completo con la sequence vigente, no un
      delta parcial
    """
    # Dado: una primera suscripción con su snapshot
    snapshot1 = _snapshot_tras_subscribe(ws)
    ws.cerrar()  # el cliente se desconecta

    # Cuando: reconecta y se re-suscribe
    with ConexionWs() as ws2:
        respuesta = ws2.suscribir("orderbook")
        assert respuesta.get("type") == "subscribed", respuesta

        # Entonces: lo primero que llega es un snapshot (nunca un update)
        m = ws2.recibir_hasta(lambda m: m.get("type") in ("snapshot", "update"))
        assert m["type"] == "snapshot", m
        assert m["sequence"] >= snapshot1["sequence"], (m["sequence"], snapshot1["sequence"])


@pytest.mark.at("AT-09-03-11")
def test_profundidad_del_snapshot_ws_y_deltas_sin_recorte(api, ws, usuario, rpc):
    """HU-09-03 Escenario 11: Profundidad del snapshot WS.

    - Dado un orderbook con más de 50 niveles activos (55 bids propios)
    - Cuando se suscribe con depth: 50
    - Entonces el snapshot trae a lo sumo 50 niveles por lado (RN-3)
    - Y suscribirse sin depth aplica el default 50; depth > 200 produce
      VALIDATION_ERROR por el socket
    - Y las deltas posteriores NO se recortan por depth: se emiten para todo
      cambio del libro, también en niveles fuera del top-50 (RN-3/RN-4)
    """
    # Dado: 55 niveles de bid propios (precios contiguos por tick, sin cruzar:
    # lado ask barrido primero)
    barrer_asks(api, rpc)
    precios = [1_500_000_000 - i * TICK_SIZE for i in range(55)]
    q = cantidad_para_notional(precios[-1])
    fondear_usdc(usuario, rpc, 55 * quote_min(q, precios[0]) + 10_000_000)
    ordenes = [
        crear_orden(usuario, "BUY", "LIMIT", price_min=p, quantity_wei=q) for p in precios
    ]
    try:
        # Cuando: suscripción con depth 50
        snapshot = _snapshot_tras_subscribe(ws, depth=50)

        # Entonces: a lo sumo 50 niveles por lado (con ≥ 55 activos ⇒ exactamente 50)
        assert len(snapshot["bids"]) == 50, len(snapshot["bids"])
        assert len(snapshot["asks"]) <= 50

        # Y: las deltas no se recortan por depth: cancelar la orden del nivel MÁS
        # BAJO (fuera del top-50 del snapshot) emite igual su update
        piso_snapshot = a_int(snapshot["bids"][-1][0])
        assert precios[-1] < piso_snapshot, "el nivel más bajo debía quedar fuera del top-50"
        resp = usuario.api.delete(f"/orders/{ordenes[-1]['orderId']}")
        assert resp.status_code == 200, resp.text
        update = ws.recibir_hasta(
            lambda m: m.get("type") == "update"
            and any(a_int(pp) == precios[-1] for pp, _ in m.get("bids", []))
        )
        entrada = next(e for e in update["bids"] if a_int(e[0]) == precios[-1])
        assert entrada[1] == "0", update

        # Y: sin depth aplica el default 50
        assert ws.desuscribir("orderbook").get("type") == "unsubscribed"
        snapshot = _snapshot_tras_subscribe(ws)  # sin depth
        assert len(snapshot["bids"]) == 50, len(snapshot["bids"])
        assert ws.desuscribir("orderbook").get("type") == "unsubscribed"

        # Y: depth > 200 ⇒ VALIDATION_ERROR por el socket
        respuesta = ws.suscribir("orderbook", depth=250)
        assert_error_ws(respuesta, "VALIDATION_ERROR")
    finally:
        for o in ordenes:
            cancelar_silencioso(usuario, o["orderId"])


@pytest.mark.at("AT-09-03-12")
def test_heartbeat_ping_pong_cierra_sin_pong_y_mantiene_con_pong(ws):
    """HU-09-03 Escenario 12: Heartbeat ping/pong.

    - Dado una conexión WS abierta
    - Cuando el servidor envía {type: ping} y el cliente NO responde pong dentro
      de la ventana (10 s)
    - Entonces el servidor cierra la conexión (RN-14)
    - Y un cliente que sí responde pong mantiene la conexión y sus suscripciones

    Nota: el ping JSON de aplicación es OBLIGATORIO (RN-14, ADR-006 D14): los
    frames de control ping/pong de RFC 6455 quedan permitidos sólo como
    mecanismo adicional, nunca como sustituto. Si el ping JSON no llega en la
    ventana, el test FALLA.
    """
    # Cuando: esperar el ping JSON obligatorio sin responderlo (intervalo
    # recomendado: 30 s; ventana holgada de 75 s)
    try:
        ws.recibir_hasta(
            lambda m: m.get("type") == "ping", timeout=75, descartar_ping=False
        )
    except TimeoutError:
        pytest.fail(
            "el SUT no emitió el ping JSON de aplicación {type: ping} en 75 s: "
            "RN-14 lo exige como mecanismo normativo del contrato (los frames "
            "de control RFC 6455 no lo sustituyen; ADR-006 D14)"
        )

    # Entonces: sin pong, el servidor cierra dentro de la ventana de 10 s (+margen)
    cerrado = False
    limite = time.monotonic() + 25
    try:
        while time.monotonic() < limite:
            try:
                ws.recibir(timeout=5)  # seguir leyendo SIN responder pongs
            except TimeoutError:
                continue
    except ConnectionClosed:
        cerrado = True
    assert cerrado, "el servidor no cerró la conexión ante la falta de pong (RN-14)"

    # Y: un cliente que responde pong mantiene la conexión y sus suscripciones
    with ConexionWs() as ws2:
        assert ws2.suscribir("trades").get("type") == "subscribed"
        limite = time.monotonic() + 45  # al menos un ciclo de ping de ~30 s
        while time.monotonic() < limite:
            try:
                m = ws2.recibir(timeout=10)
            except TimeoutError:
                continue
            if m.get("type") == "ping":
                ws2.enviar({"type": "pong"})
        # la conexión y la suscripción siguen vivas: el protocolo responde
        assert ws2.desuscribir("trades").get("type") == "unsubscribed"


@pytest.mark.at("AT-09-03-13")
def test_bootstrap_rest_mas_ws_reproduce_el_mismo_libro(api, ws, usuario, rpc):
    """HU-09-03 Escenario 13: Bootstrap REST + WS.

    - Dado un cliente que se suscribe al canal orderbook y acumula deltas en buffer
    - Cuando consulta GET /market/orderbook?depth=100 con sequence = S, aplica el
      snapshot REST y luego aplica del buffer solo las deltas con sequence > S
    - Entonces su copia local es idéntica a la del snapshot WS puro más sus deltas
      (RN-15; consistencia fuerte por número de secuencia, RN-12)
    """
    # Dado: suscripción WS (espejo puro-WS) + buffer de deltas
    snapshot_ws = _snapshot_tras_subscribe(ws, depth=200)
    espejo_ws = espejo_de_snapshot(snapshot_ws)

    p1, p2, p3 = niveles_bid_frescos(espejo_ws, precio_bid_seguro(api), 3)
    q = cantidad_para_notional(p3)
    fondear_usdc(usuario, rpc, 3 * quote_min(q, p1) + 10_000_000)

    ordenes = [crear_orden(usuario, "BUY", "LIMIT", price_min=p1, quantity_wei=q)]
    u1 = ws.recibir_hasta(lambda m: m.get("type") == "update")
    ordenes.append(crear_orden(usuario, "BUY", "LIMIT", price_min=p2, quantity_wei=q))
    u2 = ws.recibir_hasta(lambda m: m.get("type") == "update")
    buffer = [u1, u2]

    try:
        # Cuando: snapshot REST con sequence = S
        rest = libro(api, depth=100)
        s_rest = rest["sequence"]
        assert s_rest == u2["sequence"], "sin más actividad, REST refleja la última delta"
        espejo_rest = espejo_de_snapshot(rest)

        # ... se descartan las deltas con sequence ≤ S y se aplican las posteriores
        for delta in buffer:
            if delta["sequence"] > s_rest:
                aplicar_delta(espejo_rest, delta)
        for delta in buffer:  # el espejo puro-WS aplica todas las suyas
            aplicar_delta(espejo_ws, delta)

        # ... y ambas copias siguen aplicando deltas en vivo
        ordenes.append(crear_orden(usuario, "BUY", "LIMIT", price_min=p3, quantity_wei=q))
        u3 = ws.recibir_hasta(lambda m: m.get("type") == "update")
        assert u3["sequence"] == s_rest + 1, "numeración única y global del libro (RN-5)"
        aplicar_delta(espejo_ws, u3)
        aplicar_delta(espejo_rest, u3)

        # Entonces: mismo libro por ambos caminos (a igual profundidad)
        assert_espejos_equivalentes(espejo_ws, espejo_rest, profundidad=100)
        assert espejo_rest["bids"].get(p3) == q
    finally:
        for o in ordenes:
            cancelar_silencioso(usuario, o["orderId"])


@pytest.mark.at("AT-09-03-14")
def test_fill_multinivel_emite_un_unico_update_atomico(api, ws, usuario, usuario_b, rpc):
    """HU-09-03 Escenario 14: Atomicidad de la delta de un fill multi-nivel.

    - Dado un orderbook con varios niveles de ask y un cliente suscrito a orderbook
    - Cuando una orden taker BUY grande barre varios niveles de ask en un solo
      evento de matching
    - Entonces el cliente recibe UN ÚNICO mensaje update (mismo sequence) con
      TODOS los niveles afectados, y nunca observa un estado intermedio cruzado
      (RN-4, INV-4)
    """
    # Dado: exactamente dos niveles de ask propios de usuario_b
    barrer_asks(api, rpc)
    p1 = precio_dominante(api)
    p2 = p1 + 10 * TICK_SIZE
    q = cantidad_para_notional(p1)
    fondear_eth(usuario_b, rpc, 2 * q)
    crear_orden(usuario_b, "SELL", "LIMIT", price_min=p1, quantity_wei=q)
    crear_orden(usuario_b, "SELL", "LIMIT", price_min=p2, quantity_wei=q)

    snapshot = _snapshot_tras_subscribe(ws, depth=200)
    espejo = espejo_de_snapshot(snapshot)
    assert espejo["asks"].get(p1) == q and espejo["asks"].get(p2) == q, snapshot

    # Cuando: taker BUY que barre ambos niveles completos (un evento de matching)
    tomar_con_buy(usuario, rpc, p2, 2 * q)

    # Entonces: el PRIMER update tras el snapshot trae ambos niveles en cero,
    # con un único sequence (nada de estados intermedios)
    update = ws.recibir_hasta(lambda m: m.get("type") == "update")
    assert update["sequence"] == snapshot["sequence"] + 1, update
    niveles_ask = {a_int(pp): a_int(qq) for pp, qq in update.get("asks", [])}
    assert niveles_ask.get(p1) == 0, f"falta la eliminación de {p1} en el mismo update: {update}"
    assert niveles_ask.get(p2) == 0, f"falta la eliminación de {p2} en el mismo update: {update}"

    # Y: aplicado atómicamente, el libro nunca queda cruzado
    aplicar_delta(espejo, update)
    if espejo["bids"] and espejo["asks"]:
        assert max(espejo["bids"]) < min(espejo["asks"]), "libro cruzado tras el delta"
