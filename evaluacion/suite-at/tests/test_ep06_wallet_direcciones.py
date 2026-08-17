"""Épica 06 — Wallet HD y direcciones de depósito: tests de aceptación black-box.

Superficie observable de la épica (HELPERS.md, black-box estricto): el único
recurso público es ``GET /api/v1/deposit-address?asset=ETH|USDC`` (HU-06-04;
contrato fijado por la épica 09, HU-09-01 RN-10). El seed/mnemonic, las claves
privadas, el ``address_index`` del mapeo persistido, el proceso de provisioning
y el evento interno ``DepositAddressAssigned`` NO tienen superficie REST/WS: los
ATs que dependen de ellos están declarados en ``no-automatizables.yaml``.

La **persistencia** del provisioning (AT-06-01-07/08, AT-06-02-06, AT-06-03-06)
sí es observable: el reinicio del SUT lo provee el evaluador vía
``SUITE_CMD_REINICIO_SUT`` (``comunes_reinicio``) y la dirección emitida antes y
después del reinicio es la proyección black-box del seed, de la derivación y del
mapeo cuenta→índice (ADR-011). Sin esa env var, ese test salta.

Lo que sí se verifica acá, con criptografía real (nunca "a ojo"):

- **Checksum EIP-55 recomputado**: toda dirección emitida por el SUT se valida
  contra la implementación de referencia de la suite (helpers/eip55.py:
  Keccak-256 sobre el lowercase, mayúscula sii el nibble del hash es ≥ 8), que a
  su vez está validada contra los vectores canónicos de HU-06-02 en
  test_smoke.py (TestEip55).
- **Unicidad de la dirección entre cuentas**: proyección observable de la
  biyección cuenta ↔ índice ↔ dirección (HU-06-03 RN-1/RN-5/RN-6): dos cuentas
  con el mismo ``address_index`` compartirían dirección (HU-06-02 RN-5), así que
  la unicidad de direcciones observa la no-colisión de índices.
- **Estabilidad / idempotencia por cuenta** (HU-06-03 RN-4, HU-06-04 RN-5/RN-7).
- **Contrato de respuesta y modelo de errores** de la consulta (HU-06-04
  RN-1..RN-9; chainId siempre string "11155111", RN-8).
- **Custodia**: ninguna respuesta expone campos de material secreto
  (HU-06-01 RN-5, HU-06-02 RN-6).
"""

import os
import re
from concurrent.futures import ThreadPoolExecutor

import pytest

from helpers.cuentas import crear_usuario, email_unico, login, registrar
from helpers.eip55 import a_checksum, assert_direccion
from helpers.errores import assert_error

from comunes_reinicio import comando_reinicio, reiniciar_sut, relogin

# chainId de Sepolia serializado como string (HU-06-04 RN-8: "de forma
# consistente en el contrato, los escenarios y details de error").
CHAIN_ID_SEPOLIA = "11155111"

# Para buscar direcciones filtradas dentro de un cuerpo de error (sin anclas,
# a diferencia de eip55.RE_DIRECCION_HEX que exige match completo).
RE_DIRECCION_EN_TEXTO = re.compile(r"0x[0-9a-fA-F]{40}")

# Nombres de campo que delatan material secreto en una respuesta (HU-06-01 RN-5:
# mnemonic/seed/clave privada nunca en respuestas de API; HU-06-02 RN-6). Se
# comparan contra el nombre de clave normalizado (minúsculas, sin '_' ni '-').
TERMINOS_SECRETOS = ("mnemonic", "seed", "privatekey", "privkey", "secretkey", "xprv")


def _direccion(usuario, asset: str = "ETH") -> dict:
    """GET /deposit-address para el activo dado, assertando el 200 del contrato
    (HU-06-04, épica 09 HU-09-01 RN-10). Devuelve el cuerpo JSON."""
    resp = usuario.api.get("/deposit-address", params={"asset": asset})
    assert resp.status_code == 200, f"GET /deposit-address?asset={asset}: {resp.status_code} {resp.text[:300]}"
    return resp.json()


