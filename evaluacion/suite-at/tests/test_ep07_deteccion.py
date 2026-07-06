"""Épica 07 — Depósitos on-chain: detección (HU-07-01 ETH nativo, HU-07-02 USDC ERC-20).

Tests black-box: el "Dado" se construye enviando ETH/USDC reales a la dirección
de depósito del usuario sobre el anvil local (fixture `rpc`), y el "Entonces"
se observa por el contrato REST de la épica 09 (GET /deposits, /deposits/{id},
/balances) más el estado on-chain. Confirmaciones por minado a demanda
(`rpc.minar_bloques`), esperas con `helpers.espera` (sin sleeps fijos).

Convenciones citadas: montos como string de entero en unidad mínima (wei /
USDC-min, convenciones-monetarias §5); identidad de depósito `(txHash,
logIndex)` con `logIndex = 0` para ETH nativo (INV-5); estado inicial
`PENDIENTE` (README épica 07, máquina de estados).
"""

import pytest

from helpers.errores import assert_error
from helpers.montos import a_int
from helpers.onchain import CUENTA_TESORERIA

from comunes_ep07 import (
    CODIGO_REVERT,
    CUENTA_AUX_1,
    CUENTA_AUX_2,
    TOPIC0_TRANSFER,
    acreditar_centinela,
    aprobar_usdc,
    assert_esquema_deposito,
    balance_de,
    bloque_de_inclusion,
    crear_contrato_con_valor,
    desplegar_otro_erc20,
    direccion_deposito,
    direccion_eoa_ajena,
    enviar_eth_con_gas,
    es_entero_json,
    esperar_deposito,
    esperar_disponible_exacto,
    esperar_estado_deposito,
    id_deposito,
    listar_depositos,
    log_index_unico,
    reenviar_tx_cruda,
    revertir_a,
    set_code,
    snapshot,
    transferencia_usdc_doble,
    tx_cruda,
)

# ==============================================================================
# HU-07-01 — Detección de depósito de ETH nativo
# ==============================================================================


@pytest.mark.at("AT-07-01-01")
def test_deteccion_deposito_eth_valido(usuario, rpc):
    """HU-07-01 Escenario 1: detección de un depósito de ETH nativo válido.

    - Dado que la épica 06 asignó una dirección a la cuenta del usuario
    - Y que se incluye una tx con to = esa dirección, value = 1.5 ETH y status = 1
    - Cuando el servicio de detección procesa el bloque
    - Entonces se registra un depósito (txHash, 0), asset = ETH,
      amountMinUnit = "1500000000000000000" y estado PENDIENTE
    - Y NO se modifica el balance en esta etapa (la acreditación es HU-07-03)
    """
    # Dado: dirección de depósito asignada a la cuenta (épica 06 / RN-2)
    direccion = direccion_deposito(usuario, "ETH")

    # Y: transferencia de 1.5 ETH incluida con status = 1 (sin confirmar aún)
    monto_wei = 1_500_000_000_000_000_000
    tx_hash = rpc.depositar_eth(direccion, monto_wei, confirmar=False)
    assert rpc.esperar_receipt(tx_hash)["status"] == "0x1"

    # Cuando/Entonces: el depósito queda registrado con identidad (txHash, 0) y PENDIENTE
    dep = esperar_deposito(usuario, id_deposito(tx_hash, 0))
    assert_esquema_deposito(dep)
    assert dep["status"] == "PENDIENTE"
    assert dep["asset"] == "ETH"
    assert dep["amountMinUnit"] == str(monto_wei)  # RN-3: wei exacto, string entero
    assert dep["txHash"] == tx_hash.lower()
    assert dep["logIndex"] == 0  # RN-4: logIndex fijo en 0 para ETH nativo
    assert dep["blockNumber"] == bloque_de_inclusion(rpc, tx_hash)

    # Y: el balance NO cambió (RN-5: la detección no acredita)
    fila = balance_de(usuario, "ETH")
    assert fila["available"] == "0" and fila["total"] == "0", fila


