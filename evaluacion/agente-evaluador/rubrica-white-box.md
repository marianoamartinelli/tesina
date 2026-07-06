# Rúbrica white-box — 66 ATs no automatizables (v1.0)

> Checklist operativo del agente evaluador (ADR-007). Cubre **exactamente** los 66
> at_id declarados en `evaluacion/suite-at/no-automatizables.yaml` — ni uno más, ni
> uno menos — agrupados por épica y en **orden ascendente de at_id**. Cada entrada es
> autosuficiente: propiedad, pasos, evidencia mínima y criterio cerrado de veredicto.
> Los veredictos y su formato de salida los fija `briefing.md` (se lee primero).

## Precondiciones comunes (verificar antes del primer AT)

1. **Entorno on-chain levantado** según `evaluacion/suite-at/entorno/README.md`:

   ```bash
   cd evaluacion/suite-at/entorno
   docker compose up -d --wait          # anvil en :8545, chainId 11155111
   python desplegar-usdc.py             # despliega el USDC-mock
   source entorno.env                   # EVAL_RPC_URL, EVAL_USDC_ADDRESS, EVAL_USDC_DEPLOY_BLOCK
   ```

2. **SUT corriendo con la configuración de evaluación** (contrato de arranque del
   entorno: RPC `http://127.0.0.1:8545`, dirección del USDC-mock, bloque de inicio del
   indexador = `EVAL_USDC_DEPLOY_BLOCK`; los demás parámetros en sus defaults de spec:
   `CONFIRMACIONES_REQUERIDAS = 12`, TTL de token 3600 s, gas fijo 20 gwei, etc.).
   El comando de arranque/parada es el que documenta la **entrega operativa** del SUT.

3. **Variables definidas:**

   | Variable                 | Uso                                                                  |
   |--------------------------|----------------------------------------------------------------------|
   | `EXCHANGE_API_URL`       | URL raíz del SUT (sin `/api/v1`); las rutas de esta rúbrica son relativas a `/api/v1` |
   | `EXCHANGE_WS_URL`        | endpoint WebSocket (`ws://host/api/v1/ws`)                           |
   | `EVAL_RPC_URL`           | nodo anvil (`http://127.0.0.1:8545`)                                 |
   | `EVAL_USDC_ADDRESS`      | dirección del USDC-mock desplegado                                   |
   | `EVAL_USDC_DEPLOY_BLOCK` | bloque de despliegue del mock (bloque de inicio del indexador)       |
   | `SUITE_CMD_REINICIO_SUT` | comando que **termina abruptamente** el proceso del SUT (equivalente `kill -9`) y lo vuelve a levantar |
   | `COPIA_EVAL`             | ruta de la **copia de evaluación** del repo de la celda (sólo lectura, sin `.git`) |

4. **Copia de evaluación preparada sin `.git`** (la prepara el humano; verificá que no
   exista `.git` y, si falta la copia, prepararla con exactamente este comando):

   ```bash
   rsync -a --exclude='.git' --exclude='.gitmodules' --exclude='.gitattributes' \
       /ruta/al/repo-de-la-celda/ "$COPIA_EVAL"/
   test ! -e "$COPIA_EVAL/.git" || echo "ERROR: la copia contiene .git"
   ```

5. **Copia descartable para ejecuciones/instrumentación** (toda ejecución, edición o
   instancia alternativa del SUT ocurre acá, nunca en `$COPIA_EVAL`):

   ```bash
   export COPIA_TMP=/tmp/eval-wb/sut
   mkdir -p "$COPIA_TMP" && rsync -a "$COPIA_EVAL"/ "$COPIA_TMP"/
   ```

6. **Antes de la épica 08:** fondear la hot wallet del SUT (dirección emisora, tomada
   de su documentación/log de arranque):
   `python evaluacion/suite-at/entorno/fondear.py 0x<emisora> --eth 100 --usdc 1000000`.

### Constantes de mnemonics de esta rúbrica

| Constante                        | Valor                                                                                 | Origen |
|----------------------------------|---------------------------------------------------------------------------------------|--------|
| `MNEMONIC_BIP39_CANONICO`        | `"abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"` (12 palabras, checksum válido) | HU-06-01 §Vector de prueba canónico |
| `MNEMONIC_HARDHAT`               | `"test test test test test test test test test test test junk"` (12 palabras)          | HU-06-02 §Vectores de prueba canónicos |
| `MNEMONIC_24_VALIDO`             | `"abandon"` ×23 + `"art"` (24 palabras; mnemonic de la entropía `0x00`×32)              | derivable del algoritmo de `corpus/documentos/bip-0039.mediawiki` §"Generating the mnemonic"; verificarlo con un script en `$COPIA_TMP` antes de usarlo (checksum = primeros 8 bits de `SHA-256(entropía)`) |
| `MNEMONIC_24_CHECKSUM_INVALIDO`  | `"abandon"` ×24 (24 palabras del wordlist, checksum inválido por construcción)          | variante de la fila anterior (la última palabra correcta es `art`) |
| `MNEMONIC_24_PALABRA_INVALIDA`   | `"abandon"` ×23 + `"xyzzy"` (24 palabras, la última fuera del wordlist)                 | verificar con `grep -cx xyzzy corpus/documentos/bip-0039-wordlist-english.txt` → `0` |

## Familias de procedimiento

Cada entrada declara **una** familia primaria; F6 sólo aparece como evidencia
complementaria o sustituta cuando la entrada lo indica.

### F1 — Inspección de propiedad interna (código y/o estado persistido)

1. **Localizar por conceptos, no por rutas** (el stack es desconocido): `grep -rni`
   sobre `$COPIA_EVAL` con los términos de dominio que la entrada lista (nombres de la
   spec: tipos de asiento, códigos de error, constantes numéricas). Excluir
   directorios de dependencias (`node_modules`, `vendor`, `.venv`, `target`, `dist`)
   al buscar código propio; **incluirlos** sólo cuando la entrada pide verificar una
   librería delegada.
2. Leer el/los archivos hallados completos alrededor del hallazgo (no sólo la línea) y
   seguir las llamadas hasta poder afirmar o negar la propiedad.
3. Si la entrada lo indica, complementar con **estado persistido interno**: conducir el
   SUT vivo por REST/RPC para producir el estado y leer su almacenamiento (BD/archivos,
   documentados en su entrega operativa) **en modo sólo lectura**.
4. Búsqueda exhaustiva antes de declarar ausencia: todos los términos de la entrada,
   más sinónimos evidentes del propio código (p. ej. si el ledger se llama `journal`).
   Ausencia documentada ⇒ `FALLA`; incapacidad de decidir ⇒
   `NO_EVALUABLE:FUNCION_NO_LOCALIZABLE`.

### F2 — Criptografía / known-answer tests (KAT) contra funciones internas

1. Localizar la función interna objetivo (F1.1) y escribir un **driver mínimo** en
   `$COPIA_TMP` (en el lenguaje del SUT) que la invoque con el vector prescripto.
2. Ejecutarlo con el toolchain del SUT (instalar dependencias en `$COPIA_TMP` si hace
   falta) y comparar la salida **exactamente** (igualdad de strings/bytes) contra el
   valor esperado fijado por la spec, contrastado con el documento del corpus citado.
3. Alternativa equivalente: si el SUT trae ese mismo KAT en sus tests propios,
   aplicar F6 (revisar el vector y ejecutarlo).
4. **Regla dura:** un KAT exige ejecución; la sola lectura de código no habilita
   `PASA`. Si el toolchain no puede ejecutarse tras 3 intentos ⇒
   `NO_EVALUABLE:HERRAMIENTA_FALTANTE` (con los errores como evidencia).

### F3 — Ciclo de vida del SUT (reinicio orquestado)

1. Construir el "Dado" contra el SUT **principal** vivo, vía REST (`curl`) y RPC del
   anvil (depósitos: transferir a la dirección de depósito + `anvil_mine` 12 bloques;
   esperar la acreditación por polling de la API).
2. Registrar el estado observable ANTES (respuestas REST relevantes y, si la entrada lo
   pide, estado persistido interno).
3. Ejecutar `eval "$SUITE_CMD_REINICIO_SUT"` (terminación abrupta + relevantamiento) y
   esperar readiness (polling a un endpoint público hasta respuesta).
4. Registrar el estado DESPUÉS y comparar campo a campo con igualdad estricta.
5. Un mismo reinicio puede servir a varios ATs contiguos si todos los "Dado" se
   construyeron antes (declararlo en la evidencia de cada AT).
6. Si el SUT no vuelve a estar operativo ⇒ `NO_EVALUABLE:SUT_NO_ARRANCA` para los ATs
   afectados (con log), y se continúa con el resto usando un arranque limpio si es
   posible.

### F4 — Inyección de fallo interno (atomicidad / límites transaccionales)

1. **Criterio primario: inspección de límites transaccionales** (variante de F1):
   localizar la operación multi-paso y verificar que **todas** sus escrituras están
   dentro de **una única unidad atómica** (transacción de BD —`BEGIN/COMMIT`, API
   transaccional del ORM, `withTransaction`—, o escritura atómica equivalente:
   `fsync` + `rename`, WAL) con rollback ante error, **sin escrituras persistentes
   fuera de esa unidad** (buscar: `transaction`, `BEGIN`, `commit`, `rollback`,
   `atomic`, `withTransaction`, `serializable`).
2. **Refuerzo opcional** (si el criterio primario deja duda y el presupuesto alcanza):
   instrumentar en `$COPIA_TMP` (inyectar una excepción tras el N-ésimo paso, editando
   la copia) y ejecutar la operación con un driver o los tests del SUT; verificar
   rollback total. Declarar exactamente qué se editó.
3. Estado en memoria sin persistencia no exime: la propiedad se evalúa sobre lo que la
   implementación persiste; si no hay mecanismo identificable de todo-o-nada para la
   operación ⇒ `FALLA`.

### F5 — Config-fault (arrancar el SUT con configuración alternativa)

1. Ubicar en la entrega operativa del SUT (README/config de `$COPIA_EVAL`) el mecanismo
   de configuración del parámetro objetivo (TTL, chainId, mnemonic importado,
   credencial de cifrado, ruta de almacenamiento).
2. Levantar una **instancia separada** desde `$COPIA_TMP`, con **almacenamiento limpio
   propio** y puerto propio, con la configuración alternativa que la entrada prescribe
   (el resto de la config, la de evaluación). La instancia principal **no se toca**.
3. Observar el comportamiento prescripto: para aborts de provisioning, capturar
   **exit code** (`echo $?`) y **stderr** (buscar el `code` del catálogo); para
   comportamiento en runtime, conducir por REST/WS.
4. Destruir la instancia y su almacenamiento al terminar.
5. Si el SUT no expone el parámetro requerido: aplicar el **fallback** que la entrada
   indique (típicamente F1) o, si la entrada no da fallback,
   `NO_EVALUABLE:PRECONDICION_IMPOSIBLE` con la búsqueda del mecanismo como evidencia.

### F6 — Tests propios del generador como evidencia

Sólo como evidencia complementaria, o sustituta donde la entrada lo permite. Antes de
aceptar un test del SUT como evidencia:

1. **Leerlo**: debe assertar **exactamente** la propiedad de la entrada, con los
   valores esperados de la spec/corpus (no valores fabricados, no asserts triviales,
   no mocks que reemplacen justo lo que se quiere verificar).
2. **Ejecutarlo** en `$COPIA_TMP` con el toolchain del SUT y capturar la salida.
3. Citar archivo:líneas del test + comando + resultado. Un test que no compila/corre
   no es evidencia; un test cuyo assert no corresponde a la propiedad, tampoco.

---

## Épica 01 — Cuentas y autenticación (3 ATs)

### AT-01-02-13
- **Familia:** F1
- **Propiedad:** log de auditoría interno de autenticación: todo intento de login
  (exitoso y fallido) queda registrado con `timestamp` UTC, `email` normalizado,
  `result` (`SUCCESS`/`FAILURE`) y `reason = INVALID_CREDENTIALS` en el fallido; el log
  no es accesible desde la API del usuario (HU-01-02 Escenario 13, RNE-9).
- **Pasos:**
  1. `grep -rni "audit\|auditor\|login_attempt\|loginAttempt\|SUCCESS\|FAILURE" $COPIA_EVAL` (módulo de auth) y localizar dónde se registra cada intento de login.
  2. Verificar en el código que se registran ambos resultados y los cuatro campos (timestamp, email normalizado, result, reason en el fallido).
  3. Refuerzo operativo: ejecutar contra el SUT vivo un login exitoso y uno fallido (`curl -s -X POST $EXCHANGE_API_URL/api/v1/auth/login ...`, usuario creado ad hoc) y localizar los dos registros en el destino del log (archivo o tabla, sólo lectura).
  4. Revisar el mapa de rutas del SUT: ninguna ruta pública/autenticada de usuario expone ese log.
