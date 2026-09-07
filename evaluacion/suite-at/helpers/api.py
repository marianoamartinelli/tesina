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

import collections
import threading
import time

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

    # Control de tasa del propio harness (spec-v1.2, ADR-024): /auth/* limita por
    # ORIGEN —60 solicitudes de registro / 60 intentos fallidos de login por ventana
    # deslizante de 60 s— y toda la suite sale de un único origen. Sin este freno la
    # suite se limita a sí misma y los ATs de registro fallan por 429 sin defecto del
    # SUT (medido en la pre-piloto-2, hallazgo H2-05). Es una espera del cliente, no
    # cambia ningún criterio: los ATs de rate limiting lo apagan con `throttle_auth`.
    throttle_auth: bool = True
    UMBRAL_VENTANA = 55            # margen sobre los 60 de la spec: el SUT pudo contar
    VENTANA_SEGUNDOS = 62.0        # solicitudes previas a esta sesión de la suite
    _ventana_registro: "collections.deque[float]" = collections.deque()
    _ventana_login_fallidos: "collections.deque[float]" = collections.deque()
    _lock = threading.Lock()

    @classmethod
    def _esperar_ventana(cls, ventana) -> None:
        with cls._lock:
            ahora = time.monotonic()
            while ventana and ahora - ventana[0] > cls.VENTANA_SEGUNDOS:
                ventana.popleft()
            if len(ventana) >= cls.UMBRAL_VENTANA:
                espera = ventana[0] + cls.VENTANA_SEGUNDOS - ahora + 0.5
                if espera > 0:
                    time.sleep(espera)
                while ventana and time.monotonic() - ventana[0] > cls.VENTANA_SEGUNDOS:
                    ventana.popleft()

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
        es_registro = ruta == "/auth/register"
        es_login = ruta == "/auth/login"
        if ClienteApi.throttle_auth and es_registro:
            self._esperar_ventana(ClienteApi._ventana_registro)
        if ClienteApi.throttle_auth and es_login:
            self._esperar_ventana(ClienteApi._ventana_login_fallidos)
        if content is not None:
            hdrs = {"Content-Type": "application/json"}
            hdrs.update(headers or {})
            resp = self._http.post(ruta, content=content, headers=hdrs)
        else:
            resp = self._http.post(ruta, json=json, headers=headers)
        if ClienteApi.throttle_auth and es_registro:
            ClienteApi._ventana_registro.append(time.monotonic())
        if ClienteApi.throttle_auth and es_login and resp.status_code != 200:
            ClienteApi._ventana_login_fallidos.append(time.monotonic())
        return resp

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
