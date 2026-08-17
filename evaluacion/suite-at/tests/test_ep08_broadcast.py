"""Épica 08 — HU-08-03 (firma EIP-155 y broadcast): la transacción REAL en la
chain local, verificada vía JSON-RPC (eth_getTransactionByHash).

Verificaciones on-chain black-box (INV-6):
- chainId = 11155111 en la firma (v = 2·chainId + 35/36, tx legacy Type-0),
- to/value/gas exactos, gasPrice == snapshot GAS_PRICE_WEI (20 gwei),
- nonce único, secuencial y contiguo por dirección emisora.

Los escenarios de fallo se provocan manipulando el nodo anvil del entorno
(anvil_setBalance para rechazar broadcasts, tx competidora impersonada para
ocupar un nonce). La persistencia del nonce y del txHash tras un reinicio
(AT-08-03-08) usa el reinicio orquestado por el evaluador
(``SUITE_CMD_REINICIO_SUT``, ``comunes_reinicio``); sin esa env var, ese test
salta.
"""

from concurrent.futures import ThreadPoolExecutor

import pytest

from helpers.montos import CHAIN_ID, a_int

from comunes_ep08 import (
    FEE_RED_ETH,
    GAS_LIMIT_ETH,
    GAS_PRICE_WEI,
    assert_tx_legacy_eip155,
    balance_de,
    crear_retiro,
    descubrir_emisora,
    destino_fresco,
    esperar_broadcast,
    esperar_retiro,
    fondear_eth,
    hex_int,
    retiro_de,
    set_balance,
    tx_impersonada,
)
from comunes_reinicio import comando_reinicio, reiniciar_sut, relogin

ETH_1 = 10**18
RESERVA_1ETH = ETH_1 + FEE_RED_ETH


@pytest.mark.at("AT-08-03-01")
def test_firma_eip155_y_broadcast_de_retiro_eth(usuario, rpc):
    """HU-08-03 Escenario 1: firma EIP-155 y broadcast de retiro de ETH (feliz).

    - Dado un retiro PENDING con reserva aplicada
    - Cuando el servicio construye, firma y broadcastea la transacción
    - Entonces la tx firmada tiene to = destino, value = amount, data vacío,
      gas_limit = 21000, chainId = 11155111 (RN-2/RN-3/RN-6)
    - Y el nodo la acepta, se registra txHash y el retiro pasa a BROADCAST (RN-8)
    - Y los balances internos NO cambian (siguen bloqueados, RN-10)
    """
    # Dado
    fondear_eth(usuario, rpc, 5 * ETH_1)
    destino = destino_fresco()
    resp = crear_retiro(usuario, "ETH", str(ETH_1), destino)
    assert resp.status_code == 202, resp.text
    wid = resp.json()["withdrawalId"]

    # Cuando (asíncrono) / Entonces: BROADCAST con txHash y la tx real en el nodo
    retiro, tx = esperar_broadcast(usuario, rpc, wid)

    assert tx["to"].lower() == destino.lower()          # RN-6: to = destino EIP-55
    assert hex_int(tx["value"]) == ETH_1                # RN-6: value = amount_wei
    assert tx.get("input") in ("0x", "", None)          # RN-6: data vacío
    assert hex_int(tx["gas"]) == GAS_LIMIT_ETH          # RN-5: gas_limit = 21000
    assert hex_int(tx["gasPrice"]) == GAS_PRICE_WEI     # RN-5: gas_price = snapshot
    assert_tx_legacy_eip155(tx)                         # RN-2: EIP-155, chainId 11155111
    assert isinstance(hex_int(tx["nonce"]), int)        # RN-3: nonce asignado

    # Y: balances internos sin cambios (bloqueo intacto hasta CONFIRMED, RN-10)
    eth = balance_de(usuario, "ETH")
    assert a_int(eth["available"]) == 5 * ETH_1 - RESERVA_1ETH
    assert a_int(eth["locked"]) == RESERVA_1ETH
    assert retiro["status"] == "BROADCAST"


