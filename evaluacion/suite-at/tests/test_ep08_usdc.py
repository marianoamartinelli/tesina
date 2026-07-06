"""Épica 08 — HU-08-05 (retiro de USDC vía ERC-20 `transfer`): reserva dual
(USDC + gas en ETH), campos exactos de la transacción ERC-20, evento Transfer
como condición de CONFIRMED y reconciliaciones duales.

La transacción real se inspecciona por JSON-RPC: `to` = contrato USDC-mock,
`value` = 0, `data` = ABI de transfer(destino, amount), `gas` = 100000,
`gasPrice` = snapshot (20 gwei), firma legacy EIP-155 chainId 11155111 (INV-6).
"""

import pytest

from helpers.errores import assert_error
from helpers.montos import a_int

from comunes_ep08 import (
    CODE_RETORNA_TRUE,
    CODE_REVIERTE,
    FEE_RED_ERC20,
    GAS_LIMIT_ERC20,
    GAS_PRICE_WEI,
    TOPIC_TRANSFER,
    assert_tx_legacy_eip155,
    automine,
    balance_de,
    confirmar_retiro,
    crear_retiro,
    data_transfer,
    destino_fresco,
    drop_tx,
    esperar_broadcast,
    esperar_retiro,
    fondear_eth,
    fondear_usdc,
    foto_balances,
    get_code,
    hex_int,
    set_code,
    tx_impersonada,
    usdc_del_entorno,
)

USDC_25 = 25_000_000
ETH_GAS = 10**16  # 0.01 ETH de fondeo para gas (≥ fee_red = 0.002 ETH)


def _fondear_para_retiro_usdc(usuario, rpc, usdcmin: int = 50_000_000, eth: int = ETH_GAS):
    """Dado común: USDC para el principal + ETH para la previsión de gas."""
    fondear_usdc(usuario, rpc, usdcmin)
    fondear_eth(usuario, rpc, eth)


@pytest.mark.at("AT-08-05-01")
def test_retiro_usdc_exitoso_de_punta_a_punta(usuario, rpc):
    """HU-08-05 Escenario 1: retiro de USDC exitoso (feliz).

    - Dado disponible(USDC) = 50 USDC y ETH para gas; fee_red_wei =
      100000 × 20 gwei = "2000000000000000" (RN-2; el Gherkin ilustra con 5 gwei,
      el entorno fija GAS_PRICE_WEI = 20 gwei)
    - Cuando solicita y se procesa un retiro de 25 USDC
    - Entonces se bloquean 25 USDC y fee_red_wei ETH (reserva dual, RN-3); se
      firma transfer(destino, 25000000) al USDC-mock con chainId 11155111,
      gas_limit 100000 y value 0 (RN-1/RN-4)
    - Y al confirmar (status 1 + Transfer + 12 confs) consume el USDC y el gas
      usado, liberando el sobrante de gas (RN-5/RN-6)
    """
    # Dado
    usdc = usdc_del_entorno(rpc)
    _fondear_para_retiro_usdc(usuario, rpc)
    destino = destino_fresco()

    # Cuando
    resp = crear_retiro(usuario, "USDC", str(USDC_25), destino)
    assert resp.status_code == 202, resp.text
    wid = resp.json()["withdrawalId"]

    # Entonces: reserva dual exacta (RN-3)
    reservado = foto_balances(usuario)
    assert reservado["USDC"] == (USDC_25, USDC_25, 50_000_000)
    assert reservado["ETH"] == (ETH_GAS - FEE_RED_ERC20, FEE_RED_ERC20, ETH_GAS)

    # Y: la transacción ERC-20 firmada es exacta (RN-1/RN-4)
    _, tx = esperar_broadcast(usuario, rpc, wid)
    assert tx["to"].lower() == usdc.lower()
    assert hex_int(tx["value"]) == 0
    assert tx["input"].lower() == data_transfer(destino, USDC_25).lower()
    assert hex_int(tx["gas"]) == GAS_LIMIT_ERC20
    assert_tx_legacy_eip155(tx)

    # Y: al confirmar, reconciliación dual exacta (RN-6)
    _, _, receipt = confirmar_retiro(usuario, rpc, wid)
    gas_usado = hex_int(receipt["gasUsed"]) * GAS_PRICE_WEI
    final = foto_balances(usuario)
    assert final["USDC"] == (USDC_25, 0, USDC_25)                       # −25 USDC
    assert final["ETH"] == (ETH_GAS - gas_usado, 0, ETH_GAS - gas_usado)  # −gas usado
    assert rpc.balance_usdc(destino) == USDC_25                          # llegó al destino


