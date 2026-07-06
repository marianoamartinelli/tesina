"""Smoke tests del propio harness (no requieren SUT ni entorno on-chain).

Validan que los helpers, el catálogo y el plugin de reporte funcionan antes de
escribir/correr los tests por épica. Deben pasar siempre:

    cd evaluacion/suite-at && ../../.venv/bin/python -m pytest test_smoke.py
"""

import pytest

import catalogo
from helpers import errores, montos, reporte
from helpers.cuentas import PASSWORD_DEFECTO, email_unico
from helpers.eip55 import a_checksum, es_direccion_valida, romper_checksum
from helpers.espera import esperar_hasta

# ------------------------------------------------------------------------------
# helpers/montos.py
# ------------------------------------------------------------------------------


class TestMontos:
    def test_montos_validos(self):
        for valor in ["0", "1", "1500000000", "100000000000000", str(10**30)]:
            assert montos.es_monto_valido(valor), valor

    def test_montos_invalidos(self):
        # casos inválidos de la spec (convenciones-monetarias §5)
        for valor in ["1.5", "1,500", "1e9", "-5", "01", "+1", "", " 1", "1 "]:
            assert not montos.es_monto_valido(valor), repr(valor)

    def test_numero_json_no_es_monto(self):
        # un número JSON parseado (int/float/bool de Python) no es serialización válida
        for valor in [1500000000, 1.5, 0, True, None]:
            assert not montos.es_monto_valido(valor), repr(valor)

    def test_assert_monto_devuelve_int(self):
        assert montos.assert_monto("2000500000", "priceMin") == 2000500000

    def test_assert_monto_falla_con_numero_json(self):
        with pytest.raises(AssertionError):
            montos.assert_monto(2000500000, "priceMin")

    def test_a_str_rechaza_negativos_y_bool(self):
        with pytest.raises(ValueError):
            montos.a_str(-1)
        with pytest.raises(ValueError):
            montos.a_str(True)

    def test_quote_min_ejemplo_de_la_spec(self):
        # activos-y-par §3.2: 1 ETH @ 2000.50 USDC/ETH ⇒ 2 000 500 000 USDC-min
        assert montos.quote_min(10**18, 2_000_500_000) == 2_000_500_000

    def test_quote_min_trunca_con_floor(self):
        # 0.0001 ETH @ 2000.00 ⇒ 0.2 USDC = 200000 USDC-min (exacto)
        assert montos.quote_min(10**14, 2_000_000_000) == 200_000
        # caso con residuo: 1 wei @ 2000.50 ⇒ floor(2000500000 / 10^18) = 0
        assert montos.quote_min(1, 2_000_500_000) == 0

    def test_producto_intermedio_supera_64_bits(self):
        # q_wei × price_min ~ 10^30 debe ser exacto (int de Python, sin overflow)
        q_wei, price_min = 10**18, 10**12
        assert q_wei * price_min == 10**30
        assert montos.quote_min(q_wei, price_min) == 10**12

    def test_fee_redondea_con_ceil(self):
        # convenciones-monetarias §3.3: fee = ceil(monto × bps / 10000)
        assert montos.fee(10_000, montos.FEE_BPS_MAKER) == 10      # exacto
        assert montos.fee(10_001, montos.FEE_BPS_MAKER) == 11      # ceil
        assert montos.fee(1, montos.FEE_BPS_TAKER) == 1            # nunca 0 si monto > 0
        assert montos.fee(0, montos.FEE_BPS_TAKER) == 0

    def test_fee_nunca_supera_lo_recibido(self):
        for monto in [1, 999, 10**18]:
            assert 0 <= montos.fee_taker(monto) <= monto

    def test_tick_y_lot(self):
        assert montos.es_multiplo_de_tick(2_000_500_000)
        assert not montos.es_multiplo_de_tick(2_000_005_000)  # 3 decimales
        assert not montos.es_multiplo_de_tick(0)
        assert montos.es_multiplo_de_lot(10**14)
        assert not montos.es_multiplo_de_lot(5 * 10**13)      # 5 decimales
        assert not montos.es_multiplo_de_lot(0)


