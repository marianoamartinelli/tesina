# Hallazgos de la pre-piloto-2

Numerados `H2-NN`. Mismo criterio que `runs/pre-piloto/hallazgos.md`: defectos y datos que
la corrida saca a la luz; lo que toca protocolo o metodología sale por ADR.

## H2-01 — B delega en subagentes: tres threads hijos en el paso 1, con tanto consumo como el principal

- **Componente:** 3.4 (delegación) y 5.6 (costo de B) — confirma **H-23** con una corrida real
- **Observado:** en los primeros 24 minutos del paso 1 de `pre-piloto-2b`, `sesiones-codex/`
  (ADR-023) recibió **4 rollouts**: el thread principal (`thread_source: user`) y **3 de
  subagente** (`thread_source: subagent`), que revisaron la implementación y le reportaron
  defectos al principal («Reporté cuatro defectos concretos al agente principal», «Revisión
  entregada al agente principal»). El `--json` del paso no emitió ningún `spawn_agent`.
- **Consumo:** el thread principal acumuló 10,06 M tokens de entrada (9,88 M cacheados) y
  39 185 de salida; los tres subagentes, **2,57 M + 3,07 M + 4,02 M de entrada** y
  17 391 + 19 271 + 25 935 de salida. `turn.completed` del `--json` no los incluye: el
  consumo real de B es del orden del **doble** de lo que la pre-piloto 1 registró.
- **Estado:** medido; entra al manifest §5 de B y al ítem 24 de la checklist H6.

## H2-02 — Corte por límite de uso de la suscripción de Codex a los 24 minutos de etapa

- **Componente:** 1.5 (corte por exit ≠ 0, **ejercitado en real por primera vez**) y
  protocolo §5.8
- **Observado:** 00:18:38 (-03): `error` + `turn.failed` con «You've hit your usage limit
  … try again at 5:35 AM»; `codex exec` salió con 1; el orquestador tomó el snapshot del
  paso 1 (97 archivos) y registró `corte: codigo_salida_no_cero`. El límite se agotó con
  10 M de entrada del principal más ~9,7 M de los subagentes en 24 minutos, sumados a las
  corridas de control y de la sesión anterior del mismo día.
- **Qué confirma:** ADR-025 D3 —la continuación por rate limit es el camino estándar— se
  aplica en la primera etapa de la primera corrida tras decidirlo. La continuación
  (INT-01) se programó para las 05:36 (-03). El tiempo de pared de la etapa backend de B
  no será utilizable como dato (mismo criterio que H-10).
- **Estado:** registrado; continuación en curso.

## H2-03 — El router de herramientas de Codex rechaza `rm -f` aunque el sandbox esté desactivado

- **Componente:** 3.3 (confinamiento de B)
- **Observado:** stderr del paso 1: `exec_command failed for /bin/sh -lc 'rm -f /tmp/…sqlite…'
  … Rejected("rm -f style commands are not permitted. Use a safer approach")`, con
  `--dangerously-bypass-approvals-and-sandbox` (ADR-019). También `timeout_ms must be at
  least 10000` ante un timeout menor pedido por el modelo. Son restricciones del CLI 0.146.0,
  no del contenedor; A no tiene equivalente.
- **Por qué importa:** es una asimetría de capacidad entre brazos no declarada en ADR-009
  D1. El agente puede rodearla (`find -delete`, `node -e`), pero cuesta turnos.
- **Estado:** a sumar a `analisis/amenazas-validez.md` como asimetría declarada.

## H2-04 — Con la instrucción de ADR-025 D1, A consulta el corpus desde el primer minuto

- **Componente:** 4.2 (consultas reales al corpus)
- **Observado:** `pre-piloto-2a`, paso 1: **8 `consulta_rag`** en los primeros 20 minutos
  (0 en las tres etapas de la pre-piloto 1). B: 0 hasta el corte (H2-02), con el mismo
  prompt de sistema.
- **Estado:** en medición; el conteo final por celda y etapa va al cierre.

## H2-05 — La suite se limitaba a sí misma: el rate limit por origen de spec-v1.2 la frena desde un único origen

