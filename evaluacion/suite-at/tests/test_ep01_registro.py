"""Épica 01 / HU-01-01 — Registro de usuario: tests de aceptación black-box.

Spec: spec/01-cuentas-y-autenticacion/HU-01-01-registro-de-usuario.md
Contrato de transporte: POST /api/v1/auth/register (HU-09-01, mapa de endpoints).

Notas de interpretación (ver también tests/comunes_ep01.py):
- La respuesta de registro expone `accountId`, `email`, `status`, `createdAt`
  (HU-01-01 RN-6); desde spec-v1.1 el ejemplo de HU-09-01 (AT-09-01-01) incluye
  `status` y ambas épicas coinciden (ADR-006 D12). Se asserta el set con `status`.
- El rate limiting de registro es OPCIONAL por config (HU-01-01 RN-10) y, si
  existe, usa RATE_LIMITED; la política determinista de HU-09-02 RN-12 aplica
  solo a endpoints autenticados, no a /auth/* (ADR-006 D4). AT-01-01-20 sondea
  N=60/T=60 s (el valor que el entorno fija si la implementación lo expone) y
  se salta si no observa RATE_LIMITED (la propia AT dice "si el rate limiting
  no está activo, este AT no aplica").
"""

import json
import re
import secrets
import time

import pytest

from helpers.cuentas import PASSWORD_DEFECTO, email_unico, login, registrar
from helpers.errores import assert_error

from comunes_ep01 import (
    N_RATE_LIMIT,
    assert_sin_claves_de_password,
    en_paralelo,
    esperar_rate_limit_liberado,
    parsear_iso8601_utc,
    reiniciar_sut,
)

DOMINIO = "@example.com"  # dominio reservado para pruebas (RFC 2606)


def _registrar(api, email, password=PASSWORD_DEFECTO):
    """POST crudo al registro (sin asserts): para los escenarios de error."""
    return api.post("/auth/register", json={"email": email, "password": password})


def _assert_no_se_creo_cuenta(api, email, password) -> None:
    """Observación black-box de "no se crea ninguna cuenta": si la cuenta se
    hubiera creado con esas credenciales, el login respondería 200 (HU-01-02
    RN-1); INVALID_CREDENTIALS prueba que no quedó una cuenta utilizable."""
    resp = api.post("/auth/login", json={"email": email, "password": str(password)})
    assert_error(resp, "INVALID_CREDENTIALS")


def _email_unico_de_largo(prefijo: str, largo: int) -> str:
    """Email único con exactamente `largo` caracteres (bordes de RN-2)."""
    local = f"{prefijo}-{secrets.token_hex(6)}"
    relleno = largo - len(local) - len(DOMINIO)
    assert relleno >= 0, "el prefijo no deja lugar para el relleno"
    email = f"{local}{'a' * relleno}{DOMINIO}"
    assert len(email) == largo
    return email


# -------------------------------------------------------------------------------------
# Camino feliz y normalización
# -------------------------------------------------------------------------------------


