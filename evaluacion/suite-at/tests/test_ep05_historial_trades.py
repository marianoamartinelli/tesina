"""Épica 05 — HU-05-04 (consultar historial de trades): tests de aceptación black-box.

Endpoint del contrato: GET /api/v1/trades (HU-09-01 RN-20): {items, nextCursor}
con paginación cursor-based (keyset) por sequence, filtros from/to y orderId
propio, y cada item proyectando SOLO la pata propia del trade (sin exponer la
contraparte). Perspectiva por usuario: HU-05-04 RN-3/RN-4.
"""

import pytest

from comunes_ep05 import (
    PRECIO_2000,
    UN_ETH_WEI,
    assert_balance,
    assert_pata_propia,
    crear_limit,
    crear_maker,
    entrada_unica,
    esperar_trades,
    fondear_eth,
    fondear_usdc,
    limpiar_ordenes_residuales,  # noqa: F401  (fixture autouse: limpieza del libro)
)
from helpers.errores import assert_error
from helpers.montos import a_int, es_monto_valido, fee_maker, fee_taker, quote_min

# fill chico reutilizado en varios escenarios: 0.005 ETH @ 2000.00
# (notional 10 USDC = mínimo exacto, activos-y-par §4.5)
Q_CHICO = 5_000_000_000_000_000


def fill_chico(usuario_comprador, usuario_vendedor, rpc, *, fondear: bool = True) -> tuple[dict, dict]:
    """Un fill de Q_CHICO @ 2000.00 con comprador taker. Devuelve (orden_maker, orden_taker)."""
    if fondear:
        fondear_eth(usuario_vendedor, rpc, Q_CHICO)
        fondear_usdc(usuario_comprador, rpc, quote_min(Q_CHICO, PRECIO_2000))
    orden_maker = crear_maker(usuario_vendedor, "SELL", PRECIO_2000, Q_CHICO)
    orden_taker = crear_limit(usuario_comprador, "BUY", PRECIO_2000, Q_CHICO)
    return orden_maker, orden_taker


@pytest.mark.at("AT-05-04-01")
def test_historial_perspectiva_comprador_taker(usuario, usuario_b, rpc):
    """HU-05-04 Escenario 1: El usuario consulta su historial (comprador taker).

    - Dado un trader autenticado que fue comprador taker en un trade de 1 ETH @
      2000.00 (quoteAmountMin 2000000000, feeBaseWei 2000000000000000)
    - Cuando consulta su historial de trades
    - Entonces la entrada muestra side = "BUY", role = "TAKER",
      priceMin = "2000000000", quantityWei = "1000000000000000000"
    - Y feeAsset = "ETH", feeAmount = "2000000000000000",
      netReceived = "998000000000000000", paid = "2000000000"
    - Y la entrada referencia su propio orderId, sin exponer la contraparte
    """
    q_wei = UN_ETH_WEI
    quote = quote_min(q_wei, PRECIO_2000)
    fee_base = fee_taker(q_wei)

    # Dado: el trade canónico con el usuario como comprador taker
    fondear_eth(usuario_b, rpc, q_wei)
    fondear_usdc(usuario, rpc, quote)
    orden_maker = crear_maker(usuario_b, "SELL", PRECIO_2000, q_wei)
    orden_taker = crear_limit(usuario, "BUY", PRECIO_2000, q_wei)

    # Cuando
    items = esperar_trades(usuario, 1)

    # Entonces: la perspectiva de su pata (RN-3/RN-4)
    assert len(items) == 1
    assert_pata_propia(
        items[0],
        side="BUY", role="TAKER", price_min=PRECIO_2000, q_wei=q_wei, quote=quote,
        fee_asset="ETH", fee=fee_base, neto=q_wei - fee_base, pagado=quote,
        order_id=orden_taker["orderId"],
    )
    assert items[0]["feeAmount"] == "2000000000000000"
    assert items[0]["netReceived"] == "998000000000000000"
    assert items[0]["paid"] == "2000000000"

    # Y: no expone la contraparte (RN-4): ni su cuenta ni su orden aparecen
    resp = usuario.api.get("/trades")
    assert usuario_b.account_id not in resp.text
    assert orden_maker["orderId"] not in resp.text


