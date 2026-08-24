# ADR-020 — El agente alcanza el nodo on-chain, y los smoke checks son ejecutables

- **Estado:** **Aceptado**
- **Fecha:** 2026-08-24
- **Contexto:** corrida pre-piloto ([ADR-018](ADR-018-corrida-pre-piloto.md)), con las
  etapas backend de las dos familias ya cerradas.
- **Reemplaza a:** de [ADR-012](ADR-012-protocolo-experimental-v1-1.md) y
  [ADR-016](ADR-016-sin-topes-de-presupuesto.md), únicamente los criterios de avance de
  etapa de `protocolo.md` §4.1 para **web** y **mobile**, que quedan enunciados de forma
  ejecutable. El resto del protocolo v1.2 no se toca; el documento pasa a **v1.3**.
  Complementa a [ADR-015](ADR-015-agentes-en-contenedores.md) sin modificarlo: agrega un
  `--add-host` a la envoltura, simétrico en las dos familias.

## Contexto

Tres hechos medidos en la pre-piloto, todos del ambiente de ejecución y ninguno visible
en seco:

1. **El nodo on-chain no era alcanzable desde el contenedor.** anvil corre en el host
   (`127.0.0.1:8545`) y la red del contenedor es propia (ADR-015 D4 la deja abierta, que
   no es lo mismo que compartida): desde adentro, `127.0.0.1:8545` no responde. Sí
   responde `http://host.docker.internal:8545`, que devuelve `0xaa36a7` — chainId
   11155111. Nada en el prompt ni en el entorno le decía al agente que ese nodo existía.
2. **El smoke de mobile no era ejecutable.** «la app mobile compila y **corre en Expo**»
   no se puede verificar sin emulador ni dispositivo, y no hay ninguno: ni en el
   contenedor del agente ni en el host. Un criterio de avance que depende del juicio del
   operador deja de ser idéntico entre celdas.
3. **El smoke de web era ambiguo.** «compila y renderiza login» mezcla una condición
   verificable (compila) con una que exige abrir la app y mirarla.

El punto 1 no bloqueó a la pre-piloto —su universo (épicas 01, 06 y parte de 09) no usa
JSON-RPC—, y por eso habría aparecido recién en la piloto, con la épica 07 en juego. Pero
su efecto es de fondo: el rol implementador tiene la instrucción de no dar por terminado
nada que no haya visto funcionar, y la spec exige verificar `eth_chainId() == 11155111`
al iniciar el indexador. Sin nodo, esa parte llega a H8 sin haberse ejecutado nunca, y
las fallas resultantes serían del ambiente y no del modelo.

## Decisión

### 1. La envoltura del contenedor hace resoluble el host

`comun/contenedor.py` agrega `--add-host host.docker.internal:host-gateway` a **las dos
familias**. Docker Desktop ya provee ese nombre; pasarlo explícito lo vuelve portable y
deja la resolución idéntica en A y B en vez de depender de un default de plataforma.

No es un permiso del contenedor: no afloja seccomp ni agrega capabilities, así que no
entra en conflicto con `verificar_confinamiento`
([ADR-019](ADR-019-confinamiento-por-contenedor-en-ambas-familias.md)), que sigue
prohibiendo `--security-opt`, `--cap-add`, `--privileged` y `--userns` en toda celda.

### 2. El prompt de etapa de backend informa el nodo disponible

Se agrega al prompt —idéntico en las 4 celdas, y también en el de la pre-piloto— que
durante la corrida hay un nodo JSON-RPC de la red en `http://host.docker.internal:8545`
para verificar la implementación, **y que la URL sigue siendo configuración**: no se
fija en el código ni se vuelve default obligatorio, porque el sistema se ejecuta después
contra otro endpoint (en H8, el mismo anvil pero desde el host).

Es información de entorno, no de dominio: no adelanta nada de la spec, no menciona la
suite de ATs y no cambia qué hay que implementar. Entra en la ventana H6, antes de toda
corrida oficial.

### 3. Los criterios de avance de etapa quedan ejecutables

`protocolo.md` §4.1 y `comun/etapas.yaml`:

| Etapa | Antes | Ahora |
|---|---|---|
| backend | el proceso levanta y responde el health-check documentado | *(sin cambios)* |
| web | «compila y renderiza login» | **el build de producción que el README del SUT documente termina con exit 0** |
| mobile | «compila y corre en Expo» | **`npx expo export --platform android` termina con exit 0** |

`expo export` compila el bundle de verdad —si el código no compila, falla— y no necesita
emulador. Verificado en el contenedor sobre un proyecto Expo recién creado: genera el
bundle y sale con 0. La variante `--platform web` **no** sirve como criterio uniforme:
falla en proyectos que no declaran `react-dom` y `react-native-web`, que es una decisión
del agente y no una propiedad de la implementación.

Lo que estos criterios verifican sigue siendo lo mismo que antes: que el artefacto de la
etapa exista y compile. La evaluación de si además *funciona* es H8, con las rúbricas.

## Consecuencias

- Las celdas ganan la capacidad de ejercitar caminos on-chain durante la generación, que
  es lo que el rol implementador ya les exigía. Simétrico entre familias y verificado por
  `verificar_paridad.py` (139 → **143 chequeos**).
- El criterio de avance deja de depender del juicio del operador en dos de las tres
  etapas. Es condición de que las 4 celdas reciban el mismo trato.
- `protocolo.md` pasa a **v1.3**. Los cambios son acotados a §4.1; el pre-registro de
  todo lo demás —intervenciones, orden de construcción, no-exposición del holdout,
  ausencia de topes— sigue como lo dejó ADR-016.
- La pre-piloto corrió sus etapas backend **sin** estas correcciones. No se rehacen: su
  objeto era encontrarlas. Las etapas web y mobile que resten sí las llevan, así que esa
  corrida es internamente heterogénea — algo que sólo es admisible porque es descartable
  y no entra en ningún análisis.
