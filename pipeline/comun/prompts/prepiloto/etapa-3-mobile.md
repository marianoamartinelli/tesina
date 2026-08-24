Etapa 3 de 3: **cliente mobile**.

Implementá el cliente mobile del exchange **acotado al alcance de esta corrida** (React
Native con Expo, según el alcance fijado por la spec).

## Alcance de esta corrida

- **Épica `11` (cliente mobile), sólo:**
  - `HU-11-01` login mobile, con sus criterios de aceptación completos;
  - de `HU-11-06`, **únicamente la pantalla de depósito**: mostrar la dirección de
    depósito del usuario con su QR (Escenarios 1 y 26, `AT-11-06-01` y `AT-11-06-26`).

Todo lo demás de la épica 11 queda **fuera de esta corrida**, incluidos los retiros y el
seguimiento de depósitos de `HU-11-06`: su backend (épicas 07 y 08) no está
implementado. No agregues pantallas ni flujos fuera del alcance.

## Indicaciones

- El cliente consume exclusivamente el contrato HTTP/WebSocket de la épica 09. Si
  detectás una discrepancia entre backend y spec, prevalece la spec: corregí el backend.
- La etapa se considera completa cuando la app compila y corre (Expo), y permite
  loguearse y ver la dirección de depósito con su QR contra el backend corriendo.

Al terminar, documentá en el README cómo instalar, configurar (URL del backend) y
correr la app.
