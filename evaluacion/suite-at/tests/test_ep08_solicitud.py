"""Épica 08 — HU-08-01 (solicitar retiro): validación, mínimos, EIP-55, fondos,
idempotencia y precedencia de errores.

Black-box: sólo el contrato REST de la épica 09 (`POST /withdrawals`,
`GET /withdrawals[/{id}]`, `GET /balances`) + fondeo por depósito on-chain real.
Prevalece 00-fundaciones (modelo-de-errores §4: precedencia determinista;
convenciones-monetarias §5: montos como string `^(0|[1-9][0-9]*)$`).
"""

import pytest

from helpers.eip55 import a_checksum, romper_checksum
from helpers.errores import assert_error
from helpers.montos import a_int, es_monto_valido

from comunes_ep08 import (
    DIRECCION_EIP55,
    FEE_RED_ERC20,
    FEE_RED_ETH,
    MIN_WITHDRAWAL_ETH,
    balance_de,
    crear_retiro,
    destino_revertidor,
    esperar_broadcast,
    esperar_retiro,
    fondear_eth,
    fondear_usdc,
    foto_balances,
    listar_retiros,
    retiro_de,
)

ETH_1 = 10**18


@pytest.mark.at("AT-08-01-01")
def test_solicitud_de_retiro_eth_valida(usuario, rpc):
    """HU-08-01 Escenario 1: solicitud de retiro de ETH válida (feliz).

    - Dado un trader con disponible(ETH) = 5 ETH y fee_red_wei = 21000 × 20 gwei
      = "420000000000000" (RN-8; GAS_PRICE_WEI del entorno = 20 gwei)
    - Cuando solicita retirar 1 ETH a una dirección con checksum EIP-55 válido
    - Entonces la solicitud se acepta y se crea un retiro PENDING
    - Y required = amount + fee_red_wei ≤ disponible(ETH) pasa la validación (RN-9)
    """
    # Dado: 5 ETH acreditados por depósito on-chain real
    fondear_eth(usuario, rpc, 5 * ETH_1)
    assert a_int(balance_de(usuario, "ETH")["available"]) == 5 * ETH_1
    # required = 1 ETH + fee_red = "1000420000000000000" ≤ 5 ETH (RN-9)
    assert ETH_1 + FEE_RED_ETH <= 5 * ETH_1

    # Cuando
    resp = crear_retiro(usuario, "ETH", str(ETH_1), DIRECCION_EIP55)

    # Entonces: 202 con el retiro PENDING (épica 09 RN-11)
    assert resp.status_code == 202, resp.text
    retiro = resp.json()
    assert retiro["status"] == "PENDING"
    assert retiro["asset"] == "ETH"
    assert retiro["amountMinUnit"] == str(ETH_1)
    assert es_monto_valido(retiro["amountMinUnit"])
    assert retiro["address"] == DIRECCION_EIP55
    assert retiro["withdrawalId"]
    assert isinstance(retiro["createdAt"], str) and isinstance(retiro["updatedAt"], str)


@pytest.mark.at("AT-08-01-02")
def test_solicitud_de_retiro_usdc_valida(usuario, rpc):
    """HU-08-01 Escenario 2: solicitud de retiro de USDC válida (feliz).

    - Dado disponible(USDC) = 50 USDC y disponible(ETH) suficiente para el gas
      (fee_red_wei = 100000 × 20 gwei = "2000000000000000"; el Gherkin ilustra
      con 5 gwei, el entorno fija GAS_PRICE_WEI = 20 gwei)
    - Cuando solicita retirar 25 USDC a una dirección EIP-55 válida
    - Entonces valida USDC ≥ amount y ETH ≥ fee_red_wei (RN-9) y crea un retiro PENDING
    """
    # Dado
    fondear_usdc(usuario, rpc, 50_000_000)
    fondear_eth(usuario, rpc, 3_000_000_000_000_000)  # 0.003 ETH ≥ fee_red (0.002)
    assert a_int(balance_de(usuario, "USDC")["available"]) >= 25_000_000
    assert a_int(balance_de(usuario, "ETH")["available"]) >= FEE_RED_ERC20

    # Cuando
    resp = crear_retiro(usuario, "USDC", "25000000", DIRECCION_EIP55)

    # Entonces
    assert resp.status_code == 202, resp.text
    retiro = resp.json()
    assert retiro["status"] == "PENDING"
    assert retiro["asset"] == "USDC"
    assert retiro["amountMinUnit"] == "25000000"


