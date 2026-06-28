# HU-11-01 — Inicio de sesión en mobile y persistencia segura del token

- **Epica:** 11 — Cliente Mobile (React Native / Expo)
- **Actor / rol:** Trader (usuario de la app mobile)
- **Prioridad:** Alta
- **Dependencias:** HU-10-01 (paridad web: login), épica 09 (endpoints de
  autenticación), épica 01 (cuentas y autenticación)
- **Estandares de dominio aplicables:** N/A (no on-chain). Manejo seguro de credenciales
  en el dispositivo.

## Historia
Como trader, quiero iniciar sesión desde la app mobile y mantener mi sesión de forma
**segura** entre aperturas de la app, para operar sin re-autenticarme en cada uso, sin que
mis credenciales queden expuestas en el dispositivo.

## Contexto y alcance
Cubre la pantalla de login mobile (email + password), la **persistencia segura del token**
de sesión en el almacenamiento cifrado del SO (Keychain en iOS / Keystore en Android, p.
ej. mediante Expo SecureStore), la **restauración de sesión** al abrir/reanudar la app, el
**logout** y el manejo de **token expirado/inválido** (`UNAUTHENTICATED`). El contrato de
autenticación (request, response y códigos de error) es **el mismo que usa el web**
(HU-10-01) y lo define la épica 09: esta HU **no** crea endpoints nuevos.

No cubre: registro de cuenta, recuperación de contraseña, KYC ni biometría (fuera de
alcance del proyecto). El cliente **no** decide autorización: la autenticación la valida el
backend; la validación de formato en cliente es sólo feedback temprano.

## Reglas de negocio e invariantes
1. **RN-1:** La pantalla de login envía `(email, password)` al endpoint de autenticación de
   la épica 09. El contrato (forma del request/response y códigos) es **idéntico** al del
   web (HU-10-01); el mobile no define variantes.
2. **RN-2:** Login exitoso ⇒ el backend devuelve un token de sesión. El token se persiste
   **únicamente** en almacenamiento **cifrado** del dispositivo (Keychain/Keystore, p. ej.
   Expo SecureStore). **Prohibido** persistirlo en almacenamiento no cifrado en claro (p.
   ej. `AsyncStorage` plano) o en logs.
3. **RN-3:** Credenciales inválidas ⇒ el backend responde `INVALID_CREDENTIALS` (401). La
   UI muestra un mensaje coherente que **no revela** si el email existe, y **no** persiste
   token.
4. **RN-4:** Al abrir o reanudar la app: si existe un token persistido, se **restaura la
   sesión** sin pedir credenciales y se navega a la vista autenticada; si no existe, se
   muestra la pantalla de login.
5. **RN-5:** Toda petición autenticada incluye el token según el esquema de la épica 09. Si
   el backend responde `UNAUTHENTICATED` (401) (token expirado o inválido), el cliente
   **borra** el token persistido, limpia el estado de sesión y **redirige al login**. Ante
   **múltiples** `UNAUTHENTICATED` concurrentes (p. ej. varias peticiones en vuelo), el
   flujo de logout es **singleton** (RG-8 del README): sólo el primer disparador ejecuta el
   borrado y la navegación; los demás son no-ops.
6. **RN-6:** Logout borra el token del almacenamiento seguro **y** de memoria, y redirige
   al login. Tras logout no es posible restaurar la sesión.
7. **RN-7:** La `password` **nunca** se persiste ni se loggea; sólo se usa en tránsito para
   el request de login. El token tampoco se loggea ni se muestra en pantallas de
   diagnóstico.
8. **RN-8:** La validación de formato (email no vacío y con forma de email, password no
   vacía) es feedback temprano en cliente; **no** sustituye la autorización del backend ni
   permite "bypass" local.
9. **RN-9:** Fallo de red durante el login (sin respuesta del backend) ⇒ la UI muestra un
   error de conectividad, **no** persiste token y permite reintentar; no se confunde con
   `INVALID_CREDENTIALS`.
