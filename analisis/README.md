# Análisis — dataset comparativo y resultados

Artefactos de los hitos H8–H9.

## Contenido

- **[`amenazas-validez.md`](amenazas-validez.md)** — registro consolidado de las
  amenazas a la validez ya pre-registradas (fuente, mitigación, estado); insumo
  directo del capítulo 4.

## Contenido previsto

- **`dataset/`** — dataset consolidado del experimento: una fila por (corrida × AT-id)
  para la tasa de aceptación, más tablas de intervenciones, alucinaciones y métricas
  estáticas por celda. Formato tabular versionable (CSV).
- **`notebooks/` o `scripts/`** — análisis de efectos principales (modelo, RAG),
  interacción, y desagregación por épica/componente.
- **`metaanalisis/`** — análisis del proceso a partir de `journal/`, ADRs y manifests
  (lo que pedía el registro exhaustivo de ADR-003).

Nada de este directorio debe ser visible para los agentes de las corridas (ADR-001).
