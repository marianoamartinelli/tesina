"""Épica 09 — HU-09-04 (WebSocket privado del usuario): tests black-box.

Cubre AT-09-04-01..10 y AT-09-04-12. AT-09-04-11 (expiración del token en sesión
activa) está declarado en no_automatizables_ep09.yaml: el TTL del token lo fija
el SUT (HU-01-02) y no hay forma black-box de emitir un token de TTL corto.

Contrato central: `auth` como PRIMER mensaje (RN-1), suscripción a orders/
balances/withdrawals sin symbol (RN-2), aislamiento estricto por cuenta (RN-3),
eventos con estado completo y `sequence` contigua por canal (RN-4..RN-8),
consistencia post-settlement atómico (RN-9) y ciclo de vida de retiros (RN-14).
"""

import time

import pytest
from websockets.exceptions import ConnectionClosed

from comunes_ep09 import (
    DESTINO_RETIRO,
    assert_secuencia_contigua,
    balances_por_activo,
    barrer_asks,
    cancelar_silencioso,
    cantidad_para_notional,
    crear_orden,
    drenar,
    es_entero_json,
    es_timestamp_utc,
    fondear_eth,
    fondear_usdc,
    precio_dominante,
    recolectar_hasta,
)
from helpers.eip55 import RE_TXHASH
from helpers.errores import assert_error_ws
from helpers.montos import a_int, a_str, es_monto_valido, fee_maker, quote_min
from helpers.ws import ConexionWs

REASONS_BALANCE = {
    "ORDER_PLACED", "ORDER_CANCELLED", "ORDER_FILLED", "DEPOSIT_CREDITED",
    "WITHDRAWAL_INITIATED", "WITHDRAWAL_CONFIRMED", "WITHDRAWAL_FAILED",
}


def _autenticar_y_suscribir(ws, usuario, canales) -> None:
    """RN-1/RN-2: primer mensaje `auth`, luego subscribe (sin symbol) por canal."""
    respuesta = ws.autenticar(usuario.token)
    assert respuesta.get("type") == "authenticated", respuesta
    for canal in canales:
        respuesta = ws.suscribir(canal, symbol=None)
        assert respuesta.get("type") == "subscribed" and respuesta.get("channel") == canal, respuesta


def _assert_invariantes_balance(evento: dict) -> None:
    """INV-2 / INV-3 sobre un evento `balance` (RN-6), con montos string."""
    disponible = a_int(evento["available"])
    bloqueado = a_int(evento["locked"])
    total = a_int(evento["total"])
    assert disponible >= 0 and bloqueado >= 0, evento           # INV-2
    assert total == disponible + bloqueado, evento              # INV-3
    assert evento["reason"] in REASONS_BALANCE, evento
    assert es_entero_json(evento["sequence"]), evento


@pytest.mark.at("AT-09-04-01")
def test_autenticacion_y_suscripcion_a_orders_y_balances(ws, usuario):
    """HU-09-04 Escenario 1: Autenticación y suscripción.

    - Dado un token válido de la cuenta A
    - Cuando A envía como primer mensaje {type: auth, token}, recibe
      {type: authenticated} y suscribe orders y balances
    - Entonces recibe {type: subscribed, channel: orders} y
      {type: subscribed, channel: balances}
    """
    # Cuando: auth como primer mensaje (RN-1)
    respuesta = ws.autenticar(usuario.token)
    # Entonces
    assert respuesta.get("type") == "authenticated", respuesta

    # Cuando / Entonces: suscripción a ambos canales privados (RN-2, sin symbol)
    respuesta = ws.suscribir("orders", symbol=None)
    assert respuesta.get("type") == "subscribed" and respuesta.get("channel") == "orders", respuesta
    respuesta = ws.suscribir("balances", symbol=None)
    assert respuesta.get("type") == "subscribed" and respuesta.get("channel") == "balances", respuesta


