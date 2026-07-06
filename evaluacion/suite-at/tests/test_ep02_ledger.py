"""Épica 02 — HU-02-03 Libro contable de movimientos: tests black-box.

GET /movements (HU-09-01 RN-22, espejo de HU-02-05) expone la proyección de los
postings PROPIOS de cada cuenta — verificada en test_ep02_movimientos.py —,
pero los asientos completos de HU-02-03 (postings de la contraparte, de EX y de
EXTERNAL, unicidad/estructura interna del asiento) siguen sin superficie
black-box: esos escenarios se declaran en no-automatizables.yaml. Acá se
automatiza el que sí es íntegramente observable por balances y trades: el
consumo parcial del locked del maker (AT-02-03-10).
"""

import pytest

from comunes_ep02 import (
    PRECIO_MATCHING,
    balances_por_activo,
    cancelar_si_posible,
    detalle_orden,
    fondear_eth,
    fondear_usdc,
    orden_creada,
    orden_resting,
    pata_propia_del_fill,
)
from helpers.montos import WEI_POR_ETH, a_str, fee_maker, fee_taker


@pytest.mark.at("AT-02-03-10")
def test_fill_parcial_consume_solo_una_fraccion_del_locked_del_maker(
    usuario, usuario_b, rpc
):
    """HU-02-03 Escenario 10 (fill parcial): TRADE_FILL consume solo una fracción
    del locked del maker.

    - Dado un vendedor maker B con SELL limit de 2 ETH abierta
      (locked(B, ETH) = 2000000000000000000) y un comprador taker A cuya BUY
      ejecuta solo 1000000000000000000 wei (1 ETH) a price_min 2000000000
    - Y quote_min = 2000000000; fee_base = 2000000000000000; fee_quote = 2000000
    - Cuando se liquida el fill parcial
    - Entonces se consume SOLO 1e18 wei del locked del vendedor; se acredita
      available(A, ETH) 998000000000000000; se consume locked(A, USDC)
      2000000000; se acredita available(B, USDC) 1998000000; y las fees van a EX
    - Y el locked residual del vendedor es 1000000000000000000 (remanente abierto)
    - Y NO se genera ningún ORDER_RELEASE para el remanente del vendedor (una
      SELL bloquea base, independiente del precio; solo se liberaría al cancelar)
    - Y el locked residual cumple INV-3/INV-7

    Los postings se observan por sus efectos exactos sobre los buckets y por la
    pata propia de GET /trades (fees hacia EX); la estructura del asiento en sí
    (un único TRADE_FILL, kind FEE) se evalúa por otra vía (ver
    no_automatizables_ep02.yaml, AT-02-03-04).
    """
    # Dado: vendedor maker B con 2 ETH bloqueados por su SELL resting
    fondear_eth(usuario_b, rpc, 2 * WEI_POR_ETH)
    maker = orden_resting(usuario_b, "SELL", 2 * WEI_POR_ETH, PRECIO_MATCHING)
    try:
        # …y comprador taker A con el quote justo para 1 ETH
        fondear_usdc(usuario, rpc, 2_000_000_000)

        # Cuando: la BUY de A ejecuta 1 de los 2 ETH del maker
        taker = orden_creada(usuario, "BUY", "LIMIT", WEI_POR_ETH, PRECIO_MATCHING)
        assert taker["status"] == "FILLED", taker
        assert taker["filledWei"] == "1000000000000000000"

        # Entonces: el maker queda parcialmente ejecutado con el remanente resting
        parcial = detalle_orden(usuario_b, maker["orderId"])
        assert parcial["status"] == "PARTIALLY_FILLED", parcial
        assert parcial["filledWei"] == "1000000000000000000"

        # Y: locked residual del vendedor = 1 ETH; NADA volvió a available
        # (sin ORDER_RELEASE para el remanente: available ETH sigue en 0)
        vendedor = balances_por_activo(usuario_b)
        assert vendedor["ETH"]["locked"] == "1000000000000000000"
        assert vendedor["ETH"]["available"] == "0"
        assert vendedor["ETH"]["total"] == "1000000000000000000"
        # crédito del quote neto de fee maker
        assert vendedor["USDC"]["available"] == "1998000000"

        # Y: el comprador consumió su bloqueado y recibió la base neta de fee taker
        comprador = balances_por_activo(usuario)
        assert comprador["USDC"]["available"] == "0"
        assert comprador["USDC"]["locked"] == "0"
        assert comprador["ETH"]["available"] == "998000000000000000"

        # Y: fees del fill hacia EX (kind FEE), observadas por la pata propia
        pata_a = pata_propia_del_fill(usuario, taker["orderId"])
        assert pata_a["feeAsset"] == "ETH"
        assert pata_a["feeAmount"] == a_str(fee_taker(WEI_POR_ETH))
        pata_b = pata_propia_del_fill(usuario_b, maker["orderId"])
        assert pata_b["feeAsset"] == "USDC"
        assert pata_b["feeAmount"] == a_str(fee_maker(2_000_000_000))
    finally:
        cancelar_si_posible(usuario_b, maker["orderId"])
