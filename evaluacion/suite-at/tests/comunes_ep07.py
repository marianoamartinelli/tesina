"""Utilidades compartidas de los tests de la épica 07 (depósitos on-chain).

Sólo para ``tests/test_ep07_*.py`` (módulo compartido por épica, HELPERS.md
§"El patrón completo"). Dos grupos:

1. Consultas REST del recurso depósito (HU-07-03 RN-11/RN-12; épica 09
   HU-09-01 RN-17) y esperas sin sleeps fijos (``helpers.espera``).
2. Control on-chain adicional del anvil local que ``helpers/onchain.py`` no
   expone y la épica 07 necesita para provocar sus escenarios: snapshot/revert
   (reorgs), replay de la misma raw tx (reinclusión con el MISMO txHash),
   ``anvil_setCode`` (tx ETH revertida, contrato "batcher" para dos ``Transfer``
   en una tx) y despliegue de un segundo ERC-20. Todas estas operaciones fueron
   validadas contra el anvil del entorno (imagen ``foundry:stable``,
   chainId 11155111) antes de escribir los tests.

Nota de rate limit (HU-09-02 RN-12: 60 req/min por cuenta y endpoint): las
esperas de este módulo usan un intervalo de polling de 1.2 s (≈ 50 req/min en
régimen), para no gatillar el límite del SUT durante esperas largas.
"""

import re
import secrets
from pathlib import Path

from helpers.espera import esperar_hasta
from helpers.montos import CONFIRMACIONES_REQUERIDAS, a_int, es_monto_valido
from helpers.onchain import CUENTA_TESORERIA, SELECTOR_TRANSFER

# Intervalo de polling que respeta el rate limit por cuenta y endpoint (ver arriba).
INTERVALO_POLL = 1.2
# Las transiciones que dependen de que el SUT detecte una reorg (walk-back por
# parentHash + reevaluación, HU-07-04 RN-11) pueden demorar más de un ciclo de
# polling del indexador: se les da un timeout más holgado.
TIMEOUT_REORG = 90.0

# Cuentas 1 y 2 de anvil (mnemonic canónico de Hardhat/Anvil, HU-06-02):
# desbloqueadas y prefondeadas con ETH para gas. La 0 (tesorería) ya la usa
# helpers/onchain.py; estas dos sirven de remitentes auxiliares cuando el test
# necesita controlar el nonce/balance del emisor (replays tras reorg).
CUENTA_AUX_1 = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"
CUENTA_AUX_2 = "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC"

# topic0 canónico de Transfer(address,address,uint256) (HU-07-02 RN-1).
TOPIC0_TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

SELECTOR_APPROVE = "0x095ea7b3"  # approve(address,uint256)

# Runtime EVM que revierte toda llamada entrante: PUSH1 0, PUSH1 0, REVERT.
# Instalado con anvil_setCode permite obtener receipt status = 0 para una
# transferencia directa de ETH (única forma de provocar ese receipt con
# `to` = EOA-como-dirección-de-depósito en el entorno local).
CODIGO_REVERT = "0x60006000fd"

# Bytecode del .bin vendoreado del entorno (para desplegar un SEGUNDO token,
# distinto del USDC-mock configurado — HU-07-02 RN-2). Sólo lectura.
RUTA_BIN_USDC_MOCK = Path(__file__).resolve().parents[1] / "entorno" / "usdc-mock.bin"

RE_TXHASH_NORMALIZADO = re.compile(r"^0x[0-9a-f]{64}$")  # minúsculas (HU-07-03 RN-12)


# ------------------------------------------------------------------------------
# Recurso depósito por REST (HU-07-03 RN-12; épica 09 HU-09-01 RN-17)
# ------------------------------------------------------------------------------


def id_deposito(tx_hash: str, log_index: int) -> str:
    """``depositId = "<txHash>:<logIndex>"`` con txHash normalizado a minúsculas
    (HU-07-03 RN-12)."""
    return f"{tx_hash.lower()}:{log_index}"


def direccion_deposito(usuario, asset: str) -> str:
    """Dirección de depósito de la cuenta para `asset` (épica 09 RN-10)."""
    resp = usuario.api.get("/deposit-address", params={"asset": asset})
    assert resp.status_code == 200, f"deposit-address falló: {resp.status_code} {resp.text[:300]}"
    return resp.json()["address"]


