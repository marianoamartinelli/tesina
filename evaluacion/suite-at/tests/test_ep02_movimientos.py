"""Épica 02 — HU-02-05 Historial de movimientos: tests de aceptación black-box.

Spec: spec/02-balances-y-ledger/HU-02-05-historial-de-movimientos.md (autoridad
semántica: contenido, filtros, orden). Superficie REST: GET /api/v1/movements
(HU-09-01 RN-22 — ADR-006 D6): `{ items, nextCursor }`, `limit` en [1, 100] con
default 20, cursor opaco anclado al `entryId`, filtro `type` repetible (OR),
`from ≤ timestamp < to`, orden descendente, montos como string entero y conteos
(`logIndex`) como enteros JSON.

El "Dado" de cada escenario se construye black-box con movimientos reales:
depósitos on-chain acreditados (épicas 06+07), órdenes con fill y cancelación
(épica 04 vía 09) y retiros (épica 08 vía 09). La validación de forma de cada
ítem (entryId/type/timestamp/reference/postings) la aplica
comunes_ep02.movimientos_ok en toda lectura.
"""

import json

import pytest

from comunes_ep02 import (
    INTERVALO_POLL_SEGUNDOS,
    PRECIO_BANDA_BAJA,
    PRECIO_MATCHING,
    RUTA_MOVIMIENTOS,
    assert_orden_descendente,
    cancelar_orden,
    cancelar_si_posible,
    consultar_movimientos,
    crear_retiro,
    detalle_retiro,
    direccion_deposito,
    fondear_eth,
    fondear_usdc,
    movimientos_ok,
    orden_creada,
    orden_resting,
    parsear_timestamp_utc_ms,
    tupla_posting,
)
from helpers.errores import assert_error, validar_envelope
from helpers.espera import esperar_hasta
from helpers.montos import WEI_POR_ETH


def _tipos(items: list) -> list:
    return [item["type"] for item in items]


def _ids(items: list) -> list:
    return [item["entryId"] for item in items]


# -------------------------------------------------------------------------------------
# Contenido y orden (RN-2, RN-6)
# -------------------------------------------------------------------------------------


