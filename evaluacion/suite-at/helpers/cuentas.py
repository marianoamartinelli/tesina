"""Helpers de dominio: registro y login de usuarios de prueba.

Contrato (HU-09-01 escenarios 1–3; épica 01):
- ``POST /api/v1/auth/register`` con ``{email, password}`` → 201
  ``{accountId, email, createdAt}`` (sin token: no hay auto-login, HU-01-01 RN-7).
- ``POST /api/v1/auth/login`` con ``{email, password}`` → 200 con ``token`` (string
  usable como Bearer) y ``expiresAt`` (ISO-8601 UTC).

Cada test debe usar usuarios **frescos** (emails únicos) para no depender del
estado de otros tests y para no compartir el límite de tasa por cuenta
(HU-09-02 RN-12: 60 req/min por cuenta y endpoint).
"""

import secrets
from dataclasses import dataclass

from .api import ClienteApi

PASSWORD_DEFECTO = "Password-123"  # cumple la política: 8..128 caracteres (HU-01-01 RN-3)


def email_unico(prefijo: str = "at") -> str:
    """Email único por invocación (dominio reservado para pruebas, RFC 2606)."""
    return f"{prefijo}-{secrets.token_hex(8)}@example.com"


@dataclass
class Usuario:
    """Usuario de prueba registrado y autenticado contra el SUT."""

    email: str
    password: str
    account_id: str
    token: str
    api: ClienteApi  # cliente con Authorization: Bearer <token>


def registrar(api: ClienteApi, email: str | None = None, password: str = PASSWORD_DEFECTO) -> dict:
    """Registra una cuenta nueva y devuelve el cuerpo 201 ({accountId, email, createdAt}).

    Falla con AssertionError si el registro no responde 201 (el helper asume el
    camino feliz; los tests de error del registro llaman a la API directamente).
    """
    email = email or email_unico()
    resp = api.post("/auth/register", json={"email": email, "password": password})
    assert resp.status_code == 201, (
        f"registro falló: status {resp.status_code}, cuerpo {resp.text[:300]}"
    )
    cuerpo = resp.json()
    assert cuerpo.get("email") and cuerpo.get("accountId"), (
        f"respuesta de registro sin accountId/email: {cuerpo!r}"
    )
    return cuerpo


def login(api: ClienteApi, email: str, password: str = PASSWORD_DEFECTO) -> str:
    """Hace login y devuelve el token de sesión (string no vacío)."""
    resp = api.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, (
        f"login falló: status {resp.status_code}, cuerpo {resp.text[:300]}"
    )
    cuerpo = resp.json()
    token = cuerpo.get("token")
    assert isinstance(token, str) and token, f"login sin token utilizable: {cuerpo!r}"
    return token


def crear_usuario(api: ClienteApi, prefijo: str = "at", password: str = PASSWORD_DEFECTO) -> Usuario:
    """Registra un usuario fresco, hace login y devuelve un `Usuario` con su
    cliente autenticado (`usuario.api`).

    Uso:
        u = crear_usuario(api)
        resp = u.api.get("/balances")
    """
    email = email_unico(prefijo)
    registro = registrar(api, email=email, password=password)
    token = login(api, email, password)
    return Usuario(
        email=email,
        password=password,
        account_id=registro["accountId"],
        token=token,
        api=api.con_token(token),
    )
