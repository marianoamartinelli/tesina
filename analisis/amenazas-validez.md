# Amenazas a la validez — registro consolidado

Insumo del capítulo 4 (diseño experimental). **Este documento sólo consolida
amenazas y mitigaciones ya pre-registradas en sus fuentes primarias; no introduce
mitigaciones nuevas** (eso exigiría la ventana de ajuste de la piloto, H6, o un
ADR de reemplazo). Ante cualquier diferencia, manda la fuente primaria citada.

Estados: **mitigada** (mitigación pre-registrada operativa; puede quedar riesgo
residual declarado) · **declarada** (asumida por diseño, se discute como
limitación) · **pendiente (H6)** (se resuelve en la ventana de la piloto — ver
`runs/piloto-01/checklist-h6.md`).

| Amenaza | Fuente primaria | Mitigación pre-registrada | Estado |
|---|---|---|---|
| **n=1 por celda:** sin réplicas no hay inferencia estadística. | `journal/2026-07-04-kickoff-estructura-y-roadmap.md`, riesgo 4 | Marco metodológico de la propuesta: DSR + estudio de caso (Yin); documentar como amenaza; evaluar réplicas si el presupuesto lo permite. | declarada |
| **Tooling nativo dentro del factor modelo:** las diferencias de herramientas entre SDKs no pueden separarse del modelo; el factor mide el pipeline completo. | ADR-005, Decisión 1 | Paridad por equivalencia funcional de todo lo demás (etapas, prompts, RAG, presupuestos idénticos, auditables en `pipeline/` y chequeados por `verificar_paridad.py`); la diferencia restante se declara como limitación en el cap. 4. | declarada |
| **Self-preference del LLM-judge:** el agente evaluador white-box (`claude-opus-4-8`) evalúa implementaciones generadas por Claude y por GPT. | ADR-007 §3 | Copia de evaluación sin `.git` ni metadatos; rúbrica reducida a verificaciones mecánicas evidence-gated; doble pasada independiente con arbitraje humano; auditoría humana del 100 %; chequeo de concordancia espejo opcional (`gpt-5.5`, 10 ATs/celda). | mitigada |
| **Efecto aprendizaje del evaluador humano único** entre corridas sucesivas. | `evaluacion/protocolo.md` §7 | Sorteo único del orden de las 4 celdas, registrado en journal; piloto como entrenamiento del evaluador. El propio protocolo declara que con n=1 no lo elimina. | mitigada (residual declarado) |
| **Deriva de modelos comerciales / ventana temporal:** los modelos cambian bajo el mismo ID comercial. | `journal/2026-07-04-kickoff-estructura-y-roadmap.md`, riesgo 5; `evaluacion/protocolo.md` §2 punto 7 | Model IDs exactos pinneados (ADR-005, Decisión 3); las 4 corridas oficiales en ventana ≤ 2 semanas. | mitigada |
| **No-determinismo de los modelos:** misma celda, otra corrida ⇒ potencialmente otro resultado. | Implícita en n=1 (`journal/2026-07-04`, riesgo 4); consolidada acá | Registro: JSONL completo por corrida (`pipeline/README.md` §Registro); parámetros de generación en default documentado (ADR-005, Decisión 3); n=1 asumido por diseño (DSR/estudio de caso). Es registro de una limitación, no un control. | declarada |
| **Generalización del caso único:** un solo caso de estudio (el exchange). | Propuesta de tesina (marco DSR — Hevner et al. 2004 — + estudio de caso — Yin 2018); `tesis/capitulos/04-diseno-experimental.tex` | El marco metodológico pre-registrado asume generalización analítica, no estadística. | declarada |
| **Defectos de protocolo detectados post-corrida:** una desviación forzada durante H7 no se corrige retroactivamente. | ADR-004, Decisión punto 3 | Piloto (H6) como única ventana de ajuste; la desviación se registra en el momento (journal + log de la corrida) y se discute como amenaza a la validez. | mitigada |
| **Contaminación del factor RAG por canal residual de shell con red:** aunque ADR-008 restrinja WebSearch/WebFetch en A, ambos harnesses conservan shell con acceso a red (necesario para `npm install`), un canal de recuperación de información no controlado. | ADR-008 (Propuesto); `pipeline/README.md` §Arquitectura | Ninguna adicional pre-registrada: el canal queda declarado; su acotamiento (allowlist de red) se decide en H6 (`checklist-h6.md`, ítem 11). | declarada |
| **Asimetría de confinamiento A/B:** A corre sin sandbox de SO (`bypassPermissions`); B corre bajo el seatbelt de su SDK. Si no se iguala, el confinamiento difiere entre celdas del factor modelo. | `pipeline/README.md` §"Pendiente para la piloto" (confinamiento del harness A) | Prevista para la piloto: probar sandbox + deny rules en A y decidir/registrar (`checklist-h6.md`, ítem 11; posible ADR). | pendiente (H6) |