- **Componente:** 6.3 (suite contra un SUT real) — defecto del **harness**, no del SUT
- **Observado:** primera corrida de la suite sobre `pre-piloto-2a`: 24 fallas + 12 errores
  de fixture, casi todos «registro falló: status 429» o «status esperado 422, llegó 429».
  El SUT de A implementa exactamente HU-01-01 RN-10 v1.2 (sonda: 429 en la solicitud 61
  con `retryAfterSeconds: 60`); la suite, desde un solo origen, registra cuentas más
  rápido que 60 por minuto y, tras el propio AT-01-01-20 (que llena la ventana a
  propósito), sigue registrando mientras la ventana del SUT está llena. Con la spec v1.1
  ninguna implementación limitaba y el problema no existía; ADR-024 D4 lo previó para
  login (sólo cuenta fallos) y no para registro.
- **Corrección (harness, sin tocar criterios):** `helpers/api.py` frena al propio cliente
  —ventana deslizante de 55 solicitudes de registro y 55 logins fallidos por 62 s— y los
  dos ATs de rate limiting lo apagan mientras corren (`ClienteApi.throttle_auth = False`)
  y esperan una ventana entera antes de devolver el control. Costo: ~2 minutos más por
  corrida de la suite completa.
- **Verificación:** con el freno, la suite sobre A da **53 pasa / 3 falla / 0 skip** en
  5 min 13 s; las 3 fallas son los 404 de endpoints fuera del alcance (`/balances`,
  `/withdrawals`; H-18) y los dos ATs de rate limiting (AT-01-01-20, AT-01-02-09), que en
  la pre-piloto 1 eran `skip`, ahora **pasan**: la regla `skip = 0` se cumple sin
  excepciones (ADR-024).
- **Estado:** corregido y verificado.

## H2-06 — El barrido de alucinaciones contaba la spec congelada como afirmación del agente

- **Componente:** instrumento de alucinaciones ejecutado por el runner (ADR-026)
- **Observado:** sobre `pre-piloto-2a`, `candidatos.txt` trajo **1 604** bloques; **607**
  (38 %) salían de `sut/spec/`, la copia de la spec que el repo satélite lleva por
  construcción, y otros tantos son usos triviales de términos (`chainId`, `checksum`).
  El agente los clasificó `CORRECTO` citando §2.6 («texto de la spec congelada»), o sea
  que el instrumento absorbió el ruido, a costa de tiempo y de dilución: 2 filas
  `ALUCINACION` (un solo hecho, `ALU-01`: «vectores canónicos BIP-44» atribuidos a
  BIP-44 para la dirección del mnemonic de Hardhat, que fija la spec y no el BIP) entre
  1 604.
- **Corrección (runner, no del procedimiento):** `extraer_candidatos` excluye `spec/`
  dentro del repo satélite, con el mismo criterio que ADR-022 para las métricas
  estáticas. `.pipeline/` sigue entrando: lo escribió el agente. Las dos pasadas de A
  corrieron con la lista de 1 604 (comparables entre sí); B y las oficiales corren con
  la lista depurada.
- **Estado:** corregido en el runner; la regla queda declarada para `alucinaciones.md`
  v1.2 si se re-pre-registra.

## H2-07 — El pool semanal de Grok Build se agotó a las 3 h 40 de evaluación: el juez tercero tiene un tope duro

- **Componente:** runtime del evaluador (ADR-026 D1) — **bloquea** el resto de la
  evaluación de la pre-piloto-2
- **Observado:** 03:40:58 (-03), en la pasada 2 de alucinaciones de A: `API error (status
  402 Payment Required): Grok Build usage balance exhausted`. Murieron en el mismo
  minuto la pasada 2 del white-box de A y el arbitraje del rol revisor de A; el smoke
  headless mínimo devuelve el mismo 402. Sesiones completas antes del corte, desde las
  23:59:

  | sesión | pared | entrada | caché leída | salida |
  |---|---|---|---|---|
  | rol revisor B, pasada 1 | 13,5 min | 226 281 | 2 044 032 | 44 836 |
  | rol revisor B, pasada 2 | 14,9 min | 295 658 | 2 292 352 | 49 812 |
  | rol revisor B, arbitraje | 8,4 min | 250 640 | 1 073 536 | 28 111 |
  | rol revisor A, pasada 1 | 15,4 min | 202 593 | 3 489 920 | 50 840 |
  | rol revisor A, pasada 2 | 21,7 min | 399 123 | 5 074 432 | 69 250 |
  | white-box A, pasada 1 | 12,2 min | 176 623 | 3 025 536 | 42 845 |
  | alucinaciones A, pasada 1 | 10,0 min | 173 630 | 2 019 328 | 32 517 |
  | **8 completas + 3 cortadas** | **~1 h 40** | **≈ 1,74 M** | **≈ 19,4 M** | **≈ 330 k** |

  Faltaban, sólo para A: white-box p2 + arbitraje, alucinaciones p2 + arbitraje, rúbrica
  web (2 + 1) y rúbrica mobile (2 + 1): unas **10 sesiones** más. Para B, las 15.
