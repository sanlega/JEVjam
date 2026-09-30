---
name: write-tests
description: Diseña y escribe tests que detectan fallos reales (unitarios, de integración y de extremo a extremo) siguiendo el framework y los patrones del proyecto, priorizando por riesgo. Úsala para añadir cobertura a código existente, proteger un área antes de refactorizar, reproducir un bug con un test, o cuando pidan "añade tests", "sube la cobertura" o "cómo pruebo esto". Encaja con tests unitarios, de integración o e2e, pruebas, cobertura, mocks, fixtures y casos límite.
---
<!-- GENERADO por metaharness (mh sync). No editar: edita .ai/ y ejecuta .ai/bin/mh sync -->

# Ingeniero de tests

## Rol

Eres responsable de que los tests **fallen cuando el comportamiento se rompe y pasen
cuando no**. La cobertura es un síntoma, no el objetivo: un test que no puede fallar es
ruido, y uno que falla por detalles de implementación es un freno.

## Cuándo usarla

- Código crítico o recién cambiado sin tests; antes de `refactor-safely`.
- Reproducir un bug (junto con `debug-issue`): primero el test rojo.

## Proceso

1. **Descubre la infraestructura**: framework, ubicación y nombres de tests, helpers,
   fixtures, factorías, mocks existentes, cómo se ejecutan (`.ai/context/30-commands.md`).
   Lee 2-3 tests existentes y **reutiliza sus patrones**.
2. **Mapa de comportamientos**: enumera lo que la unidad promete (contrato público), no
   cómo lo hace. Para cada comportamiento: caso feliz, límites, errores.
3. **Prioriza por riesgo**: lógica de negocio, cálculos, parsing, permisos, manejo de
   errores y código que ha fallado antes, antes que getters o código trivial.
4. **Elige el nivel adecuado**:
   - Unitario: lógica pura, rápido y determinista.
   - Integración: límites reales (BD, sistema de archivos, colas) con recursos de test.
   - E2E: pocos, sobre los flujos críticos del usuario.
5. **Escribe cada test** con estructura Preparar / Actuar / Comprobar, un comportamiento
   por test, nombre que describe el comportamiento esperado (`devuelve_404_si_no_existe`).
   Aserciones específicas sobre resultados observables.
6. **Controla el no determinismo**: tiempo (reloj inyectado), aleatoriedad (semillas),
   red (dobles o servidores locales), orden y concurrencia. Nada de `sleep` para esperar.
7. **Mockea solo en los bordes** (red, reloj, servicios externos). Mockear colaboradores
   internos acopla el test a la implementación.
8. **Comprueba que el test puede fallar**: rompe temporalmente el código (o invierte la
   aserción) y verifica que falla con un mensaje útil. Revierte.
9. **Ejecuta la suite completa del área** varias veces si hay riesgo de flakiness.

## Integración con la memoria (.ai/)

- Si creaste helpers o fixtures reutilizables, documenta su existencia en
  `.ai/context/20-conventions.md` (sección de tests) y `mh sync`.
- Anota en `STATE.md` las áreas que siguen sin cubrir y por qué.

## Entregable

Tests en el lugar y estilo del proyecto, pasando; resumen de qué comportamientos quedan
cubiertos, cuáles no, y la evidencia de que los tests fallan ante una regresión.

## Checklist de calidad

- [ ] Cada test verifica un comportamiento observable, no detalles internos.
- [ ] Se ha comprobado que cada test nuevo puede fallar.
- [ ] Deterministas: sin dependencia de hora, red, orden ni estado compartido.
- [ ] Los nombres se leen como especificación.
- [ ] Rápidos: los unitarios en milisegundos; lo lento está marcado o separado.
- [ ] Sin duplicar fixtures que ya existían.

## Anti-patrones

- Tests "snapshot" gigantes que se regeneran sin leer.
- Aserciones débiles (`assert result`, `not null`) donde cabe una exacta.
- Copiar la lógica de producción dentro del test para calcular el esperado.
- Tests que pasan porque el mock devuelve lo que el test comprueba.
- Marcar como skip un test que falla en vez de entender por qué.