@pytest.mark.at("AT-08-01-03a")
def test_monto_exactamente_igual_al_minimo_pasa(usuario, rpc):
    """HU-08-01 Escenario 3a (borde): monto exactamente igual al mínimo pasa.

    - Dado un trader con fondos suficientes
    - Cuando solicita retirar ETH por MIN_WITHDRAWAL_ETH = "1000000000000000"
    - Entonces la validación de mínimo pasa (comparación amount ≥ mínimo, RN-7)
      y la solicitud se acepta
    """
    # Dado
    fondear_eth(usuario, rpc, 10**16)  # 0.01 ETH

    # Cuando
    resp = crear_retiro(usuario, "ETH", str(MIN_WITHDRAWAL_ETH), DIRECCION_EIP55)

    # Entonces
    assert resp.status_code == 202, resp.text
    assert resp.json()["status"] == "PENDING"


@pytest.mark.at("AT-08-01-03b")
def test_monto_un_wei_por_debajo_del_minimo_falla(usuario, rpc):
    """HU-08-01 Escenario 3b (borde): monto 1 wei por debajo del mínimo falla.

    - Dado un trader con fondos suficientes
    - Cuando solicita retirar ETH por "999999999999999" (mínimo − 1 wei)
    - Entonces WITHDRAWAL_BELOW_MIN (422) con details {asset, amount, minWithdrawal} (RN-7)
    - Y no se bloquea ningún fondo (RN-12)
    """
    # Dado
    fondear_eth(usuario, rpc, 10**16)
    antes = foto_balances(usuario)

    # Cuando
    resp = crear_retiro(usuario, "ETH", "999999999999999", DIRECCION_EIP55)

    # Entonces
    err = assert_error(resp, "WITHDRAWAL_BELOW_MIN")
    details = err.get("details") or {}
    assert details.get("asset") == "ETH"
    assert details.get("amount") == "999999999999999"
    assert details.get("minWithdrawal") == str(MIN_WITHDRAWAL_ETH)
    assert es_monto_valido(details["amount"]) and es_monto_valido(details["minWithdrawal"])

    # Y: balances idénticos (RN-12, INV-2)
    assert foto_balances(usuario) == antes


@pytest.mark.at("AT-08-01-04")
def test_direccion_en_minusculas_se_acepta_y_normaliza(usuario, rpc):
    """HU-08-01 Escenario 4 (borde): dirección en minúsculas se acepta y normaliza.

    - Dado un trader con fondos suficientes
    - Cuando solicita un retiro a la dirección toda en minúsculas (sin checksum mixto)
    - Entonces se acepta (RN-5) y se normaliza a su forma con checksum EIP-55
    - Y la solicitud continúa la validación de monto y fondos (202)
    """
    # Dado
    fondear_eth(usuario, rpc, 10**16)
    minusculas = DIRECCION_EIP55.lower()

    # Cuando
    resp = crear_retiro(usuario, "ETH", str(MIN_WITHDRAWAL_ETH), minusculas)

    # Entonces: aceptada y normalizada a EIP-55 en la respuesta y en el detalle
    assert resp.status_code == 202, resp.text
    retiro = resp.json()
    assert retiro["address"] == a_checksum(minusculas) == DIRECCION_EIP55
    detalle = retiro_de(usuario, retiro["withdrawalId"])
    assert detalle["address"] == DIRECCION_EIP55


