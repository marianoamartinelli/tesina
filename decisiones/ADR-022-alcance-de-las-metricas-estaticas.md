# ADR-022 — Las métricas estáticas no cuentan la spec ni los lockfiles

- **Estado:** **Aceptado**
- **Fecha:** 2026-08-24
- **Contexto:** corrida pre-piloto ([ADR-018](ADR-018-corrida-pre-piloto.md)), primera
  ejecución de `metricas-estaticas/medir.sh` sobre una implementación real.
- **Reemplaza a:** de `protocolo.md` §10.3 y del README de `metricas-estaticas/`,
  únicamente la **lista de exclusiones**, que hasta ahora sólo nombraba `.pipeline/`
  (más los directorios de build y dependencias). El resto del pre-registro de las
  métricas —qué se mide, con qué herramientas y en qué versiones— no se toca.
  `protocolo.md` pasa a **v1.5**.

## Contexto

El repo satélite lleva `spec/` adentro: es la única entrada que reciben las 4 celdas.
`medir.sh` la contaba como código del agente.

Medido sobre el backend de `pre-piloto-b`:

| | loc | lenguaje principal |
|---|---|---|
| como estaba | **32 648** | **JSON** |
| sin `spec/` ni lockfiles | **5 301** | TypeScript |

Los 27 347 de diferencia son **11 740 líneas de Markdown de la spec** y **16 070 de
lockfiles** (`package-lock.json`). O sea: el 86 % de lo que la métrica atribuía al agente
no lo escribió el agente.

El efecto sobre el análisis de H9 es doble y va en direcciones distintas:

- La spec es **constante** entre celdas: no introduce diferencias, pero infla el
  denominador y **diluye** las que hay. Una diferencia real de 500 loc entre dos celdas
  pasa de ser el 10 % del código a ser el 1,5 % del total medido.
- Los lockfiles son **variables** entre celdas: su tamaño depende de cuántas
  dependencias eligió cada agente. Eso es ruido correlacionado con el stack, no con lo
  que se quiere comparar — y encima ya se mide aparte y bien, en
  `deps_directas_prod` / `deps_directas_dev`.

Además, `lenguaje_principal` salía **JSON**, que no describe ninguna implementación.

## Decisión

`medir.sh` excluye:

1. **`spec/`**, sumado a `EXCL_DIRS`. Es input del experimento, inmutable e idéntico en
   las 4 celdas; contarlo como producto es un error de categoría.
2. **Los lockfiles** (`package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`, `poetry.lock`,
   `Cargo.lock`, `go.sum`, `composer.lock`, `Gemfile.lock`), vía `--not-match-f`. Los
   genera el gestor de paquetes.

Lo demás de la lista queda como estaba, `.pipeline/` incluido (ADR-009 Decisión 4: es el
canal de handoff entre roles, no código evaluado).

## Consecuencias

- `loc_efectivas` y `lenguaje_principal` pasan a describir el código que el agente
  efectivamente escribió. Ninguna medición previa se invalida: **no había ninguna** — la
  pre-piloto fue la primera vez que el script corrió sobre una implementación.
- La corrección es simétrica por construcción: el mismo script, la misma lista, las 4
  celdas.
- Queda pendiente, y no lo decide este ADR, **cómo se separan los tres componentes**
  (backend, web, mobile) cuando el agente los deja en el mismo repo: en `pre-piloto-b`
  el backend está en la raíz y los clientes en `web/` y `mobile/`, pero nada garantiza
  ese layout en las 4 celdas. Hoy `medir.sh` recibe la ruta del componente como
  argumento y el evaluador la elige leyendo el README del SUT; si eso resulta ambiguo en
  alguna celda oficial, hace falta un criterio explícito.
