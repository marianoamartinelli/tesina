#!/usr/bin/env python3
"""Verificación mecánica de paridad entre las 4 celdas del 2×2 (ADR-009 / ADR-010).

Reemplaza a la versión escrita contra ADR-005: los invariantes cambiaron con el
pasaje de los SDK a los CLI, y los chequeos viejos que siguen teniendo sentido
(campos de las configs, mismo `etapas.yaml`, BM25, SHA-256 del corpus) se
conservan tal cual.

Falla (exit code != 0) si se rompe cualquiera de estas garantías:

 1. Las 4 configs oficiales tienen exactamente los campos esperados y sólo
    difieren en los factores (`celda`, `harness`, `modelo`, `rag`).
 2. Los pares (harness, modelo) son exactamente los pinneados por ADR-009
    Decisión 3, con `effort: xhigh` en las 4, y cada harness tiene una celda con
    RAG y una sin RAG.
 3. Las 4 configs resuelven al MISMO `etapas.yaml`, cuya secuencia de roles es
    implementador → revisor → implementador (ADR-009 Decisión 4), y los prompts
    que ese archivo referencia existen y no están vacíos.
 4. Los prompts que efectivamente recibiría el CLI —de sistema, de etapa y de
    rol, ya compuestos— son **byte-idénticos** entre las 4 celdas, en las 3
    etapas. Se computa cargando cada celda con el mismo código que usan los
    orquestadores.
 5. Los prompts de rol traen la instrucción de delegación (ADR-010 Decisión 1) y
    ningún prompt nombra herramientas de un proveedor ni menciona el RAG.
 6. El RAG es un único servidor MCP stdio con los mismos parámetros para las dos
    familias, y tanto su comando como el bucle de ejecución de los pasos salen de
    `comun/nucleo.py` y no de cada orquestador.
 7. Los parámetros BM25 de `etapas.yaml` coinciden con las constantes del índice
    (`comun/rag/indice.py`), que no se ajustan por celda.
 8. Los SHA-256 de `corpus/documentos/*` coinciden byte a byte con el manifest
    congelado de H3 (`corpus/manifest.md`), sin archivos de más ni de menos.
 9. La restricción de recuperación web de ADR-008 está en la línea de comandos
    efectiva de **las dos** familias: `--disallowed-tools WebSearch,WebFetch` en
    A, y `web_search=disabled` más `--disable apps/browser_use/computer_use` en B
    (ADR-014 Decisión 2). Hasta ADR-014, el verificador no inspeccionaba ninguna
    línea de comandos: el traslado se daba por hecho sin chequeo que lo sostuviera.
10. Toda invocación va envuelta en `docker run` (ADR-015), con montajes idénticos
    entre familias salvo el `auth.json` de B, sin montar el holdout (`evaluacion/`) ni
    `pipeline/` entero, con la misma imagen base y tag, y con el mismo `--env-file` de
    credenciales en las 4 celdas.

Correr antes de cada corrida (protocolo §2 / ADR-004):
    .venv/bin/python pipeline/verificar_paridad.py
"""

from __future__ import annotations

import hashlib
import re
import sys
import tempfile
from pathlib import Path

import yaml

RAIZ_PIPELINE = Path(__file__).resolve().parent
RAIZ_REPO = RAIZ_PIPELINE.parent
sys.path.insert(0, str(RAIZ_PIPELINE))

from comun.nucleo import (  # noqa: E402
    RUTA_SERVIDOR_MCP,
    SERVIDOR_MCP,
    Corrida,
    cargar_corrida,
    comando_servidor_rag,
    sistema_compuesto,
)
from comun.rag import indice as modulo_indice  # noqa: E402
from comun import contenedor  # noqa: E402

sys.path.insert(0, str(RAIZ_PIPELINE / "harness_a"))
sys.path.insert(0, str(RAIZ_PIPELINE / "harness_b"))

