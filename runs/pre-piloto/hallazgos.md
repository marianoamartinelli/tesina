# Hallazgos de la pre-piloto

Defectos, sorpresas y decisiones pendientes que la corrida saca a la luz, en orden de
aparición. Es el producto principal de la pre-piloto: la implementación generada se
descarta, esto no.

Cada hallazgo dice qué componente toca (numeración de
[`matriz-componentes.md`](matriz-componentes.md)), qué se observó, y qué corrección
requiere: `pipeline` (código del harness), `protocolo` (ADR nuevo), `evaluación`
(suite/rúbricas/briefing) o `ninguna` (comportamiento esperado, se documenta y listo).

Un hallazgo que exija cambiar metodología sale por **ADR nuevo**. Nada se corrige
editando `spec/` (congelada en `spec-v1.1`) ni ADRs aceptados.

---

## H-01 — El tag de spec es anotado: `rev-parse spec-v1.1` no da el commit

- **Componente:** 1.7 (repo satélite)
- **Observado:** `git rev-parse spec-v1.1` devuelve `b93db9f8…`, que es el objeto tag,
  no el commit. El commit es `c00da9b8…` (`spec-v1.1^{commit}`). Un manifest que
  registre el primero apunta a un objeto que no es el estado de la spec.
- **Corrección:** `pipeline` — `crear-repo-satelite.sh` resuelve `"$TAG^{commit}"` y
  eso es lo que imprime y lo que va al manifest.
- **Estado:** resuelto.

## H-02 — El layout del repo satélite y sus logs no estaba definido

- **Componente:** 1.7
- **Observado:** el orquestador escribe el JSONL en `<repo>/../logs/`, así que dos
  corridas con sus repos hermanos en un mismo directorio compartirían el directorio de
  logs. El manifest de `piloto-01` nombra el repo `tesina-run-piloto-01` sin fijar
  dónde cuelga.
- **Corrección:** `pipeline` — `crear-repo-satelite.sh` fija el layout
  `<destino>/tesina-run-<id>/` con `<destino>/logs/` al lado, y lo documenta.
  La piloto y las 4 oficiales lo heredan.
- **Estado:** resuelto.

## H-03 — `codex exec` no arranca en el contenedor: `CODEX_HOME` no es escribible

- **Componente:** 2.2 / 2.4 (imagen y credenciales de B)
- **Observado:** primera invocación real de `codex exec` dentro del contenedor:
  `WARNING: proceeding, even though we could not create PATH aliases: Permission denied
  (os error 13)` seguido de `Error: failed to initialize in-process app-server client:
  Permission denied (os error 13)`, exit 1, sin llegar a hablar con el modelo.
  Causa: el bind-mount de `~/.codex/auth.json` en `/home/agente/.codex/auth.json` hace
  que docker cree el directorio padre —que la imagen no tenía— como `root:root 755`. El
  usuario `agente` (uid 1001) no puede escribir ahí, y Codex necesita `CODEX_HOME`
  **escribible**, no sólo legible: escribe aliases de PATH y estado de sesión.
- **Corrección:** `pipeline` — `Dockerfile.b` crea `/home/agente/.codex` con dueño
  `agente` antes del montaje. Imagen `tesina/agente-b:piloto-01` reconstruida; digest
  nuevo `sha256:d15e87122831…` (el anterior era `ab065e2f3eed…`), registrado en los
  manifests.
- **Verificado:** tras el fix, `codex exec` completa un turno con exit 0 y el servidor
  MCP del RAG responde.
- **Estado:** resuelto.
- **Alcance:** habría cortado `piloto-02` y las dos celdas B oficiales en su primera
  invocación.

## H-04 — El sandbox nativo de Codex no funciona dentro del contenedor: B se queda sin shell

- **Componente:** 3.3 (sandbox de B con red)
- **Observado:** con `-s workspace-write`, **todo** comando que el modelo ejecuta falla
  con `bwrap: No permissions to create a new namespace, likely because the kernel does
  not allow non-privileged user namespaces`, exit 1. El turno completa, el modelo
  reporta lo que puede leer por sus herramientas de archivo, pero no ejecuta nada:
  sin shell no hay `npm install`, ni build, ni verificación. Las dos celdas B quedarían
  inservibles.
  Causa: Codex confina los comandos con bubblewrap, que necesita crear user namespaces;
  el perfil seccomp por default de Docker bloquea esas syscalls. Medido: el kernel de la
  VM sí los permite (`/proc/sys/user/max_user_namespaces` = 31319), y el `bwrap`
  embebido del CLI corre bien con `--security-opt seccomp=unconfined`.
