#!/usr/bin/env python3
"""Validador mecánico de la salida del agente evaluador white-box (ADR-007).

Valida un YAML de pasada (``runs/<id>/no-automatizables/pasada-<n>.yaml``) —o
``veredicto-final.yaml``, que usa el mismo esquema de items— contra el contrato
fijado por ``plantilla-resultados.yaml`` (la plantilla es la fuente del
contrato; este script sólo lo mecaniza):

1. Exactamente 66 items cuyos ``at_id`` coinciden uno a uno **y en orden** con
   los de ``plantilla-resultados.yaml`` (orden canónico ascendente de la
   rúbrica). ``suite-at/no-automatizables.yaml`` se usa sólo como verificación
   cruzada del **conjunto** de IDs (está agrupado por motivo, no ordenado).
2. ``veredicto`` ∈ {PASA, FALLA, NO_EVALUABLE}.
3. ``causa`` presente (no nula) **si y sólo si** veredicto = NO_EVALUABLE, y
   ∈ {SUT_NO_ARRANCA, FUNCION_NO_LOCALIZABLE, PRECONDICION_IMPOSIBLE,
   HERRAMIENTA_FALTANTE, OTRO}.
4. ``evidencia``: lista NO vacía de objetos con ``tipo`` ∈ {archivo, comando,
   corpus}, ``ref`` string no vacío y ``detalle`` presente (un veredicto sin
   evidencia es inválido, briefing §4).
5. ``justificacion`` no vacía y ``duracion_min`` numérico, 0 ≤ x ≤ 15
   (tope del briefing §5).
6. Sin campos fuera de la plantilla (ni en items, ni en evidencia, ni en el
   nivel superior) y ``metadatos`` completos: ``celda`` = "celda-en-evaluacion"
   (anonimizada), ``fecha`` AAAA-MM-DD, ``pasada`` ∈ {1, 2},
   ``modelo_evaluador``, ``briefing_version`` y ``rubrica_version`` no vacíos.

Uso (lo ejecuta el humano sobre cada pasada ANTES del arbitraje):

    .venv/bin/python evaluacion/agente-evaluador/validar-resultados.py \
        runs/<id>/no-automatizables/pasada-1.yaml
    .venv/bin/python evaluacion/agente-evaluador/validar-resultados.py \
        --final runs/<id>/no-automatizables/veredicto-final.yaml

``--final`` relaja únicamente el chequeo de ``metadatos.pasada`` (el veredicto
final arbitrado no pertenece a una pasada; si el campo está, igual debe ser 1 o 2).

Exit code 0 sólo si el archivo cumple todo el contrato; ≠ 0 ante cualquier
violación, listando los at_id afectados.
"""

import argparse
import re
import sys
from pathlib import Path

import yaml

DIR_SCRIPT = Path(__file__).resolve().parent
PLANTILLA = DIR_SCRIPT / "plantilla-resultados.yaml"
NO_AUTOMATIZABLES = DIR_SCRIPT.parent / "suite-at" / "no-automatizables.yaml"

VEREDICTOS = {"PASA", "FALLA", "NO_EVALUABLE"}
CAUSAS = {
    "SUT_NO_ARRANCA",
    "FUNCION_NO_LOCALIZABLE",
    "PRECONDICION_IMPOSIBLE",
    "HERRAMIENTA_FALTANTE",
    "OTRO",
}
TIPOS_EVIDENCIA = {"archivo", "comando", "corpus"}

CAMPOS_ITEM = {"at_id", "veredicto", "causa", "evidencia", "justificacion", "duracion_min"}
CAMPOS_EVIDENCIA = {"tipo", "ref", "detalle"}
CAMPOS_TOP = {"metadatos", "resultados"}
CAMPOS_METADATOS = {"celda", "fecha", "pasada", "modelo_evaluador", "briefing_version", "rubrica_version"}

RE_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _es_string_no_vacio(valor) -> bool:
    return isinstance(valor, str) and valor.strip() != ""


def _es_numero(valor) -> bool:
    # bool es subclase de int en Python: excluirlo explícitamente.
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


