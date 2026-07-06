"""Épica 02 — HU-02-02 Reserva y liberación de fondos: tests black-box.

Verifica la mecánica de transición entre buckets (bloquear / liberar / consumir)
observándola por GET /balances, el alta/cancelación de órdenes (épica 04 vía
HU-09-01) y los retiros (épica 08 vía HU-09-01). Las fees que el settlement
acredita a EX se observan por la pata propia de GET /trades (HU-09-01 RN-20).

Los asientos de ledger que estas transiciones generan (ORDER_LOCK,
ORDER_RELEASE, TRADE_FILL, WITHDRAWAL_*) no tienen superficie propia en el
contrato de la épica 09: acá se verifica su efecto observable sobre los buckets;
la estructura de los asientos se evalúa por otra vía (no_automatizables_ep02.yaml).
"""

from concurrent.futures import ThreadPoolExecutor

import pytest

from comunes_ep02 import (
    PRECIO_BANDA_BAJA,
    PRECIO_MATCHING,
    SIMBOLO,
    balance,
    balances_por_activo,
    cancelar_orden,
    cancelar_si_posible,
    crear_orden,
    crear_retiro,
    detalle_orden,
    detalle_retiro,
    fondear_eth,
    fondear_usdc,
    nuevo_client_order_id,
    orden_creada,
    orden_resting,
    pata_propia_del_fill,
)
from helpers.errores import assert_error, assert_montos_en_details
from helpers.espera import esperar_hasta
from helpers.montos import WEI_POR_ETH, a_int, a_str, fee_maker, fee_taker


@pytest.mark.at("AT-02-02-01")
def test_bloqueo_por_orden_de_compra_limit(usuario, rpc):
    """HU-02-02 Escenario 1: Bloqueo por orden de compra limit.

    - Dado un trader con USDC disponible 2000000000 (2000 USDC) y bloqueado 0
    - Cuando crea una BUY limit de 1 ETH a price_min 2000000000 (2000.00)
    - Entonces se bloquea lock_quote = floor(1e18 × 2000000000 / 1e18) = 2000000000 (RN-1)
    - Y USDC queda disponible "0" y bloqueado "2000000000"
    - Y total de USDC permanece "2000000000" (RN-3 / INV-3)
    """
    # Dado
    fondear_usdc(usuario, rpc, 2_000_000_000)

    # Cuando
    orden = orden_resting(usuario, "BUY", WEI_POR_ETH, PRECIO_MATCHING)
    try:
        # Entonces / Y
        usdc = balance(usuario, "USDC")
        assert usdc["available"] == "0"
        assert usdc["locked"] == "2000000000"
        assert usdc["total"] == "2000000000"
    finally:
        cancelar_si_posible(usuario, orden["orderId"])


@pytest.mark.at("AT-02-02-02")
def test_bloqueo_por_orden_de_venta_limit(usuario, rpc):
    """HU-02-02 Escenario 2: Bloqueo por orden de venta limit.

    - Dado un trader con ETH disponible 1000000000000000000 (1 ETH) y bloqueado 0
    - Cuando crea una SELL limit de 1 ETH a price_min 2100000000
    - Entonces se bloquea lock_base = 1000000000000000000 (la cantidad, RN-1:
      independiente del precio)
    - Y ETH queda disponible "0" y bloqueado "1000000000000000000"
    - Y total de ETH permanece "1000000000000000000"
    """
    # Dado
    fondear_eth(usuario, rpc, WEI_POR_ETH)

    # Cuando (2100.00 > banda de matching: no cruza bids de otros tests)
    orden = orden_resting(usuario, "SELL", WEI_POR_ETH, 2_100_000_000)
    try:
        # Entonces / Y
        eth = balance(usuario, "ETH")
        assert eth["available"] == "0"
        assert eth["locked"] == "1000000000000000000"
        assert eth["total"] == "1000000000000000000"
    finally:
        cancelar_si_posible(usuario, orden["orderId"])


