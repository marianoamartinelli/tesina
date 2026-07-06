"""Tests de sanidad del índice BM25 sobre el corpus real congelado (H3).

Correr desde pipeline/comun/rag/:  python3 -m pytest test_indice.py -q
"""

from pathlib import Path

import pytest

from indice import IndiceCorpus, _tokenizar

CORPUS = Path(__file__).resolve().parents[3] / "corpus" / "documentos"


@pytest.fixture(scope="module")
def idx() -> IndiceCorpus:
    return IndiceCorpus.desde_directorio(CORPUS)


def test_corpus_completo(idx):
    docs = {c.documento for c in idx._chunks}
    assert docs == {
        "bip-0032.mediawiki", "bip-0039.mediawiki", "bip-0039-wordlist-english.txt",
        "bip-0044.mediawiki", "eip-155.md", "erc-20.md", "erc-55.md", "erc-681.md",
        "ethereum-json-rpc.md",
    }


def test_determinismo(idx):
    q = "hardened derivation path child key"
    r1 = idx.consultar(q)
    idx2 = IndiceCorpus.desde_directorio(CORPUS)
    r2 = idx2.consultar(q)
    assert r1 == r2


def test_relevancia_basica(idx):
    casos = {
        "mnemonic wordlist checksum PBKDF2": "bip-0039",
        "hardened child key derivation CKDpriv": "bip-0032.mediawiki",
        "purpose coin_type account change address_index": "bip-0044.mediawiki",
        "replay attack chain id signing v value": "eip-155.md",
        "transfer event balanceOf allowance": "erc-20.md",
        "mixed-case checksum address encoding keccak": "erc-55.md",
        "payment request URI QR ethereum:": "erc-681.md",
        "eth_getLogs logIndex transaction receipt": "ethereum-json-rpc.md",
    }
    for consulta, doc_esperado in casos.items():
        top = idx.consultar(consulta, k=3)
        docs = [p.documento for p in top]
        assert any(d.startswith(doc_esperado) for d in docs), (
            f"consulta {consulta!r}: esperaba {doc_esperado} en top-3, obtuve {docs}"
        )


def test_tokenizador_conserva_terminos_tecnicos():
    toks = _tokenizar("m/44'/60'/0'/0/0 eth_getLogs EIP-155 chainId=11155111")
    assert "m/44'/60'/0'/0/0" in toks
    assert "eth_getlogs" in toks
    assert "eip-155" in toks
    assert "11155111" in toks


def test_sin_resultados(idx):
    assert idx.consultar("zzzz inexistente qqqq") == []
