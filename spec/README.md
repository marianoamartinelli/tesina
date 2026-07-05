# Especificación funcional — Exchange de criptomonedas (tesina)

Este repositorio contiene la **especificación funcional completa** de un exchange de
criptomonedas centralizado y simplificado, redactada en español, organizada en épicas
y Historias de Usuario (HU) con criterios de aceptación testeables.

---

## 1. Objetivo de la especificación y su doble rol

Esta spec cumple **dos roles simultáneos**:

1. **Insumo (input) común del pipeline de agentes.** Es el material de entrada idéntico
   para las 4 corridas de un experimento factorial 2×2 (modelo A/B × con/sin RAG). Cada
   corrida recibe exactamente la misma spec y debe producir una implementación del
   exchange a partir de ella.

2. **Criterio objetivo de evaluación (holdout).** Los criterios de aceptación expresados
   en lenguaje natural (escenarios Gherkin + reglas) constituyen el **conjunto de
   validación holdout**. El modelo codificador **NO puede modificarlos**: son la vara
   con la que se mide, de forma objetiva y reproducible, cuán correcta es cada
   implementación generada.

Como consecuencia de este doble rol, **toda la spec debe ser precisa, no ambigua y
testeable**. Cada afirmación normativa tiene que poder convertirse en un test
automatizable que dé verdadero/falso sin juicio subjetivo. Cuando un comportamiento
admite más de una interpretación razonable, la spec **fija una** y la declara como
convención.

---

## 2. Alcance

### Dentro de alcance

- **Matching engine:** órdenes `limit` y `market`, prioridad **precio-tiempo**,
  persistencia del orderbook, emisión de eventos de ejecución (fills).
- **Reglas de negocio:** cuentas, balances (disponible/bloqueado), fees maker/taker,
  settlement interno **atómico** al momento del match, validaciones de entrada,
  API HTTP y WebSocket.
- **Capa on-chain (mínima):** derivación de claves BIP-32/39/44 (coin type 60),
  firma y broadcast de transacciones EIP-155, detección y acreditación de depósitos,
  procesamiento de retiros.
- **UX:** cliente **web (React)** y cliente **mobile (React Native / Expo)**.

### Fuera de alcance

- KYC / AML.
- Múltiples redes on-chain (solo **Sepolia**, chainId `11155111`).
- Tipos de orden avanzados (stop, OCO, iceberg, trailing, etc.).
- Múltiples pares de trading (solo **ETH / USDC-mock**).
- Alta disponibilidad y baja latencia de grado industrial.
- Hardening de seguridad de producción (rotación de secretos, HSM, auditoría
  exhaustiva, protección DDoS, etc.).

> Las HU son **agnósticas a la implementación del backend**: no fijan lenguaje ni
> framework de servidor. El frontend sí está fijado por alcance (React y
> React Native/Expo).

---

## 3. Listado de épicas

| Épica | Carpeta                          | Resumen (una línea)                                                                       |
|-------|----------------------------------|------------------------------------------------------------------------------------------|
| 00    | `00-fundaciones`                 | Convenciones transversales: glosario, activos/par, dinero, errores, invariantes.         |
| 01    | `01-cuentas-y-autenticacion`     | Registro, autenticación, sesiones/credenciales de API y autorización de operaciones.     |
| 02    | `02-balances-y-ledger`           | Modelo de balances disponible/bloqueado y ledger interno de doble entrada por activo.    |
| 03    | `03-motor-de-matching`           | Orderbook persistente, matching limit/market y prioridad precio-tiempo.                  |
| 04    | `04-gestion-de-ordenes`          | Ciclo de vida de órdenes: alta, consulta, cancelación, estados y validaciones.           |
| 05    | `05-settlement-y-fees`           | Liquidación interna atómica del fill y cálculo/cobro de fees maker/taker.                |
| 06    | `06-wallet-hd-y-direcciones`     | Wallet HD (BIP-32/39/44), derivación de direcciones de depósito por cuenta.               |
| 07    | `07-depositos-on-chain`          | Detección de depósitos, confirmaciones, reorgs y acreditación idempotente.                |
| 08    | `08-retiros-on-chain`            | Solicitud, firma EIP-155, broadcast, gestión de nonce/gas y anti-replay de retiros.      |
| 09    | `09-api-http-websocket`          | Contrato de la API HTTP/REST y WebSocket: endpoints, paginación, formato de errores.     |
| 10    | `10-cliente-web`                 | UX web (React): trading, balances, depósitos/retiros, market data en tiempo real.        |
| 11    | `11-cliente-mobile`              | UX mobile (React Native/Expo): paridad funcional con web según alcance.                   |

---

## 4. Convención de identificadores

### IDs de Historias de Usuario

```
HU-<epica>-<seq>
```

- `<epica>`: número de épica con dos dígitos (`01`..`11`).
- `<seq>`: número secuencial de la HU dentro de la épica, dos dígitos (`01`, `02`, ...).

Ejemplo: `HU-03-02` es la segunda HU de la épica 03 (motor de matching).

### IDs de tests de aceptación

```
AT-<epica>-<huSeq>-<NN>
```

