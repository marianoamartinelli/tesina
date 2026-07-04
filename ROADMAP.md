# Roadmap de hitos

Estado: `[ ]` pendiente · `[~]` en curso · `[x]` completado. Cada hito cerrado se
registra en `journal/` y, si implicó decisiones estructurales, en `decisiones/`.

## Fase preparatoria (restante)

- [x] **H0 — Infraestructura del repo.** Estructura de versionado, ADRs, journal,
  plantillas de manifest, roadmap. *(2026-07-04)*
- [ ] **H1 — Spec freeze.** Auditoría final de la spec (consistencia de AT-ids,
  referencias cruzadas, precedencia de errores, invariantes) y tag `spec-v1.0`.
  A partir del tag, la spec es **inmutable** para el experimento: las 4 corridas
  reciben exactamente ese commit.
- [ ] **H2 — Protocolo experimental pre-registrado.** Documento que fija, antes de
  cualquier corrida: criterios de intervención humana (cuándo intervenir, cómo se
  clasifica según las 8 causas raíz de la propuesta), orden de construcción
  (backend → web → mobile), presupuestos por corrida (tokens/costo/tiempo), qué se
  registra y cómo. Se congela como ADR + documento en `evaluacion/`.
- [ ] **H3 — Corpus RAG.** Curaduría de BIPs 32/39/44, EIP-155 y estándares de soporte
  (ERC-20/EIP-20, EIP-55, gas/JSON-RPC según se decida). Manifest con fuente, versión
  y hash de cada documento. Congelado antes de las corridas.
- [ ] **H4 — Pipeline/harness de agentes.** Instalación y configuración de los dos
  harness (Claude Agent SDK y OpenAI Agents SDK), pinneo de model IDs exactos,
  integración RAG conmutable, paridad de prompts/etapas entre condiciones.
- [ ] **H5 — Harness de evaluación.** Suite de tests de aceptación **black-box**
  contra el contrato HTTP/WS de la épica 09, escrita una sola vez y reutilizable
  contra las 4 implementaciones; rúbricas para clientes web/mobile; procedimiento de
  detección de alucinaciones de dominio; tooling de métricas estáticas. Construida
  **antes** de las corridas para eliminar sesgo del evaluador.

## Fase de ejecución comparativa

- [ ] **H6 — Corrida piloto.** Una corrida completa con configuración descartable
  (no cuenta para el 2×2) para debuggear protocolo, harness, registro y evaluación.
  Los defectos encontrados ajustan H2–H5 antes de congelar el protocolo definitivo.
- [ ] **H7 — Corridas oficiales.** Las 4 celdas del factorial, en ventana temporal
  corta (los modelos comerciales cambian): A-sin-RAG, A-con-RAG, B-sin-RAG, B-con-RAG.
  Cada corrida: repo propio + manifest + log de intervenciones + métricas.
- [ ] **H8 — Evaluación.** Ejecución del harness de evaluación sobre las 4
  implementaciones; consolidación del dataset comparativo en `analisis/`.

## Fase de análisis y cierre

- [ ] **H9 — Análisis comparativo.** Efectos principales (modelo, RAG), interacción,
  patrones cualitativos por categoría de intervención, meta-análisis del journal.
- [ ] **H10 — Redacción y defensa.** Documento final en `tesis/`.

## En paralelo (sin dependencia de corridas)

- [ ] **Estado del arte** (capítulo 2): puede empezar ya — MetaGPT, ChatDev, SWE-Agent,
  AgentMesh, RAG, arquitectura de exchanges, BIPs/EIPs.
- [ ] **Capítulos 3 y 4** (caso de estudio y diseño experimental): redactables apenas
  cierren H1 y H2, sin esperar resultados.
