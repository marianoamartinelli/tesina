# Tesina — Modelo vs. contexto

**Estudio comparativo del impacto del LLM y del conocimiento de dominio en la generación
de código por agentes de IA.** Experimento factorial 2×2 (modelo Claude/GPT × sin/con RAG
sobre corpus de BIPs y EIPs) usando como caso de estudio un exchange de criptomonedas
centralizado y simplificado.

- **Alumno:** Mariano Alex Martinelli — Facultad de Informática, UNLP.
- **Directores:** Dra. Claudia Pons, Dr. Matías Urbieta.

## Estado del proyecto

Hitos **H0–H5 completos**: spec congelada en el tag `spec-v1.2` (57 HUs, 693 AT-ids),
protocolo experimental pre-registrado (ADR-004, hoy v1.7), corpus RAG de 9 documentos con
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

**Corrida pre-piloto (ADR-018), 2026-08-23/24 — completa.** Antes de la piloto se corrió
una verificación end-to-end de todos los componentes sobre un **universo reducido** de la
spec (6 HU de backend —registro, login y la épica 06 completa, que es la que fuerza el
RAG— y 2 de cliente), en las dos familias, con `effort high`. **Las 6 etapas cerraron con
sus 6 smokes de avance** y sin una sola intervención de las categorías 1–8 del protocolo.
Es la primera vez en el proyecto que los CLI de agente ejecutan etapas, que la suite de
ATs corre contra un sistema real, que el agente evaluador white-box se ejecuta y que se
miden las métricas estáticas.

Resultado: **27 hallazgos** ([`runs/pre-piloto/hallazgos.md`](runs/pre-piloto/hallazgos.md))
y **cinco ADRs** (018–022), con `protocolo.md` de v1.2 a **v1.5** y la paridad de 117 a
**143 chequeos**. Los que habrían roto la piloto: el sandbox nativo de Codex dejaba al
agente B **sin shell** dentro del contenedor sin cortar la corrida (ADR-019); el build de
los clientes **falla en el host** porque `node_modules` es del contenedor, lo que en H8
habría hecho fallar los 465 ATs por la plataforma del evaluador (ADR-021); el readiness
probe del reinicio ataba los **21 ATs de persistencia** a la épica 03; `--no-summary`
suprimía en silencio la escritura del CSV de resultados; y las métricas estáticas contaban
la spec y los lockfiles como código del agente — 32 648 loc contra 5 301 reales (ADR-022).

Tres datos que quedan para decidir antes de H7: **ninguna de las dos familias consultó el
corpus** en ninguna etapa (el factor RAG mediría disponibilidad y no uso); el universo
reducido consumió **USD 142** en A, lo que obliga a revisar el supuesto de consumo con el
que ADR-016 quitó los topes; y las dos implementaciones dieron **idéntico black-box**
(51 pasa / 3 falla / 2 skip) pero A escribió **2,3× más código** que B.

**Cierre de la pre-piloto (2026-09-06):** dos corridas de control mostraron que B **sí
puede delegar** y que el `--json` de Codex no registra a sus subagentes (H-23 corrige
H-22; **ADR-023**, Propuesto, persiste los rollouts en los logs). Las rúbricas web y del
rol revisor se ensayaron sobre B (10/11 y 35/36) y dejaron los huecos del instrumento
(H-24, H-26); la mobile no tiene emulador donde correr (H-25). La matriz queda en
**38 de 44**, la checklist H6 en **18 de 24**. El mismo día el tesista cerró las
decisiones pendientes (**ADR-024**: `spec-v1.2` con el rate limiting de `/auth/*` fijado;
**ADR-025**: protocolo **v1.6** con RAG disponible e instruido, `duracion_min` no-métrica,
suscripción con continuación estándar y emulador Android para la rúbrica mobile) y
ratificó ADR-023. Paridad en **146 chequeos**. La misma noche, **ADR-026**: la evaluación
pasa a estar gestionada íntegramente por agentes —todo paso con juicio lo ejecuta un
**agente tercero** (Grok Build, `grok-4.6`) en dos pasadas independientes más un
arbitraje por agente; el tesista opera y no emite veredictos— y el protocolo queda en
**v1.7**.

**Pre-piloto-2 (2026-09-06/07) — completa** ([`runs/pre-piloto-2/`](runs/pre-piloto-2/README.md)).
Segunda corrida descartable sobre el mismo universo reducido, lanzada en modo autónomo con
todo lo decidido el 2026-09-06. Las dos familias generaron sus tres etapas (B con dos
cortes por el límite de uso de Codex y continuación con `--desde-paso`) y **la evaluación
corrió entera por agentes en las dos celdas**: 5 instrumentos × 2 pasadas + arbitraje,
rúbrica mobile sobre el emulador por primera vez. Con la instrucción de ADR-025 D1 las dos
familias **sí consultaron el corpus** (25 y 17 consultas; en la primera pre-piloto, 0).
Black-box 53/3 y 52/4, white-box 22/22 en ambas; A escribió 11 468 loc contra 5 825 de B.
El juez concordó consigo mismo en 8 de los 10 circuitos; las discrepancias
reales las resolvió el arbitraje con evidencia. **11 hallazgos** más
([`runs/pre-piloto-2/hallazgos.md`](runs/pre-piloto-2/hallazgos.md)): los rollouts de B
muestran 3 subagentes por invocación que consumen más que el thread principal; los topes
que ADR-016 dio por inexistentes aparecieron en Codex (~30 min por ventana de 5 h) y en
Grok (pool semanal); la suite se frenaba sola con el rate limit de `spec-v1.2`. Checklist
H6 en **20 de 24**. Queda abierta la re-pre-registración de la rúbrica del rol revisor
(H-26) y la decisión de correr `piloto-01` como estaba previsto o pasar a H7.

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
| 🎓 | [Avance para directores](https://claude.ai/code/artifact/080ad423-0e1c-4238-abf0-f77769208a9b) | Estado del proyecto para la dirección (2026-09-07): diseño 2×2, método, lo que midieron las dos pre-pilotos y las decisiones abiertas. Reemplaza al artifact de julio, que ya no es accesible desde esta cuenta. |
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
