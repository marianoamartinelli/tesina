#!/usr/bin/env python3
"""Fondea una dirección en el anvil local con ETH y/o USDC-mock.

Uso operativo típico: fondear la dirección emisora (hot wallet) del SUT antes de
los tests de retiros — la spec asume que la emisora siempre tiene ETH on-chain
para el gas (spec/08-retiros-on-chain/README.md, "Supuesto operacional") y que
su recarga es operación externa al SUT.

Uso:
    python fondear.py 0xDireccion --eth 10 --usdc 100000
    python fondear.py 0xDireccion --wei 500000000000000000 --usdc-min 25000000

(--eth/--usdc en unidades enteras humanas; --wei/--usdc-min en unidad mínima.)
Requiere el entorno levantado y, para USDC, `EVAL_USDC_ADDRESS` o el archivo
`usdc-mock.address` generado por desplegar-usdc.py.
"""

import argparse
import os
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))

from helpers.onchain import ClienteRpc  # noqa: E402
from helpers.montos import WEI_POR_ETH, USDCMIN_POR_USDC  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("direccion", help="dirección destino (0x + 40 hex)")
    parser.add_argument("--eth", type=int, default=0, help="ETH enteros a transferir")
    parser.add_argument("--wei", type=int, default=0, help="wei a transferir")
    parser.add_argument("--usdc", type=int, default=0, help="USDC enteros a mintear")
    parser.add_argument("--usdc-min", type=int, default=0, help="USDC-min a mintear")
    parser.add_argument("--rpc-url", default=None)
    args = parser.parse_args()

    usdc_address = os.environ.get("EVAL_USDC_ADDRESS")
    if not usdc_address and (AQUI / "usdc-mock.address").exists():
        usdc_address = (AQUI / "usdc-mock.address").read_text().strip()

    rpc = ClienteRpc(url=args.rpc_url, usdc=usdc_address)
    if not rpc.disponible():
        print(f"ERROR: nodo no disponible o chainId ≠ 11155111 en {rpc.url}", file=sys.stderr)
        raise SystemExit(1)

    total_wei = args.eth * WEI_POR_ETH + args.wei
    total_usdcmin = args.usdc * USDCMIN_POR_USDC + args.usdc_min
    if not total_wei and not total_usdcmin:
        print("Nada que fondear (usar --eth/--wei/--usdc/--usdc-min).", file=sys.stderr)
        raise SystemExit(1)

    if total_wei:
        tx = rpc.enviar_eth(args.direccion, total_wei)
        rpc.esperar_receipt(tx)
        print(f"ETH:  {total_wei} wei → {args.direccion} (tx {tx})")
    if total_usdcmin:
        tx = rpc.mint_usdc(args.direccion, total_usdcmin)
        rpc.esperar_receipt(tx)
        print(f"USDC: {total_usdcmin} USDC-min → {args.direccion} (tx {tx})")

    print(f"Balance on-chain: {rpc.balance_eth(args.direccion)} wei", end="")
    if rpc.direccion_usdc:
        print(f", {rpc.balance_usdc(args.direccion)} USDC-min")
    else:
        print()


if __name__ == "__main__":
    main()
