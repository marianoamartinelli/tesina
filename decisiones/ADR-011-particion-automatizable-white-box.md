# ADR-011 — Partición final automatizable / white-box de los ATs backend

- **Estado:** **Aceptado** (ratificado por el tesista el 2026-08-17)
- **Fecha:** 2026-08-16
- **Contexto:** de los 66 ATs backend que H5 declaró no automatizables black-box, **13**
  (la familia F3 de la rúbrica) alegaban lo mismo: que el harness no controla el ciclo de
  vida del SUT. El alegato era falso — la suite ya reiniciaba el SUT con
  `SUITE_CMD_REINICIO_SUT` en otras épicas — y quedó anotado como sobre-declaración a
  resolver en la ventana de la piloto (journal 2026-07-06 §Pendientes punto 1; ítem 4 de
  la checklist H6).
- **Complementa a:** [ADR-007](ADR-007-agente-evaluador-white-box.md), que fijó el
  instrumento white-box pero no el criterio de la partición. No se edita.
- **Deadline:** entra **antes** de la primera corrida que produzca implementación. Mover
  la frontera después de ver código sería elegir la vara conociendo al examinado
  (`evaluacion/protocolo.md` §9).

## Decisión

### 1. Criterio de la partición

Un AT backend queda **no automatizable** si y sólo si:

- **(a)** su "Cuando" no tiene disparador black-box — ninguna secuencia del contrato
  HTTP/WS de la épica 09, del JSON-RPC del anvil local o del entorno de evaluación
  provoca el evento; o
- **(b)** alguna afirmación de su "Entonces" no tiene superficie observable por REST/WS
  ni on-chain.

Dos corolarios:

- **El AT es la unidad de reporte, entera.** Si una sola afirmación cae en (b), el AT
  completo va a white-box: no se automatiza "la mitad verificable", porque un `pasa`
  sobre media verificación sobredeclara cobertura.
- **El ciclo de vida del SUT no es motivo.** `SUITE_CMD_REINICIO_SUT` es un insumo del
  entorno como la URL del SUT o el nodo anvil; su ausencia hace que el test **salte con
  motivo explícito**, no que el AT se declare inautomatizable. Los ATs de persistencia
  (INV-8) son automatizables de forma **condicional**.

### 2. Partición final: 465 automatizados / 56 white-box

Sobre los **521 ATs backend**:

| | Antes (H5) | Ahora | Δ |
|---|---:|---:|---:|
| Automatizados black-box | 455 | **465** | +10 |
| White-box (ADR-007) | 66 | **56** | −10 |
| Sin cobertura (`sin_test`) | 0 | **0** | — |

Los 10 migrados, todos de persistencia tras reinicio: **AT-04-01-11, AT-04-04-12,
AT-04-05-13, AT-06-01-07, AT-06-01-08, AT-06-02-06, AT-06-03-06, AT-07-04-07,
AT-07-04-11, AT-08-03-08**. Los cuatro de la épica 06 comparten un solo test de cuatro
markers: su única proyección black-box es la dirección que emite `GET /deposit-address`,
así que pasan o fallan juntos.

La suite pasa a **456 funciones de test** y los ATs que dependen del reinicio, de 11 a
**21**: `SUITE_CMD_REINICIO_SUT` deja de ser opcional.

### 3. Los tres parciales quedan white-box

Ninguno por el ciclo de vida del SUT. Motivo completo en `no-automatizables.yaml`:

| AT | Razón | Criterio |
|----|-------|----------|
| **AT-05-03-07** | La reconciliación de fees contra la cuenta técnica `EX` (RN-8): ningún endpoint de la épica 09 expone su saldo ni sus movimientos | (b) |
| **AT-07-04-01** | Reobservar una identidad ya acreditada no es provocable: la reorg ≥ 13 está excluida por HU-07-04 §Contexto, no hay endpoint de acreditación y el reinicio reanuda en `checkpoint + 1` (RN-8) | (a) + (b) |
| **AT-07-04-03** | Variante ETH nativo del anterior, misma razón | (a) |

Se reescribió además el motivo de **AT-06-02-05**, que se apoyaba en el mismo alegato:
su razón real es que el contrato no permite elegir seed ni `address_index`, así que la
pureza de la derivación es inobservable desde afuera.

## Consecuencias

- **Sube la cobertura de la métrica principal**: `pasa / (pasa + falla)` se computa sobre
  465 ATs en vez de 455, y los INV-8 de las épicas 04, 06, 07 y 08 pasan a medirse con
  vara mecánica en las 4 celdas en lugar de por juicio del agente evaluador.
- **Baja la superficie de self-preference**: 10 ATs menos bajo un juez LLM.
- **La familia F3 queda vacía** y sus 3 sobrevivientes se reclasifican en F1
  (inspección). `rubrica-white-box.md` pasa a v1.1 y `briefing.md` a v1.1 con el único
  cambio del conteo 66 → 56, dentro de la ventana que el propio briefing declara
  ajustable.
- **`SUITE_CMD_REINICIO_SUT` es precondición dura de toda corrida H8** (21 ATs dependen
  de él) y se registra en el manifest. AT-07-04-11 verifica su hueco de downtime en modo
  best-effort, declarado como limitación en el docstring del test.
- **Ventana cerrada:** cualquier movimiento posterior de la frontera violaría el
  protocolo §9, porque para entonces habrá implementación a la vista.

## Alternativas consideradas

- **Migrar los 13 partiendo los parciales** en mitad automatizada + mitad white-box.
  Rechazada: el AT-id es la unidad de reporte (`resultados-at.csv` tiene una fila por AT)
  y partirlo contamina la métrica principal.
- **Dejar los 13 en white-box** reescribiendo sólo los motivos. Rechazada: 10 propiedades
  mecanizables quedarían medidas por juicio de un LLM.
- **Postergar a después de la piloto.** Rechazada por el deadline.
