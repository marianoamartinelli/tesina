# Evaluación — harness y protocolo

Artefactos del hito H5 (construidos **antes** de las corridas para eliminar sesgo del
evaluador) y del hito H2 (protocolo experimental pre-registrado).

## Contenido

- **`protocolo.md`** — protocolo experimental pre-registrado (v1.0): criterios de
  intervención humana y su clasificación (8 causas raíz), orden de construcción,
  presupuestos, procedimiento de corrida paso a paso. Congelado por
  [ADR-004](../decisiones/ADR-004-protocolo-experimental-preregistrado.md); única
  ventana de ajuste: la corrida piloto (H6).
- **`rubricas/`** — rúbricas manuales pre-registradas para los clientes (una fila por
  AT-id, veredicto PASA/FALLA/NO_EVALUABLE): `epica-10-web.md` (78 AT + `AT-10-E2E-01`)
  y `epica-11-mobile.md` (94 AT). Se completan una sola vez por corrida en H8, por el
  mismo evaluador, en el mismo orden.
- **`alucinaciones.md`** — procedimiento pre-registrado de detección y conteo de
  alucinaciones de dominio (categorías C1–C6, regla de doble conteo con fallos de AT,
  barrido mecánico por grep + verificación contra el corpus congelado, unidad de
  conteo, doble pasada del mismo evaluador).
- **`metricas-estaticas/`** — criterios pre-registrados de métricas estáticas
  comparables entre lenguajes (cloc 2.10, lizard 1.23.0, jscpd 5.0.11, dependencias
  directas, cobertura de tests propios) y `medir.sh` que vuelca
  `runs/<id>/metricas-estaticas.csv`. El linting específico de framework y las métricas
  estéticas quedan explícitamente fuera (ver su README §3).
- **`suite-at/`** — suite de tests de aceptación **black-box** contra el contrato
  HTTP/WebSocket de la épica 09. Se escribe una sola vez y corre idéntica contra las
  4 implementaciones; reporta por **AT-id** (`resultados-at.csv`). Cubre backend
  (épicas 01–09, 521 ATs). Incluye el catálogo completo de 693 ATs
  (`catalogo-at.csv`), los helpers documentados (`HELPERS.md`), el entorno on-chain
  local (anvil chainId 11155111 + USDC-mock) con el contrato de arranque del SUT, y
  la declaración de ATs no automatizables. **Sólo se corre en H8** (regla de
  no-exposición, ver su README).

## Contenido previsto (H5)
- **`rubricas/`** — rúbrica del rol revisor del agente (análisis cualitativo),
  complementaria a las de épicas 10–11 ya existentes.
