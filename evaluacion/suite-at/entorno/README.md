# Entorno on-chain de evaluación

Nodo Ethereum local que reemplaza a Sepolia durante la evaluación (H8), con el
mismo `chainId` (**11155111**) que la spec fija como única red
(`spec/00-fundaciones/activos-y-par-de-trading.md` §1). Sobre él se despliega el
**USDC-mock** (ERC-20, 6 decimales, `mint` público) que la spec declara como
"configuración por entorno" (§2.2).

## Componentes

| Archivo              | Qué es                                                                  |
|----------------------|-------------------------------------------------------------------------|
| `docker-compose.yml` | Nodo **anvil** (foundry) con `--chain-id 11155111`, automine, puerto 8545. Imagen pinneada por digest: `ghcr.io/foundry-rs/foundry:stable@sha256:043752653d5be351c71709091b3db97c4421c907eb40ea294195e7f532aadf46` (tag `stable` resuelto el 2026-07-07 contra el registry de ghcr; manifest index multi-arch amd64+arm64, build del 2025-12-22, commit foundry `b0a9dd9c`) |
| `UsdcMock.sol`       | Fuente del ERC-20 mock (6 decimales, `mint(address,uint256)` público)   |
| `usdc-mock.bin/.abi.json` | Artefactos compilados (solc 0.8.28, vendoreados: el despliegue no requiere toolchain Solidity) |
| `desplegar-usdc.py`  | Despliega el mock vía `eth_sendTransaction` (cuenta 0 de anvil) y escribe `usdc-mock.address` + `entorno.env` |
| `fondear.py`         | Fondea cualquier dirección con ETH y/o USDC-mock (p. ej. la hot wallet del SUT) |

## Levantar y preparar

```bash
cd evaluacion/suite-at/entorno
docker compose up -d --wait      # nodo en http://127.0.0.1:8545
python desplegar-usdc.py         # imprime la dirección del USDC-mock y el bloque
source entorno.env               # exporta EVAL_RPC_URL / EVAL_USDC_ADDRESS / EVAL_USDC_DEPLOY_BLOCK
```

Apagar con `docker compose down`. **No hay estado persistente a propósito**: cada
corrida de evaluación parte de una cadena limpia y un mock recién desplegado.

## Decisiones de diseño

- **Automine + minado a demanda.** anvil mina cada transacción al instante y el
  harness avanza confirmaciones minando bloques vacíos (`anvil_mine`, expuesto en
  `helpers/onchain.py` como `minar_bloques(n)`). Con
  `CONFIRMACIONES_REQUERIDAS = 12`, un depósito se vuelve acreditable minando 12
  bloques después de su inclusión — determinista y sin esperas de reloj.
- **Cuentas de anvil.** anvil usa por defecto el mnemonic canónico de
  Hardhat/Anvil (`MNEMONIC_HARDHAT` de HU-06-02: `"test test ... junk"`): las
  cuentas 0..9 (índices BIP-44 0..9) están **desbloqueadas** y prefondeadas con
  10 000 ETH. El harness usa la cuenta 0 como tesorería (deploy, fondeo,
  depósitos simulados) sin necesidad de firmar del lado del test. Nota: el
  escaneo de depósitos del SUT parte de `BLOQUE_INICIO` (≥ bloque de despliegue
  del mock), de modo que los saldos de génesis no cuentan como depósitos.
- **Imagen de anvil pinneada por digest.** El tag `stable` de ghcr es flotante;
  el compose fija `stable@sha256:0437526…` (manifest index multi-arch), de modo
  que un `docker pull` entre la piloto y las corridas oficiales no pueda traer
  un anvil distinto. Verificación: `docker manifest inspect
  ghcr.io/foundry-rs/foundry:stable` debe devolver ese digest; si el proyecto
  decide adoptar un `stable` más nuevo, se actualiza el digest acá y en el
  compose en el mismo commit (nunca entre celdas de una misma ventana de corridas).
- **Sin fork de Sepolia real.** La spec sólo exige el `chainId` y el
  comportamiento JSON-RPC estándar (`eth_getLogs`, `eth_getTransactionReceipt`,
  `eth_chainId`, etc.), que anvil provee; una testnet real haría los tests lentos
  y no deterministas (12 confirmaciones ≈ 2.5 min por depósito, reorgs reales).

## Contrato de arranque del SUT (parámetros de entorno)

La spec **prevé** estos parámetros como configuración por entorno; son lo único
que el entorno de evaluación le comunica a la implementación evaluada. La spec
**no fija nombres de variables** (el SUT documenta los suyos); acá se listan el
**parámetro, su valor en este entorno y dónde la spec lo prevé**:

| Parámetro (del SUT)              | Valor en este entorno                   | Previsto por la spec en |
|----------------------------------|------------------------------------------|--------------------------|
| URL del nodo RPC de Sepolia      | `http://127.0.0.1:8545`                 | épica 07 (README, "nodo RPC configurado"; verifica `eth_chainId == 11155111` al arrancar) |
| Dirección del contrato USDC-mock | salida de `desplegar-usdc.py` (`usdc-mock.address`) | `00-fundaciones/activos-y-par-de-trading.md` §2.2; épicas 07/08 ("única y constante por entorno") |
| Bloque de inicio del indexador (`BLOQUE_INICIO_CONFIGURADO`) | `EVAL_USDC_DEPLOY_BLOCK` (bloque de despliegue del mock) | épica 07 (README, "parámetro de entorno… como mínimo el bloque de despliegue del contrato") |
| Mnemonic/seed HD                 | lo genera o importa el SUT (24 palabras BIP-39; HU-06-01 RN-1/RN-2) — **no** lo provee el entorno | HU-06-01 ("puede generarse internamente o importarse desde una configuración segura") |

Los demás parámetros on-chain y de plataforma tienen **valor por defecto fijado
por la spec** y no se tocan: `CONFIRMACIONES_REQUERIDAS = 12`,
`GAS_PRICE_SOURCE = configured_fixed`, `GAS_PRICE_WEI = 20000000000`,
`GAS_LIMIT_ETH = 21000`, `GAS_LIMIT_ERC20 = 100000`, `MAX_BROADCAST_RETRIES = 5`,
`MAX_BLOCKS_PENDING = 50`, mínimos de retiro, TTL de token 3600 s, rate limit
60 req/min (épicas 01/02/07/08, HU-09-02 RN-12). Si una implementación los
expone como configuración, se dejan en esos valores.

**Fondeo de la hot wallet (dirección emisora).** La spec asume que la emisora
del SUT siempre tiene ETH on-chain para el gas y declara su recarga fuera de
alcance (`spec/08-retiros-on-chain/README.md`, "Supuesto operacional"). Antes de
evaluar la épica 08, el evaluador obtiene la dirección emisora del SUT (de su
documentación/log de arranque, parte de su entrega operativa) y la fondea:

```bash
python fondear.py 0x<emisora> --eth 100          # gas para retiros ETH y ERC-20
python fondear.py 0x<emisora> --usdc 1000000     # respaldo USDC de retiros USDC
```

## Variables que consume la suite (lado harness)

| Env var                  | Default                  | Uso                                    |
|--------------------------|--------------------------|----------------------------------------|
| `EVAL_RPC_URL`           | `http://127.0.0.1:8545`  | `helpers/onchain.py` (fixture `rpc`)   |
| `EVAL_USDC_ADDRESS`      | —                        | mint/transfer/balance del USDC-mock    |
| `EVAL_USDC_DEPLOY_BLOCK` | —                        | referencia para configurar el SUT      |
