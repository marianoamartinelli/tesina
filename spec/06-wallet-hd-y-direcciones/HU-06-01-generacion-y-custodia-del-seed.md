# HU-06-01 — Generación y custodia del seed HD

- **Epica:** 06 — Wallet HD y Direcciones de Depósito
- **Actor / rol:** Sistema (proceso de provisioning de la wallet HD) / Operador del exchange
- **Prioridad:** Alta
- **Dependencias:** N/A (es la raíz de la épica; las demás HU de 06 dependen de esta)
- **Estandares de dominio aplicables:** BIP-39 (mnemonic + derivación de seed por
  PBKDF2-HMAC-SHA512), BIP-32 (la seed binaria es la raíz de la HD wallet). Coin type
  BIP-44 = 60 (se usa en HU-06-02). Red única: Sepolia, chainId 11155111.

## Historia
Como **Sistema/Operador del exchange**, quiero **generar un seed/mnemonic HD conforme a
BIP-39 con entropía criptográficamente segura y custodiarlo sin exponerlo nunca**, para
**disponer de una raíz determinística única de la que derivar todas las direcciones de
depósito de los usuarios, de forma reproducible y persistente**.

## Contexto y alcance
Esta HU cubre la **creación única** del secreto maestro de la wallet HD del exchange (un
solo seed para todo el exchange), la validación de su conformidad con BIP-39 (entropía,
checksum, longitud de mnemonic) y las reglas mínimas de **custodia**: el seed, el mnemonic
y las claves privadas derivadas no se exponen por la API ni se escriben en logs, y el seed
**persiste** de forma estable entre reinicios.

**No cubre:** la derivación de claves/direcciones hijas (HU-06-02), la asignación a cuentas
(HU-06-03) ni la firma de transacciones (épica 08). Tampoco cubre hardening de producción
(HSM, multi-firma, Shamir, key ceremony), que está **fuera de alcance**; la custodia aquí
es la mínima del caso de estudio.

**Supuestos:** existe un mecanismo de almacenamiento persistente y un CSPRNG del entorno.
El mnemonic puede generarse internamente o importarse desde una configuración segura del
despliegue; en ambos casos debe validar BIP-39.

**Mecanismo de superficie de errores (provisioning).** El provisioning es un **proceso
interno de arranque**, no un endpoint HTTP público. Cuando detecta una condición de error
—mnemonic inválido (RN-2), fallo de descifrado del seed (RN-6), violación de atomicidad
(RN-9) o verificación de integridad fallida (RN-10)— el proceso **aborta con código de
salida distinto de cero** y registra en `stderr` el `code` correspondiente del catálogo
(`VALIDATION_ERROR` para mnemonic inválido; `INTERNAL_ERROR` para fallo de descifrado o de
integridad), **sin filtrar material secreto** y **sin generar ni sobrescribir** un seed.
No se expone un endpoint HTTP para esta operación; el código HTTP del catálogo se usa solo
como identificador estable del tipo de error, no como respuesta de red.

## Reglas de negocio e invariantes
1. **RN-1 (estándar BIP-39, entropía):** el mnemonic se genera a partir de entropía
   producida por un **CSPRNG** del entorno. La entropía fijada para el proyecto es de
   **256 bits**, lo que produce un mnemonic de **24 palabras** del wordlist BIP-39 en
   inglés (2048 palabras). Se admite importar un mnemonic externo solo si cumple BIP-39.
2. **RN-2 (validación BIP-39: normalización, longitud, wordlist y checksum):** antes de
   validar y de derivar la seed (RN-3), el mnemonic y la passphrase se **normalizan a
   Unicode NFKD** (conforme a la sección "Generating the mnemonic" de BIP-39). Para el
   wordlist inglés (ASCII puro) la NFKD es un **no-op**, pero el procesamiento la aplica de
   forma genérica para ser conforme al estándar y robusto ante mnemonics importados de
   sistemas con distinta normalización. Sobre el mnemonic normalizado se valida, en este
   orden: (a) **longitud** = exactamente **24 palabras** (la entropía fijada del proyecto
   es de 256 bits; un mnemonic de 12/15/18/21 palabras, aun con checksum válido para su
   propia entropía, corresponde a otra entropía y **se rechaza**); (b) que **todas** las
   palabras pertenezcan al **wordlist BIP-39 inglés** (2048 palabras); (c) el **checksum**:
   los últimos `ENT/32` bits (8 bits para 256 de entropía) son los primeros `ENT/32` bits
   de `SHA-256(entropía)`. Un mnemonic que falle cualquiera de (a)/(b)/(c) **se rechaza**
   (no se adopta como seed) con `VALIDATION_ERROR` (ver mecanismo de superficie en Contexto
   y alcance).
