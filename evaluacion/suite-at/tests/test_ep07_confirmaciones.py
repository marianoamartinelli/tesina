"""Épica 07 — Depósitos on-chain: confirmaciones y acreditación (HU-07-03).

Umbral CONFIRMACIONES_REQUERIDAS = 12 (00-fundaciones/activos-y-par-de-trading.md),
cómputo `confirmaciones = max(0, cabeza − bloque_de_inclusión)` (RN-1). Con el
anvil del entorno la cabeza sólo avanza por minado a demanda, así que cada
número de confirmaciones es un estado estable y verificable sin sleeps.

AT-07-03-03 (DEPOSIT_NOT_CONFIRMED ante una solicitud explícita de
acreditación) está declarado en no_automatizables_ep07.yaml: la épica 09 no
expone ningún endpoint que solicite acreditar/usar un depósito por identidad.
"""

import secrets

import pytest

from helpers.errores import assert_error
from helpers.montos import a_int, es_monto_valido

from comunes_ep07 import (
    acreditar_centinela,
    assert_esquema_deposito,
    balance_de,
    bloque_de_inclusion,
    direccion_deposito,
    es_entero_json,
    esperar_confirmaciones,
    esperar_deposito,
    esperar_disponible_exacto,
    esperar_estado_deposito,
    id_deposito,
    listar_depositos,
    log_index_unico,
)


def _tx_hash_inexistente() -> str:
    """txHash bien formado (0x + 64 hex) que no corresponde a ninguna tx."""
    return "0x" + secrets.token_hex(32)


@pytest.mark.at("AT-07-03-01")
def test_acreditacion_al_alcanzar_exactamente_12_confirmaciones(usuario, rpc):
    """HU-07-03 Escenario 1: acreditación al alcanzar exactamente 12 confirmaciones.

    - Dado un depósito ETH PENDIENTE por "1500000000000000000" incluido en B,
      con disponible(ETH) = "0"
    - Y que la cabeza avanza hasta B + 12 (confirmaciones = 12)
    - Cuando el servicio evalúa el depósito
    - Entonces pasa a ACREDITADO y disponible(ETH) = "1500000000000000000"
    - Y total aumenta en el mismo monto y bloqueado no cambia (INV-3)
    """
    # Dado: depósito detectado, aún sin confirmaciones suficientes
    direccion = direccion_deposito(usuario, "ETH")
    monto_wei = 1_500_000_000_000_000_000
    tx_hash = rpc.depositar_eth(direccion, monto_wei, confirmar=False)
    dep_id = id_deposito(tx_hash, 0)
    esperar_deposito(usuario, dep_id)
    assert balance_de(usuario, "ETH")["available"] == "0"

    # Y: la cabeza llega exactamente a B + 12
    rpc.minar_bloques(12)

    # Cuando/Entonces: ACREDITADO y el disponible refleja el monto íntegro (RN-4)
    dep = esperar_estado_deposito(usuario, dep_id, "ACREDITADO")
    assert_esquema_deposito(dep)  # creditedAt presente, required = 12, etc.
    fila = esperar_disponible_exacto(usuario, "ETH", monto_wei)

    # Y: INV-3 — total = available + locked; bloqueado no cambió
    assert fila["locked"] == "0"
    assert a_int(fila["total"]) == a_int(fila["available"]) == monto_wei
    # (el asiento de ledger de RN-5/INV-8 no tiene superficie REST propia; su
    # efecto observable es exactamente esta acreditación)


@pytest.mark.at("AT-07-03-02")
def test_once_confirmaciones_no_alcanzan_el_umbral(usuario, rpc):
    """HU-07-03 Escenario 2 (borde): 11 confirmaciones no alcanzan el umbral.

    - Dado un depósito incluido en el bloque B
    - Y que la cabeza está en B + 11 (confirmaciones = 11)
    - Cuando el servicio evalúa el depósito
    - Entonces permanece PENDIENTE y NO se acredita (RN-2, RN-3)
    - Y disponible(ETH) sigue en "0"
    """
    # Dado
    direccion = direccion_deposito(usuario, "ETH")
    tx_hash = rpc.depositar_eth(direccion, 10**18, confirmar=False)
    dep_id = id_deposito(tx_hash, 0)
    esperar_deposito(usuario, dep_id)

    # Y: cabeza en B + 11 — la cadena queda detenida ahí (minado a demanda),
    # así que "confirmations == 11" es un estado estable, no una carrera
    rpc.minar_bloques(11)

    # Cuando: el SUT ya observó la cabeza B + 11 (reporta 11 confirmaciones)
    dep = esperar_confirmaciones(usuario, dep_id, 11)

    # Entonces: sigue PENDIENTE, sin acreditar
    assert dep["status"] == "PENDIENTE", dep
    assert not dep.get("creditedAt"), dep
    assert balance_de(usuario, "ETH")["available"] == "0"


