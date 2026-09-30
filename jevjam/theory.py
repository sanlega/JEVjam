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
        raise ValueError(f"unrecognised key: {text!r} (examples: 'A minor', 'Am', 'C', 'F# major')")
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


# ------------------------------------------------------------ armonía funcional
# Probabilidad del grado siguiente dado el actual, a mano a partir de la práctica común y
# del pop/rock (V→I, IV→V, ii→V, VII→i…). No pretende ser exacta: es un prior que Jev afina.
# Grados como semitonos sobre la tónica + calidad.
_MAJOR_DEGREES = {"I": (0, "maj"), "ii": (2, "min"), "iii": (4, "min"), "IV": (5, "maj"), "V": (7, "maj"),
                  "vi": (9, "min")}
_MINOR_DEGREES = {"i": (0, "min"), "III": (3, "maj"), "iv": (5, "min"), "v": (7, "min"), "V": (7, "maj"),
                  "VI": (8, "maj"), "VII": (10, "maj")}
_MAJOR_NEXT = {
    "I": {"IV": .30, "V": .28, "vi": .20, "ii": .10, "iii": .05, "I": .07},
    "ii": {"V": .55, "IV": .10, "I": .10, "vi": .10, "iii": .05, "ii": .10},
    "iii": {"vi": .40, "IV": .30, "ii": .10, "I": .10, "V": .05, "iii": .05},
    "IV": {"V": .35, "I": .30, "vi": .15, "ii": .05, "iii": .05, "IV": .10},
    "V": {"I": .50, "vi": .25, "IV": .15, "ii": .03, "iii": .02, "V": .05},
    "vi": {"IV": .40, "V": .20, "ii": .15, "I": .10, "iii": .10, "vi": .05},
}
_MINOR_NEXT = {
    "i": {"iv": .22, "VI": .20, "VII": .20, "V": .15, "III": .10, "v": .05, "i": .08},
    "iv": {"V": .25, "i": .25, "VII": .20, "VI": .10, "III": .05, "v": .05, "iv": .10},
    "v": {"i": .40, "VI": .25, "iv": .15, "VII": .10, "v": .10},
    "V": {"i": .60, "VI": .20, "iv": .10, "VII": .05, "V": .05},
    "VI": {"VII": .28, "V": .18, "iv": .15, "III": .14, "i": .15, "VI": .10},
    "VII": {"i": .30, "III": .30, "VI": .15, "V": .10, "iv": .10, "VII": .05},
    "III": {"VI": .30, "VII": .20, "iv": .20, "i": .15, "V": .10, "III": .05},
}


def degrees(tonic: int, mode: str) -> dict[str, tuple[int, str]]:
    """Grado (numeral romano) → (fundamental, calidad) de los acordes de la tonalidad."""
    table = _MAJOR_DEGREES if mode == "major" else _MINOR_DEGREES
    return {deg: ((tonic + iv) % 12, q) for deg, (iv, q) in table.items()}


def degree_of(root: int, quality: str, tonic: int, mode: str) -> str | None:
    """Grado de un acorde en la tonalidad (las cuatriadas cuentan como su tríada)."""
    triad = "min" if quality in ("min", "min7") else "maj"
    for deg, (r, q) in degrees(tonic, mode).items():
        if r == root % 12 and q == triad:
            return deg
    return None


def next_chord_prior(current: str | None, tonic: int, mode: str, p_stay: float = 0.1) -> dict[str, float]:
    """Distribución del acorde del próximo compás (nombres de acorde) según la armonía funcional.

    `p_stay` es la probabilidad de repetir acorde (se estima del ritmo armónico del humano:
    si cambia cada dos compases, repetir es tan probable como cambiar).
    """
    degs = degrees(tonic, mode)
    names = {deg: chord_name(r, q) for deg, (r, q) in degs.items()}
    table = _MAJOR_NEXT if mode == "major" else _MINOR_NEXT
    cur_deg = None
    if current:
        parsed = parse_chord(current)
        cur_deg = degree_of(*parsed, tonic, mode) if parsed else None
    if cur_deg is None:  # sin acorde actual en la tonalidad: tónica y dominante lo más probable
        base = {deg: 1.0 for deg in degs}
        base[next(iter(degs))] = 3.0
        dist = {names[d]: w for d, w in base.items()}
    else:
        moves = {d: p for d, p in table[cur_deg].items() if d != cur_deg}
        total = sum(moves.values())
        dist = {names[d]: (1 - p_stay) * p / total for d, p in moves.items()}
        dist[names[cur_deg]] = dist.get(names[cur_deg], 0.0) + p_stay
    for name in names.values():
        dist.setdefault(name, 0.01)
    s = sum(dist.values())
    return {k: v / s for k, v in dist.items()}


def parse_chord(name: str) -> tuple[int, str] | None:
    for q in CHORD_QUALITIES:
        for r in range(12):
            if chord_name(r, q) == name:
                return r, q
    return None


