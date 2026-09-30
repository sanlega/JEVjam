"""JEVjam: micrófono → análisis → contexto → Jev → MIDI → instrumento virtual.

    python -m jevjam --input demo            # un humano sintético toca; lo oyes a él y a la banda
    python -m jevjam --input mic --bpm 100   # tocas tú (con tempo fijo, más robusto)
    python -m jevjam --input mic --key Am    # tonalidad fija: acordes solo de La menor
    python -m jevjam --out virtual           # MIDI a un puerto virtual "JEVjam" (DAW/synth)
    python -m jevjam --input recordings/session-X/input.wav   # repite una jam grabada
    python -m jevjam --list-devices

Cada ejecución se graba en recordings/session-*/ (audio, MIDI, decisiones). Revisión:
    python -m jevjam.review recordings/session-X
"""
from __future__ import annotations

import argparse

from .session import Session, SessionConfig, list_devices


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="jevjam", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", default="demo", help="mic | demo | ruta a un .wav (p. ej. una grabación anterior)")
    p.add_argument("--device", help="dispositivo de entrada (índice o nombre) para --input mic")
    p.add_argument("--channel", type=int, default=0, help="canal de la interfaz de audio (desde 0)")
    p.add_argument("--out", default="synth", help="synth | virtual | both | nombre de un puerto MIDI existente")
    p.add_argument("--bpm", type=float, help="tempo fijo (desactiva la detección)")
    p.add_argument("--key", help="tonalidad fija, p. ej. 'A minor', 'Am', 'C', 'F# major' (desactiva la detección)")
    p.add_argument("--bars", type=int, help="nº de compases a tocar")
    p.add_argument("--model", help="modelo de Jev (por defecto jev-1.13.0 o $JEV_MODEL)")
    p.add_argument("--progression", default="Am,F,C,G", help="progresión del humano de --input demo")
    p.add_argument("--demo-bpm", type=float, default=100)
    p.add_argument("--mute-demo", action="store_true", help="no reproducir el audio del humano de demo")
    p.add_argument("--sr", type=int, default=48000)
    p.add_argument("--list-devices", action="store_true")
    p.add_argument("--no-record", action="store_true", help="no grabar la sesión en recordings/")
    args = p.parse_args(argv)

    if args.list_devices:
        devices = list_devices()
        print("Entradas de audio:")
        for d in devices["inputs"]:
            print(f"  {d['index']:2d}  {d['name']}  ({d['channels']} canales){'  ← por defecto' if d['default'] else ''}")
        print("Salidas MIDI:", devices["midi_outputs"] or "ninguna")
        return 0

    cfg = SessionConfig(input=args.input, device=args.device, channel=args.channel, out=args.out, bpm=args.bpm,
                        key=args.key, bars=args.bars, model=args.model, progression=args.progression,
                        demo_bpm=args.demo_bpm, mute_demo=args.mute_demo, sr=args.sr, record=not args.no_record)
    try:
        cfg.fixed_key()
    except ValueError as exc:
        p.error(str(exc))

    def emit(kind: str, data: dict) -> None:
        if kind == "message" and data["text"].startswith(("tonalidad", "MIDI", "demo", "archivo")):
            print(data["text"])
        elif kind == "status" and data["state"] in ("listening", "saving", "error"):
            print(("\n" if data["state"] != "listening" else "") + data["text"]
                  + (" (Ctrl+C para salir)" if data["state"] == "listening" else ""))
        elif kind == "summary":
            j = data.get("jev")
            if j:
                print(f"Jev: {j['on_time']} a tiempo, {j['late']} tarde, {j['errors']} errores; latencia mediana "
                      f"{j['median_ms']} ms, máx {j['max_ms']} ms; retraso máx. del planificador MIDI "
                      f"{j['midi_max_late_ms']} ms")
            if data.get("folder"):
                print(f"sesión grabada en {data['folder']}/  →  revisa con: .venv/bin/python -m jevjam.review {data['folder']}")
            for tip in data.get("warnings", []):
                print(f"⚠ {tip}")

    session = Session(cfg, emit=emit, verbose=True)
    try:
        session.run()  # Ctrl+C se gestiona dentro: se guarda la sesión igualmente
    except RuntimeError as exc:
        print(exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