@pytest.mark.at("AT-09-04-02")
def test_canal_privado_sin_token_valido_rechaza_y_cierra(ws):
    """HU-09-04 Escenario 2 (error): Sin token válido.

    - Dado el canal privado
    - Cuando un cliente envía auth con token inválido, o intenta subscribe sin
      auth, o no envía auth dentro de los 10 s de apertura
    - Entonces recibe { error: { code: "UNAUTHENTICATED" } } y el servidor cierra
      la conexión, sin entregar ningún evento de usuario (RN-1)
    """
    # Cuando: auth con token inválido
    respuesta = ws.autenticar("token-invalido-o-expirado")
    # Entonces: error UNAUTHENTICATED...
    assert_error_ws(respuesta, "UNAUTHENTICATED")
    # ... y cierre de la conexión (RN-1)
    cerrado = False
    try:
        limite = time.monotonic() + 10
        while time.monotonic() < limite:
            ws.recibir(timeout=2)
    except (ConnectionClosed, TimeoutError) as exc:
        cerrado = isinstance(exc, ConnectionClosed)
    assert cerrado, "tras auth inválido el servidor debe cerrar la conexión (RN-1)"

    # Cuando: subscribe a canal privado SIN auth previo
    with ConexionWs() as ws2:
        try:
            respuesta = ws2.suscribir("orders", symbol=None)
            assert_error_ws(respuesta, "UNAUTHENTICATED")
        except ConnectionClosed:
            pass  # cierre inmediato: también es rechazo sin entregar eventos

    # Cuando: ningún auth dentro de los 10 s desde la apertura
    with ConexionWs() as ws3:
        try:
            mensaje = ws3.recibir_hasta(lambda m: "error" in m, timeout=20)
            assert_error_ws(mensaje, "UNAUTHENTICATED")
            # Entonces: el servidor cierra tras el error
            cerrado = False
            try:
                ws3.recibir(timeout=10)
            except ConnectionClosed:
                cerrado = True
            except TimeoutError:
                cerrado = False
            assert cerrado, "tras el timeout de auth el servidor debe cerrar (RN-1)"
        except ConnectionClosed:
            pass  # cierre directo dentro de la ventana: rechazo válido


@pytest.mark.at("AT-09-04-03")
def test_evento_order_open_al_aceptar_el_alta(api, ws, usuario, rpc):
    """HU-09-04 Escenario 3: Evento de orden al aceptar el alta.

    - Dado A suscrito a orders
    - Cuando A crea una orden limit que queda resting
    - Entonces A recibe un evento order con status: "OPEN", filledWei: "0",
      feeWei: "0", feeUsdcMin: "0" y los montos como strings (RN-4/RN-10)
    """
    # Dado: fondos primero (el depósito no debe intercalar eventos), luego suscripción
    barrer_asks(api, rpc)  # garantiza que el bid quede resting
    p = precio_dominante(api)
    q = cantidad_para_notional(p)
    fondear_usdc(usuario, rpc, quote_min(q, p) + 10_000_000)
    _autenticar_y_suscribir(ws, usuario, ["orders"])

    # Cuando
    orden = crear_orden(usuario, "BUY", "LIMIT", price_min=p, quantity_wei=q)

    try:
        # Entonces
        evento = ws.recibir_hasta(lambda m: m.get("type") == "order")
        assert evento["orderId"] == orden["orderId"], evento
        assert evento["clientOrderId"] == orden["clientOrderId"], evento
        assert evento["symbol"] == "ETH-USDC" and evento["side"] == "BUY", evento
        assert evento["status"] == "OPEN", evento
        assert evento["filledWei"] == "0", evento
        assert evento["feeWei"] == "0" and evento["feeUsdcMin"] == "0", evento
        for campo in ("priceMin", "quantityWei", "filledWei", "feeWei", "feeUsdcMin"):
            assert es_monto_valido(evento[campo]), (campo, evento)
        assert es_entero_json(evento["sequence"]), evento
        assert es_timestamp_utc(evento["timestamp"]), evento
    finally:
        cancelar_silencioso(usuario, orden["orderId"])