@pytest.mark.at("AT-01-01-01")
def test_registro_exitoso_con_credenciales_validas(api):
    """HU-01-01 Escenario 1: Registro exitoso con credenciales válidas.

    - Dado un visitante no autenticado y un email que no existe en el sistema
    - Y una contraseña de 12 caracteres `Sup3rSecreta`
    - Cuando envía la solicitud de registro con `email` y `password` válidos
    - Entonces la respuesta es 201 con `accountId` no vacío, `email`,
      `status = "ACTIVE"` y `createdAt` ISO 8601 UTC
    - Y el cuerpo no contiene contraseña, hash, sal ni token de sesión
    - Y el estado interno tiene balances disponible = "0" y bloqueado = "0"
      para ETH y USDC (consultables vía épica 02, no en el cuerpo del registro)
    """
    # Dado
    email = email_unico("reg")
    password = "Sup3rSecreta"  # 12 caracteres, dentro del rango 8..128 (RN-3)

    # Cuando
    resp = api.post("/auth/register", json={"email": email, "password": password})

    # Entonces
    assert resp.status_code == 201, resp.text
    cuerpo = resp.json()
    assert isinstance(cuerpo["accountId"], str) and cuerpo["accountId"]  # RN-6
    assert cuerpo["email"] == email  # RN-1 (email ya normalizado)
    assert cuerpo["status"] == "ACTIVE"  # RN-6 (la 09 coincide: AT-09-01-01 incluye status)
    parsear_iso8601_utc(cuerpo["createdAt"], "createdAt")  # RN-6 / RNE-8

    # Y: sin contraseña/hash/sal ni token (RN-5, RN-7, RNE-2)
    assert_sin_claves_de_password(cuerpo)
    assert "token" not in cuerpo, "el registro no emite token (RN-7: no auto-login)"
    assert password not in resp.text, "la contraseña no viaja en la respuesta (RN-5)"

    # Y: balances iniciales en cero como estado interno, vía épica 02 (RN-6, INV-1)
    token = login(api, email, password)
    with api.con_token(token) as autenticado:
        balances = autenticado.get("/balances").json()
    por_activo = {b["asset"]: b for b in balances}
    for activo in ("ETH", "USDC"):
        assert por_activo[activo]["available"] == "0"  # RN-6: disponible inicial "0"
        assert por_activo[activo]["locked"] == "0"  # RN-6: bloqueado inicial "0"


@pytest.mark.at("AT-01-01-02")
def test_normalizacion_del_email_en_el_registro(api):
    """HU-01-01 Escenario 2 (borde): Normalización del email (mayúsculas y espacios).

    - Dado que no existe ninguna cuenta con el email normalizado
    - Cuando se registra con espacios de borde y mayúsculas
    - Entonces 201 y el email persistido/normalizado queda en minúsculas sin bordes
    - Y registrar la misma identidad normalizada en mayúsculas se rechaza con
      EMAIL_ALREADY_EXISTS (409)
    """
    # Dado
    sufijo = secrets.token_hex(6)
    email_normalizado = f"at-norm-{sufijo}@example.com"

    # Cuando: variante con espacios de borde y capitalización mixta (RN-1: trim + lowercase)
    resp = _registrar(api, f"  At-Norm-{sufijo.upper()}@Example.COM  ")

    # Entonces
    assert resp.status_code == 201, resp.text
    assert resp.json()["email"] == email_normalizado  # RN-1: normalización trim+lowercase

    # Y: misma identidad normalizada, otra capitalización ⇒ 409 (RN-1, RNE-1)
    resp = _registrar(api, f"AT-NORM-{sufijo.upper()}@example.com")
    assert_error(resp, "EMAIL_ALREADY_EXISTS")


@pytest.mark.at("AT-01-01-03")
def test_email_ya_registrado_se_rechaza_con_409(api):
    """HU-01-01 Escenario 3 (error): Email ya registrado.

    - Dado que ya existe una cuenta con ese email normalizado
    - Cuando se intenta registrar el mismo email
    - Entonces EMAIL_ALREADY_EXISTS (409) con details.email
    - Y no se crea una segunda cuenta
    """
    # Dado
    email = email_unico("dup")
    registro = registrar(api, email=email)

    # Cuando
    resp = _registrar(api, email)

    # Entonces (RN-1: unicidad; catálogo 3.6: details = { email })
    err = assert_error(resp, "EMAIL_ALREADY_EXISTS")
    assert err["details"]["email"] == email

    # Y: la única cuenta sigue siendo la original (mismo accountId al autenticar)
    token = login(api, email)
    with api.con_token(token) as autenticado:
        perfil = autenticado.get("/me").json()
    assert perfil["accountId"] == registro["accountId"]


# -------------------------------------------------------------------------------------
# Formato de email inválido (RN-2)
# -------------------------------------------------------------------------------------