CELDAS_OFICIALES = ["a-sin-rag", "a-con-rag", "b-sin-rag", "b-con-rag"]
ETAPAS = ["backend", "web", "mobile"]
CAMPOS_FACTORES = {"celda", "harness", "modelo", "rag"}
CAMPOS_CONFIG = CAMPOS_FACTORES | {"effort", "etapas"}

# Pareo pinneado por ADR-009 Decisión 3 (reemplaza al de ADR-005). Cambiarlo
# exige un ADR de reemplazo, no una edición de este archivo.
PARES_ADR009 = {"a": "claude-opus-5", "b": "gpt-5.6-sol"}
EFFORT_ADR009 = "xhigh"

SECUENCIA_ADR009 = ("implementador", "revisor", "implementador")

# Frase que ADR-010 Decisión 1 exige en los prompts de rol, verbatim e idéntica
# entre celdas (los prompts son un único archivo, así que idéntica por
# construcción; lo que este chequeo protege es que no se caiga al editarlos).
INSTRUCCION_DELEGACION = "Delegá en subagentes el trabajo independiente y acotado."

# Ningún prompt puede nombrar el stack de un proveedor: el texto es
# vendor-neutral y byte-idéntico entre las 4 celdas (ADR-009 D4 / ADR-010 D1).
TERMINOS_PROVEEDOR = [
    "claude", "codex", "anthropic", "openai", "gpt", "opus",
    "websearch", "webfetch", "spawn_agent", "followup_task",
    "agents.md", "claude.md", "mcp",
]
# Ni mencionar el RAG: su disponibilidad es la única diferencia entre celdas con
# y sin RAG (ADR-009 Decisión 2).
TERMINOS_RAG = [
    "rag", "corpus", "consultar_corpus", "bm25", "base de conocimiento",
]

ORQUESTADORES = {
    "a": RAIZ_PIPELINE / "harness_a" / "orquestar.py",
    "b": RAIZ_PIPELINE / "harness_b" / "orquestar.py",
}

_fallas: list[str] = []
_total = 0


def chequear(condicion: bool, mensaje: str) -> None:
    global _total
    _total += 1
    marca = "OK " if condicion else "FALLA"
    print(f"[{marca}] {mensaje}")
    if not condicion:
        _fallas.append(mensaje)


