"""Épica 02 — HU-02-01 Consultar balances: tests de aceptación black-box.

Verifica GET /api/v1/balances (HU-09-01 RN-9) contra las reglas de HU-02-01:
buckets available/locked/total por activo, partición INV-3, no-negatividad
INV-2, serialización de montos como string (convenciones-monetarias §5) y
aislamiento por cuenta.

El "Dado" de cada escenario se construye black-box: depósitos on-chain reales
(épicas 06+07) para el disponible y órdenes/retiros (épicas 04/08) para el
bloqueado.
"""

import pytest

from comunes_ep02 import (
    FEE_RED_ERC20_WEI,
    PRECIO_BANDA_BAJA,
    PRECIO_MATCHING,
    balance,
    balances_por_activo,
    cancelar_si_posible,
    crear_retiro,
    fondear_eth,
    fondear_usdc,
    orden_creada,
    orden_resting,
)
from helpers.errores import assert_error, validar_envelope
from helpers.montos import WEI_POR_ETH, a_str, es_monto_valido


@pytest.mark.at("AT-02-01-01")
def test_consulta_con_fondos_en_ambos_buckets(usuario, rpc):
    """HU-02-01 Escenario 1: Consulta con fondos en ambos buckets.

    - Dado un trader con ETH disponible 1500000000000000000 (1.5 ETH) y bloqueado 0
    - Y USDC disponible 3000000000 (3000) y bloqueado 2000000000 (2000, por una orden)
    - Cuando consulta sus balances
    - Entonces ETH: available "1500000000000000000", locked "0", total "1500000000000000000"
    - Y USDC: available "3000000000", locked "2000000000", total "5000000000"
    - Y todos los montos matchean ^(0|[1-9][0-9]*)$
    """
    # Dado: 1.5 ETH y 5000 USDC depositados; una orden BUY limit bloquea 2000 USDC
    # (2 ETH @ 1000.00, banda baja: lock_quote = floor(2e18 × 1e9 / 1e18) = 2000000000,
    #  HU-02-02 RN-1)
    fondear_eth(usuario, rpc, 1_500_000_000_000_000_000)
    fondear_usdc(usuario, rpc, 5_000_000_000)
    orden = orden_resting(usuario, "BUY", 2 * WEI_POR_ETH, PRECIO_BANDA_BAJA)
    try:
        # Cuando
        por_activo = balances_por_activo(usuario)

        # Entonces (RN-4: exactamente available/locked/total, montos exactos)
        eth, usdc = por_activo["ETH"], por_activo["USDC"]
        assert eth["available"] == "1500000000000000000"
        assert eth["locked"] == "0"
        assert eth["total"] == "1500000000000000000"
        assert usdc["available"] == "3000000000"
        assert usdc["locked"] == "2000000000"
        assert usdc["total"] == "5000000000"

        # Y: serialización string (RN-7; balances_por_activo ya la valida campo a campo)
        for item in por_activo.values():
            for campo in ("available", "locked", "total"):
                assert es_monto_valido(item[campo]), (campo, item)
    finally:
        cancelar_si_posible(usuario, orden["orderId"])


@pytest.mark.at("AT-02-01-02")
def test_cuenta_recien_creada_reporta_ambos_activos_en_cero(usuario):
    """HU-02-01 Escenario 2 (borde): Cuenta recién creada, sin movimientos.

    - Dado un trader autenticado cuya cuenta nunca recibió depósitos ni operó
    - Cuando consulta sus balances
    - Entonces la respuesta lista ambos activos (RN-3)
    - Y ETH y USDC reportan available "0", locked "0", total "0"
    """
    # Dado: el fixture `usuario` es una cuenta fresca sin movimientos

    # Cuando
    por_activo = balances_por_activo(usuario)

    # Entonces / Y (RN-3: ambos activos presentes aun con saldo cero)
    for activo in ("ETH", "USDC"):
        assert por_activo[activo]["available"] == "0", por_activo[activo]
        assert por_activo[activo]["locked"] == "0", por_activo[activo]
        assert por_activo[activo]["total"] == "0", por_activo[activo]