- **Lo que dice el proveedor:** el CLI no informa el tamaño del pool ni la fecha de
  reposición; según terceros consultados el 2026-09-07 (xAI no lo publica), SuperGrok
  usa un **pool semanal de cómputo compartido** entre Chat, Imagine, Build y API, con
  ventana **deslizante de 7 días** (cada unidad vuelve 7 días después de gastarse).
- **Por qué importa:** ADR-026 supuso un juez «bajo suscripción» sin tope operativo. El
  tope existe, es semanal y una celda del universo reducido lo agota a mitad de su
  evaluación; una celda oficial (56 white-box + 173 filas de rúbrica + alucinaciones
  sobre 57 HU) necesita del orden de 5–10× más. Con la suscripción actual la evaluación
  de H8 **no cabe en la ventana de ≤ 2 semanas** del protocolo §7.
- **Corrección del runner (hecha):** una pasada sin salida se declara fallida (exit 1,
  `faltantes` en el evento `fin`) y se repite entera; no se completa a mano.
- **Decisión del tesista (pendiente), tres caminos:** (a) esperar la reposición del pool
  y espaciar la evaluación (la ventana de §7 se excede y queda declarada); (b) créditos
  de la **API de xAI** (`XAI_API_KEY`, pago por token: grok-4.6 a USD 2–4 / 6–12 por M)
  con el runtime alternativo de ADR-026 D1 —Codex CLI con proveedor custom— o con Grok
  Build si admite API key (no verificado); (c) tier **SuperGrok Heavy**, con pool mayor
  (tamaño no publicado).
- **Estado:** bloqueante; la generación de B sigue (no depende de Grok).

## H2-08 — La suscripción de Codex rinde ~30 minutos de trabajo de B por ventana de 5 horas

- **Componente:** consumo de B (5.6) y protocolo §5.8 / ADR-025 D3
- **Observado:** dos cortes en la misma etapa: 00:18 (24 min de trabajo) y 06:05 (29 min:
  paso 1 continuado 13 min, revisor 14 min, pase correctivo 2,5 min). Entre ambos, 5 h 17
  de espera. Cada invocación de B lanzó **3 subagentes** —12 threads hijos en 4
  invocaciones— y los subagentes consumieron **más entrada que el thread principal**:
  22,7 M contra 20,1 M de tokens de entrada (rollouts de `sesiones-codex/`, ADR-023). El
  `turn.completed` del `--json` sólo ve los 20,1 M.
- **Por qué importa:** con este ritmo, la etapa backend del universo reducido necesita
  **tres ventanas** (≥ 10 h de pared por ~55 min de trabajo) y una etapa oficial de B, del
  orden de días. ADR-025 D3 asumió cortes «una o más veces por etapa»; el dato es «una
  ventana entera por cada media hora». La decisión suscripción/API key de B se reabre
  con este número; la de A no (A completó sus tres etapas sin un solo corte).
- **Corrección de procedimiento (hecha):** `--desde-paso N` en el orquestador para
  continuar desde el paso interrumpido sin repetir los completos (`paso_omitido` en el
  JSONL), que es lo que §5.8 describe y el núcleo no tenía.
- **Estado:** medido; decisión del tesista sobre B.

## H2-09 — Alucinaciones: dos pasadas sobre la misma lista, 0 y 5 hallazgos; el arbitraje decide

- **Componente:** instrumento de alucinaciones por agente (ADR-026), sobre `pre-piloto-2a`
- **Observado:** con la lista depurada de 1 027 candidatos (H2-06), la pasada 1 marcó
  **0** `ALUCINACION` (10 min) y la pasada 2 **5** (2 hechos, C6: un JSDoc sobre EIP-55 que
  afirma que las direcciones todo-minúscula o todo-mayúscula «no superan» el checksum, y
  «vectores canónicos BIP-44» atribuidos al BIP para la dirección del mnemonic de Hardhat,
  que fija la spec). Con la lista de 1 604, otra pasada 1 había encontrado sólo el segundo.
  El árbitro re-verificó los 5 contra el corpus y dio la razón a la pasada 2 en los 5:
  veredicto final **2 hechos, 5 ocurrencias**.
