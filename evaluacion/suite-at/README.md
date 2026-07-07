# suite-at — suite de tests de aceptación black-box (H5)

Harness que verifica los **criterios de aceptación de la spec** (AT-id por AT-id)
contra una implementación del exchange, exclusivamente a través del **contrato
HTTP/WebSocket de la épica 09** (más el estado on-chain del entorno local). Se
escribió **una sola vez, antes de que existiera implementación alguna**, y corre
**idéntica** contra las 4 implementaciones del factorial 2×2 (ADR-004).

Cubre los **521 ATs backend (épicas 01–09)**: 455 con test automatizado (449
funciones de test; la relación test↔AT es muchos-a-muchos) + 66 declarados en
`no-automatizables.yaml`, que se evalúan en H8 vía el agente white-box de
ADR-007. Los de épicas 10–11 (web/mobile, 172 ATs) se evalúan con las rúbricas
de `../rubricas/`.

## Regla de no-exposición del holdout (obligatoria)

> La suite **NUNCA se corre durante una corrida de generación** (H6/H7), ni se le
> adelantan al agente resultados parciales. Corre **una sola vez por corrida, al
> cierre, en H8** (`../protocolo.md` §4). Usar el holdout como feedback durante
> la generación lo convertiría en set de entrenamiento y sesgaría la métrica
> principal. El smoke check de avance de etapa del protocolo **no** usa esta suite.

## Contenido

| Ruta                     | Qué es                                                        |
|--------------------------|----------------------------------------------------------------|
| `catalogo.py`            | genera `catalogo-at.csv` desde `spec/` (693 ATs, regenerable)  |
| `catalogo-at.csv`        | catálogo: at_id, épica, HU, archivo, título, tipo              |
| `conftest.py`            | fixtures black-box + plugin de reporte por AT-id               |
| `pytest.ini`             | registro del marker `at`, testpaths                            |
| `helpers/`               | clientes HTTP/WS, cuentas, montos, errores, EIP-55, espera, on-chain (API documentada en `HELPERS.md`) |
| `entorno/`               | anvil local (chainId 11155111) + USDC-mock + fondeo (ver su README: **contrato de arranque del SUT**) |
| `tests/`                 | tests por épica (`test_epNN_*.py`); incluye `test_ep09_contrato.py` como referencia de estilo |
| `test_smoke.py`          | tests del propio harness (sin SUT): siempre deben pasar        |
| `no-automatizables.yaml` | ATs de 01–09 no verificables black-box, con motivo             |
| `HELPERS.md`             | guía para escribir los tests por épica                         |
| `requirements.txt`       | dependencias pinneadas                                         |

## Instalación

```bash
# desde la raíz del repo (usa el venv existente)
.venv/bin/pip install -r evaluacion/suite-at/requirements.txt
```

Verificar el harness (no requiere SUT ni docker):

```bash
cd evaluacion/suite-at
../../.venv/bin/python -m pytest test_smoke.py -q     # debe dar todo verde
```

## Cómo se corre una evaluación (H8)

### 1. Levantar el entorno on-chain

```bash
cd evaluacion/suite-at/entorno
docker compose up -d --wait                  # anvil en :8545, chainId 11155111
../../../.venv/bin/python desplegar-usdc.py  # despliega el USDC-mock
source entorno.env                           # EVAL_RPC_URL, EVAL_USDC_ADDRESS, EVAL_USDC_DEPLOY_BLOCK
```

### 2. Arrancar la implementación evaluada (SUT)

Configurarla con los parámetros del **contrato de arranque** (`entorno/README.md`):
nodo RPC `http://127.0.0.1:8545`, dirección del USDC-mock, bloque de inicio del
indexador. Antes de los tests de retiros, fondear su hot wallet:
`python entorno/fondear.py 0x<emisora> --eth 100 --usdc 1000000`.

### 3. Apuntar la suite y correr

