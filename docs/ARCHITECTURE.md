# JEVjam — arquitectura técnica del MVP

> Objetivo: que tocar con una IA se parezca a **improvisar con otro músico**, no a usar un
> generador. Esta página recoge la investigación, las decisiones y lo que ya se ha medido
> en la prueba de concepto (`jevjam/`).

## 1. Qué es Jev de verdad (y qué no)

Fuente: documentación viva de TypeSafe (docs.typesafe.ai, jev‑1.13, revisada el 2026‑09‑30).

| Jev **sí** | Jev **no** |
|---|---|
| Recibe un `state` de **texto/JSON** y preguntas tipadas | Audio, MIDI binario, imágenes (solo texto) |
| Devuelve **Choice** (1 de ≤255 opciones + probabilidades), **Score** (2‑10 niveles ordenados), **Noul** (probabilidad de sí) | Generar texto, notas, secuencias o MIDI (“use a generative model”) |
| Todas las preguntas de una petición se evalúan en paralelo sobre el mismo estado (fan‑out) | Encadenar razonamiento entre preguntas de la misma petición |
| Probabilidades calibradas + `confidence` para decidir cuándo actuar | Aritmética, contar, comparar números con precisión |
| ~100 ms según la doc; **medido desde aquí: mediana 230‑275 ms, máx. ~0,9 s** (incluye red) | Ejecutarse en local (API en la nube; 40 req/s, 64k tokens por petición) |

**Consecuencia de diseño:** Jev no puede “tocar”. Puede hacer lo que hace un músico en
fracciones de segundo: *juzgar* —¿subo la energía?, ¿hago un fill?, ¿dejo espacio?, ¿ha
cambiado la sección?, ¿qué papel toco en el próximo compás?—. Todo lo exacto (qué notas
encajan, cuándo suenan, la velocity) lo hace código determinista. Es el patrón
“select instead of generate” de TypeSafe aplicado a la música.

## 2. Arquitectura

```
┌──────────────────────────── LOCAL (tiempo real) ────────────────────────────┐
│                                                                              │
│  micro / interfaz ──► [captura] ──cola──► [análisis]  cada ~10 ms            │
│   (sounddevice,        256 muestras        onsets, tempo, fase de pulso,     │
│    5,3 ms/bloque)                          croma→acorde, tonalidad,          │
│                                            dinámica, densidad, silencio      │
│                                                 │ Snapshot (números)         │
│                                                 ▼                            │
│                                     [conductor: reloj musical]               │
│                                      · rejilla de compases propia            │
│                                      · pulso 1 por cambios de acorde         │
│                                      · aprende y PREDICE la progresión       │
│                                      · sigue tempo/fase suavemente           │
│                     contexto en palabras │           ▲ Decision             │
│                     (context.py)         ▼           │ (o la última)        │
│                              ┌────────── hilo Jev (asyncio) ──────────┐      │
│                              │ 1 petición/compás, fan‑out de 7 preguntas│     │
│                              └──────────────────┬──────────────────────┘     │
│                                                 │ (nube, 0,2‑0,9 s)          │
│  [músicos: band.py]  ◄── papel + energía + armonía predicha                  │
│   batería · bajo · teclado  →  NoteEvents de 1 compás, deterministas         │
│                 │                                                            │
│                 ▼                                                            │
│  [planificador MIDI]  reloj monótono, precisión <1 ms, note_off garantizado  │
│        │                       │                        │                    │
│        ▼                       ▼                        ▼                    │
│  synth integrado      puerto virtual "JEVjam"     puerto existente           │
│  (numpy, 0,7 ms/bloque)  (Logic, Ableton, GarageBand, VSTs)  (IAC, hardware)  │
└──────────────────────────────────────────────────────────────────────────────┘
                                   ▲
                                   │ POST /v1/systemone
                              Jev (TypeSafe)
```

### Dos bucles, dos escalas de tiempo

| Bucle | Frecuencia | Dónde | Qué decide | Si falla |
|---|---|---|---|---|
| **Reflejo** (tiempo real) | cada bloque/pulso | local | cuándo suena cada nota, tempo, fase, acorde | — (es código) |
| **Juicio** (musical) | 1 vez por compás | Jev | papel de cada músico, energía, sección, espacio | se mantiene la última decisión de Jev |

Así la latencia de Jev **nunca** toca el audio. Un músico humano tampoco cambia de papel a
mitad de corchea: decide hacia dónde va el siguiente compás mientras toca el actual.

