"""Cliente JSON-RPC contra el nodo local anvil del entorno de evaluación.

El entorno (evaluacion/suite-at/entorno/) levanta un anvil con
``--chain-id 11155111`` (Sepolia local, spec/00-fundaciones/activos-y-par-de-trading.md)
y automine (cada transacción se mina de inmediato). Este helper da a los tests el
control del mundo on-chain:

- fondear direcciones con ETH (``enviar_eth``) y USDC-mock (``mint_usdc``),
- simular depósitos (transferencias hacia la dirección de depósito del usuario),
- minar bloques vacíos para avanzar confirmaciones (``minar_bloques``; con
  CONFIRMACIONES_REQUERIDAS = 12, minar 12 tras la inclusión acredita),
- inspeccionar transacciones/receipts de retiros del SUT (chainId, nonce, gas).

Las cuentas de anvil (mnemonic canónico de Hardhat/Anvil, HU-06-02) están
desbloqueadas: ``eth_sendTransaction`` no requiere firmar del lado del test.
"""

import json
import os
import urllib.request

VAR_RPC_URL = "EVAL_RPC_URL"
VAR_USDC = "EVAL_USDC_ADDRESS"
RPC_URL_DEFECTO = "http://127.0.0.1:8545"

CHAIN_ID_SEPOLIA = 11155111

# Cuentas 0..9 de anvil (mnemonic canónico "test test ... junk", HU-06-02):
# desbloqueadas y prefondeadas con 10000 ETH. La 0 es la tesorería del harness.
CUENTA_TESORERIA = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"

# Selectores de función ERC-20 (4 primeros bytes de keccak256 de la firma; estándar):
SELECTOR_MINT = "0x40c10f19"        # mint(address,uint256)
SELECTOR_TRANSFER = "0xa9059cbb"    # transfer(address,uint256)
SELECTOR_BALANCE_OF = "0x70a08231"  # balanceOf(address)
SELECTOR_DECIMALS = "0x313ce567"    # decimals()


def _abi_direccion(direccion: str) -> str:
    return direccion.lower().replace("0x", "").rjust(64, "0")


def _abi_uint256(valor: int) -> str:
    return format(valor, "x").rjust(64, "0")


