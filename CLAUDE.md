# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Qué es este repositorio

**Es un repositorio de especificación, no de código.** Contiene la **especificación
funcional completa** (en español) de un exchange de criptomonedas centralizado y
simplificado, más la documentación de la propuesta de tesina. No hay build, ni tests, ni
lint, ni dependencias: el "producto" es el corpus de Markdown en `spec/`.

Árboles de contenido (mapa completo en `README.md`, hitos en `ROADMAP.md`):

- `spec/` — la especificación: `00-fundaciones/` (convenciones transversales) + épicas
  `01`..`11`, cada una con un `README.md` y sus Historias de Usuario (`HU-*.md`).
- `propuesta/` — documentos `.docx` de la propuesta de tesina (nota al decano, formulario).
  Son binarios; no se editan desde acá.
- `decisiones/` — ADRs numerados e inmutables; `journal/` — bitácora fechada por sesión.
- `corpus/` — BIPs/EIPs para RAG; `pipeline/` — harness de agentes; `evaluacion/` —
  harness de evaluación y protocolo; `runs/` — manifest/intervenciones/métricas por
  corrida; `analisis/` — dataset y resultados; `tesis/` — documento final en LaTeX.

## Protocolo de registro (ADR-003 — obligatorio)

Todo queda versionado para meta-análisis posterior:

- **Al cerrar cada sesión de trabajo significativa** (incluidas sesiones con Claude),
  proponer/escribir una entrada en `journal/AAAA-MM-DD-tema.md` según
  `journal/README.md`: qué se hizo, decisiones, pendientes, observaciones.
- **Decisión estructural** (metodología, herramientas, protocolo, alcance) ⇒ ADR nuevo
  en `decisiones/` (numeración secuencial; los ADR aceptados no se editan, se
  reemplazan) + actualizar el índice de `decisiones/README.md`.
- **Corridas del pipeline** ⇒ manifest y log de intervenciones según plantillas de
  `runs/plantillas/`, completando el manifest *antes* de iniciar la corrida.
- **Commits** con convención `area: descripción` (`spec:`, `journal:`, `adr:`, `runs:`,
  `tesis:`, `corpus:`, `pipeline:`, `evaluacion:`, `analisis:`, `repo:`).
- Las implementaciones generadas por las corridas viven en **repos separados**
  (ADR-001); nunca dentro de este repo.

## Regla non-slop (estilo obligatorio de todo lo que se escribe acá)

Vale para spec, journal, ADRs, READMEs, prompts, artifacts y la tesis. La vara: cada
oración aporta algo que el lector necesita; lo que no, se corta.

- **Ningún dato inventado.** Toda cifra, conteo o afirmación fáctica sale de una fuente
  primaria del repo — contar/medir antes de escribir. Lo no verificado se marca como tal
  o no se escribe. Un número plausible pero falso es peor que ningún número.
- **No sobre-informar.** Un dato entra si cambia lo que el lector hace o decide; la
  exhaustividad no es un valor en sí misma. Mejor una afirmación verificada que tres
  plausibles.
- **Sin relleno retórico.** Nada de "cabe destacar", "es importante mencionar",
  superlativos promocionales ni cierres que repiten lo ya dicho. Emojis, negritas y
  estructura (tablas, listas, encabezados) sólo cuando organizan contenido real, nunca
  como decoración.
- **Simple es mejor que complejo, pero complejo es mejor que complicado.** Elegir la
  representación más simple que no mienta. Cuando el dominio es genuinamente complejo
  (matching, settlement, paridad experimental), se lo representa con precisión en vez de
  esconderlo tras una simplificación falsa o una maraña de detalle accidental.

Slop preexistente en un documento vivo se corrige al tocarlo. Los documentos congelados
(ADRs aceptados, spec taggeada, protocolo pre-registrado) no se reescriben por estilo.

## Mantenimiento del README

El `README.md` de la raíz incluye una sección "Estado del proyecto" y una tabla de los
*artifacts* de claude.ai publicados (documentación visual del roadmap, los hitos y la
infraestructura técnica). Mantenerla al día:

- Al publicar un artifact nuevo o redeployar uno existente, agregar/actualizar su fila
  en la tabla del README (favicon, nombre, link, descripción de una línea) y reflejar
  el mismo cambio en la memoria de sesión `artifacts-publicados` para que sesiones
  futuras puedan redeployarlo sin perder la URL. Si un artifact se descontinúa, quitar
  su fila del README.
- Al cerrar un hito del `ROADMAP.md` (marcarlo `[x]`) o al congelar un nuevo tag de
  spec, revisar si "Estado del proyecto" sigue siendo preciso (hitos completos, hito
  próximo, contadores de AT-ids) y actualizarlo si no.
- Esta revisión es parte del cierre de sesión (junto con el journal), no un paso
  aparte: no hace falta un commit dedicado sólo para el README salvo que sea el único
  cambio pendiente.

## El doble rol de la spec (contexto crítico antes de tocar nada)

Esta spec es simultáneamente:

1. **El input de un experimento factorial 2×2** (modelo A/B × con/sin RAG): las 4 corridas
   reciben *exactamente la misma spec* y deben generar una implementación del exchange.
