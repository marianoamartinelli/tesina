# 2026-07-06 — Documentación técnica de la infraestructura y correcciones pre-piloto

**Contexto:** entre H5 y H6 (piloto). Sesión de asistencia con Claude Code. Se pidió
documentación explicativa de la infraestructura construida en H3–H5 — arquitectura RAG,
los dos pipelines de generación y el harness de evaluación — como revisión de cobertura
previa a la corrida piloto, con el relevamiento delegado en subagentes de sólo lectura
contra el repo.

## Qué se produjo

Tres documentos técnicos publicados como artifacts (enlazados desde el artifact del
roadmap y desde los de los hitos H3/H4/H5; el mapa de URLs queda en la memoria de la
sesión de Claude, la fuente de verdad del contenido es siempre el repo):

- **Arquitectura RAG** — los 9 documentos del corpus y su freeze, chunking e índice BM25
  (K1=1.5, B=0.75, k=6, sin embeddings ni persistencia), la tool única
  `consultar_corpus`, la conmutación `rag: true|false`, la paridad por construcción +
  `verificar_paridad.py`, la justificación de ADR-005 decisión 2 y los límites asumidos.
- **Pipelines de generación A y B** — el diseño "núcleo común en `pipeline/comun/` +
  adaptadores finos por SDK": stack pinneado, tools, entorno de ejecución, steps de una
  corrida, tabla idéntico/equivalente/distinto entre harnesses, registro (JSONL,
  manifest, intervenciones) y los `PENDIENTE-PILOTO`.
- **Harness de evaluación** — catálogo → tres destinos (suite black-box, agente
  white-box ADR-007, rúbricas web/mobile) → CSV por AT-id; invocación y parámetros;
  fallos on-chain provocados de verdad; familias F1–F6; métricas y agregación en
  `analisis/dataset/`; valor como holdout (ADR-004).

El relevamiento (3 agentes en paralelo) verificó afirmaciones contra los archivos:
SHA-256 del corpus re-chequeados contra el manifest, 449 funciones de test contadas,
parámetros BM25 cotejados código↔config, chequeos de paridad enumerados.

## Hallazgos y correcciones aplicadas

1. **`runs/plantillas/manifest.template.yaml` pinneaba `tag: "spec-v1.0"`** —
   desactualizado respecto de ADR-006 (re-freeze como `spec-v1.1`). Corregido. El código
   del pipeline es agnóstico al tag, pero el primer manifest real habría arrastrado el
   tag viejo a una corrida.
2. **Falso positivo, descartado con verificación:** el relevamiento sugirió que la prosa
   de `evaluacion/suite-at/README.md` conservaba conteos pre-v1.1 (431/439/82). Grep
   contra `evaluacion/` mostró que esos números sólo existen en el journal (histórico,
   inmutable por diseño) y que el "521 ATs backend" del README es correcto. Como el dato
   que confundió al agente era la falta de desglose, se explicitó en el README:
   455 ATs con test (449 funciones, relación muchos-a-muchos) + 66 no-automatizables
   = 521. El artifact del harness, que había publicado la afirmación errónea, se
   corrigió y re-publicó.

## Pendientes

Sin cambios respecto de los ya registrados para la ventana de la piloto: los
`PENDIENTE-PILOTO` de `pipeline/`, los 2 `TODO-REVISAR` de ep08 (status del reenvío
idempotente), la posible sobre-declaración de F3 y el mecanismo de importar mnemonic
(journal 2026-07-06 del agente evaluador).

## Observaciones para el meta-análisis

- **Los documentos históricos son fuente recurrente de falsos positivos para agentes.**
  Un subagente de relevamiento leyó conteos viejos en una entrada de journal (que es
  histórica e inmutable a propósito) y los reportó como inconsistencia vigente de otro
  archivo. El agente orquestador amplificó esa nota vaga a una afirmación concreta y
  falsa ("el README dice 431/439/82") sin re-verificar contra el archivo — el mismo
  patrón de sobre-especificación que el procedimiento de alucinaciones (C1–C6) busca
  detectar en los agentes generadores, ahora observado en un agente asistente del propio
  proyecto.
- **La regla "verificar antes de editar" pagó:** el grep previo a la corrección evitó
  "arreglar" un archivo que estaba bien, y convirtió el falso positivo en una mejora
  real (explicitar el desglose que faltaba).
- Delegar el relevamiento en 3 agentes de sólo lectura en paralelo funcionó bien para
  cobertura y velocidad; la lección es que sus informes son borradores con citas, no
  veredictos — exactamente el mismo rol que ADR-007 le asigna al agente evaluador.

## Commits

`runs:` manifest template a spec-v1.1 · `evaluacion:` desglose explícito en el README de
suite-at · `journal:` esta entrada.
