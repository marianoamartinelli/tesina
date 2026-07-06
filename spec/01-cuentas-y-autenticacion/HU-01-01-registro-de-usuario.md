# HU-01-01 — Registro de usuario

- **Epica:** 01 — Cuentas y Autenticación
- **Actor / rol:** Visitante (usuario no autenticado)
- **Prioridad:** Alta
- **Dependencias:** N/A (solo depende de las convenciones de `00-fundaciones`). Es
  dependencia de HU-01-02, HU-01-03, HU-01-04 y de todas las épicas que requieren cuenta.
- **Estandares de dominio aplicables:** N/A (esta HU no tiene componente on-chain;
  BIP-32/39/44 y EIP-155 no aplican).

## Historia
Como visitante del exchange, quiero crear una cuenta con un email y una contraseña válidos,
para obtener una identidad propia a la que asociar mis balances, órdenes, direcciones de
depósito y retiros.

## Contexto y alcance
Cubre el alta de una cuenta nueva a partir de credenciales (email + password): validación
de formato de los datos, **unicidad** de la identidad por email normalizado, creación del
registro de cuenta y definición de su **estado inicial**. El registro **no** inicia sesión
automáticamente: para operar, el usuario debe luego autenticarse (HU-01-02).

No cubre KYC/AML, verificación de email por enlace, MFA, recuperación de contraseña ni
edición/baja de la cuenta (fuera de alcance de la épica). El endpoint de registro es
**público** (no requiere autenticación previa). La persistencia del registro debe sobrevivir
reinicios (`INV-8`), igual que el resto del estado del sistema.

## Reglas de negocio e invariantes

1. **RN-1 (identidad por email único).** El **email normalizado** es la clave única de la
   cuenta. Normalización = `trim` (recorte de espacios al inicio y fin) + `lowercase`
   (minúsculas). No pueden coexistir dos cuentas con el mismo email normalizado; el segundo
   intento se rechaza con `EMAIL_ALREADY_EXISTS` (409). (RNE-1)
   - **Alcance de la deduplicación.** `trim` + `lowercase` es la **única** deduplicación
     soportada en este alcance. Las variantes que corresponden al mismo buzón real pero
     difieren en la parte local —subaddressing (`user+tag@dominio` ≡ `user@dominio`) y dots
     equivalentes de algunos proveedores (`u.s.e.r@gmail.com` ≡ `user@gmail.com`)— **no** se
     normalizan ni se deduplican: se tratan como identidades distintas. Esta limitación se
     documenta explícitamente para que el riesgo (registro de múltiples cuentas sobre el
     mismo buzón) sea visible al evaluar; mitigarlo queda fuera de alcance de la épica.
2. **RN-2 (formato de email).** El email debe ser sintácticamente válido: cumplir el patrón
   `^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$` (exactamente un `@`, parte local no vacía, dominio con
   al menos un punto, sin espacios y **sin** punto inicial/final ni puntos consecutivos en el
   dominio). Si no, `VALIDATION_ERROR` (422). La longitud total del email no debe exceder
   **254** caracteres (un email de exactamente 254 caracteres es **válido**; uno de 255 se
   rechaza). El patrón anterior corrige la versión previa `^[^@\s]+@[^@\s]+\.[^@\s]+$`, que
   aceptaba indebidamente dominios como `a@.b.c` (punto inicial) o `a@b..c` (puntos
   consecutivos), inválidos según RFC 5321.
3. **RN-3 (política de contraseña).** La contraseña debe tener **entre 8 y 128 caracteres**
   (inclusive). Una contraseña fuera de ese rango se rechaza con `VALIDATION_ERROR` (422).
   No se imponen otras reglas de complejidad en este alcance.
4. **RN-4 (campos requeridos y esquema).** El payload debe contener exactamente los campos
   `email` (string) y `password` (string). Campo faltante, tipo incorrecto o campos
   desconocidos se rechazan con `VALIDATION_ERROR` (422) (`details.issues` puede listar las
   causas).