@pytest.mark.at("AT-02-05-01")
def test_historial_completo_sin_filtros(usuario, usuario_b, rpc):
    """HU-02-05 Escenario 1: Historial completo sin filtros.

    Reproduce los cuatro movimientos del Dado con las cifras del AT:
    1. DEPOSIT `3000000000` USDC (reference `{txHash, logIndex}`)
    2. ORDER_LOCK `2000000000` USDC — BUY limit 1 ETH @ 2000.00 (reference `{orderId}`)
    3. TRADE_FILL — fill parcial de 0.995 ETH exactamente al precio límite
       (reference `{tradeId}`; sin ORDER_RELEASE de surplus: release = 0,
       HU-02-02 RN-6)
    4. ORDER_RELEASE `10000000` USDC — cancelación del remanente de 0.005 ETH
       (`floor(5e15 × 2000000000 / 1e18) = 10000000`; reference `{orderId}`)
    - Entonces recibe exactamente 4 ítems, cada uno con entryId/type/timestamp
      ISO-8601/reference y sus postings propios `^[1-9][0-9]*$`
      (movimientos_ok valida cada ítem)
    - Y ordenados por timestamp desc (entryId desc ante empate):
      ORDER_RELEASE, TRADE_FILL, ORDER_LOCK, DEPOSIT
    """
    # Dado: maker con 0.995 ETH resting a 2000.00 para el fill parcial del taker
    fondear_eth(usuario_b, rpc, 995_000_000_000_000_000)
    maker = orden_resting(usuario_b, "SELL", 995_000_000_000_000_000, PRECIO_MATCHING)
    orden_id = None
    try:
        # 1. DEPOSIT
        fondear_usdc(usuario, rpc, 3_000_000_000)
        # 2.+3. ORDER_LOCK 2000000000 + TRADE_FILL (ejecuta 0.995 de 1 ETH al límite)
        taker = orden_creada(usuario, "BUY", "LIMIT", WEI_POR_ETH, PRECIO_MATCHING)
        orden_id = taker["orderId"]
        assert taker["status"] == "PARTIALLY_FILLED", taker
        assert taker["filledWei"] == "995000000000000000"
        # 4. ORDER_RELEASE 10000000 (remanente de 0.005 ETH al precio original)
        cancelar_orden(usuario, orden_id)
        orden_id = None

        # Cuando: consulta sin filtros
        cuerpo = movimientos_ok(usuario)
        items = cuerpo["items"]

        # Entonces: exactamente 4 ítems, en el orden descendente del AT
        assert _tipos(items) == ["ORDER_RELEASE", "TRADE_FILL", "ORDER_LOCK", "DEPOSIT"], (
            f"orden/contenido inesperado del historial: {_tipos(items)}"
        )
        assert_orden_descendente(items)
        assert cuerpo["nextCursor"] is None  # única página (4 ítems < default 20)

        release, fill, lock, deposito = items

        # Y: reference según el origen (RN-2)
        assert lock["reference"]["orderId"] == taker["orderId"]
        assert release["reference"]["orderId"] == taker["orderId"]
        assert isinstance(fill["reference"]["tradeId"], str) and fill["reference"]["tradeId"]
        # (el {txHash, logIndex} del DEPOSIT ya lo exige movimientos_ok)

        # Y: postings propios exactos (README de la 02 §5.2), todos PRINCIPAL
        assert {tupla_posting(p) for p in deposito["postings"]} == {
            ("USDC", "AVAILABLE", "CREDIT", "3000000000"),
        }, deposito
        assert {tupla_posting(p) for p in lock["postings"]} == {
            ("USDC", "AVAILABLE", "DEBIT", "2000000000"),
            ("USDC", "LOCKED", "CREDIT", "2000000000"),
        }, lock
        # el fill paga floor(0.995e18 × 2000000000 / 1e18) = 1990000000 y
        # acredita 0.995 ETH − fee taker (ceil(0.995e18 × 20 / 10000))
        assert {tupla_posting(p) for p in fill["postings"]} == {
            ("USDC", "LOCKED", "DEBIT", "1990000000"),
            ("ETH", "AVAILABLE", "CREDIT", "993010000000000000"),
        }, fill
        assert {tupla_posting(p) for p in release["postings"]} == {
            ("USDC", "LOCKED", "DEBIT", "10000000"),
            ("USDC", "AVAILABLE", "CREDIT", "10000000"),
        }, release
        for item in items:
            for posting in item["postings"]:
                assert posting["kind"] == "PRINCIPAL", posting
    finally:
        if orden_id:
            cancelar_si_posible(usuario, orden_id)
        cancelar_si_posible(usuario_b, maker["orderId"])


# -------------------------------------------------------------------------------------
# Filtros (RN-3, RN-4, RN-5, RN-8)
# -------------------------------------------------------------------------------------


@pytest.mark.at("AT-02-05-02")
def test_filtro_por_activo(usuario, rpc):
    """HU-02-05 Escenario 2: Filtro por activo.

    - Dado un trader con movimientos en ETH y en USDC (un depósito de cada uno)
    - Cuando consulta con asset = USDC
    - Entonces solo recibe ítems con al menos un posting propio en USDC
    - Y ningún ítem cuyos postings propios sean exclusivamente en ETH (RN-3)
    """
    # Dado
    fondear_eth(usuario, rpc, 100_000_000_000_000_000)  # 0.1 ETH
    fondear_usdc(usuario, rpc, 50_000_000)              # 50 USDC

    # Cuando
    items = movimientos_ok(usuario, {"asset": "USDC"})["items"]

    # Entonces: de los dos depósitos, solo el de USDC
    assert len(items) == 1, f"se esperaba solo el depósito USDC: {_tipos(items)}"
    for item in items:
        assert any(p["asset"] == "USDC" for p in item["postings"]), item
    # Y: ningún ítem exclusivamente en ETH
    assert not any(
        all(p["asset"] == "ETH" for p in item["postings"]) for item in items
    )

    # (control: sin filtro el historial sí contiene el depósito de ETH)
    assert len(movimientos_ok(usuario)["items"]) == 2


