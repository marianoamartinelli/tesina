# HU-01-03 — Cierre y expiración de sesión

- **Epica:** 01 — Cuentas y Autenticación
- **Actor / rol:** Usuario autenticado (titular de un token de sesión vigente)
- **Prioridad:** Alta
- **Dependencias:** HU-01-02 (debe existir un token emitido). Se relaciona con todas las
  épicas con endpoints protegidos (el efecto del cierre/expiración es `UNAUTHENTICATED`).
- **Estandares de dominio aplicables:** N/A (no hay componente on-chain en esta HU).

## Historia
Como usuario autenticado, quiero cerrar mi sesión explícitamente y que mi token caduque
automáticamente al cumplirse su expiración, para que mis credenciales de sesión no puedan
seguir usándose para operar una vez que dejo de necesitarlas o pasa demasiado tiempo.

## Contexto y alcance
Cubre dos mecanismos de fin de sesión: (a) **logout explícito**, que invalida de inmediato
el token presentado; y (b) **expiración automática** por TTL (`expiresAt`, definido en
HU-01-02). En ambos casos, el efecto observable es que las llamadas protegidas posteriores
con ese token se rechazan con `UNAUTHENTICATED` (401). La ruta canónica del endpoint de
logout es `POST /api/v1/auth/logout` (mapa de endpoints de HU-09-01); su comportamiento lo
fija esta HU.

No cubre la emisión ni la renovación de tokens (refresh tokens están fuera de alcance: el
usuario vuelve a hacer login para obtener un token nuevo). El logout opera **sobre el token
presentado** y no afecta otras sesiones de la misma cuenta (RN-5).

## Reglas de negocio e invariantes

1. **RN-1 (logout invalida el token presentado).** Un logout autenticado invalida de forma
   inmediata y permanente el token con el que se realizó. Tras un logout exitoso, ese token
   no vuelve a autenticar. (RNE-4)
2. **RN-2 (efecto sobre operaciones posteriores).** Cualquier llamada a un endpoint
   protegido presentando un token invalidado (por logout) o expirado (por TTL) se rechaza
   con `UNAUTHENTICATED` (401). La respuesta no distingue entre "invalidado" y "expirado":
   en ambos casos el token simplemente no autentica.
3. **RN-3 (expiración por TTL).** Un token deja de autenticar a partir de su `expiresAt`. En
   el instante `t ≥ expiresAt` el token está expirado y produce `UNAUTHENTICATED` (401) en
   endpoints protegidos. Estrictamente antes de `expiresAt` (`t < expiresAt`), y si no fue
   invalidado por logout, el token sigue siendo válido.
4. **RN-4 (autenticación requerida para logout).** El logout es una operación protegida:
   requiere un token válido. Un logout sin token, con token malformado, ya invalidado o
   expirado se rechaza con `UNAUTHENTICATED` (401) y no produce ningún efecto adicional.
5. **RN-5 (aislamiento entre sesiones).** El logout invalida **únicamente** el token
   presentado. Otros tokens vigentes de la misma cuenta (sesiones obtenidas por otros
   logins, RN-6 de HU-01-02) siguen siendo válidos.
6. **RN-6 (idempotencia observable del logout y atomicidad).** Hacer logout exitosamente y
   luego volver a intentar logout con el **mismo** token (ya invalidado) se rechaza con
   `UNAUTHENTICATED` (401): el primer logout ya surtió efecto; el segundo no cambia el estado.
   No se produce un error de servidor ni un doble efecto. La invalidación del token es
   **atómica** (implementable como operación CAS, transacción de BD con aislamiento
   serializable o equivalente): si dos solicitudes de logout **concurrentes** presentan el
   mismo token, **exactamente una** recibe respuesta exitosa y la(s) restante(s) reciben
   `UNAUTHENTICATED` (401); el token queda revocado **exactamente una vez** (no se permite que
   ambas fallen ni que el token quede sin revocar).
7. **RN-7 (sin reactivación).** Un token invalidado o expirado **no** puede reactivarse;
   para volver a operar el usuario debe autenticarse de nuevo (HU-01-02) y obtener un token
   nuevo.
8. **RN-8 (persistencia de la invalidación).** El efecto del logout y de la expiración debe
   sobrevivir reinicios del sistema (`INV-8`): un token invalidado/expirado antes del
   reinicio sigue sin autenticar después.
9. **RN-9 (no exposición de secretos).** Ni el logout ni el rechazo por expiración exponen
   el token, el hash de la contraseña ni datos sensibles en sus respuestas. (RNE-2)
10. **RN-10 (estado de invalidación persistente — denylist).** La implementación **debe**
    persistir el estado de invalidación de los tokens cerrados por logout en almacenamiento
    durable, de modo que el efecto sobreviva reinicios (`INV-8`, RN-8). Según el esquema de
    token:
    - **Token opaco:** toda sesión activa se registra en almacenamiento durable; el logout
      marca/elimina la sesión, y esa marca persiste.
    - **JWT (stateless):** dado que la validez de un JWT se verifica criptográficamente sin
      consultar un store, el logout **requiere una lista de revocación (denylist) persistente**
      (p. ej. del `jti` o del hash del token) en BD. Una implementación JWT **sin** denylist
      persistente **no** puede satisfacer RN-8 ni `INV-8`: tras un reinicio, un JWT revocado
      cuya firma siga siendo válida y cuyo `expiresAt` no haya vencido volvería a autenticar.
      La expiración por TTL (codificada en el token) **sí** sobrevive sin estado adicional;
      la **invalidación por logout** no. (Los refresh tokens están fuera de alcance, por lo
      que el JWT debe complementarse con denylist persistente, no con tokens de vida ultra
      corta + refresh.)

