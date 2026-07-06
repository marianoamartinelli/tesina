"""Épica 01 / HU-01-03 — Cierre y expiración de sesión: tests black-box.

Spec: spec/01-cuentas-y-autenticacion/HU-01-03-cierre-y-expiracion-de-sesion.md

Ruta de logout: POST /api/v1/auth/logout, canónica en el mapa de endpoints de
HU-09-01 (fila Logout, éxito 204; ADR-006 D5); el comportamiento lo fija
HU-01-03. Estos tests la toman de comunes_ep01.RUTA_LOGOUT.

No automatizables (declarados en no-automatizables.yaml):
- AT-01-03-04 y AT-01-03-09 requieren un token expirado por TTL; el entorno de
  evaluación fija el TTL en 3600 s (entorno/README.md) y no hay vía black-box
  para acortarlo ni adelantar el reloj del SUT.

Los ATs de persistencia tras reinicio (AT-01-03-08, AT-01-03-10) usan el
reinicio orquestado por el evaluador (SUITE_CMD_REINICIO_SUT); sin esa env var
se saltan.
"""

from datetime import datetime, timezone

import pytest

from helpers.cuentas import login
from helpers.errores import assert_error

from comunes_ep01 import (
    en_paralelo,
    es_jwt,
    logout,
    parsear_iso8601_utc,
    reiniciar_sut,
)


@pytest.mark.at("AT-01-03-01")
def test_logout_explicito_exitoso_devuelve_204_sin_cuerpo(usuario):
    """HU-01-03 Escenario 1: Logout explícito exitoso.

    - Dado un usuario autenticado con token válido y no expirado
    - Cuando invoca el endpoint de logout con ese token
    - Entonces 204 sin cuerpo (status único y determinista)
    - Y a partir de ese momento el token queda invalidado
    """
    # Cuando
    resp = logout(usuario.api)

    # Entonces: 204 sin cuerpo
    assert resp.status_code == 204, resp.text
    assert resp.content == b"", "el 204 de logout no lleva cuerpo"

    # Y: el token quedó invalidado de inmediato (RN-1)
    assert_error(usuario.api.get("/me"), "UNAUTHENTICATED")


@pytest.mark.at("AT-01-03-02")
def test_token_invalidado_por_logout_no_autentica(usuario):
    """HU-01-03 Escenario 2: Token invalidado por logout no autentica.

    - Dado un token invalidado por un logout exitoso
    - Cuando se usa en un endpoint protegido (perfil, HU-01-04)
    - Entonces UNAUTHENTICATED (401)
    - Y la operación protegida no se ejecuta
    """
    # Dado
    assert logout(usuario.api).status_code == 204

    # Cuando
    resp = usuario.api.get("/me")

    # Entonces (RN-1, RN-2)
    assert_error(resp, "UNAUTHENTICATED")

    # Y: no se devuelve ningún dato de la cuenta (sólo el envelope de error)
    assert set(resp.json()) == {"error"}
    assert usuario.email not in resp.text


@pytest.mark.at("AT-01-03-03")
def test_token_valido_antes_de_expirar_autentica(api, usuario):
    """HU-01-03 Escenario 3 (borde): Token válido antes de expirar.

    - Dado un token con expiresAt en el futuro y no invalidado por logout
    - Cuando se usa en un endpoint protegido en t < expiresAt
    - Entonces la llamada se procesa autenticada (no UNAUTHENTICATED)
    """
    # Dado: un login que devuelve token y expiresAt (HU-01-02 RN-3)
    resp_login = api.post(
        "/auth/login", json={"email": usuario.email, "password": usuario.password}
    )
    assert resp_login.status_code == 200, resp_login.text
    cuerpo = resp_login.json()
    expira = parsear_iso8601_utc(cuerpo["expiresAt"], "expiresAt")
    assert expira > datetime.now(timezone.utc)  # estamos en t < expiresAt (RN-3)

    # Cuando
    with api.con_token(cuerpo["token"]) as sesion:
        resp = sesion.get("/me")

    # Entonces
    assert resp.status_code == 200, resp.text


@pytest.mark.at("AT-01-03-05")
def test_logout_afecta_solo_al_token_presentado(api, usuario):
    """HU-01-03 Escenario 5 (borde): Logout afecta solo al token presentado.

    - Dado una cuenta con dos sesiones activas (tokenA y tokenB)
    - Cuando hace logout presentando tokenA
    - Entonces tokenA queda invalidado (UNAUTHENTICATED en protegidos)
    - Y tokenB sigue autenticando normalmente
    """
    # Dado: dos sesiones de la misma cuenta (HU-01-02 RN-6)
    token_a = usuario.token
    token_b = login(api, usuario.email, usuario.password)
    assert token_a != token_b

    # Cuando: logout con tokenA
    assert logout(usuario.api).status_code == 204

    # Entonces: tokenA invalidado (RN-1, RN-5)
    assert_error(usuario.api.get("/me"), "UNAUTHENTICATED")

    # Y: tokenB sigue válido (RN-5: aislamiento entre sesiones)
    with api.con_token(token_b) as sesion_b:
        assert sesion_b.get("/me").status_code == 200