# Progresiones habituales (en grados, un acorde por compás), con un peso de popularidad
# aproximado. Se comparan en todas sus rotaciones: un músico puede empezar en cualquier punto.
COMMON_PROGRESSIONS: dict[str, tuple[tuple[str, ...], float]] = {
    # mayor
    "pop (I-V-vi-IV)": (("I", "V", "vi", "IV"), 1.0),
    "doo-wop (I-vi-IV-V)": (("I", "vi", "IV", "V"), 0.7),
    "I-IV-V-IV": (("I", "IV", "V", "IV"), 0.6),
    "I-V-IV-V": (("I", "V", "IV", "V"), 0.5),
    "I-IV-vi-V": (("I", "IV", "vi", "V"), 0.5),
    "I-IV-I-V": (("I", "IV", "I", "V"), 0.5),
    "ii-V-I-I": (("ii", "V", "I", "I"), 0.5),
    "I-vi-ii-V": (("I", "vi", "ii", "V"), 0.5),
    "I-iii-IV-V": (("I", "iii", "IV", "V"), 0.3),
    "I-IV (vamp)": (("I", "IV"), 0.5),
    "I-V (vamp)": (("I", "V"), 0.4),
    # (El blues de 12 compases se define por duraciones, no por orden de acordes: pendiente.)
    # menor
    "Andalusian (i-VII-VI-V)": (("i", "VII", "VI", "V"), 0.8),
    "i-VI-III-VII": (("i", "VI", "III", "VII"), 0.8),
    "i-iv-v-i": (("i", "iv", "v", "i"), 0.4),
    "i-iv-V-i": (("i", "iv", "V", "i"), 0.5),
    "i-VI-VII-i": (("i", "VI", "VII", "i"), 0.5),
    "i-VII-VI-VII": (("i", "VII", "VI", "VII"), 0.5),
    "i-iv-VII-III": (("i", "iv", "VII", "III"), 0.4),
    "i-VI-iv-V": (("i", "VI", "iv", "V"), 0.4),
    "i-iv (vamp)": (("i", "iv"), 0.4),
    "i-VII (vamp)": (("i", "VII"), 0.4),
}


def _events(bars: list[str]) -> tuple[list[str | None], list[int]]:
    """Compases → acordes con su duración en compases. Un compás "N" es un comodín (None):
    ocupa su sitio en la secuencia pero no sabemos qué acorde era."""
    chords: list[str | None] = []
    lengths: list[int] = []
    for c in bars:
        if c == "N":
            chords.append(None)
            lengths.append(1)
        elif chords and c == chords[-1]:
            lengths[-1] += 1
        else:
            chords.append(c)
            lengths.append(1)
    return chords, lengths


def anticipate_chord(bars: list[str], tonic: int, mode: str, min_events: int = 2) -> tuple[str, float, str] | None:
    """Acorde del próximo compás reconociendo progresiones habituales.

    Devuelve (acorde, confianza 0..1, nombre de la progresión) o None si no hay base.
    Sigue el ritmo armónico: si el humano mantiene cada acorde N compases, predice
    "el mismo" hasta completar la duración habitual.
    """
    chords, lengths = _events(bars)
    if sum(c is not None for c in chords) < min_events or chords[-1] is None:
        return None
    # Ritmo armónico: duración típica de los acordes ya completos (el último sigue sonando).
    done = [n for c, n in zip(chords[:-1], lengths[:-1]) if c is not None] or [1]
    typical = sorted(done)[len(done) // 2]
    if lengths[-1] < typical:
        return chords[-1], 0.8, "holding the chord"
    seq = []
    for c in chords[-6:]:
        parsed = parse_chord(c) if c else None
        seq.append(degree_of(*parsed, tonic, mode) if parsed else None)
    table = {deg: chord_name(r, q) for deg, (r, q) in degrees(tonic, mode).items()}
    votes: dict[str, float] = {}
    matched: dict[str, str] = {}
    for name, (prog, weight) in COMMON_PROGRESSIONS.items():
        # Quitamos repeticiones consecutivas (el ritmo armónico ya lo tratamos aparte).
        pattern = [d for i, d in enumerate(prog) if i == 0 or d != prog[i - 1]]
        if len(pattern) > 1 and pattern[0] == pattern[-1]:
            pattern = pattern[:-1]
        if not all(d in table for d in pattern):
            continue
        L = len(pattern)
        for offset in range(L):
            hits = misses = 0
            for j, deg in enumerate(seq):
                expected = pattern[(offset + j) % L]
                if deg is None:
                    continue
                if deg == expected:
                    hits += 1
                else:
                    misses += 1
            if misses or hits < min(min_events, len(seq)):
                continue
            nxt = table[pattern[(offset + len(seq)) % L]]
            score = weight * hits
            if score > votes.get(nxt, 0.0):
                matched[nxt] = name
            votes[nxt] = votes.get(nxt, 0.0) + score
    if not votes:
        return None
    # Desempate musical: si varias progresiones encajan, pesa también la armonía funcional.
    prior = next_chord_prior(chords[-1], tonic, mode, p_stay=0.0)  # chords[-1] no es None (ver arriba)
    fused = {c: v * (0.5 + prior.get(c, 0.0)) for c, v in votes.items()}
    total = sum(fused.values())
    best = max(fused, key=fused.get)
    return best, fused[best] / total, matched[best]


def fuse_distributions(prior: dict[str, float], evidence: dict[str, float] | None,
                       prior_weight: float = 0.5) -> dict[str, float]:
    """Combina prior y opinión de Jev (media geométrica ponderada, renormalizada)."""
    if not evidence:
        return dict(prior)
    keys = set(prior) | set(evidence)
    out = {k: (prior.get(k, 1e-3) ** prior_weight) * (max(evidence.get(k, 0.0), 1e-3)) for k in keys}
    s = sum(out.values())
    return {k: v / s for k, v in out.items()}