- **Evidencia mínima:** archivo:líneas del código de registro; los dos registros producidos (o cita del código si el destino no es legible); constatación de ausencia de endpoint.
- **Criterio:** PASA si y sólo si ambos intentos quedan registrados con los cuatro campos requeridos y el log no es accesible por la API de usuario. FALLA si no existe registro de intentos, faltan campos (p. ej. no registra los fallidos o no distingue result), o un endpoint de usuario lo expone. NO_EVALUABLE típico: `FUNCION_NO_LOCALIZABLE` si no se puede determinar el destino efectivo del log.

### AT-01-03-04
- **Familia:** F1
- **Propiedad:** un token con `t ≥ expiresAt` no autentica (`UNAUTHENTICATED`, 401) y
  el TTL se valida al arranque dentro de `[60, 86400]` (HU-01-03 RN-3; HU-01-02 RN-3).
- **Pasos:**
  1. `grep -rni "expiresAt\|expires_at\|ttl\|token_ttl" $COPIA_EVAL` y localizar (a) la verificación de expiración en el middleware/guard de autenticación y (b) la carga/validación del TTL de configuración.
  2. Verificar el borde: el token se rechaza cuando `ahora ≥ expiresAt` (un chequeo `ahora > expiresAt` dejaría válido el instante exacto de expiración y viola RN-3).
  3. Verificar que un TTL configurado fuera de `[60, 86400]` (≤ 0 o > 86400) **impide el arranque** del servicio.
  4. Refuerzo opcional (F5): instancia descartable con TTL = 60 s; login; esperar 61 s; una llamada protegida debe dar 401 `UNAUTHENTICATED`.
- **Evidencia mínima:** archivo:líneas del chequeo de expiración (con el operador del borde) y de la validación del TTL al arranque.
- **Criterio:** PASA si y sólo si existe el chequeo de expiración con borde `≥ expiresAt` aplicado a toda request autenticada Y el arranque valida el rango del TTL. FALLA si falta el chequeo, el borde es incorrecto, o un TTL inválido no impide el arranque. NO_EVALUABLE típico: `FUNCION_NO_LOCALIZABLE`.

### AT-01-03-09
- **Familia:** F1
- **Propiedad:** un token expirado no puede reactivarse: no existe ninguna operación de
  renovación/reactivación; sólo un nuevo login emite un token válido (HU-01-03 RN-7).
- **Pasos:**
  1. `grep -rni "refresh\|renew\|extend\|reactivate\|revive" $COPIA_EVAL` sobre el módulo de auth y el registro de rutas.
  2. Verificar que ninguna ruta ni función interna extiende `expiresAt` ni re-marca como válido un token expirado/invalidado, y que la única emisión de tokens es el login (HU-01-02).
  3. Verificar que la verificación de expiración (AT-01-03-04, paso 2) se aplica de forma incondicional en cada request (no hay caminos que la salteen).
- **Evidencia mínima:** salida de las búsquedas (sin hallazgos de reactivación) + archivo:líneas del único punto de emisión de tokens.
- **Criterio:** PASA si y sólo si no existe vía de renovación/reactivación de tokens y la validación de expiración es incondicional. FALLA si existe un endpoint/función que renueva o reactiva tokens, o un camino autenticado que omite el chequeo. NO_EVALUABLE típico: `FUNCION_NO_LOCALIZABLE`.

## Épica 02 — Balances y ledger (12 ATs)

### AT-02-03-01
- **Familia:** F1
- **Propiedad:** la acreditación de un depósito escribe un asiento `DEPOSIT` con
  `reference = { txHash, logIndex }`, `timestamp` ISO-8601 y postings
  `CREDIT available(acc, A)` / `DEBIT EXTERNAL(A)` balanceados por activo
  (HU-02-03 RN-2/RN-3/RN-4).
- **Pasos:**
  1. Producir un depósito real: crear usuario (`POST /auth/register` + login), `GET /deposit-address?asset=USDC`; transferir USDC-mock a esa dirección (vía `EVAL_RPC_URL`, p. ej. reutilizando `evaluacion/suite-at/entorno/fondear.py` con la dirección de depósito) y minar 12 bloques (`anvil_mine`); esperar `status=ACREDITADO` en `GET /deposits`.
  2. Localizar el almacenamiento del ledger (`grep -rni "ledger\|posting\|entry\|journal\|DEPOSIT" $COPIA_EVAL` + entrega operativa) y leer el asiento generado (sólo lectura).
  3. Verificar: `type = DEPOSIT`; `reference` con `txHash` y `logIndex` del depósito; dos postings con los buckets/direcciones/contracuenta `EXTERNAL` y el monto exacto; Σ CREDIT = Σ DEBIT en USDC.
  4. Si la lectura del almacenamiento es inviable, fallback: inspección del código que construye el asiento en el pipeline de acreditación.
- **Evidencia mínima:** el asiento leído (o archivo:líneas del constructor del asiento) + comandos del depósito.
- **Criterio:** PASA si y sólo si el asiento existe con exactamente esa forma (type, reference, ambos postings, balanceado). FALLA si la acreditación muta balances sin asiento, el asiento carece de `reference {txHash, logIndex}` o de la contracuenta `EXTERNAL`, o no balancea. NO_EVALUABLE típico: `FUNCION_NO_LOCALIZABLE` (modelo de ledger indeterminable).

### AT-02-03-02
- **Familia:** F1
- **Propiedad:** el bloqueo por alta de orden escribe un asiento `ORDER_LOCK` con
  `reference = { orderId }` y postings `DEBIT available` / `CREDIT locked` por el monto
  bloqueado, balanceado (HU-02-03 RN-2/RN-4).
- **Pasos:**
  1. Con el usuario fondeado de AT-02-03-01, colocar una `BUY LIMIT` que descanse (`POST /orders`, `priceMin="2000000000"`, `quantityWei="1000000000000000000"`, `clientOrderId` único) — bloquea `2000000000` USDC-min.
  2. Leer el asiento `ORDER_LOCK` en el ledger: `type`, `reference.orderId` = el orderId devuelto, postings `DEBIT available(A, USDC) 2000000000` / `CREDIT locked(A, USDC) 2000000000`.
  3. Fallback: inspección del código del flujo de reserva (épica 02/04).
- **Evidencia mínima:** el asiento leído (o archivo:líneas) + comando del alta.
- **Criterio:** PASA si y sólo si existe un asiento `ORDER_LOCK` con esa referencia y esos dos postings exactos. FALLA si el bloqueo se aplica sin asiento, con otro type/estructura, o desbalanceado. NO_EVALUABLE típico: `FUNCION_NO_LOCALIZABLE`.

### AT-02-03-03
- **Familia:** F1
- **Propiedad:** la cancelación de la orden sin fills escribe un asiento
  `ORDER_RELEASE` con `reference = { orderId }` y postings `DEBIT locked` /
  `CREDIT available` por el remanente (HU-02-03 RN-2/RN-4).
- **Pasos:**
  1. Cancelar la orden de AT-02-03-02 (`DELETE /orders/{orderId}`).
  2. Leer el asiento `ORDER_RELEASE`: `reference.orderId`, postings `DEBIT locked(A, USDC) 2000000000` / `CREDIT available(A, USDC) 2000000000`.
  3. Fallback: inspección del código del flujo de liberación.
- **Evidencia mínima:** el asiento leído (o archivo:líneas) + comando de cancelación.
- **Criterio:** PASA si y sólo si existe un asiento `ORDER_RELEASE` con esa referencia y esos postings exactos. FALLA si la liberación no deja asiento o su estructura difiere. NO_EVALUABLE típico: `FUNCION_NO_LOCALIZABLE`.

### AT-02-03-04
- **Familia:** F1
- **Propiedad:** un fill genera **un único** asiento `TRADE_FILL` con
  `reference = { tradeId }` y **seis** postings (los de HU-02-03 AT-02-03-04: débitos de
  locked de ambas partes, créditos netos, y dos postings `kind = FEE` hacia `EX`),
  balanceado por activo (HU-02-03 RN-2/RN-3/RN-4).
- **Pasos:**
  1. Producir el fill de referencia: usuario A fondeado con USDC (≥ 2000 USDC) y usuario B con ETH (≥ 1 ETH, depósito ETH análogo a AT-02-03-01); B coloca `SELL LIMIT 1 ETH @ 2000000000`; A coloca `BUY LIMIT 1 ETH @ 2000000000` (taker).
  2. Leer el/los asientos del fill en el ledger y verificar: **un solo** asiento `TRADE_FILL`, `reference.tradeId` presente, exactamente 6 postings con los montos del escenario (`DEBIT locked(A,USDC) 2000000000`; `CREDIT available(A,ETH) 998000000000000000`; `DEBIT locked(B,ETH) 1000000000000000000`; `CREDIT available(B,USDC) 1998000000`; `CREDIT available(EX,ETH) 2000000000000000` kind FEE; `CREDIT available(EX,USDC) 2000000` kind FEE).
  3. Verificar balanceo por activo (ETH y USDC por separado).
  4. Fallback: inspección del constructor del asiento de settlement (épica 05 → épica 02).
- **Evidencia mínima:** el asiento leído con sus 6 postings (o archivo:líneas del constructor) + comandos del fill.
- **Criterio:** PASA si y sólo si hay exactamente un asiento `TRADE_FILL` por el fill, con los 6 postings, montos exactos, `kind = FEE` sólo hacia `EX`, balanceado por activo. FALLA si el fill produce varios asientos separados por pata, faltan las fees a `EX`, los montos difieren, o no balancea. NO_EVALUABLE típico: `FUNCION_NO_LOCALIZABLE`.

### AT-02-03-05
- **Familia:** F1
- **Propiedad:** los balances son reconstruibles sumando `CREDIT − DEBIT` por
  cuenta/activo/bucket sobre el ledger, coinciden exactamente con los reportados, y el
  recomputo es determinista (HU-02-03 RN-6, INV-8).
- **Pasos:**
  1. Con el estado producido por AT-02-03-01..04, leer **todos** los postings del ledger (sólo lectura) con un script en `$COPIA_TMP`.
  2. Computar `Σ CREDIT − Σ DEBIT` por `(cuenta, activo, bucket)` con enteros (sin floats).
  3. Comparar con `GET /balances` de A y B (available/locked) con igualdad estricta; si el almacenamiento tiene tabla de balances materializados, comparar también contra ella.
  4. Reejecutar el script: mismo resultado (determinismo).
- **Evidencia mínima:** script + salida de ambas corridas + respuestas de `/balances`.
- **Criterio:** PASA si y sólo si la reconstrucción coincide exactamente con los balances reportados y es determinista. FALLA si difiere en cualquier `(cuenta, activo, bucket)` o el ledger no contiene los postings necesarios para reconstruir. NO_EVALUABLE típico: `FUNCION_NO_LOCALIZABLE` (almacenamiento ilegible).

### AT-02-03-06
- **Familia:** F1
- **Propiedad:** la corrección se hace con un asiento `REVERSAL` de postings
  exactamente inversos y `reference = { reversedEntryId }`, sin modificar ni borrar el
  asiento original (ledger append-only) (HU-02-03 RN-4/RN-5).
- **Pasos:**
  1. `grep -rni "REVERSAL\|reversed\|reversedEntryId" $COPIA_EVAL`.
  2. Verificar en el código: el mecanismo crea un asiento nuevo con las mismas líneas `{account, asset, bucket, amount, kind}` y `direction` opuesta, `reference.reversedEntryId` = entryId original.
  3. Verificar append-only: no existe `UPDATE`/`DELETE` (o equivalente del almacenamiento) sobre asientos/postings en el código del motor contable (`grep -rni "update\|delete" ` acotado al módulo de ledger).
- **Evidencia mínima:** archivo:líneas del mecanismo REVERSAL + salida de la búsqueda de mutaciones.
- **Criterio:** PASA si y sólo si existe el mecanismo `REVERSAL` con postings inversos y referencia al asiento revertido, y el ledger es append-only. FALLA si no existe `REVERSAL` (enum incompleto), o la corrección edita/borra asientos existentes. NO_EVALUABLE típico: `FUNCION_NO_LOCALIZABLE`.

### AT-02-03-07
- **Familia:** F1
- **Propiedad:** un asiento `DEPOSIT` por identidad `(txHash, logIndex)` se escribe a
  lo sumo una vez; el reproceso no crea un segundo asiento y se reporta
  `DEPOSIT_ALREADY_CREDITED` (HU-02-03 RN-8, INV-5).
- **Pasos:**
  1. `grep -rni "DEPOSIT_ALREADY_CREDITED\|logIndex\|log_index" $COPIA_EVAL` y localizar la garantía de unicidad de la identidad en la acreditación.
  2. Verificar que la garantía vive en la persistencia o está serializada (constraint UNIQUE sobre la identidad —con el activo/tipo, HU-07-04 RN-1/RN-2— con `INSERT ... ON CONFLICT`/manejo del conflicto, o check+insert dentro de una única transacción serializada) y que el camino de reproceso **no** escribe un segundo asiento `DEPOSIT`.
  3. Verificar que el resultado del reproceso se reporta como `DEPOSIT_ALREADY_CREDITED` (log/retorno interno).
