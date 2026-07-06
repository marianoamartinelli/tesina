"""Épica 09 — HU-09-01 (contrato REST): tests de aceptación black-box.

Cubre AT-09-01-01..22 (más AT-09-05-10, cuyo flujo es idéntico a AT-09-01-15).
Los tests de las demás HU de la épica viven en sus archivos temáticos:
autenticación/autorización (test_ep09_auth.py), WS público
(test_ep09_ws_publico.py), WS privado (test_ep09_ws_privado.py) y modelo de
errores (test_ep09_errores.py).

Convenciones: un test por escenario AT, marcado con ``@pytest.mark.at(...)``,
Gherkin de la spec mapeado como comentarios Dado/Cuando/Entonces (HELPERS.md).
El "Dado" lo construye cada test sobre el libro compartido (comunes_ep09).
"""

import pytest

from comunes_ep09 import (
    CAMPOS_ORDEN,
    DESTINO_RETIRO,
    balances_por_activo,
    barrer_asks,
    barrer_bids,
    cancelar_silencioso,
    cantidad_para_notional,
    colocar_ask_dominante,
    crear_orden,
    direccion_de_deposito,
    es_entero_json,
    es_timestamp_utc,
    fondear_eth,
    fondear_usdc,
    id_cliente,
    libro,
    precio_bid_seguro,
    precio_dominante,
    tomar_con_buy,
)
from helpers.cuentas import PASSWORD_DEFECTO, email_unico, registrar
from helpers.eip55 import RE_TXHASH, assert_direccion, romper_checksum
from helpers.errores import assert_error, assert_montos_en_details
from helpers.espera import esperar_hasta
from helpers.montos import SIMBOLO, a_int, a_str, es_monto_valido, quote_min


@pytest.mark.at("AT-09-01-01")
def test_registro_de_cuenta_devuelve_201_sin_secretos(api):
    """HU-09-01 Escenario 1: Registro de cuenta.

    - Dado un email no registrado y una contraseña válida
    - Cuando el cliente hace POST /api/v1/auth/register con {email, password}
    - Entonces la respuesta es 201 con cuerpo {accountId, email, createdAt}
    - Y no se expone la contraseña ni hash alguno en la respuesta
    """
    # Dado
    email = email_unico("reg")

    # Cuando
    resp = api.post("/auth/register", json={"email": email, "password": PASSWORD_DEFECTO})

    # Entonces
    assert resp.status_code == 201, resp.text
    cuerpo = resp.json()
    assert set(cuerpo) >= {"accountId", "email", "createdAt"}, cuerpo
    assert cuerpo["email"] == email

    # Y (la contraseña o cualquier derivado no aparece en la respuesta)
    assert PASSWORD_DEFECTO not in resp.text
    assert not any(clave in cuerpo for clave in ("password", "passwordHash", "hash", "salt"))


@pytest.mark.at("AT-09-01-02")
def test_login_devuelve_token_utilizable_y_rechaza_credenciales_incorrectas(api):
    """HU-09-01 Escenario 2: Login devuelve token.

    - Dado una cuenta registrada
    - Cuando POST /api/v1/auth/login con credenciales correctas
    - Entonces 200 con un token (string) utilizable como Authorization: Bearer
    - Y con credenciales incorrectas responde INVALID_CREDENTIALS (401) sin
      revelar si el email existe
    """
    # Dado
    email = email_unico("login")
    registrar(api, email=email)

    # Cuando
    resp = api.post("/auth/login", json={"email": email, "password": PASSWORD_DEFECTO})

    # Entonces: 200 con token string utilizable en un endpoint protegido
    assert resp.status_code == 200, resp.text
    token = resp.json().get("token")
    assert isinstance(token, str) and token, resp.text
    assert api.con_token(token).get("/me").status_code == 200

    # Y: password incorrecta ⇒ INVALID_CREDENTIALS (401)
    resp_mala = api.post("/auth/login", json={"email": email, "password": "incorrecta-123"})
    err_mala = assert_error(resp_mala, "INVALID_CREDENTIALS")

    # Y: email inexistente ⇒ mismo code y status (no revela si el email existe)
    resp_fantasma = api.post(
        "/auth/login", json={"email": email_unico("fantasma"), "password": PASSWORD_DEFECTO}
    )
    err_fantasma = assert_error(resp_fantasma, "INVALID_CREDENTIALS")
    assert err_mala["code"] == err_fantasma["code"]
    assert resp_mala.status_code == resp_fantasma.status_code


@pytest.mark.at("AT-09-01-03")
def test_perfil_propio_devuelve_los_datos_de_la_cuenta_del_token(usuario):
    """HU-09-01 Escenario 3: Perfil propio.

    - Dado un token válido
    - Cuando el cliente hace GET /api/v1/me
    - Entonces 200 con {accountId, email, createdAt} de la cuenta dueña del token
    """
    # Cuando
    resp = usuario.api.get("/me")

    # Entonces
    assert resp.status_code == 200, resp.text
    cuerpo = resp.json()
    assert set(cuerpo) >= {"accountId", "email", "createdAt"}, cuerpo
    assert cuerpo["accountId"] == usuario.account_id
    assert cuerpo["email"] == usuario.email
    assert es_timestamp_utc(cuerpo["createdAt"]), cuerpo["createdAt"]


