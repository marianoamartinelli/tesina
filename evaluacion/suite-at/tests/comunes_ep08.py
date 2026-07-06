"""Utilidades compartidas de los tests de la épica 08 (retiros on-chain).

Sólo helpers black-box: REST (épica 09), estado on-chain vía JSON-RPC (anvil del
entorno) y control del mundo on-chain con métodos `anvil_*`/`evm_*` (minado a
demanda, saldos, código de contratos) para construir los "Dado" y provocar los
escenarios de fallo de HU-08-03/HU-08-04/HU-08-05.

Parámetros de la épica (spec/08-retiros-on-chain/README.md §Parámetros; el
entorno de evaluación los deja en sus valores por defecto, ver
evaluacion/suite-at/entorno/README.md):
- GAS_PRICE_SOURCE = configured_fixed, GAS_PRICE_WEI = 20 gwei (snapshot del retiro)
- GAS_LIMIT_ETH = 21000, GAS_LIMIT_ERC20 = 100000, TX_TYPE = legacy (Type-0)
- MIN_WITHDRAWAL_ETH = 0.001 ETH, MIN_WITHDRAWAL_USDC = 1 USDC
- MAX_BROADCAST_RETRIES = 5, MAX_BLOCKS_PENDING = 50, CONFIRMACIONES = 12
"""

import secrets

import pytest
from Crypto.Hash import keccak

from helpers.eip55 import a_checksum
from helpers.espera import esperar_hasta
from helpers.montos import CHAIN_ID, CONFIRMACIONES_REQUERIDAS, a_int
from helpers.onchain import CUENTA_TESORERIA

# --------------------------------------------------------------------------------
# Constantes de la épica 08 (README de la épica; valores del entorno de evaluación)
# --------------------------------------------------------------------------------

GAS_PRICE_WEI = 20_000_000_000                     # 20 gwei (GAS_PRICE_WEI, snapshot)
GAS_LIMIT_ETH = 21_000
GAS_LIMIT_ERC20 = 100_000
FEE_RED_ETH = GAS_LIMIT_ETH * GAS_PRICE_WEI        # 420000000000000 (HU-08-01 RN-8)
FEE_RED_ERC20 = GAS_LIMIT_ERC20 * GAS_PRICE_WEI    # 2000000000000000 (HU-08-05 RN-2)
MIN_WITHDRAWAL_ETH = 1_000_000_000_000_000         # 0.001 ETH (HU-08-01 RN-7)
MIN_WITHDRAWAL_USDC = 1_000_000                    # 1 USDC (HU-08-01 RN-7)
MAX_BROADCAST_RETRIES = 5
MAX_BLOCKS_PENDING = 50

# v de una firma legacy EIP-155 con chainId 11155111: v = 35|36 + 2·chainId (INV-6)
V_EIP155 = {2 * CHAIN_ID + 35, 2 * CHAIN_ID + 36}

# keccak256("Transfer(address,address,uint256)") — evento ERC-20 estándar (HU-08-05 RN-5)
TOPIC_TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
SELECTOR_TRANSFER = "0xa9059cbb"                   # transfer(address,uint256)

# Dirección EIP-55 válida (vector todo-mayúsculas del propio EIP-55; para tests
# de validación pura donde no se verifica llegada de fondos).
DIRECCION_EIP55 = "0x52908400098527886E0F7030069857D2E4169EE7"

# Runtime de 5 bytes `PUSH1 0, PUSH1 0, REVERT`: cualquier llamada/transferencia a
# una cuenta con este código falla (status = 0). Para un retiro ETH con
# gas_limit = 21000 (intrínseco exacto) la ejecución del código agota el gas.
CODE_REVIERTE = "0x60006000fd"
# Runtime que responde exitosamente (status = 1) devolviendo uint256(1) y SIN
# emitir ningún log: sabotea el USDC-mock para el caso "status = 1 sin Transfer"
# (HU-08-04 RN-2 / HU-08-05 RN-5).
CODE_RETORNA_TRUE = "0x600160005260206000f3"


# --------------------------------------------------------------------------------
# Direcciones y ABI
# --------------------------------------------------------------------------------


def destino_fresco() -> str:
    """Dirección EIP-55 aleatoria sin historia on-chain (balance 0, sin código).

    Permite verificar la llegada de fondos con igualdad exacta.
    """
    return a_checksum("0x" + secrets.token_bytes(20).hex())


def abi_pad_direccion(direccion: str) -> str:
    return direccion.lower().replace("0x", "").rjust(64, "0")


def abi_pad_uint(valor: int) -> str:
    return format(valor, "x").rjust(64, "0")