def _assert_email_invalido(api, email) -> None:
    # RN-2: email que no cumple el patrón ⇒ VALIDATION_ERROR (422)
    resp = _registrar(api, email)
    assert_error(resp, "VALIDATION_ERROR")
    # Y: no se crea ninguna cuenta
    _assert_no_se_creo_cuenta(api, email, PASSWORD_DEFECTO)


@pytest.mark.at("AT-01-01-04a")
def test_email_sin_arroba_es_validation_error(api):
    """HU-01-01 Escenario 4 (error): Formato de email inválido — sin `@`."""
    # Cuando / Entonces
    _assert_email_invalido(api, "trader-at-example.com")


@pytest.mark.at("AT-01-01-04b")
def test_email_con_dominio_sin_punto_es_validation_error(api):
    """HU-01-01 Escenario 4b (error): Formato de email inválido — dominio sin punto."""
    _assert_email_invalido(api, "trader@example")


@pytest.mark.at("AT-01-01-04c")
def test_email_con_parte_local_vacia_es_validation_error(api):
    """HU-01-01 Escenario 4c (error): Formato de email inválido — parte local vacía."""
    _assert_email_invalido(api, "@example.com")


@pytest.mark.at("AT-01-01-04d")
def test_email_con_espacio_interno_es_validation_error(api):
    """HU-01-01 Escenario 4d (error): Formato de email inválido — espacio interno.

    El espacio es interno (no de borde), así que la normalización trim de RN-1
    no lo elimina y el patrón de RN-2 lo rechaza.
    """
    _assert_email_invalido(api, "a b@example.com")


@pytest.mark.at("AT-01-01-04e")
def test_email_con_puntos_invalidos_en_dominio_es_validation_error(api):
    """HU-01-01 Escenario 4e (error): dominio con punto inicial o puntos consecutivos.

    RN-2 (patrón corregido): rechaza `user@.example.com` y `user@example..com`.
    """
    _assert_email_invalido(api, "user@.example.com")
    _assert_email_invalido(api, "user@example..com")


# -------------------------------------------------------------------------------------
# Política de contraseña (RN-3) y bordes
# -------------------------------------------------------------------------------------


@pytest.mark.at("AT-01-01-05")
def test_password_demasiado_corta_es_validation_error(api):
    """HU-01-01 Escenario 5 (error): Contraseña demasiado corta (7 caracteres)."""
    # Dado
    email = email_unico("pwcorta")
    password = "Abc1234"
    assert len(password) == 7  # borde inferior − 1 (RN-3)

    # Cuando / Entonces (RN-3: fuera de 8..128 ⇒ 422)
    resp = _registrar(api, email, password)
    assert_error(resp, "VALIDATION_ERROR")

    # Y: no se crea ninguna cuenta
    _assert_no_se_creo_cuenta(api, email, password)


@pytest.mark.at("AT-01-01-06")
def test_password_demasiado_larga_es_validation_error(api):
    """HU-01-01 Escenario 6 (error): Contraseña demasiado larga (129 caracteres)."""
    # Dado
    email = email_unico("pwlarga")
    password = "Abcd1234" * 16 + "x"
    assert len(password) == 129  # borde superior + 1 (RN-3)

    # Cuando / Entonces
    resp = _registrar(api, email, password)
    assert_error(resp, "VALIDATION_ERROR")
    _assert_no_se_creo_cuenta(api, email, password)


@pytest.mark.at("AT-01-01-12")
def test_password_en_el_limite_inferior_valido(api):
    """HU-01-01 Escenario 12 (borde): Contraseña de exactamente 8 caracteres."""
    # Dado
    email = email_unico("pw8")
    password = "Abcd1234"
    assert len(password) == 8  # borde inferior inclusive (RN-3)

    # Cuando / Entonces
    resp = _registrar(api, email, password)
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "ACTIVE"  # RN-6

    # La cuenta quedó creada y utilizable
    login(api, email, password)


