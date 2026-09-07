# 2026-09-07 — pre-piloto-2: la generación con los cambios del día anterior y la evaluación por agentes, hasta que los proveedores dijeron basta

- **Hito:** H6. Corrida **pre-piloto-2** (ADR-018, descartable), lanzada el 2026-09-06 a las
  23:54 en modo autónomo por pedido del tesista («seguí ejecutando una nueva pre-piloto
  supervisada post los cambios que charlamos»), sobre el mismo universo reducido que la
  primera y con todo lo decidido el 2026-09-06: `spec-v1.2`, RAG instruido, rollouts de B,
  evaluación gestionada por agentes (ADR-026), emulador.
- **Contexto:** sesión con Claude Code de la noche entera, sin el tesista. Registro en
  `runs/pre-piloto-2/` (manifests, intervenciones, hallazgos H2-01..08, evaluación de A).

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

## Decisiones tomadas

- `--desde-paso N` en el orquestador: la continuación de §5.8 repone sólo el paso
  interrumpido (hasta hoy re-invocaba la etapa entera).
- El barrido de alucinaciones excluye `spec/` del repo satélite (criterio de ADR-022).
- Una pasada del evaluador sin salida es una pasada fallida: exit 1, se repite.

## Pendientes (del tesista)

1. **Cupo del juez tercero (H2-07):** esperar la reposición semanal de Grok, comprar
   créditos de API de xAI (runtime alternativo de ADR-026 D1, sin implementar) o subir de
   tier. Sin eso, la evaluación por agentes no termina ni para el universo reducido.
2. **B bajo suscripción (H2-08):** ~30 minutos de trabajo por ventana de 5 horas.
   Reabre suscripción/API key **sólo para B**.
3. Cerrar la pre-piloto-2 cuando haya cupo: white-box p2 + arbitraje, alucinaciones p2 +
   arbitraje, rúbricas web y mobile de A; las tres etapas restantes y la evaluación de B.

## Observaciones de método

- **Los dos topes que ADR-016 declaró inexistentes aparecieron la misma noche, en los dos
  proveedores que no son A:** Codex por ventana de 5 horas y Grok por pool semanal. A, con
  la misma suscripción de siempre, no se cortó.
- **Un stream que no muestra un evento no prueba su ausencia**, por segunda vez: el
  `--json` de Codex escondía la mitad del consumo y toda la delegación; los rollouts, no.
- El circuito de dos pasadas más arbitraje funciona: cuatro instrumentos corrieron con
  salidas válidas, evidencia por fila y arbitrajes que citan la regla que decide.