def cargar_orden_canonico() -> list[str]:
    """at_id de la plantilla, en su orden (el orden canónico de la rúbrica)."""
    plantilla = yaml.safe_load(PLANTILLA.read_text(encoding="utf-8"))
    return [item["at_id"] for item in plantilla["resultados"]]


def verificar_cruzado_con_no_automatizables(orden_canonico: list[str]) -> list[str]:
    """Verificación cruzada del CONJUNTO (nunca del orden) contra no-automatizables.yaml."""
    declarados = yaml.safe_load(NO_AUTOMATIZABLES.read_text(encoding="utf-8"))
    ids_declarados = {item["at_id"] for item in declarados}
    errores = []
    faltan = ids_declarados - set(orden_canonico)
    sobran = set(orden_canonico) - ids_declarados
    if faltan:
        errores.append(
            "plantilla-resultados.yaml no cubre ATs declarados en "
            f"no-automatizables.yaml: {sorted(faltan)}"
        )
    if sobran:
        errores.append(
            "plantilla-resultados.yaml incluye ATs no declarados en "
            f"no-automatizables.yaml: {sorted(sobran)}"
        )
    return errores


def validar_metadatos(datos: dict, final: bool) -> list[str]:
    errores = []
    metadatos = datos.get("metadatos")
    if not isinstance(metadatos, dict):
        return ["falta el bloque `metadatos` (o no es un mapa)"]

    desconocidos = set(metadatos) - CAMPOS_METADATOS
    if desconocidos:
        errores.append(f"metadatos: campos fuera de la plantilla: {sorted(desconocidos)}")

    if metadatos.get("celda") != "celda-en-evaluacion":
        errores.append(
            "metadatos.celda debe ser exactamente \"celda-en-evaluacion\" "
            f"(anonimizada); se encontró: {metadatos.get('celda')!r}"
        )
    fecha = metadatos.get("fecha")
    fecha_str = fecha.isoformat() if hasattr(fecha, "isoformat") else fecha
    if not (isinstance(fecha_str, str) and RE_FECHA.match(fecha_str)):
        errores.append(f"metadatos.fecha debe ser AAAA-MM-DD; se encontró: {fecha!r}")
    pasada = metadatos.get("pasada")
    if pasada in (1, 2):
        pass
    elif final and pasada is None:
        pass  # el veredicto final arbitrado no pertenece a una pasada
    else:
        errores.append(f"metadatos.pasada debe ser 1 o 2; se encontró: {pasada!r}")
    for campo in ("modelo_evaluador", "briefing_version", "rubrica_version"):
        if not _es_string_no_vacio(metadatos.get(campo)):
            errores.append(f"metadatos.{campo} debe ser un string no vacío")
    return errores


def validar_item(item: dict) -> list[str]:
    """Violaciones de un item (los mensajes ya vienen prefijados con su at_id)."""
    at_id = item.get("at_id", "<sin at_id>")
    errores = []

    desconocidos = set(item) - CAMPOS_ITEM
    if desconocidos:
        errores.append(f"{at_id}: campos fuera de la plantilla: {sorted(desconocidos)}")

    veredicto = item.get("veredicto")
    if veredicto not in VEREDICTOS:
        errores.append(
            f"{at_id}: veredicto inválido {veredicto!r} (debe ser PASA | FALLA | NO_EVALUABLE)"
        )

    causa = item.get("causa")
    if veredicto == "NO_EVALUABLE":
        if causa is None:
            errores.append(f"{at_id}: NO_EVALUABLE exige `causa` (tabla del briefing)")
        elif causa not in CAUSAS:
            errores.append(f"{at_id}: causa inválida {causa!r} (∈ {sorted(CAUSAS)})")
    elif causa is not None:
        errores.append(
            f"{at_id}: `causa` presente ({causa!r}) con veredicto {veredicto!r} "
            "(sólo se admite bajo NO_EVALUABLE)"
        )

    evidencia = item.get("evidencia")
    if not isinstance(evidencia, list) or not evidencia:
        errores.append(
            f"{at_id}: `evidencia` debe ser una lista NO vacía "
            "(un veredicto sin evidencia es inválido, briefing §4)"
        )
    else:
        for n, objeto in enumerate(evidencia, start=1):
            if not isinstance(objeto, dict):
                errores.append(f"{at_id}: evidencia[{n}] no es un objeto {{tipo, ref, detalle}}")
                continue
            desconocidos = set(objeto) - CAMPOS_EVIDENCIA
            if desconocidos:
                errores.append(
                    f"{at_id}: evidencia[{n}]: campos fuera de la plantilla: {sorted(desconocidos)}"
                )
            if objeto.get("tipo") not in TIPOS_EVIDENCIA:
                errores.append(
                    f"{at_id}: evidencia[{n}].tipo inválido {objeto.get('tipo')!r} "
                    f"(∈ {sorted(TIPOS_EVIDENCIA)})"
                )
            if not _es_string_no_vacio(objeto.get("ref")):
                errores.append(f"{at_id}: evidencia[{n}].ref debe ser un string no vacío")
            if "detalle" not in objeto or objeto.get("detalle") is None:
                errores.append(f"{at_id}: evidencia[{n}] sin campo `detalle`")

    if not _es_string_no_vacio(item.get("justificacion")):
        errores.append(f"{at_id}: `justificacion` no puede estar vacía")

    duracion = item.get("duracion_min")
    if not _es_numero(duracion) or not (0 <= duracion <= 15):
        errores.append(
            f"{at_id}: duracion_min debe ser numérico entre 0 y 15 (tope del briefing §5); "
            f"se encontró: {duracion!r}"
        )
    return errores


