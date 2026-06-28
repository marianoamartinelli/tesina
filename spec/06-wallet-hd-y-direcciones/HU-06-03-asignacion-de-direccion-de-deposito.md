# HU-06-03 — Asignación de dirección de depósito

- **Epica:** 06 — Wallet HD y Direcciones de Depósito
- **Actor / rol:** Sistema (asignador de índices de derivación), disparado **de forma eager
  por el alta de una cuenta** (épica 01, HU-01-01); la primera solicitud de dirección
  (HU-06-04) actúa solo como **fallback idempotente** (ver RN-12)
- **Prioridad:** Alta
- **Dependencias:** HU-06-01 (seed), HU-06-02 (derivación), HU-01-01 (registro/creación de
  cuenta — provee el concepto de "cuenta existente" y el disparador de alta)
- **Estandares de dominio aplicables:** BIP-44 (`address_index` como índice por usuario),
  BIP-32 (derivación), coin type 60, EIP-55 (checksum de la dirección emitida). Red única:
  Sepolia, chainId 11155111.

## Historia
Como **Sistema**, quiero **asignar a cada cuenta de usuario una dirección de depósito única
mediante un índice de derivación monótono e inmutable**, para **que cada usuario tenga una
dirección estable, reproducible y exclusiva donde recibir ETH y USDC en la misma red**.

## Contexto y alcance
Esta HU cubre la **biyección cuenta ↔ índice ↔ dirección**: a cada cuenta se le asigna un
`address_index` único (monótono, contiguo desde 0, sin reúso, inmutable), del cual se
deriva (HU-06-02) la dirección de depósito. Una **única dirección por cuenta** sirve para
**ETH (nativo)** y **USDC-mock (ERC-20)** porque ambos comparten la misma cuenta on-chain
(EOA) en Sepolia. La asignación es **idempotente** y se persiste de forma que sobreviva a
reinicios.

**No cubre:** la consulta por parte del usuario (HU-06-04), la detección de depósitos
(épica 07) ni los retiros (épica 08).

**Supuesto:** las cuentas existen y se identifican según la épica 01; el asignador tiene
acceso a un almacenamiento persistente y a la función de derivación de HU-06-02.

**Modelo de disparo (eager primario, lazy fallback).** La asignación se decide de forma
**canónica eager**: al crearse una cuenta (épica 01, HU-01-01) el sistema asigna y persiste
**de inmediato** su `address_index` y deriva su dirección (RN-12). Esto elimina la ventana
en la que un depósito podría llegar antes de que la dirección exista y permite que la épica
07 monitoree la dirección desde el alta. La asignación on-demand en la primera consulta
(HU-06-04 RN-5) es un **fallback idempotente** (consistencia eventual): si por cualquier
motivo la dirección no existiera, la primera consulta la asigna sin crear un segundo índice.

**Naturaleza de la operación y contrato.** La asignación es una **operación interna** del
sistema; **no** expone un endpoint HTTP propio. El recurso visible para el usuario es el
endpoint de consulta de HU-06-04 (`GET /api/v1/deposit-address`, épica 09 HU-09-01 RN-10).
Por lo tanto, los criterios de aceptación de esta HU se evalúan **sobre el estado
persistido** y sobre el evento de integración (RN-11), no sobre una respuesta HTTP propia.
El registro persistido de una asignación contiene, como mínimo: `accountId`, `addressIndex`
(entero), `address` (checksum EIP-55), `derivationPath`
(`m/44'/60'/0'/0/{addressIndex}`), `network` (`"sepolia"`) y `chainId` (`"11155111"`).

## Reglas de negocio e invariantes
1. **RN-1 (índice por cuenta, monótono):** a cada cuenta se le asigna un `address_index`
   entero **único**, de forma **monótona creciente**, comenzando en `0`, **sin reúso** (un
   índice liberado no se reutiliza; la baja de cuentas está fuera de alcance). En el camino
   normal los índices son además **contiguos** (`{0, 1, …, max}` sin huecos). **Reconciliación
   con BIP-32 (HU-06-02 RN-8):** en el caso excepcionalmente improbable (~2⁻¹²⁷) de que un
   índice produzca una clave BIP-32 inválida, ese índice se **salta de forma determinista** y
   el **próximo índice válido** se asigna a la cuenta, **registrando en el mapeo el
   `address_index` efectivamente usado** (no el nominal saltado). Por lo tanto la garantía
   formal es **monotonía estricta**, con **posibles huecos de medida cero** únicamente por
   índices BIP-32 inválidos, cuya ocurrencia se registra para auditoría. En ausencia de ese
   evento (la práctica) la secuencia es contigua desde 0.
2. **RN-2 (path e inmutabilidad):** el índice se mapea al path
   `m / 44' / 60' / 0' / 0 / address_index` (HU-06-02). Una vez asignado, el índice de una
   cuenta es **inmutable**: nunca cambia, por lo que la dirección es estable de por vida.
