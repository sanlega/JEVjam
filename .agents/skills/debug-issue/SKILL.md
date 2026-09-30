---
name: debug-issue
description: Diagnostica y corrige bugs de forma sistemática (reproducir, aislar, formular hipótesis, verificar la causa raíz, arreglar con test de regresión) en lugar de probar cambios a ciegas. Úsala ante errores, excepciones, tests que fallan, CI en rojo, comportamiento inesperado o regresiones, o cuando pidan "no funciona", "arregla este error", "por qué falla" o "investiga este bug". Encaja con excepción, stack trace, error 500, crash, se cae, falla, regresión, comportamiento raro o causa del fallo.
---
<!-- GENERADO por metaharness (mh sync). No editar: edita .ai/ y ejecuta .ai/bin/mh sync -->

# Depurador

## Rol

Eres un investigador. Tu entregable no es "un cambio que hace desaparecer el síntoma",
sino **la causa raíz demostrada, el arreglo mínimo y un test que impide que vuelva**.
Nunca llames "flaky" a algo sin haberlo demostrado.

## Proceso

1. **Recoge los hechos**: mensaje de error completo, stack trace, logs, entrada exacta,
   entorno (versión, SO, configuración), desde cuándo ocurre y qué cambió (`git log`).
   Revisa `.ai/memory/sessions/` por si alguien ya lo investigó.
2. **Reproduce** de forma fiable y con el ciclo más corto posible: idealmente un test
   que falla o un comando de una línea. Si no se reproduce, el primer trabajo es
   conseguirlo (misma versión, datos, variables de entorno, concurrencia).
3. **Aísla**: reduce el caso al mínimo. Técnicas: búsqueda binaria en el código
   (comentar mitades), en el historial (`git bisect run <test>`), en los datos
   (recortar la entrada), en la configuración.
4. **Formula hipótesis explícitas** y ordénalas por probabilidad × facilidad de comprobar.
   Para cada una, define qué observación la confirmaría o descartaría **antes** de mirar.
5. **Experimenta, un cambio cada vez**: logs dirigidos, depurador, aserciones. Anota
   resultado de cada experimento. Si una hipótesis cae, descártala de verdad.
6. **Demuestra la causa raíz**: debes poder explicar la cadena completa desde la causa
   hasta el síntoma, y predecir qué pasa si la tocas. "Parece que" no es una causa raíz.
   Pregúntate "¿por qué?" hasta llegar a algo accionable (5 porqués).
7. **Test de regresión** que falla con el bug (ver `write-tests`).
8. **Arreglo mínimo en el lugar correcto** (la causa, no el síntoma). Busca el mismo
   patrón defectuoso en otros sitios del código (`grep`).
9. **Verifica**: el test de regresión pasa, la suite completa pasa, el caso original
   del usuario funciona. Retira la instrumentación temporal.

## Integración con la memoria (.ai/)

- Si la investigación ocupa más de una sesión, deja un diario en la bitácora de sesión:
  hipótesis probadas, resultados, siguiente experimento. Es lo que más tiempo ahorra a
  quien continúe.
- Si el bug revela una trampa del sistema (orden de inicialización, variable de entorno
  obligatoria...), añádela a `.ai/context/20-conventions.md` y `mh sync`.

## Entregable

1. Causa raíz en 2-4 frases (qué, por qué, desde cuándo).
2. Arreglo + test de regresión en un commit.
3. Evidencia: comando reproductor fallando antes y pasando después.
4. Otros lugares afectados o riesgos relacionados.

## Checklist de calidad

- [ ] Reproducido antes de cambiar código.
- [ ] Causa raíz explicada de extremo a extremo, no solo el síntoma.
- [ ] Hay test que fallaba y ahora pasa.
- [ ] Arreglo mínimo; sin cambios oportunistas mezclados.
- [ ] Se buscó el mismo defecto en otras partes.
- [ ] Instrumentación temporal eliminada.

## Anti-patrones

- Cambiar cosas al azar hasta que el error desaparece.
- Añadir reintentos, sleeps o try/catch para tapar el síntoma.
- Actualizar el valor esperado del test para que coincida con el bug.
- Varias modificaciones a la vez: ya no sabes cuál arregló (o rompió) qué.
- Dar por hecho que es un problema del entorno o de una dependencia sin pruebas.
