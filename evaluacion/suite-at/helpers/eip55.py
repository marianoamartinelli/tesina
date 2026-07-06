"""Direcciones Ethereum: validación de formato y checksum EIP-55.

La spec exige que toda dirección expuesta por la API tenga formato ``0x`` + 40 hex
con checksum EIP-55 (HU-09-01 RN-10, HU-06-02 RN-4). Implementación de referencia
del EIP-55: Keccak-256 (vía pycryptodome) sobre la dirección en minúsculas; cada
dígito hex va en mayúscula sii el nibble correspondiente del hash es ≥ 8.
"""

import re

from Crypto.Hash import keccak

RE_DIRECCION_HEX = re.compile(r"^0x[0-9a-fA-F]{40}$")
RE_TXHASH = re.compile(r"^0x[0-9a-fA-F]{64}$")


def a_checksum(direccion: str) -> str:
    """Aplica el checksum EIP-55 a una dirección (con o sin checksum previo).

    Vectores canónicos en spec/06-wallet-hd-y-direcciones/HU-06-02 (§ vectores
    EIP-55): p. ej. `5aaeb6053f...` → `0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed`.
    """
    if not RE_DIRECCION_HEX.fullmatch(direccion if direccion.startswith("0x") else "0x" + direccion):
        raise ValueError(f"no es una dirección Ethereum de 20 bytes: {direccion!r}")
    cuerpo = (direccion[2:] if direccion.startswith("0x") else direccion).lower()
    h = keccak.new(digest_bits=256, data=cuerpo.encode("ascii")).hexdigest()
    resultado = "".join(
        c.upper() if c.isalpha() and int(h[i], 16) >= 8 else c
        for i, c in enumerate(cuerpo)
    )
    return "0x" + resultado


def es_direccion_valida(direccion) -> bool:
    """True sii es string `0x`+40 hex con checksum EIP-55 correcto.

    Nota: una dirección toda en minúsculas NO pasa esta validación estricta
    (la spec exige que el SUT *emita* direcciones con checksum aplicado).
    """
    if not isinstance(direccion, str) or not RE_DIRECCION_HEX.fullmatch(direccion):
        return False
    return a_checksum(direccion) == direccion


def assert_direccion(direccion, campo: str = "address") -> str:
    """Asserta formato + checksum EIP-55 y devuelve la dirección."""
    assert isinstance(direccion, str) and RE_DIRECCION_HEX.fullmatch(direccion or ""), (
        f"{campo}: se esperaba 0x + 40 hex, llegó {direccion!r}"
    )
    assert a_checksum(direccion) == direccion, (
        f"{campo}: checksum EIP-55 incorrecto en {direccion!r} "
        f"(esperado {a_checksum(direccion)!r})"
    )
    return direccion


def romper_checksum(direccion: str) -> str:
    """Devuelve la misma dirección con el checksum EIP-55 inválido (para tests
    de INVALID_ADDRESS): invierte la caja del primer carácter alfabético.

    Garantiza que el resultado difiere del checksum correcto.
    """
    con_checksum = a_checksum(direccion)
    cuerpo = list(con_checksum[2:])
    for i, c in enumerate(cuerpo):
        if c.isalpha():
            cuerpo[i] = c.lower() if c.isupper() else c.upper()
            return "0x" + "".join(cuerpo)
    raise ValueError(f"dirección sin caracteres alfabéticos, no se puede romper: {direccion!r}")