```bash
cd evaluacion/suite-at
export EXCHANGE_API_URL="http://localhost:3000"          # URL raíz del SUT (sin /api/v1)
export EXCHANGE_WS_URL="ws://localhost:3000/api/v1/ws"   # endpoint WS (RG-API-11)
export SUITE_CMD_REINICIO_SUT="..."                      # reinicio abrupto del SUT (ver nota)
../../.venv/bin/python -m pytest tests/ -q
```

`SUITE_CMD_REINICIO_SUT` es un comando de shell provisto por el evaluador que
**termina abruptamente** el proceso del SUT (equivalente a `kill -9`,
HU-03-07 RN-1), preserva su persistencia y lo vuelve a levantar; la suite espera
la readiness por polling de `GET /market/ticker` (timeouts de 90–120 s ya
codificados en los helpers).

Sin `EXCHANGE_API_URL`/`EXCHANGE_WS_URL` los tests contra el SUT **se saltan
solos** (y el reporte los marca `skip`): la suite nunca "inventa" un veredicto.
Sin `SUITE_CMD_REINICIO_SUT` quedan `skip` los tests de reinicio (AT-03-07-01/
02/03/05/06/07/08, AT-01-03-08, AT-01-03-10, AT-01-01-11 y AT-02-04-06), con lo
que la corrida **viola la regla `skip = 0`** de una corrida H8 válida (ver
"Cómo leer `resultados-at.csv`").

### 4. Guardar los resultados

`resultados-at.csv` se escribe al final de la corrida (configurable con
`SUITE_RESULTADOS_AT=/ruta/salida.csv`). Copiarlo a `runs/<id>/` y volcar el
resumen a `runs/<id>/metricas.md`, según el protocolo. Entre implementaciones:
`docker compose down && up` + redeploy del mock + reinicio del SUT (estado
on-chain limpio por celda).

## Cómo leer `resultados-at.csv`

Una fila por **cada** AT backend del catálogo (521), ordenadas por at_id:

| Columna              | Contenido                                                     |
|----------------------|----------------------------------------------------------------|
| `at_id`              | ID estable del criterio (p. ej. `AT-03-02-01`)                 |
| `resultado`          | ver tabla de categorías                                        |
| `test`               | nodeid(s) pytest que lo verifican, separados por `;`           |
| `duracion_segundos`  | suma de duraciones de esos tests                               |
| `detalle`            | motivo (para `no_automatizado` / `sin_test`)                   |

| `resultado`       | Significado                                                            |
|-------------------|-------------------------------------------------------------------------|
| `pasa`            | todos sus tests pasaron (≥ 1)                                          |
| `falla`           | al menos un test falló (incluye errores de fixture)                    |
| `skip`            | tiene tests pero se saltaron (típico: SUT/entorno no configurado)      |
| `no_automatizado` | declarado en `no-automatizables.yaml`; se evalúa por otra vía (H8)     |
| `sin_test`        | hueco de **cobertura de la suite** (no dice nada del SUT; debe tender a 0 antes de la primera evaluación) |

La métrica principal del experimento (tasa de ATs superados) se computa sobre
`pasa / (pasa + falla)` por épica y total; `no_automatizado` se reporta aparte
(con su vía de evaluación) y `skip`/`sin_test` deben ser 0 en una corrida H8 válida.

## Mantenimiento

- **Regenerar el catálogo** (sólo si la spec congelada cambiara, cosa que no
  debería pasar fuera de la ventana del piloto): `python catalogo.py` — falla si
  el total difiere de 693.
- **Escribir tests de una épica**: leer `HELPERS.md` (convenciones, fixtures,
  ejemplo completo) y usar `tests/test_ep09_contrato.py` como referencia de estilo.
- **Tests del harness**: cualquier cambio en `helpers/` o en el plugin de reporte
  debe mantener `test_smoke.py` en verde y, si agrega comportamiento, cubrirlo ahí.
