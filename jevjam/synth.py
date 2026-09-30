"""Instrumento virtual integrado, para tocar sin DAW.

Todo en numpy, por bloques, dentro del callback de audio (y offline para `mix.wav`):

- teclado: piano eléctrico por síntesis FM (portadora 1:1 con índice que decae + "púa" aguda
  al ataque, al estilo Rhodes/DX7), cálido y sin aliasing;
- bajo: suma de 4 armónicos (sin aliasing) con envolvente de pulsación y saturación suave;
- batería: bombo con barrido de tono y clic, caja con cuerpo y ruido, charles y platos con
  ruido filtrado, toms afinados;
- estéreo con cada instrumento en su sitio, reverb ligera (Schroeder vectorizada) y un
  limitador suave en lugar de saturar la mezcla.

Es un `Sink` MIDI: recibe los mismos mensajes que un DAW (canal 10 batería, 1 bajo, 2 teclado).
"""
from __future__ import annotations

import threading

import mido
import numpy as np

from .band import BASS_CH, DRUM_CH
from .theory import midi_to_hz

TWO_PI = 2 * np.pi
# Ganancias de batería equilibradas midiendo cada instrumento por separado (nivel percibido):
# bombo ≈ bajo ≈ teclado, caja 2-4 dB por debajo, charles ~12 dB por debajo.
G_SNARE, G_HAT, G_CRASH = 1.5, 0.72, 0.8


class _Voice:
    __slots__ = ("ch", "note", "freq", "amp", "phase", "age", "released", "rel_age", "kind", "pan", "extra")

    def __init__(self, ch: int, note: int, vel: int, kind: str, pan: float):
        self.ch, self.note, self.kind, self.pan = ch, note, kind, pan
        self.freq = midi_to_hz(note)
        self.amp = (vel / 127) ** 1.6
        self.phase = 0.0
        self.age = 0
        self.released = False
        self.rel_age = 0
        self.extra = 0.0  # estado propio (fase del barrido del bombo, etc.)


class _Delay:
    """Línea de retardo por bloques (retardo >= tamaño de bloque, así se vectoriza)."""

    def __init__(self, delay: int):
        self.d = delay
        self.buf = np.zeros(delay)
        self.pos = 0

    def read(self, n: int) -> np.ndarray:
        idx = (self.pos + np.arange(n)) % self.d
        return self.buf[idx]

    def write(self, x: np.ndarray) -> None:
        idx = (self.pos + np.arange(len(x))) % self.d
        self.buf[idx] = x
        self.pos = (self.pos + len(x)) % self.d


class _Reverb:
    """Reverb de Schroeder (4 peines en paralelo + 2 pasa-todo) por canal, sin bucles por muestra."""

    COMBS = (1116, 1188, 1277, 1356)
    ALLPASS = (556, 441)

    def __init__(self, sr: int, block: int, feedback: float = 0.8, spread: int = 23):
        scale = sr / 44100
        self.fb = feedback
        self.channels = []
        for s in (0, spread):
            combs = [_Delay(max(block, int((d + s) * scale))) for d in self.COMBS]
            aps = [_Delay(max(block, int((d + s) * scale))) for d in self.ALLPASS]
            self.channels.append((combs, aps))

    def process(self, x: np.ndarray) -> np.ndarray:
        n = len(x)
        # Suavizado previo (la cola de la reverb no debe tener agudos ásperos).
        x = np.convolve(x, np.ones(4) / 4, mode="same")
        out = np.zeros((n, 2))
        for c, (combs, aps) in enumerate(self.channels):
            y = np.zeros(n)
            for comb in combs:
                delayed = comb.read(n)
                comb.write(x + self.fb * delayed)
                y += delayed
            y /= len(combs)
            for ap in aps:
                delayed = ap.read(n)
                v = y + 0.5 * delayed
                ap.write(v)
                y = delayed - 0.5 * v
            out[:, c] = y
        return out


# Panorama (−1 izquierda … +1 derecha) y envío a reverb por tipo de sonido.
_PAN = {"bass": 0.0, "keys": 0.2, 36: 0.0, 38: -0.05, 37: -0.05, 42: -0.35, 46: -0.35, 49: 0.4,
        50: -0.25, 47: 0.05, 43: 0.3}
_SEND = {"bass": 0.03, "keys": 0.28, "drum": 0.12}


