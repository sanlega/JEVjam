"""Teoría musical mínima: clases de altura, acordes, tonalidades y voicings."""
from __future__ import annotations

import numpy as np

PC_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]

# Intervalos de cada calidad de acorde (en semitonos desde la fundamental).
CHORD_QUALITIES = {
    "maj": (0, 4, 7),
    "min": (0, 3, 7),
    "7": (0, 4, 7, 10),
    "min7": (0, 3, 7, 10),
    "maj7": (0, 4, 7, 11),
}

# Perfiles de Krumhansl-Kessler para estimar la tonalidad.
_MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

SEVENTH_PENALTY = 0.12  # los armónicos imitan séptimas: solo se eligen si mejoran claramente

MAJOR_SCALE = (0, 2, 4, 5, 7, 9, 11)
MINOR_SCALE = (0, 2, 3, 5, 7, 8, 10)  # menor natural


def chord_name(root: int, quality: str) -> str:
    suffix = {"maj": "", "min": "m", "7": "7", "min7": "m7", "maj7": "maj7"}[quality]
    return PC_NAMES[root % 12] + suffix


# Serie armónica en semitonos (armónicos 1..6) y su peso relativo en un croma de energía.
# Modelarla en las plantillas evita que el 3.er armónico de la tercera (p. ej. B → F# en G)
# se lea como una séptima mayor.
_HARMONICS = ((0, 1.0), (12, 0.6), (19, 0.36), (24, 0.22), (28, 0.13), (31, 0.08))


def _templates() -> tuple[np.ndarray, list[tuple[int, str]]]:
    rows, labels = [], []
    for quality, ivs in CHORD_QUALITIES.items():
        for root in range(12):
            t = np.zeros(12)
            for i, iv in enumerate(ivs):
                w = 1.0 if i < 3 else 0.7  # la séptima pesa menos
                for h, hw in _HARMONICS:
                    t[(root + iv + h) % 12] += w * hw
            rows.append(t / np.linalg.norm(t))
            labels.append((root, quality))
    return np.array(rows), labels


_TEMPLATES, _TEMPLATE_LABELS = _templates()


def detect_chord(chroma: np.ndarray, min_similarity: float = 0.7,
                 allowed: set[tuple[int, str]] | None = None) -> tuple[int, str, float] | None:
    """Acorde más parecido a un croma (12 bins). None si no hay acorde claro.

    `allowed` restringe los candidatos (p. ej. a los acordes de una tonalidad fija).
    """
    norm = np.linalg.norm(chroma)
    if norm < 1e-9:
        return None
    sims = _TEMPLATES @ (chroma / norm)
    # Preferimos tríadas salvo que la séptima mejore claramente el ajuste.
    penalty = np.array([0.0 if len(CHORD_QUALITIES[q]) == 3 else SEVENTH_PENALTY for _, q in _TEMPLATE_LABELS])
    if allowed is not None:
        penalty = penalty + np.array([0.0 if lbl in allowed else np.inf for lbl in _TEMPLATE_LABELS])
    best = int(np.argmax(sims - penalty))
    if sims[best] < min_similarity:
        return None
    root, quality = _TEMPLATE_LABELS[best]
    return root, quality, float(sims[best])


def chord_candidates(chroma: np.ndarray, k: int = 3,
                     allowed: set[tuple[int, str]] | None = None) -> list[tuple[str, float]]:
    """Los `k` acordes más parecidos con su similitud (para revisar sesiones)."""
    norm = np.linalg.norm(chroma)
    if norm < 1e-9:
        return []
    sims = _TEMPLATES @ (chroma / norm)
    order = [i for i in np.argsort(sims)[::-1] if allowed is None or _TEMPLATE_LABELS[i] in allowed]
    return [(chord_name(*_TEMPLATE_LABELS[i]), round(float(sims[i]), 3)) for i in order[:k]]