@pytest.mark.at("AT-05-04-02")
def test_historial_misma_cuenta_perspectiva_vendedor_maker(usuario, usuario_b, rpc):
    """HU-05-04 Escenario 2: Misma cuenta, perspectiva vendedor maker.

    - Dado el mismo trader que en otro trade fue vendedor maker (1 ETH @ 2000.00,
      feeQuoteMin 2000000)
    - Cuando consulta su historial
    - Entonces esa entrada muestra side = "SELL", role = "MAKER", feeAsset = "USDC",
      feeAmount = "2000000", netReceived = "1998000000", paid = "1000000000000000000"
    - Y ambas entradas (esta y la de AT-05-04-01) aparecen en el mismo historial,
      cada una con su perspectiva
    """
    q_wei = UN_ETH_WEI
    quote = quote_min(q_wei, PRECIO_2000)

    # Dado: trade 1 — usuario comprador taker (como en AT-05-04-01)
    fondear_eth(usuario_b, rpc, q_wei)
    fondear_usdc(usuario, rpc, quote)
    crear_maker(usuario_b, "SELL", PRECIO_2000, q_wei)
    crear_limit(usuario, "BUY", PRECIO_2000, q_wei)
    esperar_trades(usuario, 1)

    # Dado: trade 2 — el mismo usuario ahora vendedor maker (SELL resting propio)
    fondear_eth(usuario, rpc, q_wei)                # 1 ETH fresco para vender entero
    fondear_usdc(usuario_b, rpc, quote)             # la contraparte compra como taker
    orden_sell_propia = crear_maker(usuario, "SELL", PRECIO_2000, q_wei)
    crear_limit(usuario_b, "BUY", PRECIO_2000, q_wei)

    # Cuando
    items = esperar_trades(usuario, 2)

    # Entonces: la entrada como vendedor maker, con su perspectiva (RN-3)
    entrada_sell = entrada_unica(items, side="SELL")
    assert_pata_propia(
        entrada_sell,
        side="SELL", role="MAKER", price_min=PRECIO_2000, q_wei=q_wei, quote=quote,
        fee_asset="USDC", fee=fee_maker(quote), neto=quote - fee_maker(quote), pagado=q_wei,
        order_id=orden_sell_propia["orderId"],
    )
    assert entrada_sell["feeAmount"] == "2000000"
    assert entrada_sell["netReceived"] == "1998000000"
    assert entrada_sell["paid"] == "1000000000000000000"

    # Y: la entrada como comprador taker convive en el mismo historial
    entrada_buy = entrada_unica(items, side="BUY")
    assert entrada_buy["role"] == "TAKER"
    assert entrada_buy["feeAsset"] == "ETH"


@pytest.mark.at("AT-05-04-03")
def test_paginacion_cursor_recencia_descendente_estable(usuario, usuario_b, rpc):
    """HU-05-04 Escenario 3: paginación cursor-based, recencia descendente, estable.

    - Dado un trader con 3 trades de sequence s1 < s2 < s3 y página N = 2
    - Cuando consulta la primera página (sin cursor)
    - Entonces recibe [s3, s2] (recencia descendente) y un cursor
    - Cuando consulta la página siguiente con ese cursor
    - Entonces recibe [s1], sin repetir ni omitir entradas (RN-6)
    - Y si entre ambas consultas se inserta un trade s4 > s3, NO aparece en la
      segunda página: la paginación permanece estable
    """
    # Dado: 3 fills chicos (el usuario es comprador taker en todos)
    fondear_eth(usuario_b, rpc, 4 * Q_CHICO)        # alcanza también para el s4 posterior
    fondear_usdc(usuario, rpc, 4 * quote_min(Q_CHICO, PRECIO_2000))
    for _ in range(3):
        fill_chico(usuario, usuario_b, rpc, fondear=False)
    todos = esperar_trades(usuario, 3)
    secuencias = sorted(it["sequence"] for it in todos)
    s1, s2, s3 = secuencias

    # Cuando: primera página sin cursor (limit 2)
    resp = usuario.api.get("/trades", params={"limit": 2})
    assert resp.status_code == 200, resp.text
    pagina_1 = resp.json()

    # Entonces: [s3, s2] en recencia descendente y cursor no nulo
    assert [it["sequence"] for it in pagina_1["items"]] == [s3, s2], pagina_1
    cursor = pagina_1["nextCursor"]
    assert isinstance(cursor, str) and cursor, pagina_1

    # Y: se inserta un nuevo trade s4 > s3 entre ambas consultas
    fill_chico(usuario, usuario_b, rpc, fondear=False)
    esperar_trades(usuario, 4)

    # Cuando: página siguiente con el cursor previo
    resp = usuario.api.get("/trades", params={"limit": 2, "cursor": cursor})
    assert resp.status_code == 200, resp.text
    pagina_2 = resp.json()

    # Entonces: exactamente [s1] — sin repetir s3/s2 y sin que aparezca s4
    # (los nuevos trades tienen sequence mayor que el cursor, RN-6)
    assert [it["sequence"] for it in pagina_2["items"]] == [s1], pagina_2
    # y no hay más páginas tras el último trade (nextCursor null, HU-09-01 RN-20)
    assert pagina_2["nextCursor"] is None, pagina_2


