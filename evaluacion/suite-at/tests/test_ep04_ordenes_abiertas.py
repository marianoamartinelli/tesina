"""Épica 04 — HU-04-06 Consultar órdenes abiertas: tests black-box.

Spec: spec/04-gestion-de-ordenes/HU-04-06-consultar-ordenes-abiertas.md
La consulta semántica "abiertas" se implementa sobre GET /orders con filtro
status en {OPEN, PARTIALLY_FILLED} (ver TODO-REVISAR 5 en comunes_ep04.py).

TODO-REVISAR: el desempate del orden por defecto difiere entre épicas
(HU-04-06 RN-4: orderId ascendente; HU-09-01 RN-8: orderId descendente); los
tests no assertan la dirección del desempate, solo createdAt descendente y la
estabilidad de la paginación.
"""

import pytest

from helpers.errores import assert_error
from helpers.montos import es_monto_valido

from comunes_ep04 import (  # noqa: F401 (limpiador es fixture)
    ETH_1,
    NOTIONAL_MIN,
    P2000,
    Q_MIN,
    abiertas,
    alta_ok,
    assert_montos_de_orden,
    balances,
    cantidad_en_nivel,
    construir_trio_terminal,
    cuerpo_orden,
    detalle,
    ejecutado_wei,
    fondear,
    limpiador,
    remanente_wei,
    requerir_sin_asks_hasta,
    requerir_zona_limpia,
)


@pytest.mark.at("AT-04-06-01")
def test_listar_abiertas_con_estado_y_remanente(usuario, usuario_b, rpc, api, limpiador):
    """HU-04-06 Escenario 1: Listar órdenes abiertas con estado y remanente."""
    # Dado un trader con una orden OPEN (1 ETH) y una PARTIALLY_FILLED
    # (1 ETH con executedQty=0.4 ETH, llenada por un taker ajeno)
    requerir_zona_limpia(api, P2000)
    requerir_sin_asks_hasta(api, 1_900_000_000)
    fondear(usuario, rpc, usdc_min=3_900_000_000)  # 1900 + 2000 USDC de reservas
    abierta = alta_ok(
        usuario, cuerpo_orden("BUY", "LIMIT", 1_900_000_000, ETH_1), estado="OPEN"
    )
    limpiador.registrar(usuario, abierta["orderId"])
    parcial = alta_ok(usuario, cuerpo_orden("BUY", "LIMIT", P2000, ETH_1), estado="OPEN")
    limpiador.registrar(usuario, parcial["orderId"])
    fondear(usuario_b, rpc, eth_wei=400_000_000_000_000_000)
    alta_ok(
        usuario_b,
        cuerpo_orden("SELL", "LIMIT", P2000, 400_000_000_000_000_000),
        estado="FILLED",
    )

    # Cuando consulta sus órdenes abiertas
    items = {i["orderId"]: i for i in abiertas(usuario)}

    # Entonces recibe ambas órdenes con status, executedQty y remainingQty correctos
    assert set(items) == {abierta["orderId"], parcial["orderId"]}
    assert items[abierta["orderId"]]["status"] == "OPEN"
    assert ejecutado_wei(items[abierta["orderId"]]) == 0
    assert remanente_wei(items[abierta["orderId"]]) == ETH_1
    # Y la PARTIALLY_FILLED muestra remainingQty="600000000000000000" (RN-3)
    assert items[parcial["orderId"]]["status"] == "PARTIALLY_FILLED"
    assert ejecutado_wei(items[parcial["orderId"]]) == 400_000_000_000_000_000
    assert remanente_wei(items[parcial["orderId"]]) == 600_000_000_000_000_000


@pytest.mark.at("AT-04-06-02")
def test_sin_ordenes_abiertas_devuelve_lista_vacia(usuario):
    """HU-04-06 Escenario 2 (borde): Sin órdenes abiertas."""
    # Dado un trader sin órdenes activas (usuario fresco)
    # Cuando consulta sus órdenes abiertas
    # Entonces recibe una lista vacía (no un error): abiertas() asserta 200
    assert abiertas(usuario) == []


