# Tonalidad fija (--key)

- **Fecha**: 2026-09-30 14:47
- **Agente**: claude
- **Rama**: HEAD @ sin commits

## Hecho
- `--key` en la CLI (acepta 'A minor', 'Am', 'C', 'F# major', 'Bbm', 'a menor'...): theory.parse_key + diatonic_chords; Analyzer(fixed_key) fija la tonalidad y limita detect_chord a los acordes diatónicos (+V/V7 en menor armónica).
- 11 tests nuevos (26 en total); e2e con Jev real OK.

## Retro
- Bien: restringir candidatos a la tonalidad es el patrón "select instead of generate" también en el análisis: menos opciones, menos confusiones (A vs C#m).