@pytest.mark.at("AT-05-04-04")
def test_filtro_por_order_id_propio_devuelve_todos_los_fills(usuario, usuario_b, rpc):
    """HU-05-04 Escenario 4 (filtro): por orderId propio devuelve todos sus fills.

    - Dado un trader comprador taker cuya orden BUY de 0.9 ETH @ 2000.00 se
      ejecutó en 3 fills parciales de 0.3 ETH (3 trades), con
      quoteAmountMin = 600000000 y feeBaseWei = 600000000000000 por fill
    - Cuando consulta el historial filtrando por ese orderId
    - Entonces devuelve exactamente esos 3 trades, todos con su orderId propio,
      side = "BUY", role = "TAKER"
    - Y por trade netReceived = "299400000000000000" (ETH) y paid = "600000000" (USDC)
    - Y la suma reproduce el efecto neto de la orden (RN-8a):
      Σ netReceived = 898200000000000000 y Σ paid = 1800000000
    """
    q_fill = 300_000_000_000_000_000                # 0.3 ETH por fill
    quote_fill = quote_min(q_fill, PRECIO_2000)
    fee_fill = fee_taker(q_fill)
    assert quote_fill == 600_000_000 and fee_fill == 600_000_000_000_000  # literales del AT

    # Dado: 3 makers SELL de 0.3 ETH al mismo precio; una única orden BUY de 0.9 barre las tres
    fondear_eth(usuario_b, rpc, 3 * q_fill)
    fondear_usdc(usuario, rpc, 3 * quote_fill)
    for _ in range(3):
        crear_maker(usuario_b, "SELL", PRECIO_2000, q_fill)
    orden_buy = crear_limit(usuario, "BUY", PRECIO_2000, 3 * q_fill)
    esperar_trades(usuario, 3)

    # Cuando: filtra por su propio orderId
    items = esperar_trades(usuario, 3, orderId=orden_buy["orderId"])

    # Entonces: exactamente los 3 fills de esa orden, con la perspectiva correcta
    assert len(items) == 3, items
    for it in items:
        assert_pata_propia(
            it,
            side="BUY", role="TAKER", price_min=PRECIO_2000, q_wei=q_fill,
            quote=quote_fill, fee_asset="ETH", fee=fee_fill,
            neto=q_fill - fee_fill, pagado=quote_fill,
            order_id=orden_buy["orderId"],
        )
        assert it["netReceived"] == "299400000000000000"
        assert it["paid"] == "600000000"

    # Y: la suma reproduce el efecto neto de la orden (RN-8a), también en balances
    suma_neto = sum(a_int(it["netReceived"]) for it in items)
    suma_pagado = sum(a_int(it["paid"]) for it in items)
    assert suma_neto == 898_200_000_000_000_000
    assert suma_pagado == 1_800_000_000
    assert_balance(usuario, "ETH", available=suma_neto, locked=0)
    assert_balance(usuario, "USDC", available=0, locked=0)


