# Estado actual

_Última actualización: 2026-09-30 por claude_

## En curso
- Tonalidad sin --key: KeyTracker por acordes (keyfinder.py). 11/11 progresiones, modulaciones en 3-5 compases; jam real 15:09 → C mayor (el croma decía G). 48 tests. Repo en github.com/sanlega/JEVjam (main).
- Jam real 15:09 con el micro correcto (--key C, C-G-F-G): 21/21 acordes reconocidos, banda 13/13 correcta en modo predicho (los 4 fallos, en modo following, 1 compás tarde como se espera), energía-volumen +0,70, sin eco. La prueba anterior falló por usar otro micro.
- Jam real 15:02 (--key C): solo batería. Causa: captación (eco de la banda por altavoces a 60 ms + entrada sin notas con altura, planitud 0,6). Añadidos: modos armónicos de respaldo (following/tonic) y diagnóstico de entrada. 33 tests.
- Grabación de sesiones (recordings/session-*/: input.wav, band.mid, mix.wav, bars.jsonl) + `python -m jevjam.review` + `--input archivo.wav` para repetir jams. 30 tests.
- Tras las primeras jams reales: acorde por ventana de pulso/compás, predicción sin atascos, descriptores relativos a la jam, reacción en 1 compás (antes 2).
- `--key` (tonalidad fija): fija la tonalidad y restringe la detección a acordes diatónicos (+V/V7 en menor). 26 tests.
- PoC funcional: micro/demo → análisis → contexto → Jev → banda (batería, bajo, teclado) → MIDI → synth/puerto virtual.
- Arquitectura y mediciones en `docs/ARCHITECTURE.md`. 15 tests en verde (sin red).
- e2e con Jev real (humano sintético Am-F-C-G a 100 BPM): 70/70 decisiones a tiempo, MIDI <2 ms de retraso,
  12/12 acordes correctos tras aprender la progresión.

## Próximos pasos
1. Que el usuario grabe jams reales con la versión nueva y revisarlas con `jevjam.review` (sobre todo tonalidad sin --key: salió F#/C# mayor en varias sesiones; sin audio no se pudo verificar).
2. Aprender la progresión antes (hoy 2 vueltas ≈ 8 compases) y seguir cambios de acorde a nivel de pulso.
3. Pulso 1 sin depender de la armonía (acentos/graves o tracker de downbeat).
4. Más músicos (guitarra, percusión, synth) y `answer_phrase` como Choice entre frases candidatas.
5. Calibrar umbrales con `recordings/*.jsonl`.

## Bloqueos / preguntas abiertas
- Solo probado con audio sintético: la precisión con instrumentos reales está por medir.
