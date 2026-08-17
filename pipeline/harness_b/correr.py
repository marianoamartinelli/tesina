#!/usr/bin/env python3
"""Harness B — OpenAI Agents SDK (Sandbox Agents), celdas b-sin-rag / b-con-rag.

SUPERSEDIDO por `orquestar.py` (ADR-009): el harness B pasó del SDK al CLI
`codex exec`. Este archivo queda como camino de vuelta hasta que la piloto valide
el reemplazo (ADR-009 §Consecuencias) y **no corre tal como está**: `comun/nucleo.py`
ya no exporta `MAX_TURNS` ni `funcion_consultar_corpus`, y `openai-agents` salió de
`requirements.txt`.

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
from agents.exceptions import MaxTurnsExceeded  # noqa: E402
from agents.result import RunResultStreaming  # noqa: E402
from agents.run import RunConfig  # noqa: E402
from agents.sandbox import (  # noqa: E402
    Manifest,
    SandboxAgent,
    SandboxPathGrant,
    SandboxRunConfig,
)
from agents.sandbox.manifest import Environment  # noqa: E402
from agents.sandbox.sandboxes.unix_local import UnixLocalSandboxClient  # noqa: E402
from agents.stream_events import (  # noqa: E402
    AgentUpdatedStreamEvent,
    RunItemStreamEvent,
)
from agents.usage import Usage  # noqa: E402

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


def ruta_tmp_sandbox(corrida: Corrida) -> Path:
    """Directorio temporal del sandbox, FUERA del repo satélite.

    El seatbelt de macOS deniega file-write* sobre el TMPDIR heredado de
    os.environ (/var/folders/…, bajo /private): herramientas node que usan
    os.tmpdir() sin fallback (metro/expo, node-gyp, postinstall scripts)
    fallarían con EPERM. Se fija TMPDIR a un directorio hermano del repo
    (junto a logs/) para no contaminar el artefacto evaluado.
    """
    return corrida.ruta_repo.parent / "tmp-sandbox"


def costo_estimado_usd(modelo: str, uso: Usage) -> float | None:
    """Estimación local de costo: el SDK de OpenAI no informa costo monetario.

    Precios planos de ADR-005 (entrada/salida, sin descuento por caché).
    # PENDIENTE-PILOTO: contrastar esta estimación con el dashboard de billing
    # de OpenAI en la corrida piloto y ajustar si difiere.
    """
    precios = PRECIOS_USD_POR_MTOK.get(modelo)
    if precios is None:
        return None
    return (uso.input_tokens * precios["entrada"] / 1_000_000
            + uso.output_tokens * precios["salida"] / 1_000_000)


def escribir_resumen_final(registro: RegistroJSONL, corrida: Corrida,
                           estado: str, es_error: bool,
                           resultado: RunResultStreaming) -> None:
    """Único punto de escritura del evento resumen_final.

    Lo comparten el camino feliz y el corte por max_turns para que ambos
    registren los mismos campos de cierre (simétricos a los del harness A).
    """
    uso = resultado.context_wrapper.usage
    costo = costo_estimado_usd(corrida.modelo, uso)
    registro.evento(
        "resumen_final",
        estado=estado,
        es_error=es_error,
        turnos=resultado.current_turn,
        pedidos_api=uso.requests,
        tokens_entrada=uso.input_tokens,
        tokens_salida=uso.output_tokens,
        tokens_total=uso.total_tokens,
        costo_estimado_usd=costo,  # estimación local, no dato del SDK
        salida_final=str(resultado.final_output)[:4000],
    )
    registro.cerrar()
    print(f"Etapa {corrida.etapa} de {corrida.celda} terminada "
          f"(estado={estado}, turnos={resultado.current_turn}, "
          f"tokens={uso.total_tokens}, costo_estimado_usd={costo}). "
          f"Log: {corrida.ruta_log}")


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
    - environment + extra_path_grants: TMPDIR apunta a un directorio temporal
      escribible fuera del repo satélite (ver `ruta_tmp_sandbox`); el env del
      manifest se aplica sobre os.environ al resolver el contexto de ejecución
      y el grant abre file-write* sobre ese path en el perfil seatbelt
      (verificado contra agents/sandbox/sandboxes/unix_local.py y
      agents/sandbox/manifest.py, v0.17.7).
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

    ruta_tmp = ruta_tmp_sandbox(corrida)
    return SandboxAgent(
        name=f"celda-{corrida.celda}",
        model=corrida.modelo,
        instructions=corrida.prompt_sistema,
        default_manifest=Manifest(
            root=str(corrida.ruta_repo),
            environment=Environment(value={"TMPDIR": str(ruta_tmp)}),
            extra_path_grants=(SandboxPathGrant(path=str(ruta_tmp), read_only=False),),
        ),
        tools=herramientas,
    )


async def ejecutar(corrida: Corrida) -> int:
    registro = RegistroJSONL(corrida.ruta_log)
    registro.evento("inicio", **metadata_corrida(corrida, VERSION_SDK, SDK))
    agente = construir_agente(corrida, registro)
    cliente = UnixLocalSandboxClient()
    sesion = await cliente.create(manifest=agente.default_manifest)
    # El TMPDIR fijado en el manifest debe existir antes de la corrida: muchas
    # herramientas fallan si $TMPDIR apunta a un directorio inexistente.
    ruta_tmp_sandbox(corrida).mkdir(parents=True, exist_ok=True)

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
            pedidos_registrados = 0
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
                # Visibilidad intra-etapa del presupuesto (el tope de 200 USD
                # de ADR-004 se vigila DURANTE la corrida): un evento por
                # pedido a la API — usage sólo avanza al completarse cada
                # respuesta del modelo, así que se emite cuando cambia
                # uso.requests, sin snapshots repetidos. Además preserva el
                # costo consumido si la corrida se corta antes del resumen.
                uso = resultado.context_wrapper.usage
                if uso.requests != pedidos_registrados:
                    pedidos_registrados = uso.requests
                    registro.evento(
                        "uso_parcial",
                        pedidos_api=uso.requests,
                        tokens_entrada=uso.input_tokens,
                        tokens_salida=uso.output_tokens,
                        tokens_total=uso.total_tokens,
                        # Misma estimación (y salvedad) que resumen_final.
                        costo_estimado_usd=costo_estimado_usd(corrida.modelo, uso),
                    )
    except MaxTurnsExceeded:
        # Cierre simétrico al del harness A (subtype error_max_turns): el
        # resumen conserva turnos/tokens/costo hasta el corte. `resultado`
        # quedó asignado antes de iterar el stream, así que está en scope.
        escribir_resumen_final(registro, corrida, estado="error_max_turns",
                               es_error=True, resultado=resultado)
        return 1
    except Exception as e:  # fallback: el log debe conservar el motivo del corte
        registro.evento("error_harness", clase=type(e).__name__, detalle=str(e))
        registro.cerrar()
        raise
    finally:
        # No borra el repo satélite: workspace_root_owned=False (root custom).
        await cliente.delete(sesion)

    escribir_resumen_final(
        registro, corrida,
        estado="completado" if resultado.is_complete else "incompleto",
        es_error=False,
        resultado=resultado,
    )
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