@pytest.mark.at("AT-02-05-03")
def test_filtro_por_tipo(usuario, rpc):
    """HU-02-05 Escenario 3: Filtro por tipo.

    - Dado un trader con asientos de varios tipos (DEPOSIT y ORDER_LOCK)
    - Cuando consulta con type = DEPOSIT
    - Entonces solo recibe ítems con type = DEPOSIT
    - Y cada uno trae su reference { txHash, logIndex } (RN-4)
    """
    # Dado: depósito + orden resting (ORDER_LOCK)
    fondear_usdc(usuario, rpc, 2_000_000_000)
    orden = orden_resting(usuario, "BUY", 2 * WEI_POR_ETH, PRECIO_BANDA_BAJA)
    try:
        # Cuando
        items = movimientos_ok(usuario, {"type": "DEPOSIT"})["items"]

        # Entonces: solo el DEPOSIT, con su identidad on-chain
        assert len(items) == 1, f"se esperaba solo el DEPOSIT: {_tipos(items)}"
        for item in items:
            assert item["type"] == "DEPOSIT"
            assert isinstance(item["reference"]["txHash"], str)
            log_index = item["reference"]["logIndex"]
            # conteo ⇒ entero JSON, no monto (HU-09-01 RN-22)
            assert isinstance(log_index, int) and not isinstance(log_index, bool)
    finally:
        cancelar_si_posible(usuario, orden["orderId"])


@pytest.mark.at("AT-02-05-04")
def test_filtro_por_periodo_inclusivo_exclusivo(usuario, rpc):
    """HU-02-05 Escenario 4: Filtro por período (from inclusivo / to exclusivo).

    - Dado tres movimientos en instantes t1 < t2 < t3 (tres depósitos USDC
      acreditados por separado: cada acreditación espera 12 confirmaciones, así
      que los timestamps difieren)
    - Cuando consulta con from = t1 y to = t3
    - Entonces recibe los movimientos de t1 y t2 (`from ≤ timestamp < to`)
    - Y NO recibe el de t3 (límite superior exclusivo) (RN-5)
    """
    # Dado
    direccion = direccion_deposito(usuario, "USDC")
    acreditados = 0
    for monto in (1_000_000, 2_000_000, 3_000_000):
        rpc.depositar_usdc(direccion, monto)
        acreditados += 1
        esperar_hasta(
            lambda n=acreditados: len(movimientos_ok(usuario)["items"]) >= n,
            intervalo=INTERVALO_POLL_SEGUNDOS,
            mensaje=f"el depósito {acreditados} no apareció en el historial",
        )

    items = movimientos_ok(usuario)["items"]  # desc: [d3, d2, d1]
    assert len(items) == 3 and set(_tipos(items)) == {"DEPOSIT"}, _tipos(items)
    d3, d2, d1 = items
    assert (
        parsear_timestamp_utc_ms(d1["timestamp"])
        < parsear_timestamp_utc_ms(d2["timestamp"])
        < parsear_timestamp_utc_ms(d3["timestamp"])
    ), "el Dado requiere tres instantes distintos"

    # Cuando: from = t1 (inclusivo), to = t3 (exclusivo)
    filtrados = movimientos_ok(
        usuario, {"from": d1["timestamp"], "to": d3["timestamp"]}
    )["items"]

    # Entonces / Y: exactamente d2 y d1 (en orden descendente); d3 queda afuera
    assert _ids(filtrados) == [d2["entryId"], d1["entryId"]], (
        f"from ≤ t < to violado: {_ids(filtrados)}"
    )


