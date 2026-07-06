"""Épica 02 — HU-02-04 Atomicidad y consistencia: tests black-box.

Las garantías transversales (INV-1..INV-4, INV-8) se verifican por observación
indirecta: sumas que cuadran antes/después (conservación con las fees observadas
en GET /trades), rechazos que dejan balances intactos, postcondiciones válidas
bajo cualquier serialización de operaciones concurrentes, idempotencia de la
acreditación y reconstrucción tras reinicio del SUT.

Los escenarios que exigen inyección de fallos internos (AT-02-04-02, AT-02-04-07)
se declaran en no_automatizables_ep02.yaml.

AT-02-04-04 (dos bloqueos concurrentes) se verifica junto con AT-02-02-09 en
test_ep02_reserva_y_liberacion.py (mismo flujo de punta a punta).
"""

import os
import subprocess
from concurrent.futures import ThreadPoolExecutor

import pytest

from comunes_ep02 import (
    INTERVALO_POLL_SEGUNDOS,
    PRECIO_BANDA_BAJA,
    PRECIO_MATCHING,
    balance,
    balances_por_activo,
    cancelar_orden,
    cancelar_si_posible,
    crear_orden,
    crear_retiro,
    detalle_orden,
    direccion_deposito,
    fondear_eth,
    fondear_usdc,
    nuevo_client_order_id,
    orden_creada,
    orden_resting,
    pata_propia_del_fill,
    total_de,
)
from helpers.errores import assert_error, assert_montos_en_details
from helpers.espera import esperar_hasta
from helpers.montos import WEI_POR_ETH, a_int, a_str, fee_maker, fee_taker


@pytest.mark.at("AT-02-04-01")
def test_conservacion_tras_un_fill(usuario, usuario_b, rpc):
    """HU-02-04 Escenario 1: Conservación tras un fill (no se crea ni destruye valor).

    - Dado un sistema con Σ total(·, ETH) = S_eth y Σ total(·, USDC) = S_usdc
      (incluyendo EX)
    - Cuando se liquida un fill entre dos cuentas (con sus fees a EX)
    - Entonces tras el settlement las sumas son idénticas (INV-1)

    Observación indirecta: la suma se restringe a las dos cuentas participantes
    más las fees acreditadas a EX (observables por la pata propia de GET /trades,
    HU-09-01 RN-20). Ningún evento on-chain ocurre durante el fill, por lo que
    la suma participantes+EX debe conservarse EXACTA. La reconciliación contra
    EXTERNAL(A) es interna (ver no_automatizables_ep02.yaml, AT-02-03-05).
    """
    # Dado: vendedor con 1 ETH y comprador con 2000 USDC (sumas iniciales conocidas)
    fondear_eth(usuario, rpc, WEI_POR_ETH)
    fondear_usdc(usuario_b, rpc, 2_000_000_000)
    s_eth = total_de(usuario, "ETH") + total_de(usuario_b, "ETH")
    s_usdc = total_de(usuario, "USDC") + total_de(usuario_b, "USDC")
    assert s_eth == WEI_POR_ETH and s_usdc == 2_000_000_000

    # Cuando: fill de 1 ETH @ 2000.00 (vendedor maker, comprador taker)
    maker = orden_resting(usuario, "SELL", WEI_POR_ETH, PRECIO_MATCHING)
    try:
        taker = orden_creada(usuario_b, "BUY", "LIMIT", WEI_POR_ETH, PRECIO_MATCHING)
        assert taker["status"] == "FILLED", taker

        # Entonces: Σ total participantes + fees a EX == sumas previas, exacto
        fee_base = a_int(pata_propia_del_fill(usuario_b, taker["orderId"])["feeAmount"])
        fee_quote = a_int(pata_propia_del_fill(usuario, maker["orderId"])["feeAmount"])
        assert fee_base == fee_taker(WEI_POR_ETH)          # 2000000000000000 wei
        assert fee_quote == fee_maker(2_000_000_000)       # 2000000 USDC-min

        eth_despues = total_de(usuario, "ETH") + total_de(usuario_b, "ETH")
        usdc_despues = total_de(usuario, "USDC") + total_de(usuario_b, "USDC")
        assert eth_despues + fee_base == s_eth, (eth_despues, fee_base, s_eth)
        assert usdc_despues + fee_quote == s_usdc, (usdc_despues, fee_quote, s_usdc)
    finally:
        cancelar_si_posible(usuario, maker["orderId"])


