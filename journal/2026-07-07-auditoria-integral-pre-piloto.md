# 2026-07-07 — Auditoría integral pre-piloto y regla non-slop

**Contexto:** entre H5 (cerrado) y H6 (piloto). Sesión con Claude: el tesista pidió
una auditoría de consistencia y mejora sobre todas las esferas del proyecto (procesos,
artifacts, pipeline, evaluación), un barrido "unslop" contra desperdicio textual y
datos inflados/inventados, y un artifact de presentación para los directores. Todo el
trabajo va en la rama `auditoria-consistencia-2026-07-07` y termina en PR para
revisión del tesista (nada directo a `main`).

## Qué se hizo

**Auditoría multi-agente con verificación adversarial** (4 auditores + 1 verificador
por hallazgo, máx. 4 en paralelo): 26 hallazgos alto/medio, de los cuales **24
confirmados y 2 refutados** por los verificadores; 5 menores adicionales. Los
confirmados se aplicaron en la misma sesión:

- **Procesos/documentación:** anotación de H5 en `ROADMAP.md` corregida a los números
  reales (449 funciones de test; 455 con test + 66 no-automatizables = 521 backend;
  quedaban los conteos pre-v1.1); nota de erratas spec-v1.0→v1.1 en
  `decisiones/README.md`; manifest de corrida extendido (paridad verificada, entorno
  host y on-chain, desglose por etapa, `logs_jsonl`); política de archivado de los
  JSONL en `runs/README.md`; **`runs/piloto-01/checklist-h6.md`** nueva, consolidando
  los 16 pendientes de la piloto que estaban dispersos en 8+ lugares;
  **`analisis/amenazas-validez.md`** nuevo, con las 10 amenazas ya pre-registradas y
  sus fuentes (insumo directo del capítulo 4).
- **Pipeline:** prompt de backend autocontenido (referenciaba un health-check "de la
  épica 09" que la spec no define); harness A con `system_prompt` preset
  `claude_code` + append (antes el prompt compartido *reemplazaba* el scaffolding
  nativo — asimetría contra ADR-005, B sí componía el suyo); harness B con cierre
  simétrico `error_max_turns` (antes crasheaba sin `resumen_final`, perdiendo
  tokens/costo), eventos `uso_parcial` por pedido a la API (el tope de 200 USD ahora
  es vigilable durante la corrida) y `TMPDIR` del sandbox fuera del repo satélite (el
  seatbelt denegaba el temporal del sistema y las herramientas node fallarían);
  `pipeline/config/piloto-02.yaml` para el smoke de B. Verificado: paridad 39/39,
  dry-run de las 6 configs, firmas contra los SDKs instalados.
- **Evaluación:** `SUITE_CMD_REINICIO_SUT` documentada en README/HELPERS (el
  procedimiento H8 escrito la omitía y ~12 tests de reinicio quedarían `skip`,
  invalidando la corrida según la propia regla skip=0); imagen de anvil pinneada por
  digest real (verificado por dos vías contra ghcr); `validar-resultados.py` nuevo
  para las pasadas del agente evaluador (probado con 6 casos sintéticos);
  `evaluacion/rubricas/README.md` con el procedimiento de archivado/export CSV por
  corrida; docstrings de ep03 con el mapeo banda↔escenario declarado.
- **Artifacts:** 8 de las 9 páginas rediseñadas pedagógicamente (glosas de jerga al
  primer uso, mini-glosario y diagrama de partición de los 693 ATs, detalle operativo
  movido a bloques colapsables, 2 obsolescencias corregidas — H1 databa el re-freeze
  v1.1 como post-experimento). H2 quedó como estaba (única con veredicto "ok").
  Artifact nuevo **"Avance para directores"** (🎓): una página visual con el diseño
  2×2, el estado de hitos, la vara y las decisiones abiertas. QA visual de las 10
  páginas renderizadas antes de publicar.
- **Unslop:** regla permanente en `CLAUDE.md` ("Regla non-slop") + barrido sobre los
  documentos vivos. Saldo: los documentos estaban en general magros; se corrigieron
  una duplicación (journal/README), una misatribución en la nota de H1 del ROADMAP y
  números de línea desactualizados en la checklist.

## Decisiones

- **Regla non-slop** como convención del repo (CLAUDE.md): ningún dato inventado, no
  sobre-informar, sin relleno; los documentos congelados no se reescriben por estilo.
- **ADR-008 (Propuesto, no aceptado):** `disallowed_tools=["WebSearch","WebFetch"]`
  en el harness A para no contaminar el factor RAG. El tesista lo ratifica o rechaza
  en la ventana H6 (el código ya está en la rama; revertible).
- Extensión de la plantilla de manifest y política de archivado de logs: se tratan
  como operacionalización de ADR-003/ADR-004 (precedente del commit 861a56a), sin ADR
  nuevo.
- Los 2 refutados por los verificadores (registro de queries RAG) no se aplicaron: la
  captura existente vía eventos del SDK ya cubre lo que H9 necesita.

## Pendientes

- **El tesista:** revisar y mergear el PR de la rama; ratificar o rechazar ADR-008.
- La deuda de la piloto vive ahora en `runs/piloto-01/checklist-h6.md` (6
  precondiciones + 16 ítems de salida) — es la fuente única; no buscar pendientes
  dispersos.
- Validación runtime de los fixes del harness B (TMPDIR, `error_max_turns`,
  `uso_parcial` vs billing) requiere API keys: piloto-02.

## Observaciones para el meta-análisis

- La verificación adversarial refutó 2 de 26 hallazgos (~8%): la tasa de falsos
  positivos de los auditores LLM es baja pero no nula — el paso de verificación no es
  ceremonial, y dos hallazgos "plausibles" habrían inducido cambios innecesarios.
- Los defectos más graves no estaban *dentro* de los componentes sino en las
  **costuras entre sesiones**: el prompt de etapa citaba un health-check que la spec
  nunca definió; el harness A perdía su scaffolding nativo mientras B conservaba el
  suyo; el procedimiento H8 omitía una variable que la propia suite exige. Cada
  componente había sido verificado al construirse; ninguna verificación cruzaba los
  bordes. Hipótesis para la discusión: en desarrollo asistido por agentes, la clase
  de defecto dominante migra del interior de los módulos a sus interfaces.
- El registro exhaustivo (ADR-003) es lo que hizo posible auditar: cada afirmación
  pudo contrastarse contra journal/ADR/código con fecha. El costo del registro se
  recuperó hoy.
- Deuda de proceso dispersa ≠ deuda registrada: todo estaba anotado en *algún* lado
  (8+ lugares) y aun así era inaccionable hasta consolidarla en una checklist.

### Observaciones diferidas de la sesión 2026-07-06 (agente evaluador)

La entrada `2026-07-06-agente-evaluador-white-box.md` omitió esta sección
(detectado en la auditoría); se reconstruyen acá, un día después, desde lo que esa
entrada sí documenta:

- Diseñar el evaluador LLM obligó a explicitar supuestos que la suite black-box
  permitía dejar implícitos (quién controla el ciclo de vida del SUT, cómo se inyecta
  un mnemonic): el instrumento nuevo actuó como auditor del instrumento viejo, y de
  ahí salió la sobre-declaración F3 que hoy se consolidó como ítem 4 de la checklist.
- El costo de la mitigación anti-sesgo (doble pasada, copia sin `.git`, arbitraje
  humano 100%) se aceptó sin medirlo; la piloto dará el dato real por celda.

## Commits

Serie en la rama `auditoria-consistencia-2026-07-07` (repo/adr/pipeline/evaluacion/
runs/analisis/journal), detallados en el PR.
