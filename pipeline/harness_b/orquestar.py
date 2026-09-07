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

from comun import contenedor  # noqa: E402
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

# Sin sandbox nativo: el confinamiento es el contenedor, en las dos familias
# (ADR-019, que enmienda la fila "Confinamiento" de ADR-009 y completa ADR-015).
#
# Medido el 2026-08-23 en la pre-piloto: con `-s workspace-write`, Codex confina
# cada comando con el `bwrap` que trae embebido, y bubblewrap no puede crear user
# namespaces dentro del contenedor —el perfil seccomp por default de Docker
# bloquea esas syscalls—, así que **todo** comando del modelo falla con
# `bwrap: No permissions to create a new namespace`, exit 1. Sin shell no hay
# `npm install`, ni build, ni verificación: las dos celdas B quedarían inservibles.
# `-s danger-full-access` no cambia nada: el wrapper se aplica igual.
#
# De las dos salidas medidas —aflojar seccomp en el `docker run` de B, o desactivar
# el sandbox nativo— se elige la segunda: deja la envoltura del contenedor
# **idéntica** entre familias (`comun/contenedor.py` la arma una sola vez) y pone a
# B en el mismo régimen que A, que ya corre sin sandbox del SO bajo
# `--dangerously-skip-permissions`. El CLI documenta este flag para exactamente
# este caso: "Intended solely for running in environments that are externally
# sandboxed".
FLAG_SIN_SANDBOX = "--dangerously-bypass-approvals-and-sandbox"

# Traslado de ADR-008 al mecanismo del CLI. El supuesto original de ADR-009
# Decisión 5 —"Codex trae la búsqueda web desactivada por default y no se activa,
# lo que satisface ADR-008 del lado B"— es **falso** en 0.146.0. Verificado el
# 2026-08-17 corriendo el CLI:
#
# - `web_search` es una clave de config de tipo string con valores válidos
#   `disabled|cached|indexed|live`. Sin pasar `--search` y con
#   `--ignore-user-config`, una corrida registró dos items `web_search`
#   completados contra GitHub: el default no es `disabled`. `--search` sólo sube
#   el nivel a `live`.
# - `codex features list` con un `CODEX_HOME` limpio —o sea, default del
#   producto y no config del host— da `apps`, `browser_use` y `computer_use` en
#   `true`. `apps` expone el servidor MCP `codex_apps` con conectores atados a la
#   cuenta; en esa misma corrida el agente llamó `github.search`,
#   `github.get_profile` y `github.search_repositories`. `--ignore-user-config`
#   no desactiva ninguna de las tres.
#
# Las dos cosas hacen falta: con los `--disable` solos las búsquedas web siguen
# ocurriendo. Con ambas, la corrida de control no registró ningún `web_search`
# ni `mcp_tool_call`.
#
# Límite conocido: esto restringe herramientas, no la red. Un agente con shell y
# red —necesaria para instalar dependencias— puede recuperar de internet igual.
# Vale también para el harness A, que corre sin sandbox del SO.
FEATURES_DESACTIVADAS = ("apps", "browser_use", "computer_use")
MODO_WEB_SEARCH = "disabled"

DETALLE_HERRAMIENTAS = (
    f"toolset nativo de Codex sin sandbox nativo ({FLAG_SIN_SANDBOX}; el "
    f"confinamiento es el contenedor, ADR-019); web_search={MODO_WEB_SEARCH} y "
    f"features {'/'.join(FEATURES_DESACTIVADAS)} desactivadas (ADR-008 del lado B); "
    f"config del host ignorada (--ignore-user-config); servidor MCP "
    f"'{SERVIDOR_MCP}' sólo en celdas con RAG"
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
    - `-c web_search` y `--disable`: traslado de ADR-008; ver la nota de
      `FEATURES_DESACTIVADAS`.
    - `-C <repo>`: el workspace del agente es el repo satélite, montado en
      `contenedor.DIR_REPO` (ADR-015): adentro la ruta del host no existe.
    - `--dangerously-bypass-approvals-and-sandbox`: ver la nota de
      `FLAG_SIN_SANDBOX` (ADR-019). Reemplaza a `-s workspace-write`.
    - `-c mcp_servers.corpus.*`: sólo en celdas con RAG.

    El prompt del paso NO va como argumento: el `-` final hace que el CLI lo lea
    de stdin, para no depender del límite de longitud de la línea de comandos.
    """
    comando = [
        CLI, "exec", "--json",
        "--ignore-user-config",
        "-C", contenedor.DIR_REPO,
        "-m", corrida.modelo,
        FLAG_SIN_SANDBOX,
        "-c", f"model_reasoning_effort={_toml(corrida.effort)}",
        "-c", f"model_context_window={_toml(VENTANA_CONTEXTO)}",
        "-c", f"developer_instructions={_toml(sistema_compuesto(corrida, paso))}",
        "-c", f"web_search={_toml(MODO_WEB_SEARCH)}",
    ]
    for feature in FEATURES_DESACTIVADAS:
        comando += ["--disable", feature]
    if corrida.rag_config is not None:
        comando += overrides_mcp(corrida, paso)
    comando.append("-")
    # Ver la nota equivalente en `harness_a/orquestar.py`: la envoltura en
    # contenedor es la misma función para las dos familias (ADR-015).
    return contenedor.envolver(comando, corrida, FAMILIA)


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
    return correr_etapa(corrida, CLI, version, FAMILIA, construir_comando, desde_paso=args.desde_paso)


if __name__ == "__main__":
    sys.exit(main())