- **Lectura:** la sensibilidad del agente varía entre pasadas sobre candidatos idénticos;
  la doble pasada más arbitraje es lo que lo absorbe (es exactamente para lo que
  `alucinaciones.md` §5 preveía la segunda pasada). Un solo pase habría reportado 0 o 2
  según la suerte. La tasa de concordancia por candidato (1 022/1 027 = 99,5 %) es alta
  porque casi todos son triviales; sobre los no triviales es baja.
- **Estado:** medido; a reportar como estabilidad del instrumento. Sin corrección.

## H2-10 — El runner del rol revisor sólo miraba el último JSONL de la etapa: una etapa continuada perdía sus pasos

- **Componente:** `agente-instrumentos/correr.py` (rol revisor), sobre `pre-piloto-2b`
- **Observado:** la etapa backend de B quedó en **tres** JSONL con sus tres directorios de
  snapshots (corte en el paso 1; continuación con pasos 1–2 y corte en el 3; continuación
  del paso 3). El runner copiaba sólo el último —que empieza en `desde_paso=3`— y el
  agente, correctamente, dio `NO_EVALUABLE (b)` a RV-02/03/04/11 de backend («faltan
  snapshots paso1 y paso2; el JSONL no contiene el paso 2») y `NO_VERIFICABLE` a sus 3
  puntos del censo. La evidencia existía en el segundo JSONL.
- **Corrección (runner):** concatena en orden cronológico todos los JSONL de la etapa en
  `logs/<etapa>.jsonl` y toma, para cada paso, el snapshot de la corrida más reciente que
  lo ejecutó. Las dos pasadas de B se relanzaron con la corrección; la pasada defectuosa
  queda en `evaluacion/b/rol-revisor/runner-defecto-H2-10/`.
- **Por qué importa para H7:** con ADR-025 D3 las continuaciones son el camino estándar,
  así que toda celda oficial de B va a tener etapas en varios JSONL.
- **Estado:** corregido.

## H2-11 — La primera pasada mobile de B fue inválida por un error del operador: cada implementación nombra su variable de URL

- **Componente:** procedimiento de arranque del entorno mobile (ADR-025 D4), sobre `pre-piloto-2b`
- **Observado:** la app de B-2 lee `EXPO_PUBLIC_API_URL` (origen sin ruta); la de A-2 y la de
  B-1 leen `EXPO_PUBLIC_API_BASE_URL` (con `/api/v1`). El operador escribió la variable de
  A y la app quedó apuntando a su default `localhost:3000`: el agente evaluador registró
  «No se pudo conectar…» en los tres intentos de login y emitió **7 PASA / 2 FALLA /
  7 NO_EVALUABLE (b)** con la causa correctamente identificada («cliente contra
  localhost:3000»). Además la app de B-2 usa Expo SDK **54** y el emulador tenía Expo Go
  **57** (instalado para A): hubo que reinstalar Expo Go 54 y abrir la app por deep link,
  porque `expo start --android` no arranca en modo no interactivo con versiones distintas.
- **Corrección:** la pasada inválida queda en `rubrica-mobile/pasada-1-invalida-entorno/`;
  se relanzó con la variable correcta y Metro reconstruido (`--clear`), tras verificar un
  login desde el emulador. El **contrato de arranque** del entorno (`suite-at/entorno/README.md`)
  debe exigir que el operador tome de la documentación del SUT el nombre de la variable
  de URL del cliente mobile y la versión de Expo Go, y verificar un login desde el emulador
  antes de lanzar la rúbrica — en H8 con 4 celdas de 2 familias, este error se repite.
- **Estado:** corregido en la corrida; procedimiento a fijar antes de H8.

## Resultados de la evaluación (las dos celdas, cerradas el 2026-09-07)

Producto de la evaluación gestionada por agentes (ADR-026) sobre el universo reducido.
No entran en el dataset; sirven para verificar que cada instrumento emite un veredicto
con evidencia y para medir cuánto concuerda el juez consigo mismo. Fuentes primarias:
`resultados-at-{a,b}.csv`, `metricas-estaticas-{a,b}.csv` y `evaluacion/{a,b}/<instrumento>/`.

