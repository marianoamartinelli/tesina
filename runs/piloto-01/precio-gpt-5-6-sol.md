# Precio por token de `gpt-5.6-sol` — verificación

Cierra el residuo abierto por [ADR-009](../../decisiones/ADR-009-harnesses-como-cli-y-orquestador-de-roles.md)
Decisión 3 y registrado como ítem 20 de la [checklist H6](checklist-h6.md): el precio
por token del flagship de la celda B no se había verificado contra fuente primaria. De
ese dato dependen dos cosas — la paridad de precio del pareo flagship-contra-flagship y
la estimación de `costo_estimado_usd` del harness B, que no tiene reporte de costo
nativo.

**Estado: verificado.** Fecha de consulta: **2026-08-16**.

## 1. El CLI no expone precios (confirmado, no inferido)

ADR-009 D3 afirmó que el catálogo del CLI expone ventana y niveles de effort pero no
precios. Se confirmó ejecutando:

```
codex debug models          # codex-cli 0.146.0
```

La salida es un JSON de 7 modelos (`gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`,
`gpt-5.5`, `gpt-5.4`, `gpt-5.4-mini`, `codex-auto-review`). Ninguna entrada tiene un
campo cuyo nombre contenga `price`, `cost`, `usd`, `billing` ni `rate`: la búsqueda de
esos términos sobre el JSON completo devuelve **0 coincidencias**. Los campos escalares
de `gpt-5.6-sol` son de capacidad y configuración (`context_window`,
`max_context_window`, `effective_context_window_percent`, `default_reasoning_level`,
`multi_agent_version`, `tool_mode`, etc.).

Tampoco hay un subcomando de precios: `codex debug --help` sólo lista `models`,
`app-server` y `prompt-input`, y `codex --help` no expone ningún comando de billing o
pricing. El precio hay que traerlo de la documentación del proveedor.

## 2. Precio verificado

Fuentes primarias (documentación oficial de OpenAI, consultadas el 2026-08-16):

- <https://developers.openai.com/api/docs/pricing.md>
- <https://developers.openai.com/api/docs/models/gpt-5.6-sol>

Las dos coinciden en el tramo estándar. Precio de lista en **USD por millón de tokens**:

| Tramo | Entrada | Entrada cacheada | Escritura de caché | Salida |
|---|---|---|---|---|
| Contexto corto (≤ 272 000 tokens de input) | 5.00 | 0.50 | 6.25 | 30.00 |
| Contexto largo (> 272 000 tokens de input) | 10.00 | 1.00 | 12.50 | 45.00 |

La página del modelo enuncia la regla del segundo tramo textualmente: *«Prompts with
>272K input tokens are priced at 2x input and 1.5x output for the full request»*. Dos
consecuencias que la estimación de costo tiene que respetar:

- El umbral se evalúa sobre los **tokens de input del request**, no sobre el acumulado
  de la etapa ni de la corrida.
- El recargo se aplica **al request completo**, no sólo a los tokens que exceden el
  umbral.

**NO VERIFICADO:** si el `service_tier: priority` («Fast», 1.5x de velocidad) que el
catálogo del CLI lista para `gpt-5.6-sol` tiene un precio distinto. No aparece en las
dos páginas consultadas y no se usa en el experimento (las invocaciones no lo piden), así
que no bloquea nada; queda anotado por si el dashboard de billing de la piloto muestra
una línea que no cierra.

## 3. Comparación con `claude-opus-5` — ¿se sostiene el pareo por precio?

