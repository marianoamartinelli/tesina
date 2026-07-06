"""Épica 08 — HU-08-04 (seguimiento de confirmaciones): estados
PENDING/BROADCAST/CONFIRMED/FAILED, 12 confirmaciones, reconciliación del
balance y cancelación de retiros PENDING (RN-13, vía POST
/withdrawals/{id}/cancel — ruta fijada por HU-09-01 RN-21, ADR-006 D1).

Control determinista del mundo on-chain (anvil del entorno):
- minado a demanda (`anvil_mine`) para avanzar confirmaciones exactas;
- `evm_setAutomine(false)` para observar la tx en mempool (sin receipt) o
  mantener un retiro en BROADCAST (no cancelable);
- `anvil_setBalance` para hacer rechazar broadcasts (BROADCAST_FAILED
  agotado; también mantiene un retiro en PENDING cancelable);
- destino con código que revierte para provocar receipt status = 0;
- `anvil_dropTransaction` + tx competidora en el mismo nonce para provocar la
  tx descartada (TX_DROPPED, HU-08-04 RN-9);
- `evm_snapshot`/`evm_revert` + re-broadcast de la misma raw tx para simular
  una reorg que deja huérfano el bloque de inclusión (AT-08-04-08).
"""

import time

import pytest

from helpers.errores import assert_error
from helpers.montos import CONFIRMACIONES_REQUERIDAS, a_int, es_monto_valido

from comunes_ep08 import (
    CODE_RETORNA_TRUE,
    FEE_RED_ERC20,
    FEE_RED_ETH,
    GAS_LIMIT_ERC20,
    GAS_LIMIT_ETH,
    GAS_PRICE_WEI,
    MAX_BLOCKS_PENDING,
    automine,
    balance_de,
    cancelar_retiro,
    confirmar_retiro,
    crear_retiro,
    descubrir_emisora,
    destino_fresco,
    destino_revertidor,
    esperar_broadcast,
    esperar_retiro,
    fondear_eth,
    fondear_usdc,
    foto_balances,
    get_code,
    hex_int,
    raw_tx_legacy,
    retiro_de,
    set_balance,
    set_code,
    snapshot,
    revert,
    drop_tx,
    tx_impersonada,
    usdc_del_entorno,
)
from helpers.espera import esperar_hasta

ETH_1 = 10**18
RESERVA_1ETH = ETH_1 + FEE_RED_ETH


@pytest.mark.at("AT-08-04-01")
def test_retiro_eth_confirmado_consume_principal_mas_gas(usuario, rpc):
    """HU-08-04 Escenario 1: retiro de ETH confirmado (feliz).

    - Dado un retiro de ETH en BROADCAST con reserva "1000420000000000000"; una
      transferencia ETH real consume exactamente el límite (gasUsed = 21000), por
      lo que gas_usado_wei == fee_red_wei (previsión exacta)
    - Cuando alcanza 12 confirmaciones con receipt status = 1
    - Entonces pasa a CONFIRMED; se consume amount + gas_usado_wei =
      "1000420000000000000" (WITHDRAWAL_SETTLE); sin sobrante que liberar (RN-3)
    - Y la suma total de ETH del usuario disminuye exactamente en eso (RN-4, INV-1)
    """
    # Dado
    fondear_eth(usuario, rpc, 5 * ETH_1)
    destino = destino_fresco()
    resp = crear_retiro(usuario, "ETH", str(ETH_1), destino)
    assert resp.status_code == 202, resp.text
    wid = resp.json()["withdrawalId"]

    # Cuando: 12 confirmaciones (minadas a demanda) con status = 1
    retiro, tx, receipt = confirmar_retiro(usuario, rpc, wid)
    assert hex_int(receipt["status"]) == 1
    gas_usado = hex_int(receipt["gasUsed"]) * GAS_PRICE_WEI
    assert hex_int(receipt["gasUsed"]) == GAS_LIMIT_ETH  # premisa: gas usado = previsión
    assert gas_usado == FEE_RED_ETH

    # Entonces: consumo exacto, sin sobrante; partición y conservación exactas
    eth = balance_de(usuario, "ETH")
    assert a_int(eth["available"]) == 5 * ETH_1 - (ETH_1 + gas_usado)  # "3999580000000000000"
    assert a_int(eth["locked"]) == 0
    assert a_int(eth["total"]) == 5 * ETH_1 - (ETH_1 + gas_usado)     # INV-1: baja exacta

    # Y: el principal llegó al destino on-chain, una sola vez
    assert rpc.balance_eth(destino) == ETH_1
    assert isinstance(retiro["confirmations"], int) and retiro["confirmations"] >= 12


