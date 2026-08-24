# ADR-017 — Las credenciales del harness A se inyectan por entorno, no por bind-mount

- **Estado:** **Aceptado** (ratificado por el tesista el 2026-08-23)
- **Fecha:** 2026-08-23
- **Contexto:** ventana H6, corrida piloto sin ejecutar. Sale de la primera prueba real
  de un CLI dentro del contenedor de [ADR-015](ADR-015-agentes-en-contenedores.md).
- **Reemplaza a:** de ADR-015 **Decisión 3**, la parte que fija bind-mount read-only de
  `~/.claude/.credentials.json` para el harness A. El mecanismo del lado B —bind-mount de
  `~/.codex/auth.json` con `CODEX_HOME` apuntado al montaje— **se conserva sin cambios**,
  igual que el resto de ADR-015. ADR-015 no se edita.

## Contexto

ADR-015 D3 asumió que el archivo de credenciales de cada CLI es la credencial viva. Del
lado B es cierto. Del lado A, en macOS, no.

Medido el 2026-08-23, en la primera invocación real de `claude -p` dentro del contenedor:

- El CLI responde **`Not logged in · Please run /login`**.
- `~/.claude/.credentials.json` existe y tiene la forma esperada
  (`claudeAiOauth.accessToken` / `refreshToken` / `expiresAt`), pero su `expiresAt` es
  **2026-06-23**: vencido hacía dos meses.
- La credencial vigente vive en el **Keychain** del sistema
  (`security find-generic-password -s "Claude Code-credentials"`), con `expiresAt`
  posterior a la fecha de la medición.
- `~/.codex/auth.json`, en cambio, es un archivo real y vigente (`auth_mode` más tokens
  OAuth), que es por qué el mecanismo de ADR-015 D3 sí sirve del lado B.

O sea: una **asimetría de plataforma**, no de diseño. En macOS el CLI de A guarda su
sesión en un almacén que un contenedor no puede leer.

## Decisión

### 1. A se autentica por variable de entorno

`CLAUDE_CODE_OAUTH_TOKEN`, un token de larga duración ligado a la suscripción que genera
`claude setup-token` (documentado por el propio binario 2.1.241 como *"Set up a
long-lived authentication token (requires Claude subscription)"*). Es el mecanismo
pensado para uso headless: no depende del Keychain ni de un archivo de sesión, que es
justamente lo que falla adentro del contenedor. **Se conserva el modo suscripción** de
ADR-009, que era el motivo 1 del pasaje a los CLI.

### 2. Un único archivo de credenciales, con plantilla versionada

`pipeline/contenedores/.env`, pasado con `--env-file` **en las 4 celdas y las dos
familias**, aunque hoy sólo A lo necesite: un `--env-file` por familia sería una
asimetría de invocación, y el archivo es el mismo para todas.

Se versiona la **plantilla** `.env.example` —el formato, sin valores— y el `.env` real va
al `.gitignore`. Los tokens son secretos de la cuenta del tesista y **no son dato del
experimento**; lo que sí entra al manifest es el **modo de auth** (suscripción | API
key), nunca el token.

### 3. B no cambia

Sigue con el bind-mount read-only de `auth.json` de ADR-015 D3. No se lo migra a variable
de entorno por simetría cosmética: su archivo funciona, y cambiarlo agregaría un
mecanismo sin resolver ningún problema.

## Consecuencias

- **La asimetría de mecanismo de auth se declara.** A por entorno, B por bind-mount. No
  cruza al otro factor —ninguna celda ve un modelo distinto por esto— y queda dentro del
  factor «pipeline», como las demás asimetrías que ADR-009 D1 enumera. Va a
  `analisis/amenazas-validez.md`.
- **`verificar_paridad.py` sube a 117 chequeos:** el invariante de montajes cambia (la
  única diferencia admisible pasa a ser el `auth.json` de B) y se agrega que las 4 celdas
  apunten al mismo `--env-file`.
- **El riesgo de exposición baja respecto de ADR-015 D3.** El token del contenedor es uno
  emitido para esto y revocable por separado, en vez de la credencial de sesión del
  tesista.
- **`ANTHROPIC_API_KEY` y `OPENAI_API_KEY` quedan en la plantilla, vacías**, para el caso
  de que la piloto decida API key en vez de suscripción (checklist H6, ítem 7). Con las
  dos variables cargadas del lado A, cuál gana **no está verificado**: la plantilla manda
  dejar una vacía, porque esa precedencia sería una diferencia no controlada.
- **Queda por verificar en la piloto:** que el token de `setup-token` sobreviva una
  corrida completa sin refresco. Si expira a mitad de etapa, se maneja por la regla de
  continuación de etapa (protocolo §5.8) como cualquier corte, y se registra.

## Alternativas consideradas

- **Exportar el Keychain a un archivo temporal por corrida** y montarlo, conservando el
  mecanismo de ADR-015 D3. Rechazada: mueve la credencial de sesión completa del tesista
  —incluido el `refreshToken`— a un archivo del filesystem por cada corrida, cuando el
  producto ya ofrece un token acotado y revocable para este uso exacto.
- **`claude login` dentro del contenedor**, con un volumen de sesión por celda.
  Rechazada: suma un paso manual interactivo por celda y un volumen que declarar en el
  manifest, y el login escribiría en el mismo almacén que acá no se puede leer.
- **Migrar también B a variable de entorno**, por simetría. Rechazada: ver Decisión 3.
