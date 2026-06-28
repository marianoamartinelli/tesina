# Épica 11 — Cliente Mobile (React Native / Expo)

## Objetivo de la épica

Especificar el **cliente mobile** del exchange, construido en **React Native / Expo**,
que consume **la misma API** que el cliente web (épica 09: HTTP/REST + WebSocket) y ofrece
**paridad funcional** con el web (épica 10) dentro del alcance del proyecto. La épica se
enfoca en las **pantallas mínimas equivalentes** a las del web, adaptadas a las
restricciones y oportunidades de mobile: navegación, ciclo de vida de la app
(foreground/background), almacenamiento seguro de credenciales, cámara/QR, portapapeles y
reconexión de streams en vivo.

Donde el comportamiento de negocio es **idéntico al web**, esta épica **referencia la HU
correspondiente de la épica 10** y se concentra en las **diferencias propias de mobile**.
El cliente mobile es un **consumidor** de la API: **no** ejecuta matching, **no** realiza
settlement, **no** firma transacciones on-chain ni maneja la seed/mnemonic. La fuente de
verdad es siempre el backend; el cliente sólo presenta estado y valida en cliente para dar
**feedback temprano** (la validación autoritativa la hace el backend).

## Alcance

Dentro de alcance:

- Inicio de sesión en mobile y **persistencia segura del token** entre sesiones de la app
  (almacenamiento cifrado del SO: Keychain en iOS / Keystore en Android, p. ej. mediante
  Expo SecureStore).
- Vista de trading adaptada a mobile: **orderbook en vivo** y **últimos trades** vía
  WebSocket (épica 09).
- **Formulario de orden** (limit/market) con validaciones de cliente, idempotencia por
  `clientOrderId` y feedback.
- **Órdenes abiertas** (con cancelación) e **historial** con paginación y actualizaciones
  en vivo.
- **Balances** (disponible / bloqueado / total) por activo, con actualizaciones en vivo.
- **Depósitos** (dirección + QR + copiar, seguimiento de confirmaciones) y **retiros**
  (validación de dirección EIP-55, monto, seguimiento on-chain) desde mobile.
- Comportamientos transversales de mobile: ciclo de vida (suspender/reanudar streams),
  reconexión con resync, pull-to-refresh, escaneo de QR con la cámara, portapapeles.

Fuera de alcance:

- Definir o modificar el contrato de la API (lo fija la épica 09) y la lógica de negocio
  (matching, settlement, on-chain) — el mobile sólo la consume.
- Registro de cuenta, KYC/AML (no aplica al proyecto).
- Notificaciones push de servidor (infraestructura): el seguimiento se hace por
  polling/WebSocket dentro de la app; sólo se contempla feedback in-app (toasts/estados).
- Firma de transacciones, manejo de claves privadas o de la mnemonic en el dispositivo.
- Hardening de seguridad de producción (jailbreak/root detection, certificate pinning
  avanzado, etc.).

## Historias de Usuario de la épica

| ID        | Título                                  | Resumen (una línea)                                                                 |
|-----------|-----------------------------------------|------------------------------------------------------------------------------------|
| HU-11-01  | Inicio de sesión en mobile              | Login mobile y persistencia segura del token entre aperturas de la app.             |
| HU-11-02  | Vista de trading en mobile              | Orderbook en vivo y últimos trades adaptados a la pantalla del celular.             |
| HU-11-03  | Formulario de orden en mobile           | Alta de órdenes limit/market con validaciones, idempotencia y feedback.             |
| HU-11-04  | Órdenes abiertas e historial en mobile  | Listado de órdenes abiertas (con cancelación) e historial con paginación y live.    |
| HU-11-05  | Balances en mobile                      | Disponible/bloqueado/total por activo con actualizaciones en vivo.                  |
| HU-11-06  | Depósitos y retiros en mobile           | Dirección/QR de depósito y retiro con validaciones y seguimiento on-chain.          |

## Dependencias hacia otras épicas

- **00 — Fundaciones:** glosario, convenciones monetarias (montos como string entero de
  unidad mínima, prohibición de floats), modelo de errores e invariantes globales. Ante
  conflicto, **prevalece 00-fundaciones**.
- **09 — API HTTP/WebSocket:** contrato único de endpoints, eventos WebSocket, formato de
  errores y paginación que el mobile consume (el mismo que el web).
- **10 — Cliente Web:** referencia de **paridad funcional**. Cada HU de esta épica mapea a
  su equivalente web y referencia su comportamiento de negocio:
  - HU-11-01 ↔ HU-10-01 (login)
  - HU-11-02 ↔ HU-10-02 (vista de trading)
  - HU-11-03 ↔ HU-10-03 (formulario de orden)
  - HU-11-04 ↔ HU-10-04 (órdenes abiertas e historial)
  - HU-11-05 ↔ HU-10-05 (balances)
  - HU-11-06 ↔ HU-10-06 (depósitos y retiros)
- **01 — Cuentas y autenticación:** semántica de credenciales/sesión consumida por el login.
- **02 — Balances y ledger:** fuente de los balances mostrados.
- **03 — Motor de matching / 04 — Gestión de órdenes / 05 — Settlement y fees:** semántica
  de órdenes, estados, fills y fees reflejada por las vistas.
- **06 — Wallet HD / 07 — Depósitos / 08 — Retiros:** semántica on-chain reflejada por la
  vista de depósitos/retiros (direcciones BIP-44 coin type 60, confirmaciones, EIP-155).

## Invariantes y reglas clave de la épica (transversales a sus HU)

