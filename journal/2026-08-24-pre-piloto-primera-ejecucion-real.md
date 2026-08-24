# 2026-08-24 — La pre-piloto: primera ejecución real del pipeline y de la evaluación

- **Hito:** H6 (ventana de la piloto). `piloto-01` sigue sin iniciar; lo que corrió es una
  corrida **pre-piloto** nueva, descartable, sobre un universo reducido de la spec.
- **Contexto:** sesión con Claude Code que arranca con el pedido de «probar todo el
  pipeline en una pre-piloto, con énfasis en corregir problemas de los tests
  whitebox/blackbox», y a mitad de camino el tesista delega la resolución autónoma de los
  problemas que aparezcan y el aprovisionamiento de los entornos. Continúa la sesión del
  2026-08-23, que dejó todo verificado **en seco**.
- **Lo que cambia respecto de todo lo anterior:** hasta ayer, ningún CLI de agente había
  ejecutado una etapa, la suite de ATs nunca había corrido contra un sistema real, el
  agente evaluador white-box nunca se había ejecutado y las métricas estáticas nunca se
  habían medido. Hoy corrieron los cuatro.

## Qué se hizo

**Se diseñó la pre-piloto (ADR-018).** Dos celdas descartables —`pre-piloto-a` y
`pre-piloto-b`, una por familia, las dos con RAG y `effort high`— sobre un subconjunto de
la spec elegido para tocar cada subsistema: `HU-01-01`, `HU-01-02` y la **épica 06
completa** en backend (la única del universo que obliga a consultar el corpus), `HU-10-01`
en web, y `HU-11-01` más la pantalla de depósito de `HU-11-06` en mobile. La spec va
**entera** al repo satélite, igual que en una corrida oficial; lo que acota es el prompt
de etapa. El alcance se expande sin residuo: 78 ATs = **56 black-box + 22 white-box**.

**Corrieron las 6 etapas, con sus 6 smokes de avance.** Las dos celdas completaron
backend, web y mobile con exit 0 en los 9 pasos cada una, handoffs escritos y leídos,
snapshots por invocación y evento `fin`. Ninguna intervención de las categorías 1–8 del
protocolo: las 6 entradas de los logs de intervenciones son smokes de avance.

**Se evaluó de punta a punta.** Suite black-box sobre los 56 ATs del alcance, agente
evaluador white-box con dos pasadas validadas, arbitraje preparado, y métricas estáticas
por componente.

## Lo que la pre-piloto encontró

**21 hallazgos** en `runs/pre-piloto/hallazgos.md`. Los que habrían roto la piloto:

- **H-03** — `codex exec` no arrancaba en el contenedor: docker creaba `/home/agente/.codex`
  como root al bind-montar `auth.json` y Codex necesita `CODEX_HOME` escribible.
- **H-04 → ADR-019** — con `-s workspace-write`, bubblewrap no puede crear user namespaces
  dentro del contenedor y **todo** comando del agente B fallaba, **sin cortar la corrida**:
  la degradaba en silencio. Sin shell no hay `npm install`, ni build, ni verificación. El
  confinamiento pasa a ser el contenedor en las dos familias, que es lo que ADR-015 ya
  había fijado; A ya corría así.
- **H-15 → ADR-021** — el build del cliente web **falla en el host** y pasa en el
  contenedor: `node_modules` se instala en linux/arm64 y rollup trae binario por
  plataforma. Los backends habían arrancado en el host de pura suerte. En H8 esto haría
  fallar los 465 ATs automatizados por la plataforma del evaluador y no por la
  implementación, y fallaría distinto en cada celda.
- **H-16** — el readiness probe tras el reinicio del SUT exigía `GET /market/ticker` con
  200, atando los **21 ATs de persistencia (INV-8)** a que la épica 03 esté bien
  implementada. Con el fix, el test pasa en 3,25 s; antes hacía timeout a los 121 s.
- **H-21** — `--no-summary` suprimía la escritura de `resultados-at.csv`, **el dato
  primario de H8**, sin ningún aviso. Y el flag es casi obligatorio para poder leer la
  salida, porque el resumen imprime los 56 no-automatizables con su motivo completo.
- **H-20 → ADR-022** — las métricas estáticas contaban `spec/` y los lockfiles como código
  del agente: **32 648 loc con «lenguaje principal JSON»**, contra 5 301 de TypeScript
  reales. El 86 % de lo medido no lo había escrito el agente.

