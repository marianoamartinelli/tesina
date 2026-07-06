"""Espera/polling con timeout para condiciones asíncronas del SUT.

Necesario para flujos que no son inmediatos black-box: acreditación de depósitos
tras N confirmaciones (épica 07), transiciones de retiros (épica 08), efectos
visibles por REST tras eventos WS, etc.
"""

import os
import time

TIMEOUT_DEFECTO_SEGUNDOS = float(os.environ.get("SUITE_POLL_TIMEOUT_SEGUNDOS", "30"))
INTERVALO_DEFECTO_SEGUNDOS = float(os.environ.get("SUITE_POLL_INTERVALO_SEGUNDOS", "0.5"))


def esperar_hasta(
    condicion,
    timeout: float | None = None,
    intervalo: float | None = None,
    mensaje: str = "la condición no se cumplió",
):
    """Re-evalúa `condicion()` hasta que devuelva un valor truthy y lo retorna.

    - `condicion`: callable sin argumentos. Puede devolver el valor útil (p. ej.
      el recurso ya en el estado esperado) para evitar una re-consulta.
    - `timeout`/`intervalo`: en segundos; defaults configurables por env vars
      SUITE_POLL_TIMEOUT_SEGUNDOS (30) y SUITE_POLL_INTERVALO_SEGUNDOS (0.5).
    - Lanza TimeoutError con `mensaje` si se agota el tiempo.

    Ejemplo (depósito acreditado tras minar 12 bloques):
        deposito = esperar_hasta(
            lambda: _deposito_si_esta(u.api, deposit_id, "ACREDITADO"),
            mensaje=f"el depósito {deposit_id} no llegó a ACREDITADO",
        )
    """
    limite = timeout if timeout is not None else TIMEOUT_DEFECTO_SEGUNDOS
    pausa = intervalo if intervalo is not None else INTERVALO_DEFECTO_SEGUNDOS
    fin = time.monotonic() + limite
    ultimo_error: Exception | None = None
    while True:
        try:
            valor = condicion()
            if valor:
                return valor
        except AssertionError as exc:
            # permite usar helpers con asserts dentro de la condición
            ultimo_error = exc
        if time.monotonic() >= fin:
            detalle = f" (último error: {ultimo_error})" if ultimo_error else ""
            raise TimeoutError(f"{mensaje} tras {limite}s{detalle}")
        time.sleep(pausa)
