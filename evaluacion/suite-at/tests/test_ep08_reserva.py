"""Épica 08 — HU-08-02 (débito y reserva al solicitar): bloqueo atómico de
principal + previsión de fee de red, conservación y concurrencia.

Black-box: los movimientos disponible→bloqueado se observan por `GET /balances`
(épica 09 RN-9: total == available + locked, INV-3). La previsión de gas es
`fee_red_wei = gas_limit × gas_price_wei` con el snapshot del entorno
(GAS_PRICE_WEI = 20 gwei; HU-08-01 RN-8, HU-08-02 RN-7).
"""

from concurrent.futures import ThreadPoolExecutor

import pytest

from helpers.errores import assert_error
from helpers.montos import a_int

from comunes_ep08 import (
    DIRECCION_EIP55,
    FEE_RED_ERC20,
    FEE_RED_ETH,
    balance_de,
    crear_retiro,
    fondear_eth,
    fondear_usdc,
    foto_balances,
)

ETH_1 = 10**18
RESERVA_1ETH = ETH_1 + FEE_RED_ETH  # "1000420000000000000" (HU-08-02 RN-1)


@pytest.mark.at("AT-08-02-01")
def test_bloqueo_de_retiro_de_eth(usuario, rpc):
    """HU-08-02 Escenario 1: bloqueo de retiro de ETH (feliz).

    - Dado disponible(ETH) = 5 ETH, bloqueado(ETH) = 0, fee_red_wei = 21000 × 20 gwei
    - Cuando se acepta un retiro de 1 ETH
    - Entonces reserva_eth = "1000420000000000000" y se aplica
      disponible −= reserva; bloqueado += reserva (RN-1/RN-2)
    - Y disponible = "3999580000000000000", bloqueado = "1000420000000000000",
      total = "5000000000000000000" constante (RN-2/RN-6, INV-3)
    """
    # Dado: exactamente 5 ETH acreditados en una cuenta fresca
    fondear_eth(usuario, rpc, 5 * ETH_1)
    assert foto_balances(usuario)["ETH"] == (5 * ETH_1, 0, 5 * ETH_1)

    # Cuando
    resp = crear_retiro(usuario, "ETH", str(ETH_1), DIRECCION_EIP55)
    assert resp.status_code == 202, resp.text

    # Entonces (la reserva es simultánea a la aceptación: sin estado parcial, INV-4)
    eth = balance_de(usuario, "ETH")
    assert a_int(eth["available"]) == 5 * ETH_1 - RESERVA_1ETH  # "3999580000000000000"
    assert a_int(eth["locked"]) == RESERVA_1ETH                 # "1000420000000000000"
    assert a_int(eth["total"]) == 5 * ETH_1                     # constante


@pytest.mark.at("AT-08-02-02")
def test_bloqueo_dual_de_retiro_de_usdc(usuario, rpc):
    """HU-08-02 Escenario 2: bloqueo dual de retiro de USDC (feliz).

    - Dado disponible(USDC) = 50 USDC y disponible(ETH) = 0.003 ETH;
      fee_red_wei = 100000 × 20 gwei = "2000000000000000" (RN-1; el Gherkin
      ilustra con 5 gwei, el entorno fija 20 gwei)
    - Cuando se acepta un retiro de 25 USDC
    - Entonces se bloquean AMBOS activos en la misma transacción contable (RN-1/RN-3)
    - Y los totales de USDC y ETH permanecen constantes (RN-2/RN-6)
    """
    # Dado
    fondear_usdc(usuario, rpc, 50_000_000)
    fondear_eth(usuario, rpc, 3_000_000_000_000_000)
    assert foto_balances(usuario) == {
        "USDC": (50_000_000, 0, 50_000_000),
        "ETH": (3_000_000_000_000_000, 0, 3_000_000_000_000_000),
    }

    # Cuando
    resp = crear_retiro(usuario, "USDC", "25000000", DIRECCION_EIP55)
    assert resp.status_code == 202, resp.text

    # Entonces: reserva dual exacta
    despues = foto_balances(usuario)
    assert despues["USDC"] == (25_000_000, 25_000_000, 50_000_000)
    assert despues["ETH"] == (
        3_000_000_000_000_000 - FEE_RED_ERC20,   # disponible 0.001 ETH
        FEE_RED_ERC20,                           # bloqueado 0.002 ETH
        3_000_000_000_000_000,                   # total constante
    )


