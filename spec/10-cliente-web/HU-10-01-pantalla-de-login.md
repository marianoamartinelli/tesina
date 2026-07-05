# HU-10-01 — Pantalla de login

- **Epica:** 10 — Cliente Web (React)
- **Actor / rol:** Usuario no autenticado (futuro trader) operando la web
- **Prioridad:** Alta
- **Dependencias:** HU de épica 09 (endpoint de autenticación HTTP y formato de error); HU de épica 01 (semántica de credenciales/sesión). Fundaciones (00).
- **Estandares de dominio aplicables:** N/A (sin on-chain). Aplica modelo de errores y serialización de `00-fundaciones`.

## Historia
Como usuario no autenticado, quiero iniciar sesión desde la web con mi email y contraseña, para obtener una sesión válida y acceder a las pantallas de trading, balances y operaciones del exchange.

## Contexto y alcance
Cubre la pantalla de login del cliente React: formulario de credenciales, envío al endpoint de autenticación de la API (épica 09), almacenamiento de la sesión resultante, manejo de errores de credenciales/validación/rate limit/red y el comportamiento ante expiración de sesión (redirección a login). No cubre el registro de cuenta, recuperación de contraseña ni la emisión/validación del token en el backend (eso es de épicas 01/09). El cliente es una capa de presentación: la autenticación real la decide el servidor (RNE-2 del README de la épica).

## Reglas de negocio e invariantes
1. **RN-1 (campos requeridos).** El formulario tiene los campos `email` y `password`, ambos obligatorios. El botón de envío permanece deshabilitado mientras alguno esté vacío o mientras haya un envío en curso.
2. **RN-2 (envío único).** Durante una solicitud de login en curso no se permite reenviar (anti doble submit): el segundo intento se ignora hasta resolver el primero.
3. **RN-3 (éxito y almacenamiento del token).** Ante respuesta exitosa (HTTP 200) con el **token Bearer** de sesión (épica 09, HU-09-02), el cliente establece la sesión y navega a la vista de trading (HU-10-02). El contrato **no** emite cookies de sesión (`httpOnly` ni de otro tipo): cada llamada autenticada envía el header `Authorization: Bearer <token>`. El cliente mantiene el token en memoria de la SPA y lo **persiste del lado del cliente junto con su expiración** para sobrevivir recargas, re-validando la sesión contra el servidor al cargar la app (RN-11). El token nunca se muestra en la UI ni se escribe en logs (RNE-4).
4. **RN-4 (credenciales inválidas).** Ante `INVALID_CREDENTIALS` (401), se muestra un mensaje **genérico** ("Email o contraseña incorrectos") que **no revela** si el email existe (coherente con `00-fundaciones/modelo-de-errores.md` §3.6). No se redirige; los campos permanecen para reintento (la contraseña se limpia).
5. **RN-5 (validación de esquema).** Ante `VALIDATION_ERROR` (422) por payload mal formado (p. ej. email con formato inválido), se muestra el detalle por campo a partir de `details.issues`, sin exponer datos sensibles.
6. **RN-6 (rate limit).** Ante `RATE_LIMITED` (429), se deshabilita el reintento y se informa el tiempo de espera tomado de `details.retryAfterSeconds`; transcurrido ese lapso se rehabilita el botón.
7. **RN-7 (expiración/no autenticado).** Ante `UNAUTHENTICATED` (401) recibido en cualquier llamada protegida posterior, el cliente limpia la sesión local y redirige a esta pantalla mostrando un aviso de "sesión expirada" (RNE-4).
8. **RN-8 (error de red / servidor).** Ante fallo de red o `INTERNAL_ERROR` (500), se muestra un mensaje no técnico ("No se pudo conectar, reintentá") y se ofrece reintentar; no se filtran detalles sensibles del error.
9. **RN-9 (sesión ya activa).** Si al cargar la pantalla de login ya existe una sesión válida en el cliente, se redirige directamente a la vista de trading sin pedir credenciales nuevamente.
10. **RN-10 (manejo por `code`).** Todo error se discrimina por su `code` del catálogo, no por el `message` (RNE-3). No hay montos en esta HU; no aplica conversión monetaria, pero rige la prohibición de floats de `00-fundaciones`.
11. **RN-11 (criterio de sesión válida).** Al cargar la app, si existe un token Bearer persistido (RN-3) **no expirado**, el cliente lo valida mediante una **llamada liviana** `GET /me` (épica 09) con el header `Authorization: Bearer <token>`: si responde 200, la sesión es válida y se procede según RN-9 (redirección a trading); si responde `UNAUTHENTICATED` (401) —o el token persistido está ausente o expirado según su expiración registrada—, el cliente limpia todo estado de sesión local y permanece en login. Más allá del chequeo local de expiración, la validez **no** se decide inspeccionando el token: el servidor es la única fuente de verdad (RNE-2). Si la app conserva el token en memoria de una navegación SPA previa, igualmente puede confiar en él hasta recibir un `UNAUTHENTICATED`, momento en el que aplica RN-7.

## Criterios de aceptación (DoD)

