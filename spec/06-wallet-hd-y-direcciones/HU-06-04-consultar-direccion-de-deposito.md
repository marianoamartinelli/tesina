# HU-06-04 — Consultar dirección de depósito

- **Epica:** 06 — Wallet HD y Direcciones de Depósito
- **Actor / rol:** Trader autenticado (consumido por cliente web React y cliente mobile
  React Native/Expo)
- **Prioridad:** Alta
- **Dependencias:** HU-06-03 (asignación de dirección), HU-01-02 (inicio de sesión) y
  HU-01-03 (cierre/expiración de sesión) para la autenticación; épica 09 HU-09-01 RN-10
  (contrato REST del endpoint `GET /api/v1/deposit-address`)
- **Estandares de dominio aplicables:** EIP-55 (formato de la dirección devuelta), coin
  type 60 (BIP-44, informativo), EIP-155 / chainId 11155111 (red de la dirección). Red
  única: Sepolia.

## Historia
Como **Trader autenticado**, quiero **consultar mi dirección de depósito por activo/red**,
para **saber a qué dirección enviar mis ETH o USDC y poder fondear mi cuenta del exchange**.

## Contexto y alcance
Esta HU cubre el **endpoint de consulta** (HTTP) que devuelve, para la cuenta autenticada,
su dirección de depósito junto con el activo y la red consultados. La dirección es la misma
para ETH y USDC (misma EOA en Sepolia). Si la cuenta aún no tiene dirección asignada, la
consulta dispara la asignación **idempotente** de HU-06-03 y devuelve la dirección
resultante. El consumo desde el frontend (mostrar dirección, copiar, QR) corresponde a las
épicas 10/11; aquí se fija el **contrato de datos** y las reglas de acceso.

**No cubre:** la asignación interna en detalle (HU-06-03), la detección/acreditación de
depósitos (épica 07), ni la UI concreta (épicas 10/11).

**Supuesto:** la autenticación y la identidad de cuenta provienen de la épica 01.

**Contrato del endpoint (épica 09 HU-09-01 RN-10).** La consulta es
`GET /api/v1/deposit-address?asset=ETH|USDC`, autenticada. La **identidad de la cuenta se
deriva exclusivamente del token** de la sesión: el endpoint **no acepta ningún selector de
cuenta** (ni `accountId` por path, query o body). Por construcción, un trader **no puede
direccionar la cuenta de otro**. La respuesta exitosa es **HTTP 200** (no 201: el contrato
de la épica 09 fija 200 para este recurso, incluso cuando la primera consulta dispara la
asignación-fallback de RN-5; no se distingue por status). El cuerpo mínimo exigido por la
épica 09 es `{ asset, address }`; esta HU añade campos informativos (`network`, `chainId`)
según RN-6.

## Reglas de negocio e invariantes
1. **RN-1 (autenticación):** la consulta requiere credencial válida. Sin credencial, o con
   credencial inválida/expirada, se rechaza con `UNAUTHENTICATED` (HTTP 401).