def _claves_sospechosas(dato, ruta: str = "") -> list[str]:
    """Recorre recursivamente un JSON y devuelve las rutas de claves cuyo nombre
    normalizado contiene un término de material secreto (TERMINOS_SECRETOS).

    El *valor* del secreto es incognoscible black-box (por diseño, nunca salió
    del SUT); lo verificable es que no exista ningún campo con esos nombres, que
    es la forma testeable de HU-06-01 escenario 6 / HU-06-02 escenario 7.
    """
    hallazgos: list[str] = []
    if isinstance(dato, dict):
        for clave, valor in dato.items():
            ruta_hija = f"{ruta}.{clave}" if ruta else str(clave)
            normalizada = str(clave).lower().replace("_", "").replace("-", "")
            if any(termino in normalizada for termino in TERMINOS_SECRETOS):
                hallazgos.append(ruta_hija)
            hallazgos.extend(_claves_sospechosas(valor, ruta_hija))
    elif isinstance(dato, list):
        for i, valor in enumerate(dato):
            hallazgos.extend(_claves_sospechosas(valor, f"{ruta}[{i}]"))
    return hallazgos


# ---------------------------------------------------------------------------------
# HU-06-01 — Generación y custodia del seed HD (parte observable black-box)
# ---------------------------------------------------------------------------------


@pytest.mark.at("AT-06-01-06")
def test_endpoints_autenticados_no_exponen_mnemonic_seed_ni_clave_privada(usuario):
    """HU-06-01 Escenario 6 (seguridad / custodia): El secreto nunca se expone.

    - Dado un seed/mnemonic ya provisionado (implícito: el SUT arrancó y opera)
    - Cuando un cliente invoca, con respuesta exitosa, cada uno de los endpoints
      autenticados que pueden tocar datos derivados del seed que el escenario
      enumera: GET /deposit-address (ETH y USDC), GET /balances, GET /me,
      GET /deposits y GET /withdrawals
    - Entonces en ninguna de esas respuestas aparece un campo `mnemonic`, `seed`
      ni `privateKey` (RN-5): solo claves públicas y direcciones

    El "Y" complementario del escenario (auditoría estática de logs/trazas) es
    explícitamente white-box ("procedimiento de auditoría estática
    complementario") y se realiza en H8; acá se cubre la superficie HTTP
    completa que el escenario enumera.
    """
    consultas = [
        ("/deposit-address", {"asset": "ETH"}),
        ("/deposit-address", {"asset": "USDC"}),
        ("/balances", None),
        ("/me", None),
        ("/deposits", None),
        ("/withdrawals", None),
    ]
    for ruta, params in consultas:
        # Cuando: invocación exitosa del endpoint autenticado
        resp = usuario.api.get(ruta, params=params)
        assert resp.status_code == 200, f"{ruta}: {resp.status_code} {resp.text[:300]}"
        # Entonces: ningún campo con nombre de material secreto, a cualquier profundidad
        hallazgos = _claves_sospechosas(resp.json())
        assert not hallazgos, f"{ruta} expone campos de material secreto: {hallazgos}"


# ---------------------------------------------------------------------------------
# HU-06-02 — Derivación jerárquica BIP-32/BIP-44 (parte observable black-box)
# ---------------------------------------------------------------------------------