@pytest.mark.at("AT-01-01-13")
def test_password_en_el_limite_superior_valido(api):
    """HU-01-01 Escenario 13 (borde): Contraseña de exactamente 128 caracteres."""
    # Dado
    email = email_unico("pw128")
    password = "Abcd1234" * 16
    assert len(password) == 128  # borde superior inclusive (RN-3)

    # Cuando / Entonces
    resp = _registrar(api, email, password)
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "ACTIVE"  # RN-6
    login(api, email, password)


@pytest.mark.at("AT-01-01-14")
def test_email_en_el_limite_superior_valido(api):
    """HU-01-01 Escenario 14 (borde): Email de exactamente 254 caracteres."""
    # Dado (RN-2: 254 es válido)
    email = _email_unico_de_largo("at14", 254)

    # Cuando / Entonces
    resp = _registrar(api, email)
    assert resp.status_code == 201, resp.text
    assert resp.json()["email"] == email


@pytest.mark.at("AT-01-01-15")
def test_email_que_excede_el_maximo_es_validation_error(api):
    """HU-01-01 Escenario 15 (error): Email de 255 caracteres."""
    # Dado (RN-2: 255 se rechaza)
    email = _email_unico_de_largo("at15", 255)

    # Cuando / Entonces
    resp = _registrar(api, email)
    assert_error(resp, "VALIDATION_ERROR")
    _assert_no_se_creo_cuenta(api, email, PASSWORD_DEFECTO)


# -------------------------------------------------------------------------------------
# Esquema del payload (RN-4) y precedencia (RN-9)
# -------------------------------------------------------------------------------------


@pytest.mark.at("AT-01-01-07")
def test_campo_requerido_faltante_es_validation_error(api):
    """HU-01-01 Escenario 7 (error): Campo requerido faltante.

    - Cuando envía un payload sin `password` (solo `email`)
    - Entonces VALIDATION_ERROR (422) y details.issues referencia `password`
    - Y un payload sin `email` también se rechaza con VALIDATION_ERROR
    """
    # Cuando: sin password
    resp = api.post("/auth/register", json={"email": email_unico("sinpw")})

    # Entonces (RN-4)
    err = assert_error(resp, "VALIDATION_ERROR")
    issues = (err.get("details") or {}).get("issues")
    assert issues, f"details.issues ausente: {err!r}"  # el AT exige issues
    assert "password" in json.dumps(issues), (
        f"issues no referencia el campo faltante 'password': {issues!r}"
    )

    # Y: sin email
    resp = api.post("/auth/register", json={"password": PASSWORD_DEFECTO})
    assert_error(resp, "VALIDATION_ERROR")


@pytest.mark.at("AT-01-01-08")
def test_tipo_de_dato_incorrecto_es_validation_error(api):
    """HU-01-01 Escenario 8 (error): `password` como número en vez de string."""
    # Dado
    email = email_unico("tipomal")

    # Cuando (RN-4: tipo incorrecto)
    resp = api.post("/auth/register", json={"email": email, "password": 12345678})

    # Entonces
    assert_error(resp, "VALIDATION_ERROR")

    # Y: no se crea ninguna cuenta (ni siquiera coercionando el número a string)
    _assert_no_se_creo_cuenta(api, email, "12345678")


@pytest.mark.at("AT-01-01-09")
def test_precedencia_email_invalido_antes_que_password_invalida(api):
    """HU-01-01 Escenario 9 (precedencia): email y password inválidos simultáneos.

    - Cuando envía email de formato inválido y password muy corta
    - Entonces se reporta UN solo error: VALIDATION_ERROR (422)
    - Y por RN-9 el primer chequeo que falla es el formato del email (nivel 2),
      no la política de contraseña (nivel 3)
    """
    # Cuando
    resp = api.post("/auth/register", json={"email": "no-es-email", "password": "123"})

    # Entonces: un solo error (RNE-7: envelope único)
    err = assert_error(resp, "VALIDATION_ERROR")
    assert set(resp.json()) == {"error"}

    # Y: si hay details, refieren al email (primer paso que falla) y no a la
    # política de contraseña (RN-9: se reporta sólo el primero)
    details = err.get("details")
    if details:
        serializado = json.dumps(details)
        assert "email" in serializado, f"el error no refiere al email: {details!r}"
        assert "password" not in serializado, (
            f"reporta también la password (viola RN-9, un solo error): {details!r}"
        )