- **Evidencia mínima:** archivo:líneas de la constraint/chequeo y del camino de reproceso.
- **Criterio:** PASA si y sólo si existe garantía de a-lo-sumo-un-asiento por identidad (en persistencia o serializada) y el reproceso reporta `DEPOSIT_ALREADY_CREDITED` sin escribir. FALLA si el reproceso escribiría un segundo asiento (sin constraint ni chequeo) o vuelve a acreditar. NO_EVALUABLE típico: `FUNCION_NO_LOCALIZABLE`.

### AT-02-03-08
- **Familia:** F1
- **Propiedad:** el motor contable valida antes de persistir que cada asiento balancea
  por activo (Σ CREDIT = Σ DEBIT); un asiento desbalanceado se rechaza sin persistir y
  sin tocar balances (HU-02-03 RN-3, Escenario 8; INV-1).
- **Pasos:**
  1. `grep -rni "balance\|balanced\|credit\|debit" $COPIA_EVAL` acotado al módulo que persiste asientos; localizar la validación de balanceo (suma por activo) o una constraint/trigger equivalente del almacenamiento.
  2. Verificar que la validación corre **antes** de persistir y que su fallo aborta sin escribir (dentro de la transacción / antes de ella).
  3. F6 opcional: si el SUT trae un test que intenta escribir un asiento desbalanceado, revisarlo y ejecutarlo.
- **Evidencia mínima:** archivo:líneas de la validación y de su punto de invocación.
- **Criterio:** PASA si y sólo si existe la validación de Σ CREDIT = Σ DEBIT por activo en el camino único de escritura de asientos y su fallo no persiste nada. FALLA si el motor persiste asientos sin validar balanceo (la propiedad ausente es FALLA). NO_EVALUABLE típico: `FUNCION_NO_LOCALIZABLE`.

### AT-02-03-09
- **Familia:** F4
- **Propiedad:** una falla tras persistir algunos postings y antes de completar el
  asiento no deja asiento parcial: cabecera y todos los postings se escriben en una
  única unidad atómica (HU-02-03 RN-7, INV-4).
- **Pasos:**
  1. Localizar el código que persiste un asiento con sus postings (mismo módulo que AT-02-03-08).
  2. Verificar el límite transaccional (procedimiento F4.1): cabecera + todos los postings dentro de una única transacción/escritura atómica, con rollback ante excepción; sin escrituras del asiento fuera de esa unidad.
  3. Refuerzo opcional (F4.2): en `$COPIA_TMP`, inyectar una excepción tras el 3.er posting y ejecutar un fill con un driver/test; verificar que no queda ningún posting de ese asiento.
- **Evidencia mínima:** archivo:líneas del límite transaccional (apertura, escrituras, commit/rollback).
- **Criterio:** PASA si y sólo si el asiento completo se escribe en una única unidad atómica con rollback. FALLA si los postings se insertan en escrituras independientes sin transacción (posible asiento parcial). NO_EVALUABLE típico: `FUNCION_NO_LOCALIZABLE`.

### AT-02-03-11
- **Familia:** F4
- **Propiedad:** el `TRADE_FILL` y el `ORDER_RELEASE` de surplus de un mismo fill son
  dos asientos pero **una unidad atómica**: se persisten en la misma transacción, ambos
  o ninguno (HU-02-03 RN-4 §surplus; HU-05-01 RN-6/RN-7; INV-4).
- **Pasos:**
  1. Localizar el settlement con surplus (`grep -rni "surplus\|release\|price_limit\|priceLimit" $COPIA_EVAL` en el módulo de settlement).
  2. Verificar que la escritura del `ORDER_RELEASE` de surplus ocurre **dentro del mismo límite transaccional** que el `TRADE_FILL` (misma transacción abierta; no una segunda transacción ni un job posterior).
  3. Refuerzo opcional: inyección en `$COPIA_TMP` entre ambas escrituras + driver de un fill con mejora de precio; verificar rollback de ambos.
- **Evidencia mínima:** archivo:líneas mostrando ambas escrituras dentro de la misma transacción.
- **Criterio:** PASA si y sólo si ambos asientos se persisten en la misma unidad atómica. FALLA si el surplus se libera en una transacción separada (podría quedar `TRADE_FILL` sin su release). NO_EVALUABLE típico: `FUNCION_NO_LOCALIZABLE`.

### AT-02-04-02
- **Familia:** F4
- **Propiedad:** el settlement de un fill (6 postings + cambios de balance) es una
  transacción única todo-o-nada: una excepción tras el N-ésimo posting revierte todo y
  los balances vuelven al estado exacto previo (HU-02-04 RN-1/RN-6, INV-4).
- **Pasos:**
  1. Localizar la operación de settlement completa (asiento `TRADE_FILL` + actualización de balances si están materializados).
  2. Verificar el límite transaccional (F4.1): todas las escrituras del settlement dentro de una única transacción con rollback; los balances materializados (si existen) se actualizan dentro de la misma transacción o se derivan del ledger.
  3. Refuerzo opcional (mecanismo de referencia del AT): en `$COPIA_TMP`, hacer que el repositorio lance una excepción tras persistir el 3.er posting; ejecutar un fill; verificar que no queda ningún posting ni cambio de balance.
- **Evidencia mínima:** archivo:líneas del límite transaccional del settlement (y, si se hizo, el diff de la instrumentación + salida).
- **Criterio:** PASA si y sólo si el settlement completo está dentro de una única unidad atómica con rollback y sin escrituras persistentes fuera de ella. FALLA si alguna pata (postings, balances, trade) se escribe fuera de la transacción. NO_EVALUABLE típico: `FUNCION_NO_LOCALIZABLE`.

### AT-02-04-07
- **Familia:** F4
- **Propiedad:** una caída con una transacción de balance sin committear no deja datos:
  tras recuperar, la operación interrumpida está completamente aplicada o completamente
  ausente, y se cumplen INV-1/INV-2/INV-3 (HU-02-04 RN-8, INV-4/INV-8).
- **Pasos:**
  1. Verificar (F4.1) que la unidad de escritura es una transacción durable del almacenamiento (BD con journal/WAL, o archivo con `fsync`+`rename`): una terminación abrupta antes del commit no puede dejar escrituras visibles.
  2. Verificar el camino de recuperación al arranque: reconstruye desde lo committeado (no reaplica operaciones a medias ni depende de estado en memoria perdido).
  3. Refuerzo opcional (F3): lanzar en loop altas/cancelaciones (`curl` en background) y ejecutar `SUITE_CMD_REINICIO_SUT` en medio; tras readiness, verificar con el script de AT-02-03-05 que ledger↔balances reconcilian y no hay asientos parciales.
- **Evidencia mínima:** archivo:líneas del mecanismo de durabilidad/commit + (si se hizo) comandos y verificación post-reinicio.
- **Criterio:** PASA si y sólo si el mecanismo de commit atómico durable existe y la recuperación parte sólo de lo committeado (y el refuerzo, si se ejecutó, no muestra incoherencias). FALLA si la persistencia usa escrituras no atómicas sin recuperación (p. ej. reescritura de archivos sin fsync/rename) o el refuerzo evidencia estado parcial. NO_EVALUABLE típico: `SUT_NO_ARRANCA` (tras el kill del refuerzo).

## Épica 03 — Motor de matching (4 ATs)

### AT-03-02-07
- **Familia:** F1
- **Propiedad:** garantía interna del motor: una segunda inserción con el mismo
  `orderId` no produce dos instancias en el libro ni dos `seq`; el duplicado se rechaza
  (HU-03-02 RN-8/Escenario 7; HU-03-01 RN-11).
- **Pasos:**
  1. Localizar la estructura del orderbook y su inserción (`grep -rni "orderbook\|order_book\|insert\|bids\|asks\|seq" $COPIA_EVAL`).
  2. Verificar la garantía: estructura indexada por `orderId` que impide duplicados (map/índice único) **o** chequeo explícito de pertenencia previo a insertar, con rechazo sin asignar `seq`.
  3. F6 opcional: test unitario del motor que intente la doble inserción; revisarlo y ejecutarlo.
- **Evidencia mínima:** archivo:líneas de la estructura/chequeo de unicidad en la inserción.
- **Criterio:** PASA si y sólo si la inserción de un `orderId` ya presente es imposible por estructura o se rechaza explícitamente sin segundo `seq`. FALLA si la inserción duplicada agregaría la orden dos veces (lista sin chequeo). NO_EVALUABLE típico: `FUNCION_NO_LOCALIZABLE`.

### AT-03-05-08
- **Familia:** F1
- **Propiedad:** ante un rechazo de matching por `SELF_TRADE_BLOCKED`, el motor emite
  hacia sus consumidores un `order-update` interno con `status = REJECTED`,
  `cumulativeFilledWei = "0"`, `remainingWei = quantityWei`,
  `reason = "SELF_TRADE_BLOCKED"`, `sequence` y `timestamp`, **sin** `tradeId` y sin
  ningún evento `trade` (HU-03-05 RN-13).
- **Pasos:**
  1. `grep -rni "SELF_TRADE_BLOCKED" $COPIA_EVAL` y localizar el camino de rechazo del motor.
  2. Verificar que ese camino emite el evento interno de actualización de orden (bus/callback/cola interna del motor) con los campos de RN-13, sin `tradeId`, y que no emite `trade`.
  3. F6 opcional: test del motor sobre el rechazo self-trade; revisarlo y ejecutarlo.
- **Evidencia mínima:** archivo:líneas de la emisión del evento en el camino de rechazo (o de su ausencia tras búsqueda exhaustiva).
- **Criterio:** PASA si y sólo si el rechazo de matching emite el `order-update` interno `REJECTED` con `reason` y sin `tradeId`. FALLA si el motor no emite ningún evento interno de rechazo (los consumidores verían la orden pendiente) o el evento carece de `reason`/lleva `tradeId`. NO_EVALUABLE típico: `FUNCION_NO_LOCALIZABLE`.

### AT-03-07-04
- **Familia:** F4
- **Propiedad:** una caída en medio de un fill (settlement no completado) no deja
  estado parcial: el fill queda aplicado por completo (settlement + libro) o no
  aplicado; INV-1/INV-2/INV-3/INV-7 se cumplen tras recuperar (HU-03-07 RN-7, INV-4).
- **Pasos:**
  1. Verificar (F4.1) que la persistencia del fill —asientos de settlement, registro de trade y efecto sobre el orderbook persistido (remanentes/retiro de makers)— comparte **una** unidad atómica, o que el libro se **reconstruye** desde el ledger/órdenes committeadas al arrancar (con lo cual el estado del libro en memoria no puede divergir de lo committeado).
  2. Localizar el camino de recuperación del orderbook (arranque) y verificar que parte exclusivamente de estado committeado.
  3. Refuerzo opcional: en `$COPIA_TMP`, hook que aborte el proceso tras el primer paso del settlement (edición declarada) + driver de un fill; reiniciar la instancia descartable y verificar balances/libro previos al fill.
- **Evidencia mínima:** archivo:líneas del límite transaccional del fill y del camino de recuperación.
- **Criterio:** PASA si y sólo si el efecto completo del fill es atómico respecto de la persistencia y la recuperación reconstruye sólo desde lo committeado. FALLA si el settlement y el estado persistido del libro se escriben en unidades separadas sin reconstrucción desde el ledger (posible fill a medias tras caída). NO_EVALUABLE típico: `FUNCION_NO_LOCALIZABLE`.

### AT-03-07-09
- **Familia:** F1
- **Propiedad:** tras una caída posterior a persistir fills de una `MARKET` pero previa
  a grabar su estado terminal, la recuperación **infiere** el estado desde los fills:
  `filledWei = quantityWei` ⇒ `FILLED`; `0 < filledWei < quantityWei` ⇒ `CANCELLED`
  (reason `MARKET_EXHAUSTED`/`MARKET_BUDGET_EXHAUSTED` o genérico); `filledWei = 0` ⇒
  `REJECTED`/`CANCELLED` consistente con el ledger; nunca en limbo (HU-03-07 RN-13).
- **Pasos:**
  1. Localizar el código de recuperación/arranque (`grep -rni "recover\|rebuild\|restore\|startup\|boot" $COPIA_EVAL`) y el tratamiento de órdenes `MARKET` sin estado terminal.
  2. Camino A: existe la lógica de inferencia con los tres casos de RN-13 → verificarla.
  3. Camino B (ventana inexistente por construcción): los fills y el estado terminal de la `MARKET` se persisten en la **misma** transacción atómica (citar el límite transaccional); entonces no puede existir una `MARKET` con fills y sin estado terminal, y la propiedad se cumple por construcción.
- **Evidencia mínima:** archivo:líneas de la lógica de inferencia (camino A) **o** del límite transaccional que une fills y estado terminal (camino B).
- **Criterio:** PASA si y sólo si (A) la inferencia RN-13 existe con los tres casos, **o** (B) fills y estado terminal son atómicos por construcción. FALLA si la ventana existe (escrituras separadas) y la recuperación no infiere el estado (la orden quedaría en limbo o en un estado no terminal). NO_EVALUABLE típico: `FUNCION_NO_LOCALIZABLE`.