def data_transfer(destino: str, monto_usdcmin: int) -> str:
    """ABI-encoding exacto de `transfer(destino, monto)` (HU-08-05 RN-1)."""
    return SELECTOR_TRANSFER + abi_pad_direccion(destino) + abi_pad_uint(monto_usdcmin)


def hex_int(h) -> int:
    """Cantidad JSON-RPC (hex string) → int."""
    return int(h, 16)


# --------------------------------------------------------------------------------
# Balances internos (REST, épica 09 RN-9)
# --------------------------------------------------------------------------------


def balance_de(usuario, asset: str) -> dict:
    """Item {asset, available, locked, total} del balance interno del usuario."""
    resp = usuario.api.get("/balances")
    assert resp.status_code == 200, resp.text
    balances = resp.json()
    item = next((b for b in balances if b["asset"] == asset), None)
    assert item is not None, f"GET /balances sin item para {asset}: {balances!r}"
    return item


def foto_balances(usuario) -> dict:
    """{asset: (available, locked, total)} como enteros, para comparar identidad."""
    return {
        a: tuple(a_int(b[k]) for k in ("available", "locked", "total"))
        for a in ("ETH", "USDC")
        for b in [balance_de(usuario, a)]
    }


# --------------------------------------------------------------------------------
# Fondeo por depósito on-chain real (único camino black-box; épicas 06+07)
# --------------------------------------------------------------------------------


def fondear_eth(usuario, rpc, monto_wei: int) -> None:
    """Deposita ETH (transfer + 12 confirmaciones) hasta verlo acreditado."""
    direccion = usuario.api.get("/deposit-address", params={"asset": "ETH"}).json()["address"]
    antes = a_int(balance_de(usuario, "ETH")["available"])
    rpc.depositar_eth(direccion, monto_wei)
    esperar_hasta(
        lambda: a_int(balance_de(usuario, "ETH")["available"]) >= antes + monto_wei,
        intervalo=1.0,
        mensaje="el depósito ETH no se acreditó al balance interno",
    )


def fondear_usdc(usuario, rpc, monto_usdcmin: int) -> None:
    """Deposita USDC (mint + transfer + 12 confirmaciones) hasta verlo acreditado."""
    direccion = usuario.api.get("/deposit-address", params={"asset": "USDC"}).json()["address"]
    antes = a_int(balance_de(usuario, "USDC")["available"])
    rpc.depositar_usdc(direccion, monto_usdcmin)
    esperar_hasta(
        lambda: a_int(balance_de(usuario, "USDC")["available"]) >= antes + monto_usdcmin,
        intervalo=1.0,
        mensaje="el depósito USDC no se acreditó al balance interno",
    )


def usdc_del_entorno(rpc) -> str:
    """Dirección del contrato USDC-mock del entorno (o skip si no está configurada)."""
    if not rpc.direccion_usdc:
        pytest.skip("EVAL_USDC_ADDRESS no configurada (entorno/desplegar-usdc.py)")
    return rpc.direccion_usdc


# --------------------------------------------------------------------------------
# Retiros: solicitud y consulta (contrato de la épica 09, HU-09-01 RN-11/RN-18)
# --------------------------------------------------------------------------------


def crear_retiro(usuario, asset: str, amount: str, address: str, client_id: str | None = None):
    """POST /withdrawals con el body de HU-09-01 RN-11. Devuelve la Response cruda."""
    body = {"asset": asset, "amountMinUnit": amount, "address": address}
    if client_id is not None:
        body["clientWithdrawalId"] = client_id
    return usuario.api.post("/withdrawals", json=body)


def retiro_de(usuario, withdrawal_id: str) -> dict:
    """GET /withdrawals/{id} (asserta 200; item de HU-09-01 RN-18)."""
    resp = usuario.api.get(f"/withdrawals/{withdrawal_id}")
    assert resp.status_code == 200, resp.text
    return resp.json()


def listar_retiros(usuario) -> list[dict]:
    resp = usuario.api.get("/withdrawals")
    assert resp.status_code == 200, resp.text
    return resp.json()["items"]


def esperar_retiro(
    usuario, withdrawal_id: str, estados, prohibidos=(), timeout=None, intervalo=1.0
) -> dict:
    """Espera hasta que el retiro esté en alguno de `estados` y lo devuelve.

    Si aparece un estado de `prohibidos` (p. ej. un terminal inesperado) aborta de
    inmediato con RuntimeError (no se sigue esperando: sería un falso timeout).
    """
    def condicion():
        retiro = retiro_de(usuario, withdrawal_id)
        if retiro["status"] in prohibidos:
            raise RuntimeError(
                f"retiro {withdrawal_id} llegó a estado prohibido {retiro['status']!r} "
                f"(failureReason={retiro.get('failureReason')!r}); se esperaba {estados}"
            )
        return retiro if retiro["status"] in estados else None

    return esperar_hasta(
        condicion,
        timeout=timeout,
        intervalo=intervalo,
        mensaje=f"el retiro {withdrawal_id} no llegó a {estados}",
    )