- **Salidas medidas** (las tres con el comando real del orquestador y el override
  impreso antes de ejecutar):
  - `--security-opt seccomp=unconfined` en el `docker run` de B → shell exit 0;
  - `--dangerously-bypass-approvals-and-sandbox` en `codex exec` → shell exit 0;
  - `-s danger-full-access` → sigue fallando: el wrapper bwrap se aplica igual.
- **Decisión del tesista (2026-08-23):** la segunda. Desactivar el sandbox nativo de B y
  dejar el confinamiento en manos del contenedor, como ya hace A con
  `--dangerously-skip-permissions`. Es la dirección que ADR-015 fijó y mantiene idéntica
  la envoltura `docker run`, que `comun/contenedor.py` arma una sola vez para ambas.
- **Corrección:** `pipeline` + `protocolo` — **ADR-019**;
  `harness_b/orquestar.py` pasa `--dangerously-bypass-approvals-and-sandbox` y ya no
  `-s`; `verificar_paridad.py` suma `verificar_confinamiento` (117 → **139 chequeos**,
  camino negativo probado). Deja sin objeto el riesgo de red del ítem 2 de la checklist
  H6.
- **Estado:** resuelto.
- **Alcance:** habría degradado en silencio las dos celdas B —el turno completa igual,
  sólo que sin haber ejecutado nada— y su implementación no sería comparable con la de A.

### Error de medición en el camino a H-04

Las tres primeras mediciones de alternativas fueron **inválidas**: el script de smoke
había perdido sus ediciones (un `cd` revertido en el shell) y las tres corridas usaron el
comando original, sin override. Se descubrió al ver que `seccomp=unconfined` fallaba en
el smoke y funcionaba a nivel binario. El script se reescribió para **imprimir los flags
efectivos antes de ejecutar**, que es lo que vuelve auditable una medición de este tipo.
Vale como advertencia para la piloto: un override que no se imprime no está medido.

## H-05 — El tope efectivo de A es el rate limit de 5 horas, sin overage disponible

- **Componente:** 5.5 (costo de A)
- **Observado:** el stream de `claude -p` trae un evento `rate_limit_event` no
  documentado en el pipeline, con `rateLimitType: "five_hour"`, `status: "allowed"`,
  `resetsAt` (epoch) y `overageStatus: "rejected"` con
  `overageDisabledReason: "out_of_credits"`. O sea: agotado el límite de 5 horas, la
  corrida se corta y **no** hay créditos de overage que la continúen.
- **Por qué importa:** ADR-016 eliminó los topes de presupuesto y dejó que la corrida
  «termine cuando termina el pipeline». El tope real no desapareció: es el rate limit,
  y no es un umbral que el tesista elija. Una etapa larga puede cortarse a mitad, lo que
  convierte la reanudación (protocolo §5.8) en un camino frecuente y no excepcional.
- **Corrección:** `ninguna` por ahora, pero el dato entra al manifest y al journal, y la
  pre-piloto debe medir cuánto consume una etapa acotada para estimar si una etapa
  completa entra en una ventana de 5 horas.
- **Estado:** registrado.

## H-06 — Coste y forma de una invocación de A, medidos

- **Componente:** 3.1 / 5.1 / 5.5
- **Observado (smoke de una invocación, 4 tareas triviales):** 7 turnos, 17,7 s de API,
  **USD 0,209**, 14 565 tokens de creación de caché, 67 807 de lectura de caché, 1 147 de
  salida (254 de thinking). Tipos de evento del stream: `system` (init y
  `thinking_tokens`), `assistant`, `user`, `rate_limit_event`, `result`.
  `total_cost_usd` viaja en `result`, como esperaba `nucleo`.
- **Verificado de paso:** ADR-008 se sostiene —`WebSearch`/`WebFetch` no existen dentro
  de la sesión y `result.usage.server_tool_use.web_search_requests` es 0—; el usuario es
  `agente` (uid 1001); el RAG respondió `bip-0044.mediawiki § Path levels`.
- **Estado:** registrado; alimenta el ítem 19 de la checklist H6.

## H-07 — El agente no puede alcanzar el entorno on-chain desde el contenedor

- **Componente:** 2.5 (red del contenedor) / 9.1 (smoke de avance)
- **Observado:** el nodo anvil corre en el host (`127.0.0.1:8545`), pero el agente corre
  dentro del contenedor, cuya red es propia (ADR-015 D4 la deja abierta pero **no** es la
  del host): desde adentro, `127.0.0.1:8545` no responde. Medido: **sí** responde
  `http://host.docker.internal:8545` —devuelve `{"result":"0xaa36a7"}`, o sea
  chainId 11155111—, porque Docker Desktop provee ese nombre. Nada en el prompt de etapa
  ni en el entorno le dice al agente que ese nodo existe ni en qué URL.
