# ADR-013 — Mecanismo de import del mnemonic en la evaluación white-box

- **Estado:** **Aceptado** (ratificado por el tesista el 2026-08-17)
- **Fecha:** 2026-08-16
- **Contexto:** cuatro ATs de la épica 06 sólo se ejercitan arrancando el SUT con un
  mnemonic **elegido por el evaluador** — AT-06-01-05 (checksum BIP-39 inválido),
  AT-06-01-09 (12 palabras), AT-06-01-10 (palabra fuera del wordlist) y AT-06-03-07
  (coherencia índice→dirección contra una derivación de referencia). La spec **permite**
  importar un mnemonic (HU-06-01 §Supuestos, RN-1) pero **no fija el mecanismo**. Quedó
  anotado como pendiente de la ventana de la piloto (journal 2026-07-06 §Pendientes
  punto 2; ítem 5 de la checklist H6).
- **Complementa a:** [ADR-007](ADR-007-agente-evaluador-white-box.md) y
  [ADR-011](ADR-011-particion-automatizable-white-box.md), que dejó a estos cuatro ATs en
  white-box. Ninguno se edita.

## Decisión

### 1. No se fija ninguna convención de entorno para el SUT

No se define variable, flag ni archivo de configuración con nombre acordado. La única
entrada de las 4 corridas es la spec congelada (`spec-v1.1`): un requisito inventado ahora
no estaría en esa entrada, ninguna implementación podría conocerlo, y exigirlo mediría
adherencia a una convención posterior a la generación en lugar de conformidad con la spec.

Corolario: que un SUT no exponga mecanismo de import **no es incumplimiento**. Lo que la
spec sí obliga —RN-2: validar longitud, wordlist y checksum antes de adoptar el mnemonic—
se evalúa igual, por la vía del punto 2.

### 2. Se ratifica el fallback declarado por AT

| AT | Sin mecanismo de import |
|----|-------------------------|
| AT-06-01-05 / -09 / -10 | **Fallback F1**: se verifica en el código del provisioning que la validación de RN-2 existe y que su fallo aborta sin adoptar seed. Veredicto normal (`PASA`/`FALLA`). |
| AT-06-03-07 | `NO_EVALUABLE:PRECONDICION_IMPOSIBLE`, **sin fallback**: RN-5 prohíbe exponer el mnemonic generado, y sin conocerlo no hay derivación de referencia contra la cual comparar. |

La asimetría es deliberada: en los tres primeros la propiedad normativa es la
**validación**, verificable leyendo el código. En AT-06-03-07 es una **igualdad contra una
referencia externa** que no existe sin el mnemonic; no hay evidencia estática equivalente.

### 3. El mecanismo se busca con un procedimiento uniforme

El riesgo del fallback no es el fallback: es que se dispare con distinto umbral en cada
celda o pasada y que la diferencia se lea después como diferencia entre modelos. La
rúbrica v1.2 (§"Mecanismo de import del mnemonic") fija una búsqueda idéntica para las 4
celdas, que se ejecuta **una sola vez** al llegar a AT-06-01-05 y cuyo resultado se cita
como evidencia en los cuatro ATs.

Regla dura: **no se agrega ni se parchea un mecanismo de import**, en ninguna copia.
Inyectar el mnemonic editando el código reemplaza el camino que el AT describe —el
provisioning validando su entrada y abortando con su propio exit code y `stderr`— por otro
distinto.

## Consecuencias

- `rubrica-white-box.md` pasa a **v1.2** y `plantilla-resultados.yaml` fija
  `rubrica_version: "v1.2"`. Ningún criterio de veredicto cambia. El briefing no se toca:
  su tabla de causas ya tipifica `PRECONDICION_IMPOSIBLE` con este caso como ejemplo.
- **La evaluabilidad de AT-06-03-07 depende de la implementación y puede diferir entre
  celdas.** Es un dato de la corrida, no un defecto a corregir ajustando el instrumento:
  si una celda lo resuelve `NO_EVALUABLE` y otra no, el par no es comparable en ese AT.
  Corresponde sumarlo a `analisis/amenazas-validez.md` como asimetría de evaluabilidad.
- Los `NO_EVALUABLE` con esta causa nunca se mezclan con los `pasa`/`falla` de la suite
  black-box ni entran en `pasa / (pasa + falla)`, como fija ADR-007.

## Alternativas consideradas

- **Fijar una variable de entorno** (p. ej. `WALLET_MNEMONIC`) y exigirla a las 4 celdas.
  Rechazada: no está en la spec congelada, así que las 4 fallarían por igual — sin señal
  experimental y con un requisito fuera del input.
- **Parchear la copia descartable** para que el provisioning tome una constante.
  Rechazada: no cubre el "Entonces" (exit code ≠ 0 y `VALIDATION_ERROR` en `stderr` del
  proceso de provisioning) y cada parche sería distinto por celda.
- **Extraer el seed persistido** y derivar la referencia desde ahí. Rechazada por ahora:
  exigiría implementar BIP-32 en el entorno de evaluación, justo lo que el anvil de
  referencia evita.
- **Mover los cuatro ATs a black-box.** Imposible por el criterio (a) de ADR-011: el
  provisioning es un proceso de arranque sin superficie REST/WS.