5. **RN-5 (secreto no expuesto ni en claro).** La contraseña se almacena **solo** mediante
   una **función de derivación de clave (KDF) con coste ajustable resistente a ataques GPU**,
   con sal única por cuenta; **nunca** en claro. Algoritmos admitidos y parámetros mínimos:
   - **Argon2id** (recomendado): memoria ≥ 19 MiB, iteraciones ≥ 2, paralelismo ≥ 1; o
   - **bcrypt** con work factor (cost) ≥ 12; o
   - **scrypt** con parámetros de coste equivalentes (N ≥ 2^15, r = 8, p = 1).

   Se **prohíbe explícitamente** usar MD5, SHA-1 o SHA-2 (p. ej. SHA-256) directos —salteados
   o no— como mecanismo de almacenamiento de la contraseña, por ser brute-forceables en GPU.
   La respuesta de registro y cualquier consulta posterior **no** devuelven la contraseña, su
   hash ni su sal. (RNE-2)
6. **RN-6 (estado inicial).** Una cuenta creada exitosamente nace con:
   - `accountId`: identificador estable, único e inmutable (no es el email; no se reutiliza
     aunque la cuenta dejara de existir). Debe ser un identificador **opaco, no secuencial y
     no predecible externamente** (UUID v4, ULID u equivalente con ≥122 bits de entropía); se
     prohíben enteros secuenciales o derivables del timestamp, para prevenir enumeración de
     cuentas. (RNE-6)
   - `status = "ACTIVE"` (único estado modelado en este alcance).
   - `createdAt`: timestamp ISO 8601 en UTC del momento de creación.
   - balances disponible = `"0"` y bloqueado = `"0"` para ETH y USDC (consistente con
     `INV-1`: sin depósitos, la suma de balances de la cuenta es 0). Estos balances son
     **estado interno** de la cuenta (consultable vía la épica 02), **no** forman parte del
     cuerpo de la respuesta de registro (que expone solo identidad: `accountId`, `email`,
     `status`, `createdAt`). El modelo de balances lo detalla la épica 02. (RNE-6)
7. **RN-7 (no auto-login).** El registro **no** emite token de sesión; la respuesta exitosa
   describe la cuenta creada pero no autentica. La autenticación es responsabilidad de
   HU-01-02.
8. **RN-8 (idempotencia / concurrencia de la unicidad).** Ante dos registros concurrentes
   con el mismo email normalizado, a lo sumo **uno** crea la cuenta; el otro se rechaza con
   `EMAIL_ALREADY_EXISTS` (409). No quedan dos cuentas con el mismo email. Toda cuenta que
   exista en el sistema es una **cuenta completa y consultable**: tiene `accountId`, `email`
   normalizado, `status = "ACTIVE"`, `createdAt` y hash de contraseña correctamente
   asignados (no quedan cuentas a medio crear que sean listables pero no consultables).
   (RNE-1, INV consistencia)
9. **RN-9 (precedencia de validación).** Orden determinista de evaluación para el alta:
   (0) rate limiting (`RATE_LIMITED`, cuando está activo, RN-10): se evalúa **antes** de
   cualquier otra validación, incluso la de esquema (mismo criterio que el "paso 0" de la
   épica 04, RE-4); con el límite excedido, una solicitud con payload inválido responde
   **429**, no 422 → (1) esquema/tipos/campos requeridos (`VALIDATION_ERROR`) → (2) formato
   de email (`VALIDATION_ERROR`) → (3) política de contraseña (`VALIDATION_ERROR`) →
   (4) unicidad de email (`EMAIL_ALREADY_EXISTS`). Se reporta **un solo error** (el
   primero). (RNE-7)
10. **RN-10 (rate limiting anti-flood de registro, configurable).** El endpoint de registro
    puede limitar la tasa de altas por origen para prevenir la creación masiva de cuentas
    (account farming), que en un exchange habilita wash trading entre cuentas propias y
    evasión de límites por cuenta. Esta es una regla de **seguridad operativa**,
    independiente del KYC/AML (fuera de alcance). Cuando el rate limiting está activo, sus
    parámetros **umbral N** (solicitudes) y **ventana T** (segundos) son **obligatorios y
    declarados** en la configuración del entorno; al superarse el umbral en la ventana, se
    rechaza con `RATE_LIMITED` (429) y `details.retryAfterSeconds ≥ 0`. Se evalúa como
    **paso 0** de la precedencia (RN-9): antes de cualquier otra validación, incluso la de
    esquema. (Consistente con el rate limiting de login, HU-01-02 RN-9.) El límite por
    cuenta autenticada de HU-09-02 RN-12 **no** aplica a este endpoint (es público, sin
    cuenta); si se implementa rate limiting aquí, usa `RATE_LIMITED`.