class SynthEngine:
    """Motor del synth sin dispositivo de audio: lo usan `Synth` (en vivo) y la mezcla offline."""

    def __init__(self, sr: int = 48000, volume: float = 0.8, block: int = 256):
        self.sr, self.volume = sr, volume
        self._voices: list[_Voice] = []
        self._inbox: list[mido.Message] = []
        self._lock = threading.Lock()
        self._rng = np.random.default_rng(0)
        self._reverb = _Reverb(sr, block)
        self._gain = 1.0  # control automático suave de la mezcla

    # --------------------------------------------------------------- MIDI
    def send(self, msg: mido.Message) -> None:
        with self._lock:
            self._inbox.append(msg)

    def _handle(self, msg: mido.Message) -> None:
        if msg.type == "note_on" and msg.velocity > 0:
            kind = "drum" if msg.channel == DRUM_CH else "bass" if msg.channel == BASS_CH else "keys"
            pan = _PAN.get(msg.note if kind == "drum" else kind, 0.0)
            if kind == "drum" and msg.note in (42, 46):  # el charles cerrado corta al abierto
                for v in self._voices:
                    if v.kind == "drum" and v.note == 46:
                        v.released = True
            if len(self._voices) > 64:
                self._voices.pop(0)
            self._voices.append(_Voice(msg.channel, msg.note, msg.velocity, kind, pan))
        elif msg.type in ("note_off", "note_on"):
            for v in self._voices:
                if v.ch == msg.channel and v.note == msg.note and not v.released and v.kind != "drum":
                    v.released = True
        elif msg.type == "control_change" and msg.control == 123:
            self._voices = [v for v in self._voices if v.ch != msg.channel]

    # --------------------------------------------------------------- audio
    def process(self, frames: int) -> np.ndarray:
        """Siguiente bloque estéreo (frames, 2) en float32."""
        with self._lock:
            inbox, self._inbox = self._inbox, []
        for m in inbox:
            self._handle(m)
        dry = np.zeros((frames, 2))
        send = np.zeros(frames)
        t = np.arange(frames)
        alive = []
        for v in self._voices:
            s = self._render(v, t, frames)
            if s is None:
                continue
            alive.append(v)
            left, right = np.cos((v.pan + 1) * np.pi / 4), np.sin((v.pan + 1) * np.pi / 4)
            dry[:, 0] += s * left
            dry[:, 1] += s * right
            send += s * _SEND["drum" if v.kind == "drum" else v.kind]
        self._voices = alive
        mix = dry + 0.9 * self._reverb.process(send)
        # Limitador suave: baja la ganancia si la mezcla se acerca a 1, la recupera despacio.
        peak = float(np.abs(mix).max(initial=0.0)) * self.volume * self._gain
        if peak > 0.9:
            self._gain *= 0.9 / peak
        else:
            self._gain = min(1.0, self._gain * 1.002)
        return np.tanh(mix * self.volume * self._gain).astype(np.float32)

    def render(self, events: list[tuple[float, mido.Message]], seconds: float, block: int = 256) -> np.ndarray:
        """Renderiza eventos (segundos, mensaje) a estéreo (n, 2), con resolución de `block` muestras."""
        n_blocks = int(seconds * self.sr) // block + 1
        out = np.zeros((n_blocks * block, 2), dtype=np.float32)
        events = sorted(events, key=lambda e: e[0])
        i = 0
        for k in range(n_blocks):
            t_end = (k + 1) * block / self.sr
            while i < len(events) and events[i][0] < t_end:
                self._handle(events[i][1])
                i += 1
            out[k * block:(k + 1) * block] = self.process(block)
        return out

    # ------------------------------------------------------------ voces
    def _release_env(self, v: _Voice, t: np.ndarray, frames: int, seconds: float) -> np.ndarray | None:
        if not v.released:
            return np.ones(frames)
        rel = np.exp(-(v.rel_age + t) / self.sr / seconds)
        v.rel_age += frames
        return None if rel[-1] < 1e-3 else rel

    def _render(self, v: _Voice, t: np.ndarray, frames: int) -> np.ndarray | None:
        sr = self.sr
        age = (v.age + t) / sr
        v.age += frames
        if v.kind == "drum":
            return self._drum(v, age, frames)
        ph = v.phase + TWO_PI * v.freq / sr * t
        v.phase = (v.phase + TWO_PI * v.freq / sr * frames) % (TWO_PI * 1000)
        if v.kind == "keys":
            # Piano eléctrico FM: índice alto al ataque (brillo) que decae (se vuelve redondo).
            index = 0.35 + 1.6 * v.amp * np.exp(-age * 3.5)
            body = np.sin(ph + index * np.sin(ph))
            tine = 0.18 * np.exp(-age * 30) * np.sin(14 * ph)  # "púa" metálica del ataque
            decay = 0.45 + v.freq / 900  # las notas agudas se apagan antes
            env = np.minimum(1.0, age / 0.004) * np.exp(-age * decay)
            rel = self._release_env(v, t, frames, 0.18)
            if rel is None or (env[-1] < 2e-4 and v.age > sr):
                return None
            return 0.3 * v.amp * (body + tine) * env * rel
        # Bajo: 4 armónicos (sin aliasing), ataque con un poco de púa y saturación suave.
        harm = (np.sin(ph) + 0.5 * np.sin(2 * ph) + 0.22 * np.sin(3 * ph) * np.exp(-age * 6)
                + 0.12 * np.sin(4 * ph) * np.exp(-age * 9))
        env = np.minimum(1.0, age / 0.006) * (0.55 + 0.45 * np.exp(-age * 5))
        rel = self._release_env(v, t, frames, 0.07)
        if rel is None:
            return None
        return 0.5 * v.amp * np.tanh(1.3 * harm) * env * rel

    def _noise(self, n: int, short: int, long: int = 0) -> np.ndarray:
        """Ruido paso-banda: media móvil corta (quita lo pegado a Nyquist) menos media móvil larga
        (quita los graves). (2, 8) ≈ 3-12 kHz a 48 kHz: platillos; (3, 12): caja; (8, 0): clic grave."""
        pad = max(short, long)
        x = self._rng.uniform(-1, 1, n + 2 * pad)
        y = np.convolve(x, np.ones(short) / short, mode="same")
        if long:
            y = y - np.convolve(x, np.ones(long) / long, mode="same")
        return y[pad:pad + n] * 2.0

    def _drum(self, v: _Voice, age: np.ndarray, frames: int) -> np.ndarray | None:
        if age[0] > 3.0:
            return None
        n, sr = v.note, self.sr
        if n == 36:  # bombo: seno con barrido 160→50 Hz y clic corto
            f = 50 + 110 * np.exp(-age * 28)
            ph = v.extra + np.cumsum(TWO_PI * f / sr)
            v.extra = ph[-1]
            s = np.sin(ph) * np.exp(-age * 6.5) + 0.3 * self._noise(frames, 8) * np.exp(-age * 300)
            return 0.95 * v.amp * s
        if n == 38:  # caja: cuerpo afinado + ruido brillante
            body = np.sin(TWO_PI * 185 * age) * np.exp(-age * 22) + 0.5 * np.sin(TWO_PI * 330 * age) * np.exp(-age * 30)
            snare = self._noise(frames, 4, 24) * np.exp(-age * 16)
            return G_SNARE * v.amp * (0.6 * body + snare)
        if n == 37:  # aro
            return 0.5 * v.amp * np.sin(TWO_PI * 1700 * age) * np.exp(-age * 70)
        if n in (42, 46):  # charles cerrado / abierto
            decay = 55 if n == 42 else 7
            env = np.exp(-age * decay)
            if v.released:  # abierto cortado por un cerrado
                env *= np.exp(-(v.rel_age + np.arange(frames)) / sr / 0.02)
                v.rel_age += frames
            return G_HAT * v.amp * self._noise(frames, 2, 8) * env  # 3-12 kHz: platillo, no fritura
        if n == 49:  # plato
            return G_CRASH * v.amp * self._noise(frames, 2, 6) * np.exp(-age * 1.6)
        f = {50: 210, 47: 160, 43: 115}.get(n, 150)  # toms con leve caída de afinación
        f_t = f * (1 + 0.25 * np.exp(-age * 20))
        ph = v.extra + np.cumsum(TWO_PI * f_t / sr)
        v.extra = ph[-1]
        return 0.6 * v.amp * np.sin(ph) * np.exp(-age * 9)


class Synth(SynthEngine):
    """Instrumento virtual en vivo: un `Sink` MIDI que suena por la salida de audio."""

    def __init__(self, sr: int = 48000, blocksize: int = 256, device=None, volume: float = 0.8):
        import sounddevice as sd

        super().__init__(sr, volume, blocksize)
        self.stream = sd.OutputStream(samplerate=sr, blocksize=blocksize, channels=2, dtype="float32",
                                      latency="low", device=device, callback=self._callback)
        self.stream.start()

    def _callback(self, out, frames, _time, _status) -> None:
        out[:] = self.process(frames)

    def close(self) -> None:
        self.stream.stop()
        self.stream.close()
