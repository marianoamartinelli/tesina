# ADR-021 — El artefacto se ejecuta donde se construyó: smoke y evaluación en contenedor

- **Estado:** **Aceptado**
- **Fecha:** 2026-08-24
- **Contexto:** corrida pre-piloto ([ADR-018](ADR-018-corrida-pre-piloto.md)), al ejecutar
  el primer smoke check de una etapa web.
- **Reemplaza a:** de [ADR-020](ADR-020-nodo-onchain-y-smoke-ejecutable.md), nada de lo
  decidido: aquel fija **qué comando** verifica cada etapa, éste fija **dónde se
  ejecuta**. ADR-020 no se edita. `protocolo.md` pasa a **v1.4** (§4.1, §4.2 y §3 paso 6).

## Contexto

El agente construye dentro del contenedor (ADR-015), así que `node_modules` queda
poblado con binarios de **linux/arm64**. El evaluador, en cambio, corría el smoke en el
host (macOS/arm64).

Medido en la etapa web de `pre-piloto-b`:

- En el host, `npm run build` del cliente web **falla**:
  `Cannot find module @rollup/rollup-linux-arm64-gnu … MODULE_NOT_FOUND`. rollup
  distribuye un binario por plataforma y el instalado es el de Linux.
- El **mismo** build, en el contenedor de la misma imagen con el repo montado:
  `✓ built in 508ms`, `dist/` generado, exit 0.

Los backends de las dos celdas sí habían arrancado en el host, pero eso fue **suerte**:
usan `node:sqlite` (builtin) y no arrastraron dependencias nativas incompatibles. Basta
una para que el criterio de avance falle por la plataforma del evaluador y no por la
implementación — y falle **distinto en cada celda**, según qué eligió cada agente.

El problema no termina en el smoke: en H8 el evaluador levanta el SUT congelado y le
corre la suite black-box. Un SUT que no arranca en el host haría fallar los 465 ATs
automatizados por una causa que no tiene nada que ver con lo que se está midiendo.

## Decisión

### 1. Los smoke checks se ejecutan dentro del contenedor de la corrida

Con la misma imagen y el mismo tag que generó el artefacto, el repo satélite montado en
`/repo` y `--add-host host.docker.internal:host-gateway` (ADR-020) para alcanzar el nodo
on-chain. Los comandos son los de ADR-020: health-check del backend, build de producción
del cliente web, `expo export --platform android` del mobile.

### 2. El SUT de H8 también corre en contenedor, con su puerto publicado

La suite black-box y el agente evaluador white-box siguen corriendo **en el host**; lo
que se mueve al contenedor es el **SUT**, con `-p <puerto-host>:<puerto-sut>` para que la
suite le pegue por `localhost` sin cambiar una línea de los tests.

Verificado en la pre-piloto: el backend de B arrancado con
`docker run -p 3103:3000 --add-host … --env-file … -v <repo>:/repo -w /repo … npm start`
responde `{"status":"ok"}` a `curl http://127.0.0.1:3103/health` **desde el host**.

Consecuencias sobre el contrato de arranque de `suite-at/entorno/README.md`, que no
cambia en su contenido —los tres parámetros siguen siendo los mismos— pero sí en dónde se
resuelven: la URL del nodo RPC que recibe el SUT pasa a ser
`http://host.docker.internal:8545` en vez de `http://127.0.0.1:8545`, porque ahora la
lee desde adentro. `EXCHANGE_API_URL` de la suite apunta al puerto publicado.

### 3. `SUITE_CMD_REINICIO_SUT` se define sobre el contenedor

La precondición dura de [ADR-011](ADR-011-particion-automatizable-white-box.md) —matar el
SUT preservando su persistencia y relevantarlo, de la que dependen 21 ATs de INV-8— se
implementa como `docker restart <nombre>` o `docker kill` + `docker start` del contenedor
del SUT, con la persistencia en un volumen o en el propio repo montado. Es más fiel al
`kill -9` que pide el protocolo que matar un proceso del host.

## Consecuencias

- El criterio de avance y la evaluación dejan de depender de la plataforma del evaluador.
  Deja de ser posible que una celda "falle" porque su stack eligió una dependencia con
  binario nativo y otra no.
- El artefacto se ejecuta en el mismo entorno en el que se construyó, que es además el
  que el manifest pinnea por digest: la evaluación se vuelve reproducible por otro.
- **La pre-piloto ya corrió smokes en el host** (backend de A y de B, que pasaron). No se
  rehacen: quedan como evidencia de que el defecto existía y de que en esos dos casos no
  se manifestó.
- El evaluador humano necesita Docker corriendo también en H8, no sólo durante la
  generación. Ya lo necesitaba para el nodo anvil.
