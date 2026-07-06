#!/usr/bin/env python3
"""Harness B — OpenAI Agents SDK (Sandbox Agents), celdas b-sin-rag / b-con-rag.

Adaptador fino sobre `comun/nucleo.py`: este archivo sólo traduce la corrida
cargada por el núcleo a la API del OpenAI Agents SDK (paquete `openai-agents`).
El agente es un `SandboxAgent` (harness de coding nativo del SDK, 2026:
exec_command / lectura / apply_patch dentro de un sandbox) sobre un
`UnixLocalSandboxClient` cuyo workspace es el repo satélite, según ADR-005
(paridad por equivalencia funcional).

Uso:
    python correr.py --config ../config/b-con-rag.yaml \
                     --repo /ruta/al/repo-satelite --etapa backend [--dry-run]

Requiere OPENAI_API_KEY en el entorno (salvo --dry-run).
"""

from __future__ import annotations

import asyncio
import sys
from importlib.metadata import version as version_paquete
from pathlib import Path

# La raíz de pipeline/ al sys.path para importar comun/ desde cualquier cwd.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents import Runner, function_tool  # noqa: E402
from agents.run import RunConfig  # noqa: E402
from agents.sandbox import Manifest, SandboxAgent, SandboxRunConfig  # noqa: E402
from agents.sandbox.sandboxes.unix_local import UnixLocalSandboxClient  # noqa: E402
from agents.stream_events import (  # noqa: E402
    AgentUpdatedStreamEvent,
    RunItemStreamEvent,
)

from comun.nucleo import (  # noqa: E402
    MAX_TURNS,
    PRECIOS_USD_POR_MTOK,
    Corrida,
    RegistroJSONL,
    cargar_corrida,
    construir_parser,
    funcion_consultar_corpus,
    metadata_corrida,
    resumen_dry_run,
)

SDK = "openai-agents"
VERSION_SDK = version_paquete("openai-agents")


def construir_agente(corrida: Corrida, registro: RegistroJSONL | None) -> SandboxAgent:
    """Traduce la corrida a un SandboxAgent.

    Decisiones (idénticas entre celdas B, registradas para el manifest):
    - instructions: el prompt de sistema compartido, verbatim.
    - default_manifest con root = repo satélite: `UnixLocalSandboxSession` usa
      el filesystem del host con el workspace enraizado en `manifest.root`, así
      que el agente lee/edita/ejecuta directamente dentro del repo. Como el
      root es un path custom (≠ default del manifest), el SDK marca
      workspace_root_owned=False y `client.delete()` NO borra el repo
      (verificado contra agents/sandbox/sandboxes/unix_local.py, v0.17.7).
    - capabilities: default del SDK (out-of-the-box, ADR-005).
    Los parámetros de generación quedan en el default del SDK (ADR-005).
    """
    herramientas = []
    if corrida.rag:
        consultar = funcion_consultar_corpus(corrida)

        def consultar_corpus(consulta: str) -> str:
            resultado = consultar(consulta)
            if registro is not None:
                registro.evento("consulta_rag", consulta=consulta,
                                longitud_resultado=len(resultado))
            return resultado

        # La descripción de la herramienta sale verbatim de etapas.yaml
        # (rag.descripcion); los prompts no la mencionan. Es la ÚNICA
        # diferencia entre celdas con y sin RAG (ADR-005, Decisión 2).
        herramientas.append(function_tool(
            consultar_corpus,
            name_override=corrida.rag_herramienta,
            description_override=corrida.rag_descripcion,
        ))

    return SandboxAgent(
        name=f"celda-{corrida.celda}",
        model=corrida.modelo,
        instructions=corrida.prompt_sistema,
        default_manifest=Manifest(root=str(corrida.ruta_repo)),
        tools=herramientas,
    )


