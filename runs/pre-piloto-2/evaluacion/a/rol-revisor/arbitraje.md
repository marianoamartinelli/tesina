celda: celda-en-evaluacion
instrumento: rol-revisor
fecha: 2026-09-07
discrepantes: 3 de 63

Las tres claves de `discrepancias.txt` son puntos del censo (`etapa,punto`). Los 36 criterios de la Parte B y los 24 puntos restantes del censo se copian de `pasada-1/` verbatim.

| clave | pasada 1 | pasada 2 | final | evidencia que decide | regla del instrumento |
| --- | --- | --- | --- | --- | --- |
| backend,3 | eje=OPERABILIDAD | eje=CORRECCION | eje=OPERABILIDAD | Artefacto L34-41: default de `USDC_CONTRACT_ADDRESS`. paso2-revisor `backend/src/config/index.ts:46` (`DEFAULT_USDC_CONTRACT_ADDRESS='0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238'`) y `:177` fallback. Spec `00-fundaciones/activos-y-par-de-trading.md` §2.2: parámetro de despliegue, «no se fija un valor literal aquí». No cita RN/AT/INV; el daño es arrancar un entorno sin la variable con un `tokenAddress` ajeno. Destino: paso3 borra el default y `parseRequiredAddressEnv` lanza `ConfigError`. | Rúbrica Parte A `eje`: CORRECCION es incumplimiento de RN/AT; este punto no cita ninguno. Es un default de configuración del despliegue (arrancar sin la variable) ⇒ OPERABILIDAD. R2 MENOR (no impide arranque). R3 SPEC. R4/R5 VERDADERO/RESUELTO. |
| backend,6 | eje=CORRECCION | eje=OPERABILIDAD | eje=CORRECCION | Artefacto L75-85 cita **HU-06-01 RN-6**. paso2-revisor `backend/scripts/bootstrap-env.mjs:16-31` hace `writeFileSync` de `backend/.env` con `WALLET_ENCRYPTION_KEY`; `package.json` start/dev invocan el script; `config/index.ts:162` default `DATABASE_PATH='./data/exchange.db'`. Spec HU-06-01 RN-6: la credencial «nunca se persiste junto al material cifrado». Destino: paso3 elimina `backend/scripts/`; start/dev ya no llaman bootstrap. | Rúbrica Parte A `eje`: un punto que afirma incumplimiento de una `RN-*` cae en CORRECCION, no en OPERABILIDAD (build/arranque/docs). R2 MAYOR. R3 SPEC. Ubicación ARCHIVO (el artefacto nombra el script sin línea). R4/R5 VERDADERO/RESUELTO. |
| mobile,8 | ubicacion=ARCHIVO_LINEA | ubicacion=ARCHIVO | ubicacion=ARCHIVO_LINEA | Artefacto L93-99: `mobile/tests/setup.ts` no llama `configure({asyncUtilTimeout})` y cita el síntoma en `deposit-address.test.tsx:76` (más tres archivos de test sin línea). paso2-revisor `mobile/tests/setup.ts:10` importa `@testing-library/react-native` sin `configure`. Destino: paso3 `configure({ asyncUtilTimeout: 10000 })`. | Rúbrica Parte A `ubicacion`: `ARCHIVO_LINEA` si el punto señala archivo:línea sobre el repo satélite. Basta una cita `archivo:línea` (`deposit-address.test.tsx:76`); no se exige que la línea sea la del archivo a cambiar. R3 ancla EJECUCION. R4 VERDADERO (ausencia de `configure` estática). R5 RESUELTO. |

## Conteos

- coincidieron con pasada 1: 3
- coincidieron con pasada 2: 0
- coincidieron con ninguna: 0
- residuales (`NO_EVALUABLE` / `NO_VERIFICABLE`): 0
