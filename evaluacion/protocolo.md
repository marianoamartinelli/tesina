# Protocolo experimental pre-registrado — v1.0

- **Estado:** congelado por [ADR-004](../decisiones/ADR-004-protocolo-experimental-preregistrado.md) (2026-07-05).
- **Ventana de ajuste:** únicamente los defectos que revele la **corrida piloto** (H6)
  pueden motivar cambios, que se registran como nueva versión de este documento más un
  ADR que reemplace a ADR-004, **antes** de la primera corrida oficial. Durante las
  corridas oficiales el protocolo es **inmutable**.
- **Propósito:** fijar, antes de cualquier corrida, las reglas que hacen comparables a
  las 4 celdas del factorial 2×2: cuándo interviene el humano y cómo se clasifica cada
  intervención, en qué orden se construye, con qué presupuestos, qué se registra y cómo.
  Todo criterio definido "sobre la marcha" invalidaría la comparación entre celdas.

---

## 1. Diseño experimental (referencia)

Factorial 2×2 — factor **modelo** (A: Claude / Claude Agent SDK; B: GPT / OpenAI Agents
SDK) × factor **RAG** (sin / con corpus de BIPs y EIPs). Cuatro corridas oficiales
(`a-sin-rag`, `a-con-rag`, `b-sin-rag`, `b-con-rag`) más una piloto descartable
(`piloto-01`). Variables dependientes (según la propuesta): tasa de ATs superados por
AT-id, intervenciones humanas por causa raíz, alucinaciones de dominio, métricas
estáticas, adherencia a estándares on-chain.

## 2. Variables controladas (constantes entre celdas)

Idénticos en las 4 corridas oficiales, pinneados en el manifest de cada corrida
**antes** de iniciarla:

1. **La spec:** el commit del tag `spec-v1.0`. Es el único contenido del repo satélite
   al arrancar.
2. **El corpus RAG** (sólo celdas con RAG): mismo commit de `corpus/` para ambas.
3. **El pipeline:** mismas etapas, mismos prompts de etapa, mismas herramientas
   habilitadas; sólo cambian el modelo y el conmutador RAG (paridad verificada en H4).
4. **Los model IDs:** exactos, pinneados por ADR antes de la primera corrida oficial.
5. **El evaluador humano:** el tesista, en todas las corridas.
6. **Este protocolo:** criterios de intervención, presupuestos y registro.
7. **La ventana temporal:** las 4 corridas oficiales se ejecutan en una ventana corta
   (objetivo: ≤ 2 semanas entre la primera y la última) para minimizar la deriva de los
   modelos comerciales.

## 3. Secuencia de una corrida (idéntica ×5)

1. **Crear el repo satélite limpio** (`tesina-run-<id>`) que contiene únicamente la
   spec pinneada a `spec-v1.0`. Registrar el hash del commit inicial.
2. **Completar y commitear el manifest** (secciones 1–4 de
   `runs/plantillas/manifest.template.yaml`) antes de que el agente ejecute nada.
3. **Ejecutar el pipeline** con la configuración de la celda, en el orden de
   construcción de la sección 4.
4. **Registrar cada intervención humana en el momento** (sección 5), en
   `runs/<id>/intervenciones.md`.
5. **Cerrar la corrida:** completar la sección 5 del manifest (timestamps, costo,
   tokens, total de intervenciones) y **congelar el repo satélite** (sólo lectura).
   Cualquier corrección posterior invalida la medición.
6. **Evaluar** (H8, posterior e independiente): correr el harness de evaluación, volcar
   métricas a `runs/<id>/metricas.md` y escribir la entrada de journal de la corrida.

## 4. Orden de construcción y avance de etapa

- **Orden fijo:** `backend` (épicas 01–09) → `cliente web` (épica 10) → `cliente
  mobile` (épica 11). El mismo en las 5 corridas.
- **Criterio de avance de etapa:** se pasa a la etapa siguiente cuando el agente declara
  la etapa completa **y** el artefacto arranca (el backend levanta y responde el
  health-check / el cliente compila y renderiza login). Este smoke check **no** usa la
  suite de ATs.
- **Regla de no-exposición del holdout:** durante la corrida, el evaluador **no** ejecuta
  la suite de tests de aceptación ni adelanta al agente resultados de evaluación. La
  suite corre una sola vez por corrida, al cierre (H8). Motivo: usar el holdout como
  feedback durante la generación lo convierte en set de entrenamiento y sesga la métrica
  principal.
- Una etapa cerrada como **incompleta** (por presupuesto o estancamiento, sección 7) no
  bloquea las siguientes: se continúa con lo que exista, registrando el estado en el
  manifest (`notas`) y en el journal. Los ATs de lo faltante simplemente fallarán en H8.