3. **RN-3 (derivación de la seed binaria, BIP-39):** la seed binaria de 512 bits (64
   bytes) se deriva con `PBKDF2(HMAC-SHA512, password = mnemonic_NFKD,
   salt = "mnemonic" + passphrase_NFKD, iteraciones = 2048, dkLen = 64)`. La `passphrase`
   es opcional; su valor por defecto es la **cadena vacía**. Esta seed es la raíz BIP-32.
4. **RN-4 (wallet única del exchange):** existe **un solo** seed/mnemonic maestro para
   todo el exchange. No se genera un seed por usuario; la individualización por usuario se
   logra por **índice de derivación** (HU-06-02/06-03).
5. **RN-5 (custodia — no exposición):** el mnemonic, la seed binaria y cualquier clave
   privada derivada **nunca** se incluyen en respuestas de la API ni en mensajes de
   WebSocket, ni se escriben en logs, trazas o mensajes de error. Solo claves públicas y
   direcciones (información no secreta) pueden salir del sistema.
6. **RN-6 (almacenamiento cifrado en reposo):** el seed (o el mnemonic) se persiste
   **cifrado en reposo** con cifrado simétrico **autenticado**: **AES-256-GCM** (clave de
   256 bits, **nonce aleatorio de 96 bits** generado por el CSPRNG **por cada operación de
   cifrado**, tag de autenticación de 128 bits). El ciphertext se almacena junto con el
   nonce y el tag (formato `nonce || ciphertext || tag`). La **clave/credencial de cifrado**
   se provee por configuración del entorno (no embebida en el código ni en el repositorio)
   y **nunca** se persiste junto al material cifrado. Al **descifrar**, el sistema **verifica
   el tag**: si el tag no coincide (corrupción, restauración incorrecta) o la credencial es
   ausente/incorrecta, el descifrado **falla** y el sistema **aborta** (RN-11); **no**
   continúa sin seed ni **regenera** uno nuevo. El hardening avanzado (HSM, rotación) queda
   fuera de alcance.
7. **RN-7 (determinismo de la derivación de seed):** el mismo `(mnemonic, passphrase)`
   produce **siempre** la misma seed binaria (función pura de RN-3); no interviene
   aleatoriedad en este paso.
8. **RN-8 (estabilidad / no regeneración — INV-8):** una vez generado, el seed **no se
   regenera** en reinicios ni reaperturas. Tras un reinicio, el sistema usa el mismo seed
   persistido, de modo que todas las direcciones derivadas se reconstruyen idénticas.
9. **RN-9 (atomicidad del provisioning):** la persistencia del mnemonic/seed cifrado es una
   operación **atómica** (commit atómico en la base de datos, write-ahead log, o escritura
   `fsync` + `rename` atómico en filesystem). El seed se considera **"provisionado"** solo
   si puede **leerse y descifrarse** exitosamente (RN-6). Si el proceso muere durante la
   escritura, al reiniciar el estado es **o bien sin seed** (re-ejecuta el provisioning
   correctamente, RN-1) **o bien con un seed completo y válido**; **nunca** queda un seed
   parcialmente escrito.
10. **RN-10 (verificación de integridad al arrancar — smoke test):** al arrancar con un
    seed ya provisionado y un mapeo `cuenta → address_index` **no vacío** (HU-06-03), el
    sistema deriva al menos los **primeros K ≥ 1** pares `(address_index, address)` del mapeo
    persistido (para el caso de estudio, `K = 1`: el índice más bajo asignado) y verifica que
    la derivación desde el seed cargado produce **exactamente** la misma dirección persistida.
    Si **cualquier** verificación falla (seed corrupto o restaurado desde un backup
    incorrecto), el sistema **se detiene con un error crítico** (RN-11) **antes** de procesar
    operaciones; **no** acepta depósitos ni deriva direcciones nuevas con un seed sospechoso.
11. **RN-11 (abort sin regeneración ante fallo crítico):** ante un mnemonic inválido (RN-2),
    un fallo de descifrado del seed (RN-6), una violación de atomicidad (RN-9) o una
    verificación de integridad fallida (RN-10), el sistema **aborta** (código de salida
    distinto de cero, error en `stderr` sin filtrar material secreto). **Nunca** continúa
    operando sin un seed válido ni **regenera** un seed nuevo, porque ambas acciones
    romperían la biyección cuenta ↔ dirección y violarían INV-8.

> **Nota (serialización).** Esta HU no maneja montos; igualmente respeta las convenciones de
> `00-fundaciones/convenciones-monetarias.md` (ningún dato sensible ni numérico cruza la API
> como float). No es una regla de negocio verificable por sí misma.