@pytest.mark.at("AT-02-02-03")
def test_bloqueo_exacto_al_disponible(usuario, rpc):
    """HU-02-02 Escenario 3 (borde): Bloqueo exacto al disponible.

    - Dado un trader con USDC disponible exactamente 2000000000 y bloqueado 0
    - Cuando crea una BUY limit cuyo lock_quote es 2000000000
    - Entonces el bloqueo tiene éxito (RN-2: la precondición es available >= x, no >)
    - Y USDC queda disponible "0", bloqueado "2000000000"
    """
    # Dado
    fondear_usdc(usuario, rpc, 2_000_000_000)

    # Cuando: 2 ETH @ 1000.00 (banda baja) ⇒ lock_quote = 2000000000 exacto
    orden = orden_resting(usuario, "BUY", 2 * WEI_POR_ETH, PRECIO_BANDA_BAJA)
    try:
        # Entonces / Y
        usdc = balance(usuario, "USDC")
        assert usdc["available"] == "0"
        assert usdc["locked"] == "2000000000"
    finally:
        cancelar_si_posible(usuario, orden["orderId"])


@pytest.mark.at("AT-02-02-04")
def test_fondos_insuficientes_para_bloquear(usuario, rpc):
    """HU-02-02 Escenario 4 (error): Fondos insuficientes para bloquear.

    - Dado un trader con USDC disponible 1999999999 y bloqueado 0
    - Cuando intenta una BUY limit cuyo lock_quote es 2000000000
    - Entonces se rechaza con INSUFFICIENT_FUNDS y HTTP 422 (RN-2)
    - Y details = { asset: "USDC", required: "2000000000", available: "1999999999" }
    - Y los balances quedan intactos (INV-2: rechazo antes de aplicar)
    """
    # Dado: 1 unidad mínima menos que lo requerido
    fondear_usdc(usuario, rpc, 1_999_999_999)

    # Cuando: BUY 1 ETH @ 2000.00 ⇒ required 2000000000 (esquema/tick/lot/notional
    # válidos, para que la precedencia llegue al paso de fondos — modelo-de-errores §4)
    resp = crear_orden(usuario, "BUY", "LIMIT", WEI_POR_ETH, PRECIO_MATCHING)

    # Entonces / Y: code + details exactos, montos como string
    err = assert_error(resp, "INSUFFICIENT_FUNDS")
    detalles = err["details"]
    assert_montos_en_details(detalles, "required", "available")
    assert detalles["asset"] == "USDC"
    assert detalles["required"] == "2000000000"
    assert detalles["available"] == "1999999999"

    # Y: balances intactos
    usdc = balance(usuario, "USDC")
    assert usdc["available"] == "1999999999"
    assert usdc["locked"] == "0"


@pytest.mark.at("AT-02-02-05")
def test_liberacion_por_cancelacion_de_orden_no_ejecutada(usuario, rpc):
    """HU-02-02 Escenario 5: Liberación por cancelación de orden no ejecutada.

    - Dado un trader con una BUY limit abierta que bloquea 2000000000 USDC, sin fills
    - Y USDC disponible "500000000", bloqueado "2000000000"
    - Cuando cancela la orden
    - Entonces se libera el remanente: USDC disponible "2500000000", bloqueado "0" (RN-4)
    - Y total de USDC no cambió ("2500000000")
    """
    # Dado
    fondear_usdc(usuario, rpc, 2_500_000_000)
    orden = orden_resting(usuario, "BUY", 2 * WEI_POR_ETH, PRECIO_BANDA_BAJA)  # lock 2000 USDC
    usdc = balance(usuario, "USDC")
    assert usdc["available"] == "500000000" and usdc["locked"] == "2000000000"

    # Cuando
    cancelar_orden(usuario, orden["orderId"])

    # Entonces / Y
    usdc = balance(usuario, "USDC")
    assert usdc["available"] == "2500000000"
    assert usdc["locked"] == "0"
    assert usdc["total"] == "2500000000"


