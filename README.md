# Tesina — Modelo vs. contexto

**Estudio comparativo del impacto del LLM y del conocimiento de dominio en la generación
de código por agentes de IA.** Experimento factorial 2×2 (modelo Claude/GPT × sin/con RAG
sobre corpus de BIPs y EIPs) usando como caso de estudio un exchange de criptomonedas
centralizado y simplificado.

- **Alumno:** Mariano Alex Martinelli — Facultad de Informática, UNLP.
- **Directores:** Dra. Claudia Pons, Dr. Matías Urbieta.

## Estado del proyecto

Hitos **H0–H5 completos**: spec congelada en el tag `spec-v1.1` (57 HUs, 693 AT-ids),
protocolo experimental pre-registrado (ADR-004), corpus RAG de 9 documentos con
manifest + SHA-256, pipeline de agentes con paridad A/B verificable (ADR-009, que
reemplaza a ADR-005) y harness de evaluación: suite black-box más agente evaluador
white-box (ADR-007) para los ATs no automatizables (521 AT-ids backend + 78 web /
94 mobile con rúbrica).

Próximo hito: **H6 — corrida piloto**, que valida el pipeline end-to-end antes de las
4 corridas oficiales de H7. Plan completo de hitos en [ROADMAP.md](ROADMAP.md).

**En curso (2026-08-23):** ADR-009 cambió la base de los harness —dejan de construirse
sobre los SDK de agentes y pasan a ser los CLI de cada proveedor (`claude -p` y
`codex exec`), con los model IDs re-pinneados a `claude-opus-5` / `gpt-5.6-sol`—. El
código de `pipeline/` ya está reescrito sobre esa base (orquestadores de roles, RAG como
servidor MCP stdio único, **139 chequeos de paridad**); los `correr.py` sobre SDK quedan
en el árbol como camino de vuelta hasta que la piloto valide el reemplazo. De la deuda de
proceso de [`runs/piloto-01/checklist-h6.md`](runs/piloto-01/checklist-h6.md) hay **16 de
24 ítems cerrados** —protocolo **v1.2**, partición 465/56 de los ATs backend, rúbrica del
rol revisor, manifest de `piloto-01`, agentes en contenedores y orden de las 4 celdas
sorteado—, con ADR-011/012/013 aceptados el 2026-08-17 y ADR-014/015/016 el 2026-08-23.
La autenticación de las dos familias quedó resuelta y verificada (**ADR-017**: A por
`CLAUDE_CODE_OAUTH_TOKEN`, B por bind-mount de su `auth.json`).

**Corrida pre-piloto (ADR-018), 2026-08-23.** Antes de la piloto corre una verificación
end-to-end de todos los componentes sobre un **universo reducido** de la spec —6 HU de
backend (registro, login y la épica 06 completa, que es la que fuerza el RAG) y 2 de
cliente—, en las dos familias y con `effort high`. Estado, evidencia por componente y
defectos en [`runs/pre-piloto/`](runs/pre-piloto/). **Es la primera vez que los CLI de
agente ejecutan etapas del pipeline**, y ya encontró cuatro defectos de ambiente que la
piloto habría pagado caro: `codex exec` no arrancaba en el contenedor por `CODEX_HOME` no
escribible; el sandbox nativo de Codex dejaba al agente B **sin shell** dentro del
contenedor sin cortar la corrida (**ADR-019**: el confinamiento pasa a ser el contenedor
en las dos familias); el tope efectivo de A no es de presupuesto sino el rate limit de 5
horas sin overage; y el nodo on-chain del host no es alcanzable desde el contenedor. Se
escribió además el runner del **agente evaluador white-box**, que cerró el
`PENDIENTE-ARRANQUE` de su invocación.

## Mapa del repositorio