@pytest.mark.at("AT-08-04-02")
def test_gas_usado_menor_que_la_prevision_libera_la_diferencia(usuario, rpc):
    """HU-08-04 Escenario 2 (borde): gas usado < previsión, se libera la
    diferencia (pata ERC-20).

    - Dado un retiro de USDC (ERC-20) en BROADCAST con amount_usdc = "25000000"
      (25 USDC) y gas_limit = GAS_LIMIT_ERC20 = 100000: una llamada ERC-20
      consume gas variable ≤ gas_limit (a diferencia de una transferencia de
      ETH nativo, que consume exactamente 21000 = GAS_LIMIT_ETH y no genera
      sobrante). El AT ilustra con gas_price_wei_snapshot = 5 gwei,
      gasUsed = 60000 y sobrante "200000000000000"; el entorno fija
      GAS_PRICE_WEI = 20 gwei y el gasUsed real lo reporta el receipt: las
      fórmulas de RN-3 se asertan EXACTAS con los valores observados
    - Cuando alcanza 12 confirmaciones con status = 1 y el evento Transfer
      esperado (RN-2)
    - Entonces se consume amount_usdc = "25000000" en USDC y
      gas_usado_wei = gasUsed × precio_efectivo_wei en ETH (WITHDRAWAL_SETTLE)
      y se LIBERA a disponible fee_red_wei − gas_usado_wei en ETH
      (WITHDRAWAL_RELEASE) (RN-3)
    - Y la suma total de USDC disminuye en "25000000" y la de ETH SOLO en
      gas_usado_wei (lo realmente salido, RN-4)
    """
    # Dado
    fondear_usdc(usuario, rpc, 50_000_000)
    fondear_eth(usuario, rpc, 10**16)  # 0.01 ETH para el gas
    usdc_del_entorno(rpc)
    destino = destino_fresco()
    resp = crear_retiro(usuario, "USDC", "25000000", destino)
    assert resp.status_code == 202, resp.text
    wid = resp.json()["withdrawalId"]

    # Cuando
    retiro, tx, receipt = confirmar_retiro(usuario, rpc, wid)
    assert hex_int(tx["gas"]) == GAS_LIMIT_ERC20            # gas_limit de la previsión
    gas_usado = hex_int(receipt["gasUsed"]) * GAS_PRICE_WEI
    assert hex_int(receipt["gasUsed"]) < GAS_LIMIT_ERC20, (
        "premisa del escenario: gasUsed < gas_limit (si no, no hay sobrante que liberar)"
    )
    # precio_efectivo_wei = effectiveGasPrice del receipt = snapshot (Type-0, RN-3)
    if receipt.get("effectiveGasPrice") is not None:
        assert hex_int(receipt["effectiveGasPrice"]) == GAS_PRICE_WEI
    sobrante = FEE_RED_ERC20 - gas_usado
    assert sobrante > 0  # fee_red_wei − gas_usado_wei, la liberación de RN-3

    # Entonces: liberación exacta del sobrante de gas en ETH
    eth = balance_de(usuario, "ETH")
    assert a_int(eth["available"]) == 10**16 - gas_usado, (
        "disponible(ETH) debe ser fondeo − gas_usado_wei: el sobrante "
        f"fee_red − gas_usado = {sobrante} fue liberado (RN-3)"
    )
    assert a_int(eth["locked"]) == 0
    assert a_int(eth["total"]) == 10**16 - gas_usado  # RN-4: ETH baja sólo el gas usado

    # Y: la pata USDC consume exactamente el principal (RN-3/RN-4)
    usdc_bal = balance_de(usuario, "USDC")
    assert a_int(usdc_bal["available"]) == 25_000_000
    assert a_int(usdc_bal["locked"]) == 0
    assert a_int(usdc_bal["total"]) == 25_000_000       # 50 − 25 USDC (INV-1)
    assert rpc.balance_usdc(destino) == 25_000_000      # llegó al destino una sola vez


@pytest.mark.at("AT-08-04-03")
def test_no_finaliza_antes_de_12_confirmaciones(usuario, rpc):
    """HU-08-04 Escenario 3 (borde): aún no alcanza 12 confirmaciones.

    - Dado un retiro BROADCAST con confirmaciones = 11 y status = 1
    - Cuando el servicio evalúa su finalización
    - Entonces permanece en BROADCAST y no se consume el bloqueo (RN-8)
    - Y al llegar a confirmaciones = 12 recién entonces pasa a CONFIRMED
    """
    # Dado
    fondear_eth(usuario, rpc, 2 * ETH_1)
    resp = crear_retiro(usuario, "ETH", str(ETH_1), destino_fresco())
    assert resp.status_code == 202, resp.text
    wid = resp.json()["withdrawalId"]
    _, tx = esperar_broadcast(usuario, rpc, wid)
    receipt = rpc.esperar_receipt(tx["hash"])
    inclusion = hex_int(receipt["blockNumber"])

    # Cuando: exactamente 11 confirmaciones (bloque_cabeza − bloque_de_inclusión = 11)
    faltan = 11 - (rpc.numero_de_bloque() - inclusion)
    assert faltan >= 0, "otro proceso minó bloques inesperados"
    if faltan:
        rpc.minar_bloques(faltan)

    # Entonces: el SUT observa 11 y NO finaliza (el retiro sigue BROADCAST)
    retiro = esperar_hasta(
        lambda: (r := retiro_de(usuario, wid)) and r["confirmations"] >= 11 and r,
        intervalo=1.0,
        mensaje="el SUT no reflejó las 11 confirmaciones",
    )
    assert retiro["confirmations"] == 11
    assert retiro["status"] == "BROADCAST", "finalizó con 11 < 12 confirmaciones (RN-8)"
    assert a_int(balance_de(usuario, "ETH")["locked"]) == RESERVA_1ETH  # bloqueo intacto

    # Y: con la confirmación 12 sí finaliza
    rpc.minar_bloques(1)
    esperar_retiro(usuario, wid, ("CONFIRMED",), prohibidos=("FAILED",))