### Vector de prueba canónico (known-answer test, BIP-39)
Para verificar la correcta implementación del paso PBKDF2 de RN-3 se usa el **vector
canónico BIP-39** (validación del algoritmo, independiente del largo de mnemonic; no es el
seed de producción):

Constante con nombre (usada literalmente en los pasos Gherkin de esta épica para evitar
abreviaturas con elipsis que no son input válido):

- `MNEMONIC_BIP39_CANONICO` = `"abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"`

Vector:

- `mnemonic` = `MNEMONIC_BIP39_CANONICO`
- `passphrase` = `"TREZOR"`
- `seed` (hex, 64 bytes) =
  `c55257c360c07c72029aebc1b53c05ed0362ada38ead3e3e9efa3708e53495531f09a6987599d18264c1e1c92f2cf141630c7a3c4ab7c81b2f001698e7463b04`

## Criterios de aceptación (DoD)

### Escenario 1: Generación de un seed nuevo válido [AT-06-01-01]
- Dado un exchange sin seed previamente provisionado
- Y un CSPRNG disponible en el entorno
- Cuando el Sistema ejecuta la generación de la wallet HD
- Entonces se produce un mnemonic BIP-39 de **24 palabras** del wordlist inglés
- Y el checksum BIP-39 del mnemonic es válido (RN-2)
- Y se deriva una seed binaria de **64 bytes** según PBKDF2-HMAC-SHA512 con 2048
  iteraciones y `passphrase` vacía por defecto (RN-3)
- Y el seed queda persistido cifrado en reposo (RN-6)

### Escenario 2 (reproducibilidad): Known-answer test BIP-39 [AT-06-01-02]
- Dado el mnemonic `MNEMONIC_BIP39_CANONICO`
  (= `"abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"`)
  y `passphrase = "TREZOR"`
- Cuando se deriva la seed binaria según RN-3
- Entonces la seed resultante en hexadecimal es exactamente
  `c55257c360c07c72029aebc1b53c05ed0362ada38ead3e3e9efa3708e53495531f09a6987599d18264c1e1c92f2cf141630c7a3c4ab7c81b2f001698e7463b04`

### Escenario 3 (determinismo): Misma entrada, misma seed [AT-06-01-03]
- Dado un mismo par `(mnemonic, passphrase)` válido
- Cuando se deriva la seed binaria dos veces, en momentos distintos
- Entonces ambas derivaciones producen **byte a byte la misma** seed (RN-7)

### Escenario 4 (entropía): Dos generaciones independientes difieren [AT-06-01-04]
- Dado un CSPRNG correcto
- Cuando se generan dos mnemonics nuevos de forma independiente
- Entonces los dos mnemonics (y sus seeds) son **distintos entre sí** (no hay valor
  fijo/hardcodeado de entropía)
- _(Nota: la probabilidad de colisión de dos entropías de 256 bits es ~2⁻²⁵⁶,
  despreciable en la práctica; el aserto se evalúa como desigualdad estricta.)_

### Escenario 5 (error / borde): Mnemonic con checksum inválido se rechaza [AT-06-01-05]
- Dado un intento de importar un mnemonic de 24 palabras cuyo checksum BIP-39 **no** es
  válido (p. ej. reemplazar la última palabra por otra del wordlist que rompe el checksum)
- Cuando el proceso de provisioning valida el mnemonic (RN-2)
- Entonces el mnemonic es **rechazado** y **no** se adopta como seed
- Y no se persiste ningún seed derivado de ese mnemonic
- Y, dado que el provisioning no es un endpoint HTTP, el proceso **aborta con código de
  salida distinto de cero** y registra en `stderr` el `code` `VALIDATION_ERROR` (catálogo de
  `00-fundaciones/modelo-de-errores.md`), **sin filtrar material secreto** (RN-11)

### Escenario 6 (seguridad / custodia): El secreto nunca se expone [AT-06-01-06]
- Dado un seed/mnemonic ya provisionado
- Cuando un cliente invoca, con respuesta exitosa, **cada uno** de los endpoints
  autenticados que pueden tocar datos derivados del seed —en particular
  `GET /api/v1/deposit-address?asset=ETH|USDC` (épica 09, HU-06-04), `GET /api/v1/balances`,
  `GET /api/v1/me`, `GET /api/v1/deposits` y `GET /api/v1/withdrawals`—
- Entonces en **ninguna** de esas respuestas (HTTP o, donde aplique, WebSocket) aparece un
  campo `mnemonic`, `seed` ni `privateKey` (ni su valor en ningún campo) — solo claves
  públicas y direcciones (RN-5)