@pytest.mark.at("AT-02-05-05")
def test_combinacion_de_filtros_and(usuario, usuario_b, rpc):
    """HU-02-05 Escenario 5: Combinación de filtros (AND).

    - Dado un trader con un DEPOSIT y dos TRADE_FILL en instantes distintos
    - Cuando consulta con asset = USDC, type = TRADE_FILL y un período que solo
      contiene el primer fill
    - Entonces recibe exactamente 1 ítem: ese TRADE_FILL (cumple las tres
      condiciones simultáneamente, AND)
    - Y NO recibe el DEPOSIT (no es TRADE_FILL) ni el segundo TRADE_FILL
      (fuera del período) (RN-8)

    Nota: la variante del Dado "TRADE_FILL con postings propios solo en ETH" no
    es construible black-box (la pata propia de todo fill entrega un activo y
    recibe el otro: siempre toca USDC y ETH); la exclusión AND se ejercita por
    tipo y por período, y el filtro asset = USDC lo satisface el fill del
    período.
    """
    # Dado: DEPOSIT + FILL1 + FILL2 (dos compras de 1 ETH contra makers resting)
    fondear_eth(usuario_b, rpc, 2 * WEI_POR_ETH)
    fondear_usdc(usuario, rpc, 4_000_000_000)
    maker_1 = orden_resting(usuario_b, "SELL", WEI_POR_ETH, PRECIO_MATCHING)
    try:
        fill_1 = orden_creada(usuario, "BUY", "LIMIT", WEI_POR_ETH, PRECIO_MATCHING)
        assert fill_1["status"] == "FILLED", fill_1
        maker_2 = orden_resting(usuario_b, "SELL", WEI_POR_ETH, PRECIO_MATCHING)
        try:
            fill_2 = orden_creada(usuario, "BUY", "LIMIT", WEI_POR_ETH, PRECIO_MATCHING)
            assert fill_2["status"] == "FILLED", fill_2
        finally:
            cancelar_si_posible(usuario_b, maker_2["orderId"])
    finally:
        cancelar_si_posible(usuario_b, maker_1["orderId"])

    todos = movimientos_ok(usuario)["items"]
    # desc: [FILL2, LOCK2, FILL1, LOCK1, DEPOSIT]
    assert _tipos(todos) == [
        "TRADE_FILL", "ORDER_LOCK", "TRADE_FILL", "ORDER_LOCK", "DEPOSIT",
    ], _tipos(todos)
    item_fill_2, _, item_fill_1, _, item_deposito = todos
    assert (
        parsear_timestamp_utc_ms(item_fill_1["timestamp"])
        < parsear_timestamp_utc_ms(item_fill_2["timestamp"])
    ), "el Dado requiere fills en instantes distintos"

    # Cuando: activo AND tipo AND período (solo el primer fill los cumple)
    filtrados = movimientos_ok(
        usuario,
        {
            "asset": "USDC",
            "type": "TRADE_FILL",
            "from": item_deposito["timestamp"],
            "to": item_fill_2["timestamp"],
        },
    )["items"]

    # Entonces / Y: exactamente el primer TRADE_FILL
    assert _ids(filtrados) == [item_fill_1["entryId"]], (
        f"la combinación AND devolvió {_tipos(filtrados)}"
    )
    assert filtrados[0]["type"] == "TRADE_FILL"


