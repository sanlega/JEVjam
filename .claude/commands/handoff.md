---
description: Cierra la sesión dejando la memoria lista para la siguiente IA
---
<!-- GENERADO por metaharness (mh sync). No editar: edita .ai/ y ejecuta .ai/bin/mh sync -->
Vamos a cerrar esta sesión. Deja todo listo para que otra IA (u otra sesión) continúe
sin que yo tenga que explicar nada:

1. Actualiza `.ai/memory/STATE.md` (fecha, agente, en curso, próximos pasos
   numerados y concretos, bloqueos).
2. Crea el registro de sesión ejecutando
   `.ai/bin/mh handoff -a <tu-nombre> -t "<resumen de 5-8 palabras>"` y pasando por stdin:
   objetivo de la sesión, cambios hechos (archivos clave), decisiones, pendientes.
3. Si hubo decisiones de arquitectura o convenciones, añádelas con `.ai/bin/mh decision`.
4. Si cambiaste `.ai/context/`, ejecuta `.ai/bin/mh sync`.
5. Haz commit de código + `.ai/` con un mensaje descriptivo.

Notas extra: $ARGUMENTS
