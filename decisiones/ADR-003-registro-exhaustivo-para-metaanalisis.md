# ADR-003 — Registro exhaustivo: journal por sesión + ADRs + manifests

- **Estado:** Aceptado
- **Fecha:** 2026-07-04

## Contexto

El proyecto quiere someter a meta-análisis posterior no sólo los resultados de las
corridas sino el proceso completo: decisiones de configuración, cambios de rumbo,
sesiones de trabajo con agentes (incluidas las sesiones de asistencia con Claude),
y observaciones cualitativas. Sin disciplina de registro, esa materia prima se pierde.

## Decisión

Tres niveles de registro, todos versionados en este repo:

1. **`journal/`** — una entrada Markdown fechada por sesión de trabajo significativa
   (formato `AAAA-MM-DD-tema.md`): qué se hizo, qué se decidió, qué quedó pendiente,
   observaciones para el meta-análisis. Las sesiones con agentes de IA de asistencia
   también se registran.
2. **`decisiones/`** — ADRs numerados e inmutables para decisiones estructurales.
3. **`runs/<run-id>/`** — manifest + log de intervenciones + métricas por corrida,
   según las plantillas de `runs/`.

Complementariamente, los commits siguen la convención `area: descripción` (p. ej.
`spec: ...`, `journal: ...`, `adr: ...`, `runs: ...`, `tesis: ...`) para poder filtrar
el historial por tipo de cambio.

## Consecuencias

- El meta-análisis del proceso (capítulo de discusión) tiene fuentes primarias
  fechadas y citables.
- Costo: disciplina de cierre de sesión (~5 minutos por sesión). El asistente de IA
  tiene instruido en `CLAUDE.md` proponer la entrada de journal al cierre de cada
  sesión de trabajo.