# ------------------------------------------------------------------------------
# catalogo.py + catalogo-at.csv
# ------------------------------------------------------------------------------


class TestCatalogo:
    def test_la_spec_define_693_ats(self):
        filas = catalogo.parsear_spec()
        assert len(filas) == 693

    def test_reparto_por_tipo(self):
        filas = catalogo.parsear_spec()
        por_tipo = {}
        for fila in filas:
            por_tipo[fila["tipo"]] = por_tipo.get(fila["tipo"], 0) + 1
        assert por_tipo == {"backend": 521, "web": 78, "mobile": 94}

    def test_at_ids_unicos_y_bien_formados(self):
        filas = catalogo.parsear_spec()
        ids = [f["at_id"] for f in filas]
        assert len(set(ids)) == len(ids)
        for at_id in ids:
            assert reporte.RE_AT_ID.fullmatch(at_id), at_id

    def test_csv_generado_esta_al_dia(self):
        # el CSV commiteado debe coincidir con lo que produce la spec congelada
        en_disco = reporte.cargar_catalogo()
        generado = {f["at_id"]: f for f in catalogo.parsear_spec()}
        assert en_disco == generado, (
            "catalogo-at.csv desactualizado: regenerar con `python catalogo.py`"
        )

    def test_titulos_no_vacios(self):
        for fila in catalogo.parsear_spec():
            assert fila["titulo_escenario"].startswith("Escenario"), fila


# ------------------------------------------------------------------------------
# helpers/errores.py
# ------------------------------------------------------------------------------


class _RespuestaFalsa:
    def __init__(self, status_code: int, cuerpo: dict):
        self.status_code = status_code
        self._cuerpo = cuerpo

    def json(self):
        return self._cuerpo


ENVELOPE_OK = {
    "error": {
        "code": "INSUFFICIENT_FUNDS",
        "message": "Saldo disponible insuficiente para la operación.",
        "details": {"asset": "USDC", "required": "10000000", "available": "5000000"},
    }
}


class TestErrores:
    def test_assert_error_acepta_envelope_correcto(self):
        err = errores.assert_error(_RespuestaFalsa(422, ENVELOPE_OK), "INSUFFICIENT_FUNDS")
        assert err["details"]["asset"] == "USDC"

    def test_assert_error_usa_el_status_del_catalogo(self):
        with pytest.raises(AssertionError, match="status esperado 422"):
            errores.assert_error(_RespuestaFalsa(400, ENVELOPE_OK), "INSUFFICIENT_FUNDS")

    def test_assert_error_rechaza_code_distinto(self):
        with pytest.raises(AssertionError, match="code esperado"):
            errores.assert_error(_RespuestaFalsa(422, ENVELOPE_OK), "VALIDATION_ERROR")

    def test_assert_error_rechaza_typo_en_el_test(self):
        # protege al autor del test: código fuera de catálogo = error del test
        with pytest.raises(AssertionError, match="fuera de catálogo"):
            errores.assert_error(_RespuestaFalsa(422, ENVELOPE_OK), "INSUFICIENT_FUNDS")

    def test_envelope_sin_message_es_invalido(self):
        cuerpo = {"error": {"code": "NOT_FOUND"}}
        with pytest.raises(AssertionError, match="message"):
            errores.validar_envelope(cuerpo)

    def test_envelope_plano_es_invalido(self):
        with pytest.raises(AssertionError, match="'error'"):
            errores.validar_envelope({"code": "NOT_FOUND", "message": "x"})

    def test_assert_error_ws(self):
        err = errores.assert_error_ws(
            {"error": {"code": "UNAUTHENTICATED", "message": "token requerido"}},
            "UNAUTHENTICATED",
        )
        assert err["code"] == "UNAUTHENTICATED"

    def test_montos_en_details(self):
        errores.assert_montos_en_details(
            ENVELOPE_OK["error"]["details"], "required", "available"
        )
        with pytest.raises(AssertionError, match="string entero"):
            errores.assert_montos_en_details({"required": 10000000}, "required")

    def test_catalogo_de_codes_coincide_con_la_spec(self):
        # muestreo de mapeos HTTP fijados por HU-09-05 RN-6
        assert errores.CATALOGO_CODES["UNAUTHENTICATED"] == 401
        assert errores.CATALOGO_CODES["VALIDATION_ERROR"] == 422
        assert errores.CATALOGO_CODES["ORDER_NOT_FOUND"] == 404
        assert errores.CATALOGO_CODES["DUPLICATE_CLIENT_ORDER_ID"] == 409
        assert errores.CATALOGO_CODES["RATE_LIMITED"] == 429
        assert errores.CATALOGO_CODES["BROADCAST_FAILED"] == 502
        assert len(errores.CATALOGO_CODES) == 33


