#!/usr/bin/env python3
"""Despliega el contrato USDC-mock (ERC-20, 6 decimales, mint público) en el anvil
local y deja la dirección lista para configurar el SUT y la suite.

El bytecode está vendoreado en `usdc-mock.bin` (compilado una única vez desde
`UsdcMock.sol` con solc 0.8.28; ver README.md), así el despliegue no necesita
toolchain de Solidity. La transacción de creación se envía con
`eth_sendTransaction` desde la cuenta 0 de anvil (desbloqueada).

Uso:
    python desplegar-usdc.py [--rpc-url http://127.0.0.1:8545]

Salida:
    - imprime la dirección del contrato (checksum EIP-55) y el bloque de despliegue;
    - escribe `usdc-mock.address` (dirección) y `entorno.env` (variables listas
      para exportar) junto a este script.

Sólo usa la biblioteca estándar de Python.
"""

import argparse
import json
import sys
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RUTA_BYTECODE = AQUI / "usdc-mock.bin"
RUTA_DIRECCION = AQUI / "usdc-mock.address"
RUTA_ENV = AQUI / "entorno.env"

CHAIN_ID_ESPERADO = 11155111
CUENTA_DESPLIEGUE = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"  # anvil cuenta 0

_id = 0


def rpc(url: str, metodo: str, params: list | None = None):
    global _id
    _id += 1
    cuerpo = json.dumps(
        {"jsonrpc": "2.0", "id": _id, "method": metodo, "params": params or []}
    ).encode()
    pedido = urllib.request.Request(url, data=cuerpo, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(pedido, timeout=10) as resp:
        respuesta = json.loads(resp.read())
    if "error" in respuesta:
        raise RuntimeError(f"RPC {metodo} falló: {respuesta['error']}")
    return respuesta["result"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rpc-url", default="http://127.0.0.1:8545")
    args = parser.parse_args()

    chain_id = int(rpc(args.rpc_url, "eth_chainId"), 16)
    if chain_id != CHAIN_ID_ESPERADO:
        print(
            f"ERROR: el nodo en {args.rpc_url} responde chainId {chain_id}, "
            f"se esperaba {CHAIN_ID_ESPERADO} (Sepolia local). "
            "¿Está levantado el docker-compose de este directorio?",
            file=sys.stderr,
        )
        raise SystemExit(1)

    bytecode = RUTA_BYTECODE.read_text().strip()
    tx_hash = rpc(
        args.rpc_url,
        "eth_sendTransaction",
        [{"from": CUENTA_DESPLIEGUE, "data": "0x" + bytecode, "gas": hex(2_000_000)}],
    )
    receipt = rpc(args.rpc_url, "eth_getTransactionReceipt", [tx_hash])
    if not receipt or receipt.get("status") != "0x1":
        print(f"ERROR: el despliegue falló (receipt: {receipt})", file=sys.stderr)
        raise SystemExit(1)

    direccion = receipt["contractAddress"]
    bloque = int(receipt["blockNumber"], 16)

    # checksum EIP-55 para copiar/pegar en la config del SUT
    sys.path.insert(0, str(AQUI.parent))
    from helpers.eip55 import a_checksum  # noqa: E402

    direccion = a_checksum(direccion)

    # sanity: decimals() == 6
    decimales = int(rpc(args.rpc_url, "eth_call", [{"to": direccion, "data": "0x313ce567"}, "latest"]), 16)
    assert decimales == 6, f"decimals() devolvió {decimales}, se esperaba 6"

    RUTA_DIRECCION.write_text(direccion + "\n")
    RUTA_ENV.write_text(
        "# Generado por desplegar-usdc.py — variables del entorno de evaluación\n"
        f"EVAL_RPC_URL={args.rpc_url}\n"
        f"EVAL_USDC_ADDRESS={direccion}\n"
        f"EVAL_USDC_DEPLOY_BLOCK={bloque}\n"
    )

    print(f"USDC-mock desplegado en: {direccion}")
    print(f"Bloque de despliegue:    {bloque}  (usar como BLOQUE_INICIO del indexador del SUT)")
    print(f"Escrito: {RUTA_DIRECCION.name}, {RUTA_ENV.name}")


if __name__ == "__main__":
    main()
