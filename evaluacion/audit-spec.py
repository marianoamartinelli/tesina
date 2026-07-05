#!/usr/bin/env python3
"""Auditoría mecánica de la spec (H1 — spec freeze)."""
import re
import sys
from pathlib import Path
from collections import defaultdict

SPEC = Path("/Users/martinelli/Desktop/projects/tesina/spec")
problems = []
infos = []


def problem(msg):
    problems.append(msg)


def info(msg):
    infos.append(msg)


# ---------- recolección ----------
hu_files = sorted(SPEC.glob("[0-9][0-9]-*/HU-*.md"))
epic_dirs = sorted(d for d in SPEC.iterdir() if d.is_dir() and re.match(r"\d{2}-", d.name))

hu_ids_from_files = {}   # 'HU-03-03' -> path
at_defs = {}             # 'AT-03-03-01' -> path
at_defs_per_hu = defaultdict(list)

RE_AT_DEF = re.compile(r"\[(AT-\d{2}-\d{2}-\d{2}[a-z]?)\]")
RE_AT_ANY = re.compile(r"\bAT-\d{2}-\d{2}-\d{2}[a-z]?\b")
RE_HU_ANY = re.compile(r"\bHU-\d{2}-\d{2}\b")
RE_INV = re.compile(r"\bINV-(\d+)\b")
RE_CODE = re.compile(r"`([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)`")

# 1. nombre de archivo vs encabezado
for f in hu_files:
    m = re.match(r"(HU-(\d{2})-(\d{2}))-", f.name)
    if not m:
        problem(f"{f}: nombre de archivo no matchea HU-EE-SS-*")
        continue
    hu_id, ep, seq = m.group(1), m.group(2), m.group(3)
    if not f.parent.name.startswith(ep + "-"):
        problem(f"{f}: épica del nombre ({ep}) no coincide con carpeta {f.parent.name}")
    hu_ids_from_files[hu_id] = f
    text = f.read_text(encoding="utf-8")
    first_line = text.splitlines()[0] if text else ""
    if not first_line.startswith(f"# {hu_id}"):
        problem(f"{f.name}: primera línea no empieza con '# {hu_id}': {first_line!r}")

    # 2. definiciones de AT en el archivo
    defs = RE_AT_DEF.findall(text)
    seen_here = set()
    for at in defs:
        at_ep, at_hu, at_nn = at[3:5], at[6:8], at[9:11]
        suffix = at[11:] if len(at) > 11 else ""
        if (at_ep, at_hu) != (ep, seq):
            # referencia con corchetes a AT de otra HU: contar como referencia, no def
            continue
        if at in seen_here:
            # repetido dentro del archivo: sólo es def la primera; puede ser re-mención
            continue
        seen_here.add(at)
        if at in at_defs:
            problem(f"AT duplicado entre archivos: {at} en {at_defs[at].name} y {f.name}")
        at_defs[at] = f
        at_defs_per_hu[hu_id].append((int(at_nn), suffix))

# 3. secuencia de AT por HU (slots 01..N sin huecos; sufijos a,b,c contiguos)
for hu, entries in sorted(at_defs_per_hu.items()):
    slots = defaultdict(list)
    for nn, suffix in entries:
        slots[nn].append(suffix)
    max_nn = max(slots)
    missing = [n for n in range(1, max_nn + 1) if n not in slots]
    if missing:
        problem(f"{hu}: slots AT faltantes {missing} (máx {max_nn})")
    for nn, suffixes in sorted(slots.items()):
        sufs = sorted(s for s in suffixes if s)
        has_base = "" in suffixes
        if sufs:
            # con base: variantes contiguas desde 'b' (el base cuenta como primera);
            # sin base: variantes contiguas desde 'a'
            start = 'b' if has_base else 'a'
            expected = [chr(ord(start) + i) for i in range(len(sufs))]
            if sufs != expected:
                problem(f"{hu}: sufijos de AT-..-{nn:02d} no contiguos desde '{start}': {sufs} (base: {has_base})")