Y los de ambiente, que salen del encargo de aprovisionar los entornos: el nodo on-chain
no era alcanzable desde el contenedor (**H-07 → ADR-020**), el smoke de mobile no era
ejecutable —no hay emulador en ningún lado— (**H-09 → ADR-020**), el agente no podía
commitear y cada familia inventó su identidad, delatando el modelo generador (**H-13**),
y el toolchain de métricas no estaba instalado (**H-20**).

**Cinco ADRs, todos Aceptados:** ADR-018 (la pre-piloto), ADR-019 (confinamiento),
ADR-020 (nodo on-chain y smokes ejecutables), ADR-021 (el artefacto se ejecuta donde se
construyó), ADR-022 (alcance de las métricas estáticas). `protocolo.md` pasó de v1.2 a
**v1.5**; la paridad, de 117 a **143 chequeos**.

## Los tres datos que cambian decisiones

**1. Nadie consultó el corpus.** Cero `consulta_rag` en las dos celdas, en las seis
etapas, con la épica 06 entera —BIP-39/32/44— dentro del alcance. El servidor MCP arrancó
42 veces sin error y en el smoke, pedido explícitamente, respondió con el pasaje correcto:
**el mecanismo funciona, los agentes no lo usan por iniciativa propia**. Si esto se
sostiene, el factor RAG mide *disponibilidad* y no *uso*, y el efecto principal saldría
nulo por construcción. Decisión pendiente del tesista (H-12: dejarlo y reportarlo,
instruir el uso, o subir la saliencia de la herramienta).

**2. El consumo real, por primera vez.** El universo reducido —6 HU de backend, 2 de
cliente, `effort high`— costó **USD 142,20** en A (nativo) y entre 13 y 262 estimados en B.
Una corrida oficial es la spec entera (57 HU) con `xhigh`. ADR-016 quitó los topes
asumiendo un consumo manejable; este es el primer dato para revisar ese supuesto. Y el
tope efectivo no es económico: es el **rate limit de 5 horas sin overage** (H-05).

**3. Las dos implementaciones son indistinguibles black-box y muy distintas por
tamaño.** 51 pasa / 3 falla / 2 skip en las dos celdas, con las mismas 3 fallas (todas por
endpoints fuera del alcance). Pero A escribió **12 030 loc** contra **5 301** de B para el
mismo alcance: 2,3×. Las métricas estáticas discriminan, que es lo que había que
verificar.

## Pendientes

- **Decisión del tesista sobre H-12** (consulta al corpus), que es la que más afecta al
  diseño. También **H-19** (el tope de esfuerzo del evaluador no es verificable: declaró
  176 minutos en 17 de reloj) y la regla `skip = 0` de ADR-011 frente a los 2 skips
  legítimos por rate limiting opcional.
- **Arbitraje** de la única discrepancia white-box de B (AT-06-03-10), preparado en
  `no-automatizables-b/arbitraje.md` con la evidencia de las dos pasadas.
- **Rúbricas manuales** de web y mobile y la del rol revisor: no se completaron.
- **Pasada 2 del white-box de A**, en curso al cerrar la sesión.
- Congelar los dos repos satélite y registrar su hash final en los manifests.

## Observaciones de método

- **Tres mediciones inválidas propias.** Al buscar alternativas para H-04, el script de
  smoke había perdido sus ediciones y las tres primeras corridas usaron el comando
  original sin override: se concluyó que dos alternativas no funcionaban cuando en
  realidad no se habían probado. Se detectó porque una de ellas funcionaba a nivel binario
  y fallaba en el smoke. El script se reescribió para **imprimir los flags efectivos antes
  de ejecutar**. Un override que no se imprime no está medido.
- **La máquina durmió 8 horas** con las dos corridas en vuelo y las congeló (H-10). Los
  contenedores y procesos siguieron vivos; el ritmo cayó de 465 eventos/hora a 1–3. El
  tiempo de pared de las etapas backend no es utilizable como dato. Para las oficiales,
  `caffeinate` y máquina enchufada entran al procedimiento de arranque.
- La pre-piloto corrió sus etapas backend **antes** de ADR-020 y ADR-021, así que es
  internamente heterogénea. Admisible sólo porque es descartable y no entra en ningún
  análisis.