@pytest.mark.at("AT-07-01-02")
def test_multiples_depositos_eth_a_la_misma_direccion(usuario, rpc):
    """HU-07-01 Escenario 2 (borde): múltiples depósitos a la misma dirección.

    - Dado una dirección de depósito asignada a la cuenta
    - Y dos transacciones distintas T1 (1 ETH) y T2 (2 ETH) hacia esa dirección
    - Cuando el servicio procesa ambas
    - Entonces se registran DOS depósitos independientes (txHash(T1), 0) y
      (txHash(T2), 0) con los montos exactos en wei (RN-9)
    """
    # Dado
    direccion = direccion_deposito(usuario, "ETH")
    monto_1 = 1_000_000_000_000_000_000
    monto_2 = 2_000_000_000_000_000_000

    # Y: dos transacciones distintas hacia la misma dirección
    tx_1 = rpc.depositar_eth(direccion, monto_1, confirmar=False)
    tx_2 = rpc.depositar_eth(direccion, monto_2, confirmar=False)
    assert tx_1 != tx_2

    # Cuando/Entonces: dos depósitos independientes, cada uno con su identidad
    dep_1 = esperar_deposito(usuario, id_deposito(tx_1, 0))
    dep_2 = esperar_deposito(usuario, id_deposito(tx_2, 0))
    assert dep_1["depositId"] != dep_2["depositId"]

    # Y: los montos se conservan exactos como enteros de wei (string)
    assert dep_1["amountMinUnit"] == str(monto_1)
    assert dep_2["amountMinUnit"] == str(monto_2)

    # (cierre del flujo: ambos acreditan de forma independiente al confirmar)
    rpc.minar_bloques(12)
    esperar_disponible_exacto(usuario, "ETH", monto_1 + monto_2)


@pytest.mark.at("AT-07-01-03")
def test_monto_en_wei_exacto_sin_perdida_de_precision(usuario, rpc):
    """HU-07-01 Escenario 3 (borde): monto exacto en wei sin pérdida de precisión.

    - Dado un depósito de 1 ETH + 1 wei ("1000000000000000001")
    - Cuando se detecta
    - Entonces amountMinUnit se registra como "1000000000000000001" (string
      entero), sin redondeo ni float, sin truncar ni reescalar (RN-3)
    """
    # Dado: 1 ETH + 1 wei — un float64 NO puede representar este valor
    direccion = direccion_deposito(usuario, "ETH")
    monto_wei = 1_000_000_000_000_000_001
    tx_hash = rpc.depositar_eth(direccion, monto_wei, confirmar=False)

    # Cuando/Entonces: el monto detectado es exacto, dígito a dígito
    dep = esperar_deposito(usuario, id_deposito(tx_hash, 0))
    assert dep["amountMinUnit"] == "1000000000000000001"
    assert a_int(dep["amountMinUnit"]) == monto_wei

    # Y: la acreditación conserva el mismo entero exacto (sin fee ni redondeo)
    rpc.minar_bloques(12)
    esperar_disponible_exacto(usuario, "ETH", monto_wei)


