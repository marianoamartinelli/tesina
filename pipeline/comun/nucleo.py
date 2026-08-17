"""Núcleo compartido de ambos orquestadores (paridad estructural, ADR-009).

Todo lo que NO depende del CLI de cada proveedor vive acá: carga de configuración
por celda, carga verbatim de los prompts (sistema, etapa y rol), secuencia de roles
de una etapa, configuración del RAG y comando del servidor MCP que lo expone,
registro JSONL y contrato de CLI. Cada `orquestar.py` es sólo un adaptador fino que
traduce esto a la línea de comandos de su proveedor (`claude -p` / `codex exec`); si
algo de este módulo se duplicara dentro de un harness, la paridad dejaría de ser
auditable por construcción.

Reemplaza al núcleo de ADR-005: no hay tope de turnos (ADR-009 §Consecuencias cierra
el ítem 14 de la checklist H6 — se cae el tope, no la métrica: turnos y tokens se
siguen registrando).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, is_dataclass, asdict
from pathlib import Path
from typing import Any

import yaml

from comun.rag.indice import IndiceCorpus

# Niveles de effort disponibles en las dos familias: `claude --effort`
# (verificado en 2.1.233) y `codex -c model_reasoning_effort` (que además acepta
# `ultra`, excluido acá porque no existe del lado A y rompería el pareo).
# ADR-009 Decisión 3 fija `xhigh` en las 4 celdas; el valor efectivo sale de la
# config de cada celda, no de este módulo.
EFFORTS_VALIDOS = ("low", "medium", "high", "xhigh", "max")

# Nombre del único servidor MCP que expone el RAG, idéntico en las dos familias
# (ADR-009 Decisión 2). En A el nombre calificado de la herramienta queda
# `mcp__corpus__<herramienta>`.
SERVIDOR_MCP = "corpus"

RUTA_SERVIDOR_MCP = Path(__file__).resolve().parent / "rag" / "servidor_mcp.py"

# Precios de lista en USD por millón de tokens. Sólo se usan para la ESTIMACIÓN de
# costo del harness B: `codex exec --json` informa tokens pero no USD, mientras que
# `claude -p` informa `total_cost_usd` nativo bajo suscripción (ADR-009 §Evidencia
# verificada).
#
# Verificados el 2026-08-16 contra la documentación de cada proveedor; el detalle,
# las URLs y la comparación del pareo están en `runs/piloto-01/precio-gpt-5-6-sol.md`
# (ítem 20 de la checklist H6, pendiente de ratificación del tesista).
#
# `umbral_tramo_largo` = tokens de INPUT a partir de los cuales el request COMPLETO
# se factura al tramo largo; None = el proveedor no tiene tramo largo. Un modelo sin
# precio verificado se registra con un string (el motivo), nunca con un número
# plausible: `costo_estimado_usd` devuelve entonces `(None, motivo)`.
PRECIO_PENDIENTE = (
    "PENDIENTE-ARRANQUE: precio por token no verificado contra la documentación del "
    "proveedor"
)
PRECIOS_USD_POR_MTOK: dict[str, dict[str, float | int | None] | str] = {
    "claude-opus-5": {
        "entrada": 5.0,
        "salida": 25.0,
        "umbral_tramo_largo": None,
    },
    "gpt-5.6-sol": {
        "entrada": 5.0,
        "salida": 30.0,
        "umbral_tramo_largo": 272_000,
        "entrada_tramo_largo": 10.0,
        "salida_tramo_largo": 45.0,
    },
}

_CAMPOS_CONFIG = {"celda", "harness", "modelo", "effort", "rag", "etapas"}


@dataclass(frozen=True)
class ConfigRAG:
    """Parámetros de la herramienta RAG, únicos para las 4 celdas (etapas.yaml)."""

    herramienta: str
    descripcion: str
    k: int
    ruta_corpus: Path


@dataclass(frozen=True)
class Paso:
    """Una invocación al CLI dentro de una etapa (ADR-009, Decisión 4).

    La secuencia por etapa es implementador → revisor → implementador; cada paso
    es una sesión fresca y el handoff son archivos bajo `.pipeline/` pasados por
    puntero en el mensaje.
    """

    orden: int                   # 1..n dentro de la etapa
    rol: str                     # id del rol en etapas.yaml
    ruta_prompt_rol: Path
    prompt_rol: str              # contenido verbatim del prompt de rol
    prompt_usuario: str          # prompt de etapa + la instrucción del paso (puntero)
    ruta_salida: Path | None     # archivo de handoff que este paso produce
    ruta_entrada: Path | None    # archivo de handoff que este paso consume


@dataclass(frozen=True)
class Corrida:
    """Todo lo que un orquestador necesita para ejecutar una etapa de una celda."""

    celda: str
    harness: str
    modelo: str
    effort: str
    rag: bool
    etapa: str
    prompt_sistema: str          # contenido verbatim de comun/prompts/sistema.md
    prompt_etapa: str            # contenido verbatim del prompt de la etapa
    ruta_prompt_sistema: Path
    ruta_prompt_etapa: Path
    ruta_etapas: Path            # comun/etapas.yaml (lo consume también el servidor MCP)
    ruta_repo: Path              # repo satélite (cwd/workspace del agente)
    ruta_log: Path               # <repo>/../logs/<celda>-<etapa>-<timestamp>.jsonl
    ruta_log_rag: Path           # ídem, sufijo -rag: lo escribe el servidor MCP
    pasos: tuple[Paso, ...]      # secuencia de invocaciones de la etapa
    rag_config: ConfigRAG | None  # None en celdas sin RAG


def sha256_archivo(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def construir_parser(descripcion: str) -> argparse.ArgumentParser:
    """Contrato de CLI idéntico para ambos orquestadores."""
    parser = argparse.ArgumentParser(description=descripcion)
    parser.add_argument("--config", required=True,
                        help="Ruta a la config de la celda (pipeline/config/<celda>.yaml)")
    parser.add_argument("--repo", required=True,
                        help="Ruta al repo satélite donde el agente implementa el exchange")
    parser.add_argument("--etapa", required=True,
                        help="Id de etapa según comun/etapas.yaml (backend|web|mobile)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Carga config + prompts + índice RAG y muestra qué ejecutaría, "
                             "sin invocar a ningún CLI")
    return parser


def cargar_rag(ruta_etapas: str | Path) -> ConfigRAG:
    """Configuración de la herramienta RAG desde etapas.yaml.

    Única fuente del nombre, la descripción, el corpus y el `k`: la consumen el
    orquestador (para lanzar el servidor) y el propio servidor MCP (para declarar
    la herramienta). Ningún harness ni el servidor definen esos valores.
    """
    ruta_etapas = Path(ruta_etapas).resolve()
    etapas = yaml.safe_load(ruta_etapas.read_text(encoding="utf-8"))
    rag = etapas["rag"]
    return ConfigRAG(
        herramienta=rag["herramienta"],
        descripcion=rag["descripcion"],
        k=rag["k"],
        # El corpus se referencia relativo a la raíz de pipeline/ (padre de comun/).
        ruta_corpus=(ruta_etapas.parent.parent / rag["corpus"]).resolve(),
    )


def _cargar_pasos(etapas: dict, raiz_pipeline: Path, etapa_id: str,
                  prompt_etapa: str, ruta_repo: Path) -> tuple[Paso, ...]:
    """Construye la secuencia de invocaciones de una etapa desde etapas.yaml."""
    roles = etapas["roles"]
    pasos: list[Paso] = []
    salidas_previas: set[str] = set()

    for orden, paso in enumerate(etapas["secuencia"], start=1):
        rol = paso["rol"]
        if rol not in roles:
            raise ValueError(f"secuencia: rol {rol!r} no está definido en 'roles'")
        ruta_prompt_rol = (raiz_pipeline / roles[rol]["prompt"]).resolve()

        salida = paso.get("salida")
        entrada = paso.get("entrada")
        salida = salida.format(etapa=etapa_id) if salida else None
        entrada = entrada.format(etapa=etapa_id) if entrada else None
        if entrada is not None and entrada not in salidas_previas:
            raise ValueError(
                f"secuencia, paso {orden}: la entrada {entrada!r} no la produce ningún "
                f"paso anterior (producidas hasta acá: {sorted(salidas_previas)})"
            )
        if salida is not None:
            salidas_previas.add(salida)

        prompt_usuario = prompt_etapa.rstrip("\n") + "\n"
        instruccion = paso.get("instruccion")
        if instruccion:
            texto = instruccion.format(etapa=etapa_id, salida=salida, entrada=entrada)
            prompt_usuario += "\n" + texto.strip() + "\n"

        pasos.append(Paso(
            orden=orden,
            rol=rol,
            ruta_prompt_rol=ruta_prompt_rol,
            prompt_rol=ruta_prompt_rol.read_text(encoding="utf-8"),
            prompt_usuario=prompt_usuario,
            ruta_salida=(ruta_repo / salida) if salida else None,
            ruta_entrada=(ruta_repo / entrada) if entrada else None,
        ))
    return tuple(pasos)


def cargar_corrida(ruta_config: str | Path, ruta_repo: str | Path, etapa_id: str,
                   harness_esperado: str) -> Corrida:
    """Carga y valida la configuración completa de una corrida de etapa.

    `harness_esperado` evita el error de correr una celda con el orquestador ajeno
    (p. ej. b-con-rag con harness_a/orquestar.py).
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
    if config["effort"] not in EFFORTS_VALIDOS:
        raise ValueError(
            f"config {ruta_config.name}: effort={config['effort']!r} no es uno de "
            f"{list(EFFORTS_VALIDOS)} (ADR-009 Decisión 3 fija 'xhigh')"
        )

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
    dir_logs = ruta_repo.parent / "logs"
    ruta_log = dir_logs / f"{config['celda']}-{etapa_id}-{marca_tiempo}.jsonl"

    return Corrida(
        celda=config["celda"],
        harness=config["harness"],
        modelo=config["modelo"],
        effort=config["effort"],
        rag=config["rag"],
        etapa=etapa_id,
        prompt_sistema=prompt_sistema,
        prompt_etapa=prompt_etapa,
        ruta_prompt_sistema=ruta_prompt_sistema,
        ruta_prompt_etapa=ruta_prompt_etapa,
        ruta_etapas=ruta_etapas,
        ruta_repo=ruta_repo,
        ruta_log=ruta_log,
        # El servidor MCP corre como proceso hijo del CLI, no del orquestador:
        # escribe su propio archivo para no intercalar escrituras sobre el mismo.
        ruta_log_rag=ruta_log.with_name(ruta_log.stem + "-rag.jsonl"),
        pasos=_cargar_pasos(etapas, raiz_pipeline, etapa_id, prompt_etapa, ruta_repo),
        rag_config=cargar_rag(ruta_etapas) if config["rag"] else None,
    )


