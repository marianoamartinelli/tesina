"""Épica 01 / HU-01-04 — Consulta de perfil: tests de aceptación black-box.

Spec: spec/01-cuentas-y-autenticacion/HU-01-04-consulta-de-perfil.md
Contrato de transporte: GET /api/v1/me (HU-09-01, mapa de endpoints).

Notas de interpretación:
- TODO-REVISAR: HU-01-04 RN-4 fija que el perfil incluye "exactamente"
  `accountId`, `email`, `status`, `createdAt`; HU-09-01 Escenario 3 lista
  `{accountId, email, createdAt}` sin `status`. 00-fundaciones no fija este
  contrato: prevalece la épica 01 (dueña del recurso) y se asserta el set exacto.
- HU-01-04 RN-3 es condicional ("si la API expone el perfil por identificador,
  p. ej. /accounts/{accountId}"): la épica 09 no lista esa ruta, así que
  AT-01-04-05/06 sondean su existencia y se saltan si no está expuesta.
"""

import secrets

import pytest

from helpers.cuentas import PASSWORD_DEFECTO, login
from helpers.errores import assert_error

from comunes_ep01 import (
    CAMPOS_IDENTIDAD,
    assert_sin_claves_de_password,
    logout,
    parsear_iso8601_utc,
)


def _perfil_por_id_expuesto(usuario) -> bool:
    """Sonda del contrato condicional de RN-3: GET /accounts/{accountId propio}.

    - 200 ⇒ la ruta existe y el propio perfil se devuelve (RN-2/RN-4);
    - 404 ⇒ la implementación no expone perfil por id (ruta inexistente,
      HU-09-01 RN-14) y los ATs 05/06 no aplican.
    """
    resp = usuario.api.get(f"/accounts/{usuario.account_id}")
    if resp.status_code == 404:
        return False
    assert resp.status_code == 200, (
        f"GET /accounts/{{accountId propio}} debería ser 200 o 404, "
        f"llegó {resp.status_code}: {resp.text[:300]}"
    )
    return True


@pytest.mark.at("AT-01-04-01")
def test_consulta_de_perfil_propio_exitosa(usuario):
    """HU-01-04 Escenario 1: Consulta de perfil propio exitosa.

    - Dado un usuario autenticado con token válido
    - Cuando consulta su perfil presentando el token
    - Entonces 200 con accountId, email, status = "ACTIVE" y createdAt ISO 8601 UTC
    - Y el cuerpo no incluye contraseña, hash, sal ni ningún token
    """
    # Cuando
    resp = usuario.api.get("/me")

    # Entonces (RN-4)
    assert resp.status_code == 200, resp.text
    perfil = resp.json()
    assert isinstance(perfil["accountId"], str) and perfil["accountId"]
    assert perfil["email"] == usuario.email  # email normalizado (RN-4)
    assert perfil["status"] == "ACTIVE"  # único estado del alcance (RN-4)
    parsear_iso8601_utc(perfil["createdAt"], "createdAt")  # RNE-8

    # Y: sin secretos (RN-5, RNE-2)
    assert_sin_claves_de_password(perfil)
    assert "token" not in perfil
    assert usuario.password not in resp.text
    assert usuario.token not in resp.text