@pytest.mark.at("AT-02-02-06")
def test_cancelacion_de_orden_parcialmente_ejecutada_libera_solo_el_remanente(
    usuario, usuario_b, rpc
):
    """HU-02-02 Escenario 6 (borde): Cancelación de orden parcialmente ejecutada.

    - Dado una SELL limit de 1 ETH con 400000000000000000 wei ya ejecutados
      (consumidos por su fill) y 600000000000000000 wei bloqueados como remanente
    - Cuando cancela la orden
    - Entonces se libera SOLO el remanente: bloqueado −6e17, disponible +6e17 (RN-4)
    - Y la porción ejecutada (4e17 wei) NO se libera (fue consumida por su fill)
    """
    # Dado: vendedor con SELL 1 ETH @ 2000.00 resting…
    fondear_eth(usuario, rpc, WEI_POR_ETH)
    orden = orden_resting(usuario, "SELL", WEI_POR_ETH, PRECIO_MATCHING)
    try:
        # …y un comprador taker que ejecuta 0.4 ETH contra ella
        fondear_usdc(usuario_b, rpc, 800_000_000)  # 0.4 × 2000 = 800 USDC justos
        taker = orden_creada(usuario_b, "BUY", "LIMIT", 400_000_000_000_000_000, PRECIO_MATCHING)
        assert taker["status"] == "FILLED", taker

        parcial = detalle_orden(usuario, orden["orderId"])
        assert parcial["status"] == "PARTIALLY_FILLED", parcial
        assert parcial["filledWei"] == "400000000000000000"

        # Cuando
        cancelar_orden(usuario, orden["orderId"])

        # Entonces: solo el remanente vuelve a disponible
        eth = balance(usuario, "ETH")
        assert eth["available"] == "600000000000000000"
        assert eth["locked"] == "0"
        # Y: la porción ejecutada no se libera (total ETH = 0.6, no 1.0)
        assert eth["total"] == "600000000000000000"

        # (consumo de la porción ejecutada: el vendedor maker recibió el quote
        #  neto de fee: 800000000 − ceil(800000000 × 10 / 10000) = 799200000)
        usdc = balance(usuario, "USDC")
        assert usdc["available"] == a_str(800_000_000 - fee_maker(800_000_000))
        assert usdc["available"] == "799200000"
    finally:
        cancelar_si_posible(usuario, orden["orderId"])


@pytest.mark.at("AT-02-02-07")
def test_liberacion_de_excedente_por_ejecucion_a_mejor_precio(usuario, usuario_b, rpc):
    """HU-02-02 Escenario 7 (borde): Liberación de excedente por mejor precio.

    - Dado una BUY limit de 1 ETH a price_min 2010000000 que bloquea 2010000000
    - Cuando ejecuta totalmente contra un ask resting a price_exec 2000000000
    - Entonces paga floor(1e18 × 2000000000 / 1e18) = 2000000000 (consumido)
    - Y se libera el excedente release = 2010000000 − 2000000000 = 10000000 (RN-6)
    - Y tras el fill el bloqueo asociado a la orden es "0"

    La cláusula "exactamente dos asientos (TRADE_FILL + ORDER_RELEASE)" no es
    observable black-box (sin superficie de ledger en la épica 09); acá se
    verifica su efecto: el excedente vuelve a disponible en la misma operación.
    """
    # Dado: ask maker resting a 2000.00
    fondear_eth(usuario_b, rpc, WEI_POR_ETH)
    maker = orden_resting(usuario_b, "SELL", WEI_POR_ETH, PRECIO_MATCHING)
    try:
        # …y el comprador con exactamente el bloqueo del límite (2010 USDC)
        fondear_usdc(usuario, rpc, 2_010_000_000)

        # Cuando: BUY 1 ETH @ 2010.00 cruza y ejecuta a 2000.00
        taker = orden_creada(usuario, "BUY", "LIMIT", WEI_POR_ETH, 2_010_000_000)
        assert taker["status"] == "FILLED", taker

        # Entonces: pagó 2000000000 y el excedente 10000000 volvió a disponible
        usdc = balance(usuario, "USDC")
        assert usdc["available"] == "10000000"   # release = 10 USDC (RN-6)
        assert usdc["locked"] == "0"             # bloqueo de la orden en 0
        assert usdc["total"] == "10000000"

        # Y: recibió 1 ETH neto de fee taker (consumo del fill, RN-5)
        eth = balance(usuario, "ETH")
        assert eth["available"] == "998000000000000000"
    finally:
        cancelar_si_posible(usuario_b, maker["orderId"])


