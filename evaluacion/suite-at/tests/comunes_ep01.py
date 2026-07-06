"""Utilidades compartidas de los tests de la épica 01 (cuentas y autenticación).

No es un módulo de tests (pytest no lo colecta). Lo importan los
``test_ep01_*.py`` que están en este mismo directorio.

Convenciones tomadas de la spec:

- Rutas según el mapa de endpoints de HU-09-01: ``/auth/register``,
  ``/auth/login``, ``/auth/logout`` y ``/me`` (el cliente agrega ``/api/v1``).
  La ruta de logout es canónica desde spec-v1.1 (ADR-006 D5): ``POST
  /api/v1/auth/logout``, fila Logout del mapa de HU-09-01; el comportamiento lo
  fija HU-01-03.

Env vars propias de estos tests (las provee el evaluador, no el SUT):

- ``SUITE_CMD_REINICIO_SUT``: comando de shell que reinicia el SUT (p. ej.
  ``docker restart sut``). Los ATs de persistencia tras reinicio (INV-8:
  AT-01-01-11, AT-01-03-08, AT-01-03-10) se saltan si no está configurada
  (HELPERS.md: "reinicio del SUT orquestado por el evaluador").
- ``SUITE_UMBRAL_TIMING_MS``: umbral en milisegundos para AT-01-02-11
  (default 50: la referencia que fija HU-01-02 Escenario 11).
"""

import base64
import json
import math
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import httpx
import pytest

from helpers.espera import esperar_hasta

# -- rutas de la épica (relativas a /api/v1, HU-09-01) -------------------------------

RUTA_REGISTRO = "/auth/register"
RUTA_LOGIN = "/auth/login"
RUTA_PERFIL = "/me"
RUTA_LOGOUT = "/auth/logout"  # canónica en el mapa de HU-09-01 (comportamiento: HU-01-03)

# Contenido exacto del perfil/registro (HU-01-04 RN-4, HU-01-01 RN-6: sólo identidad).
CAMPOS_IDENTIDAD = {"accountId", "email", "status", "createdAt"}

# Claves que jamás pueden aparecer en una respuesta de esta épica (RNE-2, HU-01-01 RN-5).
CLAVES_DE_PASSWORD = (
    "password",
    "passwordhash",
    "password_hash",
    "hash",
    "salt",
    "secret",
)

# Rate limiting: la política determinista de HU-09-02 RN-12 (60 req/min por
# cuenta y endpoint, ventana deslizante de 60 s) aplica SOLO a endpoints
# autenticados. En los endpoints públicos /auth/* el rate limiting es OPCIONAL
# y lo rige la épica 01 (HU-01-01 RN-10, HU-01-02 RN-9): si existe, responde
# RATE_LIMITED. El entorno de evaluación deja el umbral en 60 req/min cuando la
# implementación lo expone (entorno/README.md), así que los tests condicionales
# de /auth/* sondean N+1 = 61 intentos y se saltan si no observan un 429.
N_RATE_LIMIT = 60
VENTANA_RATE_LIMIT_SEGUNDOS = 60

VAR_CMD_REINICIO = "SUITE_CMD_REINICIO_SUT"
VAR_UMBRAL_TIMING = "SUITE_UMBRAL_TIMING_MS"


# -- timestamps ------------------------------------------------------------------------


def parsear_iso8601_utc(valor, campo: str = "timestamp") -> datetime:
    """Valida que `valor` sea un timestamp ISO 8601 en UTC (RNE-8) y lo devuelve.

    Acepta el sufijo ``Z`` o el offset explícito ``+00:00`` (ambos denotan UTC).
    """
    assert isinstance(valor, str) and valor, f"{campo} ausente o no string: {valor!r}"
    try:
        dt = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        raise AssertionError(f"{campo} no es ISO 8601: {valor!r}") from None
    assert dt.tzinfo is not None, f"{campo} sin zona horaria explícita (se exige UTC): {valor!r}"
    assert dt.utcoffset() == timedelta(0), f"{campo} no está en UTC: {valor!r}"
    return dt


# -- secretos nunca expuestos (RNE-2) --------------------------------------------------


