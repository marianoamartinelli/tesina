# Pipeline — harness de agentes

Código y configuración de los dos harness del experimento (hito H4):

- **Harness A:** Claude Agent SDK (Anthropic).
- **Harness B:** OpenAI Agents SDK.

## Principios de diseño (paridad entre condiciones)

1. **Sólo varían los dos factores:** modelo subyacente y disponibilidad de RAG. Todo lo
   demás — etapas del pipeline, prompts de sistema, herramientas disponibles,
   presupuestos — debe ser equivalente entre celdas, y esa equivalencia debe ser
   auditable en este directorio.
2. **Model IDs pinneados:** los IDs exactos se fijan por ADR antes de la primera
   corrida oficial y se registran en cada manifest.
3. **RAG conmutable:** la integración de la base de conocimiento se activa/desactiva
   por configuración, sin cambiar el resto del pipeline.
4. Todo cambio al pipeline posterior a la corrida piloto y anterior a las oficiales se
   registra en el journal; después de la primera corrida oficial, el pipeline queda
   **congelado** hasta terminar las 4.