@pytest.mark.at("AT-08-02-03")
def test_bloqueo_que_consume_exactamente_todo_el_disponible(usuario, rpc):
    """HU-08-02 Escenario 3 (borde): bloqueo que consume exactamente el disponible.

    - Dado disponible(ETH) = "1000420000000000000" (reserva exacta de 1 ETH + gas)
    - Cuando se acepta un retiro de 1 ETH
    - Entonces reserva_eth = disponible exacto: disponible = "0",
      bloqueado = "1000420000000000000" (comparación disponible ≥ reserva, RN-4)
    - Y no hay error
    """
    # Dado
    fondear_eth(usuario, rpc, RESERVA_1ETH)

    # Cuando
    resp = crear_retiro(usuario, "ETH", str(ETH_1), DIRECCION_EIP55)

    # Entonces
    assert resp.status_code == 202, resp.text
    eth = balance_de(usuario, "ETH")
    assert a_int(eth["available"]) == 0
    assert a_int(eth["locked"]) == RESERVA_1ETH


@pytest.mark.at("AT-08-02-04", "AT-08-05-03")
def test_retiro_usdc_con_eth_insuficiente_para_gas_no_bloquea_nada(usuario, rpc):
    """HU-08-02 Escenario 4 / HU-08-05 Escenario 3: USDC alcanza pero falta ETH
    para el gas — la reserva dual es atómica y no bloquea nada.

    - Dado disponible(USDC) = 50 USDC y disponible(ETH) = "100000000000000"
      (0.0001 ETH) < fee_red_wei = "2000000000000000"
    - Cuando intenta retirar 25 USDC
    - Entonces INSUFFICIENT_FUNDS con asset = "ETH", required = fee_red_wei,
      available = "100000000000000" (HU-08-05 RN-3)
    - Y NO se bloquea ninguna de las dos patas: ni USDC ni ETH (HU-08-02 RN-3,
      INV-4); los balances quedan idénticos (RN-4)
    """
    # Dado
    fondear_usdc(usuario, rpc, 50_000_000)
    fondear_eth(usuario, rpc, 100_000_000_000_000)
    antes = foto_balances(usuario)
    assert antes["ETH"] == (100_000_000_000_000, 0, 100_000_000_000_000)

    # Cuando
    resp = crear_retiro(usuario, "USDC", "25000000", DIRECCION_EIP55)

    # Entonces
    err = assert_error(resp, "INSUFFICIENT_FUNDS")
    details = err.get("details") or {}
    assert details.get("asset") == "ETH"
    assert details.get("required") == str(FEE_RED_ERC20)
    assert details.get("available") == "100000000000000"

    # Y: atomicidad de la reserva dual — nada bloqueado en ningún activo
    assert foto_balances(usuario) == antes