@pytest.mark.at("AT-08-05-02")
def test_campos_de_la_transaccion_erc20(usuario, rpc):
    """HU-08-05 Escenario 2 (campos de la transacción ERC-20).

    - Dado un retiro de USDC a un destino EIP-55 por 25 USDC
    - Cuando se construye la transacción
    - Entonces to = contrato USDC-mock, value = "0", data = encoding de
      transfer(destino, 25000000) (RN-1)
    - Y no se transfiere ETH como value nativo (el ETH sólo paga gas, RN-2)
    """
    # Dado
    usdc = usdc_del_entorno(rpc)
    _fondear_para_retiro_usdc(usuario, rpc)
    destino = destino_fresco()

    # Cuando
    resp = crear_retiro(usuario, "USDC", str(USDC_25), destino)
    assert resp.status_code == 202, resp.text

    # Entonces
    _, tx = esperar_broadcast(usuario, rpc, resp.json()["withdrawalId"])
    assert tx["to"].lower() == usdc.lower(), "to debe ser el contrato USDC-mock (RN-1)"
    assert hex_int(tx["value"]) == 0, "value nativo debe ser 0 (RN-1/RN-2)"
    data = tx["input"].lower()
    assert data == data_transfer(destino, USDC_25).lower(), (
        f"data ≠ ABI de transfer({destino}, {USDC_25}): {data}"
    )


@pytest.mark.at("AT-08-05-04")
def test_falta_usdc_para_el_principal(usuario, rpc):
    """HU-08-05 Escenario 4 (borde): falta USDC para el principal.

    - Dado disponible(USDC) = 10 USDC y ETH suficiente para gas
    - Cuando intenta retirar 25 USDC
    - Entonces INSUFFICIENT_FUNDS con asset = "USDC", required = "25000000",
      available = "10000000" (RN-3)
    - Y no se bloquea ETH
    """
    # Dado
    _fondear_para_retiro_usdc(usuario, rpc, usdcmin=10_000_000)
    antes = foto_balances(usuario)

    # Cuando
    resp = crear_retiro(usuario, "USDC", str(USDC_25), destino_fresco())

    # Entonces
    err = assert_error(resp, "INSUFFICIENT_FUNDS")
    details = err.get("details") or {}
    assert details.get("asset") == "USDC"
    assert details.get("required") == "25000000"
    assert details.get("available") == "10000000"

    # Y: nada bloqueado en ninguno de los dos activos
    assert foto_balances(usuario) == antes


@pytest.mark.at("AT-08-05-04b")
def test_ambos_activos_insuficientes_precede_usdc(usuario, rpc):
    """HU-08-05 Escenario 4b (borde): ambos activos insuficientes → precede USDC.

    - Dado disponible(USDC) = 10 USDC (< 25) Y disponible(ETH) = 0.0001 ETH
      (< fee_red_wei)
    - Cuando intenta retirar 25 USDC
    - Entonces INSUFFICIENT_FUNDS con asset = "USDC" (la precedencia verifica
      USDC antes que ETH; RN-3, HU-08-01 RN-9)
    - Y no se bloquea ningún activo (atomicidad de la reserva dual, INV-4)
    """
    # Dado
    _fondear_para_retiro_usdc(usuario, rpc, usdcmin=10_000_000, eth=100_000_000_000_000)
    antes = foto_balances(usuario)

    # Cuando
    resp = crear_retiro(usuario, "USDC", str(USDC_25), destino_fresco())

    # Entonces
    err = assert_error(resp, "INSUFFICIENT_FUNDS")
    details = err.get("details") or {}
    assert details.get("asset") == "USDC", "la precedencia evalúa USDC antes que ETH"
    assert details.get("required") == "25000000"
    assert details.get("available") == "10000000"

    # Y
    assert foto_balances(usuario) == antes


