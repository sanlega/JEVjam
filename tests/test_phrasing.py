"""Fraseo: cambios de papel solo por frases (sin audio ni red)."""
from jevjam.phrasing import PhrasePlanner

SOFT = {"drums": {"light_time": 0.8, "groove": 0.15, "fill": 0.05},
        "bass": {"roots_whole": 0.8, "octaves": 0.2}, "keys": {"pads": 0.9, "comping": 0.1}}
LOUD = {"drums": {"light_time": 0.1, "driving": 0.85, "fill": 0.05},
        "bass": {"roots_whole": 0.1, "octaves": 0.9}, "keys": {"pads": 0.1, "comping": 0.9}}


def run(planner, script, section=None):
    """script: lista de (probabilidades, energía) por compás; devuelve los planes."""
    section = section or {}
    return [planner.plan(bar, probs, energy, section.get(bar, 0.0)) for bar, (probs, energy) in enumerate(script)]


def test_parts_only_change_at_phrase_starts():
    # Jev alterna suave/fuerte cada compás: la banda no debe temblar.
    plans = run(PhrasePlanner(phrase_bars=4, margin=0.1), [(SOFT if i % 2 == 0 else LOUD, 2.0) for i in range(16)])
    for p in plans:
        if p.changed:
            assert p.bar % 4 == 0
    structural = [(p.parts["bass"], p.parts["keys"]) for p in plans]
    for start in range(0, 16, 4):
        assert len(set(structural[start:start + 4])) == 1  # un papel por frase


def test_change_follows_the_majority_of_the_phrase():
    script = [(SOFT, 1.5)] * 4 + [(LOUD, 4.0)] * 4 + [(LOUD, 4.0)] * 4
    plans = run(PhrasePlanner(phrase_bars=4), script)
    assert plans[3].parts["keys"] == "pads"
    assert plans[4].parts["keys"] == "pads"  # la frase 2 empieza con los votos de la frase 1 (suave)
    assert plans[8].changed and plans[8].parts == {"drums": "driving", "bass": "octaves", "keys": "comping"}


def test_all_musicians_change_together():
    plans = run(PhrasePlanner(phrase_bars=4), [(SOFT, 2)] * 4 + [(LOUD, 4)] * 8)
    changes = [p for p in plans if p.changed and p.reason == "phrase"]
    assert changes and set(changes[0].changed_agents) == {"drums", "bass", "keys"}


def test_minimum_phrase_length_is_configurable():
    plans = run(PhrasePlanner(phrase_bars=8), [(SOFT, 2)] * 4 + [(LOUD, 4)] * 12)
    assert [p.bar for p in plans if p.changed and p.reason] == [0, 8]


def test_clear_section_change_does_not_wait_for_the_phrase():
    script = [(SOFT, 1.5)] * 3 + [(LOUD, 4.5)] * 5
    plans = run(PhrasePlanner(phrase_bars=4), script, section={3: 0.95})
    assert plans[3].changed and plans[3].reason == "section"
    assert plans[3].phrase_pos == 0  # empieza una frase nueva ahí
    assert not any(p.changed for p in plans[4:7])  # y dura su frase completa


def test_uncertain_section_change_waits():
    plans = run(PhrasePlanner(phrase_bars=4), [(SOFT, 1.5)] * 2 + [(LOUD, 4.5)] * 2, section={2: 0.6})
    assert not plans[2].changed and not plans[3].changed


def test_energy_moves_gradually():
    plans = run(PhrasePlanner(phrase_bars=4, energy_step=0.5), [(SOFT, 1.0)] * 2 + [(LOUD, 4.0)] * 6)
    energies = [p.energy for p in plans]
    assert energies[:3] == [1.0, 1.0, 1.5]
    assert all(abs(b - a) <= 0.5 + 1e-9 for a, b in zip(energies, energies[1:]))
    assert energies[-1] == 4.0


def test_fill_is_an_ornament_before_a_change():
    plans = run(PhrasePlanner(phrase_bars=4), [(SOFT, 2)] * 4 + [(LOUD, 4)] * 8)
    assert [p.bar for p in plans if p.fill] == [7]  # último compás antes del cambio de la frase 3
    assert plans[7].parts["drums"] == "fill"
    assert all(p.parts["drums"] != "fill" for p in plans if not p.fill)


def test_jev_voting_fill_never_becomes_a_phrase_part():
    fill_heavy = {"drums": {"fill": 0.7, "groove": 0.3}, "bass": {"octaves": 1.0}, "keys": {"pads": 1.0}}
    plans = run(PhrasePlanner(phrase_bars=4), [(fill_heavy, 3)] * 8)
    assert plans[0].parts["drums"] == "groove"
    assert [p.bar for p in plans if p.fill] == [3, 7]


def test_late_decisions_keep_the_plan():
    plans = run(PhrasePlanner(phrase_bars=4), [(SOFT, 2), (None, None), (None, None), (LOUD, 4)])
    assert all(p.parts["keys"] == "pads" for p in plans)
    assert plans[1].energy == 2.0


def test_nothing_to_play_before_the_first_decision():
    p = PhrasePlanner().plan(0, None, None)
    assert p.parts == {} and p.energy == 0.0


def test_near_tie_keeps_the_current_part():
    # Jev casi empatado entre dos papeles: la banda no debe alternar frase sí, frase no.
    a = {"drums": {"light_time": 0.55, "driving": 0.45}, "bass": {"roots_whole": 1.0}, "keys": {"pads": 1.0}}
    b = {"drums": {"light_time": 0.45, "driving": 0.55}, "bass": {"roots_whole": 1.0}, "keys": {"pads": 1.0}}
    plans = run(PhrasePlanner(phrase_bars=4), [(a, 2)] * 4 + [(b, 2)] * 4 + [(a, 2)] * 4 + [(b, 2)] * 4)
    assert {p.parts["drums"] for p in plans if not p.fill} == {"light_time"}
