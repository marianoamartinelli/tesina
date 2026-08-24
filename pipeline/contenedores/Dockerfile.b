# Capa del harness B — Codex CLI. ADR-015 Decisión 2.
#
# Espejo exacto de `Dockerfile.a`: misma base, misma estructura, sólo cambia el
# paquete del CLI. Cualquier divergencia entre estos dos archivos que no sea el
# nombre del paquete es una asimetría del factor pipeline.
#
# Build:
#   docker build -f Dockerfile.base -t tesina/agente-base:<tag> .
#   docker build -f Dockerfile.b --build-arg BASE_TAG=<tag> \
#                --build-arg VERSION_CLI=0.146.0 -t tesina/agente-b:<tag> .
#
# `auth.json` NO va en la imagen: se monta read-only en runtime (ADR-015
# Decisión 3). Codex lo busca en `CODEX_HOME`, que el orquestador apunta al
# montaje.
#
# `CODEX_HOME` tiene que existir en la imagen y ser del usuario `agente` **antes**
# del bind-mount. Si no existe, docker crea el directorio padre del archivo montado
# como `root:root 755`, y `codex exec` muere en el arranque con
# `failed to initialize in-process app-server client: Permission denied (os error 13)`:
# necesita escribir en `CODEX_HOME` (aliases de PATH, estado de sesión), no sólo leer
# `auth.json`. Medido el 2026-08-23 en la pre-piloto (runs/pre-piloto/hallazgos.md H-03).

ARG BASE_TAG=dev
FROM tesina/agente-base:${BASE_TAG}

ARG VERSION_CLI
RUN test -n "${VERSION_CLI}" || (echo "VERSION_CLI es obligatorio" >&2; exit 1)

USER root
RUN npm install -g "@openai/codex@${VERSION_CLI}"
RUN mkdir -p /home/agente/.codex && chown agente:agente /home/agente/.codex
USER agente

ENTRYPOINT ["codex"]