@pytest.mark.at("AT-01-03-06")
def test_logout_sin_token_o_con_token_invalido_es_unauthenticated(api, usuario):
    """HU-01-03 Escenario 6 (error): Logout sin token o con token inválido.

    - Dado un cliente sin token, o con un token malformado/inexistente
    - Cuando invoca el endpoint de logout
    - Entonces UNAUTHENTICATED (401)
    - Y no se produce ningún efecto sobre sesiones existentes
    """
    # Cuando: sin token (RN-4: el logout es una operación protegida)
    assert_error(logout(api), "UNAUTHENTICATED")

    # Cuando: token malformado/inexistente
    with api.con_token("token-invalido-que-no-existe") as impostor:
        assert_error(logout(impostor), "UNAUTHENTICATED")

    # Y: la sesión existente no fue afectada (RN-4: "ningún efecto adicional")
    assert usuario.api.get("/me").status_code == 200


@pytest.mark.at("AT-01-03-07")
def test_doble_logout_con_el_mismo_token_es_unauthenticated(api, usuario):
    """HU-01-03 Escenario 7 (idempotencia): Doble logout con el mismo token.

    - Dado un token ya invalidado por un logout exitoso
    - Cuando intenta hacer logout otra vez con ese mismo token
    - Entonces UNAUTHENTICATED (401): el primero ya surtió efecto
    - Y el estado de las sesiones no cambia respecto del primer logout
    """
    # Dado: otra sesión de la misma cuenta, para observar que el estado no cambia
    token_b = login(api, usuario.email, usuario.password)
    assert logout(usuario.api).status_code == 204  # primer logout

    # Cuando: segundo logout con el mismo token
    resp = logout(usuario.api)

    # Entonces (RN-6: sin error de servidor ni doble efecto)
    assert_error(resp, "UNAUTHENTICATED")

    # Y: el estado no cambió — el token sigue invalidado y la otra sesión viva
    assert_error(usuario.api.get("/me"), "UNAUTHENTICATED")
    with api.con_token(token_b) as sesion_b:
        assert sesion_b.get("/me").status_code == 200


@pytest.mark.at("AT-01-03-08")
def test_invalidacion_por_logout_sobrevive_un_reinicio(api, usuario):
    """HU-01-03 Escenario 8 (borde): Persistencia de la invalidación tras reinicio.

    - Dado un token invalidado por logout antes de un reinicio
    - Cuando el sistema se reinicia y se vuelve a usar ese token
    - Entonces UNAUTHENTICATED (401): la invalidación sobrevivió (RN-8, INV-8)

    Requiere SUITE_CMD_REINICIO_SUT (reinicio orquestado por el evaluador).
    """
    # Dado
    assert logout(usuario.api).status_code == 204

    # Cuando
    reiniciar_sut(api)

    # Entonces (RN-8, RN-10, INV-8)
    assert_error(usuario.api.get("/me"), "UNAUTHENTICATED")


@pytest.mark.at("AT-01-03-10")
def test_jwt_revocado_por_logout_sigue_revocado_tras_reinicio(api, usuario):
    """HU-01-03 Escenario 10 (persistencia JWT): denylist persistente tras reinicio.

    - Dado una implementación con JWT y un JWT con firma válida y no vencido
    - Cuando se hace logout, se reinicia el servicio y se reutiliza el JWT
    - Entonces UNAUTHENTICATED (401): la denylist sobrevivió al reinicio (RN-10)
    - (Si el esquema de token es opaco, el caso lo cubre AT-01-03-08 y este
      test se salta, tal como lo prevé el propio escenario)
    """
    # Dado: el esquema debe ser JWT (detección observable por la forma del token)
    if not es_jwt(usuario.token):
        pytest.skip(
            "el esquema de token no es JWT: el caso queda cubierto por "
            "AT-01-03-08 (HU-01-03 Escenario 10)"
        )
    # el token está recién emitido ⇒ su expiresAt no venció (TTL 3600 s del entorno)

    # Cuando: logout (entra a la denylist, RN-10) + reinicio + reuso
    assert logout(usuario.api).status_code == 204
    reiniciar_sut(api)
    resp = usuario.api.get("/me")

    # Entonces: la firma sigue siendo válida pero la denylist persistió (RN-10)
    assert_error(resp, "UNAUTHENTICATED")


@pytest.mark.at("AT-01-03-11")
def test_doble_logout_concurrente_invalida_exactamente_una_vez(api, usuario):
    """HU-01-03 Escenario 11 (concurrencia): doble logout concurrente.

    - Dado un token válido T y no expirado
    - Cuando dos solicitudes de logout con T se envían concurrentes
    - Entonces exactamente una responde 204 y la otra UNAUTHENTICATED (401)
      (RN-6: invalidación atómica, ni dos 204 ni dos fallos)
    - Y cualquier uso posterior de T devuelve UNAUTHENTICATED (401)
    """
    # Cuando: dos clientes independientes con el mismo token, en paralelo
    with api.con_token(usuario.token) as c1, api.con_token(usuario.token) as c2:
        r1, r2 = en_paralelo(lambda: logout(c1), lambda: logout(c2))

    # Entonces: exactamente una 204 y una 401 (RN-6: atomicidad tipo CAS)
    codigos = sorted([r1.status_code, r2.status_code])
    assert codigos == [204, 401], (
        f"se esperaba exactamente un 204 y un 401, llegó {codigos} (RN-6)"
    )
    exitosa = r1 if r1.status_code == 204 else r2
    rechazada = r1 if r1.status_code != 204 else r2
    assert exitosa.content == b""  # el 204 no lleva cuerpo (Escenario 1)
    assert_error(rechazada, "UNAUTHENTICATED")

    # Y: T quedó revocado para cualquier uso posterior
    assert_error(usuario.api.get("/me"), "UNAUTHENTICATED")
