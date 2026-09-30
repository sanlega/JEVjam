# Lecciones

Memoria rápida de la automejora (estilo Reflexion): una línea por lección, concreta y
accionable ("antes de X, haz Y porque Z"). Se añaden con `.ai/bin/mh learn "..."`.
La skill `self-improve` las consolida en skills, contexto o protocolo y las retira de aquí.

- 2026-09-30 [unknown] stop-check da falso positivo en repos sin commits: git status --porcelain agrupa directorios sin seguimiento (?? .ai/, ?? .claude/), así que no ve .ai/memory/STATE.md ni casa con los prefijos generados. Arreglo: usar --untracked-files=all.
- 2026-09-30 [unknown] En macOS con Python 3.14, threading.Condition.wait(timeout) tiene ~10 ms de granularidad; para temporizar MIDI usar time.sleep en tramos cortos + espera activa final.
- 2026-09-30 [unknown] Con micro real, los descriptores absolutos (dB, ataques/s) dependen de la ganancia y del instrumento: para Jev usar magnitudes relativas a la propia sesión.
- 2026-09-30 [unknown] Chrome headless (--headless=new) tiene un ancho mínimo de ventana de 500 px: las capturas a 390 px salen recortadas y parecen desbordes. Además, una página con SSE nunca termina de cargar: usar --timeout.
- 2026-09-30 [unknown] Para reconocer acordes de guitarra, el croma debe usar magnitud y no energía (magnitud²): los graves fuertes (Mi grave) tapan las terceras. Validado con jams reales grabadas.