### Línea temporal de un compás (implementada en `conductor.py`)

```
compás N:  |pulso 1 ─────|pulso 2 ─────|pulso 3 ─────|pulso 4 ───── ▲ ─|compás N+1
               ▲ foto + petición a Jev para N+1        plazo = inicio N+1 − 120 ms:
                                                       decisión (o la anterior) → notas de N+1
```

Presupuesto para Jev: ~3 pulsos menos 120 ms → 1,68 s a 100 BPM, 0,88 s a 180 BPM.
Medido: 70/70 decisiones a tiempo en 4 jams de prueba (medianas 234‑275 ms, máx. 702 ms).

## 3. Respuestas a las preguntas del encargo

### Qué se ejecuta en local
Captura, análisis, reloj, predicción armónica, generación de notas, planificación MIDI y
síntesis. Es decir: **todo lo que tiene plazo**. Lo único remoto es el juicio de Jev, y
tiene un plan B (mantener la decisión anterior), así que un corte de red degrada la
creatividad de la banda, no la música.

### Qué hace Jev
Una petición por compás con 7 preguntas en fan‑out (`brain.py`):

| id | Tipo | Pregunta (resumen) | Uso en código |
|---|---|---|---|
| `energy` | Score 0‑5 | ¿con cuánta energía debe tocar la banda? | velocity; <0,5 = silencio |
| `section_change` | Noul | ¿ha empezado el humano una sección nueva? | contador de sección; salta la histéresis |
| `leave_space` | Noul | ¿el humano hace un solo denso/fuerte y hay que dejarle sitio? | comping más escaso |
| `human_stopped` | Noul | ¿ha dejado de tocar? | la banda para |
| `drums_part` | Choice ×6 | tacet / light_time / groove / driving / half_time / fill | patrón de batería |
| `bass_part` | Choice ×6 | tacet / roots_whole / roots_pulse / octaves / walking / syncopated | patrón de bajo |
| `keys_part` | Choice ×5 | tacet / pads / comping / arpeggio / answer_phrase | patrón de teclado |

Cada opción lleva una descripción musical concreta (lo que Jev lee). Añadir un músico =
añadir una entrada en `AGENT_OPTIONS` y su generador en `band.py`; sigue siendo **una sola
petición** (≈1.340 tokens de entrada por compás ≈ 0,08 $/hora a 100 BPM).

Lecciones medidas con Jev:
- Pedirle “mantén la coherencia con lo que tocaste” lo **ancla**: nunca cambiaba de papel
  aunque la energía subiera de 1,3 a 4,1. Sin esa frase, con el humano suave elige
  `light_time/roots_whole/pads` y fuerte `driving/octaves/comping` (confianza 0,8‑0,9).
  La continuidad va en código: **histéresis** (si `confidence` < 0,25 y no hay cambio de
  sección, se mantiene el papel anterior).
- Con el estado en palabras, hace lo musicalmente sensato sin reglas: un **fill** justo en
  el compás de transición y `driving → groove` una vez asentada la nueva sección.

### Cómo representar el contexto (`context.py`)
Jev falla con números (doc “jaggedness”), así que el código traduce medidas a categorías
con nombre y mantiene el estado pequeño (context rot):

```json
{
  "human_player": {
    "tempo": "medium (about 100 BPM)", "key": "C major", "current_chord": "Am",
    "progression": {"recent_bars": ["Am","F","C","G"], "harmonic_rhythm": "chords change every bar or so"},
    "loudness": "loud", "loudness_trend": "getting much louder",
    "note_density": "moderate (eighth-note feel)", "playing": "playing"
  },
  "band": {"position_in_phrase": "last bar of a phrase, leading into a new phrase", "section": "section 1"}
}
```

La posición en la frase se calcula en código y se entrega en palabras: así Jev puede
decidir un fill “al final de la frase” sin contar compases.

### Cómo detectar BPM, tonalidad, acordes y notas con suficiente velocidad (`analysis.py`)
Todo numpy, hop de 512 muestras (10,7 ms), FFT de 4096; ~110× más rápido que tiempo real.

