# Solo percusión: diagnóstico de captación y respaldo armónico

- **Fecha**: 2026-09-30 15:07
- **Agente**: claude
- **Rama**: HEAD @ sin commits

## Hecho
- Revisada la jam real 15:02: 2/31 compases con acorde. Audio: eco de la banda en el micro (60 ms, índice 0,53) y entrada casi sin notas con altura (planitud 0,6, nivel de ruido -42 dB).
- Modos armónicos de respaldo en conductor (predicted/following/tonic/waiting) tras 4 compases; se registran en bars.jsonl (harmony_mode).
- review: input_quality (nivel, saturación, planitud, eco de la banda por caída del pico de correlación) + consejos; también al final de cada sesión con micro.
- 33 tests.

## Retro
- Bien: grabar el audio permitió ver que el fallo era de captación y no de análisis; sin eso habría seguido afinando umbrales a ciegas.
- Mejorable: la primera métrica de eco (correlación bruta) daba falso positivo con música sincronizada; validar métricas contra un caso negativo conocido antes de usarlas.
