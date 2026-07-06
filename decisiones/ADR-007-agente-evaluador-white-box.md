# ADR-007 — Agente evaluador para los ATs no automatizables (rúbrica white-box)

- **Estado:** aceptado (2026-07-06)
- **Contexto:** 66 ATs de las épicas 01–09 quedaron declarados no automatizables
  black-box (`evaluacion/suite-at/no-automatizables.yaml`): su vía de evaluación es
  white-box (inspección de código, procedimientos sobre el ciclo de vida/config del
  SUT, criptografía contra funciones internas). Esa evaluación debe ser **idéntica
  entre las 4 celdas** — misma vara, mismos pasos, mismo criterio — y el tesista
  decidió instrumentarla con un **agente evaluador LLM** en lugar de ejecutarla a
  mano, para eliminar la deriva humana entre corridas.

## Decisión

### 1. Un único agente evaluador, congelado

- **Modelo pinneado:** `claude-opus-4-8` (mismo criterio de pinneo que ADR-005),
  ejecutado headless con el Claude Agent SDK ya instalado en `pipeline/`
  (herramientas de lectura de archivos y bash: exactamente lo que la evaluación
  white-box necesita).
- **Instrucciones congeladas:** el briefing completo vive versionado en
  `evaluacion/agente-evaluador/briefing.md` y se pasa **verbatim** en las 4 celdas.
  Ningún prompt ad hoc.
- **Mismo contexto inicial, sesión fresca por celda:** el agente arranca cada celda
  sin memoria de las anteriores. Insumos permitidos: el briefing, la rúbrica, la spec
  (`spec-v1.1`), el corpus congelado de H3 (referencia normativa para todo chequeo
  BIP/EIP: el agente tiene prohibido resolver contenido de estándares "de memoria"),
  la **copia de evaluación** del repo de la celda, y el entorno levantado (SUT +
  anvil con la config de evaluación). Insumos prohibidos: resultados de la suite
  black-box, rúbricas web/mobile completadas, otras celdas, `journal/`, `runs/`,
  `analisis/`.
- **Orden fijo:** los 66 ATs en orden ascendente de AT-id, mismas precondiciones de
  entorno documentadas en la rúbrica.

### 2. Veredictos condicionados a evidencia (evidence-gated)

Veredicto por AT: `PASA` / `FALLA` / `NO_EVALUABLE` (con causa tipificada). Todo
veredicto exige **evidencia citada**: rutas y líneas de archivo inspeccionado, o
comando ejecutado + salida relevante. **Un veredicto sin evidencia es inválido** y se
trata como no emitido. El agente no repara, no modifica el repo evaluado (sólo
lectura; ejecuciones en copia descartable) y no emite juicios de calidad — sólo
verifica las propiedades que la rúbrica enumera.

### 3. Ciego parcial y amenaza de self-preference

Evaluar implementaciones generadas por Claude y por GPT con un modelo de uno de los
dos proveedores introduce riesgo de **self-preference (LLM-as-judge)**. Mitigaciones
pre-registradas:

1. La **copia de evaluación** se prepara **sin `.git`** ni metadatos de la corrida
   (elimina autores/mensajes de commit como señal del modelo generador); el briefing
   prohíbe explícitamente intentar identificar al generador.
2. La rúbrica reduce el juicio a verificaciones mecánicas con evidencia — el espacio
   de discrecionalidad del evaluador es mínimo por construcción.
3. **Doble pasada independiente por celda** (dos sesiones frescas con el mismo
   briefing); las discrepancias las arbitra el humano con la evidencia de ambas.
4. **Auditoría humana del 100%:** el tesista revisa cada veredicto contra su
   evidencia y firma el resultado final. El agente es un **instrumento**; el
   evaluador de registro sigue siendo el humano (se preserva ADR-004 §2.5).
5. **Chequeo de concordancia opcional** (si el presupuesto lo permite, pre-registrado
   acá): re-evaluar una muestra aleatoria de 10 ATs por celda con un evaluador espejo
   (`gpt-5.5`, mismo briefing) y reportar la tasa de acuerdo — detector de sesgo
   sistemático. Su omisión por presupuesto se registra en el journal.

La amenaza y sus mitigaciones se discuten en el cap. 4 (amenazas a la validez).

### 4. Artefactos y salida

- `evaluacion/agente-evaluador/briefing.md` — instrucciones congeladas del agente
  (rol, insumos, prohibiciones, formato de salida, criterio de veredicto).
- `evaluacion/agente-evaluador/rubrica-white-box.md` — el checklist operativo: una
  entrada por AT (66/66, verificado contra el yaml), agrupadas por familia de
  procedimiento, con pasos accionables, evidencia mínima obligatoria y criterio
  cerrado de veredicto.
- `evaluacion/agente-evaluador/plantilla-resultados.yaml` — formato de salida
  obligatorio por AT.
- Salida por corrida: `runs/<id>/no-automatizables/pasada-1.yaml`, `pasada-2.yaml` y
  `veredicto-final.yaml` (el del humano tras arbitrar), que alimenta la fila
  `no_automatizado` del dataset de H8.

### 5. Relación con el protocolo

El texto de `evaluacion/protocolo.md` (congelado por ADR-004) se actualizará en la
revisión post-piloto ya prevista, incorporando este instrumento. La **piloto (H6)
ejercita también este framework** (agente, briefing, rúbrica y formato de salida);
sus defectos se corrigen en esa ventana y el conjunto queda congelado antes de las
corridas oficiales, igual que el resto de H2–H5.

## Consecuencias

- La evaluación de los 66 deja de depender de la consistencia manual del tesista
  entre la corrida 1 y la 4; el costo es el sesgo LLM-judge, acotado por §3.
- El mismo framework queda disponible como patrón si en el futuro se instrumentan
  las rúbricas web/mobile (fuera de alcance por ahora: siguen siendo manuales).