class ClienteRpc:
    """Cliente JSON-RPC mínimo (stdlib) contra el anvil del entorno."""

    def __init__(self, url: str | None = None, usdc: str | None = None):
        self.url = (url or os.environ.get(VAR_RPC_URL) or RPC_URL_DEFECTO).rstrip("/")
        self.direccion_usdc = usdc or os.environ.get(VAR_USDC)
        self._id = 0

    # -- transporte -------------------------------------------------------------

    def llamar(self, metodo: str, params: list | None = None):
        self._id += 1
        cuerpo = json.dumps(
            {"jsonrpc": "2.0", "id": self._id, "method": metodo, "params": params or []}
        ).encode()
        pedido = urllib.request.Request(
            self.url, data=cuerpo, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(pedido, timeout=10) as resp:
            respuesta = json.loads(resp.read())
        if "error" in respuesta:
            raise RuntimeError(f"RPC {metodo} falló: {respuesta['error']}")
        return respuesta["result"]

    def disponible(self) -> bool:
        """True si el nodo responde (para skip de tests que requieren entorno)."""
        try:
            return self.chain_id() == CHAIN_ID_SEPOLIA
        except Exception:
            return False

    # -- lectura ------------------------------------------------------------------

    def chain_id(self) -> int:
        return int(self.llamar("eth_chainId"), 16)

    def numero_de_bloque(self) -> int:
        return int(self.llamar("eth_blockNumber"), 16)

    def balance_eth(self, direccion: str) -> int:
        """Balance on-chain en wei (int)."""
        return int(self.llamar("eth_getBalance", [direccion, "latest"]), 16)

    def balance_usdc(self, direccion: str, contrato: str | None = None) -> int:
        """Balance del token USDC-mock en USDC-min (int), vía eth_call balanceOf."""
        destino = contrato or self._usdc_requerido()
        data = SELECTOR_BALANCE_OF + _abi_direccion(direccion)
        resultado = self.llamar("eth_call", [{"to": destino, "data": data}, "latest"])
        return int(resultado, 16)

    def transaccion(self, tx_hash: str) -> dict | None:
        """La transacción (incluye chainId/nonce/gasPrice) o None si no existe."""
        return self.llamar("eth_getTransactionByHash", [tx_hash])

    def receipt(self, tx_hash: str) -> dict | None:
        return self.llamar("eth_getTransactionReceipt", [tx_hash])

    def nonce(self, direccion: str) -> int:
        return int(self.llamar("eth_getTransactionCount", [direccion, "latest"]), 16)

    # -- mutación (anvil) ------------------------------------------------------------

    def minar_bloques(self, cantidad: int = 1) -> None:
        """Mina `cantidad` bloques vacíos (avanza confirmaciones: 12 ⇒ acreditable)."""
        self.llamar("anvil_mine", [hex(cantidad)])

    def enviar_eth(self, hacia: str, valor_wei: int, desde: str = CUENTA_TESORERIA) -> str:
        """Transfiere ETH desde una cuenta desbloqueada de anvil. Devuelve txHash.

        Con automine la transacción queda incluida de inmediato (1 bloque).
        """
        tx = {"from": desde, "to": hacia, "value": hex(valor_wei)}
        return self.llamar("eth_sendTransaction", [tx])

    def mint_usdc(self, hacia: str, monto_usdcmin: int, contrato: str | None = None) -> str:
        """Emite USDC-mock a una dirección (mint público del mock). Devuelve txHash."""
        destino = contrato or self._usdc_requerido()
        data = SELECTOR_MINT + _abi_direccion(hacia) + _abi_uint256(monto_usdcmin)
        tx = {"from": CUENTA_TESORERIA, "to": destino, "data": data, "gas": hex(200_000)}
        return self.llamar("eth_sendTransaction", [tx])

    def transferir_usdc(
        self, hacia: str, monto_usdcmin: int, desde: str = CUENTA_TESORERIA, contrato: str | None = None
    ) -> str:
        """`transfer` ERC-20 desde una cuenta desbloqueada (simula un depósito USDC:
        el log Transfer hacia la dirección de depósito es lo que detecta la épica 07)."""
        destino = contrato or self._usdc_requerido()
        data = SELECTOR_TRANSFER + _abi_direccion(hacia) + _abi_uint256(monto_usdcmin)
        tx = {"from": desde, "to": destino, "data": data, "gas": hex(200_000)}
        return self.llamar("eth_sendTransaction", [tx])

    def esperar_receipt(self, tx_hash: str) -> dict:
        """Receipt de una tx (con automine debería existir de inmediato)."""
        from .espera import esperar_hasta

        return esperar_hasta(
            lambda: self.receipt(tx_hash),
            mensaje=f"sin receipt para {tx_hash}",
        )

    # -- helpers de escenario ----------------------------------------------------------

    def depositar_eth(self, direccion_deposito: str, valor_wei: int, confirmar: bool = True) -> str:
        """Simula un depósito de ETH del usuario: transferencia a su dirección de
        depósito + (opcional) 12 bloques para alcanzar las confirmaciones (épica 07)."""
        tx_hash = self.enviar_eth(direccion_deposito, valor_wei)
        self.esperar_receipt(tx_hash)
        if confirmar:
            self.minar_bloques(12)
        return tx_hash

    def depositar_usdc(self, direccion_deposito: str, monto_usdcmin: int, confirmar: bool = True) -> str:
        """Simula un depósito de USDC: mint a tesorería + transfer al usuario
        (el depósito debe detectarse por el log Transfer, HU-07-02)."""
        self.mint_usdc(CUENTA_TESORERIA, monto_usdcmin)
        tx_hash = self.transferir_usdc(direccion_deposito, monto_usdcmin)
        self.esperar_receipt(tx_hash)
        if confirmar:
            self.minar_bloques(12)
        return tx_hash

    # -- interno ------------------------------------------------------------------------

    def _usdc_requerido(self) -> str:
        if not self.direccion_usdc:
            raise RuntimeError(
                f"Falta la env var {VAR_USDC} (dirección del contrato USDC-mock; "
                "la imprime entorno/desplegar-usdc.py)."
            )
        return self.direccion_usdc