## Épica 04 — Gestión de órdenes (4 ATs)

### AT-04-01-11
- **Familia:** F3
- **Propiedad:** una orden `LIMIT` `OPEN` y su reserva sobreviven a un reinicio: mismo
  estado y campos, prioridad precio-tiempo intacta, `bloqueado`/`disponible`
  reconstruidos idénticos (HU-04-01 RN-12/Escenario 11; INV-7, INV-8).
- **Pasos:**
  1. Crear dos usuarios A y B; fondear USDC a ambos (procedimiento de AT-02-03-01). A coloca `BUY LIMIT 1 ETH @ 2000000000` y B coloca después otra `BUY LIMIT 1 ETH @ 2000000000` (mismo precio, A con prioridad FIFO).
  2. Registrar ANTES: `GET /orders/{id}` de ambas (status, priceMin, quantityWei, filledWei, remainingWei) y `GET /balances` de A y B.
  3. Reiniciar: `eval "$SUITE_CMD_REINICIO_SUT"`; esperar readiness.
  4. Registrar DESPUÉS y comparar campo a campo (igualdad estricta de strings).
  5. Verificar prioridad: un tercer usuario C (fondeado con ETH) envía `SELL LIMIT 1 ETH @ 2000000000`; la orden de **A** debe quedar `FILLED` y la de B seguir `OPEN`.
- **Evidencia mínima:** respuestas antes/después + comando de reinicio + resultado del fill dirigido.
- **Criterio:** PASA si y sólo si ambas órdenes y los balances son idénticos tras el reinicio y el fill dirigido consume primero la orden más antigua (FIFO preservado). FALLA si una orden desaparece/cambia de estado o campos, los balances difieren, o la prioridad se invierte. NO_EVALUABLE típico: `SUT_NO_ARRANCA`.

### AT-04-04-12
- **Familia:** F3
- **Propiedad:** el estado `CANCELLED`, la ausencia del libro y la liberación de fondos
  persisten tras un reinicio (HU-04-04 RN-10, INV-8).
- **Pasos:**
  1. Usuario fondeado coloca una `BUY LIMIT` que descansa y la cancela (`DELETE /orders/{id}`).
  2. Registrar ANTES: `GET /orders/{id}` (`status = CANCELLED`), `GET /balances` (reserva liberada) y `GET /orderbook` (la orden no figura).
  3. Reiniciar con `SUITE_CMD_REINICIO_SUT`; esperar readiness.
  4. Registrar DESPUÉS y comparar: sigue `CANCELLED`, ausente del libro, balances idénticos.
- **Evidencia mínima:** respuestas antes/después + comando de reinicio.
- **Criterio:** PASA si y sólo si tras el reinicio la orden sigue `CANCELLED`, no está en el orderbook y los balances coinciden exactamente. FALLA si la orden reaparece abierta, re-bloquea fondos o los balances difieren. NO_EVALUABLE típico: `SUT_NO_ARRANCA`.

### AT-04-05-13
- **Familia:** F3
- **Propiedad:** órdenes en estados `OPEN`, `PARTIALLY_FILLED`, `FILLED` y `CANCELLED`
  conservan estado y `filledWei` tras un reinicio; las abiertas mantienen su prioridad
  (HU-04-05 RN-10/Escenario 13; INV-7, INV-8).
- **Pasos:**
  1. Construir los cuatro estados con usuarios fondeados: O1 `OPEN` (BUY que descansa); O2 `PARTIALLY_FILLED` (BUY 1 ETH contra un SELL ajeno de 0.4 ETH); O3 `FILLED` (BUY marketable total); O4 `CANCELLED` (BUY cancelada).
  2. Registrar ANTES: `GET /orders/{id}` de las cuatro (status, filledWei, remainingWei) y balances de los involucrados.
  3. Reiniciar; esperar readiness.
  4. Registrar DESPUÉS y comparar las cuatro órdenes campo a campo; verificar que O1/O2 siguen en el libro (`GET /orderbook`) y O3/O4 no.
- **Evidencia mínima:** respuestas antes/después de las cuatro órdenes + comando de reinicio.
- **Criterio:** PASA si y sólo si cada orden conserva exactamente estado y `filledWei`, y las abiertas siguen en el libro respaldadas. FALLA si algún estado/campo cambia, una abierta desaparece o una terminal "revive". NO_EVALUABLE típico: `SUT_NO_ARRANCA`.

### AT-04-05-14
- **Familia:** F4
- **Propiedad:** `NEW` es transitorio y nunca durable: el alta (reserva + matching +
  registro) es atómica; tras recuperar, toda orden está en su estado resultante con
  reserva consistente o no existe (y no quedó reserva tomada); ninguna consulta
  devuelve `NEW` (HU-04-05 RN-11).
- **Pasos:**
  1. Localizar el flujo de alta (`grep -rni "NEW\|place_order\|placeOrder\|create_order" $COPIA_EVAL`) y verificar (F4.1) que reserva + resultado del matching + registro del estado comparten una unidad atómica, o que `NEW` no se persiste nunca fuera de ella.
  2. Verificar que las consultas (GET /orders, historial) filtran/no pueden devolver `NEW`.
  3. Refuerzo opcional (F3): loop de altas concurrentes con `curl` + `SUITE_CMD_REINICIO_SUT` en medio; tras readiness, verificar que ninguna orden está `NEW` y que no hay `locked` huérfano (balances vs órdenes abiertas).
- **Evidencia mínima:** archivo:líneas del límite transaccional del alta y del filtrado de `NEW` en consultas.
- **Criterio:** PASA si y sólo si el alta es atómica (o `NEW` no es durable) y ninguna consulta puede devolver `NEW`. FALLA si `NEW` se persiste fuera de la transacción del alta (ventana de fondos bloqueados sin orden visible) o una consulta lo expone. NO_EVALUABLE típico: `FUNCION_NO_LOCALIZABLE`.

## Épica 05 — Settlement y fees (6 ATs)

### AT-05-01-06
- **Familia:** F4
- **Propiedad:** una falla a mitad del settlement (después de debitar la base, antes de
  acreditar la quote) revierte **todo**: balances de las partes y de `EX` exactamente
  como antes del fill, sin snapshot intermedio observable, con `INTERNAL_ERROR`
  reportado y reintento idempotente posible (HU-05-01 RN-7/Escenario 6, INV-4).
- **Pasos:**
  1. Localizar el settlement (`grep -rni "settle\|settlement\|fee\|trade_fill\|TRADE_FILL" $COPIA_EVAL`).
  2. Verificar (F4.1) que los asientos/patas de RN-7 (base, quote, fees, surplus) están íntegramente dentro de una única transacción con rollback ante excepción, y que el camino de error reporta `INTERNAL_ERROR` sin escrituras residuales.
  3. Refuerzo opcional: en `$COPIA_TMP`, mock/edición que lance una excepción tras el primer asiento + driver de un fill; verificar balances intactos y ausencia de trade.
- **Evidencia mínima:** archivo:líneas del límite transaccional (apertura → todas las patas → commit/rollback).
- **Criterio:** PASA si y sólo si todas las patas del settlement comparten una unidad atómica con rollback total. FALLA si alguna pata (p. ej. fees a `EX` o el crédito de la contraparte) se aplica fuera de la transacción. NO_EVALUABLE típico: `FUNCION_NO_LOCALIZABLE`.

### AT-05-01-07
- **Familia:** F1
- **Propiedad:** el settlement es idempotente por `tradeId`: antes de aplicar verifica
  si ya existe un trade con ese `tradeId` y, si existe, es no-op (sin nuevos asientos
  ni fees) (HU-05-01 RN-10).
- **Pasos:**
  1. `grep -rni "tradeId\|trade_id\|idempoten" $COPIA_EVAL` en el módulo de settlement.
  2. Verificar el chequeo previo "¿existe tradeId?" con retorno no-op, **o** una constraint UNIQUE sobre `tradeId` cuyo conflicto se maneja como no-op (sin abortar dejando asientos aplicados).
  3. F6 opcional: test propio de reproceso del mismo fill; revisarlo y ejecutarlo.
- **Evidencia mínima:** archivo:líneas del chequeo/constraint y del manejo del caso duplicado.
- **Criterio:** PASA si y sólo si reprocesar un `tradeId` ya liquidado no genera asientos ni fees (no-op garantizado por chequeo serializado o constraint manejada). FALLA si no hay chequeo (el reproceso duplicaría asientos) o el conflicto deja efectos parciales. NO_EVALUABLE típico: `FUNCION_NO_LOCALIZABLE`.

### AT-05-01-09
- **Familia:** F1
- **Propiedad:** antes de aplicar, el settlement verifica las precondiciones
  `bloqueado(vendedor, ETH) ≥ q_wei` y `bloqueado(comprador, USDC) ≥ quote_min`; si no
  se cumplen, no aplica ningún asiento, deja balances intactos y reporta
  `INTERNAL_ERROR` (HU-05-01 RN-9, INV-2/INV-4).
- **Pasos:**
  1. En el settlement, localizar la verificación de bloqueado suficiente previa a los asientos (`grep -rni "locked\|bloqueado\|INTERNAL_ERROR\|precondition" $COPIA_EVAL`).
  2. Verificar que el camino de fallo no muta nada (retorno/excepción antes de escribir, o dentro de la transacción con rollback) y reporta `INTERNAL_ERROR`.
  3. Equivalente aceptable: constraint de no-negatividad en la persistencia (`CHECK ≥ 0` o validación del modelo) que aborta la transacción completa del settlement con error.
- **Evidencia mínima:** archivo:líneas de la verificación (o constraint) y del camino de fallo.
- **Criterio:** PASA si y sólo si existe una verificación/garantía que rechaza el fill sin aplicar asiento alguno cuando el bloqueado no alcanza, reportando `INTERNAL_ERROR`. FALLA si el settlement aplicaría los asientos sin verificar (balance negativo posible) o corrige después. NO_EVALUABLE típico: `FUNCION_NO_LOCALIZABLE`.

### AT-05-03-05
- **Familia:** F1
- **Propiedad:** el reproceso de un fill no crea un segundo registro de trade: existe
  exactamente un trade por `tradeId`, garantizado por unicidad en persistencia o por la
  misma guarda de idempotencia del settlement (HU-05-03 RN-2).
- **Pasos:**
  1. Localizar el registro de trades (`grep -rni "trades\|trade\b\|T-\|UNIQUE" $COPIA_EVAL`).
  2. Verificar unicidad de `tradeId`: constraint UNIQUE/clave primaria, o inserción dentro del mismo camino idempotente de AT-05-01-07 (el no-op evita la segunda inserción).
  3. Verificar que el trade se crea una sola vez con campos estables (no se sobreescribe en reprocesos).
- **Evidencia mínima:** archivo:líneas de la clave/constraint o de la guarda que impide la segunda inserción.
- **Criterio:** PASA si y sólo si es imposible persistir dos registros con el mismo `tradeId` (constraint o guarda serializada). FALLA si el reproceso insertaría un duplicado o reescribe el registro. NO_EVALUABLE típico: `FUNCION_NO_LOCALIZABLE`.

### AT-05-03-06
- **Familia:** F4
- **Propiedad:** el registro del trade se crea dentro de la **misma transacción
  atómica** que los asientos del settlement: un settlement revertido no deja trade
  (HU-05-03 RN-1, INV-4).
- **Pasos:**
  1. En el código del settlement, localizar la creación del registro de trade.
  2. Verificar que ocurre dentro del mismo límite transaccional que los asientos (no antes de abrir la transacción ni después del commit, ni en un job/evento posterior).
  3. Refuerzo opcional: con la inyección de AT-05-01-06 en `$COPIA_TMP`, verificar que tras el rollback no existe registro de trade.
- **Evidencia mínima:** archivo:líneas mostrando la inserción del trade dentro de la transacción del settlement.
- **Criterio:** PASA si y sólo si trade y asientos comparten la unidad atómica. FALLA si el trade se registra fuera de la transacción (podría quedar trade sin settlement o viceversa). NO_EVALUABLE típico: `FUNCION_NO_LOCALIZABLE`.

### AT-05-03-07
- **Familia:** F3
- **Propiedad:** los trades sobreviven al reinicio con `tradeId`/`sequence` y montos
  idénticos, y la reconciliación cierra: `Σ feeBaseWei` == acreditado total a `EX` en
  ETH y `Σ feeQuoteMin` == acreditado a `EX` en USDC (HU-05-03 RN-8/RN-9, INV-1/INV-8).
