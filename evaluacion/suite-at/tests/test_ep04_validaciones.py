"""Épica 04 — HU-04-03 Validaciones de orden: tests de aceptación black-box.

Spec: spec/04-gestion-de-ordenes/HU-04-03-validaciones-de-orden.md
Cubre los disparadores exactos de cada error de validación y la precedencia
determinista (RE-4 / modelo-de-errores §4). Los usuarios frescos arrancan con
balances en cero: los tests de validación pura no fondean (más rápido y el
resultado es el mismo, porque las validaciones preceden a fondos).
"""

import pytest

from helpers.errores import assert_error

from comunes_ep04 import (  # noqa: F401 (limpiador es fixture)
    ETH_1,
    NOTIONAL_MIN,
    P2000,
    Q_MIN,
    abiertas,
    alta_ok,
    assert_balances,
    bloqueado,
    cuerpo_orden,
    detalle,
    disponible,
    ejecutado_wei,
    fondear,
    historial,
    limpiador,
    post_orden,
    requerir_sin_asks_hasta,
    requerir_zona_limpia,
)


@pytest.mark.at("AT-04-03-01")
def test_precedencia_tick_gana_sobre_fondos(usuario):
    """HU-04-03 Escenario 1: Precedencia — tick gana sobre fondos."""
    # Dado un trader con disponible(USDC) = 0 (usuario fresco, sin fondeo)
    assert disponible(usuario, "USDC") == 0

    # Cuando coloca una orden con precio fuera de tick y sin fondos
    resp = post_orden(usuario, cuerpo_orden("BUY", "LIMIT", 2_000_005_000, ETH_1))

    # Entonces se reporta solo INVALID_PRICE_TICK: la regla del par (paso 4)
    # precede a fondos (paso 7) y no se reporta INSUFFICIENT_FUNDS (RN-1)
    assert_error(resp, "INVALID_PRICE_TICK")


@pytest.mark.at("AT-04-03-02")
def test_lado_invalido(usuario):
    """HU-04-03 Escenario 2 (error): Lado inválido."""
    # Cuando coloca una orden con side="LONG" (resto del payload válido)
    resp = post_orden(usuario, cuerpo_orden("LONG", "LIMIT", P2000, ETH_1))

    # Entonces se rechaza con INVALID_SIDE (422), details.side (RN-3)
    err = assert_error(resp, "INVALID_SIDE")
    assert err["details"]["side"] == "LONG", err


@pytest.mark.at("AT-04-03-03")
def test_tipo_de_orden_invalido(usuario):
    """HU-04-03 Escenario 3 (error): Tipo de orden inválido."""
    # Cuando coloca una orden con type="STOP"
    resp = post_orden(usuario, cuerpo_orden("BUY", "STOP", P2000, ETH_1))

    # Entonces se rechaza con INVALID_ORDER_TYPE (422), details.type (RN-4)
    err = assert_error(resp, "INVALID_ORDER_TYPE")
    assert err["details"]["type"] == "STOP", err


@pytest.mark.at("AT-04-03-04")
def test_limit_sin_precio(usuario):
    """HU-04-03 Escenario 4 (error): Limit sin precio."""
    # Cuando coloca BUY LIMIT con quantityWei pero sin priceMin
    resp = post_orden(usuario, cuerpo_orden("BUY", "LIMIT", quantity_wei=ETH_1))

    # Entonces se rechaza con PRICE_REQUIRED (422) (RN-5)
    assert_error(resp, "PRICE_REQUIRED")


@pytest.mark.at("AT-04-03-05")
def test_market_con_precio(usuario):
    """HU-04-03 Escenario 5 (error): Market con precio."""
    # Cuando coloca BUY MARKET con quoteOrderQty y priceMin
    resp = post_orden(
        usuario,
        cuerpo_orden("BUY", "MARKET", price_min=P2000, quote_order_qty=2_000_000_000),
    )

    # Entonces se rechaza con PRICE_NOT_ALLOWED (422) (RN-5)
    assert_error(resp, "PRICE_NOT_ALLOWED")