def balance_de(usuario, asset: str) -> dict:
    """Fila de GET /balances para `asset` (épica 09 RN-9)."""
    resp = usuario.api.get("/balances")
    assert resp.status_code == 200, f"balances falló: {resp.status_code} {resp.text[:300]}"
    return next(b for b in resp.json() if b["asset"] == asset)


def deposito_o_none(usuario, dep_id: str) -> dict | None:
    """GET /deposits/{depositId}: el objeto depósito si responde 200, si no None."""
    resp = usuario.api.get(f"/deposits/{dep_id}")
    return resp.json() if resp.status_code == 200 else None


def listar_depositos(usuario, **params) -> list[dict]:
    """Items de GET /deposits (filtros opcionales asset/status, RN-12/RN-17)."""
    resp = usuario.api.get("/deposits", params=params or None)
    assert resp.status_code == 200, f"GET /deposits falló: {resp.status_code} {resp.text[:300]}"
    cuerpo = resp.json()
    assert "items" in cuerpo and "nextCursor" in cuerpo, cuerpo  # envelope RN-17
    return cuerpo["items"]


def esperar_deposito(usuario, dep_id: str, timeout: float | None = None) -> dict:
    """Espera a que el depósito sea visible por REST (detección, HU-07-01/02)."""
    return esperar_hasta(
        lambda: deposito_o_none(usuario, dep_id),
        timeout=timeout,
        intervalo=INTERVALO_POLL,
        mensaje=f"el depósito {dep_id} nunca fue detectado (GET /deposits/{{id}} sin 200)",
    )


def esperar_estado_deposito(usuario, dep_id: str, estado: str, timeout: float | None = None) -> dict:
    """Espera a que el depósito exista y esté en `estado` (máquina de estados
    del README de la épica 07)."""

    def _en_estado():
        dep = deposito_o_none(usuario, dep_id)
        return dep if dep is not None and dep.get("status") == estado else None

    return esperar_hasta(
        _en_estado,
        timeout=timeout,
        intervalo=INTERVALO_POLL,
        mensaje=f"el depósito {dep_id} no llegó al estado {estado}",
    )


def esperar_confirmaciones(usuario, dep_id: str, n: int, timeout: float | None = None) -> dict:
    """Espera a que la consulta reporte exactamente `n` confirmaciones.

    Con la cadena detenida en cabeza = bloque_de_inclusión + n (minado a
    demanda), `confirmaciones = max(0, cabeza − bloque)` = n es un valor
    estable (HU-07-03 RN-1): la espera es determinista, sin sleeps.
    """

    def _con_confirmaciones():
        dep = deposito_o_none(usuario, dep_id)
        return dep if dep is not None and dep.get("confirmations") == n else None

    return esperar_hasta(
        _con_confirmaciones,
        timeout=timeout,
        intervalo=INTERVALO_POLL,
        mensaje=f"el depósito {dep_id} no llegó a reportar confirmations == {n}",
    )


def esperar_deposito_en_bloque(usuario, dep_id: str, bloque: int, timeout: float | None = None) -> dict:
    """Espera a que la consulta muestre el depósito con `blockNumber == bloque`.

    Sirve para confirmar que el SUT observó UNA inclusión específica de la
    identidad (p. ej. la reinclusión en B' tras una reorg, HU-07-04 RN-6/RN-12).
    """

    def _en_bloque():
        dep = deposito_o_none(usuario, dep_id)
        return dep if dep is not None and dep.get("blockNumber") == bloque else None

    return esperar_hasta(
        _en_bloque,
        timeout=timeout,
        intervalo=INTERVALO_POLL,
        mensaje=f"el depósito {dep_id} no fue observado en el bloque {bloque}",
    )


def esperar_disponible_exacto(usuario, asset: str, monto_min_unit: int, timeout: float | None = None) -> dict:
    """Espera a que `available` del activo sea exactamente `monto_min_unit`
    (comparación estricta de enteros de unidad mínima, nunca tolerancia)."""

    def _disponible_exacto():
        fila = balance_de(usuario, asset)
        return fila if a_int(fila["available"]) == monto_min_unit else None

    return esperar_hasta(
        _disponible_exacto,
        timeout=timeout,
        intervalo=INTERVALO_POLL,
        mensaje=f"available de {asset} no llegó exactamente a {monto_min_unit}",
    )


