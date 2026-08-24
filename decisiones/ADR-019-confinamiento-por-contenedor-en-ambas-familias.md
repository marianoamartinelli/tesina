# ADR-019 — El confinamiento es el contenedor: B corre sin su sandbox nativo

- **Estado:** **Aceptado** (decidido por el tesista el 2026-08-23)
- **Fecha:** 2026-08-23
- **Contexto:** ventana H6, corrida pre-piloto ([ADR-018](ADR-018-corrida-pre-piloto.md)).
  Sale de la primera ejecución real de comandos de shell por el agente B dentro del
  contenedor de [ADR-015](ADR-015-agentes-en-contenedores.md).
- **Reemplaza a:** de [ADR-009](ADR-009-harnesses-como-cli-y-orquestador-de-roles.md), la
  fila **«Confinamiento»** de su tabla de equivalencias —`-s workspace-write` del lado B—
  y, con ella, la asimetría de confinamiento que ADR-009 Decisión 1 declaraba como
  limitación. ADR-009 no se edita. El resto de sus decisiones queda intacto, incluido el
  traslado de ADR-008 (`web_search=disabled` + `--disable`), que es independiente.

## Contexto

ADR-015 contenedorizó las dos familias y declaró que con eso «elimina la asimetría de
confinamiento que ADR-009 D1 declaraba»: el confinamiento pasa a ser el contenedor, igual
en A y en B. Pero el orquestador de B seguía pasando `-s workspace-write`, el sandbox
nativo de Codex, que quedaba **encima** del contenedor.

Medido el 2026-08-23, primera vez que un agente B ejecuta comandos adentro:

- Con `-s workspace-write`, **todo** comando del modelo falla con
  `bwrap: No permissions to create a new namespace, likely because the kernel does not
  allow non-privileged user namespaces`, exit 1. Codex confina cada comando con el
  `bwrap` que trae embebido; bubblewrap necesita crear user namespaces y el perfil
  seccomp por default de Docker bloquea esas syscalls. El turno completa igual —el
  modelo lee archivos con sus herramientas propias y contesta—, así que **el fallo no
  corta la corrida**: la degrada en silencio.
- Sin shell no hay `npm install`, ni build, ni arranque del sistema, ni verificación de
  nada: el rol implementador no puede cumplir su punto 3 («no des por terminado nada que
  no hayas visto funcionar») y el revisor no puede comprobar sus afirmaciones. Las dos
  celdas B serían inservibles como implementación y no comparables con las de A.
- El kernel de la VM sí permite user namespaces
  (`/proc/sys/user/max_user_namespaces` = 31319): el bloqueo es del perfil seccomp, no
  del kernel.

Dos salidas, ambas medidas end-to-end con el comando real del orquestador:

| Salida | Resultado | Costo |
|---|---|---|
| `--security-opt seccomp=unconfined` en el `docker run` de B | shell funciona (exit 0) | la envoltura del contenedor deja de ser idéntica entre familias |
| `--dangerously-bypass-approvals-and-sandbox` en `codex exec` | shell funciona (exit 0) | B pierde el sandbox nativo, que el contenedor ya reemplaza |

`-s danger-full-access` **no** es una salida: el wrapper bwrap se aplica igual y los
comandos siguen fallando.

## Decisión

**El harness B corre con `--dangerously-bypass-approvals-and-sandbox` y sin `-s`.** El
confinamiento de las dos familias es el contenedor de ADR-015, y nada más.

Motivos, en orden:

1. **Simetría por construcción.** `comun/contenedor.py` arma la envoltura `docker run`
   una sola vez para las dos familias, y ADR-015 Decisión 5 hace de esa identidad la
   garantía de que montajes, red, usuario y workdir no divergen. Meter
   `--security-opt seccomp=unconfined` en una sola familia rompe justamente esa
   propiedad; hacerlo en las dos degradaría el aislamiento de A sin que A lo necesite.
2. **Es el régimen que A ya tiene.** A corre headless con
   `--dangerously-skip-permissions`, o sea sin sandbox del SO, desde ADR-009. Con esta
   decisión las dos familias quedan en el mismo régimen, que es lo que el diseño
   experimental necesita: lo que cambia entre celdas debe ser el modelo y el RAG, no
   cuánto puede ejecutar cada agente.
3. **Es el uso que el propio CLI documenta** para el flag: *«Skip all confirmation
   prompts and execute commands without sandboxing. EXTREMELY DANGEROUS. Intended solely
   for running in environments that are externally sandboxed»* — que describe
   exactamente el contenedor de ADR-015.

### Consecuencia sobre la restricción de red del ítem 2 de la checklist H6

El riesgo registrado ahí —que con `workspace-write` el CLI le anunciara al modelo
«Network access is restricted» y eso impidiera `npm install`— **deja de aplicar**: sin
sandbox nativo no hay política de red que anunciar. La corrección propuesta entonces
(`-c sandbox_workspace_write.network_access=true`) queda sin objeto. La red del
contenedor sigue abierta por ADR-015 Decisión 4, igual en las dos familias.

### Verificación mecánica

`verificar_paridad.py` incorpora `verificar_confinamiento` (paridad: 117 → **139
chequeos**): que las celdas A lleven `--dangerously-skip-permissions`, que las B lleven
el flag sin sandbox y **no** lleven `-s`, y que ningún `docker run` de ninguna celda
lleve `--security-opt`, `--cap-add`, `--privileged` ni `--userns` —o sea, que la
envoltura no compense con permisos extra en una familia—. El camino negativo se probó
rompiendo los chequeos a propósito.

## Consecuencias

- **Lo que el agente B puede hacer se amplía** respecto de lo que ADR-009 preveía: sin
  sandbox nativo, sus comandos pueden escribir fuera del workspace *dentro del
  contenedor*. Fuera del contenedor no cambia nada: los montajes siguen siendo el repo
  satélite (rw), los logs (rw) y —en celdas con RAG— `comun/` y el corpus (ro), y
  `evaluacion/` no se monta en ninguna celda.
- **Aumenta la paridad, no la reduce.** La asimetría que ADR-009 D1 declaraba como
  limitación conocida queda efectivamente cerrada, ahora sí en el mecanismo.
- La decisión se tomó **antes** de que ninguna implementación existiera, así que no hay
  dato contaminado ni resultado que reinterpretar.
- Se declara en `analisis/amenazas-validez.md` junto con las demás decisiones de entorno:
  los agentes de las 4 celdas corren sin sandbox del SO, confinados sólo por contenedor,
  con red abierta.
