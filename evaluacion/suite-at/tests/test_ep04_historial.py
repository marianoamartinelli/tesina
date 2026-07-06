"""Épica 04 — HU-04-07 Consultar historial de órdenes: tests black-box.

Spec: spec/04-gestion-de-ordenes/HU-04-07-consultar-historial-de-ordenes.md
La consulta semántica "historial" se implementa sobre GET /orders con filtro
status en {FILLED, CANCELLED, REJECTED} y filtros de período `from`/`to`
(ver TODO-REVISAR 4 y 5 en comunes_ep04.py: la épica 09 no define parámetros
temporales para GET /orders; los nombres se toman de HU-09-01 RN-20).

TODO-REVISAR (AT-04-07-09): HU-04-07 RN-3 exige VALIDATION_ERROR para un filtro
`status=OPEN` en el historial, pero AT-09-01-07 usa GET /orders?status=OPEN con
respuesta 200 (misma ruta). Se asserta solo el caso no contradictorio
(status fuera de todo enum, p. ej. "FOO").
"""

import pytest

from helpers.errores import assert_error

from comunes_ep04 import (  # noqa: F401 (limpiador es fixture)
    NOTIONAL_MIN,
    P2000,
    Q_MIN,
    abiertas,
    alta_ok,
    assert_montos_de_orden,
    buscar_por_client_id,
    buscar_por_id,
    cancelar_ok,
    client_order_id,
    construir_trio_terminal,
    crear_filled,
    crear_rejected_sin_liquidez,
    cuerpo_orden,
    ejecutado_wei,
    fondear,
    historial,
    items_por_estado,
    limpiador,
    post_orden,
    requerir_lado_vacio,
    requerir_sin_asks_hasta,
)


def _dos_cancelled(usuario, rpc, api) -> tuple[dict, dict]:
    """Dos órdenes CANCELLED sucesivas (finalizadas en ese orden temporal)."""
    requerir_sin_asks_hasta(api, P2000)
    fondear(usuario, rpc, usdc_min=NOTIONAL_MIN)
    primera = alta_ok(usuario, cuerpo_orden("BUY", "LIMIT", P2000, Q_MIN), estado="OPEN")
    primera = cancelar_ok(usuario, primera["orderId"])
    segunda = alta_ok(usuario, cuerpo_orden("BUY", "LIMIT", P2000, Q_MIN), estado="OPEN")
    segunda = cancelar_ok(usuario, segunda["orderId"])
    return primera, segunda


@pytest.mark.at("AT-04-07-01")
def test_listar_historial_sin_filtros(usuario, usuario_b, rpc, api):
    """HU-04-07 Escenario 1: Listar historial sin filtros."""
    # Dado un trader con órdenes FILLED, CANCELLED y REJECTED
    trio = construir_trio_terminal(usuario, usuario_b, rpc, api)

    # Cuando consulta su historial (sin filtro de período; estados terminales)
    items = {i["orderId"]: i for i in historial(usuario)}

    # Entonces recibe las tres órdenes con su status, executedQty y marcas temporales
    assert set(items) == {orden["orderId"] for orden in trio.values()}
    for clave, orden in trio.items():
        item = items[orden["orderId"]]
        assert item["status"] == orden["status"], (clave, item)
        assert ejecutado_wei(item) == ejecutado_wei(orden)
        assert isinstance(item["createdAt"], str) and item["createdAt"]
        assert isinstance(item["updatedAt"], str) and item["updatedAt"]


@pytest.mark.at("AT-04-07-02")
def test_historial_filtrado_solo_filled(usuario, usuario_b, rpc, api):
    """HU-04-07 Escenario 2 (filtro): Solo FILLED."""
    # Dado un trader con órdenes FILLED, CANCELLED y REJECTED
    trio = construir_trio_terminal(usuario, usuario_b, rpc, api)

    # Cuando consulta su historial filtrando status=FILLED
    items = items_por_estado(usuario, "FILLED")

    # Entonces recibe únicamente las órdenes FILLED (RN-3, RN-5)
    assert all(i["status"] == "FILLED" for i in items)
    ids = {i["orderId"] for i in items}
    assert trio["filled"]["orderId"] in ids
    assert trio["cancelled"]["orderId"] not in ids
    assert trio["rejected"]["orderId"] not in ids