@pytest.mark.at("AT-09-01-04")
def test_alta_de_orden_limit_feliz_devuelve_201_con_montos_string(usuario, rpc):
    """HU-09-01 Escenario 4: Alta de orden limit (feliz).

    - Dado un token válido y balance suficiente
    - Cuando POST /api/v1/orders {clientOrderId, symbol, side: BUY, type: LIMIT,
      priceMin: "2000500000", quantityWei: "1000000000000000000"}
    - Entonces 201 con el objeto orden: orderId, status ∈ {OPEN, PARTIALLY_FILLED,
      FILLED} (nunca REJECTED), priceMin/quantityWei ecoados, filledWei/feeWei/
      feeUsdcMin como strings
    - Y si quedó OPEN sin fills: filledWei == "0" y fees "0"; si tuvo fills,
      feeWei acumula (BUY recibe ETH) y feeUsdcMin == "0" (RN-2/RN-5)
    - Y todos los montos matchean ^(0|[1-9][0-9]*)$
    """
    # Dado: balance USDC suficiente para bloquear R = floor(q×P/10^18) (HU-04-01 RN-3)
    fondear_usdc(usuario, rpc, 2_100_000_000)  # 2100 USDC > 2000.5 requeridos

    # Cuando
    resp = usuario.api.post(
        "/orders",
        json={
            "clientOrderId": id_cliente("feliz"),
            "symbol": SIMBOLO,
            "side": "BUY",
            "type": "LIMIT",
            "priceMin": "2000500000",
            "quantityWei": "1000000000000000000",
        },
    )

    # Entonces
    assert resp.status_code == 201, resp.text
    orden = resp.json()
    assert set(orden) >= CAMPOS_ORDEN, orden
    assert orden["status"] in ("OPEN", "PARTIALLY_FILLED", "FILLED"), orden
    assert orden["priceMin"] == "2000500000"
    assert orden["quantityWei"] == "1000000000000000000"

    # Y: montos siempre string entero; fees según fills (BUY acumula en feeWei)
    for campo in ("priceMin", "quantityWei", "filledWei", "feeWei", "feeUsdcMin"):
        assert es_monto_valido(orden[campo]), (campo, orden[campo])
    assert orden["feeUsdcMin"] == "0"  # BUY recibe ETH: la fee jamás va en USDC
    if orden["status"] == "OPEN" and orden["filledWei"] == "0":
        assert orden["feeWei"] == "0"
    if a_int(orden["filledWei"]) == 0:
        assert orden["feeWei"] == "0"

    # (higiene del libro compartido: retirar el remanente)
    cancelar_silencioso(usuario, orden["orderId"])


@pytest.mark.at("AT-09-01-05")
def test_alta_market_sin_precio_y_errores_de_precio_por_tipo(api, usuario, usuario_b, rpc):
    """HU-09-01 Escenario 5: Alta de orden market (borde: sin precio).

    - Dado un token válido y liquidez en el lado opuesto
    - Cuando envía {side: SELL, type: MARKET, quantityWei: "100000000000000"} sin priceMin
    - Entonces 201 con el objeto orden y priceMin: null
    - Y MARKET con priceMin produce PRICE_NOT_ALLOWED (422)
    - Y LIMIT sin priceMin produce PRICE_REQUIRED (422)

    Nota de dominio: el notional estimado de una MARKET SELL usa el mejor bid
    (HU-04-02 RN-3) y debe ser ≥ 10 USDC; con q = 10^14 wei eso exige un bid a
    ≥ 100000 USDC/ETH. Se construye ese bid tras barrer el lado ask.
    """
    # Dado: lado ask vacío + un bid propio de usuario_b a precio suficiente para
    # que floor(10^14 × P / 10^18) ≥ MIN_NOTIONAL (liquidez del lado opuesto)
    barrer_asks(api, rpc)
    q = 100_000_000_000_000  # 10^14 wei (1 lot), la cantidad literal del escenario
    p = max(100_000_000_000, precio_dominante(api))  # ≥ 100000 USDC/ETH, tick-aligned
    tomar_con_buy(usuario_b, rpc, p, q)  # bid resting (no hay asks que cruzar)
    fondear_eth(usuario, rpc, q)  # la MARKET SELL reserva la base (HU-04-02 RN-5)

    # Cuando: MARKET SELL sin priceMin
    resp = usuario.api.post(
        "/orders",
        json={
            "clientOrderId": id_cliente("mkt"),
            "symbol": SIMBOLO,
            "side": "SELL",
            "type": "MARKET",
            "quantityWei": a_str(q),
        },
    )

    # Entonces: 201 con priceMin null
    assert resp.status_code == 201, resp.text
    orden = resp.json()
    assert orden["priceMin"] is None, orden
    assert orden["status"] == "FILLED", orden  # consumió el único bid, exacto

    # Y: MARKET con priceMin ⇒ PRICE_NOT_ALLOWED (422)
    resp = usuario.api.post(
        "/orders",
        json={
            "clientOrderId": id_cliente("mkt-p"),
            "symbol": SIMBOLO,
            "side": "SELL",
            "type": "MARKET",
            "priceMin": a_str(p),
            "quantityWei": a_str(q),
        },
    )
    assert_error(resp, "PRICE_NOT_ALLOWED")

    # Y: LIMIT sin priceMin ⇒ PRICE_REQUIRED (422)
    resp = usuario.api.post(
        "/orders",
        json={
            "clientOrderId": id_cliente("lim-sp"),
            "symbol": SIMBOLO,
            "side": "SELL",
            "type": "LIMIT",
            "quantityWei": a_str(q),
        },
    )
    assert_error(resp, "PRICE_REQUIRED")


@pytest.mark.at("AT-09-01-06")
def test_detalle_de_orden_devuelve_el_objeto_completo(api, usuario, rpc):
    """HU-09-01 Escenario 6: Detalle de orden.

    - Dado una orden propia con orderId conocido
    - Cuando GET /api/v1/orders/{orderId}
    - Entonces 200 con el objeto orden completo y sus montos como strings
    """
    # Dado: una orden propia resting (bid por debajo del mejor ask)
    p = precio_bid_seguro(api)
    q = cantidad_para_notional(p)
    fondear_usdc(usuario, rpc, quote_min(q, p) + 10_000_000)
    orden = crear_orden(usuario, "BUY", "LIMIT", price_min=p, quantity_wei=q)

    # Cuando
    resp = usuario.api.get(f"/orders/{orden['orderId']}")

    # Entonces: objeto completo (HU-09-01 RN-5), montos string, timestamps ISO
    assert resp.status_code == 200, resp.text
    detalle = resp.json()
    assert set(detalle) >= CAMPOS_ORDEN, detalle
    assert detalle["orderId"] == orden["orderId"]
    assert detalle["symbol"] == SIMBOLO
    for campo in ("priceMin", "quantityWei", "filledWei", "feeWei", "feeUsdcMin"):
        assert es_monto_valido(detalle[campo]), (campo, detalle[campo])
    assert es_timestamp_utc(detalle["createdAt"]) and es_timestamp_utc(detalle["updatedAt"])

    cancelar_silencioso(usuario, orden["orderId"])


