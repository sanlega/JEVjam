# Fraseo: cambios por frases

- **Fecha**: 2026-09-30 16:30
- **Agente**: claude
- **Rama**: main @ 94ddec2

## Hecho
- Preguntas al usuario (frase elegible, todos a la vez, excepción por sección clara, energía gradual).
- PhrasePlanner (phrasing.py) integrado en conductor; opción phrase_bars en SessionConfig, CLI (--phrase) y app (tarjeta Banda); frase visible en la app y en el registro.
- Margen de histéresis elegido re-simulando decisiones grabadas de Jev (0,1 alternaba; 0,2 estable).
- Bajo y teclado no se retiran por un compás sin acorde (_ever_known).
- 71 tests; e2e con la jam real: 3 cambios de papel en 28 compases.

## Retro
- Bien: bars.jsonl guarda las probabilidades de Jev, así que se pudo calibrar el planificador sin nuevas llamadas ni volver a tocar.
- Mejorable: un test de cambio de sección falló por diseño (votos de la sección anterior); pensar qué evidencia es válida en cada tipo de cambio.
