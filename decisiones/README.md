# Decisiones (ADRs)

Registro de decisiones estructurales del proyecto, en formato Architecture Decision
Record. Cada ADR es **inmutable una vez aceptado**: si una decisión se revierte o
cambia, se escribe un ADR nuevo que la reemplaza y se actualiza el estado del viejo a
`Reemplazado por ADR-NNN` (sin reescribir su contenido).

## Convención

- Archivo: `ADR-NNN-titulo-en-kebab-case.md`, numeración secuencial de tres dígitos.
- Estructura: **Estado** (Propuesto/Aceptado/Reemplazado) · **Fecha** · **Contexto** ·
  **Decisión** · **Consecuencias**.
- Ámbito: decisiones que condicionan el experimento o la estructura del trabajo
  (metodología, herramientas, protocolo, alcance). Las observaciones del día a día van
  a `journal/`, no acá.

## Índice

| ADR | Título | Estado |
|-----|--------|--------|
| [ADR-001](ADR-001-implementaciones-en-repos-separados.md) | Implementaciones generadas en repos separados por corrida | Aceptado |
| [ADR-002](ADR-002-tesis-en-latex.md) | Documento de tesina en LaTeX versionado en el repo | Aceptado |
| [ADR-003](ADR-003-registro-exhaustivo-para-metaanalisis.md) | Registro exhaustivo: journal por sesión + ADRs + manifests | Aceptado |