def validar(ruta: Path, final: bool) -> list[str]:
    try:
        datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return [f"YAML malformado: {exc}"]
    if not isinstance(datos, dict):
        return ["el documento raíz debe ser un mapa {metadatos, resultados}"]

    errores = []
    desconocidos = set(datos) - CAMPOS_TOP
    if desconocidos:
        errores.append(f"nivel superior: campos fuera de la plantilla: {sorted(desconocidos)}")

    errores += validar_metadatos(datos, final=final)

    orden_canonico = cargar_orden_canonico()
    errores += verificar_cruzado_con_no_automatizables(orden_canonico)

    resultados = datos.get("resultados")
    if not isinstance(resultados, list):
        errores.append("falta la lista `resultados`")
        return errores

    no_mapas = [n for n, item in enumerate(resultados, start=1) if not isinstance(item, dict)]
    if no_mapas:
        errores.append(f"items que no son mapas (posiciones): {no_mapas}")
        return errores

    ids = [item.get("at_id") for item in resultados]
    if len(ids) != len(orden_canonico):
        errores.append(
            f"deben ser exactamente {len(orden_canonico)} items; hay {len(ids)}"
        )
    faltantes = sorted(set(orden_canonico) - set(ids))
    inesperados = sorted(set(ids) - set(orden_canonico), key=str)
    duplicados = sorted({i for i in ids if ids.count(i) > 1}, key=str)
    if faltantes:
        errores.append(f"at_id faltantes: {faltantes}")
    if inesperados:
        errores.append(f"at_id fuera de la rúbrica: {inesperados}")
    if duplicados:
        errores.append(f"at_id duplicados: {duplicados}")
    if not faltantes and not inesperados and not duplicados and ids != orden_canonico:
        fuera_de_orden = [
            f"posición {n}: {tiene!r} (se esperaba {esperado!r})"
            for n, (tiene, esperado) in enumerate(zip(ids, orden_canonico), start=1)
            if tiene != esperado
        ]
        errores.append(
            "los at_id no siguen el orden canónico de la plantilla: "
            + "; ".join(fuera_de_orden)
        )

    for item in resultados:
        errores += validar_item(item)
    return errores


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("archivo", type=Path, help="pasada-<n>.yaml o veredicto-final.yaml")
    parser.add_argument(
        "--final",
        action="store_true",
        help="validar un veredicto-final.yaml (permite metadatos.pasada ausente)",
    )
    args = parser.parse_args()

    if not args.archivo.is_file():
        print(f"ERROR: no existe el archivo {args.archivo}", file=sys.stderr)
        return 2

    errores = validar(args.archivo, final=args.final)
    if errores:
        print(f"INVALIDO: {args.archivo} — {len(errores)} violación(es) del contrato:")
        for error in errores:
            print(f"  - {error}")
        return 1
    print(f"OK: {args.archivo} cumple el contrato de plantilla-resultados.yaml (66 items).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
