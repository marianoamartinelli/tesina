Etapa 3 de 3: **cliente mobile**.

Implementá el cliente mobile del exchange: épica `11` de `spec/` (React Native con
Expo, según el alcance fijado por la spec).

Indicaciones:

- El cliente consume exclusivamente el contrato HTTP/WebSocket de la épica 09. Si
  detectás una discrepancia entre backend y spec, prevalece la spec: corregí el backend.
- Las HU de la épica 11 definen pantallas, navegación, flujos (incluido el QR de
  depósito) y manejo de errores; sus criterios de aceptación son la definición de
  terminado.
- La etapa se considera completa cuando la app compila y corre (Expo), y permite operar
  los flujos especificados contra el backend corriendo.

Al terminar, documentá en el README cómo instalar, configurar (URL del backend) y
correr la app.
