#!/usr/bin/env bash
# medir.sh — métricas estáticas pre-registradas (H5) sobre un componente de un repo satélite.
# Ver criterios y versiones pinneadas en README.md (mismo directorio).
#
# Uso:
#   ./medir.sh <ruta_componente> <run_id> <componente> [csv_salida]
#
#   ruta_componente : directorio a medir (subárbol del repo satélite congelado)
#   run_id          : a-sin-rag | a-con-rag | b-sin-rag | b-con-rag | piloto-01
#   componente      : backend | cliente-web | cliente-mobile | total
#   csv_salida      : (opcional) CSV al que anexar; default: ./metricas-estaticas.csv
#
# Requiere: cloc 2.10, lizard 1.23.0, jscpd 5.0.11, jq, python3.
# Aborta si las versiones difieren de las pinneadas (override: PERMITIR_VERSIONES=1).
# La columna cobertura_tests_propios_pct queda en NA: se completa a mano (README §5).

set -euo pipefail
export LC_ALL=C   # separador decimal estable (punto) en awk/printf

# ---------- versiones pinneadas (README §1/§6) ----------
CLOC_PIN="2.10"
LIZARD_PIN="1.23.0"
JSCPD_PIN="5.0.11"

# ---------- exclusiones pre-registradas (README §1.1) ----------
EXCL_DIRS="node_modules,.git,dist,build,out,coverage,vendor,Pods,__pycache__,.next,.expo,target,generated"

# ---------- argumentos ----------
if [ $# -lt 3 ]; then
  echo "Uso: $0 <ruta_componente> <run_id> <componente> [csv_salida]" >&2
  exit 1
fi
RUTA="$(cd "$1" && pwd)"
RUN_ID="$2"
COMPONENTE="$3"
CSV="${4:-./metricas-estaticas.csv}"
FECHA="$(date +%Y-%m-%d)"
NOTAS=""

# ---------- verificación de herramientas y versiones ----------
falta() { echo "ERROR: falta la herramienta '$1' (ver README §6)" >&2; exit 2; }
command -v cloc >/dev/null   || falta cloc
command -v lizard >/dev/null || falta lizard
command -v jscpd >/dev/null  || falta jscpd
command -v jq >/dev/null     || falta jq
command -v python3 >/dev/null || falta python3

CLOC_V="$(cloc --version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+' | head -1)"
LIZARD_V="$(lizard --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
JSCPD_V="$(jscpd --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"

check_pin() { # nombre actual pinneada
  if [ "$2" != "$3" ]; then
    if [ "${PERMITIR_VERSIONES:-0}" = "1" ]; then
      NOTAS="${NOTAS}version $1=$2 difiere de pin $3; "
      echo "AVISO: $1 $2 != pin $3 (override activo)" >&2
    else
      echo "ERROR: $1 $2 != version pinneada $3 (README §6). Override: PERMITIR_VERSIONES=1" >&2
      exit 3
    fi
  fi
}
check_pin cloc   "$CLOC_V"   "$CLOC_PIN"
check_pin lizard "$LIZARD_V" "$LIZARD_PIN"
check_pin jscpd  "$JSCPD_V"  "$JSCPD_PIN"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# ---------- 1) cloc: LOC efectivas, archivos, lenguaje principal ----------
cloc --json --quiet --exclude-dir="$EXCL_DIRS" "$RUTA" > "$TMP/cloc.json" || true
if jq -e '.SUM' "$TMP/cloc.json" >/dev/null 2>&1; then
  LOC="$(jq -r '.SUM.code' "$TMP/cloc.json")"
  ARCHIVOS="$(jq -r '.SUM.nFiles' "$TMP/cloc.json")"
  LENGUAJE="$(jq -r 'to_entries | map(select(.key != "header" and .key != "SUM"))
                     | max_by(.value.code) | .key' "$TMP/cloc.json")"
else
  LOC="NA"; ARCHIVOS="NA"; LENGUAJE="NA"; NOTAS="${NOTAS}cloc sin resultados; "
fi

# ---------- 2) lizard: CCN promedio y p90 por funcion (nearest-rank) ----------
LIZ_EXCL=()
IFS=',' read -ra _dirs <<< "$EXCL_DIRS"
for d in "${_dirs[@]}"; do LIZ_EXCL+=(-x "*/$d/*"); done
lizard --csv "${LIZ_EXCL[@]}" "$RUTA" > "$TMP/lizard.csv" 2>/dev/null || true
# CSV de lizard: NLOC,CCN,token,PARAM,length,location,... (sin encabezado; CCN = col 2)
read -r FUNCIONES CCN_AVG CCN_P90 <<< "$(
  cut -d, -f2 "$TMP/lizard.csv" | grep -E '^[0-9]+$' | sort -n | awk '
    { v[NR] = $1; s += $1 }
    END {
      if (NR == 0) { print "0 NA NA"; exit }
      idx = int(0.9 * NR); if (idx < 0.9 * NR) idx++      # nearest-rank: ceil(0.9*n)
      printf "%d %.2f %d\n", NR, s / NR, v[idx]
    }'
)"
[ "$FUNCIONES" = "0" ] && NOTAS="${NOTAS}lizard: 0 funciones (lenguaje no soportado?); "