def esperar_broadcast(usuario, rpc, withdrawal_id: str, timeout=None):
    """Espera BROADCAST con txHash y devuelve (retiro, tx) con la tx real del nodo.

    Con automine la transacción queda incluida al broadcastearse y no avanza a
    CONFIRMED hasta que el test mine 12 bloques (control determinista).
    """
    retiro = esperar_retiro(
        usuario, withdrawal_id, ("BROADCAST",), prohibidos=("FAILED", "CONFIRMED"),
        timeout=timeout,
    )
    tx_hash = retiro.get("txHash")
    assert isinstance(tx_hash, str) and tx_hash, f"retiro BROADCAST sin txHash: {retiro!r}"
    tx = esperar_hasta(
        lambda: rpc.transaccion(tx_hash),
        mensaje=f"la transacción {tx_hash} expuesta por la API no existe en el nodo",
    )
    return retiro, tx


def confirmar_retiro(usuario, rpc, withdrawal_id: str, timeout=None):
    """Lleva un retiro hasta CONFIRMED: espera BROADCAST, mina hasta 12
    confirmaciones y espera la transición. Devuelve (retiro, tx, receipt)."""
    _, tx = esperar_broadcast(usuario, rpc, withdrawal_id, timeout=timeout)
    receipt = rpc.esperar_receipt(tx["hash"])
    inclusion = hex_int(receipt["blockNumber"])
    faltan = CONFIRMACIONES_REQUERIDAS - (rpc.numero_de_bloque() - inclusion)
    if faltan > 0:
        rpc.minar_bloques(faltan)
    retiro = esperar_retiro(
        usuario, withdrawal_id, ("CONFIRMED",), prohibidos=("FAILED",), timeout=timeout
    )
    return retiro, tx, receipt


def descubrir_emisora(usuario, rpc) -> str:
    """Devuelve la dirección emisora (hot wallet) del SUT, observada black-box.

    La spec no publica la emisora por API: se descubre ejecutando un retiro
    mínimo real y leyendo el campo `from` de su transacción. Deja el retiro
    CONFIRMED (sin estado en vuelo). Requiere fondear 0.002 ETH.
    """
    fondear_eth(usuario, rpc, 2 * MIN_WITHDRAWAL_ETH)  # cubre mínimo + fee_red
    resp = crear_retiro(usuario, "ETH", str(MIN_WITHDRAWAL_ETH), destino_fresco())
    assert resp.status_code == 202, resp.text
    _, tx, _ = confirmar_retiro(usuario, rpc, resp.json()["withdrawalId"])
    return tx["from"]


# --------------------------------------------------------------------------------
# Asserts sobre la transacción firmada (INV-6, HU-08-03)
# --------------------------------------------------------------------------------


def assert_tx_legacy_eip155(tx: dict) -> None:
    """Firma legacy (Type-0, TX_TYPE=legacy) conforme EIP-155 con chainId 11155111.

    - `type` (si el nodo lo reporta) debe ser 0x0 (README épica 08: TX_TYPE=legacy).
    - `v` ∈ {2·11155111+35, 2·11155111+36}: el chainId está EN la firma (INV-6).
    - `chainId` (si el nodo lo reporta) == 11155111.
    """
    if tx.get("type") is not None:
        assert hex_int(tx["type"]) == 0, f"la transacción no es legacy Type-0: {tx['type']!r}"
    v = hex_int(tx["v"])
    assert v in V_EIP155, (
        f"v={v} no corresponde a una firma EIP-155 con chainId {CHAIN_ID} "
        f"(esperado uno de {sorted(V_EIP155)}): la tx no es anti-replay (INV-6)"
    )
    if tx.get("chainId") is not None:
        assert hex_int(tx["chainId"]) == CHAIN_ID, (
            f"chainId {hex_int(tx['chainId'])} ≠ {CHAIN_ID} (INV-6)"
        )


# --------------------------------------------------------------------------------
# Control del mundo on-chain (métodos anvil/evm del nodo del entorno)
# --------------------------------------------------------------------------------


def automine(rpc, activo: bool) -> None:
    rpc.llamar("evm_setAutomine", [activo])