@pytest.mark.at("AT-01-01-16")
def test_precedencia_campo_faltante_antes_que_politica_de_password(api):
    """HU-01-01 Escenario 16 (precedencia): campo faltante prevalece sobre formato.

    - Cuando envía un payload sin `email` y con password muy corta ("123")
    - Entonces UN solo error VALIDATION_ERROR (422) por campo faltante (nivel 1
      de RN-9), no por política de contraseña (nivel 3)
    - Y details.issues referencia el campo faltante `email`
    """
    # Cuando
    resp = api.post("/auth/register", json={"password": "123"})

    # Entonces
    err = assert_error(resp, "VALIDATION_ERROR")
    assert set(resp.json()) == {"error"}  # un solo error (RNE-7)
    issues = (err.get("details") or {}).get("issues")
    assert issues, f"details.issues ausente: {err!r}"  # el AT exige issues
    serializado = json.dumps(issues)
    assert "email" in serializado, f"issues no referencia 'email': {issues!r}"
    # RN-9: el error de nivel 3 (password corta) no debe reportarse junto al de nivel 1
    assert "password" not in serializado, (
        f"reporta también la password (viola RN-9): {issues!r}"
    )


@pytest.mark.at("AT-01-01-17")
def test_precedencia_tipo_incorrecto_antes_que_unicidad(api):
    """HU-01-01 Escenario 17 (precedencia): tipo incorrecto prevalece sobre unicidad.

    Nota: el Dado literal ("ya existe una cuenta cuyo email normalizado
    coincidiría con el valor enviado") es hipotético — un email numérico no
    puede registrarse (RN-2) —; el punto testeable es que el chequeo de tipo
    (nivel 1 de RN-9) se evalúa antes que la unicidad (nivel 4).
    """
    # Dado: existe al menos una cuenta en el sistema
    registrar(api, email=email_unico("tipo17"))

    # Cuando: email como número JSON (tipo incorrecto) + password válida
    resp = api.post("/auth/register", json={"email": 12345, "password": PASSWORD_DEFECTO})

    # Entonces: VALIDATION_ERROR (nivel 1), no EMAIL_ALREADY_EXISTS (nivel 4)
    assert_error(resp, "VALIDATION_ERROR")
    assert set(resp.json()) == {"error"}  # un solo error (RNE-7)


@pytest.mark.at("AT-01-01-18")
def test_campo_desconocido_en_el_payload_es_validation_error(api):
    """HU-01-01 Escenario 18 (error): Campo desconocido en el payload.

    - Cuando envía email y password válidos más un campo extra ("role": "admin")
    - Entonces VALIDATION_ERROR (422) y details.issues referencia el campo desconocido
    - Y no se crea ninguna cuenta
    """
    # Dado
    email = email_unico("extra")

    # Cuando (RN-4: el payload debe contener exactamente email y password)
    resp = api.post(
        "/auth/register",
        json={"email": email, "password": PASSWORD_DEFECTO, "role": "admin"},
    )

    # Entonces
    err = assert_error(resp, "VALIDATION_ERROR")
    issues = (err.get("details") or {}).get("issues")
    assert issues, f"details.issues ausente: {err!r}"  # el AT exige issues
    assert "role" in json.dumps(issues), (
        f"issues no referencia el campo desconocido 'role': {issues!r}"
    )

    # Y: no se crea ninguna cuenta
    _assert_no_se_creo_cuenta(api, email, PASSWORD_DEFECTO)