2. **RN-2 (autorización / aislamiento):** la consulta devuelve **únicamente** la dirección
   de la **cuenta autenticada**, cuya identidad se toma **exclusivamente del token** (el
   endpoint no expone selector de cuenta). En consecuencia, leer la dirección de otra cuenta
   es **estructuralmente imposible**: cualquier identificador de cuenta que un cliente
   intente inyectar (query/body) se **ignora** y la respuesta es siempre la dirección del
   dueño del token. Si una variante futura del contrato expusiera un selector de recurso
   ajeno, el acceso al recurso de otra cuenta se rechazaría con `NOT_FOUND` (HTTP 404) sin
   revelar su existencia, conforme a la política de recursos ajenos de
   `00-fundaciones/modelo-de-errores.md` (`UNAUTHORIZED` queda reservado para actuar "a
   nombre de" otra cuenta). En ningún caso se revela la dirección de terceros.
3. **RN-3 (activos soportados):** los activos válidos son `ETH` y `USDC`. Para **ambos**,
   la respuesta contiene **la misma** dirección (misma red, misma EOA). Un activo fuera de
   `{ETH, USDC}` se rechaza con `VALIDATION_ERROR` (HTTP 422) y `details.issues`.
4. **RN-4 (red soportada):** la única red válida es **Sepolia, chainId 11155111**. El
   endpoint canónico (épica 09) solo recibe `asset`; la red es implícitamente Sepolia. Si,
   no obstante, la consulta especificara una red o `chainId` distinto de Sepolia, se rechaza
   con `CHAIN_ID_MISMATCH` (HTTP 422) y `details.expected = "11155111"`,
   `details.got = "<valor recibido>"` (serializados como **string**, ver RN-8). Este uso de
   `CHAIN_ID_MISMATCH` para una solicitud de API está habilitado por la descripción ampliada
   del código en `00-fundaciones/modelo-de-errores.md` (§3.5).
5. **RN-5 (asignación on-demand idempotente — fallback):** la asignación primaria es **eager**
   al crear la cuenta (HU-06-03 RN-12). Esta regla es el **fallback** de consistencia
   eventual: si, excepcionalmente, la cuenta autenticada aún no tuviera dirección asignada,
   la consulta dispara la asignación de HU-06-03 (idempotente) y devuelve la dirección
   resultante con **HTTP 200**. Consultas posteriores devuelven **la misma** dirección (RN-4
   de HU-06-03). La asignación-fallback **no** asigna un segundo índice a una cuenta que ya
   tiene uno.
6. **RN-6 (contrato de respuesta):** la respuesta exitosa incluye, como mínimo (épica 09
   HU-09-01 RN-10): la `address` (string `0x` + 40 hex con **checksum EIP-55**) y el `asset`
   consultado (`"ETH"` o `"USDC"`). Para `asset = USDC` la respuesta incluye **además** el
   campo `tokenAddress`: la dirección del contrato USDC-mock del entorno (string `0x` + 40
   hex con checksum EIP-55), coherente con HU-09-01 RN-10. Esta HU añade, como campos
   **informativos**, la red (`network = "sepolia"`) y el `chainId` (string `"11155111"`);
   opcionalmente el `derivationPath` (dato no secreto). **Nunca** incluye claves privadas ni
   el seed (custodia, HU-06-01/02).
7. **RN-7 (consistencia / idempotencia de lectura):** múltiples consultas de la misma
   cuenta (para el mismo o distinto activo) devuelven **siempre la misma** dirección; la
   consulta no muta el índice asignado.
8. **RN-8 (serialización):** los strings de respuesta siguen las convenciones de
   `00-fundaciones`. La dirección es un string (no un monto). El `chainId` es un
   identificador de red con valor fijado (no un monto monetario) y se **serializa como
   string `"11155111"`** —de forma consistente en el contrato (`RN-4`, `RN-6`), los
   escenarios de aceptación y `details` de error— para evitar ambigüedad de tipo entero vs.
   string en el campo.
9. **RN-9 (precedencia de validación, determinista):** el orden de evaluación es
   `UNAUTHENTICATED` → `UNAUTHORIZED` → esquema/activo (`VALIDATION_ERROR`) → red
   (`CHAIN_ID_MISMATCH`) → asignación/lectura. Se reporta **un solo** error por respuesta
   (el primero según este orden), conforme a `00-fundaciones/modelo-de-errores.md`.

## Criterios de aceptación (DoD)

### Escenario 1: Consulta exitosa para ETH [AT-06-04-01]
- Dado un trader autenticado cuya cuenta tiene dirección de depósito asignada
- Cuando consulta su dirección de depósito para el activo `ETH` en la red Sepolia
- Entonces recibe HTTP 200 con `address` (checksum EIP-55), `asset = "ETH"`,
  `network = "sepolia"` y `chainId = "11155111"` (string, RN-6, RN-8)
- Y la respuesta no contiene clave privada ni seed

### Escenario 2: Misma dirección para USDC [AT-06-04-02]
- Dado el mismo trader del escenario 1
- Cuando consulta su dirección de depósito para el activo `USDC`
- Entonces recibe la **misma** `address` que para `ETH`, con `asset = "USDC"`,
  `chainId = "11155111"` (string, RN-3)

### Escenario 3 (error): Falta de autenticación [AT-06-04-03]
- Dado una solicitud sin credencial válida (ausente, inválida o expirada)
- Cuando se consulta la dirección de depósito
- Entonces se rechaza con `UNAUTHENTICATED` (HTTP 401)
- Y no se revela ninguna dirección (RN-1)

### Escenario 4 (autorización / aislamiento): No se accede a la dirección de otra cuenta [AT-06-04-04]
- Dado dos traders A y B, cada uno con su dirección asignada, y el token de A
- Cuando A consulta `GET /api/v1/deposit-address?asset=ETH` (con su token) e **intenta
  inyectar** un `accountId` de B por query o body
- Entonces el selector inyectado se **ignora** y la respuesta (HTTP 200) contiene la
  dirección de **A**, nunca la de B (RN-2)
- Y no existe ningún parámetro del contrato (épica 09) que permita direccionar la cuenta de
  B; la dirección de B no se revela en ningún caso

### Escenario 5 (error / validación): Activo no soportado [AT-06-04-05]
- Dado un trader autenticado
- Cuando consulta la dirección para un activo distinto de `ETH`/`USDC` (p. ej. `"BTC"`)
- Entonces se rechaza con `VALIDATION_ERROR` (HTTP 422) y `details.issues` indicando el
  activo inválido (RN-3, RN-9)

### Escenario 6 (error / red): chainId distinto de Sepolia [AT-06-04-06]
- Dado un trader autenticado
- Cuando consulta su dirección especificando una red o `chainId` distinto de `11155111`
  (p. ej. `1`)
- Entonces se rechaza con `CHAIN_ID_MISMATCH` (HTTP 422) y
  `details.expected = "11155111"`, `details.got = "1"` (RN-4, RN-9)

### Escenario 7 (borde / fallback): Asignación on-demand en la primera consulta [AT-06-04-07]
- Dado un trader autenticado cuya cuenta **aún no** tiene dirección asignada (caso
  excepcional, ya que la asignación primaria es eager al alta; HU-06-03 RN-12)
- Cuando consulta por primera vez su dirección de depósito
- Entonces el Sistema asigna (idempotentemente, HU-06-03) un índice y devuelve la
  dirección resultante con **HTTP 200** (no 201; RN-5 y contrato épica 09)
- Y una segunda consulta devuelve **la misma** dirección

### Escenario 8 (idempotencia / consistencia): Consultas repetidas [AT-06-04-08]
- Dado un trader autenticado con dirección ya asignada
- Cuando consulta su dirección varias veces, para `ETH` y para `USDC`
- Entonces **todas** las respuestas devuelven exactamente la **misma** dirección
- Y la consulta no altera el `address_index` asignado (RN-7)

### Escenario 9 (concurrencia del fallback): Primera consulta concurrente [AT-06-04-09]
- Dado un trader autenticado **sin** dirección asignada
- Cuando **dos** consultas de su dirección llegan **concurrentemente** (ambas disparan el
  fallback de asignación de RN-5)
- Entonces se asigna **exactamente un** `address_index` a la cuenta (nunca dos índices
  distintos al mismo usuario; HU-06-03 RN-6/RN-12)
- Y **ambas** respuestas son HTTP 200 con la **misma** dirección

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-06-04-01..09) pasan
- [ ] Reglas de negocio RN-1..RN-9 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md
      (`UNAUTHENTICATED`, `UNAUTHORIZED`, `VALIDATION_ERROR`, `CHAIN_ID_MISMATCH`),
      un error por respuesta según la precedencia de RN-9
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md
      (dirección y chainId serializados como strings; sin floats)
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md), en
      particular INV-6 (red Sepolia/EIP-155) e INV-8 (consistencia de la dirección)
- [ ] Adherencia verificada al estándar on-chain citado (dirección con checksum EIP-55,
      chainId 11155111)