def detect_key(chroma_hist: np.ndarray) -> tuple[int, str, float] | None:
    """Tonalidad (tónica, 'major'|'minor', correlación) por Krumhansl-Schmuckler."""
    if chroma_hist.sum() < 1e-9:
        return None
    best = None
    for mode, profile in (("major", _MAJOR_PROFILE), ("minor", _MINOR_PROFILE)):
        for tonic in range(12):
            r = float(np.corrcoef(chroma_hist, np.roll(profile, tonic))[0, 1])
            if best is None or r > best[2]:
                best = (tonic, mode, r)
    return best


_PC_ALIASES = {"DB": 1, "D#": 3, "GB": 6, "G#": 8, "A#": 10, "CB": 11, "E#": 5, "FB": 4, "B#": 0}


def parse_key(text: str) -> tuple[int, str]:
    """'A minor', 'Am', 'a', 'F# major', 'Bbm', 'C' → (tónica, modo)."""
    t = text.strip().replace("♯", "#").replace("♭", "b")
    low = t.lower()
    mode = "minor" if low.endswith(("minor", "min", "menor")) or (low.endswith("m") and not low.endswith("major")) \
        else "major"
    name = t.split()[0] if " " in t else t
    for suffix in ("minor", "major", "mayor", "menor", "min", "maj", "m"):
        if name.lower().endswith(suffix) and len(name) > len(suffix):
            name = name[: -len(suffix)]
            break
    name = name[0].upper() + name[1:]
    names = {n.upper(): i for i, n in enumerate(PC_NAMES)} | _PC_ALIASES
    if name.upper() not in names:
        raise ValueError(f"tonalidad no reconocida: {text!r} (ejemplos: 'A minor', 'Am', 'C', 'F# major')")
    return names[name.upper()], mode


def diatonic_chords(tonic: int, mode: str) -> set[tuple[int, str]]:
    """Acordes diatónicos (tríadas y cuatriadas); en menor, también V y V7 (menor armónica)."""
    scale = scale_pcs(tonic, mode)
    out: set[tuple[int, str]] = set()
    for i, root in enumerate(scale):
        third, fifth, seventh = (scale[(i + k) % 7] for k in (2, 4, 6))
        ivs = ((third - root) % 12, (fifth - root) % 12, (seventh - root) % 12)
        for quality, q_ivs in CHORD_QUALITIES.items():
            if q_ivs[1:3] == ivs[:2] and (len(q_ivs) == 3 or q_ivs[3] == ivs[2]):
                out.add((root, quality))
    if mode == "minor":
        dominant = (tonic + 7) % 12
        out |= {(dominant, "maj"), (dominant, "7")}
    return out


def key_name(tonic: int, mode: str) -> str:
    return f"{PC_NAMES[tonic]} {mode}"


def scale_pcs(tonic: int, mode: str) -> list[int]:
    return [(tonic + s) % 12 for s in (MAJOR_SCALE if mode == "major" else MINOR_SCALE)]


def chord_pcs(root: int, quality: str) -> list[int]:
    return [(root + iv) % 12 for iv in CHORD_QUALITIES[quality]]


def nearest_voicing(pcs: list[int], previous: list[int] | None, low: int = 55, high: int = 74) -> list[int]:
    """Voicing cerrado de `pcs` dentro de [low, high] con mínimo movimiento respecto a `previous`."""
    candidates = []
    for inversion in range(len(pcs)):
        order = pcs[inversion:] + pcs[:inversion]
        for base in range(low, high):
            if base % 12 != order[0]:
                continue
            notes, cur = [], base
            for pc in order:
                while cur % 12 != pc:
                    cur += 1
                notes.append(cur)
                cur += 1
            if notes[-1] <= high:
                candidates.append(notes)
    if not candidates:
        return [low + ((pc - low) % 12) for pc in pcs]
    if not previous:
        center = (low + high) / 2
        return min(candidates, key=lambda n: abs(np.mean(n) - center))
    return min(candidates, key=lambda n: sum(min(abs(a - b) for b in previous) for a in n))


def midi_to_hz(note: float) -> float:
    return 440.0 * 2 ** ((note - 69) / 12)
