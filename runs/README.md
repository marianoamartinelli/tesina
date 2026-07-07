# Runs — registro de corridas del pipeline

Un directorio por corrida. La implementación generada **no** vive acá (ver ADR-001):
vive en un repo propio, referenciado desde el manifest.

## Nomenclatura

- Celdas oficiales del 2×2: `a-sin-rag`, `a-con-rag`, `b-sin-rag`, `b-con-rag`
  (A = Claude / Claude Agent SDK; B = GPT / OpenAI Agents SDK).
- Piloto: `piloto-NN` (no cuenta para el análisis factorial).

## Contenido mínimo por corrida

```
runs/<run-id>/
├── manifest.yaml            # configuración exacta y referencias (plantilla abajo)
├── intervenciones.md        # log clasificado de intervenciones humanas
├── metricas.md              # resultados de la evaluación (por AT-id, estáticas, etc.)
├── notas.md                 # observaciones cualitativas durante la corrida
├── logs/                    # JSONL del pipeline, dato primario (regla 4 abajo)
├── no-automatizables/       # pasada-1.yaml, pasada-2.yaml, veredicto-final.yaml
│                            #   (agente evaluador white-box, ADR-007 §4; en H8)
├── rubricas/                # copia completada de las rúbricas 10/11 + CSV de veredictos
│                            #   por corrida (ver evaluacion/rubricas/README.md; en H8)
├── metricas-estaticas.csv   # salida de evaluacion/metricas-estaticas/medir.sh (H8)
└── resultados-at.csv        # salida de la suite black-box (H8)
```

Plantillas: [`plantillas/manifest.template.yaml`](plantillas/manifest.template.yaml) y
[`plantillas/intervenciones.template.md`](plantillas/intervenciones.template.md).

La piloto agrega además un artefacto propio, que no forma parte del contenido mínimo
de las corridas oficiales: [`piloto-01/checklist-h6.md`](piloto-01/checklist-h6.md)
(checklist de entrada/salida de la ventana H6).

## Reglas

1. El manifest se completa **antes de iniciar** la corrida (todo salvo los campos de
   cierre) y se commitea; los campos de cierre se completan al finalizar.
2. Toda intervención humana se registra en el momento, clasificada según las 8
   categorías de causa raíz del protocolo experimental.
3. Terminada la corrida, su repo queda congelado (sólo lectura) y este directorio se
   completa con métricas y notas. Correcciones posteriores invalidan la medición.
4. **Archivado de logs:** al cerrar cada etapa (o, a más tardar, al cerrar la
   corrida), los JSONL que el pipeline escribe en `<repo-satelite>/../logs/` se
   copian a `runs/<id>/logs/` y se listan en el campo `logs_jsonl` del manifest
   (§5). Una etapa puede tener varios JSONL (reintentos — intervención tipo (d)
   del protocolo §5); se copian todos.
