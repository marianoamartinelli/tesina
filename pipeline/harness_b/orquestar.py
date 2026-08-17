#!/usr/bin/env python3
"""Orquestador del harness B — Codex CLI (`codex exec`), celdas b-*.

Adaptador delgado sobre `comun/nucleo.py` (ADR-009, Decisión 4). Su única
responsabilidad es **invocar el CLI**: elegir prompt de sistema, de etapa y de
rol; fijar modelo, effort, herramientas y cwd. El bucle de ejecución y el registro
JSONL son de `comun/nucleo.py`, idénticos en las dos familias. No
implementa lógica de agente, no interpreta la salida del modelo y no decide el
avance de etapa (eso lo gatea el evaluador humano, protocolo §4).

Cada paso de la secuencia (implementador → revisor → implementador) es una
**sesión fresca** del CLI: no se usa `codex exec resume`. El estado compartido
entre pasos es el repo satélite, y el handoff son los archivos bajo `.pipeline/`
que el prompt pasa por puntero.

Uso:
    python orquestar.py --config ../config/b-con-rag.yaml \
                        --repo /ruta/al/repo-satelite --etapa backend [--dry-run]

Autenticación: la del `codex` instalado en la máquina (suscripción del tesista).
Por eso NO se usa un `CODEX_HOME` limpio —ahí vive `auth.json`— sino
`--ignore-user-config`, que ignora la config preservando las credenciales
(ADR-009, Decisión 5).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# La raíz de pipeline/ al sys.path para importar comun/ desde cualquier cwd.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from comun.nucleo import (  # noqa: E402
    SERVIDOR_MCP,
    Corrida,
    Paso,
    cargar_corrida,
    comando_legible,
    comando_servidor_rag,
    construir_parser,
    correr_etapa,
    resumen_dry_run,
    sistema_compuesto,
)

CLI = "codex"
FAMILIA = "b"

# Ventana de contexto forzada, idéntica en las dos celdas B (ADR-010, Decisión 2).
# Gobierna el umbral de auto-compactación entre turnos, no el tamaño máximo de un
# request. Su efecto real es una hipótesis a validar en la piloto (ítem 22).
VENTANA_CONTEXTO = 1_000_000

# NO VERIFICADO: el default de sandbox de `codex exec` no está documentado en
# `codex exec --help` (0.146.0) y no se pudo comprobar sin ejecutar el CLI de
# verdad. Se fija el modo mínimo que permite al implementador escribir en su
# workspace, que es además el confinamiento que ADR-009 declara como asimetría
# de B respecto de A (B sandboxea el shell, A en headless no).
SANDBOX = "workspace-write"

DETALLE_HERRAMIENTAS = (
    f"toolset nativo de Codex con sandbox {SANDBOX}; búsqueda web desactivada por "
    f"default y no activada (ADR-008 del lado B); config del host ignorada "
    f"(--ignore-user-config); servidor MCP '{SERVIDOR_MCP}' sólo en celdas con RAG"
)


def version_cli() -> str:
    """Versión exacta del CLI, para el evento inicial del log y el manifest."""
    salida = subprocess.run([CLI, "--version"], capture_output=True, text=True, check=True)
    return salida.stdout.strip()


def _toml(valor) -> str:
    """Valor de un `-c clave=valor` de Codex, serializado como TOML.

    El CLI parsea el lado derecho como TOML y sólo cae al literal crudo si no
    parsea. `json.dumps` produce TOML válido para strings (comillas dobles con
    `\\n`, `\\"` y `\\uXXXX` legales en TOML básico), listas y enteros, así que el
    valor nunca depende de ese fallback.
    """
    return json.dumps(valor, ensure_ascii=False)


def overrides_mcp(corrida: Corrida, paso: Paso) -> list[str]:
    """Overrides que declaran el servidor MCP stdio del RAG.

    El comando sale de `comun.nucleo.comando_servidor_rag`, el mismo que usa el
    harness A: una sola implementación de la herramienta para las dos familias
    (ADR-009, Decisión 2).
    """
    comando = comando_servidor_rag(corrida, paso)
    return [
        "-c", f"mcp_servers.{SERVIDOR_MCP}.command={_toml(comando[0])}",
        "-c", f"mcp_servers.{SERVIDOR_MCP}.args={_toml(comando[1:])}",
    ]


def construir_comando(corrida: Corrida, paso: Paso) -> list[str]:
    """Línea de comandos exacta de `codex exec` para un paso.

    Cada flag y su fuente:
    - `exec --json`: modo headless con un evento JSON por línea.
    - `-m` / `-c model_reasoning_effort`: ADR-009 Decisión 3 (`gpt-5.6-sol`,
      `xhigh`). Codex no expone `--effort`; el nivel se fija por config, y su
      default (`low` en el flagship) no coincide con el de A.
    - `-c developer_instructions`: mecanismo de inyección del prompt propio en B.
      **Prependea**: aparece como primer `input_text` del mensaje `developer`,
      antes del scaffolding nativo, que se conserva íntegro (ADR-009, verificado
      con `codex debug prompt-input`).
    - `-c model_context_window`: ADR-010 Decisión 2.
    - `--ignore-user-config`: aislamiento de la config del host preservando
      `auth.json` (ADR-009 Decisión 5).
    - `-C <repo>`: el workspace del agente es el repo satélite.
    - `-s`: ver la nota de `SANDBOX`.
    - `-c mcp_servers.corpus.*`: sólo en celdas con RAG.

    El prompt del paso NO va como argumento: el `-` final hace que el CLI lo lea
    de stdin, para no depender del límite de longitud de la línea de comandos.
    """
    comando = [
        CLI, "exec", "--json",
        "--ignore-user-config",
        "-C", str(corrida.ruta_repo),
        "-m", corrida.modelo,
        "-s", SANDBOX,
        "-c", f"model_reasoning_effort={_toml(corrida.effort)}",
        "-c", f"model_context_window={_toml(VENTANA_CONTEXTO)}",
        "-c", f"developer_instructions={_toml(sistema_compuesto(corrida, paso))}",
    ]
    if corrida.rag_config is not None:
        comando += overrides_mcp(corrida, paso)
    comando.append("-")
    return comando


def main() -> int:
    args = construir_parser(
        "Orquestador del harness B (Codex CLI) — una etapa de una celda"
    ).parse_args()
    corrida = cargar_corrida(args.config, args.repo, args.etapa, harness_esperado=FAMILIA)
    version = version_cli()

    if args.dry_run:
        print(resumen_dry_run(corrida, CLI, version, DETALLE_HERRAMIENTAS))
        for paso in corrida.pasos:
            print(f"\n  paso {paso.orden} ({paso.rol}):")
            print("    " + " ".join(comando_legible(construir_comando(corrida, paso))))
            print(f"    prompt por stdin ({len(paso.prompt_usuario)} chars)")
        return 0

    # `construir_comando` es lo único que este orquestador aporta al bucle de
    # ejecución, que vive en `comun.nucleo` para las dos familias.
    return correr_etapa(corrida, CLI, version, FAMILIA, construir_comando)


if __name__ == "__main__":
    sys.exit(main())
