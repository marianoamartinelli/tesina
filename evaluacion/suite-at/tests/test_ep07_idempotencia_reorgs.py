"""Épica 07 — Depósitos on-chain: idempotencia y reorgs (HU-07-04).

Las reorgs se provocan con `evm_snapshot`/`evm_revert` del anvil local
(helpers locales en comunes_ep07, validados contra el nodo del entorno):
revertir deja huérfanos los bloques posteriores al snapshot, y minar de nuevo
produce una cadena alternativa con hashes distintos — exactamente el escenario
que el indexador debe detectar por `parentHash` (RN-11). La reinclusión de la
MISMA identidad `(txHash, logIndex)` se logra reinyectando la transacción
firmada original (`eth_sendRawTransaction`), que conserva el txHash.

Los estados finales se esperan por REST sin sleeps (`helpers.espera`); la
señal determinista de "el indexador ya procesó estos bloques" es un depósito
centinela de OTRO activo (ver comunes_ep07.acreditar_centinela).

Declarados no automatizables (tests/no_automatizables_ep07.yaml, con
justificación): AT-07-04-01 y AT-07-04-03 (reprocesar una identidad YA
acreditada exige reinicio del SUT o reorg de profundidad ≥ 13, excluida por el
supuesto de la HU), AT-07-04-02 (concurrencia interna con barrera),
AT-07-04-07 y AT-07-04-11 (reinicio del SUT, fuera de la superficie black-box).
"""

import pytest

from helpers.errores import assert_error
from helpers.montos import a_int

from comunes_ep07 import (
    CUENTA_AUX_1,
    CUENTA_AUX_2,
    TIMEOUT_REORG,
    acreditar_centinela,
    assert_esquema_deposito,
    balance_de,
    bloque_de_inclusion,
    direccion_deposito,
    esperar_confirmaciones,
    esperar_deposito,
    esperar_deposito_en_bloque,
    esperar_disponible_exacto,
    esperar_estado_deposito,
    id_deposito,
    listar_depositos,
    log_index_unico,
    reenviar_tx_cruda,
    revertir_a,
    snapshot,
    tx_cruda,
)


@pytest.mark.at("AT-07-04-04")
def test_reorg_antes_de_confirmar_descarta_el_deposito(usuario, rpc):
    """HU-07-04 Escenario 4 (reorg antes de confirmar): bloque huérfano.

    - Dado un depósito PENDIENTE con confirmaciones = 4, incluido en el bloque B
    - Cuando una reorg deja a B huérfano y la transacción NO reaparece
    - Entonces el depósito se descarta y nunca se acredita (RN-5)
    - Y ningún balance de usuario se modifica
    """
    # Dado: depósito PENDIENTE con 4 confirmaciones (cabeza = B + 4)
    direccion = direccion_deposito(usuario, "ETH")
    snap = snapshot(rpc)
    tx_hash = rpc.depositar_eth(direccion, 10**18, confirmar=False)
    dep_id = id_deposito(tx_hash, 0)
    rpc.minar_bloques(4)
    esperar_confirmaciones(usuario, dep_id, 4)

    # Cuando: reorg (revert al snapshot) y cadena alternativa SIN la transacción,
    # que avanza más allá de la cabeza anterior (el indexador detecta el
    # parentHash discordante y retrocede al ancestro común, RN-11)
    revertir_a(rpc, snap)
    rpc.minar_bloques(20)
    assert rpc.transaccion(tx_hash) is None  # la tx no reaparece en la cadena canónica

    # Entonces: DESCARTADO con causa REORG, visible y persistido (RN-12)
    dep = esperar_estado_deposito(usuario, dep_id, "DESCARTADO", timeout=TIMEOUT_REORG)
    assert_esquema_deposito(dep)
    assert dep["discardReason"] == "REORG", dep
    assert any(i["depositId"] == dep_id for i in listar_depositos(usuario)), (
        "el registro DESCARTADO debe persistir para auditoría (RN-12, INV-8)"
    )

    # Y: nunca se acredita ni mueve balances (baliza: centinela USDC procesado
    # mucho después del descarte)
    acreditar_centinela(usuario, rpc, asset="USDC")
    assert balance_de(usuario, "ETH")["total"] == "0"
    assert usuario.api.get(f"/deposits/{dep_id}").json()["status"] == "DESCARTADO"


