"""Pregunta y respuesta: dónde deja huecos el humano y en qué registro toca.

En la improvisación en grupo se responde en los silencios del otro (call and response,
trading fours) y en otro registro, y el acompañante se retira cuando el solista es denso.
Aquí el código escucha, pulso a pulso, si el humano deja espacio (no ataca y su sonido se
apaga) y aprende su patrón de huecos en los últimos compases; la frase de respuesta del
teclado se coloca en esos pulsos y lejos de su registro. Jev recibe el fraseo en palabras
para decidir si responder tiene sentido.
"""
from __future__ import annotations

from collections import deque

import numpy as np

from .analysis import Window


def beat_gaps(windows: list[Window], drop_db: float = 8.0, strong_drop_db: float = 15.0,
              silence_db: float = -50.0) -> list[bool]:
    """Hueco = el sonido del humano se ha apagado bastante respecto a su pulso más fuerte.

    Cuenta sobre todo la caída de nivel: un rasgueo que se deja sonar cae 20-30 dB en el
    compás y el detector de ataques ve pequeños picos en la cola que no son notas nuevas
    (jam real 2026-09-30 16:31). Con caída moderada, hace falta además que no haya ataques.
    """
    if not windows:
        return []
    loudest = max(w.rms_db for w in windows)
    return [w.rms_db < silence_db or w.rms_db <= loudest - strong_drop_db
            or (w.onsets == 0 and w.rms_db < loudest - drop_db) for w in windows]


class GapProfile:
    """Patrón de huecos por posición de pulso en los últimos compases."""

    def __init__(self, beats_per_bar: int = 4, memory_bars: int = 4):
        self.bpb = beats_per_bar
        self.bars: deque[list[bool]] = deque(maxlen=memory_bars)
        self.registers: deque[float] = deque(maxlen=memory_bars * beats_per_bar)

    def add_bar(self, windows: list[Window]) -> list[bool]:
        gaps = beat_gaps(windows)
        if len(gaps) == self.bpb:
            self.bars.append(gaps)
        for w, g in zip(windows, gaps):
            if not g and w.register is not None:
                self.registers.append(w.register)
        return gaps

    def fractions(self) -> list[float]:
        if not self.bars:
            return [0.0] * self.bpb
        return [float(np.mean([bar[i] for bar in self.bars])) for i in range(self.bpb)]

    def answer_beats(self, min_fraction: float = 0.5, min_bars: int = 2) -> list[int]:
        """Pulsos donde el humano suele dejar espacio (donde encaja una respuesta)."""
        if len(self.bars) < min_bars:
            return []
        return [i for i, f in enumerate(self.fractions()) if f >= min_fraction]

    def register(self) -> float | None:
        return float(np.median(self.registers)) if self.registers else None

    def phrasing_words(self) -> str:
        """El fraseo del humano en palabras (para el estado de Jev)."""
        if len(self.bars) < 2:
            return "not enough history yet"
        fr = self.fractions()
        if min(fr) >= 0.75:
            return "mostly silent, leaving the whole bar empty"
        gaps = self.answer_beats()
        if not gaps:
            return "playing continuously, without leaving gaps"
        if gaps == list(range(self.bpb - len(gaps), self.bpb)):
            return "plays at the start of each bar and leaves space at the end, inviting an answer"
        return "leaves gaps on some beats of each bar"

    def last_bar_words(self) -> str:
        if not self.bars:
            return "unknown"
        last = self.bars[-1]
        if all(last):
            return "left the whole last bar empty"
        if last[-1] and last[-2]:
            return "just left a gap at the end of the bar"
        return "kept playing through the bar"


def answer_register(human_register: float | None, low: tuple[int, int] = (55, 67),
                    high: tuple[int, int] = (67, 84)) -> tuple[int, int]:
    """Rango MIDI para responder lejos del humano: encima si toca grave, debajo si toca agudo."""
    if human_register is None:
        return high
    return low if human_register >= 64 else high
