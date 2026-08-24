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

## H-13 — El agente no podía commitear, y al resolverlo solo firmó con una identidad que delata el modelo

- **Componente:** 2.1 / 2.2 (ambiente del contenedor) / 8.4 (métricas estáticas)
- **Observado:** el prompt de sistema (regla 4) le pide al agente «commiteá con mensajes
  descriptivos a medida que avances», pero el contenedor no trae identidad git. Las dos
  familias chocaron con `Author identity unknown … Please tell me who you are` en su
  primer `git commit` —una vez cada una— y **cada una la resolvió a su manera**:
  - `pre-piloto-a`: `Agente Implementador <agente@local>`
  - `pre-piloto-b`: **`Codex <codex@local>`**
- **Por qué importa, doble:**
  1. **Des-anonimización.** El autor de los commits nombra al proveedor. El agente
     evaluador white-box no lo vería —el briefing §2 exige la copia de evaluación sin
     `.git`, y `correr.py` la prepara así—, pero el historial queda en el repo de la
     corrida, que alimenta las métricas estáticas y la rúbrica del rol revisor, y el
     briefing §3.4 prohíbe explícitamente que el origen influya en un veredicto.
  2. **Variable no controlada.** Que cada celda elija su identidad, su convención de
     mensajes y cuánto commitea vuelve el historial no comparable, justo cuando es dato
     del experimento.
- **Corrección aplicada:** `crear-repo-satelite.sh` fija `user.name = agente` y
  `user.email = agente@tesina.local` en el repo satélite al crearlo. Va en el repo y no
  en la imagen a propósito: viaja con la corrida, es idéntica para las dos familias por
  construcción y **no invalida el digest** de ninguna imagen ya registrada en un
  manifest. Verificado creando un repo satélite nuevo y commiteando: el autor sale
  `agente <agente@tesina.local>`.
- **Alcance:** los repos de la pre-piloto **no** se corrigen —ya tienen commits con la
  identidad vieja y la corrida está en vuelo—; el dato queda medido. La corrección rige
  desde la piloto.
- **Estado:** resuelto.

## H-14 — El estimador de costo de B sobreestima ~19× por dos supuestos falsos

- **Componente:** 5.6 — cierra parte de los ítems 19 y 20 de la checklist H6
- **Medido** sobre los 3 `turn.completed` de la etapa backend de `pre-piloto-b`:

  | turno | `input_tokens` | de esos, `cached_input_tokens` | `output_tokens` | estimado como está | descontando caché |
  |---|---|---|---|---|---|
  | 1 | 9 963 410 | 9 520 384 (96 %) | 46 190 | USD 101,71 | USD 6,51 |
  | 2 | 2 951 262 | 2 801 152 (95 %) | 12 182 | USD 30,06 | USD 1,12 |
  | 3 | 4 375 668 | 4 145 664 (95 %) | 10 648 | USD 44,24 | USD 1,47 |
  | **total** | **17 290 340** | **16 467 200 (95 %)** | **69 020** | **USD 176,01** | **USD 9,10** |

- **Supuesto falso 1 — el umbral de tramo largo no aplica al agregado del turno.**
  `costo_estimado_usd` compara los tokens de entrada contra `umbral_tramo_largo`
  (272 000) y, si lo supera, factura **todo** al tramo largo. Su propio docstring dice
  que se llama «por request… nunca sobre el total de la etapa», pero `turn.completed`
  es exactamente un agregado: 9,96 M de entrada en un turno son decenas o cientos de
  requests, y **ninguno** necesariamente cruzó el umbral. El estimador cobra el doble de
  entrada y 1,5× de salida sobre todo, sin evidencia.
- **Supuesto falso 2 — el 95 % de la entrada es caché y se cobra como entrada fresca.**
  `turn.completed` informa `cached_input_tokens` aparte, y el estimador lo ignora. La
  tarifa de entrada cacheada no está en `PRECIOS_USD_POR_MTOK`.
- **Consecuencia:** el número que hoy produce el pipeline para B no sirve ni como cota
  superior útil (19× de diferencia). Y como A informa `total_cost_usd` nativo, comparar
  costo entre familias con el estimador actual sería comparar dos cosas distintas.
- **Corrección:** `pipeline` — (a) no aplicar el tramo largo sobre agregados de turno:
  o se estima por request, o se documenta que la estimación es de tramo corto; (b) sumar
  la tarifa de entrada cacheada a `PRECIOS_USD_POR_MTOK` y descontarla. Qué tarifa usar
  para la caché es la decisión que el ítem 20 dejaba explícitamente al tesista; los
  números de arriba le dan el orden de magnitud de lo que está en juego.
- **Estado:** abierto — implementación al cerrar las etapas en curso.

## Referencia de consumo real, medida (para dimensionar H7)

