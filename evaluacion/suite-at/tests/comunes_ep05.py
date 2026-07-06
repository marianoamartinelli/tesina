"""Helpers compartidos de los tests de la épica 05 (settlement y fees).

Provee, para los archivos ``test_ep05_*.py``:

- **Fondeo black-box**: el único camino para dar balance interno a un usuario es
  el flujo real de depósito on-chain acreditado (épicas 06+07; HELPERS.md,
  §"El patrón completo").
- **Lectura de balances** con verificación de INV-3 (`total == available + locked`)
  y de la serialización de montos en cada snapshot.
- **Alta de órdenes** LIMIT/MARKET contra el contrato de la épica 09 (HU-09-01
  RN-4/RN-5) para construir el "Dado" de cada fill.
- **Historial de trades** (GET /trades, HU-09-01 RN-20 / HU-05-04) con espera de
  convergencia.
- **Limpieza de órdenes residuales**: el orderbook del SUT es global; una orden
  resting que un test deje (remanente parcial, maker sin cruzar por una falla)
  podría cruzarse con las órdenes de un test posterior. La fixture autouse
  ``limpiar_ordenes_residuales`` cancela las órdenes abiertas de los usuarios
  del test al terminar, preservando la independencia entre tests (HELPERS.md,
  principio 5) sin tocar ``conftest.py``.

Toda la aritmética es sobre ``int`` de Python (precisión arbitraria) a partir de
los strings de la API; **prohibido float** (convenciones-monetarias §1.1).
"""

import secrets

import pytest

from helpers.espera import esperar_hasta
from helpers.montos import SIMBOLO, a_int, a_str

# --- Constantes de escenario (unidades mínimas; 00-fundaciones) --------------------

UN_ETH_WEI = 10**18                # 1 ETH
UN_LOT_WEI = 10**14                # lot size (activos-y-par §4.2)
PRECIO_2000 = 2_000_000_000        # 2000.00 USDC/ETH en price_min (tick ✓)
PRECIO_2001 = 2_001_000_000        # 2001.00
PRECIO_2010 = 2_010_000_000        # 2010.00


# --- Fondeo black-box (depósito on-chain acreditado, épicas 06+07) ------------------

def direccion_deposito(usuario, asset: str) -> str:
    """Dirección de depósito de la cuenta para `asset` (HU-09-01 RN-10)."""
    resp = usuario.api.get("/deposit-address", params={"asset": asset})
    assert resp.status_code == 200, (
        f"GET /deposit-address?asset={asset} falló: {resp.status_code} {resp.text[:300]}"
    )
    return resp.json()["address"]


def fondear_eth(usuario, rpc, valor_wei: int) -> None:
    """Deposita `valor_wei` on-chain (12 confirmaciones) y espera la acreditación."""
    rpc.depositar_eth(direccion_deposito(usuario, "ETH"), valor_wei)
    esperar_hasta(
        lambda: a_int(balance_de(usuario, "ETH")["available"]) >= valor_wei,
        mensaje=f"el depósito de {valor_wei} wei no se acreditó al balance interno",
    )


def fondear_usdc(usuario, rpc, monto_usdcmin: int) -> None:
    """Deposita `monto_usdcmin` USDC-min on-chain y espera la acreditación."""
    rpc.depositar_usdc(direccion_deposito(usuario, "USDC"), monto_usdcmin)
    esperar_hasta(
        lambda: a_int(balance_de(usuario, "USDC")["available"]) >= monto_usdcmin,
        mensaje=f"el depósito de {monto_usdcmin} USDC-min no se acreditó al balance interno",
    )


# --- Balances (GET /balances, HU-09-01 RN-9) ---------------------------------------

def balances_de(usuario) -> dict[str, dict]:
    """Balances por activo. Verifica INV-3 y la serialización en cada snapshot."""
    resp = usuario.api.get("/balances")
    assert resp.status_code == 200, f"GET /balances falló: {resp.status_code} {resp.text[:300]}"
    por_activo = {b["asset"]: b for b in resp.json()}
    for activo, b in por_activo.items():
        # INV-3: total == available + locked, con montos string bien serializados
        # (a_int valida el patrón ^(0|[1-9][0-9]*)$ ⇒ además nunca negativos, INV-2).
        assert a_int(b["total"]) == a_int(b["available"]) + a_int(b["locked"]), (
            f"INV-3 violado para {activo}: {b!r}"
        )
    return por_activo


