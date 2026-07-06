"""Helpers compartidos de los tests de la épica 02 (balances y ledger).

Convenciones de precio de este módulo (el orderbook del SUT es compartido entre
tests; par único ETH-USDC):

- ``PRECIO_BANDA_BAJA``: bids resting que NO deben ejecutar (ningún test de la
  épica deja asks por debajo de la banda de matching).
- ``PRECIO_BANDA_ALTA``: asks resting que NO deben ejecutar.
- ``PRECIO_MATCHING``:   banda central para fills controlados (los valores de la
  spec: 2000.00 USDC/ETH). Todo test que deje una orden resting en esta banda la
  cancela al terminar (``cancelar_si_posible`` en un ``finally``).

El único camino black-box para fondear una cuenta interna es el depósito
on-chain acreditado (épicas 06+07): ``fondear_eth`` / ``fondear_usdc`` depositan
vía el nodo anvil del entorno y esperan la acreditación (HELPERS.md).
"""

import re
import secrets
from datetime import datetime, timedelta

from helpers.espera import esperar_hasta
from helpers.montos import a_int, a_str, assert_monto

SIMBOLO = "ETH-USDC"

# Bandas de precio (price_min, USDC-min por ETH; múltiplos del tick 10_000).
PRECIO_BANDA_BAJA = 1_000_000_000   # 1000.00 USDC/ETH
PRECIO_BANDA_ALTA = 9_000_000_000   # 9000.00 USDC/ETH
PRECIO_MATCHING = 2_000_000_000     # 2000.00 USDC/ETH (valor canónico de la spec)

# Dirección externa con checksum EIP-55 válido (misma que usa HELPERS.md).
DESTINO_RETIRO = "0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc"

# Intervalo de polling conservador: el rate limit es 60 req/min por cuenta y
# endpoint (HU-09-02 RN-12); a 1.5 s el polling queda en ~40 req/min.
INTERVALO_POLL_SEGUNDOS = 1.5

# Parámetros on-chain fijados por la spec y por el entorno de evaluación
# (entorno/README.md): GAS_PRICE_SOURCE = configured_fixed. El snapshot de gas
# de un retiro usa GAS_PRICE_WEI de configuración (HU-08-02 RN-7) y
# fee_red_wei = gas_limit × gas_price_wei (HU-08-02 RN-1); tras ADR-006 D2 el
# modelo de la épica 08 (el usuario paga el fee de red) rige también en la 02.
GAS_PRICE_WEI = 20_000_000_000          # 20 gwei
GAS_LIMIT_ETH = 21_000                  # transferencia ETH: exactamente 21000 gas
GAS_LIMIT_ERC20 = 100_000               # transferencia ERC-20 (retiro USDC)
FEE_RED_ETH_WEI = GAS_LIMIT_ETH * GAS_PRICE_WEI       # 420000000000000
FEE_RED_ERC20_WEI = GAS_LIMIT_ERC20 * GAS_PRICE_WEI   # 2000000000000000


def nuevo_client_order_id(prefijo: str = "ep02") -> str:
    """clientOrderId único (1..64 ASCII imprimibles, HU-09-01 RN-19)."""
    return f"{prefijo}-{secrets.token_hex(8)}"


# --------------------------------------------------------------------------------
# Balances (HU-02-01)
# --------------------------------------------------------------------------------


