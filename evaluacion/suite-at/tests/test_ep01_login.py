"""Épica 01 / HU-01-02 — Inicio de sesión: tests de aceptación black-box.

Spec: spec/01-cuentas-y-autenticacion/HU-01-02-inicio-de-sesion.md
Contrato de transporte: POST /api/v1/auth/login (HU-09-01, mapa de endpoints).

AT-01-02-13 (log de auditoría interno) se declara no automatizable en
tests/no_automatizables_ep01.yaml: la propia HU lo marca como "no observable
por caja negra en la respuesta de la API" (RNE-9).

Los tests de carga (AT-01-02-09/10/11) están definidos al final del archivo
para que su presión sobre la ventana de rate limiting por IP (HU-09-02 RN-12)
no afecte a los escenarios livianos; además cada uno espera la liberación de
la ventana antes de terminar, así el orden de ejecución no importa.
"""

import os
import time
from datetime import datetime, timezone
from itertools import combinations

import pytest

from helpers.cuentas import PASSWORD_DEFECTO, email_unico, login, registrar
from helpers.errores import assert_error
from helpers.espera import esperar_hasta

from comunes_ep01 import (
    N_RATE_LIMIT,
    VAR_UMBRAL_TIMING,
    assert_sin_claves_de_password,
    esperar_rate_limit_liberado,
    parsear_iso8601_utc,
    percentil,
)

RUTA_LOGIN = "/auth/login"


def _login(api, email, password):
    """POST crudo al login (sin asserts): para los escenarios de error."""
    return api.post(RUTA_LOGIN, json={"email": email, "password": password})


# -------------------------------------------------------------------------------------
# Camino feliz, normalización y sesiones
# -------------------------------------------------------------------------------------


@pytest.mark.at("AT-01-02-01")
def test_login_exitoso_devuelve_token_con_expiracion(api):
    """HU-01-02 Escenario 1: Login exitoso.

    - Dado una cuenta ACTIVE con contraseña `Sup3rSecreta`
    - Cuando hace login con las credenciales correctas
    - Entonces 200 con `token` no vacío y `expiresAt` ISO 8601 UTC futuro
    - Y el cuerpo no incluye la contraseña ni su hash
    """
    # Dado
    email = email_unico("login")
    password = "Sup3rSecreta"
    registrar(api, email=email, password=password)

    # Cuando
    resp = _login(api, email, password)

    # Entonces (RN-3: token + expiresAt)
    assert resp.status_code == 200, resp.text
    cuerpo = resp.json()
    assert isinstance(cuerpo["token"], str) and cuerpo["token"]
    expira = parsear_iso8601_utc(cuerpo["expiresAt"], "expiresAt")
    assert expira > datetime.now(timezone.utc), (
        f"expiresAt no es posterior al instante actual: {cuerpo['expiresAt']}"
    )

    # Y: sin contraseña ni hash (RN-4, RNE-2)
    assert_sin_claves_de_password(cuerpo)
    assert password not in resp.text


@pytest.mark.at("AT-01-02-02")
def test_login_normaliza_capitalizacion_y_espacios_del_email(api):
    """HU-01-02 Escenario 2 (borde): email con distinta capitalización y espacios.

    - Dado una cuenta cuyo email normalizado es conocido
    - Cuando hace login con mayúsculas y espacios de borde y la contraseña correcta
    - Entonces 200 y autentica la MISMA cuenta (RN-1: se normaliza antes de buscar)
    """
    # Dado
    email = email_unico("caps")
    registro = registrar(api, email=email)

    # Cuando (RN-1: trim + lowercase antes de buscar)
    resp = _login(api, f"  {email.upper()} ", PASSWORD_DEFECTO)

    # Entonces
    assert resp.status_code == 200, resp.text
    token = resp.json()["token"]

    # Y: es la misma cuenta (mismo accountId que el registro)
    with api.con_token(token) as autenticado:
        assert autenticado.get("/me").json()["accountId"] == registro["accountId"]


@pytest.mark.at("AT-01-02-03")
def test_el_token_autentica_una_llamada_protegida(api):
    """HU-01-02 Escenario 3 (borde): el token autentica una llamada protegida.

    - Dado un login exitoso con `token` válido y no expirado
    - Cuando invoca un endpoint protegido (perfil, HU-01-04) con ese token
    - Entonces la llamada se procesa autenticada (no UNAUTHENTICATED)
    """
    # Dado
    email = email_unico("tok")
    registro = registrar(api, email=email)
    token = login(api, email)

    # Cuando
    with api.con_token(token) as autenticado:
        resp = autenticado.get("/me")

    # Entonces (RN-5: token funcional inmediato)
    assert resp.status_code == 200, resp.text
    assert resp.json()["accountId"] == registro["accountId"]