@pytest.mark.at("AT-08-03-02")
def test_anti_replay_chainid_siempre_sepolia(usuario, rpc):
    """HU-08-03 Escenario 2 (anti-replay): chainId siempre 11155111.

    - Dado cualquier retiro a firmar
    - Cuando se construye la firma
    - Entonces el chainId firmado es exactamente 11155111 (Sepolia), conforme
      EIP-155 (RN-2, INV-6): v ∈ {2·11155111+35, 2·11155111+36} y el campo
      chainId de la tx reportada por el nodo es 11155111
    - Y nunca se broadcastea una tx con otro chainId: toda tx observada lleva
      el chainId de Sepolia

    Nota: la cláusula "una tx firmada para chainId = 1 se rechaza con
    CHAIN_ID_MISMATCH" requiere inyectar una configuración errónea DENTRO del
    SUT (no hay superficie black-box para forzarla); la propiedad evaluable es
    la positiva: la tx real broadcasteada está firmada para 11155111 y por lo
    tanto es inválida (anti-replay) en cualquier otra red.
    """
    # Dado
    fondear_eth(usuario, rpc, 2 * ETH_1)
    resp = crear_retiro(usuario, "ETH", str(ETH_1), destino_fresco())
    assert resp.status_code == 202, resp.text

    # Cuando / Entonces
    _, tx = esperar_broadcast(usuario, rpc, resp.json()["withdrawalId"])
    assert_tx_legacy_eip155(tx)
    v = hex_int(tx["v"])
    assert (v - 35) // 2 == CHAIN_ID, f"la firma EIP-155 codifica chainId {(v - 35) // 2}"


@pytest.mark.at("AT-08-03-03")
def test_nonces_secuenciales_en_retiros_sucesivos(usuario, rpc):
    """HU-08-03 Escenario 3 (nonce secuencial): retiros sucesivos de la misma emisora.

    - Dado tres retiros a procesar (se crean y broadcastean en orden)
    - Cuando se firman y broadcastean
    - Entonces toman nonces n, n+1, n+2: únicos, secuenciales y contiguos (RN-3, INV-6)
    - Y la lista de nonces usados por la emisora es estrictamente creciente y sin huecos
    """
    # Dado
    fondear_eth(usuario, rpc, 4 * ETH_1)

    nonces = []
    emisoras = set()
    for i in range(3):
        # Cuando: un retiro por vez (sucesivos: se espera el BROADCAST antes del siguiente)
        resp = crear_retiro(usuario, "ETH", str(ETH_1), destino_fresco(), f"w-seq-{i}")
        assert resp.status_code == 202, resp.text
        _, tx = esperar_broadcast(usuario, rpc, resp.json()["withdrawalId"])
        nonces.append(hex_int(tx["nonce"]))
        emisoras.add(tx["from"].lower())

    # Entonces: misma emisora, nonces contiguos y estrictamente crecientes
    assert len(emisoras) == 1, f"los retiros salieron de emisoras distintas: {emisoras}"
    assert nonces == [nonces[0], nonces[0] + 1, nonces[0] + 2], nonces


