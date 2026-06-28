# HU-09-02 — Autenticación y autorización de la API

- **Epica:** 09 — API HTTP/WebSocket
- **Actor / rol:** Trader autenticado / Cliente web/mobile / Sistema (servidor de API)
- **Prioridad:** Alta
- **Dependencias:** HU-09-01 (contrato REST), HU-09-04 (WS privado), HU-09-05 (modelo de
  errores), HU-01-* (emisión/validación de token, cuentas)
- **Estándares de dominio aplicables:** N/A on-chain (autenticación es de plataforma)

## Historia
Como trader, quiero que cada request a un recurso protegido se autentique con mi token y
que solo pueda acceder a **mis propios recursos**, para que ningún otro usuario pueda leer
ni operar mis órdenes, balances, depósitos o retiros.

## Contexto y alcance
Esta HU fija el mecanismo de **autenticación por token Bearer** en la API y la **regla de
autorización (aislamiento por cuenta)**. La emisión del token, su expiración y la gestión
de credenciales son de HU-01-*; aquí se define cómo se **presenta** y cómo se **rechaza**
su ausencia/invalidez, y cómo se **aísla** el acceso por cuenta tanto en REST como en el
canal WebSocket privado. No cubre roles/permisos avanzados (no existen roles en el
proyecto: cada cuenta accede solo a lo suyo).

## Reglas de negocio e invariantes

1. **RN-1 (presentación del token):** los recursos marcados "Auth: Sí" en HU-09-01 exigen
   el header `Authorization: Bearer <token>`. Endpoints públicos (`/auth/register`,
   `/auth/login`, `/market/*`) no lo exigen.
2. **RN-2 (token ausente):** si falta el header `Authorization` en un recurso protegido ⇒
   `UNAUTHENTICATED` (401).
3. **RN-3 (token inválido/expirado/malformado):** si el token no valida, está expirado, o
   el esquema no es `Bearer <token>` ⇒ `UNAUTHENTICATED` (401). No se distingue
   públicamente el motivo (no se filtra si el token "existió").
4. **RN-4 (resolución de identidad):** un token válido resuelve a exactamente **una**
   cuenta (`accountId`). Todas las operaciones de la request actúan en nombre de esa cuenta.
5. **RN-5 (aislamiento de lectura):** los listados (`/orders`, `/deposits`,
   `/withdrawals`, `/balances`) devuelven **solo** recursos de la cuenta autenticada. Nunca
   incluyen ni cuentan recursos de otra cuenta (privacidad).
6. **RN-6 (aislamiento de acceso directo a orden):** `GET`/`DELETE /orders/{orderId}` de
   una orden que no pertenece a la cuenta autenticada devuelve `ORDER_NOT_FOUND` (404) —
   **no** se distingue de "no existe", para no filtrar la existencia de órdenes ajenas.
   Esta es la convención del proyecto para recursos user-scoped (coherente con el
   disparador de `ORDER_NOT_FOUND`: "no existe o no pertenece a la cuenta").
7. **RN-7 (aislamiento de acceso directo a retiro):** `GET /withdrawals/{withdrawalId}` de
   un retiro ajeno devuelve `NOT_FOUND` (404) por la misma razón de no filtrar existencia.
8. **RN-8 (autorización vs autenticación):** `UNAUTHORIZED` (403) se reserva para el caso
   en que la credencial es válida pero la acción está explícitamente prohibida sobre un
   recurso cuya existencia no es sensible; para recursos user-scoped se usa la familia
   NOT_FOUND (RN-6/RN-7). La elección por endpoint es **determinista** y documentada.
9. **RN-9 (precedencia de validación):** la autenticación se evalúa **antes** que cualquier
   regla de esquema o de negocio (`00-fundaciones/modelo-de-errores.md` §4): primero
   `UNAUTHENTICATED`/autorización, luego el resto. Un payload inválido enviado sin token
   devuelve `UNAUTHENTICATED` (401), no `VALIDATION_ERROR`.
10. **RN-10 (WS privado):** el canal WebSocket privado (HU-09-04) exige el mismo token; sin
    token válido la conexión/suscripción privada se rechaza con un mensaje de error
    `{ error: { code: "UNAUTHENTICATED" } }` y/o cierre de conexión. El canal **público**
    (HU-09-03) no exige token.
11. **RN-11 (no fuga de credenciales):** el token nunca se devuelve en cuerpos de error ni
    en logs expuestos por la API; las respuestas de error solo contienen el envelope de
    HU-09-05.