| Rasgo | Método MVP | Resultado en pruebas |
|---|---|---|
| Onsets | flujo espectral log + umbral adaptativo | — |
| Tempo | autocorrelación de la envolvente de onsets (8 s), prior log‑normal en 110 BPM, pico parabólico | ±0,1 BPM en 84‑150 BPM |
| Fase de pulso | media circular de la fase de los onsets | bajo ±30 ms/compás de corrección |
| Pulso 1 | posición dominante de los cambios de acorde | alinea en 2‑3 compases |
| Acorde | croma de **magnitud** (38 Hz‑2,1 kHz) vs plantillas con **serie armónica** modelada; penaliza séptimas | 56/56 sintéticas; jam real F‑E‑Am‑G 22/22 (con croma de energía, el E de guitarra salía 0/5) |
| Tonalidad | **rastreador por acordes** (`keyfinder.py`): encaje diatónico + presencia de la tónica + perfil de croma, con histéresis; o fija con `--key` | 11/11 progresiones; sigue modulaciones en 3‑5 compases; jam real C‑G‑F‑G: C mayor (solo croma: G mayor) |
| Dinámica / tendencia / densidad / silencio | RMS en dB, 2 s vs 6 s previos, onsets/pulso | — |

El acorde del **próximo** compás no se puede oír a tiempo: la banda **aprende la
progresión** (busca un ciclo de 4/2/8/3/1 compases que se repite) y la anticipa. Hasta
aprenderla, bajo y teclado esperan (tocarían un compás tarde); la batería entra enseguida.

### Cómo devuelve Jev las decisiones
Como respuestas tipadas (`choice` + `probabilities` + `confidence`, `score`, `noul`) que
el código consume sin parsear texto. Guardamos las probabilidades en el registro
(`recordings/*.jsonl`) para calibrar umbrales con jams reales.

### Cómo generar MIDI de forma estable (`band.py`, `midi_out.py`)
- Generadores **deterministas por compás** (semilla = compás): reproducibles y testeables.
- Voice leading por mínima distancia, notas siempre del acorde o de la escala (tests).
- Planificador en hilo propio con reloj monótono: retraso máximo medido **0,4‑1,7 ms**.
- Cada `note_on` lleva su `note_off` programado; re‑ataques cierran la nota previa;
  `panic()` (All Notes Off, CC123) al salir. Nada queda colgado aunque falle Jev o la red.
- Canales GM: 10 batería, 1 bajo, 2 teclado → funciona con cualquier DAW/sampler.

### Cómo evitar que la latencia de Jev rompa la jam
1. Jev fuera del camino crítico: decide el compás **siguiente**.
2. Plazo duro por compás; si no llega, se mantiene la última decisión (nunca se espera).
3. Reintentos acotados (1, backoff 50‑100 ms, timeout 1,5 s): un reintento tardío no sirve.
4. Una única petición por compás (fan‑out) en vez de una por músico.
5. Histéresis por confianza para que la banda no “tiemble” entre opciones.

## 4. Stack

**MVP (actual): Python 3.14** — iteración rápida, numpy, SDK oficial de TypeSafe.

| Pieza | Elección MVP | Por qué |
|---|---|---|
| Audio E/S | `sounddevice` (PortAudio) | bloques de 256 muestras, Core Audio/ASIO/ALSA |
| Análisis | numpy propio | latencia predecible, sin dependencias pesadas |
| Jev | `typesafe-sdk` (async) | cliente oficial, reintentos configurables |
| MIDI | `mido` + `python-rtmidi` | puerto virtual nativo en macOS/Linux |
| Instrumento | synth integrado (numpy) o DAW | probar sin nada instalado |

**Evolución (VST/AU, desktop, DAW):** el camino de audio pasa a C++/Rust; el cerebro sigue
siendo un proceso/servicio aparte:

```
Plugin (JUCE C++ o nih-plug Rust)          Servicio JEVjam (Python o Rust)
  análisis + reloj + generadores   ◄──IPC/OSC──►  contexto + Jev + memoria de la jam
  MIDI out sample-accurate                        (mismo contrato Decision)
```
- **JUCE** (VST3/AU/standalone; GPLv3 o licencia comercial) o **nih-plug** (Rust, VST3/CLAP).
- **Ableton Link** para compartir tempo con el DAW y otras apps (licencia GPL/comercial).
- En plugin, la posición/tempo del host sustituyen a la detección de tempo.

## 5. Librerías aprovechables (siguiente iteración)