def es_entero_json(valor) -> bool:
    """Conteos/índices (`confirmations`, `required`, `logIndex`, `blockNumber`)
    viajan como enteros JSON, no strings (convenciones-monetarias §5)."""
    return isinstance(valor, int) and not isinstance(valor, bool)


def assert_esquema_deposito(dep: dict) -> None:
    """Esquema del objeto <deposito> (HU-07-03 RN-12; épica 09 RN-17)."""
    # montos como string entero; conteos/índices como enteros JSON
    assert es_monto_valido(dep["amountMinUnit"]), dep
    for campo in ("confirmations", "required", "logIndex", "blockNumber"):
        assert es_entero_json(dep[campo]), f"{campo} debe ser entero JSON: {dep!r}"
    assert dep["required"] == CONFIRMACIONES_REQUERIDAS, dep  # required = 12 (RN-8)
    assert dep["asset"] in ("ETH", "USDC"), dep
    assert dep["status"] in ("PENDIENTE", "ACREDITADO", "DESCARTADO"), dep
    # txHash normalizado a minúsculas (RN-12) e identidad compuesta
    assert RE_TXHASH_NORMALIZADO.fullmatch(dep["txHash"]), dep
    assert dep["depositId"] == f"{dep['txHash']}:{dep['logIndex']}", dep
    assert isinstance(dep["createdAt"], str) and isinstance(dep["updatedAt"], str), dep
    # creditedAt sólo si ACREDITADO; discardReason ∈ {REORG, REVERTED} sólo si DESCARTADO
    if dep["status"] == "ACREDITADO":
        assert dep.get("creditedAt"), dep
    else:
        assert not dep.get("creditedAt"), dep
    if dep["status"] == "DESCARTADO":
        assert dep.get("discardReason") in ("REORG", "REVERTED"), dep
    else:
        assert not dep.get("discardReason"), dep


# ------------------------------------------------------------------------------
# Control on-chain adicional (anvil) — sólo tests de la épica 07
# ------------------------------------------------------------------------------


def _abi_direccion(direccion: str) -> str:
    return direccion.lower().replace("0x", "").rjust(64, "0")


def _abi_uint256(valor: int) -> str:
    return format(valor, "x").rjust(64, "0")


def _usdc_configurado(rpc) -> str:
    assert rpc.direccion_usdc, "falta EVAL_USDC_ADDRESS (ver entorno/README.md)"
    return rpc.direccion_usdc


def bloque_de_inclusion(rpc, tx_hash: str) -> int:
    """Número de bloque que incluye la transacción (int)."""
    return int(rpc.esperar_receipt(tx_hash)["blockNumber"], 16)


def log_index_unico(rpc, tx_hash: str) -> int:
    """`logIndex` global (block-scoped, HU-07-02 RN-7) del ÚNICO log del receipt."""
    logs = rpc.esperar_receipt(tx_hash)["logs"]
    assert len(logs) == 1, f"se esperaba exactamente 1 log en {tx_hash}: {logs!r}"
    return int(logs[0]["logIndex"], 16)


def snapshot(rpc) -> str:
    """`evm_snapshot`: id de snapshot para revertir la cadena (simular reorgs)."""
    return rpc.llamar("evm_snapshot")


def revertir_a(rpc, snap_id: str) -> None:
    """`evm_revert`: vuelve la cadena al snapshot (los bloques posteriores quedan
    huérfanos). Adelanta el reloj 2 s para que los bloques re-minados a las
    mismas alturas tengan hash distinto de los huérfanos (la reorg queda
    detectable por parentHash, HU-07-04 RN-11). Un snapshot sólo puede
    revertirse una vez (semántica de anvil)."""
    ok = rpc.llamar("evm_revert", [snap_id])
    assert ok is True, f"evm_revert({snap_id}) devolvió {ok!r}"
    rpc.llamar("evm_increaseTime", [2])


def tx_cruda(rpc, tx_hash: str) -> str:
    """RLP firmado de una tx incluida (capturarlo ANTES de revertir el snapshot:
    después del revert la tx ya no existe en el nodo)."""
    try:
        return rpc.llamar("debug_getRawTransaction", [tx_hash])
    except RuntimeError:
        return rpc.llamar("eth_getRawTransactionByHash", [tx_hash])


