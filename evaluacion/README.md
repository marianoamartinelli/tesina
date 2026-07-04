# Evaluación — harness y protocolo

Artefactos del hito H5 (construidos **antes** de las corridas para eliminar sesgo del
evaluador) y del hito H2 (protocolo experimental pre-registrado).

## Contenido previsto

- **`protocolo.md`** — protocolo experimental pre-registrado: criterios de intervención
  humana y su clasificación (8 causas raíz), orden de construcción, presupuestos,
  procedimiento de corrida paso a paso. Congelado por ADR antes de la piloto.
- **`suite-at/`** — suite de tests de aceptación **black-box** contra el contrato
  HTTP/WebSocket de la épica 09. Se escribe una sola vez y corre idéntica contra las
  4 implementaciones; reporta por **AT-id** (pasa/falla). Cubre backend (épicas 01–09).
- **`rubricas/`** — rúbricas de evaluación para los clientes web y mobile (épicas
  10–11), donde la verificación es en parte manual, y para el rol revisor del agente
  (análisis cualitativo).
- **`alucinaciones.md`** — procedimiento de detección y conteo de alucinaciones de
  dominio (estándares inexistentes, números de BIP/EIP inventados, derivación
  incorrecta).
- **`metricas-estaticas/`** — tooling de complejidad ciclomática, linting y cobertura.
  Nota: el backend es agnóstico de lenguaje, así que el tooling se resuelve por
  lenguaje una vez conocida cada implementación, con criterios equivalentes
  documentados acá.
