# ADR-018 — Corrida pre-piloto sobre un universo reducido de la spec

- **Estado:** **Aceptado** (decidido por el tesista el 2026-08-23)
- **Fecha:** 2026-08-23
- **Contexto:** ventana H6, con `piloto-01` y `piloto-02` todavía sin ejecutar.
- **Reemplaza a:** nada. Es aditivo: no toca el protocolo (v1.2, congelado por
  [ADR-016](ADR-016-sin-topes-de-presupuesto.md)), ni la spec (`spec-v1.1`), ni la
  partición de ATs ([ADR-011](ADR-011-particion-automatizable-white-box.md)), ni ningún
  ADR aceptado.

## Contexto

Al 2026-08-23 el pipeline está reescrito, contenedorizado y verificado **en seco**:
dry-runs de las 6 configs en las 3 etapas, paridad en verde (117 chequeos), el servidor
MCP hablado a mano por stdio, el bucle de ejecución corrido contra un CLI simulado, las
tres imágenes construidas y la autenticación de las dos familias resuelta
([ADR-017](ADR-017-credenciales-por-entorno-en-el-harness-a.md)). Lo que no ocurrió
nunca es que **un CLI de agente ejecute una etapa**: los 8 ítems abiertos de la
checklist H6 necesitan, todos, la corrida misma.

La piloto es la corrida que debe depurar protocolo, harness, registro y evaluación. Pero
`piloto-01` es una corrida **completa** —las 57 HU de la spec en 3 etapas—, y usarla para
descubrir que, por ejemplo, el sandbox de `codex exec` no deja correr `npm install`
(riesgo ya identificado, ítem 2 de la checklist) significa gastar una corrida larga en
depurar infraestructura. Los defectos de infraestructura no necesitan una spec completa
para aparecer: necesitan que cada componente se ejecute al menos una vez.

Hay además componentes que **ninguna corrida ha ejercitado todavía y que la piloto sola
tampoco cubre bien**: la suite black-box nunca corrió contra un SUT real (sólo su
auto-test de 40 casos, que no levanta ningún sistema), el agente evaluador white-box
nunca se ejecutó, y las rúbricas manuales nunca se completaron sobre una implementación.

## Decisión

### 1. Existe una corrida pre-piloto, previa a la piloto

Dos celdas descartables, **`pre-piloto-a`** y **`pre-piloto-b`**, una por familia, con
las 3 etapas cada una. Se corren con el mismo pipeline, los mismos contenedores, los
mismos model IDs y el mismo `effort` que las celdas oficiales. No cuentan para el
factorial 2×2, no cierran ítems de la checklist H6 y sus repos satélite se descartan.

Las dos familias, y no sólo una, porque los riesgos abiertos más concretos son del lado B
(red del sandbox `workspace-write`, esquema del JSONL de `--json`, estimación local de
costo) y del lado A la novedad es la autenticación por token de suscripción.

### 2. El universo es un subconjunto de la spec, acotado por el prompt de etapa

La spec **completa y sin recortar** va al repo satélite, igual que en una corrida
oficial: recortar `spec/` rompería las referencias cruzadas entre HU y la precedencia de
`00-fundaciones/`, y dejaría de ejercitar cómo el agente navega la spec real. Lo que
acota el trabajo es el **prompt de etapa**:

- **backend:** `HU-01-01` (registro), `HU-01-02` (login), **épica 06 completa**
  (`HU-06-01` a `HU-06-04`), y de la épica 09 sólo lo que esas HU exponen — tres
  endpoints de `HU-09-01`, más `HU-09-02` y `HU-09-05` aplicadas a ellos;
- **web:** `HU-10-01` (pantalla de login);
- **mobile:** `HU-11-01` (login) más la pantalla de depósito de `HU-11-06`
  (`AT-11-06-01` y `AT-11-06-26`).

La épica 06 está adentro por una razón mecánica: es la única del universo que obliga a
consultar los estándares del corpus (BIP-32, BIP-39, BIP-44), así que sin ella el
servidor MCP del RAG quedaría sin ejercitar. La vertical elegida también toca
autenticación, persistencia, lectura on-chain y los dos clientes.

Los prompts viven en `pipeline/comun/prompts/prepiloto/` y la definición de etapas en
`pipeline/comun/etapas-prepiloto.yaml`, que difiere de `etapas.yaml` **únicamente** en
las tres rutas de prompt de etapa (verificable con un `diff`, documentado en su
encabezado). Roles, secuencia implementador → revisor → implementador, prompt de sistema,
criterios de avance y configuración del RAG son los mismos archivos que usan las celdas
oficiales: lo que la pre-piloto prueba es la mecánica del pipeline, no una variante de él.