@pytest.mark.at("AT-09-04-04")
def test_transiciones_por_fill_parcial_y_total_con_sequence_contigua(api, ws, usuario, usuario_b, rpc):
    """HU-09-04 Escenario 4: Transición por fill parcial y total.

    - Dado una orden limit propia OPEN por quantityWei "1000000000000000000" (1 ETH)
    - Cuando se ejecuta un fill parcial de 0.4 ETH y luego el resto
    - Entonces A recibe order con status "PARTIALLY_FILLED" y
      filledWei "400000000000000000", y luego "FILLED" con filledWei total
    - Y los eventos llegan con sequence creciente y contigua (RN-8)
    """
    # Dado: ask propio de 1 ETH como único ask del libro
    barrer_asks(api, rpc)
    p = precio_dominante(api)
    q_total = 1_000_000_000_000_000_000
    q_parcial = 400_000_000_000_000_000
    fondear_eth(usuario, rpc, q_total)
    fondear_usdc(usuario_b, rpc, quote_min(q_total, p) + 10_000_000)
    _autenticar_y_suscribir(ws, usuario, ["orders"])
    orden = crear_orden(usuario, "SELL", "LIMIT", price_min=p, quantity_wei=q_total)

    # Cuando: fill parcial (0.4 ETH) y luego el resto (0.6 ETH)
    crear_orden(usuario_b, "BUY", "LIMIT", price_min=p, quantity_wei=q_parcial)
    crear_orden(usuario_b, "BUY", "LIMIT", price_min=p, quantity_wei=q_total - q_parcial)

    # Entonces: OPEN → PARTIALLY_FILLED(0.4) → FILLED(1.0), con sequence contigua
    eventos = recolectar_hasta(
        ws,
        lambda m: m.get("type") == "order" and m.get("status") == "FILLED",
        timeout=10,
    )
    de_orden = [m for m in eventos if m.get("type") == "order"]
    estados = [(m["status"], m["filledWei"]) for m in de_orden]
    assert estados == [
        ("OPEN", "0"),
        ("PARTIALLY_FILLED", a_str(q_parcial)),
        ("FILLED", a_str(q_total)),
    ], estados
    assert_secuencia_contigua(de_orden, contexto="canal orders")


