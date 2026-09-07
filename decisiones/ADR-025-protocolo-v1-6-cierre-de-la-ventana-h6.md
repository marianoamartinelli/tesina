# ADR-025 — Protocolo v1.6: cierre de la ventana H6 con lo que midió la pre-piloto

- **Estado:** **Aceptado** (las cinco decisiones las tomó el tesista el 2026-09-06)
- **Fecha:** 2026-09-06
- **Contexto:** ventana H6. La corrida pre-piloto ([ADR-018](ADR-018-corrida-pre-piloto.md))
  y su cierre dejaron datos medidos sobre cinco cosas que el protocolo v1.5 dejaba
  abiertas o suponía distinto (`runs/pre-piloto/hallazgos.md`: H-12, H-19, H-05 y la
  proyección de consumo, H-24, H-25).
- **Reemplaza a:** `evaluacion/protocolo.md` **v1.5 → v1.6**. De
  [ADR-009](ADR-009-harnesses-como-cli-y-orquestador-de-roles.md) Decisión 2, la frase
  «ningún prompt menciona el RAG» en su lectura estricta (D1). De
  [ADR-016](ADR-016-sin-topes-de-presupuesto.md), nada: se conserva íntegro y se cierra
  la decisión suscripción/API key que dejaba abierta (D3). Ningún ADR anterior se edita.

## Decisiones

**D1 — El factor RAG pasa a ser «disponible e instruido».** En la pre-piloto las dos
celdas corrieron con RAG y ninguna consultó el corpus ni una vez en 6 etapas, con la
épica 06 (BIP-39/32/44) en el alcance; el servidor MCP arrancó 42 veces sin error y
respondió bien cuando se le pidió a mano (H-12). Un factor que nadie usa mide
disponibilidad, no uso, y su efecto sale nulo por construcción. Se agrega al **prompt de
sistema** (`pipeline/comun/prompts/sistema.md`, regla 6) una instrucción **condicional**:
si entre las herramientas hay una que busca en los estándares del dominio on-chain, usarla
antes de implementar cualquiera de esos estándares; si no está, la regla no aplica. Es
byte-idéntica en las 4 celdas, inerte sin la herramienta, no nombra el RAG ni el corpus
(`TERMINOS_RAG` de `verificar_paridad.py` sigue vigente) y `verificar_paridad.py` la exige
verbatim, como a la instrucción de delegación de ADR-010. Alternativas descartadas: subir
la saliencia de la descripción de la herramienta (cambio menor de efecto incierto) y
dejarlo como está (efecto principal nulo por construcción). La rúbrica del rol revisor no
se re-pre-registra: cambia el prompt de sistema, no el del rol.

**D2 — `duracion_min` del evaluador white-box no es métrica.** El agente no tiene reloj:
en las 4 pasadas de la pre-piloto declaró entre 128 y 202 minutos contra 12–19 de pared
(8,5×–10,8×, H-19). El tope «15 minutos por AT» del briefing congelado (ADR-007) se lee
como instrucción de comportamiento; el esfuerzo por pasada se mide con el tiempo de pared
del runner, los turnos y los tokens del JSONL. El briefing no se toca. Alternativa
descartada: instrumentar marcas de tiempo por AT, que exige cambiar el formato de salida
congelado.

**D3 — Las 4 corridas oficiales corren bajo suscripción, sin topes, y la continuación
por rate limit es el camino estándar.** ADR-016 quitó los topes suponiendo un consumo
manejable; la pre-piloto midió USD 142 de equivalente API por celda A sobre el universo
reducido y proyecta ≈ USD 700 por celda completa a `effort high` (más a `xhigh`, no
medido), con etapas de varias horas que cruzan la ventana de 5 horas del rate limit de A,
que no tiene overage (H-05). Se mantiene ADR-016 y la suscripción: cada corte se registra
como intervención (d) / D2 (protocolo §5.8) y el manifest §5 lleva el conteo de cortes
por etapa. Alternativas descartadas: API key (sin cortes, USD 700+ por celda A pagados
aparte) y reponer un tope de costo (censura la variable que el experimento compara).

**D4 — El entorno de evaluación provee un emulador Android para la rúbrica mobile.** La
rúbrica de la épica 11 (94 ATs) exige la app corriendo en emulador, simulador o
dispositivo, y no había ninguno (H-25): en H8 los 94 ATs habrían quedado `NO_EVALUABLE`
en las 4 celdas. Se aprovisiona **una vez** en la máquina del evaluador: Java 17
(`openjdk@17`), `android-commandlinetools`, `platform-tools`, `emulator`,
`platforms;android-35` y la imagen `system-images;android-35;google_apis;arm64-v8a`; AVD
**`tesina-eval`** (perfil `pixel_6`). Verificado el 2026-09-06: bootea sin ventana en
10 s (`sys.boot_completed = 1`, Android 15). El backend de la celda corre en su contenedor
con puerto publicado y el emulador lo alcanza por `10.0.2.2`. Alternativas descartadas:
dispositivo físico con Expo Go (red y dispositivo no reproducibles) y sacar la épica 11
de la evaluación manual (el cliente mobile quedaría sin evaluación funcional).

**D5 — Rúbrica web v1.1: dos precisiones de procedimiento.** Del ensayo sobre la
pre-piloto (H-24): (a) un navegador automatizado (Playwright) entra a las herramientas
permitidas, usado con las mismas capacidades que DevTools y el proxy —inspeccionar,
demorar, abortar o adulterar requests—, anotando cuándo se usó; (b) en AT-10-01-07, si
el cliente no emite otro request protegido que el chequeo de sesión (`GET /me`), ese es
el camino que se evalúa. Ningún criterio de veredicto cambia. (El tercer cambio de la
v1.1, la fila AT-10-01-06, es de ADR-024 D7.)

## Consecuencias

- `verificar_paridad.py`: **146 chequeos** (145 tras ADR-023).
- Amenazas a la validez nuevas, en `analisis/amenazas-validez.md`: el objeto medido pasa
  a ser «cada CLI bajo la orquestación de ADR-009/010 **y con la consulta de estándares
  instruida**»; y la reapertura `spec-v1.2` ocurrió con la spec ya vista por los agentes
  de la pre-piloto (ADR-024).
- Los nueve huecos de la rúbrica del rol revisor que el ensayo sacó a la luz (H-26)
  **quedan abiertos**: corregirlos es re-pre-registrarla, y eso es una decisión aparte
  del tesista antes de H7.
- Sigue sin medir el comportamiento de cada CLI ante un rate limit a mitad de etapa
  (checklist H6, ítem 19): lo mide `piloto-01`.