def sha(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def cargar_configs() -> dict[str, dict]:
    configs = {}
    for celda in CELDAS_OFICIALES:
        ruta = RAIZ_PIPELINE / "config" / f"{celda}.yaml"
        chequear(ruta.is_file(), f"existe config/{celda}.yaml")
        if ruta.is_file():
            configs[celda] = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    return configs


def verificar_configs(configs: dict[str, dict]) -> None:
    for celda, config in configs.items():
        chequear(set(config) == CAMPOS_CONFIG,
                 f"{celda}: campos exactamente {sorted(CAMPOS_CONFIG)}")
        chequear(config.get("celda") == celda,
                 f"{celda}: el campo 'celda' coincide con el nombre del archivo")
        chequear(isinstance(config.get("rag"), bool), f"{celda}: 'rag' es booleano")
        chequear(config.get("effort") == EFFORT_ADR009,
                 f"{celda}: effort == {EFFORT_ADR009!r} (ADR-009 Decisión 3)")

    # Fuera de los factores, todo lo demás debe ser idéntico entre las 4.
    compartidos = [{c: v for c, v in config.items() if c not in CAMPOS_FACTORES}
                   for config in configs.values()]
    chequear(all(c == compartidos[0] for c in compartidos),
             "las 4 configs sólo difieren en celda/harness/modelo/rag")

    pares = {(config["harness"], config["modelo"]) for config in configs.values()}
    chequear(pares == set(PARES_ADR009.items()),
             f"pares (harness, modelo) exactamente los de ADR-009 Decisión 3: "
             f"{sorted(PARES_ADR009.items())} (hay {sorted(pares)})")
    for harness in PARES_ADR009:
        rags = sorted(config["rag"] for config in configs.values()
                      if config["harness"] == harness)
        chequear(rags == [False, True],
                 f"harness {harness}: una celda con RAG y una sin RAG")


def verificar_etapas_y_prompts(configs: dict[str, dict]) -> tuple[dict, list[Path]]:
    rutas = {(RAIZ_PIPELINE / "config" / config["etapas"]).resolve()
             for config in configs.values()}
    chequear(len(rutas) == 1, "las 4 configs referencian el MISMO etapas.yaml")
    ruta_etapas = next(iter(rutas))
    chequear(ruta_etapas.is_file(), f"etapas.yaml existe ({ruta_etapas})")
    etapas = yaml.safe_load(ruta_etapas.read_text(encoding="utf-8"))
    raiz = ruta_etapas.parent.parent

    roles = etapas.get("roles", {})
    secuencia = tuple(p["rol"] for p in etapas.get("secuencia", []))
    chequear(secuencia == SECUENCIA_ADR009,
             f"secuencia de roles == {' → '.join(SECUENCIA_ADR009)} "
             f"(ADR-009 Decisión 4; hay {' → '.join(secuencia) or '∅'})")
    chequear(all(rol in roles for rol in secuencia),
             "todos los roles de la secuencia están definidos en 'roles'")

    rutas_prompts = ([raiz / etapas["prompt_sistema"]]
                     + [raiz / e["prompt"] for e in etapas["etapas"]]
                     + [raiz / roles[rol]["prompt"] for rol in sorted(roles)])
    for ruta in rutas_prompts:
        existe = ruta.is_file() and ruta.stat().st_size > 0
        chequear(existe, f"prompt existe y no está vacío: {ruta.relative_to(RAIZ_REPO)}")
    return etapas, rutas_prompts


def huella(corrida: Corrida) -> tuple:
    """Todo el texto que el CLI recibiría, reducido a hashes comparables."""
    return (
        sha(corrida.prompt_sistema),
        sha(corrida.prompt_etapa),
        tuple((paso.rol, sha(sistema_compuesto(corrida, paso)), sha(paso.prompt_usuario))
              for paso in corrida.pasos),
    )


def cargar_corridas(repo: Path) -> dict[tuple[str, str], Corrida]:
    corridas = {}
    for celda in CELDAS_OFICIALES:
        for etapa in ETAPAS:
            corridas[(celda, etapa)] = cargar_corrida(
                RAIZ_PIPELINE / "config" / f"{celda}.yaml", repo, etapa,
                harness_esperado=celda[0])
    return corridas


def verificar_prompts_identicos(corridas: dict[tuple[str, str], Corrida]) -> None:
    for etapa in ETAPAS:
        huellas = {celda: huella(corridas[(celda, etapa)]) for celda in CELDAS_OFICIALES}
        distintas = {h for h in huellas.values()}
        chequear(len(distintas) == 1,
                 f"etapa {etapa}: prompts (sistema + etapa + rol, ya compuestos) "
                 f"byte-idénticos entre las 4 celdas")


def verificar_prompts_de_rol(etapas: dict, rutas_prompts: list[Path]) -> None:
    raiz = RAIZ_PIPELINE
    for rol in sorted(etapas["roles"]):
        ruta = raiz / etapas["roles"][rol]["prompt"]
        texto = ruta.read_text(encoding="utf-8")
        chequear(INSTRUCCION_DELEGACION in texto,
                 f"prompt de rol {rol}: trae la instrucción de delegación "
                 f"(ADR-010 Decisión 1)")

    for ruta in rutas_prompts:
        texto = ruta.read_text(encoding="utf-8")
        nombre = ruta.relative_to(RAIZ_REPO)
        proveedor = [t for t in TERMINOS_PROVEEDOR
                     if re.search(rf"\b{re.escape(t)}\b", texto, re.IGNORECASE)]
        chequear(not proveedor,
                 f"{nombre}: no nombra herramientas ni productos de un proveedor"
                 + (f" (aparece {proveedor})" if proveedor else ""))
        rag = [t for t in TERMINOS_RAG
               if re.search(rf"\b{re.escape(t)}\b", texto, re.IGNORECASE)]
        chequear(not rag,
                 f"{nombre}: no menciona el RAG"
                 + (f" (aparece {rag})" if rag else ""))


def _comando_invariante(comando: list[str]) -> list[str]:
    """El comando del servidor MCP sin las partes que dependen de la invocación.

    `--celda`, `--etapa`, `--rol`, `--paso` y `--log` atribuyen cada consulta a
    su contexto (ADR-003); todo lo demás —intérprete, servidor, `etapas.yaml`—
    tiene que ser idéntico entre las dos familias.
    """
    variables = {"--celda", "--etapa", "--rol", "--paso", "--log"}
    fijo, saltar = [], False
    for arg in comando:
        if saltar:
            saltar = False
            continue
        if arg in variables:
            saltar = True
            continue
        fijo.append(arg)
    return fijo


def verificar_servidor_mcp(corridas: dict[tuple[str, str], Corrida]) -> None:
    chequear(RUTA_SERVIDOR_MCP.is_file(),
             f"el servidor MCP del RAG existe ({RUTA_SERVIDOR_MCP.name})")

    a = corridas[("a-con-rag", "backend")]
    b = corridas[("b-con-rag", "backend")]
    chequear(a.rag_config == b.rag_config,
             "la config del RAG (herramienta, descripción, k, corpus) es idéntica "
             "en las dos familias")
    chequear(_comando_invariante(comando_servidor_rag(a, a.pasos[0]))
             == _comando_invariante(comando_servidor_rag(b, b.pasos[0])),
             f"un único servidor MCP stdio '{SERVIDOR_MCP}' para las dos familias, "
             f"con el mismo comando")

    for celda in ("a-sin-rag", "b-sin-rag"):
        chequear(corridas[(celda, "backend")].rag_config is None,
                 f"{celda}: no se registra la herramienta RAG")

    for familia, ruta in ORQUESTADORES.items():
        chequear(ruta.is_file(), f"existe harness_{familia}/orquestar.py")
        if not ruta.is_file():
            continue
        fuente = ruta.read_text(encoding="utf-8")
        chequear("comando_servidor_rag" in fuente
                 and RUTA_SERVIDOR_MCP.name not in fuente,
                 f"harness_{familia}: el comando del servidor MCP sale de "
                 f"comun/nucleo.py, no del orquestador")
        chequear("prompts/" not in fuente,
                 f"harness_{familia}: no referencia archivos de prompt por su cuenta")
        # El bucle de ejecución (Popen + stdin + lectura de stdout + stderr a
        # archivo + creación de `.pipeline/`) vive una sola vez en comun/nucleo.py:
        # si un orquestador se hiciera el suyo, la paridad de ejecución dejaría de
        # ser auditable por construcción.
        chequear("Popen" not in fuente and "correr_etapa" in fuente,
                 f"harness_{familia}: el bucle de ejecución de los pasos sale de "
                 f"comun/nucleo.py (correr_etapa), no del orquestador")


def verificar_bm25(etapas: dict) -> None:
    bm25 = etapas.get("rag", {}).get("bm25", {})
    k = etapas.get("rag", {}).get("k")
    chequear(bm25.get("k1") == modulo_indice.K1 and bm25.get("b") == modulo_indice.B,
             f"parámetros BM25 de etapas.yaml == constantes del índice "
             f"(k1={modulo_indice.K1}, b={modulo_indice.B})")
    chequear(k == modulo_indice.K_DEFAULT,
             f"k de etapas.yaml == K_DEFAULT del índice ({modulo_indice.K_DEFAULT})")


def verificar_corpus() -> None:
    manifest = (RAIZ_REPO / "corpus" / "manifest.md").read_text(encoding="utf-8")
    # Filas de la tabla del manifest: | n | `documentos/<archivo>` | ... | `<sha256>` |
    esperados = dict(re.findall(
        r"\|\s*\d+\s*\|\s*`documentos/([^`]+)`.*?`([0-9a-f]{64})`", manifest))
    chequear(len(esperados) == 9, f"el manifest lista 9 documentos (hay {len(esperados)})")

    dir_corpus = RAIZ_REPO / "corpus" / "documentos"
    reales = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(dir_corpus.iterdir()) if p.is_file()}

    chequear(set(reales) == set(esperados),
             "corpus/documentos/ contiene exactamente los archivos del manifest"
             + ("" if set(reales) == set(esperados)
                else f" (sobran {sorted(set(reales) - set(esperados))},"
                     f" faltan {sorted(set(esperados) - set(reales))})"))
    for nombre in sorted(set(reales) & set(esperados)):
        chequear(reales[nombre] == esperados[nombre],
                 f"SHA-256 de {nombre} coincide con el manifest")