@pytest.mark.at("AT-09-04-05")
def test_eventos_balance_al_bloquear_y_al_liquidar_con_invariantes(api, ws, usuario, usuario_b, rpc):
    """HU-09-04 Escenario 5: Evento de balance al bloquear y al liquidar.

    - Dado A suscrito a balances con USDC disponible
    - Cuando A crea una orden BUY que bloquea USDC y luego se llena
    - Entonces A recibe un balance de USDC con locked aumentado
      (reason ORDER_PLACED, refId = orderId) y, tras el fill, eventos balance
      (reason ORDER_FILLED, refId = orderId) con el consumo del bloqueado y el
      crédito de ETH (menos la fee)
    - Y en cada evento total == available + locked (INV-3) y todos ≥ 0 (INV-2)
    """
    # Dado: fondeo previo a la suscripción (el depósito no intercala eventos)
    barrer_asks(api, rpc)
    p = precio_dominante(api)
    q = cantidad_para_notional(p)
    reserva = quote_min(q, p)
    margen = 10_000_000
    fondear_usdc(usuario, rpc, reserva + margen)
    fondear_eth(usuario_b, rpc, q)
    _autenticar_y_suscribir(ws, usuario, ["balances"])

    # Cuando: BUY propio que queda resting (mejor bid; sin asks que crucen)...
    orden = crear_orden(usuario, "BUY", "LIMIT", price_min=p, quantity_wei=q)

    # Entonces: bloqueo reflejado (ORDER_PLACED con refId = orderId)
    bloqueo = ws.recibir_hasta(
        lambda m: m.get("type") == "balance" and m.get("reason") == "ORDER_PLACED"
    )
    _assert_invariantes_balance(bloqueo)
    assert bloqueo["asset"] == "USDC", bloqueo
    assert bloqueo["refId"] == orden["orderId"], bloqueo
    assert a_int(bloqueo["locked"]) == reserva, bloqueo

    # ... y luego se llena (taker SELL de B contra el mejor bid, que es el de A)
    crear_orden(usuario_b, "SELL", "LIMIT", price_min=p, quantity_wei=q)

    # Entonces: consumo del bloqueado (USDC) y crédito de ETH menos la fee maker
    # (el orden relativo USDC/ETH no está fijado: se espera hasta ver ambos)
    activos_vistos: set = set()

    def _ambos_activos(m):
        if m.get("type") == "balance" and m.get("reason") == "ORDER_FILLED":
            activos_vistos.add(m.get("asset"))
        return {"USDC", "ETH"} <= activos_vistos

    eventos = recolectar_hasta(ws, _ambos_activos, timeout=10)
    de_balance = [m for m in eventos if m.get("type") == "balance"]
    for evento in de_balance:
        _assert_invariantes_balance(evento)

    usdc_fill = next(
        m for m in de_balance if m["reason"] == "ORDER_FILLED" and m["asset"] == "USDC"
    )
    assert usdc_fill["refId"] == orden["orderId"], usdc_fill
    assert a_int(usdc_fill["locked"]) == 0, usdc_fill            # bloqueado consumido
    assert a_int(usdc_fill["total"]) == margen, usdc_fill        # sólo queda el margen

    eth_fill = next(
        m for m in de_balance if m["reason"] == "ORDER_FILLED" and m["asset"] == "ETH"
    )
    assert eth_fill["refId"] == orden["orderId"], eth_fill
    # crédito exacto: q menos la fee maker (BUY recibe ETH; fee con ceil, §3.3)
    assert a_int(eth_fill["total"]) == q - fee_maker(q), eth_fill


@pytest.mark.at("AT-09-04-06")
def test_cancelacion_reflejada_en_order_y_balance(api, ws, usuario, rpc):
    """HU-09-04 Escenario 6: Cancelación reflejada.

    - Dado una orden propia OPEN
    - Cuando A la cancela vía DELETE /orders/{orderId}
    - Entonces A recibe un evento order con status "CANCELLED" y un evento
      balance (reason ORDER_CANCELLED, refId = orderId) que libera el bloqueado
      (bloqueado→disponible, total constante, INV-3)
    """
    # Dado: bid propio resting con su reserva bloqueada
    barrer_asks(api, rpc)
    p = precio_dominante(api)
    q = cantidad_para_notional(p)
    reserva = quote_min(q, p)
    fondeo = reserva + 10_000_000
    fondear_usdc(usuario, rpc, fondeo)
    _autenticar_y_suscribir(ws, usuario, ["orders", "balances"])
    orden = crear_orden(usuario, "BUY", "LIMIT", price_min=p, quantity_wei=q)
    # drenar los eventos del alta (order OPEN + balance ORDER_PLACED)
    recolectar_hasta(
        ws,
        lambda m: m.get("type") == "balance" and m.get("reason") == "ORDER_PLACED",
        timeout=10,
    )

    # Cuando
    resp = usuario.api.delete(f"/orders/{orden['orderId']}")
    assert resp.status_code == 200, resp.text

    # Entonces: evento order CANCELLED + balance ORDER_CANCELLED que libera todo
    eventos = recolectar_hasta(
        ws,
        lambda m: m.get("type") == "balance" and m.get("reason") == "ORDER_CANCELLED",
        timeout=10,
    )
    cancel_orden = next(
        m for m in eventos
        if m.get("type") == "order" and m.get("status") == "CANCELLED"
    )
    assert cancel_orden["orderId"] == orden["orderId"], cancel_orden

    liberacion = eventos[-1]
    _assert_invariantes_balance(liberacion)
    assert liberacion["asset"] == "USDC", liberacion
    assert liberacion["refId"] == orden["orderId"], liberacion
    assert a_int(liberacion["locked"]) == 0, liberacion                 # bloqueado→disponible
    assert a_int(liberacion["available"]) == fondeo, liberacion         # todo liberado
    assert a_int(liberacion["total"]) == fondeo, liberacion             # total constante


