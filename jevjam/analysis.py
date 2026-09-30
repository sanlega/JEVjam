"""Análisis musical en streaming: onsets, tempo, croma, acorde, tonalidad, dinámica y densidad.

Diseñado para bloques pequeños (hop de ~10 ms). Todo es numpy puro para que el camino
crítico sea predecible; los modelos pesados (transcripción polifónica, beat tracking con
redes) quedan fuera del MVP.
"""
from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field

import numpy as np

from . import theory


class LevelMeter:
    """Nivel de entrada para un vúmetro: RMS y pico en dBFS cada `interval` segundos de audio."""

    def __init__(self, sr: int = 48000, interval: float = 0.05):
        self.every = int(sr * interval)
        self._sum2, self._peak, self._n = 0.0, 0.0, 0

    def feed(self, block: np.ndarray) -> dict | None:
        """Devuelve {"rms_db", "peak_db"} al completar un intervalo; si no, None."""
        block = np.asarray(block, dtype=np.float32).reshape(-1)
        self._sum2 += float(np.dot(block, block))
        self._peak = max(self._peak, float(np.abs(block).max(initial=0.0)))
        self._n += len(block)
        if self._n < self.every:
            return None
        level = {"rms_db": round(10 * np.log10(self._sum2 / self._n + 1e-12), 1),
                 "peak_db": round(20 * np.log10(self._peak + 1e-6), 1)}
        self._sum2, self._peak, self._n = 0.0, 0.0, 0
        return level


@dataclass
class Window:
    """Lo que sonó entre dos llamadas a `Analyzer.take_window()` (p. ej. un pulso de la banda)."""

    chroma: np.ndarray  # energía por clase de altura, sumada en la ventana (sin normalizar)
    rms_db: float
    onsets: int
    seconds: float
    register: float | None = None  # altura media (MIDI) de lo que suena por encima del bajo


@dataclass
class Snapshot:
    """Lo que la escucha sabe en un instante. Números crudos: `context.py` los describe."""

    time: float
    bpm: float | None
    tempo_confidence: float
    beat_phase_time: float | None  # instante (s) de un pulso reciente estimado
    key: tuple[int, str, float] | None
    chord: tuple[int, str, float] | None
    chord_history: list[str] = field(default_factory=list)  # un acorde por pulso, reciente al final
    rms_db: float = -120.0
    rms_trend_db: float = 0.0  # diferencia entre los últimos ~2 s y los ~6 s anteriores
    onsets_per_second: float = 0.0
    silence_seconds: float = 0.0
    pitch_classes: list[int] = field(default_factory=list)  # más presentes, de más a menos


