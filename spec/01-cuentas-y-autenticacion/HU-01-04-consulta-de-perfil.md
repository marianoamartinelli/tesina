# HU-01-04 — Consulta de perfil

- **Epica:** 01 — Cuentas y Autenticación
- **Actor / rol:** Usuario autenticado (titular de un token de sesión vigente)
- **Prioridad:** Media
- **Dependencias:** HU-01-01 (la cuenta existe), HU-01-02 (token de sesión), HU-01-03
  (un token invalidado/expirado no autentica).
- **Estandares de dominio aplicables:** N/A (no hay componente on-chain en esta HU).

## Historia
Como usuario autenticado, quiero consultar los datos y el estado de mi cuenta, para
verificar mi identidad registrada (email, `accountId`, estado y fecha de alta) sin que se
expongan secretos.

## Contexto y alcance
Cubre la lectura del **perfil propio**: identidad (`accountId`, `email`), estado de la
cuenta (`status`) y metadatos (`createdAt`). Es una operación de solo lectura y protegida
(requiere autenticación). El usuario solo puede consultar **su propia** cuenta (RNE-5).

No cubre la edición del perfil (cambio de email/contraseña están fuera de alcance) ni la
exposición de balances: el contrato de perfil de esta épica devuelve **solo identidad**
(`accountId`, `email`, `status`, `createdAt`) y **no** incluye balances. Los balances se
consultan **exclusivamente** por los endpoints de `02-balances-y-ledger`. No expone
contraseña, hash, sal ni tokens (RNE-2).

## Reglas de negocio e invariantes

1. **RN-1 (autenticación requerida).** La consulta de perfil es una operación protegida.
   Sin token válido (ausente, malformado, invalidado o expirado) se rechaza con
   `UNAUTHENTICATED` (401). (RNE-4)
2. **RN-2 (alcance propio).** La consulta resuelve la cuenta a partir del token presentado y
   devuelve **solo** los datos de esa cuenta. Un usuario no puede obtener el perfil de otra
   cuenta.
3. **RN-3 (autorización al acceder a recurso ajeno).** Si la API expone el perfil por
   identificador (p. ej. `/accounts/{accountId}`) y el `accountId` solicitado **no** coincide
   con el de la cuenta autenticada, la solicitud se rechaza con `UNAUTHORIZED` (403) con
   `details = { "resource": ... }`. (No se usa `NOT_FOUND` para no filtrar la existencia de
   otras cuentas.) (RNE-5)
4. **RN-4 (contenido del perfil).** Una respuesta exitosa incluye exactamente los campos de
   identidad: `accountId` (estable), `email` (normalizado), `status` (`"ACTIVE"` en este
   alcance) y `createdAt` (ISO 8601 UTC). Los campos coinciden exactamente con los datos del
   registro (HU-01-01). El perfil **no** incluye balances ni otros montos: los balances se
   consultan exclusivamente por los endpoints de la épica 02.
5. **RN-5 (no exposición de secretos).** La respuesta **nunca** incluye la contraseña, su
   hash, su sal ni ningún token de sesión. (RNE-2)
6. **RN-6 (sin montos en el perfil).** El perfil de esta épica **no** expone balances ni
   montos; por lo tanto no hay serialización monetaria que aplicar en su respuesta. Los
   balances (y su serialización como **string de entero de unidad mínima**, p. ej. `"0"`) son
   responsabilidad de la épica 02. (RNE-8, `convenciones-monetarias.md`)
7. **RN-7 (consistencia / lectura).** La consulta es de solo lectura y no modifica el estado
   de la cuenta ni de la sesión (no extiende ni renueva el TTL del token).
8. **RN-8 (precedencia de validación).** Orden determinista: (1) autenticación
   (`UNAUTHENTICATED`) → (2) autorización sobre el recurso (`UNAUTHORIZED`). Un solo error
   por respuesta. (RNE-7)

## Criterios de aceptación (DoD)

### Escenario 1: Consulta de perfil propio exitosa [AT-01-04-01]
- Dado un usuario autenticado con un token válido para la cuenta `trader@example.com`
- Cuando consulta su perfil presentando el token
- Entonces la respuesta es exitosa con status HTTP 200
- Y el cuerpo incluye `accountId`, `email = "trader@example.com"`, `status = "ACTIVE"` y
  `createdAt` en ISO 8601 UTC
- Y el cuerpo **no** incluye la contraseña, su hash, su sal ni ningún token

### Escenario 2 (borde): Los datos coinciden con el registro [AT-01-04-02]
- Dado una cuenta registrada vía HU-01-01 con email normalizado `trader@example.com`
- Cuando el titular consulta su perfil
- Entonces `accountId`, `email`, `status` y `createdAt` coinciden exactamente con los valores
  asignados en el registro
- Y el `email` devuelto está normalizado (minúsculas, sin espacios de borde)

### Escenario 3 (error): Consulta sin autenticación [AT-01-04-03]
- Dado un cliente que no presenta token (o presenta un token malformado)
- Cuando intenta consultar un perfil
- Entonces la solicitud se rechaza con `UNAUTHENTICATED` y status HTTP 401
- Y no se devuelve ningún dato de cuenta

### Escenario 4 (error): Token expirado o invalidado [AT-01-04-04]
- Dado un token expirado por TTL o invalidado por logout (HU-01-03)
- Cuando se usa para consultar el perfil
- Entonces la solicitud se rechaza con `UNAUTHENTICATED` y status HTTP 401

### Escenario 5 (error): Intento de consultar el perfil de otra cuenta [AT-01-04-05]
- Dado un usuario autenticado como cuenta A con token válido
- Y un `accountId` que pertenece a la cuenta B (distinta de A)
- Cuando solicita el perfil del `accountId` de B (p. ej. `/accounts/{accountId_B}`)
- Entonces la solicitud se rechaza con `UNAUTHORIZED` y status HTTP 403
- Y `details` incluye el `resource` solicitado
- Y no se devuelve ningún dato de la cuenta B

### Escenario 6 (precedencia): Sin token y recurso ajeno [AT-01-04-06]
- Dado un cliente sin token válido que solicita el perfil de un `accountId` ajeno
- Cuando realiza la solicitud
- Entonces se reporta **un solo** error y es `UNAUTHENTICATED` (401), no `UNAUTHORIZED`
  (conforme a la precedencia RN-8: primero autenticación, luego autorización)

### Escenario 7 (borde): La consulta no altera la sesión ni el estado [AT-01-04-07]
- Dado un usuario autenticado con un token cuyo `expiresAt` es conocido
- Cuando consulta su perfil una o varias veces
- Entonces cada respuesta es 200 con los mismos datos
- Y el `expiresAt` del token no cambia (la lectura no renueva el TTL) y el estado de la
  cuenta sigue siendo `ACTIVE`

### Escenario 8 (contrato): El perfil no expone balances [AT-01-04-08]
- Dado un usuario recién registrado (sin depósitos) que consulta su perfil
- Cuando recibe la respuesta exitosa (200)
- Entonces el cuerpo contiene exactamente los campos de identidad (`accountId`, `email`,
  `status`, `createdAt`) y **no** incluye campos de balance ni montos (RN-4, RN-6)
- Y los balances de la cuenta se consultan exclusivamente por los endpoints de la épica 02

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptacion (AT-*) pasan
- [ ] Reglas de negocio RN-1..RN-8 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md — N/A (el perfil no expone montos)
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md)
- [ ] (si aplica) Adherencia verificada al estandar on-chain citado — N/A en esta HU