# HUs sin ningún AT
for hu, f in hu_ids_from_files.items():
    if hu not in at_defs_per_hu:
        problem(f"{hu} ({f.name}): no define ningún AT")

# ---------- referencias en TODO el árbol spec ----------
all_md = sorted(SPEC.rglob("*.md"))
catalog_codes = set()
err_file = SPEC / "00-fundaciones" / "modelo-de-errores.md"
err_text = err_file.read_text(encoding="utf-8")
for m in re.finditer(r"^\|\s*`([A-Z][A-Z0-9_]+)`\s*\|\s*\d{3}\s*\|", err_text, re.M):
    catalog_codes.add(m.group(1))

used_codes = defaultdict(set)  # code -> {files}
NON_ERROR_TOKENS = {
    # tokens ALL_CAPS con guión bajo que no son códigos de error
    "MAYUSCULAS_CON_GUION_BAJO",
    "PARTIALLY_FILLED",  # estado de orden
    "CONFIRMACIONES_REQUERIDAS",
}

for f in all_md:
    text = f.read_text(encoding="utf-8")
    rel = f.relative_to(SPEC)

    # referencias AT
    for at in set(RE_AT_ANY.findall(text)):
        if at not in at_defs:
            problem(f"{rel}: referencia a AT inexistente {at}")

    # referencias HU
    for hu in set(RE_HU_ANY.findall(text)):
        if hu not in hu_ids_from_files:
            problem(f"{rel}: referencia a HU inexistente {hu}")

    # referencias INV
    for n in set(RE_INV.findall(text)):
        if not (1 <= int(n) <= 8):
            problem(f"{rel}: referencia a INV-{n} fuera de INV-1..INV-8")

    # códigos de error usados
    for code in set(RE_CODE.findall(text)):
        if code in NON_ERROR_TOKENS:
            continue
        used_codes[code].add(str(rel))

# códigos usados que no están en catálogo (filtrar estados/constantes conocidos)
KNOWN_NON_CODES = set()
for code, files in sorted(used_codes.items()):
    if code not in catalog_codes:
        # heurística: si termina en _ERROR/_FAILED/etc o aparece como `code`, sospechoso
        info(f"token ALL_CAPS fuera de catálogo: {code} — en {sorted(files)[:4]}")

# códigos del catálogo nunca usados en épicas
for code in sorted(catalog_codes):
    uses = {f for f in used_codes.get(code, set()) if not f.startswith("00-")}
    if not uses:
        info(f"código de catálogo sin uso en épicas 01-11: {code}")

# ---------- READMEs de épica ----------
for d in epic_dirs:
    if d.name == "00-fundaciones":
        continue
    readme = d / "README.md"
    if not readme.exists():
        problem(f"{d.name}: falta README.md")
        continue
    rtext = readme.read_text(encoding="utf-8")
    hus_in_dir = {re.match(r"(HU-\d{2}-\d{2})", f.name).group(1) for f in d.glob("HU-*.md")}
    hus_in_readme = set(RE_HU_ANY.findall(rtext))
    for hu in sorted(hus_in_dir - hus_in_readme):
        problem(f"{d.name}/README.md: no lista {hu}")
    for hu in sorted(h for h in hus_in_readme if h.startswith(f"HU-{d.name[:2]}-") and h not in hus_in_dir):
        problem(f"{d.name}/README.md: lista {hu} que no existe en la carpeta")

# ---------- conteos ----------
print("=" * 70)
print(f"HUs: {len(hu_files)}   ATs definidos: {len(at_defs)}   Épicas: {len(epic_dirs)}")
print(f"Códigos en catálogo: {len(catalog_codes)}")
per_epic = defaultdict(int)
for at in at_defs:
    per_epic[at[3:5]] += 1
print("ATs por épica:", dict(sorted(per_epic.items())))
print("=" * 70)
if problems:
    print(f"\nPROBLEMAS ({len(problems)}):")
    for p in problems:
        print(f"  ✗ {p}")
else:
    print("\nSin problemas mecánicos.")
if infos:
    print(f"\nINFO ({len(infos)}):")
    for i in infos:
        print(f"  · {i}")
sys.exit(1 if problems else 0)
