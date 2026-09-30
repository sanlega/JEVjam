"""Instrumento virtual integrado, para probar sin DAW.

Sintetizador sustractivo mínimo (bajo, teclado) y batería sintetizada, todo en numpy
dentro del callback de audio. Es un `Sink` MIDI: recibe los mismos mensajes que un DAW.
"""
from __future__ import annotations

import threading

import mido
import numpy as np

from .band import BASS_CH, DRUM_CH, KEYS_CH
from .theory import midi_to_hz


class _Voice:
    __slots__ = ("ch", "note", "freq", "amp", "phase", "age", "released", "rel_age", "kind", "decay")

    def __init__(self, ch: int, note: int, vel: int, kind: str):
        self.ch, self.note, self.kind = ch, note, kind
        self.freq = midi_to_hz(note)
        self.amp = (vel / 127) ** 1.5
        self.phase = 0.0
        self.age = 0
        self.released = False
        self.rel_age = 0
        self.decay = 1.0


class SynthEngine:
    """Motor del synth sin dispositivo de audio: lo usan `Synth` (en vivo) y la mezcla offline."""

    def __init__(self, sr: int = 48000, volume: float = 0.5):
        self.sr, self.volume = sr, volume
        self._voices: list[_Voice] = []
        self._inbox: list[mido.Message] = []
        self._lock = threading.Lock()
        self._rng = np.random.default_rng(0)

    def send(self, msg: mido.Message) -> None:
        with self._lock:
            self._inbox.append(msg)

    def process(self, frames: int) -> np.ndarray:
        with self._lock:
            inbox, self._inbox = self._inbox, []
        for m in inbox:
            self._handle(m)
        buf = np.zeros(frames, dtype=np.float32)
        t = np.arange(frames)
        alive = []
        for v in self._voices:
            s = self._render(v, t, frames)
            if s is not None:
                buf += s
                alive.append(v)
        self._voices = alive
        return np.tanh(buf * self.volume)

    def render(self, events: list[tuple[float, mido.Message]], seconds: float, block: int = 128) -> np.ndarray:
        """Renderiza eventos (segundos, mensaje) a un array mono, con resolución de `block` muestras."""
        out = np.zeros(int(seconds * self.sr) + block, dtype=np.float32)
        events = sorted(events, key=lambda e: e[0])
        i = 0
        for start in range(0, len(out) - block + 1, block):
            t_end = (start + block) / self.sr
            while i < len(events) and events[i][0] < t_end:
                self._handle(events[i][1])
                i += 1
            out[start:start + block] = self.process(block)
        return out

    def _handle(self, msg: mido.Message) -> None:
        if msg.type == "note_on" and msg.velocity > 0:
            kind = "drum" if msg.channel == DRUM_CH else "bass" if msg.channel == BASS_CH else "keys"
            if len(self._voices) > 48:
                self._voices.pop(0)
            self._voices.append(_Voice(msg.channel, msg.note, msg.velocity, kind))
        elif msg.type in ("note_off", "note_on"):
            for v in self._voices:
                if v.ch == msg.channel and v.note == msg.note and not v.released:
                    v.released = True
        elif msg.type == "control_change" and msg.control == 123:
            self._voices = [v for v in self._voices if v.ch != msg.channel]

    def _render(self, v: _Voice, t: np.ndarray, frames: int) -> np.ndarray | None:
        sr = self.sr
        age = (v.age + t) / sr
        v.age += frames
        if v.kind == "drum":
            return self._drum(v, age)
        inc = v.freq / sr
        ph = v.phase + inc * t
        v.phase = (v.phase + inc * frames) % 1.0
        if v.kind == "bass":
            wave = 0.7 * np.sin(2 * np.pi * ph) + 0.3 * (2 * (ph % 1.0) - 1) * 0.5
            env = np.minimum(1, age / 0.005) * (0.6 + 0.4 * np.exp(-age * 4))
            gain = 0.55
        else:
            saw = 2 * (ph % 1.0) - 1
            wave = 0.5 * np.sin(2 * np.pi * ph) + 0.25 * saw + 0.25 * np.sin(4 * np.pi * ph)
            env = np.minimum(1, age / 0.01) * (0.5 + 0.5 * np.exp(-age * 3))
            gain = 0.18
        if v.released:
            rel = np.exp(-(v.rel_age + t) / sr / 0.08)
            v.rel_age += frames
            env = env * rel
            if rel[-1] < 1e-3:
                return None
        return (wave * env * v.amp * gain).astype(np.float32)

    def _drum(self, v: _Voice, age: np.ndarray) -> np.ndarray | None:
        if age[0] > 1.5:
            return None
        n = v.note
        noise = self._rng.uniform(-1, 1, len(age))
        if n == 36:  # bombo: seno con barrido de pitch
            f = 50 + 90 * np.exp(-age * 30)
            s = np.sin(2 * np.pi * np.cumsum(f) / self.sr + v.phase) * np.exp(-age * 8)
            v.phase += 2 * np.pi * f.sum() / self.sr
            g = 0.9
        elif n in (38, 37):  # caja / aro
            s = (0.6 * noise + 0.4 * np.sin(2 * np.pi * 190 * age)) * np.exp(-age * (18 if n == 38 else 40))
            g = 0.5
        elif n in (42, 46):  # charles cerrado / abierto
            hp = np.diff(noise, prepend=0)
            s = hp * np.exp(-age * (45 if n == 42 else 8))
            g = 0.18
        elif n == 49:  # crash
            s = np.diff(noise, prepend=0) * np.exp(-age * 2.5)
            g = 0.2
        else:  # toms
            f = {50: 200, 47: 150, 43: 110}.get(n, 150)
            s = np.sin(2 * np.pi * f * age) * np.exp(-age * 10)
            g = 0.6
        return (s * v.amp * g).astype(np.float32)


class Synth(SynthEngine):
    """Instrumento virtual en vivo: un `Sink` MIDI que suena por la salida de audio."""

    def __init__(self, sr: int = 48000, blocksize: int = 256, device=None, volume: float = 0.5):
        import sounddevice as sd

        super().__init__(sr, volume)
        self.stream = sd.OutputStream(samplerate=sr, blocksize=blocksize, channels=1, dtype="float32",
                                      latency="low", device=device, callback=self._callback)
        self.stream.start()

    def _callback(self, out, frames, _time, _status) -> None:
        out[:, 0] = self.process(frames)

    def close(self) -> None:
        self.stream.stop()
        self.stream.close()