@pytest.mark.at("AT-08-03-04")
def test_conflicto_de_nonce_no_duplica_ni_pierde_el_retiro(usuario, rpc):
    """HU-08-03 Escenario 4 (error): conflicto de nonce.

    - Dado que el nonce candidato de la emisora ya fue usado por otra transacción
      (se ocupa el siguiente nonce con una tx competidora impersonada en anvil)
    - Cuando el servicio intenta broadcastear con ese nonce
    - Entonces detecta el conflicto (NONCE_CONFLICT, RN-4): el retiro NO falla ni
      se duplica; permanece re-procesable con el nonce correcto
    - Y al re-procesar toma el siguiente nonce contiguo (sin reusar ni saltear,
      INV-6) y el destino recibe el principal exactamente una vez

    Nota: el 409 NONCE_CONFLICT ocurre en el procesamiento asíncrono (la
    solicitud ya respondió 202); lo observable black-box es la ausencia de
    duplicación/pérdida y la contigüidad del nonce final.
    """
    # Dado: emisora conocida y su próximo nonce ocupado por una tx competidora
    emisora = descubrir_emisora(usuario, rpc)
    nonce_ocupado = rpc.nonce(emisora)
    tx_hash_competidora = tx_impersonada(rpc, emisora, nonce=nonce_ocupado)
    rpc.esperar_receipt(tx_hash_competidora)  # minada: el nonce quedó usado

    fondear_eth(usuario, rpc, 2 * ETH_1)
    destino = destino_fresco()

    # Cuando
    resp = crear_retiro(usuario, "ETH", str(ETH_1), destino)
    assert resp.status_code == 202, resp.text
    wid = resp.json()["withdrawalId"]

    # Entonces: el retiro no se pierde (nunca FAILED por conflicto de nonce: no es
    # un disparador de FAILED en HU-08-04 RN-1) y sale con el nonce contiguo
    _, tx = esperar_broadcast(usuario, rpc, wid)
    assert hex_int(tx["nonce"]) == nonce_ocupado + 1, (
        f"nonce {hex_int(tx['nonce'])}: se esperaba {nonce_ocupado + 1} "
        "(el ocupado no se reusa y no se deja hueco, INV-6)"
    )

    # Y: sin duplicación — confirmando, el destino recibe el principal UNA sola vez
    rpc.minar_bloques(12)
    esperar_retiro(usuario, wid, ("CONFIRMED",), prohibidos=("FAILED",))
    assert rpc.balance_eth(destino) == ETH_1


@pytest.mark.at("AT-08-03-05")
def test_dos_retiros_concurrentes_no_toman_el_mismo_nonce(usuario, rpc):
    """HU-08-03 Escenario 5 (concurrencia): dos retiros no toman el mismo nonce.

    - Dado dos retiros PENDING de la misma emisora procesados concurrentemente
    - Cuando ambos asignan nonce
    - Entonces la asignación serializada otorga n a uno y n+1 al otro (RN-3);
      nunca ambos el mismo
    - Y no se produce un hueco en la secuencia
    """
    # Dado
    fondear_eth(usuario, rpc, 3 * ETH_1)
    destinos = [destino_fresco(), destino_fresco()]

    # Cuando: dos solicitudes simultáneas
    with ThreadPoolExecutor(max_workers=2) as pool:
        futuros = [
            pool.submit(crear_retiro, usuario, "ETH", str(ETH_1), destinos[i], f"w-par-{i}")
            for i in (0, 1)
        ]
        respuestas = [f.result() for f in futuros]
    assert all(r.status_code == 202 for r in respuestas), [r.text[:200] for r in respuestas]

    # Entonces: ambos broadcastean con nonces distintos y consecutivos
    txs = [
        esperar_broadcast(usuario, rpc, r.json()["withdrawalId"])[1] for r in respuestas
    ]
    nonces = sorted(hex_int(t["nonce"]) for t in txs)
    assert nonces[1] == nonces[0] + 1, f"nonces no consecutivos o repetidos: {nonces}"
    assert txs[0]["from"].lower() == txs[1]["from"].lower()

    # Y: ambos confirman y cada destino recibe su principal exactamente una vez
    rpc.minar_bloques(12)
    for r, destino in zip(respuestas, destinos):
        esperar_retiro(usuario, r.json()["withdrawalId"], ("CONFIRMED",), prohibidos=("FAILED",))
        assert rpc.balance_eth(destino) == ETH_1


