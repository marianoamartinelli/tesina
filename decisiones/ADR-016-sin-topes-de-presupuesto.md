# ADR-016 — No hay topes de presupuesto: la corrida termina cuando el pipeline termina

- **Estado:** **Aceptado** (ratificado por el tesista el 2026-08-23)
- **Fecha:** 2026-08-23
- **Contexto:** ventana H6, corrida piloto sin ejecutar.
- **Reemplaza a:** [ADR-012](ADR-012-protocolo-experimental-v1-1.md), que congeló
  `evaluacion/protocolo.md` **v1.1**. Este ADR congela la **v1.2**. Sólo cambia §6 y la
  rama de §5.7 que dependía de ella; el resto de la v1.1 se conserva verbatim. ADR-012 no
  se edita.
- **Cierra:** el ítem 7 de la checklist H6 (`PENDIENTE-PILOTO` de los presupuestos
  definitivos).

## Contexto

§6 de la v1.1 fijaba `costo_max_usd = 200` y `tiempo_max_horas = 24` como provisionales,
con la regla «al agotarse un tope, la corrida se cierra en el estado en que esté», y
dejaba los definitivos pendientes del consumo que midiera la piloto. La v1.1 ya había
declarado que bajo suscripción `costo_max_usd` **no** es vinculante y que el tope real
son los rate limits, que son asimétricos entre proveedores y no están bajo control del
experimento. El presupuesto de turnos ya se había eliminado (ADR-009 §Consecuencias).

O sea: de los tres topes de la tabla, uno ya no aplicaba, otro nunca tuvo valor y el
tercero era un número sin fundamento empírico.

## Decisión

### 1. No hay topes de presupuesto. La corrida termina cuando termina el pipeline

Se elimina la tabla de §6 completa —`costo_max_usd`, `tiempo_max_horas`, `tokens_max`— y
la regla de cierre por agotamiento. Una corrida se cierra cuando las tres etapas
completan su secuencia, o por los criterios de progreso de §5.7, que no son
presupuestarios.

### 2. Costo, tiempo y tokens se siguen midiendo, con la misma granularidad

Nada se deja de registrar: costo (nativo en A vía `total_cost_usd`, estimado localmente
desde tokens en B), tiempo de reloj por invocación y por etapa, tokens por invocación,
turnos. Dejan de ser **topes** y quedan como **variables dependientes** — que es lo que
el experimento compara entre celdas. Un tope de 200 USD, de hecho, habría censurado
justamente la variable que se quiere medir: si una celda gasta el doble que otra, ese es
el resultado, no un motivo de corte.

### 3. `presupuesto_proporcional` deja de ser presupuesto

El reparto backend 60 % / web 25 % / mobile 15 % de `pipeline/comun/etapas.yaml` deja de
gatear el abandono de etapa. Se conserva **como referencia descriptiva** para el análisis
—qué fracción del esfuerzo total se fue en cada etapa, comparable entre celdas—, no como
umbral operativo.

### 4. El abandono de etapa queda sólo por criterio de progreso

§5.7 pierde la rama «tras agotar el presupuesto proporcional» y conserva la de los 3
estancamientos acumulados, que mide falta de progreso y no consumo. El estancamiento
propio (3 intervenciones consecutivas con la misma causa raíz sobre el mismo defecto sin
progreso observable) no se toca.

## Consecuencias

- **La ventana de ≤2 semanas de §7 pasa a ser la única restricción temporal del
  experimento**, y sigue presionada por los rate limits, que no están bajo control. Si
  una corrida se extiende más allá de la ventana, es un dato a registrar y una amenaza a
  la validez —los modelos comerciales cambian—, no un motivo de corte a mitad de etapa.
- **La decisión suscripción contra API key para H7 queda abierta**, pero ya no bloquea:
  sin topes vinculantes, se toma con el consumo que mida la piloto y se registra en el
  journal. Es lo único que quedaba del ítem 7.
- **Riesgo asumido:** una celda puede consumir un múltiplo de lo previsto sin que nada la
  detenga. El tesista lo asume explícitamente; la alternativa —cortar— destruiría la
  comparabilidad de la celda cortada, que es peor para el experimento que el costo.
- El manifest deja de llevar campos de tope y conserva los de consumo medido.
- **Cerrar por agotamiento de presupuesto habría sido una amenaza a la validez que la
  v1.1 no declaraba:** las celdas cortadas y las completas no son comparables en ninguna
  métrica de conformidad. Va a `analisis/amenazas-validez.md` como riesgo **eliminado**
  por esta decisión, para dejar registro de por qué la v1.1 lo tenía.

## Alternativas consideradas

- **Pinnear los definitivos con lo que mida la piloto** (lo que la v1.1 preveía).
  Rechazada: la piloto es **una** corrida con configuración descartable; derivar de ahí
  un tope para las 4 oficiales sería un número con apariencia empírica y n=1.
- **Conservar sólo el tope de tiempo.** Rechazada por el mismo motivo del punto 2: el
  tiempo por celda es una de las variables que se comparan.