@pytest.mark.at("AT-08-04-04")
def test_failed_por_broadcast_definitivamente_imposible(usuario, rpc):
    """HU-08-04 Escenario 4 (FAILED por broadcast definitivamente imposible).

    - Dado un retiro PENDING cuyo broadcast el nodo rechaza siempre (emisora sin
      ETH on-chain: BROADCAST_FAILED por RN-13 de HU-08-03) hasta agotar
      MAX_BROADCAST_RETRIES = 5
    - Cuando se agotan los reintentos
    - Entonces PENDING → FAILED (RN-1 disparador (f)) con gas_usado_wei = 0 y se
      libera TODA la reserva a disponible (WITHDRAWAL_RELEASE) (RN-5)
    - Y la suma total de ETH no cambia (nada salió del sistema; INV-1)
    """
    # Dado
    emisora = descubrir_emisora(usuario, rpc)
    fondear_eth(usuario, rpc, 2 * ETH_1)
    disponible_previo = a_int(balance_de(usuario, "ETH")["available"])
    total_previo = a_int(balance_de(usuario, "ETH")["total"])
    saldo_emisora = rpc.balance_eth(emisora)
    destino = destino_fresco()

    set_balance(rpc, emisora, 0)
    try:
        resp = crear_retiro(usuario, "ETH", str(ETH_1), destino)
        assert resp.status_code == 202, resp.text
        wid = resp.json()["withdrawalId"]
        # la reserva queda aplicada mientras el retiro está PENDING (si el SUT
        # reintenta sin delay puede estar ya FAILED con la reserva liberada)
        if retiro_de(usuario, wid)["status"] == "PENDING":
            assert a_int(balance_de(usuario, "ETH")["locked"]) == RESERVA_1ETH

        # Cuando: se agotan los 5 reintentos (cadencia interna del SUT; espera generosa)
        retiro = esperar_retiro(
            usuario, wid, ("FAILED",), prohibidos=("BROADCAST", "CONFIRMED"),
            timeout=180, intervalo=2.0,
        )
    finally:
        set_balance(rpc, emisora, saldo_emisora)

    # Entonces: failureReason = BROADCAST_FAILED (épica 09 RN-18) y liberación total
    assert retiro.get("failureReason") == "BROADCAST_FAILED"
    assert retiro.get("txHash") is None  # nunca hubo broadcast aceptado
    eth = balance_de(usuario, "ETH")
    assert a_int(eth["available"]) == disponible_previo
    assert a_int(eth["locked"]) == 0
    # Y: la suma total no cambió y nada llegó al destino
    assert a_int(eth["total"]) == total_previo
    assert rpc.balance_eth(destino) == 0


@pytest.mark.at("AT-08-04-05")
def test_failed_revertida_reacredita_principal_y_consume_gas(usuario, rpc):
    """HU-08-04 Escenario 5 (FAILED revertida): tx minada con status = 0.

    - Dado un retiro de ETH BROADCAST cuya transacción se mina pero revierte
      (status = 0; se provoca con un destino cuyo código rechaza la transferencia)
    - Cuando se reconcilia como FAILED
    - Entonces se reacredita el principal y se libera fee_red − gas_usado; se
      consume gas_usado_wei en ETH (gas pagado al validador) (RN-5)
    - Y la suma total de ETH disminuye SOLO en gas_usado_wei, no en el principal
    """
    # Dado
    fondear_eth(usuario, rpc, 2 * ETH_1)
    destino = destino_revertidor(rpc)
    resp = crear_retiro(usuario, "ETH", str(ETH_1), destino)
    assert resp.status_code == 202, resp.text
    wid = resp.json()["withdrawalId"]

    _, tx = esperar_broadcast(usuario, rpc, wid)
    receipt = rpc.esperar_receipt(tx["hash"])
    assert hex_int(receipt["status"]) == 0, "la tx debía revertir (destino revertidor)"
    gas_usado = hex_int(receipt["gasUsed"]) * GAS_PRICE_WEI

    # Cuando (12 bloques por si el SUT espera confirmaciones antes de reconciliar)
    rpc.minar_bloques(12)
    retiro = esperar_retiro(usuario, wid, ("FAILED",), prohibidos=("CONFIRMED",))

    # Entonces
    assert retiro.get("failureReason") == "TX_REVERTED"
    eth = balance_de(usuario, "ETH")
    assert a_int(eth["available"]) == 2 * ETH_1 - gas_usado  # principal reacreditado
    assert a_int(eth["locked"]) == 0
    # Y: la suma total baja sólo el gas; el principal no salió
    assert a_int(eth["total"]) == 2 * ETH_1 - gas_usado
    assert rpc.balance_eth(destino) == 0