@pytest.mark.at("AT-07-04-05")
def test_reorg_con_reinclusion_recomputa_confirmaciones_desde_el_nuevo_bloque(usuario, rpc):
    """HU-07-04 Escenario 5 (reorg con reinclusión): recuento desde el nuevo bloque.

    - Dado un depósito PENDIENTE con confirmaciones = 3, incluido en B
    - Cuando una reorg reincluye la misma transacción en B' (≠ B) con status = 1
    - Entonces las confirmaciones se recomputan desde B' (RN-6)
    - Y al alcanzar B' + 12 se acredita UNA sola vez para (txHash, logIndex)
    - Y si había quedado DESCARTADO por el bloque huérfano, la reinclusión lo
      reactiva a PENDIENTE con blockNumber = B' (RN-12)
    """
    # Dado: depósito PENDIENTE con 3 confirmaciones en el bloque B
    direccion = direccion_deposito(usuario, "ETH")
    monto_wei = 10**18
    snap = snapshot(rpc)
    tx_hash = rpc.depositar_eth(direccion, monto_wei, confirmar=False)
    raw = tx_cruda(rpc, tx_hash)  # capturar ANTES del revert
    bloque_b = bloque_de_inclusion(rpc, tx_hash)
    dep_id = id_deposito(tx_hash, 0)
    rpc.minar_bloques(3)
    esperar_confirmaciones(usuario, dep_id, 3)

    # Cuando: reorg sin la tx; se espera el DESCARTADO (estado intermedio
    # determinista) antes de reincluir, para observar la reactivación de RN-12
    revertir_a(rpc, snap)
    rpc.minar_bloques(6)
    esperar_estado_deposito(usuario, dep_id, "DESCARTADO", timeout=TIMEOUT_REORG)

    # Y: reinclusión de la MISMA transacción firmada en B' > B
    assert reenviar_tx_cruda(rpc, raw) == tx_hash
    bloque_b_prima = bloque_de_inclusion(rpc, tx_hash)
    assert bloque_b_prima != bloque_b, "la reinclusión debe caer en un bloque distinto"
    rpc.minar_bloques(3)  # cabeza = B' + 3

    # Entonces: reactivado con blockNumber = B' (RN-12) y confirmaciones
    # recomputadas desde B' (cabeza − B' = 3, estable con la cadena detenida;
    # no las heredadas del bloque huérfano)
    esperar_deposito_en_bloque(usuario, dep_id, bloque_b_prima, timeout=TIMEOUT_REORG)
    dep = esperar_confirmaciones(usuario, dep_id, 3, timeout=TIMEOUT_REORG)
    assert dep["status"] == "PENDIENTE", dep
    assert dep["blockNumber"] == bloque_b_prima, dep

    # Y: acreditación única al llegar a B' + 12
    rpc.minar_bloques(9)
    esperar_estado_deposito(usuario, dep_id, "ACREDITADO")
    esperar_disponible_exacto(usuario, "ETH", monto_wei)

    # Y: haber sido vista en B y en B' no produce doble acreditación (INV-5) —
    # el centinela garantiza que el indexador siguió procesando después
    acreditar_centinela(usuario, rpc, asset="USDC")
    assert balance_de(usuario, "ETH")["available"] == str(monto_wei)


@pytest.mark.at("AT-07-04-06")
def test_transaccion_revertida_nunca_se_acredita(usuario, rpc):
    """HU-07-04 Escenario 6 (error/ignorar): transacción revertida no acreditable.

    - Dado una transacción hacia la dirección de depósito con receipt status = 0
    - Cuando el servicio evalúa la identidad (también con 12+ confirmaciones)
    - Entonces la observación se descarta y la identidad nunca se acredita (RN-7)

    Nota: la variante "observación previamente PENDIENTE que luego resulta
    revertida" se ejercita en AT-07-04-09 (reinclusión revertida); acá se
    verifica que una tx revertida no es acreditable en ninguna etapa, aunque
    supere ampliamente el umbral de confirmaciones. El "intento explícito de
    acreditarla" no tiene superficie REST (ver no_automatizables_ep07.yaml,
    AT-07-03-03).
    """
    # Dado: transfer USDC que revierte (balance insuficiente del remitente)
    direccion = direccion_deposito(usuario, "USDC")
    monto = rpc.balance_usdc(CUENTA_AUX_2) + 10_000_000
    tx_hash = rpc.transferir_usdc(direccion, monto, desde=CUENTA_AUX_2)
    receipt = rpc.esperar_receipt(tx_hash)
    assert receipt["status"] == "0x0", receipt

    # Cuando: la tx queda con 13 confirmaciones (más que el umbral) y el
    # indexador procesa todos esos bloques (baliza: centinela ETH)
    rpc.minar_bloques(13)
    acreditar_centinela(usuario, rpc, asset="ETH")

    # Entonces: ninguna identidad de esa tx existe ni se acreditó jamás
    assert_error(usuario.api.get(f"/deposits/{id_deposito(tx_hash, 0)}"), "NOT_FOUND")
    assert balance_de(usuario, "USDC")["total"] == "0"
    assert not any(
        i["txHash"] == tx_hash.lower() for i in listar_depositos(usuario)
    ), "una tx revertida no debe figurar como depósito acreditable"