| Carpeta       | Contenido                                                                    |
|---------------|--------------------------------------------------------------------------------|
| `spec/`       | Especificación funcional del exchange (épicas + HUs + criterios de aceptación). Input común de las 4 corridas y holdout de evaluación. |
| `propuesta/`  | Documentos formales de la propuesta de tesina (.docx).                        |
| `decisiones/` | ADRs: decisiones estructurales del proyecto, numeradas e inmutables.          |
| `journal/`    | Bitácora fechada de sesiones de trabajo (materia prima del meta-análisis).    |
| `corpus/`     | Corpus curado de BIPs/EIPs para las condiciones con RAG.                      |
| `pipeline/`   | Configuración y código del harness de agentes: orquesta los CLI de cada proveedor (Claude Code / Codex CLI) con roles implementador/revisor, según ADR-009. El pipeline anterior sobre SDK sigue versionado como camino de vuelta. |
| `evaluacion/` | Harness de evaluación: suite black-box, agente evaluador white-box (ADR-007) y rúbricas. |
| `runs/`       | Un directorio por corrida: manifest, log de intervenciones, métricas. Las implementaciones generadas viven en **repos separados** referenciados desde cada manifest. |
| `analisis/`   | Dataset comparativo y análisis de resultados.                                 |
| `tesis/`      | Documento final en LaTeX, un archivo por capítulo.                           |

## Documentación en vivo (artifacts)

Además de los documentos en Markdown, el roadmap, cada hito cerrado y la infraestructura
técnica del proyecto tienen una página de referencia navegable, publicada como *artifact*
de claude.ai:

| | Artifact | Descripción |
|---|---|---|
| 🎓 | [Avance para directores](https://claude.ai/code/artifact/5bf48c1c-62a2-4d99-94fa-b8eb30b4aa4f) | Presentación visual del estado del proyecto para la dirección: diseño 2×2, hitos, vara de evaluación y decisiones abiertas. |
| 🧭 | [Roadmap y protocolo (hub)](https://claude.ai/code/artifact/064ea0c6-f229-4a71-b998-3d9bef9d719b) | Página central: enlaza el roadmap de hitos y el protocolo experimental. |
| 🧊 | [H1 — Spec freeze](https://claude.ai/code/artifact/13d3543f-2fa3-4144-991e-fbf625daf04e) | Snapshot del freeze de la especificación (`spec-v1.1`): alcance, convenciones y auditoría. |
| 📋 | [H2 — Protocolo](https://claude.ai/code/artifact/9950ffe5-3009-441c-8ce2-e6370e091e19) | Protocolo experimental pre-registrado: criterios de intervención, orden de construcción, presupuestos. |
| 📚 | [H3 — Corpus](https://claude.ai/code/artifact/c26967c0-6b61-440d-b647-d6aca6f9482b) | Curaduría del corpus RAG de BIPs/EIPs. |
| ⚙️ | [H4 — Pipeline](https://claude.ai/code/artifact/327d3e4e-e12d-4e14-8c79-b7b8de3287b0) | Configuración de los dos harness de agentes y verificación de paridad A/B. |
| 🧪 | [H5 — Harness](https://claude.ai/code/artifact/53690139-1893-4c56-ad47-af495f2e667e) | La vara de evaluación: suite black-box, agente white-box y rúbricas, con la partición de los 693 ATs. |
| 🔎 | [Doc técnica — Arquitectura RAG](https://claude.ai/code/artifact/d37185ee-517c-407c-99d1-6161ae98d301) | Detalle de la arquitectura de recuperación usada en las condiciones "con RAG". |
| 🤖 | [Doc técnica — Pipelines A y B](https://claude.ai/code/artifact/c3407398-8438-47f7-8087-6be55db8a62b) | Detalle de la implementación de ambos harness de agentes. |
| ⚖️ | [Doc técnica — Harness de evaluación](https://claude.ai/code/artifact/f489fda2-e18c-48a3-ba95-3ea7fad71cac) | Detalle del harness, incluido el agente evaluador white-box (ADR-007). |

Estos artifacts son privados por defecto (compartibles bajo demanda) y se actualizan a
medida que avanza el proyecto — ver [CLAUDE.md](CLAUDE.md) para el criterio de cuándo
refrescar esta tabla.

## Convenciones de trabajo

El protocolo de registro (ADRs, journal, manifests de corridas) y las convenciones de la
especificación viven en [CLAUDE.md](CLAUDE.md).
