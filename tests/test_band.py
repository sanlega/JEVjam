"""Músicos, contexto, predicción de acordes y planificador MIDI (sin red)."""
import time

from jevjam import theory
from jevjam.analysis import Snapshot
from jevjam.band import BASS_CH, KEYS_CH, Band, Harmony
from jevjam.brain import AGENT_OPTIONS, build_questions
from jevjam.conductor import predict_next_chord
from jevjam.context import BandMemory, build_state
from jevjam.midi_out import Recorder, Scheduler

H = Harmony(root=9, quality="min", key_tonic=0, key_mode="major")  # Am en Do


def all_parts():
    for d in AGENT_OPTIONS["drums"]:
        for b in AGENT_OPTIONS["bass"]:
            for k in AGENT_OPTIONS["keys"]:
                yield {"drums": d, "bass": b, "keys": k}


def test_every_option_renders_inside_the_bar():
    band = Band()
    for bar, parts in enumerate(all_parts()):
        for e in band.render_bar(bar, parts, 3.0, H, None, 4, False):
            assert 0 <= e.beat < 4 and e.dur > 0 and 1 <= e.velocity <= 127 and 0 <= e.note <= 127


def test_harmonic_parts_fit_chord_or_key():
    band = Band()
    chord, scale = set(theory.chord_pcs(9, "min")), set(theory.scale_pcs(0, "major"))
    for part in ("roots_whole", "roots_pulse", "octaves"):
        ev = band.render_bar(1, {"bass": part}, 3.0, H, None, 4, False)
        assert {e.note % 12 for e in ev if e.channel == BASS_CH} <= chord
    for part in ("pads", "comping", "arpeggio"):
        ev = band.render_bar(1, {"keys": part}, 3.0, H, None, 4, False)
        assert {e.note % 12 for e in ev if e.channel == KEYS_CH} <= chord
    ev = band.render_bar(1, {"keys": "answer_phrase"}, 3.0, H, None, 4, False)
    assert {e.note % 12 for e in ev} <= scale


def test_render_is_deterministic_per_bar():
    parts = {"drums": "groove", "bass": "walking", "keys": "comping"}
    assert Band().render_bar(5, parts, 3, H, None, 4, False) == Band().render_bar(5, parts, 3, H, None, 4, False)


def test_silent_energy_plays_nothing():
    assert Band().render_bar(0, {"drums": "driving", "bass": "octaves", "keys": "pads"}, 0.2, H, None, 4, False) == []


def test_predict_next_chord_from_repeated_progression():
    assert predict_next_chord(["Am", "F", "C", "G"] * 2) == "Am"
    assert predict_next_chord(["Am", "F"]) is None


def test_predict_tolerates_unclear_bars():
    assert predict_next_chord(["Am", "F", "N", "G", "Am", "F", "C", "G"]) == "Am"


def test_predict_does_not_stick_to_a_stale_chord():
    # Regresión (sesión 2026-09-30 14:48): al descartar los "N" se quedaba en F para siempre.
    assert predict_next_chord(["F", "N", "N", "N", "N", "N", "N", "N"]) is None
    assert predict_next_chord(["F", "F", "Am", "C", "G", "Am", "F", "C"]) is None


def test_predict_vamp():
    assert predict_next_chord(["N", "C", "C", "C"]) == "C"


def test_relative_descriptors_ignore_mic_gain():
    from jevjam.context import relative_density, relative_loudness

    quiet_mic = [-48, -47, -48, -47, -41]  # micro muy bajo, pero el último compás es claramente más fuerte
    assert relative_loudness(quiet_mic) == "the loudest moment of the jam so far"
    assert relative_loudness([-20, -20, -21, -20, -20.5]) == "about as loud as usual"
    assert relative_loudness([-20, -20]) == "not enough history yet"
    assert relative_density([2, 2, 2, 2, 4]) == "many more notes than usual"
    assert relative_density([2, 2, 2, 2, 1.5]) == "fewer notes than usual"
    assert relative_density([2, 2, 2, 2, 1]) == "far fewer notes than usual"


def test_state_uses_words_not_raw_numbers():
    snap = Snapshot(time=10, bpm=101.7, tempo_confidence=0.9, beat_phase_time=9.5, key=(0, "major", 0.8),
                    chord=(9, "min", 0.9), chord_history=["Am"] * 8, rms_db=-25, rms_trend_db=7,
                    onsets_per_second=4, silence_seconds=0)
    s = build_state(snap, BandMemory())
    hp = s["human_player"]
    assert hp["tempo"].startswith("medium") and hp["key"] == "C major" and hp["current_chord"] == "Am"
    assert hp["loudness_trend"] == "getting much louder" and hp["loudness"] == "medium"


def test_questions_cover_every_agent():
    q = build_questions()
    assert {f"{a}_part" for a in AGENT_OPTIONS} <= set(q)


def test_scheduler_timing_and_note_offs():
    rec = Recorder()
    sch = Scheduler([rec])
    t0 = time.monotonic() + 0.05
    for i in range(10):
        sch.note(t0 + i * 0.02, 0.01, 0, 60 + i, 100)
    time.sleep(0.4)
    sch.close()
    ons = [(t, m) for t, m in rec.events if m.type == "note_on" and m.velocity > 0]
    offs = [m for _, m in rec.events if m.type == "note_off"]
    assert len(ons) == 10 and len(offs) >= 10
    assert max(abs(t - (t0 + i * 0.02)) for i, (t, _) in enumerate(ons)) < 0.005


def _conductor(fixed_key=None, bar_chords=()):
    import numpy as np

    from jevjam.analysis import Analyzer, Window
    from jevjam.conductor import Beat, Conductor

    c = Conductor.__new__(Conductor)
    c.bpb, c._last_harmony = 4, None
    c.analyzer = Analyzer(fixed_key=fixed_key)
    from jevjam.keyfinder import KeyTracker

    c.key_tracker = None if fixed_key else KeyTracker()
    chroma = {"C": [0, 4, 7], "F": [5, 9, 0], "G": [7, 11, 2], "Am": [9, 0, 4]}
    c.beats = []
    for name in bar_chords:
        v = np.zeros(12)
        v[chroma[name]] = 1.0 if name != "N" else 0
        c.beats += [Beat(name, Window(v, -20.0, 1, 0.6))] * 4
    return c


def test_harmony_waits_then_falls_back_to_tonic_with_fixed_key():
    c = _conductor(fixed_key=(0, "major"))
    assert c._harmony(bar=1)[1] == "waiting"
    h, mode = c._harmony(bar=4)
    assert mode == "tonic" and (h.root, h.quality) == (0, "maj")


def test_harmony_follows_last_heard_chord_after_patience():
    c = _conductor(bar_chords=["C", "F"])
    assert c._harmony(bar=2)[1] == "waiting"
    h, mode = c._harmony(bar=4)
    assert mode == "following" and theory.chord_name(h.root, h.quality) == "F"


def test_harmony_prefers_prediction():
    h, mode = _conductor(bar_chords=["C", "F", "G", "Am"] * 2)._harmony(bar=8)
    assert mode == "predicted" and theory.chord_name(h.root, h.quality) == "C"