@pytest.mark.at("AT-09-01-07")
def test_listado_de_ordenes_paginado_con_cursor_estable(api, usuario, rpc):
    """HU-09-01 Escenario 7: Listado de órdenes con paginación.

    - Dado una cuenta con más órdenes que el limit solicitado
    - Cuando GET /api/v1/orders?status=OPEN&limit=2
    - Entonces 200 con {items, nextCursor}, items.length ≤ 2, todas OPEN y propias
    - Y items ordenados por createdAt descendente
    - Y ?cursor=<cursor> da la página siguiente sin solapamiento
    - Y una orden creada entre páginas NO aparece al paginar con el cursor previo (RN-8)
    - Y limit=0 o limit=500 (> máx) produce VALIDATION_ERROR (422)
    """
    # Dado: 3 órdenes OPEN propias (bids resting que no cruzan)
    p = precio_bid_seguro(api)
    q = cantidad_para_notional(p)
    fondear_usdc(usuario, rpc, 4 * quote_min(q, p) + 10_000_000)
    ordenes = [crear_orden(usuario, "BUY", "LIMIT", price_min=p, quantity_wei=q) for _ in range(3)]
    ids_propios = {o["clientOrderId"] for o in ordenes}
    try:
        # Cuando
        resp = usuario.api.get("/orders", params={"status": "OPEN", "limit": 2})

        # Entonces
        assert resp.status_code == 200, resp.text
        pagina1 = resp.json()
        assert set(pagina1) >= {"items", "nextCursor"}, pagina1
        assert len(pagina1["items"]) <= 2
        assert pagina1["nextCursor"], "con 3 órdenes OPEN y limit=2 debe haber nextCursor"
        for item in pagina1["items"]:
            assert item["status"] == "OPEN", item
            assert item["clientOrderId"] in ids_propios, "item ajeno o inesperado en el listado"

        # Y: orden por createdAt descendente (el primero es el más reciente)
        fechas = [item["createdAt"] for item in pagina1["items"]]
        assert fechas == sorted(fechas, reverse=True), fechas

        # Y: una orden creada DESPUÉS de emitido el cursor no aparece con ese cursor
        orden_nueva = crear_orden(usuario, "BUY", "LIMIT", price_min=p, quantity_wei=q)
        ordenes.append(orden_nueva)

        resp = usuario.api.get(
            "/orders",
            params={"status": "OPEN", "limit": 2, "cursor": pagina1["nextCursor"]},
        )
        assert resp.status_code == 200, resp.text
        pagina2 = resp.json()
        ids_p1 = {i["orderId"] for i in pagina1["items"]}
        ids_p2 = {i["orderId"] for i in pagina2["items"]}
        assert not ids_p1 & ids_p2, "páginas consecutivas solapadas"
        assert orden_nueva["orderId"] not in ids_p2, "el cursor no es estable (RN-8)"
        # entre ambas páginas están exactamente las 3 órdenes previas al cursor
        assert ids_p1 | ids_p2 == {o["orderId"] for o in ordenes[:3]}

        # Y: limit inválido ⇒ VALIDATION_ERROR (422)
        assert_error(usuario.api.get("/orders", params={"limit": 0}), "VALIDATION_ERROR")
        assert_error(usuario.api.get("/orders", params={"limit": 500}), "VALIDATION_ERROR")
    finally:
        for o in ordenes:
            cancelar_silencioso(usuario, o["orderId"])


