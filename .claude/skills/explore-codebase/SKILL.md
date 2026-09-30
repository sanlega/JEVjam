---
name: explore-codebase
description: Explora y cartografía un repositorio desconocido o poco documentado y deja un mapa reutilizable en .ai/context para que ninguna sesión futura tenga que repetir la exploración. Úsala al llegar a un proyecto nuevo, cuando el contexto de .ai/ esté vacío o desactualizado, o cuando pidan "entiende este repo", "cómo está organizado", "dónde se hace X" u "onboarding". Encaja con soy nuevo, arquitectura, estructura, mapa del código, qué hace este proyecto, módulos y flujos.
---
<!-- GENERADO por metaharness (mh sync). No editar: edita .ai/ y ejecuta .ai/bin/mh sync -->

# Explorador de código

## Rol

Eres un ingeniero senior que acaba de heredar el proyecto. Tu trabajo no es cambiar
código, sino **construir un modelo mental correcto y ponerlo por escrito** para que
cualquier otra IA o persona pueda trabajar sin repetir tu exploración. Lo que no quede
escrito en `.ai/` se pierde al cerrar la sesión.

## Cuándo usarla

- Primera sesión en un repositorio, o `.ai/context/10-project.md` aún tiene la plantilla.
- El contexto de `.ai/context/` contradice lo que ves en el código.
- Te preguntan dónde vive una funcionalidad y la respuesta no está documentada.

No la uses para una pregunta puntual que se responde con una búsqueda: responde y ya.

## Proceso

1. **Lee lo que ya existe** antes de explorar: `.ai/context/`, `.ai/memory/STATE.md`,
   `README*`, `CONTRIBUTING*`, `docs/`. Anota qué afirman para verificarlo.
2. **Identifica el stack y los puntos de entrada** mirando manifiestos
   (`package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`, `pom.xml`, `Gemfile`,
   `Makefile`, `Dockerfile`, `docker-compose*`, CI en `.github/workflows/`).
   Los scripts de CI son la verdad sobre cómo se instala, testea y despliega.
3. **Recorre la estructura de arriba abajo**: lista directorios de primer y segundo
   nivel; para cada uno, una frase de propósito. Ignora dependencias vendorizadas,
   artefactos de build y generados.
4. **Sigue un flujo real de extremo a extremo** (una petición HTTP, un comando CLI,
   un evento): desde el punto de entrada hasta la persistencia y la respuesta.
   Un flujo trazado vale más que diez directorios descritos.
5. **Localiza los contratos**: modelos de datos, esquemas, APIs públicas, interfaces
   entre módulos, variables de entorno y configuración.
6. **Verifica los comandos**: ejecuta la instalación, los tests y el lint si es seguro
   y barato. Anota qué funciona, cuánto tarda y qué falla.
7. **Detecta convenciones implícitas** leyendo 3-5 archivos representativos: estilo,
   manejo de errores, logging, organización de tests, nombres.
8. **Registra riesgos y rarezas**: código muerto, TODOs relevantes, módulos sin tests,
   dependencias obsoletas, partes frágiles.

## Integración con la memoria (.ai/)

- Actualiza `.ai/context/10-project.md` (propósito, stack, arquitectura, flujo trazado,
  rutas clave), `20-conventions.md` y `30-commands.md` con comandos **verificados**.
- Riesgos y preguntas abiertas → `.ai/memory/STATE.md` (sección bloqueos/preguntas).
- Si el mapa detallado es largo, guárdalo en `.ai/resources/architecture.md` y deja en
  `10-project.md` solo el resumen y el enlace: el contexto se carga en cada sesión.
- Ejecuta `.ai/bin/mh sync` y cierra con el protocolo de handoff.

## Entregable

1. Contexto de `.ai/context/` actualizado y conciso (objetivo: < 150 líneas en total).
2. Un resumen en el chat: qué es, cómo se ejecuta, los 3 archivos más importantes,
   los 3 riesgos principales.

## Checklist de calidad

- [ ] Cada afirmación del contexto se ha comprobado en el código, no inferido del README.
- [ ] Los comandos de `30-commands.md` se han ejecutado o están marcados como no verificados.
- [ ] Hay al menos un flujo trazado de extremo a extremo con rutas de archivo reales.
- [ ] Las rutas citadas existen (`ls`).
- [ ] Otra IA podría implementar un cambio pequeño leyendo solo `.ai/context/`.

## Anti-patrones

- Volcar el árbol de archivos completo en el contexto: ruido que se paga en cada sesión.
- Describir lo que el código "debería" hacer según su nombre sin abrirlo.
- Modificar código durante la exploración.
- Copiar el README sin contrastarlo.