- **Pasos:**
  1. Producir ≥ 2 fills (reutilizar el flujo de AT-02-03-04 con montos distintos).
  2. Registrar ANTES: `GET /trades` propio de los usuarios (tradeId, sequence, priceMin, quantityWei, fees) — o el registro persistido de trades si la vista REST no expone fees.
  3. Reiniciar con `SUITE_CMD_REINICIO_SUT`; esperar readiness; registrar DESPUÉS y comparar registro a registro.
  4. Reconciliar: con un script en `$COPIA_TMP`, sumar `feeBaseWei`/`feeQuoteMin` de todos los trades persistidos y compararlas con lo acreditado a `EX` (balance interno de `EX` o Σ de postings `kind = FEE` del ledger), igualdad estricta.
- **Evidencia mínima:** listados antes/después + script de reconciliación + salida.
- **Criterio:** PASA si y sólo si los trades son idénticos tras el reinicio y ambas sumas de fees igualan exactamente lo acreditado a `EX` por activo. FALLA si difiere un trade o la reconciliación no cierra. NO_EVALUABLE típico: `SUT_NO_ARRANCA`.

## Épica 06 — Wallet HD y direcciones (25 ATs)

### AT-06-01-01
- **Familia:** F1
- **Propiedad:** la generación del seed usa entropía de 256 bits de un **CSPRNG** del
  entorno ⇒ mnemonic de 24 palabras con checksum BIP-39 válido; la seed se deriva con
  `PBKDF2(HMAC-SHA512, mnemonic NFKD, "mnemonic"+passphrase, 2048 iter, 64 bytes)` con
  passphrase vacía por defecto; el seed se persiste **cifrado** (AES-256-GCM, nonce de
  96 bits por operación, tag 128 bits, credencial por entorno) (HU-06-01 RN-1/RN-2/RN-3/RN-6).
- **Pasos:**
  1. `grep -rni "mnemonic\|entropy\|PBKDF2\|pbkdf2\|2048\|seed" $COPIA_EVAL` y localizar generación, derivación y persistencia.
  2. Verificar la fuente de entropía: CSPRNG del entorno (`crypto.randomBytes`, `secrets`/`os.urandom`, `SecureRandom`, `getrandom`…), 32 bytes; **prohibido** `Math.random`/PRNG sembrado.
  3. Verificar parámetros PBKDF2: HMAC-SHA512, salt `"mnemonic" + passphrase`, 2048 iteraciones, dkLen 64, passphrase default `""` — contrastar con `corpus/documentos/bip-0039.mediawiki` §"From mnemonic to seed". Si delega en librería BIP-39, verificar la llamada y (en las fuentes vendoreadas de la librería) los parámetros.
  4. Verificar el cifrado en reposo: AES-256-GCM con nonce aleatorio por cifrado y tag verificado al descifrar; credencial desde el entorno, no hardcodeada ni persistida junto al blob.
- **Evidencia mínima:** archivo:líneas de (a) la fuente de entropía, (b) los parámetros de derivación, (c) el cifrado; cita del corpus.
- **Criterio:** PASA si y sólo si se cumplen los cuatro puntos (CSPRNG 256 bits/24 palabras, PBKDF2-HMAC-SHA512/2048/64, passphrase vacía por defecto, cifrado AES-256-GCM en reposo con credencial externa). FALLA si cualquiera difiere (p. ej. 12 palabras, iteraciones ≠ 2048, seed en claro, clave embebida). NO_EVALUABLE típico: `FUNCION_NO_LOCALIZABLE`.

### AT-06-01-02
- **Familia:** F2
- **Propiedad:** known-answer test BIP-39: `MNEMONIC_BIP39_CANONICO` + passphrase
  `"TREZOR"` ⇒ seed hex exacta
  `c55257c360c07c72029aebc1b53c05ed0362ada38ead3e3e9efa3708e53495531f09a6987599d18264c1e1c92f2cf141630c7a3c4ab7c81b2f001698e7463b04`
  (HU-06-01 RN-3/Escenario 2).
- **Pasos:**
  1. Localizar la función interna mnemonic→seed del SUT.
  2. Driver en `$COPIA_TMP` que la invoque con el vector y emita la seed en hex; comparar por igualdad de strings con el valor de HU-06-01. Referencia normativa del algoritmo: `corpus/documentos/bip-0039.mediawiki` §"From mnemonic to seed".
  3. Alternativa F6: si el SUT trae este KAT, verificar que su valor esperado es exactamente el de la spec y ejecutarlo.
- **Evidencia mínima:** driver (o test propio citado) + comando + salida con la seed obtenida.
- **Criterio:** PASA si y sólo si la seed obtenida coincide exactamente con la esperada. FALLA si difiere en cualquier byte. NO_EVALUABLE típico: `HERRAMIENTA_FALTANTE` (toolchain inejecutable tras 3 intentos) o `FUNCION_NO_LOCALIZABLE`.

### AT-06-01-03
- **Familia:** F2
- **Propiedad:** determinismo de la derivación: el mismo `(mnemonic, passphrase)`
  produce byte a byte la misma seed en ejecuciones distintas (HU-06-01 RN-7).
- **Pasos:**
  1. Con el driver de AT-06-01-02, derivar dos veces —en **dos invocaciones separadas
     del proceso**— la seed de `MNEMONIC_24_VALIDO` con passphrase vacía.
  2. Comparar ambas salidas (igualdad exacta de hex).
- **Evidencia mínima:** los dos comandos + ambas salidas idénticas.
- **Criterio:** PASA si y sólo si ambas derivaciones son idénticas. FALLA si difieren (hay aleatoriedad o estado en RN-3). NO_EVALUABLE típico: `HERRAMIENTA_FALTANTE`.

### AT-06-01-04
- **Familia:** F5
- **Propiedad:** dos provisioning independientes generan mnemonics/seeds distintos (no
  hay entropía fija/hardcodeada) (HU-06-01 RN-1/Escenario 4).
- **Pasos:**
  1. Levantar la instancia descartable **I1** desde `$COPIA_TMP` con almacenamiento limpio, dejar que provisione (generación, sin importar mnemonic); crear una cuenta y registrar su `GET /deposit-address?asset=ETH`.
  2. Destruir I1 (incluido su almacenamiento) y repetir como **I2**; registrar la dirección de su primera cuenta.
  3. Comparar ambas direcciones (índice 0 de cada seed). **No** comparar ciphertexts (el nonce GCM los hace diferir aunque el seed fuera igual).
- **Evidencia mínima:** comandos de ambos arranques + las dos direcciones.
- **Criterio:** PASA si y sólo si las direcciones difieren. FALLA si coinciden (seed fijo). NO_EVALUABLE típico: `SUT_NO_ARRANCA`.

### AT-06-01-05
- **Familia:** F5
- **Propiedad:** un mnemonic de 24 palabras con checksum BIP-39 inválido se rechaza en
  el provisioning: no se adopta ni persiste seed; el proceso aborta con exit code ≠ 0 y
  `VALIDATION_ERROR` en stderr, sin filtrar secretos (HU-06-01 RN-2(c)/RN-11, Escenario 5).
- **Pasos:**
  1. Verificar la constante: script en `$COPIA_TMP` que compute el mnemonic de la entropía `0x00`×32 según `corpus/documentos/bip-0039.mediawiki` §"Generating the mnemonic" (debe dar `MNEMONIC_24_VALIDO`); `MNEMONIC_24_CHECKSUM_INVALIDO` (= `abandon`×24) difiere sólo en la última palabra ⇒ checksum inválido.
  2. Ubicar el mecanismo de **import** de mnemonic del SUT (config documentada). Levantar instancia descartable limpia con `MNEMONIC_24_CHECKSUM_INVALIDO`; capturar exit code y stderr.
  3. Verificar: exit ≠ 0, `VALIDATION_ERROR` en stderr, sin material secreto en stderr, y almacenamiento sin seed persistido.
  4. **Fallback (si no hay mecanismo de import):** F1 — verificar en el código del provisioning la validación de checksum de RN-2(c) (primeros `ENT/32` bits de `SHA-256(entropía)`) y que su fallo aborta sin adoptar seed.
- **Evidencia mínima:** comando de arranque + exit code + stderr (o archivo:líneas de la validación en el fallback) + verificación de la constante.
- **Criterio:** PASA si y sólo si el mnemonic se rechaza con esa señal sin persistir seed (o, en fallback, la validación de checksum existe y aborta). FALLA si lo acepta, persiste un seed, o la validación de checksum no existe. NO_EVALUABLE típico: `SUT_NO_ARRANCA` (la instancia no llega ni a validar).

### AT-06-01-07
- **Familia:** F3
- **Propiedad:** el seed persiste entre reinicios: no se regenera y las direcciones
  derivadas después del reinicio son idénticas a las previas (HU-06-01 RN-8, INV-8).
- **Pasos:**
  1. En la instancia **principal**: crear una cuenta y registrar `GET /deposit-address?asset=ETH` (y `?asset=USDC`, deben coincidir entre sí, HU-06-03 RN-3).
  2. Reiniciar con `SUITE_CMD_REINICIO_SUT`; esperar readiness.
  3. Repetir la consulta para la misma cuenta y comparar.
- **Evidencia mínima:** direcciones antes/después + comando de reinicio.
- **Criterio:** PASA si y sólo si la dirección es idéntica tras el reinicio. FALLA si cambia (seed regenerado) o el SUT exige re-provisioning manual. NO_EVALUABLE típico: `SUT_NO_ARRANCA`.

### AT-06-01-08
- **Familia:** F3
- **Propiedad:** re-ejecutar el provisioning (el arranque con seed ya provisionado) no
  sobrescribe ni regenera el seed; seed y direcciones permanecen sin cambios
  (HU-06-01 RN-4/RN-8).
- **Pasos:**
  1. Reutilizar el reinicio de AT-06-01-07 (mismo disparador, declararlo): la dirección de la cuenta es idéntica tras el re-arranque.
  2. F1 complementario: localizar en el código de arranque la guarda "si existe seed → cargar, no generar" y verificar que ningún camino sobrescribe un seed existente.
- **Evidencia mínima:** direcciones antes/después + archivo:líneas de la guarda.
- **Criterio:** PASA si y sólo si el arranque con seed existente lo carga sin regenerar/sobrescribir y las direcciones no cambian. FALLA si el provisioning regenera o sobrescribe con seed presente. NO_EVALUABLE típico: `SUT_NO_ARRANCA`.

### AT-06-01-09
- **Familia:** F5
- **Propiedad:** un mnemonic de **12 palabras** (válido para 128 bits) se rechaza por
  longitud ≠ 24 con `VALIDATION_ERROR`, sin adoptarse como seed (HU-06-01 RN-2(a), Escenario 9).
- **Pasos:**
  1. Levantar instancia descartable limpia importando `MNEMONIC_BIP39_CANONICO` (12 palabras, checksum válido); capturar exit code y stderr.
  2. Verificar: exit ≠ 0, `VALIDATION_ERROR` en stderr, sin seed persistido.
  3. **Fallback sin import:** F1 — la validación de longitud == 24 palabras existe en el provisioning y su fallo aborta.
- **Evidencia mínima:** comando + exit code + stderr (o archivo:líneas de la validación).
- **Criterio:** PASA si y sólo si el mnemonic de 12 palabras se rechaza con esa señal (o la validación de longitud existe y aborta). FALLA si lo acepta (adoptaría 128 bits de entropía). NO_EVALUABLE típico: `SUT_NO_ARRANCA`.

### AT-06-01-10
- **Familia:** F5
- **Propiedad:** un mnemonic de 24 palabras con al menos una fuera del wordlist BIP-39
  inglés se rechaza con `VALIDATION_ERROR` (HU-06-01 RN-2(b), Escenario 10).
- **Pasos:**
  1. Verificar la constante: `grep -cx xyzzy corpus/documentos/bip-0039-wordlist-english.txt` → `0` (la palabra no pertenece al wordlist de 2048).
  2. Levantar instancia descartable limpia importando `MNEMONIC_24_PALABRA_INVALIDA`; capturar exit code y stderr.
  3. Verificar: exit ≠ 0, `VALIDATION_ERROR`, sin seed persistido.
  4. **Fallback sin import:** F1 — la validación de pertenencia al wordlist (las 2048 palabras, corpus doc 3) existe y su fallo aborta.
- **Evidencia mínima:** salida del grep sobre el wordlist + comando + exit code + stderr (o archivo:líneas de la validación).
- **Criterio:** PASA si y sólo si el mnemonic se rechaza con esa señal (o la validación de wordlist existe y aborta). FALLA si lo acepta o la validación no contempla el wordlist. NO_EVALUABLE típico: `SUT_NO_ARRANCA`.

### AT-06-01-11
- **Familia:** F5
- **Propiedad:** si la credencial de descifrado es ausente/incorrecta o el blob está
  corrupto (el tag GCM no verifica), el arranque aborta con exit ≠ 0 e
  `INTERNAL_ERROR` en stderr, **sin** regenerar seed ni continuar sin seed, sin filtrar
  secretos (HU-06-01 RN-6/RN-11, Escenario 11).