@pytest.mark.at("AT-02-01-03")
def test_particion_total_igual_disponible_mas_bloqueado(usuario, rpc):
    """HU-02-01 Escenario 3 (borde): Partición total = disponible + bloqueado.

    - Dado un trader con USDC disponible 4500000 y bloqueado 5500000
    - Cuando consulta sus balances
    - Entonces USDC.total es "10000000"
    - Y total == available + locked para cada activo (RN-5 / INV-3)

    El bloqueado de 5.5 USDC no puede construirse con una orden (BELOW_MIN_NOTIONAL,
    mínimo 10 USDC): se construye con un retiro USDC aceptado (WITHDRAWAL_LOCK,
    HU-02-02 RN-10). Se fondea además ETH por la previsión de gas que la épica 08
    exige para retiros USDC (HU-08-02 RN-1, reserva dual).
    """
    # Dado: 10 USDC depositados y un retiro de 5.5 USDC aceptado que bloquea 5500000
    fondear_usdc(usuario, rpc, 10_000_000)
    fondear_eth(usuario, rpc, 10_000_000_000_000_000)  # 0.01 ETH para la previsión de gas
    resp = crear_retiro(usuario, "USDC", 5_500_000)
    assert resp.status_code == 202, resp.text

    # Cuando
    por_activo = balances_por_activo(usuario)

    # Entonces: partición exacta en USDC
    usdc = por_activo["USDC"]
    assert usdc["available"] == "4500000"
    assert usdc["locked"] == "5500000"
    assert usdc["total"] == "10000000"

    # Y: total == available + locked para CADA activo de la respuesta
    # (balances_por_activo lo valida por activo; acá queda explícito).
    for item in por_activo.values():
        assert int(item["total"]) == int(item["available"]) + int(item["locked"]), item

    # Y: la reserva dual del retiro USDC bloquea además la previsión de gas en
    # ETH (HU-02-02 RN-10 según el modelo de la épica 08 — ADR-006 D2; HU-08-02
    # RN-1: fee_red_wei = GAS_LIMIT_ERC20 × gas_price = 100000 × 20 gwei,
    # valores del entorno). El total de ETH es invariante al bloqueo (INV-3).
    eth = por_activo["ETH"]
    assert eth["locked"] == a_str(FEE_RED_ERC20_WEI)
    assert eth["locked"] == "2000000000000000"
    assert eth["available"] == a_str(10_000_000_000_000_000 - FEE_RED_ERC20_WEI)
    assert eth["total"] == "10000000000000000"


@pytest.mark.at("AT-02-01-04")
def test_saldos_grandes_que_exceden_2_a_la_53(usuario, rpc):
    """HU-02-01 Escenario 4 (borde): Saldos grandes que exceden 2^53.

    - Dado un trader con ETH disponible 123456789012345678901 (≈123.45 ETH, > 2^53 wei)
    - Cuando consulta sus balances
    - Entonces ETH.available es el string exacto "123456789012345678901"
    - Y el valor NO se serializa como número JSON
    """
    # Dado: depósito on-chain por el monto exacto (no cabe en IEEE-754 sin pérdida)
    monto = 123456789012345678901
    assert monto > 2**53
    fondear_eth(usuario, rpc, monto)

    # Cuando
    eth = balance(usuario, "ETH")

    # Entonces: string exacto, sin pérdida de precisión (RN-7)
    assert eth["available"] == "123456789012345678901"

    # Y: es string (un número JSON llegaría como int/float tras el parseo)
    assert isinstance(eth["available"], str)
    assert es_monto_valido(eth["available"])


@pytest.mark.at("AT-02-01-05")
def test_consulta_sin_autenticacion_rechaza_unauthenticated(api):
    """HU-02-01 Escenario 5 (error): Sin autenticación.

    - Dado un cliente sin credencial válida (ausente, inválida o expirada)
    - Cuando intenta consultar balances
    - Entonces se rechaza con code UNAUTHENTICATED y HTTP 401 (RN-1)
    - Y no se devuelve ningún balance
    """
    # Cuando: sin header Authorization (el fixture `api` no lleva token)
    resp = api.get("/balances")

    # Entonces: envelope uniforme + code + status del catálogo
    assert_error(resp, "UNAUTHENTICATED")

    # Y: la respuesta de error no incluye datos de balance (modelo-de-errores §1)
    cuerpo = resp.json()
    assert not any(k in cuerpo for k in ("available", "locked", "total", "asset")), cuerpo

    # Y (credencial inválida): un token basura también produce UNAUTHENTICATED
    with api.con_token("token-invalido-ep02") as cliente:
        resp = cliente.get("/balances")
    assert_error(resp, "UNAUTHENTICATED")


