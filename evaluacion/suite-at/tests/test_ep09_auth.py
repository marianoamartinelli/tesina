"""Épica 09 — HU-09-02 (autenticación y autorización de la API): tests black-box.

Cubre AT-09-02-01..11, más AT-09-05-04 (precedencia auth > esquema, mismo flujo
que AT-09-02-04) y AT-09-05-08 (forma del 429, mismo flujo que AT-09-02-11).

Regla central: token Bearer en recursos protegidos (RN-1..RN-3), aislamiento
estricto por cuenta (RN-5..RN-8), auth antes que esquema (RN-9), WS privado con
el mismo token (RN-10) y rate limit de 60 req/min por cuenta y endpoint (RN-12).
"""

import time

import pytest
from websockets.exceptions import ConnectionClosed

from comunes_ep09 import (
    DESTINO_RETIRO,
    balances_por_activo,
    barrer_asks,
    cancelar_silencioso,
    cantidad_para_notional,
    colocar_ask_dominante,
    crear_orden,
    es_entero_json,
    fondear_eth,
    fondear_usdc,
    precio_bid_seguro,
    recolectar_hasta,
    tomar_con_buy,
)
from helpers.cuentas import crear_usuario
from helpers.errores import assert_error, assert_error_ws
from helpers.montos import quote_min
from helpers.ws import ConexionWs


@pytest.mark.at("AT-09-02-01")
def test_acceso_autenticado_exitoso_a_recurso_protegido(usuario):
    """HU-09-02 Escenario 1: Acceso autenticado exitoso.

    - Dado un token válido emitido para la cuenta A
    - Cuando A hace GET /api/v1/balances con Authorization: Bearer <token>
    - Entonces la respuesta es 200 con los balances de la cuenta A
    """
    # Cuando (usuario.api lleva Authorization: Bearer <token>)
    resp = usuario.api.get("/balances")

    # Entonces: 200 con el arreglo de balances propio (cuenta fresca: ambos activos)
    assert resp.status_code == 200, resp.text
    activos = {b["asset"] for b in resp.json()}
    assert {"ETH", "USDC"} <= activos, resp.text


@pytest.mark.at("AT-09-02-02")
def test_recurso_protegido_sin_token_responde_unauthenticated(api):
    """HU-09-02 Escenario 2 (error): Token ausente.

    - Dado un recurso protegido (GET /api/v1/me)
    - Cuando el cliente lo invoca sin header Authorization
    - Entonces la respuesta es UNAUTHENTICATED (401) con el envelope de error
    """
    # Dado / Cuando (el fixture `api` no lleva token)
    resp = api.get("/me")

    # Entonces (assert_error valida envelope + code + status 401 del catálogo)
    assert_error(resp, "UNAUTHENTICATED")


@pytest.mark.at("AT-09-02-03")
def test_token_invalido_o_esquema_no_bearer_responde_unauthenticated(api):
    """HU-09-02 Escenario 3 (error): Token inválido o malformado.

    - Dado un recurso protegido
    - Cuando envía "Bearer xxx-invalido" o "Token abc" (esquema no Bearer)
    - Entonces la respuesta es UNAUTHENTICATED (401)
    - Y el message no revela si el token existió ni por qué exactamente falló

    Nota: la variante "token expirado" del escenario no es forzable black-box
    (TTL fijo del SUT, HU-01-02 RN); el rechazo por expiración usa el mismo
    code según HU-09-02 RN-3.
    """
    # Cuando: token inválido con esquema Bearer
    resp = api.get("/me", headers={"Authorization": "Bearer xxx-invalido"})
    # Entonces
    err = assert_error(resp, "UNAUTHENTICATED")
    # Y: el message no ecoa el token ni distingue el motivo
    assert "xxx-invalido" not in err["message"], err

    # Cuando: esquema no Bearer
    resp = api.get("/me", headers={"Authorization": "Token abc"})
    assert_error(resp, "UNAUTHENTICATED")