def balances_por_activo(usuario) -> dict:
    """GET /balances validando en cada lectura las propiedades transversales:

    - serialización de montos como string ``^(0|[1-9][0-9]*)$`` (HU-02-01 RN-7);
    - no-negatividad (INV-2; implícita en el patrón, que excluye negativos);
    - partición ``total == available + locked`` (INV-3, HU-02-01 RN-5);
    - presencia de exactamente los dos activos del par (HU-02-01 RN-3).

    Devuelve ``{"ETH": item, "USDC": item}``.
    """
    resp = usuario.api.get("/balances")
    assert resp.status_code == 200, (
        f"GET /balances falló: {resp.status_code} {resp.text[:300]}"
    )
    cuerpo = resp.json()
    assert isinstance(cuerpo, list), f"se esperaba un arreglo de balances: {cuerpo!r}"
    por_activo: dict = {}
    for item in cuerpo:
        activo = item["asset"]
        disponible = assert_monto(item["available"], f"{activo}.available")
        bloqueado = assert_monto(item["locked"], f"{activo}.locked")
        total = assert_monto(item["total"], f"{activo}.total")
        assert total == disponible + bloqueado, (
            f"INV-3 violado en {activo}: total {total} != "
            f"available {disponible} + locked {bloqueado}"
        )
        por_activo[activo] = item
    assert set(por_activo) == {"ETH", "USDC"}, (
        f"la respuesta debe enumerar exactamente ETH y USDC (HU-02-01 RN-3): "
        f"{sorted(por_activo)}"
    )
    return por_activo


def balance(usuario, asset: str) -> dict:
    """El item de balance de un activo (ya validado por ``balances_por_activo``)."""
    return balances_por_activo(usuario)[asset]


def total_de(usuario, asset: str) -> int:
    return a_int(balance(usuario, asset)["total"])


# --------------------------------------------------------------------------------
# Fondeo black-box vía depósito on-chain (épicas 06+07)
# --------------------------------------------------------------------------------


def direccion_deposito(usuario, asset: str) -> str:
    resp = usuario.api.get("/deposit-address", params={"asset": asset})
    assert resp.status_code == 200, (
        f"GET /deposit-address falló: {resp.status_code} {resp.text[:300]}"
    )
    return resp.json()["address"]


def fondear_usdc(usuario, rpc, monto_usdcmin: int) -> None:
    """Deposita USDC (mint + transfer + 12 confirmaciones) hasta verlo acreditado.

    Pensado para usuarios frescos (parten de disponible 0): espera
    ``available >= monto`` y el test asserta después el valor exacto.
    """
    direccion = direccion_deposito(usuario, "USDC")
    rpc.depositar_usdc(direccion, monto_usdcmin)
    esperar_hasta(
        lambda: a_int(balance(usuario, "USDC")["available"]) >= monto_usdcmin,
        intervalo=INTERVALO_POLL_SEGUNDOS,
        mensaje=f"el depósito de {monto_usdcmin} USDC-min no se acreditó",
    )


def fondear_eth(usuario, rpc, monto_wei: int) -> None:
    """Deposita ETH nativo (transfer + 12 confirmaciones) hasta verlo acreditado."""
    direccion = direccion_deposito(usuario, "ETH")
    rpc.depositar_eth(direccion, monto_wei)
    esperar_hasta(
        lambda: a_int(balance(usuario, "ETH")["available"]) >= monto_wei,
        intervalo=INTERVALO_POLL_SEGUNDOS,
        mensaje=f"el depósito de {monto_wei} wei no se acreditó",
    )


# --------------------------------------------------------------------------------
# Órdenes (contrato HU-09-01 RN-4/RN-5/RN-7)
# --------------------------------------------------------------------------------


def crear_orden(usuario, side: str, tipo: str, quantity_wei: int,
                price_min: int | None = None, client_order_id: str | None = None):
    """POST /orders. Devuelve la respuesta cruda (para tests de error)."""
    payload = {
        "clientOrderId": client_order_id or nuevo_client_order_id(),
        "symbol": SIMBOLO,
        "side": side,
        "type": tipo,
        "quantityWei": a_str(quantity_wei),
    }
    if price_min is not None:
        payload["priceMin"] = a_str(price_min)
    return usuario.api.post("/orders", json=payload)


def orden_creada(usuario, side: str, tipo: str, quantity_wei: int,
                 price_min: int | None = None, client_order_id: str | None = None) -> dict:
    """Alta de orden asumiendo camino feliz (201). Devuelve el objeto orden."""
    resp = crear_orden(usuario, side, tipo, quantity_wei, price_min, client_order_id)
    assert resp.status_code == 201, (
        f"alta de orden falló: {resp.status_code} {resp.text[:300]}"
    )
    return resp.json()


