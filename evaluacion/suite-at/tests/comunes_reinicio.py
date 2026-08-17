"""Reinicio del SUT orquestado por el evaluador — helper transversal a las épicas.

El contrato HTTP/WS de la épica 09 no expone ninguna operación de reinicio (y no
debe: sería una superficie de administración que la spec no define). El reinicio
lo provee el **evaluador** por fuera del contrato, con la env var
``SUITE_CMD_REINICIO_SUT``: un comando de shell que termina el proceso del SUT
**abruptamente** (equivalente a ``kill -9``; HU-03-07 RN-1 define "durable" como
sobrevivir a esa terminación), preserva su persistencia y lo vuelve a levantar.

Eso hace que los ATs de persistencia (INV-8) sean **automatizables black-box de
forma condicional**: el test construye el "Dado" y verifica el "Entonces" por
REST/WS/on-chain como cualquier otro, y el único elemento no contractual —el
disparo del reinicio— viene del entorno. Sin la env var, el test **se salta con
motivo explícito** (nunca inventa un veredicto ni una API de reinicio).

Los tests de las épicas 01 y 03 ya usaban copias locales de este helper
(``comunes_ep01.reiniciar_sut``, ``comunes_ep03.reiniciar_sut``); este módulo es
la versión compartida que usan las épicas 04, 06, 07 y 08. La duplicación previa
se deja como está para no tocar tests ya congelados.
"""

import os
import subprocess

import pytest

from helpers.cuentas import login
from helpers.espera import esperar_hasta

VAR_CMD_REINICIO = "SUITE_CMD_REINICIO_SUT"

# El comando puede tener que compilar/levantar el SUT: se le da margen amplio.
TIMEOUT_COMANDO_SEGUNDOS = 120
TIMEOUT_READINESS_SEGUNDOS = 120
INTERVALO_READINESS_SEGUNDOS = 2


def comando_reinicio() -> str:
    """Devuelve el comando de reinicio, o salta el test con motivo explícito.

    Se expone aparte de :func:`reiniciar_sut` para los tests que necesitan
    verificar la precondición **antes** de construir un "Dado" caro (depósitos
    on-chain, retiros broadcasteados).
    """
    comando = os.environ.get(VAR_CMD_REINICIO, "").strip()
    if not comando:
        pytest.skip(
            f"{VAR_CMD_REINICIO} no configurada: el reinicio del SUT lo provee el "
            "evaluador (el contrato de la épica 09 no expone ninguna operación de "
            "reinicio). Sin ese comando, el AT de persistencia (INV-8) no es "
            "verificable y la corrida H8 no es válida (README de la suite)"
        )
    return comando


def sut_responde(api) -> bool:
    """True si el SUT atiende el endpoint público de readiness (``GET /market/ticker``)."""
    try:
        return api.get("/market/ticker").status_code == 200
    except Exception:
        return False


def reiniciar_sut(api) -> None:
    """Ejecuta el reinicio abrupto del SUT y espera a que vuelva a responder."""
    comando = comando_reinicio()
    resultado = subprocess.run(
        comando,
        shell=True,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_COMANDO_SEGUNDOS,
    )
    assert resultado.returncode == 0, (
        f"el comando de reinicio del SUT falló ({resultado.returncode}): "
        f"{resultado.stderr[:300]}"
    )
    esperar_hasta(
        lambda: sut_responde(api),
        timeout=TIMEOUT_READINESS_SEGUNDOS,
        intervalo=INTERVALO_READINESS_SEGUNDOS,
        mensaje="el SUT no volvió a responder tras el reinicio",
    )


def relogin(usuario) -> None:
    """Renueva la sesión tras un reinicio.

    La spec no exige que los tokens sobrevivan al reinicio (sí los balances, las
    órdenes y el estado on-chain: INV-8), así que todo test que siga operando
    autenticado tras el reinicio vuelve a loguearse.
    """
    usuario.token = login(usuario.api.sin_token(), usuario.email, usuario.password)
    usuario.api = usuario.api.con_token(usuario.token)
