#!/usr/bin/env bash
# Crea el repo satélite de una corrida (protocolo §3 paso 1).
#
# El repo satélite es el workspace del agente: contiene **únicamente** la spec
# pinneada al tag, extraída con `git archive` para que ni el historial ni ningún otro
# árbol de la tesina (evaluacion/, pipeline/, runs/, decisiones/, journal/) llegue al
# contexto del agente. Se le hace `git init` propio: el historial que quede ahí es
# producto del agente y dato del experimento.
#
# Layout que crea, y que el orquestador da por supuesto — el JSONL va a
# `<repo>/../logs/`, así que el repo NO puede colgar directamente de un directorio
# compartido con otras corridas:
#
#   <destino>/
#     tesina-run-<id>/   repo satélite (git init + commit inicial con la spec)
#     logs/              lo crea el orquestador en la primera etapa
#
# Uso:
#   pipeline/crear-repo-satelite.sh <id-corrida> <destino> [tag-de-spec]
#
# Ejemplo:
#   pipeline/crear-repo-satelite.sh pre-piloto-a ~/Desktop/projects/tesina-runs/pre-piloto-a
#
# Imprime el hash del commit del tag de spec y el del commit inicial del satélite:
# los dos van al manifest (§2 `spec.commit`, §4 `repo.commit_inicial`) antes de que
# el agente ejecute nada.

set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "uso: $0 <id-corrida> <destino> [tag-de-spec]" >&2
  exit 2
fi

ID="$1"
DESTINO="$2"
TAG="${3:-spec-v1.1}"
RAIZ_TESINA="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="$DESTINO/tesina-run-$ID"

if [[ -e "$REPO" ]]; then
  echo "error: $REPO ya existe; una corrida arranca sobre un repo limpio" >&2
  exit 1
fi

COMMIT_SPEC="$(git -C "$RAIZ_TESINA" rev-parse "$TAG^{commit}")"

mkdir -p "$REPO"
# Sólo `spec/`: el resto del árbol de la tesina no entra al repo satélite.
git -C "$RAIZ_TESINA" archive "$TAG" spec | tar -x -C "$REPO"

git -C "$REPO" init -q -b main

# Identidad de commit **fijada y neutra**, idéntica en las 4 celdas.
#
# El prompt de sistema le pide al agente commitear a medida que avanza, pero un
# contenedor recién creado no tiene identidad git: sin esto, el primer `git commit`
# falla con `Author identity unknown` y cada agente inventa la suya. Medido en la
# pre-piloto (hallazgo H-13): A commiteó como «Agente Implementador <agente@local>» y
# B como «Codex <codex@local>» — o sea que el autor de los commits **revela el modelo
# generador**, y el historial, que es dato del experimento (métricas estáticas, rúbrica
# del rol revisor), deja de ser comparable entre celdas.
#
# Va en el repo satélite y no en la imagen a propósito: así viaja con la corrida, es
# la misma para las dos familias por construcción y no invalida el digest de ninguna
# imagen ya registrada en un manifest.
git -C "$REPO" config user.name "agente"
git -C "$REPO" config user.email "agente@tesina.local"

git -C "$REPO" add -A
git -C "$REPO" -c user.name="pipeline" -c user.email="pipeline@tesina.local" \
    commit -q -m "spec: $TAG ($COMMIT_SPEC) — estado inicial del repo satélite $ID"

COMMIT_INICIAL="$(git -C "$REPO" rev-parse HEAD)"
ARCHIVOS="$(git -C "$REPO" ls-files | wc -l | tr -d ' ')"

echo "repo satélite:    $REPO"
echo "spec.tag:         $TAG"
echo "spec.commit:      $COMMIT_SPEC"
echo "repo.commit_inicial: $COMMIT_INICIAL"
echo "archivos:         $ARCHIVOS (todos bajo spec/)"