@pytest.mark.at("AT-08-01-05")
def test_direccion_con_checksum_eip55_invalido(usuario, rpc):
    """HU-08-01 Escenario 5 (error): dirección con checksum EIP-55 inválido.

    - Dado un trader con fondos suficientes
    - Cuando solicita un retiro a una dirección con caja mixta que NO satisface EIP-55
    - Entonces INVALID_ADDRESS (422) con details.address con el valor recibido (RN-5)
    - Y no se bloquea ningún fondo (RN-12)
    """
    # Dado
    fondear_eth(usuario, rpc, 10**16)
    antes = foto_balances(usuario)
    rota = romper_checksum(DIRECCION_EIP55)

    # Cuando
    resp = crear_retiro(usuario, "ETH", str(MIN_WITHDRAWAL_ETH), rota)

    # Entonces
    err = assert_error(resp, "INVALID_ADDRESS")
    assert (err.get("details") or {}).get("address") == rota

    # Y
    assert foto_balances(usuario) == antes


@pytest.mark.at("AT-08-01-06")
def test_direccion_con_longitud_o_prefijo_invalidos(usuario):
    """HU-08-01 Escenario 6 (error): dirección con longitud o prefijo inválidos.

    - Dado un trader autenticado
    - Cuando solicita un retiro a "0x1234" (corta), a 40 hex sin prefijo 0x, o con
      caracteres no hexadecimales
    - Entonces INVALID_ADDRESS (422) (RN-4), antes de evaluar monto o fondos (RN-11)
    """
    invalidas = [
        "0x1234",                                        # no son 40 hex
        DIRECCION_EIP55[2:],                             # sin prefijo 0x
        "0xZZ08400098527886E0F7030069857D2E4169EE7",     # caracteres no hex
    ]
    for direccion in invalidas:
        # Cuando (sin fondos: la validación de dirección precede a la de fondos, RN-11)
        resp = crear_retiro(usuario, "ETH", str(MIN_WITHDRAWAL_ETH), direccion)
        # Entonces
        assert_error(resp, "INVALID_ADDRESS")


@pytest.mark.at("AT-08-01-07")
def test_monto_no_positivo(usuario):
    """HU-08-01 Escenario 7 (error): monto no positivo.

    - Dado un trader autenticado con dirección válida
    - Cuando solicita asset = ETH, amount = "0"
    - Entonces WITHDRAWAL_AMOUNT_INVALID (422) (RN-6; el patrón admite "0" pero el
      monto debe ser estrictamente positivo)
    - Y no se bloquea ningún fondo
    """
    antes = foto_balances(usuario)

    # Cuando
    resp = crear_retiro(usuario, "ETH", "0", DIRECCION_EIP55)

    # Entonces
    assert_error(resp, "WITHDRAWAL_AMOUNT_INVALID")

    # Y
    assert foto_balances(usuario) == antes


@pytest.mark.at("AT-08-01-08")
def test_monto_con_formato_invalido(usuario):
    """HU-08-01 Escenario 8 (error): monto con formato inválido (no matchea el patrón).

    - Dado un trader autenticado
    - Cuando solicita amount = "1.5" | "1e18" | "-5" | "01" | 1000 (número JSON)
    - Entonces VALIDATION_ERROR (422) con details.issues (RN-2), por violar
      ^(0|[1-9][0-9]*)$
    - Y se evalúa antes que dirección, mínimo o fondos (RN-11)
    """
    variantes = ["1.5", "1e18", "-5", "01", 1000]
    for amount in variantes:
        # Cuando
        resp = crear_retiro(usuario, "ETH", amount, DIRECCION_EIP55)
        # Entonces
        err = assert_error(resp, "VALIDATION_ERROR")
        assert "issues" in (err.get("details") or {}), err

    # Y: el error de esquema precede al de dirección (RN-11: paso 2 antes que paso 4)
    resp = crear_retiro(usuario, "ETH", "1.5", "0x1234")
    assert_error(resp, "VALIDATION_ERROR")