def orden_resting(usuario, side: str, quantity_wei: int, price_min: int) -> dict:
    """Alta de orden LIMIT que DEBE quedar pasiva en el libro (Dado de los tests)."""
    orden = orden_creada(usuario, side, "LIMIT", quantity_wei, price_min)
    assert orden["status"] == "OPEN" and orden["filledWei"] == "0", (
        f"la orden debía quedar resting sin fills; llegó status={orden['status']!r}, "
        f"filledWei={orden['filledWei']!r} (¿libro contaminado por otro test?)"
    )
    return orden


def detalle_orden(usuario, order_id: str) -> dict:
    resp = usuario.api.get(f"/orders/{order_id}")
    assert resp.status_code == 200, (
        f"GET /orders/{order_id} falló: {resp.status_code} {resp.text[:300]}"
    )
    return resp.json()


def cancelar_orden(usuario, order_id: str) -> dict:
    """DELETE /orders/{id} asumiendo camino feliz (200, estado CANCELLED)."""
    resp = usuario.api.delete(f"/orders/{order_id}")
    assert resp.status_code == 200, (
        f"cancelación falló: {resp.status_code} {resp.text[:300]}"
    )
    cuerpo = resp.json()
    assert cuerpo["status"] == "CANCELLED", cuerpo
    return cuerpo


def cancelar_si_posible(usuario, order_id: str) -> None:
    """Cleanup best-effort: cancela sin assertar (para ``finally`` de los tests
    que dejan órdenes resting en la banda de matching)."""
    try:
        usuario.api.delete(f"/orders/{order_id}")
    except Exception:
        pass


def pata_propia_del_fill(usuario, order_id: str) -> dict:
    """Primera pata propia del trade de una orden (GET /trades?orderId=...,
    HU-09-01 RN-20): expone feeAsset/feeAmount, la vía black-box para observar
    la fee que el settlement acredita a EX."""
    def _buscar():
        resp = usuario.api.get("/trades", params={"orderId": order_id})
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        return items[0] if items else None

    return esperar_hasta(
        _buscar,
        intervalo=INTERVALO_POLL_SEGUNDOS,
        mensaje=f"sin trade propio para la orden {order_id}",
    )


# --------------------------------------------------------------------------------
# Retiros (contrato HU-09-01 RN-11/RN-18)
# --------------------------------------------------------------------------------


def crear_retiro(usuario, asset: str, amount_min_unit: int, address: str = DESTINO_RETIRO):
    """POST /withdrawals. Devuelve la respuesta cruda."""
    return usuario.api.post(
        "/withdrawals",
        json={"asset": asset, "amountMinUnit": a_str(amount_min_unit), "address": address},
    )


def detalle_retiro(usuario, withdrawal_id: str) -> dict:
    resp = usuario.api.get(f"/withdrawals/{withdrawal_id}")
    assert resp.status_code == 200, (
        f"GET /withdrawals/{withdrawal_id} falló: {resp.status_code} {resp.text[:300]}"
    )
    return resp.json()


def cancelar_retiro(usuario, withdrawal_id: str):
    """POST /withdrawals/{id}/cancel (HU-09-01 RN-21, semántica HU-08-04 RN-13).

    Devuelve la respuesta cruda: la cancelación solo procede sobre un retiro
    PENDING sin broadcast (si no, CONFLICT 409).
    """
    return usuario.api.post(f"/withdrawals/{withdrawal_id}/cancel")


# --------------------------------------------------------------------------------
# Historial de movimientos (HU-02-05 vía GET /movements, HU-09-01 RN-22)
# --------------------------------------------------------------------------------

RUTA_MOVIMIENTOS = "/movements"

# Enum cerrado de tipos de asiento (HU-02-03 RN-2).
TIPOS_DE_ASIENTO = {
    "DEPOSIT",
    "ORDER_LOCK",
    "ORDER_RELEASE",
    "TRADE_FILL",
    "WITHDRAWAL_LOCK",
    "WITHDRAWAL_SETTLE",
    "WITHDRAWAL_RELEASE",
    "REVERSAL",
}