def sistema_compuesto(corrida: Corrida, paso: Paso) -> str:
    """Prompt propio del experimento: el de sistema más el del rol, en ese orden.

    Es el mismo texto para las 4 celdas; lo que difiere es el punto de inserción
    respecto del scaffolding nativo (A lo appendea con `--append-system-prompt`,
    B lo prependea con `-c developer_instructions=…`), declarado por ADR-009
    Decisión 1 como equivalencia funcional, no como identidad.
    """
    return corrida.prompt_sistema.rstrip("\n") + "\n\n" + paso.prompt_rol.rstrip("\n") + "\n"


def comando_servidor_rag(corrida: Corrida, paso: Paso) -> list[str]:
    """Comando que lanza el servidor MCP del RAG, idéntico en las dos familias.

    Lo consumen A vía `--mcp-config` (+ `--strict-mcp-config`) y B vía
    `-c mcp_servers.<SERVIDOR_MCP>.command/.args`. El contexto de la invocación va
    en los argumentos para que cada `consulta_rag` quede atribuida a su celda,
    etapa y rol (ADR-003 / ADR-010 Decisión 1).
    """
    if corrida.rag_config is None:
        raise ValueError("la celda no tiene RAG habilitado; no hay servidor que lanzar")
    return [
        sys.executable, str(RUTA_SERVIDOR_MCP),
        "--etapas", str(corrida.ruta_etapas),
        "--log", str(corrida.ruta_log_rag),
        "--celda", corrida.celda,
        "--etapa", corrida.etapa,
        "--rol", paso.rol,
        "--paso", str(paso.orden),
    ]