@pytest.mark.at("AT-08-01-09")
def test_activo_no_soportado(usuario):
    """HU-08-01 Escenario 9 (error): activo no soportado.

    - Dado un trader autenticado
    - Cuando solicita asset = "BTC" (fuera de {ETH, USDC})
    - Entonces VALIDATION_ERROR (422) (RN-3: no existe un código INVALID_ASSET)
    """
    resp = crear_retiro(usuario, "BTC", "25000000", DIRECCION_EIP55)
    assert_error(resp, "VALIDATION_ERROR")


@pytest.mark.at("AT-08-01-10", "AT-08-02-05")
def test_fondos_insuficientes_en_eth_para_principal_mas_gas(usuario, rpc):
    """HU-08-01 Escenario 10 / HU-08-02 Escenario 5: ETH insuficiente para
    principal + gas no bloquea nada.

    - Dado disponible(ETH) = 1 ETH exacto y fee_red_wei = "420000000000000"
    - Cuando solicita retirar 1 ETH (todo su disponible)
    - Entonces required = "1000420000000000000" > disponible e INSUFFICIENT_FUNDS
      (422) con details {asset: ETH, required, available} (HU-08-01 RN-9)
    - Y no se bloquea ningún fondo: disponible y bloqueado quedan intactos
      (HU-08-01 RN-12, HU-08-02 RN-4, INV-2)
    """
    # Dado: exactamente 1 ETH acreditado (cuenta fresca)
    fondear_eth(usuario, rpc, ETH_1)
    antes = foto_balances(usuario)
    assert antes["ETH"] == (ETH_1, 0, ETH_1)

    # Cuando
    resp = crear_retiro(usuario, "ETH", str(ETH_1), DIRECCION_EIP55)

    # Entonces
    err = assert_error(resp, "INSUFFICIENT_FUNDS")
    details = err.get("details") or {}
    assert details.get("asset") == "ETH"
    assert details.get("required") == str(ETH_1 + FEE_RED_ETH)   # "1000420000000000000"
    assert details.get("available") == str(ETH_1)
    assert es_monto_valido(details["required"]) and es_monto_valido(details["available"])

    # Y: balances idénticos, nada bloqueado
    assert foto_balances(usuario) == antes


@pytest.mark.at("AT-08-01-11")
def test_retiro_usdc_sin_eth_para_el_gas(usuario, rpc):
    """HU-08-01 Escenario 11 (error): USDC suficiente pero sin ETH para el gas.

    - Dado disponible(USDC) = 50 USDC y disponible(ETH) = "0"
    - Cuando solicita retirar 25 USDC
    - Entonces INSUFFICIENT_FUNDS (422) con details.asset = "ETH",
      required = fee_red_wei y available = "0" (RN-9)
    """
    # Dado (sin fondear ETH: cuenta fresca ⇒ disponible(ETH) = 0)
    fondear_usdc(usuario, rpc, 50_000_000)
    assert a_int(balance_de(usuario, "ETH")["available"]) == 0

    # Cuando
    resp = crear_retiro(usuario, "USDC", "25000000", DIRECCION_EIP55)

    # Entonces
    err = assert_error(resp, "INSUFFICIENT_FUNDS")
    details = err.get("details") or {}
    assert details.get("asset") == "ETH"
    assert details.get("required") == str(FEE_RED_ERC20)  # "2000000000000000"
    assert details.get("available") == "0"


