celda: celda-en-evaluacion
instrumento: rol-revisor
fecha: 2026-09-07
discrepantes: 2 de 47

Claves en `discrepancias.txt`: `backend,2` y `mobile,3` (censo, Parte A). Los 9 puntos concordantes y las 36 filas de Parte B se copian de `pasada-1/` verbatim (R6 del briefing de arbitraje; no es `etapa,*`).

| clave | pasada 1 | pasada 2 | final | evidencia que decide | regla del instrumento |
|-------|----------|----------|-------|----------------------|-----------------------|
| backend,2 | eje=CORRECCION; severidad=MAYOR; ancla=SPEC; veracidad=VERDADERO; destino=RESUELTO | eje=COMPLETITUD; severidad=MENOR; ancla=SPEC; veracidad=VERDADERO; destino=RESUELTO | eje=COMPLETITUD; severidad=MENOR; ancla=SPEC; veracidad=VERDADERO; destino=RESUELTO | Artefacto L2. paso2-revisor/src/app.ts:111-118 (error handler RATE_LIMITED por `pendingPublicRateLimit` sin auditar); :44-62 y :194-197 (`validateCredentialsBody` lanza VALIDATION_ERROR antes de `login`); auth-service.ts:85-96 (audita solo SUCCESS/INVALID_CREDENTIALS); :110-112 y :162-166 (`auditRateLimited` solo en `preValidation`, no corre si el parseo JSON falla). Spec: `spec/01-cuentas-y-autenticacion/README.md` RNE-9 L136-140 (todo intento, reason RATE_LIMITED etc.); HU-01-02 RN-8/RN-9 L69-84 (precedencia de error HTTP, no auditoría); AT-01-02-13 L204-210 (SUCCESS e INVALID_CREDENTIALS, ya auditados). Diff paso2→paso3: `onResponse`+`loginAuditOutcome` y `test/login-audit.test.ts`. | R1 (un punto que agrupa dos huecos). R3 SPEC (cita RNE/HU/RN). R2 MENOR: no es INV-* ni arranque; MAYOR exige incumplir un `AT-*` o una `RN-*` concreta — RNE-9 no es `RN-*`; RN-8/RN-9 no mandan auditar; AT-01-02-13 no se incumple. Eje COMPLETITUD: cobertura incompleta del log, no error HTTP incorrecto. R4 VERDADERO (lectura). R5 RESUELTO. |
| mobile,3 | eje=OPERABILIDAD; severidad=MAYOR; ancla=SPEC; veracidad=VERDADERO; destino=RESUELTO | eje=CORRECCION; severidad=MENOR; ancla=SPEC; veracidad=VERDADERO; destino=RESUELTO | eje=OPERABILIDAD; severidad=MENOR; ancla=SPEC; veracidad=VERDADERO; destino=RESUELTO | Artefacto L5. paso2-revisor/mobile/src/session/usePrivateSocket.ts:99-103 (`onclose` hace `scheduleReconnect()` siempre, también si `current!==socket`); :106-109 (foreground llama `connect()`); :45-54 (sin generación). Secuencia background→foreground→onclose viejo: socket A se cierra, B se instala, onclose de A agenda C. Spec: `spec/11-cliente-mobile/README.md` RG-5 L100-102 (ciclo de vida: suspender/reconectar; no exige unicidad); HU-11-01 RN-12 L73-77 (token en handshake); AT-11-01-10 L153-158 (sesión se mantiene); AT-11-01-12 L160-165 (UNAUTHENTICATED en reconexión). Diff paso2→paso3: `onclose` retorna si `current!==socket`; `connect()` no abre otro si ya hay `socket`. | R1 (un punto). R3 SPEC. Eje OPERABILIDAD: defecto de ciclo de vida y estado de conexión (RG-5), no RN de negocio. R2 MENOR: MAYOR exige `AT-*` o `RN-*` concreta — RG-5 no es `RN-*`; RN-12/AT-11-01-10/12 no prohíben sockets duplicados; no es INV-* ni impide arranque. R4 VERDADERO (el código hace lo afirmado). R5 RESUELTO. La pasada 1 acertó el eje y aplicó mal R2 (citar RN/AT no basta). La pasada 2 acertó R2 y aplicó mal el eje (CORRECCION). |

## Totales

- coinciden con pasada 1: 0
- coinciden con pasada 2: 1 (`backend,2`)
- coinciden con ninguna: 1 (`mobile,3`)
- residuales (`NO_EVALUABLE` / `NO_VERIFICABLE`): 0