@pytest.mark.at("AT-06-02-03")
def test_toda_direccion_emitida_cumple_checksum_eip55(api):
    """HU-06-02 Escenario 3: Checksum EIP-55 correcto.

    - Dado direcciones emitidas por el Sistema (tres cuentas frescas, ambos activos)
    - Cuando se recomputa el checksum EIP-55 con la implementación de referencia
      de la suite (helpers/eip55.py: Keccak-256 sobre el lowercase ASCII,
      mayúscula sii el nibble del hash es ≥ 8 — el algoritmo exacto de RN-4)
    - Entonces cada dirección emitida coincide carácter a carácter con su forma
      checksum, y tiene la forma 0x + 40 hex ("toda dirección emitida por el
      Sistema tiene la forma 0x + 40 hex con checksum EIP-55")

    Los vectores fijos de la tabla de HU-06-02 alimentan la función interna de
    codificación del SUT (no invocable black-box): con ellos se valida acá la
    implementación de REFERENCIA (también en test_smoke.py::TestEip55). La
    cláusula observable del escenario se verifica recomputando el checksum sobre
    direcciones reales emitidas: cada dirección emitida es un vector real contra
    la referencia, y un encoder EIP-55 incorrecto produciría un mismatch en
    cualquier dirección que contenga letras (todas, salvo probabilidad ínfima).
    """
    # Sanity de la referencia contra el primer vector canónico de la spec
    # (HU-06-02, tabla "Vectores de checksum EIP-55"): valida al árbitro, no al SUT.
    assert (
        a_checksum("0x5aaeb6053f3e94c9b9a09f33669435e7ef1beaed")
        == "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"
    )

    # Dado: direcciones emitidas por el SUT para tres cuentas frescas
    emitidas = []
    for _ in range(3):
        u = crear_usuario(api, prefijo="at06-eip55")
        emitidas.append(_direccion(u, "ETH")["address"])
        cuerpo_usdc = _direccion(u, "USDC")
        emitidas.append(cuerpo_usdc["address"])
        if "tokenAddress" in cuerpo_usdc:
            # tokenAddress también es una dirección emitida (RN-6 de HU-06-04);
            # su presencia obligatoria se verifica en AT-06-04-02.
            emitidas.append(cuerpo_usdc["tokenAddress"])

    # Cuando / Entonces: recomputación EIP-55 exacta sobre cada dirección emitida
    for direccion in emitidas:
        assert_direccion(direccion)  # 0x + 40 hex y checksum recomputado idéntico


@pytest.mark.at("AT-06-02-07")
def test_respuestas_con_direcciones_no_exponen_clave_privada(usuario):
    """HU-06-02 Escenario 7 (seguridad): La clave privada nunca se expone.

    - Dado que el SUT deriva claves para responder los endpoints que exponen
      direcciones (GET /deposit-address?asset=ETH|USDC, HU-06-04)
    - Cuando se emiten esas respuestas, y se consulta la superficie de retiros
      (GET /withdrawals, donde el flujo de retiro usa las claves derivadas)
    - Entonces en ninguna respuesta aparece un campo con la clave privada
      derivada: solo claves públicas y/o direcciones (RN-6)

    El "Y" del escenario (auditoría estática de logs/trazas) es white-box y se
    realiza en H8. El flujo de retiro con firma real (épica 08) emite sus
    respuestas por los endpoints de retiros, cuyos ATs propios (épica 08) las
    cubren; el valor de la clave es incognoscible black-box, por eso se verifica
    por nombre de campo (ver _claves_sospechosas).
    """
    respuestas = {
        "deposit-address ETH": usuario.api.get("/deposit-address", params={"asset": "ETH"}),
        "deposit-address USDC": usuario.api.get("/deposit-address", params={"asset": "USDC"}),
        "withdrawals": usuario.api.get("/withdrawals"),
    }
    for nombre, resp in respuestas.items():
        assert resp.status_code == 200, f"{nombre}: {resp.status_code} {resp.text[:300]}"
        hallazgos = _claves_sospechosas(resp.json())
        assert not hallazgos, f"{nombre} expone material de clave privada: {hallazgos}"


# ---------------------------------------------------------------------------------
# HU-06-03 — Asignación de dirección de depósito (parte observable black-box)
# ---------------------------------------------------------------------------------


@pytest.mark.at("AT-06-03-01")
def test_cuenta_nueva_recibe_direccion_eip55_exclusiva(usuario, usuario_b):
    """HU-06-03 Escenario 1: Asignación a una cuenta nueva.

    - Dado una cuenta recién creada (fixture: registro fresco; la asignación es
      eager al alta, RN-12)
    - Cuando se obtiene su dirección de depósito por la superficie pública de la
      asignación (GET /deposit-address, HU-06-04)
    - Entonces la dirección derivada tiene checksum EIP-55 válido (RN-8,
      recomputado con Keccak-256)
    - Y queda asociada exclusivamente a esa cuenta: la dirección de otra cuenta
      es distinta (RN-1/RN-5; un address_index repetido produciría la misma
      dirección, así que la unicidad observable cubre la unicidad del índice)

    El valor del address_index ("único y monótono") no se expone por el contrato
    público (derivationPath es opcional, HU-06-04 RN-6); se evalúa sobre el
    estado persistido en H8 (INV-EPICA-06-A).
    """
    # Cuando
    direccion_a = _direccion(usuario)["address"]

    # Entonces: formato 0x + 40 hex y checksum EIP-55 recomputado
    assert_direccion(direccion_a)

    # Y: exclusividad observable entre cuentas
    direccion_b = _direccion(usuario_b)["address"]
    assert_direccion(direccion_b)
    assert direccion_a != direccion_b, "dos cuentas comparten dirección de depósito (RN-5)"


