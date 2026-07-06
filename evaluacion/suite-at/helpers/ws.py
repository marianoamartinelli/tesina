"""Cliente WebSocket black-box contra los canales de la épica 09.

Envuelve ``websockets`` (cliente síncrono) con:
- URL tomada de la env var ``EXCHANGE_WS_URL`` (p. ej. ``ws://localhost:3000/api/v1/ws``,
  RG-API-11: canal público y privado sobre la misma URL);
- mensajes JSON de texto: ``enviar(dict)`` / ``recibir() -> dict``;
- ``recibir_hasta(pred)`` para esperar un mensaje puntual descartando intermedios
  (p. ej. ignorar pings de heartbeat, HU-09-03 RN-14);
- helpers de protocolo: ``suscribir``, ``autenticar`` (HU-09-03 RN-2, HU-09-04 RN-1).
"""

import json
import os

from websockets.sync.client import connect

VAR_WS_URL = "EXCHANGE_WS_URL"
TIMEOUT_WS_SEGUNDOS = float(os.environ.get("SUITE_WS_TIMEOUT_SEGUNDOS", "10"))


def url_ws_configurada() -> str | None:
    valor = os.environ.get(VAR_WS_URL, "").strip()
    return valor or None


class ConexionWs:
    """Conexión WebSocket de prueba. Usar como context manager.

    Uso:
        with ConexionWs() as ws:
            ws.suscribir("orderbook")
            snapshot = ws.recibir_hasta(lambda m: m.get("type") == "snapshot")
    """

    def __init__(self, url: str | None = None, timeout: float = TIMEOUT_WS_SEGUNDOS):
        destino = url or url_ws_configurada()
        if not destino:
            raise RuntimeError(
                f"Falta la env var {VAR_WS_URL} (URL del endpoint WS, p. ej. ws://host/api/v1/ws)."
            )
        self.timeout = timeout
        self._ws = connect(destino, open_timeout=timeout, close_timeout=timeout)

    # -- primitivas ---------------------------------------------------------------

    def enviar(self, mensaje: dict) -> None:
        self._ws.send(json.dumps(mensaje))

    def recibir(self, timeout: float | None = None) -> dict:
        """Recibe y parsea el próximo mensaje JSON. TimeoutError si no llega."""
        crudo = self._ws.recv(timeout=timeout if timeout is not None else self.timeout)
        return json.loads(crudo)

    def recibir_hasta(self, predicado, timeout: float | None = None, descartar_ping: bool = True) -> dict:
        """Recibe mensajes hasta que `predicado(mensaje)` sea True y lo devuelve.

        Descarta los mensajes intermedios (por defecto también los `ping` del
        heartbeat, respondiéndoles `pong` para mantener viva la conexión).
        Lanza TimeoutError (del socket) si el mensaje esperado no llega.
        """
        limite = timeout if timeout is not None else self.timeout
        while True:
            mensaje = self.recibir(timeout=limite)
            if descartar_ping and mensaje.get("type") == "ping":
                self.enviar({"type": "pong"})
                continue
            if predicado(mensaje):
                return mensaje

    def no_debe_llegar(self, predicado, ventana: float = 2.0) -> None:
        """Asserta que durante `ventana` segundos NO llega un mensaje que cumpla
        `predicado` (p. ej. aislamiento por cuenta, AT-09-02-10)."""
        try:
            mensaje = self.recibir_hasta(predicado, timeout=ventana)
        except TimeoutError:
            return
        raise AssertionError(f"llegó un mensaje que no debía llegar: {mensaje!r}")

    # -- protocolo de la épica 09 ---------------------------------------------------

    def autenticar(self, token: str) -> dict:
        """Canal privado (HU-09-04 RN-1): primer mensaje `auth`; devuelve la respuesta
        (`{"type": "authenticated"}` o envelope de error)."""
        self.enviar({"type": "auth", "token": token})
        return self.recibir_hasta(
            lambda m: m.get("type") == "authenticated" or "error" in m
        )

    def suscribir(self, canal: str, symbol: str | None = "ETH-USDC", depth: int | None = None) -> dict:
        """Envía `subscribe` y devuelve la respuesta (`subscribed` o error).

        Para canales privados (`orders`/`balances`/`withdrawals`) pasar
        ``symbol=None`` (HU-09-04 RN-2: no requieren symbol).
        """
        mensaje: dict = {"type": "subscribe", "channel": canal}
        if symbol is not None:
            mensaje["symbol"] = symbol
        if depth is not None:
            mensaje["depth"] = depth
        self.enviar(mensaje)
        return self.recibir_hasta(
            lambda m: (m.get("type") == "subscribed" and m.get("channel") == canal)
            or "error" in m
        )

    def desuscribir(self, canal: str, symbol: str | None = "ETH-USDC") -> dict:
        mensaje: dict = {"type": "unsubscribe", "channel": canal}
        if symbol is not None:
            mensaje["symbol"] = symbol
        self.enviar(mensaje)
        return self.recibir_hasta(
            lambda m: (m.get("type") == "unsubscribed" and m.get("channel") == canal)
            or "error" in m
        )

    # -- ciclo de vida ---------------------------------------------------------------

    def cerrar(self) -> None:
        self._ws.close()

    def __enter__(self) -> "ConexionWs":
        return self

    def __exit__(self, *exc) -> None:
        self.cerrar()