def _comandos_por_celda(corridas: dict[tuple[str, str], Corrida]) -> dict[str, list[str]]:
    """Línea de comandos efectiva del primer paso de cada celda.

    Importa los orquestadores y les pide el comando real, en vez de leer su
    fuente con grep: un chequeo textual pasaría igual si el flag estuviera
    escrito pero nunca llegara al comando, que es justo la clase de falso verde
    que ADR-014 encontró.
    """
    import importlib.util

    comandos: dict[str, list[str]] = {}
    for familia in ("a", "b"):
        spec = importlib.util.spec_from_file_location(
            f"orq_{familia}", ORQUESTADORES[familia])
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        for celda in (f"{familia}-sin-rag", f"{familia}-con-rag"):
            corrida = corridas[(celda, "backend")]
            paso = corrida.pasos[0]
            if familia == "a":
                ruta_mcp = (modulo.ruta_config_mcp(corrida, paso)
                            if corrida.rag_config else None)
                comandos[celda] = modulo.construir_comando(corrida, paso, ruta_mcp)
            else:
                comandos[celda] = modulo.construir_comando(corrida, paso)
    return comandos


def verificar_recuperacion_web(comandos: dict[str, list[str]]) -> None:
    """ADR-008 trasladado, verificado en el comando real de cada familia (ADR-014 D2)."""
    for celda in ("a-sin-rag", "a-con-rag"):
        cmd = comandos[celda]
        chequear("--disallowed-tools" in cmd
                 and cmd[cmd.index("--disallowed-tools") + 1] == "WebSearch,WebFetch",
                 f"{celda}: --disallowed-tools WebSearch,WebFetch (ADR-008)")
    for celda in ("b-sin-rag", "b-con-rag"):
        cmd = comandos[celda]
        chequear('web_search="disabled"' in cmd,
                 f"{celda}: -c web_search=disabled (ADR-014; el default NO es disabled)")
        for feature in ("apps", "browser_use", "computer_use"):
            pares = [(cmd[i], cmd[i + 1]) for i in range(len(cmd) - 1)]
            chequear(("--disable", feature) in pares,
                     f"{celda}: --disable {feature} (ADR-014)")
        # `--search` sube web_search a `live`: si aparece, la desactivación se
        # revierte y la celda sin RAG dejaría de ser sin recuperación.
        chequear("--search" not in cmd, f"{celda}: no se pasa --search")