### Escenario 1: Login exitoso [AT-10-01-01]
- Dado que el usuario no tiene sesión activa y está en la pantalla de login
- Y completó `email` y `password` con credenciales correctas
- Cuando presiona "Ingresar"
- Entonces el cliente envía la solicitud al endpoint de autenticación de la API (épica 09)
- Y al recibir 200 establece la sesión y navega a la vista de trading (HU-10-02)
- Y el token de sesión no aparece en el DOM renderizado ni en la URL (la prohibición de exponerlo en logs rige por RN-3/RNE-4, fuera del alcance de este AT de caja negra)

### Escenario 2a: Email inexistente responde con mensaje genérico [AT-10-01-02a]
- Dado un email que no corresponde a ninguna cuenta y una contraseña cualquiera
- Cuando envía el formulario y la API responde `{ error: { code: "INVALID_CREDENTIALS" } }` (401)
- Entonces se muestra el mensaje genérico "Email o contraseña incorrectos"
- Y el campo `password` se limpia y el usuario permanece en la pantalla de login

### Escenario 2b: Email existente con contraseña incorrecta responde con el mismo mensaje [AT-10-01-02b]
- Dado un email que sí corresponde a una cuenta y una contraseña incorrecta
- Cuando envía el formulario y la API responde `{ error: { code: "INVALID_CREDENTIALS" } }` (401)
- Entonces se muestra el **mismo** mensaje genérico "Email o contraseña incorrectos" que en AT-10-01-02a (mismo `code`; no revela si el email existe)
- Y el campo `password` se limpia y el usuario permanece en la pantalla de login

### Escenario 3 (borde): campos vacíos deshabilitan el envío [AT-10-01-03]
- Dado que el usuario está en la pantalla de login
- Cuando deja vacío el campo `email` o el campo `password`
- Entonces el botón "Ingresar" permanece deshabilitado
- Y no se realiza ninguna llamada a la API

### Escenario 4 (borde): anti doble submit [AT-10-01-04]
- Dado que el usuario envió credenciales y la solicitud está en curso
- Cuando vuelve a presionar "Ingresar" antes de recibir respuesta
- Entonces el segundo intento se ignora (no se dispara una segunda llamada)
- Y el botón muestra estado de carga hasta resolver la primera solicitud

### Escenario 5 (error): validación de esquema [AT-10-01-05]
- Dado que el usuario ingresa un email con formato inválido
- Cuando la API responde `{ error: { code: "VALIDATION_ERROR", details: { issues: [...] } } }` (422)
- Entonces se muestran los mensajes por campo derivados de `details.issues`
- Y no se navega fuera de la pantalla de login

### Escenario 6 (error): rate limit [AT-10-01-06]
- Dado que el usuario superó el límite de intentos de login
- Cuando la API responde `{ error: { code: "RATE_LIMITED", details: { retryAfterSeconds: 30 } } }` (429; `retryAfterSeconds` es un conteo y viaja como **entero JSON**, no string)
- Entonces se deshabilita el botón "Ingresar" e informa que debe esperar 30 segundos
- Y al transcurrir el tiempo indicado el botón se rehabilita

### Escenario 7 (error): expiración de sesión redirige a login [AT-10-01-07]
- Dado que el usuario tenía sesión activa y navegaba otra pantalla
- Cuando una llamada protegida responde `{ error: { code: "UNAUTHENTICATED" } }` (401)
- Entonces el cliente limpia la sesión local
- Y redirige a la pantalla de login mostrando "Tu sesión expiró, ingresá nuevamente"

### Escenario 8 (error): fallo de red / servidor [AT-10-01-08]
- Dado que el usuario envía credenciales válidas
- Cuando la solicitud falla por red o la API responde `INTERNAL_ERROR` (500)
- Entonces se muestra un mensaje no técnico ("No se pudo conectar, reintentá")
- Y se ofrece reintentar sin perder el email ingresado
- Y no se filtra ningún detalle sensible del error

### Escenario 9 (borde): sesión ya activa redirige automáticamente [AT-10-01-09]
- Dado que el cliente conserva un token Bearer persistido vigente (no expirado) (RN-3)
- Cuando el usuario navega a la ruta de login y la app ejecuta la validación de sesión (RN-11)
- Y la llamada `GET /me` (con `Authorization: Bearer <token>`) responde 200
- Entonces es redirigido automáticamente a la vista de trading sin volver a autenticarse

### Escenario 10 (borde): sesión persistida inválida permanece en login [AT-10-01-10]
- Dado que el cliente conserva un token Bearer persistido **inválido o expirado** (o revocado por el servidor)
- Cuando el usuario navega a la ruta de login y la app ejecuta la validación de sesión (RN-11)
- Y la llamada `GET /me` responde `{ error: { code: "UNAUTHENTICATED" } }` (401)
- Entonces el cliente limpia cualquier estado de sesión local (incluido el token persistido)
- Y muestra el formulario de login (no redirige a la vista de trading)

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-*) pasan
- [ ] Reglas de negocio RN-1..RN-11 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md)
- [ ] (si aplica) Adherencia verificada al estandar on-chain citado