@pytest.mark.at("AT-08-04-06")
def test_atomicidad_observable_sin_estados_parciales(usuario, rpc):
    """HU-08-04 Escenario 6 (atomicidad observable como invariante black-box).

    - Dado un retiro que se reconcilia (consumo + liberación)
    - Cuando se consultan estado y balances en cualquier momento del ciclo de vida
    - Entonces nunca es observable un estado parcial: cada snapshot de
      (available, locked) es exactamente uno de {pre-bloqueo, bloqueado,
      settled} y siempre total == available + locked ≥ 0 (RN-6, INV-2/3/4)

    Nota: la prueba de fault-injection interna está fuera de alcance black-box
    (nota del propio escenario); el criterio evaluable es la ausencia de estado
    parcial observable.
    """
    # Dado: 3 ETH exactos; estados contables válidos del ciclo de vida completo
    fondear_eth(usuario, rpc, 3 * ETH_1)
    a0 = 3 * ETH_1
    # (gasUsed de una transferencia ETH = 21000 ⇒ settle deja available = a0 − reserva)
    estados_validos = {
        (a0, 0),                                # antes del bloqueo
        (a0 - RESERVA_1ETH, RESERVA_1ETH),      # bloqueado (PENDING/BROADCAST)
        (a0 - RESERVA_1ETH, 0),                 # settled (CONFIRMED)
    }

    resp = crear_retiro(usuario, "ETH", str(ETH_1), destino_fresco())
    assert resp.status_code == 202, resp.text
    wid = resp.json()["withdrawalId"]

    # Cuando: muestreo continuo de balances durante todo el ciclo hasta CONFIRMED
    minado = False
    fin = time.monotonic() + 90
    while True:
        eth = balance_de(usuario, "ETH")
        muestra = (a_int(eth["available"]), a_int(eth["locked"]))
        # Entonces: jamás un estado intermedio/parcial
        assert muestra in estados_validos, (
            f"estado parcial observable: (available, locked) = {muestra} "
            f"∉ {sorted(estados_validos)} (INV-4)"
        )
        assert muestra[0] + muestra[1] == a_int(eth["total"])  # INV-3
        assert muestra[0] >= 0 and muestra[1] >= 0             # INV-2

        retiro = retiro_de(usuario, wid)
        if retiro["status"] == "CONFIRMED":
            break
        assert retiro["status"] != "FAILED", retiro
        if retiro["status"] == "BROADCAST" and not minado:
            rpc.minar_bloques(12)  # habilita la finalización; seguimos muestreando
            minado = True
        assert time.monotonic() < fin, "el retiro no llegó a CONFIRMED en la ventana"
        time.sleep(0.2)  # cadencia de muestreo (polling, no espera fija)

    assert foto_balances(usuario)["ETH"] == (a0 - RESERVA_1ETH, 0, a0 - RESERVA_1ETH)


@pytest.mark.at("AT-08-04-07")
def test_observar_la_confirmacion_varias_veces_es_idempotente(usuario, rpc):
    """HU-08-04 Escenario 7 (idempotencia): observar la confirmación varias veces.

    - Dado un retiro ya CONFIRMED y reconciliado
    - Cuando el servicio vuelve a observar el evento de confirmación (la cadena
      sigue avanzando: 12 bloques más) y se consulta repetidamente
    - Entonces NO se consume ni libera de nuevo (RN-7): los balances no cambian
      respecto de la primera reconciliación
    """
    # Dado
    fondear_eth(usuario, rpc, 2 * ETH_1)
    resp = crear_retiro(usuario, "ETH", str(ETH_1), destino_fresco())
    assert resp.status_code == 202, resp.text
    wid = resp.json()["withdrawalId"]
    confirmar_retiro(usuario, rpc, wid)
    balances_settle = foto_balances(usuario)

    # Cuando: la cadena avanza y el SUT re-observa la confirmación
    rpc.minar_bloques(12)

    # Entonces: muestreo repetido — los balances quedan idénticos y el estado terminal
    muestras = {"n": 0}

    def sin_cambios():
        if foto_balances(usuario) != balances_settle:
            raise RuntimeError("la reconciliación se aplicó más de una vez (RN-7)")
        assert retiro_de(usuario, wid)["status"] == "CONFIRMED"
        muestras["n"] += 1
        return muestras["n"] >= 6

    esperar_hasta(sin_cambios, intervalo=0.5, mensaje="muestreo de idempotencia incompleto")