@pytest.mark.at("AT-09-04-07")
def test_aislamiento_cada_cuenta_recibe_solo_sus_eventos(api, ws, usuario, usuario_b, rpc):
    """HU-09-04 Escenario 7 (aislamiento): Eventos solo del dueño.

    - Dado A y B suscritos al canal privado con sus respectivos tokens
    - Cuando ocurre un fill entre una orden de A (maker) y una de B (taker)
    - Entonces A recibe únicamente sus eventos order/balance y B únicamente los
      suyos; ninguno recibe eventos del otro (RN-3)
    """
    # Dado: fondeo previo + ambos suscritos a orders y balances
    barrer_asks(api, rpc)
    p = precio_dominante(api)
    q = cantidad_para_notional(p)
    fondear_eth(usuario, rpc, q)
    fondear_usdc(usuario_b, rpc, quote_min(q, p) + 10_000_000)
    _autenticar_y_suscribir(ws, usuario, ["orders", "balances"])
    with ConexionWs() as ws_b:
        _autenticar_y_suscribir(ws_b, usuario_b, ["orders", "balances"])

        # Cuando: fill A (maker SELL) × B (taker BUY)
        orden_a = crear_orden(usuario, "SELL", "LIMIT", price_min=p, quantity_wei=q)
        orden_b = crear_orden(usuario_b, "BUY", "LIMIT", price_min=p, quantity_wei=q)

        # Entonces: cada uno ve su orden llegar a FILLED...
        eventos_a = recolectar_hasta(
            ws, lambda m: m.get("type") == "order" and m.get("status") == "FILLED", timeout=10
        )
        eventos_b = recolectar_hasta(
            ws_b, lambda m: m.get("type") == "order" and m.get("status") == "FILLED", timeout=10
        )
        eventos_a += drenar(ws, ventana=2.0)   # capturar también los balances del fill
        eventos_b += drenar(ws_b, ventana=2.0)

        def _solo_del_duenio(eventos, orden_propia, orden_ajena, quien):
            ids_orden = {m.get("orderId") for m in eventos if m.get("type") == "order"}
            assert ids_orden == {orden_propia["orderId"]}, (quien, eventos)
            refs = {m.get("refId") for m in eventos if m.get("type") == "balance"}
            assert orden_ajena["orderId"] not in refs, (quien, eventos)
            assert orden_ajena["clientOrderId"] not in {
                m.get("clientOrderId") for m in eventos
            }, (quien, eventos)

        _solo_del_duenio(eventos_a, orden_a, orden_b, "A")
        _solo_del_duenio(eventos_b, orden_b, orden_a, "B")