# ------------------------------------------------------------------------------
# helpers/eip55.py
# ------------------------------------------------------------------------------


class TestEip55:
    # vectores canónicos de HU-06-02 (§ vectores de checksum EIP-55)
    VECTORES = [
        ("5aaeb6053f3e94c9b9a09f33669435e7ef1beaed", "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"),
        ("fb6916095ca1df60bb79ce92ce3ea74c37c5d359", "0xfB6916095ca1df60bB79Ce92cE3Ea74c37c5d359"),
        ("dbf03b407c01e7cd3cbea99509d93f8dddc8c6fb", "0xdbF03B407c01E7cD3CBea99509d93f8DDDC8C6FB"),
        ("d1220a0cf47c7b9be7a2e6ba89f429762e7b9adb", "0xD1220A0cf47c7B9Be7A2E6BA89F429762e7b9aDb"),
    ]

    def test_vectores_canonicos_de_la_spec(self):
        for crudo, esperado in self.VECTORES:
            assert a_checksum("0x" + crudo) == esperado

    def test_direccion_de_anvil_cuenta_0(self):
        # HU-06-02: address_index 0 del mnemonic canónico
        assert es_direccion_valida("0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266")

    def test_minusculas_no_pasan_validacion_estricta(self):
        assert not es_direccion_valida("0x5aaeb6053f3e94c9b9a09f33669435e7ef1beaed")

    def test_romper_checksum_produce_invalida(self):
        rota = romper_checksum("0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed")
        assert not es_direccion_valida(rota)
        assert rota != "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"


# ------------------------------------------------------------------------------
# helpers/espera.py
# ------------------------------------------------------------------------------


class TestEspera:
    def test_devuelve_el_valor_de_la_condicion(self):
        assert esperar_hasta(lambda: {"listo": True}, timeout=1) == {"listo": True}

    def test_reintenta_hasta_cumplirse(self):
        intentos = []

        def condicion():
            intentos.append(1)
            return len(intentos) >= 3

        assert esperar_hasta(condicion, timeout=5, intervalo=0.01) is True
        assert len(intentos) == 3

    def test_timeout_lanza_error_con_mensaje(self):
        with pytest.raises(TimeoutError, match="nunca pasa"):
            esperar_hasta(lambda: False, timeout=0.05, intervalo=0.01, mensaje="nunca pasa")


# ------------------------------------------------------------------------------
# helpers/cuentas.py (sin SUT: sólo generación de datos)
# ------------------------------------------------------------------------------


class TestCuentas:
    def test_emails_unicos(self):
        assert email_unico() != email_unico()
        assert email_unico("x").endswith("@example.com")

    def test_password_defecto_cumple_politica(self):
        # HU-01-01 RN-3: entre 8 y 128 caracteres
        assert 8 <= len(PASSWORD_DEFECTO) <= 128


# ------------------------------------------------------------------------------
# helpers/reporte.py + no-automatizables.yaml (lógica del plugin de reporte)
# ------------------------------------------------------------------------------


