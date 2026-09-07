# pre-piloto-2 — segunda verificación end-to-end, tras los cambios del 2026-09-06

Corrida **descartable** (ADR-018), lanzada el 2026-09-06 en modo autónomo por pedido del
tesista, sobre el **mismo universo reducido** que [`../pre-piloto/`](../pre-piloto/README.md)
(`evaluacion/pre-piloto/alcance.yaml`, prompts de `pipeline/comun/prompts/prepiloto/`),
con `effort high` en las dos celdas y con RAG. No cuenta para el 2×2 ni cierra ítems de la
checklist H6 por sí sola.

Qué verifica, y que la primera pre-piloto no pudo:

| Cambio | Qué se mira |
|---|---|
| `spec-v1.2` (ADR-024) | los ATs de rate limiting de la suite ya no son `skip`; AT-10-01-06 en la rúbrica web |
| RAG disponible e instruido (ADR-025 D1) | `consulta_rag` por celda y etapa, contra los 0 de la primera pre-piloto (H-12) |
| Rollouts de B persistidos (ADR-023) | fan-out real de B, tokens de subagentes, compactación (ítems 22 y 24 de la checklist) |
| Evaluación por agentes (ADR-026) | white-box en 2 pasadas + arbitraje, rúbricas web/mobile/rol revisor y alucinaciones, todo por Grok Build; concordancia entre pasadas |
| Emulador Android (ADR-025 D4) | la rúbrica mobile corre por primera vez |

| Archivo | Qué es |
|---|---|
| `manifest-a.yaml` / `manifest-b.yaml` | configuración exacta de cada celda (§1–4 antes de arrancar; §5–6 al cerrar) |
| `intervenciones-a.md` / `intervenciones-b.md` | log de intervenciones, clasificado |
| `logs/` | JSONL de las etapas, snapshots y sesiones del CLI, archivados al cerrar |
| `evaluacion/` | salidas de los agentes evaluadores por instrumento y pasada |
| `hallazgos.md` | defectos y decisiones que la corrida saca a la luz, y la tabla de resultados por instrumento y celda |
| `resultados-at-{a,b}.csv` / `metricas-estaticas-{a,b}.csv` | dato primario de black-box y métricas estáticas |

## Estado: cerrada el 2026-09-07

Las dos celdas generaron sus tres etapas (A sin cortes; B con dos cortes por límite de uso
y continuación con `--desde-paso`, INT-01/02) y se evaluaron enteras por agentes: 5
instrumentos × 2 pasadas + arbitraje por celda, todo por Grok Build. Resultados y
concordancia entre pasadas en [`hallazgos.md`](hallazgos.md) §Resultados; 11 hallazgos
(H2-01..11). Repos satélite congelados en `1570c97` (A) y `f4770bf` (B).

Qué respondió de la tabla de arriba: los ATs de rate limiting pasan sin `skip` en las dos
celdas; con RAG instruido las dos familias consultan el corpus (25 y 17 consultas contra 0
en la primera); los rollouts muestran 3 subagentes por invocación de B (44 rollouts) y
cierran el ítem 24 de la checklist; los 10 circuitos de evaluación produjeron veredicto con
evidencia; la rúbrica mobile corrió sobre el emulador en las dos celdas.