async def ejecutar(corrida: Corrida) -> int:
    registro = RegistroJSONL(corrida.ruta_log)
    registro.evento("inicio", **metadata_corrida(corrida, VERSION_SDK, SDK))
    agente = construir_agente(corrida, registro)
    cliente = UnixLocalSandboxClient()
    sesion = await cliente.create(manifest=agente.default_manifest)
    es_error = False

    try:
        async with sesion:
            # Una corrida de agente por etapa: el prompt de etapa es el único
            # input; el avance de etapa lo decide el humano según el protocolo.
            # Streaming para que el log JSONL conserve todo ante un corte.
            resultado = Runner.run_streamed(
                agente,
                corrida.prompt_etapa,
                max_turns=MAX_TURNS,
                run_config=RunConfig(
                    sandbox=SandboxRunConfig(session=sesion),
                    # Sin tracing: evita subir trazas a la plataforma de OpenAI
                    # (el registro del experimento es el JSONL local).
                    tracing_disabled=True,
                    workflow_name=f"{corrida.celda}-{corrida.etapa}",
                ),
            )
            async for evento in resultado.stream_events():
                if isinstance(evento, RunItemStreamEvent):
                    # raw_item: el ítem crudo de la Responses API (mensaje,
                    # tool call, tool output). Los deltas token a token
                    # (raw_response_event) se omiten por volumen.
                    registro.evento("item", nombre=evento.name,
                                    clase=type(evento.item).__name__,
                                    datos=getattr(evento.item, "raw_item", None))
                elif isinstance(evento, AgentUpdatedStreamEvent):
                    registro.evento("agente_actualizado",
                                    agente=evento.new_agent.name)
    except Exception as e:  # el log debe conservar el motivo del corte
        registro.evento("error_harness", clase=type(e).__name__, detalle=str(e))
        registro.cerrar()
        raise
    finally:
        # No borra el repo satélite: workspace_root_owned=False (root custom).
        await cliente.delete(sesion)

    uso = resultado.context_wrapper.usage
    # El SDK de OpenAI no informa costo monetario: se ESTIMA con los precios de
    # ADR-005 (entrada/salida planas, sin descuento por caché).
    # PENDIENTE-PILOTO: contrastar esta estimación con el dashboard de billing
    # de OpenAI en la corrida piloto y ajustar si difiere.
    precios = PRECIOS_USD_POR_MTOK.get(corrida.modelo)
    costo_estimado = (
        uso.input_tokens * precios["entrada"] / 1_000_000
        + uso.output_tokens * precios["salida"] / 1_000_000
    ) if precios else None

    registro.evento(
        "resumen_final",
        estado="completado" if resultado.is_complete else "incompleto",
        es_error=es_error,
        turnos=resultado.current_turn,
        pedidos_api=uso.requests,
        tokens_entrada=uso.input_tokens,
        tokens_salida=uso.output_tokens,
        tokens_total=uso.total_tokens,
        costo_estimado_usd=costo_estimado,  # estimación local, no dato del SDK
        salida_final=str(resultado.final_output)[:4000],
    )
    registro.cerrar()
    print(f"Etapa {corrida.etapa} de {corrida.celda} terminada "
          f"(turnos={resultado.current_turn}, tokens={uso.total_tokens}, "
          f"costo_estimado_usd={costo_estimado}). Log: {corrida.ruta_log}")
    return 0


def main() -> int:
    args = construir_parser(__doc__.splitlines()[0]).parse_args()
    corrida = cargar_corrida(args.config, args.repo, args.etapa, harness_esperado="b")

    if args.dry_run:
        # Construye el agente real (valida el adaptador y el manifest) sin
        # crear la sesión sandbox ni llamar a la API.
        agente = construir_agente(corrida, registro=None)
        nombres = [getattr(h, "name", type(h).__name__) for h in agente.tools]
        detalle = (
            "SandboxAgent (capabilities default: shell + archivos + apply_patch) "
            f"sobre UnixLocalSandboxClient, workspace={agente.default_manifest.root}"
            + (f" + {nombres}" if nombres else "")
        )
        print(resumen_dry_run(corrida, VERSION_SDK, SDK, detalle))
        return 0

    return asyncio.run(ejecutar(corrida))


if __name__ == "__main__":
    sys.exit(main())