def costo_estimado_usd(modelo: str, tokens_entrada: int,
                       tokens_salida: int) -> tuple[float | None, str | None]:
    """Estimación local de costo de UN request → `(costo, motivo)`.

    `motivo` es None cuando hay costo. Nunca devuelve un número inventado: si el
    precio del modelo no está verificado, devuelve `(None, motivo)` y el motivo
    queda registrado en el JSONL.

    **Se llama por request (o por turno) y se acumula**, nunca sobre el total de
    la etapa: el tramo de precio se decide comparando los tokens de input de
    *ese* request contra `umbral_tramo_largo`, y el recargo se aplica al request
    completo —no sólo a los tokens excedentes—, que es como lo enuncia la
    documentación del proveedor. Una tarifa plana al tramo corto subestima y una
    plana al tramo largo sobreestima.

    Usa precios de lista sin descuento por caché: `turn.completed` reporta la
    entrada cacheada y la escritura de caché como clases de token separadas, y si
    esas tarifas entran o no en la estimación es decisión del tesista (ítem 20 de
    la checklist H6).

    **Todavía no la llama el orquestador**: se computa sobre los `evento_cli` ya
    registrados en el JSONL. Cablearla al bucle exige conocer los nombres exactos
    de los campos de tokens de `turn.completed`, que es justamente lo que la
    piloto pinnea (ítem 19); adivinarlos ahora sería inventar el esquema.
    """
    precios = PRECIOS_USD_POR_MTOK.get(modelo)
    if precios is None:
        return None, f"modelo {modelo!r} sin precio registrado en PRECIOS_USD_POR_MTOK"
    if isinstance(precios, str):
        return None, precios

    umbral = precios["umbral_tramo_largo"]
    tramo_largo = umbral is not None and tokens_entrada > umbral
    precio_entrada = precios["entrada_tramo_largo"] if tramo_largo else precios["entrada"]
    precio_salida = precios["salida_tramo_largo"] if tramo_largo else precios["salida"]
    return (tokens_entrada * precio_entrada / 1_000_000
            + tokens_salida * precio_salida / 1_000_000), None


