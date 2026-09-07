# Evaluación por agentes sobre la pre-piloto (ADR-026) — primera ejecución

Salidas del **agente evaluador tercero** (Grok Build `grok-4.6`) sobre `pre-piloto-b`, la
noche del 2026-09-06, como verificación del circuito de ADR-026 antes de la pre-piloto-2:
dos pasadas independientes más arbitraje por agente (hallazgo H-27 de `../hallazgos.md`).

| Directorio | Qué es |
|---|---|
| `rol-revisor/pasada-1/`, `pasada-2/` | rúbrica completada, `resultados-rubrica-revisor.csv`, `censo-revision.csv`, sesiones del CLI |
| `rol-revisor/veredicto-final/` + `arbitraje.md` | veredicto de registro tras arbitrar las 2 discrepancias del censo |
| `rol-revisor/*.jsonl` | registro de cada sesión, con el formato del pipeline |

No entra en ningún dataset: la pre-piloto es descartable (ADR-018).
