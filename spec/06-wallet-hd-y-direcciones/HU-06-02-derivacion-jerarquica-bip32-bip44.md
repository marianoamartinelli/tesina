# HU-06-02 — Derivación jerárquica BIP-32/BIP-44

- **Epica:** 06 — Wallet HD y Direcciones de Depósito
- **Actor / rol:** Sistema (motor de derivación de claves de la wallet HD)
- **Prioridad:** Alta
- **Dependencias:** HU-06-01 (seed/mnemonic raíz)
- **Estandares de dominio aplicables:** BIP-32 (derivación de claves maestra e hija,
  hardened/normal sobre curva secp256k1), BIP-44 (estructura de path
  `m / purpose' / coin_type' / account' / change / address_index`), coin type **60**
  (Ethereum, SLIP-44), EIP-55 (checksum de direcciones), Keccak-256 (derivación de la
  dirección). Red única: Sepolia, chainId 11155111.

## Historia
Como **Sistema**, quiero **derivar claves y direcciones de forma determinística siguiendo
BIP-32/BIP-44 con el path estándar de Ethereum (coin type 60, índices hardened según el
estándar)**, para **obtener, a partir de un único seed y un índice, exactamente la
dirección Ethereum correcta y reproducible, conforme a los estándares de la industria**.

## Contexto y alcance
Esta HU cubre la **función de derivación**: a partir de la seed binaria (HU-06-01) y un
`address_index`, computar la clave privada, la clave pública (secp256k1) y la **dirección
Ethereum** (Keccak-256 + checksum EIP-55), usando el path BIP-44 estándar de Ethereum
`m / 44' / 60' / 0' / 0 / address_index`. La corrección y reproducibilidad se verifican
con **known-answer tests** (vectores canónicos públicos).

**No cubre:** la elección/asignación del `address_index` a una cuenta concreta (HU-06-03),
ni la exposición vía API (HU-06-04), ni la firma de transacciones (épica 08). La derivación
es una **función pura** de `(seed, path)`; no depende de estado mutable.

**Supuesto:** la seed proviene de HU-06-01 y se opera siempre en memoria controlada; las
claves privadas derivadas no abandonan el sistema.

## Reglas de negocio e invariantes
1. **RN-1 (clave maestra BIP-32):** la clave maestra se obtiene como
   `I = HMAC-SHA512(key = "Bitcoin seed", data = seed)`; `I_L = I[0:32]` es la clave
   privada maestra y `I_R = I[32:64]` es el chain code maestro. Se valida `1 ≤ I_L < n`,
   con `n` = orden del grupo de secp256k1
   (`0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141`).
2. **RN-2 (path estándar Ethereum, BIP-44):** la derivación usa el path
   `m / 44' / 60' / 0' / 0 / address_index`, donde:
   - `purpose' = 44'` (hardened), `coin_type' = 60'` (hardened, Ethereum),
     `account' = 0'` (hardened),
   - `change = 0` (cadena externa, **no** hardened),
   - `address_index` = índice del usuario (**no** hardened).
   El offset hardened es `0x80000000 = 2³¹ = 2147483648`; por lo tanto los componentes
   hardened se codifican como `44 + 2³¹ = 2147483692`, `60 + 2³¹ = 2147483708`,
   `0 + 2³¹ = 2147483648`.
3. **RN-3 (derivación de clave hija BIP-32):** cada paso usa `CKDpriv`:
   - **Hardened** (`i ≥ 2³¹`): `I = HMAC-SHA512(chain_code_par, 0x00 || ser256(k_par) || ser32(i))`.
   - **Normal** (`i < 2³¹`): `I = HMAC-SHA512(chain_code_par, serP(point(k_par)) || ser32(i))`.
   - La clave hija es `k_hijo = (I_L + k_par) mod n` y el chain code hijo es `I_R`.
4. **RN-4 (dirección Ethereum):** desde la clave pública secp256k1 **sin comprimir** (64
   bytes = coordenadas `X || Y`, descartando el prefijo `0x04`), la dirección es los
   **últimos 20 bytes** de `Keccak-256(X || Y)`. La dirección se serializa como `0x` + 40
   hexadecimales con **checksum EIP-55** (mayúsculas/minúsculas mixtas).
5. **RN-5 (determinismo / reproducibilidad — invariante de la épica):** la derivación es
   una **función pura** de `(seed, path)`. El mismo seed y el mismo `address_index`
   producen **siempre** la misma clave privada, clave pública y dirección, en cualquier
   ejecución y tras cualquier reinicio (INV-8).
6. **RN-6 (custodia):** las claves privadas derivadas **nunca** se serializan ni se logean;
   solo la clave pública y la dirección (datos no secretos) pueden exponerse.
