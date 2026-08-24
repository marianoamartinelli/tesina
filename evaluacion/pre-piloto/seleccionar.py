#!/usr/bin/env python3
"""Traduce el alcance de la pre-piloto (ADR-018) a una selección de pytest.

La suite black-box no se toca: se la invoca con los **nodeids** de los tests cuyos
markers `@pytest.mark.at` caen dentro del alcance. Los demás ni se recolectan, así
que el reporte por AT-id los marca `sin_test` en vez de acumular fallas por
fuera-de-alcance.

Salidas (a `evaluacion/pre-piloto/`):
    nodeids.txt        un nodeid por línea, para `pytest $(cat nodeids.txt)`
    ats-white-box.txt  los ATs del alcance declarados no automatizables, que van al
                       agente evaluador white-box (ADR-007)

Uso:
    ../../.venv/bin/python evaluacion/pre-piloto/seleccionar.py [--check]

`--check` no escribe: sólo imprime el resumen. El script es determinista.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import pytest
import yaml

AQUI = Path(__file__).resolve().parent
SUITE = AQUI.parent / "suite-at"
ALCANCE = AQUI / "alcance.yaml"


def ats_del_alcance() -> tuple[set[str], dict]:
    """AT-ids backend del alcance, expandidos desde el catálogo por HU."""
    alcance = yaml.safe_load(ALCANCE.read_text(encoding="utf-8"))
    hus = set(alcance["hus_backend"])
    ats = set()
    with (SUITE / "catalogo-at.csv").open(encoding="utf-8") as archivo:
        for fila in csv.DictReader(archivo):
            if fila["hu"] in hus:
                ats.add(fila["at_id"])
    if not ats:
        raise SystemExit("el alcance no expandió a ningún AT: revisar alcance.yaml")
    return ats, alcance


class _Recolector:
    """Plugin que captura nodeid -> AT-ids durante la recolección."""

    def __init__(self) -> None:
        self.por_nodeid: dict[str, list[str]] = {}

    def pytest_collection_modifyitems(self, config, items):
        for item in items:
            ats = [str(a) for m in item.iter_markers(name="at") for a in m.args]
            if ats:
                self.por_nodeid[item.nodeid] = ats


def recolectar() -> dict[str, list[str]]:
    """Corre `pytest --collect-only` sobre la suite y devuelve el mapa nodeid→ATs."""
    plugin = _Recolector()
    codigo = pytest.main(
        ["--collect-only", "-q", "--no-header", "--no-summary", "-p", "no:cacheprovider", "tests"],
        plugins=[plugin],
    )
    if codigo not in (0, pytest.ExitCode.NO_TESTS_COLLECTED):
        raise SystemExit(f"la recolección de pytest falló con código {codigo}")
    return plugin.por_nodeid


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="no escribe archivos; sólo imprime el resumen")
    args = parser.parse_args()

    ats, alcance = ats_del_alcance()
    no_autom = {
        entrada["at_id"]
        for entrada in yaml.safe_load(
            (SUITE / "no-automatizables.yaml").read_text(encoding="utf-8"))
    }

    import os
    os.chdir(SUITE)  # la suite se recolecta desde su propio directorio (pytest.ini)
    por_nodeid = recolectar()

    nodeids = sorted(n for n, sus in por_nodeid.items() if ats & set(sus))
    cubiertos = {a for n in nodeids for a in por_nodeid[n]} & ats
    white_box = sorted(ats & no_autom)
    sin_cubrir = sorted(ats - cubiertos - set(white_box))

    print(f"alcance:        {len(alcance['hus_backend'])} HU backend → {len(ats)} ATs")
    print(f"black-box:      {len(cubiertos)} ATs con test, en {len(nodeids)} funciones")
    print(f"white-box:      {len(white_box)} ATs declarados no automatizables")
    print(f"sin cubrir:     {len(sin_cubrir)}"
          + (f" → {', '.join(sin_cubrir)}" if sin_cubrir else ""))

    if args.check:
        return 1 if sin_cubrir else 0

    (AQUI / "nodeids.txt").write_text("\n".join(nodeids) + "\n", encoding="utf-8")
    (AQUI / "ats-white-box.txt").write_text("\n".join(white_box) + "\n", encoding="utf-8")
    print(f"\nescrito: {AQUI / 'nodeids.txt'} y {AQUI / 'ats-white-box.txt'}")
    return 1 if sin_cubrir else 0


if __name__ == "__main__":
    sys.exit(main())