- **Por qué importa:** el rol implementador exige «no des por terminado nada que no hayas
  visto funcionar» y la spec obliga a verificar `eth_chainId() == 11155111` al iniciar el
  indexador (épica 07). Sin nodo alcanzable, el agente no puede ejercitar ningún camino
  on-chain durante la generación: la implementación llega a H8 con esa parte sin probar,
  y las fallas resultantes serían del ambiente, no del modelo.
  **En la pre-piloto no bloquea** —su universo (01, 06, 09) es derivación HD y HTTP, sin
  RPC—, y por eso el defecto habría aparecido recién en la piloto.
- **Corrección:** `pipeline` + `protocolo` — `comun/contenedor.py` agrega
  `--add-host=host.docker.internal:host-gateway` (simétrico en las dos familias, no es
  un permiso del contenedor: no cae bajo la prohibición de `--security-opt` / `--cap-add`
  del chequeo de confinamiento), y el prompt de etapa de backend le informa la URL del
  nodo disponible. Va por ADR: cambia un instrumento pre-registrado de las 4 celdas.
- **Estado:** abierto — la corrección se aplica al terminar las etapas backend en curso,
  para no cambiar la envoltura entre pasos de una misma etapa.

## H-08 — Toolchain del contenedor: alcanza para el camino probable, sin compilador

- **Componente:** 2.5
- **Observado:** la imagen base no trae `gcc`/`g++`/`make`/`python3-dev` (ni `jq`,
  `sqlite3`, `pnpm`, `watchman`). Verificado que **no hace falta** para el stack más
  probable: `better-sqlite3`, `bcrypt` y `argon2` instalan por prebuild y cargan en
  Node 23 arm64 (`require` de los tres, más un `CREATE TABLE` en memoria, OK).
- **Riesgo remanente:** cualquier dependencia sin prebuild ni wheel para esta plataforma
  fallaría al compilar, y el agente lo vería como un error de instalación sin salida.
- **Decisión:** no se toca la imagen mientras hay corridas en vuelo. Si alguna etapa
  falla por esto, se agrega `build-essential` + `python3-dev` a `Dockerfile.base` (es la
  base común: el cambio es simétrico por construcción) y se re-registra el digest.
- **Estado:** registrado, sin acción por ahora.

## H-09 — El smoke de la etapa mobile no era ejecutable como está enunciado

- **Componente:** 9.1 (smoke de avance de etapa)
- **Observado:** el criterio de avance de mobile es «la app mobile compila y **corre en
  Expo**» (protocolo §4.1, `etapas.yaml`). «Corre en Expo» no es verificable sin
  emulador ni dispositivo, y no hay ninguno: ni en el contenedor del agente ni en el
  host de la corrida. Sin un procedimiento concreto, el criterio se vuelve un juicio del
  operador y deja de ser idéntico entre celdas.
- **Medido en el contenedor, sobre un proyecto Expo recién creado:**
  - `npx expo export --platform android` → **funciona**, genera el bundle
    (`_expo/static/js/android/index-….hbc`, 1,4 MB) y `metadata.json`, exit 0. Es
    compilación real del bundle JS: si el código no compila, falla.
  - `npx expo export --platform web` → falla en un proyecto que no declaró `react-dom`
    y `react-native-web`. Es una falta del proyecto, no del ambiente; sirve como smoke
    sólo si el agente incluyó el target web.
  - Etapa web: `npm create vite` + `npx vite build` → **funciona** (dist generado).
- **Corrección propuesta:** fijar el smoke de mobile como
  `npx expo export --platform android` con exit 0, y el de web como el build de
  producción que el README del SUT documente. Toca el protocolo (§4.1) y `etapas.yaml`,
  así que va por ADR junto con H-07.
- **Estado:** abierto — la corrección se aplica al cerrar las etapas backend en curso.

## H-10 — La máquina durmió y congeló las dos corridas ~8 horas

- **Componente:** 9.3 (cierre de corrida) / operación
- **Observado:** las etapas backend arrancaron el 2026-08-23 a las 23:45. El ritmo fue de
  ~465 eventos en la primera hora y ~195 en la segunda, y **se derrumbó a 1–3 eventos por
  hora entre la 01:00 y las 08:00**, en las **dos** familias a la vez. `pmset -g log`
  muestra ciclos de `Entering Sleep` / `DarkWake` durante toda la noche con la máquina a
  batería (47 %), y un `Wake … UserActivity` a las 09:20:22 — el mismo minuto del último
  evento de ambos JSONL. Los contenedores y los procesos del orquestador seguían vivos
  (`Up 10 hours`): no se cayó nada, quedó todo suspendido.
- **Efecto colateral:** 3 eventos `API Error: Connection lost mid-response` en el log de
  A, en los momentos de suspensión. El CLI reintentó y siguió; no cortó la etapa.