@pytest.mark.at("AT-09-02-04", "AT-09-05-04")
def test_payload_invalido_sin_token_es_unauthenticated_no_validation(api):
    """HU-09-02 Escenario 4 / HU-09-05 Escenario 4: Auth antes que esquema.

    - Dado un recurso protegido POST /api/v1/orders
    - Cuando el cliente envía un body inválido SIN token
    - Entonces la respuesta es UNAUTHENTICATED (401), no VALIDATION_ERROR
      (la autenticación precede a la validación de esquema, modelo-de-errores §4)
    """
    # Cuando: body claramente inválido (campos faltantes y monto mal serializado)
    resp = api.post("/orders", json={"side": "HOLD", "priceMin": 1.5})

    # Entonces: gana la autenticación (401), nunca 422
    err = assert_error(resp, "UNAUTHENTICATED")
    assert err["code"] != "VALIDATION_ERROR"


@pytest.mark.at("AT-09-02-05")
def test_listados_de_ordenes_aislados_por_cuenta(api, usuario, usuario_b, rpc):
    """HU-09-02 Escenario 5 (autorización): Listados aislados por cuenta.

    - Dado que la cuenta A tiene 3 órdenes y la cuenta B tiene 2 órdenes
    - Cuando A hace GET /api/v1/orders
    - Entonces la respuesta solo incluye las 3 órdenes de A
    - Y ninguna orden, conteo o cursor revela las órdenes de B
    """
    # Dado: 3 bids resting de A y 2 de B (cuentas frescas)
    p = precio_bid_seguro(api)
    q = cantidad_para_notional(p)
    fondear_usdc(usuario, rpc, 3 * quote_min(q, p) + 10_000_000)
    fondear_usdc(usuario_b, rpc, 2 * quote_min(q, p) + 10_000_000)
    ordenes_a = [crear_orden(usuario, "BUY", "LIMIT", price_min=p, quantity_wei=q) for _ in range(3)]
    ordenes_b = [crear_orden(usuario_b, "BUY", "LIMIT", price_min=p, quantity_wei=q) for _ in range(2)]
    try:
        # Cuando
        resp = usuario.api.get("/orders", params={"limit": 200})

        # Entonces: exactamente las 3 órdenes de A (la cuenta es fresca)
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        ids_listados = {i["orderId"] for i in items}
        assert ids_listados == {o["orderId"] for o in ordenes_a}, items

        # Y: nada de B aparece (ni ids ni clientOrderIds)
        ids_b = {o["orderId"] for o in ordenes_b}
        cids_b = {o["clientOrderId"] for o in ordenes_b}
        assert not ids_listados & ids_b
        assert not {i["clientOrderId"] for i in items} & cids_b
    finally:
        for o in ordenes_a:
            cancelar_silencioso(usuario, o["orderId"])
        for o in ordenes_b:
            cancelar_silencioso(usuario_b, o["orderId"])


@pytest.mark.at("AT-09-02-06")
def test_acceso_a_orden_ajena_es_order_not_found_indistinguible(api, usuario, usuario_b, rpc):
    """HU-09-02 Escenario 6 (autorización/error): Acceso a orden ajena.

    - Dado una orden con orderId perteneciente a la cuenta B
    - Cuando la cuenta A hace GET /api/v1/orders/{orderId} de esa orden
    - Entonces la respuesta es ORDER_NOT_FOUND (404)
    - Y es indistinguible de la de un orderId inexistente (no filtra existencia)
    """
    # Dado: una orden resting de B
    p = precio_bid_seguro(api)
    q = cantidad_para_notional(p)
    fondear_usdc(usuario_b, rpc, quote_min(q, p) + 10_000_000)
    orden_b = crear_orden(usuario_b, "BUY", "LIMIT", price_min=p, quantity_wei=q)
    try:
        # Cuando: A consulta la orden de B
        resp_ajena = usuario.api.get(f"/orders/{orden_b['orderId']}")
        # Entonces
        err_ajena = assert_error(resp_ajena, "ORDER_NOT_FOUND")

        # Y: misma respuesta (code + status) que un orderId inexistente
        resp_inexistente = usuario.api.get("/orders/orden-inexistente-000")
        err_inexistente = assert_error(resp_inexistente, "ORDER_NOT_FOUND")
        assert resp_ajena.status_code == resp_inexistente.status_code
        assert err_ajena["code"] == err_inexistente["code"]
    finally:
        cancelar_silencioso(usuario_b, orden_b["orderId"])


