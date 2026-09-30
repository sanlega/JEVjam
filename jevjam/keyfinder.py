"""Tonalidad en tiempo real a partir de los acordes reconocidos (y del croma como apoyo).

Los detectores clásicos (Krumhansl, libKeyFinder, qm-dsp, Essentia) comparan el croma con
perfiles de tonalidad. Funcionan con piezas largas, pero con pocos compases confunden
tonalidades vecinas: en C-G-F-G el croma da G mayor 0,64 frente a C mayor 0,62, porque
comparten 6 de 7 notas. Los acordes resuelven lo que las notas sueltas no:

    encaje    ¿qué parte de los acordes recientes es diatónica a la tonalidad?  (F descarta G mayor)
    tónica    ¿suena su acorde de tónica, y al empezar frase?                    (C mayor vs La menor)
    croma     correlación con el perfil de Krumhansl-Kessler                     (desempate)

Con histéresis: solo cambia si otra tonalidad gana dos compases seguidos por un margen.
"""
from __future__ import annotations

import numpy as np

from . import theory

_CHORDS = {theory.chord_name(r, q): (r, q) for q in theory.CHORD_QUALITIES for r in range(12)}
_KEYS = [(t, m) for m in ("major", "minor") for t in range(12)]
_DIATONIC = {k: theory.diatonic_chords(*k) for k in _KEYS}


def _tonic_chords(tonic: int, mode: str) -> set[tuple[int, str]]:
    return {(tonic, q) for q in (("maj", "maj7") if mode == "major" else ("min", "min7"))}


class KeyTracker:
    def __init__(self, memory_bars: int = 16, decay: float = 0.8, switch_margin: float = 0.04,
                 switch_bars: int = 2, bars_per_phrase: int = 4):
        self.memory_bars, self.decay = memory_bars, decay
        self.switch_margin, self.switch_bars = switch_margin, switch_bars
        self.bars_per_phrase = bars_per_phrase
        self.chords: list[str] = []  # un acorde por compás ("N" = no claro)
        self.chroma = np.zeros(12)
        self.key: tuple[int, str] | None = None
        self.confidence = 0.0
        self._challenger: tuple[tuple[int, str], int] | None = None
        self.first_chord: tuple[int, str] | None = None  # el primer acorde claro de la jam
        self.bars_seen = 0

    def update(self, bar_chord: str | None, bar_chroma: np.ndarray | None = None) -> tuple[int, str, float] | None:
        self.chords = (self.chords + [bar_chord or "N"])[-self.memory_bars:]
        self.bars_seen += 1
        if self.first_chord is None and bar_chord in _CHORDS:
            self.first_chord = _CHORDS[bar_chord]
        if bar_chroma is not None and bar_chroma.sum() > 0:
            self.chroma = self.chroma * self.decay + bar_chroma / bar_chroma.sum()
        scores = self.scores()
        if not scores:
            return None
        ranked = sorted(scores, key=scores.get, reverse=True)
        best, second = ranked[0], ranked[1]
        if self.key is None:
            self.key = best
        elif best != self.key:
            if scores[best] - scores[self.key] >= self.switch_margin:
                n = self._challenger[1] + 1 if self._challenger and self._challenger[0] == best else 1
                self._challenger = (best, n)
                if n >= self.switch_bars:
                    self.key, self._challenger = best, None
            else:
                self._challenger = None
        else:
            self._challenger = None
        margin = scores[self.key] - max(scores[k] for k in scores if k != self.key)
        heard = sum(c != "N" for c in self.chords)
        self.confidence = float(np.clip(0.5 + 4 * margin, 0, 1)) if heard >= 3 else 0.3
        return (*self.key, self.confidence)

    def scores(self) -> dict[tuple[int, str], float]:
        """Puntuación 0..1 aprox. de cada una de las 24 tonalidades."""
        n = len(self.chords)
        heard = [(i, _CHORDS[c]) for i, c in enumerate(self.chords) if c != "N" and c in _CHORDS]
        if not heard and self.chroma.sum() == 0:
            return {}
        # Más peso a lo reciente y a los compases que abren frase (donde suele estar la tónica).
        w = np.array([self.decay ** (n - 1 - i) for i, _ in heard])
        starts = np.array([1.5 if i % self.bars_per_phrase == 0 else 1.0 for i, _ in heard])
        out = {}
        for key in _KEYS:
            if heard:
                fit = float(sum(wi for wi, (_, ch) in zip(w, heard) if ch in _DIATONIC[key]) / w.sum())
                tw = w * starts
                tonic = float(sum(wi for wi, (_, ch) in zip(tw, heard) if ch in _tonic_chords(*key)) / tw.sum())
                # Se suele empezar en la tónica; la pista caduca para poder seguir modulaciones.
                if self.bars_seen <= 8 and self.first_chord in _tonic_chords(*key):
                    tonic += 0.15
            else:
                fit = tonic = 0.0
            if self.chroma.sum() > 0:
                profile = theory._MAJOR_PROFILE if key[1] == "major" else theory._MINOR_PROFILE
                corr = float(np.corrcoef(self.chroma, np.roll(profile, key[0]))[0, 1])
            else:
                corr = 0.0
            chord_weight = 1.0 if len(heard) >= 2 else 0.3
            out[key] = chord_weight * (0.55 * fit + 0.3 * tonic) + 0.15 * (corr + 1) / 2
        return out


def key_from_chords(chords: list[str], chromas: list[np.ndarray] | None = None) -> tuple[int, str, float] | None:
    """Tonalidad de una secuencia completa (para revisar sesiones)."""
    kt = KeyTracker(memory_bars=max(16, len(chords)), decay=1.0)
    result = None
    for i, c in enumerate(chords):
        result = kt.update(c, chromas[i] if chromas else None)
    return result