@pytest.mark.at("AT-04-07-03")
def test_historial_filtrado_por_periodo(usuario, rpc, api):
    """HU-04-07 Escenario 3 (filtro): Por período."""
    # Dado órdenes finalizadas en distintos momentos (dos CANCELLED sucesivas)
    primera, segunda = _dos_cancelled(usuario, rpc, api)

    # Cuando consulta con from/to que cubren solo la finalización de la segunda
    # (el rango [from, to] es cerrado en ambos extremos, RN-4)
    acotado = historial(
        usuario, {"from": segunda["updatedAt"], "to": segunda["updatedAt"]}
    )

    # Entonces recibe la orden cuya finalización cae dentro del rango inclusivo
    assert buscar_por_id(acotado, segunda["orderId"]) is not None
    # Y la primera queda fuera (si sus marcas de finalización difieren)
    if primera["updatedAt"] != segunda["updatedAt"]:
        assert buscar_por_id(acotado, primera["orderId"]) is None

    # Y un rango que cubre ambas finalizaciones (extremos inclusive) trae las dos
    completo = historial(
        usuario, {"from": primera["updatedAt"], "to": segunda["updatedAt"]}
    )
    assert buscar_por_id(completo, primera["orderId"]) is not None
    assert buscar_por_id(completo, segunda["orderId"]) is not None


@pytest.mark.at("AT-04-07-04")
def test_historial_filtro_combinado_estado_y_periodo(usuario, usuario_b, rpc, api):
    """HU-04-07 Escenario 4 (filtro combinado): Estado + período."""
    # Dado órdenes FILLED y CANCELLED finalizadas en fechas cercanas
    filled = crear_filled(usuario, usuario_b, rpc, api)
    requerir_sin_asks_hasta(api, P2000)
    fondear(usuario, rpc, usdc_min=NOTIONAL_MIN)
    abierta = alta_ok(usuario, cuerpo_orden("BUY", "LIMIT", P2000, Q_MIN), estado="OPEN")
    cancelled = cancelar_ok(usuario, abierta["orderId"])

    # Cuando consulta status=CANCELLED con un período que cubre su finalización
    items = items_por_estado(
        usuario,
        "CANCELLED",
        {"from": cancelled["updatedAt"], "to": cancelled["updatedAt"]},
    )

    # Entonces recibe solo las CANCELLED finalizadas dentro del período (RN-5):
    # los filtros se combinan con AND
    assert all(i["status"] == "CANCELLED" for i in items)
    assert buscar_por_id(items, cancelled["orderId"]) is not None
    assert buscar_por_id(items, filled["orderId"]) is None


@pytest.mark.at("AT-04-07-05")
def test_historial_no_incluye_abiertas(usuario, rpc, api, limpiador):
    """HU-04-07 Escenario 5 (exclusión): No incluye abiertas."""
    # Dado un trader con una orden OPEN además de una terminal (CANCELLED)
    requerir_sin_asks_hasta(api, P2000)
    fondear(usuario, rpc, usdc_min=2 * NOTIONAL_MIN)
    terminal = alta_ok(usuario, cuerpo_orden("BUY", "LIMIT", P2000, Q_MIN), estado="OPEN")
    terminal = cancelar_ok(usuario, terminal["orderId"])
    abierta = alta_ok(usuario, cuerpo_orden("BUY", "LIMIT", P2000, Q_MIN), estado="OPEN")
    limpiador.registrar(usuario, abierta["orderId"])

    # Cuando consulta su historial
    items = historial(usuario)

    # Entonces las abiertas no aparecen (RN-1); la terminal sí
    ids = {i["orderId"] for i in items}
    assert abierta["orderId"] not in ids
    assert terminal["orderId"] in ids


@pytest.mark.at("AT-04-07-06")
def test_historial_no_devuelve_ordenes_ajenas(usuario, usuario_b, rpc, api):
    """HU-04-07 Escenario 6 (aislamiento): No devuelve órdenes ajenas."""
    # Dado un trader A con historial y un trader B con historial
    requerir_sin_asks_hasta(api, P2000)
    fondear(usuario, rpc, usdc_min=NOTIONAL_MIN)
    orden_a = alta_ok(usuario, cuerpo_orden("BUY", "LIMIT", P2000, Q_MIN), estado="OPEN")
    orden_a = cancelar_ok(usuario, orden_a["orderId"])
    fondear(usuario_b, rpc, usdc_min=NOTIONAL_MIN)
    orden_b = alta_ok(usuario_b, cuerpo_orden("BUY", "LIMIT", P2000, Q_MIN), estado="OPEN")
    orden_b = cancelar_ok(usuario_b, orden_b["orderId"])

    # Cuando A consulta su historial
    ids_de_a = {i["orderId"] for i in historial(usuario)}

    # Entonces recibe solo el suyo (RN-2)
    assert orden_a["orderId"] in ids_de_a
    assert orden_b["orderId"] not in ids_de_a


