#!/usr/bin/env python3
"""Harness A — Claude Agent SDK (Anthropic), celdas a-sin-rag / a-con-rag.

Adaptador fino sobre `comun/nucleo.py`: este archivo sólo traduce la corrida
cargada por el núcleo a la API del Claude Agent SDK (paquete `claude-agent-sdk`).
El agente usa el toolset nativo de coding del SDK (Read/Write/Edit/Bash/Glob/
Grep, etc.) con el repo satélite como cwd, según ADR-005 (paridad por
equivalencia funcional).

Uso:
    python correr.py --config ../config/a-con-rag.yaml \
                     --repo /ruta/al/repo-satelite --etapa backend [--dry-run]

Requiere ANTHROPIC_API_KEY en el entorno (salvo --dry-run).
"""

from __future__ import annotations

import asyncio
import sys
from importlib.metadata import version as version_paquete
from pathlib import Path
from typing import Any

# La raíz de pipeline/ al sys.path para importar comun/ desde cualquier cwd.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from claude_agent_sdk import (  # noqa: E402
    ClaudeAgentOptions,
    ResultMessage,
    create_sdk_mcp_server,
    query,
    tool,
)

from comun.nucleo import (  # noqa: E402
    MAX_TURNS,
    Corrida,
    RegistroJSONL,
    cargar_corrida,
    construir_parser,
    funcion_consultar_corpus,
    metadata_corrida,
    resumen_dry_run,
)

SDK = "claude-agent-sdk"
VERSION_SDK = version_paquete("claude-agent-sdk")
# Nombre del servidor MCP in-process; el nombre calificado de la herramienta
# queda mcp__corpus__consultar_corpus (convención del SDK: mcp__<server>__<tool>).
SERVIDOR_MCP = "corpus"


def construir_opciones(corrida: Corrida, registro: RegistroJSONL | None) -> ClaudeAgentOptions:
    """Traduce la corrida a ClaudeAgentOptions.

    Decisiones (idénticas entre celdas A, registradas para el manifest):
    - system_prompt: el prompt de sistema compartido, verbatim.
    - cwd: el repo satélite; el toolset nativo opera ahí.
    - permission_mode="bypassPermissions": corrida headless sin prompts
      interactivos; el confinamiento efectivo lo da el protocolo (repo satélite
      dedicado + supervisión humana según ADR-004).
      # PENDIENTE-PILOTO: evaluar en la piloto si conviene sumar
      # sandbox=SandboxSettings(enabled=True) para aislar bash a nivel SO sin
      # romper builds que necesitan red (npm/pip install).
    - setting_sources=[]: aísla la corrida de settings/CLAUDE.md/plugins de la
      máquina del tesista (reproducibilidad).
    - max_turns=MAX_TURNS: tope de seguridad compartido con el harness B.
    Los parámetros de generación quedan en el default del SDK (ADR-005).
    """
    servidores_mcp: dict[str, Any] = {}
    herramientas_permitidas: list[str] = []

    if corrida.rag:
        consultar = funcion_consultar_corpus(corrida)

        # La descripción de la herramienta sale verbatim de etapas.yaml
        # (rag.descripcion); los prompts no la mencionan. Es la ÚNICA
        # diferencia entre celdas con y sin RAG (ADR-005, Decisión 2).
        @tool(corrida.rag_herramienta, corrida.rag_descripcion, {"consulta": str})
        async def consultar_corpus(args: dict[str, Any]) -> dict[str, Any]:
            consulta = args["consulta"]
            resultado = consultar(consulta)
            if registro is not None:
                registro.evento("consulta_rag", consulta=consulta,
                                longitud_resultado=len(resultado))
            return {"content": [{"type": "text", "text": resultado}]}

        servidores_mcp[SERVIDOR_MCP] = create_sdk_mcp_server(
            name=SERVIDOR_MCP, version="1.0.0", tools=[consultar_corpus]
        )
        herramientas_permitidas.append(f"mcp__{SERVIDOR_MCP}__{corrida.rag_herramienta}")

    return ClaudeAgentOptions(
        model=corrida.modelo,
        cwd=str(corrida.ruta_repo),
        system_prompt=corrida.prompt_sistema,
        permission_mode="bypassPermissions",
        setting_sources=[],
        mcp_servers=servidores_mcp,
        allowed_tools=herramientas_permitidas,
        max_turns=MAX_TURNS,
    )


async def ejecutar(corrida: Corrida) -> int:
    registro = RegistroJSONL(corrida.ruta_log)
    registro.evento("inicio", **metadata_corrida(corrida, VERSION_SDK, SDK))
    opciones = construir_opciones(corrida, registro)
    resultado: ResultMessage | None = None

    try:
        # Una corrida de agente por etapa: el prompt de etapa es el único input;
        # el avance a la etapa siguiente lo decide el humano según el protocolo.
        async for mensaje in query(prompt=corrida.prompt_etapa, options=opciones):
            registro.evento("mensaje", clase=type(mensaje).__name__, datos=mensaje)
            if isinstance(mensaje, ResultMessage):
                resultado = mensaje
    except Exception as e:  # el log debe conservar el motivo del corte
        registro.evento("error_harness", clase=type(e).__name__, detalle=str(e))
        registro.cerrar()
        raise

    if resultado is None:
        registro.evento("resumen_final", estado="sin_result_message")
        registro.cerrar()
        print(f"ADVERTENCIA: la corrida terminó sin ResultMessage; ver {corrida.ruta_log}")
        return 1

    registro.evento(
        "resumen_final",
        estado=resultado.subtype,
        es_error=resultado.is_error,
        turnos=resultado.num_turns,
        duracion_ms=resultado.duration_ms,
        duracion_api_ms=resultado.duration_api_ms,
        costo_total_usd=resultado.total_cost_usd,  # el SDK lo informa nativo
        uso=resultado.usage,
        session_id=resultado.session_id,
    )
    registro.cerrar()
    print(f"Etapa {corrida.etapa} de {corrida.celda} terminada "
          f"(subtype={resultado.subtype}, turnos={resultado.num_turns}, "
          f"costo_usd={resultado.total_cost_usd}). Log: {corrida.ruta_log}")
    return 1 if resultado.is_error else 0


def main() -> int:
    args = construir_parser(__doc__.splitlines()[0]).parse_args()
    corrida = cargar_corrida(args.config, args.repo, args.etapa, harness_esperado="a")

    if args.dry_run:
        # Construye las opciones reales (valida el adaptador) sin llamar a la API.
        opciones = construir_opciones(corrida, registro=None)
        detalle = (
            "toolset nativo de coding del Claude Agent SDK"
            + (f" + {opciones.allowed_tools}" if opciones.allowed_tools else "")
        )
        print(resumen_dry_run(corrida, VERSION_SDK, SDK, detalle))
        return 0

    return asyncio.run(ejecutar(corrida))


if __name__ == "__main__":
    sys.exit(main())
