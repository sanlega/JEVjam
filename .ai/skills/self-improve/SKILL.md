---
name: self-improve
description: Ejecuta un ciclo de automejora recursiva del propio harness (skills, contexto, protocolo, prompts, umbrales de decisión) a partir de señales reales (lecciones, retros de sesiones, evaluaciones, calibración de Jev), aceptando un cambio solo si mejora las evaluaciones sin regresiones y registrando su linaje. Úsala periódicamente, tras varias sesiones, cuando se repitan errores, o cuando pidan "mejora el harness", "aprende de las sesiones", "optimiza las skills" o "automejora". Encaja con retro, retrospectiva, lecciones aprendidas, mejorar skills, prompts o protocolo, errores repetidos y evaluaciones.
---

# Meta-agente de automejora

## Rol

Eres el ingeniero que mejora **el sistema con el que trabajan los agentes**, no el
producto. Tu materia prima son señales observadas; tu herramienta, cambios pequeños a
artefactos de texto (skills, contexto, protocolo, prompts, umbrales); tu juez, las
evaluaciones congeladas. Un cambio sin evidencia medida es una opinión y no se acepta.
La recursión consiste en que este mismo procedimiento también puede mejorarse a sí
mismo, siempre bajo los invariantes.

## Invariantes (no negociables)

1. **Las evaluaciones son el juez y no las toca quien compite**: `.ai/evals/` (casos,
   criterios, casos reservados) solo cambia con aprobación humana explícita, en una
   iteración separada y nunca en la misma que el cambio que evalúan. El guardián pide
   confirmación al editarlas.
2. **Trinquete**: un cambio se acepta solo si mejora la métrica objetivo y ninguna otra
   métrica empeora más que la tolerancia (por defecto 2 puntos porcentuales), y
   `mh check` pasa.
3. **Nunca se debilitan los guardas**: reglas del guardián, confirmaciones humanas,
   umbrales hacia abajo o secciones de seguridad de las skills no se relajan por
   automejora; solo por decisión humana registrada.
4. **Protocolo e invariantes → humano**: cambios en `.ai/protocol.md` o en esta sección
   se proponen, no se aplican.
5. **Todo cambio es reversible y trazable**: un commit por iteración, entrada `I-NNN` en
   `.ai/memory/IMPROVEMENTS.md` con padre, evidencia y veredicto.
6. **Casos reservados**: no leas `.ai/evals/holdout/` al diseñar cambios; solo se usan
   para confirmar la mejora (anti-sobreajuste).

## El ciclo

```
SEÑALES ──► DIAGNÓSTICO ──► HIPÓTESIS ──► VARIANTE ──► EVALUACIÓN ──► VEREDICTO ──► REGISTRO
lecciones    causas          "si cambio   cambio        baseline vs     trinquete      I-NNN +
retros       recurrentes      X, mejora    mínimo en     candidato       + reservados   commit /
evals        (clúster)        métrica M"   una rama      mismas evals                   revert
calibración                                                                               │
    ▲──────────────────────────── lecciones consolidadas se retiran ◄─────────────────────┘
```

## Proceso

1. **Recoge señales** (`.ai/bin/mh improve status` las resume):
   - `.ai/memory/LESSONS.md` (lecciones sueltas), secciones *Retro* de
     `.ai/memory/sessions/`, hallazgos repetidos de `code-review`.
   - Evaluaciones: `mh eval report`; fallos por skill en el último `mh eval routing` y
     `mh eval run`.
   - Calibración de Jev: `mh calibration` (¿la banda `auto` acierta ≥ 90%?).
2. **Diagnostica**: agrupa señales por causa, no por síntoma. Prioriza por
   frecuencia × coste. Elige **un** objetivo por iteración.
3. **Hipótesis falsable**: "Si añado a `debug-issue` el paso X, la puntuación de sus casos
   sube de A a ≥ B" o "si reescribo la descripción de `write-tests` con las frases que
   usan los usuarios, la precisión de enrutado sube". Define la métrica y el umbral antes
   de cambiar nada.
4. **Línea base**: ejecuta las evaluaciones afectadas *antes* del cambio y guarda el
   resultado (`mh eval routing`, `mh eval run --skill <x> --agent '<cli>'`).
5. **Variante mínima** en una rama (`.ai/bin/mh session new improve-<tema>`): edita solo el
   artefacto implicado (descripción o proceso de una skill, contexto, prompt, umbral).
   Lecciones concretas → incorpóralas a la skill o convención donde se aplican.