def verificar_confinamiento(comandos: dict[str, list[str]]) -> None:
    """El confinamiento es el contenedor en las dos familias (ADR-019).

    Ninguna de las dos usa el sandbox del SO de su CLI: A corre con
    `--dangerously-skip-permissions` desde ADR-009, y B pasa a correr sin su
    sandbox nativo porque bubblewrap no puede crear user namespaces dentro del
    contenedor (medido en la pre-piloto: todo comando del modelo fallaba). Que
    ninguna lo use es la condición que hace comparable lo que cada agente puede
    ejecutar; si una lo recuperara, el factor pipeline cambiaría entre familias.
    """
    import harness_b.orquestar as orq_b

    for celda in ("a-sin-rag", "a-con-rag"):
        cmd = comandos[celda]
        chequear("--dangerously-skip-permissions" in cmd,
                 f"{celda}: sin sandbox del SO (--dangerously-skip-permissions)")
    for celda in ("b-sin-rag", "b-con-rag"):
        cmd = comandos[celda]
        chequear(orq_b.FLAG_SIN_SANDBOX in cmd,
                 f"{celda}: sin sandbox nativo de Codex ({orq_b.FLAG_SIN_SANDBOX}, ADR-019)")
        chequear("-s" not in cmd,
                 f"{celda}: no se pasa `-s` (el sandbox de Codex no funciona en contenedor)")

    # La envoltura del contenedor no compensa con permisos extra en una familia:
    # aflojar seccomp o agregar capabilities en una sola rompería la simetría que
    # `comun/contenedor.py` sostiene por construcción.
    for celda, cmd in comandos.items():
        for flag in ("--security-opt", "--cap-add", "--privileged", "--userns"):
            chequear(flag not in cmd,
                     f"{celda}: el docker run no lleva {flag} (envoltura idéntica)")