@pytest.mark.at("AT-08-03-06")
def test_broadcast_rechazado_por_el_nodo_deja_el_retiro_pending(usuario, rpc):
    """HU-08-03 Escenario 6 (error): broadcast rechazado por el nodo.

    - Dado un retiro correctamente firmado cuyo broadcast el nodo rechaza (se
      provoca dejando a la emisora sin ETH on-chain: rechazo por fondos de la
      emisora, tratado como BROADCAST_FAILED por RN-8/RN-13)
    - Cuando el nodo rechaza el broadcast
    - Entonces el retiro permanece PENDING (reintentable) y el bloqueo de balance
      no se libera ni se consume (RN-8/RN-10)
    - Y al desaparecer la causa el retiro se re-procesa (o, si el SUT ya agotó
      MAX_BROADCAST_RETRIES = 5 durante la ventana, termina FAILED con
      failureReason BROADCAST_FAILED y liberación total — HU-08-03 RN-8)
    """
    # Dado
    emisora = descubrir_emisora(usuario, rpc)
    fondear_eth(usuario, rpc, 2 * ETH_1)
    disponible_previo = a_int(balance_de(usuario, "ETH")["available"])
    saldo_emisora = rpc.balance_eth(emisora)
    nonce_previo = rpc.nonce(emisora)
    destino = destino_fresco()

    set_balance(rpc, emisora, 0)
    try:
        # Cuando
        resp = crear_retiro(usuario, "ETH", str(ETH_1), destino)
        assert resp.status_code == 202, resp.text
        wid = resp.json()["withdrawalId"]

        # Entonces: sin txHash ni tx on-chain; mientras esté PENDING, el bloqueo
        # aplicado no se libera ni consume (RN-8/RN-10). (Si el SUT reintenta sin
        # delay pudo haber agotado ya los 5 reintentos y estar FAILED: la ventana
        # PENDING no es observable; el desenlace contable se verifica abajo.)
        retiro = retiro_de(usuario, wid)
        assert retiro["status"] in ("PENDING", "FAILED"), retiro
        assert retiro.get("txHash") is None
        assert rpc.nonce(emisora) == nonce_previo  # ninguna tx salió de la emisora
        if retiro["status"] == "PENDING":
            eth = balance_de(usuario, "ETH")
            assert a_int(eth["locked"]) == RESERVA_1ETH
            assert a_int(eth["available"]) == disponible_previo - RESERVA_1ETH
    finally:
        set_balance(rpc, emisora, saldo_emisora)

    # Y: con la causa resuelta, el retiro se re-procesa (reintentable) o quedó
    # FAILED/BROADCAST_FAILED si los 5 reintentos se agotaron en la ventana
    retiro = esperar_retiro(
        usuario, wid, ("BROADCAST", "CONFIRMED", "FAILED"), timeout=150, intervalo=2.0
    )
    if retiro["status"] == "FAILED":
        assert retiro.get("failureReason") == "BROADCAST_FAILED"
        eth = balance_de(usuario, "ETH")
        assert a_int(eth["available"]) == disponible_previo  # liberación total
        assert a_int(eth["locked"]) == 0
    else:
        rpc.minar_bloques(12)
        esperar_retiro(usuario, wid, ("CONFIRMED",), prohibidos=("FAILED",))
        assert rpc.balance_eth(destino) == ETH_1


@pytest.mark.at("AT-08-03-07")
def test_la_transaccion_usa_el_gas_price_snapshotteado(usuario, rpc):
    """HU-08-03 Escenario 7 (gas respaldado exactamente): gas_price = snapshot.

    - Dado un retiro de ETH con gas_price_wei_snapshot = "20000000000" (20 gwei,
      GAS_PRICE_WEI del entorno) y fee_red_wei = "420000000000000" reservado
    - Cuando se construye la transacción con gas_limit = 21000
    - Entonces la tx usa gas_price = "20000000000" == snapshot (RN-5) y
      gas_limit × gas_price == fee_red_wei: el costo máximo está respaldado
      EXACTAMENTE por la reserva (ni sub- ni sobre-reserva)
    """
    # Dado
    fondear_eth(usuario, rpc, 2 * ETH_1)
    resp = crear_retiro(usuario, "ETH", str(ETH_1), destino_fresco())
    assert resp.status_code == 202, resp.text

    # la reserva incluye la previsión exacta (bloqueado = amount + fee_red_wei)
    eth = balance_de(usuario, "ETH")
    assert a_int(eth["locked"]) == ETH_1 + FEE_RED_ETH

    # Cuando / Entonces: la tx real usa el snapshot exacto
    _, tx = esperar_broadcast(usuario, rpc, resp.json()["withdrawalId"])
    assert hex_int(tx["gasPrice"]) == GAS_PRICE_WEI
    assert hex_int(tx["gas"]) == GAS_LIMIT_ETH
    assert hex_int(tx["gas"]) * hex_int(tx["gasPrice"]) == FEE_RED_ETH, (
        "gas_limit × gas_price debe igualar la previsión reservada (respaldo exacto, RN-5)"
    )


