# Corpus de conocimiento de dominio (condiciones con RAG)

Corpus curado de BIPs y EIPs que se indexa como base de conocimiento en las celdas
`*-con-rag`. **Congelado** (hito H3, 2026-07-05): el commit usado para indexar queda
registrado en el manifest de cada corrida.

## Contenido (9 documentos — ver `manifest.md` para fuente, versión y hash)

- **Núcleo:** BIP-32, BIP-39 (+ wordlist inglés, normativa por HU-06-01 RN-2), BIP-44,
  EIP-155, ERC-20 (EIP-20), ERC-55 (EIP-55).
- **Soporte:** ERC-681 (EIP-681, URI/QR de depósito en mobile), JSON-RPC de Ethereum
  (métodos `eth_*` citados por las épicas 07–08).
- **Excluido deliberadamente:** EIP-1559 — la spec fija `TX_TYPE = legacy` (Type-0) y
  declara EIP-1559 fuera de alcance; incluirlo induciría a contradecir la convención.

## Reglas de curaduría

1. Cada documento se guarda en su versión fuente (texto plano/Markdown) con un
   registro en `manifest.md`: título, fuente (URL), fecha de captura, hash del
   contenido.
2. El corpus es **idéntico** para las dos celdas con RAG; no se ajusta por modelo.
3. No se incluye material que resuelva el ejercicio (p. ej. implementaciones de
   exchanges): sólo estándares y documentación normativa del dominio on-chain.
