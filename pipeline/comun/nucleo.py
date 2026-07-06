"""Núcleo compartido de ambos harnesses (paridad estructural, ADR-005).

Todo lo que NO depende del SDK de agentes vive acá: carga de configuración por
celda, carga verbatim de prompts, construcción del índice RAG, registro JSONL y
contrato de CLI. Cada `correr.py` es sólo un adaptador fino a su SDK; si algo de
este módulo se duplicara dentro de un harness, la paridad dejaría de ser
auditable por construcción.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import dataclass, is_dataclass, asdict
from pathlib import Path
from typing import Any, Callable

import yaml

from comun.rag.indice import IndiceCorpus

# Tope de iteraciones del loop agéntico, idéntico en ambos harnesses (una
# "iteración" ≈ una invocación al modelo). Es un límite de seguridad contra
# loops descontrolados, no un parámetro de generación; el corte real de una
# corrida lo dan los presupuestos del protocolo (ADR-004).
# En harness A se pasa como ClaudeAgentOptions.max_turns; en harness B como
# Runner.run_streamed(max_turns=...). La semántica exacta de "turno" difiere
# levemente entre SDKs; se documenta como limitación en el README.
MAX_TURNS = 500

# Precios USD por millón de tokens según ADR-005 (verificados 2026-07-05).
# Sólo se usan para la ESTIMACIÓN de costo del harness B, cuyo SDK no informa
# costo monetario; el harness A usa el total_cost_usd nativo del SDK.
PRECIOS_USD_POR_MTOK = {
    "claude-opus-4-8": {"entrada": 5.0, "salida": 25.0},
    "gpt-5.5": {"entrada": 5.0, "salida": 30.0},
}

_CAMPOS_CONFIG = {"celda", "harness", "modelo", "rag", "etapas"}


@dataclass(frozen=True)
class Corrida:
    """Todo lo que un harness necesita para ejecutar una etapa de una celda."""

    celda: str
    harness: str
    modelo: str
    rag: bool
    etapa: str
    prompt_sistema: str          # contenido verbatim de comun/prompts/sistema.md
    prompt_etapa: str            # contenido verbatim del prompt de la etapa
    ruta_prompt_sistema: Path
    ruta_prompt_etapa: Path
    ruta_repo: Path              # repo satélite (cwd/workspace del agente)
    ruta_log: Path               # <repo>/../logs/<celda>-<etapa>-<timestamp>.jsonl
    rag_herramienta: str | None  # nombre de la herramienta (etapas.yaml: rag.herramienta)
    rag_descripcion: str | None  # descripción de la herramienta (etapas.yaml: rag.descripcion)
    rag_k: int | None
    indice: IndiceCorpus | None  # None en celdas sin RAG
    ruta_corpus: Path | None


def sha256_archivo(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def construir_parser(descripcion: str) -> argparse.ArgumentParser:
    """Contrato de CLI idéntico para ambos harnesses."""
    parser = argparse.ArgumentParser(description=descripcion)
    parser.add_argument("--config", required=True,
                        help="Ruta a la config de la celda (pipeline/config/<celda>.yaml)")
    parser.add_argument("--repo", required=True,
                        help="Ruta al repo satélite donde el agente implementa el exchange")
    parser.add_argument("--etapa", required=True,
                        help="Id de etapa según comun/etapas.yaml (backend|web|mobile)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Carga config + prompts + índice RAG y muestra qué ejecutaría, "
                             "sin llamar a ninguna API")
    return parser


def cargar_corrida(ruta_config: str | Path, ruta_repo: str | Path, etapa_id: str,
                   harness_esperado: str) -> Corrida:
    """Carga y valida la configuración completa de una corrida de etapa.

    `harness_esperado` evita el error de correr una celda con el harness ajeno
    (p. ej. b-con-rag con harness_a/correr.py).
    """
    ruta_config = Path(ruta_config).resolve()
    config = yaml.safe_load(ruta_config.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError(f"config inválida (no es un mapeo): {ruta_config}")
    if set(config) != _CAMPOS_CONFIG:
        raise ValueError(
            f"config {ruta_config.name}: se esperaban exactamente los campos "
            f"{sorted(_CAMPOS_CONFIG)}, hay {sorted(config)}"
        )
    if config["harness"] != harness_esperado:
        raise ValueError(
            f"la celda {config['celda']!r} declara harness={config['harness']!r} "
            f"pero se la intentó correr con el harness {harness_esperado!r}"
        )
    if not isinstance(config["rag"], bool):
        raise ValueError(f"config {ruta_config.name}: 'rag' debe ser booleano")

    # etapas.yaml se referencia relativo a la config; los prompts y el corpus,
    # relativos a la raíz de pipeline/ (el padre de comun/).
    ruta_etapas = (ruta_config.parent / config["etapas"]).resolve()
    etapas = yaml.safe_load(ruta_etapas.read_text(encoding="utf-8"))
    raiz_pipeline = ruta_etapas.parent.parent

    por_id = {e["id"]: e for e in etapas["etapas"]}
    if etapa_id not in por_id:
        raise ValueError(f"etapa {etapa_id!r} desconocida; válidas: {sorted(por_id)}")

    ruta_prompt_sistema = (raiz_pipeline / etapas["prompt_sistema"]).resolve()
    ruta_prompt_etapa = (raiz_pipeline / por_id[etapa_id]["prompt"]).resolve()
    prompt_sistema = ruta_prompt_sistema.read_text(encoding="utf-8")
    prompt_etapa = ruta_prompt_etapa.read_text(encoding="utf-8")

    ruta_repo = Path(ruta_repo).resolve()
    if not ruta_repo.is_dir():
        raise ValueError(f"el repo satélite no existe o no es un directorio: {ruta_repo}")

    marca_tiempo = time.strftime("%Y%m%d-%H%M%S")
    ruta_log = ruta_repo.parent / "logs" / f"{config['celda']}-{etapa_id}-{marca_tiempo}.jsonl"

    indice = None
    ruta_corpus = None
    rag_conf = etapas.get("rag", {})
    if config["rag"]:
        ruta_corpus = (raiz_pipeline / rag_conf["corpus"]).resolve()
        indice = IndiceCorpus.desde_directorio(ruta_corpus)

    return Corrida(
        celda=config["celda"],
        harness=config["harness"],
        modelo=config["modelo"],
        rag=config["rag"],
        etapa=etapa_id,
        prompt_sistema=prompt_sistema,
        prompt_etapa=prompt_etapa,
        ruta_prompt_sistema=ruta_prompt_sistema,
        ruta_prompt_etapa=ruta_prompt_etapa,
        ruta_repo=ruta_repo,
        ruta_log=ruta_log,
        rag_herramienta=rag_conf.get("herramienta") if config["rag"] else None,
        rag_descripcion=rag_conf.get("descripcion") if config["rag"] else None,
        rag_k=rag_conf.get("k") if config["rag"] else None,
        indice=indice,
        ruta_corpus=ruta_corpus,
    )


def funcion_consultar_corpus(corrida: Corrida) -> Callable[[str], str]:
    """Implementación única de la herramienta RAG (la que ambos SDKs envuelven).

    Los harnesses sólo la registran con el nombre y la descripción de
    etapas.yaml; la recuperación en sí es idéntica byte a byte entre celdas.
    """
    if corrida.indice is None:
        raise ValueError("la celda no tiene RAG habilitado; no hay índice que consultar")
    indice, k = corrida.indice, corrida.rag_k

    def consultar(consulta: str) -> str:
        return indice.formatear(consulta, k=k)

    return consultar


def serializar(obj: Any) -> Any:
    """Convierte mensajes/eventos de cualquiera de los dos SDKs a algo JSON-able."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(c): serializar(v) for c, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [serializar(v) for v in obj]
    if hasattr(obj, "model_dump"):  # modelos pydantic (SDK de OpenAI)
        try:
            return obj.model_dump(mode="json")
        except Exception:
            return str(obj)
    if is_dataclass(obj) and not isinstance(obj, type):  # dataclasses (SDK de Claude)
        try:
            return serializar(asdict(obj))
        except Exception:
            return str(obj)
    return str(obj)