@pytest.mark.at("AT-02-05-14")
def test_filtro_por_multiples_tipos_or(usuario, usuario_b, rpc):
    """HU-02-05 Escenario 14: Filtro por múltiples tipos (OR entre tipos).

    - Dado un trader con movimientos DEPOSIT, ORDER_LOCK, TRADE_FILL y
      WITHDRAWAL_SETTLE (depósito de 1.5 ETH; SELL maker de 1 ETH ejecutada;
      retiro de 0.4 ETH confirmado on-chain)
    - Cuando consulta con type=DEPOSIT&type=ORDER_LOCK (parámetros repetidos)
    - Entonces solo recibe ítems con type = DEPOSIT o type = ORDER_LOCK
    - Y ningún ítem de otro tipo (TRADE_FILL, WITHDRAWAL_*) (RN-4/RN-8)
    """
    # Dado: DEPOSIT + ORDER_LOCK + TRADE_FILL (el trader vende 1 ETH como maker)
    fondear_eth(usuario, rpc, 1_500_000_000_000_000_000)
    maker = orden_resting(usuario, "SELL", WEI_POR_ETH, PRECIO_MATCHING)
    try:
        fondear_usdc(usuario_b, rpc, 2_000_000_000)
        taker = orden_creada(usuario_b, "BUY", "LIMIT", WEI_POR_ETH, PRECIO_MATCHING)
        assert taker["status"] == "FILLED", taker
    finally:
        cancelar_si_posible(usuario, maker["orderId"])

    # …y WITHDRAWAL_LOCK + WITHDRAWAL_SETTLE (retiro confirmado, HU-08-04)
    resp = crear_retiro(usuario, "ETH", 400_000_000_000_000_000)
    assert resp.status_code == 202, resp.text
    retiro = resp.json()
    esperar_hasta(
        lambda: detalle_retiro(usuario, retiro["withdrawalId"]).get("txHash"),
        intervalo=INTERVALO_POLL_SEGUNDOS,
        mensaje="el retiro nunca se broadcasteó (¿hot wallet sin fondear?)",
    )
    rpc.minar_bloques(12)
    esperar_hasta(
        lambda: detalle_retiro(usuario, retiro["withdrawalId"])["status"] == "CONFIRMED",
        intervalo=INTERVALO_POLL_SEGUNDOS,
        mensaje="el retiro no llegó a CONFIRMED tras 12 confirmaciones",
    )

    # (control del Dado: el historial completo contiene los cuatro tipos)
    todos = movimientos_ok(usuario)["items"]
    assert {"DEPOSIT", "ORDER_LOCK", "TRADE_FILL", "WITHDRAWAL_SETTLE"} <= set(
        _tipos(todos)
    ), _tipos(todos)

    # Cuando: parámetros repetidos (?type=DEPOSIT&type=ORDER_LOCK)
    items = movimientos_ok(usuario, {"type": ["DEPOSIT", "ORDER_LOCK"]})["items"]

    # Entonces: OR entre los tipos solicitados…
    assert sorted(_tipos(items)) == ["DEPOSIT", "ORDER_LOCK"], _tipos(items)
    # …y ningún ítem de otro tipo quedó incluido
    assert len(items) == sum(
        1 for item in todos if item["type"] in ("DEPOSIT", "ORDER_LOCK")
    )


# -------------------------------------------------------------------------------------
# Paginación (RN-7)
# -------------------------------------------------------------------------------------


