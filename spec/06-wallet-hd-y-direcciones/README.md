# Épica 06 — Wallet HD y Direcciones de Depósito

## Objetivo de la épica

Proveer la base criptográfica on-chain del exchange: una **wallet jerárquica
determinística (HD)** conforme a los estándares **BIP-39** (mnemonic), **BIP-32**
(derivación de claves) y **BIP-44** (estructura de rutas de derivación, coin type `60`
para Ethereum). A partir de un único seed maestro, el sistema deriva de forma
**determinística y reproducible** una **dirección de depósito por cuenta de usuario**,
válida tanto para **ETH** (nativo) como para **USDC-mock** (ERC-20) en la **misma red**
(Sepolia, chainId `11155111`), y permite al usuario **consultar** dicha dirección.

Esta épica es la pieza de la que dependen las épicas on-chain posteriores:
`07-depositos-on-chain` (detecta transferencias entrantes a estas direcciones) y
`08-retiros-on-chain` (firma transacciones EIP-155 con las claves derivadas de este
mismo seed).

---

## Alcance

### Dentro de alcance

- Generación del **seed/mnemonic** HD (BIP-39) con entropía de un CSPRNG y su **custodia
  segura** básica (no exposición por API, no logging, persistencia estable).
- **Derivación determinística** de claves siguiendo BIP-32/BIP-44 con el path estándar de
  Ethereum `m / 44' / 60' / 0' / 0 / address_index` (índices `purpose`, `coin_type` y
  `account` **hardened** según el estándar).
- Cómputo de la **dirección Ethereum** a partir de la clave pública (Keccak-256 + checksum
  **EIP-55**).
- **Asignación** de una dirección de depósito **única por cuenta** mediante un índice de
  derivación monótono, persistente e inmutable.
- **Consulta** por parte del usuario autenticado de su dirección de depósito por
  activo/red.
- **Reproducibilidad** verificable mediante known-answer tests (vectores de prueba
  canónicos).

### Fuera de alcance

- Detección, confirmación y acreditación de depósitos on-chain (épica `07`).
- Firma, broadcast, gestión de nonce/gas de retiros (épica `08`).
- Hardening de seguridad de producción: HSM, rotación de secretos, multi-firma, esquemas
  de respaldo distribuido (Shamir), key ceremony. La custodia aquí es la **mínima** del
  caso de estudio (ver `00-fundaciones/README` / decisiones de alcance).
- Múltiples redes, múltiples wallets o coin types distintos de `60`.
- Rotación de direcciones de depósito por usuario (cada cuenta tiene **una** dirección
  estable).

---

## Historias de Usuario de la épica

| ID         | Título                                            | Resumen (una línea)                                                                                  |
|------------|---------------------------------------------------|-----------------------------------------------------------------------------------------------------|
| HU-06-01   | Generación y custodia del seed HD                 | Generar el seed/mnemonic BIP-39 (raíz de toda la wallet) con entropía segura y custodiarlo sin exponerlo. |
| HU-06-02   | Derivación jerárquica BIP-32/BIP-44               | Derivar claves y direcciones de forma determinística con el path Ethereum estándar (coin type 60, hardened). |
| HU-06-03   | Asignación de dirección de depósito               | Asignar a cada cuenta una dirección de depósito única (por índice de derivación), válida para ETH y USDC. |
| HU-06-04   | Consultar dirección de depósito                   | Permitir al usuario autenticado consultar su dirección de depósito por activo/red.                   |

---

## Dependencias hacia otras épicas

- **01 — Cuentas y autenticación:** la asignación de índice/dirección se ancla a una
  **cuenta** existente. **HU-06-03 depende de HU-01-01 (registro/creación de cuenta)**: el
  alta de una cuenta dispara **de forma eager** la asignación de su dirección (HU-06-03
  RN-12). La consulta **HU-06-04 depende de HU-01-02 (inicio de sesión) y HU-01-03
  (cierre/expiración de sesión)** para la autenticación; la identidad de la cuenta se deriva
  exclusivamente del token.
- **00 — Fundaciones:** glosario (HD wallet, seed, derivation path, dirección, EIP-55),
  red/chainId y coin type (`activos-y-par-de-trading.md`), modelo de errores
  (`modelo-de-errores.md`), invariantes globales (`invariantes-globales.md`) y
  convenciones de serialización (`convenciones-monetarias.md`).
- **09 — API HTTP/WebSocket:** el contrato REST del endpoint de consulta
  (`GET /api/v1/deposit-address`) lo fija HU-09-01 RN-10 (respuesta `{ asset, address }`
  —más `tokenAddress` cuando `asset = USDC`, HU-06-04 RN-6—, **HTTP 200**, identidad por
  token).

**Dependientes de esta épica:**