Etapa backend acotada a 6 HU, `effort high`, 3 invocaciones de rol:

| | A (`claude-opus-5`) | B (`gpt-5.6-sol`) |
|---|---|---|
| costo | **USD 30,06** sólo el paso 1 (nativo) | USD 9,10 los 3 pasos (estimado, caché descontada) |
| tokens de entrada | 12,8 M de caché leída en el paso 1 | 17,3 M en los 3 pasos (95 % caché) |
| tokens de salida | 95 287 en el paso 1 | 69 020 en los 3 pasos |
| turnos | 65 en el paso 1 | 3 turnos (agregados) |

La comparación **no es simétrica todavía** —A es un paso y B son tres, y los dos números
salen de fuentes distintas (nativo contra estimado)—, pero el orden de magnitud alcanza
para lo que importa: una corrida oficial es la spec **entera** (57 HU contra 6), con
`effort xhigh`, 3 etapas de 3 pasos, ×4 celdas. ADR-016 quitó los topes de presupuesto
asumiendo que el consumo sería manejable; este es el primer dato real para revisar ese
supuesto.

## H-15 — El artefacto no corre en el host: `node_modules` es del contenedor

- **Componente:** 9.1 (smoke de avance) y, sobre todo, 6.3 (suite contra un SUT real)
- **Observado:** al ejecutar el smoke de la etapa web de B **en el host**,
  `npm run build` muere con
  `Cannot find module @rollup/rollup-linux-arm64-gnu … MODULE_NOT_FOUND`: el agente
  instaló las dependencias dentro del contenedor (linux/arm64) y rollup distribuye un
  binario por plataforma. El **mismo** build, en el contenedor de la misma imagen con el
  repo montado, pasa en **508 ms**.
- **Por qué es peor de lo que parece:** los backends de A y B **sí** arrancaron en el
  host, pero por suerte —usan `node:sqlite`, builtin, y no arrastraron binarios nativos
  incompatibles—. Basta una dependencia así para que el criterio de avance falle por la
  plataforma del evaluador, y falle **distinto en cada celda** según qué eligió cada
  agente. En H8 el efecto sería catastrófico: un SUT que no arranca hace fallar los 465
  ATs automatizados por una causa ajena a lo que se mide.
- **Verificado como corrección:** el backend de B levantado con
  `docker run -p 3103:3000 --add-host host.docker.internal:host-gateway --env-file … -v <repo>:/repo -w /repo … npm start`
  responde `{"status":"ok"}` a `curl http://127.0.0.1:3103/health` **desde el host**. O
  sea: SUT en contenedor con puerto publicado, suite y evaluador white-box en el host,
  sin tocar una línea de los tests.
- **Corrección:** `protocolo` — **ADR-021**, `protocolo.md` v1.4. Incluye redefinir
  `SUITE_CMD_REINICIO_SUT` sobre el contenedor (`docker restart` / `kill` + `start`), que
  además es más fiel al `kill -9` que el protocolo pide.
- **Estado:** resuelto.

## H-16 — El readiness probe del reinicio estaba acoplado a la épica 03

- **Componente:** 6.4 (`SUITE_CMD_REINICIO_SUT`) — riesgo directo sobre 21 ATs de INV-8
- **Observado:** `tests/comunes_reinicio.py::sut_responde` daba por vuelto el SUT sólo si
  `GET /market/ticker` respondía **200**. El ticker es de la épica 03. En la pre-piloto,
  con esa épica fuera del alcance, el endpoint devolvía 404 y el helper esperaba los
  **120 s completos** antes de fallar con «el SUT no volvió a responder tras el
  reinicio» — cuando el SUT, medido aparte, volvía en **2 segundos**.
- **Por qué importa en H8, donde la épica 03 sí está implementada:** el mensaje culpa al
  reinicio de un problema del ticker. Una celda que implemente mal ese endpoint haría
  fallar por timeout los **21 ATs de persistencia** que dependen del reinicio (ADR-011),
  con un diagnóstico que apunta al lugar equivocado, y sumaría 2 minutos de espera por
  cada uno.
- **Corrección aplicada:** `sut_responde` da por vuelto el SUT si **responde HTTP**,
  cualquiera sea el status: lo que estos ATs necesitan saber es si el proceso volvió a
  servir, no si una épica está implementada. Ningún criterio de AT cambia — es
  instrumentación, admitida por ADR-018 Decisión 5.
- **Verificado:** el test de persistencia pasa en **3,25 s** (antes: timeout de 121 s).
- **Estado:** resuelto.

## H-17 — Un test que explota con `TypeError` no dice qué falló

