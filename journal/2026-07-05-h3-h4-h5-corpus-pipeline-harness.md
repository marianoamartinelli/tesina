# 2026-07-05 — H3 (corpus RAG), H4 (pipeline) y H5 (harness de evaluación)

**Contexto:** hitos H3, H4 y H5 del [ROADMAP](../ROADMAP.md), los tres paralelizables
tras el cierre de H1/H2. Sesión con Claude Code; trabajo pesado delegado en 12
agentes (3 de infraestructura + 9 de tests por épica).

## Qué se hizo

### H3 — Corpus RAG congelado (commit `2435bb3`)

- **9 documentos** descargados de fuentes canónicas con manifest (fuente, commit
  upstream, fecha, SHA-256): BIP-32/39/44 + **wordlist inglés** (normativa por
  HU-06-01 RN-2), EIP-155, ERC-20/55/681, JSON-RPC de Ethereum (doc de ethereum.org).
- Decisiones de curaduría: **EIP-681 entra** (QR de depósito en mobile, 9 menciones);
  **EIP-1559 excluido** — la spec fija `TX_TYPE = legacy` y lo declara fuera de
  alcance; incluirlo induciría a implementar lo que la spec prohíbe. Los ERC se
  capturaron del repo `ethereum/ERCs` (en `ethereum/EIPs` son stubs `status: Moved`).

### H4 — Pipeline con paridad verificable (commits `32dad74`, `20be924`)

- **ADR-005** fija las tres decisiones estructurales: (1) **paridad por equivalencia
  funcional** — cada harness usa el stack agéntico nativo de su proveedor
  out-of-the-box; lo idéntico entre celdas son etapas, prompts (byte a byte), input,
  RAG y presupuestos; (2) **RAG léxico BM25 determinista sin embeddings** — un modelo
  de embeddings de cualquier proveedor contaminaría el aislamiento del factor modelo;
  (3) **model IDs pinneados**: `claude-opus-4-8` vs `gpt-5.5` (flagship contra
  flagship, mismo precio de input USD 5/M, misma ventana 1M; plan B tier medio si la
  piloto muestra que 200 USD/corrida no alcanzan).
- Estructura: `comun/` (etapas.yaml + prompts + RAG con tests), adaptadores finos
  `harness_a/` (claude-agent-sdk==0.2.110) y `harness_b/` (openai-agents==0.17.7,
  con su harness de sandbox/coding 2026), configs declarativas por celda,
  `verificar_paridad.py` (39 chequeos, incluye hashes del corpus vs manifest de H3).
- Los prompts **no mencionan la herramienta RAG**: su registro (con descripción
  propia) es la única diferencia entre celdas con/sin RAG.
- **Pendiente-piloto** (marcado en código y README): ejecución end-to-end real con
  API keys, contraste de la estimación de costo del harness B contra billing,
  semántica de `max_turns` entre SDKs.

### H5 — Harness de evaluación completo (commits `3ee750e`, `4e09551`, `3067af1`)

- **Catálogo**: 693 AT-ids regenerables por script (backend 521 / web 78 / mobile 94).
- **Suite black-box**: 431 tests pytest contra el contrato HTTP/WS de la épica 09,
  cubriendo **439 ATs con test + 82 declarados no-automatizables con justificación =
  521/521**, cobertura bidireccional verificada sin huecos ni solapamientos. Escrita
  **antes de existir implementación alguna** (regla de no-exposición, protocolo §9).
- Infraestructura: helpers (HTTP, WS, montos string-entero con fórmulas de referencia
  floor/ceil, catálogo de errores, EIP-55 con Keccak real), entorno on-chain local
  (anvil chainId 11155111, USDC-mock 6 decimales con bytecode vendoreado,
  confirmaciones por minado a demanda — deterministas, sin sleeps), reporte por AT-id
  (`resultados-at.csv`, una fila por cada uno de los 521).
- Fallos on-chain **provocados de verdad** en los tests (validados contra anvil):
  reorgs vía snapshot/revert, TX_DROPPED con tx competidora en el mismo nonce,
  TX_REVERTED vía setCode, broadcast sin fondos.
- **Rúbricas** épicas 10/11 con cobertura 1:1 (78 y 94 ATs), **alucinaciones.md**
  (categorías C1–C6 en cascada, unidad = hecho falso distinto, doble pasada en ciego,
  corpus H3 como referencia normativa) y **métricas estáticas** multi-lenguaje
  (cloc 2.10 / lizard 1.23.0 / jscpd 5.0.11 pinneados, `medir.sh` probado).