def verificar_contenedor(comandos: dict[str, list[str]],
                         corridas: dict[tuple[str, str], Corrida]) -> None:
    """Envoltura en contenedor idéntica entre familias (ADR-015)."""
    for celda, cmd in comandos.items():
        chequear(cmd[:2] == [contenedor.RUNTIME, "run"],
                 f"{celda}: la invocación va envuelta en `docker run` (ADR-015)")
        chequear("--rm" in cmd and "-i" in cmd,
                 f"{celda}: contenedor descartable (--rm) y con stdin (-i)")
        # El nodo on-chain corre en el host y la red del contenedor es propia: sin esto
        # el agente no puede ejercitar ningún camino JSON-RPC durante la generación
        # (ADR-020). Tiene que estar en las dos familias o la asimetría es de capacidad.
        pares = [(cmd[i], cmd[i + 1]) for i in range(len(cmd) - 1)]
        chequear(("--add-host", f"{contenedor.HOST_ANFITRION}:host-gateway") in pares,
                 f"{celda}: --add-host {contenedor.HOST_ANFITRION} (ADR-020)")

    # Los montajes sólo pueden diferir en el archivo de credenciales y en el estado de
    # sesión del CLI de B (ADR-023): cualquier otra diferencia es una asimetría de
    # entorno entre familias.
    def destinos(celda: str) -> set[str]:
        familia = celda[0]
        return {m.destino for m in contenedor.montajes(corridas[(celda, "backend")], familia)}

    for sufijo in ("sin-rag", "con-rag"):
        solo_a = destinos(f"a-{sufijo}") - destinos(f"b-{sufijo}")
        solo_b = destinos(f"b-{sufijo}") - destinos(f"a-{sufijo}")
        # A no monta credencial: se autentica por `--env-file` porque en macOS no hay
        # archivo vigente que montar (ver contenedor.CREDENCIALES). Y A no persiste
        # estado de sesión porque su stream ya registra a los subagentes; B lo necesita
        # (ver contenedor.ESTADO_CLI). Son las dos únicas diferencias admisibles.
        admisibles = {contenedor.CREDENCIALES["b"][1], contenedor.ESTADO_CLI["b"][1]}
        chequear(solo_a == set() and solo_b == admisibles,
                 f"{sufijo}: los montajes de A y B sólo difieren en las credenciales "
                 f"y el estado de sesión de B (ADR-023)")

    # El estado de sesión de B se persiste **bajo los logs de la corrida** y como hermano
    # de `auth.json` (un montaje anidado en otro montaje falla en docker; ADR-023).
    for celda in ("b-sin-rag", "b-con-rag"):
        corrida = corridas[(celda, "backend")]
        ms = {m.destino: m for m in contenedor.montajes(corrida, "b")}
        estado = ms[contenedor.ESTADO_CLI["b"][1]]
        chequear(not estado.ro and Path(estado.origen).parent == corrida.ruta_log.parent
                 and Path(estado.destino).parent == Path(contenedor.CREDENCIALES["b"][1]).parent,
                 f"{celda}: el estado de sesión de B va rw bajo los logs, hermano de auth.json")

    # El mismo archivo de credenciales por entorno para las 4 celdas: uno por familia
    # sería una asimetría de invocación.
    for celda, cmd in comandos.items():
        chequear("--env-file" in cmd
                 and cmd[cmd.index("--env-file") + 1] == str(contenedor.ARCHIVO_ENV),
                 f"{celda}: --env-file apunta al archivo único de credenciales")

    # El holdout no se monta, en ninguna celda: es lo que hace que la
    # no-exposición del protocolo §9 la sostenga el mecanismo (ADR-015 D5).
    for celda, cmd in comandos.items():
        montados = [cmd[i + 1] for i, a in enumerate(cmd[:-1]) if a == "-v"]
        chequear(not any("/evaluacion" in m for m in montados),
                 f"{celda}: no se monta el holdout (evaluacion/)")
        chequear(not any(m.split(":")[0].rstrip("/").endswith("/pipeline")
                         for m in montados),
                 f"{celda}: no se monta pipeline/ entero (config/ y el verificador "
                 f"son instrumentos, no insumos del agente)")

    # Un solo tag para las 4 celdas: dos toolchains distintos las volverían
    # incomparables (ver la nota de contenedor.TAG).
    tags = {contenedor.imagen(celda[0]).rsplit(":", 1)[1] for celda in comandos}
    chequear(len(tags) == 1, f"las 4 celdas usan el mismo tag de imagen: {sorted(tags)}")

    # Las dos capas parten de la misma base (ADR-015 D2).
    dir_c = RAIZ_PIPELINE / "contenedores"
    base = (dir_c / "Dockerfile.base").read_text(encoding="utf-8") if (
        dir_c / "Dockerfile.base").is_file() else ""
    chequear(bool(base), "existe contenedores/Dockerfile.base")
    for familia in ("a", "b"):
        ruta = dir_c / f"Dockerfile.{familia}"
        chequear(ruta.is_file(), f"existe contenedores/Dockerfile.{familia}")
        if ruta.is_file():
            chequear("FROM tesina/agente-base:" in ruta.read_text(encoding="utf-8"),
                     f"Dockerfile.{familia} parte de la base común (ADR-015 D2)")


