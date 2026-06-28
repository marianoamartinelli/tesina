# Épica 01 — Cuentas y Autenticación

## Objetivo de la épica

Gestionar la **identidad** de los usuarios del exchange: registro de cuentas,
autenticación (login), manejo de sesión/token (cierre y expiración) y consulta del propio
perfil. Esta épica es la **base de autorización** del resto del sistema: toda operación de
trading, balances, órdenes, direcciones de depósito y retiros se asocia a una cuenta
autenticada. Si la identidad no es confiable, ningún invariante financiero posterior puede
sostenerse.

La épica fija **cómo** se obtiene y se pierde el derecho a operar (la credencial de
sesión), pero **no** fija el contrato de transporte completo de la API (eso lo hace
`09-api-http-websocket`) ni el modelo de balances (eso lo hace `02-balances-y-ledger`).
Aquí solo se establece que una cuenta recién creada nace con balances en cero, consistente
con `INV-1`.

---

## Alcance

### Dentro de alcance

- **Registro de usuario** con credenciales (email + password): validación de datos,
  unicidad de identidad por email y estado inicial de la cuenta.
- **Inicio de sesión**: verificación de credenciales y emisión de un token/sesión con
  expiración para autenticar llamadas posteriores.
- **Cierre y expiración de sesión**: logout explícito que invalida el token, y expiración
  automática por TTL; efecto sobre operaciones posteriores.
- **Consulta de perfil**: lectura de los datos de identidad y el estado de la cuenta del
  propio usuario autenticado.
- **Autorización básica**: una credencial válida solo da acceso a los recursos de la
  **propia** cuenta.

### Fuera de alcance

- **KYC / AML**: verificación de identidad legal, listas de sanciones, prueba de domicilio,
  etc. No se recolectan ni validan documentos.
- **Recuperación de contraseña**, verificación de email por enlace, MFA/2FA.
- **Edición de perfil** (cambio de email/password) y baja/cierre de cuenta por el usuario.
- **Roles administrativos / RBAC avanzado**: solo existe el rol "usuario" sobre su propia
  cuenta. La cuenta interna de fees del exchange (`EX`) no es una cuenta de usuario y no se
  registra ni autentica por estos flujos.
- **Estados de cuenta más allá de `ACTIVE`** (suspensión, bloqueo, cierre): se modela
  únicamente el estado inicial `ACTIVE`.
- **Hardening de producción**: rotación de secretos, almacenamiento en HSM, políticas de
  contraseña corporativas avanzadas, captcha, etc.

> El backend es **agnóstico** (no se fija lenguaje ni framework). El esquema concreto del
> token (opaco vs JWT) queda a criterio de la implementación siempre que se cumplan las
> reglas e invariantes de esta épica. El frontend está fijado por alcance global: React
> (web) y React Native/Expo (mobile).

---

## Historias de Usuario de la épica

| ID        | Título                            | Resumen (una línea)                                                                 |
|-----------|-----------------------------------|-------------------------------------------------------------------------------------|
| HU-01-01  | Registro de usuario               | Un visitante crea una cuenta con credenciales válidas; unicidad de email, validación de datos y estado inicial `ACTIVE` con balances en cero. |
| HU-01-02  | Inicio de sesión                  | Un usuario registrado se autentica y obtiene un token de sesión con expiración; credenciales inválidas se rechazan sin revelar si el email existe. |
| HU-01-03  | Cierre y expiración de sesión     | El usuario cierra sesión (logout) invalidando su token, y todo token caduca por TTL; el efecto sobre operaciones posteriores es `UNAUTHENTICATED`. |
| HU-01-04  | Consulta de perfil                | El usuario autenticado consulta los datos y el estado de su propia cuenta, sin exponer secretos. |

---

## Dependencias

- **Épica 00 — Fundaciones** (obligatoria): glosario, modelo de errores
  (`EMAIL_ALREADY_EXISTS`, `INVALID_CREDENTIALS`, `ACCOUNT_NOT_FOUND`, `UNAUTHENTICATED`,
  `UNAUTHORIZED`, `VALIDATION_ERROR`, `RATE_LIMITED`, etc.), serialización y, en lo que
  aplica a balances iniciales, invariantes globales (`INV-1`).

Esta épica **no** depende de otras épicas funcionales, pero es **dependencia de casi
todas** las demás: `02`..`08` (operaciones sobre fondos/órdenes/on-chain) exigen una cuenta
autenticada; `09` consume el token emitido aquí como mecanismo de autenticación de la API;
`10` y `11` construyen las pantallas de registro/login/perfil sobre estos flujos.

---

## Invariantes y reglas clave de la épica

Estas reglas son transversales a las HUs de la épica y se evalúan como criterio:

- **RNE-1 — Unicidad de identidad.** El **email normalizado** es la identidad única de una
  cuenta. No pueden coexistir dos cuentas con el mismo email normalizado. Normalización:
  recorte de espacios al inicio/fin (`trim`) y conversión a minúsculas (`lowercase`).
