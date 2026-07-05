# HU-01-02 — Inicio de sesión

- **Epica:** 01 — Cuentas y Autenticación
- **Actor / rol:** Usuario registrado (visitante con cuenta `ACTIVE`)
- **Prioridad:** Alta
- **Dependencias:** HU-01-01 (la cuenta debe existir). Es dependencia de HU-01-03,
  HU-01-04 y de toda operación autenticada de las épicas 02..08.
- **Estandares de dominio aplicables:** N/A (no hay componente on-chain en esta HU).

## Historia
Como usuario registrado, quiero iniciar sesión con mis credenciales y recibir un token de
sesión con expiración, para poder autenticar mis llamadas posteriores y operar en el
exchange.

## Contexto y alcance
Cubre la verificación de credenciales (email + password) contra una cuenta existente y la
**emisión de un token de sesión** con expiración (TTL). El token es el mecanismo con el que
el cliente autentica las llamadas protegidas (se presenta típicamente como `Authorization:
Bearer <token>`; el contrato exacto de transporte lo fija `09-api-http-websocket`). El
esquema interno del token (opaco o JWT) es libre para la implementación mientras cumpla las
reglas e invariantes de esta épica.

No cubre MFA, recuperación de contraseña ni el flujo de logout/expiración (HU-01-03). El
endpoint de login es **público**. Una preocupación central es **no filtrar la existencia de
cuentas** (RNE-3).

## Reglas de negocio e invariantes

1. **RN-1 (verificación de credenciales).** El login recibe `email` y `password`. El email
   se normaliza (`trim` + `lowercase`, igual que en el registro) y se busca la cuenta. El
   acceso se concede solo si existe una cuenta para ese email normalizado **y** la
   contraseña verifica contra el hash almacenado.
2. **RN-2 (no enumeración de cuentas).** Si el email no existe **o** la contraseña es
   incorrecta, la respuesta es **idéntica**: `INVALID_CREDENTIALS` (401), sin `details` que
   revele cuál de las dos causas ocurrió. No debe poderse inferir si el email existe.
   (RNE-3)
3. **RN-3 (emisión de token con expiración).** Ante credenciales válidas, se emite un token
   de sesión que:
   - es de **alta entropía y no adivinable** (no deriva trivialmente del email ni de datos
     públicos), con criterios objetivos según el esquema:
     - **token opaco:** ≥ **128 bits** de entropía generados con un **CSPRNG** del sistema
       operativo (p. ej. `crypto.randomBytes` en Node, `secrets.token_bytes` en Python).
     - **JWT:** firmado con **RS256** o **ES256** (clave RSA ≥ 2048 bits o EC P-256); si se
       usa HS256, el secreto debe tener ≥ 256 bits generado con CSPRNG.
     - Se **prohíbe** usar `Math.random()`/`Date.now()` como única fuente de entropía y los
       UUID v1/v3 (timestamp/MD5) como token.
   - tiene un instante de expiración `expiresAt` (**TTL configurable**, entero positivo en
     segundos dentro del rango **[60, 86400]** = 1 minuto a 24 horas; valor por defecto del
     proyecto: **3600 segundos** = 1 hora desde la emisión). Un TTL fuera de ese rango (≤ 0,
     negativo o excesivo) es un **error de configuración** que debe impedir el arranque del
     servicio (no se inicia en estado inválido).
   - queda asociado a la `accountId` de la cuenta autenticada.
   La respuesta incluye el token y su `expiresAt` (ISO 8601 UTC). La verificación de la
   entropía/CSPRNG se delega a inspección de código (DoD); el AT-01-02-10 actúa como
   heurística observable mínima. (RNE-4)
4. **RN-4 (secreto no expuesto).** La respuesta de login **no** incluye la contraseña ni su
   hash. El token es el único secreto que se entrega, y solo al titular que prueba las
   credenciales. (RNE-2)
5. **RN-5 (token funcional inmediato).** El token emitido autentica de inmediato las
   llamadas protegidas; presentado en un endpoint protegido antes de su expiración, la
   solicitud se procesa como autenticada por la cuenta correspondiente.
6. **RN-6 (sesiones múltiples).** Logins sucesivos exitosos de la misma cuenta emiten
   tokens **distintos** y todos válidos hasta su expiración o invalidación individual
   (HU-01-03). El login no invalida sesiones previas.
7. **RN-7 (esquema del payload).** El payload debe contener `email` (string) y `password`
   (string). Esquema inválido (campo faltante, tipo incorrecto) ⇒ `VALIDATION_ERROR` (422).