## 5. Política de intervención humana

### 5.1 Definición

**Intervención** es toda acción del evaluador que altera el curso del pipeline más allá
de la operación mecánica del harness. Son intervenciones:

- (a) un prompt correctivo o aclaratorio al agente;
- (b) responder una pregunta que el agente formula;
- (c) editar manualmente código, configuración o archivos generados;
- (d) reiniciar/reintentar una etapa o sub-tarea;
- (e) cualquier decisión de configuración tomada a mitad de corrida.

**No** son intervenciones (no se registran como INT, aunque sí en notas si son
llamativas): aprobar prompts de permiso del harness sin modificar nada, esperar a que
termine una tarea, avanzar a la etapa siguiente cuando se cumplió el criterio de la
sección 4.

### 5.2 Disparadores — cuándo SÍ se interviene

Sólo ante un **bloqueo objetivo**, definido como cualquiera de:

- **D1.** El agente declara terminada una tarea/etapa pero el artefacto no compila, no
  arranca o falla el smoke check de la sección 4.
- **D2.** El agente queda detenido: espera input, entra en bucle (≥ 2 iteraciones
  consecutivas sin diff nuevo sobre el repo), o aborta con error del harness.
- **D3.** El agente se desvía del alcance de forma que impide continuar: ignora una
  épica completa, inventa alcance no pedido que reemplaza al pedido, o modifica la spec
  (la spec es inmutable: cualquier edición del agente sobre `spec/` se revierte y se
  registra).
- **D4.** El agente solicita explícitamente una decisión o aclaración.

### 5.3 Cuándo NO se interviene

- **Calidad subóptima que no bloquea** (código feo, duplicado, sin tests propios,
  decisiones de diseño discutibles): no se toca; lo capturan las métricas de H8.
- **Errores funcionales no bloqueantes** (un endpoint que devuelve un campo mal, un
  cálculo incorrecto): no se corrigen aunque el evaluador los note; los captura el
  holdout. Intervenir acá sería optimizar la celda a mano.
- **Anticipación:** no se interviene "porque se ve venir" un problema; sólo ante D1–D4
  consumados.

### 5.4 Contenido permitido de una intervención

Para no contaminar la comparación ni el holdout:

- La intervención **mínima suficiente** para desbloquear, en este orden de preferencia:
  (a) señalar el error observable (mensaje de compilación, stack trace); (b) señalar la
  sección/HU/RN de la spec pertinente; (c) instrucción correctiva concreta; (d) edición
  manual (último recurso; se registra el diff).
- **Prohibido:** citar o parafrasear escenarios de aceptación como "tests que van a
  correrse", revelar resultados de evaluación, aportar conocimiento de dominio que la
  celda no tiene (en particular, explicar contenido de BIPs/EIPs a una celda sin RAG:
  si el agente no lo sabe y la spec no lo fija, ese fallo **es un dato**, no un
  problema a resolver).
- Si el bloqueo proviene de una **ambigüedad o defecto real de la spec**, aplica la
  sección 8 (no se resuelve ad hoc para una sola celda).

### 5.5 Registro

Cada intervención se registra **en el momento** en `runs/<id>/intervenciones.md` según
`runs/plantillas/intervenciones.template.md`: timestamp, etapa/componente, categoría de
causa raíz, disparador (D1–D4), descripción, prompt textual usado, respuesta del agente,
referencias (AT/HU/INV/commit).

### 5.6 Clasificación por causa raíz (cascada determinista)

Las 8 categorías provienen del marco metodológico de la propuesta. Cada intervención
recibe **exactamente una** categoría, la **primera que aplique** recorriendo esta
cascada (de la más específica de dominio a la más genérica):

| Orden | Cat. | Se asigna si el defecto raíz…                                                                 |
|-------|------|------------------------------------------------------------------------------------------------|
| 1º    | 8    | involucra estándares on-chain: BIP-32/39/44, EIP-155, EIP-55, ERC-20 mal aplicados, inventados o desactualizados |
| 2º    | 7    | involucra lógica financiera o invariantes del matching: unidades, redondeo, fees, INV-1..8, prioridad precio-tiempo |
| 3º    | 6    | es de UI/UX: render, navegación, formularios, estados visuales (épicas 10–11)                    |
| 4º    | 5    | es un fallo de **integración entre componentes** (backend↔web↔mobile, contrato API mal consumido) |
| 5º    | 3    | es **pérdida de contexto**: el agente olvida/contradice decisiones o artefactos propios de etapas previas |
| 6º    | 4    | es una **alucinación general** (API/librería/archivo inexistente) no cubierta por 8              |
| 7º    | 2    | es código que **no compila o no funciona** sin causa más específica identificable                |
| 8º    | 1    | es una **mala interpretación de la especificación** (la spec fija X sin ambigüedad; el agente hizo Y) |

