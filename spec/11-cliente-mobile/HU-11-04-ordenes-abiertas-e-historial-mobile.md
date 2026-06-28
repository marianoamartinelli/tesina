# HU-11-04 — Órdenes abiertas e historial en mobile

- **Epica:** 11 — Cliente Mobile (React Native / Expo)
- **Actor / rol:** Trader autenticado
- **Prioridad:** Alta
- **Dependencias:** HU-10-04 (paridad web: órdenes e historial), épica 09 (endpoints de
  órdenes, cancelación y eventos WebSocket), épica 04 (gestión de órdenes), HU-11-01 (sesión)
- **Estandares de dominio aplicables:** N/A (no on-chain)

## Historia
Como trader autenticado, quiero ver mis **órdenes abiertas** (y poder **cancelarlas**) y mi
**historial** de órdenes en mobile, para gestionar mi operatoria desde el celular.

## Contexto y alcance
Cubre el listado de **órdenes abiertas** (`OPEN`, `PARTIALLY_FILLED`) con acción de
**cancelar**, y el **historial** (`FILLED`, `CANCELLED`, `REJECTED`) con **paginación**. Los
datos provienen de la API de la épica 09 (REST para listados/cancelación + WebSocket para
actualizaciones en vivo de órdenes propias). El contrato es **el mismo que el web**
(HU-10-04).

Diferencias mobile: lista scrolleable, acción de cancelar (botón/swipe) con **confirmación**,
prevención de doble envío, **pull-to-refresh**, **paginación infinita** ("cargar más") y
**resync por ciclo de vida**. La cancelación y los estados los decide el backend; la UI sólo
refleja el estado.

## Reglas de negocio e invariantes
1. **RN-1 (clasificación):** "abiertas" = `OPEN` y `PARTIALLY_FILLED`; "historial" =
   `FILLED`, `CANCELLED`, `REJECTED`. La fuente es la API (épica 09); el cliente no infiere
   estados por su cuenta.
2. **RN-2 (datos por orden):** cada orden muestra `id`, `side`, `type`, `price` (LIMIT),
   `quantity`, ejecutado/remanente, estado y timestamps. Los montos llegan como string
   entero de unidad mínima y se muestran formateados **sin floats** (ETH = /10¹⁸, USDC y
   precio = /10⁶).
3. **RN-3 (cancelación y errores):** la cancelación se envía contra una orden **propia**
   (épica 09). Sólo `OPEN`/`PARTIALLY_FILLED` son cancelables; cancelar `FILLED`/`CANCELLED`/
   `REJECTED` ⇒ `ORDER_NOT_CANCELLABLE` (409) con `details {orderId, status}`. Orden
   inexistente **o de otra cuenta** ⇒ `ORDER_NOT_FOUND` (404) con `details {orderId}`: por
   el aislamiento por cuenta de la épica 09 (RG-API-6), el acceso a una orden ajena devuelve
   **siempre 404** (no `UNAUTHORIZED` 403) para **no filtrar la existencia** de recursos de
   otras cuentas. La UI usa el `code` devuelto.
4. **RN-4 (efecto de cancelar):** una cancelación exitosa lleva la orden a `CANCELLED`, la
   mueve de "abiertas" a "historial" y libera en el backend el bloqueado del remanente (la
   liberación la refleja HU-11-05). La UI se actualiza por la respuesta y/o por evento WS.
5. **RN-5 (live updates):** vía WebSocket (épica 09, canal `orders`) las órdenes propias
   actualizan su estado (fill parcial, fill total, cancelación) sin recarga manual. Si llega
   un evento `order` para un `orderId` **no presente** en el listado local (porque proviene
   de otra sesión/dispositivo o de una página del historial aún no descargada), el cliente
   dispara un **refetch** del listado de órdenes abiertas (`GET /orders?status=OPEN`); para
   eventos de fill total/cancelación de órdenes no visibles, el historial se actualiza en el
   próximo pull-to-refresh o resync por foreground (RN-9). El cliente nunca **ignora**
   silenciosamente un evento dejando el listado desactualizado.
6. **RN-6 (paginación):** el historial se pagina según la épica 09 (cursor u offset); se
   ofrece scroll infinito o "cargar más", en orden cronológico **descendente** por defecto.
7. **RN-7 (idempotencia de cancelación):** cancelar dos veces la misma orden ⇒ la segunda
   responde `ORDER_NOT_CANCELLABLE`; la UI lo trata como "ya cancelada" (estado final
   consistente), no como fallo duro.
8. **RN-8 (confirmación y anti doble-envío):** se confirma antes de cancelar; el control de
   cancelar se deshabilita mientras el request está en vuelo (evita doble envío).
9. **RN-9 (ciclo de vida):** al volver a foreground, el cliente re-sincroniza el listado
   (refetch + re-suscripción al WebSocket).
10. **RN-10 (sesión):** ante `UNAUTHENTICATED` (401), limpia la sesión y redirige al login
    (consistente con HU-11-01, flujo singleton RG-8).
11. **RN-11 (fallo de red):** si una petición de listado o de cancelación no obtiene
    respuesta del backend (fallo de red/timeout), la UI muestra un error de **conectividad**
    (distinto de los errores de negocio), el estado local de la orden **no** cambia y se
    permite reintentar.

## Criterios de aceptación (DoD)