def assert_sin_claves_de_password(cuerpo: dict) -> None:
    """Asserta que ninguna clave del cuerpo huela a contraseña/hash/sal (RNE-2, RN-5)."""
    assert isinstance(cuerpo, dict), f"se esperaba un objeto JSON: {cuerpo!r}"
    for clave in cuerpo:
        assert clave.lower() not in CLAVES_DE_PASSWORD, (
            f"clave sensible {clave!r} expuesta en la respuesta (RNE-2)"
        )


# -- logout (HU-01-03) -----------------------------------------------------------------


def logout(cliente):
    """POST al endpoint de logout con el cliente dado (autenticado o no)."""
    return cliente.post(RUTA_LOGOUT)


def es_jwt(token: str) -> bool:
    """Heurística observable: 3 segmentos base64url y encabezado JSON con `alg`.

    Sirve para decidir si aplica AT-01-03-10 (denylist persistente para JWT,
    HU-01-03 RN-10) o si el caso queda cubierto por AT-01-03-08 (token opaco).
    """
    partes = token.split(".")
    if len(partes) != 3:
        return False
    try:
        relleno = "=" * (-len(partes[0]) % 4)
        encabezado = json.loads(base64.urlsafe_b64decode(partes[0] + relleno))
    except (ValueError, json.JSONDecodeError):
        return False
    return isinstance(encabezado, dict) and "alg" in encabezado


# -- reinicio del SUT (INV-8) ----------------------------------------------------------


def _sut_responde(api) -> bool:
    """Cualquier respuesta HTTP del SUT (endpoint público, HU-09-01 RN-16) prueba
    que volvió a estar arriba; las fallas de conexión indican que sigue caído."""
    try:
        api.get("/market/ticker")
        return True
    except httpx.HTTPError:
        return False


def reiniciar_sut(api) -> None:
    """Reinicia el SUT vía el comando del evaluador y espera a que vuelva a responder.

    El reinicio no es provocable por el contrato HTTP/WS: lo orquesta el
    evaluador (HELPERS.md §no-automatizables) a través de ``SUITE_CMD_REINICIO_SUT``.
    Sin esa env var, el test que lo necesita se salta.
    """
    cmd = os.environ.get(VAR_CMD_REINICIO, "").strip()
    if not cmd:
        pytest.skip(
            f"{VAR_CMD_REINICIO} no configurada: el reinicio del SUT (INV-8) "
            "lo orquesta el evaluador"
        )
    resultado = subprocess.run(cmd, shell=True)
    assert resultado.returncode == 0, f"el comando de reinicio del SUT falló: {cmd!r}"
    esperar_hasta(
        lambda: _sut_responde(api),
        timeout=120,
        intervalo=2,
        mensaje="el SUT no volvió a responder tras el reinicio",
    )


# -- concurrencia ----------------------------------------------------------------------


def en_paralelo(*tareas):
    """Ejecuta callables sin argumentos en threads simultáneos y devuelve sus
    resultados en el mismo orden (para los ATs de concurrencia: AT-01-01-10,
    AT-01-03-11)."""
    with ThreadPoolExecutor(max_workers=len(tareas)) as pool:
        futuros = [pool.submit(tarea) for tarea in tareas]
        return [futuro.result() for futuro in futuros]


# -- rate limiting ---------------------------------------------------------------------


def esperar_rate_limit_liberado(intento_ok, mensaje: str):
    """Espera a que un endpoint deje de responder RATE_LIMITED.

    ``intento_ok()`` debe devolver truthy cuando el endpoint volvió a aceptar.
    Se sondea cada 5 s (12 req/min << 60 req/min) para que el propio sondeo no
    mantenga saturada la ventana deslizante de 60 s del rate limiting opcional
    de /auth/* (HU-01-01 RN-10 / HU-01-02 RN-9; valor del entorno: 60/min).
    """
    return esperar_hasta(
        intento_ok,
        timeout=3 * VENTANA_RATE_LIMIT_SEGUNDOS,
        intervalo=5,
        mensaje=mensaje,
    )


# -- estadística (AT-01-02-11) ---------------------------------------------------------


def percentil(datos, p: float) -> float:
    """Percentil por rango más cercano (nearest-rank); la spec no fija el método."""
    assert datos, "sin muestras para calcular percentil"
    ordenados = sorted(datos)
    k = max(1, math.ceil(p / 100 * len(ordenados)))
    return ordenados[k - 1]