# --- Status HTTP del reenvío idempotente: criterio {200, 202} ------------------
# Aplica a los dos tests siguientes (AT-08-01-12 / AT-08-02-07 y AT-08-01-12b).
# Ratificado en la ventana de ajuste H6 (`runs/piloto-01/checklist-h6.md` ítem 3).
#
# spec-v1.1 fija 202 para la **creación** del retiro y funda ese status en la
# asincronía del procesamiento: HU-09-01 RN-11 ("Responde 202 Accepted … porque el
# procesamiento on-chain (firma EIP-155 + broadcast) es asíncrono"), fila "Crear
# retiro" del mapa de endpoints. Para el **reenvío idempotente** no fija ninguno:
# ni HU-08-01 RN-10 ni sus Escenarios 12/12b mencionan status, y lo que ambos
# exigen —mismo retiro, sin crear otro, sin volver a bloquear fondos— es
# exactamente lo que estos tests verifican. Un reenvío sobre un retiro ya terminal
# no acepta nada para procesar, así que 200 es tan defendible como 202 (la spec
# asigna status por semántica de operación: HU-09-01 RN-21 le da 200 a la
# cancelación de un retiro).
# Aceptar ambos mide lo que la spec cierra y no penaliza la lectura que deja
# abierta. La lectura contraria —que la columna "Éxito 202" del mapa de endpoints
# vale para toda respuesta exitosa de POST /withdrawals— es defendible, y queda
# registrada como candidata a reapertura para una eventual spec-v1.2; spec-v1.1
# está congelada y no se toca.
@pytest.mark.at("AT-08-01-12", "AT-08-02-07")
def test_reenvio_idempotente_devuelve_el_mismo_retiro_sin_doble_bloqueo(usuario, rpc):
    """HU-08-01 Escenario 12 / HU-08-02 Escenario 7: reenvío con la misma clave y
    mismos parámetros es idempotente y no vuelve a bloquear.

    - Dado un retiro ya creado con clientWithdrawalId = "w-123" (1 ETH)
    - Cuando reenvía exactamente la misma solicitud
    - Entonces NO se crea un segundo retiro: se devuelve el mismo identificador
      (HU-08-01 RN-10)
    - Y no hay un segundo WITHDRAWAL_LOCK: los balances no cambian respecto del
      primer bloqueo (HU-08-02 RN-8)
    """
    # Dado
    fondear_eth(usuario, rpc, 5 * ETH_1)
    resp1 = crear_retiro(usuario, "ETH", str(ETH_1), DIRECCION_EIP55, client_id="w-123")
    assert resp1.status_code == 202, resp1.text
    retiro1 = resp1.json()
    despues_del_lock = foto_balances(usuario)
    assert despues_del_lock["ETH"] == (5 * ETH_1 - (ETH_1 + FEE_RED_ETH), ETH_1 + FEE_RED_ETH, 5 * ETH_1)

    # Cuando: reenvío idéntico (misma clave + mismos parámetros)
    resp2 = crear_retiro(usuario, "ETH", str(ETH_1), DIRECCION_EIP55, client_id="w-123")

    # Entonces: mismo retiro, sin crear otro
    assert resp2.status_code in (200, 202), resp2.text  # {200, 202}: ver nota de arriba
    assert resp2.json()["withdrawalId"] == retiro1["withdrawalId"]
    assert len(listar_retiros(usuario)) == 1

    # Y: sin segundo bloqueo (balances idénticos al primer lock)
    assert foto_balances(usuario) == despues_del_lock


@pytest.mark.at("AT-08-01-12b")
def test_reenvio_idempotente_de_un_retiro_ya_failed(usuario, rpc):
    """HU-08-01 Escenario 12b: reenvío de una clave de un retiro ya FAILED (terminal).

    - Dado un retiro con clientWithdrawalId = "w-terminal" ya FAILED (la reserva
      fue liberada; se provoca con un destino cuyo código revierte la transferencia)
    - Cuando reenvía la misma solicitud con la misma clave y parámetros
    - Entonces devuelve el mismo retiro FAILED sin crear uno nuevo ni volver a
      bloquear fondos (RN-10)
    - Y con una clave distinta se evalúa como solicitud nueva
    """
    # Dado: retiro que termina FAILED de forma determinista (tx minada y revertida)
    fondear_eth(usuario, rpc, 2 * ETH_1)
    destino = destino_revertidor(rpc)
    resp1 = crear_retiro(usuario, "ETH", str(ETH_1), destino, client_id="w-terminal")
    assert resp1.status_code == 202, resp1.text
    wid = resp1.json()["withdrawalId"]
    esperar_broadcast(usuario, rpc, wid)
    rpc.minar_bloques(12)
    retiro_failed = esperar_retiro(usuario, wid, ("FAILED",), prohibidos=("CONFIRMED",))
    balances_tras_failed = foto_balances(usuario)
    assert balances_tras_failed["ETH"][1] == 0  # reserva ya liberada (nada bloqueado)

    # Cuando: reenvío idéntico sobre el retiro terminal
    resp2 = crear_retiro(usuario, "ETH", str(ETH_1), destino, client_id="w-terminal")

    # Entonces: mismo retiro FAILED, sin retiro nuevo ni re-bloqueo
    assert resp2.status_code in (200, 202), resp2.text  # {200, 202}: ver nota de arriba
    assert resp2.json()["withdrawalId"] == wid
    assert retiro_de(usuario, wid)["status"] == "FAILED"
    assert len(listar_retiros(usuario)) == 1
    assert foto_balances(usuario) == balances_tras_failed

    # Y: una clave distinta crea una solicitud nueva (retiro independiente)
    resp3 = crear_retiro(
        usuario, "ETH", str(MIN_WITHDRAWAL_ETH), DIRECCION_EIP55, client_id="w-reintento"
    )
    assert resp3.status_code == 202, resp3.text
    assert resp3.json()["withdrawalId"] != wid