- **Componente:** 6.5 (fallas del harness contra fallas del SUT)
- **Observado:** `test_registro_exitoso_con_credenciales_validas` (AT-01-01-01) hacía
  `{b["asset"]: b for b in balances}` sobre la respuesta de `GET /balances` sin verificar
  antes status ni forma. Con `/balances` devolviendo 404, `balances` era el envelope de
  error, iterarlo daba las claves como strings y el test moría con
  `TypeError: string indices must be integers` — que no dice nada de lo que pasó.
- **Por qué importa en H8:** una celda que devuelva `/balances` con otra forma —un objeto
  en vez de una lista, por ejemplo— produciría el mismo `TypeError`, y el evaluador
  tendría que depurar el harness para descubrir que en realidad es un hallazgo sobre el
  SUT. Distinguir falla del SUT de falla del harness es precisamente lo que la pre-piloto
  vino a probar.
- **Corrección aplicada:** el test verifica status 200 y que la respuesta sea una lista
  **antes** de indexar, con el cuerpo recortado en el mensaje. El criterio del AT no
  cambia: sigue exigiendo `available`/`locked` en `"0"` para ETH y USDC.
- **Estado:** resuelto.

## H-18 — La selección por HU no basta: hay tests transversales

- **Componente:** 6.2 (selección por alcance de la pre-piloto)
- **Observado:** los 7 ATs que fallan en `pre-piloto-b` **no son defectos del SUT**: son
  404 de `/balances` (épica 02) y `/withdrawals` (épica 08), endpoints que el prompt de
  la pre-piloto excluyó explícitamente. Los tests que los tocan pertenecen a HU-01-01 y
  HU-06-01/02/03 —dentro del alcance— pero recorren endpoints de otras épicas para
  verificar propiedades transversales (que ninguna respuesta autenticada exponga el seed,
  que los balances iniciales sean cero).
- **Alcance del problema:** es **exclusivo de la pre-piloto**. En una corrida oficial la
  spec está entera y esos endpoints existen. No hay nada que corregir en la suite.
- **Corrección:** documentar en `evaluacion/pre-piloto/README.md` que el criterio de
  lectura del CSV de la pre-piloto es *falla ⇒ revisar si el endpoint estaba en el
  alcance*, y que 7 ATs son falsos positivos conocidos por esta causa.
- **Estado:** documentado; sin cambios en el harness.

## H-19 — El tope de esfuerzo por AT del evaluador no es verificable: el agente declara el tiempo

- **Componente:** 7.1 (briefing y rúbrica white-box)
- **Observado:** la pasada 1 sobre `pre-piloto-b` corrió de **11:15 a 11:32 — 17 minutos
  de reloj**, y en su YAML declaró `duracion_min` sumando **176 minutos**. El campo lo
  escribe el modelo: no tiene reloj ni forma de medir su propio tiempo.
- **Por qué importa:** el briefing §5 fija «máximo 15 minutos por AT o 3 intentos
  fallidos» y justifica el tope diciendo que «las cuatro celdas reciben exactamente el
  mismo esfuerzo; la uniformidad vale más que la exhaustividad». Con un tiempo
  auto-declarado, **ese control no existe**: ni el tope se puede hacer cumplir ni
  `duracion_min` sirve como métrica de esfuerzo en el dataset.
- **Qué sí es medible:** el tiempo de pared por pasada (el JSONL del runner lo registra),
  los turnos y los tokens. El esfuerzo comparable entre celdas se mide con eso, no con lo
  que el agente declara.
- **Corrección propuesta (decisión del tesista, no la tomo):** o se reinterpreta el tope
  como una instrucción de comportamiento —«no te empantanes»— y `duracion_min` se declara
  no-métrica en el dataset, o se instrumenta de verdad (marcas de tiempo por AT desde el
  JSONL). La primera no toca el briefing congelado; la segunda sí, y necesita ADR.
- **Estado:** abierto — a elevar al tesista.

## Resultado de la pasada 1 del evaluador white-box (instrumento verificado)

Primera ejecución del agente evaluador de ADR-007 en todo el proyecto:

- **Formato:** 56 items exactos, en orden, con el bloque de metadatos completo.
  `validar-resultados.py` da **OK** sin una sola violación del contrato.
- **Veredictos:** los **22 ATs del alcance, todos `PASA`**, con evidencia real (hasta 7
  entradas por AT, de tipo `archivo` y `comando`, con rutas y líneas). Los 34 fuera del
  alcance, `NO_EVALUABLE` con causa `FUNCION_NO_LOCALIZABLE`, como pedía la instrucción
  de acotamiento.
- **Aislamiento:** corrió sobre el directorio de trabajo de `/tmp` con sólo los insumos
  del briefing §2; no vio `suite-at/`, `runs/`, `journal/` ni `analisis/`.
- Falta la pasada 2 y el arbitraje para saber la **tasa de concordancia**, que es el dato
  que dimensiona cuánto trabajo humano cuesta H8.
