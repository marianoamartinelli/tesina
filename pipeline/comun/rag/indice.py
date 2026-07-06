"""Índice léxico determinista (BM25) sobre el corpus congelado de H3.

Sin dependencias externas (ADR-005, Decisión 2): misma consulta => mismos pasajes,
en cualquier máquina, reconstruible bit a bit desde `corpus/documentos/`.

Uso:
    from indice import IndiceCorpus
    idx = IndiceCorpus.desde_directorio("../corpus/documentos")
    for p in idx.consultar("derivation path hardened key", k=6):
        print(p.documento, p.seccion, p.puntaje)
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

# Parámetros BM25 fijados por ADR-005; no se ajustan por celda ni por corrida.
K1 = 1.5
B = 0.75
K_DEFAULT = 6

# Chunks: se corta por encabezado de sección (Markdown `#`/`##`/... o MediaWiki
# `==...==`). Secciones muy largas se subdividen en ventanas de este tamaño en
# tokens, sin solapamiento (determinista).
MAX_TOKENS_CHUNK = 400

_RE_ENCABEZADO = re.compile(r"^(#{1,6}\s+.+|={2,6}[^=].*?={2,6}\s*)$")
_RE_TOKEN = re.compile(r"[a-z0-9_/'\-]+")


def _tokenizar(texto: str) -> list[str]:
    """Tokenización determinista: NFKD, minúsculas, alfanuméricos y separadores
    técnicos habituales en los estándares (guiones, barras de derivation paths)."""
    texto = unicodedata.normalize("NFKD", texto).lower()
    return _RE_TOKEN.findall(texto)


@dataclass(frozen=True)
class Pasaje:
    documento: str  # nombre de archivo del corpus
    seccion: str    # encabezado de la sección a la que pertenece
    texto: str
    puntaje: float


@dataclass(frozen=True)
class _Chunk:
    documento: str
    seccion: str
    texto: str
    tokens: tuple[str, ...]


def _chunkear(nombre: str, contenido: str) -> list[_Chunk]:
    chunks: list[_Chunk] = []
    seccion = "(inicio)"
    buffer: list[str] = []

    def cerrar() -> None:
        texto = "\n".join(buffer).strip()
        if not texto:
            return
        tokens = _tokenizar(texto)
        if not tokens:
            return
        # Subdividir secciones largas en ventanas fijas por líneas, acumulando
        # hasta MAX_TOKENS_CHUNK tokens por ventana.
        lineas = texto.split("\n")
        ventana: list[str] = []
        n_tokens = 0
        for linea in lineas:
            t = len(_tokenizar(linea))
            if ventana and n_tokens + t > MAX_TOKENS_CHUNK:
                _emitir(ventana)
                ventana, n_tokens = [], 0
            ventana.append(linea)
            n_tokens += t
        if ventana:
            _emitir(ventana)

    def _emitir(lineas: list[str]) -> None:
        texto = "\n".join(lineas).strip()
        toks = tuple(_tokenizar(texto))
        if toks:
            chunks.append(_Chunk(nombre, seccion, texto, toks))

    for linea in contenido.split("\n"):
        if _RE_ENCABEZADO.match(linea.strip()):
            cerrar()
            buffer = []
            seccion = linea.strip().strip("#= ").strip()
            continue
        buffer.append(linea)
    cerrar()
    return chunks


class IndiceCorpus:
    def __init__(self, chunks: list[_Chunk]):
        if not chunks:
            raise ValueError("corpus vacío: no hay chunks para indexar")
        self._chunks = chunks
        self._n = len(chunks)
        self._long_prom = sum(len(c.tokens) for c in chunks) / self._n
        # document frequency por término
        self._df: dict[str, int] = {}
        self._tf: list[dict[str, int]] = []
        for c in chunks:
            tf: dict[str, int] = {}
            for t in c.tokens:
                tf[t] = tf.get(t, 0) + 1
            self._tf.append(tf)
            for t in tf:
                self._df[t] = self._df.get(t, 0) + 1

    @classmethod
    def desde_directorio(cls, ruta: str | Path) -> "IndiceCorpus":
        ruta = Path(ruta)
        chunks: list[_Chunk] = []
        # sorted(): orden de indexado independiente del filesystem
        for archivo in sorted(ruta.iterdir()):
            if archivo.is_file():
                chunks.extend(_chunkear(archivo.name, archivo.read_text(encoding="utf-8")))
        return cls(chunks)

    def _idf(self, termino: str) -> float:
        df = self._df.get(termino, 0)
        if df == 0:
            return 0.0
        return math.log(1 + (self._n - df + 0.5) / (df + 0.5))

    def consultar(self, consulta: str, k: int = K_DEFAULT) -> list[Pasaje]:
        q = _tokenizar(consulta)
        puntajes: list[tuple[float, int]] = []
        for i, c in enumerate(self._chunks):
            tf = self._tf[i]
            s = 0.0
            for t in q:
                f = tf.get(t, 0)
                if f == 0:
                    continue
                denom = f + K1 * (1 - B + B * len(c.tokens) / self._long_prom)
                s += self._idf(t) * f * (K1 + 1) / denom
            if s > 0:
                puntajes.append((s, i))
        # Desempate determinista: puntaje desc, luego (documento, seccion, texto) asc.
        puntajes.sort(key=lambda p: (-p[0], self._chunks[p[1]].documento,
                                     self._chunks[p[1]].seccion, self._chunks[p[1]].texto))
        resultado = []
        for s, i in puntajes[:k]:
            c = self._chunks[i]
            resultado.append(Pasaje(c.documento, c.seccion, c.texto, round(s, 6)))
        return resultado

    def formatear(self, consulta: str, k: int = K_DEFAULT) -> str:
        """Salida en texto plano para inyectar como resultado de la herramienta."""
        pasajes = self.consultar(consulta, k)
        if not pasajes:
            return "Sin resultados en el corpus para esa consulta."
        partes = []
        for p in pasajes:
            partes.append(f"[{p.documento} § {p.seccion}]\n{p.texto}")
        return "\n\n---\n\n".join(partes)
