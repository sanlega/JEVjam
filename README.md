# JEVjam

Una banda de IA que **escucha lo que tocas y te acompaña en directo por MIDI**, usando
[Jev](https://docs.typesafe.ai) (TypeSafe) como el "oído musical" que decide qué papel toca
cada músico en el siguiente compás.

```
micrófono → análisis (tempo, acordes, dinámica…) → contexto en palabras → Jev → músicos → MIDI → instrumento
```

Jev no genera notas: juzga (¿más energía?, ¿un fill?, ¿dejo espacio?, ¿qué patrón toco?).
Las notas las genera código determinista, y la latencia de Jev nunca toca el audio porque
decide siempre el compás **siguiente**. Detalles y mediciones en
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Hoja de ruta musical: [docs/MUSICAL-METHODS.md](docs/MUSICAL-METHODS.md).

## Puesta en marcha

```sh
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
echo 'TYPESAFE_API_KEY=...' > .env          # clave de console.typesafe.ai (.env está en .gitignore)
```

## App

```sh
.venv/bin/python -m jevjam.app      # abre http://127.0.0.1:8765 en el navegador
```

Todas las opciones (entrada, dispositivo y canal con **vúmetro** para comprobar el micro antes de empezar, tempo, tonalidad, salida, compases,
grabación), un botón rojo para empezar y parar, la jam en directo (qué oye, qué toca la
banda, tonalidad, energía y papel de cada músico) y las sesiones grabadas con su revisión
o para repetirlas. Solo escucha en tu máquina (127.0.0.1).

## Uso por terminal

```sh
.venv/bin/python -m jevjam --input demo                 # un humano sintético toca Am-F-C-G; oyes todo
.venv/bin/python -m jevjam --input mic --bpm 100        # tocas tú (tempo fijo = más robusto)
.venv/bin/python -m jevjam --input mic --bpm 100 --key Am   # y tonalidad fija: acordes solo de La menor
.venv/bin/python -m jevjam --input mic                  # tocas tú y la banda detecta el tempo
.venv/bin/python -m jevjam --out virtual                # MIDI al puerto virtual "JEVjam" para tu DAW
.venv/bin/python -m jevjam --list-devices               # entradas de audio y puertos MIDI
```

- **Salidas**: `synth` (sintetizador integrado, por defecto), `virtual` (puerto "JEVjam":
  canal 10 batería, 1 bajo, 2 teclado), `both`, o el nombre de un puerto MIDI existente.
- Usa **auriculares** con `--input mic`: si el micro oye a la banda, se escucha a sí misma.
- La banda piensa en **frases** (4 compases por defecto, `--phrase` o selector en la app):
  cada músico mantiene su papel toda la frase y todos cambian a la vez al empezar la
  siguiente, con un redoble antes. Solo un cambio de sección muy claro se adelanta. La
  intensidad sigue tu volumen compás a compás, sin saltos.
- La batería entra enseguida. Bajo y teclado anticipan tus acordes cuando la progresión se
  repite; mientras no la conocen, a partir del compás 4 siguen el último acorde oído (un
  compás tarde) o, si no oyen acordes claros y usas `--key`, sostienen la tónica.
- La entrada importa más que nada: con el micro del portátil el instrumento debe estar
  cerca y la banda en **auriculares**. Al terminar se avisa si el micro oyó a la banda, si
  la señal llegó baja o si casi no había notas con altura (golpes/ruido).

## Grabar, revisar y afinar

Cada ejecución se graba en `recordings/session-AAAAMMDD-HHMMSS/` (desactívalo con `--no-record`):

| Archivo | Contenido |
|---|---|
| `input.wav` | lo que entró por el micro/interfaz |
| `band.mid` | lo que tocó la banda (ábrelo en tu DAW junto a `input.wav`) |
| `mix.wav` | humano (izquierda) + banda (derecha) para escuchar la jam |
| `bars.jsonl` | por compás: acorde oído y candidatos, volumen y ataques por pulso, estado enviado a Jev, su decisión y lo que tocó la banda |
| `review.csv` | lo genera la revisión |

```sh
.venv/bin/python -m jevjam.review                        # revisa la sesión más reciente
.venv/bin/python -m jevjam.review recordings/session-X --reanalyze   # re-analiza el audio con el código actual
.venv/bin/python -m jevjam --input recordings/session-X/input.wav    # repite la jam (misma entrada, código nuevo)
```

La revisión resume lo importante: % de compases con acorde reconocido, % en que la banda
tocó tu mismo acorde, tonalidad estimada sobre toda la grabación y correlación entre la
energía de la banda y tu volumen/densidad (¿te sigue?).

## Tests

```sh
.venv/bin/python -m pytest          # análisis, músicos, contexto y planificador (sin red)
```

## Estructura

| Archivo | Papel |
|---|---|
| `jevjam/analysis.py` | escucha en streaming: onsets, tempo, fase, croma, acorde, tonalidad, dinámica |
| `jevjam/context.py` | medidas → contexto en palabras para Jev |
| `jevjam/brain.py` | preguntas a Jev (fan-out de 7 por compás) y cliente asíncrono con plazo |
| `jevjam/keyfinder.py` | tonalidad en tiempo real a partir de los acordes reconocidos |
| `jevjam/phrasing.py` | fraseo: los papeles cambian por frases (2/4/8/16 compases), energía gradual |
| `jevjam/conductor.py` | reloj musical, pulso 1, predicción de progresión, plazos e histéresis |
| `jevjam/band.py` | batería, bajo y teclado: papel → notas MIDI deterministas |
| `jevjam/midi_out.py` | planificador MIDI preciso y destinos (puerto virtual, puerto existente) |
| `jevjam/synth.py` | instrumento virtual integrado |
| `jevjam/session.py` | una jam de principio a fin (la usan la CLI y la app) |
| `jevjam/app.py`, `jevjam/web/` | app local: servidor y página |
| `jevjam/sources.py` | micrófono, archivo WAV y humano sintético |
| `jevjam/recording.py` | grabación de sesiones (WAV, MIDI, compases, mezcla) |
| `jevjam/review.py` | revisión de sesiones grabadas |