@pytest.mark.at("AT-09-04-08")
def test_estado_posterior_al_settlement_atomico_consistente(api, ws, usuario, usuario_b, rpc):
    """HU-09-04 Escenario 8 (atomicidad): Estado posterior al settlement.

    - Dado un fill que afecta orden y balances de A
    - Cuando A recolecta todos los eventos privados desde el alta hasta el
      order con status "FILLED"
    - Entonces (1) el cambio de filledWei y los cambios de available/locked son
      mutuamente consistentes según INV-3; y (2) no existe evento balance que
      reduzca locked sin el correspondiente incremento de filledWei del mismo
      fill (estado posterior al settlement atómico, INV-4)
    """
    # Dado: A maker BUY (bloquea USDC), B taker SELL; fondeo previo a suscribir
    barrer_asks(api, rpc)
    p = precio_dominante(api)
    q = cantidad_para_notional(p)
    reserva = quote_min(q, p)
    fondear_usdc(usuario, rpc, reserva + 10_000_000)
    fondear_eth(usuario_b, rpc, q)
    _autenticar_y_suscribir(ws, usuario, ["orders", "balances"])

    # Cuando: alta + fill, recolectando TODOS los eventos hasta FILLED (+drenaje)
    orden = crear_orden(usuario, "BUY", "LIMIT", price_min=p, quantity_wei=q)
    crear_orden(usuario_b, "SELL", "LIMIT", price_min=p, quantity_wei=q)
    eventos = recolectar_hasta(
        ws, lambda m: m.get("type") == "order" and m.get("status") == "FILLED", timeout=10
    )
    eventos += drenar(ws, ventana=2.0)

    de_orden = [m for m in eventos if m.get("type") == "order"]
    de_balance = [m for m in eventos if m.get("type") == "balance"]

    # Entonces (1): invariantes en cada evento y consistencia mutua exacta
    for evento in de_balance:
        _assert_invariantes_balance(evento)
    fill_orden = next(m for m in de_orden if m["status"] == "FILLED")
    assert fill_orden["filledWei"] == a_str(q), fill_orden

    reducciones_locked = [
        m for m in de_balance
        if m["reason"] == "ORDER_FILLED" and m["asset"] == "USDC"
    ]
    assert reducciones_locked, "el fill debe reflejar el consumo del bloqueado USDC"
    usdc_fill = reducciones_locked[-1]
    # el bloqueado consumido es exactamente el notional del fill (misma fórmula floor)
    assert a_int(usdc_fill["locked"]) == reserva - quote_min(q, p) == 0, usdc_fill
    eth_fill = next(
        m for m in de_balance if m["reason"] == "ORDER_FILLED" and m["asset"] == "ETH"
    )
    assert a_int(eth_fill["total"]) == q - fee_maker(q), eth_fill

    # Entonces (2): toda reducción de locked por fill correlaciona (refId) con la
    # orden cuyo evento FILLED registra el incremento de filledWei del mismo fill
    for m in reducciones_locked:
        assert m["refId"] == orden["orderId"], m
    assert fill_orden["orderId"] == orden["orderId"]


@pytest.mark.at("AT-09-04-09")
def test_secuencia_privada_contigua_por_canal_y_resincronizacion_rest(api, ws, usuario, rpc):
    """HU-09-04 Escenario 9 (borde): Hueco de secuencia.

    - Dado A recibió eventos hasta sequence = s en el canal orders
    - Cuando debe re-sincronizar (el contrato: reconsultar REST o re-suscribirse)
    - Entonces tras re-sincronizar el estado es consistente
    - Y un evento de otro canal (balances) con sequence distinta no se interpreta
      como hueco: cada canal mantiene su numeración contigua propia (RN-8)

    Nota: la pérdida de mensajes no es inyectable black-box; se verifica la
    numeración por canal que define el hueco y la consistencia del re-sync REST.
    """
    # Dado: suscripto a orders y balances, con actividad en ambos canales
    barrer_asks(api, rpc)
    p = precio_dominante(api)
    q = cantidad_para_notional(p)
    fondeo = quote_min(q, p) + 10_000_000
    fondear_usdc(usuario, rpc, fondeo)
    _autenticar_y_suscribir(ws, usuario, ["orders", "balances"])

    orden = crear_orden(usuario, "BUY", "LIMIT", price_min=p, quantity_wei=q)
    resp = usuario.api.delete(f"/orders/{orden['orderId']}")
    assert resp.status_code == 200, resp.text
    eventos = recolectar_hasta(
        ws,
        lambda m: m.get("type") == "balance" and m.get("reason") == "ORDER_CANCELLED",
        timeout=10,
    )
    eventos += drenar(ws, ventana=1.0)

    # Y: secuencias contiguas DENTRO de cada canal, pese al intercalado del otro
    de_orden = [m for m in eventos if m.get("type") == "order"]
    de_balance = [m for m in eventos if m.get("type") == "balance"]
    assert de_orden and de_balance, eventos
    assert_secuencia_contigua(de_orden, contexto="canal orders")
    assert_secuencia_contigua(de_balance, contexto="canal balances")

    # Entonces: re-sincronizar por REST da un estado consistente con el último evento
    detalle = usuario.api.get(f"/orders/{orden['orderId']}").json()
    assert detalle["status"] == de_orden[-1]["status"] == "CANCELLED"
    usdc = balances_por_activo(usuario)["USDC"]
    ultimo_balance = de_balance[-1]
    assert usdc["available"] == ultimo_balance["available"], (usdc, ultimo_balance)
    assert usdc["locked"] == ultimo_balance["locked"], (usdc, ultimo_balance)
    assert usdc["total"] == ultimo_balance["total"], (usdc, ultimo_balance)


