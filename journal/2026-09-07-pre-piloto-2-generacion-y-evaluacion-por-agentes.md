# 2026-09-07 — pre-piloto-2: la generación con los cambios del día anterior y la evaluación por agentes, hasta que los proveedores dijeron basta

- **Hito:** H6. Corrida **pre-piloto-2** (ADR-018, descartable), lanzada el 2026-09-06 a las
  23:54 en modo autónomo por pedido del tesista («seguí ejecutando una nueva pre-piloto
  supervisada post los cambios que charlamos»), sobre el mismo universo reducido que la
  primera y con todo lo decidido el 2026-09-06: `spec-v1.2`, RAG instruido, rollouts de B,
  evaluación gestionada por agentes (ADR-026), emulador.
- **Contexto:** sesión con Claude Code de la noche entera, sin el tesista. Registro en
  `runs/pre-piloto-2/` (manifests, intervenciones, hallazgos H2-01..11, evaluación de las
  dos celdas).

## Qué se hizo

**Antes de arrancar, ADR-026 quedó implementado y verificado:** `evaluacion/runtime_evaluador.py`
(Grok Build `grok-4.6` con `GROK_HOME` por invocación y `HOME` vacío —sin eso el CLI carga
las 58 skills y los plugins de Claude Code del host—), `agente-instrumentos/correr.py` (los
cinco instrumentos, discrepancias mecánicas, arbitraje), cinco briefings pre-registrados
(escritos por un subagente de la sesión), `--runtime grok` en el white-box, protocolo
**v1.7** y las versiones de los instrumentos. El circuito completo se probó primero sobre
la pre-piloto 1: rol revisor de B en dos pasadas (36/36 concordantes, censo 9/11) y
arbitraje de las dos discrepancias con evidencia y regla citadas (H-27). Mismos veredictos
que el ensayo con Claude del día anterior.

**Generación.** A completó sus tres etapas sin un corte: 65 + 43 + 62 minutos, **USD 168,67**,
y **25 consultas al corpus** (16 + 0 + 9; en la pre-piloto 1 fueron 0): la instrucción de
ADR-025 D1 cambia el comportamiento de A, con queries precisas sobre BIP-32/39/44, EIP-55
y ERC-681 (H2-04). B fue cortada **dos veces** por el límite de uso de la suscripción de
Codex —a los 24 minutos y, tras esperar 5 h 17, a los 29— y quedó en el paso 3 de backend
con la continuación programada para las 13:37 (H2-02, H2-08, INT-01/02). Los rollouts
persistidos por ADR-023 mostraron que **B lanza 3 subagentes en cada invocación** y que esos
subagentes consumen más entrada que el thread principal (22,7 M contra 20,1 M): el
`--json` veía la mitad del consumo real (H2-01). Codex además rechaza `rm -f` aunque el
sandbox esté desactivado (H2-03).

**Evaluación de A** (todo por Grok Build, salvo lo mecánico): black-box **53 pasa / 3 falla /
0 skip** —los dos ATs de rate limiting que eran `skip` ahora pasan—, después de corregir un
defecto del harness que la spec v1.2 destapó: la suite, desde un único origen, se limitaba a
sí misma (24 fallas + 12 errores por 429); ahora frena su propio tráfico a `/auth/*` (H2-05).
Rol revisor: dos pasadas con **36/36** en criterios (29 PASA / 7 FALLA; entre ellas RV-02 en
web porque la sesión del revisor de A creó `.claude/worktrees/`), censo de 27 puntos con 3
discrepancias. White-box pasada 1: **22/22**. Alucinaciones pasada 1: 1 hecho en 1 604
candidatos, 607 de ellos ruido de `sut/spec/` (corregido en el runner, H2-06). Métricas
estáticas: 5 901 + 1 533 + 4 034 loc.

**A las 03:40 Grok Build agotó su pool semanal** (402) con tres sesiones en vuelo —white-box
p2, arbitraje del revisor, alucinaciones p2— y las tiró. Faltan ~10 sesiones de A y las 15
de B (H2-07). El runner declara fallida toda pasada sin salida y la repite entera.

## Cierre de la corrida (tarde del 2026-09-07)

El tesista extendió las dos suscripciones a la mañana («reanudemos») y la sesión siguió
sola hasta cerrar las dos celdas.

**B terminó de generar.** El paso 3 de backend se repuso con `--desde-paso 3` (INT-03) y
web y mobile corrieron sin cortes (INT-04, INT-05); repo congelado en `f4770bf`. B hizo
**17 consultas al corpus** (15 + 0 + 2) y dejó **44 rollouts** (11 threads principales +
33 de subagente): 3 subagentes por invocación, profundidad 1. A, medido con el mismo
criterio, abrió 31 en 9 invocaciones. El ítem 24 de la checklist queda cerrado con eso;
la checklist pasa a **20 de 24** (abiertos 1, 2, 19 y 22).

