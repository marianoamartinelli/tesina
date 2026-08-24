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

ARG BASE_TAG=dev
FROM tesina/agente-base:${BASE_TAG}

ARG VERSION_CLI
RUN test -n "${VERSION_CLI}" || (echo "VERSION_CLI es obligatorio" >&2; exit 1)

USER root
RUN npm install -g "@openai/codex@${VERSION_CLI}"
USER agente

ENTRYPOINT ["codex"]