@pytest.mark.at("AT-07-03-04")
def test_acreditacion_de_un_deposito_usdc_suma_al_disponible_previo(usuario, rpc):
    """HU-07-03 Escenario 4: acreditación de un depósito USDC.

    - Dado un depósito USDC PENDIENTE por "10000000" (10 USDC) incluido en B,
      con disponible(USDC) = "2500000"
    - Y que la cabeza llega a B + 12
    - Cuando el servicio evalúa el depósito
    - Entonces disponible(USDC) pasa a "12500000" (suma exacta de enteros)
    - Y el monto acreditado es idéntico al detectado, sin fee ni redondeo (RN-4, RN-7)
    """
    # Dado: disponible previo de "2500000" construido con un primer depósito real
    direccion = direccion_deposito(usuario, "USDC")
    rpc.depositar_usdc(direccion, 2_500_000)  # confirmar=True: 12 bloques
    esperar_disponible_exacto(usuario, "USDC", 2_500_000)

    # Y: segundo depósito de 10 USDC, aún sin confirmar
    tx_hash = rpc.depositar_usdc(direccion, 10_000_000, confirmar=False)
    dep_id = id_deposito(tx_hash, log_index_unico(rpc, tx_hash))
    esperar_deposito(usuario, dep_id)
    assert balance_de(usuario, "USDC")["available"] == "2500000"  # PENDIENTE no suma

    # Cuando: la cabeza llega a B + 12
    rpc.minar_bloques(12)

    # Entonces: suma entera exacta 2500000 + 10000000 = 12500000 (6 decimales)
    esperar_estado_deposito(usuario, dep_id, "ACREDITADO")
    esperar_disponible_exacto(usuario, "USDC", 12_500_000)


@pytest.mark.at("AT-07-03-05")
def test_confirmaciones_muy_por_encima_del_umbral_acreditan_una_sola_vez(usuario, rpc):
    """HU-07-03 Escenario 5 (borde): confirmaciones muy por encima del umbral.

    - Dado un depósito PENDIENTE incluido en B
    - Y que la cabeza está en B + 50 (confirmaciones = 50)
    - Cuando el servicio evalúa el depósito
    - Entonces se acredita exactamente una vez por el monto detectado
    - Y posteriores evaluaciones no vuelven a acreditar (RN-9)
    """
    # Dado
    direccion = direccion_deposito(usuario, "USDC")
    monto = 10_000_000
    tx_hash = rpc.depositar_usdc(direccion, monto, confirmar=False)
    dep_id = id_deposito(tx_hash, log_index_unico(rpc, tx_hash))
    esperar_deposito(usuario, dep_id)

    # Y: la cabeza salta directamente a B + 50
    rpc.minar_bloques(50)

    # Cuando/Entonces: una única acreditación por el monto exacto
    esperar_estado_deposito(usuario, dep_id, "ACREDITADO")
    esperar_disponible_exacto(usuario, "USDC", monto)

    # Y: nuevas evaluaciones (el indexador sigue procesando bloques: el
    # centinela ETH lo garantiza) no vuelven a sumar
    acreditar_centinela(usuario, rpc, asset="ETH")
    assert balance_de(usuario, "USDC")["available"] == str(monto)
    items = listar_depositos(usuario, asset="USDC")
    assert [i["depositId"] for i in items].count(dep_id) == 1, items


