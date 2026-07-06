"""Montos en unidad mínima: representación, validación y aritmética de referencia.

La spec obliga a que todo monto/precio/fee/balance viaje por la API como **string
de entero decimal** en unidad mínima (patrón ``^(0|[1-9][0-9]*)$``) y prohíbe los
floats binarios (spec/00-fundaciones/convenciones-monetarias.md). Estos helpers:

- validan la serialización (``es_monto_valido`` / ``assert_monto``),
- convierten string ⇄ ``int`` de Python (precisión arbitraria, apto para
  productos del orden de 10^30),
- implementan las fórmulas de referencia de la spec (``quote_min`` con floor,
  ``fee`` con ceil) para que los tests comparen contra el valor esperado exacto.

Nunca usar ``float`` en tests para montos: toda la aritmética es entera.
"""

import re

# --- Constantes del dominio (spec/00-fundaciones) ---------------------------------

PATRON_MONTO = re.compile(r"^(0|[1-9][0-9]*)$")

WEI_POR_ETH = 10**18          # 1 ETH = 10^18 wei
USDCMIN_POR_USDC = 10**6      # 1 USDC = 10^6 unidades mínimas

TICK_SIZE = 10_000            # price_min mod 10000 == 0 (activos-y-par §4.1)
LOT_SIZE = 10**14             # q_wei mod 10^14 == 0 (activos-y-par §4.2)
MIN_NOTIONAL = 10_000_000     # 10 USDC en USDC-min (activos-y-par §4.4)

FEE_BPS_MAKER = 10            # 0.10 % (convenciones-monetarias §3.3)
FEE_BPS_TAKER = 20            # 0.20 %
FEE_DENOMINADOR = 10_000

CHAIN_ID = 11155111           # Sepolia (activos-y-par §1)
CONFIRMACIONES_REQUERIDAS = 12

SIMBOLO = "ETH-USDC"          # símbolo canónico del par único (RG-API-1)


# --- Validación de serialización ---------------------------------------------------

def es_monto_valido(valor) -> bool:
    """True sii `valor` es un string que matchea ^(0|[1-9][0-9]*)$.

    Un número JSON (int/float de Python tras el parseo) NO es válido: la spec
    exige string. Tampoco lo son negativos, decimales, notación científica ni
    ceros a la izquierda.
    """
    return isinstance(valor, str) and PATRON_MONTO.fullmatch(valor) is not None


def assert_monto(valor, campo: str = "monto") -> int:
    """Asserta que `valor` es un monto bien serializado y devuelve su int.

    Uso típico:
        precio = assert_monto(orden["priceMin"], "priceMin")
    """
    assert es_monto_valido(valor), (
        f"{campo}: se esperaba string entero ^(0|[1-9][0-9]*)$, "
        f"llegó {valor!r} (tipo {type(valor).__name__})"
    )
    return int(valor)


def a_int(valor) -> int:
    """Convierte un monto serializado (string) a int, validando el patrón."""
    return assert_monto(valor)


def a_str(valor: int) -> str:
    """Serializa un int no negativo como string de monto para enviar a la API."""
    if not isinstance(valor, int) or isinstance(valor, bool) or valor < 0:
        raise ValueError(f"monto inválido para serializar: {valor!r}")
    return str(valor)


# --- Conversión a unidades humanas (sólo para construir datos de prueba) -----------

def eth_a_wei(eth_enteros: int) -> int:
    """ETH enteros → wei. Sólo enteros: para fracciones operar en wei directamente."""
    return eth_enteros * WEI_POR_ETH


def usdc_a_usdcmin(usdc_enteros: int) -> int:
    """USDC enteros → unidad mínima (6 decimales)."""
    return usdc_enteros * USDCMIN_POR_USDC


def precio_usdc_a_pricemin(usdc_enteros: int) -> int:
    """Precio en USDC/ETH enteros → price_min (USDC-min por 1 ETH)."""
    return usdc_enteros * USDCMIN_POR_USDC


# --- Fórmulas de referencia de la spec ---------------------------------------------

def quote_min(q_wei: int, price_min: int) -> int:
    """Notional de un fill: floor(q_wei × price_min / 10^18).

    (convenciones-monetarias §2.2; mismo quote_min para ambas patas del fill.)
    """
    return (q_wei * price_min) // WEI_POR_ETH


def fee(monto_recibido: int, fee_bps: int) -> int:
    """Fee de un fill: ceil(monto_recibido × fee_bps / 10000).

    (convenciones-monetarias §3.3; redondeo a favor del exchange.)
    ceil con enteros: -(-a // b).
    """
    return -(-(monto_recibido * fee_bps) // FEE_DENOMINADOR)


def fee_maker(monto_recibido: int) -> int:
    return fee(monto_recibido, FEE_BPS_MAKER)


def fee_taker(monto_recibido: int) -> int:
    return fee(monto_recibido, FEE_BPS_TAKER)


def es_multiplo_de_tick(price_min: int) -> bool:
    return price_min > 0 and price_min % TICK_SIZE == 0


def es_multiplo_de_lot(q_wei: int) -> bool:
    return q_wei > 0 and q_wei % LOT_SIZE == 0