@pytest.mark.at("AT-08-03-08")
def test_reinicio_no_reasigna_nonce_ni_refirma_un_retiro_broadcast(api, usuario, rpc):
    """HU-08-03 Escenario 8 (idempotencia/persistencia): reinicio no reasigna nonce.

    - Dado un retiro ya en BROADCAST con nonce n y txHash
    - Cuando el sistema se reinicia (INV-8) y reanuda el procesamiento
    - Entonces NO se firma una segunda transacción para ese retiro ni se reasigna
      su nonce; se conserva (nonce = n, txHash) (RN-9/RN-11)
    - Y un nuevo retiro de la misma emisora toma nonce = n + 1, manteniendo la
      contigüidad

    "No se firmó una segunda transacción" se observa on-chain sin salir del
    black-box: el nonce de cuenta de la emisora es el conteo de transacciones que
    envió, así que si tras el reinicio siguiera valiendo lo mismo, el SUT no
    emitió ninguna otra; y el retiro sigue exponiendo el mismo txHash.
    """
    comando_reinicio()  # precondición antes del "Dado" caro (retiro real)

    # Dado: un retiro en BROADCAST (sin minar las 12 confirmaciones: no avanza)
    emisora = descubrir_emisora(usuario, rpc)
    fondear_eth(usuario, rpc, 3 * ETH_1)
    resp = crear_retiro(usuario, "ETH", str(ETH_1), destino_fresco(), "w-reinicio-1")
    assert resp.status_code == 202, resp.text
    wid = resp.json()["withdrawalId"]
    retiro_previo, tx_previa = esperar_broadcast(usuario, rpc, wid)
    nonce_retiro = hex_int(tx_previa["nonce"])
    nonce_cuenta_previo = rpc.nonce(emisora)

    # Cuando
    reiniciar_sut(api)
    relogin(usuario)

    # Entonces: mismo txHash y mismo nonce; ninguna transacción nueva de la emisora
    reconstruido = esperar_retiro(usuario, wid, ("BROADCAST", "CONFIRMED"), prohibidos=("FAILED",))
    assert reconstruido["txHash"] == retiro_previo["txHash"], (
        f"el retiro cambió de txHash tras el reinicio ({retiro_previo['txHash']} → "
        f"{reconstruido['txHash']}): se re-firmó (viola RN-9/RN-11, INV-8)"
    )
    assert hex_int(rpc.transaccion(reconstruido["txHash"])["nonce"]) == nonce_retiro
    assert rpc.nonce(emisora) == nonce_cuenta_previo, (
        f"el nonce de cuenta de la emisora avanzó de {nonce_cuenta_previo} a "
        f"{rpc.nonce(emisora)} sin retiros nuevos: se firmó una segunda transacción"
    )

    # Y: un retiro nuevo toma el nonce contiguo (n + 1), sin reusar ni saltear
    resp = crear_retiro(usuario, "ETH", str(ETH_1), destino_fresco(), "w-reinicio-2")
    assert resp.status_code == 202, resp.text
    _, tx_nueva = esperar_broadcast(usuario, rpc, resp.json()["withdrawalId"])
    assert hex_int(tx_nueva["nonce"]) == nonce_retiro + 1, (
        f"nonce {hex_int(tx_nueva['nonce'])}: se esperaba {nonce_retiro + 1} "
        "(contigüidad de la secuencia tras el reinicio, RN-3/RN-9)"
    )