11. **RN-11 (persistencia).** La cuenta creada se persiste de forma durable y sobrevive a
    reinicios del sistema (`INV-8`).

## Criterios de aceptación (DoD)

### Escenario 1: Registro exitoso con credenciales válidas [AT-01-01-01]
- Dado un visitante no autenticado y un email `trader@example.com` que no existe en el sistema
- Y una contraseña de 12 caracteres `Sup3rSecreta`
- Cuando envía la solicitud de registro con `email` y `password` válidos
- Entonces la respuesta es exitosa con status HTTP 201
- Y el cuerpo describe la cuenta con `accountId` no vacío, `email = "trader@example.com"`,
  `status = "ACTIVE"` y `createdAt` en formato ISO 8601 UTC
- Y el cuerpo **no** contiene la contraseña, ni su hash, ni su sal, ni ningún token de sesión
- Y el **estado interno** de la cuenta tiene balances iniciales disponible = `"0"` y
  bloqueado = `"0"` para ETH y para USDC (estos balances **no** se incluyen en el cuerpo de
  la respuesta de registro; se consultan vía los endpoints de la épica 02)

### Escenario 2 (borde): Normalización del email (mayúsculas y espacios) [AT-01-01-02]
- Dado que no existe ninguna cuenta con email normalizado `trader@example.com`
- Cuando un visitante se registra con `email = "  Trader@Example.COM  "` y una contraseña válida
- Entonces el registro es exitoso (201) y el email persistido/normalizado es `trader@example.com`
- Y un intento posterior de registrar `email = "TRADER@example.com"` (misma identidad
  normalizada) se rechaza con `EMAIL_ALREADY_EXISTS` (409)

### Escenario 3 (error): Email ya registrado [AT-01-01-03]
- Dado que ya existe una cuenta con email normalizado `trader@example.com`
- Cuando un visitante intenta registrarse con `email = "trader@example.com"` y una contraseña válida
- Entonces la solicitud se rechaza con `EMAIL_ALREADY_EXISTS` y status HTTP 409
- Y `details` incluye `{ "email": "trader@example.com" }`
- Y no se crea una segunda cuenta

### Escenario 4 (error): Formato de email inválido — sin `@` [AT-01-01-04a]
- Dado un visitante no autenticado
- Cuando intenta registrarse con `email = "trader-at-example.com"` (sin `@`) y una contraseña válida
- Entonces la solicitud se rechaza con `VALIDATION_ERROR` y status HTTP 422
- Y no se crea ninguna cuenta

### Escenario 4b (error): Formato de email inválido — dominio sin punto [AT-01-01-04b]
- Dado un visitante no autenticado
- Cuando intenta registrarse con `email = "trader@example"` (dominio sin punto) y una contraseña válida
- Entonces la solicitud se rechaza con `VALIDATION_ERROR` y status HTTP 422
- Y no se crea ninguna cuenta

### Escenario 4c (error): Formato de email inválido — parte local vacía [AT-01-01-04c]
- Dado un visitante no autenticado
- Cuando intenta registrarse con `email = "@example.com"` (parte local vacía) y una contraseña válida
- Entonces la solicitud se rechaza con `VALIDATION_ERROR` y status HTTP 422
- Y no se crea ninguna cuenta

### Escenario 4d (error): Formato de email inválido — espacio interno [AT-01-01-04d]
- Dado un visitante no autenticado
- Cuando intenta registrarse con `email = "a b@example.com"` (espacio interno, no de borde) y una contraseña válida
- Entonces la solicitud se rechaza con `VALIDATION_ERROR` y status HTTP 422
- Y no se crea ninguna cuenta