@pytest.mark.at("AT-02-04-03")
def test_rechazo_previo_deja_balances_intactos(usuario, rpc):
    """HU-02-04 Escenario 3 (no-negatividad): Rechazo previo deja balances intactos.

    - Dado un trader con USDC disponible 1000000 (1 USDC)
    - Cuando intenta una operación que requeriría bloquear 10000000 (10 USDC)
    - Entonces se rechaza con INSUFFICIENT_FUNDS ANTES de aplicar (INV-2, RN-3)
    - Y USDC permanece disponible "1000000", bloqueado "0"
    """
    # Dado
    fondear_usdc(usuario, rpc, 1_000_000)

    # Cuando: BUY 0.01 ETH @ 1000.00 ⇒ lock_quote = floor(1e16 × 1e9 / 1e18)
    # = 10000000 (notional exactamente el mínimo de 10 USDC: pasa tick/lot/notional
    # y llega al paso de fondos)
    resp = crear_orden(usuario, "BUY", "LIMIT", 10**16, PRECIO_BANDA_BAJA)

    # Entonces
    err = assert_error(resp, "INSUFFICIENT_FUNDS")
    detalles = err["details"]
    assert_montos_en_details(detalles, "required", "available")
    assert detalles["asset"] == "USDC"
    assert detalles["required"] == "10000000"
    assert detalles["available"] == "1000000"

    # Y: balances intactos (rechazo previo, nunca "aplicar y corregir")
    usdc = balance(usuario, "USDC")
    assert usdc["available"] == "1000000"
    assert usdc["locked"] == "0"


@pytest.mark.at("AT-02-04-05")
def test_fill_y_cancelacion_concurrentes_sobre_la_misma_orden(usuario, usuario_b, rpc):
    """HU-02-04 Escenario 5 (concurrencia): Fill y cancelación concurrentes sobre
    la misma orden.

    - Dada una orden abierta con remanente bloqueado (SELL 1 ETH @ 2000.00)
    - Cuando llegan concurrentemente un fill que la ejecuta y una cancelación
    - Entonces solo UNO de los efectos se aplica al remanente: o se consume por el
      fill o se libera por la cancelación, nunca ambos sobre la misma cantidad
    - Y no se libera ni consume más de lo bloqueado (INV-2/INV-7); la suma global
      se conserva (INV-1)

    Nota: la barrera de sincronización del mecanismo de referencia es interna;
    black-box se lanzan las dos requests en paralelo y se asserta la
    postcondición exacta de la rama que haya ganado (válida para cualquier
    serialización, HU-02-04 RN-5/RN-11).
    """
    # Dado
    fondear_eth(usuario, rpc, WEI_POR_ETH)
    fondear_usdc(usuario_b, rpc, 2_000_000_000)
    maker = orden_resting(usuario, "SELL", WEI_POR_ETH, PRECIO_MATCHING)
    order_id = maker["orderId"]

    # Cuando: fill (BUY taker de usuario_b) y cancelación (usuario) en paralelo
    payload_taker = {
        "clientOrderId": nuevo_client_order_id("conc-fill"),
        "symbol": "ETH-USDC",
        "side": "BUY",
        "type": "LIMIT",
        "priceMin": a_str(PRECIO_MATCHING),
        "quantityWei": a_str(WEI_POR_ETH),
    }
    taker_id = None
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futuro_fill = pool.submit(usuario_b.api.post, "/orders", payload_taker)
            futuro_cancel = pool.submit(usuario.api.delete, f"/orders/{order_id}")
            resp_fill, resp_cancel = futuro_fill.result(), futuro_cancel.result()

        assert resp_fill.status_code == 201, resp_fill.text
        orden_taker = resp_fill.json()
        taker_id = orden_taker["orderId"]

        # Entonces: la orden maker terminó en exactamente uno de los dos estados
        final_maker = detalle_orden(usuario, order_id)
        assert final_maker["status"] in ("FILLED", "CANCELLED"), final_maker

        vendedor = balances_por_activo(usuario)
        comprador = balances_por_activo(usuario_b)

        if final_maker["status"] == "FILLED":
            # rama fill: el remanente fue CONSUMIDO; la cancelación debió rechazarse
            err = assert_error(resp_cancel, "ORDER_NOT_CANCELLABLE")
            assert err["details"]["orderId"] == order_id
            assert orden_taker["status"] == "FILLED"
            # vendedor: 1 ETH consumido (no liberado) + quote neto de fee maker
            assert vendedor["ETH"]["total"] == "0"
            assert vendedor["ETH"]["locked"] == "0"
            assert vendedor["USDC"]["available"] == "1998000000"
            # comprador: quote consumido + base neta de fee taker
            assert comprador["USDC"]["total"] == "0"
            assert comprador["ETH"]["available"] == "998000000000000000"
        else:
            # rama cancelación: el remanente fue LIBERADO; el fill no encontró
            # contraparte y la BUY quedó resting sin ejecutar
            assert resp_cancel.status_code == 200, resp_cancel.text
            assert resp_cancel.json()["status"] == "CANCELLED"
            assert orden_taker["status"] == "OPEN" and orden_taker["filledWei"] == "0"
            # vendedor: todo liberado, nada consumido
            assert vendedor["ETH"]["available"] == "1000000000000000000"
            assert vendedor["ETH"]["locked"] == "0"
            assert vendedor["USDC"]["total"] == "0"
            # comprador: su bloqueo sigue respaldando la BUY resting, sin fills
            assert comprador["USDC"]["locked"] == "2000000000"
            assert comprador["ETH"]["total"] == "0"
    finally:
        # limpiar lo que haya quedado resting en la banda de matching
        if taker_id:
            cancelar_si_posible(usuario_b, taker_id)
        cancelar_si_posible(usuario, order_id)


