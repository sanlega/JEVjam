# Anticipación, sincronía y pregunta-respuesta

- **Fecha**: 2026-09-30 17:13
- **Agente**: claude
- **Rama**: main @ 1cebb18

## Hecho
- Anticipación de acordes (theory.anticipate_chord + modo anticipated + plan en la app). Jev probado para esto: 3/10, descartado (D-004).
- BeatSync (fase α0,4 / periodo β0,1, guarda de rejilla creíble) sustituye a _follow; asincronía en bars.jsonl, revisión y app.
- Pregunta-respuesta: dialogue.GapProfile (caída de nivel), registro del humano, answer_phrase en huecos; fraseo para Jev.
- Replays con jams reales: acordes 10/10 y 11/11 desde la entrada; sincronía +10 ms ±28; respuestas en huecos 80 %.
- 94 tests.

## Retro
- Bien: medir a Jev antes de integrarlo evitó meter una pieza que empeoraba el resultado.
- Bien: guardar ventanas por pulso en bars.jsonl permitió recalibrar el detector de huecos sin volver a tocar.
- Mejorable: el tempo automático sigue siendo el eslabón débil; tras la corrección de periodo hay que protegerlo de rejillas equivocadas.