## Hallazgos de spec (TODO-REVISAR en los tests; NO se edita spec-v1.0)

Traducir la spec a tests ejecutables reveló una **segunda capa de defectos** que la
auditoría estática de H1 no vio — casi todos huecos del contrato de la épica 09:

1. **Rutas que otras épicas delegan en la 09 y la 09 nunca define**: logout
   (HU-01-03), historial de movimientos (HU-02-05 → **14 ATs quedaron
   no-automatizables por esto**), cancelación de retiros (HU-08-04 RN-13).
2. **Nomenclatura 04↔09 divergente**: `executedQty` vs `filledWei`;
   `remainingQty`/`avgExecutionPrice` exigidos por la 04 y ausentes del objeto orden
   de la 09; `clientOrderId` opcional (04) vs obligatorio (09); orden de desempate
   del historial asc (04) vs desc (09); `status=OPEN` → 422 (04) vs 200 (09).
3. **Retiros 02↔08**: la 02 dice que se bloquea el monto exacto; la 08 bloquea
   `monto + fee_red_wei`. Los tests aceptan ambos con nota.
4. **Datos de ejemplo imposibles**: AT-08-04-02 usa `gasUsed=15000` para una
   transferencia ETH (on-chain consume exactamente 21000); el Dado de AT-03-04-07
   viola el mínimo notional que la propia spec fija.
5. Política de rate limiting distinta entre 01 (opcional, por email/origen) y 09
   (60/min por cuenta y endpoint).

**Tratamiento** (protocolo §8): la spec taggeada no se edita; los tests toleran ambas
lecturas donde es posible y documentan el criterio; las resoluciones se decidirán
idénticas para las 4 celdas antes de las corridas oficiales y se acumulan para un
eventual `spec-v1.1` post-experimento.

## Commits

`2435bb3` corpus (H3) · `32dad74` adr ADR-005 · `20be924` pipeline (H4) ·
`3ee750e` rúbricas/alucinaciones/métricas · `4e09551` núcleo suite-at ·
`3067af1` tests 01–09 (H5) · (este commit) journal + ROADMAP.

## Pendientes / próximos pasos

- **H6 (piloto)** queda desbloqueado: única pieza que ningún hito pudo validar es la
  ejecución end-to-end del pipeline con API keys reales y el costo por corrida.
- Antes o durante la piloto: resolver los TODO-REVISAR (decisión única para las 4
  celdas, registrada en journal + eventual ADR); decidir si los 3 huecos de rutas de
  la épica 09 bloquean (una implementación puede elegir cualquier ruta y la suite no
  la encontraría — hoy la suite trata esos ATs como no-automatizables/tolerantes).
- Redactables ya: caps. 2–4 de la tesis.

## Observaciones para el meta-análisis

- **Cada profundización de uso de la spec encuentra una capa nueva de defectos**: la
  auditoría semántica (H1) encontró 52 inconsistencias normativas; la traducción a
  tests ejecutables (H5) encontró ~15 más, de otra clase (huecos de contrato, datos
  de ejemplo imposibles, delegaciones circulares 04↔09). Ninguna lectura las había
  detectado. Refuerza la misma tesis que el hallazgo de H1: los defectos viven en
  los **bordes** (entre épicas, y entre la spec y su ejecutabilidad).
- **La orquestación 3+9 agentes funcionó**: cobertura bidireccional exacta en las 9
  épicas al primer intento, cero colisiones de archivos (convención de un archivo de
  no-automatizables por épica fusionado después), y una sola inconsistencia menor
  (dos nombres para la env var de reinicio, unificada en la consolidación). El
  patrón "núcleo primero con HELPERS.md como contrato, luego fan-out" evitó la
  deriva de estilo entre agentes.
- El 15.7% de ATs backend no-automatizables black-box (82/521) no es uniforme: se
  concentra en las épicas cuyo objeto es interno (06 wallet: 61%; 02 ledger: 48% —
  inflado por el hueco del endpoint de movimientos) y cae a ~4–8% en las épicas de
  contrato puro. Dato útil para el cap. 4 al justificar la combinación
  suite + inspección white-box en H8.