`claude-opus-5`: **USD 5 / M de entrada, 25 / M de salida**, según ADR-009 D3. Se
cross-chequeó contra la documentación de Anthropic el 2026-08-16
(<https://platform.claude.com/docs/en/about-claude/models/overview.md>), que confirma
esos valores y publica **un único par de precios para la ventana completa de 1M**, sin
tramo por longitud de contexto — a diferencia de la página de OpenAI, que lista dos.

| Concepto | `claude-opus-5` (A) | `gpt-5.6-sol` (B) | B / A |
|---|---|---|---|
| Entrada, tramo corto | 5.00 | 5.00 | 1.00 |
| Salida, tramo corto | 25.00 | 30.00 | 1.20 |
| Entrada, > 272K input | 5.00 | 10.00 | 2.00 |
| Salida, > 272K input | 25.00 | 45.00 | 1.80 |

**Veredicto: el pareo por precio se sostiene en el tramo corto y no en el tramo largo.**

- En el tramo corto la entrada es **idéntica** y la salida es **20 % más cara** del lado
  B. Es la misma asimetría que ADR-005 ya había aceptado al parear `claude-opus-4-8`
  (5/25) con `gpt-5.5` (5/30) — el criterio de pareo no cambia de naturaleza con el
  re-pinneo, sólo se confirma con fuente primaria.
- La alternativa que ADR-009 D3 descartó para A, `claude-fable-5` (10/50), habría dejado
  una brecha mayor y en el sentido contrario: A habría costado 2.00x la entrada y 1.67x
  la salida de B. El pareo elegido sigue siendo el más cerrado disponible.
- En el tramo largo la brecha se abre a 2.00x / 1.80x. Esto **es nuevo**: no existía como
  categoría cuando se escribió el criterio de pareo, porque del lado A no hay tramo largo.

### El tramo largo no es hipotético para el harness B

Los dos hechos siguientes están verificados por separado y su cruce es una inferencia,
no una medición:

1. El umbral de facturación es 272 000 tokens de input (§2, fuente primaria).
2. [ADR-010](../../decisiones/ADR-010-delegacion-contexto-y-evaluador.md) D2 registra un
   turno de `gpt-5.6-sol` que completó con **294 318 tokens de input**, con y sin el
   override `model_context_window=1000000`.

Es decir: **ese turno ya cayó en el tramo largo**, y con ADR-010 D2 fijando
`-c model_context_window=1000000` en las dos celdas B, el umbral de auto-compactación
sube a ≈ 950 000 —si el override opera como ADR-010 D2 espera, que es exactamente lo que
el ítem 22 manda medir—, con lo cual la historia puede acumularse muy por encima de 272 000
antes de que el harness compacte, y cada request a partir de ahí se factura al doble de
entrada. **La estimación de costo de B no puede usar una tarifa plana**: tiene que
decidir el tramo request por request. Un estimador plano al tramo corto subestima; uno
plano al tramo largo sobreestima.

Esto no reabre ADR-010 D2 — el override sigue siendo la decisión correcta para cerrar la
asimetría de compactación — pero le pone un costo cuantificado que antes no estaba
declarado, y refuerza la instrucción del ítem 22 de medir la compactación en la piloto.

## 4. Discrepancia de ventana de contexto entre fuentes (no resuelta acá)

Anotada porque apareció al leer las mismas páginas, y porque toca la asimetría de ventana
que ADR-009 D3 declaró como amenaza:

| Fuente | Ventana de `gpt-5.6-sol` |
|---|---|
| `codex debug models` (0.146.0) | `context_window: 272000`, `max_context_window: 272000` |
| Página del modelo de OpenAI (2026-08-16) | «1,050,000 context window» |

El 272 000 del catálogo del CLI coincide exactamente con el umbral de facturación de la
documentación, lo que sugiere que el CLI está pinneando el límite del tramo barato y no
la capacidad del modelo. **No se resuelve en este documento**: pertenece a ADR-009 D3
(que declaró la asimetría 1 000 000 contra 272 000) y al ítem 22 de la checklist. Queda
como decisión para el tesista.

## 5. Qué queda por hacer con este dato

- Cargar la tabla de precios en `pipeline/comun/nucleo.py` (`PRECIOS_USD_POR_MTOK`), que
  hoy sigue pinneada a `claude-opus-4-8` / `gpt-5.5`. Reemplazo propuesto (el archivo es
  de otro agente; esto no está aplicado):

  ```python
  # Precios de lista en USD por millón de tokens. Verificados 2026-08-16 contra
  # developers.openai.com/api/docs/pricing.md y
  # platform.claude.com/docs/en/about-claude/models/overview.md.
  # Detalle y comparación: runs/piloto-01/precio-gpt-5-6-sol.md
  # `umbral_tramo_largo` = tokens de INPUT a partir de los cuales el request
  # COMPLETO se factura al tramo largo; None = el proveedor no tiene tramo largo.
  PRECIOS_USD_POR_MTOK = {
      "claude-opus-5": {
          "entrada": 5.0,
          "salida": 25.0,
          "umbral_tramo_largo": None,
      },
      "gpt-5.6-sol": {
          "entrada": 5.0,
          "salida": 30.0,
          "umbral_tramo_largo": 272_000,
          "entrada_tramo_largo": 10.0,
          "salida_tramo_largo": 45.0,
      },
  }
  ```

  El tramo se decide **por request**, contra los `input_tokens` de ese request; no
  contra el acumulado de la etapa.
- Registrar en el manifest de cada corrida los precios usados para estimar, para que el
  meta-análisis pueda recalcular si el proveedor los cambia.
- Contrastar la estimación local contra el dashboard de billing de OpenAI en la piloto-02
  (ítem 2 de la checklist H6), que es donde este número se valida de verdad.