@pytest.mark.at("AT-04-07-07")
def test_historial_paginado_sin_duplicados_ni_omisiones(usuario, rpc, api):
    """HU-04-07 Escenario 7 (paginación): Resultado estable y paginado."""
    # Dado un trader con 3 órdenes terminales (CANCELLED sucesivas)
    requerir_sin_asks_hasta(api, P2000)
    fondear(usuario, rpc, usdc_min=NOTIONAL_MIN)  # la reserva se libera al cancelar
    esperadas = set()
    for _ in range(3):
        orden = alta_ok(usuario, cuerpo_orden("BUY", "LIMIT", P2000, Q_MIN), estado="OPEN")
        cancelar_ok(usuario, orden["orderId"])
        esperadas.add(orden["orderId"])

    # Cuando pagina con el orden por defecto (finalización desc)
    vistos: list[str] = []
    cursor = None
    for _ in range(10):
        params = {"status": "CANCELLED", "limit": 2}
        if cursor:
            params["cursor"] = cursor
        resp = usuario.api.get("/orders", params=params)
        assert resp.status_code == 200, resp.text
        cuerpo = resp.json()
        assert len(cuerpo["items"]) <= 2
        vistos.extend(i["orderId"] for i in cuerpo["items"])
        cursor = cuerpo.get("nextCursor")
        if not cursor:
            break

    # Entonces cada orden aparece exactamente una vez, sin duplicados ni
    # omisiones entre páginas (RN-6, RN-7)
    assert sorted(vistos) == sorted(esperadas)
    assert len(vistos) == len(set(vistos)) == 3


@pytest.mark.at("AT-04-07-08")
def test_historial_vacio_devuelve_lista_vacia(usuario):
    """HU-04-07 Escenario 8 (borde): Historial vacío."""
    # Dado un trader sin órdenes terminales (usuario fresco)
    # Cuando consulta su historial
    # Entonces recibe una lista vacía (no un error): cada consulta asserta 200
    assert historial(usuario) == []


@pytest.mark.at("AT-04-07-09")
def test_historial_con_filtro_de_estado_invalido(usuario):
    """HU-04-07 Escenario 9 (error): Filtro de estado inválido."""
    # Cuando consulta con status=FOO (fuera de todo enum de estados)
    resp = usuario.api.get("/orders", params={"status": "FOO"})

    # Entonces se rechaza con VALIDATION_ERROR (422) y details.issues (RN-3)
    err = assert_error(resp, "VALIDATION_ERROR")
    assert err.get("details", {}).get("issues"), err
    # (el caso status=OPEN contradice AT-09-01-07 y no se asserta acá; ver
    # TODO-REVISAR en el docstring del módulo)


@pytest.mark.at("AT-04-07-10")
def test_historial_con_rango_temporal_invalido(usuario):
    """HU-04-07 Escenario 10 (error): Rango temporal inválido."""
    # Cuando consulta con from posterior a to
    resp = usuario.api.get(
        "/orders",
        params={
            "status": "FILLED",
            "from": "2026-01-02T00:00:00Z",
            "to": "2026-01-01T00:00:00Z",
        },
    )
    # Entonces se rechaza con VALIDATION_ERROR (422) (RN-4)
    assert_error(resp, "VALIDATION_ERROR")

    # Y con fechas mal formadas también
    resp = usuario.api.get(
        "/orders", params={"status": "FILLED", "from": "no-es-una-fecha"}
    )
    assert_error(resp, "VALIDATION_ERROR")


@pytest.mark.at("AT-04-07-11")
def test_consultar_historial_sin_autenticacion(api):
    """HU-04-07 Escenario 11 (error): No autenticado."""
    # Dado un cliente sin credencial válida
    # Cuando consulta el historial
    resp = api.get("/orders", params={"status": "FILLED"})

    # Entonces se rechaza con UNAUTHENTICATED (401) (RN-9)
    assert_error(resp, "UNAUTHENTICATED")


