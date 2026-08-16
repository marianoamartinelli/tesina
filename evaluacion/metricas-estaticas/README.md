# Métricas estáticas — criterios pre-registrados v1.0

- **Estado:** pre-registrado en H5, antes de la primera corrida. Sólo la piloto (H6) puede
  motivar ajustes, versionados antes de la primera corrida oficial (misma regla que
  `evaluacion/protocolo.md`).
- **Variable dependiente:** "métricas estáticas" del diseño 2×2 (protocolo §1). El backend
  es agnóstico de lenguaje, así que las 4 implementaciones pueden estar en lenguajes
  distintos: **todos los criterios se fijan acá, antes de mirar cualquier resultado**, para
  que la comparación sea legítima.
- **Cuándo y sobre qué:** en H8, sobre el repo satélite **congelado** de cada corrida, por
  **componente**: `backend`, `cliente-web`, `cliente-mobile` (más una fila `total` con el
  repo completo). Salida: `runs/<id>/metricas-estaticas.csv`.

## 1. Métricas y herramientas (pinneadas)

| Métrica | Definición operativa | Herramienta (versión pinneada) |
|---------|----------------------|--------------------------------|
| **LOC efectivas** | Líneas de código sin blancos ni comentarios (`SUM.code` de cloc), excluyendo directorios generados (§1.1). Se registran también `archivos` y `lenguaje_principal` (el de mayor `code`). | **cloc v2.10** |
| **Complejidad ciclomática (CCN)** | Por función, según la definición de lizard (CCN clásico). Se reportan **promedio** y **p90** sobre todas las funciones del componente, más el total de `funciones`. Percentil: **nearest-rank** (`p90 = valor en la posición ⌈0.9·n⌉` de la lista ordenada). | **lizard 1.23.0** (pip) |
| **Duplicación** | Porcentaje de líneas duplicadas (`statistics.total.percentage` del reporte JSON), con los parámetros por defecto de la herramienta (min-tokens 50). | **jscpd 5.0.11** (npm) |
| **Dependencias directas** | Conteo de dependencias **declaradas de primer nivel** en el manifiesto del ecosistema, separando producción y desarrollo (§1.2). No cuenta transitivas. | manifiesto del ecosistema + `medir.sh` |
| **Cobertura de tests propios** | % de líneas cubiertas por los tests **que el agente generó**, medida con el runner nativo del ecosistema (§5). **Nunca** con la suite holdout. `NA` si el agente no dejó tests o no ejecutan. | runner nativo (se registra cuál y su versión en `notas`) |

### 1.1 Exclusiones de conteo (idénticas para las 4 celdas)

Directorios excluidos en cloc/lizard/jscpd: `node_modules`, `.git`, `dist`, `build`,
`out`, `coverage`, `vendor`, `Pods`, `__pycache__`, `.next`, `.expo`, `target`,
`generated`, **`.pipeline`**. Los lockfiles y archivos binarios quedan fuera (cloc los
ignora; jscpd/lizard sólo procesan fuentes). Los **tests propios del agente sí cuentan**
en LOC/CCN/duplicación (son código generado; se anota en `notas` si su ubicación es
separable).

`.pipeline/` se excluye por ADR-009 Decisión 4: contiene los artefactos de handoff entre
roles (p. ej. `revision-<etapa>.md`), que son mecánica del orquestador y no producto
generado. La regla se fija **antes** de la piloto y de ver implementación alguna, por el
mismo criterio de congelamiento del protocolo §9 que gobierna la suite de ATs; queda
pendiente reflejarla en el código de `medir.sh` (checklist H6, ítem 18).

### 1.2 Dependencias directas por ecosistema (mapeo fijado antes de medir)

| Ecosistema | Producción | Desarrollo |
|------------|------------|------------|
| Node (`package.json`) | `dependencies` | `devDependencies` |
| Python (`requirements.txt`) | líneas no vacías/no comentario/no `-r` | `requirements-dev.txt` si existe |
| Python (`pyproject.toml`) | `[project].dependencies` | `[project.optional-dependencies]` + grupos dev de poetry |
| Go (`go.mod`) | `require` sin `// indirect` | — (no distingue; se anota) |
| Rust (`Cargo.toml`) | `[dependencies]` | `[dev-dependencies]` |
| Java (`pom.xml` / `build.gradle`) | `dependencies` sin scope `test` | scope `test` |

Si un componente tiene varios manifiestos (workspaces), se **suman** los que pertenecen al
componente. Ecosistema no listado ⇒ se agrega su mapeo a esta tabla **antes** de mirar el
número, en una nueva versión de este documento.

## 2. Regla de equivalencia entre lenguajes