@pytest.mark.at("AT-06-03-02")
def test_reobtener_la_direccion_no_asigna_una_nueva(usuario):
    """HU-06-03 Escenario 2 (idempotencia): Reasignación devuelve la misma dirección.

    - Dado una cuenta que ya tiene dirección asignada (primera obtención)
    - Cuando se solicita nuevamente la asignación/obtención de su dirección (la
      vía pública de la asignación es la consulta, fallback idempotente:
      HU-06-03 RN-12 / HU-06-04 RN-5)
    - Entonces se devuelve la misma dirección y no se asigna un índice nuevo
      (RN-4: un índice nuevo derivaría una dirección distinta, HU-06-02 RN-5,
      así que la estabilidad de la dirección observa la estabilidad del índice)
    """
    # Dado
    primera = assert_direccion(_direccion(usuario)["address"])

    # Cuando / Entonces
    for intento in range(3):
        repetida = _direccion(usuario)["address"]
        assert repetida == primera, (
            f"la re-obtención #{intento + 1} devolvió otra dirección: {repetida} != {primera} (RN-4)"
        )


@pytest.mark.at("AT-06-03-04")
def test_una_sola_direccion_para_eth_y_usdc(usuario):
    """HU-06-03 Escenario 4: Una dirección válida para ETH y USDC.

    - Dado una cuenta con dirección de depósito asignada
    - Cuando se consulta la dirección de depósito para ETH y para USDC
    - Entonces ambas consultas devuelven exactamente la misma dirección (RN-3:
      ETH nativo y USDC ERC-20 comparten la misma EOA)
    - Y la dirección corresponde a la red Sepolia: chainId "11155111" (string,
      HU-06-04 RN-8) en ambas respuestas
    """
    # Cuando
    cuerpo_eth = _direccion(usuario, "ETH")
    cuerpo_usdc = _direccion(usuario, "USDC")

    # Entonces
    assert cuerpo_eth["address"] == cuerpo_usdc["address"], (
        f"direcciones distintas por activo: ETH={cuerpo_eth['address']} USDC={cuerpo_usdc['address']} (RN-3)"
    )
    assert_direccion(cuerpo_eth["address"])

    # Y: red Sepolia en ambas respuestas
    assert cuerpo_eth["chainId"] == CHAIN_ID_SEPOLIA, cuerpo_eth
    assert cuerpo_usdc["chainId"] == CHAIN_ID_SEPOLIA, cuerpo_usdc


@pytest.mark.at("AT-06-03-05")
def test_asignaciones_concurrentes_no_colisionan(api):
    """HU-06-03 Escenario 5 (concurrencia): Asignaciones simultáneas sin colisión.

    - Dado N = 20 cuentas distintas que disparan la asignación de forma
      concurrente (la asignación es eager al alta, RN-12: registrar 20 cuentas
      en paralelo dispara 20 asignaciones "en el mismo ciclo")
    - Cuando el Sistema procesa las solicitudes
    - Entonces se producen 20 direcciones distintas, una por cuenta (RN-6: si la
      obtención del siguiente índice no fuera atómica, dos cuentas recibirían el
      mismo address_index y compartirían dirección — eso es lo observable)

    La cláusula "el conjunto de índices es exactamente {0..19}" exige estado
    limpio y leer el mapeo persistido: no es observable black-box (se verifica
    en H8 sobre el estado persistido, INV-EPICA-06-A). La ausencia de colisión
    —el núcleo de RN-6— sí lo es, y es lo que se verifica acá.
    """
    # Dado: 20 registros concurrentes (cada alta dispara su asignación eager)
    emails = [email_unico("at06-conc") for _ in range(20)]
    with ThreadPoolExecutor(max_workers=20) as pool:
        list(pool.map(lambda email: registrar(api, email=email), emails))

    # Cuando: se obtiene la dirección asignada a cada cuenta
    direcciones = []
    for email in emails:
        token = login(api, email)
        with api.con_token(token) as api_auth:
            resp = api_auth.get("/deposit-address", params={"asset": "ETH"})
            assert resp.status_code == 200, resp.text
            direcciones.append(assert_direccion(resp.json()["address"]))

    # Entonces: 20 direcciones distintas, una por cuenta
    assert len(set(direcciones)) == 20, (
        f"colisión de direcciones bajo asignación concurrente (RN-6): "
        f"{len(set(direcciones))} únicas de {len(direcciones)}"
    )


