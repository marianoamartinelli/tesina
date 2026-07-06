Etapa 1 de 3: **backend**.

Implementá el backend completo del exchange: épicas `01` a `09` de `spec/`
(cuentas y autenticación, balances y ledger, motor de matching, gestión de órdenes,
settlement y fees, wallet HD y direcciones, depósitos on-chain, retiros on-chain, y la
API HTTP/WebSocket).

Indicaciones:

- La spec no fija lenguaje ni framework de servidor: elegí el stack que consideres más
  adecuado y justificá brevemente la elección en el README del repo.
- La épica 09 define el contrato HTTP/WebSocket exacto (rutas, formatos, códigos de
  error, eventos). Ese contrato es el que consumirán los clientes de las etapas
  siguientes y contra el que se verificará el sistema: respetalo literalmente.
- La interacción con la red (chainId 11155111) se hace vía JSON-RPC contra el endpoint
  configurable definido por la spec; no asumas servicios de terceros no especificados.
- La etapa se considera completa cuando el backend compila/arranca, expone el
  health-check definido en la épica 09, y las funcionalidades de las épicas 01–09 están
  implementadas según sus criterios de aceptación.

Al terminar, dejá documentado en el README cómo instalar dependencias, configurar el
entorno (variables, RPC, base de datos si aplica) y levantar el servidor.