@pytest.mark.at("AT-07-01-04")
def test_transaccion_eth_revertida_no_es_deposito(usuario, rpc):
    """HU-07-01 Escenario 4 (error/ignorar): transacción revertida.

    - Dado una tx con to = dirección de depósito, value = 0.5 ETH y status = 0
    - Cuando el servicio procesa el bloque
    - Entonces NO se registra un depósito acreditable (RN-6)
    - Y el balance no se ve afectado en ninguna etapa posterior

    Nota de entorno: una transferencia directa a un EOA no puede revertir por
    sí sola; para provocar receipt status = 0 con `to` = la dirección de
    depósito, se instala transitoriamente código que revierte (anvil_setCode)
    y se restaura a EOA ("0x") antes de seguir. Lo que la spec exige del SUT
    (ignorar la tx con status = 0) es independiente de cómo se provocó.
    """
    # Dado: la dirección de depósito revierte la próxima transferencia entrante
    direccion = direccion_deposito(usuario, "ETH")
    set_code(rpc, direccion, CODIGO_REVERT)
    tx_hash, receipt = enviar_eth_con_gas(rpc, direccion, 500_000_000_000_000_000)
    assert receipt["status"] == "0x0", receipt  # el Dado exige status = 0
    set_code(rpc, direccion, "0x")  # restaura la dirección como EOA

    # Cuando: el indexador procesa ese bloque y los siguientes (centinela USDC:
    # su acreditación garantiza que el bloque de la tx revertida ya fue procesado)
    acreditar_centinela(usuario, rpc, asset="USDC")

    # Entonces: no existe depósito con identidad (txHash, 0)
    assert_error(usuario.api.get(f"/deposits/{id_deposito(tx_hash, 0)}"), "NOT_FOUND")

    # Y: el balance de ETH nunca se afectó
    fila = balance_de(usuario, "ETH")
    assert fila["available"] == "0" and fila["total"] == "0", fila


@pytest.mark.at("AT-07-01-05")
def test_transferencia_eth_de_valor_cero_se_ignora(usuario, rpc):
    """HU-07-01 Escenario 5 (borde): transferencia de valor cero.

    - Dado una tx con to = dirección de depósito y value = 0
    - Cuando el servicio procesa el bloque
    - Entonces NO se registra un depósito (RN-8): no hubo transferencia de ETH
    """
    # Dado: tx exitosa con value = 0 hacia la dirección de depósito
    direccion = direccion_deposito(usuario, "ETH")
    tx_hash = rpc.enviar_eth(direccion, 0)
    assert rpc.esperar_receipt(tx_hash)["status"] == "0x1"

    # Cuando: el indexador procesa ese bloque (baliza: centinela USDC acreditado)
    acreditar_centinela(usuario, rpc, asset="USDC")

    # Entonces: sin depósito para (txHash, 0) y balance de ETH intacto
    assert_error(usuario.api.get(f"/deposits/{id_deposito(tx_hash, 0)}"), "NOT_FOUND")
    assert balance_de(usuario, "ETH")["total"] == "0"


@pytest.mark.at("AT-07-01-06")
def test_destino_eth_no_asignado_no_genera_deposito(usuario, rpc):
    """HU-07-01 Escenario 6 (borde): destino no asignado a ningún usuario.

    - Dado una dirección NO asignada a ninguna cuenta por la épica 06
    - Y una tx hacia ella con value > 0
    - Cuando el servicio procesa el bloque
    - Entonces NO se genera un depósito atribuible (RN-7) y ningún balance
      de usuario cambia

    Aproximación black-box: las direcciones "controladas por el exchange pero
    no asignadas" son inobservables desde afuera (dependen del seed HD interno,
    HU-06-01 RN-5); se usa una EOA cualquiera no asignada, que para el mapeo
    dirección → cuenta del SUT (única superficie observable, HU-06-03) es
    indistinguible del caso de la spec: no está asignada a ninguna cuenta.
    """
    # Dado: una dirección ajena al SUT, y una tx válida hacia ella
    ajena = direccion_eoa_ajena()
    tx_hash = rpc.enviar_eth(ajena, 400_000_000_000_000_000)
    assert rpc.esperar_receipt(tx_hash)["status"] == "0x1"

    # Cuando: el indexador procesa ese bloque; el centinela ETH del usuario
    # sirve además de referencia exacta de su balance
    monto_centinela = acreditar_centinela(usuario, rpc, asset="ETH")

    # Entonces: sin depósito atribuible y el balance del usuario refleja SOLO
    # su centinela (la tx hacia la dirección ajena no movió ningún balance)
    assert_error(usuario.api.get(f"/deposits/{id_deposito(tx_hash, 0)}"), "NOT_FOUND")
    assert balance_de(usuario, "ETH")["total"] == str(monto_centinela)