# ---------------------------------------------------------------------------------
# HU-06-04 — Consultar dirección de depósito
# ---------------------------------------------------------------------------------


@pytest.mark.at("AT-06-04-01")
def test_consulta_eth_devuelve_contrato_completo(usuario):
    """HU-06-04 Escenario 1: Consulta exitosa para ETH.

    - Dado un trader autenticado cuya cuenta tiene dirección asignada (eager al
      alta, HU-06-03 RN-12)
    - Cuando consulta GET /api/v1/deposit-address?asset=ETH
    - Entonces recibe HTTP 200 con address (checksum EIP-55 recomputado),
      asset = "ETH", network = "sepolia" y chainId = "11155111" como string
      (RN-6, RN-8)
    - Y la respuesta no contiene clave privada ni seed
    """
    # Cuando
    resp = usuario.api.get("/deposit-address", params={"asset": "ETH"})

    # Entonces
    assert resp.status_code == 200, resp.text
    cuerpo = resp.json()
    assert cuerpo["asset"] == "ETH", cuerpo
    assert_direccion(cuerpo["address"])
    assert cuerpo["network"] == "sepolia", cuerpo
    # chainId como string "11155111": la comparación falla si viniera como
    # entero JSON (RN-8 fija string para evitar la ambigüedad de tipo)
    assert cuerpo["chainId"] == CHAIN_ID_SEPOLIA, cuerpo
    assert isinstance(cuerpo["chainId"], str), f"chainId debe ser string (RN-8): {cuerpo['chainId']!r}"

    # Y: sin material secreto en la respuesta
    assert not _claves_sospechosas(cuerpo), cuerpo


@pytest.mark.at("AT-06-04-02")
def test_consulta_usdc_devuelve_la_misma_direccion_y_token_address(usuario):
    """HU-06-04 Escenario 2: Misma dirección para USDC.

    - Dado el mismo trader del escenario 1 (misma cuenta autenticada)
    - Cuando consulta su dirección de depósito para el activo USDC
    - Entonces recibe la misma address que para ETH, con asset = "USDC" y
      chainId = "11155111" string (RN-3, RN-8)
    - Y (RN-6; épica 09 HU-09-01 RN-10) la respuesta para USDC incluye además
      tokenAddress: la dirección del contrato USDC-mock del entorno, con
      checksum EIP-55
    """
    # Dado: la dirección para ETH de la misma cuenta
    direccion_eth = _direccion(usuario, "ETH")["address"]

    # Cuando
    resp = usuario.api.get("/deposit-address", params={"asset": "USDC"})

    # Entonces
    assert resp.status_code == 200, resp.text
    cuerpo = resp.json()
    assert cuerpo["asset"] == "USDC", cuerpo
    assert cuerpo["address"] == direccion_eth, (
        f"la dirección para USDC difiere de la de ETH: {cuerpo['address']} != {direccion_eth} (RN-3)"
    )
    assert cuerpo["chainId"] == CHAIN_ID_SEPOLIA, cuerpo

    # Y: tokenAddress del USDC-mock, obligatorio para asset=USDC (RN-6)
    token_address = assert_direccion(cuerpo["tokenAddress"], campo="tokenAddress")
    usdc_del_entorno = os.environ.get("EVAL_USDC_ADDRESS", "").strip()
    if usdc_del_entorno:
        # el contrato USDC-mock es "único y constante por entorno"
        # (00-fundaciones/activos-y-par-de-trading.md §2.2)
        assert token_address == a_checksum(usdc_del_entorno), (
            f"tokenAddress {token_address} no es el USDC-mock del entorno ({usdc_del_entorno})"
        )


