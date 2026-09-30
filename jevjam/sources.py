"""Fuentes de audio: micrófono/interfaz en tiempo real, o un "humano" sintetizado para demos y tests."""
from __future__ import annotations

import threading
import time
from typing import Callable

import numpy as np

from . import theory


class MicInput:
    """Captura con sounddevice en bloques pequeños y entrega cada bloque a `on_block`."""

    def __init__(self, on_block: Callable[[np.ndarray], None], sr: int = 48000, blocksize: int = 256,
                 device=None, channel: int = 0):
        import sounddevice as sd

        self.channel = channel
        self._on_block = on_block
        self.overflows = 0  # bloques que el sistema de audio no pudo entregar a tiempo
        self.stream = sd.InputStream(samplerate=sr, blocksize=blocksize, channels=channel + 1, dtype="float32",
                                     latency="low", device=device, callback=self._cb)

    def _cb(self, indata, frames, _time, status) -> None:
        if status and status.input_overflow:
            self.overflows += 1
        self._on_block(indata[:, self.channel].copy())

    def start(self) -> None:
        self.stream.start()

    def close(self) -> None:
        self.stream.stop()
        self.stream.close()


def render_human(progression: list[str], bpm: float, sr: int = 48000, bars_per_chord: int = 1,
                 beats_per_bar: int = 4, repeats: int = 4, loud_from_bar: int | None = None,
                 strum: str = "quarters") -> np.ndarray:
    """Guitarra/piano sintético rasgueando una progresión. Sirve como humano reproducible."""
    names = {theory.chord_name(r, q): (r, q) for q in theory.CHORD_QUALITIES for r in range(12)}
    beat = 60 / bpm
    total_bars = len(progression) * bars_per_chord * repeats
    out = np.zeros(int(total_bars * beats_per_bar * beat * sr) + sr)
    rng = np.random.default_rng(1)
    bar = 0
    for _ in range(repeats):
        for ch in progression:
            root, quality = names[ch]
            notes = [48 + (root - 48) % 12 - 12] + theory.nearest_voicing(theory.chord_pcs(root, quality), None, 52, 67)
            for _b in range(bars_per_chord):
                loud = loud_from_bar is not None and bar >= loud_from_bar
                hits = [i * 0.5 for i in range(beats_per_bar * 2)] if (loud or strum == "eighths") \
                    else list(range(beats_per_bar))
                for h in hits:
                    t0 = (bar * beats_per_bar + h) * beat
                    amp = (0.35 if loud else 0.12) * (1.0 if h % 1 == 0 else 0.6)
                    for k, n in enumerate(notes):
                        start = int((t0 + k * 0.006) * sr)  # rasgueo: 6 ms entre cuerdas
                        dur = int(beat * (0.5 if loud else 0.9) * sr)
                        tt = np.arange(dur) / sr
                        f = theory.midi_to_hz(n)
                        tone = sum(np.sin(2 * np.pi * f * m * tt) / m ** 1.3 for m in (1, 2, 3, 4))
                        env = np.exp(-tt * 3.5) * np.minimum(1, tt / 0.003)
                        out[start:start + dur] += amp * tone * env * rng.uniform(0.85, 1.0)
                bar += 1
    return (out / max(1.0, np.abs(out).max() / 0.9)).astype(np.float32)


def load_audio_file(path: str, sr: int) -> np.ndarray:
    """WAV (16/24/32 bits, mono o estéreo) remuestreado a `sr` por interpolación lineal."""
    from .recording import read_wav

    audio, file_sr = read_wav(path)
    if file_sr != sr:
        n = int(len(audio) * sr / file_sr)
        audio = np.interp(np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio).astype(np.float32)
    return audio


class DemoHuman:
    """Reproduce audio en tiempo real (humano sintético o una grabación): lo oyes y el análisis lo escucha."""

    def __init__(self, on_block: Callable[[np.ndarray], None], audio: np.ndarray, sr: int = 48000,
                 blocksize: int = 256, play: bool = True):
        self.audio, self.sr, self.blocksize, self._on_block, self.play = audio, sr, blocksize, on_block, play
        self._pos = 0
        self._stream = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        if self.play:
            import sounddevice as sd

            self._stream = sd.OutputStream(samplerate=self.sr, blocksize=self.blocksize, channels=1,
                                           dtype="float32", latency="low", callback=self._cb)
            self._stream.start()
        else:
            self._thread = threading.Thread(target=self._clock, daemon=True)
            self._thread.start()

    def _next(self, frames: int) -> np.ndarray:
        block = self.audio[self._pos:self._pos + frames]
        self._pos += frames
        if len(block) < frames:
            block = np.pad(block, (0, frames - len(block)))
        return block

    def _cb(self, out, frames, _time, _status) -> None:
        block = self._next(frames)
        out[:, 0] = block * 0.8
        self._on_block(block)

    def _clock(self) -> None:
        period = self.blocksize / self.sr
        t = time.monotonic()
        while not self._stop.is_set():
            self._on_block(self._next(self.blocksize))
            t += period
            time.sleep(max(0.0, t - time.monotonic()))

    @property
    def finished(self) -> bool:
        return self._pos >= len(self.audio)

    def close(self) -> None:
        self._stop.set()
        if self._stream:
            self._stream.stop()
            self._stream.close()