12. **RN-12 (rate limiting por identidad):** la política es **determinista y única**: en
    recursos **protegidos** (con token válido) el límite se aplica **por cuenta**
    (`accountId`); en recursos **públicos** (`/auth/*`, `/market/*`) se aplica **por IP de
    origen**. El umbral del entorno de evaluación es **60 requests por minuto** por sujeto
    (cuenta o IP) y endpoint (ventana deslizante de 60 s). Al superarlo ⇒ `RATE_LIMITED`
    (429) con `details.retryAfterSeconds` (entero) y header `Retry-After`. (Coherente con
    RG-API-10.)

## Criterios de aceptación (DoD)

### Escenario 1: Acceso autenticado exitoso [AT-09-02-01]
- Dado un token válido emitido para la cuenta A
- Cuando A hace `GET /api/v1/balances` con `Authorization: Bearer <token>`
- Entonces la respuesta es **200** con los balances de la cuenta A

### Escenario 2 (error): Token ausente [AT-09-02-02]
- Dado un recurso protegido (`GET /api/v1/me`)
- Cuando el cliente lo invoca **sin** header `Authorization`
- Entonces la respuesta es `UNAUTHENTICATED` (401) con el envelope de error
- Y no se ejecuta ninguna lógica de negocio

### Escenario 3 (error): Token inválido o malformado [AT-09-02-03]
- Dado un recurso protegido
- Cuando el cliente envía `Authorization: Bearer xxx-invalido` o `Authorization: Token abc`
  (esquema no `Bearer`) o un token expirado
- Entonces la respuesta es `UNAUTHENTICATED` (401)
- Y el `message` no revela si el token existió o por qué exactamente falló

### Escenario 4 (precedencia): Payload inválido sin token [AT-09-02-04]
- Dado un recurso protegido `POST /api/v1/orders`
- Cuando el cliente envía un body inválido **sin** token
- Entonces la respuesta es `UNAUTHENTICATED` (401), **no** `VALIDATION_ERROR`
  (la autenticación precede a la validación de esquema)

### Escenario 5 (autorización): Listados aislados por cuenta [AT-09-02-05]
- Dado que la cuenta A tiene 3 órdenes y la cuenta B tiene 2 órdenes
- Cuando A hace `GET /api/v1/orders`
- Entonces la respuesta **solo** incluye las 3 órdenes de A
- Y ninguna orden, conteo o cursor revela las órdenes de B

### Escenario 6 (autorización/error): Acceso a orden ajena [AT-09-02-06]
- Dado una orden con `orderId` perteneciente a la cuenta B
- Cuando la cuenta A hace `GET /api/v1/orders/{orderId}` de esa orden
- Entonces la respuesta es `ORDER_NOT_FOUND` (404)
- Y la respuesta es **indistinguible** de la de un `orderId` inexistente (no filtra
  existencia)

### Escenario 7 (autorización/error): Cancelar orden ajena [AT-09-02-07]
- Dado una orden `OPEN` perteneciente a la cuenta B
- Cuando la cuenta A hace `DELETE /api/v1/orders/{orderId}` de esa orden
- Entonces la respuesta es `ORDER_NOT_FOUND` (404)
- Y la orden de B permanece `OPEN` (no se modifica; sus balances bloqueados no cambian,
  INV-3)

### Escenario 8 (autorización/error): Acceso a retiro ajeno [AT-09-02-08]
- Dado un retiro perteneciente a la cuenta B
- Cuando la cuenta A hace `GET /api/v1/withdrawals/{withdrawalId}` de ese retiro
- Entonces la respuesta es `NOT_FOUND` (404), indistinguible de un id inexistente

### Escenario 9 (WS privado): Suscripción privada requiere token [AT-09-02-09]
- Dado el canal WebSocket privado
- Cuando un cliente intenta abrir/suscribirse al canal privado sin token válido
- Entonces el servidor responde con `{ error: { code: "UNAUTHENTICATED" } }` y/o cierra la
  conexión, sin entregar ningún evento de usuario

### Escenario 10 (aislamiento WS): Eventos solo de la cuenta dueña [AT-09-02-10]
- Dado que A y B están suscritos al canal privado con sus tokens
- Cuando ocurre un fill que afecta a B
- Entonces A **no** recibe ningún evento de orden ni de balance de B; solo B los recibe

### Escenario 11 (rate limit): Exceso de solicitudes [AT-09-02-11]
- Dado una cuenta autenticada y el umbral de 60 requests/min por cuenta y endpoint (RN-12)
- Cuando envía 61 requests al mismo endpoint protegido con el **mismo token** dentro de una
  ventana de 60 s
- Entonces la request número 61 responde `RATE_LIMITED` (429) con `details.retryAfterSeconds`
  (entero) presente y header `Retry-After` presente
- Y las primeras 60 requests no fueron limitadas por esta regla

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-*) pasan
- [ ] Reglas de negocio RN-1..RN-12 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md)
- [ ] (si aplica) Adherencia verificada al estandar on-chain citado (N/A)