- **RNE-2 — Secretos nunca expuestos.** La contraseña **jamás** se almacena en claro: se
  almacena únicamente como la salida de una **función de derivación de clave (KDF) con coste
  ajustable resistente a ataques GPU** (el algoritmo y los parámetros mínimos se fijan en
  HU-01-01 RN-5). La contraseña no se devuelve en ninguna respuesta de la API. Ningún
  endpoint de esta épica retorna el hash, la sal ni el secreto del token de otra forma que
  no sea el propio token al hacer login.
- **RNE-3 — No enumeración de cuentas.** En el login, credenciales incorrectas se rechazan
  **siempre** con `INVALID_CREDENTIALS` (401) con una respuesta indistinguible, tanto si el
  email no existe como si la contraseña es incorrecta. No se debe poder inferir la
  existencia de un email a partir de la respuesta de login. La indistinguibilidad incluye el
  **canal lateral de tiempo**: la verificación de credenciales se realiza en tiempo
  constante respecto de si el email existe (cuando el email no existe se ejecuta una
  operación de hash dummy de coste equivalente al KDF configurado antes de responder), de
  modo que la latencia no permita enumerar emails (se detalla en HU-01-02 RN-12).
- **RNE-4 — Sesión con expiración.** Todo token emitido tiene una expiración (TTL
  configurable). Un token expirado o invalidado (logout) no autentica: las llamadas
  protegidas se rechazan con `UNAUTHENTICATED` (401).
- **RNE-5 — Aislamiento por cuenta.** Una credencial válida solo autoriza el acceso a los
  recursos de su **propia** cuenta. Intentar operar sobre recursos de otra cuenta se
  rechaza con `UNAUTHORIZED` (403).
- **RNE-6 — Estado inicial determinista.** Una cuenta recién creada nace en estado
  `ACTIVE`, con un `accountId` estable e inmutable, y con balances disponible = `"0"` y
  bloqueado = `"0"` para ETH y USDC (consistente con `INV-1`: sin depósitos confirmados, la
  suma de balances de la cuenta es 0). Estos balances iniciales son **estado interno** de la
  cuenta (consultable por los endpoints de la épica 02), no parte del contrato de respuesta
  de los endpoints de esta épica (registro y perfil exponen solo identidad). El detalle del
  modelo de balances vive en la épica 02.
  - **Formato del `accountId`.** El `accountId` es un identificador **opaco, no secuencial y
    no predecible externamente** (p. ej. UUID v4 o ULID, con ≥122 bits de entropía). Se
    prohíben enteros secuenciales (`1, 2, 3…`) o identificadores derivables del timestamp,
    para impedir la enumeración de cuentas y la inferencia del número total de usuarios. El
    formato concreto (UUID v4, ULID u otro) es libre para la implementación siempre que
    cumpla esas propiedades; los AT verifican: (a) string no vacío, (b) **mismo** valor en
    respuestas sucesivas para la misma cuenta, (c) **distinto** entre cuentas distintas, y
    (d) **no secuencial ni con patrón predecible** entre cuentas creadas consecutivamente.
- **RNE-7 — Precedencia de validación determinista.** Para cada operación de la épica, el
  orden de evaluación de errores es fijo (se detalla por HU) de modo que los tests de
  aceptación sean reproducibles. Se reporta **un solo error por respuesta** (el primero
  según el orden).
- **RNE-8 — Serialización.** Los endpoints de esta épica (registro, login, logout, perfil)
  **no** exponen montos en sus respuestas: los balances iniciales en cero son estado interno
  y se consultan por la épica 02. Si alguna respuesta llegara a incluir un monto, seguiría la
  regla de **string de entero de unidad mínima** de `convenciones-monetarias.md` (p. ej.
  `"0"`). Las marcas de tiempo (p. ej. `createdAt`, `expiresAt`) se serializan como
  timestamps ISO 8601 en UTC y **no** son montos.
- **RNE-9 — Auditoría de eventos de autenticación.** Todo intento de autenticación
  (login exitoso o fallido) y todo logout se registran en un **log de auditoría interno** con,
  al menos: `timestamp` UTC (ISO 8601), `email` normalizado del intento, `result`
  (`SUCCESS` / `FAILURE`), `reason` del fallo cuando aplica (`INVALID_CREDENTIALS`,
  `RATE_LIMITED`, etc.) y `origin` (IP del cliente cuando esté disponible). El log es
  **interno**: no es consultable por el usuario final y por lo tanto su existencia **no**
  viola `RNE-3` (la no-enumeración aplica a las respuestas de la API, no al log operativo).
  Es un requisito operativo del exchange (detección de credential stuffing y anomalías) y es
  **anterior e independiente del KYC/AML** (que está fuera de alcance). Su verificación se
  delega a inspección interna documentada en el DoD (no es observable por caja negra en la
  respuesta de la API).

> Ante cualquier conflicto entre estas reglas y `00-fundaciones`, **prevalece
> `00-fundaciones`**.
