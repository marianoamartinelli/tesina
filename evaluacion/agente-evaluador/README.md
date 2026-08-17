# Agente evaluador white-box

Framework de evaluación de los **56 ATs no automatizables** black-box de las épicas
01–09 ([ADR-007](../../decisiones/ADR-007-agente-evaluador-white-box.md); la partición
465/56 la fija [ADR-011](../../decisiones/ADR-011-particion-automatizable-white-box.md)).
El agente es un **instrumento**: el evaluador de registro sigue siendo el tesista, que
audita el 100 % de los veredictos contra su evidencia (ADR-004 §2.5).

## Archivos

| Archivo | Qué es |
|---------|--------|
| `briefing.md` | Instrucciones **congeladas**; se pasan verbatim en las 4 celdas y en cada pasada. Sin prompts ad hoc. |
| `rubrica-white-box.md` | Checklist operativo: familia, propiedad, pasos, evidencia mínima y criterio cerrado, AT por AT, en orden ascendente de at_id. |
| `plantilla-resultados.yaml` | Formato de salida obligatorio: metadatos + 56 items. |
| `validar-resultados.py` | Validación mecánica de cada pasada **antes** del arbitraje humano. |

## Ejecución

- **Modelo pinneado:** `claude-opus-5`, y el **chequeo de concordancia espejo** —opcional,
  muestra de 10 ATs por celda (ADR-007 §3 punto 5)— `gpt-5.6-sol`. Ambos re-pinneados por
  [ADR-010](../../decisiones/ADR-010-delegacion-contexto-y-evaluador.md) Decisión 3. Su
  ejecución u omisión se decide por el costo observado en la piloto (checklist H6, ítem 6).
- **Runtime:** `claude -p` en modo headless, con lectura de archivos y bash — las únicas
  herramientas que la evaluación white-box necesita (ADR-010 Decisión 3, que reemplaza el
  runtime de ADR-007 Decisión 1). Los flags concretos de la invocación (permisos de
  herramientas, formato de salida, registro del JSONL) siguen sin fijarse:
  **PENDIENTE-ARRANQUE**, a resolver antes de H8. El orquestador de generación
  (`pipeline/harness_a/orquestar.py`, checklist H6 ítem 17) sirve de referencia, pero no
  cubre esta invocación: el evaluador no es una celda del pipeline.
- **Sesión fresca por celda y por pasada**, sin memoria de las anteriores y sin `resume`;
  dos pasadas independientes por celda (ADR-007 §3 punto 3).
- **Insumos permitidos y prohibidos:** los enumera el briefing §2 (spec `spec-v1.1`,
  corpus congelado de H3, copia de evaluación sin `.git`, entorno levantado; prohibidos
  los resultados de la suite black-box, otras celdas y la otra pasada).

## Salida y arbitraje

Cada pasada se archiva como `runs/<id>/no-automatizables/pasada-<n>.yaml` y se valida
antes de arbitrar:

```bash
.venv/bin/python evaluacion/agente-evaluador/validar-resultados.py \
    runs/<id>/no-automatizables/pasada-1.yaml
```

El humano arbitra las discrepancias entre pasadas con la evidencia de ambas y firma
`veredicto-final.yaml` (mismo esquema; se valida con `--final`). Estos veredictos
alimentan **sólo** la fila `no_automatizado` del dataset de H8: nunca se suman a los
`pasa`/`falla` de `evaluacion/suite-at/resultados-at.csv` ni entran en la métrica
principal `pasa / (pasa + falla)`.
