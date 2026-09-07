# ADR-026 — La evaluación es gestionada íntegramente por agentes: un tercer proveedor ejecuta todo paso con juicio

- **Estado:** **Aceptado** (decidido por el tesista el 2026-09-06)
- **Fecha:** 2026-09-06
- **Contexto:** ventana H6, cierre de la corrida pre-piloto. El tesista fijó que **ningún
  veredicto sobre los entregables de una celda dependa de un QA humano que evalúe ATs a
  mano** ni de un modelo generador, y que todo paso de evaluación no automatizable lo
  ejecute un tercer modelo.
- **Reemplaza a:** de [ADR-004](ADR-004-protocolo-experimental-preregistrado.md) §2.5, «el
  evaluador de registro es el humano»; de [ADR-007](ADR-007-agente-evaluador-white-box.md)
  §3, las mitigaciones **4** (auditoría humana del 100 %) y **5** (espejo con el otro
  proveedor generador), y de su §4 el `veredicto-final.yaml` «del humano tras arbitrar»;
  de [ADR-010](ADR-010-delegacion-contexto-y-evaluador.md) Decisión 3, el juez white-box
  `claude-opus-5` y el espejo `gpt-5.6-sol`. Ningún ADR anterior se edita; los briefings
  y rúbricas congelados tampoco: cambia **quién los ejecuta** y cómo se cierra un
  veredicto.

## Contexto

Hasta hoy la evaluación de una celda tenía cinco pasos con juicio y cuatro de ellos eran
humanos:

| Paso | Quién juzgaba | Instrumento |
|---|---|---|
| 56 ATs white-box | agente `claude-opus-5` (dos pasadas) | `agente-evaluador/briefing.md` + rúbrica |
| Arbitraje de discrepancias white-box | el tesista | ADR-007 §3.3 |
| Rúbricas web (79) y mobile (94) | el tesista | `rubricas/epica-10-web.md`, `epica-11-mobile.md` |
| Rúbrica del rol revisor (36 + censo) | el tesista | `rubricas/rol-revisor.md` |
| Alucinaciones de dominio | el tesista, dos pasadas a ≥ 7 días | `alucinaciones.md` §3–§5 |

Y el único juez no humano era el modelo que genera la celda A, con cinco mitigaciones de
self-preference pre-registradas. Lo que la pre-piloto mostró sobre esos pasos: el agente
white-box corrió con concordancia 43/44 entre pasadas; los ensayos de las rúbricas web y
del rol revisor por un agente produjeron veredictos con evidencia y sacaron a la luz los
huecos del instrumento (H-24, H-26); y la rúbrica mobile no tenía dónde correr (H-25,
resuelto por ADR-025 D4).

## Decisión

**D1 — Runtime: Grok Build, `grok-4.6`, un tercer proveedor.** El evaluador es
`grok -p` (Grok Build, xAI; en el host `1.0.4`), headless, con `--output-format
streaming-json`, `--system-prompt-override` para pasar el briefing verbatim,
`--permission-mode bypassPermissions`, `--disable-web-search`, `--no-subagents` en los
instrumentos que no lo necesitan, `--reasoning-effort xhigh` (mismo nivel que la
generación, ADR-009 D3, y que el evaluador white-box tenía) y `GROK_HOME` apuntando a un
directorio aislado por invocación que contiene **sólo** el `auth.json` del tesista
(copiado en sólo lectura) y la configuración mínima del instrumento (los servidores MCP
que necesite): ni plugins, ni skills, ni memoria entre sesiones, ni la config del host.
Corre en el host, como el evaluador white-box hasta hoy, porque necesita el SUT y el nodo
publicados por los contenedores, el navegador y el emulador. La versión del CLI, el
modelo y el effort se registran en el manifest de cada corrida. Alternativas
descartadas: la API de xAI a través de un proveedor custom de Codex CLI (reusa el harness
B, paga por token, y el wire `responses` de xAI contra Codex no está verificado) y un
cuarto proveedor sin instalar.

**D2 — Todo paso con juicio lo ejecuta ese agente, en dos pasadas independientes más un
arbitraje por agente.** Para los cinco instrumentos:

