"""Configuración pytest de la suite AT: fixtures black-box + reporte por AT-id.

Fixtures principales (ver HELPERS.md):
- ``api``       cliente REST sin token (endpoints públicos / registro).
- ``usuario``   usuario fresco registrado y logueado (``usuario.api`` autenticado).
- ``usuario_b`` segundo usuario fresco (tests de aislamiento entre cuentas).
- ``ws``        conexión WebSocket nueva contra EXCHANGE_WS_URL.
- ``rpc``       cliente JSON-RPC contra el anvil del entorno (control on-chain).

Plugin de reporte:
- cada test declara sus ATs con ``@pytest.mark.at("AT-EE-SS-NN", ...)``;
- al terminar la corrida se vuelca ``resultados-at.csv`` con una fila por AT
  backend del catálogo (pasa/falla/skip/no_automatizado/sin_test) y el resumen
  en la terminal lista aparte los no automatizables.
"""

import os
from pathlib import Path

import pytest

from helpers import reporte
from helpers.api import ClienteApi, url_api_configurada
from helpers.cuentas import crear_usuario
from helpers.onchain import ClienteRpc
from helpers.ws import ConexionWs, url_ws_configurada

# --------------------------------------------------------------------------------
# Fixtures black-box
# --------------------------------------------------------------------------------


@pytest.fixture(scope="session")
def api() -> ClienteApi:
    """Cliente REST sin token contra EXCHANGE_API_URL. Salta si no hay SUT."""
    if not url_api_configurada():
        pytest.skip("EXCHANGE_API_URL no configurada: no hay SUT contra el cual correr")
    cliente = ClienteApi()
    yield cliente
    cliente.cerrar()


@pytest.fixture
def usuario(api):
    """Usuario fresco (registro + login). Usar `usuario.api` para llamadas autenticadas."""
    return crear_usuario(api)


@pytest.fixture
def usuario_b(api):
    """Segundo usuario fresco, para tests de aislamiento por cuenta (HU-09-02)."""
    return crear_usuario(api, prefijo="at-b")


@pytest.fixture
def ws():
    """Conexión WebSocket nueva contra EXCHANGE_WS_URL. Salta si no está configurada."""
    if not url_ws_configurada():
        pytest.skip("EXCHANGE_WS_URL no configurada: no hay SUT WebSocket")
    conexion = ConexionWs()
    yield conexion
    conexion.cerrar()


@pytest.fixture(scope="session")
def rpc() -> ClienteRpc:
    """Cliente JSON-RPC del entorno on-chain (anvil chainId 11155111).

    Salta si el nodo no responde o no es la red esperada.
    """
    cliente = ClienteRpc()
    if not cliente.disponible():
        pytest.skip(
            f"nodo RPC no disponible o chainId ≠ 11155111 en {cliente.url} "
            "(levantar evaluacion/suite-at/entorno/)"
        )
    return cliente


# --------------------------------------------------------------------------------
# Plugin de reporte por AT-id
# --------------------------------------------------------------------------------


def _ats_del_item(item) -> list[str]:
    """AT-ids declarados por un test vía @pytest.mark.at (acumula múltiples markers)."""
    ats: list[str] = []
    for marker in item.iter_markers(name="at"):
        ats.extend(str(a) for a in marker.args)
    return ats


def pytest_collection_modifyitems(config, items):
    """Valida los AT-ids declarados contra el catálogo y no-automatizables.yaml."""
    ats_por_test = {}
    for item in items:
        ats = _ats_del_item(item)
        if ats:
            ats_por_test[item.nodeid] = ats

    config._ats_por_test = ats_por_test
    config._resultados_tests = {}

    if not ats_por_test:
        return

    catalogo = reporte.cargar_catalogo()
    no_autom = reporte.cargar_no_automatizables()
    problemas = reporte.validar_ats_declarados(ats_por_test, catalogo, no_autom)
    if problemas:
        raise pytest.UsageError(
            "AT-ids inválidos en markers @pytest.mark.at:\n  - " + "\n  - ".join(problemas)
        )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Acumula outcome y duración por test para el reporte por AT."""
    salida = yield
    report = salida.get_result()
    registro = item.config._resultados_tests.setdefault(
        item.nodeid, {"outcome": "passed", "duracion": 0.0}
    )
    registro["duracion"] += report.duration
    if report.when == "call":
        if report.failed:
            registro["outcome"] = "failed"
        elif report.skipped:
            registro["outcome"] = "skipped"
        elif registro["outcome"] != "failed":
            registro["outcome"] = "passed"
    elif report.when == "setup":
        if report.failed:
            registro["outcome"] = "failed"   # error de fixture cuenta como falla
        elif report.skipped:
            registro["outcome"] = "skipped"  # skip por falta de SUT/entorno
    elif report.when == "teardown" and report.failed:
        registro["outcome"] = "failed"


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Escribe resultados-at.csv y resume por categoría (no automatizables aparte)."""
    ats_por_test = getattr(config, "_ats_por_test", {})
    if not ats_por_test:
        return  # corrida sin tests de AT (p. ej. sólo smoke): no se reporta
    if exitstatus == pytest.ExitCode.USAGE_ERROR or exitstatus == pytest.ExitCode.INTERRUPTED:
        return  # corrida abortada (p. ej. marker inválido): no se reporta

    catalogo = reporte.cargar_catalogo()
    no_autom = reporte.cargar_no_automatizables()
    resultados_tests = {
        nodeid: datos
        for nodeid, datos in config._resultados_tests.items()
        if nodeid in ats_por_test
    }
    filas = reporte.agregar_resultados(catalogo, no_autom, resultados_tests, ats_por_test)

    destino = os.environ.get("SUITE_RESULTADOS_AT")
    ruta = reporte.escribir_resultados(
        filas, Path(destino) if destino else reporte.RUTA_RESULTADOS
    )

    conteo = reporte.resumen(filas)
    total = sum(conteo.values())
    tr = terminalreporter
    tr.section("Reporte por AT-id (backend, épicas 01–09)")
    tr.write_line(f"Archivo: {ruta}")
    tr.write_line(
        f"Total ATs backend: {total} | "
        + " | ".join(f"{k}: {v}" for k, v in sorted(conteo.items()))
    )
    no_automatizados = [f for f in filas if f["resultado"] == "no_automatizado"]
    if no_automatizados:
        tr.write_line("")
        tr.write_line("ATs declarados no automatizables (se evalúan por otra vía):")
        for fila in no_automatizados:
            tr.write_line(f"  {fila['at_id']}: {fila['detalle']}")
