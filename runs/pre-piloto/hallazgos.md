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