- **Pasos:**
  1. Levantar instancia descartable limpia y dejar que provisione; detenerla.
  2. Re-arrancarla con la credencial de cifrado **ausente** (y en una segunda corrida, **incorrecta**); capturar exit code y stderr.
  3. Verificar: exit ≠ 0, `INTERNAL_ERROR` en stderr, sin material secreto en el mensaje; el almacenamiento cifrado quedó **intacto** (no se sobrescribió con un seed nuevo).
  4. Variante equivalente si la credencial no es manipulable: corromper un byte del blob cifrado en el almacenamiento de la instancia descartable y re-arrancar.
- **Evidencia mínima:** comandos + exit codes + stderr + constatación del blob intacto.
- **Criterio:** PASA si y sólo si el arranque aborta con esa señal sin regenerar ni operar sin seed. FALLA si arranca igual, regenera un seed nuevo, o el error filtra material secreto. NO_EVALUABLE típico: `PRECONDICION_IMPOSIBLE` (ni credencial ni blob manipulables — documentar el intento).

### AT-06-01-12
- **Familia:** F4
- **Propiedad:** la persistencia del seed cifrado es atómica: si el proceso muere
  durante la escritura, al reiniciar el estado es "sin seed" (re-provisiona) o "seed
  completo y descifrable"; nunca un seed parcial interpretado como válido; el seed se
  considera provisionado sólo si puede leerse y descifrarse (HU-06-01 RN-9).
- **Pasos:**
  1. Localizar la escritura del seed (`grep -rni "seed\|rename\|fsync\|tmp\|atomic" $COPIA_EVAL` en el módulo de provisioning/almacenamiento).
  2. Verificar el mecanismo atómico: transacción de BD, o escritura a archivo temporal + `fsync` + `rename` atómico (no escritura directa sobre el destino).
  3. Verificar el criterio de "provisionado": al cargar, un blob ilegible/no descifrable no se interpreta como seed válido (el tag GCM actúa de verificación, RN-6) — un blob truncado debe fallar el descifrado y disparar RN-11, no adoptarse.
- **Evidencia mínima:** archivo:líneas del mecanismo de escritura y de la carga/verificación.
- **Criterio:** PASA si y sólo si la escritura es atómica (transacción o fsync+rename) y la carga sólo acepta un blob que descifra correctamente. FALLA si escribe directo sobre el destino sin atomicidad (posible seed parcial) o la carga acepta blobs sin verificar. NO_EVALUABLE típico: `FUNCION_NO_LOCALIZABLE`.

### AT-06-01-13
- **Familia:** F5
- **Propiedad:** smoke test de integridad al arrancar: con mapeo `cuenta→address_index`
  no vacío, el sistema deriva el índice más bajo y compara con la dirección persistida;
  ante mismatch (seed corrupto/restaurado mal) se detiene con error crítico **antes**
  de procesar operaciones, sin regenerar (HU-06-01 RN-10/RN-11, Escenario 13).
- **Pasos:**
  1. Levantar instancia descartable limpia; crear una cuenta (mapeo no vacío); detenerla.
  2. Simular la corrupción en el almacenamiento de la instancia descartable: editar la **dirección persistida** del índice más bajo (cambiar un carácter hex manteniendo formato) — así el seed cargado ya no deriva esa dirección.
  3. Re-arrancar; verificar que aborta con error crítico antes de servir (exit ≠ 0 o rechazo de toda operación), sin regenerar seed ni reasignar direcciones.
  4. **Fallback:** F1 — localizar en el arranque la verificación RN-10 (deriva el índice más bajo del mapeo y compara con lo persistido; mismatch ⇒ abort). Si la verificación **no existe** en el código, el veredicto es FALLA aunque el paso 3 no se haya podido ejecutar.
- **Evidencia mínima:** comandos + diff declarado de la corrupción + exit/comportamiento observado (o archivo:líneas de la verificación).
- **Criterio:** PASA si y sólo si el arranque verifica seed↔mapeo y aborta ante mismatch sin regenerar. FALLA si arranca y opera con el mismatch, o si no existe verificación de integridad al arranque. NO_EVALUABLE típico: `PRECONDICION_IMPOSIBLE` (almacenamiento no editable y código no concluyente).

### AT-06-02-01
- **Familia:** F2
- **Propiedad:** KAT de la cadena completa BIP-39→BIP-32/BIP-44→dirección:
  `MNEMONIC_HARDHAT` (passphrase vacía), path `m/44'/60'/0'/0/0` ⇒
  `0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266` (HU-06-02 RN-1..RN-4, Escenario 1).
- **Pasos:**
  1. Localizar la cadena de derivación del SUT (mnemonic→seed→clave del path→dirección EIP-55).
  2. Driver en `$COPIA_TMP` que la invoque con el vector (si la función interna toma `(seed, index)`, derivar la seed con la función mnemonic→seed del propio SUT) y emita la dirección.
  3. Comparar exactamente (checksum EIP-55 incluido, carácter a carácter) con la tabla de HU-06-02. Referencias normativas: `corpus/documentos/bip-0032.mediawiki` (CKDpriv/master key), `bip-0044.mediawiki` (niveles del path), `erc-55.md` (checksum).
  4. Alternativa F6: KAT propio del SUT con el mismo vector, revisado y ejecutado.
- **Evidencia mínima:** driver/test + comando + dirección obtenida.
- **Criterio:** PASA si y sólo si la dirección coincide exactamente. FALLA si difiere (incluido checksum EIP-55 incorrecto). NO_EVALUABLE típico: `HERRAMIENTA_FALTANTE` o `FUNCION_NO_LOCALIZABLE`.

### AT-06-02-02
- **Familia:** F2
- **Propiedad:** KAT de los índices 1..3 con `MNEMONIC_HARDHAT`:
  `0x70997970C51812dc3A010C7d01b50e0d17dc79C8`,
  `0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC`,
  `0x90F79bf6EB2c4f870365E785982E1f101E93b906`; índices distintos ⇒ direcciones
  distintas (HU-06-02 Escenario 2).
- **Pasos:**
  1. Extender el driver de AT-06-02-01 a los índices 1, 2 y 3.
  2. Comparar las tres direcciones con la tabla de HU-06-02 (igualdad exacta) y verificar que las cuatro (0..3) son distintas entre sí.
- **Evidencia mínima:** comando + las tres direcciones obtenidas.
- **Criterio:** PASA si y sólo si las tres coinciden exactamente con la tabla. FALLA si cualquiera difiere. NO_EVALUABLE típico: `HERRAMIENTA_FALTANTE`.

### AT-06-02-04
- **Familia:** F1
- **Propiedad:** el path es `m/44'/60'/0'/0/address_index` con `purpose`, `coin_type` y
  `account` **hardened** (índices efectivos `2147483692`, `2147483708`, `2147483648`;
  offset `0x80000000`) y `change`/`address_index` **no** hardened (HU-06-02 RN-2).
- **Pasos:**
  1. `grep -rni "44'\|m/44\|0x80000000\|2147483648\|hardened\|coin_type\|coinType" $COPIA_EVAL`.
  2. Si el SUT construye el path como string (`"m/44'/60'/0'/0/" + i`) delegando en una librería BIP-32/44: el literal exacto del path es evidencia suficiente del hardening (el apóstrofe marca hardened según `corpus/documentos/bip-0032.mediawiki` §"The key tree" y `bip-0044.mediawiki` §"Path levels").
  3. Si construye índices numéricos: verificar el offset 2³¹ aplicado exactamente a los tres primeros niveles y no a los dos últimos.
- **Evidencia mínima:** archivo:líneas de la construcción del path/índices + cita del corpus.
- **Criterio:** PASA si y sólo si el path es exactamente `m/44'/60'/0'/0/index` con ese hardening. FALLA si difiere en cualquier nivel (coin_type ≠ 60, account no hardened, address_index hardened, etc.). NO_EVALUABLE típico: `FUNCION_NO_LOCALIZABLE`.

### AT-06-02-05
- **Familia:** F2
- **Propiedad:** la derivación es una función pura de `(seed, path)`: en momentos y
  **procesos distintos** produce idéntica clave pública y dirección (HU-06-02 RN-5, INV-8).
- **Pasos:**
  1. Ejecutar el driver de AT-06-02-01 (índice 0) **dos veces en procesos separados** y comparar las direcciones.
  2. F1 complementario: inspección breve del camino de derivación para confirmar que no interviene RNG, reloj ni estado mutable.
- **Evidencia mínima:** los dos comandos + salidas idénticas.
- **Criterio:** PASA si y sólo si ambos procesos producen la misma dirección y el camino no depende de estado mutable. FALLA si difieren. NO_EVALUABLE típico: `HERRAMIENTA_FALTANTE`.

### AT-06-02-06
- **Familia:** F3
- **Propiedad:** tras un reinicio, las direcciones de los índices ya derivados se
  reconstruyen idénticas (HU-06-02 RN-5, INV-8).
- **Pasos:**
  1. En la instancia principal, con ≥ 2 cuentas existentes (crearlas si hace falta), registrar `GET /deposit-address?asset=ETH` de cada una.
  2. Reiniciar con `SUITE_CMD_REINICIO_SUT` (puede ser el mismo reinicio que AT-06-03-06 si los "Dado" ya estaban construidos; declararlo).
  3. Repetir las consultas y comparar dirección por dirección.
- **Evidencia mínima:** pares de direcciones antes/después + comando de reinicio.
- **Criterio:** PASA si y sólo si todas las direcciones son idénticas tras el reinicio. FALLA si alguna cambia. NO_EVALUABLE típico: `SUT_NO_ARRANCA`.

### AT-06-02-08
- **Familia:** F1
- **Propiedad:** ante `I_L ≥ n` o `k_hijo = 0` en un paso CKDpriv (probabilidad
  ~2⁻¹²⁷), el índice se considera inválido y se **avanza al siguiente** de forma
  determinista, registrando el índice efectivamente usado (HU-06-02 RN-8;
  HU-06-03 RN-1).
- **Pasos:**
  1. `grep -rni "0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6\|curve order\|IL\|I_L\|invalid.*key\|ki\b" $COPIA_EVAL` (código propio y librería BIP-32 utilizada, incluidas sus fuentes vendoreadas).
  2. Verificar que el chequeo existe (propio o de la librería: típicamente lanza un error en ese caso) — contrastar con `corpus/documentos/bip-0032.mediawiki` §"Private parent key → private child key" ("In case parse256(IL) ≥ n or ki = 0 … proceed with the next value for i").
  3. Verificar que el SUT **maneja** esa condición avanzando al siguiente índice de forma determinista y registrando el índice usado (no un crash sin manejo, no ignorar la condición).
  4. F6 opcional: test propio con mock de HMAC-SHA512 que fuerce la condición.
- **Evidencia mínima:** archivo:líneas del chequeo (propio o de la librería) y del manejo del salto; cita del corpus.
- **Criterio:** PASA si y sólo si la condición se detecta (chequeo propio o delegado) y el SUT avanza al siguiente índice de forma determinista y registrada. FALLA si la condición se ignora (usaría una clave inválida) o no hay manejo (el error abortaría la asignación sin salto). NO_EVALUABLE típico: `FUNCION_NO_LOCALIZABLE` (librería ilegible).

### AT-06-02-09
- **Familia:** F1
- **Propiedad:** un `address_index ≥ 2³¹` (= 2147483648) se rechaza con
  `VALIDATION_ERROR` (422) y `details.issues` señalando `address_index`, **antes** de
  derivar; `2³¹ − 1` (= 2147483647) se acepta (HU-06-02 RN-9).
- **Pasos:**
  1. `grep -rni "2147483647\|2147483648\|0x7fffffff\|2 \*\* 31\|1 << 31\|MAX.*INDEX" $COPIA_EVAL`.
  2. Verificar la validación de rango en la función de derivación/asignación: rechazo con `VALIDATION_ERROR` y `details.issues` con `address_index`, **antes** de invocar la derivación; el borde correcto (≥ 2³¹ rechaza, 2³¹−1 pasa).
  3. F6 opcional: test propio de bordes; revisarlo y ejecutarlo.
- **Evidencia mínima:** archivo:líneas de la validación con su borde y su error.
- **Criterio:** PASA si y sólo si la validación existe con el borde exacto y el error prescripto, previa a la derivación. FALLA si no valida (derivaría hardened en silencio), el borde está corrido, o el error es otro. NO_EVALUABLE típico: `FUNCION_NO_LOCALIZABLE`.

### AT-06-03-03
- **Familia:** F1
- **Propiedad:** en estado limpio, dos cuentas creadas secuencialmente reciben
  `address_index` 0 y 1 (contiguos, sin huecos) y direcciones distintas
  (HU-06-03 RN-1/RN-5, Escenario 3).
- **Pasos:**
  1. Levantar una instancia descartable desde `$COPIA_TMP` con almacenamiento limpio.
  2. Crear la cuenta A y después la cuenta B (`POST /auth/register`, secuencial).
  3. Leer el **mapeo persistido** (tabla/colección de asignaciones; localizarla con `grep -rni "address_index\|addressIndex\|derivation" $COPIA_EVAL`): A → índice 0, B → índice 1; direcciones distintas y con formato EIP-55.
  4. Destruir la instancia.