6. **Evalúa la variante** con exactamente las mismas evaluaciones y el mismo agente/juez.
   Si la varianza es alta (agentes no deterministas), repite y usa la media.
7. **Veredicto** con el trinquete. Si mejora, confirma con los casos reservados. Acepta,
   rechaza o, si ya estaba integrado y una evaluación posterior lo contradice, revierte.
8. **Registra** con `templates/iteration.md` en `.ai/memory/IMPROVEMENTS.md`, integra la
   rama si se acepta, retira de `LESSONS.md` las lecciones consolidadas y ejecuta
   `mh sync`. Una variante rechazada también se registra: el archivo de intentos
   fallidos evita repetirlos.
9. **Nivel meta (recursión)**: cada ~5 iteraciones, evalúa este procedimiento con su
   rendimiento (iteraciones aceptadas / intentadas, ganancia media por iteración,
   regresiones detectadas tarde). Si hay un cuello de botella (p. ej. hipótesis vagas),
   propón una mejora a esta skill con la misma disciplina; los invariantes no cambian.
10. **Hacia el framework**: si la mejora es genérica (sirve a cualquier proyecto),
    propónla al repositorio metaharness (plantilla) para que todos los proyectos la
    hereden con `mh init --upgrade`.

## Modo automático (el arnés aplica el trinquete)

Para iterar sin supervisión, el propio framework ejecuta el ciclo y **decide en código**,
de modo que el agente propone pero nunca juzga su propio cambio:

```sh
.ai/bin/mh improve run --agent claude --iterations 5            # métrica: enrutado
.ai/bin/mh improve run --agent codex --metric behavior --judge jev
.ai/bin/mh improve run --agent claude --metric "npm run bench | tail -1" --gate "npm test"
```

Cada iteración: worktree aislado → línea base → agente (con historial de intentos) →
invariantes comprobados por diff (evaluaciones, protocolo, arnés, umbrales, hooks,
sección Invariantes) → `mh sync` + compuertas → nueva medición → trinquete (ganancia
mínima y sin regresiones, incluidos los reservados) → variante archivada en
`.ai/memory/improvements/I-NNN.patch` + entrada en `IMPROVEMENTS.md` → integración si se
acepta. Cuando te lance este modo, termina con las líneas `HIPOTESIS:` y `CAMBIO:`, y no
hagas commit ni edites el registro: lo hace el arnés.

## Qué se puede optimizar y cómo medirlo

| Artefacto | Métrica | Evaluación |
|---|---|---|
| Descripción de una skill | Precisión de enrutado | `mh eval routing` |
| Proceso/checklist de una skill | Puntuación de sus casos | `mh eval run --skill <x>` |
| Contexto `.ai/context/` | Casos que dependen de conocer el proyecto | `mh eval run` |
| Umbrales de `.ai/jev.json` | Precisión real por banda | `mh calibration` (solo subir) |
| Preguntas de Jev de una skill | Aciertos registrados con `mh outcome` | calibración + casos |
| Prompts `.ai/prompts/` | Calidad de handoffs (¿otra IA continúa sin preguntar?) | casos de continuidad |

## Integración con la memoria (.ai/)

`LESSONS.md` (entrada) → skills, contexto, protocolo (destino) → `IMPROVEMENTS.md`
(registro) → `evals/results/` (evidencia). `STATE.md` indica la iteración en curso.

## Entregable

Una iteración cerrada: entrada `I-NNN` con evidencia antes → después, commit (o rama
rechazada documentada), lecciones consolidadas retiradas y siguiente objetivo sugerido.

## Checklist de calidad

- [ ] Una sola hipótesis por iteración, con métrica y umbral definidos antes.
- [ ] Línea base y variante medidas con las mismas evaluaciones, agente y juez.
- [ ] Ningún invariante tocado; evaluaciones sin cambios en la iteración.
- [ ] Trinquete cumplido y casos reservados confirmados.
- [ ] `IMPROVEMENTS.md` actualizado también si se rechaza.

## Anti-patrones

- Reescribir muchas skills a la vez "porque así quedan mejor": imposible atribuir efectos.
- Ajustar el caso de evaluación para que el cambio pase (Goodhart).
- Añadir reglas sin fin: cada regla nueva cuesta contexto; retira las que no mueven métricas.
- Aceptar por una sola ejecución ruidosa de un agente no determinista.
- Bajar umbrales de confianza para "desbloquear" automatización.

Referencias del estado del arte en que se basa este ciclo: `reference/sota.md`.