@pytest.mark.at("AT-08-05-05")
def test_transfer_revierte_usdc_se_reacredita_y_el_gas_se_consume(usuario, rpc):
    """HU-08-05 Escenario 5 (FAILED revertida): el transfer revierte.

    - Dado un retiro de USDC cuya transacción se mina pero revierte (status = 0;
      se provoca reemplazando el código del USDC-mock por un stub que revierte)
    - Cuando se reconcilia como FAILED
    - Entonces se reacredita el USDC (no se transfirió), se consume gas_usado_wei
      en ETH y se libera fee_red − gas_usado (RN-7)
    - Y la suma total de USDC no cambia; la de ETH disminuye en gas_usado_wei (RN-9)
    """
    # Dado
    usdc = usdc_del_entorno(rpc)
    _fondear_para_retiro_usdc(usuario, rpc)
    destino = destino_fresco()
    codigo_original = get_code(rpc, usdc)

    set_code(rpc, usdc, CODE_REVIERTE)  # todo call al mock revierte (status = 0)
    try:
        resp = crear_retiro(usuario, "USDC", str(USDC_25), destino)
        assert resp.status_code == 202, resp.text
        wid = resp.json()["withdrawalId"]

        _, tx = esperar_broadcast(usuario, rpc, wid)
        receipt = rpc.esperar_receipt(tx["hash"])
        assert hex_int(receipt["status"]) == 0, "premisa: el transfer debía revertir"
        gas_usado = hex_int(receipt["gasUsed"]) * GAS_PRICE_WEI
        assert 0 < gas_usado < FEE_RED_ERC20  # hay sobrante de gas que liberar

        # Cuando (12 bloques por si el SUT espera confirmaciones para reconciliar)
        rpc.minar_bloques(12)
        retiro = esperar_retiro(
            usuario, wid, ("FAILED",), prohibidos=("CONFIRMED",), timeout=60, intervalo=1.0
        )
    finally:
        set_code(rpc, usdc, codigo_original)

    # Entonces
    assert retiro.get("failureReason") == "TX_REVERTED"
    final = foto_balances(usuario)
    assert final["USDC"] == (50_000_000, 0, 50_000_000)  # reacreditado; total sin cambio
    assert final["ETH"] == (ETH_GAS - gas_usado, 0, ETH_GAS - gas_usado)  # sólo el gas
    assert rpc.balance_usdc(destino) == 0


@pytest.mark.at("AT-08-05-06")
def test_failed_no_minada_libera_toda_la_reserva_dual(usuario, rpc):
    """HU-08-05 Escenario 6 (FAILED no minada): se libera toda la reserva dual.

    - Dado un retiro de USDC cuya transacción nunca se mina (descartada del
      mempool y con el nonce ocupado por otra tx; y vence el timeout de inclusión
      MAX_BLOCKS_PENDING)
    - Cuando se declara FAILED
    - Entonces se libera TODA la reserva: 25 USDC y fee_red_wei ETH vuelven a
      disponible (gas_usado_wei = 0, RN-7)
    - Y ninguna suma total por activo cambia (INV-1)
    """
    # Dado
    usdc_del_entorno(rpc)
    _fondear_para_retiro_usdc(usuario, rpc)
    antes = foto_balances(usuario)
    destino = destino_fresco()

    automine(rpc, False)
    try:
        resp = crear_retiro(usuario, "USDC", str(USDC_25), destino)
        assert resp.status_code == 202, resp.text
        wid = resp.json()["withdrawalId"]
        _, tx = esperar_broadcast(usuario, rpc, wid)   # en mempool, sin minar
        assert tx.get("blockNumber") is None
        drop_tx(rpc, tx["hash"])                       # descartada…
        tx_impersonada(rpc, tx["from"], nonce=hex_int(tx["nonce"]))  # …y nonce ocupado
    finally:
        automine(rpc, True)

    rpc.minar_bloques(52)  # > MAX_BLOCKS_PENDING desde el broadcast (timeout de inclusión)

    # Cuando / Entonces
    retiro = esperar_retiro(
        usuario, wid, ("FAILED",), prohibidos=("CONFIRMED",), timeout=120, intervalo=2.0
    )
    assert retiro.get("failureReason") == "TX_DROPPED"
    assert foto_balances(usuario) == antes  # reserva dual liberada completa; totales intactos
    assert rpc.balance_usdc(destino) == 0


