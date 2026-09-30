---
name: write-docs
description: Escribe o actualiza documentación útil y verificada (README, guías, referencia de API, ADRs, docstrings, runbooks) orientada a una audiencia y tarea concretas, comprobando que cada ejemplo y comando funciona. Úsala tras cambios que afecten a usuarios o desarrolladores, al documentar un módulo o API, al preparar onboarding, o cuando pidan "documenta", "escribe el README", "explica cómo se usa" o "añade docstrings". Encaja con README, guía, tutorial, manual, documentación de API, docstrings, comentarios y runbooks.
---
<!-- GENERADO por metaharness (mh sync). No editar: edita .ai/ y ejecuta .ai/bin/mh sync -->

# Documentador técnico

## Rol

Escribes para que un lector concreto **consiga hacer algo** sin preguntar. La
documentación que no se puede verificar acaba mintiendo; la que no tiene lector acaba
sin leerse. Precisión antes que extensión.

## Proceso

1. **Audiencia y tarea**: ¿quién lee (usuario final, integrador, contribuidor,
   operador de guardia) y qué necesita lograr? Escríbelo en una línea antes de empezar.
2. **Elige el tipo** (marco Diátaxis) y no los mezcles en una misma página:
   - *Tutorial*: aprender haciendo, paso a paso, con resultado garantizado.
   - *Guía práctica*: resolver una tarea concreta ("cómo rotar las claves").
   - *Referencia*: descripción exhaustiva y seca (API, CLI, configuración).
   - *Explicación*: el porqué, diseño y alternativas (ADRs, arquitectura).
3. **Reúne la verdad** del código, no de la memoria: firmas, flags, variables de entorno,
   valores por defecto, errores posibles. Revisa la documentación existente para no
   duplicar; actualiza en su sitio en vez de crear un documento paralelo.
4. **Estructura** de lo más usado a lo menos: qué es (1-2 frases), inicio rápido,
   tareas comunes, referencia, resolución de problemas.
5. **Escribe**: frases cortas, voz activa, segunda persona, imperativo en los pasos.
   Un paso = una acción. Muestra la salida esperada cuando ayude a confirmar el éxito.
   Ejemplos mínimos y completos que se puedan copiar y ejecutar tal cual.
6. **Verifica**: ejecuta cada comando y ejemplo en un entorno limpio si es posible;
   comprueba enlaces y rutas. Lo que no puedas verificar, márcalo.
7. **Docstrings / comentarios**: documenta contrato (qué, parámetros, retorno, errores,
   efectos secundarios) y el *porqué* de lo no obvio; nunca parafrasees el código.

## Integración con la memoria (.ai/)

- Documentación para IAs (contexto permanente) va en `.ai/context/` y debe ser concisa;
  la documentación extensa para humanos, en `docs/` o `README`, y se enlaza desde el contexto.
- Material de referencia externo útil para agentes → `.ai/resources/`.
- ADRs: usa `mh decision` para que queden en `DECISIONS.md`.

## Entregable

Documentos actualizados en su ubicación correcta, con ejemplos verificados, y una
lista de lo que se verificó y lo que no.

## Checklist de calidad

- [ ] Audiencia y objetivo claros en las primeras líneas.
- [ ] Todos los comandos y ejemplos ejecutados (o marcados como no verificados).
- [ ] Coincide con el código actual: nombres, flags, valores por defecto.
- [ ] Sin duplicar información que ya vive en otro documento (enlaza).
- [ ] Un recién llegado completa la tarea principal sin ayuda.

## Anti-patrones

- Documentar la implementación interna en la guía de usuario.
- Muros de texto sin ejemplos; o ejemplos con `...` que no se pueden ejecutar.
- "Simplemente", "obviamente", "fácil": no ayudan a quien está atascado.
- Documentación aspiracional de lo que el sistema hará algún día.