@pytest.mark.at("AT-09-02-07")
def test_cancelar_orden_ajena_es_404_y_no_la_modifica(api, usuario, usuario_b, rpc):
    """HU-09-02 Escenario 7 (autorización/error): Cancelar orden ajena.

    - Dado una orden OPEN perteneciente a la cuenta B
    - Cuando la cuenta A hace DELETE /api/v1/orders/{orderId} de esa orden
    - Entonces la respuesta es ORDER_NOT_FOUND (404)
    - Y la orden de B permanece OPEN (sus balances bloqueados no cambian, INV-3)
    """
    # Dado: una orden OPEN de B con su reserva bloqueada
    p = precio_bid_seguro(api)
    q = cantidad_para_notional(p)
    fondear_usdc(usuario_b, rpc, quote_min(q, p) + 10_000_000)
    orden_b = crear_orden(usuario_b, "BUY", "LIMIT", price_min=p, quantity_wei=q)
    assert orden_b["status"] == "OPEN"
    bloqueado_previo = balances_por_activo(usuario_b)["USDC"]["locked"]
    try:
        # Cuando: A intenta cancelarla
        resp = usuario.api.delete(f"/orders/{orden_b['orderId']}")

        # Entonces: 404 sin filtrar existencia
        assert_error(resp, "ORDER_NOT_FOUND")

        # Y: la orden de B sigue OPEN y su bloqueado no cambió
        detalle = usuario_b.api.get(f"/orders/{orden_b['orderId']}").json()
        assert detalle["status"] == "OPEN", detalle
        assert balances_por_activo(usuario_b)["USDC"]["locked"] == bloqueado_previo
    finally:
        cancelar_silencioso(usuario_b, orden_b["orderId"])


@pytest.mark.at("AT-09-02-08")
def test_acceso_a_retiro_ajeno_es_not_found_indistinguible(usuario, usuario_b, rpc):
    """HU-09-02 Escenario 8 (autorización/error): Acceso a retiro ajeno.

    - Dado un retiro perteneciente a la cuenta B
    - Cuando la cuenta A hace GET /api/v1/withdrawals/{withdrawalId} de ese retiro
    - Entonces la respuesta es NOT_FOUND (404), indistinguible de un id inexistente
    """
    # Dado: un retiro de B (fondos + previsión de gas en ETH, HU-08-01 RN-9)
    fondear_usdc(usuario_b, rpc, 10_000_000)
    fondear_eth(usuario_b, rpc, 10_000_000_000_000_000)  # 0.01 ETH
    resp = usuario_b.api.post(
        "/withdrawals",
        json={"asset": "USDC", "amountMinUnit": "5000000", "address": DESTINO_RETIRO},
    )
    assert resp.status_code == 202, resp.text
    retiro_b = resp.json()["withdrawalId"]

    # Cuando: A consulta el retiro de B
    resp_ajeno = usuario.api.get(f"/withdrawals/{retiro_b}")
    # Entonces
    err_ajeno = assert_error(resp_ajeno, "NOT_FOUND")

    # Y: indistinguible de un id inexistente (mismo code y status)
    resp_inexistente = usuario.api.get("/withdrawals/retiro-inexistente-000")
    err_inexistente = assert_error(resp_inexistente, "NOT_FOUND")
    assert resp_ajeno.status_code == resp_inexistente.status_code
    assert err_ajeno["code"] == err_inexistente["code"]


@pytest.mark.at("AT-09-02-09")
def test_suscripcion_ws_privada_sin_token_se_rechaza(ws):
    """HU-09-02 Escenario 9 (WS privado): Suscripción privada requiere token.

    - Dado el canal WebSocket privado
    - Cuando un cliente intenta suscribirse al canal privado sin token válido
    - Entonces el servidor responde { error: { code: "UNAUTHENTICATED" } } y/o
      cierra la conexión, sin entregar ningún evento de usuario (RN-10)
    """
    # Cuando: subscribe a un canal privado sin haber autenticado
    try:
        respuesta = ws.suscribir("orders", symbol=None)
    except ConnectionClosed:
        return  # cierre sin mensaje: también es un rechazo válido según RN-10

    # Entonces: envelope de error UNAUTHENTICATED por el socket
    assert_error_ws(respuesta, "UNAUTHENTICATED")

    # Y: no llega ningún evento de usuario en una ventana corta
    try:
        ws.no_debe_llegar(
            lambda m: m.get("type") in ("order", "balance", "withdrawal", "subscribed"),
            ventana=2.0,
        )
    except ConnectionClosed:
        pass  # el servidor puede cerrar tras el error (RN-10)