class Analyzer:
    """Consume audio mono en bloques y mantiene un `Snapshot` actualizado.

    `feed()` puede llamarse desde el hilo de captura; `snapshot()` desde cualquier hilo.
    """

    def __init__(self, sr: int = 48000, hop: int = 512, fft_size: int = 4096,
                 min_bpm: float = 60.0, max_bpm: float = 180.0, silence_db: float = -50.0,
                 fixed_key: tuple[int, str] | None = None):
        self.sr, self.hop, self.fft_size = sr, hop, fft_size
        # Con tonalidad fija no se estima y los acordes se buscan solo entre los de la tonalidad.
        self.fixed_key = fixed_key
        self._allowed_chords = theory.diatonic_chords(*fixed_key) if fixed_key else None
        self.min_bpm, self.max_bpm, self.silence_db = min_bpm, max_bpm, silence_db
        self._window = np.hanning(fft_size)
        self._buf = np.zeros(fft_size, dtype=np.float32)
        self._pending = np.zeros(0, dtype=np.float32)
        self._frames = 0
        self._prev_mag: np.ndarray | None = None
        self._lock = threading.Lock()

        freqs = np.fft.rfftfreq(fft_size, 1 / sr)
        valid = (freqs > 38) & (freqs < 2100)  # ~D1..C7: donde vive la armonía útil
        midi = 69 + 12 * np.log2(np.where(valid, freqs, 1.0) / 440.0)
        self._note_lo = 26
        self._note_of_bin = np.where(valid, np.round(midi).astype(int) - self._note_lo, -1)
        self._n_notes = int(self._note_of_bin.max()) + 1

        fps = sr / hop
        self.fps = fps
        self._flux = deque(maxlen=int(fps * 8))  # 8 s de envolvente de onsets
        self._rms = deque(maxlen=int(fps * 8))
        self._onset_times: deque[float] = deque(maxlen=256)
        self._chroma_fast = np.zeros(12)  # ~0.3 s: acorde actual
        self._chroma_slow = np.zeros(12)  # ~20 s: tonalidad
        self._last_loud = 0.0
        self._bpm: float | None = None
        self._tempo_conf = 0.0
        self._chords_per_beat: deque[str] = deque(maxlen=32)
        self._next_beat_mark: float | None = None
        self._flux_mean, self._flux_var = 0.0, 1e-6
        self._reset_window()

    @property
    def now(self) -> float:
        return self._frames / self.fps

    def feed(self, block: np.ndarray) -> None:
        block = np.asarray(block, dtype=np.float32).reshape(-1)
        self._pending = np.concatenate([self._pending, block])
        while len(self._pending) >= self.hop:
            self._process_hop(self._pending[: self.hop])
            self._pending = self._pending[self.hop:]

    # ----------------------------------------------------------------- por hop
    def _process_hop(self, hop: np.ndarray) -> None:
        self._buf = np.concatenate([self._buf[self.hop:], hop])
        self._frames += 1
        t = self.now

        rms = float(np.sqrt(np.mean(hop ** 2)) + 1e-12)
        rms_db = 20 * np.log10(rms)
        mag = np.abs(np.fft.rfft(self._buf * self._window))
        logmag = np.log1p(100 * mag)

        flux = 0.0 if self._prev_mag is None else float(np.maximum(logmag - self._prev_mag, 0).sum())
        self._prev_mag = logmag

        notes = self._notes(mag)
        chroma = self._chroma(mag, notes)
        loud = rms_db > self.silence_db
        with self._lock:
            self._flux.append(flux)
            self._rms.append(rms_db)
            self._win_frames += 1
            self._win_power += rms ** 2
            if loud:
                self._last_loud = t
                self._win_chroma += chroma
                self._win_notes += notes
                c = chroma / (chroma.sum() + 1e-12)
                self._chroma_fast += (c - self._chroma_fast) * (1 - np.exp(-1 / (0.3 * self.fps)))
                self._chroma_slow += (c - self._chroma_slow) * (1 - np.exp(-1 / (20 * self.fps)))
            self._detect_onset(flux, t, loud)
            if self._frames % int(self.fps) == 0:  # tempo: 1 vez por segundo basta
                self._estimate_tempo()
            self._mark_beat_chord(t)

    def _notes(self, mag: np.ndarray) -> np.ndarray:
        """Magnitud por semitono (nota MIDI desde `_note_lo`)."""
        sel = self._note_of_bin >= 0
        return np.bincount(self._note_of_bin[sel], weights=mag[sel], minlength=self._n_notes)

    def _chroma(self, mag: np.ndarray, notes: np.ndarray | None = None) -> np.ndarray:
        """Croma por clase de altura con la magnitud (no la energía); los armónicos van en las plantillas.

        Con energía (magnitud²) una nota grave fuerte tapaba al resto: en un E de guitarra la
        cuerda de Mi grave dejaba el G# (la tercera) en un 2 % y el acorde no se reconocía
        (jam real 2026-09-30 16:31: E en 0/5 compases; con magnitud, 5/5).
        """
        notes = self._notes(mag) if notes is None else notes
        chroma = np.zeros(12)
        np.add.at(chroma, (np.arange(self._n_notes) + self._note_lo) % 12, notes)
        return chroma

    def _detect_onset(self, flux: float, t: float, loud: bool) -> None:
        # Umbral adaptativo: media + k·desviación con memoria de ~1 s.
        a = 1 / self.fps
        self._flux_mean += (flux - self._flux_mean) * a
        self._flux_var += ((flux - self._flux_mean) ** 2 - self._flux_var) * a
        threshold = self._flux_mean + 2.0 * np.sqrt(self._flux_var)
        refractory = not self._onset_times or t - self._onset_times[-1] > 0.07
        if loud and flux > threshold and refractory:
            self._onset_times.append(t)
            self._win_onsets += 1

    def _reset_window(self) -> None:
        self._win_chroma = np.zeros(12)
        self._win_notes = np.zeros(self._n_notes)
        self._win_power = 0.0
        self._win_frames = 0
        self._win_onsets = 0

    def _register(self, above_midi: int = 48) -> float | None:
        """Altura "central" (MIDI) de lo que suena por encima de C3: dónde toca el humano."""
        midi = np.arange(self._n_notes) + self._note_lo
        w = np.where(midi >= above_midi, self._win_notes, 0.0)
        if w.sum() <= 0:
            return None
        return float(np.sum(midi * w) / w.sum())

    def take_window(self) -> Window:
        """Devuelve lo acumulado desde la última llamada y empieza una ventana nueva."""
        with self._lock:
            n = max(1, self._win_frames)
            w = Window(chroma=self._win_chroma.copy(), register=self._register(),
                       rms_db=float(10 * np.log10(self._win_power / n + 1e-24)),
                       onsets=self._win_onsets, seconds=self._win_frames / self.fps)
            self._reset_window()
            return w

    def chord_of(self, chroma: np.ndarray, min_similarity: float | None = None) -> tuple[int, str, float] | None:
        """Acorde de un croma acumulado; con tonalidad fija solo entre sus acordes y con umbral más bajo."""
        if min_similarity is None:
            min_similarity = 0.55 if self._allowed_chords else 0.65
        return theory.detect_chord(chroma, min_similarity=min_similarity, allowed=self._allowed_chords)

    def _estimate_tempo(self) -> None:
        env = np.array(self._flux)
        if len(env) < self.fps * 3:
            return
        env = env - env.mean()
        ac = np.correlate(env, env, mode="full")[len(env) - 1:]
        if ac[0] <= 0:
            return
        ac = ac / ac[0]
        lags = np.arange(len(ac))
        bpm_of_lag = 60 * self.fps / np.maximum(lags, 1)
        mask = (bpm_of_lag >= self.min_bpm) & (bpm_of_lag <= self.max_bpm)
        if not mask.any():
            return
        # Sesgo suave hacia ~110 BPM para resolver ambigüedad de octava de tempo.
        prior = np.exp(-0.5 * (np.log2(bpm_of_lag / 110) / 0.9) ** 2)
        scored = np.where(mask, ac * prior, -np.inf)
        lag = int(np.argmax(scored))
        # Refinamiento parabólico del pico.
        if 1 <= lag < len(ac) - 1:
            y0, y1, y2 = ac[lag - 1], ac[lag], ac[lag + 1]
            denom = y0 - 2 * y1 + y2
            frac = 0.5 * (y0 - y2) / denom if abs(denom) > 1e-12 else 0.0
        else:
            frac = 0.0
        bpm = 60 * self.fps / (lag + frac)
        conf = float(np.clip(ac[lag], 0, 1))
        if self._bpm is None or abs(bpm - self._bpm) / self._bpm > 0.08:
            self._bpm = bpm  # cambio claro: saltamos
        else:
            self._bpm += (bpm - self._bpm) * 0.3  # ajuste fino: suavizamos
        self._tempo_conf = conf

    def _mark_beat_chord(self, t: float) -> None:
        if not self._bpm:
            return
        period = 60 / self._bpm
        if self._next_beat_mark is None:
            self._next_beat_mark = t + period
        if t >= self._next_beat_mark:
            self._next_beat_mark += period
            ch = theory.detect_chord(self._chroma_fast, allowed=self._allowed_chords) if t - self._last_loud < 0.5 else None
            self._chords_per_beat.append(theory.chord_name(ch[0], ch[1]) if ch else "N")

    # --------------------------------------------------------------- consulta
    def beat_phase(self) -> float | None:
        """Instante de un pulso reciente, alineando la rejilla de tempo a los onsets."""
        if not self._bpm or len(self._onset_times) < 4:
            return None
        period = 60 / self._bpm
        onsets = np.array([o for o in self._onset_times if self.now - o < 8])
        if len(onsets) < 4:
            return None
        # Media circular de la fase de los onsets respecto al periodo.
        angles = 2 * np.pi * (onsets % period) / period
        phase = np.angle(np.mean(np.exp(1j * angles)))
        offset = (phase % (2 * np.pi)) / (2 * np.pi) * period
        last = self.now - ((self.now - offset) % period)
        return float(last)

    def onsets_between(self, t0: float, t1: float) -> list[float]:
        """Ataques detectados entre dos instantes (tiempo del analizador)."""
        with self._lock:
            return [o for o in self._onset_times if t0 <= o <= t1]

    def snapshot(self) -> Snapshot:
        with self._lock:
            t = self.now
            rms = np.array(self._rms) if self._rms else np.array([-120.0])
            recent = rms[-int(self.fps * 2):]
            before = rms[:-int(self.fps * 2)] if len(rms) > self.fps * 2 else recent
            trend = float(np.mean(recent) - np.mean(before))
            onsets_ps = sum(1 for o in self._onset_times if t - o < 4) / min(4.0, max(t, 1e-6))
            loud_recently = t - self._last_loud < 0.5
            chord = theory.detect_chord(self._chroma_fast, allowed=self._allowed_chords) if loud_recently else None
            key = (*self.fixed_key, 1.0) if self.fixed_key else theory.detect_key(self._chroma_slow)
            pcs = [int(i) for i in np.argsort(self._chroma_fast)[::-1][:5] if self._chroma_fast[i] > 0.05]
            return Snapshot(
                time=t,
                bpm=self._bpm,
                tempo_confidence=self._tempo_conf,
                beat_phase_time=self.beat_phase(),
                key=key,
                chord=chord,
                chord_history=list(self._chords_per_beat),
                rms_db=float(np.mean(rms[-int(self.fps * 0.5):])),
                rms_trend_db=trend,
                onsets_per_second=onsets_ps,
                silence_seconds=max(0.0, t - self._last_loud),
                pitch_classes=pcs,
            )