def reenviar_tx_cruda(rpc, raw: str) -> str:
    """Reinyecta la MISMA transacción firmada (mismo txHash) tras un revert:
    reinclusión de la identidad `(txHash, logIndex)` en un bloque nuevo
    (HU-07-04 RN-6/RN-12). Devuelve el txHash (idéntico al original)."""
    tx_hash = rpc.llamar("eth_sendRawTransaction", [raw])
    rpc.esperar_receipt(tx_hash)
    return tx_hash


def set_code(rpc, direccion: str, codigo: str) -> None:
    """`anvil_setCode`: instala (o borra, con "0x") código en una dirección."""
    rpc.llamar("anvil_setCode", [direccion, codigo])


def enviar_eth_con_gas(rpc, hacia: str, valor_wei: int, desde: str = CUENTA_TESORERIA, gas: int = 100_000):
    """Transferencia de ETH con gas explícito (evita la estimación de gas del
    nodo, que fallaría si el destino revierte). Devuelve (tx_hash, receipt)."""
    tx = {"from": desde, "to": hacia, "value": hex(valor_wei), "gas": hex(gas)}
    tx_hash = rpc.llamar("eth_sendTransaction", [tx])
    return tx_hash, rpc.esperar_receipt(tx_hash)


def crear_contrato_con_valor(rpc, valor_wei: int):
    """Transacción de CREACIÓN de contrato (`to = null`) con `value > 0`
    (HU-07-01 Escenario 9). Init code vacío ⇒ despliega un contrato sin código
    que acepta el valor. Devuelve (tx_hash, receipt)."""
    tx = {"from": CUENTA_TESORERIA, "data": "0x", "value": hex(valor_wei), "gas": hex(100_000)}
    tx_hash = rpc.llamar("eth_sendTransaction", [tx])
    return tx_hash, rpc.esperar_receipt(tx_hash)


def desplegar_otro_erc20(rpc) -> str:
    """Despliega una SEGUNDA instancia del bytecode del mock: un token con la
    misma interfaz pero dirección distinta del USDC-mock configurado. Sus logs
    `Transfer` deben ignorarse (HU-07-02 RN-2)."""
    bytecode = RUTA_BIN_USDC_MOCK.read_text().strip()
    tx = {"from": CUENTA_TESORERIA, "data": "0x" + bytecode, "gas": hex(2_000_000)}
    tx_hash = rpc.llamar("eth_sendTransaction", [tx])
    receipt = rpc.esperar_receipt(tx_hash)
    assert receipt["status"] == "0x1", receipt
    return receipt["contractAddress"]


def aprobar_usdc(rpc, spender: str, monto_usdcmin: int):
    """`approve()` del USDC-mock REAL: emite un log del contrato configurado con
    `topic0` ≠ Transfer (Approval) — HU-07-02 RN-1/Escenario 5.
    Devuelve (tx_hash, receipt)."""
    data = SELECTOR_APPROVE[2:] + _abi_direccion(spender) + _abi_uint256(monto_usdcmin)
    tx = {"from": CUENTA_TESORERIA, "to": _usdc_configurado(rpc), "data": "0x" + data, "gas": hex(100_000)}
    tx_hash = rpc.llamar("eth_sendTransaction", [tx])
    return tx_hash, rpc.esperar_receipt(tx_hash)


def direccion_eoa_ajena() -> str:
    """EOA aleatoria, no asignada a ninguna cuenta del SUT (colisión con una
    dirección derivada por su HD wallet: probabilidad despreciable)."""
    return "0x" + secrets.token_hex(20)


# ------------------------------------------------------------------------------
# Batcher: dos logs Transfer del USDC-mock en UNA transacción (HU-07-02 Esc. 2)
# ------------------------------------------------------------------------------

# Dirección arbitraria sin código donde se instala el batcher (anvil_setCode).
DIRECCION_BATCHER = "0x00000000000000000000000000000000000b47c4"