@pytest.mark.at("AT-01-02-08")
def test_sesiones_multiples_concurrentes_no_se_invalidan(api):
    """HU-01-02 Escenario 8 (borde): sesiones múltiples concurrentes.

    - Cuando el usuario hace login dos veces seguidas con credenciales correctas
    - Entonces se emiten dos tokens distintos, ambos utilizables
    - Y el segundo login no invalida el token del primero
    """
    # Dado
    email = email_unico("multi")
    registrar(api, email=email)

    # Cuando: dos logins sucesivos
    token_a = login(api, email)
    token_b = login(api, email)

    # Entonces: tokens distintos (RN-6)
    assert token_a != token_b

    # Y: ambos válidos; el segundo login no invalidó al primero (RN-6)
    with api.con_token(token_b) as sesion_b:
        assert sesion_b.get("/me").status_code == 200
    with api.con_token(token_a) as sesion_a:
        assert sesion_a.get("/me").status_code == 200


# -------------------------------------------------------------------------------------
# Errores de credenciales y no-enumeración (RN-2, RN-11, RNE-3)
# -------------------------------------------------------------------------------------


@pytest.mark.at("AT-01-02-04")
def test_password_incorrecta_es_invalid_credentials(api, usuario):
    """HU-01-02 Escenario 4 (error): Contraseña incorrecta.

    - Cuando hace login con un email existente y una contraseña incorrecta
    - Entonces INVALID_CREDENTIALS (401) sin details discriminante
    - Y no se emite ningún token
    """
    # Cuando
    resp = _login(api, usuario.email, "Incorrecta-123")

    # Entonces (RN-2; catálogo 3.6: INVALID_CREDENTIALS = 401, details "—")
    err = assert_error(resp, "INVALID_CREDENTIALS")
    assert not err.get("details"), (
        f"details en INVALID_CREDENTIALS puede revelar la causa (RN-2): {err!r}"
    )

    # Y: no se emite ningún token (el cuerpo es sólo el envelope de error)
    assert set(resp.json()) == {"error"}


@pytest.mark.at("AT-01-02-05")
def test_email_inexistente_es_indistinguible_de_password_incorrecta(api, usuario):
    """HU-01-02 Escenario 5 (error): email inexistente — respuesta indistinguible.

    - Dado que no existe ninguna cuenta con cierto email
    - Cuando hace login con ese email y cualquier contraseña
    - Entonces INVALID_CREDENTIALS (401)
    - Y la respuesta (code, status y forma) es indistinguible de la del
      Escenario 4 (password incorrecta sobre email existente)
    """
    # Dado / Cuando: las dos rutas de fallo
    resp_password_mal = _login(api, usuario.email, "Incorrecta-123")
    resp_inexistente = _login(api, email_unico("noexiste"), "Incorrecta-123")

    # Entonces (RN-2)
    assert_error(resp_password_mal, "INVALID_CREDENTIALS")
    assert_error(resp_inexistente, "INVALID_CREDENTIALS")

    # Y: respuestas idénticas entre sí (RN-2: "la respuesta es idéntica"; RNE-3)
    assert resp_inexistente.status_code == resp_password_mal.status_code
    assert resp_inexistente.json() == resp_password_mal.json(), (
        "las respuestas de 'email inexistente' y 'password incorrecta' difieren "
        "(permite enumerar cuentas, RN-2/RNE-3)"
    )


@pytest.mark.at("AT-01-02-12")
def test_email_con_formato_invalido_en_login_no_es_validation_error(api):
    """HU-01-02 Escenario 12 (no enumeración): email con formato inválido en login.

    - Cuando hace login con un email de formato inválido (string sin `@`)
    - Entonces INVALID_CREDENTIALS (401), NO VALIDATION_ERROR (RN-11)
    - Y la respuesta es indistinguible de la de un email válido pero inexistente
    """
    password = "CualquierClave-1"

    # Cuando: formato inválido (pasa el esquema por ser string; RN-11)
    resp_formato_invalido = _login(api, "no-es-email", password)

    # Entonces: se resuelve como credenciales inválidas, no como validación
    assert_error(resp_formato_invalido, "INVALID_CREDENTIALS")

    # Y: indistinguible del email con formato válido pero inexistente (RNE-3)
    resp_inexistente = _login(api, email_unico("noexiste12"), password)
    assert_error(resp_inexistente, "INVALID_CREDENTIALS")
    assert resp_formato_invalido.status_code == resp_inexistente.status_code
    assert resp_formato_invalido.json() == resp_inexistente.json(), (
        "la respuesta al formato inválido difiere de la del email inexistente "
        "(filtra información, RN-11/RNE-3)"
    )