@pytest.mark.at("AT-01-04-02")
def test_los_datos_del_perfil_coinciden_con_el_registro(api):
    """HU-01-04 Escenario 2 (borde): Los datos coinciden con el registro.

    - Dado una cuenta registrada vía HU-01-01 (con email a normalizar)
    - Cuando el titular consulta su perfil
    - Entonces accountId, email, status y createdAt coinciden exactamente con
      los valores asignados en el registro
    - Y el email devuelto está normalizado (minúsculas, sin espacios de borde)
    """
    # Dado: registro con capitalización y espacios de borde (HU-01-01 RN-1)
    sufijo = secrets.token_hex(6)
    email_normalizado = f"at-perfil-{sufijo}@example.com"
    resp_registro = api.post(
        "/auth/register",
        json={"email": f"  At-Perfil-{sufijo.upper()}@EXAMPLE.com ", "password": PASSWORD_DEFECTO},
    )
    assert resp_registro.status_code == 201, resp_registro.text
    registro = resp_registro.json()

    # Cuando
    token = login(api, email_normalizado)
    with api.con_token(token) as autenticado:
        resp = autenticado.get("/me")

    # Entonces: coincidencia exacta con el registro (RN-4)
    assert resp.status_code == 200, resp.text
    perfil = resp.json()
    assert perfil["accountId"] == registro["accountId"]
    assert perfil["status"] == registro["status"] == "ACTIVE"
    assert perfil["createdAt"] == registro["createdAt"]

    # Y: email normalizado (RN-4; HU-01-01 RN-1)
    assert perfil["email"] == registro["email"] == email_normalizado


@pytest.mark.at("AT-01-04-03")
def test_consulta_de_perfil_sin_autenticacion(api):
    """HU-01-04 Escenario 3 (error): Consulta sin autenticación.

    - Dado un cliente sin token (o con token malformado)
    - Cuando intenta consultar un perfil
    - Entonces UNAUTHENTICATED (401) y no se devuelve ningún dato de cuenta
    """
    # Cuando: sin token (RN-1)
    resp = api.get("/me")

    # Entonces
    assert_error(resp, "UNAUTHENTICATED")
    assert set(resp.json()) == {"error"}  # sin datos de cuenta

    # Y: con token malformado también (RN-1)
    with api.con_token("token-malformado") as impostor:
        resp = impostor.get("/me")
    assert_error(resp, "UNAUTHENTICATED")
    assert set(resp.json()) == {"error"}


@pytest.mark.at("AT-01-04-04")
def test_token_invalidado_no_consulta_el_perfil(usuario):
    """HU-01-04 Escenario 4 (error): Token expirado o invalidado.

    - Dado un token expirado por TTL **o** invalidado por logout (HU-01-03)
    - Cuando se usa para consultar el perfil
    - Entonces UNAUTHENTICATED (401)

    Se ejerce la rama "invalidado por logout" del propio AT: la rama "expirado
    por TTL" no es provocable black-box (TTL fijo de 3600 s en el entorno; ver
    AT-01-03-04 en no_automatizables_ep01.yaml) y la respuesta es la misma
    para ambas causas (HU-01-03 RN-2: no se distinguen).
    """
    # Dado: token invalidado por logout (HU-01-03 RN-1)
    assert logout(usuario.api).status_code == 204

    # Cuando
    resp = usuario.api.get("/me")

    # Entonces (RN-1)
    assert_error(resp, "UNAUTHENTICATED")


@pytest.mark.at("AT-01-04-05")
def test_consultar_el_perfil_de_otra_cuenta_es_unauthorized(usuario, usuario_b):
    """HU-01-04 Escenario 5 (error): Intento de consultar el perfil de otra cuenta.

    - Dado un usuario autenticado como cuenta A y el accountId de la cuenta B
    - Cuando solicita /accounts/{accountId_B}
    - Entonces UNAUTHORIZED (403) con details.resource
    - Y no se devuelve ningún dato de la cuenta B
    - (Condicional: si la API no expone perfil por id, RN-3 no aplica y se salta)
    """
    # Dado: la ruta condicional existe (RN-3)
    if not _perfil_por_id_expuesto(usuario):
        pytest.skip(
            "la API no expone el perfil por identificador (/accounts/{accountId}): "
            "HU-01-04 RN-3 es condicional y no aplica"
        )

    # Cuando
    resp = usuario.api.get(f"/accounts/{usuario_b.account_id}")

    # Entonces: 403 con details.resource (RN-3: no NOT_FOUND, no filtra existencia)
    err = assert_error(resp, "UNAUTHORIZED")
    assert "resource" in (err.get("details") or {}), (
        f"details.resource ausente (RN-3): {err!r}"
    )

    # Y: ningún dato de B en la respuesta (RN-2)
    assert usuario_b.email not in resp.text


