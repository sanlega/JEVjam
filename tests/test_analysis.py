"""Análisis musical sobre audio sintético reproducible (sin red)."""
import pytest

from jevjam import theory
from jevjam.analysis import Analyzer
from jevjam.sources import render_human

SR = 48000

CASES = [
    (["Am", "F", "C", "G"], 100),
    (["C", "G", "Am", "F"], 128),
    (["E", "A", "B", "E"], 150),
    (["F", "Bb", "C7", "F"], 96),
    (["Gm", "Eb", "Bb", "F"], 84),
]


def analyse(prog, bpm):
    audio = render_human(prog, bpm, sr=SR, repeats=2)
    an, beat, pos, got = Analyzer(sr=SR), 60 / bpm, 0, []
    for bar in range(len(prog) * 2):
        end = int((bar * 4 + 3) * beat * SR)  # consultamos en el pulso 4 de cada compás
        an.feed(audio[pos:end])
        pos = end
        s = an.snapshot()
        got.append(theory.chord_name(*s.chord[:2]) if s.chord else "N")
    an.feed(audio[pos:])
    return an.snapshot(), got


@pytest.mark.parametrize("prog,bpm", CASES)
def test_tempo_and_chords(prog, bpm):
    snap, chords = analyse(prog, bpm)
    assert snap.bpm == pytest.approx(bpm, rel=0.03)
    assert chords == prog * 2


def test_key_of_diatonic_progression():
    snap, _ = analyse(["F", "Bb", "C7", "F"], 96)
    assert theory.key_name(*snap.key[:2]) == "F major"


def test_silence_is_detected():
    import numpy as np

    an = Analyzer(sr=SR)
    an.feed(np.zeros(SR * 3, dtype=np.float32))
    snap = an.snapshot()
    assert snap.chord is None and snap.silence_seconds > 2.5


@pytest.mark.parametrize("text,expected", [
    ("A minor", (9, "minor")), ("Am", (9, "minor")), ("a menor", (9, "minor")), ("C", (0, "major")),
    ("F# major", (6, "major")), ("Bbm", (10, "minor")), ("Eb", (3, "major")), ("Db major", (1, "major")),
])
def test_parse_key(text, expected):
    assert theory.parse_key(text) == expected


def test_parse_key_rejects_garbage():
    with pytest.raises(ValueError):
        theory.parse_key("H minor")


def test_diatonic_chords():
    c_major = {theory.chord_name(*c) for c in theory.diatonic_chords(0, "major")}
    assert {"C", "Dm", "Em", "F", "G", "Am", "G7", "Cmaj7", "Dm7"} <= c_major
    assert not {"C#m", "E", "Bb"} & c_major
    a_minor = {theory.chord_name(*c) for c in theory.diatonic_chords(9, "minor")}
    assert {"Am", "Dm", "Em", "E", "E7", "F", "G", "C"} <= a_minor


def test_fixed_key_restricts_chords_and_sets_key():
    audio = render_human(["E", "A", "B", "E"], 150, sr=SR, repeats=1)
    an = Analyzer(sr=SR, fixed_key=(4, "major"))
    an.feed(audio)
    snap = an.snapshot()
    assert snap.key[:2] == (4, "major")
    allowed = theory.diatonic_chords(4, "major")
    assert snap.chord is None or (snap.chord[0], snap.chord[1]) in allowed


from jevjam.keyfinder import KeyTracker  # noqa: E402

KEY_CASES = {
    ("C", "G", "F", "G"): "C major",  # el croma solo dice G mayor (sesión real 2026-09-30 15:09)
    ("Am", "F", "C", "G"): "A minor", ("C", "Am", "F", "G"): "C major",
    ("E", "A", "B", "E"): "E major", ("Dm", "G", "C", "C"): "C major", ("F", "Bb", "C7", "F"): "F major",
    ("Gm", "Eb", "Bb", "F"): "G minor", ("Em", "C", "D", "Bm"): "E minor", ("G", "D", "Em", "C"): "G major",
    ("Am", "Dm", "E7", "Am"): "A minor", ("D", "A", "Bm", "G"): "D major",
}


