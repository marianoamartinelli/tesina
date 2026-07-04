# ADR-001 — Implementaciones generadas en repos separados por corrida

- **Estado:** Aceptado
- **Fecha:** 2026-07-04

## Contexto

Cada una de las 4 corridas del factorial 2×2 (más la piloto) produce una implementación
completa del exchange. El historial de commits que genera el agente durante la corrida
es un **dato experimental primario** (secuencia de construcción, correcciones tras
intervenciones, patrones de fallo). Además, el aislamiento experimental exige que el
agente no pueda leer el análisis de otras corridas, el journal del tesista ni el
tooling de evaluación: sólo la spec.

Alternativas consideradas: (a) carpetas dentro de este repo, (b) submódulos git,
(c) repos independientes por corrida.

## Decisión

Cada corrida se ejecuta en un **repositorio git independiente y limpio** (p. ej.
`tesina-run-a-sin-rag`), que al inicio contiene únicamente la spec pinneada al commit
del tag `spec-v1.0`. Este repo central los referencia desde
`runs/<run-id>/manifest.yaml` por URL + hash del commit inicial y final.

## Consecuencias

- El agente trabaja sin contaminación de contexto; el entorno de las 4 corridas es
  idéntico y auditable.
- El historial de commits de cada corrida queda intacto como dato del experimento y
  puede analizarse por separado (frecuencia, tamaño, mensajes, reversiones).
- Costo operativo: crear y administrar 5+ repos; mitigado con el manifest por corrida
  que centraliza las referencias en este repo.
- Los repos de corrida son **de sólo lectura una vez finalizada la corrida**: cualquier
  corrección posterior a la evaluación invalida la medición.