3. **RN-3 (una dirección, ambos activos):** la cuenta tiene **una sola** dirección de
   depósito, válida para **ETH** y **USDC-mock** en **Sepolia (chainId 11155111)**. No se
   derivan direcciones distintas por activo: ETH (nativo) y USDC (ERC-20) se reciben en la
   **misma** dirección EOA.
4. **RN-4 (idempotencia de asignación):** solicitar la asignación/obtención de la dirección
   de una cuenta más de una vez devuelve **siempre el mismo** índice y la **misma**
   dirección; nunca asigna un índice nuevo a una cuenta que ya tiene uno.
5. **RN-5 (unicidad de direcciones):** índices distintos producen direcciones distintas; el
   mapeo cuenta ↔ dirección es **biyectivo** y se verifica de forma directa (dos cuentas
   distintas nunca comparten dirección).

   > **Nota teórica (no es regla verificable, no implica lógica de implementación).** La
   > inyectividad índice → dirección está **computacionalmente garantizada** por las
   > propiedades de secp256k1 + Keccak-256 (espacio de 2¹⁶⁰); una colisión es físicamente
   > imposible en la escala del proyecto. No se implementa lógica de "avanzar al siguiente
   > índice por colisión", por ser código muerto inalcanzable.
6. **RN-6 (atomicidad / concurrencia):** la obtención del siguiente índice es **atómica /
   serializada**: bajo asignaciones concurrentes, no se entrega el mismo índice a dos
   cuentas, ni se generan huecos. El resultado es un conjunto de índices únicos y
   contiguos.
7. **RN-7 (persistencia y recuperación — INV-8):** el mapeo `cuenta → address_index` se
   persiste; tras un reinicio, la dirección de cada cuenta se reconstruye **idéntica**
   (porque `seed + índice` la determinan de forma pura, HU-06-02).
8. **RN-8 (formato de la dirección):** la dirección asignada se representa como `0x` + 40
   hexadecimales con **checksum EIP-55** (RN-4 de HU-06-02).
9. **RN-9 (custodia):** la asignación expone solo la **dirección** (y opcionalmente el path
   o índice, datos no secretos); nunca la clave privada ni el seed.
10. **RN-10 (cuenta válida):** solo se asigna dirección a una cuenta existente. Si la cuenta
    referenciada no existe, se rechaza con `ACCOUNT_NOT_FOUND` (404), conforme a
    `00-fundaciones/modelo-de-errores.md`.
11. **RN-11 (contrato de integración con la épica 07):** cuando una dirección queda asignada,
    el sistema **emite un evento de dominio interno**
    `DepositAddressAssigned { accountId, addressIndex, address, chainId }` (con
    `chainId = "11155111"`) que la épica 07 consume para **registrar esa dirección en su
    conjunto de direcciones monitoreadas**. De forma equivalente/complementaria, el sistema
    expone una **consulta interna** del conjunto de direcciones asignadas (p. ej.
    `GET /internal/deposit-addresses`, no pública) que la épica 07 puede leer al arrancar
    para cargar todas las direcciones existentes. Este contrato satisface la dependencia de
    HU-07-01 RN-1/RN-7 ("dirección de depósito conocida provista por la épica 06"): toda
    dirección asignada es conocible por el monitor **desde el momento de su asignación**
    (eager, RN-12), de modo que no existe una ventana en la que un depósito a una dirección
    ya asignada quede sin monitorear.
12. **RN-12 (disparo eager primario; fallback idempotente):** la asignación se dispara **de
    forma eager al crear la cuenta** (épica 01, HU-01-01): la dirección existe y se emite el
    evento de RN-11 **inmediatamente después** del alta, sin esperar a que el usuario
    consulte. La asignación on-demand en la primera consulta (HU-06-04 RN-5) es un **fallback
    idempotente** (RN-4): si la dirección ya existe, la devuelve; si no, la asigna sin crear
    un segundo índice. Bajo concurrencia, la combinación alta-eager + fallback-on-demand
    nunca asigna dos índices a la misma cuenta (RN-6).
13. **RN-13 (límite del `address_index`):** los índices se asignan dentro del rango
    no-hardened de BIP-44 (`[0, 2³¹ − 1]`, HU-06-02 RN-9). Si la secuencia de asignación
    alcanzara `2³¹ − 1` (inalcanzable en la escala del proyecto), nuevas asignaciones se
    **rechazan** con `INTERNAL_ERROR` (500) documentado, en lugar de producir silenciosamente
    un índice hardened.

## Criterios de aceptación (DoD)

### Escenario 1: Asignación a una cuenta nueva [AT-06-03-01]
- Dado una cuenta existente sin dirección de depósito asignada
- Cuando el Sistema realiza la asignación
- Entonces se le asigna un `address_index` único y monótono
- Y se deriva (HU-06-02) y persiste una dirección con checksum EIP-55 válido
- Y la dirección queda asociada exclusivamente a esa cuenta (RN-1, RN-2, RN-8)