def tipo_evento_cli(payload: dict) -> str | None:
    """Tipo declarado por un evento del CLI, si lo trae.

    Se lee de forma defensiva: los esquemas exactos de ambos streams
    (`claude -p --output-format stream-json` y `codex exec --json`) se validan en
    la piloto (ítem 19 de la checklist H6). Un evento sin `type` se registra igual,
    con su payload completo.
    """
    valor = payload.get("type")
    return valor if isinstance(valor, str) else None


def es_de_subagente(familia: str, payload: dict) -> bool | None:
    """¿El evento viene de un subagente? `None` = no determinable con lo verificado.

    ADR-010 Decisión 1 exige que el JSONL capture la actividad de subagentes y no
    sólo la del agente principal.

    - Familia `a`: `claude --forward-subagent-text` reenvía el texto y el thinking
      de los subagentes como mensajes con `parent_tool_use_id` seteado (verificado
      en `claude --help`, 2.1.233). Sin ese flag el campo nunca aparece y todo se
      lee como agente principal.
    - Familia `b`: el mapeo de los eventos de thread de `codex exec --json` a
      subagentes no está verificado, así que no se decide acá y el payload queda
      completo en el log. PENDIENTE-PILOTO (ítem 24 de la checklist H6).
    """
    if familia == "a":
        return payload.get("parent_tool_use_id") is not None
    return None


def serializar(obj: Any) -> Any:
    """Convierte a algo JSON-able cualquier cosa que se quiera registrar.

    Los eventos de los CLI ya llegan como JSON parseado; esto cubre el resto
    (objetos de la stdlib, dataclasses del núcleo) y degrada a `str()` lo que no
    reconoce, para que un objeto exótico no rompa el log. Que esa degradación no
    pierda información relevante para el meta-análisis se revisa en la piloto
    (ítem 16 de la checklist H6).
    """
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(c): serializar(v) for c, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [serializar(v) for v in obj]
    if hasattr(obj, "model_dump"):  # modelos pydantic
        try:
            return obj.model_dump(mode="json")
        except Exception:
            return str(obj)
    if is_dataclass(obj) and not isinstance(obj, type):
        try:
            return serializar(asdict(obj))
        except Exception:
            return str(obj)
    return str(obj)


