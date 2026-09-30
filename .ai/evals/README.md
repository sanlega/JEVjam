# Evaluaciones (juez de la automejora)

**Invariante**: estos archivos solo cambian con aprobación humana y nunca en la misma
iteración que un cambio que evalúan (ver skill `self-improve`). El guardián pide
confirmación al editarlos.

| Archivo | Qué mide | Comando |
|---|---|---|
| `routing.jsonl` | ¿Se elige la skill correcta para cada petición? | `.ai/bin/mh eval routing` |
| `cases/*.json` | ¿El agente sigue el procedimiento de la skill? | `.ai/bin/mh eval run --agent 'claude -p' --judge jev` |
| `holdout/` | Confirmación final; **no leer** al diseñar cambios | `.ai/bin/mh eval routing --cases .ai/evals/holdout/routing.jsonl` |
| `results/` | Histórico de puntuaciones (evidencia) | `.ai/bin/mh eval report` |

Añade casos propios de tu proyecto (tareas reales que hayan salido mal) en `cases/`:
son la señal más valiosa. Los casos de comportamiento ejecutan un agente real que
puede modificar archivos: lánzalos en una sesión aislada (`mh session new eval`).
