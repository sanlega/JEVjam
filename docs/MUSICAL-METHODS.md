# Métodos musicales aplicables a JEVjam

Investigación del 2026-09-30: qué técnicas de la práctica musical, la psicología del ritmo y
la informática musical (MIR, sistemas de improvisación) pueden mejorar la banda, y dónde
encajan en la arquitectura actual. Ordenado por impacto esperado sobre los problemas que
hemos visto en jams reales.

Criterio de encaje: JEVjam es **código que escucha y genera + Jev que juzga en opciones
acotadas**. Un método encaja si (a) mejora la escucha, (b) mejora la generación
determinista, o (c) da a Jev mejores preguntas u opciones. Los modelos que generan audio de
extremo a extremo no encajan con el diseño MIDI‑primero (ver §9).

---

## 1. Anticipar el acorde siguiente con armonía funcional (+ Jev)

**Problema actual:** hasta oír la progresión dos veces (≈ 8 compases) la banda va un compás
tarde ("sigo el último acorde oído"). Es el mayor fallo audible que queda.

**Método:** la armonía tonal no es aleatoria. Las funciones (tónica → subdominante →
dominante → tónica) y las estadísticas de corpus de pop/rock dan probabilidades de
transición entre grados. Por ejemplo, V → I y IV → V son muy frecuentes, y en menor
iv → V → i. [ReaLJam](https://arxiv.org/abs/2502.21267) (Google, CHI 2025) resuelve el mismo
problema con **anticipación**: el agente predice y planifica los acordes antes de que suenen,
y le enseña su plan al músico. Su modelo, ReaLchords, se entrenó con unos 30.000 fragmentos
de canciones pop anotados de Hooktheory.

**En JEVjam:**
- Prior en código: tabla de transiciones entre grados diatónicos (en `theory.py`, a mano
  a partir de la práctica común; se puede afinar con corpus como el de de Clercq & Temperley
  o McGill Billboard).
- Jev como **Choice** entre los acordes diatónicos: "Dado `progression`, ¿qué acorde es más
  probable que toque ahora el humano?". Es un juicio de sentido común musical; Jev conoce
  progresiones típicas descritas en texto (p. ej. "I‑V‑vi‑IV").
- Fusión en código: prior × Jev; si la confianza supera un umbral, se toca la predicción; si
  no, el modo actual.
- Bonus ReaLJam: **mostrar en la app el acorde que la banda planea tocar** (ya tenemos
  "la banda toca"; añadir "próximo").

**Medida:** acierto de acordes de la banda en los compases 0‑8 (hoy ≈ 0 %, porque espera o
va tarde).

## 2. Seguimiento de tempo con corrección de fase y periodo

**Problema actual:** `_follow` corrige la fase de forma ad hoc (30 % del error, ±30 ms) y
el tempo con un suavizado fijo.

**Método:** en psicología del ritmo, la sincronización entre músicos se modela con
**corrección lineal de fase** (y de periodo): cada uno corrige una fracción α de la
asincronía medida en el pulso anterior. [Wing, Endo, Bradbury y Vorberg
(2014)](https://royalsocietypublishing.org/doi/10.1098/rsif.2013.1125) lo midieron en
cuartetos de cuerda y derivan la α óptima que minimiza la varianza de la asincronía.
[B‑Keeper](https://zenodo.org/record/1177231) (Robertson y Plumbley) aplica esta idea a un
secuenciador que sigue a un batería en directo (Ableton), con un margen de tempo de ±5 %.

**En JEVjam:**
- Medir la asincronía en **cada pulso**: onset del humano más cercano frente a nuestro
  pulso. Aplicar corrección de fase α ≈ 0,25‑0,5 y de periodo β ≈ 0,1 con límites, como
  B‑Keeper.
- Dar más peso a los onsets graves o acentuados (bombo/bajo en B‑Keeper; en guitarra, el
  rasgueo del pulso 1).
- Registrar la asincronía en `bars.jsonl` y mostrarla en la revisión (ms, media y
  desviación).

**Medida:** asincronía media y su desviación entre los ataques del humano y la banda.

## 3. Pregunta‑respuesta según los huecos del humano

**Problema actual:** `answer_phrase` responde en la segunda mitad del compás, toque lo que
toque el humano.

**Método:** en la improvisación en grupo (trading fours/eights, call and response) se
responde **en los silencios del otro**, y el acompañante se retira cuando el solista es
denso. Continuator (Pachet, 2003) y
[Somax2](https://github.com/DYCI2/Somax2) (IRCAM) escuchan en continuo y responden en función
de lo oído.

**En JEVjam:**
- Escucha: detectar **huecos** (pulsos por debajo del umbral tras una frase del humano) y
  **densidad por pulso**. Ya tenemos ventanas por pulso: es poco trabajo.
- Contexto para Jev: "the human just left a gap at the end of the phrase" /
  "the human is playing a dense line".
- Generación: la frase de respuesta se toca **en el hueco** (no en un sitio fijo) y en un
  **registro distinto** al del humano.

**Medida:** % de notas de respuesta que caen en huecos del humano frente a encima de él.

## 4. Armonía más robusta: transcripción aproximada + suavizado temporal

**Problema actual:** algunos compases salen "sin acorde" o con acordes espurios al cambiar
de acorde dentro del compás.

**Métodos:**
- **NNLS chroma** ([Mauch y Dixon, ISMIR 2010](https://code.soundsoftware.ac.uk/projects/nnls-chroma/)):
  antes del croma hace una transcripción aproximada (mínimos cuadrados no negativos con un
  diccionario de notas con armónicos). Mejora en especial los "acordes difíciles"; es la
  versión rigurosa del arreglo que hicimos para el E de guitarra.
- **HMM / Viterbi de acordes** con transiciones que dependen de la tonalidad (Chordino,
  Sheh y Ellis): en vez de decidir cada compás por separado, se busca la secuencia más
  probable. En tiempo real: filtrado *forward* con un retardo fijo de 1‑2 pulsos.
- Detectar **cambios de acorde a mitad de compás** (dos acordes por compás) en vez de
  forzar uno por compás.

**Medida:** % de compases con acorde claro y acierto frente a una verdad anotada de 2‑3
jams reales.

## 5. Hipermetro y arco del arreglo

**Problema actual:** las frases de 4 compases ya ordenan los cambios, pero la jam no tiene
"forma" (intro, crescendo, estribillo, final).

**Método:** la *Generative Theory of Tonal Music* (Lerdahl y Jackendoff, 1983) describe la
**estructura hipermétrica**: los compases se agrupan en 2 → 4 → 8 → 16, y los cambios
importantes caen en los límites mayores. La práctica de producción añade el **layering**:
los instrumentos entran de uno en uno para construir intensidad, se quitan capas antes de
un momento fuerte (*break*) y hay redobles o *pickups* antes de los límites.

**En JEVjam (sobre `phrasing.py`):**
- Jerarquía: frase (4) → sección (8/16). Los cambios grandes solo en límites de sección y
  los pequeños (un músico) en límites de frase.
- **Entrada escalonada** al empezar: batería → bajo → teclado, frase a frase, como una banda
  que se incorpora.
- Jev: Score de "en qué punto del arco está la jam" (intro / crece / pico / baja / final)
  a partir del volumen y la densidad relativos y del tiempo transcurrido; el código lo traduce
  en capas.
- **Final**: si el humano va parando (tendencia a la baja + fin de frase), la banda cierra
  con un acorde de tónica en el pulso 1 en vez de apagarse.

**Medida:** escucha (A/B con y sin arco) y número de "momentos" por jam.

## 6. Groove: acentos, síncopa y swing del humano

**Problema actual:** la batería elige patrón por energía, pero no copia la rítmica del humano
(acentos en 2 y 4, síncopas, swing o corcheas rectas).

**Métodos:**
- Perfil de acentos por subdivisión (qué corcheas o semicorcheas llevan ataques fuertes):
  índice de síncopa, detección de *half‑time*.
- **Swing ratio**: relación de duración entre la primera y la segunda corchea (1:1 recto,
  ~2:1 swing).
- **Microtiming** por rol, como en la práctica real: el bajo ligeramente por delante o
  encima del pulso, el charles con swing y la caja algo por detrás en *laid‑back*. Sustituye
  el ±jitter aleatorio actual.

**En JEVjam:** análisis por pulso (ya hay onsets) → descriptores en palabras para Jev
("straight eighths", "swung", "accents on 2 and 4", "syncopated") → Jev elige la sensación y
el código aplica swing/microtiming en `band.py`.

**Medida:** coincidencia de swing y acentos entre humano y banda (analizable en `mix.wav`).

## 7. Práctica de voicings y reparto de registro

**Problema actual:** el teclado toca tríadas cerradas en 55‑74 y puede pisar el registro del
humano y duplicar al bajo.

**Métodos (pedagogía de acompañamiento):**
- **Voicings sin fundamental** cuando hay bajo (la fundamental la pone el bajo) y **notas
  guía** (3ª y 7ª) en el comping; tensiones (9ª) en estilos que lo piden.
- **Reparto de registro**: el teclado evita el rango en que toca el humano (se estima con el
  croma por octavas o el onset grave), igual que un pianista deja sitio al cantante.
- Conducción de voces ya implementada (mínimo movimiento): mantenerla.

**Medida:** escucha y solapamiento de registro entre humano y banda.

## 8. Aprender el estilo del propio músico

**Métodos:** Continuator (Pachet, 2003; modelos de Markov de orden
variable sobre lo que toca el músico), OMax / [Somax2](https://github.com/DYCI2/Somax2)
(IRCAM: Factor Oracle y memoria de corpus, agentes que escuchan y recombinan en tiempo real),
ImproteK/DYCI2 (improvisación guiada por un "escenario", p. ej. una rejilla de acordes, que es
exactamente nuestra progresión predicha).

**En JEVjam:** a medio plazo, las frases de respuesta del teclado se construyen con motivos
del propio humano (transcritos con pitch monofónico) y se transponen a la armonía actual.
Jev elige entre candidatos ("¿cuál de estas 5 frases responde mejor a lo que acaba de tocar?"),
que es el patrón "select instead of generate" de TypeSafe.

## 9. Lo que no encaja (por ahora)

- **Modelos que generan audio en tiempo real** como [Magenta RealTime](https://github.com/magenta/magenta-realtime)
  (Google DeepMind, pesos abiertos, fragmentos de audio de 2 s guiados por texto o audio):
  impresionantes, pero generan audio y no MIDI, no siguen acorde a acorde y su latencia de
  bloque choca con el objetivo de otro músico que responde. Pueden servir de inspiración
  para un modo "textura/ambiente".
- **Modelos entrenados de acompañamiento** (ReaLchords): la referencia de calidad para el
  punto 1, pero requieren entrenamiento propio; empezar con prior + Jev y medir.

---

## Prioridad recomendada

| # | Método | Arregla | Esfuerzo | Jev |
|---|---|---|---|---|
| 1 | Anticipar acordes (armonía funcional + Jev) | compás de retraso al empezar y con progresiones nuevas | medio | Choice del siguiente acorde |
| 2 | Corrección de fase/periodo | sincronía fina con el humano | bajo‑medio | — |
| 3 | Pregunta‑respuesta por huecos | "músico que escucha" en vez de patrón fijo | bajo | nuevo contexto + Noul |
| 5 | Hipermetro, capas y final | que la jam tenga forma | medio | Score del arco |
| 6 | Groove (acentos/swing) | que la batería "sienta" como el humano | medio | Choice de sensación |
| 4 | NNLS + HMM de acordes | robustez armónica | medio‑alto | — |
| 7 | Voicings y registro | sonido más profesional | bajo | — |
| 8 | Estilo del músico | respuestas con su lenguaje | alto | selección de candidatos |

Referencias generales: R. Rowe, *Machine Musicianship* (MIT Press, 2001), el diseño
escucha/actuación que sigue JEVjam; F. Lerdahl y R. Jackendoff, *A Generative Theory of
Tonal Music* (MIT Press, 1983).