@pytest.mark.at("AT-07-01-07")
def test_reprocesar_el_mismo_bloque_no_duplica_la_deteccion_eth(usuario, rpc):
    """HU-07-01 Escenario 7 (idempotencia de detección): reprocesar el mismo bloque.

    - Dado un depósito ya detectado con identidad (txHash, 0)
    - Cuando el servicio reprocesa el mismo bloque
    - Entonces NO se crea un segundo registro para (txHash, 0) (RN-4, INV-5)
    - Y el estado y los metadatos permanecen consistentes

    Provocación black-box del reproceso: reorg superficial con reinclusión de
    la MISMA transacción firmada a la MISMA altura (evm_snapshot / evm_revert +
    eth_sendRawTransaction): el indexador debe retroceder al ancestro común y
    volver a escanear el bloque (HU-07-04 RN-11), reobservando (txHash, 0).
    """
    # Dado: depósito detectado (PENDIENTE) en el bloque B
    direccion = direccion_deposito(usuario, "ETH")
    monto_wei = 10**18
    snap = snapshot(rpc)
    tx_hash = rpc.depositar_eth(direccion, monto_wei, confirmar=False)
    raw = tx_cruda(rpc, tx_hash)  # capturar ANTES del revert
    bloque_b = bloque_de_inclusion(rpc, tx_hash)
    rpc.minar_bloques(2)
    esperar_deposito(usuario, id_deposito(tx_hash, 0))

    # Cuando: reorg que re-mina la misma altura con la misma tx (mismo txHash)
    revertir_a(rpc, snap)
    assert reenviar_tx_cruda(rpc, raw) == tx_hash
    assert bloque_de_inclusion(rpc, tx_hash) == bloque_b  # mismo bloque (altura)
    rpc.minar_bloques(12)

    # Entonces: una sola identidad (sin segundo registro) y metadatos consistentes
    dep = esperar_estado_deposito(usuario, id_deposito(tx_hash, 0), "ACREDITADO")
    assert_esquema_deposito(dep)
    assert dep["amountMinUnit"] == str(monto_wei)
    items = listar_depositos(usuario, asset="ETH")
    assert [i["depositId"] for i in items].count(id_deposito(tx_hash, 0)) == 1, items
    assert len(items) == 1, items  # usuario fresco: no hay ningún otro registro

    # Y: la acreditación ocurrió UNA sola vez (INV-5)
    assert balance_de(usuario, "ETH")["available"] == str(monto_wei)


@pytest.mark.at("AT-07-01-08")
def test_atribucion_correcta_a_distintas_cuentas(usuario, usuario_b, rpc):
    """HU-07-01 Escenario 8: atribución correcta a distintas cuentas.

    - Dado la dirección A asignada a la cuenta A y la B a la cuenta B
    - Y transacciones Ta (to = A) y Tb (to = B), ambas válidas
    - Cuando el servicio procesa el bloque
    - Entonces el depósito de Ta se atribuye a A y el de Tb a B (RN-2), sin cruces
    """
    # Dado: dos usuarios con direcciones de depósito propias
    direccion_a = direccion_deposito(usuario, "ETH")
    direccion_b = direccion_deposito(usuario_b, "ETH")
    assert direccion_a != direccion_b  # resolución dirección → cuenta única (RN-2)
    monto_a = 700_000_000_000_000_000
    monto_b = 300_000_000_000_000_000

    # Y / Cuando
    tx_a = rpc.depositar_eth(direccion_a, monto_a, confirmar=False)
    tx_b = rpc.depositar_eth(direccion_b, monto_b, confirmar=False)

    # Entonces: cada dueño ve su depósito...
    dep_a = esperar_deposito(usuario, id_deposito(tx_a, 0))
    dep_b = esperar_deposito(usuario_b, id_deposito(tx_b, 0))
    assert dep_a["amountMinUnit"] == str(monto_a)
    assert dep_b["amountMinUnit"] == str(monto_b)

    # ...y NO ve el ajeno (sin cruces; no se revela el recurso ajeno, RN-11 de HU-07-03)
    assert_error(usuario.api.get(f"/deposits/{id_deposito(tx_b, 0)}"), "NOT_FOUND")
    assert_error(usuario_b.api.get(f"/deposits/{id_deposito(tx_a, 0)}"), "NOT_FOUND")

    # Y: al confirmar, cada balance recibe exactamente su monto, sin cruces
    rpc.minar_bloques(12)
    esperar_disponible_exacto(usuario, "ETH", monto_a)
    esperar_disponible_exacto(usuario_b, "ETH", monto_b)