# -------------------------------------------------------------------------------------
# Esquema del payload y precedencia (RN-7, RN-8)
# -------------------------------------------------------------------------------------


@pytest.mark.at("AT-01-02-06")
def test_payload_de_login_mal_formado_es_validation_error(api):
    """HU-01-02 Escenario 6 (error): payload sin `password`.

    - Cuando envía un login sin el campo `password`
    - Entonces VALIDATION_ERROR (422) y no se emite ningún token
    """
    # Cuando (RN-7: esquema requiere email y password strings)
    resp = api.post(RUTA_LOGIN, json={"email": email_unico("sinpw")})

    # Entonces
    assert_error(resp, "VALIDATION_ERROR")
    assert set(resp.json()) == {"error"}  # sin token en la respuesta


@pytest.mark.at("AT-01-02-07")
def test_precedencia_esquema_antes_que_credenciales(api):
    """HU-01-02 Escenario 7 (precedencia): esquema inválido antes que credenciales.

    - Cuando envía un login con `email` ausente y `password` presente
    - Entonces UN solo error: VALIDATION_ERROR (422), no INVALID_CREDENTIALS
      (RN-8: paso 1 esquema → paso 2 credenciales)
    """
    # Cuando
    resp = api.post(RUTA_LOGIN, json={"password": "loquesea"})

    # Entonces (assert_error exige exactamente VALIDATION_ERROR/422)
    assert_error(resp, "VALIDATION_ERROR")
    assert set(resp.json()) == {"error"}  # un solo error por respuesta (RNE-7)


# -------------------------------------------------------------------------------------
# Seguridad: timing, entropía y rate limiting (tests de carga, al final)
# -------------------------------------------------------------------------------------


@pytest.mark.at("AT-01-02-11")
def test_indistinguibilidad_temporal_anti_timing_attack(api, usuario):
    """HU-01-02 Escenario 11 (seguridad): anti timing attack (RN-12, RNE-3).

    - Dado una cuenta existente y un email inexistente
    - Cuando se miden 50 intentos de login por cada ruta de fallo, bajo carga
      controlada (intercalados y a ritmo constante)
    - Entonces P50 y P95 de ambas rutas no difieren más que el umbral del
      entorno (SUITE_UMBRAL_TIMING_MS; referencia de la spec: < 50 ms)
    """
    # Dado
    email_inexistente = email_unico("timing-noexiste")
    password = "CualquierClave-1"
    n = 50
    umbral_ms = float(os.environ.get(VAR_UMBRAL_TIMING, "50"))

    def medir(email: str) -> float:
        t0 = time.perf_counter()
        resp = _login(api, email, password)
        ms = (time.perf_counter() - t0) * 1000.0
        # ambas rutas deben terminar en el mismo error (RN-2); un 429 acá
        # invalidaría la muestra, el pacing de abajo lo evita
        assert_error(resp, "INVALID_CREDENTIALS")
        return ms

    # Cuando: muestras intercaladas, a ritmo < 60 req/min por endpoint para no
    # disparar RATE_LIMITED (HU-09-02 RN-12). El sleep es control de tasa del
    # propio test (carga controlada del AT), no una espera de estado del SUT.
    paso = 1.05
    inicio = time.monotonic()
    lat_inexistente: list[float] = []
    lat_password_mal: list[float] = []
    for i in range(n):
        for indice, (destino, email) in enumerate(
            ((lat_inexistente, email_inexistente), (lat_password_mal, usuario.email))
        ):
            objetivo = inicio + (2 * i + indice) * paso
            falta = objetivo - time.monotonic()
            if falta > 0:
                time.sleep(falta)
            destino.append(medir(email))

    # Entonces: percentiles indistinguibles (evidencia del hash dummy de RN-12)
    for p in (50, 95):
        diferencia = abs(percentil(lat_inexistente, p) - percentil(lat_password_mal, p))
        assert diferencia < umbral_ms, (
            f"P{p} difiere {diferencia:.1f} ms ≥ {umbral_ms:.0f} ms entre "
            "'email inexistente' y 'password incorrecta': el canal lateral de "
            "tiempo permite enumerar emails (RN-12, RNE-3)"
        )


