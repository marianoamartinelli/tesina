# Roadmap de hitos

Estado: `[ ]` pendiente · `[~]` en curso · `[x]` completado. Cada hito cerrado se
registra en `journal/` y, si implicó decisiones estructurales, en `decisiones/`.

## Fase preparatoria (restante)

- [x] **H0 — Infraestructura del repo.** Estructura de versionado, ADRs, journal,
  plantillas de manifest, roadmap. *(2026-07-04)*
- [x] **H1 — Spec freeze.** Auditoría final de la spec (consistencia de AT-ids,
  referencias cruzadas, precedencia de errores, invariantes) y tag `spec-v1.0`.
  A partir del tag, la spec es **inmutable** para el experimento: las 4 corridas
  reciben exactamente ese commit. *(2026-07-05 — tag `spec-v1.0`; 57 HUs,
  693 AT-ids; ~50 correcciones de consistencia, ver journal. Re-freeze como
  **`spec-v1.1`** el mismo día, antes de toda corrida: ADR-006 cierra 17 decisiones
  (defectos hallados al construir la suite de H5 más 2 menores ya conocidos de H1)
  con AT-ids intactos; las corridas pinnean v1.1.)*
- [x] **H2 — Protocolo experimental pre-registrado.** Documento que fija, antes de
  cualquier corrida: criterios de intervención humana (cuándo intervenir, cómo se
  clasifica según las 8 causas raíz de la propuesta), orden de construcción
  (backend → web → mobile), presupuestos por corrida (tokens/costo/tiempo), qué se
  registra y cómo. Se congela como ADR + documento en `evaluacion/`.
  *(2026-07-05 — `evaluacion/protocolo.md` v1.0 + ADR-004; presupuestos
  provisionales hasta la piloto.)*
- [x] **H3 — Corpus RAG.** Curaduría de BIPs 32/39/44, EIP-155 y estándares de soporte
  (ERC-20/EIP-20, EIP-55, gas/JSON-RPC según se decida). Manifest con fuente, versión
  y hash de cada documento. Congelado antes de las corridas. *(2026-07-05 — 9
  documentos con manifest y SHA-256; EIP-681 incluido, EIP-1559 excluido
  deliberadamente; ver journal.)*
- [x] **H4 — Pipeline/harness de agentes.** Instalación y configuración de los dos
  harness (Claude Agent SDK y OpenAI Agents SDK), pinneo de model IDs exactos,
  integración RAG conmutable, paridad de prompts/etapas entre condiciones.
  *(2026-07-05 — ADR-005: paridad por equivalencia funcional, RAG BM25 determinista,
  `claude-opus-4-8` vs `gpt-5.5`; verificador de paridad con 39 chequeos; ejecución
  end-to-end con API keys pendiente para la piloto.)*
- [x] **H5 — Harness de evaluación.** Suite de tests de aceptación **black-box**
  contra el contrato HTTP/WS de la épica 09, escrita una sola vez y reutilizable
  contra las 4 implementaciones; rúbricas para clientes web/mobile; procedimiento de
  detección de alucinaciones de dominio; tooling de métricas estáticas. Construida
  **antes** de las corridas para eliminar sesgo del evaluador. *(2026-07-05 — 449
  funciones de test / 521 ATs backend cubiertos (455 con test + 66 no-automatizables
  justificados, que evalúa el agente white-box de ADR-007 en H8); rúbricas 78+94 ATs;
  entorno on-chain local determinista; los hallazgos de spec detectados al construir
  la suite se corrigieron vía ADR-006 (re-freeze `spec-v1.1`, ver H1); quedan 2
  TODO-REVISAR (status HTTP del reenvío idempotente de retiros,
  `test_ep08_solicitud.py`) a resolver en la piloto.)*

## Fase de ejecución comparativa

- [ ] **H6 — Corrida piloto.** Una corrida completa con configuración descartable
  (no cuenta para el 2×2) para debuggear protocolo, harness, registro y evaluación.
  Los defectos encontrados ajustan H2–H5 antes de congelar el protocolo definitivo.
  Entrada y salida de la ventana:
  [`runs/piloto-01/checklist-h6.md`](runs/piloto-01/checklist-h6.md). La ventana
  comprende `piloto-01` (corrida completa con el harness A) y `piloto-02` (smoke
  end-to-end del harness B).
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