@pytest.mark.at("AT-08-04-08")
def test_reorg_antes_de_confirmar_recalcula_sin_finalizar(usuario, rpc):
    """HU-08-04 Escenario 8 (reorg antes de confirmar).

    - Dado un retiro BROADCAST con ~5 confirmaciones cuyo bloque de inclusión
      queda huérfano por una reorg (se simula con evm_snapshot/evm_revert y
      re-broadcast de la MISMA raw tx firmada, que se re-incluye en la nueva
      cadena canónica)
    - Cuando se recalcula contra la nueva cadena
    - Entonces las confirmaciones se recalculan y el retiro NO se finaliza hasta
      re-incluirse y alcanzar 12 confirmaciones (RN-9)
    - Y el bloqueo de balance permanece intacto mientras tanto
    """
    # Dado
    fondear_eth(usuario, rpc, 2 * ETH_1)
    destino = destino_fresco()
    marca = snapshot(rpc)  # snapshot ANTES del broadcast (el depósito ya es canónico)
    resp = crear_retiro(usuario, "ETH", str(ETH_1), destino)
    assert resp.status_code == 202, resp.text
    wid = resp.json()["withdrawalId"]

    _, tx = esperar_broadcast(usuario, rpc, wid)
    rpc.esperar_receipt(tx["hash"])
    raw = raw_tx_legacy(tx)  # misma tx firmada (auto-verificada contra el txHash)
    rpc.minar_bloques(5)
    esperar_hasta(
        lambda: retiro_de(usuario, wid)["confirmations"] >= 5,
        intervalo=1.0,
        mensaje="el SUT no llegó a observar ~5 confirmaciones",
    )

    # Cuando: reorg — el bloque de inclusión deja de ser canónico y la tx se
    # re-incluye de inmediato en la nueva cadena (misma firma, mismo hash)
    assert revert(rpc, marca) is True
    rehash = rpc.llamar("eth_sendRawTransaction", [raw])
    assert rehash.lower() == tx["hash"].lower()
    receipt2 = rpc.esperar_receipt(tx["hash"])

    # Entonces: no se finaliza con la inclusión nueva sin sus 12 confirmaciones
    retiro = retiro_de(usuario, wid)
    assert retiro["status"] == "BROADCAST", (
        f"tras la reorg el retiro debe seguir BROADCAST, está {retiro['status']!r} (RN-9)"
    )
    assert a_int(balance_de(usuario, "ETH")["locked"]) == RESERVA_1ETH  # bloqueo intacto

    # Y: con 12 confirmaciones sobre la NUEVA inclusión, confirma una sola vez
    faltan = CONFIRMACIONES_REQUERIDAS - (rpc.numero_de_bloque() - hex_int(receipt2["blockNumber"]))
    if faltan > 0:
        rpc.minar_bloques(faltan)
    esperar_retiro(usuario, wid, ("CONFIRMED",), prohibidos=("FAILED",))
    assert rpc.balance_eth(destino) == ETH_1  # el principal llegó exactamente una vez


@pytest.mark.at("AT-08-04-08b")
def test_reorg_con_tx_descartada_transiciona_a_failed(usuario, rpc):
    """HU-08-04 Escenario 8b (reorg con tx descartada → FAILED).

    - Dado un retiro BROADCAST cuya transacción es descartada del mempool sin
      reaparecer y con su nonce ocupado por otra tx en la cadena canónica
      (anvil: automine off → drop de la tx pendiente → tx competidora con el
      mismo nonce → automine on), superando además el timeout de inclusión
      (bloque_cabeza − bloque_de_broadcast > MAX_BLOCKS_PENDING = 50)
    - Cuando el sistema detecta la tx descartada
    - Entonces BROADCAST → FAILED con la reconciliación de no minada:
      gas_usado_wei = 0, se libera TODA la reserva (RN-9/RN-5)
    - Y la suma total de ETH no cambia (nada salió; INV-1)
    """
    # Dado
    fondear_eth(usuario, rpc, 2 * ETH_1)
    total_previo = a_int(balance_de(usuario, "ETH")["total"])
    disponible_previo = a_int(balance_de(usuario, "ETH")["available"])
    destino = destino_fresco()

    automine(rpc, False)
    try:
        resp = crear_retiro(usuario, "ETH", str(ETH_1), destino)
        assert resp.status_code == 202, resp.text
        wid = resp.json()["withdrawalId"]
        _, tx = esperar_broadcast(usuario, rpc, wid)  # tx en mempool, sin minar
        assert tx.get("blockNumber") is None

        # la tx se descarta y su nonce lo ocupa una tx competidora (RN-9: "el nonce
        # fue ocupado por otra tx en la cadena canónica") ⇒ no puede reaparecer
        drop_tx(rpc, tx["hash"])
        tx_impersonada(rpc, tx["from"], nonce=hex_int(tx["nonce"]))
    finally:
        automine(rpc, True)

    # timeout de inclusión: > MAX_BLOCKS_PENDING bloques desde el broadcast
    rpc.minar_bloques(MAX_BLOCKS_PENDING + 2)

    # Cuando / Entonces
    retiro = esperar_retiro(
        usuario, wid, ("FAILED",), prohibidos=("CONFIRMED",), timeout=120, intervalo=2.0
    )
    assert retiro.get("failureReason") == "TX_DROPPED"

    # liberación total: gas_usado_wei = 0, nada salió del sistema
    eth = balance_de(usuario, "ETH")
    assert a_int(eth["available"]) == disponible_previo
    assert a_int(eth["locked"]) == 0
    assert a_int(eth["total"]) == total_previo
    assert rpc.balance_eth(destino) == 0
    assert rpc.transaccion(tx["hash"]) is None  # la tx no reapareció