@pytest.mark.at("AT-04-03-06")
def test_precio_fuera_de_tick(usuario):
    """HU-04-03 Escenario 6 (error): Precio fuera de tick."""
    # Cuando coloca LIMIT con priceMin="2000005000" (no múltiplo de 10000)
    resp = post_orden(usuario, cuerpo_orden("BUY", "LIMIT", 2_000_005_000, ETH_1))

    # Entonces se rechaza con INVALID_PRICE_TICK (422) y details exactos (RN-6)
    err = assert_error(resp, "INVALID_PRICE_TICK")
    assert err["details"]["priceMin"] == "2000005000", err
    assert err["details"]["tickSize"] == "10000", err


@pytest.mark.at("AT-04-03-07")
def test_cantidad_fuera_de_lot(usuario):
    """HU-04-03 Escenario 7 (error): Cantidad fuera de lot."""
    # Cuando coloca LIMIT con quantityWei="50000000000000" (0.00005 ETH)
    resp = post_orden(usuario, cuerpo_orden("BUY", "LIMIT", P2000, 50_000_000_000_000))

    # Entonces se rechaza con INVALID_LOT_SIZE (422) y details exactos (RN-7)
    err = assert_error(resp, "INVALID_LOT_SIZE")
    assert err["details"]["quantityWei"] == "50000000000000", err
    assert err["details"]["lotSize"] == "100000000000000", err


@pytest.mark.at("AT-04-03-08")
def test_notional_por_debajo_del_minimo(usuario):
    """HU-04-03 Escenario 8 (error): Notional por debajo del mínimo."""
    # Cuando coloca LIMIT 0.0001 ETH @ 2000 (notional 200000 = 0.2 USDC)
    resp = post_orden(usuario, cuerpo_orden("BUY", "LIMIT", P2000, 100_000_000_000_000))

    # Entonces se rechaza con BELOW_MIN_NOTIONAL (422) y details exactos (RN-8)
    err = assert_error(resp, "BELOW_MIN_NOTIONAL")
    assert err["details"]["actualNotional"] == "200000", err
    assert err["details"]["minNotional"] == "10000000", err


@pytest.mark.at("AT-04-03-09")
def test_montos_no_enteros_o_con_patron_invalido(usuario):
    """HU-04-03 Escenario 9 (error): Monto no entero / float / patrón inválido."""
    # Cuando coloca LIMIT con priceMin="2000.50" y quantityWei="1e18"
    resp = post_orden(
        usuario, cuerpo_orden("BUY", "LIMIT", price_min="2000.50", quantity_wei="1e18")
    )

    # Entonces se rechaza con VALIDATION_ERROR (422) y details.issues lista los
    # campos que no matchean ^(0|[1-9][0-9]*)$ (RN-2)
    err = assert_error(resp, "VALIDATION_ERROR")
    issues = err.get("details", {}).get("issues")
    assert isinstance(issues, list) and issues, err
    # (que ningún monto cruce la API como float lo garantiza el propio rechazo)


@pytest.mark.at("AT-04-03-10")
def test_precio_cero_cae_en_tick(usuario):
    """HU-04-03 Escenario 10 (borde): Precio cero ⇒ tick."""
    # Cuando coloca LIMIT con priceMin="0" (matchea el patrón pero no es positivo)
    resp = post_orden(usuario, cuerpo_orden("BUY", "LIMIT", price_min="0", quantity_wei=ETH_1))

    # Entonces se rechaza con INVALID_PRICE_TICK (422) (RN-6, RN-9)
    assert_error(resp, "INVALID_PRICE_TICK")


@pytest.mark.at("AT-04-03-11")
def test_cero_a_la_izquierda_rechazado(usuario):
    """HU-04-03 Escenario 11 (borde): Cero a la izquierda rechazado."""
    # Cuando coloca una orden con priceMin="02000000000"
    resp = post_orden(
        usuario, cuerpo_orden("BUY", "LIMIT", price_min="02000000000", quantity_wei=ETH_1)
    )

    # Entonces se rechaza con VALIDATION_ERROR (422): no matchea el patrón (RN-2)
    assert_error(resp, "VALIDATION_ERROR")