@pytest.mark.at("AT-09-04-10")
def test_eventos_idempotentes_y_numeracion_nueva_tras_reconexion(api, ws, usuario, rpc):
    """HU-09-04 Escenario 10 (idempotencia de cliente): Reaplicar evento.

    - Dado A recibió un evento order con orderId X, status FILLED/terminal, sequence s
    - Cuando reaplica un evento con sequence ≤ s para X (retransmisión simulada
      dentro de la misma conexión)
    - Entonces la copia local no se corrompe ni retrocede: los eventos llevan el
      estado completo + orderId + sequence, suficientes para aplicar
      "último estado gana" (RN-11)
    - Y tras una reconexión la numeración del canal es NUEVA (no comparable): el
      cliente re-sincroniza por REST (RN-8)
    """
    # Dado: dos eventos de la misma orden (OPEN y CANCELLED) en una conexión
    barrer_asks(api, rpc)
    p = precio_dominante(api)
    q = cantidad_para_notional(p)
    fondear_usdc(usuario, rpc, 2 * quote_min(q, p) + 10_000_000)
    _autenticar_y_suscribir(ws, usuario, ["orders"])
    orden = crear_orden(usuario, "BUY", "LIMIT", price_min=p, quantity_wei=q)
    assert usuario.api.delete(f"/orders/{orden['orderId']}").status_code == 200
    e_open = ws.recibir_hasta(lambda m: m.get("type") == "order" and m["status"] == "OPEN")
    e_cancel = ws.recibir_hasta(
        lambda m: m.get("type") == "order" and m["status"] == "CANCELLED"
    )

    # Entonces: cada evento trae identidad + secuencia + estado completo (RN-11)
    for e in (e_open, e_cancel):
        assert e["orderId"] == orden["orderId"], e
        assert es_entero_json(e["sequence"]), e
        assert set(e) >= {"status", "filledWei", "quantityWei"}, e

    # ... aplicar "último estado gana por sequence" y reaplicar el evento viejo:
    # la copia local no retrocede (idempotencia del lado cliente)
    copia_local: dict = {}

    def aplicar(evento):
        actual = copia_local.get(evento["orderId"])
        if actual is None or evento["sequence"] >= actual["sequence"]:
            copia_local[evento["orderId"]] = evento

    aplicar(e_open)
    aplicar(e_cancel)
    estado_final = dict(copia_local[orden["orderId"]])
    aplicar(e_open)  # retransmisión con sequence ≤ s
    assert copia_local[orden["orderId"]] == estado_final, "la copia local retrocedió"

    # Y: tras reconectar, el canal arranca numeración propia y sigue contiguo
    ws.cerrar()
    with ConexionWs() as ws2:
        _autenticar_y_suscribir(ws2, usuario, ["orders"])
        orden2 = crear_orden(usuario, "BUY", "LIMIT", price_min=p, quantity_wei=q)
        assert usuario.api.delete(f"/orders/{orden2['orderId']}").status_code == 200
        e1 = ws2.recibir_hasta(lambda m: m.get("type") == "order")
        e2 = ws2.recibir_hasta(lambda m: m.get("type") == "order")
        # numeración nueva de la conexión: sólo se exige contigüidad interna;
        # el cliente re-sincroniza por REST y no compara con la conexión anterior
        assert_secuencia_contigua([e1, e2], contexto="canal orders (reconexión)")
        detalle = usuario.api.get(f"/orders/{orden2['orderId']}").json()
        assert detalle["status"] == "CANCELLED"


