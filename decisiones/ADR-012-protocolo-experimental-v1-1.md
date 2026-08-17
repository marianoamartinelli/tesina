# ADR-012 — Protocolo experimental v1.1 (reemplaza a ADR-004)

- **Estado:** **Aceptado** (ratificado por el tesista el 2026-08-17, en conjunto con
  ADR-011)
- **Fecha:** 2026-08-16
- **Reemplaza a:** [ADR-004](ADR-004-protocolo-experimental-preregistrado.md), que congeló
  `evaluacion/protocolo.md` **v1.0**. ADR-004 **no se edita**: queda como registro fechado
  del pre-registro original, y la trazabilidad v1.0 → v1.1 vive en la tabla de §3.
- **Contexto:** ventana H6 —la única ventana de ajuste que ADR-004 punto 2 admite—, con
  las dos corridas piloto todavía sin ejecutar. Entre el pre-registro (2026-07-05) y hoy,
  ADR-006, ADR-007, ADR-009, ADR-010 y ADR-011 dejaron la v1.0 nombrando un tag de spec
  que ya no se usa, un factor «modelo» definido sobre SDK que ya no se usan y un H8 que no
  menciona la mitad de sus instrumentos.

## Decisión

### 1. El protocolo pasa a v1.1 y queda congelado por este ADR

`evaluacion/protocolo.md` v1.1 rige desde la aceptación de este ADR y antes de la primera
corrida oficial.

### 2. Qué se conserva de ADR-004, sin cambio

- El **principio de pre-registro**: los criterios que hacen comparable la métrica de
  intervenciones se fijan antes de la primera corrida, públicos y fechados.
- **Punto 2** (ventana de ajuste única), **punto 3** (inmutabilidad durante H7: una
  desviación forzada se registra como amenaza, no se corrige el protocolo
  retroactivamente) y **punto 4** (presupuestos provisionales, que sigue abierto).
- **El evaluador de registro sigue siendo el humano**; el agente white-box de ADR-007 es
  un instrumento y el tesista audita el 100 % de sus veredictos.
- Todo el contenido normativo que la tabla de §3 no toca: definición de intervención,
  disparadores D1–D4, no-intervención, no-exposición del holdout, cascada de las 8 causas
  raíz, estancamiento y abandono, orden backend → web → mobile, sorteo y ventana temporal.

### 3. Qué cambia de v1.0 a v1.1

| Sección | Cambio | Fuente |
|---------|--------|--------|
| Encabezado | v1.1 congelada por este ADR; la ventana H6 se declara consolidada | ADR-004 punto 2 |
| §1 | El factor «modelo» pasa de SDK a **Claude Code CLI (`claude -p`) vs Codex CLI (`codex exec`)**; se deja constancia de que la ventana piloto comprende `piloto-01` (A completa) y `piloto-02` (B smoke), ambas descartables | ADR-009 D1; checklist H6 |
| §2.1 y §3 paso 1 | `spec-v1.0` → **`spec-v1.1`** | ADR-006 |
| §2 puntos 3 y 4 | Las constantes del pipeline incorporan los prompts de rol y la secuencia por etapa; los model IDs pasan a ADR-009 D3 y el pinneo suma `effort: xhigh`, versión exacta de cada CLI y `model_context_window` en las celdas B | ADR-009 D3–D5; ADR-010 D1–D2 |
| §3 paso 6 | H8 se abre en seis sub-pasos ordenados, con `SUITE_CMD_REINICIO_SUT` como precondición dura y **`validar-resultados.py` previo al arbitraje** | ADR-007 §5; ADR-010 D3; ADR-011 |
| §4 | Se reorganiza en §4.1 criterio de avance, §4.2 smoke de backend con el entorno on-chain, §4.3 no-exposición. El **health-check queda autocontenido**: si el agente no documentó su ruta, el smoke no se puede ejecutar y es un **D1** | `pipeline/comun/etapas.yaml`; prompt de etapa 1 |
| §5 | El corte de una invocación del CLI antes de completar el paso entra en **D2** con continuación tipo (d), y la nueva **§5.8** fija la regla: re-invocar al orquestador sobre el estado actual del repo, **sesión fresca sin `resume`**. La causa esperable pasa a ser el rate limit | ADR-009 §Consecuencias |
| §6 | **No hay tope de turnos** (se cae el tope, no la métrica) y, bajo suscripción, el tope vinculante son los **rate limits**, no `costo_max_usd`. Los presupuestos definitivos quedan `PENDIENTE-PILOTO`, sin número | ADR-009 §Consecuencias; checklist H6 ítems 7 y 14 |
| §7 | Se nombra la presión de los rate limits sobre la ventana de ≤ 2 semanas | ADR-009 §Consecuencias |
| §8 punto 3 | «eventual `spec-v1.1`» → «eventual **`spec-v1.2`**» | ADR-006 |
| §9 | Se registra el pre-registro de `rubricas/rol-revisor.md` en H6 (no en H5) con su cláusula de re-pre-registro acotada a la piloto, y la partición **465/56** como cerrada dentro de la ventana | ADR-009 D4; ADR-011 |
| §10 | La tabla de artefactos se amplía (JSONL del orquestador, pasadas del agente white-box, CSV de rúbricas, métricas, alucinaciones) y gana tres subsecciones: **§10.1** formato CSV de las rúbricas, **§10.2** censo del revisor antes de abrir `resultados-at.csv`, **§10.3** exclusión de `.pipeline/` de las métricas estáticas | ADR-009 D4; `evaluacion/rubricas/README.md` |