@pytest.mark.at("AT-06-04-03")
def test_consulta_sin_credencial_es_unauthenticated(api):
    """HU-06-04 Escenario 3 (error): Falta de autenticación.

    - Dado una solicitud sin credencial válida (ausente, y también inválida)
    - Cuando se consulta la dirección de depósito
    - Entonces se rechaza con UNAUTHENTICATED (HTTP 401) (RN-1; la autenticación
      es el primer paso de la precedencia RN-9)
    - Y no se revela ninguna dirección
    """
    # Cuando: sin header Authorization (el fixture `api` no lleva token)
    resp = api.get("/deposit-address", params={"asset": "ETH"})

    # Entonces: envelope de error, code y status 401 del catálogo
    assert_error(resp, "UNAUTHENTICATED")
    # Y: en el cuerpo del error no viaja ninguna dirección Ethereum
    assert not RE_DIRECCION_EN_TEXTO.search(resp.text), resp.text

    # Cuando: token inválido (credencial presente pero no válida, RN-1)
    with api.con_token("token-invalido-at-06-04-03") as api_invalida:
        resp = api_invalida.get("/deposit-address", params={"asset": "ETH"})
    assert_error(resp, "UNAUTHENTICATED")
    assert not RE_DIRECCION_EN_TEXTO.search(resp.text), resp.text


@pytest.mark.at("AT-06-04-04")
def test_selector_de_cuenta_inyectado_se_ignora(usuario, usuario_b):
    """HU-06-04 Escenario 4 (autorización / aislamiento): No se accede a la
    dirección de otra cuenta.

    - Dado dos traders A y B, cada uno con su dirección asignada, y el token de A
    - Cuando A consulta ?asset=ETH e intenta inyectar el accountId de B por
      query string
    - Entonces el selector inyectado se ignora y la respuesta (HTTP 200)
      contiene la dirección de A, nunca la de B (RN-2: la identidad de la cuenta
      se toma exclusivamente del token; el contrato no expone selector de cuenta)
    """
    # Dado: A y B con direcciones asignadas (y distintas, HU-06-03 RN-5)
    direccion_a = _direccion(usuario)["address"]
    direccion_b = _direccion(usuario_b)["address"]
    assert direccion_a != direccion_b, "precondición: A y B deben tener direcciones distintas"

    # Cuando: A inyecta el accountId de B como parámetro de query
    resp = usuario.api.get(
        "/deposit-address",
        params={"asset": "ETH", "accountId": usuario_b.account_id},
    )

    # Entonces: 200 con la dirección de A; la de B no se revela en ningún caso
    assert resp.status_code == 200, resp.text
    cuerpo = resp.json()
    assert cuerpo["address"] == direccion_a, (
        f"el selector inyectado no se ignoró: se esperaba la dirección de A ({direccion_a}), "
        f"llegó {cuerpo['address']} (RN-2)"
    )
    assert direccion_b not in resp.text, "la dirección de B se filtró en la respuesta (RN-2)"


@pytest.mark.at("AT-06-04-05")
def test_activo_no_soportado_es_validation_error(usuario):
    """HU-06-04 Escenario 5 (error / validación): Activo no soportado.

    - Dado un trader autenticado (token válido: lo único inválido es el activo,
      precedencia RN-9)
    - Cuando consulta la dirección para un activo fuera de {ETH, USDC} ("BTC")
    - Entonces se rechaza con VALIDATION_ERROR (HTTP 422) y details.issues
      indicando el activo inválido (RN-3, RN-9)
    """
    # Cuando
    resp = usuario.api.get("/deposit-address", params={"asset": "BTC"})

    # Entonces
    err = assert_error(resp, "VALIDATION_ERROR")
    assert "issues" in (err.get("details") or {}), err