@pytest.mark.at("AT-08-04-09")
def test_consulta_de_estado_del_retiro_propio_y_ajeno(usuario, usuario_b, rpc):
    """HU-08-04 Escenario 9 (consulta): el trader consulta el estado de su retiro.

    - Dado un retiro en BROADCAST con receipt presente y confirmaciones = 4
    - Cuando el titular lo consulta
    - Entonces obtiene status = BROADCAST, txHash, confirmations = 4 (entero
      JSON, sin comillas) y los montos como string (RN-10)
    - Y otro usuario que consulta ese retiro recibe NOT_FOUND (404) con
      details {resource: "withdrawal", id}, indistinguible de un id inexistente
    """
    # Dado
    fondear_eth(usuario, rpc, 2 * ETH_1)
    resp = crear_retiro(usuario, "ETH", str(ETH_1), destino_fresco())
    assert resp.status_code == 202, resp.text
    wid = resp.json()["withdrawalId"]
    _, tx = esperar_broadcast(usuario, rpc, wid)
    receipt = rpc.esperar_receipt(tx["hash"])
    faltan = 4 - (rpc.numero_de_bloque() - hex_int(receipt["blockNumber"]))
    if faltan > 0:
        rpc.minar_bloques(faltan)

    # Cuando / Entonces
    retiro = esperar_hasta(
        lambda: (r := retiro_de(usuario, wid)) and r["confirmations"] >= 4 and r,
        intervalo=1.0,
        mensaje="el SUT no reflejó las 4 confirmaciones",
    )
    assert retiro["status"] == "BROADCAST"
    assert retiro["confirmations"] == 4
    assert isinstance(retiro["confirmations"], int)          # entero JSON, no string
    assert not isinstance(retiro["confirmations"], bool)
    assert retiro["txHash"] == tx["hash"]
    assert es_monto_valido(retiro["amountMinUnit"])          # montos como string

    # Y: retiro ajeno ⇒ NOT_FOUND indistinguible (nunca UNAUTHORIZED; RN-10, HU-08-01 RN-1)
    resp_ajeno = usuario_b.api.get(f"/withdrawals/{wid}")
    err = assert_error(resp_ajeno, "NOT_FOUND")
    assert (err.get("details") or {}).get("resource") == "withdrawal"
    assert (err.get("details") or {}).get("id") == wid

    # Y: retiro inexistente ⇒ NOT_FOUND con el mismo shape
    resp_inexistente = usuario.api.get("/withdrawals/w-inexistente-ep08")
    err = assert_error(resp_inexistente, "NOT_FOUND")
    assert (err.get("details") or {}).get("resource") == "withdrawal"


@pytest.mark.at("AT-08-04-09b")
def test_consulta_en_mempool_sin_receipt_confirmaciones_cero(usuario, rpc):
    """HU-08-04 Escenario 9b (consulta en mempool, aún sin receipt).

    - Dado un retiro BROADCAST cuya tx está en el mempool sin receipt
      (bloque_de_inclusión = null; se desactiva el automine del nodo)
    - Cuando el titular consulta su retiro
    - Entonces obtiene status = BROADCAST y confirmations = 0 (entero JSON),
      conforme a la fórmula total de RN-2 (sin receipt ⇒ confirmaciones = 0)
    """
    # Dado (el fondeo ocurre antes de apagar el automine)
    fondear_eth(usuario, rpc, 2 * ETH_1)
    automine(rpc, False)
    try:
        resp = crear_retiro(usuario, "ETH", str(ETH_1), destino_fresco())
        assert resp.status_code == 202, resp.text
        wid = resp.json()["withdrawalId"]

        # Cuando: BROADCAST con la tx todavía en el mempool
        retiro, tx = esperar_broadcast(usuario, rpc, wid)
        assert tx.get("blockNumber") is None            # sin inclusión
        assert rpc.receipt(tx["hash"]) is None          # sin receipt

        # Entonces
        assert retiro["status"] == "BROADCAST"
        assert retiro["confirmations"] == 0
        assert isinstance(retiro["confirmations"], int)
    finally:
        automine(rpc, True)

    # limpieza determinista: se mina la tx y se deja el retiro terminal
    rpc.minar_bloques(13)
    esperar_retiro(usuario, wid, ("CONFIRMED",), prohibidos=("FAILED",))