- `<epica>`: número de épica con dos dígitos.
- `<huSeq>`: secuencia de la HU dentro de la épica (la misma que en el ID de la HU).
- `<NN>`: número del criterio/test de aceptación dentro de la HU, dos dígitos,
  opcionalmente seguido de un **sufijo de una letra minúscula** para variantes
  estrechamente relacionadas del mismo caso (p. ej. `AT-01-01-04a`..`AT-01-01-04e`,
  cinco variantes de "formato de email inválido").

Ejemplo: `AT-03-02-01` es el primer criterio de aceptación de la HU `HU-03-02`.

Reglas del sufijo (consecuencia de la estabilidad de los AT-id):

- Cuando un caso nace dividido en variantes, éstas usan sufijos contiguos desde `a`
  (`04a`, `04b`, …) y **no existe** el id base sin sufijo (`04`).
- Cuando a un AT base ya existente se le agrega después una variante, el id base **se
  conserva** (no se renombra a `a`) y la variante nueva toma el sufijo `b` (p. ej.
  `AT-08-01-12` y `AT-08-01-12b`): el base cuenta como primera variante.
- Un AT sufijado es un test independiente a todos los efectos (se reporta por su id
  completo).

> Los **AT-id son la unidad de trazabilidad** del experimento. Cada test del holdout se
> referencia por su AT-id; los reportes de evaluación de cada corrida indican qué AT-id
> pasan y cuáles fallan. Los AT-id **son estables**: no se reutilizan ni se renumeran.

---

## 5. Decisiones de diseño tomadas

Estas decisiones están **fijadas** y aplican a toda la spec. No son negociables por la
implementación.

1. **Idioma:** español para la redacción; términos técnicos y de dominio en su forma
   original (maker/taker, orderbook, fill, settlement, HD wallet, BIP/EIP, nonce, gas,
   etc.). El glosario en `00-fundaciones/glosario.md` es la referencia única.
2. **Par único:** **ETH (base) / USDC-mock (quote)**. El precio se expresa en **USDC por
   ETH**. No hay otros pares.
3. **Red única:** **Sepolia**, chainId `11155111`. USDC es un ERC-20 mock desplegado en
   testnet (6 decimales). ETH es nativo (18 decimales).
4. **Formato de criterios de aceptación:** combinación de **escenarios Gherkin**
   (`Dado / Cuando / Entonces`, en español) **+ reglas** explícitas (listas de
   condiciones, tablas de ejemplo, fórmulas). El Gherkin describe flujos; las reglas
   fijan los detalles cuantitativos y los bordes.
5. **Granularidad exhaustiva:** se cubren casos felices, bordes y casos de error de forma
   explícita. Se prefiere redundancia controlada antes que ambigüedad.
6. **Trazabilidad por AT-id:** todo comportamiento verificable tiene un AT-id; la
   evaluación se reporta por AT-id.
7. **Dinero en enteros:** todos los montos se manejan en **enteros de la unidad mínima**
   (wei para ETH; unidades de 6 decimales para USDC). **Prohibido** el uso de floats
   binarios para montos o precios. Ver `00-fundaciones/convenciones-monetarias.md`.
8. **Serialización de montos:** en la API, los montos y precios viajan como **strings de
   enteros** en unidades mínimas.
9. **Errores uniformes:** toda respuesta de error sigue la estructura
   `{ code, message, details }` del catálogo en `00-fundaciones/modelo-de-errores.md`.
10. **Invariantes globales:** las propiedades de `00-fundaciones/invariantes-globales.md`
    (conservación de fondos, no-negatividad, atomicidad, idempotencia, anti-replay) deben
    cumplirse en **toda** corrida y forman parte del criterio de evaluación.

---

## 6. Guía de la carpeta `00-fundaciones`

La carpeta `00-fundaciones` contiene las **convenciones transversales** que el resto de
las épicas dan por supuestas. **Leer estos documentos primero.**

| Archivo                          | Qué define                                                                                          |
|----------------------------------|----------------------------------------------------------------------------------------------------|
| `glosario.md`                    | Vocabulario de dominio compartido (maker/taker, orderbook, fill, settlement, HD wallet, etc.).     |
| `activos-y-par-de-trading.md`    | ETH y USDC-mock, decimales, red/chainId, coin type, representación de precio, tick/lot/min notional.|
| `convenciones-monetarias.md`     | Representación entera del dinero, prohibición de floats, redondeo, precisión y serialización.       |
| `modelo-de-errores.md`           | Catálogo de errores de dominio (code/descripción/disparador) y forma uniforme de la respuesta.     |
| `invariantes-globales.md`        | Invariantes chequeables que toda implementación debe respetar y que se usan como evaluación.        |

### Orden de lectura recomendado

1. `glosario.md` — para fijar vocabulario.
2. `activos-y-par-de-trading.md` — para entender el objeto del intercambio.
3. `convenciones-monetarias.md` — para entender cómo se cuentan los montos.
4. `modelo-de-errores.md` — para entender cómo se rechazan operaciones inválidas.
5. `invariantes-globales.md` — para entender qué nunca debe romperse.
6. Épicas `01`..`11` en orden.

> Ante cualquier conflicto entre una HU de épica y un documento de `00-fundaciones`,
> **prevalece `00-fundaciones`**.
