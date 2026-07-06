# Detección y conteo de alucinaciones de dominio — procedimiento pre-registrado v1.0

- **Estado:** pre-registrado en H5, antes de la primera corrida. Sólo la corrida piloto
  (H6) puede motivar ajustes, con nueva versión de este documento antes de la primera
  corrida oficial (misma regla que `protocolo.md`).
- **Variable dependiente:** "alucinaciones de dominio" del diseño 2×2 (protocolo §1). Se
  mide **idéntico** en las 4 implementaciones oficiales (y en la piloto, como ensayo),
  sobre el repo satélite congelado y las trazas de la corrida.
- **Referencia normativa:** el corpus RAG congelado (`corpus/manifest.md`, 9 documentos en
  `corpus/documentos/`). Nótese la asimetría deliberada: el corpus es *input* sólo para las
  celdas `*-con-rag`, pero es *vara de verificación* para las 4 celdas.
- **Distinción con otras métricas:** esta métrica cuenta **afirmaciones de dominio falsas**
  (conocimiento declarado o aplicado sobre estándares), no fallos de comportamiento (los
  cuenta el holdout por AT-id) ni intervenciones (las cuenta `intervenciones.md`; la
  categoría 8 del protocolo §5.6 clasifica *causas de intervención*, no esta métrica).

## 1. Qué cuenta como alucinación de dominio

Una **alucinación de dominio** es una afirmación identificable —en código, comentarios,
documentación generada, mensajes/strings, nombres significativos o trazas del agente— que
atribuye al dominio on-chain/estándares un contenido **falso**, verificable contra la
referencia normativa. Categorías numeradas; cada alucinación recibe **exactamente una**,
la **primera que aplique** en esta cascada (de más específica a más general, mismo estilo
que protocolo §5.6):

| Orden | Cat. | Definición | Ejemplos |
|-------|------|------------|----------|
| 1º | **C1** | **Estándar inexistente**: se cita un BIP/EIP/ERC u otro estándar que no existe, o se lo invoca como fuente ("BIP-99 dice…"). | "según BIP-99", "ERC-2000 define el checksum" |
| 2º | **C2** | **Número incorrecto para el concepto**: el estándar citado existe, pero el concepto atribuido pertenece a otro. | "BIP-32 define la mnemonic de 12 palabras" (es BIP-39); "EIP-20 define el checksum de direcciones" (es EIP-55) |
| 3º | **C3** | **Wordlist BIP-39 inventada o incorrecta**: palabras presentadas como parte del wordlist inglés que no están entre las 2048, tamaño distinto de 2048, u ordenamiento/propiedades inventados. | wordlist "de 2000 palabras"; validar contra una lista con palabras inexistentes |
| 4º | **C4** | **Parámetro de red o de interfaz on-chain incorrecto afirmado como hecho del dominio**: chainId de Sepolia ≠ 11155111, red equivocada presentada como Sepolia, método JSON-RPC inexistente o con semántica inventada. | "Sepolia chainId 11155112"; "`eth_getDeposits` del nodo"; "logIndex es global a la cadena" |
| 5º | **C5** | **Constante, fórmula o estructura errónea de un estándar real**: derivation path mal formado presentado como BIP-44, `v` de EIP-155 distinto de `{0,1} + chainId × 2 + 35`, algoritmo EIP-55 mal descripto (p. ej. "SHA-256 del address"), URI EIP-681 con esquema/estructura incorrectos atribuidos al estándar, firma/selector ERC-20 inventado. | `m/44/60/0/0/0` "según BIP-44" (sin hardened); "v = chainId + 27 según EIP-155" |
| 6º | **C6** | **Contenido normativo inventado o incorrecto atribuido a un estándar real** (residual): cualquier otra afirmación falsa sobre lo que un estándar exige, permite o define. | "ERC-20 exige que `transfer` revierta ante saldo insuficiente"; "BIP-44 exige coin type 61 para testnets Ethereum" |

Notas de alcance:

- La afirmación puede estar **aplicada** (código que computa `v = chainId + 27` es una
  afirmación falsa sobre EIP-155 aunque no haya comentario) o **declarada** (comentario,
  doc, traza). En código sin mención explícita del estándar, cuenta sólo si la construcción
  es inequívocamente la implementación del estándar en cuestión (p. ej. un derivation path,
  el cálculo de `v`, el checksum de address); en caso de duda, no cuenta (ver §2).