1. **Pasada 1 y pasada 2:** sesiones frescas, mismo briefing verbatim, mismo directorio de
   trabajo aislado (sólo los insumos permitidos), sin acceso a la otra pasada. El
   white-box conserva su briefing v1.1 y su plantilla; las rúbricas y las alucinaciones
   reciben **briefings nuevos** en `evaluacion/agente-instrumentos/` (pre-registrados
   con este ADR) que no redefinen ningún criterio: fijan insumos, herramientas, orden y
   formato de salida.
2. **Discrepancias:** las detecta un script (misma clave, distinto veredicto o categoría).
3. **Arbitraje:** una tercera sesión fresca con `briefing-arbitraje.md`, que recibe las dos
   pasadas y la lista de discrepantes, re-verifica **sólo** esos items con las mismas
   herramientas e insumos, y emite el archivo final con el esquema de una pasada. Los
   items concordantes se copian de la pasada 1. Es el `veredicto-final` que entra al
   dataset.
4. **Métrica de validez del instrumento:** la tasa de concordancia entre pasadas y el
   conteo de arbitrajes, por instrumento y por celda (reemplaza a la auditoría humana como
   medida de confiabilidad).

**D3 — El humano es operador, no evaluador.** El tesista levanta entornos, lanza los
runners en el orden del protocolo §10.2, archiva los resultados y firma el manifest. No
emite ni revisa veredictos: la evaluación es «totalmente gestionada por IA», decisión
literal del tesista. ADR-004 §2.5 queda reemplazado en ese punto.

**D4 — Self-preference: eliminado por construcción.** El juez no pertenece a ningún
proveedor generador. De las mitigaciones de ADR-007 §3 se conservan 1 (copia sin `.git`),
2 (criterios evidence-gated) y 3 (doble pasada); se retiran 4 (auditoría humana) y 5 (el
espejo `gpt-5.6-sol`; con eso el ítem 6 de la checklist H6 se cierra por retiro).

**D5 — Registro.** Cada sesión del evaluador deja su JSONL (el stream de `grok -p`) con el
mismo formato de registro del pipeline, más el directorio de sesiones de `GROK_HOME`,
en `runs/<id>/evaluacion/<instrumento>/pasada-<n>.*` y `arbitraje.*`; el manifest §5
registra tokens y turnos por instrumento (bajo suscripción no hay USD nativo).

**D6 — Paridad de la evaluación.** El mismo runner, los mismos briefings (por hash), el
mismo modelo, effort y versión de CLI para las 4 celdas; el runner escribe los hashes en
el evento `inicio` del JSONL, como la generación.

## Consecuencias

- `evaluacion/protocolo.md` pasa a **v1.7**: §1 (evaluador de registro), §9 (instrumentos
  ejecutados por agente en dos pasadas + arbitraje), §10 (qué se registra). Los
  instrumentos que nombraban al tesista como ejecutor cambian esa frase, y sólo esa:
  `alucinaciones.md` v1.1, `epica-10-web.md` v1.2, `epica-11-mobile.md` v1.1,
  `rol-revisor.md` v1.1. Ningún criterio de veredicto cambia.
- Implementación: `evaluacion/comun/runtime_evaluador.py` (la invocación de `grok -p` y el
  `GROK_HOME` aislado, una sola vez), `evaluacion/agente-instrumentos/correr.py` (rúbricas,
  alucinaciones y arbitraje) y `evaluacion/agente-evaluador/correr.py` con `--runtime grok`
  (default) conservando `claude` para reproducir la pre-piloto.
- **Pendiente de arranque:** `grok login` (el token vence a los 7 días); verificar el
  headless con un smoke y pinnear la versión de `@playwright/mcp` en el manifest; el
  emulador `tesina-eval` levantado antes de la rúbrica mobile.
- **Amenazas a la validez, declaradas:** (a) los briefings nuevos se escriben después de
  vistas las implementaciones descartables de la pre-piloto (misma condición que
  ADR-024); (b) un solo proveedor juzga las 4 celdas — el sesgo sistemático del juez, si
  lo hay, es simétrico entre celdas y no favorece a un generador; (c) la concordancia
  entre pasadas mide estabilidad del juez, no su acuerdo con un humano: no hay medida de
  acuerdo humano-agente por decisión del tesista.
- Los nueve huecos de la rúbrica del rol revisor (H-26) siguen abiertos; el briefing del
  agente los resuelve mecánicamente y lo declara, sin editar la rúbrica.