@pytest.mark.at("AT-02-02-08")
def test_fill_consume_bloqueado_y_acredita_a_la_contraparte(usuario, usuario_b, rpc):
    """HU-02-02 Escenario 8 (consumo): Fill consume bloqueado y acredita la contraparte.

    - Dado un vendedor maker (SELL 1 ETH @ 2000.00 resting, 1e18 wei bloqueados) y
      un comprador taker (BUY 1 ETH @ 2000.00, 2000000000 USDC bloqueados)
    - Cuando matchean por 1 ETH a price_exec 2000000000 (quote_min = 2000000000)
    - Entonces comprador: locked(USDC) −= 2000000000; available(ETH) += 998000000000000000
      (fee_base taker = ceil(1e18 × 20 / 10000) = 2000000000000000)
    - Y vendedor: locked(ETH) −= 1e18; available(USDC) += 1998000000
      (fee_quote maker = ceil(2000000000 × 10 / 10000) = 2000000)
    - Y las fees se acreditan a EX (observadas por la pata propia de GET /trades)
    - Y la conservación por activo es exacta (INV-1)
    """
    # Dado: vendedor maker resting
    fondear_eth(usuario, rpc, WEI_POR_ETH)
    maker = orden_resting(usuario, "SELL", WEI_POR_ETH, PRECIO_MATCHING)
    try:
        # …y comprador con el quote justo
        fondear_usdc(usuario_b, rpc, 2_000_000_000)

        # Cuando
        taker = orden_creada(usuario_b, "BUY", "LIMIT", WEI_POR_ETH, PRECIO_MATCHING)
        assert taker["status"] == "FILLED", taker

        # Entonces: comprador (consumo del bloqueado + crédito neto de fee)
        comprador = balances_por_activo(usuario_b)
        assert comprador["USDC"]["available"] == "0"
        assert comprador["USDC"]["locked"] == "0"
        assert comprador["ETH"]["available"] == "998000000000000000"

        # Y: vendedor (bloqueado consumido + quote neto de fee)
        vendedor = balances_por_activo(usuario)
        assert vendedor["ETH"]["available"] == "0"
        assert vendedor["ETH"]["locked"] == "0"
        assert vendedor["USDC"]["available"] == "1998000000"

        # Y: fees hacia EX, observadas en la pata propia de cada uno (HU-09-01 RN-20)
        pata_comprador = pata_propia_del_fill(usuario_b, taker["orderId"])
        assert pata_comprador["feeAsset"] == "ETH"
        assert pata_comprador["feeAmount"] == a_str(fee_taker(WEI_POR_ETH))
        assert pata_comprador["feeAmount"] == "2000000000000000"
        pata_vendedor = pata_propia_del_fill(usuario, maker["orderId"])
        assert pata_vendedor["feeAsset"] == "USDC"
        assert pata_vendedor["feeAmount"] == a_str(fee_maker(2_000_000_000))
        assert pata_vendedor["feeAmount"] == "2000000"

        # Y: conservación exacta por activo (convenciones-monetarias §3.4, INV-1)
        assert WEI_POR_ETH == 998_000_000_000_000_000 + a_int(pata_comprador["feeAmount"])
        assert 2_000_000_000 == 1_998_000_000 + a_int(pata_vendedor["feeAmount"])
    finally:
        cancelar_si_posible(usuario, maker["orderId"])


