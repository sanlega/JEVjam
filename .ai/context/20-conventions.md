# Convenciones

<!-- Estilo de código, nombres, estructura de carpetas, idioma de commits, etc. -->
- Commits pequeños y descriptivos.

## TypeSafe / Jev
- Al diseñar o programar cualquier parte con IA (juicios, enrutado, clasificación, ranking, verificación), usa la skill **TypeSafe** (`typesafe-ai`; en Claude Code: plugin `typesafe@typesafe-ai`; otras IAs: `npx skills add typesafe-ai/skills --skill typesafe-ai`).
- Fuente de verdad: la documentación viva en https://docs.typesafe.ai/llms.txt (páginas en `.md`). No inventes detalles de API/SDK dependientes de versión.
- Preguntas estrechas con primitivas tipadas (Choice / Noul / Score); reglas, cálculos y ejecución en código. Credenciales de la API solo en servidor.

## JEVjam
- Nada con plazo depende de la red: Jev decide el compás siguiente; el camino de audio/MIDI es local.
- No hay cerebro local alternativo: las decisiones musicales las toma Jev (decisión del usuario).
  El código solo aporta lo exacto (armonía, tiempos, velocity) y la red de seguridad (mantener la última decisión).
- El estado para Jev va en palabras/categorías, nunca números crudos ni listas largas.
- No pedir a Jev "mantén lo anterior" en las preguntas (se ancla); la continuidad es histéresis en código.
- Los generadores de `band.py` son deterministas por compás (semilla) y se testean sin red.
- Código y comentarios en español; identificadores y preguntas a Jev en inglés.