@pytest.mark.at("AT-05-04-05")
def test_historial_vacio_devuelve_lista_vacia(usuario):
    """HU-05-04 Escenario 5 (borde): historial vacío.

    - Dado un trader autenticado que nunca ejecutó un trade
    - Cuando consulta su historial
    - Entonces recibe una lista vacía (no un error) con metadatos de paginación
      coherentes (RN-11): items = [] y nextCursor = null (no hay más páginas)
    """
    # Dado: usuario fresco, sin trades (fixture)

    # Cuando
    resp = usuario.api.get("/trades")

    # Entonces
    assert resp.status_code == 200, resp.text
    cuerpo = resp.json()
    assert cuerpo["items"] == [], cuerpo
    assert cuerpo["nextCursor"] is None, cuerpo


@pytest.mark.at("AT-05-04-06")
def test_historial_sin_autenticacion_unauthenticated(api):
    """HU-05-04 Escenario 6 (error): sin autenticación.

    - Dado un cliente sin credencial válida (token ausente o inválido)
    - Cuando intenta consultar el historial de trades
    - Entonces se rechaza con UNAUTHENTICATED (401) y no se devuelve dato alguno (RN-1)
    """
    # Cuando: token ausente (el fixture `api` no lleva Authorization)
    resp = api.get("/trades")
    # Entonces
    err = assert_error(resp, "UNAUTHENTICATED")
    assert "items" not in resp.json(), resp.text    # solo el envelope de error
    assert err is not None

    # Y: token inválido también es UNAUTHENTICATED (catálogo de errores)
    resp = api.con_token("token-invalido-ep05").get("/trades")
    assert_error(resp, "UNAUTHENTICATED")


@pytest.mark.at("AT-05-04-07")
def test_aislamiento_historial_solo_pata_propia(usuario, usuario_b, rpc):
    """HU-05-04 Escenario 7 (error): intento de ver trades de otra cuenta.

    - Dado un trader autenticado como cuenta A y un fill entre A y B
    - Cuando consulta el historial por el endpoint del contrato (GET /api/v1/trades),
      que no admite indicar otra cuenta en la ruta
    - Entonces el aislamiento es por diseño: la respuesta contiene solo la pata
      propia de A (RN-2) y no hay forma de solicitar el historial de B
    - Y si una implementación expusiera un endpoint con accountId (fuera del
      contrato), pedir la cuenta ajena se rechaza (UNAUTHORIZED) sin filtrar
      ninguna entrada de B
    """
    # Dado: un fill entre A (comprador taker) y B (vendedor maker)
    orden_maker_b, orden_taker_a = fill_chico(usuario, usuario_b, rpc)
    esperar_trades(usuario, 1)
    esperar_trades(usuario_b, 1)

    # Cuando / Entonces: A ve solo su pata; nada identifica a B
    resp_a = usuario.api.get("/trades")
    assert resp_a.status_code == 200
    for it in resp_a.json()["items"]:
        assert it["orderId"] == orden_taker_a["orderId"], it
        assert it["side"] == "BUY", it
    assert usuario_b.account_id not in resp_a.text
    assert orden_maker_b["orderId"] not in resp_a.text

    # Y: B ve solo su pata; nada identifica a A (simetría de RN-2)
    resp_b = usuario_b.api.get("/trades")
    assert resp_b.status_code == 200
    for it in resp_b.json()["items"]:
        assert it["orderId"] == orden_maker_b["orderId"], it
        assert it["side"] == "SELL", it
    assert usuario.account_id not in resp_b.text
    assert orden_taker_a["orderId"] not in resp_b.text

    # Y: un endpoint por accountId ajeno (fuera del contrato) nunca responde 2xx
    # con datos: o no existe (NOT_FOUND) o se rechaza (UNAUTHORIZED) (RN-2)
    resp = usuario.api.get(f"/accounts/{usuario_b.account_id}/trades")
    assert resp.status_code >= 400, (
        f"el historial de otra cuenta no debe ser accesible: {resp.status_code} {resp.text[:200]}"
    )
    # Y: si el endpoint del contrato ignora un query param accountId ajeno, la
    # respuesta sigue conteniendo únicamente la pata propia de A
    resp = usuario.api.get("/trades", params={"accountId": usuario_b.account_id})
    if resp.status_code == 200:
        for it in resp.json()["items"]:
            assert it["orderId"] == orden_taker_a["orderId"], it
        assert usuario_b.account_id not in resp.text