@pytest.mark.at("AT-07-04-08")
def test_conservacion_bajo_n_reprocesos_de_la_misma_identidad(usuario, rpc):
    """HU-07-04 Escenario 8 (conservación bajo N reprocesos).

    - Dado un depósito de monto m con identidad (txHash, logIndex)
    - Cuando la misma identidad se procesa N veces (N = 3: tres inclusiones de
      la misma transacción firmada en cadenas alternativas sucesivas)
    - Entonces el balance se incrementa exactamente en m, una sola vez (INV-5)
    - Y la suma acreditada es consistente con el lado "depósitos confirmados"
      de INV-1 (RN-9)
    """
    direccion = direccion_deposito(usuario, "ETH")
    monto_wei = 10**18
    dep_id = None
    raw = None
    tx_hash = None

    # Dado/Cuando: ciclos 1 y 2 — la identidad se observa PENDIENTE y su bloque
    # queda huérfano (cada ciclo desplaza la altura para que B_i difiera)
    for ciclo in range(2):
        snap = snapshot(rpc)
        if raw is None:
            tx_hash = rpc.depositar_eth(direccion, monto_wei, confirmar=False)
            raw = tx_cruda(rpc, tx_hash)  # misma tx firmada para los reprocesos
            dep_id = id_deposito(tx_hash, 0)
        else:
            assert reenviar_tx_cruda(rpc, raw) == tx_hash
        bloque_i = bloque_de_inclusion(rpc, tx_hash)
        rpc.minar_bloques(3)

        # el SUT observó ESTA inclusión (blockNumber = B_i) antes de la reorg;
        # así cada ciclo cuenta como un reproceso efectivamente observado
        esperar_deposito_en_bloque(usuario, dep_id, bloque_i, timeout=TIMEOUT_REORG)
        revertir_a(rpc, snap)
        rpc.minar_bloques(2)  # desplaza la altura de la próxima inclusión

    # Cuando: ciclo 3 (última inclusión) llega a las 12 confirmaciones
    assert reenviar_tx_cruda(rpc, raw) == tx_hash
    rpc.minar_bloques(12)

    # Entonces: acreditación única por el monto exacto m (no 2m ni 3m)
    esperar_estado_deposito(usuario, dep_id, "ACREDITADO", timeout=TIMEOUT_REORG)
    esperar_disponible_exacto(usuario, "ETH", monto_wei)

    # Y: tras seguir procesando (centinela USDC), el balance sigue siendo m y
    # existe UN solo registro para la identidad
    acreditar_centinela(usuario, rpc, asset="USDC")
    assert balance_de(usuario, "ETH")["available"] == str(monto_wei)
    items = listar_depositos(usuario, asset="ETH")
    assert [i["depositId"] for i in items].count(dep_id) == 1, items


