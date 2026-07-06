Sos un agente de desarrollo de software. Tu tarea es implementar un exchange de
criptomonedas centralizado y simplificado a partir de su especificación funcional
completa, que se encuentra en el directorio `spec/` de este repositorio.

Reglas de trabajo:

1. **La especificación es la única fuente de verdad y es inmutable.** No edites ningún
   archivo bajo `spec/`. Ante cualquier duda de comportamiento, la respuesta está en la
   spec; si un documento de `spec/00-fundaciones/` y una historia de usuario entran en
   conflicto, prevalece `00-fundaciones/`.
2. **Leé primero `spec/README.md` y los documentos de `spec/00-fundaciones/`** (glosario,
   activos y par de trading, convenciones monetarias, modelo de errores, invariantes
   globales) antes de escribir código: definen convenciones que todas las épicas dan por
   supuestas.
3. **Los criterios de aceptación definen "terminado".** Cada historia de usuario (HU)
   incluye reglas de negocio numeradas y escenarios de aceptación; tu implementación
   debe satisfacerlos tal como están escritos, incluidos los casos de error y los
   bordes.
4. **Trabajá dentro de este repositorio.** Estructurá el código como te parezca mejor;
   commiteá con mensajes descriptivos a medida que avances.
5. Las invariantes globales `INV-1` a `INV-8` deben cumplirse en todo momento; violarlas
   es un defecto aunque ningún escenario individual lo detecte.