@pytest.mark.at("AT-06-04-06")
def test_chain_id_distinto_de_sepolia_es_chain_id_mismatch(usuario):
    """HU-06-04 Escenario 6 (error / red): chainId distinto de Sepolia.

    - Dado un trader autenticado (token y activo válidos: la única violación es
      la red, precedencia RN-9: VALIDATION_ERROR se evalúa antes que
      CHAIN_ID_MISMATCH)
    - Cuando consulta su dirección especificando chainId = 1
    - Entonces se rechaza con CHAIN_ID_MISMATCH (HTTP 422) y
      details.expected = "11155111", details.got = "1", ambos serializados como
      string (RN-4, RN-8; modelo-de-errores §3.5)
    """
    # Cuando
    resp = usuario.api.get("/deposit-address", params={"asset": "ETH", "chainId": "1"})

    # Entonces
    err = assert_error(resp, "CHAIN_ID_MISMATCH")
    details = err.get("details") or {}
    assert details.get("expected") == CHAIN_ID_SEPOLIA, details
    assert details.get("got") == "1", details


@pytest.mark.at("AT-06-04-07")
def test_primera_consulta_devuelve_200_y_direccion_estable(api):
    """HU-06-04 Escenario 7 (borde / fallback): Asignación on-demand en la
    primera consulta.

    - Dado un trader recién registrado que nunca consultó su dirección
    - Cuando consulta por primera vez su dirección de depósito
    - Entonces recibe la dirección resultante con HTTP 200 exacto (no 201,
      aunque la consulta hubiera disparado la asignación-fallback; RN-5 y
      contrato de la épica 09: "no se distingue por status")
    - Y una segunda consulta devuelve la misma dirección

    Nota: el "Dado" literal del escenario (cuenta sin dirección asignada) no es
    forzable black-box porque la asignación primaria es eager al alta (HU-06-03
    RN-12); el contrato observable exigido (200 + misma dirección en la primera
    consulta de la vida de la cuenta) es idéntico por ambos caminos y, si el SUT
    implementa la asignación de forma lazy, este flujo ejercita el fallback real.
    """
    # Dado: cuenta fresca sin consultas previas de su dirección
    usuario_nuevo = crear_usuario(api, prefijo="at06-fallback")

    # Cuando: primera consulta de la vida de la cuenta
    resp = usuario_nuevo.api.get("/deposit-address", params={"asset": "ETH"})

    # Entonces: 200 exacto (no 201) con dirección válida
    assert resp.status_code == 200, (
        f"se esperaba 200 (no 201 ni otro status), llegó {resp.status_code}: {resp.text[:300]}"
    )
    primera = assert_direccion(resp.json()["address"])

    # Y: la segunda consulta devuelve la misma dirección
    segunda = _direccion(usuario_nuevo)["address"]
    assert segunda == primera, f"la segunda consulta cambió la dirección: {segunda} != {primera}"


@pytest.mark.at("AT-06-04-08")
def test_consultas_repetidas_devuelven_siempre_la_misma_direccion(usuario):
    """HU-06-04 Escenario 8 (idempotencia / consistencia): Consultas repetidas.

    - Dado un trader autenticado con dirección ya asignada
    - Cuando consulta su dirección varias veces, para ETH y para USDC
    - Entonces todas las respuestas devuelven exactamente la misma dirección
    - Y la consulta no altera el address_index asignado (RN-7: un índice mutado
      sería observable como cambio de dirección, HU-06-02 RN-5)
    """
    # Dado: primera obtención como referencia
    referencia = assert_direccion(_direccion(usuario, "ETH")["address"])

    # Cuando / Entonces: consultas repetidas alternando activos
    for asset in ("USDC", "ETH", "USDC", "ETH"):
        obtenida = _direccion(usuario, asset)["address"]
        assert obtenida == referencia, (
            f"consulta repetida (asset={asset}) devolvió otra dirección: {obtenida} != {referencia} (RN-7)"
        )