### Escenario 4e (error): Formato de email inválido — dominio con punto inicial o puntos consecutivos [AT-01-01-04e]
- Dado un visitante no autenticado
- Cuando intenta registrarse con `email = "user@.example.com"` (dominio con punto inicial) y una contraseña válida
- Entonces la solicitud se rechaza con `VALIDATION_ERROR` y status HTTP 422
- Y análogamente, `email = "user@example..com"` (puntos consecutivos en el dominio) también
  se rechaza con `VALIDATION_ERROR` (422)
- Y no se crea ninguna cuenta

### Escenario 5 (error): Contraseña demasiado corta [AT-01-01-05]
- Dado un visitante no autenticado y un email válido inexistente
- Cuando intenta registrarse con una contraseña de 7 caracteres `Abc1234`
- Entonces la solicitud se rechaza con `VALIDATION_ERROR` y status HTTP 422
- Y no se crea ninguna cuenta

### Escenario 6 (error): Contraseña demasiado larga [AT-01-01-06]
- Dado un visitante no autenticado y un email válido inexistente
- Cuando intenta registrarse con una contraseña de 129 caracteres
- Entonces la solicitud se rechaza con `VALIDATION_ERROR` y status HTTP 422
- Y no se crea ninguna cuenta

### Escenario 7 (error): Campo requerido faltante [AT-01-01-07]
- Dado un visitante no autenticado
- Cuando envía un payload sin el campo `password` (solo `email`)
- Entonces la solicitud se rechaza con `VALIDATION_ERROR` y status HTTP 422
- Y `details.issues` referencia el campo faltante `password`
- Y análogamente, un payload sin `email` también se rechaza con `VALIDATION_ERROR`

### Escenario 8 (error): Tipo de dato incorrecto [AT-01-01-08]
- Dado un visitante no autenticado
- Cuando envía `password` como número (`12345678`) en vez de string
- Entonces la solicitud se rechaza con `VALIDATION_ERROR` y status HTTP 422
- Y no se crea ninguna cuenta

### Escenario 9 (precedencia): Email inválido y password inválida simultáneos [AT-01-01-09]
- Dado un visitante no autenticado
- Cuando envía `email = "no-es-email"` (formato inválido) y `password = "123"` (muy corta)
- Entonces se reporta **un solo** error y es `VALIDATION_ERROR` (422)
- Y conforme a la precedencia RN-9, el primer chequeo que falla es el formato de email antes
  que la política de contraseña

### Escenario 10 (concurrencia): Dos registros simultáneos con el mismo email [AT-01-01-10]
- Dado que no existe ninguna cuenta con email `trader@example.com`
- Cuando dos solicitudes de registro con el mismo email normalizado se procesan de forma
  concurrente
- Entonces exactamente **una** crea la cuenta (201) y la otra se rechaza con
  `EMAIL_ALREADY_EXISTS` (409)
- Y al final existe **una sola** cuenta para ese email, en estado `ACTIVE`
- Y esa cuenta es **completa y consultable**: una consulta inmediata posterior devuelve
  `accountId` no vacío, `email` normalizado, `status = "ACTIVE"` y `createdAt` (no queda en
  estado a medio crear, RN-8)

### Escenario 11 (borde): Persistencia tras reinicio [AT-01-01-11]
- Dado que un visitante se registró exitosamente con `trader@example.com`
- Cuando el sistema se reinicia
- Entonces la cuenta sigue existiendo con el mismo `accountId`, `email`, `status = "ACTIVE"` y
  `createdAt`
- Y un nuevo intento de registrar `trader@example.com` se rechaza con `EMAIL_ALREADY_EXISTS`

### Escenario 12 (borde): Contraseña en el límite inferior válido (8 caracteres) [AT-01-01-12]
- Dado un visitante no autenticado y un email válido inexistente
- Cuando se registra con una contraseña de **exactamente 8 caracteres** (p. ej. `Abcd1234`)
- Entonces la respuesta es exitosa con status HTTP 201 y la cuenta queda creada en `ACTIVE`