@pytest.mark.at("AT-02-04-06")
def test_reconstruccion_de_balances_tras_reinicio(usuario, usuario_b, rpc):
    """HU-02-04 Escenario 6 (persistencia): Reconstrucción de balances tras reinicio.

    - Dado un sistema con balances y ledger poblados (depósitos, órdenes, fills)
    - Cuando se reinicia el sistema
    - Entonces los balances reconstruidos coinciden EXACTAMENTE con los previos (INV-8)
    - Y las órdenes abiertas siguen respaldadas por su locked

    El reinicio del SUT lo orquesta el evaluador (HELPERS.md): este test lo
    ejecuta vía la env var SUITE_CMD_REINICIO_SUT (comando de shell que reinicia
    el SUT preservando su persistencia y termina cuando el proceso fue
    relanzado). Sin esa variable el test se salta (el AT queda `skip`, nunca
    `pasa`), forzando a proveer el comando en una corrida H8 válida.
    """
    comando = os.environ.get("SUITE_CMD_REINICIO_SUT", "").strip()
    if not comando:
        pytest.skip(
            "SUITE_CMD_REINICIO_SUT no configurada: el reinicio del SUT lo orquesta "
            "el evaluador (INV-8)"
        )

    # Dado: estado poblado — depósitos en ambas cuentas, un fill y una orden
    # abierta con locked > 0
    fondear_usdc(usuario, rpc, 3_000_000_000)
    fondear_eth(usuario_b, rpc, WEI_POR_ETH)
    maker = orden_resting(usuario_b, "SELL", 10**17, PRECIO_MATCHING)  # 0.1 ETH
    abierta = None
    try:
        taker = orden_creada(usuario, "BUY", "LIMIT", 10**17, PRECIO_MATCHING)
        assert taker["status"] == "FILLED", taker
        # orden abierta que mantiene fondos bloqueados (banda baja, no cruza)
        abierta = orden_resting(usuario, "BUY", WEI_POR_ETH, PRECIO_BANDA_BAJA)

        antes_a = balances_por_activo(usuario)
        antes_b = balances_por_activo(usuario_b)
        assert a_int(antes_a["USDC"]["locked"]) > 0  # respaldo de la orden abierta

        # Cuando: reinicio del SUT
        subprocess.run(comando, shell=True, check=True, timeout=180)

        def _sut_responde():
            try:
                return usuario.api.get("/balances").status_code == 200
            except Exception:
                return False

        esperar_hasta(
            _sut_responde,
            timeout=120,
            intervalo=INTERVALO_POLL_SEGUNDOS,
            mensaje="el SUT no volvió a responder tras el reinicio",
        )

        # Entonces: balances idénticos, campo a campo, para ambas cuentas
        despues_a = balances_por_activo(usuario)
        despues_b = balances_por_activo(usuario_b)
        for activo in ("ETH", "USDC"):
            for campo in ("available", "locked", "total"):
                assert despues_a[activo][campo] == antes_a[activo][campo], (
                    activo, campo, antes_a[activo], despues_a[activo]
                )
                assert despues_b[activo][campo] == antes_b[activo][campo], (
                    activo, campo, antes_b[activo], despues_b[activo]
                )

        # Y: la orden abierta sigue abierta, con su prioridad/remanente intactos
        recuperada = detalle_orden(usuario, abierta["orderId"])
        assert recuperada["status"] == "OPEN", recuperada
        assert recuperada["filledWei"] == "0"
        assert recuperada["quantityWei"] == abierta["quantityWei"]
    finally:
        if abierta:
            cancelar_si_posible(usuario, abierta["orderId"])
        cancelar_si_posible(usuario_b, maker["orderId"])