@pytest.mark.at("AT-07-01-09")
def test_creacion_de_contrato_to_null_se_ignora(usuario, rpc):
    """HU-07-01 Escenario 9 (borde): transacción de creación de contrato (to = null).

    - Dado una tx de creación de contrato (to = null) con value > 0
    - Cuando el servicio procesa el bloque
    - Entonces NO se registra ningún depósito (RN-1(a)) y se ignora sin error
    - Y ningún balance de usuario cambia
    """
    # Dado: creación de contrato con value = 0.1 ETH
    tx_hash, receipt = crear_contrato_con_valor(rpc, 100_000_000_000_000_000)
    assert receipt["status"] == "0x1" and receipt["contractAddress"], receipt
    assert rpc.transaccion(tx_hash)["to"] is None  # el Dado exige to = null

    # Cuando: el indexador procesa ese bloque sin error (si abortara al ver
    # to = null, el centinela posterior jamás se acreditaría)
    acreditar_centinela(usuario, rpc, asset="USDC")

    # Entonces: sin depósito para (txHash, 0) y balance ETH del usuario intacto
    assert_error(usuario.api.get(f"/deposits/{id_deposito(tx_hash, 0)}"), "NOT_FOUND")
    assert balance_de(usuario, "ETH")["total"] == "0"


# ==============================================================================
# HU-07-02 — Detección de depósito USDC (ERC-20)
# ==============================================================================


@pytest.mark.at("AT-07-02-01")
def test_deteccion_deposito_usdc_valido(usuario, rpc):
    """HU-07-02 Escenario 1: detección de un depósito USDC válido.

    - Dado una dirección de depósito asignada a la cuenta
    - Y un evento Transfer del USDC-mock con to = esa dirección y
      value = "10000000" (10 USDC) en una tx con status = 1
    - Cuando el servicio procesa los logs del bloque
    - Entonces se registra un depósito (txHash, logIndex), asset = USDC,
      amountMinUnit = "10000000" y estado PENDIENTE
    - Y NO se modifica el balance en esta etapa
    """
    # Dado / Y: Transfer de 10 USDC hacia la dirección de depósito
    direccion = direccion_deposito(usuario, "USDC")
    monto = 10_000_000
    tx_hash = rpc.depositar_usdc(direccion, monto, confirmar=False)
    log_index = log_index_unico(rpc, tx_hash)  # logIndex global del bloque (RN-7)

    # Cuando/Entonces
    dep = esperar_deposito(usuario, id_deposito(tx_hash, log_index))
    assert_esquema_deposito(dep)
    assert dep["status"] == "PENDIENTE"  # RN-8: estado inicial
    assert dep["asset"] == "USDC"
    assert dep["amountMinUnit"] == str(monto)  # RN-6: unidad de 6 decimales, exacta
    assert dep["txHash"] == tx_hash.lower()
    assert es_entero_json(dep["logIndex"]) and dep["logIndex"] == log_index

    # Y: el balance NO cambió (la acreditación es HU-07-03)
    fila = balance_de(usuario, "USDC")
    assert fila["available"] == "0" and fila["total"] == "0", fila