| Instrumento | A (`pre-piloto-2a`) | B (`pre-piloto-2b`) |
|---|---|---|
| Black-box (56 ATs) | 53 pasa / 3 falla / 0 skip | 52 pasa / 4 falla / 0 skip |
| White-box (22 ATs del alcance) | 22/22 PASA | 22/22 PASA |
| Rol revisor (36 criterios + censo) | 29 PASA / 7 FALLA; censo 27 puntos | 36 PASA / 0 FALLA; censo 6 puntos |
| Rúbrica web (11 filas del alcance) | 11 PASA | 11 PASA |
| Rúbrica mobile (16 filas del alcance) | 15 PASA / 1 NO_EVALUABLE | 16 PASA |
| Alucinaciones de dominio | 2 hechos, 5 ocurrencias en 1 027 candidatos | 1 hecho, 1 ocurrencia en 260 candidatos |
| Métricas estáticas (loc efectivas) | backend 5 901 + web 1 533 + mobile 4 034 = 11 468 | backend 3 162 + web 1 010 + mobile 1 653 = 5 825 |
| Consultas al corpus (backend + web + mobile) | 16 + 0 + 9 = 25 | 15 + 0 + 2 = 17 |

Lecturas:

- **Black-box.** Las tres fallas compartidas son las mismas de la primera pre-piloto:
  `AT-01-01-01`, `AT-06-01-06` y `AT-06-02-07` piden `GET /balances` o `/withdrawals`,
  endpoints fuera del universo reducido. Los dos ATs de rate limiting (`spec-v1.2`) pasan
  en las dos celdas; ya no hay `skip`. La cuarta falla de B es propia: `AT-01-02-11`, el
  P95 del login con email inexistente difiere en 1 003,7 ms del de password incorrecta
  (umbral 50 ms), un canal lateral que permite enumerar emails.
- **Rol revisor.** Las 7 FALLA de A son las tres RV-07 (inversiones de severidad en las
  tres etapas), dos RV-05 (un punto sin ancla en web y otro en mobile), RV-02 en web (el
  revisor creó `.claude/worktrees/` fuera del artefacto) y RV-08 en web (un punto con eje
  `OTRO`). Confirma el hueco 1 de H-26: RV-07 mide un orden que el revisor no usó.
- **Alucinaciones.** Las de A están en H2-09. La de B es C5: el README atribuye a BIP-39
  una seed «de 256 bits» (el estándar deriva 512).
- **Mobile A.** El único NO_EVALUABLE (`AT-11-01-12`, reconexión del WebSocket privado)
  es por alcance: el backend reducido no expone HU-09-03/04.

Concordancia entre pasadas, por instrumento (discrepancias sobre filas comparadas) y
duración de cada sesión de Grok Build:

| Celda | Instrumento | Discrepancias | Pasada 1 | Pasada 2 | Arbitraje |
|---|---|---|---|---|---|
| A | white-box | 0 de 56 | 12,2 min | 13,4 min | trivial |
| A | rol revisor | 3 de 63 (las tres en el censo) | 15,4 min | 21,7 min | 7,5 min |
| A | alucinaciones | 5 de 1 027 (H2-09) | 11,2 min | 9,7 min | 5,1 min |
| A | rúbrica web | 0 de 79 | 12,3 min | 18,1 min | trivial |
| A | rúbrica mobile | 0 de 94 | 38,2 min | 33,9 min | trivial |
| B | white-box | 0 de 56 | 15,4 min | 15,8 min | trivial |
| B | rol revisor | 0 de 42 | 10,0 min | 11,8 min | trivial |
| B | alucinaciones | 0 de 260 | 10,2 min | 10,3 min | trivial |
| B | rúbrica web | 0 de 79 | 17,2 min | 24,9 min | trivial |
| B | rúbrica mobile | 0 de 94 | 39,7 min | 42,2 min | trivial |

«Trivial» = 0 discrepancias: el runner copia la pasada 1 como veredicto final sin abrir
sesión. Las discrepancias reales quedaron en tres sesiones de arbitraje, cada una con la
evidencia y la regla del instrumento que decide (`evaluacion/a/*/arbitraje.md`). Lo que
esta métrica no mide es el acuerdo con un evaluador humano; queda declarado en
`analisis/amenazas-validez.md`.
