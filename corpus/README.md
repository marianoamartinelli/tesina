# Corpus de conocimiento de dominio (condiciones con RAG)

Corpus curado de BIPs y EIPs que se indexa como base de conocimiento en las celdas
`*-con-rag`. **Congelado antes de las corridas oficiales** (hito H3): el commit usado
para indexar queda registrado en el manifest de cada corrida.

## Alcance previsto

- **Núcleo (aplican directamente a la spec):** BIP-32, BIP-39, BIP-44, EIP-155,
  EIP-20 (ERC-20), EIP-55.
- **Soporte (a evaluar en la curaduría):** documentación de gas/fees (EIP-1559),
  JSON-RPC de Ethereum, según qué necesiten realmente las épicas 06–08.

## Reglas de curaduría

1. Cada documento se guarda en su versión fuente (texto plano/Markdown) con un
   registro en `manifest.md`: título, fuente (URL), fecha de captura, hash del
   contenido.
2. El corpus es **idéntico** para las dos celdas con RAG; no se ajusta por modelo.
3. No se incluye material que resuelva el ejercicio (p. ej. implementaciones de
   exchanges): sólo estándares y documentación normativa del dominio on-chain.
