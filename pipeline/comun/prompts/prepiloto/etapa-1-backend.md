Etapa 1 de 3: **backend**.

Implementá el backend del exchange **acotado al alcance de esta corrida**, que es un
subconjunto de la spec. El alcance está enumerado abajo: es exhaustivo, y lo que no
figura ahí no se implementa en esta corrida.

## Alcance de esta corrida

- **Épica `01` (cuentas y autenticación), sólo dos HU:**
  - `HU-01-01` registro de usuario;
  - `HU-01-02` inicio de sesión.
  Las HU `01-03` (cierre y expiración de sesión) y `01-04` (consulta de perfil)
  quedan **fuera**.
- **Épica `06` (wallet HD y direcciones), completa:** `HU-06-01` a `HU-06-04`
  (generación y custodia del seed, derivación jerárquica BIP-32/BIP-44, asignación de
  dirección de depósito, consulta de dirección de depósito).
- **Épica `09` (API HTTP/WebSocket), sólo lo que las HU de arriba exponen:**
  - de `HU-09-01`, los tres endpoints del alcance: `POST /api/v1/auth/register`,
    `POST /api/v1/auth/login` y `GET /api/v1/deposit-address?asset=ETH`, con sus
    formatos de request/response y sus códigos de estado tal como el contrato los
    define;
  - `HU-09-02` (autenticación y autorización de la API) aplicada a esos endpoints;
  - `HU-09-05` (modelo de errores de la API), completa: la estructura uniforme de error
    y los `code` del catálogo que estos endpoints pueden devolver.
  El resto del contrato REST, el WebSocket público (`HU-09-03`) y el privado
  (`HU-09-04`) quedan **fuera**.

Todo lo demás de la spec —balances y ledger, matching, órdenes, settlement, depósitos
on-chain, retiros— queda **fuera de esta corrida**. No implementes endpoints,
entidades ni servicios de esas épicas, ni siquiera como stub.

Los documentos de `spec/00-fundaciones/` **rigen igual** y hay que leerlos completos:
las convenciones monetarias, el modelo de errores y las invariantes globales aplican al
código de esta etapa aunque su épica no esté en el alcance.

## Indicaciones

- La spec no fija lenguaje ni framework de servidor: elegí el stack que consideres más
  adecuado y justificá brevemente la elección en el README del repo.
- El contrato de la épica 09 es el que consumirán los clientes de las etapas siguientes:
  respetalo literalmente en los endpoints del alcance.
- La interacción con la red (chainId 11155111) se hace vía JSON-RPC contra el endpoint
  configurable definido por la spec; no asumas servicios de terceros no especificados.
- **Nodo disponible para probar:** durante esta corrida tenés un nodo JSON-RPC de esa red
  en `http://host.docker.internal:8545`. Usalo para verificar tu implementación. La URL
  **sigue siendo configuración**, como la spec exige: no la fijes en el código ni la
  conviertas en default obligatorio, porque el sistema se ejecutará después contra otro
  endpoint.
- Exponé un endpoint de health-check simple, p. ej. `GET /health` — elegí la ruta y
  documentala en el README del proyecto.
- La etapa se considera completa cuando el backend compila/arranca, responde ese
  health-check, y las HU del alcance están implementadas según sus criterios de
  aceptación.

Al terminar, dejá documentado en el README cómo instalar dependencias, configurar el
entorno (variables, RPC, base de datos si aplica) y levantar el servidor.
