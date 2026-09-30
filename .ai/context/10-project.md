# Proyecto

- **Nombre**: JEVjam
- **Objetivo**: jam sessions en directo con una banda de IA que escucha al músico humano
  (micro/interfaz) y responde por MIDI como otro músico, no como un generador de canciones.
- **Stack**: Python 3.14 (numpy, sounddevice, mido/python-rtmidi, typesafe-sdk). Futuro:
  núcleo de audio en C++/Rust (JUCE o nih-plug) para VST/AU, con el cerebro como servicio aparte.

## Arquitectura

Detalle y mediciones: `docs/ARCHITECTURE.md`. Flujo: audio → `analysis.py` (Snapshot numérico)
→ `context.py` (estado en palabras) → `brain.py` (Jev, 1 petición/compás en fan-out) →
`conductor.py` (reloj, pulso 1, predicción de progresión, plazos, histéresis) → `band.py`
(papel → NoteEvents deterministas) → `midi_out.py` (planificador) → `synth.py` / puerto MIDI.

- Jev **no genera MIDI** (solo texto de entrada; Choice/Score/Noul de salida). Decide el
  papel de cada músico para el compás SIGUIENTE; si llega tarde se mantiene su última decisión.
- Latencia medida de Jev desde aquí: mediana ~250 ms, máx. ~0,9 s (la doc dice ~100 ms sin red).