@pytest.mark.at("AT-04-06-03")
def test_abiertas_excluye_ordenes_terminales(usuario, usuario_b, rpc, api, limpiador):
    """HU-04-06 Escenario 3 (filtro): Excluye órdenes terminales."""
    # Dado un trader con órdenes FILLED, CANCELLED y REJECTED, además de una OPEN
    trio = construir_trio_terminal(usuario, usuario_b, rpc, api, usdc_extra=15_200_000)
    abierta = alta_ok(
        usuario,
        cuerpo_orden("BUY", "LIMIT", 1_900_000_000, 8_000_000_000_000_000),  # 0.008 @ 1900
        estado="OPEN",
    )
    limpiador.registrar(usuario, abierta["orderId"])

    # Cuando consulta sus órdenes abiertas
    items = abiertas(usuario)

    # Entonces recibe solo la orden OPEN; ninguna terminal aparece (RN-1)
    assert [i["orderId"] for i in items] == [abierta["orderId"]]
    ids_terminales = {orden["orderId"] for orden in trio.values()}
    assert ids_terminales.isdisjoint({i["orderId"] for i in items})


@pytest.mark.at("AT-04-06-04")
def test_abiertas_no_devuelve_ordenes_ajenas(usuario, usuario_b, rpc, api, limpiador):
    """HU-04-06 Escenario 4 (aislamiento): No devuelve órdenes ajenas."""
    # Dado un trader A con una orden OPEN y un trader B con otra orden OPEN
    requerir_sin_asks_hasta(api, P2000)
    fondear(usuario, rpc, usdc_min=NOTIONAL_MIN)
    orden_a = alta_ok(usuario, cuerpo_orden("BUY", "LIMIT", P2000, Q_MIN), estado="OPEN")
    limpiador.registrar(usuario, orden_a["orderId"])
    fondear(usuario_b, rpc, usdc_min=NOTIONAL_MIN)
    orden_b = alta_ok(usuario_b, cuerpo_orden("BUY", "LIMIT", P2000, Q_MIN), estado="OPEN")
    limpiador.registrar(usuario_b, orden_b["orderId"])

    # Cuando A consulta sus órdenes abiertas
    ids_de_a = {i["orderId"] for i in abiertas(usuario)}

    # Entonces recibe solo la suya; la de B no aparece (RN-2, RE-7)
    assert ids_de_a == {orden_a["orderId"]}


@pytest.mark.at("AT-04-06-05")
def test_abiertas_paginadas_sin_duplicados_ni_omisiones(usuario, rpc, api, limpiador):
    """HU-04-06 Escenario 5 (paginación/orden): Resultado estable y paginado."""
    # Dado un trader con 3 órdenes abiertas (más que el limit=2 solicitado)
    requerir_sin_asks_hasta(api, 1_700_000_000)
    fondear(usuario, rpc, usdc_min=48_000_000)  # 15 + 16 + 17 USDC de reservas
    esperadas = set()
    for precio in (1_500_000_000, 1_600_000_000, 1_700_000_000):
        orden = alta_ok(
            usuario, cuerpo_orden("BUY", "LIMIT", precio, 10_000_000_000_000_000),
            estado="OPEN",
        )
        limpiador.registrar(usuario, orden["orderId"])
        esperadas.add(orden["orderId"])

    # Cuando consulta página por página con el orden por defecto
    vistos: list[str] = []
    creados: list[str] = []
    cursor = None
    for _ in range(10):
        params = {"status": "OPEN", "limit": 2}
        if cursor:
            params["cursor"] = cursor
        resp = usuario.api.get("/orders", params=params)
        assert resp.status_code == 200, resp.text
        cuerpo = resp.json()
        assert len(cuerpo["items"]) <= 2
        vistos.extend(i["orderId"] for i in cuerpo["items"])
        creados.extend(i["createdAt"] for i in cuerpo["items"])
        cursor = cuerpo.get("nextCursor")
        if not cursor:
            break

    # Entonces cada orden aparece exactamente una vez, sin duplicados ni
    # omisiones (RN-4, RN-5), con createdAt descendente (más reciente primero)
    assert sorted(vistos) == sorted(esperadas)
    assert len(vistos) == len(set(vistos)) == 3
    assert creados == sorted(creados, reverse=True)


@pytest.mark.at("AT-04-06-06")
def test_consultar_abiertas_sin_autenticacion(api):
    """HU-04-06 Escenario 6 (error): No autenticado."""
    # Dado un cliente sin credencial válida
    # Cuando consulta órdenes abiertas
    resp = api.get("/orders", params={"status": "OPEN"})

    # Entonces se rechaza con UNAUTHENTICATED (401) (RN-7)
    assert_error(resp, "UNAUTHENTICATED")


