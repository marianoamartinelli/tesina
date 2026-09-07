# Log de intervenciones humanas — pre-piloto-2b

Registrar **en el momento**, una entrada por intervención, numeradas secuencialmente.

Categorías de causa raíz (del marco metodológico de la propuesta):

1. Mala interpretación de la especificación
2. Código que no compila o no funciona
3. Pérdida de contexto entre etapas o componentes
4. Alucinación general del modelo
5. Fallo de integración entre componentes
6. Problemas de UI/UX
7. Errores en lógica financiera o invariantes del matching engine
8. Errores en estándares de dominio on-chain (BIPs/EIPs mal aplicados, inventados o desactualizados)

---

## INT-01 — Corte de la etapa backend por límite de uso de la suscripción de Codex (continuación §5.8)

- **Timestamp:** 2026-09-07 00:18:38 (-03)
- **Etapa/componente:** backend / paso 1 (`implementador`)
- **Categoría causa raíz:** no aplica — corte por rate limit del proveedor (protocolo §5.8:
  disparador **D2**, intervención tipo **(d)**)
- **Disparador:** a los 24 min de etapa el stream `--json` emitió `error` + `turn.failed`
  con «You've hit your usage limit … try again at 5:35 AM»; `codex exec` salió con 1 y el
  orquestador registró `corte: codigo_salida_no_cero` tras tomar el snapshot del paso 1
  (97 archivos). Ninguna corrección al agente.
- **Intervención:** re-invocar el orquestador para `--etapa backend` sobre el estado
  actual del repo satélite, con sesión fresca y los mismos prompts, cuando el límite se
  libere (05:36 -03, programado). El JSONL nuevo se suma al de la etapa en el manifest.
- **Resultado:** la continuación arrancó a las 05:36:00 con sesión fresca sobre el repo:
  paso 1 completo (exit 0, 05:48), paso 2 completo con `revision-backend.md` (06:02), y
  el **paso 3 cortado a las 06:05:13** por el mismo límite («try again at 1:36 PM»).
  Ver INT-02.
- **Referencias:** protocolo §5.8; ADR-025 D3 (la continuación es el camino estándar);
  hallazgo H2-02.

## INT-02 — Segundo corte por límite de uso; continuación del paso 3 programada

- **Timestamp:** 2026-09-07 06:05:13 (-03)
- **Etapa/componente:** backend / paso 3 (`implementador`, pase correctivo)
- **Categoría causa raíz:** no aplica — corte por rate limit del proveedor (§5.8, D2 / (d))
- **Disparador:** `turn.failed` con «You've hit your usage limit … try again at 1:36 PM» a
  los 2 min 33 s del paso 3; snapshot tomado; `corte: codigo_salida_no_cero`.
- **Intervención:** re-invocar el orquestador con `--desde-paso 3` (agregado al núcleo en
  esta sesión: salta los pasos ya completos y registra `paso_omitido`) a las 13:37 (-03),
  sobre el estado actual del repo y con `revision-backend.md` ya escrito.
- **Resultado:** el tesista extendió la suscripción de Codex a las 11:00 y la continuación
  se lanzó a las 11:05:15 en vez de esperar a las 13:37: pasos 1 y 2 registrados como
  `paso_omitido`, paso 3 completo a las 11:18:03 (exit 0, evento `fin`). Etapa backend
  **completa** en tres invocaciones del orquestador.
- **Referencias:** protocolo §5.8; H2-08.

## INT-03 — Smoke check de avance de la etapa backend

- **Timestamp:** 2026-09-07 11:22 (-03)
- **Etapa/componente:** backend / procedimiento de avance de etapa
- **Categoría causa raíz:** no aplica (procedimiento del protocolo §4.2, ADR-021)
- **Disparador:** cierre de la etapa backend (paso 3 exit 0, `fin`); 15 consultas al corpus
  en la etapa; 20 rollouts en `sesiones-codex/`.
- **Intervención:** contenedor `tesina/agente-b:piloto-01` con el repo montado, variables por
  entorno (`WALLET_ENCRYPTION_KEY` aleatoria, `USDC_TOKEN_ADDRESS`, `RPC_URL`,
  `DATABASE_PATH` en `/tmp`), `npm start`, puerto 3202. Un primer intento con los nombres
  de variables del SUT de la pre-piloto 1 (`USDC_MOCK_ADDRESS`, `SEPOLIA_RPC_URL`) abortó
  con `INTERNAL_ERROR: el backend no pudo iniciar`: cada implementación nombra sus
  variables (contrato de arranque, `entorno/README.md`).
- **Resultado:** `GET /health` → `{"status":"ok"}`. **Criterio de avance cumplido.** Sin
  residuos en el repo.
- **Referencias:** protocolo §4.1/§4.2; ADR-021.

## INT-04 — Smoke check de avance de la etapa web

- **Timestamp:** 2026-09-07 12:18 (-03)
- **Etapa/componente:** web / procedimiento de avance de etapa
- **Categoría causa raíz:** no aplica (procedimiento del protocolo §4.1, ADR-020/021)
- **Disparador:** cierre de la etapa web (3 pasos, exit 0, sin cortes; 56 min; 0 consultas
  al corpus).
- **Intervención:** `npm run build` en `web/` dentro del contenedor `tesina/agente-b:piloto-01`.
- **Resultado:** `tsc -b && vite build` → `✓ built in 382ms`, exit 0. **Criterio de avance
  cumplido.** Sin residuos.
- **Referencias:** protocolo §4.1; ADR-020; ADR-021.

## INT-05 — Smoke check de avance de la etapa mobile

- **Timestamp:** 2026-09-07 13:22 (-03)
- **Etapa/componente:** mobile / procedimiento de avance de etapa
- **Categoría causa raíz:** no aplica (procedimiento del protocolo §4.1, ADR-020/021)
- **Disparador:** cierre de la etapa mobile (3 pasos, exit 0, sin cortes; 61 min; 2
  consultas al corpus). Total de la celda: 17 consultas, 44 rollouts, 3 etapas completas.
- **Intervención:** `npx expo export --platform android` en `mobile/` dentro del contenedor
  `tesina/agente-b:piloto-01`.
- **Resultado:** `Exported: dist`, exit 0. **Criterio de avance cumplido.** Sin residuos: B
  commiteó todo su trabajo (a diferencia de A, que dejó 20 archivos sin commitear).
- **Referencias:** protocolo §4.1; ADR-020; ADR-021.
