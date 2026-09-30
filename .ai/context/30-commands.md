# Comandos

```sh
.venv/bin/python -m jevjam.app                              # app en el navegador (127.0.0.1:8765)
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'   # instalar
.venv/bin/python -m pytest                                   # tests (sin red)
.venv/bin/python -m jevjam --input demo --mute-demo --out virtual --bars 8   # e2e con Jev real, sin sonido
.venv/bin/python -m jevjam --input demo                      # demo audible (humano sintético + synth)
.venv/bin/python -m jevjam --input mic --bpm 100             # tocar en directo
```
La clave va en `.env` (`TYPESAFE_API_KEY=...`, ignorado por git). Modelo fijado: `jev-1.13.0` (`JEV_MODEL`).