7. **RN-7 (red):** las direcciones se usan exclusivamente en **Sepolia (chainId
   11155111)**. El formato de dirección es agnóstico a la red, pero el contexto operativo
   y la firma de transacciones salientes (épica 08, EIP-155) usan ese chainId (INV-6).
8. **RN-8 (borde de clave inválida, BIP-32):** si en algún paso `I_L ≥ n` o el `k_hijo`
   resultante es `0` (probabilidad ~2⁻¹²⁷, despreciable), ese índice se considera inválido
   y se **avanza al siguiente** índice, conforme a BIP-32. El comportamiento es
   determinista y reproducible. (La interacción de este salto con la contigüidad de índices
   de HU-06-03 se reconcilia en HU-06-03 RN-1.)
9. **RN-9 (rango del `address_index`, BIP-44 no-hardened):** el `address_index` debe ser un
   entero en el rango **`[0, 2³¹ − 1]` = `[0, 2147483647]`** (espacio **no-hardened** de
   BIP-32). Un `address_index ≥ 2³¹` violaría el espacio no-hardened (produciría
   silenciosamente una derivación hardened) y **se rechaza con `VALIDATION_ERROR`** (HTTP
   422), con `details.issues` indicando el parámetro `address_index`, **antes** de intentar
   la derivación. Esta validación se propaga al asignador (HU-06-03 RN-13).

### Vectores de prueba canónicos (known-answer tests)
Para validar la cadena completa BIP-32 → BIP-44 → dirección EIP-55 se usa el **mnemonic de
prueba canónico** de Hardhat/Anvil (passphrase vacía), de uso público y verificable (no es
el seed de producción):

Constante con nombre (usada literalmente en los pasos Gherkin para evitar abreviaturas con
elipsis que no son input válido):

- `MNEMONIC_HARDHAT` = `"test test test test test test test test test test test junk"`,
  `passphrase = ""`

- `mnemonic` = `MNEMONIC_HARDHAT`, `passphrase = ""`
- Path base: `m / 44' / 60' / 0' / 0 / address_index`

| `address_index` | Path                       | Dirección (EIP-55)                            |
|-----------------|----------------------------|-----------------------------------------------|
| 0               | `m/44'/60'/0'/0/0`         | `0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266`  |
| 1               | `m/44'/60'/0'/0/1`         | `0x70997970C51812dc3A010C7d01b50e0d17dc79C8`  |
| 2               | `m/44'/60'/0'/0/2`         | `0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC`  |
| 3               | `m/44'/60'/0'/0/3`         | `0x90F79bf6EB2c4f870365E785982E1f101E93b906`  |

### Vectores de checksum EIP-55 (validación de RN-4)
Vectores canónicos de EIP-55 (los cuatro casos "mixed-case" del propio EIP-55). Cada fila da
el **input crudo** (los 20 bytes en hexadecimal en **minúsculas**, sin prefijo `0x`) que
alimenta el algoritmo y el **output** esperado (checksum aplicado). El algoritmo computa
`Keccak-256` sobre la cadena ASCII en minúsculas y, para cada dígito hexadecimal, lo pasa a
mayúscula si el nibble correspondiente del hash es ≥ 8. La comparación es **carácter a
carácter**:

| input raw (lowercase, sin `0x`)              | output esperado (EIP-55)                       |
|----------------------------------------------|------------------------------------------------|
| `5aaeb6053f3e94c9b9a09f33669435e7ef1beaed`   | `0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed`   |
| `fb6916095ca1df60bb79ce92ce3ea74c37c5d359`   | `0xfB6916095ca1df60bB79Ce92cE3Ea74c37c5d359`   |
| `dbf03b407c01e7cd3cbea99509d93f8dddc8c6fb`   | `0xdbF03B407c01E7cD3CBea99509d93f8DDDC8C6FB`   |
| `d1220a0cf47c7b9be7a2e6ba89f429762e7b9adb`   | `0xD1220A0cf47c7B9Be7A2E6BA89F429762e7b9aDb`   |

## Criterios de aceptación (DoD)

### Escenario 1: Derivación del índice 0 (known-answer test) [AT-06-02-01]
- Dado el mnemonic `MNEMONIC_HARDHAT`
  (= `"test test test test test test test test test test test junk"`) con passphrase vacía
- Y el path `m/44'/60'/0'/0/0`
- Cuando el Sistema deriva la clave y computa la dirección (RN-1..RN-4)
- Entonces la dirección resultante es exactamente
  `0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266`

### Escenario 2: Derivación de múltiples índices [AT-06-02-02]
- Dado el mismo mnemonic `MNEMONIC_HARDHAT`
- Cuando se derivan los `address_index` 1, 2 y 3 con el path base
- Entonces las direcciones son, respectivamente,
  `0x70997970C51812dc3A010C7d01b50e0d17dc79C8`,
  `0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC` y
  `0x90F79bf6EB2c4f870365E785982E1f101E93b906`