def main() -> int:
    print("Verificación de paridad del pipeline (ADR-009 / ADR-010)\n")
    configs = cargar_configs()
    if len(configs) == len(CELDAS_OFICIALES):
        verificar_configs(configs)
        etapas, rutas_prompts = verificar_etapas_y_prompts(configs)
        verificar_prompts_de_rol(etapas, rutas_prompts)
        verificar_bm25(etapas)
        # Las corridas se cargan con el mismo código que usan los orquestadores;
        # el repo satélite sólo tiene que existir, no se escribe nada en él.
        with tempfile.TemporaryDirectory() as repo:
            corridas = cargar_corridas(Path(repo))
            verificar_prompts_identicos(corridas)
            verificar_servidor_mcp(corridas)
            comandos = _comandos_por_celda(corridas)
            verificar_recuperacion_web(comandos)
            verificar_confinamiento(comandos)
            verificar_contenedor(comandos, corridas)
    verificar_corpus()

    print()
    if _fallas:
        print(f"PARIDAD ROTA: {len(_fallas)} de {_total} chequeos fallaron:")
        for f in _fallas:
            print(f"  - {f}")
        return 1
    print(f"Paridad verificada ({_total} chequeos): las 4 celdas sólo difieren en "
          f"los factores del 2×2.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