@pytest.mark.at("AT-07-04-09")
def test_reorg_con_reinclusion_revertida_descarta_el_deposito(usuario, rpc):
    """HU-07-04 Escenario 9 (reorg con reinclusión revertida): status = 0.

    - Dado un depósito PENDIENTE (txHash, logIndex) que en el bloque (luego
      huérfano) B tenía status = 1
    - Cuando una reorg reincluye la misma transacción en B' (≠ B) con status = 0
    - Entonces pasa a DESCARTADO (discardReason = REVERTED) y NO se acredita,
      pese a que en B tenía status = 1 (RN-13)
    - Y ningún balance de usuario se modifica

    Mecánica: el remitente auxiliar recibe el fondeo DESPUÉS del snapshot; al
    revertir, su balance USDC vuelve a ser insuficiente y la reinclusión de la
    misma tx firmada ejecuta con revert (status = 0) — validado contra anvil.
    """
    # Dado: en la cadena original la transferencia ejecuta con éxito
    direccion = direccion_deposito(usuario, "USDC")
    balance_previo = rpc.balance_usdc(CUENTA_AUX_1)
    monto = balance_previo + 5_000_000  # > balance del remitente tras el revert
    snap = snapshot(rpc)
    rpc.mint_usdc(CUENTA_AUX_1, 5_000_000)  # fondeo DENTRO del segmento a revertir
    tx_hash = rpc.transferir_usdc(direccion, monto, desde=CUENTA_AUX_1)
    receipt = rpc.esperar_receipt(tx_hash)
    assert receipt["status"] == "0x1", receipt  # el Dado exige status = 1 en B
    raw = tx_cruda(rpc, tx_hash)
    bloque_b = bloque_de_inclusion(rpc, tx_hash)
    log_index = log_index_unico(rpc, tx_hash)
    dep_id = id_deposito(tx_hash, log_index)
    rpc.minar_bloques(3)
    esperar_deposito(usuario, dep_id)  # observado PENDIENTE en B

    # Cuando: reorg + reinclusión inmediata de la MISMA tx, ahora revertida
    revertir_a(rpc, snap)
    assert reenviar_tx_cruda(rpc, raw) == tx_hash
    receipt_b_prima = rpc.esperar_receipt(tx_hash)
    assert receipt_b_prima["status"] == "0x0", receipt_b_prima  # revertida en B'
    assert int(receipt_b_prima["blockNumber"], 16) != bloque_b
    rpc.minar_bloques(15)  # muy por encima del umbral: aun así no debe acreditar

    # Entonces: DESCARTADO con causa REVERTED (RN-13), nunca ACREDITADO
    dep = esperar_estado_deposito(usuario, dep_id, "DESCARTADO", timeout=TIMEOUT_REORG)
    assert_esquema_deposito(dep)
    assert dep["discardReason"] == "REVERTED", dep

    # Y: ningún balance se movió (baliza: centinela ETH procesado después)
    acreditar_centinela(usuario, rpc, asset="ETH")
    assert balance_de(usuario, "USDC")["total"] == "0"
    assert usuario.api.get(f"/deposits/{dep_id}").json()["status"] == "DESCARTADO"


@pytest.mark.at("AT-07-04-10")
def test_deteccion_de_reorg_por_parenthash_y_avance_normal_sin_reevaluacion(usuario, rpc):
    """HU-07-04 Escenario 10 (detección de reorg por parentHash).

    - Dado el último bloque procesado persistido con su hash
    - Cuando la cabeza avanza a un bloque cuyo parentHash NO coincide
    - Entonces el servicio detecta la reorg, retrocede al ancestro común y
      reevalúa los depósitos PENDIENTE afectados (RN-11)
    - Y un avance normal (parentHash coincidente) no dispara ninguna reevaluación

    Observables black-box del mecanismo: (a) un depósito cuyo bloque quedó
    huérfano termina DESCARTADO (la reorg FUE detectada y reevaluada);
    (b) un depósito anterior al ancestro común no se ve afectado por la reorg
    ni por el avance normal: conserva su blockNumber y se acredita normalmente.
    """
    # Dado: depósito 1 (no afectado) detectado y con avance normal de 5 bloques
    direccion = direccion_deposito(usuario, "ETH")
    monto_1 = 10**18
    tx_1 = rpc.depositar_eth(direccion, monto_1, confirmar=False)
    dep_id_1 = id_deposito(tx_1, 0)
    bloque_1 = bloque_de_inclusion(rpc, tx_1)
    rpc.minar_bloques(5)

    # Y: el avance normal no disparó reevaluación (sigue PENDIENTE, mismo bloque)
    dep_1 = esperar_confirmaciones(usuario, dep_id_1, 5)
    assert dep_1["status"] == "PENDIENTE", dep_1
    assert dep_1["blockNumber"] == bloque_1, dep_1

    # Cuando: un segundo depósito queda en un segmento que la reorg deja huérfano
    snap = snapshot(rpc)
    tx_2 = rpc.depositar_eth(direccion, 500_000_000_000_000_000, confirmar=False)
    dep_id_2 = id_deposito(tx_2, 0)
    rpc.minar_bloques(2)
    esperar_deposito(usuario, dep_id_2)
    revertir_a(rpc, snap)  # la nueva cadena diverge DESPUÉS del bloque de tx_1
    rpc.minar_bloques(8)

    # Entonces: la reorg fue detectada y el PENDIENTE afectado se reevaluó
    dep_2 = esperar_estado_deposito(usuario, dep_id_2, "DESCARTADO", timeout=TIMEOUT_REORG)
    assert dep_2["discardReason"] == "REORG", dep_2

    # Y: el depósito anterior al ancestro común no fue tocado: conserva su
    # bloque y, con la cadena ya en bloque_1 + 13, se acredita normalmente
    dep_1 = esperar_estado_deposito(usuario, dep_id_1, "ACREDITADO", timeout=TIMEOUT_REORG)
    assert dep_1["blockNumber"] == bloque_1, dep_1
    esperar_disponible_exacto(usuario, "ETH", monto_1)
    assert a_int(balance_de(usuario, "ETH")["total"]) == monto_1  # dep_2 no sumó
