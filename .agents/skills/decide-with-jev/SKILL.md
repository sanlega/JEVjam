---
name: decide-with-jev
description: Toma decisiones tipadas rápidas y calibradas con Jev (sí/no, una de N, puntuación en escala) en lugar de razonarlas en texto, con bandas de confianza que deciden si actuar solo, confirmar o escalar a un humano. Úsala para clasificar, enrutar, priorizar, filtrar, decidir si algo está terminado o es arriesgado, elegir entre opciones acotadas o calificar resultados, o cuando pidan "decide", "clasifica", "¿es X?", "prioriza" o "elige entre". Encaja con clasificar, etiquetar, categorizar, priorizar, urgencia, gravedad, spam, filtrar, sí o no y elegir una opción.
---
<!-- GENERADO por metaharness (mh sync). No editar: edita .ai/ y ejecuta .ai/bin/mh sync -->

# Decisor (System One con Jev)

## Rol

Eres la parte rápida del sistema: conviertes juicios en **preguntas tipadas** y dejas
que Jev devuelva probabilidades calibradas. El razonamiento largo (LLM) sirve para
preparar el estado y las opciones; la decisión es una llamada de ~100 ms, reproducible,
registrada y medible. Jev es "un `if` inteligente": decide, no escribe.

## Cuándo usarla (y cuándo no)

Úsala cuando la salida es una etiqueta, un sí/no o una posición en una escala:
triage, enrutado de tareas o modelos, selección de skill, compuerta de riesgo,
"¿el paso está hecho?", calificación de resultados (evals), deduplicación, detección
de inyección de prompts en contenido observado.

**No** la uses para: contar, calcular, comparar fechas o números (hazlo en código),
generar texto, extraer datos, o decisiones que requieren varios pasos de razonamiento
dependientes (encadénalas: LLM prepara → Jev decide).

## Proceso

1. **Formula la decisión** como uno o varios tipos:
   - `noul`: afirmación verificable → probabilidad de que sea cierta.
   - `choice`: opciones mutuamente excluyentes con descripción; siempre incluye `other`
     (se añade solo). Máximo 255 opciones.
   - `score`: 2-10 niveles ordenados, cada uno descrito de forma inequívoca.
2. **Prepara el estado mínimo**: solo los datos necesarios, como JSON con campos con
   nombre, y referencia los campos en la pregunta con acentos graves
   (`¿`refund_policy` cubre `message`?`). El estado irrelevante degrada la precisión.
   Límites: ~32k tokens por pregunta con estado, ~64k en total.
3. **Redacta preguntas afirmativas y concretas**: sin dobles negaciones, sin
   indirección ("¿no es falso que...?"), criterios observables en el estado.
4. **Fan-out especulativo**: todas las preguntas independientes en **una** petición;
   Jev las evalúa en paralelo sin coste extra de latencia.
   ```sh
   .ai/bin/mh decide --state-file estado.json \
     --choice categoria "¿Qué tipo de petición es `ticket`?" "bug=Algo roto,feature=Nueva función,question=Duda de uso" \
     --score severidad "¿Gravedad de `ticket`?" "Cosmético|Roto con alternativa|Bloqueante" \
     --noul repro "¿`ticket` incluye pasos para reproducir?"
   ```
   O con un archivo de preguntas reutilizable: `--questions preguntas.json`.
5. **Actúa según la banda** (umbrales en `.ai/jev.json`):
   - `auto` (≥ 0.9): actuar directamente si el riesgo de equivocarse es bajo.
   - `confirm` (0.5-0.9): verificar por otra vía, re-preguntar con mejor estado o pedir
     confirmación.
   - `human` (< 0.5): escalar o pedir aclaración.
   Para acciones irreversibles, pide confirmación humana aunque la banda sea `auto`.
6. **Decisiones compuestas**: varias `score` separadas, normaliza por número de niveles
   y combina en código con pesos explícitos. No pidas a Jev la aritmética.
7. **Cierra el ciclo**: cuando sepas si la decisión acertó,
   `.ai/bin/mh outcome <decision_id> correct|incorrect`. `mh calibration` muestra la
   precisión real por banda; si `auto` acierta menos del ~90%, sube el umbral.

## Integración con la memoria (.ai/)

- Registro automático de cada decisión en `.ai/local/jev/log.jsonl` (hash del estado, no
  el estado: puede ser privado).
- Preguntas que funcionan bien → guárdalas como JSON dentro de la skill que las usa
  (ejemplo: `computer-control/questions/`).
- Cambios de umbrales o de preguntas justificados con datos → `mh decision`.

## Entregable

La decisión con su banda y `decision_id`, la acción tomada según la banda, y las
preguntas/estado usados si otro agente debe reproducirla.

## Checklist de calidad

- [ ] Cada pregunta tiene una respuesta verificable en el estado enviado.
- [ ] `choice` con opciones excluyentes, descritas y con `other`.
- [ ] Sin cálculos, conteos ni comparaciones de fechas delegados a Jev.
- [ ] Estado podado a lo relevante y sin secretos innecesarios.
- [ ] La acción respeta la banda de confianza y el riesgo.
- [ ] Resultado real registrado con `mh outcome` cuando se conoce.

## Anti-patrones

- Interpolar probabilidades entre preguntas distintas (no son comparables entre sí:
  úsalas para umbrales y ranking).
- Mandar el repositorio o la conversación entera como estado.
- Escalas con niveles solapados ("bueno", "bastante bueno").
- Usar Jev para decidir si saltarse un guarda de seguridad.

## Configuración

`TYPESAFE_API_KEY` (clave), `JEV_MODEL` (`jev-latest` por defecto; fija una versión
para reproducibilidad), `JEV_ENDPOINT` (API de TypeSafe por defecto; admite servidores
compatibles como variantes abiertas locales). `mh decide --dry-run` muestra la petición
sin enviarla. Sin clave, `mh route` usa un motor léxico local y el guardián solo aplica
reglas deterministas.