@pytest.mark.at("AT-09-04-12")
def test_canal_withdrawals_refleja_el_ciclo_de_vida_con_aislamiento(api, ws, usuario, usuario_b, rpc):
    """HU-09-04 Escenario 12 (retiros): Canal de retiros refleja el ciclo de vida.

    - Dado A suscrito a withdrawals
    - Cuando A solicita un retiro y este avanza on-chain
    - Entonces A recibe un evento withdrawal por transición: PENDING, BROADCAST
      (con txHash no nulo) y finalmente CONFIRMED o FAILED, con amountMinUnit
      string y confirmations entero JSON (RN-14)
    - Y failureReason es no nulo (enum de HU-09-01 RN-18) solo si FAILED
    - Y A no recibe eventos de retiros de otra cuenta (aislamiento, RN-3)
    """
    # Dado: fondos ETH (monto + previsión de gas) y ambos suscritos a withdrawals
    fondear_eth(usuario, rpc, 1_100_000_000_000_000_000)  # 1.1 ETH
    _autenticar_y_suscribir(ws, usuario, ["withdrawals"])
    with ConexionWs() as ws_b:
        _autenticar_y_suscribir(ws_b, usuario_b, ["withdrawals"])

        # Cuando: A solicita un retiro de 1 ETH
        resp = usuario.api.post(
            "/withdrawals",
            json={"asset": "ETH", "amountMinUnit": "1000000000000000000",
                  "address": DESTINO_RETIRO},
        )
        assert resp.status_code == 202, resp.text
        wid = resp.json()["withdrawalId"]

        # Entonces: eventos por transición hasta el estado terminal. Tras ver
        # BROADCAST se minan 12 bloques para permitir CONFIRMED (entorno anvil).
        eventos: list[dict] = []

        def _evento_de_retiro(timeout=45):
            m = ws.recibir_hasta(
                lambda m: m.get("type") == "withdrawal" and m.get("withdrawalId") == wid,
                timeout=timeout,
            )
            eventos.append(m)
            return m

        m = _evento_de_retiro()
        assert m["status"] == "PENDING", m
        assert m["txHash"] is None, m

        while eventos[-1]["status"] not in ("CONFIRMED", "FAILED"):
            m = _evento_de_retiro()
            if m["status"] == "BROADCAST":
                assert isinstance(m["txHash"], str) and RE_TXHASH.fullmatch(m["txHash"]), m
                rpc.minar_bloques(12)  # confirmaciones a demanda

        # ... con la forma del contrato en cada evento (RN-14)
        for m in eventos:
            assert m["asset"] == "ETH", m
            assert m["amountMinUnit"] == "1000000000000000000", m
            assert es_monto_valido(m["amountMinUnit"]), m
            assert es_entero_json(m["confirmations"]), m
            assert es_entero_json(m["sequence"]), m
            if m["status"] == "FAILED":
                assert m["failureReason"] in (
                    "BROADCAST_FAILED", "TX_DROPPED", "TX_REVERTED", "USER_CANCELLED"
                ), m
            else:
                assert m["failureReason"] is None, m

        estados = [m["status"] for m in eventos]
        assert estados[0] == "PENDING" and estados[-1] in ("CONFIRMED", "FAILED"), estados
        if estados[-1] == "CONFIRMED":
            assert "BROADCAST" in estados, estados  # el ciclo pasa por el broadcast

        # Y: B no recibió ningún evento del retiro de A (aislamiento RN-3)
        ws_b.no_debe_llegar(lambda m: m.get("type") == "withdrawal", ventana=2.0)