10. **RN-10 (estrategia de restauración — optimista):** la restauración de sesión (RN-4) es
    **optimista**: si existe un token persistido, la app navega **directamente** a la vista
    autenticada usándolo, **sin** una llamada de validación previa al backend. La expiración
    se detecta de forma **reactiva**: la **primera** petición autenticada (REST o handshake
    WebSocket) que reciba `UNAUTHENTICATED` (401) aplica el flujo de logout (RN-5). No existe
    un endpoint de validación de token dedicado; el comportamiento observable es que la
    pantalla autenticada puede mostrarse brevemente antes de redirigir al login si el token
    estaba expirado.
11. **RN-11 (fallo de acceso al almacén seguro):** si la lectura de SecureStore/Keychain
    **falla con error** (p. ej. *Keychain item inaccessible* en estado *Before First Unlock*
    tras un reinicio del dispositivo, o el almacén no disponible), el cliente trata el caso
    **como si no hubiera token persistido**: muestra la pantalla de login. **No** expone el
    detalle del error interno en la UI ni lo loggea con datos sensibles (RN-7). En el próximo
    intento de foreground reintenta el acceso.
12. **RN-12 (autenticación de la reconexión WebSocket):** la (re)conexión del WebSocket
    privado incluye el **mismo** token del almacenamiento seguro en el handshake (épica 09,
    RG-API-5). Si el handshake o un mensaje del canal privado responde `UNAUTHENTICATED`
    (token expirado mientras la app estuvo en background), el cliente aplica el **mismo**
    flujo de limpieza de sesión y redirección al login que para las peticiones REST (RN-5,
    singleton por RG-8).

## Criterios de aceptación (DoD)

### Escenario 1: Login exitoso persiste el token y navega [AT-11-01-01]
- Dado un trader en la pantalla de login con credenciales válidas
- Cuando envía el formulario y el backend (épica 09) responde con un token de sesión
- Entonces el token se persiste en el almacenamiento **cifrado** del dispositivo
- Y la app navega a la vista autenticada (p. ej. trading/balances)
- Y la `password` no queda almacenada en ningún medio

### Escenario 2: Restauración de sesión al abrir la app (optimista) [AT-11-01-02]
- Dado un token válido previamente persistido en el almacenamiento seguro
- Cuando el usuario abre la app (cold start)
- Entonces la sesión se restaura sin pedir credenciales y **sin** una llamada de validación
  previa al backend (estrategia optimista, RN-10)
- Y la app muestra directamente la vista autenticada
- Y la expiración, si la hubiera, se detecta sólo cuando la primera petición autenticada
  reciba `UNAUTHENTICATED` (Escenario 5)

### Escenario 3 (borde): Apertura sin token persistido [AT-11-01-03]
- Dado que no hay token persistido (primera vez o tras logout)
- Cuando el usuario abre la app
- Entonces la app muestra la pantalla de login
- Y no intenta llamar a endpoints autenticados

### Escenario 4 (error): Credenciales inválidas [AT-11-01-04]
- Dado un trader en la pantalla de login con email o password incorrectos
- Cuando envía el formulario y el backend responde `INVALID_CREDENTIALS` (401)
- Entonces la UI muestra un mensaje de error coherente que **no** revela si el email existe
- Y no se persiste ningún token
- Y el usuario permanece en la pantalla de login para reintentar

### Escenario 5 (error): Token expirado en una petición autenticada [AT-11-01-05]
- Dado un usuario con sesión activa cuyo token expiró o fue invalidado
- Cuando una petición autenticada recibe `UNAUTHENTICATED` (401) del backend
- Entonces el cliente borra el token persistido y el estado de sesión
- Y redirige a la pantalla de login

### Escenario 6: Logout borra el token [AT-11-01-06]
- Dado un usuario con sesión activa
- Cuando ejecuta logout
- Entonces el token se borra del almacenamiento seguro y de memoria
- Y la app vuelve al login
- Y reabrir la app no restaura la sesión (vuelve a pedir credenciales)

### Escenario 7 (borde): Validación de campos en cliente [AT-11-01-07]
- Dado un trader en la pantalla de login
- Cuando deja el email o la password vacíos (o el email con formato inválido) e intenta
  enviar
