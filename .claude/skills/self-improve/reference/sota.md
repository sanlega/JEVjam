# Fundamentos: automejora de agentes

metaharness aplica la automejora sobre el **harness** (instrucciones, skills,
memoria y políticas de decisión), no sobre los pesos del modelo. Es la forma de
automejora más barata, auditable y reversible: todo cambio es un diff de texto en git.

| Idea (literatura) | Qué aporta | Cómo aparece en metaharness |
|---|---|---|
| **Reflexion** (retroalimentación verbal guardada en memoria) | Aprender de errores sin reentrenar | `mh learn` → `LESSONS.md`, secciones *Retro* de los handoffs, lecciones en `mh brief` |
| **Self-Refine** (generar → criticar → refinar) | Mejora iterativa con autocrítica | Checklists de calidad y anti-patrones en cada skill; `code-review` cruzado |
| **Voyager** (biblioteca de habilidades reutilizables) | Acumular procedimientos que funcionan | `.ai/skills/`, `mh skill new`, consolidación de lecciones en skills |
| **Optimización de prompts guiada por evaluaciones** (DSPy, evolución reflexiva de prompts tipo GEPA) | Mejorar instrucciones midiendo en un conjunto de evaluación | Ciclo de `self-improve` con `mh eval` como métrica |
| **Búsqueda de diseños de agentes / meta-agentes** (ADAS) | Un agente que diseña agentes | `self-improve` modifica skills y protocolo del propio harness |
| **Archivo de variantes con validación empírica** (Darwin Gödel Machine) | Conservar linaje e intentos, aceptar solo lo validado | `IMPROVEMENTS.md` con padre/veredicto, ramas `session/improve-*`, trinquete |
| **Optimizador que se mejora a sí mismo** (STOP) | Recursión: mejorar el mejorador | Nivel meta del paso 9, con invariantes congelados |
| **Decisiones calibradas** (RLCD de Jev) | Probabilidades que significan lo que dicen | Bandas auto/confirm/human, `mh outcome` + `mh calibration` |

## Principios de seguridad de la automejora

- **Separación juez/concursante**: quien propone cambios no edita las evaluaciones.
- **Trinquete con tolerancia**: sin regresiones en otras métricas.
- **Casos reservados** contra el sobreajuste a la batería visible.
- **Supervisión humana** en protocolo, invariantes, guardas y evaluaciones.
- **Reversibilidad**: un commit por iteración; revertir es `git revert`.
- **Parsimonia**: el contexto es un recurso escaso; una regla que no mueve métricas se retira.
