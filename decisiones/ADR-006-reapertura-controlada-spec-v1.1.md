# ADR-006 — Reapertura controlada de la spec y re-freeze como spec-v1.1

- **Estado:** aceptado (2026-07-05)
- **Contexto:** los ~15 defectos de spec descubiertos al construir la suite de
  aceptación (H5, ver journal 2026-07-05) más 2 menores conscientes de H1. Ninguna
  corrida (ni siquiera la piloto) se ejecutó aún.

## Decisión

Se corrige la spec **antes de la piloto** y se re-congela como tag `spec-v1.1`, que
reemplaza a `spec-v1.0` como el commit único que reciben las 5 corridas (piloto + 4
oficiales). La condición experimental protegida es "input idéntico entre celdas", no
un tag en particular; como ningún agente vio la spec todavía, la corrección preserva
la validez y **fortalece el holdout** (ATs hoy no-testeables pasan a serlo) y reduce
ruido de intervenciones D4 evitables. La referencia a `spec-v1.0` en
`evaluacion/protocolo.md` §2.1 queda superada por este ADR; el texto del protocolo se
actualizará formalmente en la revisión post-piloto que ADR-004 ya prevé.

### Reglas de la reapertura (no negociables)

1. **AT-ids intocables**: no se renombran, renumeran, agregan ni eliminan. El corpus
   sigue teniendo exactamente 693 ATs. Los ATs cuyo contenido contradiga una decisión
   de abajo se **reescriben en el lugar** (precedente: AT-06-03-07 en H1).
2. **Catálogo de errores intocable**: no se agregan ni renombran `code`s; toda
   validación nueva usa códigos existentes (p. ej. `VALIDATION_ERROR` con `details`).
3. **Alcance cerrado**: únicamente las decisiones D1–D17 de este ADR. Nada más.
4. La auditoría mecánica (`evaluacion/audit-spec.py`) debe pasar tras las ediciones.
5. La suite de H5 se actualiza en el mismo movimiento (sigue sin existir
   implementación alguna, así que no se introduce sesgo de evaluador).

## Decisiones (D1–D4 del tesista; D5–D17 por criterio de consistencia)