@pytest.mark.at("AT-01-02-10")
def test_heuristica_de_entropia_cien_tokens_sin_prefijo_comun(api, usuario):
    """HU-01-02 Escenario 10 (seguridad): heurística de entropía del token.

    - Cuando se emiten cien tokens para la misma cuenta (cien logins exitosos)
    - Entonces los cien son distintos entre sí
    - Y ningún par comparte un prefijo de más de 4 caracteres (heurística
      observable mínima de RN-3; la verificación formal es del DoD)

    TODO-REVISAR: RN-3 admite JWT como esquema de token, pero todo JWT firmado
    con el mismo algoritmo comparte el prefijo del encabezado base64
    ("eyJhbGciOi..."), con lo cual un SUT con JWT falla esta heurística tal como
    está redactada en el AT. Se implementa literal al texto del AT (holdout).
    """

    def login_ok():
        resp = _login(api, usuario.email, usuario.password)
        return resp if resp.status_code == 200 else False

    # Cuando: cien logins exitosos; si la ventana de 60 req/min por IP
    # (HU-09-02 RN-12) responde 429, se sondea hasta que se libere y se sigue.
    tokens: list[str] = []
    try:
        while len(tokens) < 100:
            resp = login_ok()
            if not resp:
                resp = esperar_hasta(
                    login_ok,
                    timeout=180,
                    intervalo=2,
                    mensaje="el endpoint de login no volvió a aceptar solicitudes",
                )
            tokens.append(resp.json()["token"])
    finally:
        # Higiene entre tests: no dejar la ventana por IP al borde del límite
        esperar_rate_limit_liberado(
            login_ok, "el endpoint de login no se recuperó tras los cien logins"
        )

    # Entonces: todos distintos (RN-6 emite tokens distintos; RN-3 no adivinables)
    assert len(set(tokens)) == 100, "hay tokens repetidos entre cien emisiones"

    # Y: ningún par comparte prefijo de más de 4 caracteres
    for a, b in combinations(tokens, 2):
        comun = os.path.commonprefix([a, b])
        assert len(comun) <= 4, (
            f"dos tokens comparten un prefijo de {len(comun)} caracteres "
            f"({comun[:16]!r}…): viola la heurística de entropía del AT"
        )


@pytest.mark.at("AT-01-02-09")
def test_rate_limiting_de_login_tras_multiples_fallos(api, usuario):
    """HU-01-02 Escenario 9 (error): rate limiting tras múltiples fallos.

    - Dado el rate limiting del entorno (N=60, W=60 s; HU-09-02 RN-12) y N
      intentos fallidos dentro de la ventana hacia el mismo email/origen
    - Cuando realiza el intento N+1 dentro de la ventana
    - Entonces RATE_LIMITED (429) con details.retryAfterSeconds
    - Y el comportamiento es uniforme y no revela si el email existe

    TODO-REVISAR: HU-01-02 RN-9 habla de límite "por email/origen" y lo declara
    opcional por config; HU-09-02 RN-12 fija una política única por IP en
    endpoints públicos (60 req/min). Se asserta el comportamiento por IP de la
    09 (la política del entorno); si no se observa 429 el test se salta (RN-9).
    """
    respuesta_429 = None
    try:
        # Dado/Cuando: intentos fallidos consecutivos hasta exceder la ventana.
        # La ventana por IP es compartida con el resto de la suite ⇒ el 429
        # puede llegar antes del intento 61 (ventana deslizante, HU-09-02 RN-12).
        for _ in range(N_RATE_LIMIT + 1):
            resp = _login(api, usuario.email, "Incorrecta-999")
            if resp.status_code == 429:
                respuesta_429 = resp
                break
            # dentro de la ventana, el fallo es el normal de credenciales
            assert_error(resp, "INVALID_CREDENTIALS")

        if respuesta_429 is None:
            pytest.skip(
                "rate limiting de login inactivo o con umbral distinto de 60/min: "
                "el Dado del AT no se cumple (HU-01-02 RN-9, opcional por config)"
            )

        # Entonces (catálogo 3.1: RATE_LIMITED = 429, details = { retryAfterSeconds })
        err = assert_error(respuesta_429, "RATE_LIMITED")
        retry = err["details"]["retryAfterSeconds"]
        # conteo ⇒ entero JSON ≥ 0 (HU-09-02 RN-12; convenciones §5)
        assert isinstance(retry, int) and not isinstance(retry, bool) and retry >= 0

        # Y: uniforme, sin revelar existencia del email — con la ventana
        # excedida, un email inexistente recibe el mismo 429 (RN-9, RNE-3)
        resp = _login(api, email_unico("noexiste-rl"), "CualquierClave-1")
        assert_error(resp, "RATE_LIMITED")
    finally:
        # Higiene entre tests: esperar a que la ventana de 60 s se libere
        if respuesta_429 is not None:
            esperar_rate_limit_liberado(
                lambda: _login(api, usuario.email, usuario.password).status_code == 200,
                "el endpoint de login no se recuperó del rate limiting",
            )
