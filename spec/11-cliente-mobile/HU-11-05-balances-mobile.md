# HU-11-05 — Balances en mobile (actualizaciones en vivo)

- **Epica:** 11 — Cliente Mobile (React Native / Expo)
- **Actor / rol:** Trader autenticado
- **Prioridad:** Alta
- **Dependencias:** HU-10-05 (paridad web: balances), épica 09 (endpoint de balances y
  eventos WebSocket), épica 02 (balances y ledger), HU-11-01 (sesión)
- **Estandares de dominio aplicables:** N/A (no on-chain)

## Historia
Como trader autenticado, quiero ver mis **balances** (disponible / bloqueado / total) de ETH
y USDC en mobile, **actualizados en vivo**, para conocer mis fondos disponibles para operar y
retirar.

## Contexto y alcance
Cubre la vista de balances por activo (ETH y USDC-mock): **disponible**, **bloqueado** y
**total**. Los datos provienen de la API (épica 09); las actualizaciones en vivo llegan por
WebSocket cuando ocurren bloqueos, liberaciones, settlements, depósitos acreditados o
retiros. El contrato es **el mismo que el web** (HU-10-05). La fuente de verdad es el ledger
del backend (épica 02); el cliente sólo **presenta**.

Diferencias mobile: tarjetas/lista por activo, **pull-to-refresh** y **resync por ciclo de
vida**. El cliente no modifica balances ni verifica conservación (eso es INV-1 en el
backend); sólo refleja y formatea sin floats.

## Reglas de negocio e invariantes
1. **RN-1 (partición INV-3):** por cada activo se muestran `disponible`, `bloqueado` y
   `total`, cumpliendo `total == disponible + bloqueado`. El cliente, si calcula el total,
   lo hace con **aritmética entera exacta** sobre las unidades mínimas; si usa el total
   provisto, éste debe coincidir exactamente con la suma.
2. **RN-2 (formato sin floats):** los montos llegan como string entero de unidad mínima y se
   formatean a humano sin floats: ETH = `wei / 10¹⁸`, USDC = `min / 10⁶`. **Prohibido**
   `float`/`Number`/`parseFloat` para montos que excedan 2⁵³; usar **BigInt**/decimal de
   precisión fija.
3. **RN-3 (no-negatividad INV-2):** `disponible ≥ 0` y `bloqueado ≥ 0`; el cliente refleja lo
   provisto por el backend (no debería observar negativos).
4. **RN-4 (live updates):** cuando un evento cambia los fondos (alta de orden bloquea,
   cancelación libera, fill liquida, depósito acreditado, retiro), el balance se actualiza
   por WebSocket (épica 09) sin recarga manual.
5. **RN-5 (pull-to-refresh):** fuerza un refetch del estado de balances (GET de la épica 09).
6. **RN-6 (ciclo de vida):** al volver a foreground, el cliente re-sincroniza (refetch +
   re-suscripción WS).
7. **RN-7 (sólo lectura):** el cliente no modifica balances; sólo los muestra. No recalcula
   conservación global (INV-1 es responsabilidad del backend).
8. **RN-8 (sesión):** ante `UNAUTHENTICATED` (401), limpia la sesión y redirige al login
   (consistente con HU-11-01, flujo singleton RG-8).
9. **RN-9 (consistencia con acciones):** tras una acción iniciada en la app (alta de orden,
   cancelación, retiro), el balance refleja el nuevo estado al recibir la respuesta o el
   evento WS, sin requerir reinicio de la app.
10. **RN-10 (composición del bloqueado):** el `bloqueado` agrega tanto las **reservas de
    órdenes abiertas** (liberables al cancelar, HU-11-04) como las **reservas de retiros en
    proceso** (`PENDING`/`BROADCAST`, no recuperables del mismo modo). Si la API de la épica
    09 expone el desglose (p. ej. `lockedByOrders` y `lockedByWithdrawals`), la vista lo
    muestra; si **no** lo expone, la vista incluye un texto informativo/ícono de ayuda
    indicando que el bloqueado puede incluir órdenes abiertas y retiros en proceso, para que
    el usuario entienda por qué un monto no está disponible.
11. **RN-11 (fallo de red):** si el `GET` de balances no obtiene respuesta del backend (fallo
    de red/timeout), la UI muestra un error de **conectividad** (distinto de los errores de
    negocio) conservando el último estado conocido, y permite reintentar (pull-to-refresh).

