"""Asserts sobre el modelo de errores de la API.

La spec fija un envelope uniforme para toda respuesta de error, HTTP o WebSocket
(spec/00-fundaciones/modelo-de-errores.md §1, HU-09-05 RN-1):

    { "error": { "code": <string>, "message": <string>, "details": <object?> } }

- `code` es lo que se evalúa (estable, del catálogo).
- `message` NO se evalúa en su literal (sólo que exista y sea string).
- `details` es opcional; cuando trae montos, van como string de entero.
"""

from .montos import es_monto_valido

# Catálogo de códigos estables (spec/00-fundaciones/modelo-de-errores.md §3).
# Sirve para detectar typos en los tests y códigos fuera de catálogo en el SUT.
CATALOGO_CODES = {
    # 3.1 autenticación y autorización
    "UNAUTHENTICATED": 401,
    "UNAUTHORIZED": 403,
    "RATE_LIMITED": 429,
    # 3.2 validación general
    "VALIDATION_ERROR": 422,
    "NOT_FOUND": 404,
    "METHOD_NOT_ALLOWED": 405,
    # 3.3 trading: validación de órdenes
    "INVALID_PRICE_TICK": 422,
    "INVALID_LOT_SIZE": 422,
    "BELOW_MIN_NOTIONAL": 422,
    "INVALID_SIDE": 422,
    "INVALID_ORDER_TYPE": 422,
    "PRICE_REQUIRED": 422,
    "PRICE_NOT_ALLOWED": 422,
    # 3.4 trading: estado y ejecución
    "INSUFFICIENT_FUNDS": 422,
    "ORDER_NOT_FOUND": 404,
    "ORDER_NOT_CANCELLABLE": 409,
    "SELF_TRADE_BLOCKED": 422,
    "MARKET_NO_LIQUIDITY": 422,
    "MARKET_BUDGET_INSUFFICIENT": 422,
    "DUPLICATE_CLIENT_ORDER_ID": 409,
    # 3.5 on-chain
    "INVALID_ADDRESS": 422,
    "WITHDRAWAL_BELOW_MIN": 422,
    "WITHDRAWAL_AMOUNT_INVALID": 422,
    "DEPOSIT_ALREADY_CREDITED": 409,
    "DEPOSIT_NOT_CONFIRMED": 409,
    "CHAIN_ID_MISMATCH": 422,
    "NONCE_CONFLICT": 409,
    "BROADCAST_FAILED": 502,
    # 3.6 cuentas
    "EMAIL_ALREADY_EXISTS": 409,
    "INVALID_CREDENTIALS": 401,
    "ACCOUNT_NOT_FOUND": 404,
    # 3.7 genéricos
    "CONFLICT": 409,
    "INTERNAL_ERROR": 500,
}


def validar_envelope(cuerpo: dict) -> dict:
    """Valida la estructura del envelope de error y devuelve el objeto `error`.

    Aplica tanto a cuerpos HTTP como a mensajes de error por WebSocket.
    """
    assert isinstance(cuerpo, dict), f"el cuerpo de error no es un objeto JSON: {cuerpo!r}"
    assert "error" in cuerpo, f"falta la clave 'error' en el envelope: {cuerpo!r}"
    err = cuerpo["error"]
    assert isinstance(err, dict), f"'error' no es un objeto: {err!r}"
    assert isinstance(err.get("code"), str) and err["code"], (
        f"error.code ausente o no string: {err.get('code')!r}"
    )
    assert isinstance(err.get("message"), str) and err["message"], (
        f"error.message ausente o no string: {err.get('message')!r}"
    )
    if "details" in err and err["details"] is not None:
        assert isinstance(err["details"], dict), (
            f"error.details presente pero no es objeto: {err['details']!r}"
        )
    return err


def assert_error(respuesta, code: str, status: int | None = None) -> dict:
    """Asserta que una respuesta HTTP es el error `code` con el envelope uniforme.

    - `respuesta`: httpx.Response (o cualquier objeto con .status_code y .json()).
    - `code`: código estable del catálogo (se valida contra CATALOGO_CODES para
      atrapar typos en el propio test).
    - `status`: status HTTP esperado; si se omite se usa el del catálogo.

    Devuelve el objeto `error` (dict) para asserts adicionales sobre `details`.

    Ejemplo:
        err = assert_error(resp, "INSUFFICIENT_FUNDS")
        assert err["details"]["asset"] == "USDC"
    """
    assert code in CATALOGO_CODES, f"código fuera de catálogo en el test: {code!r}"
    esperado = status if status is not None else CATALOGO_CODES[code]

    cuerpo = respuesta.json()
    err = validar_envelope(cuerpo)
    assert respuesta.status_code == esperado, (
        f"status esperado {esperado}, llegó {respuesta.status_code} "
        f"(code={err['code']!r}, message={err['message']!r})"
    )
    assert err["code"] == code, (
        f"code esperado {code!r}, llegó {err['code']!r} (message={err['message']!r})"
    )
    return err


def assert_error_ws(mensaje: dict, code: str) -> dict:
    """Asserta que un mensaje WebSocket es el error `code` con el envelope uniforme.

    Por WS no hay status HTTP: el `code` es lo determinante (HU-09-05 RN-7).
    """
    assert code in CATALOGO_CODES, f"código fuera de catálogo en el test: {code!r}"
    err = validar_envelope(mensaje)
    assert err["code"] == code, f"code esperado {code!r}, llegó {err['code']!r}"
    return err


def assert_montos_en_details(details: dict, *campos: str) -> None:
    """Asserta que los campos monetarios de `details` van como string de entero.

    Ejemplo (HU-09-05 RN-4):
        assert_montos_en_details(err["details"], "required", "available")
    """
    for campo in campos:
        assert campo in details, f"details.{campo} ausente: {details!r}"
        assert es_monto_valido(details[campo]), (
            f"details.{campo} debe ser string entero ^(0|[1-9][0-9]*)$, "
            f"llegó {details[campo]!r}"
        )