8. **RN-8 (precedencia de validación).** Orden determinista: (0) rate limiting
   (`RATE_LIMITED`, cuando está activo, RN-9): se evalúa **antes** de cualquier otra
   validación, incluso la de esquema (mismo criterio que el "paso 0" de la épica 04, RE-4);
   con el límite excedido, la solicitud `N+1` con payload inválido responde **429**, no 422
   → (1) esquema/tipos (`VALIDATION_ERROR`) → (2) verificación de credenciales
   (`INVALID_CREDENTIALS`). Un solo error por respuesta. (RNE-7)
9. **RN-9 (rate limiting anti-fuerza-bruta, opcional por config).** El endpoint puede
   limitar intentos por email/origen. Al superarse el umbral, `RATE_LIMITED` (429) con
   `details.retryAfterSeconds`. Se evalúa como **paso 0** de la precedencia (RN-8): antes de
   cualquier otra validación, incluso la de esquema. El rate limiting no debe revelar la
   existencia del email (se aplica de forma uniforme).
10. **RN-10 (estado de la cuenta).** En este alcance solo existe el estado `ACTIVE`; toda
    cuenta registrada puede autenticarse. (La gestión de estados como suspensión queda
    fuera de alcance de la épica.)
11. **RN-11 (el login no valida el formato del email).** En el login **no** se valida la
    sintaxis del email. Cualquier string —independientemente de su formato (p. ej.
    `"no-es-email"`, una cadena sin `@`)— pasa la validación de esquema del paso 1 (tipo
    `string` correcto) y se trata como un intento de autenticación que se resuelve en el
    paso 2. El login **no** debe agregar validaciones de formato que retornen
    `VALIDATION_ERROR`, porque la diferencia de respuesta entre "email con formato inválido"
    y "email con formato válido pero inexistente" filtraría información y violaría RNE-3.
    Ambos casos resuelven en `INVALID_CREDENTIALS` (401), indistinguibles entre sí. (RNE-3)
12. **RN-12 (verificación en tiempo constante — anti timing attack).** La verificación de
    credenciales se realiza en **tiempo constante respecto de si el email existe o no**:
    cuando el email **no** existe, el servidor ejecuta una operación de **hash dummy** de
    coste equivalente al KDF configurado (mismos parámetros que HU-01-01 RN-5) antes de
    responder, de modo que el tiempo de procesamiento sea estadísticamente indistinguible
    del caso "email existe + contraseña incorrecta". Esto cierra el **canal lateral de
    tiempo** que de otro modo permitiría enumerar emails sin violar RN-2 textualmente.
    (RNE-3)

## Criterios de aceptación (DoD)

### Escenario 1: Login exitoso [AT-01-02-01]
- Dado que existe una cuenta `ACTIVE` con email `trader@example.com` y contraseña `Sup3rSecreta`
- Cuando el usuario hace login con `email = "trader@example.com"` y `password = "Sup3rSecreta"`
- Entonces la respuesta es exitosa con status HTTP 200
- Y el cuerpo incluye un `token` no vacío y un `expiresAt` en ISO 8601 UTC posterior al
  instante actual
- Y el cuerpo **no** incluye la contraseña ni su hash

### Escenario 2 (borde): Email con distinta capitalización y espacios [AT-01-02-02]
- Dado que existe una cuenta cuyo email normalizado es `trader@example.com`
- Cuando el usuario hace login con `email = "  TRADER@Example.com "` y la contraseña correcta
- Entonces el login es exitoso (200) y autentica la misma cuenta (el email se normaliza antes
  de buscar)

### Escenario 3 (borde): El token autentica una llamada protegida [AT-01-02-03]
- Dado un login exitoso que devolvió un `token` válido y no expirado
- Cuando el usuario invoca un endpoint protegido (p. ej. la consulta de perfil de HU-01-04)
  presentando ese `token`
- Entonces la llamada se procesa como autenticada por la cuenta correspondiente (no devuelve
  `UNAUTHENTICATED`)

### Escenario 4 (error): Contraseña incorrecta [AT-01-02-04]
- Dado que existe una cuenta `ACTIVE` con email `trader@example.com`
- Cuando el usuario hace login con `email = "trader@example.com"` y una contraseña incorrecta
- Entonces la solicitud se rechaza con `INVALID_CREDENTIALS` y status HTTP 401
- Y la respuesta no revela que el email existe (sin `details` discriminante)
- Y no se emite ningún token

### Escenario 5 (error): Email inexistente — respuesta indistinguible [AT-01-02-05]
- Dado que no existe ninguna cuenta con email `desconocido@example.com`
- Cuando un visitante hace login con `email = "desconocido@example.com"` y cualquier contraseña
- Entonces la solicitud se rechaza con `INVALID_CREDENTIALS` y status HTTP 401
- Y la respuesta (code, status y forma) es **indistinguible** de la del Escenario 4
  (contraseña incorrecta sobre un email existente)

### Escenario 6 (error): Payload mal formado [AT-01-02-06]
- Dado un visitante no autenticado
- Cuando envía un login sin el campo `password`
- Entonces la solicitud se rechaza con `VALIDATION_ERROR` y status HTTP 422
- Y no se emite ningún token

