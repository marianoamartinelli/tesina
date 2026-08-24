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
