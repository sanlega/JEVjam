"""Pregunta y respuesta: huecos del humano, registro y colocación de la frase (sin audio ni red)."""
import random

import numpy as np

from jevjam.analysis import Window
from jevjam.band import KEYS_CH, Harmony, Keys
from jevjam.dialogue import GapProfile, answer_register, beat_gaps


def w(rms_db, onsets, register=60.0):
    return Window(np.ones(12), rms_db, onsets, 0.6, register)


STRUM_AND_RING = [w(-15, 3), w(-20, 1), w(-30, 0), w(-45, 0)]  # rasgueo en 1-2 y deja sonar 3-4
CONTINUOUS = [w(-18, 2), w(-19, 2), w(-18, 2), w(-19, 2)]


def test_gap_is_no_attack_and_fading_sound():
    assert beat_gaps(STRUM_AND_RING) == [False, False, True, True]
    assert beat_gaps(CONTINUOUS) == [False] * 4


def test_profile_learns_where_the_human_leaves_space():
    g = GapProfile()
    g.add_bar(STRUM_AND_RING)
    assert g.answer_beats() == []  # un compás no basta
    g.add_bar(STRUM_AND_RING)
    assert g.answer_beats() == [2, 3]
    assert "leaves space at the end" in g.phrasing_words()
    assert g.last_bar_words() == "just left a gap at the end of the bar"


def test_continuous_player_gets_no_answer_slots():
    g = GapProfile()
    for _ in range(3):
        g.add_bar(CONTINUOUS)
    assert g.answer_beats() == [] and "without leaving gaps" in g.phrasing_words()


def test_answer_register_avoids_the_human():
    assert answer_register(72.0) == (55, 67)  # humano agudo → respuesta grave
    assert answer_register(55.0) == (67, 84)  # humano grave → respuesta aguda


H = Harmony(root=9, quality="min", key_tonic=0, key_mode="major")


def test_answer_phrase_goes_into_the_gaps_and_register():
    ev = Keys().play("answer_phrase", H, 3.0, 4, random.Random(1), False, answer_beats=[2, 3],
                     register_range=(55, 67))
    assert ev and all(e.channel == KEYS_CH for e in ev)
    assert all(2 <= e.beat < 4 for e in ev)
    assert all(55 <= e.note <= 67 for e in ev)
    assert all(e.beat + e.dur <= 4.0 + 1e-9 for e in ev)  # no invade el compás siguiente


def test_no_gaps_means_the_keys_stay_back():
    ev = Keys().play("answer_phrase", H, 3.0, 4, random.Random(1), False, answer_beats=[])
    assert len(ev) == 1 and ev[0].velocity < 70
