"""Épica 09 — HU-09-05 (modelo de errores de la API): tests black-box.

Cubre AT-09-05-01, -02, -03, -05, -06, -11 y -12. Los restantes se verifican
en el mismo flujo que su escenario gemelo de otra HU (marcados allí):
AT-09-05-04 → test_ep09_auth (con AT-09-02-04); AT-09-05-07 → test_ep09_ws_publico
(con AT-09-03-09); AT-09-05-08 → test_ep09_auth (con AT-09-02-11);
AT-09-05-10 → test_ep09_contrato (con AT-09-01-15). AT-09-05-09 (500 sin fuga)
está declarado en no_automatizables_ep09.yaml.

El catálogo de `00-fundaciones/modelo-de-errores.md` prevalece: `code` estable,
status del catálogo, envelope uniforme y precedencia determinista (§4).
"""

import json

import pytest

from comunes_ep09 import (
    DESTINO_RETIRO,
    balances_por_activo,
    fondear_usdc,
    id_cliente,
)
from helpers.cuentas import PASSWORD_DEFECTO, email_unico, registrar
from helpers.eip55 import romper_checksum
from helpers.errores import assert_error, assert_montos_en_details, validar_envelope
from helpers.montos import SIMBOLO, a_int, quote_min


def _orden_valida(client_order_id: str | None = None) -> dict:
    """Alta de orden válida en esquema/enums/reglas del par (tick, lot, notional)."""
    return {
        "clientOrderId": client_order_id or id_cliente("err"),
        "symbol": SIMBOLO,
        "side": "BUY",
        "type": "LIMIT",
        "priceMin": "2000000000",              # 2000 USDC, múltiplo de tick
        "quantityWei": "20000000000000000",    # 0.02 ETH, múltiplo de lot; notional 40 USDC
    }


@pytest.mark.at("AT-09-05-01")
def test_envelope_uniforme_en_toda_respuesta_de_error(api):
    """HU-09-05 Escenario 1: Envelope uniforme.

    - Dado cualquier operación que falle
    - Cuando el servidor responde con error
    - Entonces el cuerpo tiene exactamente la forma
      { "error": { "code", "message", "details"? } } con code y message presentes
    """
    # Cuando: errores de tres familias distintas (401, 404, 422)
    respuestas = [
        api.get("/me"),                                     # sin token ⇒ 401
        api.get("/foo"),                                    # ruta inexistente ⇒ 404
        api.get("/market/orderbook", params={"depth": 0}),  # depth inválido ⇒ 422
    ]

    # Entonces: envelope exacto en todas (sin claves extra en la raíz ni en error)
    for resp in respuestas:
        assert resp.status_code in (401, 404, 422), resp.text
        cuerpo = resp.json()
        err = validar_envelope(cuerpo)  # code/message obligatorios, details objeto
        assert set(cuerpo) == {"error"}, cuerpo
        assert set(err) <= {"code", "message", "details"}, err


@pytest.mark.at("AT-09-05-02")
def test_insufficient_funds_mapea_a_422_con_details_estructurado(usuario):
    """HU-09-05 Escenario 2: Mapeo de código a HTTP.

    - Dado un alta de orden con balance insuficiente
    - Cuando el servidor la rechaza
    - Entonces el status HTTP es 422 y error.code == "INSUFFICIENT_FUNDS" con
      details = { asset, required, available }, todos los montos como strings
    """
    # Dado: cuenta fresca sin fondos + orden válida en todo lo que precede a fondos
    cuerpo = _orden_valida()

    # Cuando
    resp = usuario.api.post("/orders", json=cuerpo)

    # Entonces: 422 del catálogo con details estructurado (RN-4/RN-6)
    err = assert_error(resp, "INSUFFICIENT_FUNDS")  # valida status 422 + code
    detalles = err.get("details") or {}
    assert detalles.get("asset") == "USDC", err  # una BUY bloquea quote (HU-04-01 RN-3)
    assert_montos_en_details(detalles, "required", "available")
    assert a_int(detalles["available"]) == 0
    # lo requerido es la reserva R = floor(q×P/10^18) (HU-04-01 RN-3)
    assert a_int(detalles["required"]) == quote_min(
        a_int(cuerpo["quantityWei"]), a_int(cuerpo["priceMin"])
    ), err