# -------------------------------------------------------------------------------------
# Concurrencia, persistencia y accountId
# -------------------------------------------------------------------------------------


@pytest.mark.at("AT-01-01-10")
def test_dos_registros_concurrentes_con_el_mismo_email(api):
    """HU-01-01 Escenario 10 (concurrencia): dos registros simultáneos, un ganador.

    - Cuando dos solicitudes con el mismo email normalizado se procesan concurrentes
    - Entonces exactamente una crea la cuenta (201) y la otra recibe
      EMAIL_ALREADY_EXISTS (409)
    - Y la cuenta resultante es completa y consultable (RN-8)
    """
    # Dado
    email = email_unico("conc")
    payload = {"email": email, "password": PASSWORD_DEFECTO}

    # Cuando: dos clientes independientes disparan el registro en paralelo
    with api.sin_token() as c1, api.sin_token() as c2:
        r1, r2 = en_paralelo(
            lambda: c1.post("/auth/register", json=payload),
            lambda: c2.post("/auth/register", json=payload),
        )

    # Entonces: exactamente una 201 y una 409 (RN-8)
    codigos = sorted([r1.status_code, r2.status_code])
    assert codigos == [201, 409], f"se esperaba [201, 409], llegó {codigos}"
    rechazada = r1 if r1.status_code == 409 else r2
    assert_error(rechazada, "EMAIL_ALREADY_EXISTS")

    # Y: una sola cuenta, completa y consultable de inmediato (RN-8)
    token = login(api, email)
    with api.con_token(token) as autenticado:
        resp = autenticado.get("/me")
    assert resp.status_code == 200, resp.text
    perfil = resp.json()
    assert isinstance(perfil["accountId"], str) and perfil["accountId"]
    assert perfil["email"] == email  # email normalizado
    assert perfil["status"] == "ACTIVE"
    parsear_iso8601_utc(perfil["createdAt"], "createdAt")


@pytest.mark.at("AT-01-01-11")
def test_cuenta_registrada_sobrevive_un_reinicio(api):
    """HU-01-01 Escenario 11 (borde): Persistencia tras reinicio (RN-11, INV-8).

    Requiere SUITE_CMD_REINICIO_SUT (reinicio orquestado por el evaluador);
    sin ella el test se salta.
    """
    # Dado: una cuenta registrada
    email = email_unico("reinicio")
    registro = registrar(api, email=email)

    # Cuando: el sistema se reinicia
    reiniciar_sut(api)

    # Entonces: la cuenta sigue existiendo con los mismos datos (RN-11)
    token = login(api, email)  # sigue autenticable tras el reinicio
    with api.con_token(token) as autenticado:
        resp = autenticado.get("/me")
    assert resp.status_code == 200, resp.text
    perfil = resp.json()
    assert perfil["accountId"] == registro["accountId"]
    assert perfil["email"] == email
    assert perfil["status"] == "ACTIVE"
    assert perfil["createdAt"] == registro["createdAt"]

    # Y: el email sigue ocupado (RN-1 sobre estado persistido)
    resp = _registrar(api, email)
    assert_error(resp, "EMAIL_ALREADY_EXISTS")


