# Ensayo de la rúbrica `epica-10-web.md` v1.0 sobre `pre-piloto-b` — `HU-10-01`

**Esto no es el veredicto del tesista.** Es un ensayo del instrumento sobre una corrida
descartable (ADR-018), hecho por Claude el 2026-09-06 para el componente 8.1 de
`runs/pre-piloto/matriz-componentes.md`. **No entra en ningún dataset.**

## Entorno

- SUT: copia del repo satélite congelado (`6fb74cd`) con `.env` propio. Backend en
  contenedor `tesina/agente-b:piloto-01` (`npm run build && npm start`), puerto publicado
  `3103`; cliente web compilado y servido adentro (`vite build` + `vite preview`), puerto
  `4173`. Entorno on-chain de `suite-at/entorno` arriba (anvil, USDC-mock en
  `0xe7f1…0512`).
- Variables elegidas por el evaluador porque la spec las deja «por config» (ver H-24):
  `LOGIN_RATE_LIMIT_MAX=5`, `LOGIN_RATE_LIMIT_WINDOW_SECONDS=60`,
  `WEB_ORIGINS=http://127.0.0.1:4173,http://localhost:4173`.
- Usuarios: `eval-web@test.local`, `contraparte@test.local`, `vacio-web@test.local`,
  creados por `POST /api/v1/auth/register`. Los fondos que la rúbrica pide (10 ETH /
  100000 USDC) no aplican a `HU-10-01` y la corrida no implementó balances.
- Navegador: Chromium vía Playwright. `page.route` se usó como equivalente de DevTools
  (throttling, offline) y del proxy interceptor (adulterar el payload); Network se leyó
  del propio Playwright. Tiempo de pared del ensayo: 22:52 → 22:58 (6 min) más los 57 s
  de espera del rate limit.

## Resultados

| AT | Veredicto | Nota (qué se observó) |
|---|---|---|
| AT-10-01-01 | PASA | `POST /api/v1/auth/login` → 200 `{token, expiresAt}`; navega a `/trading`; el token (43 chars) no aparece en la URL ni en `document.documentElement.outerHTML`; persiste en `localStorage["axis.session.v1"]`. |
| AT-10-01-02a | PASA | Email inexistente → 401 `INVALID_CREDENTIALS`; mensaje «Email o contraseña incorrectos»; el campo password queda vacío, el email se conserva; sigue en `/login`. |
| AT-10-01-02b | PASA | Email del evaluador + password incorrecta → 401; **el mismo texto** «Email o contraseña incorrectos» (comparación textual); password vacío; sigue en `/login`. |
| AT-10-01-03 | PASA | Con `email` vacío y con `password` vacío el botón «Ingresar» está `disabled`; cero requests a `/api/` en ambos casos. |
| AT-10-01-04 | PASA | Respuesta del login demorada 3 s; tres clicks sobre el botón (dos forzados) → **1** request a `/auth/login`; durante la espera el botón está `disabled` con texto «Ingresando…». |
| AT-10-01-05 | PASA | `a@b` pasa la validación local pero el backend no responde 422 por formato (respondió 429 por el rate limit ya acumulado); con el payload adulterado (`{"email": …}` sin `password`) → 422 `VALIDATION_ERROR` con `details.issues=[{field: "password", message: "Campo requerido"}]` y el cliente muestra «Campo requerido» bajo el campo password; no navega. Provocado por adulteración, como la rúbrica admite. |
| AT-10-01-06 | PASA | 5.º fallo → 429 `RATE_LIMITED` con `details.retryAfterSeconds: 57`; el cliente muestra «◷ Esperá 57 segundos antes de volver a intentar.» y el botón queda `disabled`; muestreado cada segundo, se rehabilita en el segundo 57. |
| AT-10-01-07 | **FALLA** | Sesión activa; token revocado del lado servidor (`POST /auth/logout` con el Bearer, 204); navegación SPA a `/login` (pushState + popstate, y «Atrás» real) dispara `GET /me` → 401 `UNAUTHENTICATED`; el cliente **limpia** `localStorage` y **redirige** a `/login`, pero **no muestra ningún aviso** de sesión expirada. Causa en el código: `App.tsx` maneja el 401 del chequeo de sesión con `clearSession()`; el aviso («Tu sesión expiró, ingresá nuevamente») sólo lo dispara `expireSession()` desde `authenticatedRequest`, que ninguna pantalla de este alcance usa. Ver H-24 (2). |
| AT-10-01-08 | PASA | Request de login abortada (equivale a Offline) → «No se pudo conectar, reintentá», sin stack trace; aparece un botón «Reintentar»; el email se conserva (también la password); al restablecer, el reintento → 200 y navega a `/trading`. |
| AT-10-01-09 | PASA | Con token persistido vigente, `goto /login` → `GET /me` con `Authorization: Bearer …` → 200 → redirige a `/trading` sin pedir credenciales. |
| AT-10-01-10 | PASA | Token reemplazado por `token-corrupto-no-expirado` en `localStorage` y recarga en `/login` → `GET /me` → 401; `localStorage` queda vacío; se muestra el formulario. |

**Agregación pre-registrada:** `PASA / (PASA + FALLA)` = **10 / 11 = 0,91**;
`NO_EVALUABLE` = 0.

## Sobre el instrumento

Los tres huecos que este ensayo saca a la luz están en `hallazgos.md`, **H-24**: el rate
limit sin valores fijados por la spec ni por el entorno de evaluación, AT-10-01-07 en un
cliente cuyo único request protegido es el chequeo de sesión, y Playwright como
herramienta no listada entre las permitidas.
