# Log de intervenciones humanas — pre-piloto-a

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


> Las tres entradas de este log son **smokes de avance de etapa** (protocolo §4.2), no
> correcciones al agente: en ninguna se le dijo ni se le mostró nada. Se registran porque
> tocan el repo de la corrida. **Cero intervenciones de las categorías 1–8** en toda la
> corrida.

## INT-01 — Smoke check de avance de la etapa backend

- **Timestamp:** 2026-08-24 ~10:11 (-03)
- **Etapa/componente:** backend / procedimiento de avance de etapa
- **Categoría causa raíz:** no aplica (procedimiento del protocolo)
- **Disparador:** cierre de la etapa backend (3 pasos, exit 0, evento `fin`).
- **Intervención:** `.env` derivado del `.env.example` del SUT con
  `WALLET_ENCRYPTION_KEY` aleatoria, `ETH_RPC_URL=http://127.0.0.1:8545`,
  `USDC_CONTRACT_ADDRESS=0x5FbDB2315678afecb367f032d93F642f64180aa3` y `PORT=3102`;
  `npm run build` y `npm start`. Se corrió **en el host**, antes de que ADR-021 fijara que
  el smoke va en contenedor.
- **Resultado:** build exit 0; `GET /health` →
  `{"status":"ok","service":"cex-backend","network":"sepolia","chainId":"11155111","rpcConfigured":true}`,
  y el log del SUT registró `JSON-RPC verificado: chainId 11155111 (sepolia)`. **Criterio
  de avance cumplido.** Se apagó el SUT y se borraron `data/` y `.env`.
- **Referencias:** protocolo §4.1/§4.2; matriz de componentes 9.1.

## INT-02 — Smoke check de avance de la etapa web

- **Timestamp:** 2026-08-24 ~12:08 (-03)
- **Etapa/componente:** web / procedimiento de avance de etapa
- **Categoría causa raíz:** no aplica (procedimiento del protocolo)
- **Disparador:** cierre de la etapa web (3 pasos, exit 0, evento `fin`).
- **Intervención y resultado:** `npm run build` sobre `web/` **dentro del contenedor** de
  la imagen `tesina/agente-a:piloto-01` (ADR-021): exit 0, `dist/` generado,
  `✓ built in 97ms`. **Criterio de avance cumplido.**
- **Referencias:** ADR-020 (qué comando); ADR-021 (dónde se ejecuta).

## INT-03 — Smoke check de avance de la etapa mobile

- **Timestamp:** 2026-08-24 ~12:14 (-03)
- **Etapa/componente:** mobile / procedimiento de avance de etapa
- **Categoría causa raíz:** no aplica (procedimiento del protocolo)
- **Disparador:** cierre de la etapa mobile (3 pasos, exit 0, evento `fin`).
- **Intervención y resultado:** `npx expo export --platform android` en el contenedor:
  exit 0, bundle y `metadata.json` generados. **Criterio de avance cumplido.** Con esto
  la corrida `pre-piloto-a` queda **completa: 3 etapas, 3 smokes**.
- **Referencias:** ADR-020; ADR-021.
