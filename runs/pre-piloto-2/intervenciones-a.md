# Log de intervenciones humanas — pre-piloto-2a

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

## INT-01 — Smoke check de avance de la etapa backend

- **Timestamp:** 2026-09-07 00:59 (-03)
- **Etapa/componente:** backend / procedimiento de avance de etapa
- **Categoría causa raíz:** no aplica (procedimiento del protocolo §4.2, ADR-021)
- **Disparador:** cierre de la etapa backend (3 pasos, exit 0, evento `fin`; USD 74,22
  nativos; 16 consultas al corpus).
- **Intervención:** en contenedor `tesina/agente-a:piloto-01` con el repo montado,
  variables por entorno (`WALLET_ENCRYPTION_KEY` aleatoria, `USDC_CONTRACT_ADDRESS` del
  entorno, `ETH_RPC_URL=http://host.docker.internal:8545`, `DATABASE_PATH` en `/tmp`),
  `npm run build && npm start`, puerto publicado 3201.
- **Resultado:** `GET /health` → `{"status":"ok", …, "chain":{"network":"sepolia",
  "chainId":"11155111","rpc":{"status":"OK","chainId":"11155111"}}}`. **Criterio de avance
  cumplido.** Contenedor eliminado; `git status` del repo sin residuos.
- **Referencias:** protocolo §4.1/§4.2; ADR-021.

## INT-02 — Smoke check de avance de la etapa web

- **Timestamp:** 2026-09-07 01:44 (-03)
- **Etapa/componente:** web / procedimiento de avance de etapa
- **Categoría causa raíz:** no aplica (procedimiento del protocolo §4.1, ADR-020/021)
- **Disparador:** cierre de la etapa web (3 pasos, exit 0; USD 38,01; 0 consultas al corpus).
- **Intervención:** `npm run build` en `web/` dentro del contenedor `tesina/agente-a:piloto-01`
  con el repo montado.
- **Resultado:** `tsc -b && vite build` → `✓ built in 540ms`, exit 0. **Criterio de avance
  cumplido.** Sin residuos en el repo (`dist/` ya existía y está ignorado).
- **Referencias:** protocolo §4.1; ADR-020; ADR-021.
