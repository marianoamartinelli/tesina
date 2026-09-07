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
- **Resultado:** PENDIENTE — se completa al cerrar la etapa.
- **Referencias:** protocolo §5.8; ADR-025 D3 (la continuación es el camino estándar);
  hallazgo H2-02.