@pytest.mark.at("AT-02-04-08")
def test_reprocesar_deposito_no_duplica_efecto(usuario, rpc):
    """HU-02-04 Escenario 8 (idempotencia): Reprocesar depósito no duplica efecto.

    - Dado un depósito ya acreditado con identidad (txHash, logIndex)
    - Cuando el mismo evento se procesa N veces adicionales
    - Entonces el balance se incrementa UNA sola vez en total (INV-5)
    - Y Σ total(·, A) refleja un único crédito por ese depósito

    Observación indirecta: no se puede forzar el reproceso desde afuera, pero el
    indexador del SUT re-observa la cadena en cada ciclo de polling. Se mina un
    excedente de bloques sobre el depósito ya acreditado y se usan depósitos
    NUEVOS como cerca de liveness: cuando el indexador acreditó eventos
    posteriores, el balance debe reflejar exactamente UNA acreditación del
    primero (y el listado de /deposits una sola identidad por evento).
    """
    # Dado: un depósito de 1000 USDC acreditado
    direccion = direccion_deposito(usuario, "USDC")
    rpc.depositar_usdc(direccion, 1_000_000_000)
    esperar_hasta(
        lambda: a_int(balance(usuario, "USDC")["available"]) >= 1_000_000_000,
        intervalo=INTERVALO_POLL_SEGUNDOS,
        mensaje="el primer depósito no se acreditó",
    )
    assert balance(usuario, "USDC")["available"] == "1000000000"

    # Cuando: la cadena avanza y el indexador re-observa los mismos bloques…
    rpc.minar_bloques(24)
    # …y se acreditan dos depósitos nuevos (cercas de liveness)
    rpc.depositar_usdc(direccion, 250_000_000)
    esperar_hasta(
        lambda: a_int(balance(usuario, "USDC")["available"]) >= 1_250_000_000,
        intervalo=INTERVALO_POLL_SEGUNDOS,
        mensaje="el segundo depósito no se acreditó",
    )
    rpc.depositar_usdc(direccion, 1_000_000)
    esperar_hasta(
        lambda: a_int(balance(usuario, "USDC")["available"]) >= 1_251_000_000,
        intervalo=INTERVALO_POLL_SEGUNDOS,
        mensaje="el tercer depósito no se acreditó",
    )

    # Entonces: exactamente UNA acreditación por evento (suma exacta, INV-5)
    assert balance(usuario, "USDC")["available"] == "1251000000"

    # Y: el listado de depósitos tiene una sola entrada por identidad
    resp = usuario.api.get("/deposits")
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    acreditados = [i for i in items if i["status"] == "ACREDITADO"]
    assert len(acreditados) == 3, items
    identidades = {(i["txHash"], i["logIndex"]) for i in acreditados}
    assert len(identidades) == 3, "identidades (txHash, logIndex) repetidas"
    assert sorted(a_int(i["amountMinUnit"]) for i in acreditados) == [
        1_000_000, 250_000_000, 1_000_000_000,
    ]


