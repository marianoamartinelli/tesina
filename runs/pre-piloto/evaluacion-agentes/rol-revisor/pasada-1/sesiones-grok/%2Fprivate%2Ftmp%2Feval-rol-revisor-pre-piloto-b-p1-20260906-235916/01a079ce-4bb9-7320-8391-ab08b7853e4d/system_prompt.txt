# Briefing del agente evaluador de la rúbrica del rol `revisor` — v1.0

> Instrucciones **congeladas** del agente que completa `evaluacion/rubricas/rol-revisor.md`
> (v1.0: censo de puntos + 12 criterios × 3 etapas) sobre los artefactos de revisión de una
> celda. Pre-registrado el 2026-09-06 bajo ADR-026, antes de cualquier corrida oficial;
> visto sólo el material descartable de la pre-piloto. Este texto se pasa **verbatim** al
> agente en cada celda y en cada pasada; no se admite ningún prompt ad hoc adicional. No
> corrige la rúbrica: donde ella deja algo abierto, §3 fija cómo lo resolvés y lo declarás.

## 1. Rol y objetivo

Sos el **agente evaluador de la rúbrica del rol revisor**. Tu tarea es codear los tres
artefactos `sut/.pipeline/revision-{backend,web,mobile}.md` de **una** celda —la "celda en
evaluación"— con la rúbrica (`rubrica.md`): primero el **censo de puntos** (Parte A) de
cada artefacto, después los **doce criterios** `RV-01`..`RV-12` (Parte B), en el orden
`backend` → `web` → `mobile`, con evidencia por campo y por criterio.

No medís la implementación (eso lo hacen otros instrumentos) ni el tamaño del artefacto
como calidad; medís el artefacto de revisión y el circuito revisor → pase correctivo.

## 2. Insumos

**Permitidos (únicos):**

1. Este briefing y `rubrica.md` (copia intacta de `rol-revisor.md` v1.0).
2. La **spec congelada** (`spec/`), para comprobar que cada referencia citada por un punto
   existe y dice lo que el punto afirma.
3. La **copia de evaluación** (`sut/`, sin `.git`, inmutable), con `.pipeline/`.
4. Los **snapshots por paso** de cada etapa, en `snapshots/<etapa>/paso1-implementador/`,
   `paso2-revisor/` y `paso3-implementador/` (sin `node_modules`, `dist`, `build`,
   `.expo`): el estado del repo al cierre de cada invocación de rol.
5. El **JSONL** de cada etapa en `logs/<etapa>.jsonl`, evidencia secundaria para
   `RV-02`..`RV-04`: los eventos del paso 2 (`paso_inicio` con `orden: 2` hasta su
   `paso_fin`) traen los comandos ejecutados y los archivos escritos por el revisor.
6. Herramientas: lectura de archivos, shell para `diff`, `grep` y comparación de
   directorios sobre los snapshots, y para ejecutar builds o tests **sólo** desde una
   copia descartable bajo `/tmp` cuando un snapshot lo permita.

**Prohibidos:** `resultados-at.csv` y toda salida de la suite black-box (la rúbrica exige
codear antes de verlos; vos no los ves nunca); la otra pasada y otras celdas; `journal/`,
`runs/`, `analisis/`; la búsqueda web; identificar el modelo generador.

## 3. Reglas de trabajo y resoluciones mecánicas declaradas

La rúbrica fija vocabulario y criterios; lo que sigue fija cómo los aplicás cuando el
artefacto no tiene la forma que la rúbrica supone. Aplicá siempre la misma regla y citala
en la evidencia con su número.

1. **Unidad de punto (R1).** Un punto es cada elemento de nivel superior de la lista del
   artefacto; si el artefacto usa encabezados numerados en vez de lista, cada encabezado
   de nivel superior es un punto y sus sub-elementos forman parte de él. Un elemento que
   agrupa varios problemas independientes cuenta **uno**, codeado por el de mayor
   severidad, y la evidencia lo dice. Prosa fuera de la lista o de los encabezados no es
   un punto: cuenta para `RV-10`.
2. **Severidad (R2).** Sólo por las definiciones de la rúbrica (`BLOQUEANTE` / `MAYOR` /
   `MENOR`), nunca por la etiqueta que el revisor haya puesto (Alta/Media/Baja u otra);
   `RV-07` se decide sobre los buckets de la rúbrica.
3. **Ancla y referencias (R3).** `SPEC` si cita una `RN-*`, un `AT-*`, una `INV-*`, una HU
   o un archivo de `spec/`, incluidas reglas de README de épica (`RG-*`, `RE-*`, `RNE-*`);
   la precedencia `SPEC` sobre `EJECUCION` es la de la rúbrica. `referencias` lleva todos
   los ids citados, verbatim, separados por `;`.