@pytest.mark.at("AT-07-02-02")
def test_dos_logs_transfer_en_la_misma_transaccion(usuario, usuario_b, rpc):
    """HU-07-02 Escenario 2 (borde): dos logs Transfer en la misma transacción.

    - Dado dos direcciones de depósito (cuentas A y B)
    - Y UNA transacción que emite dos Transfer del USDC-mock: 5 USDC → A y
      7 USDC → B, con logIndex globales del bloque distintos
    - Cuando el servicio procesa los logs
    - Entonces se registran DOS depósitos independientes (txHash, li_1) → A y
      (txHash, li_2) → B, que difieren sólo en logIndex (block-scoped, RN-7)
    """
    # Dado
    direccion_a = direccion_deposito(usuario, "USDC")
    direccion_b = direccion_deposito(usuario_b, "USDC")
    monto_a, monto_b = 5_000_000, 7_000_000

    # Y: una única tx con dos Transfer (contrato batcher, ver comunes_ep07)
    tx_hash, li_a, li_b = transferencia_usdc_doble(rpc, direccion_a, monto_a, direccion_b, monto_b)
    assert li_a != li_b  # dos logs del mismo bloque nunca comparten logIndex

    # Cuando/Entonces: dos depósitos independientes, mismo txHash, distinto logIndex
    dep_a = esperar_deposito(usuario, id_deposito(tx_hash, li_a))
    dep_b = esperar_deposito(usuario_b, id_deposito(tx_hash, li_b))
    assert dep_a["txHash"] == dep_b["txHash"] == tx_hash.lower()
    assert dep_a["logIndex"] == li_a and dep_b["logIndex"] == li_b
    assert dep_a["amountMinUnit"] == str(monto_a)
    assert dep_b["amountMinUnit"] == str(monto_b)

    # Y: al confirmar, cada cuenta recibe exactamente su parte
    rpc.minar_bloques(12)
    esperar_disponible_exacto(usuario, "USDC", monto_a)
    esperar_disponible_exacto(usuario_b, "USDC", monto_b)


@pytest.mark.at("AT-07-02-03")
def test_monto_usdc_con_maxima_precision_de_6_decimales(usuario, rpc):
    """HU-07-02 Escenario 3 (borde): monto con máxima precisión de 6 decimales.

    - Dado un Transfer hacia la dirección de depósito con value = "1"
      (0.000001 USDC, 1 unidad mínima)
    - Cuando se detecta
    - Entonces amountMinUnit se registra como "1" (string entero), sin redondeo
      ni float (RN-6), preservando exactamente la unidad mínima
    """
    # Dado: 1 unidad mínima de USDC
    direccion = direccion_deposito(usuario, "USDC")
    tx_hash = rpc.depositar_usdc(direccion, 1, confirmar=False)
    log_index = log_index_unico(rpc, tx_hash)

    # Cuando/Entonces
    dep = esperar_deposito(usuario, id_deposito(tx_hash, log_index))
    assert dep["amountMinUnit"] == "1"

    # Y: se acredita exactamente 1 unidad mínima (sin redondeo a 0 ni a otra escala)
    rpc.minar_bloques(12)
    esperar_disponible_exacto(usuario, "USDC", 1)


@pytest.mark.at("AT-07-02-04")
def test_transfer_de_un_contrato_distinto_al_usdc_mock_se_ignora(usuario, rpc):
    """HU-07-02 Escenario 4 (error/ignorar): Transfer de un contrato distinto.

    - Dado un Transfer con to = dirección de depósito y value > 0, pero emitido
      por un ERC-20 DISTINTO del USDC-mock configurado
    - Cuando el servicio procesa los logs
    - Entonces el log se ignora y NO se registra depósito (RN-2)
    - Y el balance no se ve afectado
    """
    # Dado: un segundo token (misma interfaz, otra dirección de contrato) que
    # emite un Transfer válido hacia la dirección de depósito del usuario
    direccion = direccion_deposito(usuario, "USDC")
    otro_token = desplegar_otro_erc20(rpc)
    assert otro_token.lower() != rpc.direccion_usdc.lower()
    rpc.mint_usdc(CUENTA_TESORERIA, 9_000_000, contrato=otro_token)
    tx_hash = rpc.transferir_usdc(direccion, 9_000_000, contrato=otro_token)
    log_index = log_index_unico(rpc, tx_hash)

    # Cuando: el indexador procesa ese bloque (baliza: centinela USDC del mock real)
    monto_centinela = acreditar_centinela(usuario, rpc, asset="USDC")

    # Entonces: el log del otro contrato no generó depósito
    assert_error(usuario.api.get(f"/deposits/{id_deposito(tx_hash, log_index)}"), "NOT_FOUND")

    # Y: el balance USDC refleja SOLO el centinela del contrato configurado
    assert balance_de(usuario, "USDC")["total"] == str(monto_centinela)