- **Evidencia mínima:** comandos + los dos registros persistidos leídos.
- **Criterio:** PASA si y sólo si los índices son exactamente 0 y 1 (en orden de alta) y las direcciones difieren. FALLA si la numeración no arranca en 0, hay huecos, se reusa índice o las direcciones coinciden. NO_EVALUABLE típico: `SUT_NO_ARRANCA` o `FUNCION_NO_LOCALIZABLE` (mapeo ilegible).

### AT-06-03-06
- **Familia:** F3
- **Propiedad:** el mapeo `cuenta → address_index` persiste: tras un reinicio cada
  cuenta conserva el mismo índice y la misma dirección (HU-06-03 RN-7, INV-8).
- **Pasos:**
  1. En la instancia principal, registrar `GET /deposit-address?asset=ETH` de ≥ 2 cuentas existentes (las de AT-06-02-06 sirven).
  2. Reiniciar con `SUITE_CMD_REINICIO_SUT` (puede compartirse con AT-06-02-06; declararlo); esperar readiness.
  3. Repetir las consultas y comparar; opcional: comparar también `addressIndex` en el mapeo persistido antes/después.
- **Evidencia mínima:** pares de direcciones antes/después + comando de reinicio.
- **Criterio:** PASA si y sólo si cada cuenta conserva la misma dirección (y el mismo índice, si se leyó). FALLA si alguna cambia. NO_EVALUABLE típico: `SUT_NO_ARRANCA`.

### AT-06-03-07
- **Familia:** F2
- **Propiedad:** coherencia índice→dirección contra una derivación BIP-44 de referencia
  **sobre el mismo mnemonic**: la dirección asignada a la cuenta con índice `i`
  coincide exactamente con la derivada externamente para `m/44'/60'/0'/0/i`
  (HU-06-03 Escenario 7; HU-06-02).
- **Pasos:**
  1. Levantar una instancia descartable limpia **importando** `MNEMONIC_24_VALIDO` (mecanismo de import del SUT; custodia controlada del mnemonic por el evaluador).
  2. Crear 3 cuentas; registrar sus direcciones (`GET /deposit-address`) y sus índices (mapeo persistido).
  3. Derivación de referencia **externa al SUT**: arrancar un anvil efímero con ese mnemonic (`docker run --rm <imagen foundry del entorno> anvil --mnemonic "abandon … art"`), que imprime las direcciones de `m/44'/60'/0'/0/0..9`; tomarlas como referencia.
  4. Comparar dirección por índice (igualdad exacta, EIP-55 incluido). Referencias normativas: corpus docs `bip-0032.mediawiki`, `bip-0044.mediawiki`, `erc-55.md`.
- **Evidencia mínima:** comandos de ambos arranques + tabla índice→dirección del SUT y de la referencia.
- **Criterio:** PASA si y sólo si todas las direcciones asignadas coinciden con la referencia para sus índices. FALLA si alguna difiere. NO_EVALUABLE típico: `PRECONDICION_IMPOSIBLE` si el SUT no soporta importar mnemonic (RN-5 impide extraer el generado; documentar la búsqueda del mecanismo).

### AT-06-03-08
- **Familia:** F1
- **Propiedad:** el asignador rechaza una cuenta inexistente con `ACCOUNT_NOT_FOUND`
  (404) y `details.accountId`, sin asignar índice ni derivar dirección
  (HU-06-03 RN-10, Escenario 8).
- **Pasos:**
  1. `grep -rni "ACCOUNT_NOT_FOUND" $COPIA_EVAL` y localizar la verificación de existencia de cuenta en el asignador interno.
  2. Verificar que el camino de fallo retorna/lanza ese error **antes** de reservar índice o derivar, y que no muta el mapeo.
  3. F6 opcional: test propio del asignador con cuenta inexistente; revisarlo y ejecutarlo.
- **Evidencia mínima:** archivo:líneas de la guarda y del camino de fallo.
- **Criterio:** PASA si y sólo si la guarda existe con ese código y el camino no asigna ni deriva. FALLA si el asignador asignaría índice a una cuenta inexistente o usa otro código. NO_EVALUABLE típico: `FUNCION_NO_LOCALIZABLE`.

### AT-06-03-09
- **Familia:** F1
- **Propiedad:** asignación **eager**: inmediatamente después del alta de la cuenta —y
  sin ninguna consulta del usuario— existe el registro persistido con `accountId`,
  `addressIndex`, `address` (EIP-55), `derivationPath = m/44'/60'/0'/0/{i}`,
  `network = "sepolia"` y `chainId = "11155111"` (HU-06-03 RN-12, Escenario 9).
- **Pasos:**
  1. En una instancia descartable limpia (puede reutilizarse la de AT-06-03-03 **antes** de destruirla, con una cuenta nueva): `POST /auth/register` y **no** llamar a `GET /deposit-address`.
  2. Leer de inmediato el registro persistido de la asignación y verificar los seis campos.
  3. F1 complementario: localizar en el código el disparo del asignador desde el alta (HU-01-01) — no desde la primera consulta.
- **Evidencia mínima:** comando del alta + el registro persistido leído + archivo:líneas del disparo eager.
- **Criterio:** PASA si y sólo si el registro completo existe tras el alta sin consulta previa. FALLA si la asignación es sólo lazy (aparece recién al consultar) o el registro carece de alguno de los campos requeridos. NO_EVALUABLE típico: `FUNCION_NO_LOCALIZABLE`.

### AT-06-03-10
- **Familia:** F1
- **Propiedad:** al confirmarse una asignación se emite el evento de dominio
  `DepositAddressAssigned { accountId, addressIndex, address, chainId = "11155111" }`
  y/o existe la consulta interna del conjunto de direcciones asignadas (p. ej.
  `GET /internal/deposit-addresses`, no pública), de modo que el monitor de la épica 07
  conoce toda dirección **desde su asignación** (HU-06-03 RN-11, Escenario 10).
- **Pasos:**
  1. `grep -rni "DepositAddressAssigned\|deposit_address_assigned\|internal/deposit" $COPIA_EVAL`.
  2. Verificar el mecanismo hallado: (a) evento con los cuatro campos, emitido tras persistir la asignación, **consumido** por el monitor de depósitos para alimentar su conjunto monitoreado; y/o (b) consulta interna que el monitor lee al arrancar/periódicamente.
  3. Verificar la ausencia de ventana: el monitor no depende de la primera consulta del usuario para conocer una dirección.
- **Evidencia mínima:** archivo:líneas de la emisión/endpoint interno y del punto de consumo en el monitor.
- **Criterio:** PASA si y sólo si existe al menos uno de los dos mecanismos con los campos requeridos y el monitor se alimenta de él desde la asignación. FALLA si no existe mecanismo o el monitor descubre direcciones con ventana (p. ej. sólo cuando el usuario consulta). NO_EVALUABLE típico: `FUNCION_NO_LOCALIZABLE`.

## Épica 07 — Depósitos on-chain (6 ATs)

### AT-07-03-03
- **Familia:** F1
- **Propiedad:** el intento de acreditar/usar un depósito con `confirmaciones < 12` se
  rechaza con `DEPOSIT_NOT_CONFIRMED` (409) y
  `details = { txHash, confirmations, required }`, donde `confirmations` y `required`
  son **enteros JSON** (no strings) y `required = 12`, sin alterar balances
  (HU-07-03 RN-8, Escenario 3).
- **Pasos:**
  1. `grep -rni "DEPOSIT_NOT_CONFIRMED" $COPIA_EVAL` y localizar la guarda de umbral en el pipeline de acreditación.
  2. Verificar: condición `confirmaciones ≥ 12` como precondición de acreditar (borde en 12, cómputo `max(0, cabeza − bloque_inclusión)` según HU-07-03 RN-1/RN-2); el camino de rechazo construye el error con los tres campos y tipos correctos (`confirmations`/`required` numéricos, `txHash` string) y no muta balances.
  3. Confirmar que el `code` está en el catálogo del SUT con status 409.
- **Evidencia mínima:** archivo:líneas de la guarda y de la construcción del error.
- **Criterio:** PASA si y sólo si la guarda de umbral existe con el borde en 12 y el error con esos campos/tipos exactos. FALLA si el código no existe, `details` difiere (montos como string en confirmations, campos faltantes) o la guarda permite acreditar con < 12. NO_EVALUABLE típico: `FUNCION_NO_LOCALIZABLE`.

### AT-07-04-01
- **Familia:** F3
- **Propiedad:** reprocesar una identidad `(txHash, logIndex)` ya `ACREDITADA` (el
  indexador reobserva el bloque tras un reinicio) no vuelve a sumar al balance ni crea
  un segundo depósito; la reobservación se resuelve como `DEPOSIT_ALREADY_CREDITED`
  (HU-07-04 RN-3/RN-8, INV-5).
- **Pasos:**
  1. Producir un depósito USDC acreditado (flujo de AT-02-03-01); registrar `GET /balances` y `GET /deposits` (una entrada, su `depositId`).
  2. Reiniciar con `SUITE_CMD_REINICIO_SUT` (este reinicio puede compartirse con AT-07-04-03/07; construir antes todos los "Dado"); esperar readiness y un ciclo de re-escaneo (el indexador reprocesa desde su checkpoint/`BLOQUE_INICIO`).
  3. Verificar DESPUÉS: balance idéntico; `GET /deposits` sigue mostrando **una** entrada para esa identidad; opcional: el log interno registra `DEPOSIT_ALREADY_CREDITED` o equivalente al reobservar.
- **Evidencia mínima:** respuestas antes/después + comando de reinicio.
- **Criterio:** PASA si y sólo si tras el reinicio no hay segunda acreditación ni duplicado del depósito. FALLA si el balance aumenta de nuevo o aparece un segundo registro con la misma identidad. NO_EVALUABLE típico: `SUT_NO_ARRANCA`.

### AT-07-04-02
- **Familia:** F1
- **Propiedad:** la acreditación es atómica por exclusión mutua en la **capa de
  persistencia**: UNIQUE sobre `(asset, txHash, logIndex)` con
  `INSERT ... ON CONFLICT` (o equivalente), o check+insert dentro de una única
  transacción serializable/lock; dos acreditaciones concurrentes de la misma identidad
  suman una sola vez (HU-07-04 RN-2/RN-4, INV-5).
- **Pasos:**
  1. `grep -rni "UNIQUE\|ON CONFLICT\|unique\|serializable\|FOR UPDATE\|constraint" $COPIA_EVAL` en el módulo de depósitos/esquema de almacenamiento.
  2. Verificar el mecanismo: (a) constraint de unicidad sobre la identidad (incluyendo el activo/tipo, RN-1) con manejo del conflicto como resultado idempotente; o (b) check+insert dentro de una única transacción con serialización (lock/aislamiento); o (c) sección crítica estructuralmente única (un solo hilo/actor escribe acreditaciones, sin punto de suspensión entre check e insert) — un check-then-act con await/llamadas intermedias sin lock **no** califica.
  3. F6 opcional: test de concurrencia propio (dos workers + barrera); revisarlo y ejecutarlo.
- **Evidencia mínima:** archivo:líneas del constraint/transacción/sección crítica y del manejo del duplicado.
- **Criterio:** PASA si y sólo si la garantía vive en persistencia o en una serialización demostrable que cubre check+insert. FALLA si es un check-then-act con ventana de carrera (doble acreditación posible). NO_EVALUABLE típico: `FUNCION_NO_LOCALIZABLE`.

### AT-07-04-03
- **Familia:** F3
- **Propiedad:** variante ETH nativo: identidad `(txHash, logIndex = 0)`; el reproceso
  tras reinicio no reacredita y la identidad se mantiene con `logIndex = 0`
  (HU-07-04 RN-1/RN-3, Escenario 3).
- **Pasos:**
  1. Producir un depósito **ETH** acreditado (transferencia de ETH a la dirección de depósito vía RPC + 12 bloques + esperar `ACREDITADO`); registrar balance y `GET /deposits` (verificar `logIndex: 0` como entero JSON y `depositId` `"<txHash>:0"`).
  2. Compartir el reinicio de AT-07-04-01 (declararlo) o ejecutar uno propio.
  3. Verificar DESPUÉS: balance ETH idéntico, una sola entrada para `(txHash, 0)`.
- **Evidencia mínima:** respuestas antes/después (con el `logIndex` visible) + comando de reinicio.
- **Criterio:** PASA si y sólo si la identidad usa `logIndex = 0` y no hay reacreditación tras el reinicio. FALLA si se duplica la acreditación o la identidad ETH no usa el centinela 0. NO_EVALUABLE típico: `SUT_NO_ARRANCA`.

### AT-07-04-07
- **Familia:** F3
- **Propiedad:** idempotencia persistente: tras reiniciar y **reprocesar los bloques
  históricos**, los depósitos ya acreditados no se reacreditan y los balances
  reconstruidos coinciden con los previos (HU-07-04 RN-8, INV-1/INV-8).
