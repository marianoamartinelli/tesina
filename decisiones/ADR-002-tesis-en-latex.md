# ADR-002 — Documento de tesina en LaTeX versionado en el repo

- **Estado:** Aceptado
- **Fecha:** 2026-07-04

## Contexto

El documento final debe redactarse a lo largo de meses, en paralelo con el experimento,
y el pedido explícito del proyecto es que todo cambio quede versionado con diffs
legibles para meta-análisis. Alternativas: LaTeX, Markdown + Pandoc, Word/Google Docs.

## Decisión

La tesina se redacta en **LaTeX**, en `tesis/`, con un archivo `.tex` por capítulo y
bibliografía en BibTeX (`bibliografia.bib`). Los artefactos de compilación no se
versionan (ver `.gitignore`). Si la Facultad de Informática (UNLP) exige una plantilla
específica, se adopta esa plantilla manteniendo la separación por capítulos.

## Consecuencias

- Diffs por commit legibles a nivel de párrafo; historial completo de la redacción.
- Control tipográfico y de bibliografía de calidad académica (BibTeX ya alineado con
  las referencias de la propuesta).
- Requiere toolchain local (`latexmk` / TeX Live); documentado en `tesis/README.md`.
