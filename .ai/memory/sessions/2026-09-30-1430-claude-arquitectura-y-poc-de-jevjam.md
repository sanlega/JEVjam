# Arquitectura y PoC de JEVjam

- **Fecha**: 2026-09-30 14:30
- **Agente**: claude
- **Rama**: HEAD @ sin commits

## Hecho
- Investigada la doc viva de TypeSafe: Jev es System One (texto → Choice/Score/Noul), no genera MIDI. Latencia medida 0,2-0,9 s.
- docs/ARCHITECTURE.md: arquitectura MVP, respuestas al encargo, stack, librerías, desarrollo propio, limitaciones.
- PoC en jevjam/ (analysis, context, brain, conductor, band, midi_out, synth, sources, CLI) + 15 tests.
- .env con TYPESAFE_API_KEY (lo creó el usuario) añadido a .gitignore.
- e2e con Jev real: 70/70 decisiones a tiempo; 12/12 acordes tras aprender la progresión; MIDI <2 ms.

## Pendiente
- Probar con instrumento real; primer commit (esperando al usuario).

## Retro
- Bien: medir con Jev real destapó que la frase "stay consistent" lo anclaba; sin ella reacciona bien.
- Bien: el e2e con verificación de acordes vs verdad encontró dos bugs de alineación (recorte de la lista y lag de 1 compás).
- Mejorable: Condition.wait con timeout tiene ~10 ms de granularidad en macOS/Python 3.14; usar time.sleep para temporizar.
