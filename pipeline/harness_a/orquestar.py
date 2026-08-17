#!/usr/bin/env python3
"""Orquestador del harness A — Claude Code CLI (`claude -p`), celdas a-*.

Adaptador delgado sobre `comun/nucleo.py` (ADR-009, Decisión 4). Su única
responsabilidad es **invocar el CLI**: elegir prompt de sistema, de etapa y de
rol; fijar modelo, effort, herramientas y cwd. El bucle de ejecución y el registro
JSONL son de `comun/nucleo.py`, idénticos en las dos familias. No
implementa lógica de agente, no interpreta la salida del modelo y no decide el
avance de etapa (eso lo gatea el evaluador humano, protocolo §4).

Cada paso de la secuencia (implementador → revisor → implementador) es una
**sesión fresca** del CLI: no se usa `--resume` ni `--continue`. El estado
compartido entre pasos es el repo satélite, y el handoff son los archivos bajo
`.pipeline/` que el prompt pasa por puntero.

Uso:
    python orquestar.py --config ../config/a-con-rag.yaml \
                        --repo /ruta/al/repo-satelite --etapa backend [--dry-run]

Autenticación: la del `claude` instalado en la máquina (suscripción del tesista).
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

CLI = "claude"
FAMILIA = "a"

# Herramientas denegadas: traslado de ADR-008 al mecanismo del CLI (ADR-009,
# Decisión 5). Se pasan como lista separada por comas porque `--disallowed-tools`
# es variádico y un valor único no puede tragarse los flags siguientes.
HERRAMIENTAS_DENEGADAS = "WebSearch,WebFetch"

DETALLE_HERRAMIENTAS = (
    "toolset nativo de Claude Code; WebSearch y WebFetch denegadas (ADR-008); "
    f"MCP restringido a --mcp-config (--strict-mcp-config); servidor '{SERVIDOR_MCP}' "
    "sólo en celdas con RAG"
)


def version_cli() -> str:
    """Versión exacta del CLI, para el evento inicial del log y el manifest."""
    salida = subprocess.run([CLI, "--version"], capture_output=True, text=True, check=True)
    return salida.stdout.strip()


def config_mcp(corrida: Corrida, paso: Paso) -> dict:
    """Config MCP que consume `--mcp-config`: un único servidor stdio.

    El comando sale de `comun.nucleo.comando_servidor_rag`, el mismo que usa el
    harness B: una sola implementación de la herramienta para las dos familias
    (ADR-009, Decisión 2).
    """
    comando = comando_servidor_rag(corrida, paso)
    return {"mcpServers": {SERVIDOR_MCP: {"command": comando[0], "args": comando[1:]}}}


def ruta_config_mcp(corrida: Corrida, paso: Paso) -> Path:
    """Archivo temporal de config MCP, junto al log (nunca dentro de pipeline/)."""
    return corrida.ruta_log.with_name(f"{corrida.ruta_log.stem}-mcp-paso{paso.orden}.json")


def construir_comando(corrida: Corrida, paso: Paso, ruta_mcp: Path | None) -> list[str]:
    """Línea de comandos exacta de `claude -p` para un paso.

    Cada flag y su fuente:
    - `-p --output-format stream-json --verbose`: modo headless con un evento
      JSON por línea. El CLI **exige** `--verbose` en esa combinación (verificado
      en el binario 2.1.233: "When using --print, --output-format=stream-json
      requires --verbose").
    - `--model` / `--effort`: ADR-009 Decisión 3 (`claude-opus-5`, `xhigh`).
    - `--append-system-prompt`: mecanismo de inyección del prompt propio en A
      (ADR-009 Decisión 1: A appendea, B prependea; equivalencia funcional).
    - `--setting-sources ""` + `--strict-mcp-config`: aislamiento de la config
      del host (ADR-009 Decisión 5). Sin settings, CLAUDE.md, plugins ni MCP de
      la máquina del tesista.
    - `--disallowed-tools`: traslado de ADR-008.
    - `--forward-subagent-text`: los subagentes emiten sus mensajes con
      `parent_tool_use_id` seteado, que es lo que `nucleo.es_de_subagente` usa
      para atribuirlos (ADR-010 Decisión 1 exige registrar la actividad de
      subagentes, no sólo la del agente principal).
    - `--dangerously-skip-permissions`: corrida headless sin prompts interactivos,
      equivalente del `permission_mode="bypassPermissions"` del harness SDK. El
      CLI rechaza `--permission-mode bypassPermissions` si la sesión no se lanzó
      con este flag (verificado en el binario 2.1.233).
    - `--mcp-config`: sólo en celdas con RAG.

    El prompt del paso NO va como argumento: se escribe por stdin, para no
    depender del límite de longitud de la línea de comandos.
    """
    comando = [
        CLI, "-p",
        "--output-format", "stream-json",
        "--verbose",
        "--model", corrida.modelo,
        "--effort", corrida.effort,
        "--append-system-prompt", sistema_compuesto(corrida, paso),
        "--setting-sources", "",
        "--strict-mcp-config",
        "--disallowed-tools", HERRAMIENTAS_DENEGADAS,
        "--forward-subagent-text",
        "--dangerously-skip-permissions",
    ]
    if ruta_mcp is not None:
        comando += ["--mcp-config", str(ruta_mcp)]
    return comando


def preparar_paso(corrida: Corrida, paso: Paso) -> tuple[list[str], dict]:
    """Deja listo el paso y devuelve `(comando, datos para el log)`.

    Es lo único que este orquestador aporta al bucle de ejecución, que vive en
    `comun.nucleo.correr_etapa` / `ejecutar_paso` para las dos familias: acá sólo
    se escribe el archivo de config MCP —`--mcp-config` toma una ruta, no un
    objeto— y se arma la línea de comandos.
    """
    ruta_mcp = None
    if corrida.rag_config is not None:
        ruta_mcp = ruta_config_mcp(corrida, paso)
        ruta_mcp.parent.mkdir(parents=True, exist_ok=True)
        ruta_mcp.write_text(json.dumps(config_mcp(corrida, paso), ensure_ascii=False),
                            encoding="utf-8")
    return (construir_comando(corrida, paso, ruta_mcp),
            {"mcp_config": str(ruta_mcp) if ruta_mcp else None})


def main() -> int:
    args = construir_parser(
        "Orquestador del harness A (Claude Code CLI) — una etapa de una celda"
    ).parse_args()
    corrida = cargar_corrida(args.config, args.repo, args.etapa, harness_esperado=FAMILIA)
    version = version_cli()

    if args.dry_run:
        print(resumen_dry_run(corrida, CLI, version, DETALLE_HERRAMIENTAS))
        for paso in corrida.pasos:
            ruta_mcp = ruta_config_mcp(corrida, paso) if corrida.rag_config else None
            print(f"\n  paso {paso.orden} ({paso.rol}):")
            print("    " + " ".join(comando_legible(
                construir_comando(corrida, paso, ruta_mcp))))
            print(f"    prompt por stdin ({len(paso.prompt_usuario)} chars)")
            if ruta_mcp is not None:
                print("    --mcp-config: "
                      + json.dumps(config_mcp(corrida, paso), ensure_ascii=False))
        return 0

    return correr_etapa(corrida, CLI, version, FAMILIA, preparar_paso)


if __name__ == "__main__":
    sys.exit(main())