@pytest.mark.at("AT-08-01-13")
def test_misma_clave_con_parametros_distintos_es_conflict(usuario, rpc):
    """HU-08-01 Escenario 13 (error de idempotencia): misma clave, parámetros distintos.

    - Dado que ya usó clientWithdrawalId = "w-123" para retirar 1 ETH
    - Cuando reenvía "w-123" con amount = 2 ETH
    - Entonces CONFLICT (409) (RN-10) y no se crea ni modifica ningún retiro
    """
    # Dado
    fondear_eth(usuario, rpc, 5 * ETH_1)
    resp1 = crear_retiro(usuario, "ETH", str(ETH_1), DIRECCION_EIP55, client_id="w-123")
    assert resp1.status_code == 202, resp1.text
    original = resp1.json()
    balances = foto_balances(usuario)

    # Cuando
    resp2 = crear_retiro(usuario, "ETH", str(2 * ETH_1), DIRECCION_EIP55, client_id="w-123")

    # Entonces
    assert_error(resp2, "CONFLICT")
    assert len(listar_retiros(usuario)) == 1
    detalle = retiro_de(usuario, original["withdrawalId"])
    assert detalle["amountMinUnit"] == str(ETH_1)  # el original no se modificó
    assert foto_balances(usuario) == balances      # ni se bloqueó nada adicional


@pytest.mark.at("AT-08-01-14")
def test_solicitud_sin_autenticacion(api):
    """HU-08-01 Escenario 14 (error): solicitud sin autenticación.

    - Dado un cliente sin credencial válida (sin token, o token inválido)
    - Cuando intenta solicitar cualquier retiro
    - Entonces UNAUTHENTICATED (401) (RN-1), antes de cualquier otra validación (RN-11)
    """
    body = {"asset": "ETH", "amountMinUnit": str(ETH_1), "address": DIRECCION_EIP55}

    # Cuando: sin header Authorization
    resp = api.post("/withdrawals", json=body)
    # Entonces
    assert_error(resp, "UNAUTHENTICATED")

    # Cuando: con token inválido
    resp = api.con_token("token-invalido-ep08").post("/withdrawals", json=body)
    # Entonces
    assert_error(resp, "UNAUTHENTICATED")


@pytest.mark.at("AT-08-01-15")
def test_precedencia_con_multiples_violaciones(usuario):
    """HU-08-01 Escenario 15 (precedencia): payload con múltiples violaciones.

    - Dado un trader autenticado
    - Cuando solicita asset = "BTC", amount = "0", address = "0x1234" (todo inválido)
    - Entonces se reporta SOLO VALIDATION_ERROR (activo/esquema), primero en el
      orden de precedencia (RN-11); dirección, monto y fondos no se evalúan
    """
    resp = crear_retiro(usuario, "BTC", "0", "0x1234")
    assert_error(resp, "VALIDATION_ERROR")