- **Pasos:**
  1. Con ≥ 2 depósitos acreditados (los de AT-07-04-01/03 sirven), registrar todos los balances involucrados y el listado de depósitos.
  2. Compartir el mismo reinicio (declararlo); esperar readiness + un ciclo completo de re-escaneo (dar tiempo/poll hasta que el indexador alcance la cabeza).
  3. Verificar: balances idénticos, mismos depósitos (sin duplicados ni cambios de estado).
- **Evidencia mínima:** respuestas antes/después + comando de reinicio.
- **Criterio:** PASA si y sólo si el reproceso histórico no altera balances ni duplica depósitos. FALLA si algo se reacredita o los balances difieren. NO_EVALUABLE típico: `SUT_NO_ARRANCA`.

### AT-07-04-11
- **Familia:** F3
- **Propiedad:** reanudación desde checkpoint: con checkpoint en `N` y un depósito
  acreditado en bloque ≤ `N`, al reiniciar el escaneo reanuda desde
  `max(BLOQUE_INICIO_CONFIGURADO, N + 1)`; los depósitos del downtime se detectan (no
  se pierden bloques) y los anteriores no se reacreditan (HU-07-04 Escenario 11, INV-8).
- **Pasos:**
  1. Producir el depósito D1 acreditado a un usuario; registrar su balance.
  2. **Detener** el SUT (comando de parada de la entrega operativa; si sólo existe `SUITE_CMD_REINICIO_SUT` atómico, usar el mecanismo de parada del proceso que documente el SUT — declarar cuál).
  3. Durante el downtime: transferir un depósito D2 a la misma dirección y minar ≥ 12 bloques (`anvil_mine`).
  4. Arrancar el SUT; esperar el escaneo; verificar: D2 aparece y se acredita (balance = D1 + D2 exactamente); D1 no se duplica; opcional: leer el checkpoint persistido (≥ N+1, avanzando a la cabeza).
- **Evidencia mínima:** comandos (parada, transferencia, minado, arranque) + balances y listado de depósitos antes/después.
- **Criterio:** PASA si y sólo si D2 (ocurrido con el SUT caído) se detecta y acredita exactamente una vez y D1 no se reacredita. FALLA si D2 se pierde (bloques salteados) o D1 se duplica. NO_EVALUABLE típico: `SUT_NO_ARRANCA` o `PRECONDICION_IMPOSIBLE` (no hay forma documentada de detener el SUT sin relanzarlo de inmediato).

## Épica 08 — Retiros on-chain (4 ATs)

### AT-08-03-08
- **Familia:** F3
- **Propiedad:** tras un reinicio, un retiro ya `BROADCAST` conserva su `(nonce,
  txHash)` —no se re-firma ni se reasigna nonce— y un retiro nuevo de la misma emisora
  toma el nonce siguiente contiguo (HU-08-03 RN-9/RN-11/RN-14, INV-6/INV-8).
- **Pasos:**
  1. Precondición: hot wallet fondeada (precondiciones comunes §6). Fondear un usuario con ETH (depósito acreditado) y crear un retiro (`POST /withdrawals`, asset ETH, dirección externa EIP-55 válida).
  2. Esperar `txHash` no nulo en `GET /withdrawals/{id}` (estado `BROADCAST` o posterior — con anvil automine puede llegar a `CONFIRMED`; la propiedad se verifica igual). Registrar `txHash` y el `nonce` real vía RPC: `eth_getTransactionByHash(txHash).nonce`; registrar `eth_getTransactionCount(emisora, "latest")`.
  3. Reiniciar con `SUITE_CMD_REINICIO_SUT`; esperar readiness.
  4. Verificar: `GET /withdrawals/{id}` conserva el mismo `txHash`; `eth_getTransactionCount(emisora)` no aumentó por el reinicio (no hubo re-firma/re-broadcast de una tx nueva).
  5. Crear un retiro nuevo; verificar que su transacción usa `nonce` = anterior + 1 (contiguo, vía `eth_getTransactionByHash`).
- **Evidencia mínima:** respuestas y consultas RPC antes/después + comando de reinicio + nonce del retiro nuevo.
- **Criterio:** PASA si y sólo si `(nonce, txHash)` del retiro son estables a través del reinicio y el retiro nuevo toma el nonce contiguo siguiente. FALLA si aparece una segunda transacción para el mismo retiro, cambia el `txHash`, o hay hueco/repetición de nonce. NO_EVALUABLE típico: `SUT_NO_ARRANCA`.

### AT-08-03-09a
- **Familia:** F1
- **Propiedad:** intentar firmar/broadcastear como `PENDING` un retiro ya `BROADCAST`
  se rechaza con `CONFLICT` (409) por transición inválida: no se genera ninguna
  transacción nueva ni se reasigna nonce; la idempotencia de RN-9 sólo re-emite la
  **misma** tx ya firmada (HU-08-03 RN-1/RN-9, Escenario 9a).
- **Pasos:**
  1. `grep -rni "CONFLICT\|PENDING\|sign\|broadcast" $COPIA_EVAL` en el servicio de firma/broadcast; localizar la guarda de estado previa a firmar.
  2. Verificar: sólo `status = PENDING` entra al camino de firma; un retiro `BROADCAST` que llegue a ese camino produce `CONFLICT` (409) sin construir/firmar una tx nueva; el único reenvío permitido re-emite la misma raw tx persistida (mismo nonce/txHash).
  3. F6 opcional: test propio de la máquina de estados; revisarlo y ejecutarlo.
- **Evidencia mínima:** archivo:líneas de la guarda y del camino de reenvío idempotente.
- **Criterio:** PASA si y sólo si la guarda restringe la firma a `PENDING` y el estado `BROADCAST` produce `CONFLICT` sin nueva tx. FALLA si no hay guarda (re-firmaría) o el camino genera una transacción/nonce nuevos. NO_EVALUABLE típico: `FUNCION_NO_LOCALIZABLE`.

### AT-08-03-09b
- **Familia:** F1
- **Propiedad:** ídem AT-08-03-09a con el retiro en estado terminal `CONFIRMED`:
  `CONFLICT` (409), sin transacción nueva, estado inmutable (HU-08-03 RN-1, Escenario 9b).
- **Pasos:**
  1. Sobre la guarda localizada en AT-08-03-09a, verificar que el estado `CONFIRMED` está excluido del camino de firma (por lista blanca `PENDING` o rechazo explícito de terminales) y produce `CONFLICT` sin efectos.
  2. Verificar que ningún flujo de reintento/reconciliación (RN-14) re-firma retiros terminales.
- **Evidencia mínima:** archivo:líneas de la guarda cubriendo `CONFIRMED` (o de la lista blanca `PENDING`).
- **Criterio:** PASA si y sólo si un retiro `CONFIRMED` no puede entrar al camino de firma y el intento produce `CONFLICT` sin mutar nada. FALLA si algún camino re-firmaría un retiro `CONFIRMED`. NO_EVALUABLE típico: `FUNCION_NO_LOCALIZABLE`.

### AT-08-03-09c
- **Familia:** F1
- **Propiedad:** ídem con el retiro en estado terminal `FAILED`: `CONFLICT` (409), sin
  transacción nueva, estado inmutable (HU-08-03 RN-1, Escenario 9c).
- **Pasos:**
  1. Sobre la misma guarda, verificar que `FAILED` está excluido del camino de firma y produce `CONFLICT` sin efectos.
  2. Verificar que el reenvío idempotente por API (`POST /withdrawals` con la misma clave) devuelve el retiro `FAILED` existente sin re-firmar (HU-08-01 RN-10), coherente con la guarda.
- **Evidencia mínima:** archivo:líneas de la guarda cubriendo `FAILED`.
- **Criterio:** PASA si y sólo si un retiro `FAILED` no puede re-firmarse y el intento produce `CONFLICT` sin mutar nada. FALLA si algún camino re-firmaría un retiro `FAILED`. NO_EVALUABLE típico: `FUNCION_NO_LOCALIZABLE`.

## Épica 09 — API HTTP/WebSocket (2 ATs)

### AT-09-04-11
- **Familia:** F5
- **Propiedad:** si el token expira con la sesión WS privada abierta, el servidor emite
  `{ error: { code: "UNAUTHENTICATED" } }` y cierra la conexión (código de cierre
  `4001` o equivalente); el cliente debe re-autenticar con token fresco
  (HU-09-04 RN-13, Escenario 11).
- **Pasos:**
  1. Levantar una instancia descartable desde `$COPIA_TMP` con **TTL = 60 s** (mínimo permitido por HU-01-02 RN-3; mecanismo de config del SUT), almacenamiento limpio, resto de config de evaluación.
  2. Registrar usuario + login (token con TTL 60 s); abrir WS (`websocat`/script), enviar `{type:"auth",token}` como primer mensaje, recibir `authenticated`, suscribirse a `orders`.
  3. Mantener la conexión > 60 s respondiendo `pong` a los `ping` del heartbeat; registrar todos los mensajes y el evento de cierre (código).
  4. Verificar: al expirar llega `{ error: { code: "UNAUTHENTICATED" } }` y el socket se cierra (código `4001` o cierre inmediato tras el error); no llegan eventos de usuario después.
  5. **Fallback (si el TTL no es configurable):** F1 — localizar en el servidor WS el chequeo de expiración sobre conexiones activas (timer/deadline por conexión) que emite el error y cierra con `4001`.
- **Evidencia mínima:** comandos + transcripción de mensajes WS con el error y el código de cierre (o archivo:líneas del mecanismo en el fallback).
- **Criterio:** PASA si y sólo si al expirar el token la conexión recibe el error `UNAUTHENTICATED` y se cierra (4001 o equivalente). FALLA si la conexión sigue entregando eventos tras la expiración o se cierra sin el error. NO_EVALUABLE típico: `PRECONDICION_IMPOSIBLE` (TTL no configurable y código WS no concluyente).

### AT-09-05-09
- **Familia:** F1
- **Propiedad:** una falla interna no clasificada responde 500 con el envelope
  `{ error: { code: "INTERNAL_ERROR", message, details? } }` y **sin fuga**: ni stack
  traces, ni secretos, ni internals en `message`/`details` (HU-09-05 RN-9, Escenario 9).
- **Pasos:**
  1. `grep -rni "INTERNAL_ERROR\|error.?handler\|exception\|middleware\|recover" $COPIA_EVAL` y localizar el manejador global de errores (catch-all del framework HTTP y del canal WS).
  2. Verificar: toda excepción no clasificada se mapea a 500 con el envelope uniforme; el `message` es genérico (no interpola `err.message`/stack); `details` no incluye stack/objetos internos; el stack sólo va al log interno.
  3. Verificar que el catch-all está registrado de forma global (no hay rutas fuera de él que devolverían la página de error por defecto del framework).
  4. Refuerzo opcional: en la instancia descartable, editar un handler para lanzar una excepción y observar la respuesta real (declarar la edición).
- **Evidencia mínima:** archivo:líneas del manejador global y de la construcción de la respuesta.
- **Criterio:** PASA si y sólo si existe el manejador global que responde el envelope `INTERNAL_ERROR` (500) sin exponer stack/secretos/internals. FALLA si no hay manejador global (respuesta por defecto del framework) o la respuesta interpola stack/mensajes internos crudos. NO_EVALUABLE típico: `FUNCION_NO_LOCALIZABLE`.

---

## Resumen: familia × cantidad de ATs

| Familia | Descripción breve                                        | ATs |
|---------|-----------------------------------------------------------|-----|
| F1      | Inspección de código / estado persistido interno          | 31  |
| F2      | Criptografía / KATs contra funciones internas             | 6   |
| F3      | Ciclo de vida del SUT (reinicio orquestado)               | 13  |
| F4      | Inyección de fallo interno / límites transaccionales      | 9   |
| F5      | Config-fault (TTL corto, mnemonic elegido, credencial)    | 7   |
| F6      | Tests propios del generador (evidencia transversal)       | 0 (complementaria) |
| **Total** |                                                         | **66** |

Distribución por épica: 01→3, 02→12, 03→4, 04→4, 05→6, 06→25, 07→6, 08→4, 09→2.

## Regla de agregación y destino de los resultados

- La salida de cada pasada (YAML según `plantilla-resultados.yaml`) se archiva como
  `runs/<id>/no-automatizables/pasada-1.yaml` y `pasada-2.yaml`; las discrepancias
  entre pasadas las arbitra el humano con la evidencia de ambas y firma
  `runs/<id>/no-automatizables/veredicto-final.yaml` (ADR-007 §3–§4).
- Estos veredictos alimentan **exclusivamente** la fila `no_automatizado` del dataset
  de H8. **Nunca** se suman ni se mezclan con los `pasa`/`falla` de
  `resultados-at.csv` de la suite black-box: la métrica principal
  (`pasa / (pasa + falla)`) no los incluye; se reportan aparte con su vía de
  evaluación, como fija el README de la suite y ADR-007.
