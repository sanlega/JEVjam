"""Contexto musical para Jev.

Jev razona mejor con descripciones que con números (ver "Math and Numbers" en la doc de
jaggedness), así que el código convierte las medidas en categorías con nombre y resume
el historial. El `state` es pequeño y solo lleva lo que las preguntas necesitan.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import numpy as np

from . import theory
from .analysis import Snapshot


def tempo_words(bpm: float | None) -> str:
    if bpm is None:
        return "unknown"
    for limit, word in ((70, "very slow"), (90, "slow"), (110, "medium"), (130, "upbeat"), (155, "fast")):
        if bpm < limit:
            return f"{word} (about {round(bpm)} BPM)"
    return f"very fast (about {round(bpm)} BPM)"


def loudness_words(rms_db: float, silence_seconds: float) -> str:
    if silence_seconds > 1.0:
        return "silent"
    for limit, word in ((-40, "very soft"), (-30, "soft"), (-20, "medium"), (-12, "loud")):
        if rms_db < limit:
            return word
    return "very loud"


def trend_words(delta_db: float) -> str:
    if delta_db > 6:
        return "getting much louder"
    if delta_db > 2.5:
        return "getting louder"
    if delta_db < -6:
        return "getting much softer"
    if delta_db < -2.5:
        return "getting softer"
    return "steady"


def density_words(onsets_per_second: float, bpm: float | None) -> str:
    per_beat = onsets_per_second * 60 / bpm if bpm else onsets_per_second / 2
    if per_beat < 0.3:
        return "very sparse (long held notes or few attacks)"
    if per_beat < 0.9:
        return "sparse (about one attack per beat or less)"
    if per_beat < 2.2:
        return "moderate (eighth-note feel)"
    return "dense (fast runs or strumming)"


def harmonic_rhythm(chord_history: list[str], beats_per_bar: int) -> dict:
    """Resumen de la progresión reciente en compases (compresión en código, no en Jev)."""
    bars = [chord_history[i:i + beats_per_bar] for i in range(0, len(chord_history), beats_per_bar)]
    per_bar = [Counter(b).most_common(1)[0][0] for b in bars if b]
    changes = sum(1 for a, b in zip(chord_history, chord_history[1:]) if a != b)
    rate = changes / max(1, len(chord_history) - 1)
    stable = "chords change rarely" if rate < 0.15 else "chords change every bar or so" if rate < 0.4 else "chords change often"
    return {"recent_bars": per_bar[-8:], "harmonic_rhythm": stable}


@dataclass
class BandMemory:
    """Lo que la banda ha hecho: cada agente recuerda su papel reciente."""

    parts: dict[str, list[str]] = field(default_factory=dict)
    section: int = 1
    phrase_pos: int = 0  # posición en su frase del compás que se va a decidir
    phrase_len: int = 4
    phrasing: str = "not enough history yet"  # dónde deja huecos el humano (dialogue.py)
    last_bar_phrasing: str = "unknown"
    # Lo que tocó el humano en cada compás completo (volumen en dB, ataques por pulso).
    bar_rms_db: list[float] = field(default_factory=list)
    bar_onsets_per_beat: list[float] = field(default_factory=list)

    # Lo que lleva sonando el compás en curso (se compara con los compases completos).
    now_rms_db: float | None = None
    now_onsets_per_beat: float | None = None

    def record_input(self, rms_db: float, onsets_per_beat: float) -> None:
        self.bar_rms_db = (self.bar_rms_db + [rms_db])[-64:]
        self.bar_onsets_per_beat = (self.bar_onsets_per_beat + [onsets_per_beat])[-64:]
        self.now_rms_db = self.now_onsets_per_beat = None

    def loudness_series(self) -> list[float]:
        return self.bar_rms_db + ([self.now_rms_db] if self.now_rms_db is not None else [])

    def density_series(self) -> list[float]:
        return self.bar_onsets_per_beat + ([self.now_onsets_per_beat] if self.now_onsets_per_beat is not None else [])

    def record(self, decisions: dict[str, str]) -> None:
        for agent, pattern in decisions.items():
            self.parts.setdefault(agent, []).append(pattern)
            self.parts[agent] = self.parts[agent][-4:]


def relative_loudness(bar_rms_db: list[float]) -> str:
    """Volumen del último compás frente a la mediana de la jam: no depende de la ganancia del micro."""
    if len(bar_rms_db) < 4:
        return "not enough history yet"
    cur, ref = bar_rms_db[-1], float(np.median(bar_rms_db[:-1]))
    if cur >= max(bar_rms_db[:-1]) and cur - ref > 3:
        return "the loudest moment of the jam so far"
    for limit, word in ((6, "much louder than usual"), (2.5, "louder than usual"), (-2.5, "about as loud as usual"),
                        (-6, "softer than usual")):
        if cur - ref > limit:
            return word
    return "much softer than usual"


def relative_density(bar_onsets_per_beat: list[float]) -> str:
    if len(bar_onsets_per_beat) < 4:
        return "not enough history yet"
    cur, ref = bar_onsets_per_beat[-1], float(np.median(bar_onsets_per_beat[:-1]))
    ratio = (cur + 0.1) / (ref + 0.1)
    for limit, word in ((1.6, "many more notes than usual"), (1.2, "more notes than usual"),
                        (0.83, "about as many notes as usual"), (0.6, "fewer notes than usual")):
        if ratio > limit:
            return word
    return "far fewer notes than usual"


def bar_trend(bar_rms_db: list[float]) -> str | None:
    """Tendencia del último compás frente a los 3 anteriores (más estable que ventanas de segundos)."""
    if len(bar_rms_db) < 3:
        return None
    return trend_words(bar_rms_db[-1] - float(np.mean(bar_rms_db[-4:-1])))


def phrase_words(pos: int, phrase_len: int = 4) -> str:
    """Posición del compás que se decide dentro de su frase (calculada en código, dicha en palabras)."""
    if pos % phrase_len == 0:
        return "first bar of a new phrase"
    if pos % phrase_len == phrase_len - 1:
        return "last bar of a phrase, leading into a new phrase"
    return "middle of a phrase"


def build_state(snap: Snapshot, memory: BandMemory, beats_per_bar: int = 4) -> dict:
    key = theory.key_name(snap.key[0], snap.key[1]) if snap.key and snap.key[2] > 0.5 else "unclear"
    chord = theory.chord_name(snap.chord[0], snap.chord[1]) if snap.chord else "no clear chord"
    return {
        "human_player": {
            "tempo": tempo_words(snap.bpm),
            "key": key,
            "current_chord": chord,
            "progression": harmonic_rhythm(snap.chord_history, beats_per_bar),
            "loudness": loudness_words(snap.rms_db, snap.silence_seconds),
            "loudness_compared_to_this_jam": relative_loudness(memory.loudness_series()),
            "loudness_trend": bar_trend(memory.loudness_series()) or trend_words(snap.rms_trend_db),
            "note_density": density_words(snap.onsets_per_second, snap.bpm),
            "note_density_compared_to_this_jam": relative_density(memory.density_series()),
            "playing": "stopped playing" if snap.silence_seconds > 2.0 else "playing",
            "phrasing": memory.phrasing,
            "last_bar": memory.last_bar_phrasing,
        },
        "band": {
            "position_in_phrase": phrase_words(memory.phrase_pos, memory.phrase_len),
            "section": f"section {memory.section}",
        },
    }
