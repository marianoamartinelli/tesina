#!/usr/bin/env python3
"""Catálogo de criterios de aceptación (AT) de la spec.

Recorre `spec/` y extrae **todos** los AT-id definidos en los encabezados de
escenario de las HU (`### Escenario N: <título> [AT-EE-SS-NN[a-z]?]`) y genera
`catalogo-at.csv` con una fila por AT.

Columnas del CSV:
    at_id             ID estable del criterio (p. ej. AT-03-02-01, AT-01-01-04a)
    epica             número de épica ("01".."11")
    hu                ID de la HU que lo define (p. ej. HU-03-02)
    archivo           ruta del archivo de spec relativa a la raíz del repo
    titulo_escenario  primera línea del escenario (texto del encabezado, sin el [AT-...])
    tipo              backend (épicas 01–09) | web (10) | mobile (11)

Uso:
    python catalogo.py            # regenera catalogo-at.csv junto a este script
    python catalogo.py --check    # no escribe; sólo valida y reporta conteos

El script es determinista: mismas fuentes ⇒ mismo CSV (ordenado por at_id).
La spec está congelada (spec-v1.1, re-freeze por ADR-006): el total esperado es 693 ATs.
"""

import argparse
import csv
import re
import sys
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parents[2]
DIR_SPEC = RAIZ_REPO / "spec"
CSV_SALIDA = Path(__file__).resolve().parent / "catalogo-at.csv"

TOTAL_ESPERADO = 693  # spec-v1.1 congelada (re-freeze por ADR-006); si cambia, es un error a investigar

# Encabezado de escenario con su AT-id: '### Escenario 1: Registro de cuenta [AT-09-01-01]'
RE_ESCENARIO = re.compile(
    r"^#{2,4}\s*(?P<titulo>Escenario[^\[\]]*?)\s*\[(?P<at>AT-\d{2}-\d{2}-\d{2}[a-z]?)\]\s*$"
)
RE_HU_ARCHIVO = re.compile(r"^(HU-(\d{2})-(\d{2}))-")


def tipo_de_epica(epica: str) -> str:
    if epica == "10":
        return "web"
    if epica == "11":
        return "mobile"
    return "backend"


def parsear_spec(dir_spec: Path = DIR_SPEC) -> list[dict]:
    """Devuelve la lista de filas del catálogo (una por AT), ordenada por at_id."""
    filas = []
    vistos: dict[str, str] = {}  # at_id -> archivo (detección de duplicados)
    errores = []

    for archivo in sorted(dir_spec.glob("[0-9][0-9]-*/HU-*.md")):
        m = RE_HU_ARCHIVO.match(archivo.name)
        if not m:
            errores.append(f"nombre de archivo no matchea HU-EE-SS-*: {archivo}")
            continue
        hu_id, epica_hu, _ = m.group(1), m.group(2), m.group(3)

        for linea in archivo.read_text(encoding="utf-8").splitlines():
            m_esc = RE_ESCENARIO.match(linea)
            if not m_esc:
                continue
            at_id = m_esc.group("at")
            titulo = m_esc.group("titulo").strip()
            epica_at = at_id[3:5]
            if epica_at != epica_hu or at_id[6:8] != hu_id[6:8]:
                # Un AT definido en el archivo de otra HU sería un error de la spec.
                errores.append(f"{archivo.name}: define {at_id} que no corresponde a {hu_id}")
                continue
            if at_id in vistos:
                errores.append(
                    f"AT duplicado: {at_id} en {vistos[at_id]} y {archivo.name}"
                )
                continue
            vistos[at_id] = archivo.name
            filas.append(
                {
                    "at_id": at_id,
                    "epica": epica_at,
                    "hu": hu_id,
                    "archivo": str(archivo.relative_to(RAIZ_REPO)),
                    "titulo_escenario": titulo,
                    "tipo": tipo_de_epica(epica_at),
                }
            )

    if errores:
        for e in errores:
            print(f"ERROR: {e}", file=sys.stderr)
        raise SystemExit(1)

    filas.sort(key=lambda f: f["at_id"])
    return filas


def escribir_csv(filas: list[dict], destino: Path = CSV_SALIDA) -> None:
    columnas = ["at_id", "epica", "hu", "archivo", "titulo_escenario", "tipo"]
    with destino.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columnas)
        w.writeheader()
        w.writerows(filas)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="no escribe el CSV; sólo valida y reporta"
    )
    args = parser.parse_args()

    filas = parsear_spec()

    por_tipo: dict[str, int] = {}
    por_epica: dict[str, int] = {}
    for fila in filas:
        por_tipo[fila["tipo"]] = por_tipo.get(fila["tipo"], 0) + 1
        por_epica[fila["epica"]] = por_epica.get(fila["epica"], 0) + 1

    print(f"ATs encontrados: {len(filas)} (esperados: {TOTAL_ESPERADO})")
    print(f"Por tipo: {dict(sorted(por_tipo.items()))}")
    print(f"Por épica: {dict(sorted(por_epica.items()))}")

    if len(filas) != TOTAL_ESPERADO:
        print(
            f"ERROR: el total ({len(filas)}) difiere del esperado ({TOTAL_ESPERADO}). "
            "La spec está congelada: investigar antes de regenerar.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    if not args.check:
        escribir_csv(filas)
        print(f"Escrito: {CSV_SALIDA}")


if __name__ == "__main__":
    main()