@pytest.mark.at("AT-02-04-09")
def test_invariantes_tras_secuencia_arbitraria(usuario, usuario_b, rpc):
    """HU-02-04 Escenario 9 (post-condición global): Invariantes tras secuencia
    arbitraria.

    - Dada una secuencia de operaciones válidas e inválidas (depósitos, altas
      rechazadas y aceptadas, un fill, una cancelación, retiros rechazado y
      aceptado)
    - Cuando finaliza la secuencia
    - Entonces se cumplen INV-1 (conservación), INV-2 (no-negatividad) e INV-3
      (total = disponible + bloqueado) simultáneamente
    - Y la reconciliación cierra exactamente para ETH y USDC (con las fees del
      fill observadas por GET /trades como el saldo de EX)
    """
    # Dado: depósitos iniciales (entradas totales al sistema: 2 ETH y 3000 USDC)
    fondear_usdc(usuario, rpc, 3_000_000_000)
    fondear_eth(usuario, rpc, WEI_POR_ETH)
    fondear_eth(usuario_b, rpc, WEI_POR_ETH)

    # 1) alta inválida: precio fuera de tick ⇒ rechazada sin tocar balances
    resp = crear_orden(usuario, "BUY", "LIMIT", WEI_POR_ETH, 2_000_005_000)
    assert_error(resp, "INVALID_PRICE_TICK")

    # 2) SELL maker de B resting + 3) BUY taker de A ⇒ fill 1 ETH @ 2000.00
    maker = orden_resting(usuario_b, "SELL", WEI_POR_ETH, PRECIO_MATCHING)
    abierta = None
    try:
        taker = orden_creada(usuario, "BUY", "LIMIT", WEI_POR_ETH, PRECIO_MATCHING)
        assert taker["status"] == "FILLED", taker

        # 4) alta válida en banda baja + cancelación ⇒ lock y release netos en 0
        abierta = orden_resting(usuario, "BUY", 5 * 10**17, PRECIO_BANDA_BAJA)
        cancelar_orden(usuario, abierta["orderId"])
        abierta = None

        # 5) retiro rechazado (más que el disponible) ⇒ sin efecto
        resp = crear_retiro(usuario, "ETH", 5 * WEI_POR_ETH)
        assert_error(resp, "INSUFFICIENT_FUNDS")

        # 6) retiro aceptado de 0.1 ETH, que queda bloqueado (sin confirmar:
        # no salen fondos del sistema, el total no cambia)
        resp = crear_retiro(usuario, "ETH", 10**17)
        assert resp.status_code == 202, resp.text

        # Cuando finaliza la secuencia / Entonces:
        # INV-2 e INV-3 se validan campo a campo en cada lectura de balances
        a = balances_por_activo(usuario)
        b = balances_por_activo(usuario_b)

        # estados finales exactos derivados de la secuencia
        assert a["USDC"]["total"] == "1000000000"      # 3000 − 2000 pagados
        assert a["USDC"]["locked"] == "0"
        assert a["ETH"]["total"] == "1998000000000000000"  # 1 + (1 − fee_taker)
        assert b["ETH"]["total"] == "0"                # vendió su ETH íntegro
        assert b["USDC"]["total"] == "1998000000"      # quote neto de fee maker
        assert b["USDC"]["locked"] == "0"

        # Y: reconciliación exacta por activo (INV-1): lo depositado ==
        # Σ totales de los participantes + fees acreditadas a EX (el retiro
        # pendiente solo bloqueó: no salió del sistema)
        fee_base = a_int(pata_propia_del_fill(usuario, taker["orderId"])["feeAmount"])
        fee_quote = a_int(pata_propia_del_fill(usuario_b, maker["orderId"])["feeAmount"])
        assert fee_base == fee_taker(WEI_POR_ETH)
        assert fee_quote == fee_maker(2_000_000_000)

        assert a_int(a["ETH"]["total"]) + a_int(b["ETH"]["total"]) + fee_base == 2 * WEI_POR_ETH
        assert a_int(a["USDC"]["total"]) + a_int(b["USDC"]["total"]) + fee_quote == 3_000_000_000
    finally:
        if abierta:
            cancelar_si_posible(usuario, abierta["orderId"])
        cancelar_si_posible(usuario_b, maker["orderId"])
