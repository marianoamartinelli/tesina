"""Cliente HTTP black-box contra el contrato REST de la épica 09.

Envuelve httpx con:
- base URL tomada de la env var ``EXCHANGE_API_URL`` (p. ej. ``http://localhost:3000``);
  la ruta base ``/api/v1`` la agrega el cliente (RG-API-1), así los tests usan rutas
  cortas: ``api.get("/balances")``.
- token Bearer opcional (RG-API-5): ``api.con_token(token)`` devuelve un cliente
  autenticado; el cliente sin token sirve para los endpoints públicos.
- sin raise en 4xx/5xx: los tests assertan status y envelope explícitamente.
"""

import os

import httpx

VAR_API_URL = "EXCHANGE_API_URL"
RUTA_BASE = "/api/v1"
TIMEOUT_HTTP_SEGUNDOS = float(os.environ.get("SUITE_HTTP_TIMEOUT_SEGUNDOS", "10"))


def url_api_configurada() -> str | None:
    """URL raíz del SUT (sin /api/v1) o None si no está configurada."""
    valor = os.environ.get(VAR_API_URL, "").strip()
    return valor.rstrip("/") or None


class ClienteApi:
    """Cliente REST black-box. No lanza excepciones por status de error.

    Uso:
        api = ClienteApi()                       # sin token (endpoints públicos)
        resp = api.post("/auth/register", json={"email": ..., "password": ...})
        autenticado = api.con_token(token)       # con Authorization: Bearer <token>
        resp = autenticado.get("/balances")
    """

    def __init__(self, base_url: str | None = None, token: str | None = None):
        base = base_url or url_api_configurada()
        if not base:
            raise RuntimeError(
                f"Falta la env var {VAR_API_URL} (URL raíz del SUT, sin /api/v1)."
            )
        self.base_url = base
        self.token = token
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._http = httpx.Client(
            base_url=base + RUTA_BASE,
            headers=headers,
            timeout=TIMEOUT_HTTP_SEGUNDOS,
        )

    # -- construcción de variantes ---------------------------------------------------

    def con_token(self, token: str) -> "ClienteApi":
        """Nuevo cliente con el mismo destino y ``Authorization: Bearer <token>``."""
        return ClienteApi(base_url=self.base_url, token=token)

    def sin_token(self) -> "ClienteApi":
        """Nuevo cliente sin header Authorization (para probar UNAUTHENTICATED)."""
        return ClienteApi(base_url=self.base_url, token=None)

    # -- verbos -----------------------------------------------------------------------

    def get(self, ruta: str, params: dict | None = None, headers: dict | None = None):
        return self._http.get(ruta, params=params, headers=headers)

    def post(
        self,
        ruta: str,
        json: dict | None = None,
        content: bytes | str | None = None,
        headers: dict | None = None,
    ):
        """POST con cuerpo JSON (`json=`) o cuerpo crudo (`content=`, para probar
        cuerpos que no son JSON válido, AT-09-01-16)."""
        if content is not None:
            hdrs = {"Content-Type": "application/json"}
            hdrs.update(headers or {})
            return self._http.post(ruta, content=content, headers=hdrs)
        return self._http.post(ruta, json=json, headers=headers)

    def delete(self, ruta: str, headers: dict | None = None):
        return self._http.delete(ruta, headers=headers)

    def request(self, metodo: str, ruta: str, **kwargs):
        """Verbo arbitrario (p. ej. PUT para probar METHOD_NOT_ALLOWED)."""
        return self._http.request(metodo, ruta, **kwargs)

    # -- ciclo de vida ------------------------------------------------------------------

    def cerrar(self) -> None:
        self._http.close()

    def __enter__(self) -> "ClienteApi":
        return self

    def __exit__(self, *exc) -> None:
        self.cerrar()
