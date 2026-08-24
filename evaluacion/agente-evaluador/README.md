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
  runtime de ADR-007 Decisión 1). Los flags concretos los fija **`correr.py`**, escrito en
  la pre-piloto (ADR-018), que cierra el `PENDIENTE-ARRANQUE` que este README tenía:

  ```bash
  .venv/bin/python evaluacion/agente-evaluador/correr.py \
      --sut <repo-congelado> --salida runs/<id>/no-automatizables --pasada 1 [--dry-run]
  ```

  Lo que decide, y por qué está acá y no en el briefing (que es texto congelado):

  - **Aislamiento de insumos por mecanismo:** arma un directorio de trabajo bajo `/tmp`
    con **sólo** lo que el briefing §2 permite —briefing, rúbrica, plantilla, `spec/`,
    `corpus/` y la copia del SUT sin `.git`— y corre el CLI ahí. El agente no ve el árbol
    de la tesina, así que la prohibición de mirar `suite-at/`, `runs/`, `journal/` y
    `analisis/` no depende de que la respete: es el criterio de ADR-015 aplicado al
    evaluador.
  - **Aislamiento de la config del host:** `--setting-sources ""` y `--strict-mcp-config`,
    como en la generación (ADR-009 D5). El evaluador **no** usa el servidor MCP del RAG:
    el briefing lo manda leer el corpus como archivos y citar documento y sección.
  - **Sin recuperación web:** `--disallowed-tools WebSearch,WebFetch`. Acá el motivo es
    más fuerte que en la generación — la regla de oro del briefing obliga a que toda
    referencia normativa salga del corpus congelado.
  - **Registro:** JSONL con el mismo formato que el pipeline (`comun/nucleo.py`), con los
    SHA-256 del briefing y de la rúbrica en el evento inicial.
  - **No corre en contenedor**, a diferencia de la generación: necesita hablar con el SUT
    y el nodo on-chain que corren en el host, y no hay paridad entre celdas que preservar
    (es el mismo instrumento, corrido igual las 8 veces).
  - `--effort xhigh`, el mismo de las corridas de generación. Ningún ADR fija el `effort`
    del evaluador: queda a ratificación del tesista.
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
