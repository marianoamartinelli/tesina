Etapa 2 de 3: **cliente web**.

Implementá el cliente web del exchange **acotado al alcance de esta corrida** (React para
web, según el alcance fijado por la spec).

## Alcance de esta corrida

- **Épica `10` (cliente web), sólo `HU-10-01`:** pantalla de login, con sus criterios de
  aceptación completos (casos felices, bordes y errores).

Las demás HU de la épica 10 —vista de trading, formulario de orden, órdenes abiertas e
historial, balances, depósitos y retiros— quedan **fuera de esta corrida**: su backend no
está implementado. No agregues pantallas ni rutas fuera del alcance.

## Indicaciones

- El cliente consume exclusivamente el contrato HTTP/WebSocket de la épica 09,
  implementado por el backend de la etapa anterior. Si detectás una discrepancia entre
  lo que el backend expone y lo que la épica 09 especifica, prevalece la spec: corregí
  el backend.
- Los criterios de aceptación de `HU-10-01` son la definición de terminado.
- La etapa se considera completa cuando el cliente compila, arranca y permite loguearse
  contra el backend corriendo.

Al terminar, documentá en el README cómo instalar, configurar (URL del backend) y
levantar el cliente web.
