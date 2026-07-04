# Tesis — documento final (LaTeX)

Un archivo por capítulo en `capitulos/`; bibliografía en `bibliografia.bib` (BibTeX).
Ver ADR-002. Si la Facultad exige plantilla propia, se adapta el preámbulo de
`main.tex` manteniendo la separación por capítulos.

## Compilar

```sh
latexmk -pdf -output-directory=build main.tex
```

## Estado de capítulos

| Cap. | Archivo | Depende de | Estado |
|------|---------|-----------|--------|
| 1 | `capitulos/01-introduccion.tex` | — | esqueleto |
| 2 | `capitulos/02-estado-del-arte.tex` | — (arrancable ya) | esqueleto |
| 3 | `capitulos/03-caso-de-estudio.tex` | H1 (spec freeze) | esqueleto |
| 4 | `capitulos/04-diseno-experimental.tex` | H2 (protocolo) | esqueleto |
| 5 | `capitulos/05-infraestructura.tex` | H3–H5 | esqueleto |
| 6 | `capitulos/06-resultados.tex` | H7–H8 | esqueleto |
| 7 | `capitulos/07-analisis-y-discusion.tex` | H9 | esqueleto |
| 8 | `capitulos/08-conclusiones.tex` | H9 | esqueleto |
