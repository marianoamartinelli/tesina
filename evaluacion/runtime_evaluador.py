"""Runtime del agente evaluador tercero — ADR-026 Decisión 1.

Una sola definición de cómo se invoca a Grok Build (`grok -p`) para **todos** los
instrumentos de evaluación (white-box, rúbricas, alucinaciones, arbitraje): el mismo
modelo, effort, flags de aislamiento y registro para las 4 celdas, verificable por hash
en el evento `inicio` de cada JSONL.

Aislamiento (por qué cada cosa):

- `GROK_HOME` apunta a un directorio **por invocación** que contiene sólo el `auth.json`
  del tesista (copiado en sólo lectura) y un `config.toml` mínimo con el modelo y los
  servidores MCP del instrumento. Sin plugins, skills de usuario, memoria ni sesiones
  previas.
- `HOME` apunta a un directorio **vacío**: medido el 2026-09-06, con `GROK_HOME` aislado el
  CLI igual descubre `~/.claude/skills` y los plugins de Claude Code del host (58 skills);
  con `HOME` vacío quedan sólo las 24 bundled del propio CLI.
- `--disable-web-search`, `--no-memory`, `--no-plan` y la lista de herramientas denegadas:
  el evaluador no recupera nada de internet (regla de oro del briefing: sólo el corpus) ni
  genera imágenes ni programa tareas.
- `--permission-mode bypassPermissions`: headless sin prompts.
- `--output-format streaming-json`: un evento por línea, registrado verbatim con
  `RegistroJSONL.evento_cli`, como los CLI de generación.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

CLI = "grok"
MODELO = "grok-4.6"
EFFORT = "xhigh"
FAMILIA = "evaluador"

# Herramientas del CLI que ningún instrumento necesita. Los nombres son los que el
# propio CLI lista en su evento `available_commands` (medido el 2026-09-06, 1.0.4).
HERRAMIENTAS_DENEGADAS = (
    "image_gen,image_edit,image_to_video,reference_to_video,"
    "scheduler_create,scheduler_delete,scheduler_list,"
    "ask_user_question,enter_plan_mode,exit_plan_mode,workflow"
)

# Versión pinneada del servidor MCP de navegador para la rúbrica web (verificada con
# `npx -y @playwright/mcp@latest --version` el 2026-09-06).
MCP_PLAYWRIGHT = {"command": "npx", "args": ["-y", "@playwright/mcp@0.0.80", "--headless"]}

AUTH_HOST = Path.home() / ".grok" / "auth.json"
BIN_HOST = Path.home() / ".grok" / "bin"


def version_cli() -> str:
    salida = subprocess.run([str(BIN_HOST / CLI), "--version"], capture_output=True,
                            text=True, check=True)
    return salida.stdout.strip()


def preparar_grok_home(dir_trabajo: Path, mcp_servers: dict[str, dict] | None = None) -> Path:
    """`GROK_HOME` aislado dentro del directorio de trabajo, con auth y config mínima."""
    home = dir_trabajo / ".grok-home"
    home.mkdir(parents=True, exist_ok=True)
    destino = home / "auth.json"
    shutil.copy2(AUTH_HOST, destino)
    destino.chmod(stat.S_IRUSR)
    lineas = ["[models]", f'default = "{MODELO}"', f'default_reasoning_effort = "{EFFORT}"', ""]
    for nombre, cfg in (mcp_servers or {}).items():
        lineas += [f"[mcp_servers.{nombre}]",
                   f'command = "{cfg["command"]}"',
                   "args = [" + ", ".join(f'"{a}"' for a in cfg["args"]) + "]",
                   "enabled = true", ""]
    (home / "config.toml").write_text("\n".join(lineas), encoding="utf-8")
    (dir_trabajo / ".home-vacio").mkdir(exist_ok=True)
    return home


def entorno(dir_trabajo: Path, extra: dict[str, str] | None = None) -> dict[str, str]:
    """Entorno del proceso: HOME vacío, GROK_HOME aislado, PATH mínimo + lo que el
    instrumento necesite (URLs del SUT, adb, node para el MCP)."""
    env = {
        "HOME": str(dir_trabajo / ".home-vacio"),
        "GROK_HOME": str(dir_trabajo / ".grok-home"),
        "PATH": f"{BIN_HOST}:{os.environ.get('PATH', '')}",
        "LANG": os.environ.get("LANG", "es_AR.UTF-8"),
        "TERM": "dumb",
    }
    for clave in ("EXCHANGE_API_URL", "EXCHANGE_WS_URL", "WEB_URL", "EVAL_RPC_URL",
                  "EVAL_USDC_ADDRESS", "EVAL_USDC_DEPLOY_BLOCK", "SUITE_CMD_REINICIO_SUT",
                  "ANDROID_HOME", "ANDROID_SDK_ROOT", "JAVA_HOME",
                  "ANDROID_SERIAL", "API_URL_EMULADOR", "CMD_RELANZAR_APP", "CMD_LOG_BACKEND"):
        if os.environ.get(clave):
            env[clave] = os.environ[clave]
    env.update(extra or {})
    return env


def construir_comando(briefing: str, ruta_prompt: Path, subagentes: bool = False) -> list[str]:
    """Línea de comandos de `grok -p` para una sesión del evaluador."""
    comando = [
        str(BIN_HOST / CLI),
        "--prompt-file", str(ruta_prompt),
        "--output-format", "streaming-json",
        "--system-prompt-override", briefing,
        "-m", MODELO,
        "--reasoning-effort", EFFORT,
        "--permission-mode", "bypassPermissions",
        "--disable-web-search",
        "--no-memory",
        "--no-plan",
        "--disallowed-tools", HERRAMIENTAS_DENEGADAS,
    ]
    if not subagentes:
        comando.append("--no-subagents")
    return comando


def ejecutar(comando: list[str], dir_trabajo: Path, env: dict[str, str], registro,
             ruta_stderr: Path) -> int:
    """Corre la sesión, registrando cada línea del stream; devuelve el exit code."""
    with ruta_stderr.open("w", encoding="utf-8") as archivo_stderr:
        proceso = subprocess.Popen(
            comando, cwd=str(dir_trabajo), env=env,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=archivo_stderr,
            text=True, encoding="utf-8", bufsize=1,
        )
        assert proceso.stdout is not None
        try:
            for linea in proceso.stdout:
                registro.evento_cli(FAMILIA, linea)
            return proceso.wait()
        except BaseException:
            proceso.terminate()
            proceso.wait()
            registro.evento("abortado")
            raise


def comando_legible(comando: list[str]) -> list[str]:
    """Para el JSONL: el briefing entero no se repite (va por hash en `inicio`)."""
    salida = []
    for i, parte in enumerate(comando):
        if i > 0 and comando[i - 1] == "--system-prompt-override":
            salida.append(f"<briefing: {len(parte)} chars>")
        else:
            salida.append(parte)
    return salida
