# 2026-07-06 — Framework del agente evaluador para los ATs no automatizables

**Contexto:** los 66 ATs no automatizables black-box tenían su vía de evaluación
declarada entrada por entrada en `no-automatizables.yaml`, pero no existía un
procedimiento operativo consolidado para ejecutarla de forma idéntica en las 4
celdas. El tesista decidió que esa evaluación la ejecute un **agente evaluador LLM**
con paridad total entre celdas. Se fijó por [ADR-007](../decisiones/ADR-007-agente-evaluador-white-box.md)
y se construyó el framework en `evaluacion/agente-evaluador/`.

## Qué se decidió (ADR-007)

- **Un único agente congelado**: `claude-opus-4-8`, briefing versionado pasado
  verbatim, sesión fresca por celda, mismos insumos, orden fijo de ATs.
- **Veredictos evidence-gated**: `PASA`/`FALLA`/`NO_EVALUABLE` sólo con evidencia
  citada (archivo:líneas o comando+salida); sin evidencia ⇒ inválido. Causas de
  `NO_EVALUABLE` tipificadas.
- **Mitigación del sesgo LLM-as-judge** (evaluar Claude y GPT con un modelo de uno
  de los dos): copia de evaluación **sin `.git`**, prohibición de identificar al
  generador, doble pasada independiente por celda con arbitraje humano, auditoría
  humana del 100% (el tesista sigue siendo el evaluador de registro — ADR-004 §2.5
  intacto), y chequeo de concordancia espejo opcional (`gpt-5.5`, 10 ATs/celda).
- Para chequeos de estándares, la referencia normativa es el **corpus de H3**
  (prohibido resolver BIPs/EIPs "de memoria").

## Qué quedó construido

- `briefing.md` — instrucciones congeladas (rol, insumos permitidos/prohibidos,
  reglas de trabajo, tope de esfuerzo por AT: 15 min / 3 intentos, formato de salida).
- `rubrica-white-box.md` — 66/66 ATs (verificado contra el yaml, sin faltantes ni
  sobrantes), agrupados en familias: **F1** inspección de propiedad interna (31),
  **F2** criptografía/KATs con vectores del corpus (6), **F3** ciclo de vida del SUT
  (13), **F4** límites transaccionales/inyección de fallo (9), **F5** config-fault
  (7); F6 (tests propios del generador como evidencia) es transversal. Cada entrada:
  familia, propiedad (con HU/RN), pasos accionables agnósticos del stack, evidencia
  mínima, criterio cerrado.
- `plantilla-resultados.yaml` — 66 items pregenerados; metadatos con celda
  **anonimizada**. Salida por corrida en `runs/<id>/no-automatizables/`.
- Limpieza: dos referencias obsoletas al hueco de HU-02-05 (resuelto en spec-v1.1)
  quedaban en `no-automatizables.yaml`; corregidas.

## Pendientes / para la ventana de la piloto

1. **Posible sobre-declaración en F3**: varios motivos del yaml alegan que el
   harness no controla el ciclo de vida del SUT, pero la suite ya usa
   `SUITE_CMD_REINICIO_SUT` en tests condicionales de otras épicas — parte de los 13
   de F3 podría migrar a tests black-box condicionales. Revisar en la piloto.
2. **Dependencia de importar mnemonic**: los ATs de provisioning de la 06 asumen que
   el SUT soporta arrancar con un mnemonic inyectado; la spec no fija el mecanismo.
   La rúbrica da fallback (F1 + `PRECONDICION_IMPOSIBLE` tipificada), pero es un
   candidato a convención de entorno para fijar post-piloto.
3. La piloto ejercita el framework completo (agente, briefing, rúbrica, salida);
   ajustes por la vía de ADR-004 antes de las corridas oficiales.

## Commits

`5fbbfd8` adr ADR-007 · `375cfb1` evaluacion framework · (este commit) journal.