@pytest.mark.at("AT-01-04-06")
def test_sin_token_y_recurso_ajeno_prevalece_unauthenticated(api, usuario, usuario_b):
    """HU-01-04 Escenario 6 (precedencia): Sin token y recurso ajeno.

    - Dado un cliente sin token válido que solicita el perfil de un accountId ajeno
    - Cuando realiza la solicitud
    - Entonces UN solo error: UNAUTHENTICATED (401), no UNAUTHORIZED
      (RN-8: autenticación antes que autorización)
    - (Condicional a que la API exponga el perfil por id, igual que AT-01-04-05)
    """
    # Dado: la ruta condicional existe (sondada con la cuenta A)
    if not _perfil_por_id_expuesto(usuario):
        pytest.skip(
            "la API no expone el perfil por identificador (/accounts/{accountId}): "
            "HU-01-04 RN-3 es condicional y no aplica"
        )

    # Cuando: sin token (el fixture `api` no lleva Authorization)
    resp = api.get(f"/accounts/{usuario_b.account_id}")

    # Entonces (RN-8; RNE-7: un solo error por respuesta)
    assert_error(resp, "UNAUTHENTICATED")
    assert set(resp.json()) == {"error"}


@pytest.mark.at("AT-01-04-07")
def test_la_consulta_de_perfil_no_altera_la_sesion_ni_el_estado(usuario):
    """HU-01-04 Escenario 7 (borde): La consulta no altera la sesión ni el estado.

    - Dado un usuario autenticado
    - Cuando consulta su perfil varias veces
    - Entonces cada respuesta es 200 con los mismos datos y status ACTIVE

    Nota: la cláusula "el expiresAt del token no cambia (la lectura no renueva
    el TTL)" no tiene superficie observable directa: ningún endpoint expone el
    expiresAt del token vigente y el TTL del entorno es 3600 s (no se puede
    esperar la expiración para compararla). Se verifica el efecto observable:
    lecturas repetidas idénticas y sin cambio de estado (RN-7).
    """
    # Cuando: varias consultas sucesivas
    cuerpos = []
    for _ in range(3):
        resp = usuario.api.get("/me")
        # Entonces: cada respuesta es 200 (la sesión sigue viva, RN-7)
        assert resp.status_code == 200, resp.text
        cuerpos.append(resp.json())

    # Y: mismos datos en todas (RN-7: lectura pura, sin efectos)
    assert cuerpos[0] == cuerpos[1] == cuerpos[2]
    assert cuerpos[0]["status"] == "ACTIVE"


@pytest.mark.at("AT-01-04-08")
def test_el_perfil_no_expone_balances(usuario):
    """HU-01-04 Escenario 8 (contrato): El perfil no expone balances.

    - Dado un usuario recién registrado (sin depósitos) que consulta su perfil
    - Cuando recibe la respuesta exitosa (200)
    - Entonces el cuerpo contiene exactamente los campos de identidad
      (accountId, email, status, createdAt), sin balances ni montos (RN-4, RN-6)
    - Y los balances se consultan exclusivamente por los endpoints de la épica 02
    """
    # Cuando
    resp = usuario.api.get("/me")

    # Entonces: exactamente los campos de identidad (RN-4/RN-6; ver TODO-REVISAR
    # del docstring del módulo sobre `status` vs HU-09-01 Escenario 3)
    assert resp.status_code == 200, resp.text
    assert set(resp.json()) == CAMPOS_IDENTIDAD, (
        f"el perfil debe exponer exactamente {sorted(CAMPOS_IDENTIDAD)}, "
        f"llegó {sorted(resp.json())}"
    )

    # Y: los balances están disponibles por la vía de la épica 02 (RN-6)
    resp_balances = usuario.api.get("/balances")
    assert resp_balances.status_code == 200, resp_balances.text