@pytest.mark.at("AT-01-01-19")
def test_account_id_opaco_y_no_secuencial(api):
    """HU-01-01 Escenario 19 (borde): el accountId es opaco y no secuencial.

    - Dado que se registran cuentas consecutivas
    - Entonces cada accountId es string no vacío, distintos entre sí, sin patrón
      secuencial/predecible (RN-6, RNE-6)
    - Y para la misma cuenta, consultas sucesivas devuelven el mismo accountId
    """
    # Dado: tres registros consecutivos
    email_primero = email_unico("opaco")
    primero = registrar(api, email=email_primero)
    ids = [
        primero["accountId"],
        registrar(api, email=email_unico("opaco"))["accountId"],
        registrar(api, email=email_unico("opaco"))["accountId"],
    ]

    # Entonces: strings no vacíos y distintos entre sí (RN-6)
    assert all(isinstance(cid, str) and cid for cid in ids)
    assert len(set(ids)) == len(ids), f"accountId repetidos: {ids}"

    # Y: sin patrón secuencial ni derivado del timestamp (heurísticas de RNE-6;
    # sólo aplican si los ids son enteros decimales — UUID/ULID pasan de largo)
    if all(re.fullmatch(r"[0-9]+", cid) for cid in ids):
        numeros = [int(cid) for cid in ids]
        diferencias = [b - a for a, b in zip(numeros, numeros[1:])]
        assert all(abs(d) > 1 for d in diferencias), (
            f"accountId enteros consecutivos (prohibido por RN-6): {ids}"
        )
        assert len(set(diferencias)) > 1, (
            f"accountId con incremento constante (patrón predecible, RN-6): {ids}"
        )
        ahora = time.time()
        for n in numeros:
            for escala in (1, 1_000, 1_000_000):  # epoch en s / ms / µs
                assert abs(n - ahora * escala) > 86_400 * escala, (
                    f"accountId {n} ≈ epoch actual (derivable del timestamp, RN-6)"
                )

    # Y: consultas sucesivas de la misma cuenta devuelven el mismo accountId
    token = login(api, email_primero)
    with api.con_token(token) as autenticado:
        assert autenticado.get("/me").json()["accountId"] == ids[0]
        assert autenticado.get("/me").json()["accountId"] == ids[0]


@pytest.mark.at("AT-01-01-20")
def test_anti_flood_de_registro_responde_rate_limited(api):
    """HU-01-01 Escenario 20 (seguridad, condicional a config): Anti-flood de registro.

    - Dado rate limiting de registro activo con umbral N y ventana T declarados
      en la configuración del entorno (60 req/min y 60 s si la implementación lo
      expone, entorno/README.md; HU-01-01 RN-10 — ADR-006 D4: opcional en este
      endpoint público, fuera de la política por cuenta de HU-09-02 RN-12)
    - Cuando se hacen N+1 solicitudes desde el mismo origen dentro de la ventana
    - Entonces la N+1 se rechaza con RATE_LIMITED (429) y
      details.retryAfterSeconds ≥ 0
    - (Si el rate limiting no está activo, el AT no aplica y el test se salta; RN-10)
    """
    respuesta_429 = None
    try:
        # Cuando: hasta N+1 registros desde el mismo origen dentro de la ventana.
        # Nota: la ventana por origen es compartida con el resto de la suite,
        # por lo que el 429 puede llegar antes de la solicitud 61 — sigue siendo
        # el comportamiento especificado (ventana deslizante de 60 s).
        for _ in range(N_RATE_LIMIT + 1):
            resp = _registrar(api, email_unico("flood"))
            if resp.status_code == 429:
                respuesta_429 = resp
                break
            # las solicitudes dentro de la ventana se procesan normalmente
            assert resp.status_code == 201, resp.text

        if respuesta_429 is None:
            pytest.skip(
                "rate limiting de registro inactivo o con umbral distinto de "
                "60/min: el AT no aplica (HU-01-01 RN-10)"
            )

        # Entonces (RN-10; catálogo 3.1: RATE_LIMITED = 429)
        err = assert_error(respuesta_429, "RATE_LIMITED")
        retry = err["details"]["retryAfterSeconds"]
        # retryAfterSeconds es un conteo ⇒ entero JSON ≥ 0 (RN-10; convenciones §5)
        assert isinstance(retry, int) and not isinstance(retry, bool) and retry >= 0
    finally:
        # Higiene entre tests: dejar el endpoint utilizable (la ventana es de 60 s)
        if respuesta_429 is not None:
            esperar_rate_limit_liberado(
                lambda: _registrar(api, email_unico("flood-fin")).status_code == 201,
                "el endpoint de registro no se recuperó del rate limiting",
            )
