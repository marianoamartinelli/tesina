# Hallazgos de la pre-piloto-2

Numerados `H2-NN`. Mismo criterio que `runs/pre-piloto/hallazgos.md`: defectos y datos que
la corrida saca a la luz; lo que toca protocolo o metodología sale por ADR.

## H2-01 — B delega en subagentes: tres threads hijos en el paso 1, con tanto consumo como el principal

- **Componente:** 3.4 (delegación) y 5.6 (costo de B) — confirma **H-23** con una corrida real
- **Observado:** en los primeros 24 minutos del paso 1 de `pre-piloto-2b`, `sesiones-codex/`
  (ADR-023) recibió **4 rollouts**: el thread principal (`thread_source: user`) y **3 de
  subagente** (`thread_source: subagent`), que revisaron la implementación y le reportaron
  defectos al principal («Reporté cuatro defectos concretos al agente principal», «Revisión
  entregada al agente principal»). El `--json` del paso no emitió ningún `spawn_agent`.
- **Consumo:** el thread principal acumuló 10,06 M tokens de entrada (9,88 M cacheados) y
  39 185 de salida; los tres subagentes, **2,57 M + 3,07 M + 4,02 M de entrada** y
  17 391 + 19 271 + 25 935 de salida. `turn.completed` del `--json` no los incluye: el
  consumo real de B es del orden del **doble** de lo que la pre-piloto 1 registró.
- **Estado:** medido; entra al manifest §5 de B y al ítem 24 de la checklist H6.

## H2-02 — Corte por límite de uso de la suscripción de Codex a los 24 minutos de etapa

- **Componente:** 1.5 (corte por exit ≠ 0, **ejercitado en real por primera vez**) y
  protocolo §5.8
- **Observado:** 00:18:38 (-03): `error` + `turn.failed` con «You've hit your usage limit
  … try again at 5:35 AM»; `codex exec` salió con 1; el orquestador tomó el snapshot del
  paso 1 (97 archivos) y registró `corte: codigo_salida_no_cero`. El límite se agotó con
  10 M de entrada del principal más ~9,7 M de los subagentes en 24 minutos, sumados a las
  corridas de control y de la sesión anterior del mismo día.
- **Qué confirma:** ADR-025 D3 —la continuación por rate limit es el camino estándar— se
  aplica en la primera etapa de la primera corrida tras decidirlo. La continuación
  (INT-01) se programó para las 05:36 (-03). El tiempo de pared de la etapa backend de B
  no será utilizable como dato (mismo criterio que H-10).
- **Estado:** registrado; continuación en curso.

## H2-03 — El router de herramientas de Codex rechaza `rm -f` aunque el sandbox esté desactivado

- **Componente:** 3.3 (confinamiento de B)
- **Observado:** stderr del paso 1: `exec_command failed for /bin/sh -lc 'rm -f /tmp/…sqlite…'
  … Rejected("rm -f style commands are not permitted. Use a safer approach")`, con
  `--dangerously-bypass-approvals-and-sandbox` (ADR-019). También `timeout_ms must be at
  least 10000` ante un timeout menor pedido por el modelo. Son restricciones del CLI 0.146.0,
  no del contenedor; A no tiene equivalente.
- **Por qué importa:** es una asimetría de capacidad entre brazos no declarada en ADR-009
  D1. El agente puede rodearla (`find -delete`, `node -e`), pero cuesta turnos.
- **Estado:** a sumar a `analisis/amenazas-validez.md` como asimetría declarada.

## H2-04 — Con la instrucción de ADR-025 D1, A consulta el corpus desde el primer minuto

- **Componente:** 4.2 (consultas reales al corpus)
- **Observado:** `pre-piloto-2a`, paso 1: **8 `consulta_rag`** en los primeros 20 minutos
  (0 en las tres etapas de la pre-piloto 1). B: 0 hasta el corte (H2-02), con el mismo
  prompt de sistema.
- **Estado:** en medición; el conteo final por celda y etapa va al cierre.