@pytest.mark.at("AT-09-01-08")
def test_cancelacion_de_orden_abierta_y_rechazo_sobre_orden_llena(api, usuario, usuario_b, rpc):
    """HU-09-01 Escenario 8: Cancelación de orden.

    - Dado una orden propia en estado OPEN
    - Cuando DELETE /api/v1/orders/{orderId}
    - Entonces 200 con la orden en estado CANCELLED
    - Y cancelar una orden ya FILLED produce ORDER_NOT_CANCELLABLE (409) con details.status
    """
    # Dado: una orden propia OPEN (bid resting)
    p = precio_bid_seguro(api)
    q = cantidad_para_notional(p)
    fondear_usdc(usuario, rpc, quote_min(q, p) + 10_000_000)
    orden = crear_orden(usuario, "BUY", "LIMIT", price_min=p, quantity_wei=q)
    assert orden["status"] == "OPEN", orden

    # Cuando / Entonces: DELETE ⇒ 200 con status CANCELLED
    resp = usuario.api.delete(f"/orders/{orden['orderId']}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "CANCELLED", resp.text

    # Y: una orden FILLED no es cancelable (cruce determinista: ask dominante propio
    # con el lado ask barrido, tomado por usuario_b)
    barrer_asks(api, rpc)
    ask, p2, q2 = colocar_ask_dominante(usuario, api, rpc)
    tomar_con_buy(usuario_b, rpc, p2, q2)
    esperar_hasta(
        lambda: usuario.api.get(f"/orders/{ask['orderId']}").json()["status"] == "FILLED",
        mensaje="el ask no llegó a FILLED tras el cruce",
    )
    resp = usuario.api.delete(f"/orders/{ask['orderId']}")
    err = assert_error(resp, "ORDER_NOT_CANCELLABLE")
    assert err["details"]["status"] == "FILLED", err


@pytest.mark.at("AT-09-01-09")
def test_balances_con_invariantes_y_montos_string(usuario):
    """HU-09-01 Escenario 9: Balances.

    - Dado un token válido
    - Cuando GET /api/v1/balances
    - Entonces 200 con un arreglo que incluye ETH y USDC con available/locked/total strings
    - Y para cada activo total == available + locked (INV-3) y todos ≥ 0 (INV-2)
    """
    # Cuando
    resp = usuario.api.get("/balances")

    # Entonces
    assert resp.status_code == 200, resp.text
    balances = {b["asset"]: b for b in resp.json()}
    assert {"ETH", "USDC"} <= set(balances), balances

    # Y: serialización string + INV-2/INV-3 exactos (aritmética entera)
    for asset in ("ETH", "USDC"):
        b = balances[asset]
        disponible = a_int(b["available"])
        bloqueado = a_int(b["locked"])
        total = a_int(b["total"])
        assert disponible >= 0 and bloqueado >= 0 and total >= 0  # INV-2
        assert total == disponible + bloqueado, b  # INV-3


@pytest.mark.at("AT-09-01-10")
def test_direccion_de_deposito_eip55_y_asset_no_soportado(usuario):
    """HU-09-01 Escenario 10: Dirección de depósito.

    - Dado un token válido
    - Cuando GET /api/v1/deposit-address?asset=ETH
    - Entonces 200 con {asset: "ETH", address} con formato 0x+40hex y checksum EIP-55
    - Y ?asset=BTC (no soportado) produce VALIDATION_ERROR (422)
    """
    # Cuando
    resp = usuario.api.get("/deposit-address", params={"asset": "ETH"})

    # Entonces
    assert resp.status_code == 200, resp.text
    cuerpo = resp.json()
    assert cuerpo["asset"] == "ETH"
    assert_direccion(cuerpo["address"])  # 0x + 40 hex + checksum EIP-55

    # Y: activo no soportado ⇒ VALIDATION_ERROR (422)
    resp = usuario.api.get("/deposit-address", params={"asset": "BTC"})
    assert_error(resp, "VALIDATION_ERROR")


@pytest.mark.at("AT-09-01-11")
def test_crear_retiro_responde_202_asincrono(usuario, rpc):
    """HU-09-01 Escenario 11: Creación de retiro (asíncrono, 202).

    - Dado un token válido y balance disponible suficiente
    - Cuando POST /api/v1/withdrawals {asset: USDC, amountMinUnit: "25000000", address}
    - Entonces 202 con {withdrawalId, asset, amountMinUnit, address, status: PENDING,
      createdAt, updatedAt} (timestamps ISO-8601 UTC)
    - Y un retiro de ETH por "1000000000000000000" (1 ETH en wei) responde 202
    - Y una address con checksum EIP-55 inválido produce INVALID_ADDRESS (422)
    - Y un amountMinUnit mayor al disponible produce INSUFFICIENT_FUNDS (422)
    """
    # Dado: USDC disponible + ETH disponible (monto del retiro ETH y previsión de
    # fee de red en ETH, HU-08-01 RN-9)
    fondear_usdc(usuario, rpc, 30_000_000)                 # 30 USDC
    fondear_eth(usuario, rpc, 1_100_000_000_000_000_000)   # 1.1 ETH (1 + gas)

    # Cuando: retiro de 25 USDC (unidad mínima USDC)
    resp = usuario.api.post(
        "/withdrawals",
        json={"asset": "USDC", "amountMinUnit": "25000000", "address": DESTINO_RETIRO},
    )

    # Entonces: 202 Accepted con el objeto retiro en PENDING
    assert resp.status_code == 202, resp.text
    retiro = resp.json()
    assert set(retiro) >= {"withdrawalId", "asset", "amountMinUnit", "address",
                           "status", "createdAt", "updatedAt"}, retiro
    assert retiro["status"] == "PENDING"
    assert retiro["asset"] == "USDC"
    assert retiro["amountMinUnit"] == "25000000"
    assert es_monto_valido(retiro["amountMinUnit"])
    assert retiro["withdrawalId"]
    assert es_timestamp_utc(retiro["createdAt"]), retiro["createdAt"]
    assert es_timestamp_utc(retiro["updatedAt"]), retiro["updatedAt"]

    # Y: retiro de ETH con amountMinUnit interpretado como wei ⇒ 202
    resp = usuario.api.post(
        "/withdrawals",
        json={"asset": "ETH", "amountMinUnit": "1000000000000000000",
              "address": DESTINO_RETIRO},
    )
    assert resp.status_code == 202, resp.text
    assert resp.json()["asset"] == "ETH"
    assert resp.json()["amountMinUnit"] == "1000000000000000000"

    # Y: checksum EIP-55 inválido ⇒ INVALID_ADDRESS (422)
    resp = usuario.api.post(
        "/withdrawals",
        json={"asset": "USDC", "amountMinUnit": "1000000",
              "address": romper_checksum(DESTINO_RETIRO)},
    )
    assert_error(resp, "INVALID_ADDRESS")

    # Y: monto mayor al disponible ⇒ INSUFFICIENT_FUNDS (422) con montos string
    resp = usuario.api.post(
        "/withdrawals",
        json={"asset": "USDC", "amountMinUnit": "99000000000", "address": DESTINO_RETIRO},
    )
    err = assert_error(resp, "INSUFFICIENT_FUNDS")
    assert_montos_en_details(err["details"], "required", "available")


@pytest.mark.at("AT-09-01-12")
def test_listar_depositos_y_retiros_con_esquemas_del_contrato(usuario, rpc):
    """HU-09-01 Escenario 12: Listar depósitos y retiros.

    - Dado un token válido (con un depósito acreditado y un retiro creado)
    - Cuando GET /api/v1/deposits y GET /api/v1/withdrawals
    - Entonces ambas 200 con {items, nextCursor} solo de la cuenta dueña
    - Y cada depósito cumple el esquema de RN-17 (depositId = "<txHash>:<logIndex>",
      montos string, conteos enteros JSON, required = 12, creditedAt solo si ACREDITADO)
    - Y cada retiro cumple el esquema de RN-18 (txHash|null, confirmations entero,
      failureReason no nulo solo si FAILED)
    - Y GET /withdrawals/{id} propio devuelve 200 con ese objeto; inexistente/ajeno ⇒ 404
    """
    # Dado: un depósito USDC real acreditado (guardando su txHash) y ETH para el gas
    direccion = direccion_de_deposito(usuario, "USDC")
    tx_deposito = rpc.depositar_usdc(direccion, 10_000_000)  # 10 USDC + 12 confirmaciones
    fondear_eth(usuario, rpc, 10_000_000_000_000_000)        # 0.01 ETH (previsión de gas)

    def _deposito_listado():
        items = usuario.api.get("/deposits").json()["items"]
        propios = [i for i in items if i["txHash"] == tx_deposito]
        return propios[0] if propios and propios[0]["status"] == "ACREDITADO" else None

    deposito = esperar_hasta(_deposito_listado, mensaje="el depósito no apareció ACREDITADO")

    # ... y un retiro creado
    resp = usuario.api.post(
        "/withdrawals",
        json={"asset": "USDC", "amountMinUnit": "5000000", "address": DESTINO_RETIRO},
    )
    assert resp.status_code == 202, resp.text
    retiro_id = resp.json()["withdrawalId"]

    # Cuando / Entonces: GET /deposits con el esquema de RN-17
    resp = usuario.api.get("/deposits")
    assert resp.status_code == 200, resp.text
    cuerpo = resp.json()
    assert set(cuerpo) >= {"items", "nextCursor"}, cuerpo
    assert set(deposito) >= {"depositId", "txHash", "logIndex", "asset", "amountMinUnit",
                             "status", "confirmations", "required", "blockNumber",
                             "createdAt", "updatedAt"}, deposito
    assert deposito["depositId"] == f"{deposito['txHash']}:{deposito['logIndex']}"
    assert RE_TXHASH.fullmatch(deposito["txHash"]), deposito["txHash"]
    assert deposito["asset"] == "USDC"
    assert deposito["amountMinUnit"] == "10000000"
    assert deposito["status"] in ("PENDIENTE", "ACREDITADO", "DESCARTADO")
    for conteo in ("confirmations", "required", "logIndex", "blockNumber"):
        assert es_entero_json(deposito[conteo]), (conteo, deposito[conteo])
    assert deposito["required"] == 12
    # creditedAt solo si ACREDITADO; discardReason solo si DESCARTADO
    assert deposito["status"] == "ACREDITADO" and deposito.get("creditedAt")
    assert deposito.get("discardReason") in (None,), deposito

    # Y: GET /withdrawals con el esquema de RN-18
    resp = usuario.api.get("/withdrawals")
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    retiro = next(i for i in items if i["withdrawalId"] == retiro_id)
    assert set(retiro) >= {"withdrawalId", "asset", "amountMinUnit", "address", "txHash",
                           "confirmations", "status", "failureReason",
                           "createdAt", "updatedAt"}, retiro
    assert retiro["status"] in ("PENDING", "BROADCAST", "CONFIRMED", "FAILED")
    assert es_monto_valido(retiro["amountMinUnit"])
    assert es_entero_json(retiro["confirmations"]), retiro["confirmations"]
    assert retiro["txHash"] is None or RE_TXHASH.fullmatch(retiro["txHash"]), retiro
    if retiro["status"] != "FAILED":
        assert retiro["failureReason"] is None, retiro

    # Y: detalle de retiro propio ⇒ 200 con el mismo objeto (identidad estable)
    resp = usuario.api.get(f"/withdrawals/{retiro_id}")
    assert resp.status_code == 200, resp.text
    detalle = resp.json()
    for campo in ("withdrawalId", "asset", "amountMinUnit", "address"):
        assert detalle[campo] == retiro[campo], (campo, detalle, retiro)

    # Y: retiro inexistente ⇒ NOT_FOUND (404)
    assert_error(usuario.api.get("/withdrawals/w-inexistente-000"), "NOT_FOUND")


@pytest.mark.at("AT-09-01-13")
def test_orderbook_publico_ordenado_y_con_montos_string(api, usuario, usuario_b, rpc):
    """HU-09-01 Escenario 13: Orderbook de mercado (público).

    - Dado que existen órdenes abiertas en ambos lados
    - Cuando un cliente (sin token) hace GET /api/v1/market/orderbook?depth=10
    - Entonces la respuesta es 200 con {symbol, sequence, bids, asks}
    - Y bids desc, asks asc, sin niveles cruzados (best_bid < best_ask) (INV-7)
    - Y cada nivel es [priceMin, quantityWei] con ambos como strings
    """
    # Dado: liquidez en ambos lados, construida por el test (un ask que no cruza
    # bids y un bid por debajo del mejor ask)
    p_ask = precio_dominante(api)
    q_ask = cantidad_para_notional(p_ask)
    fondear_eth(usuario, rpc, q_ask)
    ask = crear_orden(usuario, "SELL", "LIMIT", price_min=p_ask, quantity_wei=q_ask)

    p_bid = precio_bid_seguro(api)
    q_bid = cantidad_para_notional(p_bid)
    fondear_usdc(usuario_b, rpc, quote_min(q_bid, p_bid) + 10_000_000)
    bid = crear_orden(usuario_b, "BUY", "LIMIT", price_min=p_bid, quantity_wei=q_bid)

    try:
        # Cuando (sin token: fixture `api`)
        resp = api.get("/market/orderbook", params={"depth": 10})

        # Entonces
        assert resp.status_code == 200, resp.text
        libro_ = resp.json()
        assert libro_["symbol"] == SIMBOLO
        assert es_entero_json(libro_["sequence"])  # conteo: entero JSON, no string

        bids, asks = libro_["bids"], libro_["asks"]
        assert bids and asks, "el Dado garantiza órdenes en ambos lados"

        # cada nivel es [priceMin, quantityWei], ambos strings bien serializados
        for nivel in bids + asks:
            precio, cantidad = nivel
            assert es_monto_valido(precio), nivel
            assert es_monto_valido(cantidad), nivel

        precios_bid = [a_int(p) for p, _ in bids]
        precios_ask = [a_int(p) for p, _ in asks]
        assert precios_bid == sorted(precios_bid, reverse=True), "bids no descendentes"
        assert precios_ask == sorted(precios_ask), "asks no ascendentes"
        assert precios_bid[0] < precios_ask[0], "libro cruzado (INV-7)"
    finally:
        cancelar_silencioso(usuario, ask["orderId"])
        cancelar_silencioso(usuario_b, bid["orderId"])


@pytest.mark.at("AT-09-01-14")
def test_trades_recientes_publicos_ordenados_y_con_limit_validado(api, usuario, usuario_b, rpc):
    """HU-09-01 Escenario 14: Trades recientes (público).

    - Dado que hubo fills
    - Cuando GET /api/v1/market/trades?limit=5 (sin token)
    - Entonces 200 con items del más reciente al más antiguo (≤ 5), cada uno
      {tradeId, priceMin, quantityWei, takerSide, timestamp}
    - Y ?limit=0 y ?limit=999 (> máx 200) producen VALIDATION_ERROR (422)
    - Y si no hubo trades, items es [] con status 200
    """
    # Dado: un fill determinista (ask dominante propio tomado por un BUY)
    barrer_asks(api, rpc)
    _, p, q = colocar_ask_dominante(usuario, api, rpc)
    tomar_con_buy(usuario_b, rpc, p, q)

    # Cuando (sin token)
    resp = api.get("/market/trades", params={"limit": 5})

    # Entonces
    assert resp.status_code == 200, resp.text
    cuerpo = resp.json()
    assert cuerpo["symbol"] == SIMBOLO
    items = cuerpo["items"]
    assert 0 < len(items) <= 5
    for t in items:
        assert set(t) >= {"tradeId", "priceMin", "quantityWei", "takerSide", "timestamp"}, t
        assert es_monto_valido(t["priceMin"]) and es_monto_valido(t["quantityWei"]), t
        assert t["takerSide"] in ("BUY", "SELL"), t
        assert es_timestamp_utc(t["timestamp"]), t
    # del más reciente al más antiguo; el más reciente es nuestro fill
    fechas = [t["timestamp"] for t in items]
    assert fechas == sorted(fechas, reverse=True), fechas
    assert items[0]["priceMin"] == a_str(p) and items[0]["quantityWei"] == a_str(q)
    assert items[0]["takerSide"] == "BUY"

    # Y: limit inválido ⇒ VALIDATION_ERROR (422)
    assert_error(api.get("/market/trades", params={"limit": 0}), "VALIDATION_ERROR")
    assert_error(api.get("/market/trades", params={"limit": 999}), "VALIDATION_ERROR")

    # Y: la cláusula "sin trades ⇒ items []" no es construible una vez que el SUT
    # registró fills (no hay forma black-box de borrar el historial); se cubre por
    # equivalencia: el endpoint nunca falla por falta de trades (status siempre 200).


@pytest.mark.at("AT-09-01-15", "AT-09-05-10")
def test_ruta_inexistente_404_y_metodo_no_permitido_405(api, usuario):
    """HU-09-01 Escenario 15 / HU-09-05 Escenario 10: NOT_FOUND y METHOD_NOT_ALLOWED.

    - Dado la ruta base /api/v1
    - Cuando GET /api/v1/foo (ruta inexistente)
    - Entonces 404 con envelope { error: { code: "NOT_FOUND" } }
    - Y PUT /api/v1/balances (método no permitido sobre ruta existente) responde 405
      con envelope y details = { method, allowed } (RN-14, HU-09-05 RN-10)
    """
    # Cuando: ruta inexistente bajo /api/v1
    resp = api.get("/foo")
    # Entonces
    assert_error(resp, "NOT_FOUND")

    # Y: método no permitido sobre ruta existente (con token válido, para que la
    # precedencia de auth no interfiera: modelo-de-errores §4)
    resp = usuario.api.request("PUT", "/balances")
    err = assert_error(resp, "METHOD_NOT_ALLOWED")
    detalles = err.get("details") or {}
    assert detalles.get("method") == "PUT", err
    assert isinstance(detalles.get("allowed"), list) and "GET" in detalles["allowed"], err


@pytest.mark.at("AT-09-01-16")
def test_cuerpo_no_json_y_montos_mal_serializados_son_validation_error(usuario):
    """HU-09-01 Escenario 16 (error): Cuerpo no JSON / monto mal serializado.

    - Dado un token válido
    - Cuando hace POST /api/v1/orders con un cuerpo que no es JSON válido
    - Entonces la respuesta es VALIDATION_ERROR (422) con details.issues
    - Y montos que violan ^(0|[1-9][0-9]*)$ (número JSON, decimal, negativo,
      cero a la izquierda) también producen VALIDATION_ERROR (422)
    - Y un clientOrderId vacío produce VALIDATION_ERROR (422) en el paso de esquema
    """
    # Cuando: cuerpo que no es JSON válido
    resp = usuario.api.post("/orders", content=b"esto no es json {")
    # Entonces
    err = assert_error(resp, "VALIDATION_ERROR")
    assert "issues" in (err.get("details") or {}), err

    # Y: variantes de monto mal serializado, cada una rechazada por esquema
    orden_base = {
        "clientOrderId": "c-at-09-01-16",
        "symbol": "ETH-USDC",
        "side": "BUY",
        "type": "LIMIT",
        "priceMin": "2000500000",
        "quantityWei": "1000000000000000000",
    }
    variantes = [
        {"priceMin": 2000500000},              # número JSON, no string
        {"priceMin": "1.5"},                   # decimal
        {"quantityWei": "-100"},               # negativo
        {"quantityWei": "0100000000000000"},   # cero a la izquierda
    ]
    for cambio in variantes:
        resp = usuario.api.post("/orders", json={**orden_base, **cambio})
        assert_error(resp, "VALIDATION_ERROR")

    # Y: clientOrderId vacío se rechaza en el paso de esquema (RN-19)
    resp = usuario.api.post("/orders", json={**orden_base, "clientOrderId": ""})
    assert_error(resp, "VALIDATION_ERROR")


@pytest.mark.at("AT-09-01-17")
def test_client_order_id_duplicado_es_409_y_no_crea_segunda_orden(api, usuario, rpc):
    """HU-09-01 Escenario 17 (concurrencia/idempotencia): clientOrderId duplicado.

    - Dado que la cuenta ya creó una orden con clientOrderId "c-1"
    - Cuando reenvía POST /api/v1/orders con el mismo clientOrderId
    - Entonces DUPLICATE_CLIENT_ORDER_ID (409) con details.clientOrderId
    - Y no se crea una segunda orden (los balances no cambian por el reintento; INV-1)
    """
    # Dado: una orden propia con clientOrderId conocido (bid resting)
    p = precio_bid_seguro(api)
    q = cantidad_para_notional(p)
    fondear_usdc(usuario, rpc, 2 * quote_min(q, p) + 10_000_000)
    cid = id_cliente("dup")
    cuerpo = {
        "clientOrderId": cid,
        "symbol": SIMBOLO,
        "side": "BUY",
        "type": "LIMIT",
        "priceMin": a_str(p),
        "quantityWei": a_str(q),
    }
    resp = usuario.api.post("/orders", json=cuerpo)
    assert resp.status_code == 201, resp.text
    orden = resp.json()
    balances_previos = balances_por_activo(usuario)

    # Cuando: reintento con el MISMO clientOrderId
    resp = usuario.api.post("/orders", json=cuerpo)

    # Entonces: 409 con details.clientOrderId
    err = assert_error(resp, "DUPLICATE_CLIENT_ORDER_ID")
    assert err["details"]["clientOrderId"] == cid, err

    # Y: el reintento no movió balances ni creó otra orden (INV-1)
    assert balances_por_activo(usuario) == balances_previos
    resp = usuario.api.get("/orders", params={"clientOrderId": cid})
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["items"]) == 1, resp.text

    cancelar_silencioso(usuario, orden["orderId"])


