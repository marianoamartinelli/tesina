# pre-piloto — verificación end-to-end del pipeline sobre un universo reducido

Corrida **descartable** que precede a la piloto (`piloto-01`/`piloto-02`), fijada por
[ADR-018](../../decisiones/ADR-018-corrida-pre-piloto.md). No cuenta para el factorial
2×2 ni cierra ítems de la ventana H6: su objeto es que **todos los componentes** —CLI de
los dos proveedores, contenedores, credenciales, servidor MCP del RAG, registro JSONL,
snapshots, suite black-box, agente evaluador white-box, rúbricas y métricas— hayan
corrido al menos una vez de punta a punta antes de gastar una corrida completa en
depurarlos.

Es una sola sesión de verificación con dos celdas, así que vive en un único directorio en
vez de uno por `run_id`; cada celda tiene su manifest y su log de intervenciones.

| Archivo | Qué es |
|---|---|
| [`matriz-componentes.md`](matriz-componentes.md) | qué componente se verifica con qué evidencia, y su estado |
| [`hallazgos.md`](hallazgos.md) | defectos y decisiones que la corrida saca a la luz — el producto que sí se conserva |
| `manifest-a.yaml` / `manifest-b.yaml` | configuración exacta de cada celda |
| `intervenciones-a.md` / `intervenciones-b.md` | log de intervenciones humanas, clasificado |

## Universo reducido

Backend: `HU-01-01`, `HU-01-02`, épica 06 completa, y de la épica 09 sólo lo que esas HU
exponen. Web: `HU-10-01`. Mobile: `HU-11-01` más la pantalla de depósito de `HU-11-06`.
Lo fijan, una sola vez cada uno, los prompts de `pipeline/comun/prompts/prepiloto/`
(qué se implementa) y [`evaluacion/pre-piloto/alcance.yaml`](../../evaluacion/pre-piloto/alcance.yaml)
(qué se evalúa).

La épica 06 está adentro a propósito: es la única del universo que obliga a consultar el
corpus (BIP-32/BIP-39/BIP-44), así que sin ella el servidor MCP del RAG quedaría sin
ejercitar. Las dos celdas corren **con** RAG por el mismo motivo — la pre-piloto no
manipula el factor RAG, lo ejercita.

## Cómo se corre

```bash
# 1. Repo satélite limpio (una vez por celda)
pipeline/crear-repo-satelite.sh pre-piloto-a ~/Desktop/projects/tesina-runs/pre-piloto-a

# 2. Puertas de arranque (las mismas del protocolo §3)
.venv/bin/python pipeline/verificar_paridad.py                      # exit 0
cd evaluacion/suite-at/entorno && docker compose up -d --wait \
  && ../../../.venv/bin/python desplegar-usdc.py                    # entorno on-chain

# 3. Una etapa (el avance entre etapas lo gatea el operador con el smoke check)
.venv/bin/python pipeline/harness_a/orquestar.py \
    --config pipeline/config/pre-piloto-a.yaml \
    --repo ~/Desktop/projects/tesina-runs/pre-piloto-a/tesina-run-pre-piloto-a \
    --etapa backend
```

`harness_b/orquestar.py` con `pre-piloto-b.yaml` para la celda B. El procedimiento de
evaluación reducida está en
[`evaluacion/pre-piloto/README.md`](../../evaluacion/pre-piloto/README.md).

## Reglas que siguen valiendo

- **No-exposición del holdout durante la generación** (protocolo §4): la suite de ATs no
  se corre ni se le reportan resultados al agente mientras genera. En la pre-piloto la
  evaluación va al final, igual que en una corrida real.
- **Toda intervención se registra en el momento**, clasificada por causa raíz.
- Los repos satélite de la pre-piloto se **descartan** al terminar; lo que se conserva es
  `hallazgos.md`, los manifests, los logs y las intervenciones.