## Criterios de aceptación (DoD)

### Escenario 1: Logout explícito exitoso [AT-01-03-01]
- Dado un usuario autenticado con un token válido y no expirado
- Cuando invoca el endpoint de logout presentando ese token
- Entonces la respuesta es exitosa con status HTTP **204** (sin cuerpo) — status único y
  determinista, por convención REST para operaciones sin cuerpo de respuesta
- Y a partir de ese momento el token queda invalidado

### Escenario 2: Token invalidado por logout no autentica [AT-01-03-02]
- Dado un token que fue invalidado por un logout exitoso (Escenario 1)
- Cuando se usa ese token en un endpoint protegido (p. ej. consulta de perfil HU-01-04)
- Entonces la solicitud se rechaza con `UNAUTHENTICATED` y status HTTP 401
- Y la operación protegida no se ejecuta

### Escenario 3 (borde): Token válido antes de expirar [AT-01-03-03]
- Dado un token con `expiresAt` en el futuro y que no fue invalidado por logout
- Cuando se usa en un endpoint protegido en un instante `t < expiresAt`
- Entonces la llamada se procesa como autenticada (no devuelve `UNAUTHENTICATED`)

### Escenario 4 (error): Token expirado por TTL [AT-01-03-04]
- Dado un token cuyo `expiresAt` ya pasó (instante actual `t ≥ expiresAt`)
- Cuando se usa en un endpoint protegido
- Entonces la solicitud se rechaza con `UNAUTHENTICATED` y status HTTP 401
- Y la respuesta es indistinguible de la de un token invalidado por logout (RN-2)

### Escenario 5 (borde): Logout afecta solo al token presentado [AT-01-03-05]
- Dado una cuenta con dos sesiones activas (dos tokens distintos, `tokenA` y `tokenB`,
  obtenidos por dos logins)
- Cuando el usuario hace logout presentando `tokenA`
- Entonces `tokenA` queda invalidado y produce `UNAUTHENTICATED` en endpoints protegidos
- Y `tokenB` sigue siendo válido y autentica normalmente

### Escenario 6 (error): Logout sin token o con token inválido [AT-01-03-06]
- Dado un cliente que no presenta token, o presenta un token malformado/inexistente
- Cuando invoca el endpoint de logout
- Entonces la solicitud se rechaza con `UNAUTHENTICATED` y status HTTP 401
- Y no se produce ningún efecto sobre sesiones existentes

### Escenario 7 (idempotencia): Doble logout con el mismo token [AT-01-03-07]
- Dado un token que ya fue invalidado por un logout exitoso
- Cuando se intenta hacer logout otra vez con ese mismo token
- Entonces la solicitud se rechaza con `UNAUTHENTICATED` y status HTTP 401
- Y el estado de las sesiones no cambia respecto del primer logout

### Escenario 8 (borde): Persistencia de la invalidación tras reinicio [AT-01-03-08]
- Dado un token invalidado por logout (o ya expirado) antes de un reinicio del sistema
- Cuando el sistema se reinicia y luego se usa ese token en un endpoint protegido
- Entonces la solicitud se rechaza con `UNAUTHENTICATED` (401): la invalidación/expiración
  sobrevivió al reinicio

### Escenario 9 (error): Token expirado no puede reactivarse [AT-01-03-09]
- Dado un token expirado por TTL
- Cuando el usuario intenta seguir usándolo en lugar de volver a autenticarse
- Entonces toda llamada protegida con ese token devuelve `UNAUTHENTICATED` (401)
- Y solo un nuevo login (HU-01-02) le permite obtener un token válido

### Escenario 10 (persistencia JWT): JWT revocado por logout sigue revocado tras reinicio [AT-01-03-10]
- Dado una implementación que usa JWT como esquema de token, y un JWT cuya firma es válida y
  cuyo `expiresAt` aún no venció
- Cuando se hace logout con ese JWT (queda en la denylist persistente, RN-10), luego se
  **reinicia** el servicio, y después se usa el mismo JWT en un endpoint protegido
- Entonces la solicitud se rechaza con `UNAUTHENTICATED` (401): la denylist sobrevivió al
  reinicio aunque la firma siga siendo criptográficamente válida
- (Si el esquema de token es opaco, este caso queda cubierto por AT-01-03-08; con JWT exige
  denylist persistente, RN-10)

### Escenario 11 (concurrencia): Doble logout concurrente con el mismo token [AT-01-03-11]
- Dado un token válido `T` y no expirado
- Cuando dos solicitudes de logout con `T` se envían de forma **concurrente**
- Entonces el token queda invalidado **exactamente una vez** (RN-6)
- Y **exactamente una** de las respuestas es el logout exitoso (204); la(s) restante(s)
  reciben `UNAUTHENTICATED` (401) — no se permite que ambas respondan 204 ni que ambas fallen
- Y cualquier uso posterior de `T` en un endpoint protegido devuelve `UNAUTHENTICATED` (401)

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptacion (AT-*) pasan
- [ ] Reglas de negocio RN-1..RN-10 verificadas
- [ ] Estado de invalidación persistente / denylist (RN-10) verificado, incluido el caso JWT
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md — N/A (sin montos)
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md)
- [ ] (si aplica) Adherencia verificada al estandar on-chain citado — N/A en esta HU