Regla de desempate adicional: se clasifica por la **causa raíz** diagnosticada, no por el
síntoma (un build roto porque el agente usó una librería inexistente es 4, no 2; un
cálculo de fee con floats es 7 aunque compile).

### 5.7 Estancamiento y abandono de etapa

- **Estancamiento:** 3 intervenciones consecutivas con la misma causa raíz sobre el
  mismo defecto sin progreso observable ⇒ se abandona ese defecto (se deja como está) y
  se registra en el log. No se insiste: el costo de insistir distorsiona la métrica de
  intervenciones.
- **Abandono de etapa:** si la etapa no alcanza el criterio de avance tras agotar el
  presupuesto proporcional (sección 6) o acumula 3 estancamientos, se cierra como
  incompleta y se continúa (sección 4).

## 6. Presupuestos por corrida

Valores **provisionales**; la corrida piloto los valida y los definitivos quedan
pinneados en el ADR de reemplazo (si cambian) y en el manifest de cada corrida oficial.

| Concepto            | Tope por corrida | Nota                                                        |
|---------------------|------------------|-------------------------------------------------------------|
| `costo_max_usd`     | 200 USD          | Tope operativo principal (API de ambos proveedores).        |
| `tiempo_max_horas`  | 24 h activas     | ~3 jornadas de sesión del evaluador, excluye esperas largas. |
| `tokens_max`        | — (sin tope)     | Se registra como métrica; el tope efectivo es el costo.      |

- Presupuesto proporcional orientativo por etapa: backend 60 % / web 25 % / mobile 15 %.
- Al agotarse un tope, la corrida se cierra en el estado en que esté (sección 4) y se
  registra el motivo del cierre en el manifest.

## 7. Orden y ventana de las corridas oficiales

- El **orden de ejecución** de las 4 celdas se sortea **una vez**, antes de la primera
  corrida oficial, y se registra en el journal (mitigación transparente del efecto
  aprendizaje del evaluador; con n=1 por celda no lo elimina — se discute como amenaza a
  la validez en el cap. 4).
- La piloto, además de debuggear protocolo/harness, funciona como **entrenamiento del
  evaluador** para amortiguar ese efecto.
- Ventana objetivo: ≤ 2 semanas entre la primera y la última corrida oficial.

## 8. Ambigüedades o defectos de la spec descubiertos mid-run

Si durante una corrida se descubre un defecto de la spec que **bloquea** (una HU
imposible de implementar como está escrita, una contradicción real):

1. Se registra la intervención (categoría según cascada; típicamente 1 con nota de
   "defecto de spec").
2. La decisión que desbloquea se documenta en el journal **y se aplica idéntica a las
   4 celdas** (a las ya corridas sólo si el defecto invalida su medición — peor caso que
   se evita con la piloto).
3. La spec taggeada **no se edita** durante la ventana de corridas; las correcciones se
   acumulan para un eventual `spec-v1.1` posterior al experimento.

## 9. Aislamiento y no-contaminación

- Los agentes de las corridas **sólo ven el repo satélite** (la spec). Nunca ven
  `journal/`, `runs/`, `analisis/`, `evaluacion/`, ni los repos de otras celdas
  (ADR-001).
- El evaluador no reutiliza prompts correctivos entre celdas salvo que el disparador sea
  idéntico; cuando lo sea, usa la misma redacción (paridad también en las
  intervenciones). El log de intervenciones de cada celda documenta el texto exacto.
- La suite de ATs (H5) se construye **antes** de la primera corrida y no se modifica
  después de vista ninguna implementación.

## 10. Qué se registra, dónde

| Qué                                    | Dónde                              | Cuándo                    |
|----------------------------------------|-------------------------------------|---------------------------|
| Configuración de la celda, insumos pinneados, presupuestos | `runs/<id>/manifest.yaml` §1–4 | Antes de iniciar          |
| Intervenciones (INT-NN)                | `runs/<id>/intervenciones.md`       | En el momento             |
| Cierre (timestamps, costo, tokens)     | `runs/<id>/manifest.yaml` §5        | Al cerrar la corrida      |
| Métricas de evaluación                 | `runs/<id>/metricas.md`             | En H8                     |
| Narrativa y observaciones              | `journal/AAAA-MM-DD-<id>.md`        | Al cierre de cada sesión  |
| Decisiones estructurales sobrevenidas  | ADR nuevo                           | Cuando ocurran            |