## Criterios de aceptación (DoD)

### Escenario 1: Vista de balances por activo [AT-11-05-01]
- Dado un trader autenticado con fondos en ETH y USDC
- Cuando abre la pantalla de balances
- Entonces ve, por cada activo, `disponible`, `bloqueado` y `total`
- Y los montos se muestran formateados a humano sin floats

### Escenario 2: total = disponible + bloqueado exacto [AT-11-05-02]
- Dado balances con `disponible = "1500000000"` y `bloqueado = "500000000"` en USDC
- Cuando se renderiza
- Entonces `total` mostrado equivale a `"2000000000"` (suma entera exacta)
- Y se cumple `total == disponible + bloqueado` (INV-3)

### Escenario 3 (live): Alta de orden bloquea fondos [AT-11-05-03]
- Dado la pantalla de balances visible
- Cuando el trader crea una orden que bloquea fondos
- Entonces el `disponible` baja y el `bloqueado` sube por el evento WS
- Y el `total` del activo permanece constante (no se crea ni destruye valor en el cliente)

### Escenario 4 (live): Cancelación libera fondos [AT-11-05-04]
- Dado una orden abierta que mantiene fondos bloqueados
- Cuando se cancela (HU-11-04)
- Entonces el `bloqueado` baja y el `disponible` sube por el evento WS, con `total` constante

### Escenario 5 (live): Depósito acreditado [AT-11-05-05]
- Dado un depósito que alcanza las confirmaciones requeridas y el backend lo acredita
- Cuando llega el evento de actualización de balance
- Entonces el `disponible` del activo aumenta en el monto acreditado

### Escenario 6 (borde): Formato exacto de monto grande [AT-11-05-06]
- Dado un balance en ETH de `"12000000000000000000"` (12 ETH, mayor a 2⁵³ en wei)
- Cuando se formatea
- Entonces se muestra el valor humano exacto (`12.0...`) sin pérdida por punto flotante

### Escenario 7: Pull-to-refresh [AT-11-05-07]
- Dado la pantalla de balances visible
- Cuando el usuario hace pull-to-refresh
- Entonces el cliente refetch-ea los balances y actualiza la vista

### Escenario 8 (ciclo de vida): Resync al volver a foreground [AT-11-05-08]
- Dado la app que pasó a background con la pantalla de balances, con un **mock del
  WebSocket** que simula el cierre de conexión al pasar a background (RG-11)
- Cuando vuelve a foreground
- Entonces re-sincroniza (refetch + re-suscripción WS) y muestra el estado actual

### Escenario 9 (error): Token expirado [AT-11-05-09]
- Dado un trader cuyo token expiró
- Cuando el GET de balances recibe `UNAUTHENTICATED` (401)
- Entonces la app limpia la sesión y redirige al login

### Escenario 10 (borde): Balance cero [AT-11-05-10]
- Dado un activo con `disponible = "0"`, `bloqueado = "0"`
- Cuando se renderiza
- Entonces se muestra `0` formateado correctamente (sin valores inválidos ni negativos)

### Escenario 11 (error): Fallo de red al cargar balances [AT-11-05-11]
- Dado la pantalla de balances y el backend caído o sin conectividad
- Cuando el `GET` de balances no obtiene respuesta (fallo de red)
- Entonces la UI muestra un error de conectividad (distinto de los errores de negocio)
- Y conserva el último estado conocido sin inventar valores
- Y permite reintentar (pull-to-refresh)

### Escenario 12 (borde): Composición del bloqueado [AT-11-05-12]
- Dado un activo con `bloqueado > 0` por una orden abierta y/o un retiro en proceso
- Cuando se renderiza la vista
- Entonces, si la API expone el desglose (`lockedByOrders`, `lockedByWithdrawals`), se
  muestran ambos componentes; si no, se muestra un texto informativo indicando que el
  bloqueado puede incluir órdenes y retiros (RN-10)

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-*) pasan
- [ ] Reglas de negocio RN-1..RN-11 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md
- [ ] Invariantes globales **verificables desde el cliente**: **INV-2** (la UI nunca muestra
      disponible/bloqueado negativos) e **INV-3** (`total = disponible + bloqueado` en la
      vista); INV-1, INV-4 e INV-8 (y demás) son responsabilidad del backend — el cliente
      los **refleja** pero no los garantiza (00-fundaciones/invariantes-globales.md)
- [ ] (si aplica) Adherencia verificada al estandar on-chain citado