- **RG-1 (consumidor, no autoridad):** el cliente mobile no recalcula matching, settlement
  ni valida fondos de forma autoritativa. Toda validación en cliente es **feedback
  temprano**; el error/estado que **prevalece** es el del backend (épica 09).
- **RG-2 (dinero como string entero, sin floats):** todos los montos/precios/cantidades/
  fees/balances viajan y se reciben como **string de entero de unidad mínima**
  (`^(0|[1-9][0-9]*)$`). El cliente **nunca** usa `float`/`double`/`Number`/`parseFloat`
  para parsear u operar montos que puedan exceder 2⁵³; usa **BigInt** o decimales de
  precisión fija. La conversión humano⇄unidad mínima es exacta (ETH ⇄ wei = ×/÷ 10¹⁸;
  USDC y precio ⇄ unidad mínima = ×/÷ 10⁶). Ver `00-fundaciones/convenciones-monetarias.md`.
- **RG-3 (errores uniformes):** todo error se interpreta por su `code` estable del catálogo
  (`00-fundaciones/modelo-de-errores.md`); el `message` se muestra como diagnóstico y los
  montos de `details` se formatean sin floats.
- **RG-4 (sesión segura):** el token se persiste sólo en almacenamiento cifrado del SO;
  ante `UNAUTHENTICATED` (401) el cliente limpia la sesión y redirige al login. La
  password y el token **nunca** se loggean ni se muestran.
- **RG-5 (ciclo de vida y live data):** las suscripciones WebSocket se suspenden en
  background y, al volver a foreground, se **reconectan y re-sincronizan** (snapshot fresco
  antes de aplicar deltas). La reconexión usa backoff y muestra el estado de conexión.
- **RG-6 (paridad funcional):** salvo las diferencias mobile explícitas, el comportamiento
  observable coincide con el de la HU web equivalente (épica 10).
- **RG-7 (presentación de invariantes):** la UI refleja, sin violarlos, los invariantes del
  backend: no-negatividad (INV-2), `total = disponible + bloqueado` (INV-3), prioridad
  precio-tiempo del orderbook (INV-7), idempotencia de depósitos (INV-5) y anti-replay
  EIP-155 de retiros (INV-6).
- **RG-8 (logout singleton ante `UNAUTHENTICATED` concurrente):** el flujo de logout
  disparado por `UNAUTHENTICATED` (401) — sea de una petición REST o del handshake/eventos
  WebSocket — se ejecuta como una **acción singleton**: un flag atómico (o una única promesa
  pendiente) garantiza que, si ya hay un logout en curso, las activaciones adicionales son
  **no-ops**. Sólo el **primer** disparador borra el token, limpia el estado de sesión y
  redirige al login; los demás 401 concurrentes (p. ej. `balances` + `orders` + market data
  recibiendo 401 a la vez al reconectar en foreground) **no** producen borrados múltiples ni
  navegaciones duplicadas al login. Referenciada por HU-11-01, HU-11-03, HU-11-04, HU-11-05
  y HU-11-06.
- **RG-9 (overlay de privacidad en background):** al recibir `AppState = inactive` /
  `background` (React Native AppState API), la app superpone un **overlay opaco o blur**
  sobre toda la pantalla **antes** de que el SO capture el screenshot para el app switcher
  (multitasking), evitando exponer balances, direcciones de depósito, montos de retiro o
  historial de órdenes. Al volver a `AppState = active` el overlay se retira. Aplica a
  **todas** las pantallas autenticadas y **no** interfiere con el ciclo de vida de las
  suscripciones WebSocket (RG-5).
- **RG-10 (parámetros de reconexión — paridad con web):** la reconexión WebSocket (RG-5)
  usa el **mismo backoff** que el cliente web (HU-10-02, RNE-9): **delay inicial 1 s,
  factor 2×, delay máximo 30 s, jitter ±500 ms**; los reintentos son indefinidos con el
  delay topeado mientras la pantalla esté en foreground, y la UI muestra el indicador de
  estado de conexión (en vivo / reconectando / desconectado). Estos valores son los del
  **contrato de evaluación**; toda HU que use reconexión los referencia (evita tests
  dependientes de timing no definido).
- **RG-11 (condiciones de prueba del ciclo de vida):** los escenarios de ciclo de vida
  (background → foreground) se evalúan con un **mock/fake del WebSocket** que expone un
  método `simulateDisconnect()` independiente del tiempo real (los tests **no** dependen de
  timers del SO). Para pruebas de integración en dispositivo real se usa un tiempo mínimo en
  background de **60 s** (umbral por encima del cual el SO típicamente cierra el socket).
  Salvo indicación contraria, cada AT de ciclo de vida asume el **cierre de la conexión** al
  pasar a background.

## Verificación de invariantes desde el cliente (alcance de la DoD)

El checklist de DoD de cada HU incluye la verificación de invariantes globales. Como el
cliente mobile es un **consumidor** (RG-1), sólo un subconjunto es verificable desde su
perspectiva de presentación:

- **Verificables en el cliente:** **INV-2** (la UI nunca muestra balances negativos) e
  **INV-3** (`total = disponible + bloqueado` en la vista de balances, HU-11-05 RN-1).
- **Responsabilidad del backend** (el cliente los **refleja** pero no los garantiza ni
  puede violarlos): INV-1 (conservación), INV-4 (atomicidad del settlement), INV-5
  (idempotencia de depósitos), INV-6 (anti-replay EIP-155), INV-7 (integridad del
  orderbook) e INV-8 (persistencia y recuperación). El cliente sólo presenta el estado que
  el backend (épica 09 y subyacentes) garantiza.