### 2 bis. El `effort` de la pre-piloto es `high`, no `xhigh`

Las celdas oficiales corren en `xhigh` (ADR-009 Decisión 3, sin cambios). La pre-piloto
baja a `high` en las dos familias: lo que verifica es que los componentes funcionen, no
la calidad de la implementación, y el `effort` no cambia ningún camino de código del
pipeline —viaja como `--effort` en A y como `-c model_reasoning_effort` en B, los dos
verificados en el smoke—. Es una diferencia más, junto con el prompt de etapa acotado,
por la que los resultados de la pre-piloto **no** son comparables con los de ninguna
celda.

### 3. Las dos celdas corren con RAG

La pre-piloto **no manipula** el factor RAG: lo ejercita. Correr una celda sin RAG no
verificaría nada que la celda con RAG no verifique, y dejaría sin probar el servidor MCP
en esa familia.

### 4. La evaluación reducida corre completa, al cierre

Sobre cada implementación generada se ejecutan las cuatro vías de H8, acotadas al
universo: la **suite black-box** sobre los ATs del alcance (56 ATs con test, 53 funciones,
seleccionados por nodeid con `evaluacion/pre-piloto/seleccionar.py`), el **agente
evaluador white-box** sobre los 22 ATs del alcance declarados no automatizables —dos
pasadas, validador mecánico y arbitraje, como manda
[ADR-007](ADR-007-agente-evaluador-white-box.md)—, las **rúbricas** de las HU de cliente
del alcance más la del rol revisor, y las **métricas estáticas**.

La **regla de no-exposición del holdout se mantiene íntegra**: durante la generación no
se corre la suite ni se le adelanta al agente resultado alguno; la evaluación va al final,
como en una corrida real (protocolo §4).

### 5. Qué se puede corregir después de la pre-piloto, y qué no

La pre-piloto produce implementaciones, y el protocolo §9 dice que la suite de ATs no se
modifica «después de vista ninguna implementación». Esa cláusula protege el **criterio**
de evaluación, no sus defectos de programación. Se fija entonces, para la pre-piloto y
para la piloto por igual:

- **Se admite corregir el harness:** un test que falla o saltea por su propia causa
  —fixture rota, helper mal usado, aserción que no dice lo que la spec dice—. Cada
  corrección se registra en `runs/pre-piloto/hallazgos.md` citando la parte de
  `spec-v1.1` que la fundamenta.
- **No se admite mover el criterio:** qué exige un AT, la partición 465/56, la frontera
  automatizable/white-box, los ítems de las rúbricas y el alcance de las métricas
  estáticas quedan como están. Un cambio ahí necesita ADR nuevo y una justificación que
  no sea «lo que la implementación hizo».
- Todo cambio a `evaluacion/` derivado de la pre-piloto se cierra **antes** de iniciar
  `piloto-01`.

### 6. Sin topes, con registro

Coherente con ADR-016: no hay `costo_max_usd` ni `tiempo_max_horas`. El control de
consumo acá es el alcance reducido, no un umbral. Costo, tokens, turnos y tiempo se
registran, y el dato sirve para dimensionar lo que la piloto y las oficiales van a
consumir — que es la incógnita que ADR-016 dejó explícitamente abierta.

## Consecuencias

- La ventana H6 se alarga: la pre-piloto es trabajo adicional antes de `piloto-01`. A
  cambio, la piloto arranca con los componentes ya ejercitados y puede dedicarse a lo
  suyo —el protocolo y el registro sobre una corrida completa— en vez de a depurar
  infraestructura.
- **El evaluador ve dos implementaciones parciales antes de las corridas oficiales.** Es
  la misma exposición que ya implicaba la piloto, adelantada y acotada a 6 HU de backend
  y 2 de cliente. Se suma a `analisis/amenazas-validez.md`.
- **La pre-piloto no mide adherencia a la spec completa** y sus resultados no son
  comparables con los de ninguna celda: el agente recibió un prompt de etapa distinto. No
  se reportan como resultado del experimento en ningún lado; su `resultados-at.csv` marca
  `sin_test` todo lo que quedó fuera del alcance, precisamente para que no se lo confunda
  con una evaluación completa.
- Los prompts de la pre-piloto viven bajo `comun/`, que las celdas con RAG montan
  read-only, así que un agente oficial podría leerlos. Es la misma exposición que ya
  tienen `etapas.yaml`, el prompt de sistema y los prompts de rol, y no afecta a las
  celdas sin RAG, que no montan `comun/`.
- `verificar_paridad.py` sigue verificando **sólo las 4 celdas oficiales**: la pre-piloto
  no entra a la paridad, y se comprobó que agregarla no la altera (117 chequeos, exit 0).