2. **El criterio de evaluación holdout**: los criterios de aceptación (escenarios Gherkin +
   reglas, identificados por **AT-id**) son la vara objetiva con la que se mide cada
   implementación generada.

Consecuencias que gobiernan cualquier edición:

- **Los AT-id son estables**: no se renombran, no se reutilizan, no se renumeran. Un test
  del holdout se referencia por su AT-id de por vida. Lo mismo para los `code` del catálogo
  de errores y los IDs `INV-*`.
- **Toda afirmación normativa debe ser precisa, no ambigua y testeable** — convertible en un
  test verdadero/falso sin juicio subjetivo. Cuando algo admite varias interpretaciones, la
  spec **fija una** y la declara convención (no deja el caso abierto).
- No confundir roles: si te piden *implementar* el exchange, la spec es input inmutable; si
  te piden *mejorar la spec*, respetá la estabilidad de identificadores de arriba.

## Regla de precedencia

Ante cualquier conflicto entre una HU de épica y un documento de `00-fundaciones/`,
**prevalece `00-fundaciones/`**. Esa carpeta define las convenciones que el resto da por
supuestas; leerla primero, en este orden: `glosario.md` → `activos-y-par-de-trading.md` →
`convenciones-monetarias.md` → `modelo-de-errores.md` → `invariantes-globales.md`.

## Convenciones de dominio fijadas (no negociables por la implementación)

Estas decisiones están cerradas en `00-fundaciones/` y `spec/README.md`; cualquier HU nueva
o editada debe adherir:

- **Alcance cerrado**: par único `ETH (base) / USDC-mock (quote)`; red única **Sepolia**
  (`chainId 11155111`); sólo órdenes `LIMIT` y `MARKET` con prioridad **precio-tiempo**.
  Fuera de alcance: KYC/AML, otros pares/redes, tipos de orden avanzados, HA/baja latencia,
  hardening de producción. El frontend está fijado (React web + React Native/Expo); el
  backend es **agnóstico** (la spec no fija lenguaje ni framework de servidor).
- **Dinero en enteros de unidad mínima** (wei = 10¹⁸/ETH; USDC-min = 10⁶/USDC; precio
  `price_min` = USDC-min por 1 ETH). **Prohibidos los floats binarios** para montos, precios,
  fees o balances. Productos intermedios (`q_wei × price_min` ~ 10³⁰) exceden 64 bits ⇒ usar
  big integers.
- **Redondeo determinista**: conversiones base⇄quote con `floor` (mismo `quote_min` para
  ambas patas del fill); fees con `ceil` (a favor del exchange). `fee_bps`: maker 10, taker
  20, denominador 10000.
- **Serialización de montos**: en la API viajan como **string de entero** en unidad mínima,
  patrón `^(0|[1-9][0-9]*)$`. Los **conteos/índices no monetarios** (`confirmations`,
  `blockNumber`, `logIndex`, `sequence`, etc.) van como **enteros JSON**. No mezclar.
- **Errores**: estructura uniforme `{ error: { code, message, details } }`; los `code`
  salen del catálogo de `modelo-de-errores.md` (espacio de nombres plano y global) y son
  estables. La precedencia de validación debe ser determinista.
- **Invariantes globales** `INV-1..INV-8` (conservación de fondos, no-negatividad,
  disponible+bloqueado=total, atomicidad del settlement, idempotencia de depósitos,
  anti-replay EIP-155, integridad del orderbook, persistencia) deben cumplirse en toda
  corrida y forman parte de la evaluación.

## Formato y convenciones de los archivos de spec

- **Idioma**: español para la redacción; términos técnicos/de dominio en su forma original
  (maker/taker, orderbook, fill, settlement, HD wallet, BIP/EIP, nonce, gas). Mantener
  acentos y ortografía correcta. `glosario.md` es la referencia única de vocabulario.
- **IDs**: HU = `HU-<epica>-<seq>` (dos dígitos cada uno, p. ej. `HU-03-02`); test de
  aceptación = `AT-<epica>-<huSeq>-<NN>` (p. ej. `AT-03-02-01`).
- **Estructura de una HU** (ver cualquier `HU-*.md` como plantilla, p. ej.
  `spec/03-motor-de-matching/HU-03-03-*.md`): encabezado (Épica, actor, prioridad,
  dependencias) → Historia → Contexto y alcance → **Reglas de negocio** numeradas `RN-*` →
  **Criterios de aceptación** como escenarios Gherkin en español (`Dado/Cuando/Entonces`)
  cada uno con su `[AT-...]` → checklist de Definición de Done.
- **Gherkin + reglas**: el Gherkin describe flujos; las reglas `RN-*` fijan los detalles
  cuantitativos, fórmulas y bordes. Se prefiere redundancia controlada antes que ambigüedad;
  se cubren explícitamente casos felices, bordes y errores.
- Cada README de épica lista sus HU, sus dependencias hacia otras épicas y sus invariantes
  clave. Al agregar/modificar una HU, actualizar también la tabla del README de la épica y,
  si corresponde, `spec/README.md`.

## Trabajo con los `.docx` de `propuesta/`

Son binarios de Word. Para leer su contenido, extraer el texto (p. ej. `unzip -p archivo.docx word/document.xml`)
en lugar de intentar abrirlos con las herramientas de lectura de texto plano.
