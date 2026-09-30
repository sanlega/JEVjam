"""JEVjam: mic → analysis → context → Jev → MIDI → virtual instrument.

    python -m jevjam --input demo            # a synthetic player strums; you hear it and the band
    python -m jevjam --input mic --bpm 100   # you play (fixed tempo, most robust)
    python -m jevjam --input mic --key Am    # fixed key: only chords from A minor
    python -m jevjam --out virtual           # MIDI to a virtual "JEVjam" port (DAW/synth)
    python -m jevjam --input recordings/session-X/input.wav   # replay a recorded jam
    python -m jevjam --list-devices

Every run is recorded to recordings/session-*/ (audio, MIDI, decisions). Review:
    python -m jevjam.review recordings/session-X
"""
from __future__ import annotations

import argparse

from .session import Session, SessionConfig, list_devices


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="jevjam", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", default="demo", help="mic | demo | path to a .wav (e.g. a previous recording)")
    p.add_argument("--device", help="input device (index or name) for --input mic")
    p.add_argument("--channel", type=int, default=0, help="audio interface channel (from 0)")
    p.add_argument("--out", default="synth", help="synth | virtual | both | name of an existing MIDI port")
    p.add_argument("--bpm", type=float, help="fixed tempo (disables detection)")
    p.add_argument("--key", help="fixed key, e.g. 'A minor', 'Am', 'C', 'F# major' (disables detection)")
    p.add_argument("--bars", type=int, help="number of bars to play")
    p.add_argument("--phrase", type=int, default=4, choices=[2, 4, 8, 16],
                   help="musicians change role at most every this many bars (default 4)")
    p.add_argument("--model", help="Jev model (default jev-1.13.0 or $JEV_MODEL)")
    p.add_argument("--progression", default="Am,F,C,G", help="progression of the --input demo player")
    p.add_argument("--demo-bpm", type=float, default=100)
    p.add_argument("--mute-demo", action="store_true", help="don't play the demo player's audio")
    p.add_argument("--sr", type=int, default=48000)
    p.add_argument("--list-devices", action="store_true")
    p.add_argument("--no-record", action="store_true", help="don't record the session in recordings/")
    args = p.parse_args(argv)

    if args.list_devices:
        devices = list_devices()
        print("Audio inputs:")
        for d in devices["inputs"]:
            print(f"  {d['index']:2d}  {d['name']}  ({d['channels']} channels){'  ← default' if d['default'] else ''}")
        print("MIDI outputs:", devices["midi_outputs"] or "none")
        return 0

    cfg = SessionConfig(input=args.input, device=args.device, channel=args.channel, out=args.out, bpm=args.bpm,
                        key=args.key, bars=args.bars, model=args.model, progression=args.progression,
                        demo_bpm=args.demo_bpm, mute_demo=args.mute_demo, sr=args.sr, record=not args.no_record,
                        phrase_bars=args.phrase)
    try:
        cfg.fixed_key()
    except ValueError as exc:
        p.error(str(exc))

    def emit(kind: str, data: dict) -> None:
        if kind == "message" and data["text"].startswith(("fixed key", "MIDI", "demo", "file")):
            print(data["text"])
        elif kind == "status" and data["state"] in ("listening", "saving", "error"):
            print(("\n" if data["state"] != "listening" else "") + data["text"]
                  + (" (Ctrl+C to quit)" if data["state"] == "listening" else ""))
        elif kind == "summary":
            j = data.get("jev")
            if j:
                print(f"Jev: {j['on_time']} on time, {j['late']} late, {j['errors']} errors; median latency "
                      f"{j['median_ms']} ms, max {j['max_ms']} ms; max MIDI scheduler lateness "
                      f"{j['midi_max_late_ms']} ms")
            if data.get("folder"):
                print(f"session recorded in {data['folder']}/  →  review it with: .venv/bin/python -m jevjam.review {data['folder']}")
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