class RegistroJSONL:
    """Log JSONL por corrida de etapa: un evento por línea, con timestamp.

    Se escribe y flushea línea a línea para que una corrida interrumpida conserve
    todo lo ocurrido hasta el corte (requisito del protocolo de registro, ADR-003
    y ADR-004).
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

    def evento_cli(self, familia: str, linea: str) -> dict | None:
        """Registra una línea del stream del CLI y devuelve su payload parseado.

        Sirve para las dos familias: el `stream-json` de `claude -p` y el JSONL de
        `codex exec --json` emiten un objeto JSON por línea. El payload se guarda
        **completo y verbatim** —ningún campo se descarta— más dos derivados que el
        meta-análisis necesita indexar: el tipo declarado y si el evento es de un
        subagente. Una línea que no parsea se registra igual, como
        `linea_cli_no_json`, en vez de romper la corrida.
        """
        texto = linea.rstrip("\n")
        if not texto.strip():
            return None
        try:
            payload = json.loads(texto)
        except json.JSONDecodeError:
            self.evento("linea_cli_no_json", familia=familia, texto=texto)
            return None
        if not isinstance(payload, dict):
            self.evento("evento_cli", familia=familia, tipo_cli=None,
                        subagente=None, payload=payload)
            return None
        self.evento("evento_cli", familia=familia,
                    tipo_cli=tipo_evento_cli(payload),
                    subagente=es_de_subagente(familia, payload),
                    payload=payload)
        return payload

    def cerrar(self) -> None:
        self._archivo.close()


def comando_legible(comando: list[str]) -> list[str]:
    """Comando con los argumentos largos truncados, para imprimir y registrar.

    Los prompts viajan dentro de la línea de comandos en las dos familias
    (`--append-system-prompt`, `-c developer_instructions=…`) y hacen ilegible el
    log; su contenido ya queda auditado por el SHA-256 de `metadata_paso`.
    """
    return [a if len(a) <= 120 else a[:117] + "…" for a in comando]


# Lo que no entra en el snapshot: directorios que no son producto del agente y que
# harían la copia inmanejable. Misma lista para las 4 celdas.
EXCLUIDOS_SNAPSHOT = (".git", "node_modules", "dist", "build", ".expo")


def snapshot_paso(corrida: Corrida, paso: Paso) -> dict[str, Any]:
    """Copia el repo satélite al cerrar una invocación de rol.

    Es la evidencia primaria del eje `veracidad` y de RV-02/RV-03 de
    `evaluacion/rubricas/rol-revisor.md` (su precondición 2 admite «commit, tag o
    copia que deja el orquestador»). Se elige la copia y no un commit para no
    escribir en el historial del repo generado, que es dato del experimento.

    Vive en el núcleo, así que es idéntico en las 4 celdas por construcción. El
    destino cuelga del stem del log —que ya lleva timestamp— para que una
    re-invocación sobre la misma etapa (protocolo v1.1 §5.8) no pise los
    snapshots del intento anterior.

    Un fallo acá **no corta la etapa**: es instrumentación, y la rúbrica ya define
    qué hacer si el estado no es recuperable (`NO_EVALUABLE` causa (b)).
    """
    destino = (corrida.ruta_log.parent / f"{corrida.ruta_log.stem}-snapshots"
               / f"paso{paso.orden}-{paso.rol}")
    try:
        shutil.copytree(corrida.ruta_repo, destino, symlinks=True,
                        ignore=shutil.ignore_patterns(*EXCLUIDOS_SNAPSHOT))
        archivos = sum(1 for ruta in destino.rglob("*") if ruta.is_file())
        return {"ok": True, "ruta": str(destino), "archivos": archivos}
    except Exception as exc:
        return {"ok": False, "ruta": str(destino), "error": repr(exc)}


def ejecutar_paso(corrida: Corrida, paso: Paso, comando: list[str], familia: str,
                  registro: RegistroJSONL, **datos_inicio: Any) -> int:
    """Corre UNA invocación al CLI y devuelve su código de salida.

    Es el mismo bucle para las dos familias —de ahí que viva acá y no en cada
    orquestador, que aporta sólo su `comando`—: sesión fresca, prompt del paso por
    stdin, una línea de stdout = un evento del JSONL, stderr a un archivo lateral.

    Detalles que no son incidentales:

    - **stderr a archivo y no a un pipe:** una etapa larga puede escribir más que
      el buffer del pipe y, con el orquestador bloqueado leyendo stdout, el CLI
      quedaría trabado. Además así sobrevive a una interrupción, como el JSONL
      (ADR-003).
    - **el prompt no va como argumento:** se escribe por stdin, para no depender
      del límite de longitud de la línea de comandos.
    - **el directorio de la salida se crea acá:** `Paso.ruta_salida` apunta a
      `.pipeline/` dentro del repo satélite (ADR-009 Decisión 4) y el agente no
      tiene por qué crear el directorio. Se crea idéntico en las 4 celdas.
    - **un handoff faltante no corta la corrida:** el orquestador no interpreta la
      salida del modelo; lo registra y sigue, y decide el evaluador humano.
    - **el snapshot se toma pase lo que pase:** también cuando el paso cortó, que
      es justo el estado que la regla de continuación de etapa necesita
      (protocolo v1.1 §5.8).
    """
    registro.evento("paso_inicio", **metadata_paso(corrida, paso),
                    comando=comando_legible(comando), **datos_inicio)

    if paso.ruta_salida is not None:
        paso.ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    if paso.ruta_entrada is not None and not paso.ruta_entrada.is_file():
        registro.evento("handoff_faltante", orden=paso.orden, rol=paso.rol,
                        entrada=str(paso.ruta_entrada))

    ruta_stderr = corrida.ruta_log.with_name(
        f"{corrida.ruta_log.stem}-stderr-paso{paso.orden}.txt")
    ruta_stderr.parent.mkdir(parents=True, exist_ok=True)
    with ruta_stderr.open("w", encoding="utf-8") as archivo_stderr:
        proceso = subprocess.Popen(
            comando, cwd=str(corrida.ruta_repo),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=archivo_stderr,
            text=True, encoding="utf-8", bufsize=1,
        )
        assert proceso.stdin is not None and proceso.stdout is not None
        try:
            proceso.stdin.write(paso.prompt_usuario)
            proceso.stdin.close()
            for linea in proceso.stdout:
                registro.evento_cli(familia, linea)
            codigo = proceso.wait()
        except BaseException:
            # Ctrl-C o error del orquestador: el CLI headless no puede quedar
            # corriendo sin supervisión, consumiendo la suscripción.
            proceso.terminate()
            proceso.wait()
            registro.evento("paso_abortado", orden=paso.orden, rol=paso.rol,
                            stderr=str(ruta_stderr))
            raise
    registro.evento("paso_fin", orden=paso.orden, rol=paso.rol, codigo_salida=codigo,
                    stderr=str(ruta_stderr),
                    salida_escrita=(paso.ruta_salida.is_file()
                                    if paso.ruta_salida else None))
    registro.evento("snapshot", orden=paso.orden, rol=paso.rol,
                    **snapshot_paso(corrida, paso))
    return codigo


def correr_etapa(corrida: Corrida, cli: str, version: str, familia: str,
                 construir_comando) -> int:
    """Bucle de una etapa: los N pasos de la secuencia, en una sesión fresca cada uno.

    `construir_comando(corrida, paso)` es lo único que aporta cada orquestador; puede
    devolver `(comando, datos_para_el_log)` si necesita registrar algo propio de su
    familia.
    """
    registro = RegistroJSONL(corrida.ruta_log)
    try:
        registro.evento("inicio", **metadata_corrida(corrida, cli, version))
        for paso in corrida.pasos:
            resultado = construir_comando(corrida, paso)
            comando, datos = resultado if isinstance(resultado, tuple) else (resultado, {})
            codigo = ejecutar_paso(corrida, paso, comando, familia, registro, **datos)
            if codigo != 0:
                # Falla del CLI, no del modelo: se corta y decide el operador
                # (protocolo §5), el orquestador no reintenta.
                registro.evento("corte", motivo="codigo_salida_no_cero",
                                orden=paso.orden, codigo_salida=codigo)
                return codigo
        registro.evento("fin", etapa=corrida.etapa, pasos=len(corrida.pasos))
    except Exception as exc:  # el log tiene que conservar la causa del corte
        registro.evento("error_orquestador", excepcion=repr(exc))
        raise
    finally:
        registro.cerrar()
    print(f"Etapa {corrida.etapa} de {corrida.celda}: {len(corrida.pasos)} "
          f"invocaciones registradas en {corrida.ruta_log}")
    return 0


def _metadata_prompt(ruta: Path) -> dict[str, str]:
    return {"ruta": str(ruta), "sha256": sha256_archivo(ruta)}


def metadata_corrida(corrida: Corrida, cli: str, version_cli: str) -> dict[str, Any]:
    """Evento inicial del log: deja auditable qué se ejecutó exactamente."""
    datos: dict[str, Any] = {
        "celda": corrida.celda,
        "harness": corrida.harness,
        "cli": cli,
        "version_cli": version_cli,
        "modelo": corrida.modelo,
        "effort": corrida.effort,
        "rag": corrida.rag,
        "etapa": corrida.etapa,
        "repo_satelite": str(corrida.ruta_repo),
        "prompt_sistema": _metadata_prompt(corrida.ruta_prompt_sistema),
        "prompt_etapa": _metadata_prompt(corrida.ruta_prompt_etapa),
        "secuencia": [
            {"orden": p.orden, "rol": p.rol,
             "prompt_rol": _metadata_prompt(p.ruta_prompt_rol)}
            for p in corrida.pasos
        ],
    }
    if corrida.rag_config is not None:
        datos["rag_config"] = {
            "herramienta": corrida.rag_config.herramienta,
            "k": corrida.rag_config.k,
            "corpus": str(corrida.rag_config.ruta_corpus),
            "servidor_mcp": SERVIDOR_MCP,
            "log": str(corrida.ruta_log_rag),
        }
    return datos


def metadata_paso(corrida: Corrida, paso: Paso) -> dict[str, Any]:
    """Evento de apertura de cada invocación al CLI (una sesión fresca por paso)."""
    return {
        "orden": paso.orden,
        "de": len(corrida.pasos),
        "rol": paso.rol,
        "prompt_rol": _metadata_prompt(paso.ruta_prompt_rol),
        "sha256_sistema_compuesto": hashlib.sha256(
            sistema_compuesto(corrida, paso).encode("utf-8")).hexdigest(),
        "sha256_prompt_usuario": hashlib.sha256(
            paso.prompt_usuario.encode("utf-8")).hexdigest(),
        "entrada": str(paso.ruta_entrada) if paso.ruta_entrada else None,
        "salida": str(paso.ruta_salida) if paso.ruta_salida else None,
    }


def resumen_dry_run(corrida: Corrida, cli: str, version_cli: str,
                    detalle_herramientas: str) -> str:
    """Texto que cada orquestador imprime con --dry-run (sin invocar al CLI).

    Construye el índice RAG de las celdas con RAG: es el chequeo previo de que el
    corpus está donde la config dice y es indexable, el mismo trabajo que hará el
    servidor MCP al arrancar.
    """
    lineas = [
        "DRY-RUN — no se invocó a ningún CLI",
        f"  celda:          {corrida.celda}",
        f"  harness:        {corrida.harness} ({cli} {version_cli})",
        f"  modelo:         {corrida.modelo} (effort {corrida.effort})",
        f"  rag:            {corrida.rag}",
        f"  etapa:          {corrida.etapa}",
        f"  repo satélite:  {corrida.ruta_repo}",
        f"  log:            {corrida.ruta_log}",
        f"  prompt sistema: {corrida.ruta_prompt_sistema}"
        f" ({len(corrida.prompt_sistema)} chars,"
        f" sha256 {sha256_archivo(corrida.ruta_prompt_sistema)[:12]}…)",
        f"  prompt etapa:   {corrida.ruta_prompt_etapa}"
        f" ({len(corrida.prompt_etapa)} chars,"
        f" sha256 {sha256_archivo(corrida.ruta_prompt_etapa)[:12]}…)",
        f"  secuencia:      {len(corrida.pasos)} invocaciones "
        f"({' → '.join(p.rol for p in corrida.pasos)})",
    ]
    for paso in corrida.pasos:
        lineas.append(
            f"    {paso.orden}. {paso.rol}: {paso.ruta_prompt_rol.name}"
            f" ({len(paso.prompt_rol)} chars,"
            f" sha256 {sha256_archivo(paso.ruta_prompt_rol)[:12]}…)"
            + (f", lee {paso.ruta_entrada.name}" if paso.ruta_entrada else "")
            + (f", escribe {paso.ruta_salida.name}" if paso.ruta_salida else "")
        )
    if corrida.rag_config is not None:
        indice = IndiceCorpus.desde_directorio(corrida.rag_config.ruta_corpus)
        lineas += [
            f"  herramienta RAG: {corrida.rag_config.herramienta}"
            f" (k={corrida.rag_config.k}, servidor MCP stdio '{SERVIDOR_MCP}')",
            f"  corpus:          {corrida.rag_config.ruta_corpus}"
            f" ({getattr(indice, '_n', '?')} chunks indexados)",
            f"  comando servidor: {' '.join(comando_servidor_rag(corrida, corrida.pasos[0]))}",
        ]
    else:
        lineas.append("  herramienta RAG: no registrada (celda sin RAG)")
    lineas.append(f"  herramientas del CLI: {detalle_herramientas}")
    return "\n".join(lineas)