@pytest.mark.at("AT-09-01-18")
def test_paginacion_de_depositos_y_retiros(usuario, rpc):
    """HU-09-01 Escenario 18: Paginación de depósitos/retiros.

    - Dado una cuenta con más depósitos que el limit solicitado
    - Cuando GET /api/v1/deposits?limit=2
    - Entonces 200 con items.length ≤ 2 ordenados por createdAt descendente y
      nextCursor no nulo si hay más páginas
    - Y ?cursor=<cursor> devuelve la página siguiente sin solapamiento
    - Y limit=0 o limit=500 (> máx) produce VALIDATION_ERROR (422)
    - Y lo mismo aplica a GET /api/v1/withdrawals
    """
    # Dado: 3 depósitos USDC acreditados y 3 retiros creados (más ETH para el gas)
    direccion = direccion_de_deposito(usuario, "USDC")
    for _ in range(3):
        rpc.depositar_usdc(direccion, 10_000_000)  # 10 USDC c/u
    esperar_hasta(
        lambda: len(usuario.api.get("/deposits").json()["items"]) >= 3,
        mensaje="no se listaron los 3 depósitos",
    )
    fondear_eth(usuario, rpc, 10_000_000_000_000_000)  # 0.01 ETH (gas de retiros)
    esperar_hasta(
        lambda: a_int(balances_por_activo(usuario)["USDC"]["available"]) >= 30_000_000,
        mensaje="los depósitos USDC no se acreditaron",
    )
    for _ in range(3):
        resp = usuario.api.post(
            "/withdrawals",
            json={"asset": "USDC", "amountMinUnit": "2000000", "address": DESTINO_RETIRO},
        )
        assert resp.status_code == 202, resp.text

    def _paginar(recurso: str, clave_id: str) -> None:
        # Cuando
        resp = usuario.api.get(recurso, params={"limit": 2})
        # Entonces
        assert resp.status_code == 200, resp.text
        pagina1 = resp.json()
        assert len(pagina1["items"]) == 2, pagina1
        fechas = [i["createdAt"] for i in pagina1["items"]]
        assert fechas == sorted(fechas, reverse=True), fechas
        assert pagina1["nextCursor"], f"{recurso}: falta nextCursor con más páginas"

        # Y: página siguiente sin solapamiento
        resp = usuario.api.get(
            recurso, params={"limit": 2, "cursor": pagina1["nextCursor"]}
        )
        assert resp.status_code == 200, resp.text
        pagina2 = resp.json()
        ids1 = {i[clave_id] for i in pagina1["items"]}
        ids2 = {i[clave_id] for i in pagina2["items"]}
        assert ids2 and not ids1 & ids2, f"{recurso}: páginas solapadas"

        # Y: limit inválido ⇒ VALIDATION_ERROR (422)
        assert_error(usuario.api.get(recurso, params={"limit": 0}), "VALIDATION_ERROR")
        assert_error(usuario.api.get(recurso, params={"limit": 500}), "VALIDATION_ERROR")

    _paginar("/deposits", "depositId")
    _paginar("/withdrawals", "withdrawalId")