@pytest.mark.at("AT-02-01-06")
def test_acceso_a_balances_ajenos_es_condicional_y_no_filtra_datos(usuario, usuario_b, rpc):
    """HU-02-01 Escenario 6 (error, condicional): Acceso a balances ajenos.

    - Dado un trader autenticado como cuenta A
    - Si la implementación expone alguna vía que reciba un accountId explícito
    - Cuando A la invoca con accountId = B (ajeno)
    - Entonces se rechaza con UNAUTHORIZED (403) y no se filtra ningún dato de B
    - Y si no expone ninguna vía con accountId (RN-2: la cuenta se infiere de la
      credencial), el AT se considera satisfecho (patrón condicional HU-01-04 RN-3)

    Black-box se sondean las vías plausibles: cada sonda debe (a) rechazar con
    UNAUTHORIZED, o (b) no existir (404) / rechazar el parámetro (422), o
    (c) ignorar el parámetro y devolver SOLO los balances de A. Nunca datos de B.
    """
    # Dado: A y B con saldos USDC distinguibles
    fondear_usdc(usuario, rpc, 1_234_000_000)    # A: 1234 USDC
    fondear_usdc(usuario_b, rpc, 7_654_000_000)  # B: 7654 USDC
    assert balance(usuario, "USDC")["available"] == "1234000000"

    sondas = [
        ("GET /balances?accountId=<B>",
         lambda: usuario.api.get("/balances", params={"accountId": usuario_b.account_id})),
        ("GET /balances/<accountId de B>",
         lambda: usuario.api.get(f"/balances/{usuario_b.account_id}")),
    ]
    for nombre, sonda in sondas:
        # Cuando: A intenta forzar el acceso a la cuenta B
        resp = sonda()

        # Entonces: ninguna vía revela datos de B
        if resp.status_code == 200:
            # la vía ignora el accountId: debe devolver los balances PROPIOS de A (RN-2)
            cuerpo = resp.json()
            assert isinstance(cuerpo, list), f"{nombre}: forma inesperada {cuerpo!r}"
            usdc = next((i for i in cuerpo if i.get("asset") == "USDC"), None)
            assert usdc is not None and usdc["available"] == "1234000000", (
                f"{nombre}: con 200 debe responder los balances de A, no otros"
            )
        elif resp.status_code == 403:
            # la vía existe y rechaza actuar a nombre de otra cuenta (el caso del AT)
            assert_error(resp, "UNAUTHORIZED")
        elif resp.status_code == 404:
            # la vía no está expuesta (o el recurso ajeno no se revela): envelope 404
            err = validar_envelope(resp.json())
            assert err["code"] in ("NOT_FOUND", "ACCOUNT_NOT_FOUND"), err
        elif resp.status_code == 422:
            # la vía rechaza el parámetro no soportado
            assert_error(resp, "VALIDATION_ERROR")
        else:
            raise AssertionError(
                f"{nombre}: status inesperado {resp.status_code}: {resp.text[:200]}"
            )

        # Y: en ningún caso aparece el saldo de B en la respuesta
        assert "7654000000" not in resp.text, f"{nombre}: filtró datos de la cuenta B"


@pytest.mark.at("AT-02-01-07")
def test_balances_coinciden_con_la_reconstruccion_del_ledger(usuario, usuario_b, rpc):
    """HU-02-01 Escenario 7 (consistencia): Coincide con la reconstrucción del ledger.

    - Dado la secuencia: 1) DEPOSIT 5000 USDC; 2) ORDER_LOCK 2000 USDC;
      3) TRADE_FILL como comprador taker de 1 ETH @ 2000.00 (fee_base taker =
      ceil(1e18 × 20 / 10000) = 2000000000000000 wei)
    - Cuando se consultan sus balances
    - Entonces USDC available "3000000000", locked "0", total "3000000000";
      ETH available "998000000000000000", locked "0", total "998000000000000000"
    - Y esos valores coinciden con la reconstrucción Σ CREDIT − Σ DEBIT (INV-8)

    Nota: el ledger no tiene superficie en el contrato de la épica 09, así que la
    reconstrucción se verifica por su proyección observable: los balances
    reportados son EXACTAMENTE los que producen los asientos normativos de la
    secuencia (RN-9). La inspección directa de postings se evalúa por otra vía
    (ver no_automatizables_ep02.yaml, HU-02-03).
    """
    # Dado: contraparte maker con 1 ETH resting SELL @ 2000.00 (banda de matching)
    fondear_eth(usuario_b, rpc, WEI_POR_ETH)
    maker = orden_resting(usuario_b, "SELL", WEI_POR_ETH, PRECIO_MATCHING)
    try:
        # 1) DEPOSIT 5000 USDC
        fondear_usdc(usuario, rpc, 5_000_000_000)
        # 2)+3) ORDER_LOCK de 2000 USDC y TRADE_FILL como comprador taker en la
        # misma alta (la BUY cruza el ask resting; el settlement es atómico, INV-4)
        taker = orden_creada(usuario, "BUY", "LIMIT", WEI_POR_ETH, PRECIO_MATCHING)
        assert taker["status"] == "FILLED", taker
        assert taker["filledWei"] == "1000000000000000000"

        # Cuando / Entonces: exactamente los valores que reconstruye el ledger
        por_activo = balances_por_activo(usuario)
        usdc, eth = por_activo["USDC"], por_activo["ETH"]
        assert usdc["available"] == "3000000000"
        assert usdc["locked"] == "0"
        assert usdc["total"] == "3000000000"
        assert eth["available"] == "998000000000000000"
        assert eth["locked"] == "0"
        assert eth["total"] == "998000000000000000"
    finally:
        cancelar_si_posible(usuario_b, maker["orderId"])