@pytest.mark.at("AT-02-02-09", "AT-02-04-04")
def test_dos_bloqueos_concurrentes_que_exceden_el_disponible(usuario, rpc):
    """HU-02-02 Escenario 9 / HU-02-04 Escenario 4 (concurrencia): dos bloqueos
    que juntos exceden el disponible.

    - Dado un trader con USDC disponible 2000000000 y bloqueado 0
    - Cuando envía dos BUY limit en paralelo, cada una con lock_quote 2000000000
    - Entonces exactamente UNA se bloquea y la otra se rechaza con
      INSUFFICIENT_FUNDS (RN-8 / HU-02-04 RN-5/RN-11)
    - Y nunca hay disponible negativo ni locked > total (INV-2/INV-3)
    - Y el estado final (disponible "0", bloqueado "2000000000", total
      "2000000000") equivale a alguna ejecución secuencial

    Nota: la barrera de sincronización que HU-02-04 propone como mecanismo de
    contención es interna al SUT; black-box se aproxima con dos requests
    paralelas. La postcondición assertada es válida para CUALQUIER serialización.
    """
    # Dado
    fondear_usdc(usuario, rpc, 2_000_000_000)

    # Cuando: dos BUY 2 ETH @ 1000.00 (lock 2000000000 c/u) en paralelo
    def _enviar(_):
        return usuario.api.post(
            "/orders",
            json={
                "clientOrderId": nuevo_client_order_id("conc"),
                "symbol": SIMBOLO,
                "side": "BUY",
                "type": "LIMIT",
                "priceMin": a_str(PRECIO_BANDA_BAJA),
                "quantityWei": a_str(2 * WEI_POR_ETH),
            },
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        respuestas = list(pool.map(_enviar, range(2)))

    # Entonces: exactamente una 201 y una INSUFFICIENT_FUNDS (422)
    exitosas = [r for r in respuestas if r.status_code == 201]
    rechazadas = [r for r in respuestas if r.status_code != 201]
    assert len(exitosas) == 1 and len(rechazadas) == 1, (
        f"se esperaba exactamente un éxito y un rechazo: "
        f"{[(r.status_code, r.text[:120]) for r in respuestas]}"
    )
    assert_error(rechazadas[0], "INSUFFICIENT_FUNDS")

    orden_ok = exitosas[0].json()
    try:
        # Y: estado final equivalente a una ejecución secuencial
        usdc = balance(usuario, "USDC")  # balance() ya valida INV-2/INV-3
        assert usdc["available"] == "0"
        assert usdc["locked"] == "2000000000"
        assert usdc["total"] == "2000000000"
    finally:
        cancelar_si_posible(usuario, orden_ok["orderId"])


@pytest.mark.at("AT-02-02-10")
def test_retiro_sin_fondos_suficientes(usuario, rpc):
    """HU-02-02 Escenario 10 (error): Retiro sin fondos suficientes.

    - Dado un trader con ETH disponible 500000000000000000 (0.5 ETH) y bloqueado 0
    - Cuando solicita un retiro de 600000000000000000 wei (0.6 ETH)
    - Entonces se rechaza con INSUFFICIENT_FUNDS (422) y details con
      asset/required/available (RN-10; catálogo modelo-de-errores §3.4)
    - Y los balances quedan intactos (no se crea WITHDRAWAL_LOCK)
    """
    # Dado
    fondear_eth(usuario, rpc, 500_000_000_000_000_000)

    # Cuando (dirección EIP-55 válida y monto ≥ mínimo, para que la precedencia
    # llegue al paso de fondos)
    resp = crear_retiro(usuario, "ETH", 600_000_000_000_000_000)

    # Entonces
    err = assert_error(resp, "INSUFFICIENT_FUNDS")
    detalles = err["details"]
    assert_montos_en_details(detalles, "required", "available")
    assert detalles["asset"] == "ETH"
    assert detalles["available"] == "500000000000000000"
    # TODO-REVISAR: discrepancia entre épicas sobre `required` — HU-02-02 RN-10 y
    # este AT (épica 02) fijan required = monto ("600000000000000000"); HU-08-01
    # RN-9 (épica 08) exige required = monto + fee_red_wei (21000 × 20 gwei) =
    # "600420000000000000". 00-fundaciones no fija la previsión de gas, así que
    # se aceptan ambos valores.
    assert detalles["required"] in ("600000000000000000", "600420000000000000"), detalles

    # Y: balances intactos
    eth = balance(usuario, "ETH")
    assert eth["available"] == "500000000000000000"
    assert eth["locked"] == "0"


@pytest.mark.at("AT-02-02-11")
def test_bloqueo_y_consumo_de_retiro_confirmado(usuario, rpc):
    """HU-02-02 Escenario 11 (retiro): Bloqueo, consumo y liberación de retiro.

    - Dado un trader con ETH disponible 1000000000000000000 (1 ETH)
    - Cuando solicita un retiro de 400000000000000000 wei aceptado
    - Entonces se bloquea (WITHDRAWAL_LOCK): total constante, bloqueado > 0
    - Y al confirmarse on-chain el bloqueado se consume y total(ETH) baja
      (WITHDRAWAL_SETTLE: los fondos salen del sistema)

    TODO-REVISAR: discrepancia entre épicas sobre el monto bloqueado/consumido —
    la épica 02 (README §5.1, RN-10 y este AT) bloquea y consume exactamente el
    monto (gas a cargo de la reserva operativa del exchange); la épica 08
    (HU-08-02 RN-1, HU-08-04 RN-3) bloquea monto + fee_red_wei (420000000000000)
    y consume monto + gas_usado. 00-fundaciones no lo fija: se aceptan ambos.

    La rama de aborto (WITHDRAWAL_RELEASE) no es provocable determinísticamente
    black-box: exige un fallo de broadcast o la cancelación de HU-08-04 RN-13,
    cuya ruta no está en el contrato REST de la épica 09.
    """
    # Dado
    fondear_eth(usuario, rpc, WEI_POR_ETH)

    # Cuando
    resp = crear_retiro(usuario, "ETH", 400_000_000_000_000_000)
    assert resp.status_code == 202, resp.text
    retiro = resp.json()
    assert retiro["status"] == "PENDING"

    # Entonces: bloqueo aplicado, total constante (INV-3; ambos modelos coinciden
    # en que el bloqueo NO cambia el total)
    eth = balance(usuario, "ETH")
    assert eth["total"] == "1000000000000000000"
    assert (eth["available"], eth["locked"]) in (
        ("600000000000000000", "400000000000000000"),  # épica 02: bloquea el monto
        ("599580000000000000", "400420000000000000"),  # épica 08: monto + fee_red_wei
    ), eth

    # Y: confirmación on-chain — esperar el broadcast, minar 12 confirmaciones
    # y esperar la transición a CONFIRMED (HU-08-04)
    esperar_hasta(
        lambda: detalle_retiro(usuario, retiro["withdrawalId"]).get("txHash"),
        intervalo=1.0,
        mensaje="el retiro nunca se broadcasteó (¿hot wallet sin fondear?)",
    )
    rpc.minar_bloques(12)
    esperar_hasta(
        lambda: detalle_retiro(usuario, retiro["withdrawalId"])["status"] == "CONFIRMED",
        intervalo=1.0,
        mensaje="el retiro no llegó a CONFIRMED tras 12 confirmaciones",
    )

    # Y: el bloqueado se consumió y el total bajó (los fondos salieron del sistema)
    eth = balance(usuario, "ETH")
    assert eth["locked"] == "0"
    assert eth["available"] == eth["total"]
    assert eth["total"] in (
        "600000000000000000",  # épica 02: total baja exactamente el monto
        "599580000000000000",  # épica 08: baja monto + gas_usado (21000 × 20 gwei)
    ), eth


@pytest.mark.at("AT-02-02-12")
def test_ejecucion_exactamente_al_precio_limite_no_libera_excedente(usuario, usuario_b, rpc):
    """HU-02-02 Escenario 12 (borde): Ejecución exactamente al precio límite ⇒
    sin ORDER_RELEASE.

    - Dado una BUY limit de 1 ETH a price_min 2000000000 que bloquea 2000000000
    - Cuando ejecuta totalmente contra un ask resting a price_exec = price_min
    - Entonces release = 0 y NO se genera liberación alguna (RN-6: solo si > 0);
      el bloqueado pasa directamente a consumido por el fill
    - Y el ledger sigue balanceado por activo (INV-1)

    Observación black-box: con release = 0, el disponible de quote del comprador
    tras el fill es exactamente 0 (nada volvió a disponible) y el bloqueado es 0
    (todo consumido). La ausencia del asiento ORDER_RELEASE en sí no es
    observable (sin superficie de ledger); se verifica su efecto nulo.
    """
    # Dado: ask maker resting a 2000.00
    fondear_eth(usuario_b, rpc, WEI_POR_ETH)
    maker = orden_resting(usuario_b, "SELL", WEI_POR_ETH, PRECIO_MATCHING)
    try:
        fondear_usdc(usuario, rpc, 2_000_000_000)

        # Cuando: BUY 1 ETH exactamente al precio del ask
        taker = orden_creada(usuario, "BUY", "LIMIT", WEI_POR_ETH, PRECIO_MATCHING)
        assert taker["status"] == "FILLED", taker

        # Entonces: sin excedente liberado, bloqueado íntegramente consumido
        usdc = balance(usuario, "USDC")
        assert usdc["available"] == "0"
        assert usdc["locked"] == "0"
        assert usdc["total"] == "0"

        # Y: conservación exacta del fill (INV-1): el comprador recibió 1 ETH
        # neto de fee taker y el vendedor el quote neto de fee maker
        eth = balance(usuario, "ETH")
        assert eth["available"] == "998000000000000000"
        vendedor_usdc = balance(usuario_b, "USDC")
        assert vendedor_usdc["available"] == "1998000000"
    finally:
        cancelar_si_posible(usuario_b, maker["orderId"])


@pytest.mark.at("AT-02-02-13")
def test_fill_parcial_a_mejor_precio_remanente_bloqueado_al_precio_original(
    usuario, usuario_b, rpc
):
    """HU-02-02 Escenario 13 (borde): Fill parcial a mejor precio, remanente al
    precio original.

    - Dado una BUY limit de 2 ETH a price_min 2010000000 que bloquea
      lock_quote = floor(2e18 × 2010000000 / 1e18) = 4020000000
    - Cuando ejecuta parcialmente 1 ETH contra un ask resting a 2000000000
    - Entonces paga 2000000000 (consumido) y libera release = 10000000 (RN-6)
    - Y el bloqueo de la porción no ejecutada permanece al precio ORIGINAL:
      locked_rem = floor(1e18 × 2010000000 / 1e18) = 2010000000
    - Y locked(USDC) tras el fill = 4020000000 − 2000000000 − 10000000
      = 2010000000 == locked_rem (INV-7)
    """
    # Dado: ask maker resting de 1 ETH a 2000.00
    fondear_eth(usuario_b, rpc, WEI_POR_ETH)
    maker = orden_resting(usuario_b, "SELL", WEI_POR_ETH, PRECIO_MATCHING)
    orden_id = None
    try:
        fondear_usdc(usuario, rpc, 4_020_000_000)

        # Cuando: BUY 2 ETH @ 2010.00 cruza por 1 ETH y el resto queda resting
        taker = orden_creada(usuario, "BUY", "LIMIT", 2 * WEI_POR_ETH, 2_010_000_000)
        orden_id = taker["orderId"]
        assert taker["status"] == "PARTIALLY_FILLED", taker
        assert taker["filledWei"] == "1000000000000000000"

        # Entonces / Y: pagó 2000, liberó 10 y retiene 2010 al precio original
        usdc = balance(usuario, "USDC")
        assert usdc["locked"] == "2010000000"      # == locked_rem (INV-7)
        assert usdc["available"] == "10000000"     # el release volvió a disponible
        assert usdc["total"] == "2020000000"       # 4020 − 2000 pagados

        # Y: recibió la porción ejecutada neta de fee taker
        eth = balance(usuario, "ETH")
        assert eth["available"] == "998000000000000000"
    finally:
        # la BUY remanente queda resting a 2010.00 (banda de matching): limpiarla
        if orden_id:
            cancelar_si_posible(usuario, orden_id)
        cancelar_si_posible(usuario_b, maker["orderId"])