@pytest.mark.at("AT-09-01-19")
def test_ticker_publico_top_of_book_con_ultimo_trade(api, usuario, usuario_b, rpc):
    """HU-09-01 Escenario 19: Ticker / top-of-book (público).

    - Dado un orderbook con órdenes en ambos lados y al menos un trade previo
    - Cuando un cliente (sin token) hace GET /api/v1/market/ticker
    - Entonces 200 con {symbol, bestBidPrice, bestAskPrice, lastPrice,
      lastQuantityWei, timestamp}, todos los montos como strings
    - Y bestBidPrice < bestAskPrice (libro no cruzado, INV-7) (RN-16)
    """
    # Dado: un trade determinista + libro con ambos lados poblados
    barrer_asks(api, rpc)
    _, p, q = colocar_ask_dominante(usuario, api, rpc)
    tomar_con_buy(usuario_b, rpc, p, q)  # fill: último trade = (p, q)

    ask2, p2, q2 = colocar_ask_dominante(usuario, api, rpc, precio=p + 100_000)
    p_bid = precio_bid_seguro(api)
    q_bid = cantidad_para_notional(p_bid)
    fondear_usdc(usuario_b, rpc, quote_min(q_bid, p_bid) + 10_000_000)
    bid = crear_orden(usuario_b, "BUY", "LIMIT", price_min=p_bid, quantity_wei=q_bid)

    try:
        # Cuando (sin token)
        resp = api.get("/market/ticker")

        # Entonces
        assert resp.status_code == 200, resp.text
        ticker = resp.json()
        assert set(ticker) >= {"symbol", "bestBidPrice", "bestAskPrice", "lastPrice",
                               "lastQuantityWei", "timestamp"}, ticker
        assert ticker["symbol"] == SIMBOLO
        for campo in ("bestBidPrice", "bestAskPrice", "lastPrice", "lastQuantityWei"):
            assert es_monto_valido(ticker[campo]), (campo, ticker[campo])
        assert es_timestamp_utc(ticker["timestamp"]), ticker["timestamp"]

        # Y: top-of-book sin cruce + último trade reflejado
        assert a_int(ticker["bestBidPrice"]) < a_int(ticker["bestAskPrice"]), ticker
        assert ticker["lastPrice"] == a_str(p), ticker
        assert ticker["lastQuantityWei"] == a_str(q), ticker
    finally:
        cancelar_silencioso(usuario, ask2["orderId"])
        cancelar_silencioso(usuario_b, bid["orderId"])


