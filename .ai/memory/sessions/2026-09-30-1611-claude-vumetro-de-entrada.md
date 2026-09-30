# Vúmetro de entrada

- **Fecha**: 2026-09-30 16:11
- **Agente**: claude
- **Rama**: main @ aeca75c

## Hecho
- LevelMeter (analysis.py) + Conductor.on_level + evento SSE "level" (no se guarda en el historial).
- MicMonitor en app.py: prueba del micro sin jam, se libera al empezar la jam y a los 30 s sin ping de la página.
- Vúmetro en la página (escenario y tarjeta de Entrada): -60..0 dBFS, pico sostenido, veredicto sin señal/muy bajo/bien/satura.
- Test del medidor (58 tests). App reiniciada en 127.0.0.1:8765.

## Retro
- Bien: el monitor previo cubre justo el fallo real de antes (micro equivocado).
- Mejorable: el monitor lanzado desde el shell del agente leyó -120 dB (¿permiso de micro de macOS o micro apagado?); no verificable desde aquí.