| Librería | Para qué | Ojo |
|---|---|---|
| aubio | onsets, tempo, pitch YIN en tiempo real (C) | GPL‑3 |
| Essentia | tonalidad, acordes, beat tracking, modo streaming (C++) | AGPL‑3 o licencia comercial |
| madmom | beat/downbeat tracking de referencia (RNN+DBN), modo online | modelos con licencia no comercial |
| BeatNet | beat/downbeat/compás en tiempo real (CRNN + filtro de partículas) | validar latencia |
| CREPE | pitch monofónico preciso (voz, instrumento solista) | coste de GPU/CPU |
| Basic Pitch (Spotify) | audio→MIDI polifónico | por ventanas: no apto para baja latencia |
| librosa | análisis offline y prototipado | no tiempo real |
| FluidSynth + SoundFont GM | instrumento de calidad sin DAW | LGPL |

## 6. Qué es desarrollo propio

- Traducción medidas → contexto en palabras (la “interfaz” con Jev) y su evaluación.
- Catálogo de papeles por músico (opciones + descripciones) y sus generadores MIDI.
- Reloj musical que sigue al humano (tempo, fase, pulso 1) y predicción de progresiones.
- Política: plazos, histéresis por confianza, aprendizaje de la progresión.
- Registro de jams para calibrar umbrales y mejorar preguntas (patrón *autoresearch*).

## 7. Primera prueba con instrumento real (2026-09-30) y cambios

Siete jams reales del usuario (sin audio grabado todavía) mostraron:

| Síntoma | Causa | Cambio |
|---|---|---|
| "no clear chord" en el 66 % de los compases | acorde decidido con 0,3 s de croma y umbral de 0,7 pensado para audio sintético | acorde por **ventana de pulso y de compás** (croma sumado); umbral 0,65 (0,55 con `--key`) |
| la banda clavada en F ~20 compases | la predicción descartaba compases sin acorde y veía un "ciclo" de un solo F | predicción con compases "N" como huecos, ≥75 % de coincidencia entre vueltas; test de regresión |
| densidad "moderate" en 52/53 compases; "very soft/silent" tocando | descriptores absolutos dependientes de la ganancia del micro | descriptores **relativos a la propia jam** (`loudness_compared_to_this_jam`, `note_density_compared_to_this_jam`) y tendencia por compases |
| reacción lenta | a Jev solo llegaban compases completos: reaccionaba 2 compases tarde | se incluye lo ya sonado del compás en curso y se pregunta tras el pulso 2 si el tempo lo permite (≤ ~125 BPM) → 1 compás |

Segunda jam real, ya grabada (`session-20260930-150212`, `--key C`): solo sonaba la batería.
La revisión del audio mostró que el problema era la captación, no el análisis: el micro del
portátil oía a la banda por los altavoces (eco a 60 ms) y la entrada propia era casi todo
ruido y golpes (planitud espectral 0,6; un instrumento afinado da <0,3), así que en 29/31
compases no había acorde que oír y bajo y teclado esperaban para siempre. Cambios: modos
armónicos de respaldo (`following`, `tonic`) tras 4 compases, y diagnóstico de la entrada
(nivel, eco de la banda, planitud) en la revisión y al terminar cada sesión.

Además, cada sesión se graba (`recording.py`) y se revisa (`review.py`), y se puede
repetir una jam desde su `input.wav` para comparar versiones del código con la misma entrada.

### Tonalidad en tiempo real: estado del arte y elección

| Proyecto | Método | Tiempo real | Licencia |
|---|---|---|---|
| libKeyFinder (Mixxx) | croma + perfiles de tonalidad | pensado para pistas; usable por tramos | GPL‑3 |
| Queen Mary key detector (qm‑dsp, Vamp) | croma + perfiles, incremental | sí | GPL |
| Essentia `Key`/`KeyExtractor` | perfiles (Krumhansl, Temperley, edma…) | modo streaming | AGPL‑3 |
| madmom | CNN | no (pista completa) | modelos no comerciales |
| Antares Auto‑Key, Mixed In Key | propietarios | Auto‑Key sí | comercial |

Todos comparan croma con perfiles, y con pocos compases confunden tonalidades vecinas
(C y G mayor comparten 6 de 7 notas). Como JEVjam ya reconoce acordes por compás, la
tonalidad se deduce de ellos: qué tonalidad contiene los acordes (el F natural descarta G
mayor), cuál tiene su acorde de tónica presente y al abrir frase (C mayor frente a La
menor), y el perfil de croma como desempate. Memoria con olvido 0,8 por compás y cambio
solo si otra tonalidad gana 2 compases seguidos.