# amount de un posting: string entero ESTRICTAMENTE positivo (HU-02-05 RN-2;
# distinto del patrón de balances, que admite "0").
PATRON_AMOUNT_POSTING = re.compile(r"^[1-9][0-9]*$")

# fracción de milisegundos + UTC explícito (HU-02-03 RN-2: ISO-8601 con ms)
_RE_TIMESTAMP_MS_UTC = re.compile(r"\.\d{3,}(Z|\+00:00)$")


def parsear_timestamp_utc_ms(valor, campo: str = "timestamp") -> datetime:
    """Valida ISO-8601 UTC con milisegundos (HU-02-03 RN-2) y devuelve datetime."""
    assert isinstance(valor, str) and valor, f"{campo} ausente o no string: {valor!r}"
    assert _RE_TIMESTAMP_MS_UTC.search(valor), (
        f"{campo} sin milisegundos o sin UTC explícito (ISO-8601): {valor!r}"
    )
    try:
        dt = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        raise AssertionError(f"{campo} no es ISO-8601: {valor!r}") from None
    assert dt.utcoffset() == timedelta(0), f"{campo} no está en UTC: {valor!r}"
    return dt


def tupla_posting(posting: dict) -> tuple:
    """Proyección (asset, bucket, direction, amount) para comparar postings."""
    return (posting["asset"], posting["bucket"], posting["direction"], posting["amount"])


def validar_item_movimiento(item: dict) -> None:
    """Valida la forma de un ítem del historial (HU-02-05 RN-2 / HU-09-01 RN-22):

    - `entryId` serializado como string; `type` del enum cerrado de HU-02-03;
    - `timestamp` ISO-8601 UTC con milisegundos;
    - `reference` como objeto según el tipo (`{txHash, logIndex}` para DEPOSIT,
      con `logIndex` como entero JSON — conteo, no monto; `orderId` para
      ORDER_LOCK; `orderId` o `tradeId` para ORDER_RELEASE — cancelación o
      surplus, HU-02-03 RN-2; `tradeId` para TRADE_FILL; `withdrawalId` para
      WITHDRAWAL_*);
    - `postings` propios `{asset, bucket, direction, amount, kind}` con `amount`
      string entero estrictamente positivo `^[1-9][0-9]*$`.
    """
    assert isinstance(item, dict), f"ítem del historial no es objeto: {item!r}"
    assert isinstance(item.get("entryId"), str) and item["entryId"], (
        f"entryId debe serializarse como string no vacío (HU-09-01 RN-22): {item!r}"
    )
    tipo = item.get("type")
    assert tipo in TIPOS_DE_ASIENTO, f"type fuera del enum de HU-02-03: {tipo!r}"
    parsear_timestamp_utc_ms(item.get("timestamp"))

    referencia = item.get("reference")
    assert isinstance(referencia, dict) and referencia, (
        f"reference ausente o vacía: {item!r}"
    )
    if tipo == "DEPOSIT":
        assert isinstance(referencia.get("txHash"), str) and referencia["txHash"].startswith("0x"), (
            f"DEPOSIT sin reference.txHash: {referencia!r}"
        )
        log_index = referencia.get("logIndex")
        assert isinstance(log_index, int) and not isinstance(log_index, bool) and log_index >= 0, (
            f"logIndex debe ser entero JSON >= 0 (conteo, no monto): {referencia!r}"
        )
    elif tipo == "ORDER_LOCK":
        assert isinstance(referencia.get("orderId"), str) and referencia["orderId"], (
            f"ORDER_LOCK sin reference.orderId: {referencia!r}"
        )
    elif tipo == "ORDER_RELEASE":
        assert any(
            isinstance(referencia.get(clave), str) and referencia[clave]
            for clave in ("orderId", "tradeId")
        ), f"ORDER_RELEASE sin reference.orderId/tradeId: {referencia!r}"
    elif tipo == "TRADE_FILL":
        assert isinstance(referencia.get("tradeId"), str) and referencia["tradeId"], (
            f"TRADE_FILL sin reference.tradeId: {referencia!r}"
        )
    elif tipo in ("WITHDRAWAL_LOCK", "WITHDRAWAL_RELEASE"):
        assert isinstance(referencia.get("withdrawalId"), str) and referencia["withdrawalId"], (
            f"{tipo} sin reference.withdrawalId: {referencia!r}"
        )
    elif tipo == "WITHDRAWAL_SETTLE":
        # referencia el retiro y, por ser de origen on-chain, puede incluir
        # además los datos on-chain (encabezado de HU-02-05)
        assert any(referencia.get(clave) for clave in ("withdrawalId", "txHash")), (
            f"WITHDRAWAL_SETTLE sin reference.withdrawalId/txHash: {referencia!r}"
        )
    elif tipo == "REVERSAL":
        assert "reversedEntryId" in referencia, (
            f"REVERSAL sin reference.reversedEntryId: {referencia!r}"
        )

    postings = item.get("postings")
    assert isinstance(postings, list) and postings, f"postings ausentes o vacíos: {item!r}"
    for posting in postings:
        assert posting.get("asset") in ("ETH", "USDC"), posting
        assert posting.get("bucket") in ("AVAILABLE", "LOCKED"), posting
        assert posting.get("direction") in ("DEBIT", "CREDIT"), posting
        assert posting.get("kind") in ("PRINCIPAL", "FEE"), posting
        amount = posting.get("amount")
        assert isinstance(amount, str) and PATRON_AMOUNT_POSTING.fullmatch(amount), (
            f"amount de posting debe ser string ^[1-9][0-9]*$ (> 0): {posting!r}"
        )