@pytest.mark.at("AT-09-05-03")
def test_multiples_violaciones_reportan_solo_el_primer_error(usuario):
    """HU-09-05 Escenario 3 (precedencia): Un error por respuesta.

    - Dado un alta de orden que viola varias reglas a la vez (side inválido Y
      precio fuera de tick Y fondos insuficientes), con token válido
    - Cuando se procesa
    - Entonces se reporta solo el primero según la precedencia (§4):
      INVALID_SIDE (enum, paso 3) antes que INVALID_PRICE_TICK (paso 4) y que
      INSUFFICIENT_FUNDS (paso 6)
    - Y la respuesta contiene un único code
    """
    # Cuando: tres violaciones simultáneas (la cuenta fresca no tiene fondos)
    resp = usuario.api.post(
        "/orders",
        json={
            "clientOrderId": id_cliente("multi"),
            "symbol": SIMBOLO,
            "side": "HOLD",                    # enum inválido (paso 3)
            "type": "LIMIT",
            "priceMin": "2000000001",          # fuera de tick (paso 4)
            "quantityWei": "20000000000000000",
        },
    )

    # Entonces: gana el primero de la precedencia, con un único code
    cuerpo = resp.json()
    assert set(cuerpo) == {"error"}, cuerpo  # un error por respuesta (RN-5)
    err = assert_error(resp, "INVALID_SIDE")
    assert err["code"] == "INVALID_SIDE"


@pytest.mark.at("AT-09-05-05")
def test_validation_error_incluye_issues_con_el_campo_ofensor(usuario):
    """HU-09-05 Escenario 5: VALIDATION_ERROR con issues.

    - Dado un alta de orden cuyo quantityWei viola ^(0|[1-9][0-9]*)$ ("1.5")
    - Cuando se procesa
    - Entonces el code es VALIDATION_ERROR (422) y details.issues describe la(s)
      causa(s), incluyendo el campo ofensor
    """
    # Cuando
    resp = usuario.api.post(
        "/orders", json={**_orden_valida(), "quantityWei": "1.5"}
    )

    # Entonces
    err = assert_error(resp, "VALIDATION_ERROR")
    detalles = err.get("details") or {}
    assert "issues" in detalles, err
    issues = detalles["issues"]
    assert isinstance(issues, list) and issues, err
    # el campo ofensor está identificado en alguna de las causas
    assert "quantityWei" in json.dumps(issues), issues


@pytest.mark.at("AT-09-05-06")
def test_montos_en_details_de_error_como_string(usuario):
    """HU-09-05 Escenario 6: Montos en details como string.

    - Dado un retiro por debajo del mínimo (MIN_WITHDRAWAL_USDC = 1 USDC,
      HU-08-01 RN-7; el mínimo se evalúa antes que los fondos, RN-11)
    - Cuando se rechaza con WITHDRAWAL_BELOW_MIN (422)
    - Entonces details = { asset, amount, minWithdrawal } con amount y
      minWithdrawal como strings que matchean ^(0|[1-9][0-9]*)$, nunca números
    """
    # Cuando: 0.999999 USDC (< mínimo de 1 USDC), dirección válida
    resp = usuario.api.post(
        "/withdrawals",
        json={"asset": "USDC", "amountMinUnit": "999999", "address": DESTINO_RETIRO},
    )

    # Entonces
    err = assert_error(resp, "WITHDRAWAL_BELOW_MIN")
    detalles = err.get("details") or {}
    assert detalles.get("asset") == "USDC", err
    assert_montos_en_details(detalles, "amount", "minWithdrawal")
    assert detalles["amount"] == "999999", err
    assert detalles["minWithdrawal"] == "1000000", err  # 1 USDC (HU-08-01 RN-7)