@pytest.mark.at("AT-04-03-12")
def test_precedencia_idempotencia_gana_sobre_fondos(usuario, rpc, api, limpiador):
    """HU-04-03 Escenario 12 (precedencia): Idempotencia gana sobre fondos."""
    # Dado un trader que ya usó clientOrderId="dup-1" y ahora tiene disponible(USDC) = 0
    requerir_sin_asks_hasta(api, P2000)
    fondear(usuario, rpc, usdc_min=NOTIONAL_MIN)  # 10 USDC, se reservan enteros
    orden = alta_ok(
        usuario, cuerpo_orden("BUY", "LIMIT", P2000, Q_MIN, client_id="dup-1"),
        estado="OPEN",
    )
    limpiador.registrar(usuario, orden["orderId"])
    assert disponible(usuario, "USDC") == 0

    # Cuando reenvía una orden válida en forma con clientOrderId="dup-1"
    resp = post_orden(usuario, cuerpo_orden("BUY", "LIMIT", P2000, Q_MIN, client_id="dup-1"))

    # Entonces se reporta DUPLICATE_CLIENT_ORDER_ID (409, paso 5) y no
    # INSUFFICIENT_FUNDS (paso 7) (RN-1, RN-10)
    assert_error(resp, "DUPLICATE_CLIENT_ORDER_ID")


@pytest.mark.at("AT-04-03-13")
def test_precedencia_fondos_gana_sobre_matching(usuario, usuario_b, rpc, api, limpiador):
    """HU-04-03 Escenario 13 (precedencia): Fondos gana sobre matching."""
    # Dado un trader con disponible(USDC) = 0 y un ask resting ajeno cruzable
    requerir_zona_limpia(api, P2000)
    fondear(usuario_b, rpc, eth_wei=Q_MIN)
    ask = alta_ok(usuario_b, cuerpo_orden("SELL", "LIMIT", P2000, Q_MIN), estado="OPEN")
    limpiador.registrar(usuario_b, ask["orderId"])
    assert disponible(usuario, "USDC") == 0

    # Cuando coloca una BUY válida en forma y reglas del par pero sin fondos
    resp = post_orden(usuario, cuerpo_orden("BUY", "LIMIT", P2000, Q_MIN))

    # Entonces se reporta INSUFFICIENT_FUNDS (422, paso 7) y no se evalúa el
    # matching (paso 8): el ask ajeno queda intacto (RN-1)
    assert_error(resp, "INSUFFICIENT_FUNDS")
    assert detalle(usuario_b, ask["orderId"])["status"] == "OPEN"
    assert ejecutado_wei(detalle(usuario_b, ask["orderId"])) == 0


@pytest.mark.at("AT-04-03-14")
def test_no_autenticado_precede_a_toda_validacion(api):
    """HU-04-03 Escenario 14 (error): No autenticado."""
    # Dado un cliente sin credencial válida
    # Cuando intenta colocar cualquier orden (incluso con payload inválido)
    resp = api.post("/orders", json=cuerpo_orden("BUY", "LIMIT", 2_000_005_000, ETH_1))

    # Entonces se rechaza con UNAUTHENTICATED (401) antes de cualquier otra
    # validación (RN-1 paso 1: no responde VALIDATION_ERROR ni INVALID_PRICE_TICK)
    assert_error(resp, "UNAUTHENTICATED")


@pytest.mark.at("AT-04-03-15")
def test_rechazo_de_validacion_no_toca_balances(usuario, rpc):
    """HU-04-03 Escenario 15 (sin efectos colaterales): Rechazo no toca balances."""
    # Dado un trader con disponible(USDC) = 5000000000 y bloqueado(USDC) = 0
    fondear(usuario, rpc, usdc_min=5_000_000_000)

    # Cuando coloca una orden que falla una validación (INVALID_PRICE_TICK)
    resp = post_orden(usuario, cuerpo_orden("BUY", "LIMIT", 2_000_005_000, ETH_1))
    assert_error(resp, "INVALID_PRICE_TICK")

    # Entonces los balances quedan exactamente igual (RN-11, INV-2)
    assert_balances(usuario, "USDC", disp=5_000_000_000, blk=0)

    # Y no se crea ninguna orden abierta ni se emite fill; el rechazo de
    # validación tampoco se persiste como orden (RE-12)
    assert abiertas(usuario) == []
    assert historial(usuario) == []