| # | Decisión |
|---|----------|
| **D1** | **Cancelación de retiros: se define la ruta.** `POST /withdrawals/{withdrawalId}/cancel` se agrega al mapa de endpoints de HU-09-01, con semántica exactamente la de HU-08-04 (sólo `PENDING`; errores con códigos existentes; 404 para recurso ajeno). |
| **D2** | **Retiros: el usuario paga el fee de red — la épica 08 prevalece íntegra.** Se bloquea `monto + fee_red_wei` y se reconcilia el sobrante según la 08. Se corrigen HU-02-02 RN-10 y README de la 02 §5.1 (y toda otra frase de la 02 que afirme lo contrario). |
| **D3** | **`clientOrderId` obligatorio en `POST /orders` — la épica 09 prevalece.** HU-04-01/HU-04-02 RN-1 pasan a obligatorio; ATs de la 04 que aserten opcionalidad se reescriben en el lugar (ausencia del campo ⇒ `VALIDATION_ERROR` con `details.field`). Verificar que las épicas 10/11 generen `clientOrderId` al crear órdenes; si no lo mencionan, agregar la aclaración mínima. |
| **D4** | **Rate limiting: HU-09-02 RN-12 (60/min por cuenta y endpoint) queda acotado explícitamente a endpoints autenticados.** En `/auth/*` rige la 01: opcional, y si existe usa `RATE_LIMITED`. Los ATs correspondientes quedan condicionales como están. |
| **D5** | **Logout**: `POST /auth/logout` se agrega al mapa de HU-09-01; comportamiento según HU-01-03. |
| **D6** | **Historial de movimientos**: se define `GET /movements` en HU-09-01, espejando HU-02-05 (paginación por cursor, filtros, conteos como enteros JSON, montos string-entero). HU-02-05 referencia la ruta. |
| **D7** | **Objeto orden REST — nombres canónicos de la 09.** La 04 adopta `filledWei` (antes `executedQty`) y demás nombres de la 09. Los campos que la 04 exige y la 09 no tenía se agregan al objeto orden de HU-09-01 RN-5 con estos nombres: `remainingWei`, `executedQuoteMin`, `avgPriceMin` (fórmulas de la 04; string-entero; `avgPriceMin = null` si `filledWei = 0`). |
| **D8** | **Presupuesto de MARKET por quote**: se oficializa en el body de `POST /orders` (HU-09-01 RN-4), mutuamente excluyente con `quantityWei`, según la 04. Nombre canónico fijado: **`quoteOrderQtyMin`** (string-entero en usdc-min, consistente con la convención de sufijos de la 09); la 04 adopta ese nombre donde hoy diga `quoteOrderQty`. |
| **D9** | **Filtros temporales de `GET /orders`**: `from`/`to` ISO-8601 UTC, mismo formato que RN-20 (trades). |
| **D10** | **Orden por defecto del historial: descendente** (más reciente primero) en órdenes y trades — la 09 prevalece; HU-04-06 RN-4 se corrige. |
| **D11** | **Validación estricta de enums**: valor fuera del enum en query params ⇒ 422 `VALIDATION_ERROR` — la 04 prevalece; AT-09-01-07 se reescribe en el lugar. |
| **D12** | **Campo `status` de cuentas: la 01 prevalece** (presente en las respuestas de registro/perfil); los ejemplos de la 09 se actualizan. |
| **D13** | **Heurística de token (HU-01-02, AT-01-02-10)**: se reescribe como propiedad satisfacible también por JWT (se elimina la cláusula de unicidad de prefijo); el token sigue siendo opaco para el cliente. |
| **D14** | **Heartbeat WS**: el `ping` JSON de aplicación de RN-14 (HU-09-03) es **obligatorio** (testeable); los frames de control RFC 6455 quedan permitidos como mecanismo adicional, nunca sustituto. |
| **D15** | **MARKET con presupuesto**: HU-04-02 (dueña del ciclo de vida) prevalece; HU-03-04 RN-9 se reescribe consistente con el modelo de `q'` precomputado (FILLED si `q'` se ejecuta completo; CANCELLED con `reason` si el libro no alcanza). AT-03-04-05 y AT-03-04-07 se ajustan en el lugar; el Dado de AT-03-04-07 pasa a respetar el mínimo notional que la propia spec fija. |
| **D16** | **Datos de ejemplo imposibles**: AT-08-04-02 ejemplifica el sobrante de gas con la pata ERC-20 (una transferencia ETH consume exactamente 21000); AT-05-01-10 se alinea al costo exacto del sweep (RE-1 de la 04). |
| **D17** | **AT-09-01-21** se alinea con HU-04-02 RN-4: la MARKET rechazada persiste como `REJECTED` en el historial; la cláusula "no se crea ninguna orden" pasa a "no queda orden abierta ni efecto en libro/balances". |

Fuera de alcance (deliberado, igual que en H1): nombres internos
`amountWei`/`amountUsdcMin` del registro interno de la 07 y nombres de campos de fee
del evento interno del motor (capas distintas, internamente consistentes).

## Consecuencias

- Correcciones aplicadas por agentes con decisiones cerradas (mismo esquema que H1),
  clusters sin solapamiento de archivos; auditoría mecánica re-corrida; tag
  `spec-v1.1` sobre el commit de las correcciones.
- La suite de H5 se actualiza: tolerancias eliminadas (asertan la decisión), los 14
  ATs de HU-02-05 y los 2 de cancelación de retiros ganan tests reales,
  `no-automatizables.yaml` se depura. Cobertura 521/521 re-verificada.
- Los manifests de corrida pinnean `spec-v1.1`. `spec-v1.0` queda como tag histórico.
