# ADR-004 — Protocolo experimental pre-registrado y congelado antes de las corridas

- **Estado:** Aceptado
- **Fecha:** 2026-07-05

## Contexto

La métrica "intervenciones humanas por causa raíz" sólo es comparable entre las 4
celdas del factorial si los criterios de intervención (cuándo intervenir, cómo
clasificar, cuánto insistir) están fijados **antes** de la primera corrida. Lo mismo
aplica a los presupuestos y al orden de construcción: cualquier criterio definido
sobre la marcha se convierte en una variable no controlada y en una amenaza directa a
la validez interna del experimento. La propuesta ya identifica este riesgo; el roadmap
lo aborda como hito H2.

## Decisión

1. El protocolo experimental queda **pre-registrado** en
   [`evaluacion/protocolo.md`](../evaluacion/protocolo.md) **v1.0**, que fija:
   definición operativa de intervención, disparadores objetivos (D1–D4), política de
   no-intervención, contenido permitido de las intervenciones (incluida la regla de
   no-exposición del holdout durante la corrida), cascada determinista de
   clasificación en las 8 causas raíz de la propuesta, reglas de estancamiento y
   abandono de etapa, presupuestos por corrida, orden de construcción
   backend → web → mobile, sorteo del orden de las celdas, y el registro obligatorio
   por corrida.
2. **Ventana de ajuste única:** sólo los defectos que revele la corrida piloto (H6)
   pueden modificar el protocolo. Todo cambio produce una nueva versión del documento
   y un ADR que reemplaza a este, **antes** de la primera corrida oficial.
3. Durante las corridas oficiales (H7) el protocolo es **inmutable**. Una desviación
   forzada por circunstancias se registra en el momento (journal + log de la corrida)
   y se discute como amenaza a la validez; no se "corrige" el protocolo retroactivamente.
4. Los presupuestos de la sección 6 del protocolo (200 USD / 24 h activas por corrida,
   tokens sin tope propio) son **provisionales hasta la piloto**; los definitivos se
   pinnean en el manifest de cada corrida oficial.

## Consecuencias

- La métrica de intervenciones es comparable entre celdas y auditable contra un
  criterio público y fechado (pre-registro).
- El evaluador pierde discrecionalidad durante las corridas: si un caso no encaja en
  D1–D4, no se interviene. Esto puede dejar corridas "peores" de lo que un operador
  libre lograría — es intencional: se mide el pipeline, no al operador.
- La piloto gana un rol formal adicional: única fuente legítima de ajustes al
  protocolo (y entrenamiento del evaluador).
- El capítulo 4 de la tesis (diseño experimental) puede redactarse citando este ADR y
  el protocolo como artefactos congelados.