class RegistroJSONL:
    """Log JSONL por corrida de etapa: un evento por línea, con timestamp.

    Se escribe y flushea línea a línea para que una corrida interrumpida
    conserve todo lo ocurrido hasta el corte (requisito del protocolo de
    registro, ADR-003/ADR-004).
    """

    def __init__(self, ruta: Path):
        ruta.parent.mkdir(parents=True, exist_ok=True)
        self.ruta = ruta
        self._archivo = ruta.open("a", encoding="utf-8")

    def evento(self, tipo: str, **datos: Any) -> None:
        linea = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "tipo": tipo}
        linea.update({c: serializar(v) for c, v in datos.items()})
        self._archivo.write(json.dumps(linea, ensure_ascii=False) + "\n")
        self._archivo.flush()

    def cerrar(self) -> None:
        self._archivo.close()


def metadata_corrida(corrida: Corrida, version_sdk: str, sdk: str) -> dict[str, Any]:
    """Evento inicial del log: deja auditable qué se ejecutó exactamente."""
    datos: dict[str, Any] = {
        "celda": corrida.celda,
        "harness": corrida.harness,
        "sdk": sdk,
        "version_sdk": version_sdk,
        "modelo": corrida.modelo,
        "rag": corrida.rag,
        "etapa": corrida.etapa,
        "repo_satelite": str(corrida.ruta_repo),
        "max_turns": MAX_TURNS,
        "prompt_sistema": {
            "ruta": str(corrida.ruta_prompt_sistema),
            "sha256": sha256_archivo(corrida.ruta_prompt_sistema),
        },
        "prompt_etapa": {
            "ruta": str(corrida.ruta_prompt_etapa),
            "sha256": sha256_archivo(corrida.ruta_prompt_etapa),
        },
    }
    if corrida.rag:
        datos["rag_config"] = {
            "herramienta": corrida.rag_herramienta,
            "k": corrida.rag_k,
            "corpus": str(corrida.ruta_corpus),
        }
    return datos


