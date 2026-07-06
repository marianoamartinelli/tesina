Etapa 2 de 3: **cliente web**.

Implementá el cliente web del exchange: épica `10` de `spec/` (React para web, según el
alcance fijado por la spec).

Indicaciones:

- El cliente consume exclusivamente el contrato HTTP/WebSocket de la épica 09,
  implementado por el backend de la etapa anterior. Si detectás una discrepancia entre
  lo que el backend expone y lo que la épica 09 especifica, prevalece la spec: corregí
  el backend.
- Las HU de la épica 10 definen pantallas, flujos, estados visuales y manejo de errores;
  sus criterios de aceptación son la definición de terminado.
- La etapa se considera completa cuando el cliente compila, arranca y permite operar
  los flujos especificados contra el backend corriendo.

Al terminar, documentá en el README cómo instalar, configurar (URL del backend) y
levantar el cliente web.
