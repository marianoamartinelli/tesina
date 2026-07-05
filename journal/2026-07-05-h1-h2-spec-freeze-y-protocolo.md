# 2026-07-05 — H1 (spec freeze) y H2 (protocolo pre-registrado)

**Contexto:** hitos H1 y H2 del [ROADMAP](../ROADMAP.md). Sesión con Claude Code
(retomando el plan del artefacto de roadmap de la sesión anterior).

## Qué se hizo

### H1 — Auditoría y spec freeze (tag `spec-v1.0`, commit `7be0b7b`)

- **Auditoría mecánica scripted** sobre todo el corpus: unicidad y secuencia de
  AT-ids, referencias cruzadas HU/AT/RN/INV, códigos de error vs. catálogo, tablas
  de READMEs de épica. Resultado: el corpus tiene **57 HUs y 693 AT-ids** (la cifra
  "676" del journal del kickoff estaba mal: no contaba los AT con sufijo de letra).
  Único defecto mecánico: la convención de sufijos (`AT-01-01-04a`, `AT-08-01-12b`)
  no estaba documentada — se documentó en `spec/README.md` §4 en lugar de renumerar
  (los AT-id no se renombran).
- **Auditoría semántica con 3 agentes en paralelo** (épicas 01-02-04 / 03-05-09 /
  06-07-08-10-11), cada uno contrastando contra `00-fundaciones`. Hallazgos: **52**,
  ninguno aritmético (todos los ejemplos numéricos y todos los datos BIP/EIP
  verificados están correctos); todos de **consistencia normativa entre épicas**.
- **Corrección**: ~50 ediciones en 50 archivos (+598/−382), aplicadas por 3 agentes
  correctores con decisiones cerradas de antemano, más una pasada de consolidación.
  **Ningún AT-id renombrado ni renumerado.**

### Decisiones normativas fijadas en la auditoría (las importantes)

1. **STP (self-trade prevention):** política canónica = HU-03-06, **rechazo atómico
   total** (si el rango consumible contiene una orden propia, la entrante se rechaza
   íntegra, sin ningún fill, ni siquiera contra terceros). La épica 04 implementaba
   la alternativa *cancel-remainder* que la propia HU-03-06 declaraba descartada; se
   reescribió la 04. Motivos: la 03 es la épica dueña del algoritmo, la política está
   argumentada con alternativas descartadas, la máquina de estados de HU-04-05 ya era
   consistente con ella, y es más simple de testear ("un error por respuesta").
2. **Estado terminal de una MARKET con fill parcial = `CANCELLED`** (con `reason`
   `MARKET_EXHAUSTED`/`MARKET_BUDGET_EXHAUSTED`). La épica 09 decía "PARTIALLY_FILLED
   terminal", incompatible con 03/04 y con la clasificación abiertas/historial de
   10/11. `PARTIALLY_FILLED` queda como estado abierto exclusivo de LIMIT.
3. **Tres contadores independientes** declarados en RT-2 (README 03): `seq`
   (prioridad FIFO), `sequence` de eventos del motor (contigua) y `sequence` de
   trades (base del `tradeId`, huecos sólo por rollback). Antes había tres
   definiciones incompatibles de "sequence".
4. **Recursos ajenos referenciados por id ⇒ 404** not-found específico (sin filtrar
   existencia); `UNAUTHORIZED` 403 sólo para actuar "a nombre de" otra cuenta.
   Unifica 01/02/04/07/08/09/10/11 (había 403 en 07/08 y 404 en 04/09).
5. **Recurso depósito**: la épica 07 es la autoridad; la 09 se alineó (estados
   `PENDIENTE/ACREDITADO/DESCARTADO`, conteos como enteros JSON, `discardReason`,
   endpoint por id `GET /deposits/{depositId}`).
6. **Serialización**: timestamps de la API en ISO-8601 UTC (05 usaba epoch-ms
   string); conteos/índices (`confirmations`, `nonce`, `logIndex`, `blockNumber`,
   `retryAfterSeconds`) como enteros JSON en todo el corpus.
7. **Identificador del par**: `pair = "ETH/USDC"` en eventos internos del motor
   (03/05); `symbol = "ETH-USDC"` en la API (09); mapeo declarado en el glosario.
8. **Épica 10 (web) realineada al contrato real** (era la más desviada): enum
   canónico de retiros con mapeo de etiquetas, polling de depósitos (no hay canal WS
   de depósitos), token Bearer (no cookies), mínimos de retiro de la 08 (estaban 10×
   mal), sin flujo de "depósito acreditado revertido" (prohibido por HU-07-04 RN-10).