@pytest.mark.at("AT-04-07-12")
def test_historial_montos_string_y_resultado_estable(usuario, usuario_b, rpc, api):
    """HU-04-07 Escenario 12 (serialización + inmutabilidad): Montos string y estable."""
    # Dado una orden FILLED con executedQty = 0.005 ETH
    filled = crear_filled(usuario, usuario_b, rpc, api)

    # Cuando consulta el historial dos veces en momentos distintos
    primero = buscar_por_id(items_por_estado(usuario, "FILLED"), filled["orderId"])
    segundo = buscar_por_id(items_por_estado(usuario, "FILLED"), filled["orderId"])

    # Entonces los montos viajan como string ^(0|[1-9][0-9]*)$ (RN-8)
    assert primero is not None
    assert_montos_de_orden(primero)
    assert ejecutado_wei(primero) == Q_MIN
    # Y la orden terminal aparece idéntica en ambas consultas (RN-10:
    # las órdenes terminales son inmutables)
    assert primero == segundo


@pytest.mark.at("AT-04-07-13")
def test_rechazos_de_matching_aparecen_como_rejected(usuario, api, rpc):
    """HU-04-07 Escenario 13 (rechazos persistidos): Self-trade y sin-liquidez."""
    # Dado una orden rechazada por SELF_TRADE_BLOCKED: bid propio como única
    # liquidez y una SELL MARKET propia que lo tiene en su rango consumible
    requerir_lado_vacio(api, "bids")
    requerir_sin_asks_hasta(api, P2000)
    fondear(usuario, rpc, eth_wei=Q_MIN, usdc_min=NOTIONAL_MIN)
    bid = alta_ok(usuario, cuerpo_orden("BUY", "LIMIT", P2000, Q_MIN), estado="OPEN")
    cid_self_trade = client_order_id("stp")
    resp = post_orden(
        usuario, cuerpo_orden("SELL", "MARKET", quantity_wei=Q_MIN, client_id=cid_self_trade)
    )
    assert_error(resp, "SELF_TRADE_BLOCKED")
    # Y otra rechazada por MARKET_NO_LIQUIDITY (bids vacíos tras cancelar el bid)
    cancelar_ok(usuario, bid["orderId"])
    cid_sin_liquidez = client_order_id("noliq")
    rechazada = crear_rejected_sin_liquidez(usuario, api, client_id=cid_sin_liquidez)

    # Cuando consulta su historial con status=REJECTED
    items = items_por_estado(usuario, "REJECTED")

    # Entonces ambas aparecen con status="REJECTED", preservando la trazabilidad
    # de auditoría (RN-12, HU-04-05 RN-5, RE-12)
    por_self_trade = buscar_por_client_id(items, cid_self_trade)
    por_sin_liquidez = buscar_por_client_id(items, cid_sin_liquidez)
    assert por_self_trade is not None and por_self_trade["status"] == "REJECTED"
    assert por_sin_liquidez is not None and por_sin_liquidez["status"] == "REJECTED"
    assert por_sin_liquidez["orderId"] == rechazada["orderId"]


@pytest.mark.at("AT-04-07-14")
def test_rechazos_de_validacion_y_fondos_no_aparecen(usuario):
    """HU-04-07 Escenario 14 (rechazos no persistidos): validación/fondos."""
    # Dado intentos fallidos por INVALID_PRICE_TICK, BELOW_MIN_NOTIONAL e
    # INSUFFICIENT_FUNDS (usuario fresco sin fondos: la orden válida en forma
    # y reglas del par cae en fondos, paso 7)
    resp = post_orden(usuario, cuerpo_orden("BUY", "LIMIT", 2_000_005_000, Q_MIN))
    assert_error(resp, "INVALID_PRICE_TICK")
    resp = post_orden(usuario, cuerpo_orden("BUY", "LIMIT", P2000, 100_000_000_000_000))
    assert_error(resp, "BELOW_MIN_NOTIONAL")
    resp = post_orden(usuario, cuerpo_orden("BUY", "LIMIT", P2000, Q_MIN))
    assert_error(resp, "INSUFFICIENT_FUNDS")

    # Cuando consulta su historial
    # Entonces ninguno de esos intentos aparece como orden: no se persisten
    # (RN-12, HU-04-05 RN-5, RE-12)
    assert historial(usuario) == []
    assert abiertas(usuario) == []
