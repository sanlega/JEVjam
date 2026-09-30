# Grabación, revisión y ajustes tras jams reales

- **Fecha**: 2026-09-30 15:00
- **Agente**: claude
- **Rama**: HEAD @ sin commits

## Hecho
- Diagnóstico de 7 jams reales (solo jsonl): 66 % compases sin acorde, predicción clavada en F, densidad siempre "moderate", reacción con 2 compases de retraso.
- Grabación de sesión (recording.py), revisión (review.py, --reanalyze), entrada desde WAV para repetir jams, SynthEngine offline para mix.wav.
- Acorde por ventana de pulso/compás; predict_next_chord robusto a "N"; descriptores relativos a la jam; petición a Jev tras el pulso 2 si da tiempo.
- 30 tests; e2e con Jev real: 100 % acordes, correlación energía-volumen +0,98, reacción en 1 compás.

## Retro
- Bien: los registros por compás bastaron para localizar 4 causas sin audio; grabar el audio cierra el ciclo (tonalidad sin verificar).
- Mejorable: el PoC se validó solo con audio sintético; los descriptores absolutos no sobrevivieron al micro real. Diseñar desde el principio para magnitudes relativas.