- Entonces la UI bloquea el envío y muestra el mensaje de validación local
- Y no realiza la petición al backend hasta corregir los campos

### Escenario 8a (seguridad — almacenamiento): el token sólo va al almacén cifrado [AT-11-01-08]
- Dado un test que instrumenta **spies/mocks** sobre `SecureStore.setItemAsync` y sobre
  `AsyncStorage.setItem` (y cualquier almacenamiento en claro disponible)
- Cuando ocurre un login exitoso
- Entonces el spy de `SecureStore.setItemAsync` recibe el token (almacenamiento cifrado del SO)
- Y el spy de `AsyncStorage.setItem` (u otro almacén en claro) **nunca** es invocado con el
  token ni con la password

### Escenario 8b (seguridad — logs): ni token ni password se loggean [AT-11-01-11]
- Dado spies sobre `console.log`/`console.error`/`console.warn` (y sobre el logger propio si
  existe)
- Cuando ocurre un login exitoso y peticiones autenticadas posteriores
- Entonces ninguna invocación de log contiene el valor del token ni de la password
  (verificación por aserción sobre los argumentos capturados por el spy)

### Escenario 9 (error): Fallo de red durante el login [AT-11-01-09]
- Dado un trader que envía credenciales válidas sin conectividad o con el backend caído
- Cuando la petición de login falla por red (no hay respuesta del backend)
- Entonces la UI muestra un error de conectividad (distinto de `INVALID_CREDENTIALS`)
- Y no se persiste token
- Y se permite reintentar el login

### Escenario 10 (ciclo de vida): Reanudación desde background [AT-11-01-10]
- Dado un usuario con sesión activa y token válido
- Cuando la app pasa a background y luego vuelve a foreground
- Entonces la sesión se mantiene sin re-autenticación
- Y si en el ínterin el token expiró, la primera petición autenticada que reciba
  `UNAUTHENTICATED` aplica el flujo del Escenario 5

### Escenario 11 (ciclo de vida): Reconexión WebSocket con token expirado [AT-11-01-12]
- Dado la app en foreground con un token persistido que expiró mientras estuvo en background
- Cuando el cliente intenta **reconectar** el WebSocket privado y el handshake (o un mensaje
  del canal) responde `UNAUTHENTICATED`
- Entonces el cliente aplica el mismo flujo del Escenario 5 (limpia la sesión y redirige al
  login), de forma **singleton** (RG-8) aunque coincidan varios 401 de REST y WS

### Escenario 12 (borde, seguridad): Fallo de lectura del almacén seguro [AT-11-01-13]
- Dado que la lectura de SecureStore/Keychain lanza una excepción al abrir la app (p. ej.
  *Keychain item inaccessible* en estado *Before First Unlock*)
- Cuando la app arranca e intenta restaurar la sesión
- Entonces muestra la pantalla de login (se trata como "sin token", RN-11)
- Y **no** expone el detalle del error interno en la UI ni lo loggea con datos sensibles

### Escenario 13 (concurrencia): Logout singleton ante múltiples 401 [AT-11-01-14]
- Dado varias peticiones autenticadas en vuelo (p. ej. balances + órdenes + market data)
- Cuando **todas** reciben `UNAUTHENTICATED` (401) de forma concurrente
- Entonces el flujo de logout se ejecuta **una sola vez** (RG-8): un único borrado de token,
  una única limpieza de estado y una **única** navegación al login (sin navegaciones
  duplicadas)

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-*) pasan
- [ ] Reglas de negocio RN-1..RN-12 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md
- [ ] Invariantes globales: desde el cliente se verifican **INV-2** (no mostrar balances
      negativos) e **INV-3** (`total = disponible + bloqueado` en la vista); INV-1, INV-4,
      INV-5, INV-6, INV-7 e INV-8 son responsabilidad del backend (épica 09 y subyacentes) —
      el cliente los **refleja** pero no los garantiza (00-fundaciones/invariantes-globales.md)
- [ ] (si aplica) Adherencia verificada al estandar on-chain citado