def balance_de(usuario, asset: str) -> dict:
    """Balance de un activo; exige que el activo esté presente (HU-09-01 RN-9)."""
    por_activo = balances_de(usuario)
    assert asset in por_activo, (
        f"GET /balances sin el activo {asset}: {sorted(por_activo)} (HU-09-01 RN-9)"
    )
    return por_activo[asset]


def assert_balance(usuario, asset: str, *, available: int, locked: int) -> None:
    """Asserta el balance exacto (enteros, sin tolerancia; convenciones §4)."""
    b = balance_de(usuario, asset)
    assert a_int(b["available"]) == available, (
        f"{asset}.available: esperado {available}, hay {b['available']}"
    )
    assert a_int(b["locked"]) == locked, (
        f"{asset}.locked: esperado {locked}, hay {b['locked']}"
    )


# --- Órdenes (POST /orders, HU-09-01 RN-4/RN-5) -------------------------------------

def client_order_id_unico(prefijo: str = "ep05") -> str:
    """clientOrderId único (1..64 ASCII imprimibles, HU-09-01 RN-19)."""
    return f"{prefijo}-{secrets.token_hex(6)}"


def crear_limit(usuario, side: str, price_min: int, q_wei: int) -> dict:
    """Crea una orden LIMIT (201) y devuelve el objeto orden."""
    cuerpo = {
        "clientOrderId": client_order_id_unico(),
        "symbol": SIMBOLO,
        "side": side,
        "type": "LIMIT",
        "priceMin": a_str(price_min),
        "quantityWei": a_str(q_wei),
    }
    resp = usuario.api.post("/orders", json=cuerpo)
    assert resp.status_code == 201, (
        f"alta LIMIT {side} {q_wei}@{price_min} falló: {resp.status_code} {resp.text[:300]}"
    )
    return resp.json()


def crear_maker(usuario, side: str, price_min: int, q_wei: int) -> dict:
    """Crea una LIMIT que debe quedar resting (OPEN): el 'Dado' del lado maker.

    Si no queda OPEN, el orderbook tenía liquidez cruzable ajena al test y el
    escenario no puede construirse de forma determinista: se falla explícito.
    """
    orden = crear_limit(usuario, side, price_min, q_wei)
    assert orden["status"] == "OPEN", (
        f"la orden maker no quedó resting (status {orden['status']!r}): "
        "hay liquidez cruzable ajena al test en el libro"
    )
    return orden


def crear_market(usuario, side: str, q_wei: int) -> dict:
    """Crea una orden MARKET por cantidad (201, sin priceMin; HU-09-01 RN-4)."""
    cuerpo = {
        "clientOrderId": client_order_id_unico(),
        "symbol": SIMBOLO,
        "side": side,
        "type": "MARKET",
        "quantityWei": a_str(q_wei),
    }
    resp = usuario.api.post("/orders", json=cuerpo)
    assert resp.status_code == 201, (
        f"alta MARKET {side} {q_wei} falló: {resp.status_code} {resp.text[:300]}"
    )
    return resp.json()


def orden_de(usuario, order_id: str) -> dict:
    """GET /orders/{orderId} (200) de una orden propia."""
    resp = usuario.api.get(f"/orders/{order_id}")
    assert resp.status_code == 200, (
        f"GET /orders/{order_id} falló: {resp.status_code} {resp.text[:300]}"
    )
    return resp.json()


def cancelar_ordenes_abiertas(*usuarios) -> None:
    """Cancela (best-effort) toda orden abierta/parcial de los usuarios dados."""
    for u in usuarios:
        try:
            for estado in ("OPEN", "PARTIALLY_FILLED"):
                resp = u.api.get("/orders", params={"status": estado, "limit": 200})
                if resp.status_code != 200:
                    continue
                for orden in resp.json().get("items", []):
                    u.api.delete(f"/orders/{orden['orderId']}")
        except Exception:
            pass  # limpieza best-effort: el teardown nunca falla por sí mismo


@pytest.fixture(autouse=True)
def limpiar_ordenes_residuales(usuario, usuario_b):
    """Fixture autouse (importarla en cada test_ep05_*.py): limpia el libro al salir."""
    yield
    cancelar_ordenes_abiertas(usuario, usuario_b)


# --- Historial de trades (GET /trades, HU-09-01 RN-20 / HU-05-04) -------------------

def trades_de(usuario, **params) -> list[dict]:
    """Items del historial de trades propios (200)."""
    resp = usuario.api.get("/trades", params=params or None)
    assert resp.status_code == 200, (
        f"GET /trades falló: {resp.status_code} {resp.text[:300]}"
    )
    return resp.json()["items"]


