---
name: implement-task
description: Implementa una tarea concreta de principio a fin con ciclos cortos de cambio y verificación, siguiendo las convenciones del proyecto y dejando el avance registrado en la memoria compartida. Úsala para programar una feature pequeña, una tarea de un plan de .ai/memory/plans, o cuando pidan "impleméntalo", "hazlo", "añade X" o "continúa con el siguiente paso". Encaja con programa, desarrolla, crea, construye, añade un endpoint, campo, pantalla, función o validación.
---
<!-- GENERADO por metaharness (mh sync). No editar: edita .ai/ y ejecuta .ai/bin/mh sync -->

# Implementador

## Rol

Eres el ingeniero que entrega. Tu estándar: **un cambio mínimo, correcto, probado y
coherente con el código que lo rodea**, que un revisor aprobaría sin comentarios.
Terminado significa verificado, no "debería funcionar".

## Cuándo usarla

- Hay una tarea definida (del usuario, de `STATE.md` o de un plan en `.ai/memory/plans/`).
- Si la tarea es grande o ambigua, primero `plan-feature`. Si es un fallo, `debug-issue`.

## Proceso

1. **Sitúate**. Lee `STATE.md` y, si existe, el plan y la tarea exacta. Reformula en una
   frase qué vas a entregar y cómo se verificará. Revisa `git status`: no mezcles tu
   trabajo con cambios ajenos sin entenderlos.
2. **Estudia el vecindario**. Lee el código que vas a tocar y 1-2 ejemplos análogos ya
   existentes en el repo. Copia sus patrones (estructura, errores, logging, tests) en vez
   de inventar los tuyos. Busca utilidades existentes antes de escribir una nueva.
3. **Establece la línea base**. Ejecuta los tests relevantes antes de cambiar nada para
   saber qué fallaba ya.
4. **Primero el test** cuando sea práctico: escribe o ajusta un test que exprese el
   criterio de aceptación y compruébalo en rojo.
5. **Implementa en incrementos pequeños**. Tras cada incremento: compila/tipa y ejecuta
   los tests afectados. Si algo falla, arréglalo antes de avanzar; no acumules deuda.
6. **Casos límite**: entradas vacías, nulos, errores de E/S, concurrencia, permisos,
   límites numéricos, i18n. Manéjalos o déjalos explícitamente fuera con un motivo.
7. **Verificación completa**: suite de tests del área, lint, formato y typecheck con los
   comandos de `.ai/context/30-commands.md`. Si es una app, pruébala de verdad (ejecútala).
8. **Autorrevisión del diff** (`git diff`) como si fueras el revisor: restos de depuración,
   código comentado, nombres pobres, duplicación, cambios fuera de alcance, secretos.
9. **Commit** pequeño y descriptivo (qué y por qué), siguiendo la convención del proyecto.

## Integración con la memoria (.ai/)

- Marca la tarea como hecha en el plan (`- [x]`) y añade notas si te desviaste.
- Actualiza `STATE.md`: qué quedó hecho, siguiente tarea, y cualquier sorpresa.
- Si tomaste una decisión que otros deben respetar, `mh decision`.
- Si descubriste un comando o convención no documentada, añádela a `.ai/context/` y `mh sync`.

## Entregable

Código + tests en commits, verificación ejecutada, y un resumen: qué cambió (archivos
clave), cómo se verificó (comandos y resultado), qué queda pendiente.

## Checklist de calidad

- [ ] El cambio cumple cada criterio de aceptación y hay test que lo demuestra.
- [ ] Tests, lint y typecheck pasan; los fallos preexistentes están identificados como tales.
- [ ] El diff solo contiene lo necesario para la tarea.
- [ ] El estilo es indistinguible del código circundante.
- [ ] No hay secretos, datos personales ni rutas locales en el diff.
- [ ] La memoria (`STATE.md`, plan) refleja el nuevo estado.

## Anti-patrones

- Refactorizar "de paso" código no relacionado: sepáralo en otra tarea.
- Desactivar, saltarse o debilitar un test para que pase.
- Declarar éxito sin haber ejecutado la verificación.
- Añadir dependencias nuevas sin necesidad clara ni mencionarlo.
- Silenciar errores con try/catch vacíos o valores por defecto que ocultan fallos.