@pytest.mark.at("AT-09-01-20")
def test_ticker_y_orderbook_con_lados_vacios(api, usuario, rpc):
    """HU-09-01 Escenario 20 (borde): Ticker y orderbook con lados vacíos.

    - Dado un orderbook sin órdenes en el lado ask (solo bids)
    - Cuando GET /api/v1/market/ticker
    - Entonces 200 con bestAskPrice: null y bestBidPrice no nulo (RN-16)
    - Y lastPrice/lastQuantityWei son null si NO hubo trades (RN-16); como el
      historial del SUT compartido puede ya tener trades, se verifica la regla
      por consistencia con GET /market/trades (null ⇔ sin trades)
    - Y GET /market/orderbook devuelve asks: [] con bids no vacío; con el libro
      totalmente vacío devuelve {bids: [], asks: []} (RN-12), siempre 200
    """
    # Dado: lado ask vacío y al menos un bid propio
    barrer_asks(api, rpc)
    p_bid = precio_bid_seguro(api)  # sin asks: 1000 USDC
    q_bid = cantidad_para_notional(p_bid)
    fondear_usdc(usuario, rpc, quote_min(q_bid, p_bid) + 10_000_000)
    bid = crear_orden(usuario, "BUY", "LIMIT", price_min=p_bid, quantity_wei=q_bid)

    # Cuando
    resp = api.get("/market/ticker")

    # Entonces: ask vacío ⇒ bestAskPrice null; hay bids ⇒ bestBidPrice string
    assert resp.status_code == 200, resp.text
    ticker = resp.json()
    assert ticker["bestAskPrice"] is None, ticker
    assert es_monto_valido(ticker["bestBidPrice"]), ticker

    # Y: lastPrice/lastQuantityWei nulos ⇔ sin trades (RN-16)
    trades = api.get("/market/trades", params={"limit": 1}).json()["items"]
    if trades:
        assert ticker["lastPrice"] == trades[0]["priceMin"], ticker
        assert es_monto_valido(ticker["lastQuantityWei"]), ticker
    else:
        assert ticker["lastPrice"] is None and ticker["lastQuantityWei"] is None, ticker

    # Y: orderbook con asks: [] y bids no vacío, status 200
    resp = api.get("/market/orderbook", params={"depth": 10})
    assert resp.status_code == 200, resp.text
    libro_ = resp.json()
    assert libro_["asks"] == [], libro_
    assert libro_["bids"], libro_

    # Y: libro totalmente vacío ⇒ {bids: [], asks: []}, status 200
    cancelar_silencioso(usuario, bid["orderId"])
    barrer_bids(api, rpc)
    resp = api.get("/market/orderbook", params={"depth": 10})
    assert resp.status_code == 200, resp.text
    libro_ = resp.json()
    assert libro_["bids"] == [] and libro_["asks"] == [], libro_


