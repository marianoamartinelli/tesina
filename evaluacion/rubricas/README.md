# rubricas — instrumentos manuales de las épicas 10–11 y su archivado por corrida

Este directorio contiene los dos instrumentos de evaluación manual,
**pre-registrados en H5** (protocolo §9: no se modifican después de vista
ninguna implementación):

| Archivo             | Cubre                                                        |
|---------------------|--------------------------------------------------------------|
| `epica-10-web.md`   | 78 ATs de la épica 10 + `AT-10-E2E-01` (fuera del catálogo de 693, se reporta por separado) |
| `epica-11-mobile.md`| 94 ATs de la épica 11                                        |

## Regla de inmutabilidad

Los dos archivos de este directorio son el **instrumento pre-registrado
(v1.0)** y **no se editan** — ni siquiera para volcar resultados. Los
veredictos de una corrida se completan sobre una **copia por corrida** (abajo).
Cualquier corrección al instrumento en sí requeriría re-pre-registro antes de
ver implementación alguna; después de la primera corrida, el instrumento queda
fijo para todo el experimento.

## Archivado por corrida (H8)

Por cada corrida evaluada:

1. **Copiar** los dos instrumentos intactos a `runs/<id>/rubricas/epica-10-web.md`
   y `runs/<id>/rubricas/epica-11-mobile.md`.
2. **Completar** las columnas Resultado/Notas **en la copia**, siguiendo el
   procedimiento y el vocabulario de veredictos del propio instrumento
   (`PASA` / `FALLA` / `NO_EVALUABLE`; nota obligatoria en `FALLA` y
   `NO_EVALUABLE`).
3. **Exportar** los veredictos a `runs/<id>/resultados-rubricas.csv` (esquema
   abajo). La copia completada es la fuente primaria (auditable); el CSV es el
   formato máquina-legible que consume la consolidación en `analisis/dataset/`.

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

## Registro en el protocolo

Este procedimiento extiende la tabla §10 del protocolo ("qué se registra,
dónde"). El ajuste formal de `evaluacion/protocolo.md` (nueva versión del
documento + ADR que reemplace a ADR-004) queda para la **ventana H6**; hasta
entonces, este README y el journal de la sesión correspondiente son el registro
del procedimiento.