def resumen_dry_run(corrida: Corrida, version_sdk: str, sdk: str,
                    detalle_herramientas: str) -> str:
    """Texto que cada correr.py imprime con --dry-run (sin llamar a ninguna API)."""
    lineas = [
        f"DRY-RUN — no se llamó a ninguna API",
        f"  celda:          {corrida.celda}",
        f"  harness:        {corrida.harness} ({sdk} {version_sdk})",
        f"  modelo:         {corrida.modelo}",
        f"  rag:            {corrida.rag}",
        f"  etapa:          {corrida.etapa}",
        f"  repo satélite:  {corrida.ruta_repo}",
        f"  log:            {corrida.ruta_log}",
        f"  max_turns:      {MAX_TURNS}",
        f"  prompt sistema: {corrida.ruta_prompt_sistema}"
        f" ({len(corrida.prompt_sistema)} chars,"
        f" sha256 {sha256_archivo(corrida.ruta_prompt_sistema)[:12]}…)",
        f"  prompt etapa:   {corrida.ruta_prompt_etapa}"
        f" ({len(corrida.prompt_etapa)} chars,"
        f" sha256 {sha256_archivo(corrida.ruta_prompt_etapa)[:12]}…)",
    ]
    if corrida.rag:
        n_chunks = getattr(corrida.indice, "_n", "?")
        lineas += [
            f"  herramienta RAG: {corrida.rag_herramienta} (k={corrida.rag_k})",
            f"  corpus:          {corrida.ruta_corpus} ({n_chunks} chunks indexados)",
        ]
    else:
        lineas.append("  herramienta RAG: no registrada (celda sin RAG)")
    lineas.append(f"  herramientas del SDK: {detalle_herramientas}")
    return "\n".join(lineas)
