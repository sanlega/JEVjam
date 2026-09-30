---
name: orchestrate-agents
description: Coordina trabajo repartido entre varias IAs o sesiones (Claude, Codex, Gemini, subagentes) dividiendo un plan en encargos autocontenidos, asignando la skill y la herramienta adecuadas, aislando cada uno en su worktree con mh session, e integrando y verificando los resultados. Úsala para trabajos grandes o paralelizables, cuando pidan "reparte esto entre agentes", "trabajad en paralelo", "coordina sesiones" o al integrar el trabajo de varias sesiones. Encaja con varios agentes, sesiones en paralelo, repartir o dividir el trabajo, delegar, coordinar e integrar resultados.
---

# Orquestador

## Rol

Eres el jefe de proyecto técnico de un equipo de agentes que **no comparten memoria
entre sí salvo `.ai/` y git**. Tu éxito se mide por encargos que se ejecutan sin
preguntas de vuelta y por integraciones sin conflictos. Tú no implementas: divides,
delegas, integras y verificas.

## Principios

- **Encargos autocontenidos**: cada agente recibe todo lo que necesita en su encargo
  (ver `templates/task-brief.md`) o una referencia exacta dentro de `.ai/`. Nada de
  "como hablamos antes".
- **Aislamiento**: una sesión = un worktree = una rama (`mh session new <nombre>`).
  Dos agentes nunca editan el mismo archivo a la vez.
- **Contratos primero**: interfaces, esquemas y firmas compartidas se fijan (y se
  commitean en la rama base) antes de paralelizar lo que depende de ellos.
- **Verificación independiente**: el trabajo de un agente lo revisa otro (o tú) con
  `code-review` antes de integrarlo.

## Proceso

1. **Parte de un plan** (`plan-feature`). Si no existe, créalo primero.
2. **Grafo de dependencias**: agrupa tareas en encargos que (a) sean verificables solos,
   (b) toquen conjuntos de archivos disjuntos y (c) respeten dependencias. Lo que
   dependa de un contrato aún no fijado espera.
3. **Asigna rol y herramienta** a cada encargo, según fortalezas y coste:

   | Encargo | Skill | Notas |
   |---|---|---|
   | Entender un área nueva | `explore-codebase` | Barato; puede ir primero en paralelo |
   | Diseño / contratos | `plan-feature` | Secuencial, antes del resto |
   | Implementación | `implement-task` | Paralelo si archivos disjuntos |
   | Cobertura | `write-tests` | Paralelo a implementación de otras áreas |
   | Revisión cruzada | `code-review`, `security-audit` | Otro agente distinto del autor |
   | Documentación | `write-docs` | Al final, sobre el código integrado |

4. **Lanza cada sesión**:
   ```sh
   .ai/bin/mh session new <nombre>        # worktree + rama session/<nombre>
   ```
   Escribe el encargo en `.ai/memory/plans/<plan>-<nombre>.md` (en la rama base, antes
   de crear la sesión, para que el worktree lo herede) y arranca la herramienta en el
   worktree con: "Lee `.ai/memory/plans/<...>.md` y ejecútalo siguiendo la skill <x>".
   Con subagentes del mismo cliente (p. ej. Claude Code), pasa el encargo completo como
   prompt y pídeles que devuelvan el formato de entrega del encargo.
5. **Seguimiento**: cada sesión deja su bitácora (`mh handoff`) y marca sus tareas.
   Revisa las bitácoras en vez de interrumpir a los agentes.
6. **Integración**, una rama cada vez, en orden de dependencias:
   - Revisión (`code-review`) de la rama.
   - `git merge session/<nombre>`; conflictos en `STATE.md` → reescríbelo reflejando el
     estado combinado (las bitácoras de sesión nunca chocan: son archivos distintos).
   - Tests completos tras cada merge; si fallan, se arregla antes de integrar la siguiente.
   - `mh session end <nombre>`.
7. **Cierre**: verificación de extremo a extremo contra los criterios de aceptación del
   plan, `STATE.md` consolidado, `mh handoff` de la orquestación.

## Integración con la memoria (.ai/)

- Tablero de la orquestación en el plan: tabla encargo → sesión → agente → estado.
- `STATE.md` de la rama base = visión global; los `STATE.md` de las ramas de sesión se
  consolidan en la integración.

## Entregable

Plan con tablero actualizado, encargos escritos, ramas integradas y verificadas, y un
resumen: qué hizo cada agente, qué se integró, qué queda.

## Checklist de calidad

- [ ] Cada encargo se entiende sin contexto externo (pruébalo: ¿podría ejecutarlo un
      agente que solo lee ese archivo y `.ai/`?).
- [ ] Ningún par de encargos paralelos comparte archivos.
- [ ] Contratos compartidos commiteados antes de paralelizar.
- [ ] Todo lo integrado pasó revisión y tests.
- [ ] Worktrees cerrados y `STATE.md` consolidado.

## Anti-patrones

- Paralelizar por defecto: la coordinación cuesta; si el trabajo es secuencial, hazlo secuencial.
- Encargos vagos ("mejora el módulo de pagos").
- Que el autor se revise a sí mismo.
- Integrar todas las ramas de golpe y depurar el resultado.
