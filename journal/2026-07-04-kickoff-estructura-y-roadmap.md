# 2026-07-04 — Kickoff: estructura del repo y roadmap

- **Contexto:** hito H0 (infraestructura del repo). Sesión de trabajo con Claude Code.
- **Estado previo:** repo con un único commit (`spec: especificacion inicial del
  exchange`); spec completa (12 épicas, 57 HUs, 676 AT-ids únicos); `propuesta/` y
  `CLAUDE.md` sin trackear.

## Qué se hizo

- Se analizó la propuesta de tesina (Formulario 1) contra el estado real del repo:
  las fases 1 (preparatoria) y 2 (especificación) de la propuesta están mayormente
  cubiertas por la spec existente; lo que falta de la fase preparatoria es corpus RAG,
  harness de agentes y harness de evaluación.
- Se definió la estructura de versionado del proyecto (este commit): `decisiones/`,
  `journal/`, `corpus/`, `pipeline/`, `evaluacion/`, `runs/`, `analisis/`, `tesis/`,
  más `ROADMAP.md` con hitos H0–H10.
- Se creó el esqueleto LaTeX de la tesina con la estructura de capítulos derivada de
  la propuesta.
- Se publicó un artefacto visual con el roadmap, el protocolo y la estructura del
  experimento: <https://claude.ai/code/artifact/064ea0c6-f229-4a71-b998-3d9bef9d719b>
  (se regenera cuando el plan cambie; la fuente de verdad es el repo).

## Decisiones tomadas (formalizadas como ADR)

- **ADR-001:** las implementaciones generadas viven en repos git separados por corrida;
  este repo las referencia vía manifest. Motivo: aislamiento experimental + el
  historial de commits del agente es dato primario.
- **ADR-002:** tesina en LaTeX, un `.tex` por capítulo, versionada en `tesis/`.
- **ADR-003:** registro exhaustivo — journal por sesión + ADRs + manifests de corrida;
  convención de commits `area: descripción`.

## Riesgos metodológicos identificados en el análisis

1. **Spec freeze pendiente (H1):** si la spec cambia después de la primera corrida, el
   experimento pierde la condición "input idéntico". Auditar y taggear antes de todo.
2. **El harness de evaluación debe existir antes de las corridas (H5):** la propuesta
   no lo lista como artefacto explícito, pero evaluar con tests escritos después de
   ver las implementaciones introduce sesgo del evaluador. La épica 09 (contrato
   HTTP/WS) permite una única suite black-box reutilizable para las 4 corridas.
3. **Falta una corrida piloto en la propuesta (H6):** sin piloto, los defectos del
   protocolo se descubren quemando corridas oficiales.
4. **n=1 por celda:** sin réplicas no hay inferencia estadística; el marco correcto ya
   está en la propuesta (DSR + estudio de caso, Yin). Documentar como amenaza a la
   validez; evaluar réplicas si el presupuesto lo permite.
5. **Deriva de modelos comerciales:** pinnear model IDs exactos y ejecutar las 4
   corridas en ventana temporal corta.
6. **Criterios de intervención humana:** deben pre-registrarse (H2) para que la métrica
   de intervenciones sea comparable entre celdas.

## Pendientes / próximos pasos

- H1: auditoría de consistencia de la spec y tag `spec-v1.0`.
- H2: redactar el protocolo experimental pre-registrado.
- Verificar si la Facultad exige plantilla de tesina propia (afecta ADR-002 sólo en
  formato, no en flujo).

## Observaciones para el meta-análisis

- La estructura de registro (journal/ADR/manifest) se definió *antes* de la primera
  corrida — el meta-análisis podrá cubrir el proyecto completo sin huecos.
- Decisiones de esta sesión tomadas vía preguntas cerradas del asistente con
  recomendación explícita; las tres recomendaciones fueron aceptadas.