@pytest.mark.at("AT-07-03-06")
def test_conservacion_la_suma_global_aumenta_solo_por_el_deposito(usuario, usuario_b, rpc):
    """HU-07-03 Escenario 6 (conservación, INV-1): la suma global aumenta sólo
    por el depósito.

    - Dado el estado global S0 antes de acreditar
    - Cuando se acredita un depósito ETH de monto m
    - Entonces el nuevo estado global es exactamente S0 + m (ningún otro
      balance se mueve)

    Alcance black-box: la Σ de INV-1 abarca todas las cuentas más la cuenta del
    exchange, que la API no permite enumerar; se verifica su proyección
    observable — la cuenta receptora aumenta EXACTAMENTE m (sin fee ni
    redondeo, RN-6/RN-7) y una cuenta espectadora no se mueve. La
    reconciliación global contra el ledger es parte de la evaluación
    white-box de INV-1/INV-8 en H8.
    """
    # Dado: S0 (totales previos de las cuentas observables, en wei exactos)
    total_a_0 = a_int(balance_de(usuario, "ETH")["total"])
    total_b_0 = a_int(balance_de(usuario_b, "ETH")["total"])
    usdc_a_0 = balance_de(usuario, "USDC")["total"]

    # Cuando: se acredita un depósito ETH de monto m
    monto_wei = 2_000_000_000_000_000_000
    direccion = direccion_deposito(usuario, "ETH")
    tx_hash = rpc.depositar_eth(direccion, monto_wei)  # + 12 confirmaciones
    esperar_estado_deposito(usuario, id_deposito(tx_hash, 0), "ACREDITADO")

    # Entonces: el receptor aumenta exactamente m...
    esperar_disponible_exacto(usuario, "ETH", total_a_0 + monto_wei)
    assert a_int(balance_de(usuario, "ETH")["total"]) == total_a_0 + monto_wei

    # ...y ningún otro balance observable se mueve
    assert a_int(balance_de(usuario_b, "ETH")["total"]) == total_b_0
    assert balance_de(usuario, "USDC")["total"] == usdc_a_0


@pytest.mark.at("AT-07-03-07")
def test_consulta_de_estado_por_el_usuario(usuario, rpc):
    """HU-07-03 Escenario 7: consulta de estado por el usuario.

    - Dado un Trader autenticado con un depósito en confirmaciones = 8
    - Cuando hace GET /api/v1/deposits/{depositId} (o GET /api/v1/deposits)
    - Entonces ve status = "PENDIENTE" con confirmations = 8 y required = 12
      (enteros JSON, RN-8/RN-12) y los campos del esquema de RN-12
    - Y al alcanzar 12 confirmaciones lo ve ACREDITADO (con creditedAt presente)
    """
    # Dado: depósito con exactamente 8 confirmaciones (cabeza = B + 8, estable)
    direccion = direccion_deposito(usuario, "ETH")
    monto_wei = 10**18
    tx_hash = rpc.depositar_eth(direccion, monto_wei, confirmar=False)
    dep_id = id_deposito(tx_hash, 0)
    bloque_b = bloque_de_inclusion(rpc, tx_hash)
    esperar_deposito(usuario, dep_id)
    rpc.minar_bloques(8)

    # Cuando/Entonces: detalle con el esquema completo de RN-12
    dep = esperar_confirmaciones(usuario, dep_id, 8)
    assert_esquema_deposito(dep)
    assert dep["status"] == "PENDIENTE"
    assert es_entero_json(dep["confirmations"]) and dep["confirmations"] == 8
    assert es_entero_json(dep["required"]) and dep["required"] == 12
    assert dep["depositId"] == dep_id
    assert dep["txHash"] == tx_hash.lower()
    assert dep["logIndex"] == 0
    assert dep["asset"] == "ETH"
    assert es_monto_valido(dep["amountMinUnit"]) and dep["amountMinUnit"] == str(monto_wei)
    assert dep["blockNumber"] == bloque_b

    # Y: también aparece en el listado de la cuenta (GET /deposits)
    items = listar_depositos(usuario)
    assert any(i["depositId"] == dep_id for i in items), items

    # Y: al llegar a 12 confirmaciones se ve ACREDITADO con creditedAt
    rpc.minar_bloques(4)
    dep = esperar_estado_deposito(usuario, dep_id, "ACREDITADO")
    assert isinstance(dep.get("creditedAt"), str) and dep["creditedAt"], dep


