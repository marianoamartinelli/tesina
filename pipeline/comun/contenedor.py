"""Envoltura en contenedor de la invocación al CLI — ADR-015.

Toda invocación de rol de las 4 celdas ocurre dentro de un contenedor, en las dos
familias, independientemente del sandbox nativo de cada CLI. Este módulo arma esa
envoltura **una sola vez**: los dos orquestadores la consumen sin parametrizar
nada propio, así que las diferencias entre A y B se reducen a la imagen y al
comando de su CLI — el resto (montajes, red, usuario, workdir) es idéntico por
construcción y verificable como tal.

Lo que el contenedor monta, y sólo eso:

- el **repo satélite** en `/repo`, read-write: es el workspace del agente;
- el **directorio de logs**, read-write: el JSONL del servidor MCP del RAG lo
  escribe un proceso que corre adentro (ver `MONTAJE_LOGS`);
- el **código del RAG** (`comun/`) y el **corpus**, read-only, sólo en celdas con
  RAG. `comun/` y no `pipeline/` entero: `config/` y `verificar_paridad.py` son
  instrumentos del experimento y el agente no los ve;
- las **credenciales** de la familia, read-only (ADR-015 Decisión 3).

`evaluacion/` NO se monta, en ninguna celda: es el holdout, y ese es el motivo por
el que ADR-015 cierra el ítem 11 de la checklist H6 — la no-exposición pasa a
sostenerla el mecanismo en vez del procedimiento (protocolo §9).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

RUNTIME = "docker"

# Tag de las imágenes, **único para las 4 celdas de una corrida**. Vive acá y no
# en la config por celda a propósito: si fuera por celda podría divergir, y dos
# celdas con toolchain distinto dejarían de ser comparables. Se fija por corrida
# y su digest efectivo se registra en el manifest (§3), con el mismo criterio que
# el pin del anvil: el tag es flotante, el digest no.
TAG = "piloto-01"

# Punto de montaje del repo satélite adentro. Coincide con el WORKDIR de
# `Dockerfile.base`: el agente ve `/repo` como su cwd, igual en las 4 celdas.
DIR_REPO = "/repo"

# Los logs se montan porque el servidor MCP del RAG corre **adentro** del
# contenedor: lo lanza el CLI como subproceso stdio, no el orquestador. Sin este
# montaje, `consulta_rag` escribiría su JSONL en el filesystem efímero del
# contenedor y se perdería al cerrar el paso — que es registro que ADR-003 exige.
DIR_LOGS = "/logs"

# Código del RAG, read-only: el servidor MCP corre adentro y necesita su propio
# fuente más `etapas.yaml`. Se montan **sólo** `comun/`, no `pipeline/` entero:
# `config/` (las 4 celdas) y `verificar_paridad.py` son instrumentos del
# experimento, no insumos del agente.
DIR_COMUN = "/pipeline/comun"

# Corpus RAG, read-only. Vive fuera de `pipeline/` (`corpus/documentos`), así que
# necesita su propio montaje: sin esto el servidor MCP levanta adentro con un
# corpus vacío.
#
# El destino **no es arbitrario**: `nucleo.cargar_rag` resuelve el corpus como
# `<etapas.yaml>/../../corpus/documentos`, y con `etapas.yaml` en `/pipeline/comun`
# eso da exactamente esta ruta. Montarlo en otro lado obligaría a parchear la
# resolución, que es código compartido con el host.
DIR_CORPUS = "/pipeline/corpus/documentos"

# Credenciales de suscripción, read-only (ADR-015 Decisión 3). Cada familia monta
# sólo la suya: el contenedor de A nunca ve las credenciales de B ni al revés.
CREDENCIALES = {
    "a": (Path.home() / ".claude" / ".credentials.json", "/home/agente/.claude/.credentials.json"),
    "b": (Path.home() / ".codex" / "auth.json", "/home/agente/.codex/auth.json"),
}

# Variables de entorno por familia. `CODEX_HOME` apunta al montaje para que el CLI
# encuentre `auth.json` sin que le pasemos un HOME distinto: ADR-009 Decisión 5
# preserva las credenciales a propósito, y `--ignore-user-config` ya se encarga de
# ignorar la config que viva ahí.
ENTORNO = {
    "a": {},
    "b": {"CODEX_HOME": "/home/agente/.codex"},
}


@dataclass(frozen=True)
class Montaje:
    """Un bind-mount. `ro=True` es read-only."""

    origen: Path
    destino: str
    ro: bool

    def a_flag(self) -> list[str]:
        modo = "ro" if self.ro else "rw"
        return ["-v", f"{self.origen}:{self.destino}:{modo}"]


def imagen(familia: str, tag: str = TAG) -> str:
    """Nombre de la imagen de una familia. `Dockerfile.a` / `Dockerfile.b`."""
    if familia not in ("a", "b"):
        raise ValueError(f"familia desconocida: {familia!r}")
    return f"tesina/agente-{familia}:{tag}"


def montajes(corrida, familia: str) -> list[Montaje]:
    """Montajes de una invocación, en orden estable.

    Idénticos entre familias salvo el archivo de credenciales, que es el único
    que no puede serlo. El corpus entra sólo si la celda tiene RAG: montarlo en
    las celdas sin RAG pondría el corpus al alcance de un agente que no debe
    tenerlo, que es exactamente el factor que el 2×2 manipula.
    """
    dir_comun = Path(__file__).resolve().parent
    ms = [
        Montaje(corrida.ruta_repo, DIR_REPO, ro=False),
        Montaje(corrida.ruta_log.parent, DIR_LOGS, ro=False),
    ]
    if corrida.rag_config is not None:
        ms.append(Montaje(dir_comun, DIR_COMUN, ro=True))
        ms.append(Montaje(corrida.rag_config.ruta_corpus, DIR_CORPUS, ro=True))
    origen, destino = CREDENCIALES[familia]
    ms.append(Montaje(origen, destino, ro=True))
    return ms


def envolver(comando_cli: list[str], corrida, familia: str,
             tag: str = TAG) -> list[str]:
    """`docker run …` que ejecuta `comando_cli` adentro del contenedor.

    - `--rm`: el contenedor es descartable; lo que persiste son los montajes.
    - `-i`: el prompt del paso sigue yendo por stdin (`nucleo.ejecutar_paso`).
    - `--network host` **no** se usa: red del contenedor, abierta pero propia.
      ADR-015 Decisión 4 deja la red abierta en la piloto —la necesitan
      `npm install` y `expo export`— y la piloto registra qué hosts se tocan.
    - `--entrypoint ""`: la imagen trae el CLI como entrypoint para uso manual,
      pero acá el comando completo lo arma el orquestador, que es quien conoce
      los flags de ADR-008/009/010.
    """
    flags: list[str] = [RUNTIME, "run", "--rm", "-i", "-w", DIR_REPO]
    for montaje in montajes(corrida, familia):
        flags += montaje.a_flag()
    for clave, valor in sorted(ENTORNO[familia].items()):
        flags += ["-e", f"{clave}={valor}"]
    flags += ["--entrypoint", "", imagen(familia, tag)]
    return flags + comando_cli


def traducir(ruta: Path | str, corrida) -> str:
    """Ruta del host → ruta equivalente adentro del contenedor.

    Necesaria porque el orquestador corre en el host y arma rutas del host, pero
    el comando se ejecuta adentro. Sin esto, `-C /Users/.../repo-satelite` o el
    `--log` del servidor MCP apuntarían a rutas que adentro no existen.
    """
    ruta = Path(ruta).resolve()
    dir_comun = Path(__file__).resolve().parent
    destinos = [(corrida.ruta_repo.resolve(), DIR_REPO),
                (corrida.ruta_log.parent.resolve(), DIR_LOGS),
                (dir_comun, DIR_COMUN)]
    if corrida.rag_config is not None:
        destinos.append((corrida.rag_config.ruta_corpus.resolve(), DIR_CORPUS))
    for origen, destino in destinos:
        try:
            relativa = ruta.relative_to(origen)
        except ValueError:
            continue
        return destino if str(relativa) == "." else f"{destino}/{relativa}"
    raise ValueError(
        f"la ruta {ruta} no cae bajo ningún montaje del contenedor: agregarla a "
        f"`montajes` o no pasarla al CLI (ADR-015 Decisión 5: el holdout no se monta)"
    )