@pytest.mark.at("AT-08-04-10")
def test_transicion_invalida_sobre_retiro_terminal_es_conflict(usuario, rpc):
    """HU-08-04 Escenario 10 (error): transición de estado inválida.

    - Dado un retiro ya CONFIRMED (terminal)
    - Cuando se intenta forzar una transición a FAILED — la única mutación de
      estado invocable por el contrato es la cancelación de RN-13
      (POST /withdrawals/{id}/cancel, ruta de HU-09-01 RN-21, ADR-006 D1),
      cuya semántica es exactamente esa transición
    - Entonces se rechaza con CONFLICT (409) (RN-1) y el estado no cambia
    - Y no hay reconciliación nueva: los balances quedan idénticos (RN-7)
    """
    # Dado: un retiro llevado a CONFIRMED (terminal)
    fondear_eth(usuario, rpc, 2 * ETH_1)
    resp = crear_retiro(usuario, "ETH", str(ETH_1), destino_fresco())
    assert resp.status_code == 202, resp.text
    wid = resp.json()["withdrawalId"]
    confirmar_retiro(usuario, rpc, wid)
    balances_previos = foto_balances(usuario)

    # Cuando: se intenta forzar CONFIRMED → FAILED vía la cancelación
    resp_cancel = cancelar_retiro(usuario, wid)

    # Entonces: CONFLICT (409) y el estado terminal no cambia
    assert_error(resp_cancel, "CONFLICT")
    assert retiro_de(usuario, wid)["status"] == "CONFIRMED"

    # Y: sin efecto contable alguno (no se libera ni consume de nuevo)
    assert foto_balances(usuario) == balances_previos


@pytest.mark.at("AT-08-04-11")
def test_usdc_status_1_sin_evento_transfer_esperado_es_failed(usuario, rpc):
    """HU-08-04 Escenario 11 (USDC con status = 1 pero sin el evento Transfer → FAILED).

    - Dado un retiro de USDC cuya transacción se mina con status = 1 y alcanza 12
      confirmaciones pero el contrato NO emite el Transfer esperado (se provoca
      reemplazando el código del USDC-mock por un stub que responde éxito sin
      emitir logs — "bug del mock")
    - Cuando se evalúa la confirmación
    - Entonces NO pasa a CONFIRMED (RN-2): se trata como FAILED (revertida): se
      reacredita el USDC, se consume gas_usado_wei en ETH y se libera el resto
    - Y la suma total de USDC no cambia; la de ETH disminuye en gas_usado_wei

    (Mismo caso, desde la HU del ERC-20, en AT-08-05-10.)
    """
    # Dado
    usdc = usdc_del_entorno(rpc)
    fondear_usdc(usuario, rpc, 50_000_000)
    fondear_eth(usuario, rpc, 10**16)
    destino = destino_fresco()
    codigo_original = get_code(rpc, usdc)

    set_code(rpc, usdc, CODE_RETORNA_TRUE)  # status=1, sin ningún log Transfer
    try:
        resp = crear_retiro(usuario, "USDC", "25000000", destino)
        assert resp.status_code == 202, resp.text
        wid = resp.json()["withdrawalId"]

        _, tx = esperar_broadcast(usuario, rpc, wid)
        receipt = rpc.esperar_receipt(tx["hash"])
        assert hex_int(receipt["status"]) == 1, "premisa: la tx debe minar con status = 1"
        assert receipt.get("logs") in ([], None), "premisa: sin evento Transfer emitido"
        gas_usado = hex_int(receipt["gasUsed"]) * GAS_PRICE_WEI

        # Cuando: 12 confirmaciones
        rpc.minar_bloques(12)
        retiro = esperar_retiro(
            usuario, wid, ("FAILED",), prohibidos=("CONFIRMED",), timeout=60, intervalo=1.0
        )
    finally:
        set_code(rpc, usdc, codigo_original)

    # Entonces: failureReason TX_REVERTED (épica 09 RN-18: status=1 sin Transfer)
    assert retiro.get("failureReason") == "TX_REVERTED"
    usdc_bal = balance_de(usuario, "USDC")
    assert a_int(usdc_bal["available"]) == 50_000_000   # USDC reacreditado
    assert a_int(usdc_bal["locked"]) == 0
    assert a_int(usdc_bal["total"]) == 50_000_000       # suma total USDC sin cambio
    eth = balance_de(usuario, "ETH")
    assert a_int(eth["available"]) == 10**16 - gas_usado  # gas consumido + resto liberado
    assert a_int(eth["locked"]) == 0
    assert a_int(eth["total"]) == 10**16 - gas_usado
    # Y: el token nunca llegó al destino
    assert rpc.balance_usdc(destino) == 0