@pytest.mark.at("AT-08-05-07")
def test_confirmacion_con_evento_transfer_correcto(usuario, rpc):
    """HU-08-05 Escenario 7 (confirmación con Transfer correcto).

    - Dado un retiro de USDC BROADCAST por 25 USDC
    - Cuando la tx se mina con status = 1 y emite Transfer(from = emisora,
      to = destino, value = 25000000) desde el USDC-mock, alcanzando 12 confs
    - Entonces pasa a CONFIRMED y la reconciliación consume 25 USDC + gas usado,
      liberando el sobrante (RN-5/RN-6)
    """
    # Dado
    usdc = usdc_del_entorno(rpc)
    _fondear_para_retiro_usdc(usuario, rpc)
    destino = destino_fresco()
    resp = crear_retiro(usuario, "USDC", str(USDC_25), destino)
    assert resp.status_code == 202, resp.text
    wid = resp.json()["withdrawalId"]

    # Cuando
    retiro, tx, receipt = confirmar_retiro(usuario, rpc, wid)

    # Entonces: el receipt contiene el Transfer esperado, emitido por el mock
    assert hex_int(receipt["status"]) == 1
    transfers = [
        log for log in receipt["logs"]
        if log["address"].lower() == usdc.lower()
        and log["topics"][0].lower() == TOPIC_TRANSFER
    ]
    assert len(transfers) == 1, f"se esperaba exactamente un Transfer del mock: {receipt['logs']!r}"
    log = transfers[0]
    assert int(log["topics"][1], 16) == int(tx["from"], 16)   # from = emisora
    assert int(log["topics"][2], 16) == int(destino, 16)      # to = destino del usuario
    assert int(log["data"], 16) == USDC_25                    # value = amount_usdc
    assert retiro["status"] == "CONFIRMED"
    assert rpc.balance_usdc(destino) == USDC_25


@pytest.mark.at("AT-08-05-08")
def test_anti_replay_y_nonce_de_la_tx_erc20(usuario, rpc):
    """HU-08-05 Escenario 8 (anti-replay y nonce — reutiliza HU-08-03).

    - Dado un retiro de USDC a firmar desde la dirección emisora
    - Cuando se firma y broadcastea
    - Entonces la tx ERC-20 lleva chainId = 11155111 (EIP-155) y un nonce
      único/secuencial/contiguo, igual que cualquier retiro (RN-4, INV-6)
    """
    # Dado
    usdc_del_entorno(rpc)
    _fondear_para_retiro_usdc(usuario, rpc)
    resp = crear_retiro(usuario, "USDC", str(USDC_25), destino_fresco())
    assert resp.status_code == 202, resp.text

    # Cuando / Entonces
    _, tx = esperar_broadcast(usuario, rpc, resp.json()["withdrawalId"])
    assert_tx_legacy_eip155(tx)  # chainId 11155111 en la firma (v EIP-155), tx legacy
    # contigüidad: la tx ya minada dejó el nonce de la emisora en tx.nonce + 1
    assert rpc.nonce(tx["from"]) == hex_int(tx["nonce"]) + 1, (
        "el nonce de la tx ERC-20 debe ser el siguiente contiguo de la emisora (INV-6)"
    )


