# rubricas — instrumentos manuales de las épicas 10–11 y del rol `revisor`, y su archivado por corrida

Este directorio contiene los tres instrumentos de evaluación manual y su
procedimiento de archivado. Todos están **pre-registrados** (protocolo §9: no se
modifican después de vista ninguna implementación):

| Archivo             | Cubre                                                        | Pre-registrado en |
|---------------------|--------------------------------------------------------------|-------------------|
| `epica-10-web.md`   | 78 ATs de la épica 10 + `AT-10-E2E-01` (fuera del catálogo de 693, se reporta por separado) | H5 |
| `epica-11-mobile.md`| 94 ATs de la épica 11                                        | H5 |
| `rol-revisor.md`    | los 3 artefactos `.pipeline/revision-<etapa>.md` del rol `revisor` por celda: 12 criterios `RV-01`..`RV-12` por artefacto + censo de puntos | H6 |

`rol-revisor.md` es consecuencia del set de roles de
[ADR-009](../../decisiones/ADR-009-harnesses-como-cli-y-orquestador-de-roles.md)
Decisión 4 y cierra el ítem 12 de la checklist H6. A diferencia de las otras dos, no
mide la implementación sino el artefacto de revisión que el pipeline produce, y por eso
es el único instrumento que mide `.pipeline/`, excluido del cómputo de métricas
estáticas (checklist H6, ítem 18).

## Regla de inmutabilidad

Los tres archivos de este directorio son el **instrumento pre-registrado (v1.0)** y
**no se editan** — ni siquiera para volcar resultados. Los veredictos de una corrida se
completan sobre una **copia por corrida** (abajo). Cualquier corrección al instrumento
en sí requeriría re-pre-registro antes de ver implementación alguna; después de la
primera corrida, el instrumento queda fijo para todo el experimento. `rol-revisor.md`
tiene además una cláusula de re-pre-registro acotada a la piloto: si el set de roles o
el prompt del rol cambian ahí, la rúbrica se corrige y se vuelve a pre-registrar antes
de H7.

## Archivado por corrida (H8)

Por cada corrida evaluada:

1. **Copiar** los tres instrumentos intactos a `runs/<id>/rubricas/epica-10-web.md`,
   `runs/<id>/rubricas/epica-11-mobile.md` y `runs/<id>/rubricas/rol-revisor.md`.
2. **Completar** las columnas Resultado/Notas **en la copia**, siguiendo el
   procedimiento y el vocabulario de veredictos del propio instrumento
   (`PASA` / `FALLA` / `NO_EVALUABLE`; nota obligatoria en `FALLA` y
   `NO_EVALUABLE`). En `rol-revisor.md`, el censo de puntos se agrega a la copia como
   una tabla por etapa, una fila por punto.
3. **Exportar** los veredictos a `runs/<id>/resultados-rubricas.csv`,
   `runs/<id>/resultados-rubrica-revisor.csv` y `runs/<id>/censo-revision.csv`
   (esquemas abajo). Las copias completadas son la fuente primaria (auditable); los CSV
   son el formato máquina-legible que consume la consolidación en `analisis/dataset/`.

Orden dentro de una corrida: el censo y los veredictos de `rol-revisor.md` se completan
**antes** de abrir `runs/<id>/resultados-at.csv` de esa celda (ver su §Procedimiento
general).

## Esquema de `resultados-rubricas.csv`

Una fila por AT, en el **orden del documento** (HU ascendente; `AT-10-E2E-01`
al final de la épica 10): 78 + 1 filas de web y 94 de mobile, 173 en total.
Los nombres de columnas se alinean con los de `resultados-at.csv` de la suite
black-box (`evaluacion/suite-at/README.md`) donde aplican, para que la
consolidación del dataset sea mecánica:

| Columna             | Contenido                                                       |
|---------------------|------------------------------------------------------------------|
| `at_id`             | ID estable del criterio (p. ej. `AT-10-03-08b`, `AT-10-E2E-01`) |
| `resultado`         | `PASA` \| `FALLA` \| `NO_EVALUABLE` (vocabulario de la rúbrica) |
| `detalle`           | la Nota de la fila (obligatoria en `FALLA` y `NO_EVALUABLE`, con su causa a/b; opcional en `PASA`) |
| `fuera_de_catalogo` | `true` **sólo** para `AT-10-E2E-01`; `false` para los 172 ATs del catálogo |

## Esquema de `resultados-rubrica-revisor.csv`

Una fila por (etapa, criterio), en el orden del documento: 3 etapas × 12 criterios = 36
filas. `resultado` y `detalle` conservan los nombres de arriba para que la
consolidación sea mecánica:

| Columna     | Contenido                                                            |
|-------------|-----------------------------------------------------------------------|
| `etapa`     | `backend` \| `web` \| `mobile` (ids de `pipeline/comun/etapas.yaml`)  |
| `criterio`  | `RV-01`..`RV-12`                                                      |
| `resultado` | `PASA` \| `FALLA` \| `NO_EVALUABLE`                                   |
| `detalle`   | la Nota de la fila: obligatoria en `FALLA` (conteo y ordinales de los puntos infractores) y en `NO_EVALUABLE` (causa a/b); opcional en `PASA` |

## Esquema de `censo-revision.csv`

Una fila por punto de cada artefacto de revisión, en el orden del documento. La
cantidad de filas depende de la corrida. Los valores admitidos de cada campo son los de
la Parte A de `rol-revisor.md`:

| Columna        | Contenido                                                                 |
|----------------|----------------------------------------------------------------------------|
| `etapa`        | `backend` \| `web` \| `mobile`                                             |
| `punto`        | ordinal del punto en su artefacto (`1..n`)                                 |
| `eje`          | `COMPLETITUD` \| `CORRECCION` \| `INVARIANTES` \| `OPERABILIDAD` \| `OTRO` |
| `severidad`    | `BLOQUEANTE` \| `MAYOR` \| `MENOR`                                         |
| `ancla`        | `SPEC` \| `EJECUCION` \| `NINGUNA`                                         |
| `referencias`  | ids citados por el punto, separados por `;`, sea cual sea el valor de `ancla` (vacío si no cita ninguno); habilita el cruce mecánico con `resultados-at.csv` |
| `ubicacion`    | `ARCHIVO_LINEA` \| `ARCHIVO` \| `NINGUNA`                                  |
| `accionable`   | `SI` \| `NO`                                                               |
| `veracidad`    | `VERDADERO` \| `FALSO` \| `NO_VERIFICABLE`                                 |
| `destino`      | `RESUELTO` \| `NO_RESUELTO` \| `RECHAZADO_CON_CONSTANCIA` \| `NO_VERIFICABLE` |
| `evidencia`    | cita del punto + archivo:línea o comando + salida que sostiene `veracidad` y `destino` (obligatoria: un campo sin evidencia es inválido) |

## Registro en el protocolo

Este procedimiento extiende la tabla §10 del protocolo ("qué se registra,
dónde"). El ajuste formal de `evaluacion/protocolo.md` (nueva versión del
documento + ADR que reemplace a ADR-004) queda para la **ventana H6**; hasta
entonces, este README y el journal de la sesión correspondiente son el registro
del procedimiento.