9. **Contrato API completado**: `GET /trades` (historial de trades propios, faltaba y
   la 05 lo requería), `failureReason` en retiros, `clientWithdrawalId` (idempotencia
   de retiros), filtro `clientOrderId` en `GET /orders`, `tokenAddress` para USDC,
   fila `MARKET_BUDGET_INSUFFICIENT` en el mapeo HTTP, y `MARKET_BUDGET_INSUFFICIENT`
   instanciado en la épica 04 (estaba catalogado pero sin comportamiento).
10. **Ledger**: tipo de asiento `REVERSAL` agregado al enum cerrado (el asiento de
    compensación de AT-02-03-06 era inexpresable sin él).
11. **WS orderbook**: las deltas se emiten para todo cambio del libro completo;
    `depth` limita sólo el snapshot; `sequence` única y global del libro (resolvía
    una incompatibilidad entre RN-3/RN-5/RN-12 de HU-09-03).
12. **Épica 06**: AT-06-03-07 reescrito como propiedad (el sistema se provisiona con
    mnemonic de 24 palabras; el AT exigía operar con `MNEMONIC_HARDHAT` de 12,
    prohibido por HU-06-01 RN-2).

### H2 — Protocolo experimental pre-registrado

- `evaluacion/protocolo.md` **v1.0**: definición operativa de intervención,
  disparadores objetivos D1–D4, cuándo NO intervenir, contenido permitido (incluida
  la **no-exposición del holdout** durante la corrida), cascada determinista para las
  8 causas raíz de la propuesta, estancamiento (3 intervenciones sin progreso) y
  abandono de etapa, presupuestos provisionales (**200 USD / 24 h activas por
  corrida**; tokens sin tope propio), orden backend → web → mobile, sorteo del orden
  de las celdas, manejo de defectos de spec mid-run (decisión idéntica para las 4
  celdas; la spec taggeada no se edita), y tabla de qué se registra dónde.
- **ADR-004** lo congela: única ventana de ajuste = corrida piloto (H6), vía nueva
  versión + ADR de reemplazo; inmutable durante H7.

## Commits

- `7be0b7b` spec: auditoría pre-freeze (H1) + tag **`spec-v1.0`**
- `1b2bf09` evaluacion: protocolo experimental pre-registrado v1.0 (H2)
- `2c08d03` adr: ADR-004 — congelamiento del protocolo
- (este commit) journal + ROADMAP

## Pendientes / próximos pasos

- H3 (corpus RAG), H4 (pipeline) y H5 (harness de evaluación) quedan desbloqueados y
  son paralelizables. El harness de H5 debe leerse contra `spec-v1.0`, no contra main.
- Redactables ya: caps. 3 y 4 de la tesis (dependían de H1 y H2).
- Cosas menores no tocadas (conscientes): nombres internos `amountWei`/`amountUsdcMin`
  en el registro interno de la épica 07 (no son contrato REST); nombres de campos de
  fee del evento `order-update` del motor vs. objeto orden REST (capas distintas,
  cada contrato es internamente consistente).

## Observaciones para el meta-análisis

- **La spec "terminada" tenía 52 defectos de consistencia entre épicas** y cero
  defectos aritméticos o de estándares. Patrón claro: cada épica es internamente
  sólida, pero los **bordes entre épicas** (quién es la autoridad de un contrato
  compartido) es donde se acumula la deriva — exactamente la categoría de fallo n.º 5
  ("integración entre componentes") que el experimento va a medir en los agentes.
  Irónico y útil para la discusión.
- Dos épicas habían tomado **decisiones opuestas y ambas deliberadas** sobre STP
  (03-06 documentaba como "descartada" la alternativa que 04 implementaba). Ninguna
  lectura local lo detecta; sólo el cruce.
- La auditoría con agentes en paralelo (3 auditores + 3 correctores con decisiones
  pre-cerradas) funcionó bien: los auditores no alucinaron hallazgos (todos
  verificados contra los archivos) y los correctores no renombraron ningún AT-id.
  Hubo que **retomar los 3 correctores** tras un corte por límite de sesión de la
  API; el retome con contexto conservado funcionó sin pérdida.
- El conteo público de ATs estaba mal (676 vs. 693 reales): ningún documento
  normativo lo afirmaba (sólo el journal), pero es un recordatorio de no citar
  números no regenerables por script. El script de auditoría queda como referencia
  (scratchpad de la sesión; conviene versionarlo en `evaluacion/` para H5).