### 4. Por qué estos ajustes entran en la ventana de ADR-004

La mayoría **no los reveló la piloto**: la piloto no corrió. Lo que ADR-004 protege es que
ningún criterio de medición se defina *después de ver una implementación*, y no existe
implementación alguna, así que se fijan en la condición más estricta posible — la misma
bajo la que se pre-registró la v1.0. Son de tres tipos:

1. **Actualizaciones de referencia** que decisiones ya aceptadas dejaron obsoletas. No
   cambian ningún criterio: cambian el nombre del insumo al que el criterio se aplica.
2. **Huecos de procedimiento que v1.0 nunca fijó** y que H8 necesita. Fijarlos hoy *es*
   pre-registro; dejarlos abiertos sería el criterio definido sobre la marcha que el
   protocolo prohíbe.
3. **Una regla nueva de conducta durante la corrida** (§5.8), también fijada antes de la
   primera corrida e idéntica en las 4 celdas.

Ninguno se apoya en datos de una corrida. El único ítem que sí depende de la piloto —los
presupuestos— se deja abierto en vez de llenarse con un número plausible.

### 5. Lo que este ADR no cierra

- **Presupuestos definitivos** y la decisión suscripción contra API key: dependen del
  consumo que mida la piloto (ítem 7).
- **Comportamiento de cada CLI ante un rate limit a mitad de etapa** (ítem 19): la regla
  de §5.8 aplica igual en ambos escenarios posibles, pero el dato falta.
- **Sorteo del orden de las 4 celdas** (ítem 15): acto previo a H7, registrado en journal.
- Si la piloto revela defectos del protocolo, se produce una **v1.2** más un ADR que
  reemplace a este, antes de la primera corrida oficial.

## Evidencia registrada

La exclusión de `.pipeline/` (§10.3) se implementó y verificó empíricamente el 2026-08-16
—antes de la piloto y sin implementación a la vista— con **cloc 2.10, lizard 1.23.0 y
jscpd 5.0.11** en sus versiones pinneadas; detalle en `evaluacion/metricas-estaticas/README.md`
§1.1. Se registra acá porque es lo que sostiene que el alcance de esa métrica quedó
congelado, que es la condición que §4 invoca para todo el conjunto.

## Consecuencias

- `evaluacion/protocolo.md` v1.1 es el texto vigente desde la aceptación; v1.0 queda como
  versión histórica en git, citada por ADR-004.
- La cadena de citas del capítulo 4 pasa a ser **ADR-004 → ADR-012**: el primero documenta
  el pre-registro, el segundo su única revisión.
- Las referencias externas a «protocolo §N» siguen resolviendo: §4, §5 y §10 ganaron
  subsecciones sin renumerar las anteriores.
- La v1.1 cita a ADR-011: **ambos se ratificaron en conjunto el 2026-08-17**, así que la
  partición 465/56 de §3 paso 6 y §9 rige sin corrección.
- Cubre el ítem 9 de la checklist H6; los ítems 7, 15 y 19 siguen abiertos.
- Si este ADR se rechaza, hay que revertir `evaluacion/protocolo.md` al texto congelado
  por ADR-004 y correr las oficiales contra un documento desactualizado.
