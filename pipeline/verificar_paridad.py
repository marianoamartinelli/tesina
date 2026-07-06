#!/usr/bin/env python3
"""Verificación mecánica de paridad entre las 4 celdas del 2×2 (ADR-005).

Falla (exit code != 0) si se rompe cualquiera de estas garantías:

1. Las 4 configs oficiales tienen exactamente los campos esperados y sólo
   difieren en los factores (`celda`, `harness`, `modelo`, `rag`).
2. Los pares (harness, modelo) son exactamente los pinneados por ADR-005 y
   cada harness tiene una celda con RAG y una sin RAG.
3. Las 4 configs resuelven al MISMO etapas.yaml, y los prompts que ese archivo
   referencia existen y no están vacíos (⇒ prompts idénticos entre celdas).
4. Los parámetros BM25 de etapas.yaml coinciden con las constantes del índice
   (comun/rag/indice.py), que no se ajustan por celda.
5. Los SHA-256 de corpus/documentos/* coinciden byte a byte con el manifest
   congelado de H3 (corpus/manifest.md), sin archivos de más ni de menos.

Correr antes de cada corrida (protocolo §2 / ADR-004):
    .venv/bin/python pipeline/verificar_paridad.py
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import yaml

RAIZ_PIPELINE = Path(__file__).resolve().parent
RAIZ_REPO = RAIZ_PIPELINE.parent
sys.path.insert(0, str(RAIZ_PIPELINE))

from comun.rag import indice as modulo_indice  # noqa: E402

CELDAS_OFICIALES = ["a-sin-rag", "a-con-rag", "b-sin-rag", "b-con-rag"]
CAMPOS_FACTORES = {"celda", "harness", "modelo", "rag"}
CAMPOS_CONFIG = CAMPOS_FACTORES | {"etapas"}
# Pareo pinneado por ADR-005, Decisión 3. Cambiarlo exige ADR de reemplazo.
PARES_ADR005 = {"a": "claude-opus-4-8", "b": "gpt-5.5"}

_fallas: list[str] = []


def chequear(condicion: bool, mensaje: str) -> None:
    marca = "OK " if condicion else "FALLA"
    print(f"[{marca}] {mensaje}")
    if not condicion:
        _fallas.append(mensaje)


def cargar_configs() -> dict[str, dict]:
    configs = {}
    for celda in CELDAS_OFICIALES:
        ruta = RAIZ_PIPELINE / "config" / f"{celda}.yaml"
        chequear(ruta.is_file(), f"existe config/{celda}.yaml")
        if ruta.is_file():
            configs[celda] = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    return configs


def verificar_configs(configs: dict[str, dict]) -> None:
    for celda, config in configs.items():
        chequear(set(config) == CAMPOS_CONFIG,
                 f"{celda}: campos exactamente {sorted(CAMPOS_CONFIG)}")
        chequear(config.get("celda") == celda,
                 f"{celda}: el campo 'celda' coincide con el nombre del archivo")
        chequear(isinstance(config.get("rag"), bool), f"{celda}: 'rag' es booleano")

    # Fuera de los factores, todo lo demás debe ser idéntico entre las 4.
    compartidos = [{c: v for c, v in config.items() if c not in CAMPOS_FACTORES}
                   for config in configs.values()]
    chequear(all(c == compartidos[0] for c in compartidos),
             "las 4 configs sólo difieren en celda/harness/modelo/rag")

    pares = {(config["harness"], config["modelo"]) for config in configs.values()}
    chequear(pares == set(PARES_ADR005.items()),
             f"pares (harness, modelo) exactamente los de ADR-005: "
             f"{sorted(PARES_ADR005.items())} (hay {sorted(pares)})")
    for harness in PARES_ADR005:
        rags = sorted(config["rag"] for config in configs.values()
                      if config["harness"] == harness)
        chequear(rags == [False, True],
                 f"harness {harness}: una celda con RAG y una sin RAG")


def verificar_etapas_y_prompts(configs: dict[str, dict]) -> dict:
    rutas = {(RAIZ_PIPELINE / "config" / config["etapas"]).resolve()
             for config in configs.values()}
    chequear(len(rutas) == 1,
             "las 4 configs referencian el MISMO etapas.yaml")
    ruta_etapas = next(iter(rutas))
    chequear(ruta_etapas.is_file(), f"etapas.yaml existe ({ruta_etapas})")
    etapas = yaml.safe_load(ruta_etapas.read_text(encoding="utf-8"))
    raiz = ruta_etapas.parent.parent

    rutas_prompts = [raiz / etapas["prompt_sistema"]] + \
                    [raiz / e["prompt"] for e in etapas["etapas"]]
    for ruta in rutas_prompts:
        existe = ruta.is_file() and ruta.stat().st_size > 0
        chequear(existe, f"prompt existe y no está vacío: {ruta.relative_to(RAIZ_REPO)}")
    return etapas


def verificar_bm25(etapas: dict) -> None:
    bm25 = etapas.get("rag", {}).get("bm25", {})
    k = etapas.get("rag", {}).get("k")
    chequear(bm25.get("k1") == modulo_indice.K1 and bm25.get("b") == modulo_indice.B,
             f"parámetros BM25 de etapas.yaml == constantes del índice "
             f"(k1={modulo_indice.K1}, b={modulo_indice.B})")
    chequear(k == modulo_indice.K_DEFAULT,
             f"k de etapas.yaml == K_DEFAULT del índice ({modulo_indice.K_DEFAULT})")


def verificar_corpus() -> None:
    manifest = (RAIZ_REPO / "corpus" / "manifest.md").read_text(encoding="utf-8")
    # Filas de la tabla del manifest: | n | `documentos/<archivo>` | ... | `<sha256>` |
    esperados = dict(re.findall(
        r"\|\s*\d+\s*\|\s*`documentos/([^`]+)`.*?`([0-9a-f]{64})`", manifest))
    chequear(len(esperados) == 9, f"el manifest lista 9 documentos (hay {len(esperados)})")

    dir_corpus = RAIZ_REPO / "corpus" / "documentos"
    reales = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(dir_corpus.iterdir()) if p.is_file()}

    chequear(set(reales) == set(esperados),
             "corpus/documentos/ contiene exactamente los archivos del manifest"
             + ("" if set(reales) == set(esperados)
                else f" (sobran {sorted(set(reales) - set(esperados))},"
                     f" faltan {sorted(set(esperados) - set(reales))})"))
    for nombre in sorted(set(reales) & set(esperados)):
        chequear(reales[nombre] == esperados[nombre],
                 f"SHA-256 de {nombre} coincide con el manifest")


def main() -> int:
    print("Verificación de paridad del pipeline (ADR-005)\n")
    configs = cargar_configs()
    if len(configs) == len(CELDAS_OFICIALES):
        verificar_configs(configs)
        etapas = verificar_etapas_y_prompts(configs)
        verificar_bm25(etapas)
    verificar_corpus()

    print()
    if _fallas:
        print(f"PARIDAD ROTA: {len(_fallas)} chequeo(s) fallaron:")
        for f in _fallas:
            print(f"  - {f}")
        return 1
    print("Paridad verificada: las 4 celdas sólo difieren en los factores del 2×2.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
