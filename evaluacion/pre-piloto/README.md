# Evaluación reducida de la pre-piloto

Procedimiento para evaluar las implementaciones que genera la corrida pre-piloto
([ADR-018](../../decisiones/ADR-018-corrida-pre-piloto.md)). Ejercita las **cuatro vías
de H8** —black-box, white-box, rúbricas y métricas estáticas— acotadas al universo
reducido, con los instrumentos reales y sin modificarlos.

No produce un resultado del experimento: mide que la maquinaria de evaluación corre.
Los CSV y veredictos que genera no son comparables con los de ninguna celda oficial.

| Archivo | Qué es |
|---|---|
| [`alcance.yaml`](alcance.yaml) | qué HU se evalúan, y cuáles se implementan sin evaluar |
| [`seleccionar.py`](seleccionar.py) | expande el alcance a AT-ids y a nodeids de pytest |
| `nodeids.txt` | salida: los tests black-box del alcance (regenerable) |
| `ats-white-box.txt` | salida: los ATs del alcance no automatizables (regenerable) |

```bash
.venv/bin/python evaluacion/pre-piloto/seleccionar.py
# alcance:   6 HU backend → 78 ATs
# black-box: 56 ATs con test, en 53 funciones
# white-box: 22 ATs declarados no automatizables
# sin cubrir: 0
```

Que los 78 ATs se repartan sin residuo entre las dos vías no es casual: la partición
465/56 de [ADR-011](../../decisiones/ADR-011-particion-automatizable-white-box.md) cubre
los 521 ATs backend, y el alcance sólo la restringe.

## 1. Black-box

Con el SUT arrancado según el contrato de arranque (`suite-at/entorno/README.md`) y el
entorno on-chain levantado:

```bash
cd evaluacion/suite-at
export EXCHANGE_API_URL="http://localhost:<puerto>"
export EXCHANGE_WS_URL="ws://localhost:<puerto>/api/v1/ws"
export SUITE_CMD_REINICIO_SUT="..."          # precondición dura (ADR-011)
export SUITE_RESULTADOS_AT="../../runs/pre-piloto/resultados-at-<celda>.csv"
../../.venv/bin/python -m pytest $(cat ../pre-piloto/nodeids.txt) -q
```

Se pasan **nodeids explícitos**: los tests fuera del alcance no se recolectan, así que el
reporte los marca `sin_test` en vez de acumular fallas por endpoints que el prompt de
etapa nunca pidió. Es el motivo por el que este CSV **no** se lee como una evaluación
completa.

Qué mirar, que es lo que la pre-piloto viene a averiguar: si un test falla por defecto del
SUT (esperable) o por defecto del harness —fixture rota, helper mal usado, aserción que no
dice lo que la spec dice—. Lo segundo se corrige y se registra en
`runs/pre-piloto/hallazgos.md`; el criterio de un AT no se toca (ADR-018 Decisión 5).

### Falsos positivos conocidos (sólo en la pre-piloto)

Un test puede pertenecer a una HU del alcance y aun así recorrer endpoints de otras
épicas para verificar propiedades transversales — que ninguna respuesta autenticada
exponga el seed, que los balances iniciales estén en cero—. Con la spec recortada esos
endpoints no existen y el test falla con 404 **sin que haya defecto del SUT**.

Medido en `pre-piloto-b`: **7 de los 7 ATs en falla** son de esta clase (`/balances` de
la épica 02 y `/withdrawals` de la épica 08). Criterio de lectura del CSV de la
pre-piloto: ante una falla, primero verificar si el endpoint involucrado estaba en el
alcance. En una corrida oficial el problema no existe, porque la spec va entera.

## 2. White-box

Sobre los 22 ATs de `ats-white-box.txt`, con el framework de
[`../agente-evaluador/`](../agente-evaluador/) sin modificaciones: briefing verbatim,
rúbrica congelada, `claude-opus-5`, **dos pasadas independientes** en sesiones frescas,
validación mecánica de cada una y arbitraje humano.

Dos detalles propios de la pre-piloto:

- La plantilla exige **56 items**, uno por cada AT no automatizable. Los 34 fuera del
  alcance se emiten como `NO_EVALUABLE` con causa `FUNCION_NO_LOCALIZABLE` y una línea de
  justificación —su épica no se implementó en esta corrida—, sin dedicarles tiempo de
  análisis. Así el validador corre tal como está, sin tocar un instrumento
  pre-registrado.
- **La invocación del evaluador todavía no está fijada** (`agente-evaluador/README.md`
  §Ejecución: PENDIENTE-ARRANQUE, a resolver antes de H8). Fijarla acá —flags de
  herramientas, formato de salida, registro del JSONL, aislamiento de la config del
  host— es uno de los productos de la pre-piloto: se documenta en `hallazgos.md` y, si
  implica una decisión metodológica, en un ADR.

```bash
.venv/bin/python evaluacion/agente-evaluador/validar-resultados.py \
    runs/pre-piloto/no-automatizables-<celda>/pasada-1.yaml
```

## 3. Rúbricas

Sobre copia por corrida, como en H8: `rubricas/epica-10-web.md` acotada a los ítems de
`HU-10-01`; `rubricas/epica-11-mobile.md` acotada a `HU-11-01` y a la pantalla de
depósito de `HU-11-06`; `rubricas/rol-revisor.md` completa, sobre las revisiones y los
snapshots que el orquestador dejó en cada etapa.

Lo que se verifica es el instrumento: si un ítem de rúbrica es ambiguo o no se puede
decidir con la evidencia disponible, es un hallazgo — y su corrección va antes de H7, que
es lo que la cláusula de re-pre-registro de `rol-revisor.md` ya prevé (protocolo §9).

## 4. Métricas estáticas

```bash
evaluacion/metricas-estaticas/medir.sh <ruta-al-repo-satelite>
```

Sobre los dos repos satélite, con `.pipeline/` excluido (protocolo §10.3). Acá interesa
que el script corra sobre un árbol real —con el stack que el agente eligió, no el
previsto— y que sus conteos sean interpretables.