@pytest.mark.at("AT-02-05-06")
def test_paginacion_estable(usuario, rpc):
    """HU-02-05 Escenario 6 (borde): Paginación estable.

    - Dado un trader con 25 movimientos (1 DEPOSIT + 12 ciclos de
      ORDER_LOCK/ORDER_RELEASE por alta y cancelación) y limit = 10
    - Cuando recorre las páginas sucesivas (sin cambios en el ledger entre
      páginas, con el cursor opaco anclado al entryId de HU-09-01 RN-22)
    - Entonces obtiene 10 + 10 + 5 ítems, sin duplicados ni omisiones
    - Y el orden global (timestamp desc, entryId desc) se mantiene a través de
      las páginas (RN-6/RN-7)
    """
    # Dado: 25 movimientos propios
    fondear_usdc(usuario, rpc, 2_000_000_000)
    for _ in range(12):
        # BUY 0.01 ETH @ 1000.00 ⇒ notional 10 USDC (= mínimo); lock + release
        orden = orden_resting(usuario, "BUY", WEI_POR_ETH // 100, PRECIO_BANDA_BAJA)
        cancelar_orden(usuario, orden["orderId"])

    completo = movimientos_ok(usuario, {"limit": 100})
    assert len(completo["items"]) == 25, _tipos(completo["items"])
    assert completo["nextCursor"] is None
    assert_orden_descendente(completo["items"])

    # Cuando: páginas sucesivas con limit = 10
    paginas = []
    cursor = None
    for esperado in (10, 10, 5):
        params = {"limit": 10}
        if cursor is not None:
            params["cursor"] = cursor
        pagina = movimientos_ok(usuario, params)
        assert len(pagina["items"]) == esperado, (
            f"página de {len(pagina['items'])} ítems; se esperaban {esperado}"
        )
        paginas.append(pagina["items"])
        cursor = pagina["nextCursor"]
        if esperado == 5:
            assert cursor is None, "tras la última página, nextCursor debe ser null"
        else:
            assert isinstance(cursor, str) and cursor, (
                f"se esperaba un cursor opaco para la página siguiente: {cursor!r}"
            )

    # Entonces: 10 + 10 + 5, sin duplicados ni omisiones
    concatenado = [item for pagina in paginas for item in pagina]
    assert len(concatenado) == 25
    assert len(set(_ids(concatenado))) == 25, "hay entryId duplicados entre páginas"

    # Y: el orden global se mantiene (idéntico al listado en una sola página)
    assert _ids(concatenado) == _ids(completo["items"])
    assert_orden_descendente(concatenado)


# -------------------------------------------------------------------------------------
# Bordes de resultado (RN-5, RN-9)
# -------------------------------------------------------------------------------------


@pytest.mark.at("AT-02-05-07")
def test_resultado_vacio_no_es_error(usuario, rpc):
    """HU-02-05 Escenario 7 (borde): Resultado vacío.

    - Dado un trader sin movimientos del tipo solicitado (tiene un DEPOSIT,
      ningún WITHDRAWAL_SETTLE)
    - Cuando consulta con type = WITHDRAWAL_SETTLE
    - Entonces recibe una lista vacía y un código de éxito, no NOT_FOUND (RN-9)
    """
    # Dado
    fondear_usdc(usuario, rpc, 1_000_000)

    # Cuando (movimientos_ok asserta el 200 de éxito)
    cuerpo = movimientos_ok(usuario, {"type": "WITHDRAWAL_SETTLE"})

    # Entonces
    assert cuerpo["items"] == []
    assert cuerpo["nextCursor"] is None


@pytest.mark.at("AT-02-05-12")
def test_rango_vacio_from_igual_to(usuario, rpc):
    """HU-02-05 Escenario 12 (borde): Rango vacío from == to ⇒ lista vacía.

    - Dado un trader con movimientos en distintos instantes
    - Cuando consulta con from = to = el timestamp exacto de uno de ellos
    - Entonces recibe lista vacía con código de éxito (no VALIDATION_ERROR):
      el intervalo `from ≤ t < from` es vacío incluso para el movimiento cuyo
      timestamp coincide con from (RN-5/RN-9)
    """
    # Dado: DEPOSIT + ORDER_LOCK + ORDER_RELEASE en instantes distintos
    fondear_usdc(usuario, rpc, 20_000_000)
    orden = orden_resting(usuario, "BUY", WEI_POR_ETH // 100, PRECIO_BANDA_BAJA)
    cancelar_orden(usuario, orden["orderId"])
    items = movimientos_ok(usuario)["items"]
    assert len(items) == 3, _tipos(items)
    instante = items[1]["timestamp"]  # existe un movimiento exactamente en `from`

    # Cuando (movimientos_ok asserta que responde 200, no un error)
    cuerpo = movimientos_ok(usuario, {"from": instante, "to": instante})

    # Entonces
    assert cuerpo["items"] == []


# -------------------------------------------------------------------------------------
# Errores de validación (RN-3, RN-5, RN-7) y autenticación (RN-1)
# -------------------------------------------------------------------------------------


@pytest.mark.at("AT-02-05-08")
def test_filtro_de_activo_invalido(usuario):
    """HU-02-05 Escenario 8 (error): Filtro de activo inválido.

    - Cuando consulta con asset = BTC (fuera de {ETH, USDC})
    - Entonces VALIDATION_ERROR (422) y details.issues describe el campo (RN-3)
    """
    # Cuando
    resp = consultar_movimientos(usuario, {"asset": "BTC"})

    # Entonces
    err = assert_error(resp, "VALIDATION_ERROR")
    issues = (err.get("details") or {}).get("issues")
    assert issues, f"details.issues ausente: {err!r}"
    assert "asset" in json.dumps(issues), (
        f"issues no referencia el campo inválido 'asset': {issues!r}"
    )


@pytest.mark.at("AT-02-05-09")
def test_rango_de_fechas_invalido(usuario):
    """HU-02-05 Escenario 9 (error): Rango de fechas inválido (from > to).

    - Cuando consulta con from = 2026-07-01 y to = 2026-06-01 (from > to)
    - Entonces VALIDATION_ERROR (422) y no se devuelve ningún movimiento (RN-5)
    """
    # Cuando
    resp = consultar_movimientos(
        usuario,
        {"from": "2026-07-01T00:00:00.000Z", "to": "2026-06-01T00:00:00.000Z"},
    )

    # Entonces / Y: solo el envelope de error, sin movimientos
    assert_error(resp, "VALIDATION_ERROR")
    assert set(resp.json()) == {"error"}


@pytest.mark.at("AT-02-05-13")
def test_limit_fuera_de_rango(usuario):
    """HU-02-05 Escenario 13 (error): `limit` fuera de rango [1, 100].

    - Cuando consulta con limit = 0 / -1 / 101
    - Entonces cada sub-caso se rechaza con VALIDATION_ERROR (422) y
      details.issues indica el campo `limit` (restricción [1, 100], RN-7)
    """
    for limite in (0, -1, 101):
        # Cuando
        resp = consultar_movimientos(usuario, {"limit": limite})

        # Entonces
        err = assert_error(resp, "VALIDATION_ERROR")
        issues = (err.get("details") or {}).get("issues")
        assert issues, f"limit={limite}: details.issues ausente: {err!r}"
        assert "limit" in json.dumps(issues), (
            f"limit={limite}: issues no referencia el campo 'limit': {issues!r}"
        )


@pytest.mark.at("AT-02-05-10")
def test_consulta_sin_autenticacion(api):
    """HU-02-05 Escenario 10 (error): Sin autenticación.

    - Dado un cliente sin credencial válida (ausente o inválida)
    - Cuando intenta consultar el historial
    - Entonces UNAUTHENTICATED (401) (RN-1; HU-09-01 RN-22)
    """
    # Cuando: sin header Authorization
    resp = api.get(RUTA_MOVIMIENTOS)

    # Entonces
    assert_error(resp, "UNAUTHENTICATED")

    # Y: una credencial inválida recibe el mismo rechazo
    with api.con_token("token-invalido-movimientos") as impostor:
        assert_error(impostor.get(RUTA_MOVIMIENTOS), "UNAUTHENTICATED")


# -------------------------------------------------------------------------------------
# Autorización / aislamiento (RN-1)
# -------------------------------------------------------------------------------------


@pytest.mark.at("AT-02-05-11")
def test_no_se_filtran_movimientos_ajenos(usuario, usuario_b, rpc):
    """HU-02-05 Escenario 11 (autorización): No se filtran movimientos ajenos.

    - Dado un trader autenticado como cuenta A y un fill entre A y B
    - Cuando A consulta su historial y aparece el TRADE_FILL correspondiente
    - Entonces el ítem muestra SOLO los postings de A
    - Y no expone los postings de B, de EX ni de EXTERNAL; un intento de pedir
      el historial de B ⇒ UNAUTHORIZED (403) (RN-1)

    La superficie de HU-09-01 RN-22 no recibe accountId (la cuenta se infiere
    del token), así que la cláusula "pedir el historial de B" es condicional:
    se sondean las vías plausibles y cada una debe rechazar (403/404/422) o
    responder solo datos propios — nunca postings ajenos (patrón de AT-02-01-06).
    """
    # Dado: fill de 1 ETH @ 2000.00 entre A (taker BUY) y B (maker SELL)
    fondear_eth(usuario_b, rpc, WEI_POR_ETH)
    maker = orden_resting(usuario_b, "SELL", WEI_POR_ETH, PRECIO_MATCHING)
    try:
        fondear_usdc(usuario, rpc, 2_000_000_000)
        taker = orden_creada(usuario, "BUY", "LIMIT", WEI_POR_ETH, PRECIO_MATCHING)
        assert taker["status"] == "FILLED", taker
    finally:
        cancelar_si_posible(usuario_b, maker["orderId"])

    # Cuando: A consulta su historial y aparece el TRADE_FILL
    items = movimientos_ok(usuario, {"type": "TRADE_FILL"})["items"]
    assert len(items) == 1, _tipos(items)
    fill = items[0]

    # Entonces: SOLO la pata de A (paga 2000 USDC bloqueados, recibe 1 ETH neto
    # de fee taker); ni los postings de B (1e18 wei entregados, 1998000000
    # recibidos) ni los de EX (fees 2000000000000000 / 2000000)
    assert {tupla_posting(p) for p in fill["postings"]} == {
        ("USDC", "LOCKED", "DEBIT", "2000000000"),
        ("ETH", "AVAILABLE", "CREDIT", "998000000000000000"),
    }, fill
    montos_ajenos = {"1000000000000000000", "1998000000", "2000000000000000", "2000000"}
    for item in movimientos_ok(usuario)["items"]:
        for posting in item["postings"]:
            assert posting["amount"] not in montos_ajenos, (
                f"posting con monto de B/EX/EXTERNAL filtrado: {item!r}"
            )

    # Y: pedir el historial de B no revela nada (vías condicionales)
    sondas = [
        (
            "GET /movements?accountId=<B>",
            lambda: usuario.api.get(
                RUTA_MOVIMIENTOS, params={"accountId": usuario_b.account_id}
            ),
        ),
        (
            "GET /movements/<accountId de B>",
            lambda: usuario.api.get(f"{RUTA_MOVIMIENTOS}/{usuario_b.account_id}"),
        ),
    ]
    for nombre, sonda in sondas:
        resp = sonda()
        if resp.status_code == 200:
            # la vía ignora el parámetro: debe responder SOLO movimientos de A
            cuerpo = resp.json()
            for item in cuerpo.get("items", []):
                for posting in item.get("postings", []):
                    assert posting.get("amount") not in montos_ajenos, (
                        f"{nombre}: filtró postings de la cuenta B / EX"
                    )
        elif resp.status_code == 403:
            # la vía existe y rechaza consultar a nombre de otra cuenta (el AT)
            assert_error(resp, "UNAUTHORIZED")
        elif resp.status_code == 404:
            # la vía no está expuesta (o el recurso ajeno no se revela)
            err = validar_envelope(resp.json())
            assert err["code"] in ("NOT_FOUND", "ACCOUNT_NOT_FOUND"), err
        elif resp.status_code == 422:
            # la vía rechaza el parámetro no soportado
            assert_error(resp, "VALIDATION_ERROR")
        else:
            raise AssertionError(
                f"{nombre}: status inesperado {resp.status_code}: {resp.text[:200]}"
            )