# Runtime EVM handcrafteado (validado contra el anvil del entorno). Interpreta
# su calldata como: token(32 bytes, address left-padded) || payload1(68 bytes)
# || payload2(68 bytes), y ejecuta CALL(token, payload1) y CALL(token, payload2)
# revirtiendo si alguna falla. Desensamblado:
#   0x00 6044 6020 6000 37   CALLDATACOPY(mem 0, calldata 0x20, 0x44)  ; payload1
#   0x07 6000 6000 6044      retSize, retOffset, argsSize
#   0x0d 6000 6000           argsOffset, value
#   0x11 6000 35             CALLDATALOAD(0x00)                        ; token
#   0x14 5a f1               GAS, CALL
#   0x16 601e 57             JUMPI a 0x1e si éxito
#   0x19 6000 6000 fd        REVERT
#   0x1e 5b                  JUMPDEST
#   0x1f 6044 6064 6000 37   CALLDATACOPY(mem 0, calldata 0x64, 0x44)  ; payload2
#   0x26 6000 6000 6044 6000 6000  (ídem CALL)
#   0x30 6000 35 5a f1
#   0x35 603d 57             JUMPI a 0x3d si éxito
#   0x38 6000 6000 fd        REVERT
#   0x3d 5b 00               JUMPDEST, STOP
BYTECODE_BATCHER = (
    "0x"
    "604460206000" "37"
    "60006000604460006000" "6000" "35" "5a" "f1"
    "601e57" "60006000fd" "5b"
    "604460646000" "37"
    "60006000604460006000" "6000" "35" "5a" "f1"
    "603d57" "60006000fd" "5b"
    "00"
)


def transferencia_usdc_doble(rpc, hacia_1: str, monto_1: int, hacia_2: str, monto_2: int):
    """UNA transacción que emite DOS eventos `Transfer` del USDC-mock
    configurado, hacia dos destinatarios distintos (HU-07-02 Escenario 2).

    Instala el batcher, le mintea el total (mint público del mock) y lo invoca;
    el batcher encadena token.transfer(hacia_1, monto_1) y
    token.transfer(hacia_2, monto_2) dentro de la misma transacción.

    Devuelve (tx_hash, log_index_1, log_index_2) con los `logIndex` globales
    del bloque (block-scoped, HU-07-02 RN-7), en el orden de los payloads.
    """
    token = _usdc_configurado(rpc)
    set_code(rpc, DIRECCION_BATCHER, BYTECODE_BATCHER)
    rpc.mint_usdc(DIRECCION_BATCHER, monto_1 + monto_2)
    sel = SELECTOR_TRANSFER[2:]
    calldata = (
        "0x"
        + _abi_direccion(token)
        + sel + _abi_direccion(hacia_1) + _abi_uint256(monto_1)
        + sel + _abi_direccion(hacia_2) + _abi_uint256(monto_2)
    )
    tx = {"from": CUENTA_TESORERIA, "to": DIRECCION_BATCHER, "data": calldata, "gas": hex(300_000)}
    tx_hash = rpc.llamar("eth_sendTransaction", [tx])
    receipt = rpc.esperar_receipt(tx_hash)
    assert receipt["status"] == "0x1", receipt
    logs = receipt["logs"]
    assert len(logs) == 2, f"se esperaban 2 logs Transfer, hay {len(logs)}: {logs!r}"
    # los logs se emiten en el orden de las CALLs: logs[0] → hacia_1, logs[1] → hacia_2
    return tx_hash, int(logs[0]["logIndex"], 16), int(logs[1]["logIndex"], 16)


# ------------------------------------------------------------------------------
# Depósito centinela (baliza de avance del indexador)
# ------------------------------------------------------------------------------


def acreditar_centinela(usuario, rpc, asset: str = "USDC") -> int:
    """Deposita y espera acreditar un depósito 'centinela' del usuario.

    El indexador del SUT procesa los bloques EN ORDEN desde su checkpoint
    (épica 07 README, "Bloque de inicio y checkpoint"): cuando la acreditación
    del centinela es visible, todo bloque anterior al suyo ya fue procesado.
    Sirve para afirmar de forma determinista —sin sleeps— que un evento
    anterior fue ignorado (tx revertida, valor cero, destino no asignado,
    contrato equivocado, etc.).

    Usar un `asset` DISTINTO del activo bajo prueba cuando el test asserta el
    balance de este último. Devuelve el monto del centinela (unidad mínima).
    """
    direccion = direccion_deposito(usuario, asset)
    if asset == "USDC":
        monto = 1_000_000  # 1 USDC
        tx_hash = rpc.depositar_usdc(direccion, monto)  # transfer + 12 bloques
        dep_id = id_deposito(tx_hash, log_index_unico(rpc, tx_hash))
    else:
        monto = 10**15  # 0.001 ETH
        tx_hash = rpc.depositar_eth(direccion, monto)
        dep_id = id_deposito(tx_hash, 0)  # ETH nativo: logIndex = 0 (INV-5)
    esperar_estado_deposito(usuario, dep_id, "ACREDITADO")
    return monto