def esperar_trades(usuario, cantidad: int, **params) -> list[dict]:
    """Espera hasta ver >= `cantidad` trades en el historial (settlement asíncrono)."""

    def _completos():
        items = trades_de(usuario, **params)
        assert len(items) >= cantidad, f"esperaba >= {cantidad} trades, hay {len(items)}"
        return items

    return esperar_hasta(
        _completos, mensaje=f"no se registraron {cantidad} trade(s) en el historial"
    )


def entrada_unica(items: list[dict], **criterios) -> dict:
    """El único item cuyos campos coinciden exactamente con `criterios`."""
    coincidentes = [it for it in items if all(it.get(k) == v for k, v in criterios.items())]
    assert len(coincidentes) == 1, (
        f"esperaba exactamente 1 item con {criterios}, hay {len(coincidentes)}: {items!r}"
    )
    return coincidentes[0]


def construir_fill_de_un_lot(usuario, usuario_b, rpc, price_min: int) -> tuple[dict, dict, dict]:
    """Construye black-box un fill de **exactamente 1 lot** con ``takerSide = BUY``.

    Una orden de 1 lot no pasa el mínimo notional al alta (BELOW_MIN_NOTIONAL,
    activos-y-par §4.4) a los precios de estos escenarios, pero un **fill parcial
    no exige mínimo notional** (HU-05-01 RN-11): el fill de 1 lot se obtiene como
    remanente de una orden mayor.

    - S1: ``usuario_b`` SELL 51 lots @ price_min (resting).
    - B1: ``usuario``  BUY 50 lots @ price_min  → fill de 50 lots (B1 FILLED).
    - B2: ``usuario``  BUY 50 lots @ price_min  → fill de **1 lot** (remanente de
      S1); B2 queda PARTIALLY_FILLED resting (la limpia ``limpiar_ordenes_residuales``).

    Devuelve ``(s1, b1, b2)`` (objetos orden del 201). El fill de 1 lot es el
    segundo trade de ambas cuentas; en él el vendedor es maker y el comprador taker.
    """
    q_50 = 50 * UN_LOT_WEI
    q_51 = 51 * UN_LOT_WEI
    # floor(q × price / 10^18) es exacto bajo tick × lot (HU-05-01 RN-3)
    bloqueo_por_orden = (q_50 * price_min) // UN_ETH_WEI

    fondear_eth(usuario_b, rpc, q_51)
    fondear_usdc(usuario, rpc, 2 * bloqueo_por_orden)

    s1 = crear_maker(usuario_b, "SELL", price_min, q_51)
    b1 = crear_limit(usuario, "BUY", price_min, q_50)
    esperar_trades(usuario, 1)
    b2 = crear_limit(usuario, "BUY", price_min, q_50)
    esperar_trades(usuario, 2)
    return s1, b1, b2


def assert_pata_propia(
    entrada: dict,
    *,
    side: str,
    role: str,
    price_min: int,
    q_wei: int,
    quote: int,
    fee_asset: str,
    fee: int,
    neto: int,
    pagado: int,
    order_id: str | None = None,
) -> None:
    """Asserta la proyección de la pata propia de un trade (HU-05-04 RN-3/RN-4).

    Todos los montos se validan como string entero (a_int) y se comparan con
    igualdad exacta contra los enteros esperados (sin tolerancia).
    """
    assert entrada["symbol"] == SIMBOLO, entrada
    assert entrada["side"] == side, entrada
    assert entrada["role"] == role, entrada
    assert a_int(entrada["priceMin"]) == price_min, entrada
    assert a_int(entrada["quantityWei"]) == q_wei, entrada
    assert a_int(entrada["quoteAmountMin"]) == quote, entrada
    assert entrada["feeAsset"] == fee_asset, entrada
    assert a_int(entrada["feeAmount"]) == fee, entrada
    assert a_int(entrada["netReceived"]) == neto, entrada
    assert a_int(entrada["paid"]) == pagado, entrada
    # sequence es conteo (entero JSON, no string; convenciones §5) y el tradeId
    # deriva de él: "T-" + sequence (HU-05-03 RN-2/RN-3).
    assert isinstance(entrada["sequence"], int) and not isinstance(entrada["sequence"], bool)
    assert entrada["tradeId"] == f"T-{entrada['sequence']}", entrada
    assert isinstance(entrada["timestamp"], str), entrada
    if order_id is not None:
        assert entrada["orderId"] == order_id, entrada