@pytest.mark.at("AT-07-02-05")
def test_log_con_topic0_distinto_de_transfer_se_ignora(usuario, rpc):
    """HU-07-02 Escenario 5 (error/ignorar): log con topic0 distinto de Transfer.

    - Dado un log emitido por el USDC-mock cuyo topic0 NO es el de Transfer
      (p. ej. Approval)
    - Cuando el servicio procesa los logs
    - Entonces el log se ignora (RN-1) y no se registra depósito
    """
    # Dado: approve(direccion_deposito, 5 USDC) sobre el mock REAL configurado:
    # emite Approval (topic0 ≠ Transfer) con la dirección de depósito en topics
    direccion = direccion_deposito(usuario, "USDC")
    tx_hash, receipt = aprobar_usdc(rpc, direccion, 5_000_000)
    assert receipt["status"] == "0x1"
    (log,) = receipt["logs"]
    assert log["topics"][0].lower() != TOPIC0_TRANSFER  # el Dado exige topic0 ≠ Transfer
    log_index = int(log["logIndex"], 16)

    # Cuando
    monto_centinela = acreditar_centinela(usuario, rpc, asset="USDC")

    # Entonces: sin depósito para esa identidad; balance sólo del centinela
    assert_error(usuario.api.get(f"/deposits/{id_deposito(tx_hash, log_index)}"), "NOT_FOUND")
    assert balance_de(usuario, "USDC")["total"] == str(monto_centinela)


@pytest.mark.at("AT-07-02-06")
def test_transfer_usdc_de_valor_cero_se_ignora(usuario, rpc):
    """HU-07-02 Escenario 6 (borde): transferencia de valor cero.

    - Dado un Transfer del USDC-mock con to = dirección de depósito y value = "0"
    - Cuando el servicio procesa los logs
    - Entonces NO se registra un depósito (RN-10)
    """
    # Dado: Transfer con value = 0 (el ERC-20 lo permite y emite el evento)
    direccion = direccion_deposito(usuario, "USDC")
    tx_hash = rpc.transferir_usdc(direccion, 0)
    log_index = log_index_unico(rpc, tx_hash)

    # Cuando
    monto_centinela = acreditar_centinela(usuario, rpc, asset="USDC")

    # Entonces
    assert_error(usuario.api.get(f"/deposits/{id_deposito(tx_hash, log_index)}"), "NOT_FOUND")
    assert balance_de(usuario, "USDC")["total"] == str(monto_centinela)


@pytest.mark.at("AT-07-02-07")
def test_transaccion_usdc_revertida_no_es_deposito(usuario, rpc):
    """HU-07-02 Escenario 7 (error/ignorar): transacción revertida.

    - Dado un intento de Transfer hacia la dirección de depósito cuya
      transacción contenedora termina con receipt status = 0 (revertida)
    - Cuando el servicio procesa el bloque
    - Entonces NO se registra un depósito acreditable (RN-9)

    Nota: en una tx revertida el nodo no persiste logs (el receipt queda con
    status = 0 y logs vacíos); el SUT no debe derivar ningún depósito de ella.
    """
    # Dado: transfer por más del balance del remitente ⇒ revert del ERC-20
    direccion = direccion_deposito(usuario, "USDC")
    monto = rpc.balance_usdc(CUENTA_AUX_2) + 10_000_000
    tx_hash = rpc.transferir_usdc(direccion, monto, desde=CUENTA_AUX_2)
    receipt = rpc.esperar_receipt(tx_hash)
    assert receipt["status"] == "0x0", receipt  # el Dado exige status = 0
    assert receipt["logs"] == [], receipt

    # Cuando
    monto_centinela = acreditar_centinela(usuario, rpc, asset="USDC")

    # Entonces: ninguna identidad de esa tx generó depósito ni movió balances
    assert_error(usuario.api.get(f"/deposits/{id_deposito(tx_hash, 0)}"), "NOT_FOUND")
    assert balance_de(usuario, "USDC")["total"] == str(monto_centinela)