- `07-depositos-on-chain`: acredita a las direcciones asignadas aquí. **Contrato de
  integración (HU-06-03 RN-11):** al asignar una dirección, la épica 06 emite el evento de
  dominio `DepositAddressAssigned { accountId, addressIndex, address, chainId }` y expone una
  consulta interna del conjunto de direcciones asignadas (p. ej.
  `GET /internal/deposit-addresses`). La épica 07 consume el evento (para registrar nuevas
  direcciones a monitorear) y/o la consulta interna (para cargar todas al arrancar). Como la
  asignación es **eager** al alta de la cuenta, toda dirección es conocible por el monitor
  desde su creación: no hay ventana en la que un depósito a una dirección ya asignada quede
  sin monitorear.
- `08-retiros-on-chain`: firma con las claves derivadas del seed de aquí.

---

## Invariantes y reglas clave de la épica

- **Determinismo / reproducibilidad (BIP-32/39/44):** una función pura del par
  `(seed, derivation_path)`. El mismo seed y el mismo path producen **siempre** la misma
  clave privada, clave pública y dirección. Verificable con known-answer tests.
- **Path estándar de Ethereum:** `m / 44' / 60' / 0' / 0 / address_index`, con
  `purpose' = 44'`, `coin_type' = 60'` y `account' = 0'` **hardened** (offset
  `0x80000000` = 2³¹ = `2147483648`), y `change = 0` (cadena externa) y `address_index`
  **no hardened**. El índice por usuario es `address_index`.
- **Una dirección por cuenta, válida para ambos activos:** dado que ETH (nativo) y
  USDC-mock (ERC-20) comparten la **misma cuenta on-chain (EOA)** de 20 bytes en la misma
  red, una sola dirección recibe ambos activos en Sepolia.
- **Unicidad y biyección cuenta ↔ índice ↔ dirección:** índices distintos producen
  direcciones distintas; el índice es **único, monótono creciente desde 0, sin reúso e
  inmutable**. En el camino normal la secuencia es además **contigua** (`{0, 1, …, max}`);
  formalmente se garantiza monotonía estricta con **posibles huecos de medida cero** solo si
  un índice produce una clave BIP-32 inválida (~2⁻¹²⁷, HU-06-02 RN-8), caso en que se salta
  de forma determinista y se registra el índice efectivamente usado (HU-06-03 RN-1). Ver
  **INV-EPICA-06-A** abajo.
- **Idempotencia de asignación:** asignar/consultar repetidamente la dirección de una
  cuenta devuelve **siempre la misma** dirección (no genera un índice nuevo).
- **Checksum EIP-55:** toda dirección devuelta por la API está codificada con checksum
  EIP-55 (mayúsculas/minúsculas mixtas), `0x` + 40 hexadecimales.
- **Anti-replay de red (EIP-155 / INV-6):** todas las direcciones y claves operan sobre
  **Sepolia, chainId `11155111`**; la firma de transacciones salientes (épica 08) usa ese
  chainId. Una consulta para una red distinta se rechaza con `CHAIN_ID_MISMATCH`.
- **Custodia del secreto maestro:** el seed/mnemonic y las claves privadas derivadas
  **nunca** se serializan en respuestas de API ni se escriben en logs; solo las claves
  **públicas** y las **direcciones** salen del sistema. El seed se persiste **cifrado en
  reposo con AES-256-GCM** (nonce por operación, tag autenticado; HU-06-01 RN-6).
- **Persistencia y recuperación (INV-8):** el seed y el mapeo cuenta → índice persisten y
  se reconstruyen idénticos tras un reinicio; nunca se regenera el seed (regenerarlo
  cambiaría todas las direcciones y rompería la asignación a usuarios). La persistencia del
  seed es **atómica** (HU-06-01 RN-9) y al arrancar se ejecuta un **smoke test de integridad**
  que verifica que el seed cargado deriva las direcciones persistidas; si falla, el sistema
  **aborta** sin regenerar (HU-06-01 RN-10/RN-11).
- **Sin floats / serialización (convenciones monetarias):** esta épica no maneja montos,
  pero respeta la convención general de serialización por string; identificadores como
  `chainId` se serializan como **string** (`"11155111"`) con su valor fijado.

### INV-EPICA-06-A — Monotonía/contigüidad e inmutabilidad del `address_index`

**Propiedad.** En todo momento, el conjunto de `address_index` asignados forma
`{0, 1, …, max_asignado}` (contiguo, sin repeticiones) en el camino normal; formalmente, es
**monótono creciente desde 0 sin reúso**, admitiendo huecos solo por índices BIP-32
inválidos (medida cero, HU-06-03 RN-1). El par `(cuenta, address_index)` es **inmutable** una
vez asignado.

**Cómo verificar.** Consultar la tabla de mapeo `cuenta → address_index` y afirmar que: (a)
no hay índices duplicados; (b) es estrictamente creciente en orden de asignación; (c) salvo
huecos auditados por índice BIP-32 inválido, cubre `{0, …, max}` sin huecos; (d) el índice de
una cuenta nunca cambia entre snapshots ni tras un reinicio (INV-8).
