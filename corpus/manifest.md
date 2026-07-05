# Manifest del corpus RAG — v1.0

- **Fecha de captura:** 2026-07-05 (todos los documentos descargados el mismo día).
- **Estado:** congelado (hito H3). El commit de este repo que contiene esta versión del
  corpus se registra en el manifest de cada corrida `*-con-rag`; cualquier cambio
  posterior exige nueva versión de este manifest **antes** de la primera corrida oficial.
- **Verificación:** `shasum -a 256 -c` contra la columna SHA-256 (los archivos se guardan
  byte a byte como se descargaron; sin reformateo).

## Documentos

| # | Archivo | Título | Fuente (URL de captura) | Versión upstream (commit · fecha) | SHA-256 |
|---|---------|--------|--------------------------|-----------------------------------|---------|
| 1 | `documentos/bip-0032.mediawiki` | BIP-32 — Hierarchical Deterministic Wallets | `raw.githubusercontent.com/bitcoin/bips/master/bip-0032.mediawiki` | `c0644a054fd1` · 2026-03-05 | `e5e00a8289db2f681052cf24a745320afc225e66b25d1e489a7c884d2fc7f11f` |
| 2 | `documentos/bip-0039.mediawiki` | BIP-39 — Mnemonic code for generating deterministic keys | `raw.githubusercontent.com/bitcoin/bips/master/bip-0039.mediawiki` | `24e96e870fff` · 2026-01-12 | `964f3adf5f7dc18d2515606ef73a2ca599c04519f90ac2fa5b5ddcec25295f76` |
| 3 | `documentos/bip-0039-wordlist-english.txt` | BIP-39 — wordlist inglés (2048 palabras) | `raw.githubusercontent.com/bitcoin/bips/master/bip-0039/english.txt` | `ce1862ac6bcf` · 2014-02-07 | `2f5eed53a4727b4bf8880d8f3f199efc90e58503646d9ff8eff3a2ed3b24dbda` |
| 4 | `documentos/bip-0044.mediawiki` | BIP-44 — Multi-Account Hierarchy for Deterministic Wallets | `raw.githubusercontent.com/bitcoin/bips/master/bip-0044.mediawiki` | `53dac1ba297a` · 2026-02-27 | `6a541c79f94077ac529941a8cbd373ce077a5d6e97b6dd8209b45ac10f737eaf` |
| 5 | `documentos/eip-155.md` | EIP-155 — Simple replay attack protection | `raw.githubusercontent.com/ethereum/EIPs/master/EIPS/eip-155.md` | `15f61ed0fda8` · 2020-09-30 | `3c208813585d8fca67a92d908ece47402f87a18a14f1b20ee5ebcb3e702dcc9c` |
| 6 | `documentos/erc-20.md` | ERC-20 (EIP-20) — Token Standard | `raw.githubusercontent.com/ethereum/ERCs/master/ERCS/erc-20.md` | `8358b94b5ed4` · 2023-12-13 | `50d0bdc535ed8987ac5c124cb5f9c39606806c97e909aae66ef4b747dd9c93dd` |
| 7 | `documentos/erc-55.md` | ERC-55 (EIP-55) — Mixed-case checksum address encoding | `raw.githubusercontent.com/ethereum/ERCs/master/ERCS/erc-55.md` | `8dd085d159cb` · 2023-10-25 | `54a9b25ffcd12966c60d6abd6584734d2793734f266fbe41118e6ee52b05dc9e` |
| 8 | `documentos/erc-681.md` | ERC-681 (EIP-681) — URL Format for Transaction Requests | `raw.githubusercontent.com/ethereum/ERCs/master/ERCS/erc-681.md` | `8dd085d159cb` · 2023-10-25 | `46320fe4a95d17703817c6addd945f86d94e9d27d431efe8623e03d86b5457c0` |
| 9 | `documentos/ethereum-json-rpc.md` | Ethereum JSON-RPC API (documentación ethereum.org) | `raw.githubusercontent.com/ethereum/ethereum-org-website/dev/public/content/developers/docs/apis/json-rpc/index.md` | `461488e093c8` · 2026-06-28 | `849abb0a4240a2f8ee9c249ceecfd120a908b08aaa0f5f7fc63055e704fc6cbd` |

La columna "Versión upstream" es el hash (12 hex) y fecha del **último commit que tocó ese
archivo** en el repositorio de origen al momento de la captura, obtenido vía API de GitHub.

## Decisiones de curaduría

1. **Núcleo incluido** (previsto en el README): BIP-32, BIP-39, BIP-44, EIP-155, ERC-20
   (EIP-20), ERC-55 (EIP-55). Cobertura verificada contra las menciones reales de la spec
   (`grep` de `BIP-*`/`EIP-*`/`ERC-*` sobre `spec/`, 2026-07-05).
2. **Wordlist BIP-39 inglés incluida como anexo** (doc 3): es normativa — HU-06-01 RN-2
   exige validar pertenencia de cada palabra al wordlist inglés de 2048 palabras; sin el
   archivo, el estándar es inaplicable.
3. **ERC-681 incluido**: HU-11-06 (mobile) lo usa para el formato de URI/QR de depósito
   (9 menciones en la spec). Es estándar normativo del dominio, no material que resuelva
   el ejercicio.
4. **JSON-RPC de Ethereum incluido como soporte** (doc 9): las épicas 07–08 citan
   `eth_getLogs`, `eth_getTransactionReceipt`, `eth_getTransactionCount`, `eth_chainId`,
   `eth_getBlockByNumber`, `eth_blockNumber`, `eth_gasPrice`; la semántica de esos métodos
   (p. ej. `logIndex` block-scoped, HU-07-02) proviene de esta interfaz. Se captura la
   documentación de ethereum.org (Markdown, apta para indexado) en lugar del OpenRPC de
   `ethereum/execution-apis` (JSON máquina-a-máquina, inadecuado para RAG).
5. **EIP-1559 excluido deliberadamente**: la spec lo declara **fuera de alcance** (README
   de la épica 08, nota de diseño: `TX_TYPE = legacy`, Type-0). Incluirlo agregaría
   material que contradice la convención fijada y podría inducir al agente a implementar
   transacciones Type-2 que la spec prohíbe.
6. **EIP-20/55/681 se capturan del repo `ethereum/ERCs`**: en el repo histórico
   `ethereum/EIPs` esos archivos son stubs con `status: Moved` (la Ethereum Foundation
   migró los ERC a un repositorio propio). Los archivos se nombran `erc-*.md` reflejando
   la fuente real; la spec los referencia indistintamente como EIP-20/EIP-55/EIP-681.
7. **Sin material que resuelva el ejercicio** (regla 3 del README): no se incluyen
   implementaciones de exchanges, motores de matching ni wallets; sólo estándares y
   documentación normativa de la interfaz on-chain.
