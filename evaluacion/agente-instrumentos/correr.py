#!/usr/bin/env python3
"""Runner de los instrumentos de evaluación ejecutados por el agente tercero (ADR-026).

Un solo runner para las rúbricas web/mobile/rol revisor, las alucinaciones de dominio y
el **arbitraje** de cualquier instrumento (incluido el white-box, cuyas pasadas corre
`../agente-evaluador/correr.py`). Lo que hace, en orden:

1. Arma un **directorio de trabajo aislado** bajo `/tmp` con sólo los insumos que el
   briefing del instrumento permite —y exactamente con los nombres que ese briefing
   fija: `rubrica.md` / `procedimiento.md`, `sut/`, `spec/`, `corpus/`, `entorno/`,
   `snapshots/<etapa>/paso*`, `logs/<etapa>.jsonl`, `candidatos.txt`, `trazas/`,
   `referencia-externa/`, `pasada-1/`, `pasada-2/`, `discrepancias.txt`—.
2. Invoca al CLI del evaluador (`evaluacion/comun/runtime_evaluador.py`) con el briefing
   verbatim como system prompt y un mensaje de usuario que sólo transporta punteros, la
   pasada y la fecha.
3. Registra el JSONL con el formato del pipeline y archiva la salida bajo `--salida`.

Uso:
    correr.py --instrumento rubrica-web --sut <repo> --salida runs/<id>/rubricas/web \\
              --pasada 1 [--alcance ats.txt] [--dry-run]
    correr.py --instrumento rol-revisor --sut <repo> --logs <repo>/../logs --salida … --pasada 2
    correr.py --instrumento alucinaciones --sut <repo> --logs … --salida … --pasada 1
    correr.py --instrumento white-box --arbitraje --pasada1 <yaml> --pasada2 <yaml> --sut … --salida …
    correr.py --instrumento rubrica-web --arbitraje --pasada1 <dir> --pasada2 <dir> --sut … --salida …

Variables de entorno que el runner reenvía al agente (las fija el operador, protocolo
§10.2): `EXCHANGE_API_URL`, `EXCHANGE_WS_URL`, `WEB_URL`, `EVAL_RPC_URL`,
`EVAL_USDC_ADDRESS`, `SUITE_CMD_REINICIO_SUT`, `ANDROID_SERIAL`, `API_URL_EMULADOR`,
`CMD_RELANZAR_APP`, `CMD_LOG_BACKEND`, `ANDROID_HOME`, `JAVA_HOME`.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "pipeline"))
sys.path.insert(0, str(RAIZ / "evaluacion"))

from comun.nucleo import RegistroJSONL, sha256_archivo  # noqa: E402  (pipeline/comun)
import runtime_evaluador as rt  # noqa: E402  (evaluacion/runtime_evaluador.py)

AQUI = Path(__file__).resolve().parent
RUBRICAS = RAIZ / "evaluacion" / "rubricas"
ENTORNO = RAIZ / "evaluacion" / "suite-at" / "entorno"
WHITE_BOX = RAIZ / "evaluacion" / "agente-evaluador"

EXCLUIDOS_SUT = (".git", "node_modules", ".expo", "dist", "build")
ETAPAS = ("backend", "web", "mobile")

# Qué copia el runner para cada instrumento, según el §2 de su briefing.
INSTRUMENTOS = {
    "rubrica-web": dict(briefing="briefing-rubrica-web.md", instrumento=RUBRICAS / "epica-10-web.md",
                        nombre_instr="rubrica.md", corpus=False, entorno=True, snapshots=False,
                        candidatos=False, mcp={"playwright": rt.MCP_PLAYWRIGHT},
                        salidas=("rubrica-completada.md", "resultados-rubricas-web.csv", "evidencia"),
                        clave="at_id", csv="resultados-rubricas-web.csv"),
    "rubrica-mobile": dict(briefing="briefing-rubrica-mobile.md", instrumento=RUBRICAS / "epica-11-mobile.md",
                           nombre_instr="rubrica.md", corpus=True, entorno=True, snapshots=False,
                           candidatos=False, mcp={},
                           salidas=("rubrica-completada.md", "resultados-rubricas-mobile.csv", "evidencia"),
                           clave="at_id", csv="resultados-rubricas-mobile.csv"),
    "rol-revisor": dict(briefing="briefing-rol-revisor.md", instrumento=RUBRICAS / "rol-revisor.md",
                        nombre_instr="rubrica.md", corpus=False, entorno=False, snapshots=True,
                        candidatos=False, mcp={},
                        salidas=("rubrica-completada.md", "resultados-rubrica-revisor.csv", "censo-revision.csv"),
                        clave=("etapa", "criterio"), csv="resultados-rubrica-revisor.csv"),
    "alucinaciones": dict(briefing="briefing-alucinaciones.md", instrumento=RAIZ / "evaluacion" / "alucinaciones.md",
                          nombre_instr="procedimiento.md", corpus=True, entorno=False, snapshots=False,
                          candidatos=True, mcp={},
                          salidas=("alucinaciones.md", "alucinaciones.csv"),
                          clave="candidato", csv="alucinaciones.csv"),
    "white-box": dict(briefing=WHITE_BOX / "briefing.md", instrumento=WHITE_BOX / "rubrica-white-box.md",
                      nombre_instr="rubrica-white-box.md", corpus=True, entorno=False, snapshots=False,
                      candidatos=False, mcp={}, salidas=("resultados.yaml",), clave="at_id", csv=None),
}

# Batería de extracción de candidatos, pinneada por `alucinaciones.md` §3.2 (case-insensitive).
BATERIA = [
    r"(bip|eip|erc)[-_ ]?[0-9]{1,4}",
    r"mnemonic|seed phrase|wordlist|derivation|hardened|xprv|xpub",
    r"m/44|coin.?type|keccak|checksum|secp256k1",
    r"chain.?id|11155111|sepolia|replay",
    r"eth_[a-z]+|json.?rpc|logindex",
]
REFERENCIA_EXTERNA = {
    "bips-README.mediawiki": "https://raw.githubusercontent.com/bitcoin/bips/master/README.mediawiki",
    "eips-indice.json": "https://api.github.com/repos/ethereum/EIPs/contents/EIPS",
    "ercs-indice.json": "https://api.github.com/repos/ethereum/ERCs/contents/ERCS",
}


# ----------------------------------------------------------------------------- insumos

def copiar_sut(sut: Path, destino: Path) -> None:
    shutil.copytree(sut, destino / "sut", symlinks=False,
                    ignore=shutil.ignore_patterns(*EXCLUIDOS_SUT))


def copiar_snapshots_y_logs(logs: Path, destino: Path) -> dict[str, str]:
    """`snapshots/<etapa>/paso*` y `logs/<etapa>.jsonl` desde el directorio de logs de la
    corrida (`<repo-satélite>/../logs/`). Devuelve qué archivo se usó por etapa."""
    usados = {}
    for etapa in ETAPAS:
        jsonls = sorted(p for p in logs.glob(f"*-{etapa}-*.jsonl")
                        if not p.name.endswith("-rag.jsonl"))
        if not jsonls:
            continue
        jsonl = jsonls[-1]
        (destino / "logs").mkdir(exist_ok=True)
        shutil.copy2(jsonl, destino / "logs" / f"{etapa}.jsonl")
        snaps = logs / f"{jsonl.stem}-snapshots"
        if snaps.is_dir():
            shutil.copytree(snaps, destino / "snapshots" / etapa, symlinks=False)
        usados[etapa] = jsonl.name
    return usados


def texto_del_agente(payload: dict) -> list[str]:
    """Respuestas del agente generador en un evento del CLI (A y B), sin prompts."""
    textos = []
    if payload.get("type") == "assistant":                       # A: claude -p
        for bloque in (payload.get("message") or {}).get("content", []) or []:
            if isinstance(bloque, dict) and bloque.get("type") == "text":
                textos.append(bloque.get("text", ""))
    item = payload.get("item") or {}                              # B: codex exec
    if payload.get("type") == "item.completed" and item.get("type") == "agent_message":
        textos.append(item.get("text", ""))
    return [t for t in textos if t.strip()]


def extraer_trazas(logs: Path, destino: Path) -> None:
    (destino / "trazas").mkdir(exist_ok=True)
    for etapa in ETAPAS:
        for jsonl in sorted(logs.glob(f"*-{etapa}-*.jsonl")):
            if jsonl.name.endswith("-rag.jsonl"):
                continue
            lineas = []
            for linea in jsonl.open(encoding="utf-8"):
                try:
                    evento = json.loads(linea)
                except json.JSONDecodeError:
                    continue
                if evento.get("tipo") != "evento_cli":
                    continue
                for texto in texto_del_agente(evento.get("payload") or {}):
                    lineas.append(f"--- {evento.get('ts')} paso={evento.get('orden', '?')}")
                    lineas.append(texto)
            (destino / "trazas" / f"{etapa}.txt").write_text("\n".join(lineas) + "\n",
                                                             encoding="utf-8")


def es_texto(ruta: Path) -> bool:
    try:
        with ruta.open("rb") as f:
            return b"\0" not in f.read(4096)
    except OSError:
        return False


def extraer_candidatos(destino: Path) -> int:
    """`candidatos.txt`: la batería de §3.2 sobre `sut/` y `trazas/`, un bloque por hit."""
    patron = re.compile("|".join(f"(?:{b})" for b in BATERIA), re.IGNORECASE)
    excluidos = set(EXCLUIDOS_SUT) | {"vendor", ".pipeline"}
    lockfiles = ("package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock")
    bloques = []
    for raiz in ("sut", "trazas"):
        for ruta in sorted((destino / raiz).rglob("*")):
            if not ruta.is_file() or any(p in excluidos for p in ruta.parts):
                continue
            if ruta.name in lockfiles or not es_texto(ruta):
                continue
            lineas = ruta.read_text(encoding="utf-8", errors="replace").split("\n")
            for i, linea in enumerate(lineas):
                if patron.search(linea):
                    ini, fin = max(0, i - 3), min(len(lineas), i + 4)
                    ctx = "\n".join(f"  {j + 1:5d}{'>' if j == i else ' '} {lineas[j][:300]}"
                                    for j in range(ini, fin))
                    bloques.append(f"{ruta.relative_to(destino)}:{i + 1}\n{ctx}")
    texto = "\n\n".join(f"K-{n:03d} {b}" for n, b in enumerate(bloques, 1))
    (destino / "candidatos.txt").write_text(texto + "\n", encoding="utf-8")
    return len(bloques)


def capturar_referencia_externa(destino: Path) -> None:
    carpeta = destino / "referencia-externa"
    carpeta.mkdir(exist_ok=True)
    fecha = time.strftime("%Y-%m-%d")
    for nombre, url in REFERENCIA_EXTERNA.items():
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                cuerpo = resp.read().decode("utf-8", errors="replace")
            (carpeta / nombre).write_text(f"# fuente: {url}\n# capturado: {fecha}\n{cuerpo}",
                                          encoding="utf-8")
        except Exception as exc:  # noqa: BLE001 — se registra, no se inventa
            (carpeta / (nombre + ".NO-CAPTURADO.txt")).write_text(
                f"# fuente: {url}\n# capturado: {fecha}\n# error: {exc}\n", encoding="utf-8")


def preparar_directorio(instr: str, args) -> tuple[Path, dict]:
    cfg = INSTRUMENTOS[instr]
    marca = time.strftime("%Y%m%d-%H%M%S")
    sufijo = "arb" if args.arbitraje else f"p{args.pasada}"
    dir_trabajo = Path("/tmp") / f"eval-{instr}-{args.celda}-{sufijo}-{marca}"
    dir_trabajo.mkdir(parents=True)
    detalle: dict = {}

    shutil.copy2(cfg["instrumento"], dir_trabajo / cfg["nombre_instr"])
    if instr == "white-box":
        shutil.copy2(WHITE_BOX / "plantilla-resultados.yaml", dir_trabajo / "plantilla-resultados.yaml")
    shutil.copytree(RAIZ / "spec", dir_trabajo / "spec")
    if cfg["corpus"]:
        shutil.copytree(RAIZ / "corpus", dir_trabajo / "corpus", ignore=shutil.ignore_patterns(".git"))
    if cfg["entorno"]:
        shutil.copytree(ENTORNO, dir_trabajo / "entorno", ignore=shutil.ignore_patterns("__pycache__"))
    copiar_sut(args.sut, dir_trabajo)
    if cfg["snapshots"]:
        detalle["logs_usados"] = copiar_snapshots_y_logs(args.logs, dir_trabajo)
    if cfg["candidatos"]:
        extraer_trazas(args.logs, dir_trabajo)
        detalle["candidatos"] = extraer_candidatos(dir_trabajo)
        capturar_referencia_externa(dir_trabajo)
    (dir_trabajo / "evidencia").mkdir(exist_ok=True)

    if args.arbitraje:
        shutil.copy2(cfg["briefing"] if isinstance(cfg["briefing"], Path) else AQUI / cfg["briefing"],
                     dir_trabajo / "briefing-instrumento.md")
        for n, origen in ((1, args.pasada1), (2, args.pasada2)):
            if origen.is_dir():
                shutil.copytree(origen, dir_trabajo / f"pasada-{n}")
            else:  # white-box: un YAML por pasada
                (dir_trabajo / f"pasada-{n}").mkdir()
                shutil.copy2(origen, dir_trabajo / f"pasada-{n}" / "resultados.yaml")
        claves = discrepancias(instr, dir_trabajo / "pasada-1", dir_trabajo / "pasada-2")
        (dir_trabajo / "discrepancias.txt").write_text("\n".join(claves) + ("\n" if claves else ""),
                                                        encoding="utf-8")
        (dir_trabajo / "final").mkdir()
        detalle["discrepancias"] = len(claves)
    return dir_trabajo, detalle


# ------------------------------------------------------------------------ discrepancias

def leer_csv(ruta: Path) -> list[dict]:
    with ruta.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def discrepancias(instr: str, p1: Path, p2: Path) -> list[str]:
    """Claves discrepantes entre pasadas, con la clave que fija `briefing-arbitraje.md` §2."""
    if instr == "white-box":
        import yaml  # noqa: PLC0415
        a = {i["at_id"]: i for i in yaml.safe_load((p1 / "resultados.yaml").read_text(encoding="utf-8"))["resultados"]}
        b = {i["at_id"]: i for i in yaml.safe_load((p2 / "resultados.yaml").read_text(encoding="utf-8"))["resultados"]}
        return [k for k in a if (a[k].get("veredicto"), a[k].get("causa")) != (b.get(k, {}).get("veredicto"), b.get(k, {}).get("causa"))]
    cfg = INSTRUMENTOS[instr]
    claves: list[str] = []
    if instr in ("rubrica-web", "rubrica-mobile"):
        a = {f["at_id"]: f for f in leer_csv(p1 / cfg["csv"])}
        b = {f["at_id"]: f for f in leer_csv(p2 / cfg["csv"])}
        claves = [k for k in a if a[k]["resultado"] != b.get(k, {}).get("resultado")]
    elif instr == "alucinaciones":
        a = {f["candidato"]: f for f in leer_csv(p1 / cfg["csv"])}
        b = {f["candidato"]: f for f in leer_csv(p2 / cfg["csv"])}
        claves = [k for k in a if (a[k]["veredicto"], a[k]["categoria"]) != (b.get(k, {}).get("veredicto"), b.get(k, {}).get("categoria"))]
    elif instr == "rol-revisor":
        a = {(f["etapa"], f["criterio"]): f for f in leer_csv(p1 / cfg["csv"])}
        b = {(f["etapa"], f["criterio"]): f for f in leer_csv(p2 / cfg["csv"])}
        claves = [f"{e},{c}" for (e, c) in a if a[(e, c)]["resultado"] != b.get((e, c), {}).get("resultado")]
        ca = leer_csv(p1 / "censo-revision.csv"); cb = leer_csv(p2 / "censo-revision.csv")
        for etapa in ETAPAS:
            fa = [f for f in ca if f["etapa"] == etapa]; fb = [f for f in cb if f["etapa"] == etapa]
            if len(fa) != len(fb):
                claves.append(f"{etapa},*")
                continue
            campos = ("eje", "severidad", "ancla", "ubicacion", "accionable", "veracidad", "destino")
            for x, y in zip(fa, fb):
                if any(x[c] != y[c] for c in campos):
                    claves.append(f"{etapa},{x['punto']}")
    return claves


# ----------------------------------------------------------------------------- prompt

def prompt_usuario(instr: str, args, detalle: dict) -> str:
    cfg = INSTRUMENTOS[instr]
    fecha = time.strftime("%Y-%m-%d")
    if args.arbitraje:
        lineas = [
            f"Arbitrá las discrepancias entre las dos pasadas del instrumento **{instr}** de la "
            "celda en evaluación, siguiendo el briefing de arbitraje que ya tenés.",
            "",
            "- Briefing del instrumento: `briefing-instrumento.md`; su rúbrica o procedimiento: "
            f"`{cfg['nombre_instr']}`.",
            "- Pasadas: `pasada-1/` y `pasada-2/`. Discrepancias: `discrepancias.txt` "
            f"({detalle.get('discrepancias', 0)} claves).",
            "- Escribí el veredicto de registro en `final/` y el informe en `arbitraje.md`, "
            f"con `fecha: {fecha}`.",
        ]
    else:
        lineas = [
            f"Ejecutá el instrumento **{instr}** sobre la celda en evaluación siguiendo el "
            "briefing que ya tenés, entrada por entrada y en el orden del documento.",
            "",
            f"- Instrumento: `{cfg['nombre_instr']}` (en el directorio actual).",
            f"- Pasada: {args.pasada}. Fecha: {fecha}.",
            "- Copia de evaluación: `sut/` (sin `.git`, inmutable). Spec: `spec/`.",
        ]
        if cfg["corpus"]:
            lineas.append("- Corpus congelado: `corpus/`.")
        if cfg["entorno"]:
            lineas.append("- Herramientas del entorno on-chain: `entorno/`.")
        if cfg["snapshots"]:
            lineas.append("- Snapshots por paso: `snapshots/<etapa>/`. JSONL por etapa: `logs/<etapa>.jsonl`.")
        if cfg["candidatos"]:
            lineas.append(f"- Candidatos: `candidatos.txt` ({detalle.get('candidatos', 0)} bloques). "
                          "Trazas: `trazas/`. Índices oficiales: `referencia-externa/`.")
        lineas.append("- Salida: los archivos del §6 del briefing, en el directorio actual "
                      "(`evidencia/` ya existe).")
    if args.alcance is not None:
        ats = [a.strip() for a in args.alcance.read_text(encoding="utf-8").split() if a.strip()]
        lineas += [
            "",
            "Esta corrida evalúa un **subconjunto** del alcance (corrida pre-piloto): las HU "
            "fuera de él no están implementadas. Aplicá el procedimiento completo únicamente a "
            "estas filas:",
            "",
            "  " + ", ".join(ats),
            "",
            "Las demás filas se emiten igual, en su orden, con `NO_EVALUABLE` causa (b) y la nota "
            "«fuera del alcance de la corrida». No les dediques análisis.",
        ]
    return "\n".join(lineas) + "\n"


# ------------------------------------------------------------------------------ main

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--instrumento", required=True, choices=sorted(INSTRUMENTOS))
    parser.add_argument("--sut", required=True, type=Path, help="repo satélite congelado")
    parser.add_argument("--logs", type=Path, help="directorio de logs de la corrida (rol-revisor, alucinaciones)")
    parser.add_argument("--salida", required=True, type=Path, help="runs/<id>/<instrumento>/")
    parser.add_argument("--pasada", type=int, choices=(1, 2))
    parser.add_argument("--arbitraje", action="store_true")
    parser.add_argument("--pasada1", type=Path); parser.add_argument("--pasada2", type=Path)
    parser.add_argument("--celda", default="celda-en-evaluacion",
                        help="sólo para nombrar archivos; el agente nunca lo ve")
    parser.add_argument("--alcance", type=Path, help="AT-ids a evaluar (subconjunto, ADR-018)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    instr = args.instrumento
    cfg = INSTRUMENTOS[instr]
    if not args.sut.is_dir():
        parser.error(f"el SUT no existe: {args.sut}")
    if args.arbitraje:
        if not (args.pasada1 and args.pasada2):
            parser.error("--arbitraje exige --pasada1 y --pasada2")
    elif args.pasada is None:
        parser.error("--pasada es obligatorio salvo en --arbitraje")
    if instr == "white-box" and not args.arbitraje:
        parser.error("las pasadas del white-box las corre agente-evaluador/correr.py")
    if (cfg["snapshots"] or cfg["candidatos"]) and not (args.logs and args.logs.is_dir()):
        parser.error(f"{instr} exige --logs")

    ruta_briefing = AQUI / "briefing-arbitraje.md" if args.arbitraje else (
        cfg["briefing"] if isinstance(cfg["briefing"], Path) else AQUI / cfg["briefing"])
    briefing = ruta_briefing.read_text(encoding="utf-8")
    dir_trabajo, detalle = preparar_directorio(instr, args)
    mensaje = prompt_usuario(instr, args, detalle)
    ruta_prompt = dir_trabajo / ".prompt-usuario.md"
    ruta_prompt.write_text(mensaje, encoding="utf-8")
    rt.preparar_grok_home(dir_trabajo, cfg["mcp"])
    env = rt.entorno(dir_trabajo)
    comando = rt.construir_comando(briefing, ruta_prompt, subagentes=False)

    etiqueta = "arbitraje" if args.arbitraje else f"pasada-{args.pasada}"
    args.salida.mkdir(parents=True, exist_ok=True)
    ruta_log = args.salida / f"{etiqueta}.jsonl"
    registro = RegistroJSONL(ruta_log)
    metadata = {
        "instrumento": instr, "modo": etiqueta, "adr": "ADR-026",
        "cli": rt.version_cli(), "modelo": rt.MODELO, "effort": rt.EFFORT,
        "sut": str(args.sut.resolve()), "dir_trabajo": str(dir_trabajo),
        "briefing": {"ruta": str(ruta_briefing), "sha256": sha256_archivo(ruta_briefing)},
        "instrumento_archivo": {"ruta": str(cfg["instrumento"]), "sha256": sha256_archivo(cfg["instrumento"])},
        "alcance": str(args.alcance) if args.alcance else None,
        "comando": rt.comando_legible(comando),
        "entorno": {k: env.get(k) for k in ("WEB_URL", "EXCHANGE_API_URL", "ANDROID_SERIAL",
                                             "API_URL_EMULADOR", "EVAL_RPC_URL")},
        **detalle,
    }
    if args.dry_run:
        print("DRY-RUN — no se invocó al CLI")
        for k, v in metadata.items():
            print(f"  {k}: {v}")
        print(f"\n  directorio de trabajo: {dir_trabajo}")
        for e in sorted(dir_trabajo.iterdir()):
            print(f"    {e.name}{'/' if e.is_dir() else ''}")
        print(f"\n  mensaje:\n{mensaje}")
        registro.cerrar(); ruta_log.unlink(missing_ok=True)
        shutil.rmtree(dir_trabajo, ignore_errors=True)
        return 0

    registro.evento("inicio", **metadata)
    codigo = rt.ejecutar(comando, dir_trabajo, env, registro, ruta_log.with_suffix(".stderr.txt"))

    destino = args.salida / ("veredicto-final" if args.arbitraje else etiqueta)
    if destino.exists():
        shutil.rmtree(destino)
    destino.mkdir()
    producidos = []
    origen_salidas = dir_trabajo / "final" if args.arbitraje else dir_trabajo
    for nombre in cfg["salidas"]:
        ruta = origen_salidas / nombre
        if ruta.is_dir():
            shutil.copytree(ruta, destino / nombre); producidos.append(nombre)
        elif ruta.is_file():
            shutil.copy2(ruta, destino / nombre); producidos.append(nombre)
    if args.arbitraje and (dir_trabajo / "arbitraje.md").is_file():
        shutil.copy2(dir_trabajo / "arbitraje.md", args.salida / "arbitraje.md"); producidos.append("arbitraje.md")
    sesiones = dir_trabajo / ".grok-home" / "sessions"
    if sesiones.is_dir():
        shutil.copytree(sesiones, destino / "sesiones-grok", dirs_exist_ok=True)
    registro.evento("fin", codigo_salida=codigo, producidos=producidos, destino=str(destino))
    registro.cerrar()
    print(f"{instr} {etiqueta}: exit={codigo}; producidos={producidos}\n  log: {ruta_log}\n  salida: {destino}")
    return 0 if codigo == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
