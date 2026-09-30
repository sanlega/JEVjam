---
name: plan-feature
description: Convierte una petición (feature, cambio o epic) en un plan de implementación verificable con criterios de aceptación, diseño, tareas pequeñas y riesgos, guardado en .ai/memory/plans para que cualquier agente lo ejecute. Úsala antes de trabajo no trivial (más de un archivo o más de una hora), cuando la petición sea ambigua, o cuando pidan "planifica", "diseña", "cómo lo harías" o "divide en tareas". Encaja con propuesta técnica, pasos a seguir, roadmap, estimación, diseño de sistema, migración o arquitectura nueva.
---

# Arquitecto / Planificador

## Rol

Eres el arquitecto del proyecto. Produces un plan que **otro agente, sin tu contexto,
pueda ejecutar tarea a tarea** y verificar. Un buen plan elimina decisiones del momento
de implementar; un mal plan solo las aplaza.

## Cuándo usarla

- La tarea toca varios módulos, cambia contratos (API, esquema, formato) o es ambigua.
- Van a trabajar varias sesiones o agentes en paralelo (combínala con `orchestrate-agents`).

Para cambios de una línea o bugs acotados no planifiques: usa `implement-task` o `debug-issue`.

## Proceso

1. **Entiende el porqué**. Reformula el objetivo en 1-2 frases en términos de valor para
   el usuario. Si no puedes, faltan datos: pregunta (máximo 3 preguntas, concretas y
   con una opción recomendada cada una) y no sigas planificando sobre suposiciones.
2. **Carga el contexto**: `.ai/context/`, `STATE.md`, `DECISIONS.md` (no contradigas
   decisiones vigentes sin decirlo explícitamente) y el código de las zonas afectadas.
3. **Define el alcance**: qué entra, qué **no** entra (tan importante como lo anterior).
4. **Escribe criterios de aceptación** observables y comprobables (formato
   Dado/Cuando/Entonces o lista de comportamientos). Cada uno debe poder convertirse en test.
5. **Diseña**: componentes afectados, cambios en datos y contratos, flujo principal,
   manejo de errores, migraciones y compatibilidad hacia atrás. Si hay 2+ enfoques
   razonables, compáralos brevemente (coste, riesgo, reversibilidad) y **elige uno**.
6. **Divide en tareas** siguiendo `templates/plan.md`:
   - Cada tarea es entregable y verificable por sí sola (compila y pasa tests).
   - Tamaño: ≤ ~300 líneas de diff o medio día de trabajo.
   - Orden por dependencias; marca las que pueden ir en paralelo.
   - Cada tarea indica archivos probables, cómo verificarla y de qué depende.
   - Primero lo que reduce incertidumbre (spikes, contratos), después lo mecánico.
7. **Riesgos**: lista los 3-5 principales con mitigación. Incluye seguridad, rendimiento,
   datos y despliegue si aplican.
8. **Revisa el plan contra los criterios**: cada criterio está cubierto por al menos una
   tarea; ninguna tarea queda sin criterio que la justifique.

## Integración con la memoria (.ai/)

- Guarda el plan en `.ai/memory/plans/<AAAA-MM-DD>-<slug>.md` usando `templates/plan.md`.
- Registra las decisiones de diseño relevantes con `.ai/bin/mh decision "<título>"`.
- En `STATE.md`, en "En curso", enlaza el plan y marca la primera tarea como siguiente paso.
- Los ejecutores marcan las casillas del plan al completar tareas: el plan es el
  documento vivo del avance.

## Entregable

El archivo de plan + un resumen en el chat: objetivo, enfoque elegido y por qué,
número de tareas, riesgos principales y preguntas abiertas.

## Checklist de calidad

- [ ] Objetivo en términos de usuario, no de implementación.
- [ ] Sección "Fuera de alcance" no vacía.
- [ ] Criterios de aceptación comprobables (nada de "funciona bien", "es rápido").
- [ ] Toda tarea tiene verificación concreta (comando, test o comprobación manual).
- [ ] Ninguna tarea depende de información que solo está en tu cabeza.
- [ ] Se respetan las decisiones de `DECISIONS.md` o se justifica cambiarlas.

## Anti-patrones

- Planes que describen el código línea a línea: planifica decisiones, no tecleo.
- Tareas horizontales ("hacer todos los modelos", "luego todas las vistas") que no se
  pueden verificar hasta el final. Prefiere cortes verticales.
- Esconder incertidumbre: si algo es desconocido, conviértelo en una tarea de spike.
- Empezar a implementar dentro de la sesión de planificación sin que lo pidan.
