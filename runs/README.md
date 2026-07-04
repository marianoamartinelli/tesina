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
├── manifest.yaml        # configuración exacta y referencias (plantilla abajo)
├── intervenciones.md    # log clasificado de intervenciones humanas
├── metricas.md          # resultados de la evaluación (por AT-id, estáticas, etc.)
└── notas.md             # observaciones cualitativas durante la corrida
```

Plantillas: [`plantillas/manifest.template.yaml`](plantillas/manifest.template.yaml) y
[`plantillas/intervenciones.template.md`](plantillas/intervenciones.template.md).

## Reglas

1. El manifest se completa **antes de iniciar** la corrida (todo salvo los campos de
   cierre) y se commitea; los campos de cierre se completan al finalizar.
2. Toda intervención humana se registra en el momento, clasificada según las 8
   categorías de causa raíz del protocolo experimental.
3. Terminada la corrida, su repo queda congelado (sólo lectura) y este directorio se
   completa con métricas y notas. Correcciones posteriores invalidan la medición.