@pytest.mark.parametrize("prog,expected", KEY_CASES.items())
def test_key_from_chords(prog, expected):
    kt = KeyTracker()
    for i in range(12):
        result = kt.update(prog[i % 4])
    assert theory.key_name(*result[:2]) == expected


@pytest.mark.parametrize("before,after,expected", [
    (["C", "G", "F", "G"], ["D", "A", "G", "A"], "D major"),
    (["Am", "F", "C", "G"], ["Em", "C", "D", "Bm"], "E minor"),
    (["C", "Am", "F", "G"], ["F", "Dm", "Bb", "C"], "F major"),
])
def test_key_follows_modulation_within_six_bars(before, after, expected):
    kt = KeyTracker()
    keys = [theory.key_name(*kt.update(c)[:2]) for c in before * 3 + after * 3]
    assert all(k == expected for k in keys[12 + 6:])


def test_key_ignores_unclear_bars():
    kt = KeyTracker()
    for c in ["C", "N", "F", "G", "N", "C", "F", "G"]:
        result = kt.update(c)
    assert theory.key_name(*result[:2]) == "C major"


def test_level_meter_reports_rms_and_peak_every_interval():
    import numpy as np

    from jevjam.analysis import LevelMeter

    m = LevelMeter(sr=48000, interval=0.05)  # un valor cada 2400 muestras
    sine = (0.5 * np.sin(2 * np.pi * 440 * np.arange(2400) / 48000)).astype(np.float32)
    assert m.feed(sine[:1200]) is None
    level = m.feed(sine[1200:])
    assert level["peak_db"] == pytest.approx(-6.0, abs=0.1)  # 0,5 de pico
    assert level["rms_db"] == pytest.approx(-9.0, abs=0.2)   # seno: pico - 3 dB
    silent = m.feed(np.zeros(2400, dtype=np.float32))
    assert silent["rms_db"] < -100


def test_guitar_e_major_with_loud_low_string_is_recognized():
    # Regresión (jam real 2026-09-30 16:31): con croma de energía, la cuerda de Mi grave tapaba
    # al G# y el E salía como "sin acorde" en 5/5 compases.
    import numpy as np

    t = np.arange(int(SR * 2.4)) / SR
    voicing = {40: 3.0, 47: 1.0, 52: 1.0, 56: 0.35, 59: 0.8, 64: 0.7}  # E2 B2 E3 G#3 B3 E4
    audio = sum(a * np.exp(-t * 1.5) * sum(np.sin(2 * np.pi * theory.midi_to_hz(n) * h * t) / h ** 1.5
                                           for h in (1, 2, 3, 4))
                for n, a in voicing.items())
    an = Analyzer(sr=SR)
    an.feed((0.05 * audio).astype(np.float32))
    ch = an.chord_of(an.take_window().chroma)
    assert ch and theory.chord_name(*ch[:2]) == "E"


@pytest.mark.parametrize("bars,key,expected,name", [
    (["F", "E"], (9, "minor"), "Am", "Andalusian"),            # jam real 2026-09-30 16:31
    (["F", "E", "Am"], (9, "minor"), "G", "Andalusian"),
    (["C", "G", "F"], (0, "major"), "G", "I-V-IV-V"),        # jam real 2026-09-30 15:09
    (["C", "G", "Am"], (0, "major"), "F", "pop"),
    (["Dm", "G"], (0, "major"), "C", "ii-V-I"),
    (["F", "N", "Am", "G"], (9, "minor"), "F", "Andalusian"),  # un compás sin reconocer no rompe la secuencia
])
def test_anticipate_common_progressions(bars, key, expected, name):
    chord, confidence, progression = theory.anticipate_chord(bars, *key)
    assert chord == expected and confidence >= 0.6 and name in progression


def test_anticipation_is_humble_when_ambiguous():
    chord, confidence, _ = theory.anticipate_chord(["C", "G"], 0, "major")
    assert confidence < 0.6  # I-V puede seguir de muchas formas: mejor esperar


def test_anticipation_follows_slow_harmonic_rhythm():
    assert theory.anticipate_chord(["C", "C", "G", "G", "Am"], 0, "major")[0] == "Am"  # 2 compases por acorde


def test_no_anticipation_without_history():
    assert theory.anticipate_chord(["C"], 0, "major") is None
    assert theory.anticipate_chord(["C", "G", "N"], 0, "major") is None