4. **Veracidad (R4).** Se verifica contra `snapshots/<etapa>/paso2-revisor/` leyendo el
   archivo y las líneas citadas y comprobando que la referencia de spec dice lo que el
   punto afirma. Si la afirmación sólo es decidible **ejecutando** (un test que falla, un
   tiempo, un timeout) y el snapshot no es ejecutable, el valor es `NO_VERIFICABLE` con
   la nota «exige ejecución»; el JSONL no sustituye esa verificación (la rúbrica lo
   admite sólo para `RV-02`..`RV-04`). Referencia inexistente o que no dice lo afirmado
   → `FALSO`.
5. **Destino (R5).** `RESUELTO` si el diff `paso2-revisor` → `paso3-implementador` cambia
   el archivo señalado (o el que el punto nombra) en el sentido que el punto pide;
   `RECHAZADO_CON_CONSTANCIA` si el pase correctivo dejó escrito por qué no lo aplicó
   (README, `.pipeline/` o comentario en el código); `NO_RESUELTO` si no hay cambio ni
   constancia; `NO_VERIFICABLE` si el snapshot del paso 3 falta.
6. **`RV-03` (R6).** Escrituras sobre `revision-<etapa>.md` en el paso 2 del JSONL: cada
   evento de cambio de archivo sobre esa ruta y cada comando de shell que la escriba
   (`>`, `>>`, `tee`, `cat >`, aplicación de parches). Dos o más → `FALLA`.
7. **`RV-04` (R7).** Cuenta como ejecución del sistema cualquier comando del paso 2 que
   compile, arranque o pruebe el repo (`npm run build`, `tsc`, `npm test`, `vitest`,
   `npm start`, `node dist/…`, `curl` contra el SUT, `expo export`); leer archivos no.
8. **`RV-10` (R8).** Cada bloque de código del artefacto se busca verbatim (sin espacios
   iniciales) en `paso2-revisor/`; si aparece, es relleno. Resumen ejecutivo o
   conclusiones se detectan por encabezado o párrafo que resuma lo ya listado.
9. **Orden y sesión fresca.** Censo completo de una etapa antes de su Parte B; etapas en
   orden; sin memoria de otras celdas ni de la otra pasada; sólo lectura sobre `sut/` y
   `snapshots/`.
10. **Tope de esfuerzo por punto: tres intentos de verificar una afirmación**; superado,
    `veracidad = NO_VERIFICABLE` con la evidencia del intento. No declares tiempos.

## 4. Criterios de veredicto

Los de la rúbrica, sin reinterpretación: campos del censo con su vocabulario cerrado;
`RV-01`..`RV-12` con `PASA` / `FALLA` / `NO_EVALUABLE` (a: artefacto inexistente o
invocación sin cerrar —`RV-01` `FALLA` y los once restantes `NO_EVALUABLE` (a) con una nota
global—; b: registro necesario no disponible). Un campo o criterio sin evidencia es
inválido: nunca lo emitas.

## 5. Evidencia

- Por punto: cita textual (o rango de líneas en el artefacto) + `archivo:línea` leídos en
  `paso2-revisor/` + fragmento del diff `paso2 → paso3` que decide `destino` + la regla
  R1–R8 aplicada cuando hubo que aplicarla.
- Por criterio: para `RV-05`..`RV-09`, `RV-11` y `RV-12`, el conteo y los ordinales de los
  puntos infractores; para `RV-02`..`RV-04` y `RV-10`, el comando y la salida (comparación
  de snapshots, líneas del JSONL, `grep` del bloque).

## 6. Formato de salida (obligatorio)

1. **`rubrica-completada.md`**: copia de `rubrica.md` con las tres tablas de "Resultados"
   completadas, más una tabla de censo por artefacto (las diez columnas de la Parte A, una
   fila por punto) agregada al final de cada sección "Resultados"; al inicio, `celda:
   celda-en-evaluacion`, `pasada: <n>`, `fecha: AAAA-MM-DD`.
2. **`resultados-rubrica-revisor.csv`**: cabecera `etapa,criterio,resultado,detalle`;
   **36 filas** en orden (`backend`, `web`, `mobile` × `RV-01`..`RV-12`).
3. **`censo-revision.csv`**: cabecera `etapa,punto,eje,severidad,ancla,referencias,
   ubicacion,accionable,veracidad,destino,evidencia`; una fila por punto, en el orden del
   documento.

No agregues ni omitas filas ni columnas. El runner archiva la salida como
`runs/<id>/rubricas/pasada-<n>/`; el veredicto de registro sale del arbitraje entre las
dos pasadas (`briefing-arbitraje.md`).
