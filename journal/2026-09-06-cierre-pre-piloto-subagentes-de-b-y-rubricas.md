# 2026-09-06 — Cierre de la pre-piloto: los subagentes de B no estaban en el registro, y los ensayos de las rúbricas

- **Hito:** H6. `piloto-01` sigue sin iniciar. La sesión retoma lo que la del 2026-08-24
  dejó abierto: 7 componentes de la matriz sin verificar y tres decisiones del tesista.
- **Contexto:** sesión con Claude Code con el pedido de «continuar con el pre-piloto:
  analizar la sesión anterior, identificar los siguientes pasos, ejecutarlos y
  monitorear». Sin el tesista presente: todo lo que era decisión suya quedó como decisión,
  no se tomó.

## Qué se hizo

**Se buscó la causa de H-22 y H-22 estaba mal leído.** Dos corridas de control en el
contenedor de B (`codex exec` 0.146.0, mismos flags del orquestador, pedido explícito de
lanzar un subagente) muestran que **B sí puede delegar** —`multi_agent` viene en `true` y
`spawn_agent` creó un segundo thread que ejecutó el comando pedido— y que **el stream
`--json` no lo registra**: sólo emite un `wait` con `receiver_thread_ids: []`, la forma
exacta de los 24 `collab_tool_call` que la pre-piloto leyó como «no delegó». Los rollouts
del CLI, que sí tienen al subagente, vivían adentro del contenedor efímero y se perdieron
con cada paso. Además, `turn.completed.usage` del thread principal no incluye los tokens
del subagente: el consumo de B en el manifest es una cota inferior.

**ADR-023 (Propuesto) y su implementación.** B monta `<logs>/sesiones-codex/` en
`$CODEX_HOME/sessions`, hermano del `auth.json`; `verificar_paridad.py` admite esa segunda
diferencia declarada y la chequea (143 → **145** chequeos, exit 0); los 5 tests del
pipeline pasan; una invocación real con los dos montajes dejó su rollout en el host. A no
cambia: su stream ya trae a los subagentes.

**Se ensayaron dos de las tres rúbricas manuales sobre B**, como ensayo del instrumento
y no como veredicto (`runs/pre-piloto/rubricas/`):

- **Web, `HU-10-01`** (backend y cliente de B en contenedores con puerto publicado,
  navegador automatizado): **10 PASA / 1 FALLA** — el cliente no muestra el aviso de
  sesión expirada al 401 (AT-10-01-07). Tres huecos del instrumento (H-24): el rate limit
  no tiene valores fijados por la spec ni por el entorno y el evaluador tuvo que elegir
  `5 / 60 s`; AT-10-01-07 supone «otra pantalla» que un cliente de sólo login no tiene;
  Playwright no está entre las herramientas permitidas aunque hace lo mismo que DevTools
  y el proxy.
- **Rol revisor, completa** (delegada a un subagente de la sesión): censo de 11 puntos,
  **35 PASA / 1 FALLA** (RV-07 en mobile), y nueve huecos del instrumento (H-26), de los
  que el más serio es que la escala de severidad colapsa a `MAYOR` y RV-07 mide un orden
  que el revisor no usó.
- **Mobile: no ejecutable** (H-25). La rúbrica exige emulador o dispositivo; no hay
  ninguno. Son 94 ATs que en H8 quedarían `NO_EVALUABLE` en las 4 celdas.

**Datos que faltaban para las decisiones pendientes.** H-19: el tiempo que el evaluador
white-box declara sobreestima el de pared entre 8,5× y 10,8× en las cuatro pasadas.
Consumo: escalando linealmente por HU, una celda A a `effort high` proyecta ≈ USD 700 de
equivalente API y etapas de varias horas, o sea cruzar la ventana de 5 horas del rate
limit en cada etapa.

**Checklist H6:** 18 de 24 ítems cerrados (16 y 23 por mecanismo); el 24 se reabrió
(H-23). Matriz de la pre-piloto: 38 de 44.

## Decisiones tomadas

- ADR-023, como **Propuesto**: cambia qué se registra (ADR-003) y es del tesista
  ratificarlo. El código ya está; si no se ratifica, se revierte el commit del pipeline.
- Las rúbricas se ensayaron y no se «completaron»: el veredicto de registro es del tesista
  (rúbricas, §Procedimiento general). Lo que se conserva son los huecos del instrumento.

## Pendientes (del tesista, todas con el dato ya medido)

1. **H-12** — el uso del corpus (las tres opciones están en `hallazgos.md`).
2. **Consumo y rate limit** — revisar el supuesto de ADR-016 con la proyección de arriba,
   y suscripción contra API key para las oficiales.
3. **H-19 y `skip = 0`** — `duracion_min` como no-métrica; los 2 skips de rate limiting
   opcional frente a la regla de ADR-011. Se conecta con H-24 (1): fijar umbral y ventana
   del rate limit en el contrato de arranque del entorno resuelve las dos cosas.
4. **Ratificar ADR-023.**
5. **H-25** — cómo se evalúa la épica 11 sin emulador.
6. **Arbitraje** de AT-06-03-10 (`no-automatizables-b/arbitraje.md`).
7. Los huecos de las rúbricas (H-24, H-26) por la cláusula de re-pre-registro, antes de H7.

## Observaciones de método

- **Un registro que no emite un evento se lee como ausencia del evento.** H-22 concluyó
  «B no delegó» con un dato verdadero (24 `wait` sin receptores) y una inferencia falsa
  (que el stream mostraría un `spawn_agent` si lo hubiera). Lo destapó una corrida de
  control con el resultado conocido de antemano, que es lo que habría que hacer con cada
  «no ocurrió» que salga de un stream de CLI.
- **El modelo de B reportó como recibida una salida que su `wait` no le devolvió** (primera
  corrida de control). En una corrida oficial eso pasa desapercibido en el `--json`; en
  los rollouts no.
- **Docker Desktop estaba pausado manualmente** y `docker desktop start` no lo despausa;
  `docker desktop restart` sí. Entra al procedimiento de arranque junto con `caffeinate`.
- Delegar el censo de la rúbrica del rol revisor a un subagente funcionó: 69 llamadas a
  herramientas y 5 minutos de escritura, con evidencia por celda; el costo fue que su
  lectura previa del material no quedó medida.