### Escenario 1: Listado de órdenes abiertas [AT-11-04-01]
- Dado un trader autenticado con órdenes `OPEN` y `PARTIALLY_FILLED`
- Cuando abre la pantalla de órdenes
- Entonces ve sus órdenes abiertas con id, side, type, price, cantidad, ejecutado/remanente
  y estado
- Y los montos se muestran formateados sin floats

### Escenario 2: Cancelar una orden abierta [AT-11-04-02]
- Dado una orden propia en estado `OPEN`
- Cuando el trader la cancela y confirma
- Entonces el backend la lleva a `CANCELLED`
- Y la orden desaparece de "abiertas" y aparece en "historial"

### Escenario 3 (live): Fill parcial actualiza el remanente [AT-11-04-03]
- Dado una orden `OPEN` visible en el listado
- Cuando el backend emite un evento de fill parcial por WebSocket
- Entonces la UI actualiza el estado a `PARTIALLY_FILLED` y el remanente, en vivo, sin
  recargar

### Escenario 4 (live): Fill total mueve a historial [AT-11-04-04]
- Dado una orden `PARTIALLY_FILLED` visible
- Cuando se completa (evento de fill total por WebSocket)
- Entonces pasa a `FILLED` y se mueve de "abiertas" a "historial"

### Escenario 5: Historial con paginación [AT-11-04-05]
- Dado un historial con más resultados que una página
- Cuando el usuario hace scroll al final o toca "cargar más"
- Entonces se solicita la siguiente página (cursor/offset de la épica 09) y se anexa al
  listado en orden cronológico descendente

### Escenario 6 (error): Cancelar una orden ya ejecutada [AT-11-04-06]
- Dado una orden en estado `FILLED`
- Cuando el trader intenta cancelarla
- Entonces el backend responde `ORDER_NOT_CANCELLABLE` (409) con `details {orderId, status}`
- Y la UI muestra que ya no es cancelable

### Escenario 7 (error): Cancelar orden inexistente o ajena [AT-11-04-07]
- Dado un `orderId` que no existe **o** pertenece a otra cuenta
- Cuando se intenta cancelar
- Entonces el backend responde **`ORDER_NOT_FOUND` (404)** con `details {orderId}` en ambos
  casos (aislamiento por cuenta, RG-API-6: no se filtra la existencia con un 403)
- Y la UI lo informa con el `code` devuelto

### Escenario 8 (idempotencia): Doble cancelación de la misma orden [AT-11-04-08]
- Dado una orden ya cancelada
- Cuando se vuelve a enviar la cancelación
- Entonces el backend responde `ORDER_NOT_CANCELLABLE`
- Y la UI mantiene el estado final `CANCELLED` (no lo trata como fallo duro)

### Escenario 9 (concurrencia): Doble tap en cancelar [AT-11-04-09]
- Dado una orden cancelable
- Cuando el usuario toca "cancelar" dos veces rápidamente
- Entonces se envía un único request (control deshabilitado durante el request en vuelo)

### Escenario 10 (ciclo de vida): Resync al volver a foreground [AT-11-04-10]
- Dado la pantalla de órdenes abierta y la app que pasó a background, con un **mock del
  WebSocket** que simula el cierre de conexión al pasar a background (RG-11)
- Cuando vuelve a foreground
- Entonces el cliente re-sincroniza (refetch + re-suscripción WS) y muestra el estado actual

### Escenario 11: Pull-to-refresh [AT-11-04-11]
- Dado la pantalla de órdenes visible
- Cuando el usuario hace pull-to-refresh
- Entonces se recargan las órdenes abiertas y la primera página del historial

### Escenario 12 (error): Token expirado [AT-11-04-12]
- Dado un trader cuyo token expiró
- Cuando una petición de listado o cancelación recibe `UNAUTHENTICATED` (401)
- Entonces la app limpia la sesión y redirige al login

### Escenario 13 (error): Fallo de red al cancelar [AT-11-04-13]
- Dado una orden cancelable y el backend caído o sin conectividad
- Cuando la petición de cancelación no obtiene respuesta (fallo de red)
- Entonces la UI muestra un error de conectividad (distinto de los errores de negocio)
- Y la orden permanece en su estado local (no se marca como cancelada)
- Y se permite reintentar la cancelación

### Escenario 14 (live, borde): Evento WS de una orden no listada [AT-11-04-14]
- Dado un evento `order` (fill parcial o cancelación) para un `orderId` **no presente** en el
  listado local (otra sesión/dispositivo o página no descargada)
- Cuando el cliente recibe el evento
- Entonces no lo ignora: dispara un refetch del listado de órdenes abiertas (RN-5)
- Y para órdenes terminales no visibles, el historial se actualiza en el próximo
  pull-to-refresh o resync por foreground

## Definicion de Done (checklist transversal)
- [ ] Todos los escenarios de aceptación (AT-*) pasan
- [ ] Reglas de negocio RN-1..RN-11 verificadas
- [ ] Manejo de errores conforme a 00-fundaciones/modelo-de-errores.md
- [ ] Precision/redondeo conforme a 00-fundaciones/convenciones-monetarias.md
- [ ] Invariantes globales: el cliente **refleja** los estados de órdenes y la liberación de
      fondos que el backend garantiza (INV-7); INV-1, INV-4 e INV-8 (y demás) son
      responsabilidad del backend — el cliente no los garantiza
      (00-fundaciones/invariantes-globales.md)
- [ ] (si aplica) Adherencia verificada al estandar on-chain citado