- Y cada índice distinto produce una dirección distinta

### Escenario 3: Checksum EIP-55 correcto [AT-06-02-03]
- Dado, para cada fila de la tabla "Vectores de checksum EIP-55", el **input raw** de 20
  bytes en minúsculas sin `0x` (p. ej. `5aaeb6053f3e94c9b9a09f33669435e7ef1beaed`)
- Cuando el Sistema codifica ese input con checksum EIP-55 (RN-4: Keccak-256 sobre el
  lowercase, mayúscula si el nibble del hash es ≥ 8)
- Entonces el output coincide **carácter a carácter** con el vector esperado de esa fila
  (p. ej. `0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed`)
- Y toda dirección emitida por el Sistema tiene la forma `0x` + 40 hex con checksum EIP-55

### Escenario 4 (borde): Componentes hardened del path [AT-06-02-04]
- Dado el path estándar `m/44'/60'/0'/0/address_index`
- Cuando el Sistema construye los índices de derivación
- Entonces `purpose`, `coin_type` y `account` se derivan como **hardened**
  (índices `2147483692`, `2147483708`, `2147483648` respectivamente)
- Y `change = 0` y `address_index` se derivan como **no hardened** (`< 2³¹`) (RN-2)

### Escenario 5 (determinismo): Reproducibilidad de la derivación [AT-06-02-05]
- Dado un mismo seed y un mismo `address_index`
- Cuando se deriva la dirección dos veces, en momentos y procesos distintos
- Entonces ambas derivaciones producen **idéntica** clave pública y dirección (RN-5)

### Escenario 6 (persistencia): Reconstrucción tras reinicio [AT-06-02-06]
- Dado un seed persistido (HU-06-01) y un conjunto de índices ya derivados
- Cuando el sistema se reinicia y vuelve a derivar las direcciones de esos índices
- Entonces las direcciones reconstruidas son **idénticas** a las previas al reinicio
  (RN-5, INV-8)

### Escenario 7 (seguridad): La clave privada nunca se expone [AT-06-02-07]
- Dado que se derivan claves para responder a los endpoints que exponen direcciones —en
  particular `GET /api/v1/deposit-address?asset=ETH|USDC` (HU-06-04) y cualquier flujo de
  retiro que use claves derivadas (épica 08)—
- Cuando se emiten las respuestas de API/WebSocket correspondientes
- Entonces en **ninguna** respuesta aparece un campo con la clave privada derivada (ni su
  valor); solo claves públicas y/o direcciones (RN-6)
- Y un **procedimiento de auditoría estática complementario** (análisis de código o `grep`
  sobre logs/trazas de una corrida de integración) confirma que ninguna clave privada
  derivada se escribe en logs ni trazas (RN-6)

### Escenario 8 (borde / error): Índice con clave derivada inválida [AT-06-02-08]
- Dado que el **test harness inyecta** (mock/stub de `HMAC-SHA512`) un paso de derivación
  que produce `I_L ≥ n` o `k_hijo == 0` (condición de probabilidad ~2⁻¹²⁷ que no se activa
  de forma natural en una corrida real)
- Cuando el Sistema detecta la condición
- Entonces ese índice se descarta y se **avanza al siguiente** índice según BIP-32 (RN-8)
- Y el índice efectivamente usado queda registrado (consistente con HU-06-03 RN-1)
- Y el resultado sigue siendo determinista y reproducible

### Escenario 9 (borde / error): `address_index` fuera del rango no-hardened [AT-06-02-09]
- Dado un `address_index = 2147483648` (= 2³¹, primer índice hardened)
- Cuando el Sistema valida el parámetro antes de derivar (RN-9)
- Entonces se rechaza con `VALIDATION_ERROR` (HTTP 422) y `details.issues` indicando el
  parámetro `address_index`, **sin** intentar la derivación
- Y un `address_index = 2147483647` (= 2³¹ − 1, último índice no-hardened válido) **sí** se
  acepta y deriva normalmente

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-06-02-01..09) pasan
- [ ] Reglas de negocio RN-1..RN-9 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md
- [ ] Sin violacion de invariantes globales (00-fundaciones/invariantes-globales.md), en
      particular INV-8 (reproducibilidad tras reinicio) e INV-6 (red Sepolia/EIP-155)
- [ ] Adherencia verificada al estándar on-chain citado (BIP-32 CKDpriv y master key,
      BIP-44 path con coin type 60 e índices hardened, Keccak-256, checksum EIP-55;
      known-answer tests AT-06-02-01..03)