@pytest.mark.at("AT-09-01-21")
def test_market_buy_sin_liquidez_es_422_y_no_muta_estado(api, usuario, rpc):
    """HU-09-01 Escenario 21 (error): Orden MARKET sin liquidez.

    - Dado un orderbook con el lado SELL (asks) vacío
    - Cuando envía una MARKET BUY válida en esquema y con fondos suficientes
    - Entonces MARKET_NO_LIQUIDITY (422) con el envelope de error estándar
    - Y los balances quedan idénticos (INV-1, INV-2) y no se crea ninguna orden
      ni queda remanente en el libro
    """
    # Dado: asks vacíos + fondos suficientes
    barrer_asks(api, rpc)
    fondear_usdc(usuario, rpc, 100_000_000)  # 100 USDC
    balances_previos = balances_por_activo(usuario)
    bids_previos = libro(api)["bids"]
    cid = id_cliente("mkt-noliq")

    # Cuando: MARKET BUY válida en esquema (cantidad múltiplo de lot)
    resp = usuario.api.post(
        "/orders",
        json={
            "clientOrderId": cid,
            "symbol": SIMBOLO,
            "side": "BUY",
            "type": "MARKET",
            "quantityWei": "10000000000000000",  # 0.01 ETH
        },
    )

    # Entonces
    assert_error(resp, "MARKET_NO_LIQUIDITY")

    # Y: balances idénticos, libro intacto y sin orden abierta ni remanente.
    # (TODO-REVISAR: AT-09-01-21 dice "no se crea ninguna orden" pero HU-04-02
    # RN-4 persiste la orden como REJECTED en el historial; acá se verifica lo
    # observable no contradictorio: nada abierto, nada resting, balances iguales.)
    assert balances_por_activo(usuario) == balances_previos
    libro_ = libro(api)
    assert libro_["asks"] == [], libro_
    assert libro_["bids"] == bids_previos, "el rechazo no debe tocar el libro"
    abiertas = usuario.api.get("/orders", params={"status": "OPEN"}).json()["items"]
    assert not any(o["clientOrderId"] == cid for o in abiertas)


@pytest.mark.at("AT-09-01-22")
def test_market_con_fill_parcial_y_liquidez_agotada_queda_cancelled(api, usuario, usuario_b, rpc):
    """HU-09-01 Escenario 22 (borde): MARKET con fill parcial y liquidez agotada.

    - Dado un orderbook cuyo lado opuesto solo alcanza para parte de la cantidad
    - Cuando envía una MARKET por una cantidad mayor a la liquidez disponible
    - Entonces 201 con status "CANCELLED", filledWei > "0" y filledWei < quantityWei
    - Y la orden no queda en el libro (remanente descartado): CANCELLED es el
      estado terminal de esa MARKET (RN-5, HU-03-04 RN-9)
    """
    # Dado: única liquidez del lado ask = 0.02 ETH de usuario_b
    barrer_asks(api, rpc)
    q_disponible = 20_000_000_000_000_000  # 0.02 ETH
    _, p, _ = colocar_ask_dominante(usuario_b, api, rpc, q_wei=q_disponible)

    q_pedida = 50_000_000_000_000_000  # 0.05 ETH > liquidez disponible
    fondear_usdc(usuario, rpc, quote_min(q_pedida, p) + 10_000_000)

    # Cuando
    resp = usuario.api.post(
        "/orders",
        json={
            "clientOrderId": id_cliente("mkt-parcial"),
            "symbol": SIMBOLO,
            "side": "BUY",
            "type": "MARKET",
            "quantityWei": a_str(q_pedida),
        },
    )

    # Entonces: 201 con estado terminal CANCELLED y fill parcial exacto
    assert resp.status_code == 201, resp.text
    orden = resp.json()
    assert orden["status"] == "CANCELLED", orden
    filled = a_int(orden["filledWei"])
    assert 0 < filled < q_pedida, orden
    assert filled == q_disponible, "debió consumir exactamente la liquidez disponible"

    # Y: sin remanente en el libro ni orden abierta (remanente descartado)
    assert libro(api)["asks"] == []
    abiertas = usuario.api.get("/orders", params={"status": "OPEN"}).json()["items"]
    assert not any(o["orderId"] == orden["orderId"] for o in abiertas)