1. **Default:** se usan las mismas herramientas multi-lenguaje en las 4 celdas — cloc,
   lizard y jscpd soportan los lenguajes plausibles del experimento (JS/TS, Python, Go,
   Java, Kotlin, Swift, Rust, C#…). Misma herramienta + misma versión + mismas exclusiones
   ⇒ números comparables.
2. **Excepción:** si el agente eligió un lenguaje que lizard/jscpd/cloc no soporta, se
   selecciona una herramienta sustituta que implemente la **misma definición** (CCN
   clásico por función; % de líneas duplicadas por tokens; LOC sin blancos/comentarios) y
   el mapeo `lenguaje → herramienta sustituta (versión) → equivalencia de definición` se
   documenta en este README **antes de mirar cualquier resultado** de esa celda, en una
   nueva versión del documento. La celda queda marcada en `notas` del CSV.
3. Los parámetros no-default de cualquier herramienta están **prohibidos** salvo que se
   pre-registren acá (hoy: ninguno; jscpd corre con defaults, lizard con defaults, cloc
   con las exclusiones de §1.1).

## 3. Qué queda fuera (y por qué)

- **Linting específico de framework/lenguaje** (ESLint, pylint score, clippy, detekt): las
  reglas activas dependen de la configuración que cada agente haya (o no) generado y de
  los defaults de cada ecosistema ⇒ no comparable entre celdas; además mezcla estilo con
  defectos.
- **Métricas estéticas** (formato, naming, largo de línea, orden de imports): sin relación
  defendible con las hipótesis y dependientes de convenciones por lenguaje.
- **Índices compuestos de mantenibilidad** (MI y similares): cada herramienta los define
  distinto; no hay equivalencia inter-lenguaje defendible.
- **Métricas dinámicas** (performance, memoria): no son estáticas; fuera del alcance.
- **Análisis de seguridad estático** (SAST): fuera del alcance de la propuesta.
- **Conteo de dependencias transitivas:** depende del resolutor/lockfile de cada
  ecosistema más que de decisiones del agente.

## 4. Formato de salida: `metricas-estaticas.csv`

Un CSV por corrida en `runs/<id>/metricas-estaticas.csv`, **una fila por componente**
(`backend`, `cliente-web`, `cliente-mobile`, `total`), generado por `medir.sh`. Columnas
fijas (orden exacto):

```
run_id,componente,fecha,lenguaje_principal,archivos,loc_efectivas,funciones,
ccn_promedio,ccn_p90,duplicacion_pct,deps_directas_prod,deps_directas_dev,
cobertura_tests_propios_pct,cloc_version,lizard_version,jscpd_version,notas
```

- Valores numéricos sin separador de miles; decimales con punto (2 decimales para
  `ccn_promedio`, `duplicacion_pct` y `cobertura_tests_propios_pct`).
- `NA` cuando la métrica no aplica o la herramienta no produjo dato (con explicación en
  `notas`).
- `notas` sin comas (usar `;`), o entre comillas dobles.

## 5. Cobertura de tests propios (procedimiento manual)

1. Detectar si el agente dejó tests y runner configurado (p. ej. script `test` en
   `package.json`, `pytest.ini`, `go test`). Si no hay tests ⇒ `NA` + nota `sin tests`.
2. Ejecutar la cobertura con el runner **nativo** y flags estándar de cobertura de línea:
   `npx jest --coverage` / `npx vitest run --coverage` / `pytest --cov=<pkg>` /
   `go test ./... -cover` (según el ecosistema; registrar comando y versión en `notas`).
3. Registrar el **% de líneas** (line coverage) global del componente. Si los tests no
   ejecutan (rotos), registrar `NA` + nota `tests no ejecutan`. No se arreglan: el repo
   está congelado.
4. Prohibido incluir la suite holdout o cualquier test del evaluador en esta medición.

## 6. Instalación (versiones pinneadas)

```bash
# cloc v2.10  — https://github.com/AlDanial/cloc
brew install cloc            # macOS; verificar: cloc --version == 2.10
# (alternativa exacta: descargar el release v2.10 del repo de GitHub)

# lizard 1.23.0 — https://github.com/terryyin/lizard
pip3 install lizard==1.23.0

# jscpd 5.0.11 — https://github.com/kucherenko/jscpd
npm install -g jscpd@5.0.11

# dependencias del script: jq, python3 (parseo de manifiestos), awk/sort (POSIX)
brew install jq
```

`medir.sh` verifica las versiones al arrancar y **aborta si difieren** de las pinneadas
(override consciente: variable `PERMITIR_VERSIONES=1`, que queda registrada en `notas`).

## 7. Uso

```bash
# una vez por componente, apuntando al subárbol correspondiente del repo satélite:
./medir.sh <ruta_componente> <run_id> <componente> [csv_salida]

# ejemplo (corrida a-con-rag):
./medir.sh ~/runs/tesina-run-a-con-rag/backend  a-con-rag backend        ../../runs/a-con-rag/metricas-estaticas.csv
./medir.sh ~/runs/tesina-run-a-con-rag/web      a-con-rag cliente-web    ../../runs/a-con-rag/metricas-estaticas.csv
./medir.sh ~/runs/tesina-run-a-con-rag/mobile   a-con-rag cliente-mobile ../../runs/a-con-rag/metricas-estaticas.csv
./medir.sh ~/runs/tesina-run-a-con-rag          a-con-rag total          ../../runs/a-con-rag/metricas-estaticas.csv
```

La partición del repo en componentes la decide la estructura que haya generado el agente;
la asignación de rutas → componentes se anota en `runs/<id>/metricas.md` antes de correr
el script. La columna `cobertura_tests_propios_pct` se completa a mano (§5) editando el
CSV después de correr el script.