@pytest.mark.at("AT-06-04-09")
def test_primeras_consultas_concurrentes_devuelven_una_sola_direccion(api):
    """HU-06-04 Escenario 9 (concurrencia del fallback): Primera consulta
    concurrente.

    - Dado un trader recién registrado, sin consultas previas de su dirección
      (si el SUT asigna de forma lazy, ambas consultas disparan el fallback RN-5)
    - Cuando dos consultas de su dirección llegan concurrentemente
    - Entonces ambas respuestas son HTTP 200 con la misma dirección: se asignó
      exactamente un address_index a la cuenta (dos índices distintos derivarían
      direcciones distintas, HU-06-02 RN-5; HU-06-03 RN-6/RN-12)
    """
    # Dado
    usuario_nuevo = crear_usuario(api, prefijo="at06-conc-fb")

    def consultar(_):
        return usuario_nuevo.api.get("/deposit-address", params={"asset": "ETH"})

    # Cuando: dos consultas concurrentes (las primeras de la vida de la cuenta)
    with ThreadPoolExecutor(max_workers=2) as pool:
        respuestas = list(pool.map(consultar, range(2)))

    # Entonces: ambas 200 y con la misma dirección
    direcciones = set()
    for resp in respuestas:
        assert resp.status_code == 200, resp.text
        direcciones.add(assert_direccion(resp.json()["address"]))
    assert len(direcciones) == 1, (
        f"las consultas concurrentes devolvieron direcciones distintas (dos índices asignados): {direcciones}"
    )


# ---------------------------------------------------------------------------------
# Persistencia del provisioning tras reinicio (HU-06-01/02/03, INV-8)
# ---------------------------------------------------------------------------------


@pytest.mark.at("AT-06-01-07", "AT-06-01-08", "AT-06-02-06", "AT-06-03-06")
def test_direcciones_asignadas_son_identicas_tras_un_reinicio(api, usuario, usuario_b):
    """HU-06-01 Esc. 7 y 8; HU-06-02 Esc. 6; HU-06-03 Esc. 6 (persistencia, INV-8).

    - Dado un seed ya provisionado y cuentas con `address_index` y dirección
      asignados (dos cuentas, para observar también la no-colisión de índices)
    - Cuando el sistema se reinicia (lo que reejecuta su proceso de provisioning
      y vuelve a derivar las direcciones de esos índices)
    - Entonces el seed se recupera del almacenamiento en vez de regenerarse, no
      se sobrescribe, y cada cuenta conserva su índice: las direcciones
      reconstruidas son **idénticas** a las previas (HU-06-01 RN-4/RN-8,
      HU-06-02 RN-5, HU-06-03 RN-7, INV-8)

    **Los cuatro ATs se verifican con la misma evidencia y fallan o pasan juntos**
    (el caso que HELPERS.md admite para agrupar ATs en un test): la única
    proyección black-box del seed, de la
    derivación y del mapeo cuenta→índice es la dirección emitida por
    `GET /deposit-address`. Un seed regenerado, una derivación no reproducible o
    un mapeo perdido cambian esa dirección; ninguno de los tres es distinguible
    de los otros desde afuera. El reinicio es también el único disparador
    black-box de "reejecutar el provisioning" (AT-06-01-08): la spec no define
    endpoint alguno para invocarlo (HU-06-01 RN-4 lo pone en el arranque).
    """
    comando_reinicio()  # precondición explícita antes de construir el "Dado"

    # Dado: dos cuentas con dirección asignada (ETH y USDC comparten la dirección,
    # HU-06-03 RN-3: se piden ambas para cubrir las dos rutas de consulta)
    previas = {
        (etiqueta, asset): _direccion(quien, asset)["address"]
        for etiqueta, quien in (("a", usuario), ("b", usuario_b))
        for asset in ("ETH", "USDC")
    }
    assert previas[("a", "ETH")] != previas[("b", "ETH")], (
        "dos cuentas distintas comparten dirección: los índices colisionaron (HU-06-03 RN-6)"
    )

    # Cuando
    reiniciar_sut(api)
    relogin(usuario)
    relogin(usuario_b)

    # Entonces: dirección idéntica, cuenta por cuenta y activo por activo
    for (etiqueta, asset), direccion_previa in previas.items():
        actual = _direccion(usuario if etiqueta == "a" else usuario_b, asset)["address"]
        assert actual == direccion_previa, (
            f"la dirección de la cuenta {etiqueta} ({asset}) cambió tras el reinicio: "
            f"{direccion_previa} → {actual} (seed regenerado, derivación no reproducible "
            "o mapeo cuenta→índice perdido; INV-8)"
        )