def consultar_movimientos(usuario, params: dict | None = None):
    """GET /movements crudo (para los escenarios de error/autenticación)."""
    return usuario.api.get(RUTA_MOVIMIENTOS, params=params)


def movimientos_ok(usuario, params: dict | None = None) -> dict:
    """GET /movements asumiendo éxito; valida el contrato de HU-09-01 RN-22.

    - 200 con ``{ items: [...], nextCursor: string|null }``;
    - cada ítem con la forma de HU-02-05 RN-2 (``validar_item_movimiento``).
    Devuelve el cuerpo completo.
    """
    resp = consultar_movimientos(usuario, params)
    assert resp.status_code == 200, (
        f"GET /movements falló: {resp.status_code} {resp.text[:300]}"
    )
    cuerpo = resp.json()
    assert isinstance(cuerpo, dict), f"se esperaba un objeto JSON: {cuerpo!r}"
    assert "items" in cuerpo and "nextCursor" in cuerpo, (
        f"la respuesta debe traer items y nextCursor (HU-09-01 RN-22): {cuerpo!r}"
    )
    assert isinstance(cuerpo["items"], list), cuerpo
    siguiente = cuerpo["nextCursor"]
    assert siguiente is None or (isinstance(siguiente, str) and siguiente), (
        f"nextCursor debe ser string opaco no vacío o null: {siguiente!r}"
    )
    for item in cuerpo["items"]:
        validar_item_movimiento(item)
    return cuerpo


def assert_orden_descendente(items: list) -> None:
    """HU-02-05 RN-6: timestamp descendente y, ante empate, entryId descendente.

    El desempate por entryId solo es comparable black-box cuando los entryId son
    numéricos (la spec admite cualquier forma monotónica serializada como
    string); en ese caso, como el entryId es estrictamente creciente en el
    tiempo de aplicación (HU-02-03 RN-2), el listado descendente completo debe
    ser estrictamente descendente por entryId.
    """
    marcas = [parsear_timestamp_utc_ms(item["timestamp"]) for item in items]
    for anterior, siguiente in zip(marcas, marcas[1:]):
        assert anterior >= siguiente, (
            f"historial fuera de orden (timestamp asc detectado): "
            f"{anterior.isoformat()} < {siguiente.isoformat()} (RN-6)"
        )
    ids = [item["entryId"] for item in items]
    if ids and all(re.fullmatch(r"[0-9]+", eid) for eid in ids):
        numeros = [int(eid) for eid in ids]
        assert all(a > b for a, b in zip(numeros, numeros[1:])), (
            f"entryId no estrictamente descendente en el listado: {ids}"
        )