- **Por qué importa:** una corrida oficial dura horas y el manifest registra `inicio` y
  `fin` como **variables dependientes** (ADR-016 eliminó los topes, así que el tiempo es
  un dato del experimento, no un límite). Ocho horas de sueño de la laptop inflan ese
  dato y lo vuelven incomparable entre celdas — una celda corrida de día y otra de noche
  no medirían lo mismo.
- **Corrección aplicada:** `caffeinate -dimsu -w <pid del orquestador>` mientras dure la
  etapa, atado al proceso para que se libere solo al terminar. Para las corridas
  oficiales hay que sumarlo al procedimiento de arranque del protocolo (§3) **y** correr
  con la máquina enchufada: con batería, macOS puede dormir igual.
- **Consecuencia sobre el dato de esta corrida:** el tiempo de pared de la etapa backend
  de la pre-piloto **no es utilizable** como estimación. Se registra el hecho en el
  manifest (`notas`) en vez de un número que mentiría.
- **Estado:** corregido en caliente; falta llevarlo al protocolo (va con el ADR de H-07 y
  H-09).

## H-11 — Hay varios `result` por invocación y su `total_cost_usd` no se suma

- **Componente:** 5.1 / 5.5 (esquema del stream de A y costo) — cierra parte del ítem 19
  de la checklist H6
- **Observado:** el paso 1 de A emitió **tres** eventos `type: "result"`, los tres en el
  mismo segundo (09:35:16), con la misma `session_id`, el mismo `duration_api_ms` y el
  **mismo `total_cost_usd` (30,0551225)**, pero distinto `num_turns`: 65, 8 y 15. Los
  tres traen `parent_tool_use_id: null`, así que `nucleo.es_de_subagente` los clasifica
  como agente principal.
- **Lectura:** el `total_cost_usd` es **acumulado de sesión**, no de segmento. Sumar los
  `result` de una invocación **triplicaría** el costo registrado. La lectura correcta es
  tomar uno solo por `session_id` (el de mayor `num_turns`, o cualquiera: el costo es el
  mismo). Los `num_turns` 8 y 15 corresponden con toda probabilidad a los subagentes que
  el implementador lanzó —hubo 3 llamadas a `Agent` y 113 mensajes con atribución de
  subagente—, pero **sus `result` no llevan `parent_tool_use_id`**, así que la atribución
  por ese campo funciona para los mensajes y no para los `result`.
- **Corrección:** `pipeline` — el cómputo de costo por etapa (que hoy se hace fuera del
  bucle, sobre el JSONL) debe agrupar por `session_id` y quedarse con un `result` por
  sesión. Documentarlo en `nucleo` junto a `costo_estimado_usd`. La atribución de
  subagentes de `es_de_subagente` queda como está para los mensajes, con la limitación
  anotada para los `result`.
- **Estado:** abierto — se implementa al cerrar las etapas en curso.

## H-12 — El agente A no consultó el corpus ni una vez, con la épica 06 en el alcance

- **Componente:** 4.2 (consultas reales al corpus)
- **Observado:** el `-rag.jsonl` de `pre-piloto-a` tiene **dos líneas, ambas
  `servidor_rag_inicio`** (una por paso): **cero consultas** en todo el paso 1, que
  implementó la épica 06 completa —generación de seed BIP-39, derivación BIP-32/BIP-44,
  asignación de direcciones—, o sea justo el contenido que el corpus congela. El servidor
  MCP arrancó bien y la herramienta estaba declarada: no es un fallo técnico, el agente
  no la usó. `pre-piloto-b`, con el mismo corpus y la misma descripción de herramienta,
  hizo 3 consultas en el mismo tramo.
- **Por qué importa, y por qué no lo corrijo por mi cuenta:** el factor manipulado del
  2×2 es *con/sin RAG*. Si el agente de una familia no consulta el corpus aunque lo
  tenga, ese factor mide **disponibilidad** y no **uso**, y la celda `a-con-rag` sería
  indistinguible de `a-sin-rag` salvo por el ruido. Pero «que el agente elija no usar la
  herramienta» **es un resultado legítimo** del experimento, y forzarlo desde el prompt
  —por ejemplo mandándole consultar el corpus antes de implementar un estándar— cambiaría
  el factor por otro distinto y afectaría a las 4 celdas. Es una decisión de diseño del
  tesista, no una corrección de infraestructura.
- **Qué falta antes de decidir:** ver si A consulta en los pasos 2 y 3 y en las etapas
  siguientes, y cuánto consulta B al terminar. Con la etapa cerrada, el dato queda
  medido en las dos familias.
- **Estado:** abierto — a elevar al tesista con el conteo final de las dos celdas.