@pytest.mark.at("AT-04-06-07")
def test_abiertas_serializa_montos_como_string_entero(usuario, rpc, api, limpiador):
    """HU-04-06 Escenario 7 (serialización): Montos como string entero."""
    # Dado un trader con una orden abierta priceMin="2000000000", quantityWei=10^18
    requerir_sin_asks_hasta(api, P2000)
    fondear(usuario, rpc, usdc_min=2_000_000_000)
    orden = alta_ok(usuario, cuerpo_orden("BUY", "LIMIT", P2000, ETH_1), estado="OPEN")
    limpiador.registrar(usuario, orden["orderId"])

    # Cuando consulta sus órdenes abiertas
    item = next(i for i in abiertas(usuario) if i["orderId"] == orden["orderId"])

    # Entonces todos los campos monetarios viajan como string ^(0|[1-9][0-9]*)$,
    # nunca como número JSON ni con decimales (RN-6)
    assert item["priceMin"] == "2000000000"
    assert item["quantityWei"] == "1000000000000000000"
    assert_montos_de_orden(item)
    # Y la única excepción es avgExecutionPrice = null cuando executedQty="0"
    # (RN-10; serialización única: nunca "0")
    if "avgExecutionPrice" in item:
        assert item["avgExecutionPrice"] is None, item


@pytest.mark.at("AT-04-06-08")
def test_consultar_abiertas_es_de_solo_lectura(usuario, rpc, api, limpiador):
    """HU-04-06 Escenario 8 (solo lectura): La consulta no altera estado."""
    # Dado un trader con balances y una orden abierta en cierto estado
    requerir_sin_asks_hasta(api, P2000)
    fondear(usuario, rpc, usdc_min=NOTIONAL_MIN)
    orden = alta_ok(usuario, cuerpo_orden("BUY", "LIMIT", P2000, Q_MIN), estado="OPEN")
    limpiador.registrar(usuario, orden["orderId"])
    saldo_previo = balances(usuario)
    detalle_previo = detalle(usuario, orden["orderId"])
    nivel_previo = cantidad_en_nivel(api, "bids", P2000)

    # Cuando consulta sus órdenes abiertas repetidas veces
    for _ in range(3):
        abiertas(usuario)

    # Entonces balances, estados y orderbook permanecen idénticos (RN-9)
    assert balances(usuario) == saldo_previo
    assert detalle(usuario, orden["orderId"]) == detalle_previo
    assert cantidad_en_nivel(api, "bids", P2000) == nivel_previo


@pytest.mark.at("AT-04-06-09")
def test_avg_execution_price_refleja_el_precio_ponderado_real(
    usuario, usuario_b, rpc, api, limpiador
):
    """HU-04-06 Escenario 9 (precio promedio): avgExecutionPrice ponderado real.

    TODO-REVISAR: `executedQuoteQty` y `avgExecutionPrice` los exige HU-04-06
    RN-10 con esos nombres; el objeto orden de HU-09-01 RN-5 no los lista. El AT
    asserta sus valores exactos, así que el campo es obligatorio acá.
    """
    # Dado dos asks ajenos: 0.4 ETH a 1980000000 y 0.6 ETH a 1990000000
    requerir_zona_limpia(api, P2000)
    fondear(usuario_b, rpc, eth_wei=ETH_1)
    alta_ok(
        usuario_b,
        cuerpo_orden("SELL", "LIMIT", 1_980_000_000, 400_000_000_000_000_000),
        estado="OPEN",
    )
    alta_ok(
        usuario_b,
        cuerpo_orden("SELL", "LIMIT", 1_990_000_000, 600_000_000_000_000_000),
        estado="OPEN",
    )
    # Y una orden BUY LIMIT 2 ETH @ 2000 que ejecuta 1 ETH en esos dos niveles
    # y cuyo remanente de 1 ETH descansa (PARTIALLY_FILLED)
    fondear(usuario, rpc, usdc_min=4_000_000_000)
    orden = alta_ok(usuario, cuerpo_orden("BUY", "LIMIT", P2000, 2 * ETH_1))
    limpiador.registrar(usuario, orden["orderId"])
    assert orden["status"] == "PARTIALLY_FILLED", orden

    # Cuando consulta sus órdenes abiertas
    item = next(i for i in abiertas(usuario) if i["orderId"] == orden["orderId"])

    # Entonces executedQty=1 ETH y executedQuoteQty = 792000000 + 1194000000 =
    # "1986000000" (floor por fill, RN-10)
    assert ejecutado_wei(item) == ETH_1
    assert item["executedQuoteQty"] == "1986000000", item

    # Y avgExecutionPrice = floor(1986000000 x 10^18 / 10^18) = "1986000000",
    # distinto del priceMin límite "2000000000" (RN-10)
    assert item["avgExecutionPrice"] == "1986000000", item
    assert es_monto_valido(item["avgExecutionPrice"])
    assert item["avgExecutionPrice"] != item["priceMin"]