### Escenario 2 (idempotencia): Reasignación devuelve la misma dirección [AT-06-03-02]
- Dado una cuenta que **ya** tiene un `address_index` y dirección asignados
- Cuando se solicita nuevamente la asignación/obtención de su dirección
- Entonces se devuelve **el mismo** índice y la **misma** dirección
- Y **no** se asigna un índice nuevo (RN-4)

### Escenario 3: Unicidad y contigüidad entre cuentas [AT-06-03-03]
- Dado un sistema en **estado limpio** (sin asignaciones previas) y dos cuentas distintas
  A y B sin dirección asignada
- Cuando se les asigna dirección de forma **secuencial** (primero A, luego B)
- Entonces A recibe `address_index = 0` y B recibe `address_index = 1` (distintos y
  contiguos)
- Y sus direcciones de depósito son **distintas** entre sí (RN-1, RN-5)

### Escenario 4: Una dirección válida para ETH y USDC [AT-06-03-04]
- Dado una cuenta con dirección de depósito asignada
- Cuando se consulta la dirección de depósito para el activo ETH y para el activo USDC
- Entonces ambas consultas devuelven **exactamente la misma** dirección
- Y la dirección corresponde a la red Sepolia (chainId 11155111) (RN-3)

### Escenario 5 (concurrencia): Asignaciones simultáneas sin colisión [AT-06-03-05]
- Dado un sistema en **estado limpio** y **N = 20** cuentas distintas que solicitan
  asignación de dirección de forma **concurrente** (p. ej. 20 hilos/goroutines disparando la
  asignación en el mismo ciclo)
- Cuando el Sistema procesa las solicitudes
- Entonces el conjunto de índices asignados es **exactamente `{0, 1, …, 19}`** (ningún índice
  repetido, sin huecos)
- Y se producen **20 direcciones distintas**, una por cuenta (RN-6)

### Escenario 6 (persistencia): Reconstrucción tras reinicio [AT-06-03-06]
- Dado un conjunto de cuentas con índices y direcciones asignados
- Cuando el sistema se reinicia y se reconstruye el estado desde el almacenamiento
- Entonces cada cuenta conserva el **mismo** `address_index` y la **misma** dirección
  (RN-7, INV-8)

### Escenario 7 (reproducibilidad): Coherencia índice → dirección [AT-06-03-07]
- Dado el seed de prueba canónico `MNEMONIC_HARDHAT`
  (= `"test test test test test test test test test test test junk"`, HU-06-02) y la cuenta
  a la que se asignó `address_index = 0`
- Cuando se deriva su dirección de depósito
- Entonces la dirección es exactamente `0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266`
  (consistente con el known-answer test de HU-06-02)

### Escenario 8 (error): Cuenta inexistente [AT-06-03-08]
- Dado una referencia a una cuenta que **no** existe
- Cuando se solicita asignar/obtener su dirección de depósito
- Entonces la operación se rechaza con `ACCOUNT_NOT_FOUND` (HTTP 404) y
  `details.accountId`
- Y no se asigna ningún índice ni se deriva ninguna dirección

### Escenario 9 (eager): La dirección existe al crear la cuenta [AT-06-03-09]
- Dado un sistema en estado limpio
- Cuando se crea una cuenta nueva (épica 01, HU-01-01)
- Entonces, **inmediatamente después del alta y sin ninguna consulta previa del usuario**,
  la cuenta tiene un `address_index` y una dirección de depósito persistidos (RN-12)
- Y el registro persistido contiene `accountId`, `addressIndex`, `address` (checksum
  EIP-55), `derivationPath`, `network = "sepolia"` y `chainId = "11155111"`

### Escenario 10 (integración con épica 07): Evento de asignación [AT-06-03-10]
- Dado que se asigna una dirección a una cuenta
- Cuando la asignación se confirma (persistida)
- Entonces el sistema emite el evento `DepositAddressAssigned` con
  `{ accountId, addressIndex, address, chainId = "11155111" }` (RN-11)
- Y la dirección queda incluida en el conjunto consultable internamente por la épica 07
  (p. ej. vía `GET /internal/deposit-addresses`), de modo que el monitor la conoce desde la
  asignación

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-06-03-01..10) pasan
- [ ] Reglas de negocio RN-1..RN-13 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md (`ACCOUNT_NOT_FOUND`)
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md), en
      particular INV-8 (persistencia/recuperación del mapeo cuenta → índice) e
      INV-EPICA-06-A (monotonía/contigüidad e inmutabilidad del `address_index`, ver README)
- [ ] Contrato de integración con la épica 07 verificado: evento `DepositAddressAssigned`
      y/o consulta interna del conjunto de direcciones asignadas (RN-11)
- [ ] Adherencia verificada al estándar on-chain citado (BIP-44 `address_index`, derivación
      reproducible de HU-06-02, checksum EIP-55)
