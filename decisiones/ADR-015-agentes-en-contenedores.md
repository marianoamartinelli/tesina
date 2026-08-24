# ADR-015 — Los agentes corren en contenedores, con toolchain común y capa por CLI

- **Estado:** **Aceptado** (ratificado por el tesista el 2026-08-23)
- **Fecha:** 2026-08-23
- **Contexto:** ventana H6, corrida piloto sin ejecutar.
- **Reemplaza a:** de [ADR-009](ADR-009-harnesses-como-cli-y-orquestador-de-roles.md)
  **Decisión 1**, la asimetría declarada como «Confinamiento: B sandboxea el shell por
  default, A no en modo headless». Deja de ser una asimetría aceptada: se iguala. El
  resto de ADR-009 D1 —los CLI como harness, lo idéntico entre celdas, las otras tres
  asimetrías— se conserva. ADR-009 no se edita.
- **Cierra:** el ítem 11 de la checklist H6.

## Contexto

Con los CLI, el confinamiento quedó invertido respecto de los SDK: Codex sandboxea el
shell por default (`-s workspace-write`) y Claude Code en headless no. El orquestador A
usa `--dangerously-skip-permissions`, con lo cual `Bash` y `Read` pueden leer fuera del
cwd — incluida `evaluacion/`, que es el holdout. La no-exposición del holdout
(protocolo §9) la sostenía sólo el procedimiento.

La checklist preveía decidir el confinamiento *después* de observarlo con el CLI real. El
tesista decidió el 2026-08-23 no esperar a ese dato: los agentes corren en contenedores
en las dos familias, independientemente de las capacidades de sandboxing que cada CLI
traiga.

## Decisión

### 1. Toda invocación de rol ocurre dentro de un contenedor

Vale para las 4 celdas oficiales y para las dos piloto. El orquestador no invoca el CLI
en el host: invoca el contenedor de su familia. Las capacidades de sandboxing nativas de
cada CLI **no se tocan** —B sigue con `-s workspace-write`, A sigue con
`--dangerously-skip-permissions`—: el contenedor es una capa exterior que no depende de
ellas, y así lo que cada agente ve de su propio entorno sigue siendo el default de su
producto.

### 2. Imagen base común más una capa fina por CLI

- `pipeline/contenedores/Dockerfile.base` — toolchain idéntico para las dos familias:
  runtime de Node y npm, Python, git y las dependencias de build de las tres etapas
  (backend, web, mobile/Expo). Versiones pinneadas.
- `pipeline/contenedores/Dockerfile.a` y `Dockerfile.b` — parten de la base y sólo
  instalan el CLI de su proveedor, en la versión que el manifest pinnea.

Motivo del split: la paridad del entorno de build queda **por construcción**, verificable
como que ambas capas declaran la misma base. Una imagen única con los dos CLI instalados
se descartó porque cada agente vería el binario del competidor en su `PATH`, que es
entorno observable por el modelo.

### 3. Credenciales por bind-mount read-only

`~/.claude/.credentials.json` y `~/.codex/auth.json` se montan read-only en el contenedor
de su familia. Se conserva el modo suscripción de ADR-009 sin login interactivo por
celda, y el arranque queda reproducible.

Riesgo asumido y declarado: un token de suscripción es legible desde adentro del
contenedor del agente. Es el mismo alcance que el agente ya tiene hoy corriendo en el
host — el contenedor no lo agrava.

### 4. Red abierta en la piloto

El contenedor sale a internet sin restricción: lo necesitan `npm install`, `expo export`
y la API del propio proveedor. La piloto **registra qué hosts se tocan realmente**, y con
ese dato se decide antes de H7 si se agrega una allowlist por proxy.

Consecuencia que se declara, no se resuelve: shell más red permiten recuperar de internet
aunque las herramientas web estén desactivadas ([ADR-014](ADR-014-recuperacion-web-en-el-harness-b.md)
punto 3). Ahora vale por igual en A y B, que es la diferencia con la situación anterior.

### 5. El holdout no se monta

El contenedor monta el repo satélite y nada más del árbol de la tesina. `evaluacion/` no
está montado, así que la no-exposición del holdout pasa a sostenerse en el **mecanismo**
en vez del procedimiento — que es el motivo por el que este ADR cierra el ítem 11.

## Consecuencias

- **Mejora la paridad del factor pipeline**, que era una de las cuatro asimetrías que
  ADR-009 D1 declaraba como limitación del cap. 4. Las otras tres siguen vigentes.
- **El toolchain deja de ser una variable del host.** Antes, la versión de Node con la
  que buildea cada celda era la de la máquina; ahora está pinneada en la imagen y entra
  al manifest.
- **El manifest suma el digest de las tres imágenes**, con el mismo criterio que el pin
  por digest del anvil (ítem 13): un tag es flotante.
- **`verificar_paridad.py` chequea que ambas capas parten de la misma base** y que las
  dos familias montan el mismo conjunto de rutas.
- **Costo:** construir y mantener las imágenes, y que un fallo de build de imagen bloquee
  el arranque de una celda. Se acepta a cambio de eliminar la asimetría.
- **La piloto valida la contenerización misma**, no sólo el pipeline: si los builds de
  etapa fallan dentro del contenedor por algo que en el host andaba, es defecto a
  corregir dentro de la ventana H6.

## Alternativas consideradas

- **Decidir con lo que observe la piloto** (lo que la checklist scripteaba). Rechazada
  por el tesista: la asimetría de confinamiento no depende de lo que se observe.
- **Confinar sólo A**, que es el lado sin sandbox. Rechazada: dejaría el confinamiento de
  cada familia en manos de un mecanismo distinto, que es la asimetría movida de capa.
- **Login interactivo dentro del contenedor.** Rechazada: suma un paso manual por celda y
  un volumen de sesión que declarar, sin cerrar un riesgo que el agente no tuviera ya.