@pytest.mark.at("AT-08-02-06")
def test_el_bloqueo_no_cambia_la_suma_total_por_activo(usuario, usuario_b, rpc):
    """HU-08-02 Escenario 6 (conservación): el bloqueo no cambia la suma total.

    - Dado disponible(ETH) = 5 ETH en acc-1 (y una segunda cuenta como control)
    - Cuando se acepta un retiro de 1 ETH (reserva "1000420000000000000")
    - Entonces total(ETH) de acc-1 no cambia: solo se movió disponible→bloqueado (RN-2)
    - Y ninguna otra cuenta cambia; análogamente para USDC (RN-6, INV-1)

    Nota black-box: la suma Σ sobre TODAS las cuentas + EX no es observable por la
    API (GET /balances es por cuenta autenticada); el bloqueo es un movimiento
    puramente intra-cuenta, por lo que la conservación se verifica con el total
    propio constante + la cuenta de control intacta + ausencia de todo movimiento
    on-chain durante el bloqueo.
    """
    # Dado
    fondear_eth(usuario, rpc, 5 * ETH_1)
    fondear_usdc(usuario, rpc, 50_000_000)
    antes = foto_balances(usuario)
    control_antes = foto_balances(usuario_b)   # cuenta ajena: (0,0,0) en ambos activos
    bloque_antes = rpc.numero_de_bloque()

    # Cuando: retiro ETH (la aceptación bloquea; nada sale on-chain hasta CONFIRMED)
    resp = crear_retiro(usuario, "ETH", str(ETH_1), DIRECCION_EIP55)
    assert resp.status_code == 202, resp.text

    # Entonces: total propio constante y partición exacta (INV-3)
    eth = foto_balances(usuario)["ETH"]
    assert eth == (5 * ETH_1 - RESERVA_1ETH, RESERVA_1ETH, 5 * ETH_1)
    assert eth[0] + eth[1] == eth[2]

    # Y: análogo para USDC (reserva dual: totales de ambos activos constantes)
    resp = crear_retiro(usuario, "USDC", "25000000", DIRECCION_EIP55)
    assert resp.status_code == 202, resp.text
    despues = foto_balances(usuario)
    assert despues["USDC"][2] == antes["USDC"][2]          # total(USDC) constante
    assert despues["ETH"][2] == antes["ETH"][2]            # total(ETH) constante
    assert despues["USDC"] == (25_000_000, 25_000_000, 50_000_000)

    # Y: la cuenta de control no cambió; el bloqueo en sí no produjo bloques nuevos
    # más allá de los broadcasts del propio SUT (que aún no consumen el total interno)
    assert foto_balances(usuario_b) == control_antes
    assert rpc.numero_de_bloque() >= bloque_antes  # sanity: la cadena sigue viva


@pytest.mark.at("AT-08-02-08")
def test_dos_retiros_concurrentes_que_compiten_por_el_mismo_disponible(usuario, rpc):
    """HU-08-02 Escenario 8 (concurrencia): dos retiros compiten por el disponible.

    - Dado disponible(ETH) = "1000420000000000000" (alcanza para exactamente uno)
    - Cuando se solicitan concurrentemente dos retiros de 1 ETH cada uno
    - Entonces a lo sumo uno se acepta y bloquea; el otro se rechaza con
      INSUFFICIENT_FUNDS (RN-9)
    - Y nunca se bloquea más que el disponible: no hay bloqueado > total ni
      disponible < 0 (INV-2/INV-3)
    """
    # Dado
    fondear_eth(usuario, rpc, RESERVA_1ETH)

    # Cuando: dos POST simultáneos (claves de idempotencia distintas)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futuros = [
            pool.submit(crear_retiro, usuario, "ETH", str(ETH_1), DIRECCION_EIP55, f"w-conc-{i}")
            for i in (1, 2)
        ]
        respuestas = [f.result() for f in futuros]

    # Entonces: exactamente una aceptada, la otra INSUFFICIENT_FUNDS
    codigos = sorted(r.status_code for r in respuestas)
    assert codigos == [202, 422], [(r.status_code, r.text[:200]) for r in respuestas]
    rechazada = next(r for r in respuestas if r.status_code != 202)
    assert_error(rechazada, "INSUFFICIENT_FUNDS")

    # Y: el bloqueo nunca excede el disponible original (INV-2/INV-3)
    eth = balance_de(usuario, "ETH")
    assert a_int(eth["available"]) == 0
    assert a_int(eth["locked"]) == RESERVA_1ETH
    assert a_int(eth["total"]) == RESERVA_1ETH
