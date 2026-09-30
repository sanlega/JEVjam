"""Una jam de principio a fin: fuente de audio → conductor → MIDI, con grabación y resumen.

La usan la CLI (`python -m jevjam`) y la app (`python -m jevjam.app`). Los avisos salen por
`emit(tipo, datos)`:

    status   {"state": starting|listening|playing|saving|done|error, "text"}
    message  {"text", "level": info|warning}
    level    {"rms_db", "peak_db"} nivel de entrada ~20 veces por segundo (vúmetro)
    bar      lo que devuelve Conductor.on_bar (un compás)
    summary  {"jev": {...}, "folder", "warnings": [...]}
"""
from __future__ import annotations

import statistics
import threading
import time
from dataclasses import asdict, dataclass
from typing import Callable

from .brain import DecisionWorker, JevBrain
from .conductor import Conductor
from .midi_out import NamedPort, Scheduler, VirtualPort
from .sources import DemoHuman, MicInput, load_audio_file, render_human
from .theory import key_name, parse_key

Emit = Callable[[str, dict], None]


@dataclass
class SessionConfig:
    input: str = "demo"  # mic | demo | ruta a un .wav
    device: str | int | None = None
    channel: int = 0
    out: str = "synth"  # synth | virtual | both | nombre de puerto MIDI
    bpm: float | None = None
    key: str | None = None
    bars: int | None = None
    model: str | None = None
    progression: str = "Am,F,C,G"
    demo_bpm: float = 100
    mute_demo: bool = False
    sr: int = 48000
    record: bool = True
    phrase_bars: int = 4  # los músicos solo cambian de papel al empezar una frase de estos compases

    def fixed_key(self) -> tuple[int, str] | None:
        return parse_key(self.key) if self.key else None  # ValueError si no es válida


def list_devices() -> dict:
    """Entradas de audio y salidas MIDI disponibles."""
    import mido
    import sounddevice as sd

    try:
        default_in = sd.default.device[0]
    except Exception:
        default_in = None
    inputs = [{"index": i, "name": d["name"], "channels": d["max_input_channels"], "default": i == default_in}
              for i, d in enumerate(sd.query_devices()) if d["max_input_channels"] > 0]
    try:
        midi_outs = mido.get_output_names()
    except Exception:
        midi_outs = []
    return {"inputs": inputs, "midi_outputs": midi_outs}