- Las trazas del agente (logs de la corrida en `runs/<id>/`) cuentan igual que el código:
  una alucinación enunciada durante la generación es un dato aunque el código final no la
  contenga (se registra con ubicación en la traza).

## 2. Qué NO cuenta

1. **Bugs comunes de programación** sin contenido de dominio (off-by-one, null/undefined,
   condiciones de carrera, errores de tipado).
2. **Decisiones subóptimas** de diseño o implementación (arquitectura, performance, estilo).
3. **Errores funcionales cubiertos por ATs** en tanto comportamiento: un endpoint que
   devuelve mal un campo, un fee mal calculado, un estado que no transiciona — son fallos
   de AT, no alucinaciones, **salvo** que incluyan una afirmación de dominio falsa (§1).
4. **Alucinaciones generales de software** (API, librería, paquete o archivo inexistente):
   las captura la clasificación de intervenciones (protocolo §5.6, categoría 4). Inventar
   una librería `bip39-utils` no es alucinación *de dominio*; sí lo sería la afirmación
   falsa sobre BIP-39 que esa invocación traiga aparejada, si existe.
5. **Malas interpretaciones de la spec** sin referencia a estándares (la spec fija X, el
   agente hizo Y): son fallos de AT o intervenciones categoría 1.
6. **Afirmaciones correctas pero incompletas**, simplificaciones razonables explícitas, y
   decisiones que la spec misma fija aunque difieran del uso típico del estándar (p. ej.
   `TX_TYPE = legacy` está fijado por la spec; usarlo no es alucinación).
7. **Menciones no verificables** (§3, veredicto `NO_VERIFICABLE`): no suman al conteo.

### Regla explícita de doble conteo (fallo de AT ∧ alucinación)

**Un mismo hecho subyacente puede contarse a la vez como fallo de AT y como alucinación de
dominio; son variables dependientes distintas y ninguna descuenta a la otra.** El criterio
que decide si además del fallo hay alucinación es la existencia de una **afirmación de
dominio falsa identificable** (§1): 

- `v` de EIP-155 mal calculado que hace fallar ATs de la épica 08 **y** cuya fórmula
  errónea es rastreable en código/comentario/traza ⇒ **1 fallo (o más) en el holdout + 1
  alucinación**, con el cruce registrado (columna `refs` de la tabla, §3.4).
- Un fee mal redondeado que hace fallar un AT pero sin ninguna afirmación sobre estándares
  ⇒ sólo fallo de AT (regla 3 de §2: el redondeo lo fija la spec, no un BIP/EIP).

Lo que esta regla prohíbe es el doble conteo **dentro de la métrica de alucinaciones**
(ver unidad de conteo, §4), no el cruce entre métricas.

## 3. Procedimiento mecánico

Se ejecuta en H8, tras el cierre de cada corrida, sobre el repo satélite **congelado** y
las trazas registradas. El mismo procedimiento, en el mismo orden, para las 4 celdas.

### 3.1 Alcance del barrido

- Todo el repo satélite de la corrida: código fuente, comentarios, docs generados
  (README, `docs/`, ADRs del agente si los hubiera), strings/mensajes, configuración.
  Se excluyen `node_modules/`, vendor, lockfiles y binarios.
- El log/trazas de la corrida (`runs/<id>/`: transcript del agente, log de intervenciones
  — sólo las **respuestas del agente**, no los prompts del evaluador).

### 3.2 Extracción de candidatos (grep pinneado)

Se corre esta batería (case-insensitive) y se vuelca cada hit con `ruta:línea` y ±3 líneas
de contexto a una lista de candidatos:

```bash
# Menciones numeradas de estándares
grep -rniE --binary-files=without-match \
  --exclude-dir={node_modules,.git,vendor,dist,build} \
  -e '(bip|eip|erc)[-_ ]?[0-9]{1,4}' <repo> <trazas>

# Términos de dominio (revisión de contexto de cada hit)
grep -rniE --binary-files=without-match \
  --exclude-dir={node_modules,.git,vendor,dist,build} \
  -e 'mnemonic|seed phrase|wordlist|derivation|hardened|xprv|xpub' \
  -e "m/44|coin.?type|keccak|checksum|secp256k1" \
  -e 'chain.?id|11155111|sepolia|replay' \
  -e 'eth_[a-z]+|json.?rpc|logindex' <repo> <trazas>
```

La lista de candidatos es **determinista** (misma batería, mismo árbol congelado) y se
genera **una sola vez** por corrida; se archiva junto a la tabla (§3.4).

### 3.3 Verificación de cada candidato