- Y un **procedimiento de auditoría estática complementario** (análisis de código o `grep`
  sobre los logs/trazas de una corrida de integración) confirma que el mnemonic, la seed
  binaria y las claves privadas derivadas **no** se escriben en logs, trazas ni mensajes de
  error en **ninguna** superficie, incluidas las no expuestas por API (RN-5)

### Escenario 7 (persistencia): El seed sobrevive a un reinicio [AT-06-01-07]
- Dado un seed ya provisionado y persistido
- Cuando el sistema se reinicia
- Entonces el mismo seed se recupera desde el almacenamiento (no se genera uno nuevo)
- Y las direcciones derivadas posteriormente son **idénticas** a las previas al reinicio
  (RN-8, INV-8)

### Escenario 8 (idempotencia de provisioning): No se regenera el seed [AT-06-01-08]
- Dado un exchange que **ya** tiene un seed provisionado
- Cuando se vuelve a ejecutar el proceso de provisioning de la wallet HD
- Entonces **no** se sobrescribe ni regenera el seed existente
- Y el seed y todas las direcciones derivadas permanecen sin cambios (RN-4, RN-8)

### Escenario 9 (error / borde): Mnemonic con longitud incorrecta se rechaza [AT-06-01-09]
- Dado un intento de importar un mnemonic de **12 palabras** válidas del wordlist BIP-39 y
  con checksum válido para 128 bits de entropía (pero entropía incorrecta para el proyecto,
  que fija 256 bits / 24 palabras)
- Cuando el proceso de provisioning valida el mnemonic (RN-2, regla de longitud)
- Entonces el mnemonic es **rechazado** con `VALIDATION_ERROR` y **no** se adopta como seed

### Escenario 10 (error / borde): Palabra fuera del wordlist se rechaza [AT-06-01-10]
- Dado un mnemonic de **24 palabras** en el que **al menos una** no pertenece al wordlist
  BIP-39 inglés
- Cuando el proceso de provisioning valida el mnemonic (RN-2, regla de wordlist)
- Entonces el mnemonic es **rechazado** con `VALIDATION_ERROR` y **no** se adopta como seed

### Escenario 11 (error / arranque): Fallo de descifrado del seed [AT-06-01-11]
- Dado un seed previamente persistido **cifrado** (RN-6)
- Y que la credencial de descifrado del entorno está **ausente o es incorrecta**, o el
  almacenamiento está corrupto (el tag GCM no verifica)
- Cuando el sistema intenta arrancar y descifrar el seed
- Entonces el proceso **aborta con código de salida distinto de cero**, **sin generar un
  seed nuevo** ni continuar sin seed (RN-6, RN-11)
- Y el error es identificable en `stderr` (`code` `INTERNAL_ERROR`) **sin filtrar** material
  secreto

### Escenario 12 (atomicidad): Crash durante la escritura del seed [AT-06-01-12]
- Dado que el proceso de provisioning muere **durante** la escritura del seed cifrado
- Cuando el sistema reinicia y lee el almacenamiento
- Entonces el estado es **o bien "sin seed"** (y el provisioning se re-ejecuta correctamente
  generando un seed nuevo válido) **o bien "con un seed completo y descifrable"**; **nunca**
  queda un seed parcialmente escrito que se interprete como válido (RN-9)

### Escenario 13 (integridad / arranque): Smoke test del seed contra el mapeo [AT-06-01-13]
- Dado un seed persistido y un mapeo `cuenta → address_index` no vacío (HU-06-03), donde la
  dirección persistida del índice más bajo es conocida (derivada del mnemonic de **24
  palabras** con el que se provisionó el sistema, RN-1/RN-2)
- Y que, por inyección del test harness, el seed cargado **no** deriva esa dirección
  (simulando corrupción o restauración incorrecta)
- Cuando el sistema ejecuta la verificación de integridad al arrancar (RN-10)
- Entonces el sistema **se detiene con un error crítico antes de procesar operaciones**,
  **no** regenera el seed ni acepta depósitos (RN-10, RN-11)

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-06-01-01..13) pasan
- [ ] Reglas de negocio RN-1..RN-11 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md (provisioning aborta
      con `code` en `stderr`, sin endpoint HTTP; ver "Mecanismo de superficie de errores")
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md), en
      particular INV-8 (persistencia/recuperación e integridad del seed)
- [ ] Cifrado en reposo AES-256-GCM verificado (nonce por operación, tag autenticado; abort
      ante fallo de descifrado) (RN-6, RN-11)
- [ ] Adherencia verificada al estándar on-chain citado (BIP-39: NFKD, longitud de mnemonic,
      wordlist, checksum, PBKDF2-HMAC-SHA512/2048/64 bytes; known-answer test AT-06-01-02)