class Session:
    def __init__(self, cfg: SessionConfig, emit: Emit | None = None, verbose: bool = False):
        self.cfg = cfg
        self.emit: Emit = emit or (lambda kind, data: None)
        self.verbose = verbose
        self.conductor: Conductor | None = None
        self._stop = threading.Event()
        self.folder = None

    def stop(self) -> None:
        self._stop.set()
        if self.conductor:
            self.conductor.stop()

    def run(self) -> dict:
        cfg, emit = self.cfg, self.emit
        emit("status", {"state": "starting", "text": "preparando…"})
        fixed_key = cfg.fixed_key()
        brain = JevBrain(model=cfg.model)  # antes de abrir audio/MIDI: si falta la clave, no queda nada abierto
        if fixed_key:
            emit("message", {"text": f"tonalidad fija: {key_name(*fixed_key)}", "level": "info"})

        sinks = []
        if cfg.out in ("synth", "both"):
            from .synth import Synth

            sinks.append(Synth(sr=cfg.sr))
        if cfg.out in ("virtual", "both"):
            sinks.append(VirtualPort("JEVjam"))
            emit("message", {"text": "MIDI: puerto virtual 'JEVjam' (canal 10 batería, 1 bajo, 2 teclado)",
                             "level": "info"})
        if cfg.out not in ("synth", "virtual", "both"):
            sinks.append(NamedPort(cfg.out))
        recorder = None
        if cfg.record:
            from .recording import SessionRecorder

            recorder = SessionRecorder(sr=cfg.sr, meta={"argv": asdict(cfg), "key": cfg.key,
                                                        "started": time.strftime("%Y-%m-%d %H:%M:%S")})
            sinks.append(recorder)
        scheduler = Scheduler(sinks)
        worker = DecisionWorker(brain)

        def on_bar(info: dict) -> None:
            if info["bar"] == 0:
                emit("status", {"state": "playing", "text": "tocando"})
            emit("bar", info)

        conductor = self.conductor = Conductor(
            worker, scheduler, sr=cfg.sr, fixed_bpm=cfg.bpm, fixed_key=fixed_key, recorder=recorder,
            verbose=self.verbose, on_bar=on_bar, phrase_bars=cfg.phrase_bars,
            on_message=lambda text, level: emit("message", {"text": text, "level": level}),
            on_level=lambda level: emit("level", level))
        source = None
        error = None
        try:
            if cfg.input == "demo":
                prog = [c.strip() for c in cfg.progression.split(",") if c.strip()]
                audio = render_human(prog, cfg.demo_bpm, sr=cfg.sr, repeats=6, loud_from_bar=len(prog) * 3)
                source = DemoHuman(conductor.on_audio, audio, sr=cfg.sr, play=not cfg.mute_demo)
                emit("message", {"text": f"demo: humano sintético tocando {'-'.join(prog)} a {cfg.demo_bpm:.0f} BPM "
                                         f"(más fuerte desde el compás {len(prog) * 3 + 1})", "level": "info"})
            elif cfg.input == "mic":
                device = int(cfg.device) if isinstance(cfg.device, str) and cfg.device.isdigit() else cfg.device
                source = MicInput(conductor.on_audio, sr=cfg.sr, device=device, channel=cfg.channel)
                conductor.input_latency_s = float(source.stream.latency)
            else:
                audio = load_audio_file(cfg.input, cfg.sr)
                source = DemoHuman(conductor.on_audio, audio, sr=cfg.sr, play=not cfg.mute_demo)
                emit("message", {"text": f"archivo: {cfg.input} ({len(audio) / cfg.sr:.0f} s)", "level": "info"})
            if recorder:
                recorder.meta.update({"model": brain.model, "input_latency_s": conductor.input_latency_s})
            if not self._stop.is_set():
                source.start()
                emit("status", {"state": "listening", "text": "escuchando: toca algo…"})
                conductor.run(max_bars=cfg.bars)
        except KeyboardInterrupt:
            pass  # Ctrl+C en la CLI: se cierra y se guarda como un final normal
        except TimeoutError as exc:
            error = str(exc)
        except Exception as exc:  # dispositivo ocupado, archivo inexistente…
            error = f"{type(exc).__name__}: {exc}"
        finally:
            conductor.stop()
            if source:
                source.close()
            time.sleep(0.3)
            scheduler.close()
            worker.close()

        s = conductor.stats
        lat = s["latencies_ms"]
        summary: dict = {"bars": s["bars"], "warnings": [], "error": error}
        lost = s.get("audio_dropped", 0) + getattr(source, "overflows", 0)
        s["input_overflows"] = getattr(source, "overflows", 0)
        if lat:
            summary["jev"] = {"on_time": s["jev_on_time"], "late": s["jev_late"], "errors": s["jev_errors"],
                              "median_ms": round(statistics.median(lat)), "max_ms": round(max(lat)),
                              "midi_max_late_ms": round(scheduler.max_late_ms, 1)}
        if recorder:
            emit("status", {"state": "saving", "text": "guardando la sesión (audio, MIDI y mezcla)…"})
            stats = {k: v for k, v in s.items() if k != "bar_starts"}
            self.folder = recorder.finish(stats)
            summary["folder"] = str(self.folder)
            if s["bar_starts"] and cfg.input == "mic":
                from .review import input_quality, quality_advice

                first_bar = recorder.rel(s["bar_starts"][0]) - 4 * 60 / (cfg.bpm or 100)
                summary["warnings"] = quality_advice(input_quality(self.folder, max(0.0, first_bar)))
        if lost:
            summary["warnings"].append(
                f"se perdieron {lost} bloques de audio de la entrada (el ordenador no llegó a tiempo); "
                f"si se repite, cierra otras apps de audio o sube el tamaño de bloque")
        emit("summary", summary)
        emit("status", {"state": "error" if error else "done", "text": error or "terminado"})
        return summary