@pytest.mark.at("AT-08-04-12")
def test_cancelacion_de_retiro_pending_por_el_usuario(usuario, usuario_b, rpc):
    """HU-08-04 Escenario 12 (cancelación de un retiro PENDING por el usuario).

    - Dado un retiro de ETH de acc-1 en PENDING sin txHash (se mantiene PENDING
      dejando a la emisora sin ETH on-chain: el nodo rechaza el broadcast y el
      retiro queda reintentable, HU-08-03 RN-8/RN-13)
    - Cuando acc-1 lo cancela vía POST /withdrawals/{id}/cancel (RN-13; ruta y
      superficie de HU-09-01 RN-21, ADR-006 D1)
    - Entonces 200 con el objeto retiro (RN-18) en FAILED con failureReason
      USER_CANCELLED: PENDING → FAILED con gas_usado_wei = 0 y liberación TOTAL
      de la reserva (WITHDRAWAL_RELEASE)
    - Y la suma total de ETH no cambia (nada salió; INV-1)
    - Y cancelar un retiro ya en BROADCAST/FAILED → CONFLICT (409) sin efecto
      (el caso CONFIRMED se cubre en AT-08-04-10); cancelar el de otra cuenta o
      un id inexistente → NOT_FOUND (404) con details {resource, id},
      indistinguibles (RN-13)
    """
    # Dado: emisora conocida y drenada — el broadcast se rechaza y el retiro
    # permanece PENDING (reintentable) sin txHash
    emisora = descubrir_emisora(usuario, rpc)
    fondear_eth(usuario, rpc, 3 * ETH_1)
    disponible_previo = a_int(balance_de(usuario, "ETH")["available"])
    total_previo = a_int(balance_de(usuario, "ETH")["total"])
    saldo_emisora = rpc.balance_eth(emisora)

    set_balance(rpc, emisora, 0)
    try:
        resp = crear_retiro(usuario, "ETH", str(ETH_1), destino_fresco())
        assert resp.status_code == 202, resp.text
        wid = resp.json()["withdrawalId"]

        # Cuando: cancelación inmediata del retiro PENDING
        resp_cancel = cancelar_retiro(usuario, wid)

        # (la spec no fija la cadencia de reintentos de broadcast: si el SUT
        # agotó sus 5 reintentos sin delay antes de que llegara la cancelación,
        # el retiro ya es FAILED/BROADCAST_FAILED y la ventana PENDING no fue
        # observable — se distingue ese caso de una falla real de RN-13)
        if (
            resp_cancel.status_code == 409
            and retiro_de(usuario, wid).get("failureReason") == "BROADCAST_FAILED"
        ):
            pytest.skip(
                "el SUT agotó MAX_BROADCAST_RETRIES antes de la cancelación: "
                "la ventana PENDING no fue observable (cadencia de reintentos "
                "no fijada por la spec)"
            )

        # Entonces: 200 con el objeto retiro FAILED / USER_CANCELLED (RN-21)
        assert resp_cancel.status_code == 200, resp_cancel.text
        retiro = resp_cancel.json()
        assert retiro["withdrawalId"] == wid
        assert retiro["status"] == "FAILED"
        assert retiro["failureReason"] == "USER_CANCELLED"
        assert retiro["txHash"] is None            # nunca hubo broadcast
        assert es_monto_valido(retiro["amountMinUnit"])
        assert retiro_de(usuario, wid)["status"] == "FAILED"  # persistido

        # Y: liberación total de la reserva; la suma total de ETH no cambia
        eth = balance_de(usuario, "ETH")
        assert a_int(eth["available"]) == disponible_previo
        assert a_int(eth["locked"]) == 0
        assert a_int(eth["total"]) == total_previo             # INV-1

        # Y: re-cancelar el retiro ya FAILED (terminal) ⇒ CONFLICT, sin doble
        # liberación (idempotencia respecto del terminal, RN-13/RN-7)
        resp_re = cancelar_retiro(usuario, wid)
        assert_error(resp_re, "CONFLICT")
        assert a_int(balance_de(usuario, "ETH")["available"]) == disponible_previo

        # Y: cancelar el retiro de otra cuenta ⇒ NOT_FOUND indistinguible
        # (nunca UNAUTHORIZED ni CONFLICT: no se revela la existencia, RN-13)
        err = assert_error(cancelar_retiro(usuario_b, wid), "NOT_FOUND")
        assert (err.get("details") or {}).get("resource") == "withdrawal"
        assert (err.get("details") or {}).get("id") == wid

        # Y: cancelar un id inexistente ⇒ NOT_FOUND con el mismo shape
        err = assert_error(cancelar_retiro(usuario, "w-inexistente-ep08"), "NOT_FOUND")
        assert (err.get("details") or {}).get("resource") == "withdrawal"
    finally:
        set_balance(rpc, emisora, saldo_emisora)

    # Y: un retiro en BROADCAST no es cancelable ⇒ CONFLICT y el estado no
    # cambia (automine off: la tx queda en mempool y el retiro en BROADCAST)
    automine(rpc, False)
    try:
        resp = crear_retiro(usuario, "ETH", str(ETH_1), destino_fresco())
        assert resp.status_code == 202, resp.text
        wid2 = resp.json()["withdrawalId"]
        esperar_broadcast(usuario, rpc, wid2)      # BROADCAST estable, sin minar

        assert_error(cancelar_retiro(usuario, wid2), "CONFLICT")
        assert retiro_de(usuario, wid2)["status"] == "BROADCAST"
        assert a_int(balance_de(usuario, "ETH")["locked"]) == RESERVA_1ETH
    finally:
        automine(rpc, True)

    # limpieza determinista: se mina la tx y el retiro queda terminal
    rpc.minar_bloques(13)
    esperar_retiro(usuario, wid2, ("CONFIRMED",), prohibidos=("FAILED",))