@pytest.mark.at("AT-09-05-11")
def test_bateria_de_codes_del_catalogo_con_status_exactos(api, usuario):
    """HU-09-05 Escenario 11 (estabilidad): code del catálogo, message libre.

    - Dado un conjunto de operaciones inválidas, una por cada code relevante
      alcanzable sin estado on-chain previo
    - Cuando la implementación rechaza cada una
    - Entonces el code devuelto y su status HTTP coinciden exactamente con los
      del catálogo, y ningún code está fuera del catálogo (espacio cerrado)

    Los codes que requieren estado construido se verifican en sus propios ATs
    (p. ej. DUPLICATE_CLIENT_ORDER_ID en AT-09-01-17, ORDER_NOT_CANCELLABLE en
    AT-09-01-08, MARKET_NO_LIQUIDITY en AT-09-01-21, RATE_LIMITED en AT-09-02-11).
    El literal de message no se evalúa (RN-3).
    """
    # Dado: una cuenta ya registrada (para EMAIL_ALREADY_EXISTS / INVALID_CREDENTIALS)
    email = email_unico("cat")
    registrar(api, email=email)

    disparadores = [
        # (code esperado, respuesta)
        ("UNAUTHENTICATED", api.get("/me")),
        ("INVALID_CREDENTIALS",
         api.post("/auth/login", json={"email": email, "password": "incorrecta-999"})),
        ("EMAIL_ALREADY_EXISTS",
         api.post("/auth/register", json={"email": email, "password": PASSWORD_DEFECTO})),
        ("VALIDATION_ERROR",
         usuario.api.post("/orders", json={"clientOrderId": id_cliente("v")})),
        ("INVALID_SIDE",
         usuario.api.post("/orders", json={**_orden_valida(), "side": "HOLD"})),
        ("INVALID_ORDER_TYPE",
         usuario.api.post("/orders", json={**_orden_valida(), "type": "STOP"})),
        ("PRICE_REQUIRED",
         usuario.api.post("/orders", json={
             k: v for k, v in _orden_valida().items() if k != "priceMin"
         })),
        ("PRICE_NOT_ALLOWED",
         usuario.api.post("/orders", json={**_orden_valida(), "type": "MARKET"})),
        ("INVALID_PRICE_TICK",
         usuario.api.post("/orders", json={**_orden_valida(), "priceMin": "2000000001"})),
        ("INVALID_LOT_SIZE",
         usuario.api.post("/orders", json={**_orden_valida(),
                                           "quantityWei": "150000000000001"})),
        ("BELOW_MIN_NOTIONAL",
         usuario.api.post("/orders", json={**_orden_valida(),
                                           "quantityWei": "100000000000000"})),
        ("INSUFFICIENT_FUNDS", usuario.api.post("/orders", json=_orden_valida())),
        ("ORDER_NOT_FOUND", usuario.api.get("/orders/orden-inexistente-000")),
        ("NOT_FOUND", usuario.api.get("/withdrawals/retiro-inexistente-000")),
        ("METHOD_NOT_ALLOWED", usuario.api.request("PUT", "/balances")),
        ("INVALID_ADDRESS",
         usuario.api.post("/withdrawals", json={
             "asset": "USDC", "amountMinUnit": "5000000",
             "address": romper_checksum(DESTINO_RETIRO),
         })),
        ("WITHDRAWAL_AMOUNT_INVALID",
         usuario.api.post("/withdrawals", json={
             "asset": "USDC", "amountMinUnit": "0", "address": DESTINO_RETIRO,
         })),
        ("WITHDRAWAL_BELOW_MIN",
         usuario.api.post("/withdrawals", json={
             "asset": "USDC", "amountMinUnit": "999999", "address": DESTINO_RETIRO,
         })),
    ]

    # Entonces: cada rechazo usa exactamente el code y el status HTTP del catálogo
    # (assert_error también falla si el SUT devuelve un code fuera del catálogo)
    for code, resp in disparadores:
        assert_error(resp, code)


@pytest.mark.at("AT-09-05-12")
def test_una_respuesta_de_error_no_muta_estado(usuario, rpc):
    """HU-09-05 Escenario 12 (invariante): El error no muta estado.

    - Dado un alta de orden que será rechazada por INSUFFICIENT_FUNDS
    - Cuando se procesa
    - Entonces los balances quedan idénticos a antes de la request (INV-2: se
      rechaza antes de mutar; INV-1: la suma global no cambia) y no se crea
      orden alguna
    """
    # Dado: fondos reales pero insuficientes (20 USDC contra 40 requeridos)
    fondear_usdc(usuario, rpc, 20_000_000)
    balances_previos = balances_por_activo(usuario)
    cid = id_cliente("nomuta")

    # Cuando
    resp = usuario.api.post("/orders", json=_orden_valida(cid))

    # Entonces: rechazo por fondos...
    assert_error(resp, "INSUFFICIENT_FUNDS")

    # ... con balances idénticos y sin orden creada
    assert balances_por_activo(usuario) == balances_previos
    resp = usuario.api.get("/orders", params={"clientOrderId": cid})
    assert resp.status_code == 200, resp.text
    assert resp.json()["items"] == [], resp.text
