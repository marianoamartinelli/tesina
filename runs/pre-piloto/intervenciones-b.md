# Log de intervenciones humanas — pre-piloto-b

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

## INT-01

- **Timestamp:**
- **Etapa/componente:** (p. ej. backend/matching, cliente-web)
- **Categoría causa raíz:** (1–8)
- **Disparador:** qué observó el evaluador que motivó intervenir (criterio del protocolo)
- **Descripción:** qué estaba mal
- **Intervención:** qué se le dijo/hizo al agente (textual si fue un prompt)
- **Resultado:** cómo respondió el agente
- **Referencias:** AT-id / HU / INV-* / commit del repo de la corrida

## INT-01 — Smoke check de avance de la etapa backend (no es intervención sobre el agente)

- **Timestamp:** 2026-08-24 ~09:50 (-03)
- **Etapa/componente:** backend / procedimiento de avance de etapa
- **Categoría causa raíz:** no aplica — es el procedimiento del protocolo §4.2, no una
  corrección al agente. Se registra igual porque toca el repo de la corrida.
- **Disparador:** cierre de la etapa backend (evento `fin`, 3 pasos con exit 0).
- **Descripción:** para ejecutar el smoke hay que configurar el SUT con el contrato de
  arranque (`suite-at/entorno/README.md`). El README del SUT documenta sus variables en
  `.env.example`.
- **Intervención:** se creó `.env` en el repo satélite con `WALLET_ENCRYPTION_KEY`
  (aleatoria), `USDC_MOCK_ADDRESS=0x5FbDB2315678afecb367f032d93F642f64180aa3`,
  `SEPOLIA_RPC_URL=http://127.0.0.1:8545` y `PORT=3101`; luego `npm run build` y
  `npm start` **en el host**. No se le dijo ni se le mostró nada al agente.
- **Resultado:** build exit 0; `GET /health` → `{"status":"ok"}`. **Criterio de avance
  cumplido.** Se apagó el SUT y se borró `data/` (base SQLite creada por el arranque)
  para no dejar estado en el repo; el `.env` queda como registro de la configuración
  usada.
- **Referencias:** protocolo §4.1/§4.2; `runs/pre-piloto/matriz-componentes.md` 9.1.

## Nota — la suite black-box NO se corrió

La regla de no-exposición del holdout (protocolo §4.3) vale también acá: la corrida de
`pre-piloto-b` no terminó (faltan las etapas web y mobile), así que la suite se corre
**una sola vez al cierre**, no entre etapas. El smoke de avance usa sólo el health-check.

## INT-02 — Smoke check de avance de la etapa web

- **Timestamp:** 2026-08-24 ~10:30 (-03)
- **Etapa/componente:** web / procedimiento de avance de etapa
- **Categoría causa raíz:** no aplica — procedimiento del protocolo, no corrección al
  agente.
- **Disparador:** cierre de la etapa web (3 pasos, exit 0, evento `fin`).
- **Descripción y resultado:** `npm run build` del cliente web **falla en el host**
  (`@rollup/rollup-linux-arm64-gnu` no encontrado) y **pasa en el contenedor** de la
  misma imagen, en 508 ms, con `dist/` generado. Criterio de avance **cumplido**, con el
  criterio de ADR-020 (build de producción, exit 0) ejecutado donde corresponde
  (ADR-021). No se le dijo nada al agente.
- **Referencias:** `runs/pre-piloto/hallazgos.md` H-15; ADR-020; ADR-021.

## INT-03 — Smoke check de avance de la etapa mobile

- **Timestamp:** 2026-08-24 ~11:05 (-03)
- **Etapa/componente:** mobile / procedimiento de avance de etapa
- **Categoría causa raíz:** no aplica — procedimiento del protocolo.
- **Disparador:** cierre de la etapa mobile (3 pasos, exit 0, evento `fin`).
- **Descripción y resultado:** `npx expo export --platform android` **en el contenedor**
  (ADR-020 fija el comando, ADR-021 el dónde): exit 0, bundle
  `_expo/static/js/android/index-….hbc` de 2,2 MB más `metadata.json`. Criterio de avance
  **cumplido**. Con esto la corrida `pre-piloto-b` queda **completa: 3 etapas, 3 smokes**.
- **Referencias:** ADR-020; ADR-021; matriz de componentes 9.1.
