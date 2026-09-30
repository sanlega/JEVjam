"""Grabación de sesiones para analizarlas y afinar después.

Cada ejecución crea `recordings/session-AAAAMMDD-HHMMSS/` con:

    input.wav    lo que entró por el micro/interfaz (mono, 16 bits)
    band.mid     lo que tocó la banda (canal 10 batería, 1 bajo, 2 teclado)
    mix.wav      entrada + banda renderizada con el synth integrado, para escuchar
    bars.jsonl   por compás: tiempos, lo que oyó el análisis, lo que se envió a Jev,
                 lo que respondió y lo que tocó la banda
    meta.json    parámetros de la sesión y estadísticas

Todos los tiempos (`*_s`) son segundos desde el primer sample de `input.wav`, así que
audio, MIDI y decisiones se alinean sin más. Revisión: `python -m jevjam.review <carpeta>`.
"""
from __future__ import annotations

import json
import threading
import time
import wave
from pathlib import Path

import mido
import numpy as np

TICKS_PER_BEAT = 480
_MIDI_TEMPO = 500000  # 120 BPM de rejilla: 1 tick = 1/960 s (el tempo real va en bars.jsonl)


class SessionRecorder:
    """Graba audio, MIDI y compases. El audio se escribe desde el hilo de análisis, nunca del de audio."""

    def __init__(self, root: Path | str = "recordings", sr: int = 48000, meta: dict | None = None):
        self.dir = Path(root) / time.strftime("session-%Y%m%d-%H%M%S")
        self.dir.mkdir(parents=True, exist_ok=True)
        self.sr = sr
        self.meta = dict(meta or {})
        self.t0: float | None = None  # monotónico del primer sample
        self._samples = 0
        self._wav = wave.open(str(self.dir / "input.wav"), "wb")
        self._wav.setnchannels(1)
        self._wav.setsampwidth(2)
        self._wav.setframerate(sr)
        self._midi: list[tuple[float, mido.Message]] = []
        self._bars = (self.dir / "bars.jsonl").open("w")
        self._lock = threading.Lock()
        self.closed = False

    # --------------------------------------------------------------- tiempos
    def rel(self, mono: float) -> float:
        return mono - self.t0 if self.t0 is not None else 0.0

    # ----------------------------------------------------------------- audio
    def write_audio(self, mono_end: float, block: np.ndarray) -> None:
        """`mono_end`: instante (monotónico) en que llegó el final del bloque."""
        if self.closed:
            return
        if self.t0 is None:
            self.t0 = mono_end - len(block) / self.sr
        pcm = np.clip(block, -1, 1)
        self._wav.writeframes((pcm * 32767).astype("<i2").tobytes())
        self._samples += len(block)

    # ------------------------------------------------------------------ MIDI
    def send(self, msg: mido.Message) -> None:  # Sink del planificador
        with self._lock:
            self._midi.append((time.monotonic(), msg))

    def close(self) -> None:  # Sink.close: lo gestiona finish()
        pass

    # --------------------------------------------------------------- compases
    def write_bar(self, row: dict) -> None:
        if not self.closed:
            self._bars.write(json.dumps(row, ensure_ascii=False, default=_json_default) + "\n")
            self._bars.flush()

    # ----------------------------------------------------------------- cierre
    def finish(self, stats: dict | None = None, render_mix: bool = True) -> Path:
        if self.closed:
            return self.dir
        self.closed = True
        self._wav.close()
        self._bars.close()
        with self._lock:
            events = [(self.rel(t), m) for t, m in self._midi]
        write_midi(events, self.dir / "band.mid")
        self.meta.update({"input_seconds": self._samples / self.sr, "sample_rate": self.sr,
                          "midi_messages": len(events), "stats": stats or {}})
        (self.dir / "meta.json").write_text(json.dumps(self.meta, ensure_ascii=False, indent=2, default=_json_default))
        if render_mix and self._samples:
            render_mix_wav(self.dir)
        return self.dir


def _json_default(o):
    if isinstance(o, np.ndarray):
        return [round(float(x), 5) for x in o]
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    raise TypeError(type(o))


def write_midi(events: list[tuple[float, mido.Message]], path: Path) -> None:
    """MIDI de tipo 1: una pista por canal usado, tiempos absolutos en segundos → ticks."""
    mid = mido.MidiFile(type=1, ticks_per_beat=TICKS_PER_BEAT)
    names = {9: "Batería", 0: "Bajo", 1: "Teclado"}
    for ch in sorted({m.channel for _, m in events if hasattr(m, "channel")}):
        track = mido.MidiTrack()
        track.append(mido.MetaMessage("track_name", name=names.get(ch, f"Canal {ch + 1}"), time=0))
        track.append(mido.MetaMessage("set_tempo", tempo=_MIDI_TEMPO, time=0))
        last = 0
        for t, m in sorted(((t, m) for t, m in events if getattr(m, "channel", None) == ch), key=lambda e: e[0]):
            tick = max(0, int(round(mido.second2tick(max(0.0, t), TICKS_PER_BEAT, _MIDI_TEMPO))))
            track.append(m.copy(time=tick - last))
            last = tick
        mid.tracks.append(track)
    mid.save(path)


def read_midi(path: Path) -> list[tuple[float, mido.Message]]:
    events = []
    for track in mido.MidiFile(path).tracks:
        ticks = 0
        for m in track:
            ticks += m.time
            if not m.is_meta:
                events.append((mido.tick2second(ticks, TICKS_PER_BEAT, _MIDI_TEMPO), m.copy(time=0)))
    return sorted(events, key=lambda e: e[0])


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as w:
        sr, n, ch, width = w.getframerate(), w.getnframes(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(n)
    if width == 2:
        x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768
    elif width == 4:
        x = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2 ** 31
    elif width == 3:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        x = ((b[:, 0].astype(np.int32) | (b[:, 1].astype(np.int32) << 8) | (b[:, 2].astype(np.int32) << 16))
             << 8 >> 8).astype(np.float32) / 2 ** 23
    else:
        x = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128) / 128
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x, sr


def write_wav(path: Path, audio: np.ndarray, sr: int, channels: int = 1) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())


def render_mix_wav(session_dir: Path) -> Path:
    """Estéreo: la banda (con su propia imagen estéreo) y el humano algo a la izquierda."""
    from .synth import SynthEngine

    audio, sr = read_wav(session_dir / "input.wav")
    band = SynthEngine(sr).render(read_midi(session_dir / "band.mid"), len(audio) / sr + 1.0)
    n = max(len(audio), len(band))
    human = np.pad(audio, (0, n - len(audio)))
    band = np.pad(band, ((0, n - len(band)), (0, 0)))
    peak = max(1e-6, np.abs(human).max())
    human = human * min(1.0, 0.7 / peak)  # la entrada suele venir baja: la normalizamos
    stereo = band + np.stack([0.8 * human, 0.45 * human], axis=1)
    stereo = stereo / max(1.0, float(np.abs(stereo).max()) / 0.95)
    path = session_dir / "mix.wav"
    write_wav(path, stereo.reshape(-1), sr, channels=2)
    return path