# ---------- 3) jscpd: % de lineas duplicadas ----------
IGNORE_GLOBS="$(echo "$EXCL_DIRS" | python3 -c 'import sys; print(",".join("**/%s/**" % d for d in sys.stdin.read().strip().split(",")))')"
jscpd --silent --reporters json --output "$TMP/jscpd" --ignore "$IGNORE_GLOBS" "$RUTA" >/dev/null 2>&1 || true
if [ -f "$TMP/jscpd/jscpd-report.json" ]; then
  DUP="$(jq -r '.statistics.total.percentage // "NA"' "$TMP/jscpd/jscpd-report.json")"
  [ "$DUP" != "NA" ] && DUP="$(printf '%.2f' "$DUP")"
else
  DUP="NA"; NOTAS="${NOTAS}jscpd sin reporte; "
fi

# ---------- 4) dependencias directas (mapeo README §1.2; suma sobre manifiestos) ----------
DEPS_PROD=0; DEPS_DEV=0; MANIFIESTOS=0

# excluir manifiestos dentro de directorios excluidos
FIND_EXCL=()
for d in "${_dirs[@]}"; do FIND_EXCL+=(-not -path "*/$d/*"); done
encontrar() { # patron de nombre
  find "$RUTA" -name "$1" "${FIND_EXCL[@]}" 2>/dev/null
}

while IFS= read -r f; do
  [ -z "$f" ] && continue
  MANIFIESTOS=$((MANIFIESTOS + 1))
  DEPS_PROD=$((DEPS_PROD + $(jq -r '.dependencies    // {} | length' "$f")))
  DEPS_DEV=$(( DEPS_DEV  + $(jq -r '.devDependencies // {} | length' "$f")))
done < <(encontrar package.json)

while IFS= read -r f; do
  [ -z "$f" ] && continue
  MANIFIESTOS=$((MANIFIESTOS + 1))
  DEPS_PROD=$((DEPS_PROD + $(grep -cvE '^\s*(#|$|-r)' "$f" || true)))
done < <(encontrar requirements.txt)

while IFS= read -r f; do
  [ -z "$f" ] && continue
  MANIFIESTOS=$((MANIFIESTOS + 1))
  read -r p d <<< "$(python3 - "$f" <<'PY'
import sys
try:
    import tomllib            # python >= 3.11
except ImportError:
    import tomli as tomllib   # fallback: pip3 install tomli
with open(sys.argv[1], "rb") as fh:
    t = tomllib.load(fh)
prod = len(t.get("project", {}).get("dependencies", []))
dev = sum(len(v) for v in t.get("project", {}).get("optional-dependencies", {}).values())
dev += sum(len(g.get("dependencies", {}))
           for g in t.get("tool", {}).get("poetry", {}).get("group", {}).values())
print(prod, dev)
PY
)"
  DEPS_PROD=$((DEPS_PROD + p)); DEPS_DEV=$((DEPS_DEV + d))
done < <(encontrar pyproject.toml)

while IFS= read -r f; do
  [ -z "$f" ] && continue
  MANIFIESTOS=$((MANIFIESTOS + 1))
  DEPS_PROD=$((DEPS_PROD + $(awk '/^require[ (]/,/^\)/' "$f" | grep -cE '^\s+[a-z]' || true)))
  DEPS_PROD=$((DEPS_PROD - $(awk '/^require[ (]/,/^\)/' "$f" | grep -c '// indirect' || true)))
  NOTAS="${NOTAS}go.mod: sin distincion prod/dev; "
done < <(encontrar go.mod)

while IFS= read -r f; do
  [ -z "$f" ] && continue
  MANIFIESTOS=$((MANIFIESTOS + 1))
  read -r p d <<< "$(python3 - "$f" <<'PY'
import sys
try:
    import tomllib
except ImportError:
    import tomli as tomllib
with open(sys.argv[1], "rb") as fh:
    t = tomllib.load(fh)
print(len(t.get("dependencies", {})), len(t.get("dev-dependencies", {})))
PY
)"
  DEPS_PROD=$((DEPS_PROD + p)); DEPS_DEV=$((DEPS_DEV + d))
done < <(encontrar Cargo.toml)

if [ "$MANIFIESTOS" -eq 0 ]; then
  DEPS_PROD="NA"; DEPS_DEV="NA"
  NOTAS="${NOTAS}sin manifiesto reconocido (agregar mapeo al README §1.2 antes de contar a mano); "
fi

# ---------- 5) fila CSV ----------
HEADER="run_id,componente,fecha,lenguaje_principal,archivos,loc_efectivas,funciones,ccn_promedio,ccn_p90,duplicacion_pct,deps_directas_prod,deps_directas_dev,cobertura_tests_propios_pct,cloc_version,lizard_version,jscpd_version,notas"
[ -f "$CSV" ] || echo "$HEADER" > "$CSV"

NOTAS="${NOTAS%; }"
echo "$RUN_ID,$COMPONENTE,$FECHA,$LENGUAJE,$ARCHIVOS,$LOC,$FUNCIONES,$CCN_AVG,$CCN_P90,$DUP,$DEPS_PROD,$DEPS_DEV,NA,$CLOC_V,$LIZARD_V,$JSCPD_V,\"$NOTAS\"" >> "$CSV"

echo "OK: fila agregada a $CSV"
echo "    $RUN_ID/$COMPONENTE: loc=$LOC funciones=$FUNCIONES ccn_avg=$CCN_AVG ccn_p90=$CCN_P90 dup=$DUP% deps=$DEPS_PROD+$DEPS_DEV"
echo "Recordatorio: completar cobertura_tests_propios_pct a mano (README §5)."
