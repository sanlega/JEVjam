"""Músicos: convierten la decisión de Jev en notas MIDI concretas para un compás.

Todo lo que es exacto (qué notas encajan en el acorde, en qué subdivisión caen, la
velocity) es código determinista. Así el resultado es estable y reproducible, y Jev solo
aporta el juicio musical.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from . import theory

DRUM_CH, BASS_CH, KEYS_CH = 9, 0, 1
KICK, SNARE, RIM, HAT, OPEN_HAT, CRASH, TOM_HI, TOM_MID, TOM_LO = 36, 38, 37, 42, 46, 49, 50, 47, 43


@dataclass(frozen=True)
class NoteEvent:
    beat: float  # posición en pulsos desde el inicio del compás
    dur: float  # duración en pulsos
    channel: int
    note: int
    velocity: int


@dataclass
class Harmony:
    """Armonía que la banda usa para el compás (resuelta en código a partir de la escucha)."""

    root: int
    quality: str
    key_tonic: int
    key_mode: str


def _vel(base: float, energy: float, accent: float = 0.0, jitter: random.Random | None = None) -> int:
    v = base * (0.45 + 0.11 * energy) + accent
    if jitter:
        v += jitter.uniform(-6, 6)  # humanización
    return int(max(1, min(127, v)))


def drums(part: str, energy: float, bpb: int, rng: random.Random) -> list[NoteEvent]:
    ev: list[NoteEvent] = []
    add = lambda b, n, v, d=0.1: ev.append(NoteEvent(b, d, DRUM_CH, n, _vel(v, energy, jitter=rng)))
    eighths = [i / 2 for i in range(bpb * 2)]
    if part == "light_time":
        for b in eighths:
            add(b, HAT, 60 if b % 1 == 0 else 45)
        add(0, KICK, 90)
        if bpb >= 3:
            add(2, RIM, 70)
    elif part == "groove":
        for b in eighths:
            add(b, HAT, 80 if b % 1 == 0 else 60)
        for b in range(0, bpb, 2):
            add(b, KICK, 105)
        for b in range(1, bpb, 2):
            add(b, SNARE, 105)
        if rng.random() < 0.3:
            add(bpb - 0.5, KICK, 85)
    elif part == "driving":
        add(0, CRASH, 110, 1.0)
        for b in eighths:
            add(b, OPEN_HAT if b % 1 else HAT, 90)
        for b in range(bpb):
            add(b, KICK, 115)
        for b in range(1, bpb, 2):
            add(b, SNARE, 120)
    elif part == "half_time":
        for b in range(bpb):
            add(b, HAT, 70)
        add(0, KICK, 110)
        add(min(2, bpb - 1), SNARE, 115)
    elif part == "fill":
        for b in range(bpb - 2):
            add(b, HAT, 75)
            add(b, KICK if b % 2 == 0 else SNARE, 100)
        toms = [SNARE, SNARE, TOM_HI, TOM_HI, TOM_MID, TOM_MID, TOM_LO, TOM_LO]
        for i, b in enumerate(x / 4 for x in range((bpb - 2) * 4, bpb * 4)):
            add(b, toms[i % len(toms)], 90 + i * 3)
    return ev


def bass(part: str, h: Harmony, next_root: int | None, energy: float, bpb: int, rng: random.Random) -> list[NoteEvent]:
    root = 36 + (h.root - 36) % 12  # C2..B2
    fifth = root + 7
    ev: list[NoteEvent] = []
    add = lambda b, n, d, v=100: ev.append(NoteEvent(b, d, BASS_CH, n, _vel(v, energy, jitter=rng)))
    if part == "roots_whole":
        add(0, root, bpb - 0.1)
    elif part == "roots_pulse":
        for b in range(bpb):
            add(b, root, 0.85, 105 if b == 0 else 92)
    elif part == "octaves":
        for i in range(bpb * 2):
            add(i / 2, root + (12 if i % 2 else 0), 0.4)
    elif part == "walking":
        scale = sorted({(root + (pc - root) % 12) for pc in theory.scale_pcs(h.key_tonic, h.key_mode)})
        chord = [root + iv for iv in theory.CHORD_QUALITIES[h.quality]]
        line = [root] + chord[1:bpb - 1]
        while len(line) < bpb - 1:
            line.append(rng.choice(scale))
        # Último pulso: nota de aproximación cromática a la siguiente fundamental.
        target = 36 + ((next_root if next_root is not None else h.root) - 36) % 12
        line.append(target + (-1 if rng.random() < 0.5 else 1))
        for b, n in enumerate(line[:bpb]):
            add(b, n, 0.9)
    elif part == "syncopated":
        for b, n, d in ((0, root, 0.75), (0.75, root, 0.25), (1.5, fifth, 0.5), (2.5, root + 12, 0.25),
                        (3, root, 0.5), (3.5, fifth, 0.4)):
            if b < bpb:
                add(b, n, d, 100 if b == 0 else 88)
    return ev


class Keys:
    """Teclado con memoria de voicing para conducir las voces suavemente."""

    def __init__(self):
        self.prev_voicing: list[int] | None = None

    def play(self, part: str, h: Harmony, energy: float, bpb: int, rng: random.Random,
             leave_space: bool) -> list[NoteEvent]:
        pcs = theory.chord_pcs(h.root, h.quality)
        voicing = theory.nearest_voicing(pcs, self.prev_voicing)
        self.prev_voicing = voicing
        ev: list[NoteEvent] = []
        add = lambda b, n, d, v=85: ev.append(NoteEvent(b, d, KEYS_CH, n, _vel(v, energy, jitter=rng)))
        if part == "pads":
            for n in voicing:
                add(0, n, bpb - 0.05, 70)
        elif part == "comping":
            hits = [0.5, 1.5, 2.5, 3.5] if not leave_space else [1.5, 3.5]
            for b in hits:
                if b < bpb and rng.random() < 0.85:
                    for n in voicing:
                        add(b, n, 0.3, 90)
        elif part == "arpeggio":
            seq = voicing + [voicing[0] + 12] + voicing[1:][::-1]
            for i in range(bpb * 2):
                add(i / 2, seq[i % len(seq)], 0.45, 80)
        elif part == "answer_phrase":
            # Frase corta en la escala, anclada en notas del acorde, en la segunda mitad del compás
            # (la primera mitad es del humano: pregunta y respuesta).
            scale = theory.scale_pcs(h.key_tonic, h.key_mode)
            pool = sorted(n for n in range(67, 84) if n % 12 in scale)
            chord_notes = [n for n in pool if n % 12 in pcs]
            start = bpb / 2
            n = rng.choice(chord_notes or pool)
            for i in range(int(bpb / 2 * 2)):
                b = start + i / 2
                if rng.random() < 0.8:
                    add(b, n, 0.45, 95)
                idx = pool.index(n) + rng.choice([-2, -1, 1, 1, 2])
                n = pool[max(0, min(len(pool) - 1, idx))]
            last = min(chord_notes or pool, key=lambda x: abs(x - n))
            ev[-1:] = [NoteEvent(ev[-1].beat, 0.9, KEYS_CH, last, ev[-1].velocity)] if ev else []
        return ev


class Band:
    def __init__(self, seed: int = 7):
        self.keys = Keys()
        self.seed = seed

    def render_bar(self, bar: int, parts: dict[str, str], energy: float, harmony: Harmony,
                   next_root: int | None, bpb: int, leave_space: bool) -> list[NoteEvent]:
        rng = random.Random(self.seed * 100003 + bar)
        if energy < 0.5:
            return []
        ev = drums(parts.get("drums", "tacet"), energy, bpb, rng)
        ev += bass(parts.get("bass", "tacet"), harmony, next_root, energy, bpb, rng)
        ev += self.keys.play(parts.get("keys", "tacet"), harmony, energy, bpb, rng, leave_space)
        return ev
