"""Reporte de resultados por AT-id (lógica pura; el wiring pytest está en conftest.py).

Modelo:
- El catálogo (catalogo-at.csv) define el universo de ATs. La suite reporta sobre
  los de tipo ``backend`` (épicas 01–09); los de 10–11 se evalúan por rúbricas.
- Cada test declara qué ATs verifica con ``@pytest.mark.at("AT-..-..-..", ...)``.
- ``no-automatizables.yaml`` declara los ATs de 01–09 que NO se pueden verificar
  black-box, con su motivo; no deben tener tests.

Resultado por AT (columna ``resultado`` de resultados-at.csv):
- ``pasa``            todos los tests que lo declaran pasaron (≥ 1 test).
- ``falla``           al menos un test que lo declara falló (o error de setup).
- ``skip``            tiene tests pero todos fueron saltados en esta corrida.
- ``no_automatizado`` declarado en no-automatizables.yaml (sin tests).
- ``sin_test``        AT backend sin test y no declarado: hueco de cobertura de
                      la suite (no dice nada del SUT; debe tender a cero).
"""

import csv
import re
from pathlib import Path

import yaml

DIR_SUITE = Path(__file__).resolve().parents[1]
RUTA_CATALOGO = DIR_SUITE / "catalogo-at.csv"
RUTA_NO_AUTOMATIZABLES = DIR_SUITE / "no-automatizables.yaml"
RUTA_RESULTADOS = DIR_SUITE / "resultados-at.csv"

RE_AT_ID = re.compile(r"^AT-\d{2}-\d{2}-\d{2}[a-z]?$")

COLUMNAS_RESULTADOS = ["at_id", "resultado", "test", "duracion_segundos", "detalle"]


def cargar_catalogo(ruta: Path = RUTA_CATALOGO) -> dict[str, dict]:
    """Catálogo completo como dict at_id -> fila. Regenerable con catalogo.py."""
    if not ruta.exists():
        raise FileNotFoundError(
            f"No existe {ruta}. Generarlo con: python {DIR_SUITE / 'catalogo.py'}"
        )
    with ruta.open(encoding="utf-8") as f:
        return {fila["at_id"]: fila for fila in csv.DictReader(f)}


def cargar_no_automatizables(ruta: Path = RUTA_NO_AUTOMATIZABLES) -> dict[str, str]:
    """Dict at_id -> motivo. Valida formato y unicidad."""
    if not ruta.exists():
        return {}
    entradas = yaml.safe_load(ruta.read_text(encoding="utf-8")) or []
    if not isinstance(entradas, list):
        raise ValueError(f"{ruta}: se esperaba una lista de entradas")
    resultado: dict[str, str] = {}
    for entrada in entradas:
        if not isinstance(entrada, dict) or "at_id" not in entrada or "motivo" not in entrada:
            raise ValueError(f"{ruta}: entrada inválida (requiere at_id y motivo): {entrada!r}")
        at_id = entrada["at_id"]
        if not RE_AT_ID.fullmatch(str(at_id)):
            raise ValueError(f"{ruta}: at_id con formato inválido: {at_id!r}")
        if at_id in resultado:
            raise ValueError(f"{ruta}: at_id duplicado: {at_id}")
        resultado[at_id] = str(entrada["motivo"]).strip()
    return resultado


def validar_ats_declarados(
    ats_por_test: dict[str, list[str]],
    catalogo: dict[str, dict],
    no_automatizables: dict[str, str],
) -> list[str]:
    """Valida los AT-ids que los tests declaran vía marker. Devuelve la lista de
    problemas (vacía si todo está bien). Reglas:

    - todo AT declarado debe tener formato válido y existir en el catálogo;
    - debe ser de tipo backend (los de 10–11 no se testean acá);
    - no puede estar a la vez declarado en no-automatizables.yaml.
    """
    problemas = []
    for test, ats in ats_por_test.items():
        if not ats:
            problemas.append(f"{test}: marker 'at' sin AT-ids")
        for at_id in ats:
            if not RE_AT_ID.fullmatch(at_id):
                problemas.append(f"{test}: AT-id con formato inválido: {at_id!r}")
            elif at_id not in catalogo:
                problemas.append(f"{test}: AT-id inexistente en el catálogo: {at_id}")
            elif catalogo[at_id]["tipo"] != "backend":
                problemas.append(
                    f"{test}: {at_id} es de tipo {catalogo[at_id]['tipo']} "
                    "(la suite sólo cubre backend, épicas 01–09)"
                )
            if at_id in no_automatizables:
                problemas.append(
                    f"{test}: {at_id} está declarado en no-automatizables.yaml "
                    "(quitar la entrada o el test)"
                )
    return problemas


def agregar_resultados(
    catalogo: dict[str, dict],
    no_automatizables: dict[str, str],
    resultados_tests: dict[str, dict],
    ats_por_test: dict[str, list[str]],
) -> list[dict]:
    """Agrega los resultados por test a resultado por AT.

    - `resultados_tests`: nodeid -> {"outcome": "passed"|"failed"|"skipped",
      "duracion": float}.
    - `ats_por_test`: nodeid -> [at_id, ...] (del marker).

    Regla de agregación por AT (sobre los tests que lo declaran):
    algún failed ⇒ falla; si no, algún passed ⇒ pasa; si no ⇒ skip.
    """
    tests_por_at: dict[str, list[str]] = {}
    for test, ats in ats_por_test.items():
        for at_id in ats:
            tests_por_at.setdefault(at_id, []).append(test)

    filas = []
    for at_id, fila_catalogo in sorted(catalogo.items()):
        if fila_catalogo["tipo"] != "backend":
            continue  # épicas 10–11: rúbricas, fuera de esta suite

        tests = sorted(tests_por_at.get(at_id, []))
        if tests:
            salidas = [resultados_tests[t]["outcome"] for t in tests if t in resultados_tests]
            duracion = sum(resultados_tests[t]["duracion"] for t in tests if t in resultados_tests)
            if not salidas:
                resultado, detalle = "skip", "tests declarados pero no ejecutados"
            elif "failed" in salidas:
                resultado, detalle = "falla", ""
            elif "passed" in salidas:
                resultado, detalle = "pasa", ""
            else:
                resultado, detalle = "skip", ""
            filas.append(
                {
                    "at_id": at_id,
                    "resultado": resultado,
                    "test": ";".join(tests),
                    "duracion_segundos": f"{duracion:.3f}",
                    "detalle": detalle,
                }
            )
        elif at_id in no_automatizables:
            filas.append(
                {
                    "at_id": at_id,
                    "resultado": "no_automatizado",
                    "test": "",
                    "duracion_segundos": "",
                    "detalle": no_automatizables[at_id],
                }
            )
        else:
            filas.append(
                {
                    "at_id": at_id,
                    "resultado": "sin_test",
                    "test": "",
                    "duracion_segundos": "",
                    "detalle": "AT backend sin test ni declaración de no automatizable",
                }
            )
    return filas


def escribir_resultados(filas: list[dict], destino: Path = RUTA_RESULTADOS) -> Path:
    with destino.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS_RESULTADOS)
        w.writeheader()
        w.writerows(filas)
    return destino


def resumen(filas: list[dict]) -> dict[str, int]:
    conteo: dict[str, int] = {}
    for fila in filas:
        conteo[fila["resultado"]] = conteo.get(fila["resultado"], 0) + 1
    return conteo