@pytest.mark.at("AT-07-02-08")
def test_reprocesar_el_mismo_log_no_duplica_la_deteccion_usdc(usuario, rpc):
    """HU-07-02 Escenario 8 (idempotencia de detección): reprocesar el mismo log.

    - Dado un depósito USDC ya detectado con identidad (txHash, logIndex)
    - Cuando el servicio reprocesa el mismo bloque/log
    - Entonces NO se crea un segundo registro para (txHash, logIndex) (RN-7, INV-5)

    Reproceso provocado igual que en AT-07-01-07: reorg superficial que re-mina
    la misma altura con la MISMA tx firmada (mismo txHash y mismo logIndex,
    porque el bloque re-minado contiene sólo esa tx).
    """
    # Dado: remitente auxiliar fondeado ANTES del snapshot (el replay debe
    # volver a ejecutar con éxito tras el revert)
    direccion = direccion_deposito(usuario, "USDC")
    monto = 3_000_000
    rpc.mint_usdc(CUENTA_AUX_1, monto)
    snap = snapshot(rpc)
    tx_hash = rpc.transferir_usdc(direccion, monto, desde=CUENTA_AUX_1)
    raw = tx_cruda(rpc, tx_hash)
    log_index = log_index_unico(rpc, tx_hash)
    rpc.minar_bloques(2)
    esperar_deposito(usuario, id_deposito(tx_hash, log_index))

    # Cuando: reorg + reinclusión de la misma tx (misma identidad)
    revertir_a(rpc, snap)
    assert reenviar_tx_cruda(rpc, raw) == tx_hash
    assert log_index_unico(rpc, tx_hash) == log_index  # mismo logIndex block-scoped
    rpc.minar_bloques(12)

    # Entonces: un único registro para la identidad y una única acreditación
    esperar_estado_deposito(usuario, id_deposito(tx_hash, log_index), "ACREDITADO")
    items = listar_depositos(usuario, asset="USDC")
    assert [i["depositId"] for i in items].count(id_deposito(tx_hash, log_index)) == 1, items
    assert len(items) == 1, items
    assert balance_de(usuario, "USDC")["available"] == str(monto)


@pytest.mark.at("AT-07-02-09")
def test_destino_usdc_no_asignado_no_genera_deposito(usuario, rpc):
    """HU-07-02 Escenario 9 (borde): destino no asignado a ningún usuario.

    - Dado un Transfer del USDC-mock con to = dirección no asignada a ninguna cuenta
    - Cuando el servicio procesa los logs
    - Entonces NO se genera un depósito atribuible (RN-11) y ningún balance
      de usuario cambia

    (Misma aproximación black-box que AT-07-01-06: una dirección "controlada
    pero no asignada" es inobservable desde afuera; para el mapeo dirección →
    cuenta del SUT, una EOA cualquiera no asignada es el mismo caso.)
    """
    # Dado
    ajena = direccion_eoa_ajena()
    tx_hash = rpc.depositar_usdc(ajena, 8_000_000, confirmar=False)
    log_index = log_index_unico(rpc, tx_hash)

    # Cuando
    monto_centinela = acreditar_centinela(usuario, rpc, asset="USDC")

    # Entonces
    assert_error(usuario.api.get(f"/deposits/{id_deposito(tx_hash, log_index)}"), "NOT_FOUND")
    assert balance_de(usuario, "USDC")["total"] == str(monto_centinela)