def set_balance(rpc, direccion: str, wei: int) -> None:
    rpc.llamar("anvil_setBalance", [direccion, hex(wei)])


def set_code(rpc, direccion: str, code: str) -> None:
    rpc.llamar("anvil_setCode", [direccion, code])


def get_code(rpc, direccion: str) -> str:
    return rpc.llamar("eth_getCode", [direccion, "latest"])


def drop_tx(rpc, tx_hash: str) -> None:
    rpc.llamar("anvil_dropTransaction", [tx_hash])


def snapshot(rpc) -> str:
    return rpc.llamar("evm_snapshot")


def revert(rpc, snapshot_id: str) -> bool:
    return rpc.llamar("evm_revert", [snapshot_id])


def tx_impersonada(rpc, desde: str, hacia: str = CUENTA_TESORERIA,
                   valor_wei: int = 0, nonce: int | None = None) -> str:
    """Envía una transacción "como si" fuera `desde` (anvil impersonation).

    Sirve para ocupar un nonce de la dirección emisora del SUT con una tx
    competidora (HU-08-03 RN-4, HU-08-04 RN-9 "el nonce fue ocupado por otra tx").
    """
    rpc.llamar("anvil_impersonateAccount", [desde])
    try:
        tx = {
            "from": desde,
            "to": hacia,
            "value": hex(valor_wei),
            "gas": hex(21_000),
            # supera el snapshot de 20 gwei del SUT: si compite en el mempool por
            # el mismo nonce, el reemplazo no queda "underpriced"
            "gasPrice": hex(2 * GAS_PRICE_WEI),
        }
        if nonce is not None:
            tx["nonce"] = hex(nonce)
        return rpc.llamar("eth_sendTransaction", [tx])
    finally:
        rpc.llamar("anvil_stopImpersonatingAccount", [desde])


def destino_revertidor(rpc) -> str:
    """Dirección fresca con código que revierte toda transferencia entrante.

    Provoca de forma determinista una tx de retiro ETH minada con status = 0
    (HU-08-04 RN-1 disparador (a), AT-08-04-05).
    """
    direccion = destino_fresco()
    set_code(rpc, direccion, CODE_REVIERTE)
    return direccion


# --------------------------------------------------------------------------------
# Re-serialización RLP de una tx legacy (para re-broadcast tras una reorg simulada)
# --------------------------------------------------------------------------------


def _rlp_item(b: bytes) -> bytes:
    if len(b) == 1 and b[0] < 0x80:
        return b
    if len(b) <= 55:
        return bytes([0x80 + len(b)]) + b
    largo = len(b).to_bytes((len(b).bit_length() + 7) // 8, "big")
    return bytes([0xB7 + len(largo)]) + largo + b


def _rlp_lista(items: list[bytes]) -> bytes:
    payload = b"".join(_rlp_item(i) for i in items)
    if len(payload) <= 55:
        return bytes([0xC0 + len(payload)]) + payload
    largo = len(payload).to_bytes((len(payload).bit_length() + 7) // 8, "big")
    return bytes([0xF7 + len(largo)]) + largo + payload


def _bytes_de_hex(h: str) -> bytes:
    h = h[2:] if h.startswith("0x") else h
    if len(h) % 2:
        h = "0" + h
    return bytes.fromhex(h)


def _bytes_de_cantidad(h: str) -> bytes:
    v = int(h, 16)
    return b"" if v == 0 else v.to_bytes((v.bit_length() + 7) // 8, "big")


def raw_tx_legacy(tx: dict) -> str:
    """Reconstruye la raw transaction (RLP) de una tx legacy firmada del nodo.

    Se auto-verifica: keccak256(rlp) debe coincidir con tx.hash (si no, el
    encoding está mal y NO debe re-broadcastearse).
    """
    campos = [
        _bytes_de_cantidad(tx["nonce"]),
        _bytes_de_cantidad(tx["gasPrice"]),
        _bytes_de_cantidad(tx["gas"]),
        _bytes_de_hex(tx["to"]),
        _bytes_de_cantidad(tx["value"]),
        _bytes_de_hex(tx.get("input") or "0x"),
        _bytes_de_cantidad(tx["v"]),
        _bytes_de_cantidad(tx["r"]),
        _bytes_de_cantidad(tx["s"]),
    ]
    rlp = _rlp_lista(campos)
    digest = keccak.new(digest_bits=256, data=rlp).hexdigest()
    assert "0x" + digest == tx["hash"].lower(), (
        f"re-encoding RLP inconsistente: keccak(rlp)=0x{digest} ≠ hash {tx['hash']}"
    )
    return "0x" + rlp.hex()
