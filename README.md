# Tesina — Modelo vs. contexto

**Estudio comparativo del impacto del LLM y del conocimiento de dominio en la generación
de código por agentes de IA.** Experimento factorial 2×2 (modelo Claude/GPT × sin/con RAG
sobre corpus de BIPs y EIPs) usando como caso de estudio un exchange de criptomonedas
centralizado y simplificado.

- **Alumno:** Mariano Alex Martinelli — Facultad de Informática, UNLP.
- **Directores:** Dra. Claudia Pons, Dr. Matías Urbieta.

## Mapa del repositorio

| Carpeta       | Contenido                                                                    |
|---------------|------------------------------------------------------------------------------|
| `spec/`       | Especificación funcional del exchange (épicas + HUs + criterios de aceptación). Input común de las 4 corridas y holdout de evaluación. |
| `propuesta/`  | Documentos formales de la propuesta de tesina (.docx).                        |
| `decisiones/` | ADRs: decisiones estructurales del proyecto, numeradas e inmutables.          |
| `journal/`    | Bitácora fechada de sesiones de trabajo (materia prima del meta-análisis).    |
| `corpus/`     | Corpus curado de BIPs/EIPs para las condiciones con RAG.                      |
| `pipeline/`   | Configuración y código del harness de agentes (Claude Agent SDK / OpenAI Agents SDK). |
| `evaluacion/` | Harness de evaluación: suite de tests de aceptación black-box y rúbricas.     |
| `runs/`       | Un directorio por corrida: manifest, log de intervenciones, métricas. Las implementaciones generadas viven en **repos separados** referenciados desde cada manifest. |
| `analisis/`   | Dataset comparativo y análisis de resultados.                                 |
| `tesis/`      | Documento final en LaTeX, un archivo por capítulo.                            |

El plan de hitos vive en [ROADMAP.md](ROADMAP.md). Las convenciones de trabajo, en
[CLAUDE.md](CLAUDE.md).
