# ADR-024 — Reapertura controlada de la spec y re-freeze como spec-v1.2: rate limiting determinista en `/auth/*`

- **Estado:** **Aceptado** (decidido por el tesista el 2026-09-06)
- **Fecha:** 2026-09-06
- **Contexto:** ventana H6, cierre de la corrida pre-piloto
  ([ADR-018](ADR-018-corrida-pre-piloto.md)). Sale de dos observaciones de la
  pre-piloto: los **2 `skip`** de la suite black-box en las dos celdas (AT-01-01-20 y
  AT-01-02-09, «rate limiting opcional por config») frente a la regla `skip = 0` de
  [ADR-011](ADR-011-particion-automatizable-white-box.md), y el ensayo de la rúbrica web,
  donde el evaluador tuvo que **elegir** umbral y ventana para poder evaluar AT-10-01-06
  (`runs/pre-piloto/hallazgos.md`, H-24).
- **Reemplaza a:** de [ADR-006](ADR-006-reapertura-controlada-spec-v1.1.md), la
  **Decisión D4** («en `/auth/*` rige la 01: opcional, y si existe usa `RATE_LIMITED`; los
  ATs correspondientes quedan condicionales») y el tag `spec-v1.1` como input de las
  corridas. ADR-006 no se edita; sus otras 16 decisiones y sus reglas de reapertura
  siguen vigentes y se aplican acá.

## Contexto

`spec-v1.1` dejaba el rate limiting de los endpoints públicos `/auth/*` «opcional por
config», con umbral `N` y ventana `W` «determinables desde la configuración del entorno de
test». Ningún documento fijaba esos valores: ni la spec, ni el contrato de arranque de
`suite-at/entorno/README.md`, ni la rúbrica web. En la práctica:

- la suite sondeaba 61 intentos y **se saltaba** si no veía un 429 — dos `skip` por
  celda, legítimos según la spec e incompatibles con `skip = 0` (ADR-011);
- la rúbrica web (AT-10-01-06) admitía `NO_EVALUABLE` (a) si el backend no limitaba, y si
  lo exponía como config el evaluador elegía los valores (5 / 60 s en el ensayo);
- una implementación podía cumplir la spec sin implementarlo, otra implementarlo con
  cualquier valor, y las cuatro celdas se evaluaban con criterios distintos.

El tesista decidió que la spec fije el rate limiting de forma exacta y determinista
(«si tenemos que cambiar suite o spec, avancemos; simpleza sobre burocracia»).

## Decisión

**La spec se reabre bajo las reglas de ADR-006 y se re-congela como `spec-v1.2`.** Cambios,
todos con AT-ids y catálogo de errores intactos:

| # | Cambio |
|---|---|
| **D1** | **HU-01-02 RN-9:** rate limiting de login **obligatorio y determinista**: **60 intentos fallidos por origen** (IP del cliente) en una **ventana deslizante de 60 s**; la solicitud siguiente desde ese origen —cualquier email, cualquier payload— responde `RATE_LIMITED` (429) con `details.retryAfterSeconds` (entero ≥ 0, segundos hasta que el fallo más antiguo salga de la ventana) y header `Retry-After`. Los intentos exitosos no cuentan ni reinician la ventana. Sigue siendo paso 0 de la precedencia (RN-8) y uniforme entre emails existentes e inexistentes. |
| **D2** | **HU-01-01 RN-10:** anti-flood de registro **obligatorio y determinista**: **60 solicitudes por origen** en una ventana deslizante de 60 s, contando toda solicitud a `POST /auth/register`; la siguiente responde `RATE_LIMITED` con `retryAfterSeconds` y `Retry-After`. Paso 0 de la precedencia (RN-9). |
| **D3** | **Escenarios AT-01-02-09 y AT-01-01-20** reescritos en el lugar con los valores fijos; pierden la cláusula «condicional a config». **HU-09-02 RN-12** referencia la política por origen de la épica 01 en vez de llamarla opcional. |
| **D4** | **Por qué 60 y por origen:** es el número que la spec ya usa (RN-12) y el que la suite asumía; contar sólo **fallos** en login evita que el tráfico legítimo de la propia suite (un login por test, desde un único origen) dispare el límite, y contar por origen —no por email— es lo que hace verificable la uniformidad (un email inexistente recibe el mismo 429). |
| **D5** | **Suite:** los tests de AT-01-02-09 y AT-01-01-20 dejan de saltarse: exigen el 429 (y el header `Retry-After`) o fallan. `N_RATE_LIMIT = 60` no cambia. `catalogo-at.csv` regenerado (mismos 693 AT-ids; cambian dos títulos de escenario). |
| **D6** | **Contrato de arranque del entorno** (`suite-at/entorno/README.md`): los valores de `/auth/*` pasan a ser constantes de la spec; si una implementación los expone como config se le pasan esos, y si no lo implementa los ATs fallan. |
| **D7** | **Rúbrica web, fila AT-10-01-06:** desaparece la salida «si el backend no implementa rate limit → NO_EVALUABLE (a)»; el modo de provocarlo queda escrito. Los otros dos cambios de la rúbrica v1.1 son de [ADR-025](ADR-025-protocolo-v1-6-cierre-de-la-ventana-h6.md). |

Valores fijados en el mismo commit del tag; auditoría mecánica (`audit-spec.py`) en verde
y `TOTAL_ESPERADO = 693` sin cambios.

## Consecuencias

- **`spec-v1.2` reemplaza a `spec-v1.1`** como el commit único que reciben `piloto-01` y
  las 4 corridas oficiales. Lo pinnean `crear-repo-satelite.sh`, la plantilla de manifest
  y el manifest de `piloto-01`. `spec-v1.1` queda como tag histórico, igual que v1.0.
- Los documentos congelados que nombran `spec-v1.1` como insumo —`agente-evaluador/briefing.md`
  §2, `rubricas/rol-revisor.md` precondición 4— **no se editan**: se leen como `spec-v1.2`,
  con el mismo criterio con que ADR-012 hizo leer `spec-v1.1` donde ADR-004 decía v1.0.
- **Amenaza a la validez, declarada:** a diferencia de ADR-006, esta reapertura ocurre
  **después** de que dos agentes vieron `spec-v1.1` — los de la pre-piloto, descartables
  por diseño (ADR-018) y que no entran en el dataset—. El cambio es una fijación de
  parámetros, no un criterio nuevo, y ocurre antes de cualquier corrida oficial. Va a
  `analisis/amenazas-validez.md`.
- La regla `skip = 0` de ADR-011 se conserva sin excepciones: ya no queda ningún AT
  condicional a configuración en la suite.
- Las implementaciones de la pre-piloto (contra `spec-v1.1`) no se re-evalúan.