@pytest.mark.at("AT-08-05-09")
def test_precision_de_decimales_usdc_6_gas_en_wei(usuario, rpc):
    """HU-08-05 Escenario 9 (precisión de decimales): USDC en 6 decimales, gas en wei.

    - Dado un retiro de amount = "1234567" (1.234567 USDC, exacto en 6 decimales)
    - Cuando se construye el transfer
    - Entonces el uint256 pasado es 1234567 (USDC-min), sin reescalar a 18
      decimales ni a float (RN-8)
    - Y la previsión de gas se computa por separado en wei (100000 × gas_price),
      sin mezclar unidades
    """
    # Dado
    usdc_del_entorno(rpc)
    _fondear_para_retiro_usdc(usuario, rpc, usdcmin=10_000_000)

    # Cuando
    resp = crear_retiro(usuario, "USDC", "1234567", destino_fresco())
    assert resp.status_code == 202, resp.text
    wid = resp.json()["withdrawalId"]

    # Entonces: reserva en unidades correctas (USDC-min y wei, sin mezclar)
    reservado = foto_balances(usuario)
    assert reservado["USDC"] == (10_000_000 - 1_234_567, 1_234_567, 10_000_000)
    assert reservado["ETH"][1] == FEE_RED_ERC20  # previsión en wei, aparte

    # Y: el uint256 del transfer es exactamente 1234567
    _, tx = esperar_broadcast(usuario, rpc, wid)
    data = tx["input"].lower()
    assert int(data[-64:], 16) == 1_234_567, f"uint256 del transfer reescalado o alterado: {data}"


@pytest.mark.at("AT-08-05-10")
def test_status_1_sin_transfer_esperado_es_failed_erc20(usuario, rpc):
    """HU-08-05 Escenario 10 (status = 1 sin el evento Transfer esperado → FAILED).

    - Dado un retiro de USDC cuya tx mina con status = 1 y 12 confirmaciones pero
      sin emitir el Transfer esperado (stub del mock que responde éxito sin logs)
    - Cuando se evalúa la confirmación (RN-5)
    - Entonces NO pasa a CONFIRMED: FAILED (análogo a revert), se reacredita el
      USDC y se consume gas_usado_wei en ETH, liberando fee_red − gas_usado (RN-5/RN-7)
    - Y la suma total de USDC no cambia; la de ETH baja en gas_usado_wei (RN-9)

    (Mismo caso, desde el seguimiento general, en AT-08-04-11; acá se verifica
    además que la solicitud y la reserva dual del ERC-20 quedaron íntegras.)
    """
    # Dado
    usdc = usdc_del_entorno(rpc)
    _fondear_para_retiro_usdc(usuario, rpc)
    destino = destino_fresco()
    codigo_original = get_code(rpc, usdc)

    set_code(rpc, usdc, CODE_RETORNA_TRUE)  # status = 1 sin ningún log
    try:
        resp = crear_retiro(usuario, "USDC", str(USDC_25), destino)
        assert resp.status_code == 202, resp.text
        wid = resp.json()["withdrawalId"]
        # reserva dual aplicada
        reservado = foto_balances(usuario)
        assert reservado["USDC"] == (USDC_25, USDC_25, 50_000_000)
        assert reservado["ETH"][1] == FEE_RED_ERC20

        _, tx = esperar_broadcast(usuario, rpc, wid)
        receipt = rpc.esperar_receipt(tx["hash"])
        assert hex_int(receipt["status"]) == 1, "premisa: status = 1"
        assert receipt.get("logs") in ([], None), "premisa: sin Transfer emitido"
        gas_usado = hex_int(receipt["gasUsed"]) * GAS_PRICE_WEI

        # Cuando
        rpc.minar_bloques(12)
        retiro = esperar_retiro(
            usuario, wid, ("FAILED",), prohibidos=("CONFIRMED",), timeout=60, intervalo=1.0
        )
    finally:
        set_code(rpc, usdc, codigo_original)

    # Entonces
    assert retiro.get("failureReason") == "TX_REVERTED"
    final = foto_balances(usuario)
    assert final["USDC"] == (50_000_000, 0, 50_000_000)
    assert final["ETH"] == (ETH_GAS - gas_usado, 0, ETH_GAS - gas_usado)
    assert rpc.balance_usdc(destino) == 0