@pytest.mark.at("AT-04-03-16")
def test_cantidad_cero_cae_en_lot(usuario):
    """HU-04-03 Escenario 16 (borde): Cantidad cero ⇒ lot."""
    # Cuando coloca LIMIT con quantityWei="0" (matchea el patrón pero no es positiva)
    resp = post_orden(usuario, cuerpo_orden("BUY", "LIMIT", P2000, quantity_wei="0"))

    # Entonces se rechaza con INVALID_LOT_SIZE (422) (RN-7, RN-9)
    assert_error(resp, "INVALID_LOT_SIZE")


@pytest.mark.at("AT-04-03-17")
def test_monto_negativo_rechazado(usuario):
    """HU-04-03 Escenario 17 (borde): Monto negativo rechazado."""
    # Cuando coloca una orden con quantityWei="-100"
    resp = post_orden(usuario, cuerpo_orden("BUY", "LIMIT", P2000, quantity_wei="-100"))

    # Entonces se rechaza con VALIDATION_ERROR (422): no matchea el patrón (RN-2)
    assert_error(resp, "VALIDATION_ERROR")


@pytest.mark.at("AT-04-03-18")
def test_operar_orden_ajena_no_expone_unauthorized(usuario, usuario_b, rpc, api, limpiador):
    """HU-04-03 Escenario 18 (autorización): Operar sobre otra cuenta no expone UNAUTHORIZED."""
    # Dado un trader A autenticado y una orden de la cuenta B
    requerir_sin_asks_hasta(api, P2000)
    fondear(usuario_b, rpc, usdc_min=NOTIONAL_MIN)
    orden_b = alta_ok(usuario_b, cuerpo_orden("BUY", "LIMIT", P2000, Q_MIN), estado="OPEN")
    limpiador.registrar(usuario_b, orden_b["orderId"])

    # Cuando A intenta referir/operar la orden de B (el alta es siempre en
    # nombre de A: no hay parámetro accountId)
    resp_get = usuario.api.get(f"/orders/{orden_b['orderId']}")
    resp_del = usuario.api.delete(f"/orders/{orden_b['orderId']}")

    # Entonces el acceso a un recurso ajeno devuelve ORDER_NOT_FOUND (404, RE-7),
    # no UNAUTHORIZED (403, reservado a autorizaciones de cuenta de la épica 01)
    assert_error(resp_get, "ORDER_NOT_FOUND")
    assert_error(resp_del, "ORDER_NOT_FOUND")
    # Y la orden de B queda intacta
    assert detalle(usuario_b, orden_b["orderId"])["status"] == "OPEN"


@pytest.mark.at("AT-04-03-19")
def test_dos_cuentas_pueden_usar_el_mismo_client_order_id(usuario, usuario_b, rpc, api, limpiador):
    """HU-04-03 Escenario 19 (idempotencia, alcance por cuenta): mismo clientOrderId."""
    # Dado un trader A con una orden exitosa con clientOrderId="shared"
    requerir_sin_asks_hasta(api, P2000)
    fondear(usuario, rpc, usdc_min=NOTIONAL_MIN)
    orden_a = alta_ok(
        usuario, cuerpo_orden("BUY", "LIMIT", P2000, Q_MIN, client_id="shared"),
        estado="OPEN",
    )
    limpiador.registrar(usuario, orden_a["orderId"])

    # Cuando un trader B coloca una orden válida con el mismo clientOrderId="shared"
    fondear(usuario_b, rpc, usdc_min=NOTIONAL_MIN)
    orden_b = alta_ok(
        usuario_b, cuerpo_orden("BUY", "LIMIT", P2000, Q_MIN, client_id="shared"),
        estado="OPEN",
    )
    limpiador.registrar(usuario_b, orden_b["orderId"])

    # Entonces la orden de B se acepta sin DUPLICATE_CLIENT_ORDER_ID: el índice
    # de unicidad es (accountId, clientOrderId), no global (RN-10, RE-5)
    assert orden_b["orderId"] != orden_a["orderId"]
