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
import statistics
import time

from .brain import DecisionWorker, JevBrain
from .conductor import Conductor
from .midi_out import NamedPort, Scheduler, VirtualPort
from .sources import DemoHuman, MicInput, load_audio_file, render_human


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

    fixed_key = None
    if args.key:
        from .theory import key_name, parse_key

        try:
            fixed_key = parse_key(args.key)
        except ValueError as exc:
            p.error(str(exc))
        print(f"tonalidad fija: {key_name(*fixed_key)}")

    if args.list_devices:
        import mido
        import sounddevice as sd

        print(sd.query_devices())
        print("MIDI out:", mido.get_output_names())
        return 0

    sinks = []
    if args.out in ("synth", "both"):
        from .synth import Synth

        sinks.append(Synth(sr=args.sr))
    if args.out in ("virtual", "both"):
        sinks.append(VirtualPort("JEVjam"))
        print("MIDI: puerto virtual 'JEVjam' (canales: 10 batería, 1 bajo, 2 teclado)")
    if args.out not in ("synth", "virtual", "both"):
        sinks.append(NamedPort(args.out))

    recorder = None
    if not args.no_record:
        from .recording import SessionRecorder

        recorder = SessionRecorder(sr=args.sr, meta={
            "argv": vars(args), "key": args.key, "started": time.strftime("%Y-%m-%d %H:%M:%S")})
        sinks.append(recorder)
    scheduler = Scheduler(sinks)
    brain = JevBrain(model=args.model)
    worker = DecisionWorker(brain)
    source = None
    conductor = Conductor(worker, scheduler, sr=args.sr, fixed_bpm=args.bpm, fixed_key=fixed_key, recorder=recorder)
    try:
        if args.input == "demo":
            prog = [c.strip() for c in args.progression.split(",")]
            audio = render_human(prog, args.demo_bpm, sr=args.sr, repeats=6, loud_from_bar=len(prog) * 3)
            source = DemoHuman(conductor.on_audio, audio, sr=args.sr, play=not args.mute_demo)
            print(f"demo: humano sintético tocando {'-'.join(prog)} a {args.demo_bpm:.0f} BPM "
                  f"(más fuerte y denso desde el compás {len(prog) * 3 + 1})")
        elif args.input == "mic":
            device = int(args.device) if args.device and args.device.isdigit() else args.device
            source = MicInput(conductor.on_audio, sr=args.sr, device=device, channel=args.channel)
            conductor.input_latency_s = float(source.stream.latency)
            print("mic: toca algo; la banda entra cuando detecta tempo (Ctrl+C para salir)")
        else:
            audio = load_audio_file(args.input, args.sr)
            source = DemoHuman(conductor.on_audio, audio, sr=args.sr, play=not args.mute_demo)
            print(f"archivo: {args.input} ({len(audio) / args.sr:.0f} s)")
        if recorder:
            recorder.meta.update({"model": brain.model, "input_latency_s": conductor.input_latency_s})
        source.start()
        conductor.run(max_bars=args.bars)
    except KeyboardInterrupt:
        pass
    except TimeoutError as exc:
        print(f"\n{exc}")
    finally:
        conductor.stop()
        if source:
            source.close()
        time.sleep(0.3)
        scheduler.close()
        worker.close()
    s = conductor.stats
    lat = s["latencies_ms"]
    if lat:
        print(f"\nJev: {s['jev_on_time']} a tiempo, {s['jev_late']} tarde, {s['jev_errors']} errores; "
              f"latencia mediana {statistics.median(lat):.0f} ms, máx {max(lat):.0f} ms; "
              f"retraso máx. del planificador MIDI {scheduler.max_late_ms:.1f} ms")
    if recorder:
        print("guardando la sesión (audio, MIDI y mezcla)…")
        stats = {k: v for k, v in s.items() if k != "bar_starts"}
        folder = recorder.finish(stats)
        print(f"sesión grabada en {folder}/  →  revisa con: .venv/bin/python -m jevjam.review {folder}")
        if s["bar_starts"] and args.input == "mic":
            from .review import input_quality, quality_advice

            first_bar = recorder.rel(s["bar_starts"][0]) - 4 * 60 / (args.bpm or 100)
            for tip in quality_advice(input_quality(folder, max(0.0, first_bar))):
                print(f"⚠ {tip}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
