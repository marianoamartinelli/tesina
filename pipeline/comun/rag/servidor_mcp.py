#!/usr/bin/env python3
"""Servidor MCP stdio que expone el RAG BM25 del corpus congelado (ADR-009, D2).

Es el **mismo** servidor para las 4 celdas: una sola implementación de la
herramienta, una sola descripción y un único punto donde se registran las
consultas. Lo lanza el CLI de cada familia como proceso hijo —A con
`--mcp-config` + `--strict-mcp-config`, B con `-c mcp_servers.corpus.command=…`—
con el comando que arma `comun.nucleo.comando_servidor_rag`.

El nombre de la herramienta, su descripción, el corpus y el `k` salen de
`comun/etapas.yaml` (clave `rag`, vía `comun.nucleo.cargar_rag`): este archivo no
define ninguno de esos valores. El algoritmo de recuperación es el de
`comun/rag/indice.py` sin cambios (BM25 puro, k1=1.5, b=0.75).

`stdout` pertenece al protocolo JSON-RPC: cualquier impresión lo corrompe. Los
diagnósticos van a `stderr` y el registro para el meta-análisis, al JSONL de
`--log` (evento `consulta_rag`, atribuido a la celda, la etapa y el rol de la
invocación que lo lanzó). Cada invocación de rol arranca su propio servidor y
appendea al mismo archivo.

Uso (lo invoca el CLI, no el operador):
    python servidor_mcp.py --etapas <ruta a comun/etapas.yaml> \
        [--log <ruta.jsonl>] [--celda C] [--etapa E] [--rol R] [--paso N]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# La raíz de pipeline/ al sys.path para importar comun/ desde cualquier cwd: el
# CLI lanza este proceso con el cwd del repo satélite.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import anyio  # noqa: E402
import mcp.types as tipos  # noqa: E402
from mcp.server.lowlevel import Server  # noqa: E402
from mcp.server.stdio import stdio_server  # noqa: E402

from comun.nucleo import SERVIDOR_MCP, ConfigRAG, RegistroJSONL, cargar_rag  # noqa: E402
from comun.rag.indice import IndiceCorpus  # noqa: E402

VERSION = "1.0.0"

# Esquema de entrada de la herramienta: un único parámetro de texto, sin
# descripción propia. Todo el texto que el modelo ve sobre la herramienta viene de
# `rag.descripcion` en etapas.yaml.
ESQUEMA_CONSULTA = {
    "type": "object",
    "properties": {"consulta": {"type": "string"}},
    "required": ["consulta"],
    "additionalProperties": False,
}


def construir_servidor(config: ConfigRAG, indice: IndiceCorpus,
                       registro: RegistroJSONL | None,
                       contexto: dict[str, str | int | None]) -> Server:
    servidor: Server = Server(name=SERVIDOR_MCP, version=VERSION)

    @servidor.list_tools()
    async def listar_herramientas() -> list[tipos.Tool]:
        return [tipos.Tool(
            name=config.herramienta,
            description=config.descripcion,
            inputSchema=ESQUEMA_CONSULTA,
        )]

    @servidor.call_tool()
    async def llamar_herramienta(nombre: str, argumentos: dict) -> list[tipos.ContentBlock]:
        if nombre != config.herramienta:
            raise ValueError(f"herramienta desconocida: {nombre!r}")
        consulta = argumentos["consulta"]
        resultado = indice.formatear(consulta, k=config.k)
        if registro is not None:
            registro.evento("consulta_rag", consulta=consulta, k=config.k,
                            longitud_resultado=len(resultado), **contexto)
        return [tipos.TextContent(type="text", text=resultado)]

    return servidor


async def _servir(servidor: Server) -> None:
    async with stdio_server() as (lectura, escritura):
        await servidor.run(lectura, escritura, servidor.create_initialization_options())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--etapas", required=True,
                        help="Ruta a comun/etapas.yaml (única fuente de la config RAG)")
    parser.add_argument("--log", help="JSONL donde registrar cada consulta_rag")
    parser.add_argument("--celda")
    parser.add_argument("--etapa")
    parser.add_argument("--rol")
    parser.add_argument("--paso", type=int)
    args = parser.parse_args()

    config = cargar_rag(args.etapas)
    indice = IndiceCorpus.desde_directorio(config.ruta_corpus)
    registro = RegistroJSONL(Path(args.log)) if args.log else None
    contexto: dict[str, str | int | None] = {
        "celda": args.celda, "etapa": args.etapa, "rol": args.rol, "paso": args.paso,
    }
    if registro is not None:
        registro.evento("servidor_rag_inicio", herramienta=config.herramienta,
                        k=config.k, corpus=str(config.ruta_corpus), **contexto)

    servidor = construir_servidor(config, indice, registro, contexto)
    try:
        anyio.run(_servir, servidor)
    finally:
        if registro is not None:
            registro.evento("servidor_rag_fin", **contexto)
            registro.cerrar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