Cada mención se revisa **manualmente contra el corpus congelado** `corpus/documentos/`
(BIP-32/39/44 + wordlist, EIP-155, ERC-20/55/681, JSON-RPC) como referencia normativa:

1. ¿La afirmación refiere a un estándar? Si no (uso trivial/correcto de un término), se
   descarta como candidato (no entra en la tabla o entra con veredicto `CORRECTO`).
2. **Existencia** (C1/C2): si el estándar citado no está en el corpus, la existencia y el
   título se verifican contra los repos oficiales (`bitcoin/bips`, `ethereum/EIPs`,
   `ethereum/ERCs`), registrando URL y fecha de consulta en la justificación.
3. **Contenido** (C3–C6): la vara es el texto del corpus (citar documento y sección/línea
   en la justificación). Si la afirmación versa sobre un estándar **fuera del corpus** y no
   es decidible con los repos oficiales en ≤ 10 minutos, veredicto `NO_VERIFICABLE` (no
   suma; queda registrada).
4. Veredicto por candidato: `ALUCINACION` (con categoría C1–C6 por cascada) /
   `CORRECTO` / `NO_VERIFICABLE`.

### 3.4 Registro

Una tabla por corrida en `runs/<id>/alucinaciones.md`, junto con la lista cruda de
candidatos. Columnas fijas:

| Campo | Contenido |
|-------|-----------|
| `id` | `ALU-<celda>-NN` (secuencial por corrida; p. ej. `ALU-a-con-rag-03`) |
| `celda` | `a-sin-rag` / `a-con-rag` / `b-sin-rag` / `b-con-rag` (o `piloto-01`) |
| `ubicacion` | `ruta:línea` en el repo satélite, o referencia a la traza (archivo + marca) — la primera ocurrencia; las demás se listan en `ocurrencias` |
| `cita` | Cita textual mínima que contiene la afirmación |
| `categoria` | C1–C6 (por cascada §1) — vacía si el veredicto no es `ALUCINACION` |
| `veredicto` | `ALUCINACION` / `CORRECTO` / `NO_VERIFICABLE` |
| `ocurrencias` | `n` = cantidad de menciones distintas del mismo hecho (con sus ubicaciones) |
| `justificacion` | Documento del corpus + sección/línea que decide, o URL+fecha si §3.3.2 |
| `refs` | Cruces: AT-id afectados, `INT-NN` si motivó intervención (regla §2) |

## 4. Unidad de conteo

- La unidad es el **hecho falso distinto** (la proposición falsa), no la mención: *n*
  menciones del mismo error —misma proposición en distintas ubicaciones, aunque cambie la
  redacción— son **1 alucinación con `ocurrencias = n`**.
- Dos afirmaciones falsas **diferentes** sobre el mismo estándar son 2 alucinaciones
  (p. ej. `v` mal calculado **y** path BIP-44 mal formado ⇒ 2).
- Criterio de identidad ante dudas: dos menciones son el mismo hecho si corregir una
  única proposición las vuelve verdaderas a ambas.
- **Métricas reportadas por celda:** total de alucinaciones (hechos distintos), desglose
  por categoría C1–C6, total de ocurrencias, y conteo de `NO_VERIFICABLE` (aparte).

## 5. Estabilidad: doble pasada del mismo evaluador

1. **Pasada 1** (H8, al cierre de la corrida): extracción de candidatos (§3.2, única) +
   clasificación completa (§3.3–3.4).
2. **Pasada 2**: el **mismo evaluador** (el tesista), **≥ 7 días** después de la pasada 1,
   re-clasifica **en ciego** la misma lista de candidatos (sin mirar los veredictos ni
   categorías de la pasada 1; se trabaja sobre una copia de la tabla con las columnas
   `categoria`/`veredicto`/`justificacion` vacías).
3. **Discrepancias:** se registran en una tabla al pie de `runs/<id>/alucinaciones.md`
   (`id`, veredicto/categoría de pasada 1, de pasada 2, resolución final, regla de este
   documento que la decide). La **resolución final** —releyendo la referencia normativa—
   es la que entra al análisis.
4. **Métrica de estabilidad reportada:** tasa de acuerdo intra-evaluador
   (`candidatos con mismo veredicto y categoría / total de candidatos`), por celda y
   global. Se discute en el capítulo de metodología como cota de confiabilidad de la
   medición (evaluador único, n=1 por celda).
5. Las dos pasadas de **todas** las celdas se completan antes de consolidar el dataset en
   `analisis/` (evita que el análisis agregue sesgo de resolución).
