# 2026-08-17 — Cierre de la deuda de escritorio de H6 y ratificación de ADR-011/012/013

- **Hito:** H6 (ventana de la piloto), todavía sin iniciar. Ningún CLI de agente se
  ejecutó.
- **Contexto:** sesión con Claude Code que arranca preguntando qué falta para poder
  correr la piloto y termina cerrando 11 de los 24 ítems de la checklist H6. Continúa la
  sesión del 2026-08-16 (ADR-009 y ADR-010) sobre la misma rama
  `adr-009-harnesses-cli-2026-08-16`.

## Qué se hizo

**Diagnóstico inicial.** El bloqueante era el ítem 17: el pipeline seguía siendo el de
ADR-005 (`correr.py` sobre los SDK), sin orquestadores, sin servidor MCP stdio y sin
prompts de rol. Un detalle que la auditoría hizo visible: `verificar_paridad.py` salía
exit 0 pero validaba los pares de ADR-005 (`claude-opus-4-8` / `gpt-5.5`), o sea que el
verde era contra invariantes obsoletos.

**Corrida de workflow multi-agente.** A pedido del tesista se orquestaron 11 agentes en
5 fases, particionados por propiedad de archivos, con alcance "todo lo resoluble sin
correr la piloto". Restricciones dadas a todos: prohibido tocar `spec/` y los ADRs
aceptados, prohibido invocar `claude -p` o `codex exec` reales (eso *es* la piloto),
ADRs nuevos nacen `Propuesto`, sin commits, y placeholders `PENDIENTE-ARRANQUE:` en vez
de valores de entorno inventados. Produjo 38 archivos modificados y 13 nuevos
(+2188/−941 líneas), 0 errores de agente.

Qué cerró, por ítem de la checklist:

- **17** — pipeline reescrito: `harness_a/orquestar.py` y `harness_b/orquestar.py` sobre
  `comun/`, servidor MCP stdio único para el RAG, prompts de rol
  (`implementador`/`revisor`), `verificar_paridad.py` reescrito (77 chequeos, contra 39
  antes) y las 6 configs re-pinneadas a `claude-opus-5` / `gpt-5.6-sol` con
  `effort: xhigh`.
- **18** — `.pipeline/` excluido del cómputo de métricas estáticas, verificado con cloc
  2.10, lizard 1.23.0 y jscpd 5.0.11 antes de ver implementación alguna.
- **4** — partición final **465 automatizados / 56 white-box** sobre 521 ATs backend: los
  10 migrables pasaron a tests black-box condicionales, los 3 parciales quedaron
  white-box con su razón real. La suite pasa a 456 funciones de test.
- **3** — criterio `{200, 202}` del reenvío idempotente ratificado en el test: 0
  TODO-REVISAR en la suite.
- **5** — mnemonic: no se fija convención de entorno, se ratifica el fallback.
- **12** — rúbrica del rol revisor (`rubricas/rol-revisor.md` v1.0) construida y
  pre-registrada.
- **9** — protocolo v1.1 más ADR-012, que reemplaza a ADR-004 sin editarlo.
- **20** — precio de `gpt-5.6-sol` verificado contra la documentación de OpenAI.
- **21** — evaluador white-box re-pinneado a `claude-opus-5`, runtime a `claude -p`.

**Simplificación de los ADRs.** Los tres nacieron largos (147/168/95 líneas) y el tesista
pidió recortarlos: reproducían el razonamiento completo que ya vive en el instrumento que
modifican. Quedaron en 95/100/77, con el detalle en su lugar (motivos AT por AT en
`no-automatizables.yaml`, evidencia de las herramientas en el README de métricas,
procedimiento del mnemonic en la rúbrica v1.2, best-effort en el docstring del test).

**Ratificación.** El tesista aceptó los tres el 2026-08-17. Se propagó a los 8 lugares que
declaraban su estado: los propios ADRs, el índice (ADR-004 pasa a *Reemplazado por
ADR-012*), el encabezado del protocolo, la checklist, el README de la raíz.

**Residuos del ítem 17.** De los tres declarados, dos ya venían resueltos por los agentes
(`mcp==1.28.1` pinneado; cabeceras de los `correr.py` declarando que no corren). El
tercero se implementó en esta sesión: `comun.nucleo.snapshot_paso` copia el repo satélite
al cerrar cada invocación de rol.

