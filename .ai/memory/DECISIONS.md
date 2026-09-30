# Registro de decisiones

Decisiones de arquitectura y convenciones. La más reciente, al final.
Formato: fecha, contexto, decisión, consecuencias.

## D-001 · Jev como capa de juicio por compás; notas generadas en código

- **Fecha**: 2026-09-30

Contexto: Jev (jev-1.13) solo acepta texto y devuelve Choice/Score/Noul; no genera secuencias. Latencia medida 0,2-0,9 s.
Decisión: Jev elige papel por músico, energía, cambio de sección, dejar espacio y si el humano paró, en UNA petición por compás, pedida en el pulso 1 para el compás siguiente. Las notas las generan generadores deterministas; si Jev no llega al plazo (inicio del compás - 120 ms) se mantiene su última decisión.
Consecuencias: la latencia de Jev nunca afecta al timing; la banda reacciona con 1 compás de retraso (como un músico). Añadir músicos = añadir opciones + generador, sin más peticiones.

## D-002 · Tonalidad por acordes en vez de solo croma

- **Fecha**: 2026-09-30

Contexto: los detectores habituales (libKeyFinder, qm-dsp, Essentia) usan croma + perfiles; con pocos compases confunden tonalidades vecinas (jam real C-G-F-G → G mayor 0,64 vs C 0,62).
Decisión: KeyTracker propio: encaje diatónico de los acordes reconocidos + presencia de la tónica (al abrir frase y al empezar la jam) + perfil de croma como desempate; olvido 0,8/compás e histéresis de 2 compases. --key sigue teniendo prioridad.
Consecuencias: depende de reconocer acordes (con melodía sola cae al croma). Sin dependencias GPL/AGPL. Sigue modulaciones en 3-5 compases.