### El E que no se oía (jam 2026-09-30 16:31)

"Pierde la entrada": el audio no tenía cortes (un solo hueco de 10 ms); lo que se perdía
era la armonía. En F‑E‑Am‑G el E salía "sin acorde" 5 de 5 veces: con croma de energía
(magnitud²) la cuerda de Mi grave dominaba y el G# quedaba en un 2 %. Sin el E no se
aprendía la progresión y la tonalidad saltaba entre F, C y La menor. Con croma de
magnitud: E 5/5, 22/22 acordes, La menor estable y 14/14 acordes de la banda en modo
predicho. Además se cuentan los bloques de audio perdidos (overflow del dispositivo o
análisis saturado) y se avisa al terminar.

### Jam larga del 2026-09-30 17:22 (75 compases, 3 min)

| Tramo | Problema | Cambio | Antes → después (misma entrada) |
|---|---|---|---|
| acordes que no se repiten | "seguir el último acorde" iba siempre un compás tarde | **modo reactivo**: bajo y teclado oyen el pulso 1 y entran en el 2 con ese acorde; sin acorde claro, callan (tónica con `--key`) | 1/17 → 10/17 |
| tocar suave sin acordes claros | la banda mantenía F 5 compases a ciegas | lo mismo: sin acorde claro no se inventa | — |
| sincronía | +55 ms constantes (micro inalámbrico + altavoces) corregidos como error: la banda se retrasaba cada compás y el tempo caía a 99,1 | `sync.py` estima la **latencia** (desfase estable, tempo estable y sin pendiente dentro del compás) y solo corrige las desviaciones | tempo estable; latencia estimada ~60 ms |
| repetir un archivo | la banda seguía tocando tras acabar el audio | la sesión para al terminar la fuente | — |

Synth integrado rehecho (`synth.py`): piano eléctrico FM, bajo por armónicos, batería con
paso-banda por diferencia de medias móviles, estéreo, reverb de Schroeder vectorizada y
limitador suave; niveles equilibrados midiendo cada instrumento (bombo −20,7, bajo −22,5,
teclado −23,7, caja −24,0, charles −31,9 dB); 1,7 ms por bloque de 256 muestras.

### Fraseo (`phrasing.py`)

En las jams reales la banda cambiaba de papel cada 1,2–2 compases: Jev decide compás a
compás y oscila mucho (en un compás 1,0 a "suave" y en el siguiente 0,65 a "a tope"). Ahora:

- los votos de Jev (probabilidades) se acumulan durante la frase y se decide por mayoría
  al empezar la siguiente; el papel actual se mantiene salvo que otro le gane por > 0,2
  (con 0,1 alternaba frase sí, frase no en la jam real);
- todos los músicos cambian a la vez, en el pulso 1 de la frase (2/4/8/16 compases);
- excepción: `section_change` de Jev ≥ 0,85 cambia en el compás siguiente (decidiendo
  con la opinión actual, no con los votos de la sección que termina) y abre frase nueva;
- el redoble es un adorno del último compás de la frase, no un papel;
- la energía sigue a Jev como mucho ±0,5 por compás;
- bajo y teclado solo entran al empezar un grupo de 4 compases y no se retiran por un
  compás sin acorde claro.

Con la misma jam real: de ~18 cambios de batería en 28 compases a 3 cambios de papel.

## 8. Limitaciones conocidas del PoC y siguientes pasos

1. **Validar con instrumentos reales**: las pruebas usan un humano sintético con
   armónicos idealizados. Medir aciertos de acorde/tempo con guitarra, piano y voz.
2. **Aprendizaje de progresión más rápido** (hoy: 2 vueltas completas ≈ 8 compases) y
   seguimiento a nivel de pulso para cambios de acorde no repetitivos.
3. **Pulso 1 sin armonía** (solo ritmo): usar acentos/graves o un tracker de downbeat.
4. **Tempo libre / rubato**: hoy se sigue deriva suave (±15 %) y se ignoran saltos.
5. **Escucha a la banda**: restar la salida propia de la entrada (o usar entrada de línea)
   para no retroalimentarse cuando se toca con altavoces.
6. **Más músicos y roles**: guitarra, percusión, sintetizador; `answer_phrase` como
   pregunta‑respuesta real (elegir frases candidatas generadas en código con un Choice).
7. **Calibración**: usar las sesiones grabadas (`bars.jsonl`, `review.csv`) para ajustar umbrales.