## Decisiones

- **ADR-011, ADR-012 y ADR-013 aceptados** (011 y 012 en conjunto, porque la v1.1 del
  protocolo cita la partición 465/56).
- **Los `correr.py` del pipeline SDK no se retiran.** Era la recomendación inicial de la
  sesión, revertida al verificar que ADR-009 §Consecuencias —Aceptado, y por lo tanto
  vinculante— prohíbe borrarlos hasta que la piloto valide el reemplazo. Su estado ya
  está documentado en tres capas (cabecera de cada archivo, `requirements.txt` y el
  README del pipeline), que era el problema real: que alguien los creyera funcionales.
- **Snapshot por copia, no por commit ni re-pre-registro.** La precondición 2 de
  `rol-revisor.md` admite «commit, tag o copia que deja el orquestador». Se eligió la
  copia para no escribir en el historial del repo generado, que es dato del experimento,
  y para no tocar un instrumento ya pre-registrado. Vive en el núcleo, así que es
  idéntica en las 4 celdas por construcción; cuelga del stem del log —que lleva
  timestamp— para que una re-invocación de la misma etapa no pise los snapshots del
  intento anterior; y un fallo de la copia se registra sin cortar la etapa.

## Pendientes y próximos pasos

Para arrancar piloto-01, todo manual: Docker arriba (`compose up -d --wait`,
`desplegar-usdc.py`, `fondear.py`), verificar la sesión de las dos suscripciones, y
completar y commitear los 9 campos `PENDIENTE-ARRANQUE:` del manifest, incluido el digest
efectivo de anvil (ítem 13).

Abierto y sin depender de la piloto: las 2 entradas que faltan en
`analisis/amenazas-validez.md` (el pareo por precio en el tramo largo y la asimetría de
evaluabilidad de AT-06-03-07), el sorteo del orden de las 4 celdas (ítem 15), y qué hacer
con `AGENTS.md`, que apareció sin trackear y no se versionó.

Los 11 ítems restantes necesitan la corrida: 1, 2, 6, 7, 11, 13, 16, 19, 22, 23 y 24.

## Observaciones para el meta-análisis

- **Un verde puede ser un falso verde.** `verificar_paridad.py` pasaba sus 39 chequeos
  contra los invariantes viejos. El costo de un verificador que sobrevive a su objeto de
  verificación es que da confianza en vez de quitarla; conviene que el propio verificador
  declare cuántos chequeos corre y contra qué ADR.
- **El pareo por precio se rompió sin que nadie lo tocara.** `gpt-5.6-sol` factura el
  request completo al tramo largo por encima de 272 000 tokens de input (2.00× entrada,
  1.80× salida contra `claude-opus-5`), y el turno de 294 318 tokens que ADR-010 midió ya
  caía ahí. Del lado A no existe tramo por longitud: es una categoría de asimetría que no
  existía cuando ADR-005 escribió el criterio de pareo.
- **Discrepancia de ventana sin resolver:** el catálogo del CLI reporta 272 000 para
  `gpt-5.6-sol` y la documentación del modelo dice 1 050 000. Que el número del CLI
  coincida exactamente con el umbral de facturación sugiere que pinnea el límite del
  tramo barato y no la capacidad. Toca la asimetría que ADR-009 D3 declaró.
- **Los agentes del workflow declararon sus propios límites sin que se les pidiera**:
  qué no verificaron, qué inferencia era suya y no del ADR que citaban, y qué decisiones
  no les correspondía tomar. La regla non-slop de `CLAUDE.md` estaba en el prompt de
  todos; la hipótesis es que una regla explícita contra el dato inventado produce más
  autodeclaración de incertidumbre que una instrucción genérica de ser cuidadoso.
- **Sesgo de recomendación del asistente:** la sesión recomendó retirar los `correr.py`
  y sólo al ir a ejecutarlo verificó que un ADR aceptado lo prohibía. La recomendación se
  formuló antes de consultar la restricción vigente — vale como caso de la misma clase de
  error que el experimento va a medir en las corridas.