### Escenario 13 (borde): Contraseña en el límite superior válido (128 caracteres) [AT-01-01-13]
- Dado un visitante no autenticado y un email válido inexistente
- Cuando se registra con una contraseña de **exactamente 128 caracteres**
- Entonces la respuesta es exitosa con status HTTP 201 y la cuenta queda creada en `ACTIVE`

### Escenario 14 (borde): Email en el límite superior válido (254 caracteres) [AT-01-01-14]
- Dado un visitante no autenticado
- Cuando se registra con un email de **exactamente 254 caracteres** y formato válido (p. ej.
  242 veces `a` seguido de `@example.com`) y una contraseña válida
- Entonces la respuesta es exitosa con status HTTP 201 y la cuenta queda creada

### Escenario 15 (error): Email que excede el máximo (255 caracteres) [AT-01-01-15]
- Dado un visitante no autenticado
- Cuando intenta registrarse con un email de **255 caracteres** (p. ej. 243 veces `a`
  seguido de `@example.com`) y una contraseña válida
- Entonces la solicitud se rechaza con `VALIDATION_ERROR` y status HTTP 422
- Y no se crea ninguna cuenta

### Escenario 16 (precedencia): Campo faltante prevalece sobre formato de email [AT-01-01-16]
- Dado un visitante no autenticado
- Cuando envía un payload **sin** el campo `email` y con `password = "123"` (muy corta)
- Entonces se reporta **un solo** error y es `VALIDATION_ERROR` (422) por **campo faltante**
  (nivel 1 de RN-9), no por política de contraseña (nivel 3)
- Y `details.issues` referencia el campo faltante `email`

### Escenario 17 (precedencia): Tipo incorrecto prevalece sobre unicidad de email [AT-01-01-17]
- Dado que ya existe una cuenta cuyo email normalizado coincidiría con el valor enviado
- Cuando envía `email` como **número** (tipo incorrecto) en vez de string, junto a una
  `password` válida
- Entonces se reporta **un solo** error y es `VALIDATION_ERROR` (422) por **tipo incorrecto**
  (nivel 1 de RN-9), no `EMAIL_ALREADY_EXISTS` (nivel 4)

### Escenario 18 (error): Campo desconocido en el payload [AT-01-01-18]
- Dado un visitante no autenticado
- Cuando envía un payload con `email` válido, `password` válida y un campo extra desconocido
  (p. ej. `"role": "admin"`)
- Entonces la solicitud se rechaza con `VALIDATION_ERROR` y status HTTP 422 (RN-4)
- Y `details.issues` referencia el campo desconocido
- Y no se crea ninguna cuenta

### Escenario 19 (borde): El `accountId` es opaco y no secuencial [AT-01-01-19]
- Dado que se registran dos cuentas consecutivas con emails válidos distintos
- Entonces cada `accountId` es un string no vacío
- Y los dos `accountId` son **distintos** entre sí
- Y **no** son secuenciales ni difieren en un patrón predecible (no son enteros consecutivos
  ni derivables del timestamp); para la **misma** cuenta, consultas sucesivas devuelven el
  **mismo** `accountId` (RN-6, RNE-6)

### Escenario 20 (seguridad, condicional a config): Anti-flood de registro [AT-01-01-20]
- Dado que el sistema tiene rate limiting de registro activo con umbral `N` solicitudes por
  origen en ventana `T` segundos (ambos leídos de la configuración del entorno de test)
- Cuando se realizan `N+1` solicitudes de registro desde el mismo origen dentro de la ventana `T`
- Entonces la solicitud `N+1` se rechaza con `RATE_LIMITED` (429) y `details.retryAfterSeconds ≥ 0`
- (Si el rate limiting no está activo en el entorno, este AT no aplica; RN-10)

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptacion (AT-*) pasan
- [ ] Reglas de negocio RN-1..RN-11 verificadas
- [ ] Algoritmo de hash de contraseña conforme a estándar de dominio (Argon2id/bcrypt/scrypt
      con los parámetros mínimos de RN-5; MD5/SHA-1/SHA-2 directos prohibidos) — verificado
      por inspección de código
- [ ] `accountId` opaco y no secuencial (RN-6) verificado
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md)
- [ ] (si aplica) Adherencia verificada al estandar on-chain citado — N/A en esta HU