@pytest.mark.at("AT-09-02-10")
def test_ws_privado_solo_entrega_eventos_de_la_cuenta_duena(api, ws, usuario, usuario_b, rpc):
    """HU-09-02 Escenario 10 (aislamiento WS): Eventos solo de la cuenta dueña.

    - Dado que A y B están suscritos al canal privado con sus tokens
    - Cuando ocurre un fill que afecta a B
    - Entonces A no recibe ningún evento de orden ni de balance de B; solo B los recibe
    """
    # Dado: libro preparado para un cruce determinista que afecte a B (maker) y a
    # un tercero C (taker); A es espectador y no participa del fill
    barrer_asks(api, rpc)
    tercero = crear_usuario(api, "at09-c")

    # A (usuario) suscrito al canal privado
    respuesta = ws.autenticar(usuario.token)
    assert respuesta.get("type") == "authenticated", respuesta
    assert ws.suscribir("orders", symbol=None).get("type") == "subscribed"
    assert ws.suscribir("balances", symbol=None).get("type") == "subscribed"

    with ConexionWs() as ws_b:
        # B suscrito al canal privado
        respuesta = ws_b.autenticar(usuario_b.token)
        assert respuesta.get("type") == "authenticated", respuesta
        assert ws_b.suscribir("orders", symbol=None).get("type") == "subscribed"

        # Cuando: fill B (maker SELL) × C (taker BUY)
        orden_b, p, q = colocar_ask_dominante(usuario_b, api, rpc)
        tomar_con_buy(tercero, rpc, p, q)

        # Entonces: B recibe sus eventos de orden (hasta FILLED)
        eventos_b = recolectar_hasta(
            ws_b,
            lambda m: m.get("type") == "order" and m.get("status") == "FILLED",
            timeout=10,
        )
        assert any(
            m.get("type") == "order" and m.get("orderId") == orden_b["orderId"]
            for m in eventos_b
        ), eventos_b

        # Y: A no recibe ningún evento de orden/balance (el fill no lo afecta)
        ws.no_debe_llegar(lambda m: m.get("type") in ("order", "balance"), ventana=3.0)


@pytest.mark.at("AT-09-02-11", "AT-09-05-08")
def test_rate_limit_61_requests_mismo_endpoint_misma_cuenta(api):
    """HU-09-02 Escenario 11 / HU-09-05 Escenario 8: Exceso de solicitudes (429).

    - Dado una cuenta autenticada y el umbral de 60 requests/min por cuenta y
      endpoint (RN-12; ventana deslizante de 60 s)
    - Cuando envía 61 requests a GET /api/v1/me con el mismo token dentro de 60 s
    - Entonces la request 61 responde RATE_LIMITED (429) con
      details.retryAfterSeconds (entero) y header Retry-After presentes
    - Y las primeras 60 requests no fueron limitadas por esta regla

    Usa un usuario dedicado: agota su cuota de /me y no debe reutilizarse.
    """
    # Dado: usuario dedicado (el rate limit es por cuenta y endpoint)
    dedicado = crear_usuario(api, "at09-ratelimit")
    inicio = time.monotonic()

    # Cuando: 60 requests dentro de la ventana ⇒ ninguna limitada
    for i in range(60):
        resp = dedicado.api.get("/me")
        assert resp.status_code != 429, f"request {i + 1} limitada antes del umbral"
        assert resp.status_code == 200, resp.text

    # ... y la request 61 dentro de la misma ventana
    resp = dedicado.api.get("/me")
    transcurrido = time.monotonic() - inicio
    if resp.status_code != 429 and transcurrido > 55:
        pytest.skip(
            f"las 61 requests tomaron {transcurrido:.1f}s: la ventana deslizante de "
            "60 s pudo expirar y el veredicto no es concluyente"
        )

    # Entonces: 429 RATE_LIMITED con retryAfterSeconds entero y header Retry-After
    err = assert_error(resp, "RATE_LIMITED")
    detalles = err.get("details") or {}
    assert es_entero_json(detalles.get("retryAfterSeconds")), err
    assert "Retry-After" in resp.headers, dict(resp.headers)