class TestReporte:
    def test_no_automatizables_referencian_ats_backend_del_catalogo(self):
        cat = reporte.cargar_catalogo()
        for at_id in reporte.cargar_no_automatizables():
            assert at_id in cat, f"{at_id} no existe en el catálogo"
            assert cat[at_id]["tipo"] == "backend", f"{at_id} no es backend"

    def test_validacion_detecta_at_inexistente_y_tipo_no_backend(self):
        cat = reporte.cargar_catalogo()
        problemas = reporte.validar_ats_declarados(
            {
                "test_a": ["AT-99-99-99"],          # inexistente
                "test_b": ["AT-10-01-01"],           # web (épica 10)
                "test_c": ["esto-no-es-un-at"],      # formato inválido
            },
            cat,
            {},
        )
        assert len(problemas) == 3

    def test_validacion_rechaza_at_testeado_y_declarado_no_automatizable(self):
        cat = reporte.cargar_catalogo()
        problemas = reporte.validar_ats_declarados(
            {"test_a": ["AT-06-01-01"]}, cat, {"AT-06-01-01": "motivo"}
        )
        assert any("no-automatizables" in p for p in problemas)

    def test_agregacion_y_csv(self, tmp_path):
        cat = reporte.cargar_catalogo()
        no_autom = reporte.cargar_no_automatizables()
        ats_por_test = {
            "tests/x.py::test_pasa": ["AT-09-01-01"],
            "tests/x.py::test_falla": ["AT-09-01-02"],
            "tests/x.py::test_skip": ["AT-09-01-03"],
            "tests/x.py::test_mixto_falla": ["AT-09-01-02", "AT-09-01-04"],
        }
        resultados_tests = {
            "tests/x.py::test_pasa": {"outcome": "passed", "duracion": 0.5},
            "tests/x.py::test_falla": {"outcome": "failed", "duracion": 0.2},
            "tests/x.py::test_skip": {"outcome": "skipped", "duracion": 0.0},
            "tests/x.py::test_mixto_falla": {"outcome": "failed", "duracion": 0.1},
        }
        filas = reporte.agregar_resultados(cat, no_autom, resultados_tests, ats_por_test)

        # una fila por cada AT backend del catálogo
        assert len(filas) == 521
        por_at = {f["at_id"]: f for f in filas}
        assert por_at["AT-09-01-01"]["resultado"] == "pasa"
        assert por_at["AT-09-01-02"]["resultado"] == "falla"
        assert por_at["AT-09-01-03"]["resultado"] == "skip"
        assert por_at["AT-09-01-04"]["resultado"] == "falla"  # su único test falló
        assert por_at["AT-06-01-01"]["resultado"] == "no_automatizado"
        assert por_at["AT-06-01-01"]["detalle"]  # con motivo
        assert por_at["AT-01-01-01"]["resultado"] == "sin_test"
        # los ATs de épicas 10/11 no aparecen
        assert not any(f["at_id"].startswith(("AT-10", "AT-11")) for f in filas)

        # el CSV se escribe y se relee consistente
        destino = tmp_path / "resultados-at.csv"
        reporte.escribir_resultados(filas, destino)
        import csv

        with destino.open(encoding="utf-8") as f:
            releidas = list(csv.DictReader(f))
        assert len(releidas) == 521
        assert releidas[0].keys() == set(reporte.COLUMNAS_RESULTADOS)

        conteo = reporte.resumen(filas)
        assert conteo["pasa"] == 1
        assert conteo["falla"] == 2
        assert conteo["skip"] == 1
        assert conteo["no_automatizado"] == len(reporte.cargar_no_automatizables())
        assert sum(conteo.values()) == 521

    def test_ats_de_un_marker_multiple(self):
        # la agregación soporta un test que cubre varios ATs y varios tests por AT
        cat = reporte.cargar_catalogo()
        filas = reporte.agregar_resultados(
            cat,
            {},
            {
                "t1": {"outcome": "passed", "duracion": 0.1},
                "t2": {"outcome": "passed", "duracion": 0.2},
            },
            {"t1": ["AT-09-05-01"], "t2": ["AT-09-05-01"]},
        )
        fila = next(f for f in filas if f["at_id"] == "AT-09-05-01")
        assert fila["resultado"] == "pasa"
        assert fila["test"] == "t1;t2"
        assert fila["duracion_segundos"] == "0.300"