**La evaluación se completó en las dos celdas, toda por Grok Build:** 2 pasadas + arbitraje
por instrumento, 5 instrumentos, 10 circuitos. Tabla completa en `runs/pre-piloto-2/hallazgos.md`
§Resultados. Lo que importa de ahí: las dos implementaciones dan el mismo white-box (22/22)
y casi el mismo black-box (53/3 y 52/4; las 3 fallas comunes son endpoints fuera del
universo, la cuarta de B es un canal lateral de tiempo en el login, `AT-01-02-11`); A
escribe **11 468** loc contra **5 825** de B (2,0×; en la pre-piloto 1 fue 2,3×); el
juez concuerda consigo mismo en 8 de los 10 circuitos con 0 discrepancias, y las
discrepancias reales (3 del censo del revisor de A, 5 candidatos de alucinaciones de A)
las resolvió el arbitraje citando evidencia y regla. La rúbrica mobile corrió por primera
vez sobre el emulador: 15 PASA / 1 NO_EVALUABLE en A (reconexión del WebSocket privado, fuera del backend reducido) y 16/16 en B, sin discrepancias entre pasadas en ninguna de las dos.

**Tres hallazgos más (H2-09..11):** la sensibilidad del agente de alucinaciones varía
entre pasadas sobre candidatos idénticos (0 y 5), y es la doble pasada la que lo absorbe;
el runner del rol revisor perdía los pasos de una etapa continuada (corregido: concatena
los JSONL y funde snapshots); y la primera pasada mobile de B fue inválida porque el
operador puso la variable de URL de A (`EXPO_PUBLIC_API_BASE_URL` contra
`EXPO_PUBLIC_API_URL`) y Expo Go 57 contra un SDK 54 — el contrato de arranque del entorno
mobile tiene que exigir leer esos dos datos del SUT y verificar un login antes de lanzar.

**Manifests §5 y §6 completos** (tokens por pasada de cada sesión de Grok), tablas
regeneradas desde los archivos primarios por script, y el artifact «Avance para
directores» rehecho por un subagente con contexto limpio sobre el formato del PDF de
julio.

## Decisiones tomadas

- `--desde-paso N` en el orquestador: la continuación de §5.8 repone sólo el paso
  interrumpido (hasta hoy re-invocaba la etapa entera).
- El barrido de alucinaciones excluye `spec/` del repo satélite (criterio de ADR-022).
- Una pasada del evaluador sin salida es una pasada fallida: exit 1, se repite.

## Pendientes (del tesista)

1. **Re-pre-registrar la rúbrica del rol revisor** (H-26): la pre-piloto-2 vuelve a
   mostrar el hueco de RV-07 (las 3 FALLA de A por orden de severidad) y suma RV-05/RV-08.
2. **Contrato de arranque del entorno mobile** (H2-11) en `suite-at/entorno/README.md`.
3. **Ítems 19c (A ante el rate limit) y 22 (compactación de B)** de la checklist: sólo
   los mide una etapa más larga que el universo reducido.
4. **Decidir si `piloto-01` se corre como estaba previsto** (spec entera, `xhigh`, una
   sola celda) o si las dos pre-pilotos ya cubren lo que H6 pedía y se pasa a H7. Con los
   topes medidos (B ~30 min por ventana de 5 h; Grok por pool semanal), una corrida
   completa se va a repartir en muchas ventanas.

## Observaciones de método

- **Los dos topes que ADR-016 declaró inexistentes aparecieron la misma noche, en los dos
  proveedores que no son A:** Codex por ventana de 5 horas y Grok por pool semanal. A, con
  la misma suscripción de siempre, no se cortó.
- **Un stream que no muestra un evento no prueba su ausencia**, por segunda vez: el
  `--json` de Codex escondía la mitad del consumo y toda la delegación; los rollouts, no.
- El circuito de dos pasadas más arbitraje funciona: cuatro instrumentos corrieron con
  salidas válidas, evidencia por fila y arbitrajes que citan la regla que decide.
- **Dos errores del operador en un día, los dos por dar por sabido algo que cada SUT
  define a su manera** (la variable de URL del cliente mobile; la versión de Expo Go). En
  H8 hay cuatro SUT de dos familias: lo que no está en un contrato escrito se va a volver
  a equivocar.
- Toda tabla de resultados se regenera por script desde los CSV/JSONL primarios; ninguna
  cifra de hoy se tipeó a mano.
