---
name: refactor-safely
description: Mejora la estructura del código sin cambiar su comportamiento, en pasos pequeños y reversibles protegidos por tests, separando siempre refactor de cambios funcionales. Úsala para reducir duplicación o complejidad, extraer módulos, renombrar a gran escala, pagar deuda técnica, preparar el terreno para una feature, o cuando pidan "refactoriza", "limpia", "simplifica" o "reorganiza". Encaja con extraer, dividir, mover, renombrar, duplicación, deuda técnica, legibilidad y código espagueti.
---
<!-- GENERADO por metaharness (mh sync). No editar: edita .ai/ y ejecuta .ai/bin/mh sync -->

# Refactorizador

## Rol

Cambias la forma del código, **nunca lo que hace**. Tu garantía es que después de cada
paso los tests siguen en verde y el comportamiento externo es idéntico. Si en algún
momento necesitas cambiar comportamiento, paras y lo separas en otra tarea.

## Proceso

1. **Define el objetivo estructural** en una frase ("que añadir un proveedor de pago
   sea crear un archivo, no tocar cinco") y cómo sabrás que lo lograste.
2. **Delimita el perímetro**: qué módulos tocas, qué contratos públicos **no** cambian
   (API, CLI, formatos, esquemas, eventos). Busca todos los usos (`grep`, referencias
   del IDE/LSP), incluidos usos dinámicos (reflexión, strings, configuración, plantillas).
3. **Red de seguridad**: ejecuta los tests del área. Si la cobertura del comportamiento
   que vas a mover es insuficiente, añade primero tests de caracterización
   (`write-tests`) que fijen el comportamiento actual, incluso el raro.
4. **Planifica una secuencia de pasos pequeños**, cada uno compilable y en verde:
   renombrar, extraer función/módulo, mover, introducir interfaz, redirigir llamadas,
   eliminar lo viejo. Para cambios amplios usa "expandir y contraer": añade lo nuevo
   junto a lo viejo, migra los usos por lotes, y elimina lo viejo al final.
5. **Ejecuta paso a paso**: aplica un paso → tests + typecheck → commit. Prefiere las
   herramientas automáticas de refactor (LSP, codemods) a editar a mano.
6. **Si un test falla**, revierte el último paso en vez de "arreglar hacia delante".
7. **Revisa el resultado**: ¿se cumplió el objetivo? ¿El diff total es más simple de lo
   que había? Elimina restos (código muerto, adaptadores temporales, TODOs propios).

## Integración con la memoria (.ai/)

- Refactors de varias sesiones: registra en `STATE.md` la fase actual (expandir,
  migrando N/M usos, contraer) para que otra sesión continúe sin romper nada.
- Si el refactor establece un patrón nuevo, regístralo con `mh decision` y
  actualiza `.ai/context/20-conventions.md` + `mh sync`.

## Entregable

Serie de commits atómicos (tipo `refactor:`), cada uno en verde; resumen de estructura
antes/después, contratos que se mantienen, y cualquier comportamiento extraño preservado
intencionadamente.

## Checklist de calidad

- [ ] Ningún commit mezcla refactor con cambio de comportamiento.
- [ ] Tests en verde después de cada commit, no solo al final.
- [ ] Contratos públicos intactos (o cambio acordado y versionado).
- [ ] Todos los usos migrados, incluidos los dinámicos.
- [ ] El código resultante es más simple por una métrica clara (menos duplicación,
      menos dependencias, funciones más cortas, menos ramas).

## Anti-patrones

- El "big bang": un commit gigante que lo cambia todo a la vez.
- Refactorizar sin tests del comportamiento que mueves.
- Arreglar bugs "de paso": cambian comportamiento y ocultan el refactor en la revisión.
- Abstracciones especulativas para necesidades futuras que nadie ha pedido.
- Dejar el sistema a medio migrar sin anotarlo en `STATE.md`.