### Escenario 7 (precedencia): Esquema inválido tiene prioridad sobre credenciales [AT-01-02-07]
- Dado un visitante no autenticado
- Cuando envía un login con `email` ausente y `password = "loquesea"`
- Entonces se reporta **un solo** error y es `VALIDATION_ERROR` (422), no `INVALID_CREDENTIALS`
  (conforme a la precedencia RN-8)

### Escenario 8 (borde): Sesiones múltiples concurrentes [AT-01-02-08]
- Dado una cuenta `ACTIVE` con credenciales válidas
- Cuando el usuario hace login dos veces seguidas con las mismas credenciales correctas
- Entonces se emiten **dos tokens distintos**, ambos válidos y utilizables en llamadas
  protegidas hasta su expiración
- Y el segundo login no invalida el token del primero

### Escenario 9 (error): Rate limiting tras múltiples fallos [AT-01-02-09]
- Dado que el sistema tiene configurado rate-limiting de login con umbral `N` y ventana `W`
  segundos (ambos **determinables desde la configuración del entorno de test** antes de
  ejecutar el AT), y que se han realizado **exactamente `N` intentos fallidos** dentro de esa
  ventana hacia el mismo email/origen
- Cuando el usuario realiza un intento de login adicional (`N+1`) dentro de la ventana `W`
- Entonces la solicitud se rechaza con `RATE_LIMITED` y status HTTP 429
- Y `details` incluye `retryAfterSeconds`
- Y el comportamiento de rate limiting es uniforme y no revela si el email existe

### Escenario 10 (seguridad): Heurística de entropía del token [AT-01-02-10]
- Dado una cuenta `ACTIVE` con credenciales válidas
- Cuando se emiten **cien tokens** para esa misma cuenta (cien logins exitosos)
- Entonces los cien tokens son **distintos** entre sí
- Y **ningún par** de tokens comparte un prefijo de más de 4 caracteres
  (heurística mínima observable de alta entropía; la verificación formal de ≥128 bits / CSPRNG
  se documenta en el DoD por inspección de código, RN-3)

### Escenario 11 (seguridad): Indistinguibilidad temporal — anti timing attack [AT-01-02-11]
- Dado una cuenta `ACTIVE` con email `trader@example.com` y un email inexistente
  `desconocido@example.com`
- Cuando se miden las latencias de `N = 50` intentos de login a la ruta
  "email inexistente + cualquier contraseña" y de `N = 50` intentos a la ruta
  "email existente + contraseña incorrecta", bajo carga controlada
- Entonces los percentiles **P50 y P95** de ambas rutas no difieren en más del umbral
  definido en la configuración del entorno de test (referencia: < 50 ms), evidenciando la
  ejecución del hash dummy de RN-12 (no hay respuesta "rápida" para email inexistente)

### Escenario 12 (no enumeración): Email con formato inválido en login [AT-01-02-12]
- Dado un visitante no autenticado
- Cuando hace login con un `email` de **formato inválido** (p. ej. `"no-es-email"`, sin `@`,
  tipo `string`) y cualquier contraseña
- Entonces la solicitud se rechaza con `INVALID_CREDENTIALS` (401), **no** con
  `VALIDATION_ERROR`
- Y la respuesta (code, status y forma) es **indistinguible** de la del Escenario 5 (email
  con formato válido pero inexistente), conforme a RN-11 y RNE-3

### Escenario 13 (auditoría): Registro de intentos de autenticación [AT-01-02-13]
- Dado un intento de login exitoso y un intento de login fallido (`INVALID_CREDENTIALS`)
- Cuando se inspecciona el **log de auditoría interno** (RNE-9)
- Entonces ambos quedan registrados con `timestamp` UTC, `email` normalizado, `result`
  (`SUCCESS` / `FAILURE`) y, en el fallido, `reason = INVALID_CREDENTIALS`
- Y el log **no** es accesible desde la API del usuario final (su existencia no viola RNE-3)
- (Verificable por inspección interna; no observable por caja negra en la respuesta de la API)

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptacion (AT-*) pasan
- [ ] Reglas de negocio RN-1..RN-12 verificadas
- [ ] Token con entropía/firma conforme a RN-3 (≥128 bits CSPRNG para opaco; RS256/ES256 o
      HS256 con secreto ≥256 bits para JWT) — verificado por inspección de código
- [ ] TTL validado contra el rango [60, 86400] al arranque (RN-3)
- [ ] Verificación de credenciales en tiempo constante con hash dummy (RN-12)
- [ ] Eventos de autenticación registrados en el log de auditoría interno (RNE-9)
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md — N/A (sin montos)
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md)
- [ ] (si aplica) Adherencia verificada al estandar on-chain citado — N/A en esta HU