@pytest.mark.at("AT-05-04-08")
def test_filtro_order_id_ajeno_o_inexistente_devuelve_lista_vacia(usuario, usuario_b, rpc):
    """HU-05-04 Escenario 8 (filtro): orderId ajeno o inexistente ⇒ lista vacía.

    - Dado un trader autenticado como cuenta A y un orderId que no pertenece a A
      (de la cuenta B, o inexistente)
    - Cuando filtra su historial por ese orderId
    - Entonces se devuelve una lista vacía (no un error), idéntica a cualquier
      filtro sin coincidencias, sin exponer fills de B ni revelar si el orderId
      existe (RN-7: nunca ORDER_NOT_FOUND)
    """
    # Dado: un fill entre A y B (así B tiene una orden real y A tiene un trade)
    orden_maker_b, orden_taker_a = fill_chico(usuario, usuario_b, rpc)
    esperar_trades(usuario, 1)

    # Cuando: filtro por el orderId REAL de B (ajeno a A)
    resp_ajeno = usuario.api.get("/trades", params={"orderId": orden_maker_b["orderId"]})
    # Entonces: 200 con lista vacía, jamás un error ni datos de B
    assert resp_ajeno.status_code == 200, resp_ajeno.text
    cuerpo_ajeno = resp_ajeno.json()
    assert cuerpo_ajeno["items"] == [], cuerpo_ajeno
    assert cuerpo_ajeno["nextCursor"] is None, cuerpo_ajeno

    # Cuando: filtro por un orderId inexistente
    resp_inexistente = usuario.api.get("/trades", params={"orderId": "ord-inexistente-ep05"})
    # Entonces: la MISMA respuesta no-reveladora (RN-7)
    assert resp_inexistente.status_code == 200, resp_inexistente.text
    assert resp_inexistente.json() == cuerpo_ajeno

    # Y (sanity): el filtro por el orderId propio sí devuelve el fill — la lista
    # vacía de arriba se debe al aislamiento, no a un filtro roto
    items_propios = esperar_trades(usuario, 1, orderId=orden_taker_a["orderId"])
    assert len(items_propios) == 1


@pytest.mark.at("AT-05-04-09")
def test_montos_del_historial_como_string_entero(usuario, usuario_b, rpc):
    """HU-05-04 Escenario 9 (serialización): montos como string entero.

    - Dado cualquier entrada del historial
    - Cuando se serializa la respuesta
    - Entonces todos los montos viajan como string que matchea ^(0|[1-9][0-9]*)$,
      nunca como número JSON, decimal ni notación científica (RN-10)
    - Y feeAsset ∈ {ETH, USDC}, side ∈ {BUY, SELL}, role ∈ {MAKER, TAKER}
    """
    # Dado: un fill entre ambos usuarios (dos entradas, una por perspectiva)
    fill_chico(usuario, usuario_b, rpc)
    entradas = esperar_trades(usuario, 1) + esperar_trades(usuario_b, 1)

    # Cuando / Entonces
    campos_monetarios = ("priceMin", "quantityWei", "quoteAmountMin", "feeAmount", "netReceived", "paid")
    for entrada in entradas:
        for campo in campos_monetarios:
            assert es_monto_valido(entrada[campo]), (campo, entrada[campo])
        # Y: enums exactos de la spec
        assert entrada["feeAsset"] in ("ETH", "USDC"), entrada
        assert entrada["side"] in ("BUY", "SELL"), entrada
        assert entrada["role"] in ("MAKER", "TAKER"), entrada
        # sequence es conteo (entero JSON); timestamp string ISO-8601 (RN-20)
        assert isinstance(entrada["sequence"], int) and not isinstance(entrada["sequence"], bool)
        assert isinstance(entrada["timestamp"], str)
