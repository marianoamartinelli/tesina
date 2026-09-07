#!/usr/bin/env python3
"""Runner del agente evaluador white-box (ADR-007; runtime por ADR-010 Decisión 3).

Cierra el `PENDIENTE-ARRANQUE` del README de este directorio: fija los flags concretos
de la invocación, el aislamiento de insumos y el registro del JSONL, para que las dos
pasadas de cada celda se ejecuten **idénticas** y sean auditables.

Qué hace, en orden:

1. **Arma un directorio de trabajo aislado** bajo `/tmp` con **sólo** los insumos que el
   briefing §2 permite: el briefing, la rúbrica, la plantilla de salida, `spec/`,
   `corpus/` y la copia de evaluación del SUT (sin `.git`). El agente corre con ese
   directorio como cwd y no ve el árbol de la tesina: la prohibición de mirar
   `evaluacion/suite-at/`, `runs/`, `journal/` y `analisis/` la sostiene el **mecanismo**
   y no la buena voluntad del agente — el mismo criterio con el que ADR-015 resolvió la
   no-exposición del holdout del lado de la generación.
2. **Invoca `claude -p`** con el briefing verbatim como prompt de sistema y un mensaje de
   usuario mínimo que sólo transporta punteros (rúbrica, plantilla, ruta de salida). El
   briefing es el instrumento congelado: acá no se agrega ni una instrucción de
   contenido.
3. **Registra el JSONL** con el mismo formato que el pipeline de generación
   (`pipeline/comun/nucleo.py`), para que el meta-análisis lea las dos cosas igual.

Uso:

    .venv/bin/python evaluacion/agente-evaluador/correr.py \\
        --sut /ruta/al/repo-satelite-congelado \\
        --salida runs/<id>/no-automatizables \\
        --pasada 1 [--ats evaluacion/pre-piloto/ats-white-box.txt] [--dry-run]

`--ats` acota la evaluación a un subconjunto (pre-piloto, ADR-018): el agente igual
emite los 56 items que la plantilla exige, con `NO_EVALUABLE` /
`FUNCION_NO_LOCALIZABLE` en los que quedan fuera. Sin `--ats` evalúa los 56.

El SUT tiene que estar **arrancado** y el entorno on-chain levantado antes de correr
esto: el briefing §2 los lista como insumo, y varias entradas de la rúbrica los usan.
Este runner no los administra — el evaluador humano los levanta con el contrato de
arranque de `suite-at/entorno/README.md` y exporta `SUITE_CMD_REINICIO_SUT`.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "pipeline"))

from comun.nucleo import RegistroJSONL, sha256_archivo  # noqa: E402

sys.path.insert(0, str(RAIZ / "evaluacion"))
import runtime_evaluador as rt  # noqa: E402  (evaluacion/runtime_evaluador.py; ADR-026)

AQUI = Path(__file__).resolve().parent
CLI = "claude"
FAMILIA = "evaluador"

# ADR-010 Decisión 3 pinnea el modelo del evaluador. El `effort` no lo fija ningún ADR:
# se usa el mismo que las corridas de generación (ADR-009 D3) para no introducir una
# variable más entre instrumento y objeto evaluado. Queda a ratificación del tesista.
MODELO = "claude-opus-5"
EFFORT = "xhigh"

# Herramientas denegadas: mismo traslado de ADR-008 que en la generación. Acá el motivo
# es más fuerte todavía — la "regla de oro" del briefing §2 prohíbe resolver contenido
# de estándares de memoria y obliga a citar el corpus congelado; una búsqueda web
# metería una fuente normativa no congelada en la evidencia.
HERRAMIENTAS_DENEGADAS = "WebSearch,WebFetch"

NOMBRE_SUT = "sut"          # copia de evaluación dentro del directorio de trabajo
NOMBRE_SALIDA = "resultados.yaml"

# Lo que NO se copia de la implementación evaluada. `.git` lo exige el briefing §2
# («preparada sin .git»): el historial revelaría autoría y momento de generación, y el
# briefing §3.4 prohíbe intentar identificar el modelo generador.
EXCLUIDOS_SUT = (".git", "node_modules", ".expo", "dist", "build")


def preparar_directorio(sut: Path, celda: str, pasada: int) -> Path:
    """Directorio de trabajo con los insumos permitidos, y nada más."""
    destino = Path("/tmp") / f"eval-wb-{celda}-p{pasada}-{time.strftime('%Y%m%d-%H%M%S')}"
    destino.mkdir(parents=True)

    for archivo in ("briefing.md", "rubrica-white-box.md", "plantilla-resultados.yaml"):
        shutil.copy2(AQUI / archivo, destino / archivo)
    # spec y corpus congelados: se copian en vez de linkearse para que el agente no
    # pueda salir del directorio de trabajo siguiendo un symlink.
    shutil.copytree(RAIZ / "spec", destino / "spec")
    shutil.copytree(RAIZ / "corpus", destino / "corpus",
                    ignore=shutil.ignore_patterns(".git"))
    shutil.copytree(sut, destino / NOMBRE_SUT, symlinks=False,
                    ignore=shutil.ignore_patterns(*EXCLUIDOS_SUT))
    return destino


def prompt_usuario(dir_trabajo: Path, ruta_ats: Path | None) -> str:
    """Mensaje del usuario: sólo punteros. El contenido lo fija el briefing."""
    lineas = [
        "Evaluá la celda en evaluación siguiendo el briefing que ya tenés y la rúbrica.",
        "",
        f"- Rúbrica: `rubrica-white-box.md` (en el directorio actual).",
        f"- Formato de salida obligatorio: `plantilla-resultados.yaml`.",
        f"- Copia de evaluación del sistema: `{NOMBRE_SUT}/` (sin `.git`, inmutable).",
        "- Spec congelada: `spec/`. Corpus congelado: `corpus/`.",
        f"- Escribí tu resultado en `{NOMBRE_SALIDA}`, en el directorio actual.",
    ]
    if ruta_ats is not None:
        ats = [a.strip() for a in ruta_ats.read_text(encoding="utf-8").split() if a.strip()]
        lineas += [
            "",
            "Esta corrida evalúa un **subconjunto** del alcance (corrida pre-piloto): las "
            "épicas fuera de él no están implementadas. Evaluá con el procedimiento "
            "completo de la rúbrica únicamente estos ATs:",
            "",
            "  " + ", ".join(ats),
            "",
            "Los demás items de la plantilla se emiten igual, en su orden, con "
            "`veredicto: NO_EVALUABLE`, `causa: FUNCION_NO_LOCALIZABLE`, una evidencia "
            "que registre la comprobación de que su épica no está implementada, una "
            "justificación de una línea y `duracion_min: 0`. No les dediques análisis.",
        ]
    return "\n".join(lineas) + "\n"


def construir_comando(dir_trabajo: Path, briefing: str) -> list[str]:
    """Línea de comandos de `claude -p` para una pasada.

    Flags y su motivo (los de aislamiento son los mismos que ADR-009 D5 fija para la
    generación; el evaluador no es una celda del pipeline, pero el aislamiento de la
    config del host vale por la misma razón: que la máquina del tesista no inyecte
    contexto en el instrumento):

    - `-p --output-format stream-json --verbose`: headless, un evento JSON por línea.
    - `--model` / `--effort`: ver `MODELO` / `EFFORT`.
    - `--append-system-prompt`: el briefing **verbatim** (ADR-007: instrucciones
      congeladas, sin prompt ad hoc).
    - `--setting-sources ""` + `--strict-mcp-config`: sin settings, CLAUDE.md, plugins
      ni MCP del host. El evaluador **no** usa el servidor MCP del RAG: el briefing lo
      manda leer el corpus como archivos y citar documento y sección.
    - `--disallowed-tools`: ver `HERRAMIENTAS_DENEGADAS`.
    - `--dangerously-skip-permissions`: headless sin prompts interactivos.

    No va en contenedor, a diferencia de la generación (ADR-015): el evaluador necesita
    hablar con el SUT y con el nodo on-chain que corren en el host, y no hay paridad
    entre celdas que preservar —es el mismo instrumento, corrido igual las 8 veces—.
    El aislamiento de insumos lo da el directorio de trabajo, no el contenedor.
    """
    return [
        CLI, "-p",
        "--output-format", "stream-json",
        "--verbose",
        "--model", MODELO,
        "--effort", EFFORT,
        "--append-system-prompt", briefing,
        "--setting-sources", "",
        "--strict-mcp-config",
        "--disallowed-tools", HERRAMIENTAS_DENEGADAS,
        "--forward-subagent-text",
        "--dangerously-skip-permissions",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sut", required=True, type=Path,
                        help="repo de la implementación evaluada (congelado)")
    parser.add_argument("--salida", required=True, type=Path,
                        help="directorio runs/<id>/no-automatizables/")
    parser.add_argument("--pasada", required=True, type=int, choices=(1, 2))
    parser.add_argument("--celda", default="celda-en-evaluacion",
                        help="id de corrida SÓLO para nombrar archivos; el agente nunca "
                             "lo ve (briefing §3.4: la celda es anónima)")
    parser.add_argument("--ats", type=Path,
                        help="archivo con los AT-ids a evaluar (subconjunto; ADR-018)")
    parser.add_argument("--dry-run", action="store_true",
                        help="prepara el directorio de trabajo y muestra la invocación, "
                             "sin llamar al CLI")
    parser.add_argument("--runtime", choices=("grok", "claude"), default="grok",
                        help="grok = agente tercero (ADR-026, default); claude = el juez de "
                             "ADR-010 D3, conservado para reproducir la pre-piloto")
    args = parser.parse_args()

    if not args.sut.is_dir():
        parser.error(f"el SUT no existe o no es un directorio: {args.sut}")

    briefing = (AQUI / "briefing.md").read_text(encoding="utf-8")
    dir_trabajo = preparar_directorio(args.sut, args.celda, args.pasada)
    mensaje = prompt_usuario(dir_trabajo, args.ats)
    if args.runtime == "grok":
        ruta_prompt = dir_trabajo / ".prompt-usuario.md"
        ruta_prompt.write_text(mensaje, encoding="utf-8")
        rt.preparar_grok_home(dir_trabajo)
        env_proceso = rt.entorno(dir_trabajo)
        comando = rt.construir_comando(briefing, ruta_prompt, subagentes=False)
        modelo, effort, adr = rt.MODELO, rt.EFFORT, "ADR-007 (framework) / ADR-026 (runtime y modelo)"
    else:
        env_proceso = None
        comando = construir_comando(dir_trabajo, briefing)
        modelo, effort, adr = MODELO, EFFORT, "ADR-007 (framework) / ADR-010 D3 (modelo y runtime)"

    args.salida.mkdir(parents=True, exist_ok=True)
    ruta_log = args.salida / f"pasada-{args.pasada}.jsonl"
    registro = RegistroJSONL(ruta_log)

    metadata = {
        "instrumento": "agente-evaluador-white-box",
        "adr": adr,
        "runtime": args.runtime,
        "cli": rt.version_cli() if args.runtime == "grok" else CLI,
        "modelo": modelo,
        "effort": effort,
        "pasada": args.pasada,
        "sut": str(args.sut.resolve()),
        "dir_trabajo": str(dir_trabajo),
        "briefing": {"ruta": str(AQUI / "briefing.md"),
                     "sha256": sha256_archivo(AQUI / "briefing.md")},
        "rubrica": {"ruta": str(AQUI / "rubrica-white-box.md"),
                    "sha256": sha256_archivo(AQUI / "rubrica-white-box.md")},
        "ats_acotados": str(args.ats) if args.ats else None,
        "entorno": {
            "EXCHANGE_API_URL": os.environ.get("EXCHANGE_API_URL"),
            "EVAL_RPC_URL": os.environ.get("EVAL_RPC_URL"),
            "SUITE_CMD_REINICIO_SUT": bool(os.environ.get("SUITE_CMD_REINICIO_SUT")),
        },
    }

    if args.dry_run:
        print(f"DRY-RUN — no se invocó al CLI")
        for clave, valor in metadata.items():
            print(f"  {clave}: {valor}")
        print(f"\n  directorio de trabajo: {dir_trabajo}")
        for entrada in sorted(dir_trabajo.iterdir()):
            print(f"    {entrada.name}{'/' if entrada.is_dir() else ''}")
        print(f"\n  comando: {' '.join(c if len(c) <= 60 else c[:57] + '…' for c in rt.comando_legible(comando))}")
        print(f"\n  mensaje ({len(mensaje)} chars):\n{mensaje}")
        registro.cerrar()
        ruta_log.unlink(missing_ok=True)
        shutil.rmtree(dir_trabajo, ignore_errors=True)
        print(f"\n  (dry-run: se borró el directorio de trabajo)")
        return 0

    registro.evento("inicio", **metadata)
    ruta_stderr = ruta_log.with_suffix(".stderr.txt")
    if args.runtime == "grok":
        codigo = rt.ejecutar(comando, dir_trabajo, env_proceso, registro, ruta_stderr)
        sesiones = dir_trabajo / ".grok-home" / "sessions"
        if sesiones.is_dir():
            shutil.copytree(sesiones, args.salida / f"pasada-{args.pasada}-sesiones-grok",
                            dirs_exist_ok=True)
    with (ruta_stderr.open("a", encoding="utf-8") if args.runtime == "grok"
          else ruta_stderr.open("w", encoding="utf-8")) as archivo_stderr:
        if args.runtime == "grok":
            proceso = None
        else:
            proceso = subprocess.Popen(
                comando, cwd=str(dir_trabajo),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=archivo_stderr,
                text=True, encoding="utf-8", bufsize=1,
            )
        if proceso is None:
            pass
        else:
            assert proceso.stdin is not None and proceso.stdout is not None
            try:
                proceso.stdin.write(mensaje)
                proceso.stdin.close()
                for linea in proceso.stdout:
                    registro.evento_cli(FAMILIA, linea)
                codigo = proceso.wait()
            except BaseException:
                proceso.terminate()
                proceso.wait()
                registro.evento("abortado")
                raise

    producido = dir_trabajo / NOMBRE_SALIDA
    destino_yaml = args.salida / f"pasada-{args.pasada}.yaml"
    if producido.is_file():
        shutil.copy2(producido, destino_yaml)
    registro.evento("fin", codigo_salida=codigo,
                    salida_escrita=producido.is_file(),
                    resultado=str(destino_yaml) if producido.is_file() else None)
    registro.cerrar()

    print(f"pasada {args.pasada}: exit={codigo}")
    print(f"  log:       {ruta_log}")
    print(f"  stderr:    {ruta_stderr}")
    if producido.is_file():
        print(f"  resultado: {destino_yaml}")
        print(f"  validar:   .venv/bin/python {AQUI / 'validar-resultados.py'} {destino_yaml}")
    else:
        print(f"  SIN RESULTADO: el agente no escribió {producido}")
    return codigo


if __name__ == "__main__":
    sys.exit(main())