@pytest.mark.at("AT-07-03-08")
def test_deposito_de_otra_cuenta_no_se_revela(usuario, usuario_b, rpc):
    """HU-07-03 Escenario 8 (aislamiento): depósito de otra cuenta no se revela.

    - Dado un Trader autenticado (cuenta A)
    - Y un depósito perteneciente a la cuenta B
    - Cuando A hace GET /api/v1/deposits/{depositId} de ese depósito
    - Entonces recibe NOT_FOUND (404) con details = {resource: "deposit", id},
      indistinguible de un depósito inexistente (RN-11; nunca UNAUTHORIZED)
    - Y ningún dato del depósito de B se filtra fuera del envelope de error
    """
    # Dado: depósito de la cuenta B con un monto distintivo
    monto_distintivo = 731_000_000_000_000_000
    direccion_b = direccion_deposito(usuario_b, "ETH")
    tx_hash = rpc.depositar_eth(direccion_b, monto_distintivo, confirmar=False)
    dep_id = id_deposito(tx_hash, 0)
    esperar_deposito(usuario_b, dep_id)  # visible para su dueño

    # Cuando: la cuenta A consulta el depósito ajeno
    resp = usuario.api.get(f"/deposits/{dep_id}")

    # Entonces: 404 con details de recurso, igual que un inexistente
    err = assert_error(resp, "NOT_FOUND")
    assert err["details"]["resource"] == "deposit", err
    assert err["details"]["id"] == dep_id, err

    # Y: nada del depósito ajeno se filtra (ni monto ni bloque, sólo el id consultado)
    assert str(monto_distintivo) not in resp.text
    # tampoco aparece en el listado de A (aislamiento de lectura, HU-09-02 RN-5)
    assert not any(i["depositId"] == dep_id for i in listar_depositos(usuario))


@pytest.mark.at("AT-07-03-09")
def test_consulta_de_depositos_sin_credencial(api):
    """HU-07-03 Escenario 9 (error de autenticación): sin credencial.

    - Dado un cliente sin credencial válida (token ausente o inválido)
    - Cuando hace GET /api/v1/deposits o GET /api/v1/deposits/{depositId}
    - Entonces se rechaza con UNAUTHENTICATED (401), por precedencia antes que
      cualquier otra validación (README épica 07, tabla de precedencia)
    """
    dep_id = f"{_tx_hash_inexistente()}:0"

    # Cuando/Entonces: token ausente
    assert_error(api.get("/deposits"), "UNAUTHENTICATED")
    assert_error(api.get(f"/deposits/{dep_id}"), "UNAUTHENTICATED")

    # Y: token inválido
    api_invalida = api.con_token("token-invalido-ep07")
    assert_error(api_invalida.get("/deposits"), "UNAUTHENTICATED")

    # Y: precedencia — aun con id MAL FORMADO, sin credencial responde 401
    # (UNAUTHENTICATED va antes que VALIDATION_ERROR)
    assert_error(api.get("/deposits/0x1234:no-entero"), "UNAUTHENTICATED")


@pytest.mark.at("AT-07-03-10")
def test_consulta_de_deposito_inexistente(usuario):
    """HU-07-03 Escenario 10 (error): depósito inexistente.

    - Dado un Trader autenticado
    - Cuando consulta una identidad (txHash, logIndex) bien formada que no existe
    - Entonces recibe NOT_FOUND (404) con details = {resource: "deposit", id}
    """
    # Dado / Cuando: identidad bien formada, inexistente
    dep_id = f"{_tx_hash_inexistente()}:0"
    resp = usuario.api.get(f"/deposits/{dep_id}")

    # Entonces
    err = assert_error(resp, "NOT_FOUND")
    assert err["details"]["resource"] == "deposit", err
    assert err["details"]["id"] == dep_id, err


@pytest.mark.at("AT-07-03-11")
def test_consulta_con_txhash_o_logindex_mal_formados(usuario):
    """HU-07-03 Escenario 11 (error): txHash mal formado.

    - Dado un Trader autenticado
    - Cuando consulta un depósito con txHash que no matchea ^0x[0-9a-fA-F]{64}$
      o un logIndex no entero
    - Entonces se rechaza con VALIDATION_ERROR (422) con details.issues (RN-12),
      por precedencia antes que NOT_FOUND
    """
    hash_valido = _tx_hash_inexistente()
    variantes = [
        "0x1234:0",                      # txHash demasiado corto
        f"{hash_valido[:-1]}:0",         # 63 caracteres hex
        f"0x{'zz' * 32}:0",              # caracteres no hexadecimales
        f"{hash_valido[2:]}:0",          # sin prefijo 0x
        f"{hash_valido}:no-entero",      # logIndex no entero
        f"{hash_valido}:1.5",            # logIndex no entero (decimal)
        f"{hash_valido}:-1",             # logIndex negativo (debe ser ≥ 0)
    ]
    for dep_id in variantes:
        # Cuando
        resp = usuario.api.get(f"/deposits/{dep_id}")
        # Entonces: VALIDATION_ERROR con details.issues (antes que NOT_FOUND)
        err = assert_error(resp, "VALIDATION_ERROR")
        assert "issues" in (err.get("details") or {}), (dep_id, err)
